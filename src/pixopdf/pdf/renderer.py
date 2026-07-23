from abc import ABC, abstractmethod
from pathlib import Path


class PdfRenderer(ABC):
    @abstractmethod
    def render_page(self, file_path: Path, page_index: int, width: int, height: int) -> bytes: ...
