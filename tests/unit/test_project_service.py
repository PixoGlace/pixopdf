from pathlib import Path

import pytest

from pixopdf.domain.project import PdfProject
from pixopdf.pdf.backend import PdfBackend
from pixopdf.pdf.exceptions import PdfOpenError
from pixopdf.services.project_service import ProjectService


class MetadataBackend(PdfBackend):
    def page_count(self, path: Path) -> int:
        if path.name == "broken.pdf":
            raise PdfOpenError("PDF illisible")
        return 2

    def export(self, project: PdfProject, destination: Path) -> None:
        raise NotImplementedError


def test_batch_import_is_transactional() -> None:
    project = PdfProject()
    service = ProjectService(MetadataBackend())

    with pytest.raises(PdfOpenError):
        service.import_files(project, [Path("valid.pdf"), Path("broken.pdf")])

    assert project.documents == {}
    assert project.pages == []
