from contextlib import suppress
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from pixopdf.pdf.renderer import PdfRenderer

ThumbnailKey = tuple[Path, int, int]


class ThumbnailSignals(QObject):
    finished = Signal(object, bytes)
    failed = Signal(object, str)


class ThumbnailTask(QRunnable):
    """Render one thumbnail away from the UI thread."""

    def __init__(
        self,
        renderer: PdfRenderer,
        key: ThumbnailKey,
        width: int = 180,
        height: int = 234,
    ) -> None:
        super().__init__()
        self.renderer = renderer
        self.key = key
        self.width = width
        self.height = height
        self.signals = ThumbnailSignals()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        if self._cancelled:
            return
        path, page_index, _rotation = self.key
        try:
            data = self.renderer.render_page(path, page_index, self.width, self.height)
        except Exception as exc:
            if not self._cancelled:
                with suppress(RuntimeError):
                    self.signals.failed.emit(self.key, str(exc))
        else:
            if not self._cancelled:
                with suppress(RuntimeError):
                    self.signals.finished.emit(self.key, data)
