import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from PySide6.QtCore import QSettings, QSize, Qt, QThreadPool, QUrl
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QMainWindow,
    QMessageBox,
)

from pixopdf.assets import asset_path
from pixopdf.commands import (
    ClearWorkspaceCommand,
    CommandStack,
    DeletePagesCommand,
    DuplicatePagesCommand,
    InsertBlankPageCommand,
    RemoveDocumentCommand,
    ReorderPagesCommand,
    RestorePagesCommand,
    RotatePagesCommand,
)
from pixopdf.config import (
    APP_NAME,
    KOFI_URL,
    ORGANIZATION,
    PROJECT_URL,
    VERSION,
)
from pixopdf.constants import SUPPORTED_PDF_FILTER
from pixopdf.domain.document import SourceDocument
from pixopdf.domain.project import PdfProject
from pixopdf.language_config import DEFAULT_LANGUAGE, LANGUAGES, is_rtl, translate
from pixopdf.pdf.pdfium_renderer import PdfiumRenderer
from pixopdf.services.project_service import ProjectService
from pixopdf.services.split_service import SplitStrategy, build_split_groups
from pixopdf.services.update_service import UpdateResult, UpdateService, UpdateStatus

from .dialogs import AboutDialog, QuickHelpDialog, SettingsDialog
from .themes.theme_manager import Theme, apply_theme
from .tool_modes import MODE_SPECS, WorkspaceMode, coerce_mode
from .workspace.operation_worker import OperationTask
from .workspace.workspace_page import WorkspacePage


class MainWindow(QMainWindow):
    AUTOMATIC_UPDATE_INTERVAL_SECONDS = 24 * 60 * 60

    def __init__(
        self,
        service: ProjectService,
        update_service: UpdateService | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.update_service = update_service or UpdateService()
        self.project = PdfProject()
        self.commands = CommandStack()
        self.settings = QSettings(ORGANIZATION, APP_NAME)
        self.theme = self._saved_theme()
        self.language = self._saved_language()
        self.active_mode = self._saved_mode()
        self._active_task: OperationTask | None = None
        self._update_task: OperationTask | None = None
        self._update_manual = False
        self._closing = False
        self.automatic_update_checks = self._saved_automatic_update_checks()
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, self.theme)
            app.setLayoutDirection(
                Qt.LayoutDirection.RightToLeft
                if is_rtl(self.language)
                else Qt.LayoutDirection.LeftToRight
            )
        self.setAcceptDrops(True)
        self.setMinimumSize(980, 640)
        saved_size = self.settings.value("window/size")
        self.resize(saved_size if isinstance(saved_size, QSize) else QSize(1280, 780))
        self.workspace = WorkspacePage(PdfiumRenderer())
        self.workspace.set_language(self.language)
        self._restore_workspace_preferences()
        self.setCentralWidget(self.workspace)
        self._connect_signals()
        self._create_shortcuts()
        self._create_menus()
        self.activate_mode(self.active_mode)
        self._apply_branding()
        self.refresh()

    def _apply_branding(self) -> None:
        self.workspace.set_theme(self.theme)
        icon_name = "logo_dark.png" if self.theme is Theme.DARK else "logo_white.png"
        icon = QIcon(str(asset_path(icon_name)))
        self.setWindowIcon(icon)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setWindowIcon(icon)

    def _restore_workspace_preferences(self) -> None:
        try:
            thumbnail_width = int(str(self.settings.value("appearance/thumbnail_width", 126)))
        except (TypeError, ValueError):
            thumbnail_width = 126
        self.workspace.zoom_slider.setValue(thumbnail_width)
        self.workspace.zoom_slider.valueChanged.connect(
            lambda value: self.settings.setValue("appearance/thumbnail_width", value)
        )
        raw_sizes = self.settings.value("window/splitter_sizes")
        if isinstance(raw_sizes, (list, tuple)) and len(raw_sizes) in (2, 3):
            try:
                sizes = [int(value) for value in raw_sizes]
            except (TypeError, ValueError):
                sizes = []
            if len(sizes) in (2, 3):
                total = max(1, sum(max(0, value) for value in sizes))
                requested_documents = sizes[0] if len(sizes) == 3 else 230
                requested_context = sizes[2] if len(sizes) == 3 else sizes[0]
                documents_width = min(300, max(220, requested_documents))
                context_width = min(360, max(280, requested_context))
                pages_width = max(1, total - documents_width - context_width)
                self.workspace.splitter.setSizes([documents_width, pages_width, context_width])

    def _saved_theme(self) -> Theme:
        value = str(self.settings.value("appearance/theme", Theme.DARK.value))
        try:
            return Theme(value)
        except ValueError:
            return Theme.DARK

    def _saved_language(self) -> str:
        language = str(self.settings.value("language", DEFAULT_LANGUAGE))
        if language in LANGUAGES:
            return language
        self.settings.setValue("language", DEFAULT_LANGUAGE)
        return DEFAULT_LANGUAGE

    def _saved_automatic_update_checks(self) -> bool:
        value = self.settings.value("updates/automatic", True)
        if isinstance(value, bool):
            return value
        return str(value).strip().casefold() not in {"0", "false", "no", "off"}

    def t(self, key: str, **values: object) -> str:
        return translate(self.language, key, **values)

    def set_language(self, language: str) -> None:
        selected = language if language in LANGUAGES else DEFAULT_LANGUAGE
        self.language = selected
        self.settings.setValue("language", selected)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setLayoutDirection(
                Qt.LayoutDirection.RightToLeft
                if is_rtl(selected)
                else Qt.LayoutDirection.LeftToRight
            )
        self.workspace.set_language(selected)
        self._translate_menus()
        self._update_window_title()

    def _saved_mode(self) -> WorkspaceMode:
        value = str(self.settings.value("workflow/mode", WorkspaceMode.ORGANIZE.value))
        try:
            selected = coerce_mode(value)
        except ValueError:
            return WorkspaceMode.ORGANIZE
        return selected if MODE_SPECS[selected].is_selectable else WorkspaceMode.ORGANIZE

    def _connect_signals(self) -> None:
        self.workspace.add_requested.connect(self.open_files)
        self.workspace.files_dropped.connect(self.import_paths)
        self.workspace.home_requested.connect(self.go_home)
        self.workspace.export_requested.connect(self.execute_primary_action)
        self.workspace.delete_requested.connect(self.delete_pages)
        self.workspace.restore_requested.connect(self.restore_pages)
        self.workspace.remove_document_requested.connect(self.remove_document)
        self.workspace.clear_workspace_requested.connect(self.clear_workspace)
        self.workspace.split_requested.connect(self.split_document)
        self.workspace.duplicate_requested.connect(self.duplicate_pages)
        self.workspace.rotate_requested.connect(self.rotate_pages)
        self.workspace.reorder_requested.connect(self.reorder_pages)
        self.workspace.blank_page_requested.connect(self.insert_blank_page)
        self.workspace.undo_requested.connect(self.undo)
        self.workspace.redo_requested.connect(self.redo)
        self.workspace.theme_requested.connect(self.toggle_theme)
        self.workspace.language_requested.connect(self.set_language)
        self.workspace.mode_requested.connect(self.activate_mode)
        self.workspace.pages.itemSelectionChanged.connect(self._sync_menu_action_state)
        self.workspace.primary_action_changed.connect(self._sync_primary_menu_action)
        self.commands.subscribe(self.refresh)

    def activate_mode(self, mode: WorkspaceMode | str) -> None:
        selected = coerce_mode(mode)
        if not MODE_SPECS[selected].is_selectable:
            return
        self.active_mode = selected
        self.settings.setValue("workflow/mode", selected.value)
        self.workspace.set_mode(selected)
        if hasattr(self, "tool_mode_actions"):
            self.tool_mode_actions[selected].setChecked(True)
            self._translate_menus()
            self._sync_menu_action_state()

    def show_settings_dialog(self) -> None:
        dialog = SettingsDialog(
            self.language,
            self.theme,
            self.automatic_update_checks,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.set_language(dialog.selected_language())
        self.set_theme(dialog.selected_theme())
        self.automatic_update_checks = dialog.automatic_updates_enabled()
        self.settings.setValue(
            "updates/automatic",
            self.automatic_update_checks,
        )

    def show_about_dialog(self) -> None:
        AboutDialog(self.language, self.theme, self).exec()

    def show_quick_help_dialog(self) -> None:
        QuickHelpDialog(self.language, self).exec()

    def _open_external_url(self, url: str) -> None:
        if QDesktopServices.openUrl(QUrl(url)):
            return
        QMessageBox.warning(
            self,
            self.t("external_link_error_title"),
            self.t("external_link_error_message"),
        )

    def open_project_page(self) -> None:
        self._open_external_url(PROJECT_URL)

    def open_sponsor_page(self) -> None:
        self._open_external_url(KOFI_URL)

    def check_for_updates_on_startup(self) -> None:
        if not self.automatic_update_checks or self._closing:
            return
        try:
            last_check = int(str(self.settings.value("updates/last_checked", 0)))
        except (TypeError, ValueError):
            last_check = 0
        if time.time() - last_check < self.AUTOMATIC_UPDATE_INTERVAL_SECONDS:
            return
        self.start_update_check(manual=False)

    def check_for_updates_manually(self) -> None:
        self.start_update_check(manual=True)

    def start_update_check(self, *, manual: bool) -> None:
        if self._update_task is not None or self._closing:
            return
        task = OperationTask(lambda: self.update_service.check(VERSION))
        self._update_task = task
        self._update_manual = manual
        task.signals.succeeded.connect(self._update_check_succeeded)
        task.signals.failed.connect(self._update_check_failed)
        self._sync_menu_action_state()
        if manual:
            self.workspace.show_message(self.t("update_checking"))
        QThreadPool.globalInstance().start(task)

    def _update_check_succeeded(self, result: object) -> None:
        if self._update_task is None:
            return
        manual = self._update_manual
        self._finish_update_check()
        if self._closing:
            return
        if not isinstance(result, UpdateResult):
            if manual:
                self.show_update_check_failed_dialog()
            return
        if result.status is UpdateStatus.AVAILABLE:
            self.show_update_available_dialog(result)
        elif manual:
            self.show_no_update_dialog(result)

    def _update_check_failed(self, _message: str) -> None:
        if self._update_task is None:
            return
        manual = self._update_manual
        self._finish_update_check()
        if manual and not self._closing:
            self.show_update_check_failed_dialog()

    def _finish_update_check(self) -> None:
        self.settings.setValue("updates/last_checked", int(time.time()))
        self._update_task = None
        self._update_manual = False
        self._sync_menu_action_state()

    def show_update_available_dialog(self, result: UpdateResult) -> None:
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Information)
        message.setWindowTitle(self.t("update_available"))
        message.setText(
            self.t(
                "update_available_message",
                app=APP_NAME,
                current=result.current_version,
                latest=result.latest_version,
            )
        )
        if result.release_notes:
            message.setDetailedText(result.release_notes[:8000])
        download_button = message.addButton(
            self.t("download_update"),
            QMessageBox.ButtonRole.AcceptRole,
        )
        message.addButton(
            self.t("update_later"),
            QMessageBox.ButtonRole.RejectRole,
        )
        message.exec()
        if message.clickedButton() is download_button:
            self._open_external_url(result.release_url)

    def show_no_update_dialog(self, result: UpdateResult) -> None:
        QMessageBox.information(
            self,
            self.t("update_current"),
            self.t(
                "update_current_message",
                app=APP_NAME,
                version=result.current_version,
            ),
        )

    def show_update_check_failed_dialog(self) -> None:
        QMessageBox.warning(
            self,
            self.t("update_check_failed"),
            self.t("update_check_failed_message"),
        )

    def go_home(self) -> None:
        """Close the current project and start a clean workspace."""
        if self._active_task is not None:
            return
        self.project = PdfProject()
        self.commands = CommandStack()
        self.commands.subscribe(self.refresh)
        self.activate_mode(WorkspaceMode.ORGANIZE)
        self.refresh()
        self.workspace.show_home()

    def open_tool(self, tool_name: str) -> None:
        if tool_name == "Ajouter une page blanche":
            self.activate_mode(WorkspaceMode.LAYOUT)
            self.insert_blank_page(len(self.project.pages), 595.28, 841.89)
            return
        legacy_modes = {
            "Fusionner": WorkspaceMode.MERGE,
            "Réorganiser": WorkspaceMode.ORGANIZE,
            "Supprimer des pages": WorkspaceMode.ORGANIZE,
            "Tourner des pages": WorkspaceMode.ORGANIZE,
            "Diviser": WorkspaceMode.SPLIT,
            "Mise en page": WorkspaceMode.LAYOUT,
            "Convertir": WorkspaceMode.CONVERT,
            "Protéger": WorkspaceMode.PROTECT,
            "Signer": WorkspaceMode.SIGN,
            "Compresser": WorkspaceMode.COMPRESS,
        }
        selected = legacy_modes.get(tool_name, WorkspaceMode.ORGANIZE)
        if not MODE_SPECS[selected].is_selectable:
            self.workspace.show_message(
                self.t(
                    "feature_unavailable",
                    feature=self.t(f"mode_{selected.value}_label"),
                )
            )
            return
        self.activate_mode(selected)
        if not (self.project.pages or self.project.documents):
            self.open_files()

    def _create_shortcuts(self) -> None:
        self.shortcut_actions: list[QAction] = []

        def shortcut_action(
            shortcut: QKeySequence.StandardKey | str,
            callback: Callable[[], Any],
        ) -> QAction:
            action = QAction(self)
            action.setShortcut(shortcut)
            action.triggered.connect(callback)
            self.addAction(action)
            self.shortcut_actions.append(action)
            return action

        self.new_workspace_action = shortcut_action(
            QKeySequence.StandardKey.New,
            self.go_home,
        )
        self.open_action = shortcut_action(QKeySequence.StandardKey.Open, self.open_files)
        self.export_action = shortcut_action(
            QKeySequence.StandardKey.Save,
            self.execute_primary_action,
        )
        self.quit_action = shortcut_action(QKeySequence.StandardKey.Quit, self.close)
        self.undo_action = shortcut_action(QKeySequence.StandardKey.Undo, self.undo)
        self.redo_action = shortcut_action(QKeySequence.StandardKey.Redo, self.redo)
        self.select_all_action = shortcut_action(
            QKeySequence.StandardKey.SelectAll,
            self.workspace.pages.selectAll,
        )
        self.clear_selection_action = shortcut_action(
            "Esc",
            self.workspace.pages.clearSelection,
        )
        self.duplicate_action = shortcut_action(
            "Ctrl+D",
            lambda: self.duplicate_pages(self.workspace.selected_indices()),
        )
        self.rotate_left_action = shortcut_action(
            "Ctrl+L",
            lambda: self.rotate_pages(self.workspace.selected_indices(), -90),
        )
        self.rotate_right_action = shortcut_action(
            "Ctrl+R",
            lambda: self.rotate_pages(self.workspace.selected_indices(), 90),
        )
        self.blank_page_action = shortcut_action(
            "Ctrl+Shift+B",
            self.workspace.request_default_blank_page,
        )
        self.delete_selection_action = shortcut_action(
            "Delete",
            self.workspace._request_delete,
        )
        self.zoom_in_action = shortcut_action("Ctrl++", self.workspace._zoom_in)
        self.zoom_out_action = shortcut_action("Ctrl+-", self.workspace._zoom_out)
        self.quick_help_action = shortcut_action(
            QKeySequence.StandardKey.HelpContents,
            self.show_quick_help_dialog,
        )

        self.toggle_theme_action = QAction(self)
        self.toggle_theme_action.triggered.connect(self.toggle_theme)
        self.settings_action = QAction(self)
        self.settings_action.setObjectName("settingsAction")
        self.settings_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        self.settings_action.setShortcut(QKeySequence("Ctrl+,"))
        self.settings_action.triggered.connect(self.show_settings_dialog)
        self.project_action = QAction(self)
        self.project_action.triggered.connect(self.open_project_page)
        self.sponsor_action = QAction(self)
        self.sponsor_action.triggered.connect(self.open_sponsor_page)
        self.check_updates_action = QAction(self)
        self.check_updates_action.triggered.connect(self.check_for_updates_manually)
        self.about_action = QAction(self)
        self.about_action.setObjectName("aboutAction")
        self.about_action.setMenuRole(QAction.MenuRole.AboutRole)
        self.about_action.triggered.connect(self.show_about_dialog)
        self.quit_action.setObjectName("quitAction")
        self.quit_action.setMenuRole(QAction.MenuRole.QuitRole)

    def _create_menus(self) -> None:
        menu_bar = self.menuBar()
        if sys.platform == "darwin":
            menu_bar.setNativeMenuBar(True)

        self.file_menu = menu_bar.addMenu("")
        self.file_menu.addAction(self.new_workspace_action)
        self.file_menu.addAction(self.open_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.export_action)
        if sys.platform != "darwin":
            self.file_menu.addSeparator()
        self.file_menu.addAction(self.quit_action)

        self.edit_menu = menu_bar.addMenu("")
        self.edit_menu.addAction(self.undo_action)
        self.edit_menu.addAction(self.redo_action)
        self.edit_menu.addSeparator()
        self.edit_menu.addAction(self.select_all_action)
        self.edit_menu.addAction(self.clear_selection_action)
        self.edit_menu.addSeparator()
        self.edit_menu.addAction(self.duplicate_action)
        self.edit_menu.addAction(self.rotate_left_action)
        self.edit_menu.addAction(self.rotate_right_action)
        self.edit_menu.addAction(self.blank_page_action)
        self.edit_menu.addAction(self.delete_selection_action)

        self.view_menu = menu_bar.addMenu("")
        self.view_menu.addAction(self.zoom_in_action)
        self.view_menu.addAction(self.zoom_out_action)
        self.view_menu.addSeparator()
        self.view_menu.addAction(self.toggle_theme_action)

        self.tools_menu = menu_bar.addMenu("")
        self.tool_mode_group = QActionGroup(self)
        self.tool_mode_group.setExclusive(True)
        self.tool_mode_actions: dict[WorkspaceMode, QAction] = {}
        for mode, spec in MODE_SPECS.items():
            action = QAction(self)
            action.setCheckable(True)
            action.setEnabled(spec.is_selectable)
            action.triggered.connect(
                lambda _checked=False, selected=mode: self.activate_mode(selected)
            )
            self.tool_mode_group.addAction(action)
            self.tool_mode_actions[mode] = action
            self.tools_menu.addAction(action)
        if sys.platform != "darwin":
            self.tools_menu.addSeparator()
        self.tools_menu.addAction(self.settings_action)

        self.help_menu = menu_bar.addMenu("")
        self.help_menu.addAction(self.quick_help_action)
        self.help_menu.addAction(self.project_action)
        self.help_menu.addAction(self.sponsor_action)
        self.help_menu.addSeparator()
        self.help_menu.addAction(self.check_updates_action)
        if sys.platform != "darwin":
            self.help_menu.addSeparator()
        self.help_menu.addAction(self.about_action)

        self._translate_menus()

    def _translate_menus(self) -> None:
        if not hasattr(self, "file_menu"):
            return
        self.file_menu.setTitle(self.t("menu_file"))
        self.edit_menu.setTitle(self.t("menu_edit"))
        self.view_menu.setTitle(self.t("menu_view"))
        self.tools_menu.setTitle(self.t("menu_tools"))
        self.help_menu.setTitle(self.t("menu_help"))

        self.new_workspace_action.setText(self.t("menu_new_workspace"))
        self.open_action.setText(self.t("menu_add_pdfs"))
        self.export_action.setText(self.workspace.export_button.text())
        self.quit_action.setText(self.t("menu_quit"))
        self.undo_action.setText(self.t("undo"))
        self.redo_action.setText(self.t("redo"))
        self.select_all_action.setText(self.t("select_all"))
        self.clear_selection_action.setText(self.t("clear_selection_menu"))
        self.duplicate_action.setText(self.t("duplicate_selected_pages"))
        self.rotate_left_action.setText(self.t("rotate_selected_left"))
        self.rotate_right_action.setText(self.t("rotate_selected_right"))
        self.blank_page_action.setText(self.t("insert_blank_page_menu"))
        self.zoom_in_action.setText(self.t("zoom_in"))
        self.zoom_out_action.setText(self.t("zoom_out"))
        self.toggle_theme_action.setText(
            self.t("switch_to_light_theme" if self.theme is Theme.DARK else "switch_to_dark_theme")
        )
        for mode, spec in MODE_SPECS.items():
            action = self.tool_mode_actions[mode]
            action.setText(self.t(f"mode_{mode.value}_label"))
            action.setToolTip(
                self.t(f"mode_{mode.value}_home_description")
                if spec.is_selectable
                else self.t("feature_unavailable", feature=action.text())
            )
        self.settings_action.setText(self.t("menu_settings"))
        self.quick_help_action.setText(self.t("menu_quick_help"))
        self.project_action.setText(self.t("menu_project_page"))
        self.sponsor_action.setText(self.t("sponsor_kofi"))
        self.check_updates_action.setText(self.t("check_updates"))
        self.about_action.setText(self.t("about_title", app=APP_NAME))
        self._sync_menu_action_state()

    def _sync_menu_action_state(self) -> None:
        if not hasattr(self, "open_action"):
            return
        busy = self._active_task is not None
        selected_indices = self.workspace.selected_indices()
        has_selection = bool(selected_indices)
        selected_deleted = [
            self.project.pages[index].is_deleted
            for index in selected_indices
            if 0 <= index < len(self.project.pages)
        ]
        all_deleted = bool(selected_deleted) and all(selected_deleted)
        contains_deleted = any(selected_deleted)
        has_pages = bool(self.project.pages)
        has_project = bool(self.project.documents or self.project.pages)

        self.new_workspace_action.setEnabled(has_project and not busy)
        self.open_action.setEnabled(not busy)
        self.export_action.setEnabled(self.workspace.export_button.isEnabled() and not busy)
        self.undo_action.setEnabled(self.commands.can_undo and not busy)
        self.redo_action.setEnabled(self.commands.can_redo and not busy)
        self.select_all_action.setEnabled(has_pages and not busy)
        self.clear_selection_action.setEnabled(has_selection and not busy)
        can_edit_selection = has_selection and not contains_deleted and not busy
        self.duplicate_action.setEnabled(can_edit_selection)
        self.rotate_left_action.setEnabled(can_edit_selection)
        self.rotate_right_action.setEnabled(can_edit_selection)
        self.blank_page_action.setEnabled(not busy)
        self.delete_selection_action.setEnabled(has_selection and not busy)
        self.delete_selection_action.setText(
            (
                self.t("restore_page")
                if len(selected_indices) == 1
                else self.t("restore_pages_count", count=len(selected_indices))
            )
            if all_deleted
            else (
                self.t("delete_page")
                if len(selected_indices) <= 1
                else self.t("delete_pages_count", count=len(selected_indices))
            )
        )
        self.zoom_in_action.setEnabled(has_pages and not busy)
        self.zoom_out_action.setEnabled(has_pages and not busy)
        for mode, spec in MODE_SPECS.items():
            self.tool_mode_actions[mode].setEnabled(spec.is_selectable and not busy)
            self.tool_mode_actions[mode].setChecked(mode is self.active_mode)
        self.check_updates_action.setEnabled(self._update_task is None and not self._closing)

    def _sync_primary_menu_action(self) -> None:
        if not hasattr(self, "export_action"):
            return
        self.export_action.setText(self.workspace.export_button.text())
        self._sync_menu_action_state()

    def undo(self) -> None:
        if self._active_task is None:
            self.commands.undo()

    def redo(self) -> None:
        if self._active_task is None:
            self.commands.redo()

    def open_files(self) -> None:
        if self._active_task is not None:
            return
        names, _ = QFileDialog.getOpenFileNames(
            self,
            self.t("open_pdf_dialog"),
            str(self.settings.value("files/last_directory", "")),
            SUPPORTED_PDF_FILTER,
        )
        if names:
            self.import_paths(names)

    def import_paths(self, names: list[str]) -> None:
        paths = [Path(name) for name in names if name.lower().endswith(".pdf")]
        if not paths or self._active_task is not None:
            return
        self.settings.setValue("files/last_directory", str(paths[0].parent))
        self.workspace.show_message(self.t("reading_files", count=len(paths)))
        self._start_operation(
            lambda: self.service.inspect_files(paths),
            self._finish_import,
            self.t("import_error_title"),
        )

    def _finish_import(self, result: object) -> None:
        if not isinstance(result, list) or not all(
            isinstance(document, SourceDocument) for document in result
        ):
            raise TypeError(self.t("import_unexpected"))
        documents: list[SourceDocument] = result
        if self.workspace.is_home and not self.project.documents and not self.project.pages:
            self.commands = CommandStack()
            self.commands.subscribe(self.refresh)
        for document in documents:
            self.project.add_document(document)
        self.commands.invalidate_clean()
        self.refresh()
        page_count = sum(document.page_count for document in documents)
        self.workspace.show_message(
            self.t(
                "documents_added",
                documents=len(documents),
                pages=page_count,
            )
        )

    def delete_pages(self, indices: list[int]) -> None:
        active_indices = [
            index
            for index in sorted(set(indices))
            if 0 <= index < len(self.project.pages) and not self.project.pages[index].is_deleted
        ]
        if active_indices and self._active_task is None:
            selected_ids = [self.project.pages[index].id for index in active_indices]
            self.commands.execute(DeletePagesCommand(self.project, active_indices))
            self.workspace.select_page_ids(selected_ids)
            self.workspace.show_message(self.t("pages_marked_deleted", count=len(active_indices)))

    def restore_pages(self, indices: list[int]) -> None:
        deleted_indices = [
            index
            for index in sorted(set(indices))
            if 0 <= index < len(self.project.pages) and self.project.pages[index].is_deleted
        ]
        if deleted_indices and self._active_task is None:
            selected_ids = [self.project.pages[index].id for index in deleted_indices]
            self.commands.execute(RestorePagesCommand(self.project, deleted_indices))
            self.workspace.select_page_ids(selected_ids)
            self.workspace.show_message(self.t("pages_restored", count=len(deleted_indices)))

    def remove_document(self, document_id: str) -> None:
        if self._active_task is not None:
            return
        try:
            identifier = UUID(document_id)
        except ValueError:
            return
        document = self.project.documents.get(identifier)
        if document is None:
            return
        command = RemoveDocumentCommand(self.project, identifier)
        self.commands.execute(command)
        self.workspace.show_message(
            self.t(
                "document_removed",
                name=document.display_name,
                pages=command.removed_page_count,
            )
        )

    def clear_workspace(self) -> None:
        if self._active_task is not None or (not self.project.documents and not self.project.pages):
            return
        command = ClearWorkspaceCommand(self.project)
        self.commands.execute(command)
        self.workspace.show_message(
            self.t(
                "workspace_cleared",
                documents=command.removed_document_count,
                pages=command.removed_page_count,
            )
        )

    def duplicate_pages(self, indices: list[int]) -> None:
        active_indices = [
            index
            for index in sorted(set(indices))
            if 0 <= index < len(self.project.pages) and not self.project.pages[index].is_deleted
        ]
        if active_indices and self._active_task is None:
            command = DuplicatePagesCommand(self.project, active_indices)
            self.commands.execute(command)
            self.workspace.select_page_ids(command.inserted_page_ids)
            self.workspace.show_message(self.t("pages_duplicated", count=len(active_indices)))

    def insert_blank_page(self, index: int, width: float, height: float) -> None:
        if self._active_task is not None:
            return
        command = InsertBlankPageCommand(self.project, index, page_size=(width, height))
        self.commands.execute(command)
        self.workspace.select_page_ids(command.inserted_page_ids)
        format_name = self._blank_format_name(width, height)
        self.workspace.show_message(self.t("blank_page_added", format=format_name))

    @staticmethod
    def _blank_format_name(width: float, height: float) -> str:
        if (round(width, 1), round(height, 1)) == (841.9, 595.3):
            return "A4 paysage"
        if (round(width, 1), round(height, 1)) == (419.5, 595.3):
            return "A5"
        return "A4"

    def rotate_pages(self, indices: list[int], degrees: int) -> None:
        active_indices = [
            index
            for index in sorted(set(indices))
            if 0 <= index < len(self.project.pages) and not self.project.pages[index].is_deleted
        ]
        if active_indices and self._active_task is None:
            self.commands.execute(RotatePagesCommand(self.project, active_indices, degrees))
            direction = self.t("left") if degrees < 0 else self.t("right")
            self.workspace.show_message(
                self.t(
                    "pages_rotated",
                    count=len(active_indices),
                    direction=direction,
                )
            )

    def reorder_pages(self, ordered_values: list[object]) -> None:
        if self._active_task is not None:
            self.refresh()
            return
        try:
            ordered_ids = [UUID(str(value)) for value in ordered_values]
        except ValueError:
            self.refresh()
            self.workspace.show_message(self.t("reorder_failed"), error=True)
            return
        current_ids = [page.id for page in self.project.pages]
        if ordered_ids == current_ids:
            return
        selected_ids: set[UUID] = set()
        for value in self.workspace.selected_page_ids():
            try:
                selected_ids.add(UUID(value))
            except ValueError:
                continue
        selected_ids.intersection_update(current_ids)
        try:
            self.commands.execute(
                ReorderPagesCommand(
                    self.project,
                    ordered_ids,
                    moved_ids=selected_ids or None,
                )
            )
        except ValueError as exc:
            self.refresh()
            self.workspace.show_message(str(exc), error=True)
            return
        self.workspace.show_message(self.t("page_order_updated"))

    def split_document(
        self,
        strategy_value: str,
        batch_size: int,
        ranges: str,
    ) -> None:
        if self._active_task is not None or not self.project.active_page_count:
            return
        try:
            strategy = SplitStrategy(strategy_value)
            groups = build_split_groups(
                self.project.active_page_count,
                strategy,
                batch_size=batch_size,
                ranges=ranges,
            )
        except ValueError as exc:
            self.workspace.show_message(str(exc), error=True)
            return
        directory = QFileDialog.getExistingDirectory(
            self,
            self.t("split_folder_dialog"),
            str(self.settings.value("files/last_directory", "")),
        )
        if not directory:
            return
        destination = Path(directory)
        self.settings.setValue("files/last_directory", str(destination))
        if len(self.project.documents) == 1:
            base_name = next(iter(self.project.documents.values())).path.stem
        elif self.project.documents:
            base_name = "projet-pixopdf"
        else:
            base_name = "pages-pixopdf"
        snapshot = PdfProject(
            documents=dict(self.project.documents),
            pages=list(self.project.active_pages),
            modified=False,
        )
        self.workspace.show_message(self.t("split_in_progress", count=len(groups)))
        self._start_operation(
            lambda: self.service.split(snapshot, destination, groups, base_name),
            self._finish_split,
            self.t("split_error_title"),
        )

    def execute_primary_action(self) -> None:
        """Run the action represented by the primary top-bar button."""
        if self.active_mode is WorkspaceMode.SPLIT:
            self.workspace.request_split()
            return
        self.export()

    def _finish_split(self, result: object) -> None:
        if (
            not isinstance(result, list)
            or not result
            or not all(isinstance(path, Path) for path in result)
        ):
            raise TypeError(self.t("split_unexpected"))
        destination = result[0].parent
        self.workspace.show_message(
            self.t("split_created", count=len(result), destination=destination)
        )

    def export(self) -> None:
        if not self.project.active_page_count or self._active_task is not None:
            return
        if self.active_mode is WorkspaceMode.MERGE and len(self.project.documents) < 2:
            self.workspace.show_message(self.t("merge_need_two"), error=True)
            return
        if not self.project.documents:
            default_name = "page-blanche.pdf"
        elif len(self.project.documents) > 1:
            default_name = "fusion-pixopdf.pdf"
        else:
            default_name = "document-modifie.pdf"
        name, _ = QFileDialog.getSaveFileName(
            self,
            self.t("export_pdf_dialog"),
            str(Path(str(self.settings.value("files/last_directory", ""))) / default_name),
            SUPPORTED_PDF_FILTER,
        )
        if not name:
            return
        destination = Path(name)
        if destination.suffix.lower() != ".pdf":
            destination = destination.with_suffix(".pdf")
        source_paths = {document.path.resolve() for document in self.project.documents.values()}
        if destination.resolve() in source_paths:
            QMessageBox.warning(
                self,
                self.t("invalid_destination_title"),
                self.t("invalid_destination_message"),
            )
            return
        snapshot = PdfProject(
            documents=dict(self.project.documents),
            pages=list(self.project.active_pages),
            modified=False,
        )
        self.workspace.show_message(self.t("export_in_progress"))
        self._start_operation(
            lambda: self._export_snapshot(snapshot, destination),
            self._finish_export,
            self.t("export_error_title"),
        )

    def _export_snapshot(self, project: PdfProject, destination: Path) -> Path:
        self.service.export(project, destination)
        return destination

    def _finish_export(self, result: object) -> None:
        if not isinstance(result, Path):
            raise TypeError(self.t("export_unexpected"))
        self.project.modified = False
        self.commands.mark_clean()
        self.refresh()
        self.workspace.show_message(self.t("export_done", destination=result))

    def _start_operation(
        self,
        operation: Callable[[], Any],
        on_success: Callable[[object], None],
        error_title: str,
    ) -> None:
        task = OperationTask(operation)
        self._active_task = task
        self._set_busy(True)
        task.signals.succeeded.connect(
            lambda result: self._operation_succeeded(task, result, on_success)
        )
        task.signals.failed.connect(
            lambda message: self._operation_failed(task, error_title, message)
        )
        QThreadPool.globalInstance().start(task)

    def _operation_succeeded(
        self,
        task: OperationTask,
        result: object,
        callback: Callable[[object], None],
    ) -> None:
        if task is not self._active_task:
            return
        self._active_task = None
        self._set_busy(False)
        try:
            callback(result)
        except Exception as exc:
            self.workspace.show_message(str(exc), error=True)

    def _operation_failed(self, task: OperationTask, title: str, message: str) -> None:
        if task is not self._active_task:
            return
        self._active_task = None
        self._set_busy(False)
        self.workspace.show_message(message, error=True)
        QMessageBox.critical(self, title, message)

    def _set_busy(self, busy: bool) -> None:
        self.workspace.setEnabled(not busy)
        for action in self.shortcut_actions:
            action.setEnabled(not busy)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            if busy:
                app.setOverrideCursor(Qt.CursorShape.WaitCursor)
            elif app.overrideCursor() is not None:
                app.restoreOverrideCursor()
        self._sync_menu_action_state()

    def refresh(self) -> None:
        self.project.modified = not self.commands.is_clean
        self.workspace.refresh(self.project)
        self.workspace.set_history_state(self.commands.can_undo, self.commands.can_redo)
        self._translate_menus()
        self._update_window_title()

    def _update_window_title(self) -> None:
        marker = "*" if self.project.modified else ""
        self.setWindowTitle(f"{self.t('untitled_project')}{marker} — {APP_NAME}")

    def toggle_theme(self) -> None:
        self.set_theme(Theme.LIGHT if self.theme == Theme.DARK else Theme.DARK)

    def set_theme(self, theme: Theme | str) -> None:
        try:
            selected = theme if isinstance(theme, Theme) else Theme(theme)
        except ValueError:
            selected = Theme.DARK
        if selected is self.theme:
            return
        self.theme = selected
        self.settings.setValue("appearance/theme", self.theme.value)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, self.theme)
        self._apply_branding()
        self._translate_menus()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if urls and all(
            url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf") for url in urls
        ):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if not urls or not all(
            url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf") for url in urls
        ):
            event.ignore()
            return
        self.import_paths([url.toLocalFile() for url in urls])
        event.acceptProposedAction()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._active_task is not None:
            QMessageBox.information(
                self,
                self.t("operation_in_progress_title"),
                self.t("operation_in_progress_message"),
            )
            event.ignore()
            return
        if self.project.modified and (self.project.documents or self.project.pages):
            message = QMessageBox(self)
            message.setIcon(QMessageBox.Icon.Warning)
            message.setWindowTitle(self.t("unexported_project_title"))
            message.setText(self.t("unexported_project_text"))
            message.setInformativeText(self.t("unexported_project_question"))
            export_button = message.addButton(
                self.t("export_ellipsis"),
                QMessageBox.ButtonRole.AcceptRole,
            )
            discard_button = message.addButton(
                self.t("quit_without_export"),
                QMessageBox.ButtonRole.DestructiveRole,
            )
            message.addButton(QMessageBox.StandardButton.Cancel)
            message.exec()
            if message.clickedButton() is export_button:
                event.ignore()
                self.export()
                return
            if message.clickedButton() is not discard_button:
                event.ignore()
                return
        self.settings.setValue("window/size", self.size())
        self.settings.setValue("window/splitter_sizes", self.workspace.splitter.sizes())
        self._closing = True
        self._update_task = None
        self.workspace.shutdown()
        event.accept()
