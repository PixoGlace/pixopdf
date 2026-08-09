from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pikepdf
from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QImageReader,
    QPageLayout,
    QPageSize,
    QPainter,
    QPdfWriter,
)

from pixopdf.pdf.exceptions import PdfError

from ._atomic import atomic_output_path, ensure_distinct_paths


class SignatureError(PdfError):
    """Base error for visual and cryptographic signature operations."""


class DigitalSignatureUnavailableError(SignatureError):
    """Raised when digital-signature support is not installed."""


@dataclass(frozen=True, slots=True)
class PdfRectangle:
    """A rectangle in PDF points, measured from the page's bottom-left corner."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        if self.x < 0 or self.y < 0:
            raise ValueError("Les coordonnées de la signature doivent être positives")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("La signature doit avoir une largeur et une hauteur positives")

    def as_box(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)


@dataclass(frozen=True, slots=True)
class VisualSignatureOptions:
    page_index: int
    rectangle: PdfRectangle
    image_path: Path
    opacity: float = 1.0
    preserve_aspect_ratio: bool = True

    def __post_init__(self) -> None:
        if self.page_index < 0:
            raise ValueError("L'indice de page doit être positif")
        if not 0.0 < self.opacity <= 1.0:
            raise ValueError("L'opacité doit être comprise entre 0 et 1")


@dataclass(frozen=True, slots=True)
class DateStampOptions:
    page_index: int
    rectangle: PdfRectangle
    value: date = field(default_factory=date.today)
    date_format: str = "%Y-%m-%d"
    prefix: str = ""
    font_family: str = "Sans Serif"
    font_size: float = 10.0
    color: str = "#172B4D"
    bold: bool = False
    opacity: float = 1.0

    def __post_init__(self) -> None:
        if self.page_index < 0:
            raise ValueError("L'indice de page doit être positif")
        if self.font_size <= 0:
            raise ValueError("La taille de police doit être positive")
        if not QColor(self.color).isValid():
            raise ValueError("La couleur du tampon de date est invalide")
        if not 0.0 < self.opacity <= 1.0:
            raise ValueError("L'opacité doit être comprise entre 0 et 1")

    @property
    def text(self) -> str:
        return f"{self.prefix}{self.value.strftime(self.date_format)}"


@dataclass(frozen=True, slots=True)
class DigitalSignatureOptions:
    field_name: str = "Signature1"
    pkcs12_path: Path | None = None
    private_key_path: Path | None = None
    certificate_path: Path | None = None
    passphrase: bytes | None = field(default=None, repr=False)
    source_password: str = field(default="", repr=False)
    ca_chain_paths: tuple[Path, ...] = ()
    visible_page_index: int | None = None
    visible_rectangle: PdfRectangle | None = None
    existing_fields_only: bool = False

    def __post_init__(self) -> None:
        if not self.field_name.strip():
            raise ValueError("Le nom du champ de signature est requis")
        uses_pkcs12 = self.pkcs12_path is not None
        uses_pem = self.private_key_path is not None or self.certificate_path is not None
        if uses_pkcs12 == uses_pem:
            raise ValueError(
                "Choisissez soit un fichier PKCS#12, soit une clé et un certificat PEM"
            )
        if uses_pem and (self.private_key_path is None or self.certificate_path is None):
            raise ValueError("La clé privée et le certificat PEM sont tous les deux requis")
        has_visible_page = self.visible_page_index is not None
        has_visible_rectangle = self.visible_rectangle is not None
        if has_visible_page != has_visible_rectangle:
            raise ValueError(
                "La page et la zone de signature visible doivent être fournies ensemble"
            )
        if self.visible_page_index is not None and self.visible_page_index < 0:
            raise ValueError("L'indice de page doit être positif")


@dataclass(frozen=True, slots=True)
class _ImageOverlay:
    page_index: int
    rectangle: PdfRectangle
    image_path: Path
    opacity: float
    preserve_aspect_ratio: bool


@dataclass(frozen=True, slots=True)
class _TextOverlay:
    page_index: int
    rectangle: PdfRectangle
    text: str
    font_family: str
    font_size: float
    color: str
    bold: bool
    opacity: float


type _VisualOverlay = _ImageOverlay | _TextOverlay


class SignatureService:
    """Add visual stamps or a final cryptographic signature to a PDF copy."""

    def add_visual_signature(
        self,
        source: Path,
        destination: Path,
        options: VisualSignatureOptions,
        *,
        source_password: str = "",
    ) -> Path:
        overlay = _ImageOverlay(
            page_index=options.page_index,
            rectangle=options.rectangle,
            image_path=options.image_path,
            opacity=options.opacity,
            preserve_aspect_ratio=options.preserve_aspect_ratio,
        )
        return self._apply_visual_overlays(
            source,
            destination,
            [overlay],
            source_password=source_password,
        )

    def add_visual_signatures(
        self,
        source: Path,
        destination: Path,
        options: Sequence[VisualSignatureOptions],
        *,
        source_password: str = "",
    ) -> Path:
        overlays = [
            _ImageOverlay(
                page_index=option.page_index,
                rectangle=option.rectangle,
                image_path=option.image_path,
                opacity=option.opacity,
                preserve_aspect_ratio=option.preserve_aspect_ratio,
            )
            for option in options
        ]
        return self._apply_visual_overlays(
            source,
            destination,
            overlays,
            source_password=source_password,
        )

    def add_date_stamp(
        self,
        source: Path,
        destination: Path,
        options: DateStampOptions,
        *,
        source_password: str = "",
    ) -> Path:
        overlay = _TextOverlay(
            page_index=options.page_index,
            rectangle=options.rectangle,
            text=options.text,
            font_family=options.font_family,
            font_size=options.font_size,
            color=options.color,
            bold=options.bold,
            opacity=options.opacity,
        )
        return self._apply_visual_overlays(
            source,
            destination,
            [overlay],
            source_password=source_password,
        )

    def add_date_stamps(
        self,
        source: Path,
        destination: Path,
        options: Sequence[DateStampOptions],
        *,
        source_password: str = "",
    ) -> Path:
        overlays = [
            _TextOverlay(
                page_index=option.page_index,
                rectangle=option.rectangle,
                text=option.text,
                font_family=option.font_family,
                font_size=option.font_size,
                color=option.color,
                bold=option.bold,
                opacity=option.opacity,
            )
            for option in options
        ]
        return self._apply_visual_overlays(
            source,
            destination,
            overlays,
            source_password=source_password,
        )

    def add_visual_signature_and_date(
        self,
        source: Path,
        destination: Path,
        signature: VisualSignatureOptions,
        date_stamp: DateStampOptions,
        *,
        source_password: str = "",
    ) -> Path:
        overlays: list[_VisualOverlay] = [
            _ImageOverlay(
                signature.page_index,
                signature.rectangle,
                signature.image_path,
                signature.opacity,
                signature.preserve_aspect_ratio,
            ),
            _TextOverlay(
                date_stamp.page_index,
                date_stamp.rectangle,
                date_stamp.text,
                date_stamp.font_family,
                date_stamp.font_size,
                date_stamp.color,
                date_stamp.bold,
                date_stamp.opacity,
            ),
        ]
        return self._apply_visual_overlays(
            source,
            destination,
            overlays,
            source_password=source_password,
        )

    def sign_digitally(
        self,
        source: Path,
        destination: Path,
        options: DigitalSignatureOptions,
    ) -> Path:
        """Apply a digital signature as the final write operation.

        The resulting file must not be saved through pikepdf afterwards, since any
        subsequent byte-level change would invalidate the signature.
        """
        self._validate_paths(source, destination)
        signers, incremental_writer, sig_field_spec = self._load_pyhanko()
        self._validate_key_files(options)
        try:
            source_is_encrypted = self._is_encrypted(source, options.source_password)
            signer = self._load_signer(signers, options)
            if signer is None:
                raise SignatureError("Impossible de charger la clé et le certificat de signature")

            metadata = signers.PdfSignatureMetadata(field_name=options.field_name)
            field_spec = None
            if options.visible_page_index is not None and options.visible_rectangle is not None:
                field_spec = sig_field_spec(
                    sig_field_name=options.field_name,
                    on_page=options.visible_page_index,
                    box=options.visible_rectangle.as_box(),
                )
            pdf_signer = signers.PdfSigner(
                metadata,
                signer=signer,
                new_field_spec=field_spec,
            )
            with (
                source.open("rb") as source_stream,
                atomic_output_path(destination) as temporary,
                temporary.open("w+b") as output_stream,
            ):
                writer = incremental_writer(source_stream)
                if source_is_encrypted:
                    # pyHanko's incremental writer keeps the original encryption
                    # settings while authorising this final signed revision.
                    writer.encrypt(options.source_password)
                pdf_signer.sign_pdf(
                    writer,
                    existing_fields_only=options.existing_fields_only,
                    output=output_stream,
                )
        except SignatureError:
            raise
        except Exception as exc:
            raise SignatureError("La signature numérique du PDF a échoué") from exc
        return destination

    def _apply_visual_overlays(
        self,
        source: Path,
        destination: Path,
        overlays: Sequence[_VisualOverlay],
        *,
        source_password: str,
    ) -> Path:
        self._validate_paths(source, destination)
        if not overlays:
            raise ValueError("Au moins une signature ou un tampon est requis")
        grouped: dict[int, list[_VisualOverlay]] = defaultdict(list)
        for overlay in overlays:
            grouped[overlay.page_index].append(overlay)

        try:
            with (
                pikepdf.open(source, password=source_password) as pdf,
                atomic_output_path(destination) as temporary,
                TemporaryDirectory(
                    prefix=".pixopdf-signature-",
                    dir=destination.parent,
                ) as overlay_directory,
            ):
                self._validate_overlay_pages(pdf, grouped)
                root = Path(overlay_directory)
                for page_index, page_overlays in grouped.items():
                    page = pdf.pages[page_index]
                    media_box = [float(value) for value in page.mediabox]
                    page_width = media_box[2] - media_box[0]
                    page_height = media_box[3] - media_box[1]
                    self._validate_overlay_rectangles(
                        page_overlays,
                        page_width,
                        page_height,
                    )
                    overlay_path = root / f"page-{page_index}.pdf"
                    self._render_overlay_pdf(
                        overlay_path,
                        page_width,
                        page_height,
                        page_overlays,
                    )
                    with pikepdf.open(overlay_path) as overlay_pdf:
                        page.add_overlay(overlay_pdf.pages[0], None)
                if pdf.is_encrypted:
                    pdf.save(temporary, encryption=True)
                else:
                    pdf.save(temporary)
        except pikepdf.PasswordError as exc:
            raise SignatureError("Le mot de passe du document source est incorrect") from exc
        except (pikepdf.PdfError, OSError) as exc:
            raise SignatureError("Impossible d'ajouter la signature visuelle au PDF") from exc
        return destination

    @staticmethod
    def _render_overlay_pdf(
        destination: Path,
        page_width: float,
        page_height: float,
        overlays: Sequence[_VisualOverlay],
    ) -> None:
        writer = QPdfWriter(str(destination))
        writer.setResolution(72)
        writer.setPageSize(
            QPageSize(
                QSizeF(page_width, page_height),
                QPageSize.Unit.Point,
                "PixoPDF overlay",
            )
        )
        writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Point)
        painter = QPainter(writer)
        if not painter.isActive():
            raise SignatureError("Impossible de préparer la signature visuelle")
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            for overlay in overlays:
                rectangle = SignatureService._qt_rectangle(
                    overlay.rectangle,
                    page_height,
                )
                painter.save()
                painter.setOpacity(overlay.opacity)
                if isinstance(overlay, _ImageOverlay):
                    image = SignatureService._load_image(overlay.image_path)
                    target = (
                        SignatureService._fit_rectangle(rectangle, image)
                        if overlay.preserve_aspect_ratio
                        else rectangle
                    )
                    painter.drawImage(target, image)
                else:
                    font = QFont(overlay.font_family)
                    font.setPointSizeF(overlay.font_size)
                    font.setBold(overlay.bold)
                    painter.setFont(font)
                    painter.setPen(QColor(overlay.color))
                    painter.drawText(
                        rectangle,
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                        overlay.text,
                    )
                painter.restore()
        finally:
            painter.end()

    @staticmethod
    def _load_image(path: Path) -> QImage:
        if not path.is_file():
            raise SignatureError(f"Image de signature introuvable : {path.name}")
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            raise SignatureError(f"Format d'image de signature non pris en charge : {path.name}")
        return image

    @staticmethod
    def _qt_rectangle(rectangle: PdfRectangle, page_height: float) -> QRectF:
        return QRectF(
            rectangle.x,
            page_height - rectangle.y - rectangle.height,
            rectangle.width,
            rectangle.height,
        )

    @staticmethod
    def _fit_rectangle(rectangle: QRectF, image: QImage) -> QRectF:
        scale = min(rectangle.width() / image.width(), rectangle.height() / image.height())
        width = image.width() * scale
        height = image.height() * scale
        return QRectF(
            rectangle.x() + (rectangle.width() - width) / 2,
            rectangle.y() + (rectangle.height() - height) / 2,
            width,
            height,
        )

    @staticmethod
    def _validate_overlay_pages(
        pdf: pikepdf.Pdf,
        grouped: dict[int, list[_VisualOverlay]],
    ) -> None:
        invalid = [index for index in grouped if index < 0 or index >= len(pdf.pages)]
        if invalid:
            raise SignatureError("La page choisie pour la signature n'existe pas")

    @staticmethod
    def _validate_overlay_rectangles(
        overlays: Sequence[_VisualOverlay],
        page_width: float,
        page_height: float,
    ) -> None:
        for overlay in overlays:
            rectangle = overlay.rectangle
            outside_width = rectangle.x + rectangle.width > page_width
            outside_height = rectangle.y + rectangle.height > page_height
            if outside_width or outside_height:
                raise SignatureError("La signature dépasse les limites de la page")

    @staticmethod
    def _validate_paths(source: Path, destination: Path) -> None:
        if not source.is_file():
            raise SignatureError(f"Fichier PDF introuvable : {source.name}")
        ensure_distinct_paths(source, destination)

    @staticmethod
    def _validate_key_files(options: DigitalSignatureOptions) -> None:
        paths = [*options.ca_chain_paths]
        if options.pkcs12_path is not None:
            paths.append(options.pkcs12_path)
        else:
            if options.private_key_path is not None:
                paths.append(options.private_key_path)
            if options.certificate_path is not None:
                paths.append(options.certificate_path)
        missing = [path.name for path in paths if not path.is_file()]
        if missing:
            raise SignatureError("Fichier de signature introuvable : " + ", ".join(missing))

    @staticmethod
    def _is_encrypted(source: Path, password: str) -> bool:
        try:
            with pikepdf.open(source, password=password) as pdf:
                return pdf.is_encrypted
        except pikepdf.PasswordError as exc:
            raise SignatureError("Le mot de passe du document source est incorrect") from exc
        except (pikepdf.PdfError, OSError) as exc:
            raise SignatureError("Impossible de lire le document à signer") from exc

    @staticmethod
    def _load_pyhanko() -> tuple[Any, Any, Any]:
        try:
            from pyhanko.pdf_utils.incremental_writer import (
                IncrementalPdfFileWriter,
            )
            from pyhanko.sign import signers
            from pyhanko.sign.fields import SigFieldSpec
        except ImportError as exc:
            raise DigitalSignatureUnavailableError(
                "La signature numérique nécessite pyHanko. Réinstallez les dépendances "
                "avec « poetry install » puis relancez PixoPDF."
            ) from exc
        return signers, IncrementalPdfFileWriter, SigFieldSpec

    @staticmethod
    def _load_signer(signers: Any, options: DigitalSignatureOptions) -> Any:
        chain = tuple(str(path) for path in options.ca_chain_paths)
        if options.pkcs12_path is not None:
            return signers.SimpleSigner.load_pkcs12(
                str(options.pkcs12_path),
                ca_chain_files=chain,
                passphrase=options.passphrase,
            )
        return signers.SimpleSigner.load(
            str(options.private_key_path),
            str(options.certificate_path),
            ca_chain_files=chain,
            key_passphrase=options.passphrase,
        )
