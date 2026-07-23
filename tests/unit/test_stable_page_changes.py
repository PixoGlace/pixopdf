from pathlib import Path

from pixopdf.commands import (
    CommandStack,
    DuplicatePagesCommand,
    InsertBlankPageCommand,
    MovePagesCommand,
    ReorderPagesCommand,
    RotatePagesCommand,
)
from pixopdf.domain.document import SourceDocument
from pixopdf.domain.page import PageChange, PageReference
from pixopdf.domain.project import PdfProject


def project_with_pages(count: int = 3) -> PdfProject:
    project = PdfProject()
    project.add_document(SourceDocument.create(Path("first.pdf"), count))
    return project


def test_imported_pages_keep_global_monotonic_numbers() -> None:
    project = project_with_pages(2)
    project.add_document(SourceDocument.create(Path("second.pdf"), 2))

    assert [page.stable_number for page in project.pages] == [1, 2, 3, 4]
    assert all(page.changes is PageChange.NONE for page in project.pages)


def test_ensure_page_numbers_normalises_direct_and_conflicting_pages() -> None:
    project = PdfProject()
    first = PageReference.blank(stable_number=7)
    project.pages.extend(
        [
            first,
            PageReference.blank(),
            PageReference.blank(stable_number=7),
        ]
    )

    project.ensure_page_numbers()
    assigned = [page.stable_number for page in project.pages]

    assert assigned == [7, 8, 9]
    project.ensure_page_numbers()
    assert [page.stable_number for page in project.pages] == assigned
    assert project.allocate_stable_number() == 10


def test_duplicate_and_blank_get_new_stable_numbers_and_added_state() -> None:
    project = project_with_pages(2)
    duplicate = DuplicatePagesCommand(project, [0])
    duplicate.execute()
    blank = InsertBlankPageCommand(project, len(project.pages))
    blank.execute()

    assert [page.stable_number for page in project.pages] == [1, 3, 2, 4]
    assert project.pages[1].changes == PageChange.ADDED
    assert project.pages[-1].changes == PageChange.ADDED

    duplicate.undo()
    another_blank = InsertBlankPageCommand(project, len(project.pages))
    another_blank.execute()
    assert another_blank._pages[0].stable_number == 5


def test_rotation_sets_and_clears_modified_and_undo_restores_flags() -> None:
    project = project_with_pages(1)
    stack = CommandStack()

    stack.execute(RotatePagesCommand(project, [0], 90))
    assert project.pages[0].changes == PageChange.MODIFIED
    stack.undo()
    assert project.pages[0].changes == PageChange.NONE

    stack.redo()
    stack.execute(RotatePagesCommand(project, [0], -90))
    assert project.pages[0].rotation == 0
    assert project.pages[0].changes == PageChange.NONE
    stack.undo()
    assert project.pages[0].rotation == 90
    assert project.pages[0].changes == PageChange.MODIFIED


def test_reorder_marks_explicit_pages_and_undo_restores_order_and_flags() -> None:
    project = project_with_pages(3)
    original = list(project.pages)
    moved_id = original[0].id
    command = ReorderPagesCommand(
        project,
        [original[1].id, original[2].id, moved_id],
        moved_ids={moved_id},
    )

    command.execute()

    assert [page.stable_number for page in project.pages] == [2, 3, 1]
    assert project.pages[-1].changes == PageChange.MOVED
    assert all(page.changes == PageChange.NONE for page in project.pages[:-1])

    command.undo()
    assert project.pages == original
    assert all(page.changes == PageChange.NONE for page in project.pages)


def test_reorder_falls_back_to_position_delta_and_move_undo_restores_flags() -> None:
    project = project_with_pages(3)
    original = list(project.pages)
    reorder = ReorderPagesCommand(project, [original[2].id, original[0].id, original[1].id])

    reorder.execute()
    assert all(page.changes & PageChange.MOVED for page in project.pages)
    reorder.undo()
    assert project.pages == original

    move = MovePagesCommand(project, 0, 2)
    move.execute()
    assert project.pages[2].stable_number == 1
    assert project.pages[2].changes == PageChange.MOVED
    move.undo()
    assert project.pages == original
