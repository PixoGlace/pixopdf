from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

from pixopdf.domain.page import PageReference
from pixopdf.domain.project import PdfProject
from pixopdf.pdf.backend import PdfBackend
from pixopdf.pdf.renderer import PdfRenderer
from pixopdf.services.project_service import ProjectService
from pixopdf.ui.main_window import MainWindow
from pixopdf.ui.tool_modes import WorkspaceMode
from pixopdf.ui.workspace.workspace_page import WorkspacePage


class UnusedRenderer(PdfRenderer):
    def render_page(
        self,
        file_path: Path,
        page_index: int,
        width: int,
        height: int,
    ) -> bytes:
        raise AssertionError("Blank pages do not need the PDF renderer")


class EmptyBackend(PdfBackend):
    def page_count(self, path: Path) -> int:
        return 0

    def export(self, project: PdfProject, destination: Path) -> None:
        destination.write_bytes(b"")


def _blank_project(count: int = 2) -> PdfProject:
    return PdfProject(pages=[PageReference.blank() for _ in range(count)])


def _close_clean(window: MainWindow) -> None:
    window.commands.mark_clean()
    window.refresh()
    window.close()


def test_workspace_switches_four_languages_and_keeps_pdf_order_ltr(
    qapp: QApplication,
) -> None:
    workspace = WorkspacePage(UnusedRenderer())
    try:
        assert not hasattr(workspace, "language_combo")
        assert not hasattr(workspace, "theme_button")

        workspace.set_language("en")
        assert workspace.home_title.text() == "Welcome to PixoPDF"
        assert workspace.mode_buttons[WorkspaceMode.SPLIT].text() == "Split"
        assert workspace.layoutDirection() == Qt.LayoutDirection.LeftToRight

        workspace.set_language("zh")
        assert workspace.home_title.text() == "欢迎使用 PixoPDF"
        assert workspace.mode_buttons[WorkspaceMode.MERGE].text() == "合并"

        workspace.set_language("ar")
        assert workspace.home_title.text() == "مرحباً بك في PixoPDF"
        assert workspace.layoutDirection() == Qt.LayoutDirection.RightToLeft
        assert workspace.pages.layoutDirection() == Qt.LayoutDirection.LeftToRight
    finally:
        workspace.shutdown()
        qapp.setLayoutDirection(Qt.LayoutDirection.LeftToRight)


def test_language_change_preserves_mode_pages_and_selection(qapp: QApplication) -> None:
    workspace = WorkspacePage(UnusedRenderer())
    project = _blank_project(3)
    workspace.set_mode(WorkspaceMode.SPLIT)
    workspace.refresh(project)
    workspace.select_page_ids([project.pages[1].id])

    try:
        original_ids = [
            workspace.pages.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(workspace.pages.count())
        ]

        workspace.set_language("en")

        assert workspace.current_mode is WorkspaceMode.SPLIT
        assert workspace.pages.count() == 3
        assert workspace.selected_page_ids() == {str(project.pages[1].id)}
        assert [
            workspace.pages.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(workspace.pages.count())
        ] == original_ids
        assert workspace.split_each_radio.text() == "One PDF per page"
    finally:
        workspace.shutdown()
        qapp.setLayoutDirection(Qt.LayoutDirection.LeftToRight)


def test_main_window_persists_language_and_restores_rtl(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    settings = QSettings("PixoGlace", "PixoPDF")
    settings.clear()

    first = MainWindow(ProjectService(EmptyBackend()))
    first.set_language("ar")
    first.settings.sync()
    assert first.settings.value("language") == "ar"
    assert qapp.layoutDirection() == Qt.LayoutDirection.RightToLeft
    _close_clean(first)

    second = MainWindow(ProjectService(EmptyBackend()))
    try:
        assert second.language == "ar"
        assert second.workspace.language == "ar"
        assert not hasattr(second.workspace, "language_combo")
        assert not hasattr(second.workspace, "theme_button")
        assert second.windowTitle().startswith("مشروع بلا عنوان")
        assert qapp.layoutDirection() == Qt.LayoutDirection.RightToLeft
    finally:
        second.set_language("fr")
        _close_clean(second)
        qapp.setLayoutDirection(Qt.LayoutDirection.LeftToRight)


def test_invalid_saved_language_falls_back_to_french(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    settings = QSettings("PixoGlace", "PixoPDF")
    settings.clear()
    settings.setValue("language", "xx")
    settings.sync()

    window = MainWindow(ProjectService(EmptyBackend()))
    try:
        assert window.language == "fr"
        assert window.workspace.home_title.text() == "Bienvenue dans PixoPDF"
        assert window.settings.value("language") == "fr"
    finally:
        _close_clean(window)
        qapp.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
