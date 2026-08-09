import importlib.util
from datetime import date
from io import BytesIO
from pathlib import Path

import pikepdf
import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from pixopdf.pdf.pdfium_renderer import PdfiumRenderer
from pixopdf.services.protection_service import (
    EncryptionStrength,
    ProtectionOptions,
    ProtectionPasswordError,
    ProtectionPermissions,
    ProtectionService,
    RemoveProtectionOptions,
)
from pixopdf.services.signature_service import (
    DateStampOptions,
    DigitalSignatureOptions,
    DigitalSignatureUnavailableError,
    PdfRectangle,
    SignatureError,
    SignatureService,
    VisualSignatureOptions,
)


def create_pdf(
    path: Path,
    *,
    width: float = 300,
    height: float = 400,
    page_count: int = 1,
) -> None:
    pdf = pikepdf.Pdf.new()
    for _ in range(page_count):
        pdf.add_blank_page(page_size=(width, height))
    pdf.save(path)
    pdf.close()


def count_colored_pixels(pdf_path: Path) -> int:
    rendered = PdfiumRenderer().render_page(pdf_path, 0, 300, 400)
    with Image.open(BytesIO(rendered)).convert("RGB") as image:
        return sum(
            1
            for y in range(image.height)
            for x in range(image.width)
            if min(image.getpixel((x, y))) < 225
        )


def test_protect_and_remove_password_preserve_source(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    protected = tmp_path / "protected.pdf"
    unlocked = tmp_path / "unlocked.pdf"
    create_pdf(source)
    source_bytes = source.read_bytes()
    permissions = ProtectionPermissions(
        accessibility=True,
        extract=False,
        modify_annotation=False,
        modify_assembly=False,
        modify_form=False,
        modify_other=False,
        print_lowres=True,
        print_highres=False,
    )

    result = ProtectionService().protect(
        source,
        protected,
        ProtectionOptions(
            owner_password="owner-secret",
            user_password="reader-secret",
            permissions=permissions,
            strength=EncryptionStrength.AES_256,
        ),
    )

    assert result == protected
    assert source.read_bytes() == source_bytes
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(protected)
    with pikepdf.open(protected, password="reader-secret") as secured:
        assert secured.is_encrypted
        assert secured.encryption.R == 6
        assert not secured.allow.extract
        assert not secured.allow.modify_other
        assert secured.allow.print_lowres
        assert not secured.allow.print_highres

    ProtectionService().remove_protection(
        protected,
        unlocked,
        RemoveProtectionOptions(password="owner-secret"),
    )

    with pikepdf.open(unlocked) as plain:
        assert not plain.is_encrypted
        assert len(plain.pages) == 1


def test_protection_rejects_wrong_password_without_partial_output(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    protected = tmp_path / "protected.pdf"
    destination = tmp_path / "unlocked.pdf"
    create_pdf(source)
    ProtectionService().protect(
        source,
        protected,
        ProtectionOptions(owner_password="owner", user_password="reader"),
    )
    destination.write_bytes(b"existing output")

    with pytest.raises(ProtectionPasswordError, match="incorrect"):
        ProtectionService().remove_protection(
            protected,
            destination,
            RemoveProtectionOptions(password="wrong"),
        )

    assert destination.read_bytes() == b"existing output"


def test_passwords_are_excluded_from_option_representations() -> None:
    protection = ProtectionOptions(
        owner_password="owner-secret",
        user_password="reader-secret",
        source_password="source-secret",
    )
    removal = RemoveProtectionOptions(password="removal-secret")
    digital = DigitalSignatureOptions(
        pkcs12_path=Path("certificate.p12"),
        passphrase=b"certificate-secret",
        source_password="digital-source-secret",
    )

    rendered = repr((protection, removal, digital))

    assert "owner-secret" not in rendered
    assert "reader-secret" not in rendered
    assert "source-secret" not in rendered
    assert "removal-secret" not in rendered
    assert "certificate-secret" not in rendered
    assert "digital-source-secret" not in rendered


def test_visual_signature_and_date_are_rendered_without_touching_source(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    del qapp
    source = tmp_path / "source.pdf"
    signature_image = tmp_path / "signature.png"
    destination = tmp_path / "signed-visually.pdf"
    create_pdf(source)
    source_bytes = source.read_bytes()
    image = Image.new("RGBA", (240, 80), (0, 0, 0, 0))
    for x in range(15, 225):
        y = 40 + round(18 * ((x % 35) / 35))
        for offset in range(-2, 3):
            image.putpixel((x, y + offset), (20, 184, 166, 255))
    image.save(signature_image)
    before = count_colored_pixels(source)

    SignatureService().add_visual_signature_and_date(
        source,
        destination,
        VisualSignatureOptions(
            page_index=0,
            rectangle=PdfRectangle(25, 35, 180, 60),
            image_path=signature_image,
        ),
        DateStampOptions(
            page_index=0,
            rectangle=PdfRectangle(25, 15, 180, 18),
            value=date(2026, 8, 3),
            prefix="Signé le ",
            color="#172B4D",
        ),
    )

    assert source.read_bytes() == source_bytes
    assert count_colored_pixels(destination) > before + 100
    with pikepdf.open(destination) as signed:
        assert len(signed.pages) == 1
        assert "/XObject" in signed.pages[0].resources


def test_visual_signature_validates_page_bounds_atomically(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    del qapp
    source = tmp_path / "source.pdf"
    signature_image = tmp_path / "signature.png"
    destination = tmp_path / "destination.pdf"
    create_pdf(source)
    Image.new("RGB", (20, 10), "black").save(signature_image)
    destination.write_bytes(b"existing output")

    with pytest.raises(SignatureError, match="dépasse"):
        SignatureService().add_visual_signature(
            source,
            destination,
            VisualSignatureOptions(
                page_index=0,
                rectangle=PdfRectangle(290, 390, 30, 20),
                image_path=signature_image,
            ),
        )

    assert destination.read_bytes() == b"existing output"


def test_visual_signatures_batch_applies_every_page(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    del qapp
    source = tmp_path / "source.pdf"
    signature_image = tmp_path / "signature.png"
    destination = tmp_path / "signed-pages.pdf"
    create_pdf(source, page_count=2)
    Image.new("RGBA", (80, 30), (20, 184, 166, 255)).save(signature_image)

    SignatureService().add_visual_signatures(
        source,
        destination,
        [
            VisualSignatureOptions(
                page_index=index,
                rectangle=PdfRectangle(20, 20, 100, 40),
                image_path=signature_image,
            )
            for index in range(2)
        ],
    )

    with pikepdf.open(destination) as signed:
        assert len(signed.pages) == 2
        assert all("/XObject" in page.resources for page in signed.pages)


def test_date_stamps_batch_applies_every_page(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    del qapp
    source = tmp_path / "source.pdf"
    destination = tmp_path / "dated-pages.pdf"
    create_pdf(source, page_count=2)

    SignatureService().add_date_stamps(
        source,
        destination,
        [
            DateStampOptions(
                page_index=index,
                rectangle=PdfRectangle(20, 20, 180, 25),
                value=date(2026, 8, 3 + index),
                prefix="Signé le ",
            )
            for index in range(2)
        ],
    )

    with pikepdf.open(destination) as dated:
        assert len(dated.pages) == 2
        assert all("/XObject" in page.resources for page in dated.pages)


def test_digital_signature_extra_has_an_explicit_error_when_absent(tmp_path: Path) -> None:
    if importlib.util.find_spec("pyhanko") is not None:
        pytest.skip("pyHanko is installed in this environment")
    source = tmp_path / "source.pdf"
    create_pdf(source)

    with pytest.raises(DigitalSignatureUnavailableError, match="pyHanko"):
        SignatureService().sign_digitally(
            source,
            tmp_path / "signed.pdf",
            DigitalSignatureOptions(pkcs12_path=tmp_path / "certificate.p12"),
        )


def test_digital_signature_is_the_last_atomic_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.pdf"
    destination = tmp_path / "signed.pdf"
    certificate = tmp_path / "certificate.p12"
    create_pdf(source)
    certificate.write_bytes(b"certificate")
    source_bytes = source.read_bytes()

    class FakeSimpleSigner:
        @staticmethod
        def load_pkcs12(*args: object, **kwargs: object) -> object:
            return object()

    class FakeMetadata:
        def __init__(self, *, field_name: str) -> None:
            self.field_name = field_name

    class FakePdfSigner:
        def __init__(self, metadata: object, *, signer: object, new_field_spec: object) -> None:
            del metadata, signer, new_field_spec

        def sign_pdf(
            self,
            writer: object,
            *,
            existing_fields_only: bool,
            output: object,
        ) -> None:
            del writer, existing_fields_only
            output.write(source_bytes + b"\n% cryptographic signature is final")

    class FakeSigners:
        SimpleSigner = FakeSimpleSigner
        PdfSignatureMetadata = FakeMetadata
        PdfSigner = FakePdfSigner

    monkeypatch.setattr(
        SignatureService,
        "_load_pyhanko",
        staticmethod(lambda: (FakeSigners, lambda stream: stream, lambda **kwargs: kwargs)),
    )

    SignatureService().sign_digitally(
        source,
        destination,
        DigitalSignatureOptions(pkcs12_path=certificate),
    )

    assert source.read_bytes() == source_bytes
    assert destination.read_bytes().endswith(b"% cryptographic signature is final")


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (DigitalSignatureOptions(pkcs12_path=Path("certificate.p12")), "introuvable"),
        (
            DigitalSignatureOptions(
                private_key_path=Path("private-key.pem"),
                certificate_path=Path("certificate.pem"),
            ),
            "introuvable",
        ),
    ],
)
def test_digital_signature_checks_pkcs12_and_pem_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    options: DigitalSignatureOptions,
    message: str,
) -> None:
    source = tmp_path / "source.pdf"
    create_pdf(source)
    monkeypatch.setattr(
        SignatureService,
        "_load_pyhanko",
        staticmethod(lambda: (object(), object(), object())),
    )

    with pytest.raises(SignatureError, match=message):
        SignatureService().sign_digitally(source, tmp_path / "signed.pdf", options)
