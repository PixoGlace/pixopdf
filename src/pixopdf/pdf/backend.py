from abc import ABC, abstractmethod
from pathlib import Path

from pixopdf.domain.project import PdfProject


class PdfBackend(ABC):
    @abstractmethod
    def page_count(self, path: Path) -> int: ...
    @abstractmethod
    def export(self, project: PdfProject, destination: Path) -> None: ...
