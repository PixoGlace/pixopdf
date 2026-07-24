import os
import tempfile
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

    def split(
        self,
        project: PdfProject,
        destination: Path,
        groups: list[list[int]],
        base_name: str,
    ) -> list[Path]:
        """Export page groups without overwriting existing files."""
        active_pages = project.active_pages
        if not groups or any(
            not group or any(index < 0 or index >= len(active_pages) for index in group)
            for group in groups
        ):
            raise ValueError("Le plan de division ne correspond pas aux pages du projet")
        destination.mkdir(parents=True, exist_ok=True)
        width = max(2, len(str(len(groups))))
        outputs = [
            destination / f"{base_name}-partie-{part:0{width}d}.pdf"
            for part in range(1, len(groups) + 1)
        ]
        collisions = [path.name for path in outputs if path.exists()]
        if collisions:
            raise FileExistsError(
                "La division n’a pas démarré car ces fichiers existent déjà : "
                + ", ".join(collisions[:3])
            )

        moved_outputs: list[Path] = []
        try:
            with tempfile.TemporaryDirectory(
                prefix=".pixopdf-split-",
                dir=destination,
            ) as temporary_directory:
                temporary_root = Path(temporary_directory)
                temporary_outputs: list[Path] = []
                for output, group in zip(outputs, groups, strict=True):
                    temporary_output = temporary_root / output.name
                    split_project = PdfProject(
                        documents=dict(project.documents),
                        pages=[active_pages[index] for index in group],
                        modified=False,
                    )
                    self.backend.export(split_project, temporary_output)
                    temporary_outputs.append(temporary_output)
                for temporary_output, output in zip(
                    temporary_outputs,
                    outputs,
                    strict=True,
                ):
                    os.replace(temporary_output, output)
                    moved_outputs.append(output)
        except Exception:
            for output in moved_outputs:
                output.unlink(missing_ok=True)
            raise
        return outputs
