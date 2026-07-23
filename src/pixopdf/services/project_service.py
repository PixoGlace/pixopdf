from pathlib import Path

from pixopdf.domain.document import SourceDocument
from pixopdf.domain.project import PdfProject
from pixopdf.pdf.backend import PdfBackend


class ProjectService:
    def __init__(self, backend: PdfBackend) -> None:
        self.backend = backend

    def import_files(self, project: PdfProject, paths: list[Path]) -> None:
        """Inspect every file first so a failed batch never leaves a partial import."""
        documents = self.inspect_files(paths)
        for document in documents:
            project.add_document(document)

    def inspect_files(self, paths: list[Path]) -> list[SourceDocument]:
        """Read source metadata without mutating a project."""
        return [SourceDocument.create(path, self.backend.page_count(path)) for path in paths]

    def export(self, project: PdfProject, destination: Path) -> None:
        self.backend.export(project, destination)
        project.modified = False
