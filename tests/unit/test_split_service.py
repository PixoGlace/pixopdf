from pathlib import Path

import pytest

from pixopdf.commands import DeletePagesCommand
from pixopdf.domain.page import PageReference
from pixopdf.domain.project import PdfProject
from pixopdf.pdf.backend import PdfBackend
from pixopdf.services.project_service import ProjectService
from pixopdf.services.split_service import SplitStrategy, build_split_groups


class RecordingBackend(PdfBackend):
    def __init__(self) -> None:
        self.exported_numbers: list[list[int]] = []

    def page_count(self, path: Path) -> int:
        return 0

    def export(self, project: PdfProject, destination: Path) -> None:
        self.exported_numbers.append([page.stable_number for page in project.pages])
        destination.write_bytes(b"%PDF-split")


def blank_project(count: int) -> PdfProject:
    project = PdfProject()
    project.pages.extend(PageReference.blank(stable_number=index) for index in range(1, count + 1))
    return project


def test_build_split_groups_for_each_page_and_batches() -> None:
    assert build_split_groups(4, SplitStrategy.EACH_PAGE) == [[0], [1], [2], [3]]
    assert build_split_groups(5, SplitStrategy.BATCH, batch_size=2) == [
        [0, 1],
        [2, 3],
        [4],
    ]


def test_build_split_groups_from_custom_ranges() -> None:
    assert build_split_groups(
        8,
        SplitStrategy.RANGES,
        ranges="1-3; 4, 6; 7-8",
    ) == [
        [0, 1, 2],
        [3, 5],
        [6, 7],
    ]


@pytest.mark.parametrize(
    ("page_count", "strategy", "batch_size", "ranges", "message"),
    [
        (0, SplitStrategy.EACH_PAGE, 1, "", "Aucune page active"),
        (3, SplitStrategy.BATCH, 0, "", "supérieur à zéro"),
        (3, SplitStrategy.RANGES, 1, "", "plages"),
        (3, SplitStrategy.RANGES, 1, "1-4", "dépasse"),
        (3, SplitStrategy.RANGES, 1, "1-2;", "point-virgule"),
    ],
)
def test_build_split_groups_rejects_invalid_settings(
    page_count: int,
    strategy: SplitStrategy,
    batch_size: int,
    ranges: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        build_split_groups(
            page_count,
            strategy,
            batch_size=batch_size,
            ranges=ranges,
        )


def test_project_service_splits_active_pages_without_overwriting(
    tmp_path: Path,
) -> None:
    backend = RecordingBackend()
    service = ProjectService(backend)
    project = blank_project(5)
    DeletePagesCommand(project, [1]).execute()
    groups = build_split_groups(
        project.active_page_count,
        SplitStrategy.BATCH,
        batch_size=2,
    )

    outputs = service.split(project, tmp_path, groups, "rapport")

    assert [path.name for path in outputs] == [
        "rapport-partie-01.pdf",
        "rapport-partie-02.pdf",
    ]
    assert all(path.read_bytes() == b"%PDF-split" for path in outputs)
    assert backend.exported_numbers == [[1, 3], [4, 5]]
    assert len(project.pages) == 5
    assert project.pages[1].is_deleted

    with pytest.raises(FileExistsError, match="existent déjà"):
        service.split(project, tmp_path, groups, "rapport")
