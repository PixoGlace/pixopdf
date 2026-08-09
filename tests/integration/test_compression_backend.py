from pathlib import Path

import pikepdf
import pytest
from PIL import Image

from pixopdf.pdf.pdfium_renderer import PdfiumRenderer
from pixopdf.services.compression_service import (
    MAX_TARGET_ITERATIONS,
    CompressionMode,
    CompressionOptions,
    CompressionProfile,
    CompressionService,
)


def create_image_heavy_pdf(path: Path, *, pages: int = 1) -> None:
    raw_path = path.with_name(f"{path.stem}-raw.pdf")
    images: list[Image.Image] = []
    try:
        for index in range(pages):
            noise = Image.effect_noise((1200, 1600), 96 + index * 3).convert("RGB")
            images.append(noise)
        images[0].save(
            raw_path,
            format="PDF",
            save_all=True,
            append_images=images[1:],
            resolution=150,
            quality=96,
        )
    finally:
        for image in images:
            image.close()

    with pikepdf.open(raw_path) as pdf:
        font = pdf.make_indirect(
            pikepdf.Dictionary(
                Type=pikepdf.Name.Font,
                Subtype=pikepdf.Name.Type1,
                BaseFont=pikepdf.Name.Helvetica,
            )
        )
        for page in pdf.pages:
            resources = page.obj["/Resources"]
            fonts = resources.get("/Font")
            if fonts is None:
                fonts = pikepdf.Dictionary()
                resources["/Font"] = fonts
            fonts["/F1"] = font
            vector_and_text = pdf.make_stream(
                b"q 0 0.6 0.5 rg 20 20 100 45 re f Q "
                b"BT /F1 14 Tf 30 80 Td (PixoPDF vector text) Tj ET"
            )
            contents = page.obj["/Contents"]
            page.obj["/Contents"] = pikepdf.Array([contents, vector_and_text])
        pdf.save(path)
    raw_path.unlink()


def content_bytes(path: Path) -> bytes:
    with pikepdf.open(path) as pdf:
        page = pdf.pages[0]
        contents = page.obj["/Contents"]
        streams = list(contents) if isinstance(contents, pikepdf.Array) else [contents]
        return b"\n".join(stream.read_bytes() for stream in streams)


@pytest.mark.parametrize("profile", list(CompressionProfile))
def test_profiles_keep_pdf_valid_source_untouched_and_vector_content(
    tmp_path: Path,
    profile: CompressionProfile,
) -> None:
    source = tmp_path / "source.pdf"
    destination = tmp_path / f"{profile.value}.pdf"
    create_image_heavy_pdf(source)
    original = source.read_bytes()

    result = CompressionService().compress(
        source,
        destination,
        CompressionOptions.for_profile(profile),
    )

    assert source.read_bytes() == original
    assert result.mode is CompressionMode.PROFILE
    assert result.profile is profile
    assert result.compressed_size == destination.stat().st_size
    assert result.compressed_size <= result.original_size
    assert result.target_reached
    assert result.iterations == 1
    assert result.preserved_text_and_vectors
    assert not result.rasterized
    assert b"PixoPDF vector text" in content_bytes(destination)
    with pikepdf.open(destination) as compressed:
        assert len(compressed.pages) == 1
        assert "/Font" in compressed.pages[0].obj["/Resources"]
    assert PdfiumRenderer().render_page(destination, 0, 180, 234).startswith(b"\x89PNG")


def test_target_mode_selects_quality_and_resolution_automatically(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    maximum_output = tmp_path / "maximum.pdf"
    destination = tmp_path / "target.pdf"
    create_image_heavy_pdf(source)
    source_size = source.stat().st_size
    maximum = CompressionService().compress(
        source,
        maximum_output,
        CompressionOptions.for_profile(CompressionProfile.MAXIMUM),
    )
    assert maximum.compressed_size < source_size
    target = min(source_size - 1, maximum.compressed_size + 2_000)

    result = CompressionService().compress(
        source,
        destination,
        CompressionOptions.for_target_bytes(target),
    )

    assert result.target_reached
    assert result.compressed_size <= target
    assert 1 <= result.iterations <= MAX_TARGET_ITERATIONS
    assert result.applied_dpi is not None
    assert result.applied_jpeg_quality is not None
    assert result.preserved_text_and_vectors
    assert not result.rasterized
    assert result.warning is None
    assert b"PixoPDF vector text" in content_bytes(destination)


def test_advanced_dpi_mode_uses_the_selected_resolution(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    destination = tmp_path / "advanced.pdf"
    create_image_heavy_pdf(source)

    result = CompressionService().compress(
        source,
        destination,
        CompressionOptions.for_advanced(dpi=96),
    )

    assert result.mode is CompressionMode.ADVANCED
    assert result.target_size_bytes is None
    assert result.applied_dpi == 96
    assert result.applied_jpeg_quality == 82
    assert result.preserved_text_and_vectors
    assert not result.rasterized
    assert b"PixoPDF vector text" in content_bytes(destination)


def test_impossibly_low_target_uses_bounded_raster_fallback_and_warns(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    destination = tmp_path / "tiny-target.pdf"
    create_image_heavy_pdf(source, pages=2)
    original = source.read_bytes()

    result = CompressionService().compress(
        source,
        destination,
        CompressionOptions.for_target_bytes(256, allow_raster_fallback=True),
    )

    assert source.read_bytes() == original
    assert not result.target_reached
    assert result.iterations == MAX_TARGET_ITERATIONS
    assert result.rasterized
    assert not result.preserved_text_and_vectors
    assert result.applied_dpi is not None and result.applied_dpi >= 72
    assert result.applied_jpeg_quality is not None and result.applied_jpeg_quality >= 35
    assert result.warning is not None
    assert "rasterisation" in result.warning
    assert "n’a pas pu être atteinte" in result.warning
    assert "72 ppp" in result.warning
    with pikepdf.open(source) as original_pdf, pikepdf.open(destination) as compressed:
        assert len(compressed.pages) == 2
        original_box = [float(value) for value in original_pdf.pages[0].mediabox]
        compressed_box = [float(value) for value in compressed.pages[0].mediabox]
        assert compressed_box == pytest.approx(original_box, abs=1.0)
    assert PdfiumRenderer().render_page(destination, 1, 180, 234).startswith(b"\x89PNG")
