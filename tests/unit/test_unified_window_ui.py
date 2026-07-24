from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QFileDialog, QFrame

from pixopdf.domain.document import SourceDocument
from pixopdf.domain.project import PdfProject
from pixopdf.pdf.backend import PdfBackend
from pixopdf.pdf.renderer import PdfRenderer
from pixopdf.services.project_service import ProjectService
from pixopdf.ui.main_window import MainWindow
from pixopdf.ui.tool_modes import MODE_SPECS, ModeStatus, WorkspaceMode
from pixopdf.ui.workspace.operation_worker import OperationTask
from pixopdf.ui.workspace.workspace_page import WorkspacePage


class UnifiedWindowBackend(PdfBackend):
    def page_count(self, path: Path) -> int:
        return 2

    def export(self, project: PdfProject, destination: Path) -> None:
        destination.write_bytes(b"exported")


class NoRenderRenderer(PdfRenderer):
    def render_page(
        self,
        file_path: Path,
        page_index: int,
        width: int,
        height: int,
    ) -> bytes:
        raise AssertionError("These tests do not render source pages")


def configure_settings(tmp_path: Path, **values: object) -> QSettings:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    settings = QSettings("PixoGlace", "PixoPDF")
    settings.clear()
    for key, value in values.items():
        settings.setValue(key.replace("__", "/"), value)
    settings.sync()
    return settings


def wait_for_operation(window: MainWindow, timeout_ms: int = 2000) -> None:
    loop = QEventLoop()

    def poll() -> None:
        if window._active_task is None:
            loop.quit()
        else:
            QTimer.singleShot(10, poll)

    QTimer.singleShot(10, poll)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()


def close_clean(window: MainWindow) -> None:
    window.commands.mark_clean()
    window.refresh()
    window.close()


def test_main_window_uses_single_workspace_shell_with_left_context(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    configure_settings(tmp_path)
    window = MainWindow(ProjectService(UnifiedWindowBackend()))
    window.show()
    qapp.processEvents()

    workspace = window.workspace
    topbar = workspace.findChild(QFrame, "topbar")

    assert window.centralWidget() is workspace
    assert not hasattr(window, "home")
    assert not hasattr(window, "stack")
    assert topbar is not None
    assert topbar.isVisible()
    assert workspace.page_stack.currentWidget() is workspace.empty_state
    assert workspace.findChild(QFrame, "centralDropZone") is None
    assert workspace.splitter.count() == 2
    assert workspace.splitter.indexOf(workspace.context_panel) == 0
    assert workspace.splitter.indexOf(workspace.pages_panel) == 1
    assert workspace.context_panel.objectName() == "contextPanel"
    assert workspace.context_panel.minimumWidth() == 280
    assert workspace.options_stack.parentWidget() is workspace.context_panel

    close_clean(window)


def test_persistent_topbar_modes_disable_unavailable_workflows(
    qapp: QApplication,
) -> None:
    workspace = WorkspacePage(NoRenderRenderer())
    requested: list[str] = []
    workspace.mode_requested.connect(requested.append)
    topbar = workspace.findChild(QFrame, "topbar")

    assert topbar is not None
    assert workspace.mode_group.exclusive()
    assert set(workspace.mode_buttons) == set(WorkspaceMode)

    for mode, spec in MODE_SPECS.items():
        button = workspace.mode_buttons[mode]
        assert button.isEnabled() is spec.is_selectable
        assert workspace.mode_actions[mode].isEnabled() is spec.is_selectable
        if spec.status is ModeStatus.COMING_SOON:
            assert "Disponible prochainement" in button.toolTip()
            assert "prochainement" in button.accessibleDescription()
            button.click()
            workspace.set_mode(mode)
            assert workspace.current_mode is WorkspaceMode.ORGANIZE

    assert requested == []
    workspace.mode_buttons[WorkspaceMode.MERGE].click()
    assert requested == [WorkspaceMode.MERGE.value]
    assert workspace.current_mode is WorkspaceMode.MERGE
    assert workspace.options_stack.currentWidget() is workspace.option_panels[WorkspaceMode.MERGE]
    assert workspace.splitter.indexOf(workspace.context_panel) == 0
    assert workspace.findChild(QFrame, "topbar") is topbar
    workspace.shutdown()


def test_programmatic_unavailable_mode_keeps_current_selectable_mode(
    qapp: QApplication,
) -> None:
    workspace = WorkspacePage(NoRenderRenderer())
    workspace.set_mode(WorkspaceMode.MERGE)
    merge_panel = workspace.option_panels[WorkspaceMode.MERGE]

    workspace.set_mode(WorkspaceMode.PROTECT)

    assert workspace.current_mode is WorkspaceMode.MERGE
    assert workspace.mode_buttons[WorkspaceMode.MERGE].isChecked()
    assert workspace.options_stack.currentWidget() is merge_panel
    assert workspace.options_heading.text() == MODE_SPECS[WorkspaceMode.MERGE].label
    workspace.shutdown()


def test_import_preserves_central_shell_topbar_mode_and_left_panel(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    configure_settings(tmp_path, workflow__mode=WorkspaceMode.MERGE.value)
    window = MainWindow(ProjectService(UnifiedWindowBackend()))
    source = tmp_path / "merge-source.pdf"
    source.write_bytes(b"fake")
    central = window.centralWidget()
    topbar = window.workspace.findChild(QFrame, "topbar")
    left_panel = window.workspace.context_panel

    window.import_paths([str(source)])
    wait_for_operation(window)
    qapp.processEvents()

    assert window.centralWidget() is central is window.workspace
    assert window.workspace.findChild(QFrame, "topbar") is topbar
    assert window.workspace.context_panel is left_panel
    assert window.workspace.page_stack.currentWidget() is window.workspace.pages
    assert window.workspace.pages.count() == 2
    assert window.active_mode is WorkspaceMode.MERGE
    assert window.workspace.current_mode is WorkspaceMode.MERGE
    assert (
        window.workspace.options_stack.currentWidget()
        is window.workspace.option_panels[WorkspaceMode.MERGE]
    )

    window.settings.sync()
    close_clean(window)

    restored = MainWindow(ProjectService(UnifiedWindowBackend()))
    assert restored.centralWidget() is restored.workspace
    assert restored.active_mode is WorkspaceMode.MERGE
    assert restored.workspace.current_mode is WorkspaceMode.MERGE
    close_clean(restored)


@pytest.mark.parametrize(
    "saved_mode",
    [
        WorkspaceMode.CONVERT.value,
        WorkspaceMode.PROTECT.value,
        WorkspaceMode.SIGN.value,
        WorkspaceMode.COMPRESS.value,
        "unknown-mode",
    ],
)
def test_unavailable_or_unknown_saved_mode_falls_back_to_organize(
    saved_mode: str,
    tmp_path: Path,
) -> None:
    settings = configure_settings(tmp_path, workflow__mode=saved_mode)
    window = MainWindow(ProjectService(UnifiedWindowBackend()))

    assert window.active_mode is WorkspaceMode.ORGANIZE
    assert window.workspace.current_mode is WorkspaceMode.ORGANIZE
    assert window.workspace.mode_buttons[WorkspaceMode.ORGANIZE].isChecked()
    assert settings.value("workflow/mode") == WorkspaceMode.ORGANIZE.value

    close_clean(window)


def test_saved_split_mode_is_restored(
    tmp_path: Path,
) -> None:
    settings = configure_settings(tmp_path, workflow__mode=WorkspaceMode.SPLIT.value)

    window = MainWindow(ProjectService(UnifiedWindowBackend()))

    assert window.active_mode is WorkspaceMode.SPLIT
    assert window.workspace.current_mode is WorkspaceMode.SPLIT
    assert window.workspace.mode_buttons[WorkspaceMode.SPLIT].isChecked()
    assert settings.value("workflow/mode") == WorkspaceMode.SPLIT.value
    close_clean(window)


def test_busy_window_blocks_undo_redo_signals_and_shortcuts(
    tmp_path: Path,
) -> None:
    configure_settings(tmp_path)
    window = MainWindow(ProjectService(UnifiedWindowBackend()))
    window.insert_blank_page(0, 595.28, 841.89)
    window.insert_blank_page(1, 595.28, 841.89)
    window.commands.undo()
    initial_page_ids = [page.id for page in window.project.pages]
    initial_history = (window.commands.can_undo, window.commands.can_redo)

    undo_bindings = QKeySequence.keyBindings(QKeySequence.StandardKey.Undo)
    redo_bindings = QKeySequence.keyBindings(QKeySequence.StandardKey.Redo)
    undo_action = next(action for action in window.actions() if action.shortcut() in undo_bindings)
    redo_action = next(action for action in window.actions() if action.shortcut() in redo_bindings)

    window._active_task = OperationTask(lambda: None)
    window._set_busy(True)
    try:
        window.workspace.undo_requested.emit()
        assert [page.id for page in window.project.pages] == initial_page_ids
        assert (window.commands.can_undo, window.commands.can_redo) == initial_history

        window.workspace.redo_requested.emit()
        assert [page.id for page in window.project.pages] == initial_page_ids
        assert (window.commands.can_undo, window.commands.can_redo) == initial_history

        undo_action.trigger()
        assert [page.id for page in window.project.pages] == initial_page_ids
        assert (window.commands.can_undo, window.commands.can_redo) == initial_history

        redo_action.trigger()
        assert [page.id for page in window.project.pages] == initial_page_ids
        assert (window.commands.can_undo, window.commands.can_redo) == initial_history
    finally:
        window._active_task = None
        window._set_busy(False)
        close_clean(window)


def test_merge_export_with_one_document_opens_no_dialog_and_starts_no_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_settings(tmp_path)
    window = MainWindow(ProjectService(UnifiedWindowBackend()))
    source = tmp_path / "single-source.pdf"
    source.write_bytes(b"fake")
    window.project.add_document(SourceDocument.create(source, 1))
    window.activate_mode(WorkspaceMode.MERGE)
    dialog_calls: list[bool] = []
    task_calls: list[bool] = []

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (
            dialog_calls.append(True) or str(tmp_path / "unexpected.pdf"),
            "",
        ),
    )
    monkeypatch.setattr(
        window,
        "_start_operation",
        lambda *_args, **_kwargs: task_calls.append(True),
    )

    window.export()

    assert dialog_calls == []
    assert task_calls == []
    assert window._active_task is None
    window.project.modified = False
    window.close()


def test_legacy_three_column_splitter_preference_migrates_to_two(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    configure_settings(tmp_path, window__splitter_sizes=[210, 700, 340])
    window = MainWindow(ProjectService(UnifiedWindowBackend()))
    window.show()
    qapp.processEvents()

    sizes = window.workspace.splitter.sizes()
    assert len(sizes) == 2
    assert abs(sizes[0] - 340) <= 2
    assert sizes[1] > sizes[0]

    close_clean(window)
    saved_sizes = QSettings("PixoGlace", "PixoPDF").value("window/splitter_sizes")
    assert isinstance(saved_sizes, list)
    assert len(saved_sizes) == 2


@pytest.mark.parametrize(
    "saved_sizes",
    [
        pytest.param([220, 730, 600], id="legacy-three-columns-oversized-context"),
        pytest.param([600, 381], id="two-columns-oversized-context"),
    ],
)
def test_oversized_context_preference_is_bounded_and_redistributed_without_gap(
    saved_sizes: list[int],
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    configure_settings(tmp_path, window__splitter_sizes=saved_sizes)
    window = MainWindow(ProjectService(UnifiedWindowBackend()))
    window.resize(1280, 780)
    window.show()
    qapp.processEvents()

    workspace = window.workspace
    splitter = workspace.splitter
    context = workspace.context_panel
    pages = workspace.pages_panel
    restored_sizes = splitter.sizes()
    seam_tolerance = 4

    assert len(restored_sizes) == 2
    assert restored_sizes[0] <= 360
    assert context.width() <= context.maximumWidth() == 360
    assert abs(context.width() - restored_sizes[0]) <= seam_tolerance

    context_end = context.geometry().x() + context.geometry().width()
    assert abs(pages.geometry().x() - context_end) <= seam_tolerance
    assert pages.geometry().right() >= splitter.rect().right() - seam_tolerance
    assert abs(sum(restored_sizes) - splitter.width()) <= seam_tolerance
    assert pages.width() >= splitter.width() - context.width() - seam_tolerance
    assert restored_sizes[1] > saved_sizes[1]

    close_clean(window)
