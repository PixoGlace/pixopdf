from pathlib import Path

import pikepdf
import pytest
from PIL import Image

from pixopdf.services.layout_service import (
    LayoutService,
    NUpOptions,
    PageFormat,
    PageOrientation,
    TargetFormatOptions,
    resolve_page_size,
)


def _illustrated_pdf(path: Path, page_count: int) -> None:
    colors = ["#172B4D", "#14B8A6", "#F59E0B", "#0F172A", "#CBD5E1"]
    images = [
        Image.new("RGB", (100 + index * 10, 140), colors[index % len(colors)])
        for index in range(page_count)
    ]
    try:
        images[0].save(
            path,
            format="PDF",
            save_all=True,
            append_images=images[1:],
            resolution=72,
        )
    finally:
        for image in images:
            image.close()


def _media_box(page: pikepdf.Page) -> list[float]:
    return [float(value) for value in page.mediabox]


def test_target_format_places_each_source_page_on_requested_size(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    destination = tmp_path / "formatted.pdf"
    _illustrated_pdf(source, 2)
    original = source.read_bytes()
    options = TargetFormatOptions(
        page_format=PageFormat.A5,
        orientation=PageOrientation.LANDSCAPE,
        margin_points=24.0,
    )

    result = LayoutService().apply_target_format(source, destination, options)

    assert result == destination
    expected_width, expected_height = options.page_size
    with pikepdf.open(destination) as pdf:
        assert len(pdf.pages) == 2
        for page in pdf.pages:
            assert _media_box(page) == pytest.approx([0.0, 0.0, expected_width, expected_height])
            assert len(page.form_xobjects) == 1
    assert source.read_bytes() == original


def test_n_up_groups_pages_in_top_to_bottom_row_major_sheets(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    destination = tmp_path / "n-up.pdf"
    _illustrated_pdf(source, 5)
    original = source.read_bytes()
    options = NUpOptions(
        rows=2,
        columns=2,
        page_format=PageFormat.A4,
        orientation=PageOrientation.LANDSCAPE,
        margin_points=18.0,
        gutter_points=9.0,
    )

    result = LayoutService().n_up(source, destination, options)

    assert result == destination
    with pikepdf.open(destination) as pdf:
        assert len(pdf.pages) == 2
        assert [len(page.form_xobjects) for page in pdf.pages] == [4, 1]
        assert all(
            _media_box(page)
            == pytest.approx([0.0, 0.0, options.page_size[0], options.page_size[1]])
            for page in pdf.pages
        )
    assert source.read_bytes() == original


def test_layout_rejects_in_place_transformation(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _illustrated_pdf(source, 1)
    original = source.read_bytes()

    with pytest.raises(ValueError, match="différent"):
        LayoutService().apply_target_format(source, source)
    with pytest.raises(ValueError, match="différent"):
        LayoutService().n_up(source, source)

    assert source.read_bytes() == original


@pytest.mark.parametrize(
    "factory",
    [
        lambda: TargetFormatOptions(margin_points=-1),
        lambda: TargetFormatOptions(margin_points=500),
        lambda: NUpOptions(rows=0),
        lambda: NUpOptions(rows=9, columns=8),
        lambda: NUpOptions(gutter_points=-1),
        lambda: NUpOptions(margin_points=300),
    ],
)
def test_layout_options_reject_invalid_geometry(factory: object) -> None:
    with pytest.raises(ValueError):
        factory()  # type: ignore[operator]


def test_standard_page_sizes_respect_orientation() -> None:
    portrait = resolve_page_size(PageFormat.A4, PageOrientation.PORTRAIT)
    landscape = resolve_page_size(PageFormat.A4, PageOrientation.LANDSCAPE)

    assert portrait == pytest.approx((595.28, 841.89))
    assert landscape == pytest.approx(tuple(reversed(portrait)))
