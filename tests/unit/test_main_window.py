from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog

from pixopdf.domain.document import SourceDocument
from pixopdf.domain.project import PdfProject
from pixopdf.pdf.backend import PdfBackend
from pixopdf.services.project_service import ProjectService
from pixopdf.ui.main_window import MainWindow
from pixopdf.ui.tool_modes import WorkspaceMode


class WindowBackend(PdfBackend):
    def __init__(self) -> None:
        self.exported_projects: list[PdfProject] = []

    def page_count(self, path: Path) -> int:
        return 2

    def export(self, project: PdfProject, destination: Path) -> None:
        self.exported_projects.append(project)
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


def test_duplicate_and_soft_delete_keep_selected_thumbnail(
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

    assert len(window.project.pages) == 4
    assert window.project.pages[2].id == copy_page.id
    assert window.project.pages[2].is_deleted
    assert window.project.active_page_count == 3
    assert window.workspace.selected_page_ids() == {str(copy_page.id)}
    assert window.workspace.delete_button.text() == "Restaurer la page"
    assert window.workspace.delete_button.property("actionKind") == "restore"
    assert "marquée(s) supprimée(s)" in window.workspace.status.text()

    window.workspace.delete_button.click()
    qapp.processEvents()

    assert not window.project.pages[2].is_deleted
    assert window.project.active_page_count == 4
    assert window.workspace.selected_page_ids() == {str(copy_page.id)}

    close_clean(window)


def test_export_snapshot_excludes_deleted_pages(
    tmp_path: Path,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    backend = WindowBackend()
    window = MainWindow(ProjectService(backend))
    window.insert_blank_page(0, 595.28, 841.89)
    window.insert_blank_page(1, 595.28, 841.89)
    window.delete_pages([0])
    destination = tmp_path / "soft-delete-export.pdf"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(destination), ""),
    )

    window.export()
    wait_for_operation(window)
    qapp.processEvents()

    assert len(window.project.pages) == 2
    assert window.project.pages[0].is_deleted
    assert len(backend.exported_projects) == 1
    assert len(backend.exported_projects[0].pages) == 1
    assert all(not page.is_deleted for page in backend.exported_projects[0].pages)
    close_clean(window)


def test_export_with_only_deleted_pages_opens_no_dialog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    backend = WindowBackend()
    window = MainWindow(ProjectService(backend))
    window.insert_blank_page(0, 595.28, 841.89)
    window.delete_pages([0])
    dialog_calls: list[bool] = []
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (
            dialog_calls.append(True) or str(tmp_path / "unexpected.pdf"),
            "",
        ),
    )

    window.export()

    assert dialog_calls == []
    assert backend.exported_projects == []
    close_clean(window)


def test_organize_document_remove_action_removes_source_pages_and_undo_restores(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    window = MainWindow(ProjectService(WindowBackend()))
    first = SourceDocument.create(tmp_path / "first.pdf", 2)
    second = SourceDocument.create(tmp_path / "second.pdf", 1)
    window.project.add_document(first)
    window.project.add_document(second)
    original_pages = list(window.project.pages)
    window.commands.mark_clean()
    window.refresh()

    assert window.workspace.organize_documents.count() == 2
    window.workspace.organize_documents.setCurrentRow(0)
    qapp.processEvents()
    window.workspace.organize_remove_document_button.click()
    qapp.processEvents()

    assert list(window.project.documents) == [second.id]
    assert all(page.source_document_id != first.id for page in window.project.pages)
    assert len(window.project.pages) == 1
    assert "first.pdf retiré du workspace" in window.workspace.status.text()

    window.commands.undo()
    qapp.processEvents()

    assert list(window.project.documents) == [first.id, second.id]
    assert window.project.pages == original_pages
    assert window.workspace.organize_documents.count() == 2
    close_clean(window)


def test_split_workspace_can_be_cleared_and_restored(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    window = MainWindow(ProjectService(WindowBackend()))
    source = tmp_path / "split-source.pdf"
    source.write_bytes(b"fake")
    window.import_paths([str(source)])
    wait_for_operation(window)
    window.activate_mode(WorkspaceMode.SPLIT)
    qapp.processEvents()

    assert len(window.project.documents) == 1
    assert len(window.project.pages) == 2
    assert window.workspace.split_documents.count() == 1

    window.workspace.split_clear_workspace_button.click()
    qapp.processEvents()

    assert window.project.documents == {}
    assert window.project.pages == []
    assert window.workspace.split_documents.count() == 0
    assert not window.workspace.export_button.isEnabled()
    assert "Workspace vidé" in window.workspace.status.text()

    window.commands.undo()
    qapp.processEvents()

    assert len(window.project.documents) == 1
    assert len(window.project.pages) == 2
    assert window.workspace.split_documents.count() == 1
    assert window.workspace.export_button.isEnabled()
    close_clean(window)


def test_split_mode_exports_batches_to_selected_directory(
    tmp_path: Path,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    backend = WindowBackend()
    window = MainWindow(ProjectService(backend))
    for index in range(5):
        window.insert_blank_page(index, 595.28, 841.89)
    window.delete_pages([1])
    destination = tmp_path / "split-output"
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: str(destination),
    )

    window.activate_mode(WorkspaceMode.SPLIT)
    window.workspace.split_batch_radio.setChecked(True)
    window.workspace.split_batch_size.setValue(2)
    assert window.workspace.export_button.text() == "Diviser en 2 PDF"
    window.workspace.export_button.click()
    wait_for_operation(window)
    qapp.processEvents()

    assert window.active_mode is WorkspaceMode.SPLIT
    assert [len(project.pages) for project in backend.exported_projects] == [2, 2]
    assert all(
        not page.is_deleted for project in backend.exported_projects for page in project.pages
    )
    assert sorted(path.name for path in destination.glob("*.pdf")) == [
        "pages-pixopdf-partie-01.pdf",
        "pages-pixopdf-partie-02.pdf",
    ]
    assert "2 PDF créé(s)" in window.workspace.status.text()
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
