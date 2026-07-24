from pathlib import Path

from PySide6.QtWidgets import QApplication

from pixopdf.domain.document import SourceDocument
from pixopdf.domain.page import PageReference
from pixopdf.domain.project import PdfProject
from pixopdf.pdf.renderer import PdfRenderer
from pixopdf.ui.tool_modes import MODE_SPECS, WorkspaceMode
from pixopdf.ui.workspace.workspace_page import (
    A4_LANDSCAPE,
    A4_PORTRAIT,
    A5_PORTRAIT,
    WorkspacePage,
)


class NoRenderRenderer(PdfRenderer):
    def render_page(self, file_path: Path, page_index: int, width: int, height: int) -> bytes:
        raise AssertionError("These mode tests only use virtual blank pages")


def blank_project(count: int = 2) -> PdfProject:
    project = PdfProject()
    project.pages.extend(PageReference.blank() for _ in range(count))
    return project


def merge_ready_project() -> PdfProject:
    project = PdfProject()
    project.add_document(SourceDocument.create(Path("first.pdf"), 1))
    project.add_document(SourceDocument.create(Path("second.pdf"), 1))
    project.pages[:] = [PageReference.blank(), PageReference.blank()]
    return project


def test_workspace_modes_are_exclusive_and_update_left_context(
    qapp: QApplication,
) -> None:
    workspace = WorkspacePage(NoRenderRenderer())
    requested: list[str] = []
    workspace.mode_requested.connect(requested.append)

    assert workspace.mode_group.exclusive()
    assert set(workspace.mode_buttons) == set(WorkspaceMode)
    assert workspace.current_mode is WorkspaceMode.ORGANIZE
    assert workspace.mode_buttons[WorkspaceMode.ORGANIZE].isChecked()

    workspace.mode_buttons[WorkspaceMode.MERGE].click()

    assert requested == [WorkspaceMode.MERGE.value]
    assert workspace.current_mode is WorkspaceMode.MERGE
    assert [mode for mode, button in workspace.mode_buttons.items() if button.isChecked()] == [
        WorkspaceMode.MERGE
    ]
    assert workspace.options_stack.currentWidget() is workspace.option_panels[WorkspaceMode.MERGE]
    assert workspace.options_heading.text() == MODE_SPECS[WorkspaceMode.MERGE].label
    workspace.shutdown()


def test_workspace_has_a_distinct_context_panel_for_every_mode(
    qapp: QApplication,
) -> None:
    workspace = WorkspacePage(NoRenderRenderer())

    assert set(workspace.option_panels) == set(WorkspaceMode)
    assert workspace.options_stack.count() == len(WorkspaceMode) == 8
    assert len({id(panel) for panel in workspace.option_panels.values()}) == 8

    for mode, spec in MODE_SPECS.items():
        assert workspace.mode_buttons[mode].isEnabled() is spec.is_selectable
        assert workspace.mode_actions[mode].isEnabled() is spec.is_selectable
        if not spec.is_selectable:
            continue
        workspace.set_mode(mode)
        assert workspace.current_mode is mode
        assert workspace.options_stack.currentWidget() is workspace.option_panels[mode]
        assert workspace.options_heading.text() == spec.label
        assert workspace.pages_heading.text() == spec.workspace_title
        assert workspace.mode_actions[mode].isChecked()
        assert sum(action.isChecked() for action in workspace.mode_actions.values()) == 1

    workspace.shutdown()


def test_workspace_merge_and_layout_actions_emit_expected_requests(
    qapp: QApplication,
) -> None:
    workspace = WorkspacePage(NoRenderRenderer())
    workspace.refresh(merge_ready_project())
    add_requests: list[bool] = []
    export_requests: list[bool] = []
    blank_requests: list[tuple[int, float, float]] = []
    workspace.add_requested.connect(lambda: add_requests.append(True))
    workspace.export_requested.connect(lambda: export_requests.append(True))
    workspace.blank_page_requested.connect(
        lambda index, width, height: blank_requests.append((index, width, height))
    )

    workspace.set_mode(WorkspaceMode.MERGE)
    merge_add_button = workspace.mode_specific_actions[WorkspaceMode.MERGE][0]
    merge_add_button.click()
    workspace.merge_export_button.click()
    assert add_requests == [True]
    assert export_requests == [True]
    assert workspace.merge_export_button.isEnabled()

    workspace.set_mode(WorkspaceMode.LAYOUT)
    workspace.pages.item(0).setSelected(True)
    qapp.processEvents()
    for button in workspace.layout_blank_buttons:
        button.click()
    assert blank_requests == [
        (1, *A4_PORTRAIT),
        (1, *A4_LANDSCAPE),
        (1, *A5_PORTRAIT),
    ]

    planned_layout_actions = workspace.mode_specific_actions[WorkspaceMode.LAYOUT][3:]
    assert planned_layout_actions
    assert all(not button.isEnabled() for button in planned_layout_actions)
    workspace.shutdown()


def test_split_panel_validates_strategies_and_emits_request(
    qapp: QApplication,
) -> None:
    workspace = WorkspacePage(NoRenderRenderer())
    workspace.refresh(blank_project(5))
    split_requests: list[tuple[str, int, str]] = []
    workspace.split_requested.connect(
        lambda strategy, batch_size, ranges: split_requests.append((strategy, batch_size, ranges))
    )

    workspace.set_mode(WorkspaceMode.SPLIT)

    assert MODE_SPECS[WorkspaceMode.SPLIT].is_selectable
    assert workspace.current_mode is WorkspaceMode.SPLIT
    assert workspace.split_each_radio.isChecked()
    assert workspace.split_execute_button.isEnabled()
    assert "5 fichiers PDF" in workspace.split_validation_label.text()

    workspace.split_batch_radio.setChecked(True)
    workspace.split_batch_size.setValue(2)
    qapp.processEvents()
    assert "3 fichiers PDF" in workspace.split_validation_label.text()
    workspace.split_execute_button.click()
    assert split_requests == [("batch", 2, "")]

    workspace.split_ranges_radio.setChecked(True)
    workspace.split_ranges_input.setText("1-8")
    qapp.processEvents()
    assert not workspace.split_execute_button.isEnabled()
    assert "dépasse" in workspace.split_validation_label.text()

    workspace.split_ranges_input.setText("1-2; 3,5")
    qapp.processEvents()
    assert workspace.split_execute_button.isEnabled()
    assert "2 fichiers PDF" in workspace.split_validation_label.text()
    workspace.split_execute_button.click()
    assert split_requests[-1] == ("ranges", 2, "1-2; 3,5")
    workspace.shutdown()


def test_documents_are_visible_and_removable_in_organize_and_merge(
    qapp: QApplication,
) -> None:
    project = merge_ready_project()
    workspace = WorkspacePage(NoRenderRenderer())
    remove_requests: list[str] = []
    workspace.remove_document_requested.connect(remove_requests.append)

    workspace.refresh(project)
    qapp.processEvents()

    assert workspace.current_mode is WorkspaceMode.ORGANIZE
    assert workspace.organize_documents.count() == 2
    assert workspace.organize_documents.isVisibleTo(workspace)
    assert workspace.organize_documents_heading.text() == "Documents (2)"
    assert not workspace.organize_remove_document_button.isEnabled()

    first_document = next(iter(project.documents.values()))
    workspace.organize_documents.setCurrentRow(0)
    qapp.processEvents()
    assert workspace.organize_remove_document_button.isEnabled()
    workspace.organize_remove_document_button.click()
    assert remove_requests == [str(first_document.id)]

    workspace.set_mode(WorkspaceMode.MERGE)
    assert workspace.merge_documents.count() == 2
    assert workspace.merge_documents_heading.text() == "Documents (2)"
    workspace.merge_documents.setCurrentRow(1)
    qapp.processEvents()
    workspace.merge_remove_document_button.click()
    assert remove_requests == [
        str(first_document.id),
        str(list(project.documents.values())[1].id),
    ]
    workspace.shutdown()


def test_workspace_keeps_mode_and_panel_after_refresh(qapp: QApplication) -> None:
    workspace = WorkspacePage(NoRenderRenderer())
    workspace.set_mode(WorkspaceMode.MERGE)
    selected_panel = workspace.option_panels[WorkspaceMode.MERGE]

    workspace.refresh(blank_project(3))
    qapp.processEvents()

    assert workspace.current_mode is WorkspaceMode.MERGE
    assert workspace.options_stack.currentWidget() is selected_panel
    assert workspace.mode_actions[WorkspaceMode.MERGE].isChecked()
    assert workspace.pages_heading.text() == MODE_SPECS[WorkspaceMode.MERGE].workspace_title
    workspace.shutdown()
