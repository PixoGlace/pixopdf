from pathlib import Path

from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication

from pixopdf.domain.project import PdfProject
from pixopdf.pdf.backend import PdfBackend
from pixopdf.services.project_service import ProjectService
from pixopdf.ui.main_window import MainWindow
from pixopdf.ui.tool_modes import WorkspaceMode


class WindowBackend(PdfBackend):
    def page_count(self, path: Path) -> int:
        return 2

    def export(self, project: PdfProject, destination: Path) -> None:
        destination.write_bytes(b"exported")


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


def test_main_window_import_and_page_actions(tmp_path: Path, qapp: QApplication) -> None:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    window = MainWindow(ProjectService(WindowBackend()))
    source = tmp_path / "source.pdf"
    source.write_bytes(b"fake")

    window.import_paths([str(source)])
    wait_for_operation(window)
    qapp.processEvents()

    assert len(window.project.pages) == 2
    assert window.centralWidget() is window.workspace
    assert window.project.modified

    window.workspace.rotate_requested.emit([0], -90)
    assert window.project.pages[0].rotation == 270
    window.workspace.duplicate_requested.emit([0])
    assert len(window.project.pages) == 3
    current_ids = [page.id for page in window.project.pages]
    window.workspace.reorder_requested.emit([str(page_id) for page_id in reversed(current_ids)])
    assert [page.id for page in window.project.pages] == list(reversed(current_ids))
    window.commands.undo()
    assert [page.id for page in window.project.pages] == current_ids

    close_clean(window)


def test_blank_page_signal_inserts_and_selects_page(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    window = MainWindow(ProjectService(WindowBackend()))

    window.workspace.blank_page_requested.emit(0, 419.53, 595.28)
    qapp.processEvents()

    assert len(window.project.pages) == 1
    blank_page = window.project.pages[0]
    assert blank_page.is_blank
    assert blank_page.blank_size == (419.53, 595.28)
    assert window.centralWidget() is window.workspace
    assert window.workspace.selected_page_ids() == {str(blank_page.id)}
    assert "Page blanche A5 ajoutée" in window.workspace.status.text()
    assert window.commands.can_undo

    close_clean(window)


def test_legacy_blank_page_tool_uses_workspace_and_selects_page(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    window = MainWindow(ProjectService(WindowBackend()))

    window.open_tool("Ajouter une page blanche")
    qapp.processEvents()

    assert len(window.project.pages) == 1
    blank_page = window.project.pages[0]
    assert blank_page.is_blank
    assert blank_page.blank_size == (595.28, 841.89)
    assert window.centralWidget() is window.workspace
    assert window.workspace.selected_page_ids() == {str(blank_page.id)}

    close_clean(window)


def test_duplicate_selects_copies_and_delete_selects_neighbor(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    window = MainWindow(ProjectService(WindowBackend()))
    for index in range(3):
        window.insert_blank_page(index, 595.28, 841.89)
    original_ids = [page.id for page in window.project.pages]

    window.workspace.select_page_ids([original_ids[1]])
    window.workspace.duplicate_requested.emit([1])
    qapp.processEvents()

    assert len(window.project.pages) == 4
    copy_page = window.project.pages[2]
    assert copy_page.id not in original_ids
    assert copy_page.is_blank
    assert window.workspace.selected_page_ids() == {str(copy_page.id)}

    window.workspace.delete_requested.emit([2])
    qapp.processEvents()

    assert [page.id for page in window.project.pages] == original_ids
    assert window.workspace.selected_page_ids() == {str(original_ids[2])}

    close_clean(window)


def test_selectable_mode_persists_and_is_kept_after_import(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    saved = QSettings("PixoGlace", "PixoPDF")
    saved.setValue("workflow/mode", WorkspaceMode.MERGE.value)
    saved.sync()

    window = MainWindow(ProjectService(WindowBackend()))
    assert window.active_mode is WorkspaceMode.MERGE
    assert window.workspace.current_mode is WorkspaceMode.MERGE

    source = tmp_path / "merge-source.pdf"
    source.write_bytes(b"fake")
    window.import_paths([str(source)])
    wait_for_operation(window)
    qapp.processEvents()

    assert len(window.project.pages) == 2
    assert window.centralWidget() is window.workspace
    assert window.active_mode is WorkspaceMode.MERGE
    assert window.workspace.current_mode is WorkspaceMode.MERGE
    assert (
        window.workspace.options_stack.currentWidget()
        is window.workspace.option_panels[WorkspaceMode.MERGE]
    )
    window.settings.sync()
    close_clean(window)

    restored = MainWindow(ProjectService(WindowBackend()))
    assert restored.active_mode is WorkspaceMode.MERGE
    assert restored.workspace.current_mode is WorkspaceMode.MERGE
    close_clean(restored)
