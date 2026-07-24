from pathlib import Path

import pikepdf
import pytest

from pixopdf.commands import DeletePagesCommand, InsertBlankPageCommand
from pixopdf.domain.document import SourceDocument
from pixopdf.domain.project import PdfProject
from pixopdf.pdf.exceptions import PdfExportError
from pixopdf.pdf.pikepdf_backend import PikePdfBackend
from pixopdf.services.project_service import ProjectService
from pixopdf.services.split_service import SplitStrategy, build_split_groups


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


def test_export_skips_pages_marked_as_deleted(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    destination = tmp_path / "export-with-deletion.pdf"
    pdf = pikepdf.Pdf.new()
    for _ in range(3):
        pdf.add_blank_page()
    pdf.save(source)
    pdf.close()
    project = PdfProject()
    project.add_document(SourceDocument.create(source, 3))
    DeletePagesCommand(project, [1]).execute()

    PikePdfBackend().export(project, destination)

    assert len(project.pages) == 3
    assert project.pages[1].is_deleted
    with pikepdf.open(destination) as exported:
        assert len(exported.pages) == 2


def test_export_rejects_project_with_only_deleted_pages(tmp_path: Path) -> None:
    destination = tmp_path / "empty-export.pdf"
    project = PdfProject()
    InsertBlankPageCommand(project, index=0).execute()
    DeletePagesCommand(project, [0]).execute()

    with pytest.raises(PdfExportError, match="aucune page active"):
        PikePdfBackend().export(project, destination)

    assert not destination.exists()


def test_real_backend_splits_pages_into_fixed_size_batches(tmp_path: Path) -> None:
    source = tmp_path / "batch-source.pdf"
    destination = tmp_path / "parts"
    pdf = pikepdf.Pdf.new()
    for index in range(5):
        pdf.add_blank_page(page_size=(500 + index, 700 + index))
    pdf.save(source)
    pdf.close()
    project = PdfProject()
    project.add_document(SourceDocument.create(source, 5))
    groups = build_split_groups(5, SplitStrategy.BATCH, batch_size=2)

    outputs = ProjectService(PikePdfBackend()).split(
        project,
        destination,
        groups,
        "batch-source",
    )

    assert [path.name for path in outputs] == [
        "batch-source-partie-01.pdf",
        "batch-source-partie-02.pdf",
        "batch-source-partie-03.pdf",
    ]
    page_sizes: list[list[tuple[float, float]]] = []
    for output in outputs:
        with pikepdf.open(output) as exported:
            page_sizes.append(
                [
                    (
                        float(page.mediabox[2]),
                        float(page.mediabox[3]),
                    )
                    for page in exported.pages
                ]
            )
    assert page_sizes == [
        [(500.0, 700.0), (501.0, 701.0)],
        [(502.0, 702.0), (503.0, 703.0)],
        [(504.0, 704.0)],
    ]
