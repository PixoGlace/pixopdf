from io import BytesIO
from pathlib import Path
from threading import Lock

import pypdfium2 as pdfium  # type: ignore[import-untyped]

from .exceptions import PdfRenderError
from .renderer import PdfRenderer

# PDFium keeps process-wide mutable state (fonts, colorspaces and caches) and is
# not safe when separate documents are rendered concurrently. Serializing every
# PDFium call prevents native crashes that Python exceptions cannot catch.
_PDFIUM_RENDER_LOCK = Lock()


class PdfiumRenderer(PdfRenderer):
    def render_page(self, file_path: Path, page_index: int, width: int, height: int) -> bytes:
        """Render a page as PNG bytes suitable for Qt, web or disk caches."""
        try:
            with _PDFIUM_RENDER_LOCK:
                pdf = pdfium.PdfDocument(file_path)
                try:
                    page = pdf[page_index]
                    try:
                        scale = min(width / page.get_width(), height / page.get_height())
                        bitmap = page.render(scale=scale)
                        try:
                            image = bitmap.to_pil().convert("RGBA")
                            try:
                                buffer = BytesIO()
                                image.save(buffer, format="PNG")
                                return buffer.getvalue()
                            finally:
                                image.close()
                        finally:
                            bitmap.close()
                    finally:
                        page.close()
                finally:
                    pdf.close()
        except Exception as exc:
            raise PdfRenderError("Impossible de générer la miniature") from exc
