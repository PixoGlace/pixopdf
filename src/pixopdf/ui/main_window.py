from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from PySide6.QtCore import QSettings, QSize, Qt, QThreadPool
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
)

from pixopdf.assets import asset_path
from pixopdf.commands import (
    CommandStack,
    DeletePagesCommand,
    DuplicatePagesCommand,
    InsertBlankPageCommand,
    RemoveDocumentCommand,
    ReorderPagesCommand,
    RestorePagesCommand,
    RotatePagesCommand,
)
from pixopdf.constants import SUPPORTED_PDF_FILTER
from pixopdf.domain.document import SourceDocument
from pixopdf.domain.project import PdfProject
from pixopdf.pdf.pdfium_renderer import PdfiumRenderer
from pixopdf.services.project_service import ProjectService

from .themes.theme_manager import Theme, apply_theme
from .tool_modes import MODE_SPECS, WorkspaceMode, coerce_mode
from .workspace.operation_worker import OperationTask
from .workspace.workspace_page import WorkspacePage


class MainWindow(QMainWindow):
    def __init__(self, service: ProjectService) -> None:
        super().__init__()
        self.service = service
        self.project = PdfProject()
        self.commands = CommandStack()
        self.settings = QSettings("PixoGlace", "PixoPDF")
        self.theme = self._saved_theme()
        self.active_mode = self._saved_mode()
        self._active_task: OperationTask | None = None
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, self.theme)
        self.setAcceptDrops(True)
        self.setMinimumSize(980, 640)
        saved_size = self.settings.value("window/size")
        self.resize(saved_size if isinstance(saved_size, QSize) else QSize(1280, 780))
        self.workspace = WorkspacePage(PdfiumRenderer())
        self._restore_workspace_preferences()
        self.setCentralWidget(self.workspace)
        self._connect_signals()
        self.activate_mode(self.active_mode)
        self._create_shortcuts()
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
                requested_context = sizes[2] if len(sizes) == 3 else sizes[0]
                context_width = min(360, max(280, requested_context))
                self.workspace.splitter.setSizes([context_width, max(1, total - context_width)])

    def _saved_theme(self) -> Theme:
        value = str(self.settings.value("appearance/theme", Theme.DARK.value))
        try:
            return Theme(value)
        except ValueError:
            return Theme.DARK

    def _saved_mode(self) -> WorkspaceMode:
        value = str(self.settings.value("workflow/mode", WorkspaceMode.ORGANIZE.value))
        try:
            selected = coerce_mode(value)
        except ValueError:
            return WorkspaceMode.ORGANIZE
        return selected if MODE_SPECS[selected].is_selectable else WorkspaceMode.ORGANIZE

    def _connect_signals(self) -> None:
        self.workspace.add_requested.connect(self.open_files)
        self.workspace.export_requested.connect(self.export)
        self.workspace.delete_requested.connect(self.delete_pages)
        self.workspace.restore_requested.connect(self.restore_pages)
        self.workspace.remove_document_requested.connect(self.remove_document)
        self.workspace.duplicate_requested.connect(self.duplicate_pages)
        self.workspace.rotate_requested.connect(self.rotate_pages)
        self.workspace.reorder_requested.connect(self.reorder_pages)
        self.workspace.blank_page_requested.connect(self.insert_blank_page)
        self.workspace.undo_requested.connect(self.undo)
        self.workspace.redo_requested.connect(self.redo)
        self.workspace.theme_requested.connect(self.toggle_theme)
        self.workspace.mode_requested.connect(self.activate_mode)
        self.commands.subscribe(self.refresh)

    def activate_mode(self, mode: WorkspaceMode | str) -> None:
        selected = coerce_mode(mode)
        if not MODE_SPECS[selected].is_selectable:
            return
        self.active_mode = selected
        self.settings.setValue("workflow/mode", selected.value)
        self.workspace.set_mode(selected)

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
            self.workspace.show_message(f"{MODE_SPECS[selected].label} sera bientôt disponible")
            return
        self.activate_mode(selected)
        if not (self.project.pages or self.project.documents):
            self.open_files()

    def _create_shortcuts(self) -> None:
        shortcuts: tuple[tuple[QKeySequence.StandardKey | str, Callable[[], Any]], ...] = (
            (QKeySequence.StandardKey.Open, self.open_files),
            (QKeySequence.StandardKey.Save, self.export),
            (QKeySequence.StandardKey.Undo, self.undo),
            (QKeySequence.StandardKey.Redo, self.redo),
            (QKeySequence.StandardKey.SelectAll, self.workspace.pages.selectAll),
            ("Ctrl+D", lambda: self.duplicate_pages(self.workspace.selected_indices())),
            ("Ctrl+L", lambda: self.rotate_pages(self.workspace.selected_indices(), -90)),
            ("Ctrl+R", lambda: self.rotate_pages(self.workspace.selected_indices(), 90)),
            ("Ctrl+Shift+B", self.workspace.request_default_blank_page),
            ("Ctrl++", self.workspace._zoom_in),
            ("Ctrl+-", self.workspace._zoom_out),
        )
        self.shortcut_actions: list[QAction] = []
        for shortcut, callback in shortcuts:
            action = QAction(self)
            action.setShortcut(shortcut)
            action.triggered.connect(callback)
            self.addAction(action)
            self.shortcut_actions.append(action)

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
            "Ouvrir des PDF",
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
        self.workspace.show_message(f"Lecture de {len(paths)} fichier(s)…")
        self._start_operation(
            lambda: self.service.inspect_files(paths),
            self._finish_import,
            "Import impossible",
        )

    def _finish_import(self, result: object) -> None:
        if not isinstance(result, list) or not all(
            isinstance(document, SourceDocument) for document in result
        ):
            raise TypeError("Résultat d’import inattendu")
        documents: list[SourceDocument] = result
        for document in documents:
            self.project.add_document(document)
        self.commands.invalidate_clean()
        self.refresh()
        page_count = sum(document.page_count for document in documents)
        self.workspace.show_message(
            f"{len(documents)} document(s) ajouté(s) • {page_count} page(s)"
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
            self.workspace.show_message(
                f"{len(active_indices)} page(s) marquée(s) supprimée(s) • "
                "elles ne seront pas exportées"
            )

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
            self.workspace.show_message(f"{len(deleted_indices)} page(s) restaurée(s)")

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
            f"{document.display_name} retiré du workspace • "
            f"{command.removed_page_count} page(s) retirée(s) • Ctrl+Z pour annuler"
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
            self.workspace.show_message(f"{len(active_indices)} page(s) dupliquée(s)")

    def insert_blank_page(self, index: int, width: float, height: float) -> None:
        if self._active_task is not None:
            return
        command = InsertBlankPageCommand(self.project, index, page_size=(width, height))
        self.commands.execute(command)
        self.workspace.select_page_ids(command.inserted_page_ids)
        format_name = self._blank_format_name(width, height)
        self.workspace.show_message(f"Page blanche {format_name} ajoutée • Ctrl+Z pour annuler")

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
            direction = "gauche" if degrees < 0 else "droite"
            self.workspace.show_message(
                f"{len(active_indices)} page(s) tournée(s) vers la {direction}"
            )

    def reorder_pages(self, ordered_values: list[object]) -> None:
        if self._active_task is not None:
            self.refresh()
            return
        try:
            ordered_ids = [UUID(str(value)) for value in ordered_values]
        except ValueError:
            self.refresh()
            self.workspace.show_message("La réorganisation a échoué", error=True)
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
        self.workspace.show_message("Ordre des pages mis à jour • Ctrl+Z pour annuler")

    def export(self) -> None:
        if not self.project.active_page_count or self._active_task is not None:
            return
        if self.active_mode is WorkspaceMode.MERGE and len(self.project.documents) < 2:
            self.workspace.show_message(
                "Ajoutez au moins deux PDF pour lancer la fusion.",
                error=True,
            )
            return
        if not self.project.documents:
            default_name = "page-blanche.pdf"
        elif len(self.project.documents) > 1:
            default_name = "fusion-pixopdf.pdf"
        else:
            default_name = "document-modifie.pdf"
        name, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter le PDF",
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
                "Destination invalide",
                "Choisissez un nouveau fichier : PixoPDF ne remplace jamais un document source.",
            )
            return
        snapshot = PdfProject(
            documents=dict(self.project.documents),
            pages=list(self.project.active_pages),
            modified=False,
        )
        self.workspace.show_message("Export du PDF en cours…")
        self._start_operation(
            lambda: self._export_snapshot(snapshot, destination),
            self._finish_export,
            "Export impossible",
        )

    def _export_snapshot(self, project: PdfProject, destination: Path) -> Path:
        self.service.export(project, destination)
        return destination

    def _finish_export(self, result: object) -> None:
        if not isinstance(result, Path):
            raise TypeError("Résultat d’export inattendu")
        self.project.modified = False
        self.commands.mark_clean()
        self.refresh()
        self.workspace.show_message(f"PDF exporté dans {result}")

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

    def refresh(self) -> None:
        self.project.modified = not self.commands.is_clean
        self.workspace.refresh(self.project)
        self.workspace.set_history_state(self.commands.can_undo, self.commands.can_redo)
        marker = "*" if self.project.modified else ""
        self.setWindowTitle(f"Projet sans titre{marker} — PixoPDF")

    def toggle_theme(self) -> None:
        self.theme = Theme.LIGHT if self.theme == Theme.DARK else Theme.DARK
        self.settings.setValue("appearance/theme", self.theme.value)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, self.theme)
        self._apply_branding()

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
                "Opération en cours",
                "Attendez la fin de l’opération avant de quitter PixoPDF.",
            )
            event.ignore()
            return
        if self.project.modified and (self.project.documents or self.project.pages):
            message = QMessageBox(self)
            message.setIcon(QMessageBox.Icon.Warning)
            message.setWindowTitle("Projet non exporté")
            message.setText("Des modifications n’ont pas été exportées.")
            message.setInformativeText("Voulez-vous exporter avant de quitter ?")
            export_button = message.addButton("Exporter…", QMessageBox.ButtonRole.AcceptRole)
            discard_button = message.addButton(
                "Quitter sans exporter", QMessageBox.ButtonRole.DestructiveRole
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
        self.workspace.shutdown()
        event.accept()
