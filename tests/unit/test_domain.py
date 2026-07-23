from pathlib import Path

from pixopdf.commands import (
    CommandStack,
    DeletePagesCommand,
    DuplicatePagesCommand,
    InsertBlankPageCommand,
    ReorderPagesCommand,
    RotatePagesCommand,
)
from pixopdf.domain.document import SourceDocument
from pixopdf.domain.project import PdfProject


def project_with_pages(count: int = 3) -> PdfProject:
    project = PdfProject()
    project.add_document(SourceDocument.create(Path("sample.pdf"), count))
    return project


def test_add_document_creates_virtual_pages() -> None:
    project = project_with_pages()
    assert [p.source_page_index for p in project.pages] == [0, 1, 2]


def test_delete_undo_redo() -> None:
    project = project_with_pages()
    stack = CommandStack()
    stack.execute(DeletePagesCommand(project, [1]))
    assert len(project.pages) == 2
    stack.undo()
    assert len(project.pages) == 3
    stack.redo()
    assert len(project.pages) == 2


def test_rotation_is_virtual_and_undoable() -> None:
    project = project_with_pages(1)
    stack = CommandStack()
    stack.execute(RotatePagesCommand(project, [0], 90))
    assert project.pages[0].rotation == 90
    stack.undo()
    assert project.pages[0].rotation == 0


def test_rotation_to_the_left() -> None:
    project = project_with_pages(1)
    RotatePagesCommand(project, [0], -90).execute()
    assert project.pages[0].rotation == 270


def test_duplicate_is_undoable() -> None:
    project = project_with_pages(2)
    original_id = project.pages[0].id
    stack = CommandStack()
    stack.execute(DuplicatePagesCommand(project, [0]))
    assert len(project.pages) == 3
    assert project.pages[1].id != original_id
    assert project.pages[1].source_page_index == project.pages[0].source_page_index
    stack.undo()
    assert len(project.pages) == 2


def test_reorder_is_undoable_and_tracks_clean_state() -> None:
    project = project_with_pages(3)
    stack = CommandStack()
    original = list(project.pages)
    stack.mark_clean()
    stack.execute(ReorderPagesCommand(project, [page.id for page in reversed(original)]))
    assert [page.id for page in project.pages] == [page.id for page in reversed(original)]
    assert not stack.is_clean
    stack.undo()
    assert project.pages == original
    assert stack.is_clean


def test_insert_blank_page_execute_undo_redo_preserves_uuid() -> None:
    project = project_with_pages(2)
    original_ids = [page.id for page in project.pages]
    stack = CommandStack()
    command = InsertBlankPageCommand(project, index=1)

    stack.execute(command)

    blank_page = project.pages[1]
    blank_id = blank_page.id
    assert blank_page.is_blank
    assert blank_page.source_document_id is None
    assert blank_page.source_page_index is None
    assert blank_page.blank_size == (595.28, 841.89)
    assert [project.pages[0].id, project.pages[2].id] == original_ids

    stack.undo()
    assert [page.id for page in project.pages] == original_ids

    stack.redo()
    assert project.pages[1].id == blank_id
    assert project.pages[1] is blank_page


def test_blank_page_can_be_rotated_and_duplicated() -> None:
    project = PdfProject()
    stack = CommandStack()
    stack.execute(InsertBlankPageCommand(project, index=0, page_size=(420.0, 595.0)))
    original_id = project.pages[0].id

    stack.execute(RotatePagesCommand(project, [0], 90))
    stack.execute(DuplicatePagesCommand(project, [0]))

    assert len(project.pages) == 2
    assert all(page.is_blank for page in project.pages)
    assert [page.rotation for page in project.pages] == [90, 90]
    assert [page.blank_size for page in project.pages] == [(420.0, 595.0)] * 2
    assert project.pages[0].id == original_id
    assert project.pages[1].id != original_id

    stack.undo()
    assert len(project.pages) == 1
    assert project.pages[0].id == original_id
    stack.undo()
    assert project.pages[0].rotation == 0
