from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from pixopdf.commands import (
    DeletePagesCommand,
    DuplicatePagesCommand,
    InsertBlankPageCommand,
    ReorderPagesCommand,
    RestorePagesCommand,
    RotatePagesCommand,
)
from pixopdf.domain.document import SourceDocument
from pixopdf.domain.page import PageChange
from pixopdf.domain.project import PdfProject
from pixopdf.pdf.backend import PdfBackend
from pixopdf.pdf.renderer import PdfRenderer
from pixopdf.services.project_service import ProjectService
from pixopdf.ui.main_window import MainWindow
from pixopdf.ui.workspace.workspace_page import (
    CURRENT_POSITION_ROLE,
    DISPLAY_ROLE,
    PAGE_CHANGE_ROLE,
    STABLE_NUMBER_ROLE,
    WorkspacePage,
    page_change_label,
)


class ImmediateRenderer(PdfRenderer):
    def render_page(self, file_path: Path, page_index: int, width: int, height: int) -> bytes:
        image = Image.new("RGB", (width, height), "white")
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()


class StablePageBackend(PdfBackend):
    def page_count(self, path: Path) -> int:
        return 3

    def export(self, project: PdfProject, destination: Path) -> None:
        destination.write_bytes(b"exported")


def project_with_pages(count: int = 3) -> PdfProject:
    project = PdfProject()
    project.add_document(SourceDocument.create(Path("stable-pages.pdf"), count))
    return project


def item_values(workspace: WorkspacePage, role: int) -> list[object]:
    return [workspace.pages.item(row).data(role) for row in range(workspace.pages.count())]


@pytest.mark.parametrize(
    ("changes", "label"),
    [
        (PageChange.NONE, ""),
        (PageChange.MOVED, "Déplacée"),
        (PageChange.MODIFIED, "Modifiée"),
        (PageChange.ADDED, "Ajoutée"),
        (PageChange.DELETED, "Supprimée"),
        (PageChange.MODIFIED | PageChange.DELETED, "Supprimée"),
        (
            PageChange.ADDED | PageChange.MOVED | PageChange.MODIFIED,
            "Ajoutée + déplacée + modifiée",
        ),
    ],
)
def test_page_change_label(changes: PageChange, label: str) -> None:
    assert page_change_label(changes) == label


def test_workspace_reorder_keeps_stable_labels_and_marks_only_moved_page(
    qapp: QApplication,
) -> None:
    project = project_with_pages()
    workspace = WorkspacePage(ImmediateRenderer())
    workspace.refresh(project)
    workspace._thread_pool.waitForDone()
    qapp.processEvents()

    assert item_values(workspace, STABLE_NUMBER_ROLE) == [1, 2, 3]
    assert item_values(workspace, CURRENT_POSITION_ROLE) == [1, 2, 3]
    assert item_values(workspace, PAGE_CHANGE_ROLE) == [int(PageChange.NONE)] * 3

    first, second, third = project.pages
    ReorderPagesCommand(
        project,
        [third.id, first.id, second.id],
        moved_ids={third.id},
    ).execute()
    workspace.refresh(project)

    assert item_values(workspace, STABLE_NUMBER_ROLE) == [3, 1, 2]
    assert item_values(workspace, CURRENT_POSITION_ROLE) == [1, 2, 3]
    assert item_values(workspace, DISPLAY_ROLE) == [
        "Page 3  ·  pos. 1",
        "Page 1  ·  pos. 2",
        "Page 2  ·  pos. 3",
    ]
    assert item_values(workspace, PAGE_CHANGE_ROLE) == [
        int(PageChange.MOVED),
        int(PageChange.NONE),
        int(PageChange.NONE),
    ]
    assert workspace.moved_pages_legend.text() == "●  1 déplacée"
    assert workspace.moved_pages_legend.property("changeKind") == "moved"
    assert not workspace.moved_pages_legend.isHidden()
    assert workspace.modified_pages_legend.isHidden()

    snapshot = [
        (
            workspace.pages.item(row).text(),
            workspace.pages.item(row).data(STABLE_NUMBER_ROLE),
            workspace.pages.item(row).data(CURRENT_POSITION_ROLE),
            workspace.pages.item(row).data(PAGE_CHANGE_ROLE),
        )
        for row in range(workspace.pages.count())
    ]
    workspace.refresh(project)
    workspace.refresh(project)
    assert [
        (
            workspace.pages.item(row).text(),
            workspace.pages.item(row).data(STABLE_NUMBER_ROLE),
            workspace.pages.item(row).data(CURRENT_POSITION_ROLE),
            workspace.pages.item(row).data(PAGE_CHANGE_ROLE),
        )
        for row in range(workspace.pages.count())
    ] == snapshot

    workspace.search.setText("page 3")
    assert [workspace.pages.item(row).isHidden() for row in range(3)] == [False, True, True]

    workspace.shutdown()


def test_workspace_rotation_keeps_number_and_shows_modified_legend(
    qapp: QApplication,
) -> None:
    project = project_with_pages()
    RotatePagesCommand(project, [1], 90).execute()
    workspace = WorkspacePage(ImmediateRenderer())
    workspace.refresh(project)
    workspace._thread_pool.waitForDone()
    qapp.processEvents()

    assert item_values(workspace, STABLE_NUMBER_ROLE) == [1, 2, 3]
    assert item_values(workspace, CURRENT_POSITION_ROLE) == [1, 2, 3]
    assert item_values(workspace, PAGE_CHANGE_ROLE) == [
        int(PageChange.NONE),
        int(PageChange.MODIFIED),
        int(PageChange.NONE),
    ]
    assert workspace.pages.item(1).data(DISPLAY_ROLE) == "Page 2  ·  ↻ 90°"
    assert "Indice stable : Page 2" in workspace.pages.item(1).toolTip()
    assert "État : Modifiée" in workspace.pages.item(1).toolTip()
    assert workspace.modified_pages_legend.text() == "●  1 modifiée / ajoutée"
    assert workspace.modified_pages_legend.property("changeKind") == "modified"
    assert not workspace.modified_pages_legend.isHidden()
    assert workspace.moved_pages_legend.isHidden()

    workspace.shutdown()


def test_workspace_keeps_deleted_page_visible_and_offers_restore(
    qapp: QApplication,
) -> None:
    project = project_with_pages()
    DeletePagesCommand(project, [1]).execute()
    workspace = WorkspacePage(ImmediateRenderer())
    restore_requests: list[list[int]] = []
    workspace.restore_requested.connect(restore_requests.append)
    workspace.refresh(project)
    workspace._thread_pool.waitForDone()
    qapp.processEvents()

    assert workspace.pages.count() == 3
    assert item_values(workspace, STABLE_NUMBER_ROLE) == [1, 2, 3]
    assert item_values(workspace, CURRENT_POSITION_ROLE) == [1, 2, 3]
    assert item_values(workspace, PAGE_CHANGE_ROLE) == [
        int(PageChange.NONE),
        int(PageChange.DELETED),
        int(PageChange.NONE),
    ]
    assert "État : Supprimée" in workspace.pages.item(1).toolTip()
    assert workspace.deleted_pages_legend.text() == "●  1 supprimée"
    assert workspace.deleted_pages_legend.property("changeKind") == "deleted"
    assert not workspace.deleted_pages_legend.isHidden()
    assert "1 supprimée" in workspace.pages_count.text()
    assert workspace.export_button.isEnabled()

    workspace.pages.item(1).setSelected(True)
    qapp.processEvents()

    assert workspace.options_selection_change.text() == "Supprimée"
    assert workspace.options_selection_change.property("changeKind") == "deleted"
    assert workspace.delete_button.text() == "Restaurer la page"
    assert workspace.delete_button.property("actionKind") == "restore"
    assert not workspace.duplicate_button.isEnabled()
    assert not workspace.rotate_left_button.isEnabled()
    assert all(not button.isEnabled() for button in workspace._move_buttons.values())

    workspace.delete_button.click()
    assert restore_requests == [[1]]
    workspace.shutdown()


def test_workspace_disables_export_when_every_page_is_deleted() -> None:
    project = project_with_pages(2)
    DeletePagesCommand(project, [0, 1]).execute()
    workspace = WorkspacePage(ImmediateRenderer())

    workspace.refresh(project)

    assert workspace.pages.count() == 2
    assert project.active_page_count == 0
    assert not workspace.export_button.isEnabled()
    assert workspace.deleted_pages_legend.text() == "●  2 supprimées"
    workspace.shutdown()


def test_restore_reveals_previous_modified_state() -> None:
    project = project_with_pages(1)
    RotatePagesCommand(project, [0], 90).execute()
    DeletePagesCommand(project, [0]).execute()

    assert page_change_label(project.pages[0].changes) == "Supprimée"

    RestorePagesCommand(project, [0]).execute()

    assert project.pages[0].changes == PageChange.MODIFIED
    assert page_change_label(project.pages[0].changes) == "Modifiée"


def test_workspace_blank_and_duplicate_get_new_numbers_without_marking_shifted_pages(
    qapp: QApplication,
) -> None:
    project = project_with_pages()
    DuplicatePagesCommand(project, [1]).execute()
    InsertBlankPageCommand(project, 0).execute()
    workspace = WorkspacePage(ImmediateRenderer())
    workspace.refresh(project)
    workspace._thread_pool.waitForDone()
    qapp.processEvents()

    assert item_values(workspace, STABLE_NUMBER_ROLE) == [5, 1, 2, 4, 3]
    assert item_values(workspace, CURRENT_POSITION_ROLE) == [1, 2, 3, 4, 5]
    assert item_values(workspace, PAGE_CHANGE_ROLE) == [
        int(PageChange.ADDED),
        int(PageChange.NONE),
        int(PageChange.NONE),
        int(PageChange.ADDED),
        int(PageChange.NONE),
    ]
    assert not any(
        PageChange(int(value)) & PageChange.MOVED
        for value in item_values(workspace, PAGE_CHANGE_ROLE)
    )
    assert workspace.moved_pages_legend.isHidden()
    assert workspace.modified_pages_legend.text() == "●  2 modifiées / ajoutées"
    assert not workspace.modified_pages_legend.isHidden()

    workspace.shutdown()


def test_main_window_reorder_undo_redo_restores_stable_ui_state(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    window = MainWindow(ProjectService(StablePageBackend()))
    window.workspace.renderer = ImmediateRenderer()
    window.project.add_document(SourceDocument.create(tmp_path / "source.pdf", 3))
    window.commands.mark_clean()
    window.refresh()
    original = list(window.project.pages)

    window.workspace.select_page_ids([original[2].id])
    window.workspace.reorder_requested.emit(
        [str(original[2].id), str(original[0].id), str(original[1].id)]
    )
    qapp.processEvents()

    assert [page.stable_number for page in window.project.pages] == [3, 1, 2]
    assert [page.changes for page in window.project.pages] == [
        PageChange.MOVED,
        PageChange.NONE,
        PageChange.NONE,
    ]
    assert item_values(window.workspace, STABLE_NUMBER_ROLE) == [3, 1, 2]

    window.commands.undo()
    qapp.processEvents()
    assert [page.stable_number for page in window.project.pages] == [1, 2, 3]
    assert all(page.changes == PageChange.NONE for page in window.project.pages)
    assert window.workspace.moved_pages_legend.isHidden()

    window.commands.redo()
    qapp.processEvents()
    assert [page.stable_number for page in window.project.pages] == [3, 1, 2]
    assert [page.changes for page in window.project.pages] == [
        PageChange.MOVED,
        PageChange.NONE,
        PageChange.NONE,
    ]
    assert window.workspace.moved_pages_legend.text() == "●  1 déplacée"

    window.commands.mark_clean()
    window.refresh()
    window.close()
