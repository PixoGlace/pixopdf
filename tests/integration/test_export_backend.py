from pathlib import Path

import pikepdf
import pytest

from pixopdf.commands import InsertBlankPageCommand
from pixopdf.domain.document import SourceDocument
from pixopdf.domain.project import PdfProject
from pixopdf.pdf.pikepdf_backend import PikePdfBackend


def test_export_opens_each_source_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.pdf"
    destination = tmp_path / "export.pdf"
    pdf = pikepdf.Pdf.new()
    for _ in range(3):
        pdf.add_blank_page()
    pdf.save(source)
    pdf.close()
    project = PdfProject()
    project.add_document(SourceDocument.create(source, 3))
    real_open = pikepdf.open
    opened_paths: list[Path] = []

    def tracked_open(path: Path, *args: object, **kwargs: object) -> pikepdf.Pdf:
        opened_paths.append(Path(path))
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(pikepdf, "open", tracked_open)

    PikePdfBackend().export(project, destination)

    assert opened_paths == [source]
    with real_open(destination) as exported:
        assert len(exported.pages) == 3


def test_export_project_containing_only_a_blank_page(tmp_path: Path) -> None:
    destination = tmp_path / "blank-page.pdf"
    project = PdfProject()
    InsertBlankPageCommand(
        project,
        index=0,
        page_size=(420.0, 595.0),
    ).execute()

    PikePdfBackend().export(project, destination)

    with pikepdf.open(destination) as exported:
        assert len(exported.pages) == 1
        media_box = [float(value) for value in exported.pages[0].mediabox]
        assert media_box == pytest.approx([0.0, 0.0, 420.0, 595.0])
