from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pikepdf
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from pixopdf.pdf.pdfium_renderer import PdfiumRenderer


def test_renderer_returns_decodable_png(tmp_path: Path, qapp: QApplication) -> None:
    source = tmp_path / "one-page.pdf"
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(595, 842))
    pdf.save(source)
    pdf.close()

    thumbnail = PdfiumRenderer().render_page(source, 0, 126, 164)

    assert thumbnail.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(thumbnail) > 100
    pixmap = QPixmap()
    assert pixmap.loadFromData(thumbnail)
    assert not pixmap.isNull()


def test_concurrent_requests_are_safely_serialized(tmp_path: Path) -> None:
    source = tmp_path / "multiple-pages.pdf"
    pdf = pikepdf.Pdf.new()
    for _ in range(8):
        pdf.add_blank_page(page_size=(595, 842))
    pdf.save(source)
    pdf.close()
    renderer = PdfiumRenderer()

    with ThreadPoolExecutor(max_workers=8) as executor:
        thumbnails = list(
            executor.map(
                lambda page_index: renderer.render_page(source, page_index, 126, 164),
                range(8),
            )
        )

    assert all(data.startswith(b"\x89PNG\r\n\x1a\n") for data in thumbnails)
