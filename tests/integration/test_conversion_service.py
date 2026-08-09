from pathlib import Path

import pikepdf
import pytest
from PIL import Image

from pixopdf.services.conversion_service import (
    ConversionService,
    ExtractImagesOptions,
    ImagesToPdfOptions,
    PdfToImagesOptions,
    RasterImageFormat,
)


def _blank_pdf(path: Path, page_sizes: list[tuple[float, float]]) -> None:
    pdf = pikepdf.Pdf.new()
    for page_size in page_sizes:
        pdf.add_blank_page(page_size=page_size)
    pdf.save(path)
    pdf.close()


def _image(path: Path, mode: str, color: object, size: tuple[int, int]) -> None:
    with Image.new(mode, size, color) as image:
        image.save(path)


def _repeated_image_pdf(path: Path) -> None:
    first = Image.new("RGB", (40, 30), "#14B8A6")
    second = first.copy()
    try:
        first.save(path, format="PDF", save_all=True, append_images=[second], resolution=72)
    finally:
        first.close()
        second.close()


def test_pdf_to_images_exports_every_page_without_touching_source(tmp_path: Path) -> None:
    source = tmp_path / "document.pdf"
    _blank_pdf(source, [(72.0, 144.0), (144.0, 72.0)])
    original = source.read_bytes()
    service = ConversionService()

    png_outputs = service.pdf_to_images(
        source,
        tmp_path / "png",
        PdfToImagesOptions(image_format=RasterImageFormat.PNG, dpi=72),
    )
    jpeg_outputs = service.pdf_to_images(
        source,
        tmp_path / "jpeg",
        PdfToImagesOptions(image_format=RasterImageFormat.JPEG, dpi=72, jpeg_quality=80),
    )

    assert [path.name for path in png_outputs] == [
        "document-page-001.png",
        "document-page-002.png",
    ]
    assert [path.name for path in jpeg_outputs] == [
        "document-page-001.jpg",
        "document-page-002.jpg",
    ]
    with Image.open(png_outputs[0]) as first, Image.open(png_outputs[1]) as second:
        assert first.size == (72, 144)
        assert second.size == (144, 72)
        assert first.format == "PNG"
    with Image.open(jpeg_outputs[0]) as jpeg:
        assert jpeg.format == "JPEG"
    assert source.read_bytes() == original


def test_pdf_to_images_detects_all_collisions_before_publication(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    destination = tmp_path / "renders"
    destination.mkdir()
    collision = destination / "source-page-002.png"
    collision.write_bytes(b"keep-me")
    _blank_pdf(source, [(72.0, 72.0), (72.0, 72.0)])

    with pytest.raises(FileExistsError, match="existent déjà"):
        ConversionService().pdf_to_images(
            source,
            destination,
            PdfToImagesOptions(dpi=72),
        )

    assert not (destination / "source-page-001.png").exists()
    assert collision.read_bytes() == b"keep-me"


def test_images_to_pdf_flattens_alpha_and_preserves_inputs(tmp_path: Path) -> None:
    first = tmp_path / "transparent.png"
    second = tmp_path / "photo.jpg"
    destination = tmp_path / "images.pdf"
    _image(first, "RGBA", (20, 80, 160, 100), (120, 60))
    _image(second, "RGB", "#F59E0B", (60, 120))
    originals = [first.read_bytes(), second.read_bytes()]

    result = ConversionService().images_to_pdf(
        [first, second],
        destination,
        ImagesToPdfOptions(dpi=72, background_color=(255, 255, 255)),
    )

    assert result == destination
    with pikepdf.open(destination) as pdf:
        assert len(pdf.pages) == 2
        assert [len(page.get_images()) for page in pdf.pages] == [1, 1]
    assert [first.read_bytes(), second.read_bytes()] == originals


def test_images_to_pdf_rejects_an_input_as_destination(tmp_path: Path) -> None:
    source = tmp_path / "image.png"
    _image(source, "RGB", "white", (20, 20))
    original = source.read_bytes()

    with pytest.raises(ValueError, match="différent"):
        ConversionService().images_to_pdf([source], source)

    assert source.read_bytes() == original


def test_extract_images_supports_recursive_deduplication(tmp_path: Path) -> None:
    source = tmp_path / "illustrated.pdf"
    _repeated_image_pdf(source)
    original = source.read_bytes()
    service = ConversionService()

    deduplicated = service.extract_images(source, tmp_path / "unique")
    all_images = service.extract_images(
        source,
        tmp_path / "all",
        ExtractImagesOptions(deduplicate=False),
    )

    assert len(deduplicated) == 1
    assert len(all_images) == 2
    assert all(path.suffix in {".jpg", ".jp2", ".png", ".tif", ".tiff"} for path in all_images)
    with Image.open(deduplicated[0]) as image:
        assert image.size == (40, 30)
    assert source.read_bytes() == original


@pytest.mark.parametrize(
    "options",
    [
        PdfToImagesOptions,
        ImagesToPdfOptions,
    ],
)
def test_conversion_options_reject_invalid_resolution(options: type[object]) -> None:
    with pytest.raises(ValueError, match="résolution"):
        options(dpi=10)  # type: ignore[call-arg]
