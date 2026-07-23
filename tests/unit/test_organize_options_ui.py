from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QListWidget

from pixopdf.domain.page import PageReference
from pixopdf.domain.project import PdfProject
from pixopdf.pdf.renderer import PdfRenderer
from pixopdf.ui.workspace.workspace_page import (
    A4_LANDSCAPE,
    A4_PORTRAIT,
    A5_PORTRAIT,
    WorkspacePage,
)


class NoRenderRenderer(PdfRenderer):
    def render_page(
        self,
        file_path: Path,
        page_index: int,
        width: int,
        height: int,
    ) -> bytes:
        raise AssertionError("These tests only use virtual blank pages")


def blank_project(count: int = 4) -> PdfProject:
    project = PdfProject()
    project.pages.extend(PageReference.blank() for _ in range(count))
    return project


def reordered_blank_project() -> PdfProject:
    project = blank_project(3)
    project.ensure_page_numbers()
    first, second, third = project.pages
    project.pages[:] = [third, first, second]
    return project


def test_organize_panel_empty_single_and_multiple_selection_states(
    qapp: QApplication,
) -> None:
    workspace = WorkspacePage(NoRenderRenderer())
    workspace.refresh(reordered_blank_project())

    assert workspace.options_selection_label.text() == "Aucune page sélectionnée"
    assert "activer les actions" in workspace.options_selection_detail.text()
    assert workspace.organize_selection_card.property("selectionState") == "empty"
    assert not workspace.move_group.isHidden()
    assert not workspace.modify_group.isHidden()
    assert not workspace.organize_danger_zone.isHidden()
    assert workspace.clear_selection_button.isHidden()
    assert all(not button.isEnabled() for button in workspace._move_buttons.values())
    assert not workspace.duplicate_button.isEnabled()
    assert not workspace.rotate_left_button.isEnabled()
    assert not workspace.rotate_right_button.isEnabled()
    assert not workspace.delete_button.isEnabled()
    assert not workspace.insert_group.isHidden()
    assert workspace.blank_page_button.isEnabled()
    assert not workspace.blank_before_action.isEnabled()
    assert not workspace.blank_after_action.isEnabled()
    assert workspace.blank_at_end_action.isEnabled()
    assert workspace.move_hint.isHidden()

    workspace.pages.item(0).setSelected(True)
    qapp.processEvents()

    assert workspace.options_selection_label.text() == "1 page sélectionnée"
    assert workspace.organize_selection_card.property("selectionState") == "selected"
    assert "Page 3" in workspace.options_selection_detail.text()
    assert "position 1 sur 3" in workspace.options_selection_detail.text()
    assert not workspace.options_selection_change.isHidden()
    assert workspace.options_selection_change.text() == "Ajoutée"
    assert workspace.options_selection_change.property("changeKind") == "modified"
    assert workspace.move_position_label.text() == "Position actuelle : 1 sur 3"
    assert "après Page 3" in workspace.blank_target_label.text()
    assert not workspace.move_group.isHidden()
    assert not workspace.modify_group.isHidden()
    assert not workspace.organize_danger_zone.isHidden()
    assert not workspace.clear_selection_button.isHidden()

    workspace.pages.item(2).setSelected(True)
    qapp.processEvents()

    assert workspace.options_selection_label.text() == "2 pages sélectionnées"
    assert "Pages 3 et 2" in workspace.options_selection_detail.text()
    assert "ordre relatif conservé" in workspace.options_selection_detail.text()
    assert workspace.options_selection_change.isHidden()
    assert "Positions actuelles : 1 et 3" in workspace.move_position_label.text()
    assert "2 pages" in workspace.duplicate_button.text()
    assert "2 pages" in workspace.delete_button.text()

    workspace.clear_selection_button.click()
    qapp.processEvents()

    assert workspace.pages.selectedItems() == []
    assert workspace.organize_selection_card.property("selectionState") == "empty"
    assert not workspace.move_group.isHidden()
    assert not workspace.modify_group.isHidden()
    assert not workspace.organize_danger_zone.isHidden()
    assert all(not button.isEnabled() for button in workspace._move_buttons.values())
    assert not workspace.duplicate_button.isEnabled()
    assert not workspace.delete_button.isEnabled()
    workspace.shutdown()


def test_organize_actions_emit_sorted_single_and_multiple_selection(
    qapp: QApplication,
) -> None:
    workspace = WorkspacePage(NoRenderRenderer())
    workspace.refresh(blank_project())
    duplicate_requests: list[list[int]] = []
    delete_requests: list[list[int]] = []
    rotate_requests: list[tuple[list[int], int]] = []
    workspace.duplicate_requested.connect(duplicate_requests.append)
    workspace.delete_requested.connect(delete_requests.append)
    workspace.rotate_requested.connect(
        lambda indices, degrees: rotate_requests.append((indices, degrees))
    )

    workspace.pages.item(1).setSelected(True)
    qapp.processEvents()
    workspace.duplicate_button.click()
    workspace.rotate_left_button.click()
    workspace.rotate_right_button.click()
    workspace.delete_button.click()

    workspace.pages.clearSelection()
    workspace.pages.item(3).setSelected(True)
    workspace.pages.item(0).setSelected(True)
    qapp.processEvents()
    workspace.duplicate_button.click()
    workspace.rotate_left_button.click()
    workspace.rotate_right_button.click()
    workspace.delete_button.click()

    assert duplicate_requests == [[1], [0, 3]]
    assert delete_requests == [[1], [0, 3]]
    assert rotate_requests == [
        ([1], -90),
        ([1], 90),
        ([0, 3], -90),
        ([0, 3], 90),
    ]
    workspace.shutdown()


def test_organize_search_banner_explains_and_clears_suspended_reordering(
    qapp: QApplication,
) -> None:
    workspace = WorkspacePage(NoRenderRenderer())
    workspace.refresh(blank_project())
    workspace.pages.item(1).setSelected(True)
    qapp.processEvents()

    workspace.search.setText("page blanche")
    qapp.processEvents()

    assert workspace.pages.selectedItems() == []
    assert not workspace.organize_search_banner.isHidden()
    assert workspace.organize_selection_card.isHidden()
    assert not workspace.move_group.isHidden()
    assert not workspace.modify_group.isHidden()
    assert not workspace.organize_danger_zone.isHidden()
    assert all(not button.isEnabled() for button in workspace._move_buttons.values())
    assert not workspace.duplicate_button.isEnabled()
    assert not workspace.delete_button.isEnabled()
    assert "Effacez la recherche" in workspace.move_hint.text()
    assert workspace.pages.dragDropMode() == QListWidget.DragDropMode.NoDragDrop

    workspace.clear_search_button.click()
    qapp.processEvents()

    assert workspace.search.text() == ""
    assert workspace.organize_search_banner.isHidden()
    assert workspace.pages.dragDropMode() == QListWidget.DragDropMode.InternalMove
    workspace.shutdown()


def test_organize_blank_page_menu_emits_end_and_format_variants(
    qapp: QApplication,
) -> None:
    workspace = WorkspacePage(NoRenderRenderer())
    workspace.refresh(blank_project())
    blank_requests: list[tuple[int, float, float]] = []
    workspace.blank_page_requested.connect(
        lambda index, width, height: blank_requests.append((index, width, height))
    )

    assert "fin du document" in workspace.blank_landscape_action.text()
    assert "fin du document" in workspace.blank_a5_action.text()
    workspace.blank_at_end_action.trigger()
    workspace.blank_landscape_action.trigger()
    workspace.blank_a5_action.trigger()

    workspace.pages.item(1).setSelected(True)
    qapp.processEvents()
    assert "après la sélection" in workspace.blank_landscape_action.text()
    assert "après la sélection" in workspace.blank_a5_action.text()
    workspace.blank_at_end_action.trigger()
    workspace.blank_landscape_action.trigger()
    workspace.blank_a5_action.trigger()

    assert blank_requests == [
        (4, *A4_PORTRAIT),
        (4, *A4_LANDSCAPE),
        (4, *A5_PORTRAIT),
        (4, *A4_PORTRAIT),
        (2, *A4_LANDSCAPE),
        (2, *A5_PORTRAIT),
    ]
    workspace.shutdown()


def test_organize_escape_clears_selection_and_actions_are_accessible(
    qapp: QApplication,
) -> None:
    workspace = WorkspacePage(NoRenderRenderer())
    workspace.refresh(blank_project())
    workspace.pages.setCurrentRow(1)
    qapp.processEvents()

    assert workspace.pages.selectedItems()
    for button in (
        workspace.clear_selection_button,
        workspace.blank_page_button,
        workspace.delete_button,
        workspace.clear_search_button,
    ):
        assert button.accessibleName().strip()
        assert button.toolTip() or button.accessibleDescription()
    for button in workspace._move_buttons.values():
        assert button.accessibleName().strip()
        assert button.accessibleDescription().strip()
    for button in (
        workspace.rotate_left_button,
        workspace.rotate_right_button,
    ):
        assert button.toolTip()
        assert button.accessibleDescription().strip()

    QTest.keyClick(workspace.pages, Qt.Key.Key_Escape)
    qapp.processEvents()

    assert workspace.pages.selectedItems() == []
    assert workspace.options_selection_label.text() == "Aucune page sélectionnée"
    assert workspace.clear_selection_button.isHidden()
    assert not workspace.organize_danger_zone.isHidden()
    assert not workspace.delete_button.isEnabled()
    workspace.shutdown()
