from collections import OrderedDict
from collections.abc import Callable, Sequence

from PySide6.QtCore import (
    QMimeData,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QRect,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDrag,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QIcon,
    QKeyEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QPolygon,
    QTransform,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pixopdf.assets import asset_path
from pixopdf.domain.page import PageChange, PageReference
from pixopdf.domain.project import PdfProject
from pixopdf.language_config import DEFAULT_LANGUAGE, LANGUAGES, is_rtl, translate
from pixopdf.pdf.renderer import PdfRenderer
from pixopdf.services.split_service import SplitStrategy, build_split_groups
from pixopdf.ui.themes.theme_manager import Theme
from pixopdf.ui.tool_modes import (
    MODE_SPECS,
    ModeSpec,
    ModeStatus,
    WorkspaceMode,
    coerce_mode,
)

from .thumbnail_worker import ThumbnailKey, ThumbnailTask

PAGE_ID_ROLE = Qt.ItemDataRole.UserRole
SEARCH_ROLE = Qt.ItemDataRole.UserRole + 1
DISPLAY_ROLE = Qt.ItemDataRole.UserRole + 2
STABLE_NUMBER_ROLE = Qt.ItemDataRole.UserRole + 3
CURRENT_POSITION_ROLE = Qt.ItemDataRole.UserRole + 4
PAGE_CHANGE_ROLE = Qt.ItemDataRole.UserRole + 5
DOCUMENT_ID_ROLE = Qt.ItemDataRole.UserRole + 6
SPLIT_GROUPS_ROLE = Qt.ItemDataRole.UserRole + 7
BASE_TOOLTIP_ROLE = Qt.ItemDataRole.UserRole + 8
THUMBNAIL_WIDTH = 180
THUMBNAIL_HEIGHT = 234
PAGE_MIME_TYPE = "application/x-pixopdf-pages"
A4_PORTRAIT = (595.28, 841.89)
A4_LANDSCAPE = (841.89, 595.28)
A5_PORTRAIT = (419.53, 595.28)


def page_change_label(changes: PageChange, language: str = DEFAULT_LANGUAGE) -> str:
    if changes & PageChange.DELETED:
        return translate(language, "page_change_deleted")
    labels: list[str] = []
    if changes & PageChange.ADDED:
        labels.append(translate(language, "page_change_added"))
    if changes & PageChange.MOVED:
        labels.append(translate(language, "page_change_moved"))
    if changes & PageChange.MODIFIED:
        labels.append(translate(language, "page_change_modified"))
    return " + ".join(labels).capitalize()


class PageItemDelegate(QStyledItemDelegate):
    """Draw a persistent, non-color-only marker around changed pages."""

    SPLIT_COLORS = (
        "#14B8A6",
        "#F59E0B",
        "#38BDF8",
        "#A78BFA",
        "#FB7185",
        "#84CC16",
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.language = DEFAULT_LANGUAGE

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        super().paint(painter, option, index)
        split_groups = index.data(SPLIT_GROUPS_ROLE)
        if split_groups is not None:
            self._paint_split_preview(painter, option.rect, tuple(split_groups))

        changes = PageChange(int(index.data(PAGE_CHANGE_ROLE) or 0))
        label = page_change_label(changes, self.language)
        if not label:
            return

        deleted = bool(changes & PageChange.DELETED)
        moved_color = QColor("#14B8A6")
        modified_color = QColor("#F59E0B")
        deleted_color = QColor("#64748B")
        border_color = (
            deleted_color
            if deleted
            else moved_color
            if changes & PageChange.MOVED
            else modified_color
        )
        badge_color = (
            deleted_color
            if deleted
            else modified_color
            if changes & (PageChange.MODIFIED | PageChange.ADDED)
            else moved_color
        )
        marker_rect = option.rect.adjusted(3, 3, -3, -3)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if deleted:
            deleted_overlay = QColor("#64748B")
            deleted_overlay.setAlpha(165)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(deleted_overlay)
            painter.drawRoundedRect(marker_rect, 8, 8)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(border_color, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawRoundedRect(marker_rect, 8, 8)

        font = painter.font()
        font.setBold(True)
        font.setPixelSize(10)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        maximum_width = max(30, marker_rect.width() - 14)
        badge_text = metrics.elidedText(label, Qt.TextElideMode.ElideRight, maximum_width - 14)
        badge_width = min(maximum_width, metrics.horizontalAdvance(badge_text) + 14)
        badge_rect = QRect(
            marker_rect.left() + 7,
            marker_rect.top() + 7,
            badge_width,
            20,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(badge_color)
        painter.drawRoundedRect(badge_rect, 6, 6)
        painter.setPen(QColor("#FFFFFF") if deleted else QColor("#172B4D"))
        painter.drawText(
            badge_rect,
            Qt.AlignmentFlag.AlignCenter,
            badge_text,
        )
        painter.restore()

    def _paint_split_preview(
        self,
        painter: QPainter,
        item_rect: QRect,
        groups: tuple[int, ...],
    ) -> None:
        marker_rect = item_rect.adjusted(4, 4, -4, -4)
        included = bool(groups)
        color = QColor(
            self.SPLIT_COLORS[(groups[0] - 1) % len(self.SPLIT_COLORS)] if included else "#64748B"
        )
        label = (
            translate(self.language, "generated_pdf", number=groups[0])
            if len(groups) == 1
            else translate(
                self.language,
                "generated_pdf_more",
                number=groups[0],
                count=len(groups) - 1,
            )
            if groups
            else translate(self.language, "outside_output")
        )

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not included:
            overlay = QColor("#64748B")
            overlay.setAlpha(42)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(overlay)
            painter.drawRoundedRect(marker_rect, 9, 9)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(
            QPen(
                color,
                3,
                Qt.PenStyle.SolidLine if included else Qt.PenStyle.DashLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        painter.drawRoundedRect(marker_rect, 9, 9)

        font = painter.font()
        font.setBold(True)
        font.setPixelSize(10)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        maximum_width = max(52, marker_rect.width() - 14)
        badge_text = metrics.elidedText(label, Qt.TextElideMode.ElideRight, maximum_width - 14)
        badge_width = min(maximum_width, metrics.horizontalAdvance(badge_text) + 14)
        badge_rect = QRect(
            marker_rect.right() - badge_width - 7,
            marker_rect.top() + 7,
            badge_width,
            20,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(badge_rect, 6, 6)
        painter.setPen(QColor("#172B4D") if included else QColor("#FFFFFF"))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)
        painter.restore()


class PageListWidget(QListWidget):
    reordered = Signal(list)
    delete_pressed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._drop_position: int | None = None

    def startDrag(self, _supported_actions: Qt.DropAction) -> None:
        if any(
            PageChange(int(item.data(PAGE_CHANGE_ROLE) or 0)) & PageChange.DELETED
            for item in self.selectedItems()
        ):
            return
        selected_ids = [
            str(self.item(row).data(PAGE_ID_ROLE))
            for row in sorted(self.row(item) for item in self.selectedItems())
        ]
        if not selected_ids:
            return
        mime_data = self.model().mimeData(self.selectedIndexes()) or QMimeData()
        mime_data.setData(PAGE_MIME_TYPE, "\n".join(selected_ids).encode())
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        first_selected = self.selectedItems()[0]
        pixmap = first_selected.icon().pixmap(self.iconSize())
        if not pixmap.isNull():
            drag.setPixmap(pixmap)
            drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
        try:
            drag.exec(Qt.DropAction.MoveAction)
        finally:
            self._clear_drop_indicator()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if (
            event.source() is self
            and event.mimeData().hasFormat(PAGE_MIME_TYPE)
            and self.selectedItems()
        ):
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            return
        event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.source() is not self or not event.mimeData().hasFormat(PAGE_MIME_TYPE):
            event.ignore()
            return
        super().dragMoveEvent(event)
        self._drop_position = self._drop_index_at(event.position().toPoint())
        self.viewport().update()
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._clear_drop_indicator()
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        if (
            event.source() is not self
            or not event.mimeData().hasFormat(PAGE_MIME_TYPE)
            or self._drop_position is None
        ):
            self._clear_drop_indicator()
            event.ignore()
            return
        ordered_ids = self._reordered_ids(self._drop_position)
        self._clear_drop_indicator()
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()
        if ordered_ids and ordered_ids != self._current_ids():
            QTimer.singleShot(0, lambda ids=ordered_ids: self.reordered.emit(ids))

    def _drop_index_at(self, position: QPoint) -> int:
        if self.count() == 0:
            return 0
        index = self.indexAt(position)
        if index.isValid():
            rect = self.visualRect(index)
            return index.row() if position.x() < rect.center().x() else index.row() + 1
        first_rect = self.visualItemRect(self.item(0))
        last_rect = self.visualItemRect(self.item(self.count() - 1))
        if position.y() < first_rect.top():
            return 0
        if position.y() > last_rect.bottom():
            return self.count()
        closest_row = min(
            range(self.count()),
            key=lambda row: (
                self.visualItemRect(self.item(row)).center() - position
            ).manhattanLength(),
        )
        closest_rect = self.visualItemRect(self.item(closest_row))
        return closest_row if position.x() < closest_rect.center().x() else closest_row + 1

    def _reordered_ids(self, insertion_index: int) -> list[object]:
        selected_rows = sorted(self.row(item) for item in self.selectedItems())
        if not selected_rows:
            return []
        all_ids = [self.item(row).data(PAGE_ID_ROLE) for row in range(self.count())]
        selected_set = set(selected_rows)
        moving_ids = [all_ids[row] for row in selected_rows]
        remaining_ids = [page_id for row, page_id in enumerate(all_ids) if row not in selected_set]
        removed_before = sum(row < insertion_index for row in selected_rows)
        adjusted_index = max(0, min(insertion_index - removed_before, len(remaining_ids)))
        return remaining_ids[:adjusted_index] + moving_ids + remaining_ids[adjusted_index:]

    def _current_ids(self) -> list[object]:
        return [self.item(row).data(PAGE_ID_ROLE) for row in range(self.count())]

    def _adjusted_insertion_index(self, insertion_index: int) -> int:
        selected_rows = [self.row(item) for item in self.selectedItems()]
        removed_before = sum(row < insertion_index for row in selected_rows)
        return max(
            0,
            min(insertion_index - removed_before, self.count() - len(selected_rows)),
        )

    def _clear_drop_indicator(self) -> None:
        self._drop_position = None
        self.viewport().update()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if self._drop_position is None or self.count() == 0:
            return
        insertion_index = self._drop_position
        if self._reordered_ids(insertion_index) == self._current_ids():
            return
        if insertion_index < self.count():
            rect = self.visualItemRect(self.item(insertion_index))
            x = rect.left() - 4
        else:
            rect = self.visualItemRect(self.item(self.count() - 1))
            x = rect.right() + 4
        top = rect.top() + 10
        bottom = rect.bottom() - 10
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#14B8A6"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPoint(x, top), QPoint(x, bottom))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#14B8A6"))
        painter.drawEllipse(QPoint(x, top), 5, 5)
        painter.drawEllipse(QPoint(x, bottom), 5, 5)
        label_rect = QRect(x - 30, max(2, top - 28), 60, 22)
        painter.drawRoundedRect(label_rect, 6, 6)
        painter.setPen(QColor("#172B4D"))
        painter.drawText(
            label_rect,
            Qt.AlignmentFlag.AlignCenter,
            f"Pos. {self._adjusted_insertion_index(insertion_index) + 1}",
        )

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_pressed.emit()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.clearSelection()
            event.accept()
            return
        super().keyPressEvent(event)


class PdfDropZone(QFrame):
    """Dedicated Home drop target for local PDF files."""

    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("centralDropZone")
        self.setAcceptDrops(True)
        self.setProperty("dragActive", False)
        self.setAccessibleName("Zone de dépôt des fichiers PDF")

    @staticmethod
    def _pdf_paths(event: QDragEnterEvent | QDropEvent) -> list[str]:
        urls = event.mimeData().urls()
        if not urls or not all(
            url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf") for url in urls
        ):
            return []
        return [url.toLocalFile() for url in urls]

    def _set_drag_active(self, active: bool) -> None:
        self.setProperty("dragActive", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._pdf_paths(event):
            self._set_drag_active(True)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_drag_active(False)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = self._pdf_paths(event)
        self._set_drag_active(False)
        if not paths:
            event.ignore()
            return
        self.files_dropped.emit(paths)
        event.acceptProposedAction()


class WorkspacePage(QWidget):
    delete_requested = Signal(list)
    restore_requested = Signal(list)
    remove_document_requested = Signal(str)
    clear_workspace_requested = Signal()
    split_requested = Signal(str, int, str)
    duplicate_requested = Signal(list)
    rotate_requested = Signal(list, int)
    reorder_requested = Signal(list)
    blank_page_requested = Signal(int, float, float)
    export_requested = Signal()
    add_requested = Signal()
    files_dropped = Signal(list)
    home_requested = Signal()
    undo_requested = Signal()
    redo_requested = Signal()
    theme_requested = Signal()
    language_requested = Signal(str)
    mode_requested = Signal(str)

    def __init__(self, renderer: PdfRenderer) -> None:
        super().__init__()
        self.renderer = renderer
        self.language = DEFAULT_LANGUAGE
        self._translated_once = False
        self.current_mode = WorkspaceMode.ORGANIZE
        self._theme = Theme.DARK
        self._document_count = 0
        self._thread_pool = QThreadPool(self)
        # PDFium is process-global and not thread-safe. A single preview worker
        # keeps the UI responsive without running native PDFium calls in parallel.
        self._thread_pool.setMaxThreadCount(1)
        self._thumbnail_cache: OrderedDict[ThumbnailKey, QPixmap] = OrderedDict()
        self._blank_thumbnails: dict[tuple[tuple[float, float], int], QPixmap] = {}
        self._thumbnail_tasks: dict[ThumbnailKey, ThumbnailTask] = {}
        self._items_by_thumbnail: dict[ThumbnailKey, list[QListWidgetItem]] = {}
        self._page_total = 0
        self._active_page_count = 0
        self._moved_page_count = 0
        self._modified_page_count = 0
        self._deleted_page_count = 0
        self._split_output_count = 0
        self._split_plan_valid = False
        self._split_groups: list[list[int]] | None = None
        self._project: PdfProject | None = None
        self._home_active = True
        self._message_token = 0
        self._base_status = "0 page au total     0 document     Traitement local"
        self.setObjectName("appRoot")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._create_topbar())
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("contentStack")
        self.home_view = self._create_home_view()
        self.editor_view = QWidget()
        self.editor_view.setObjectName("editorView")
        editor_layout = QVBoxLayout(self.editor_view)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        self.splitter = QSplitter()
        self.splitter.setObjectName("workspaceSplitter")
        self.splitter.setChildrenCollapsible(False)
        self.documents_panel = self._create_workspace_documents_panel()
        self.pages_panel = self._create_pages_panel()
        self.context_panel = self._create_options_panel()
        self.splitter.addWidget(self.documents_panel)
        self.splitter.addWidget(self.pages_panel)
        self.splitter.addWidget(self.context_panel)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([230, 720, 300])
        editor_layout.addWidget(self.splitter)
        self.content_stack.addWidget(self.home_view)
        self.content_stack.addWidget(self.editor_view)
        root.addWidget(self.content_stack, 1)
        self.statusbar = self._create_statusbar()
        root.addWidget(self.statusbar)
        self.set_mode(self.current_mode)
        self._update_selection()
        self.show_home()

    def _button(
        self,
        text: str,
        slot: Callable[[], None],
        object_name: str = "",
        tooltip: str = "",
    ) -> QPushButton:
        button = QPushButton(text)
        if object_name:
            button.setObjectName(object_name)
        if tooltip:
            button.setToolTip(tooltip)
        button.clicked.connect(slot)
        return button

    def _create_topbar(self) -> QFrame:
        topbar = QFrame()
        topbar.setObjectName("topbar")
        layout = QVBoxLayout(topbar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        command_bar = QFrame()
        command_bar.setObjectName("workspaceCommandBar")
        command_layout = QHBoxLayout(command_bar)
        command_layout.setContentsMargins(14, 8, 14, 7)
        command_layout.setSpacing(7)

        brand = QWidget()
        brand.setObjectName("brandWidget")
        brand.setFixedWidth(148)
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(8)
        self.workspace_brand_icon = QLabel()
        self.workspace_brand_icon.setFixedSize(25, 31)
        self.workspace_brand_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_layout.addWidget(self.workspace_brand_icon)
        self.workspace_brand_label = QLabel()
        self.workspace_brand_label.setObjectName("brand")
        self.workspace_brand_label.setTextFormat(Qt.TextFormat.RichText)
        brand_layout.addWidget(self.workspace_brand_label, 1)
        command_layout.addWidget(brand)

        self.home_button = self._button(
            "⌂  Accueil",
            self.home_requested.emit,
            "homeButton",
            "Fermer les fichiers ouverts et revenir à l’accueil",
        )
        self.home_button.setAccessibleName("Accueil")
        command_layout.addWidget(self.home_button)

        self.undo_button = self._button(
            "Annuler",
            self.undo_requested.emit,
            "topCommandButton",
            "Annuler (Ctrl+Z)",
        )
        self.redo_button = self._button(
            "Rétablir",
            self.redo_requested.emit,
            "topCommandButton",
            "Rétablir (Ctrl+Maj+Z)",
        )
        command_layout.addWidget(self.undo_button)
        command_layout.addWidget(self.redo_button)
        command_layout.addStretch()
        self.add_files_button = self._button(
            "＋  Ajouter des PDF",
            self.add_requested.emit,
            "topCommandButton",
            "Ajouter des documents PDF (Ctrl+O)",
        )
        command_layout.addWidget(self.add_files_button)
        self.export_button = self._button(
            "Exporter",
            self.export_requested.emit,
            "primaryButton",
            "Exporter le PDF (Ctrl+S)",
        )
        command_layout.addWidget(self.export_button)
        self.theme_button = self._button(
            "◐",
            self.theme_requested.emit,
            "iconButton",
            "Changer de thème",
        )
        self.theme_button.setAccessibleName("Changer de thème")
        command_layout.addWidget(self.theme_button)
        self.language_combo = QComboBox()
        self.language_combo.setObjectName("languageCombo")
        self.language_combo.setAccessibleName("Langue de l’interface")
        self.language_combo.setToolTip("Changer la langue de l’interface")
        self.language_combo.setMinimumContentsLength(8)
        self.language_combo.setMaximumWidth(126)
        for language_code, metadata in LANGUAGES.items():
            self.language_combo.addItem(str(metadata["name"]), language_code)
        current_language_index = self.language_combo.findData(self.language)
        if current_language_index >= 0:
            self.language_combo.setCurrentIndex(current_language_index)
        self.language_combo.currentIndexChanged.connect(self._request_language)
        command_layout.addWidget(self.language_combo)
        layout.addWidget(command_bar)

        mode_bar = QFrame()
        mode_bar.setObjectName("workspaceModeBar")
        mode_layout = QHBoxLayout(mode_bar)
        mode_layout.setContentsMargins(14, 5, 14, 8)
        mode_layout.setSpacing(6)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_buttons: dict[WorkspaceMode, QPushButton] = {}

        # Compatibility actions are kept for integrations that previously used
        # the compact mode menu. The visible navigation is the row of buttons.
        self.mode_button = QToolButton(topbar)
        self.mode_button.setObjectName("workspaceModeButton")
        self.mode_button.hide()
        self.mode_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.mode_button.setAccessibleName("Changer d’outil")
        self.mode_menu = QMenu(self.mode_button)
        self.mode_actions = {}
        for mode, spec in MODE_SPECS.items():
            action = self.mode_menu.addAction(spec.label)
            action.setCheckable(True)
            action.setEnabled(spec.is_selectable)
            action.setToolTip(
                spec.home_description
                if spec.is_selectable
                else f"Disponible prochainement — {spec.home_description}"
            )
            action.triggered.connect(
                lambda _checked=False, selected_mode=mode: self._request_mode(selected_mode)
            )
            self.mode_actions[mode] = action
            button = QPushButton(spec.label)
            button.setObjectName("workspaceModeNavButton")
            button.setCheckable(True)
            button.setProperty("status", spec.status.value)
            button.setIcon(self._mode_icon(spec))
            button.setIconSize(QSize(17, 17))
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            button.setAccessibleName(f"Outil {spec.label}")
            if spec.is_selectable:
                button.setToolTip(spec.home_description)
                button.clicked.connect(
                    lambda _checked=False, selected_mode=mode: self._request_mode(selected_mode)
                )
            else:
                button.setEnabled(False)
                button.setToolTip(f"Disponible prochainement — {spec.home_description}")
                button.setAccessibleDescription(f"{spec.label} sera disponible prochainement.")
            self.mode_group.addButton(button)
            self.mode_buttons[mode] = button
            mode_layout.addWidget(button, 1)
        self.mode_button.setMenu(self.mode_menu)
        layout.addWidget(mode_bar)
        self._update_workspace_brand()
        return topbar

    def _create_home_view(self) -> QWidget:
        home = QWidget()
        home.setObjectName("homeView")
        layout = QVBoxLayout(home)
        layout.setContentsMargins(48, 42, 48, 42)
        layout.addStretch()

        self.home_drop_zone = PdfDropZone()
        self.home_drop_zone.setMinimumHeight(330)
        self.home_drop_zone.setMinimumWidth(620)
        self.home_drop_zone.setMaximumWidth(760)
        drop_layout = QVBoxLayout(self.home_drop_zone)
        drop_layout.setContentsMargins(42, 38, 42, 38)
        drop_layout.setSpacing(12)
        drop_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("▱")
        icon.setObjectName("homeDropIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(icon)

        self.home_title = QLabel("Bienvenue dans PixoPDF")
        self.home_title.setObjectName("homeTitle")
        self.home_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(self.home_title)

        self.home_description = QLabel(
            "Déposez vos fichiers PDF ici pour commencer à les organiser, fusionner ou diviser."
        )
        self.home_description.setObjectName("homeDescription")
        self.home_description.setWordWrap(True)
        self.home_description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(self.home_description)

        self.home_open_button = self._button(
            "＋  Ouvrir des fichiers PDF",
            self.add_requested.emit,
            "primaryButton",
            "Choisir un ou plusieurs fichiers PDF",
        )
        self.home_open_button.setAccessibleName("Ouvrir des fichiers PDF")
        drop_layout.addWidget(self.home_open_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.home_drop_prompt = QLabel("ou glissez-déposez vos PDF dans cette zone")
        self.home_drop_prompt.setObjectName("dropPrompt")
        self.home_drop_prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(self.home_drop_prompt)

        self.home_privacy = QLabel("Traitement 100 % local • aucun fichier envoyé en ligne")
        self.home_privacy.setObjectName("dropPrivacy")
        self.home_privacy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(self.home_privacy)

        self.home_drop_zone.files_dropped.connect(self.files_dropped.emit)
        layout.addWidget(
            self.home_drop_zone,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )
        layout.addStretch()
        return home

    def _create_workspace_documents_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("documentsPanel")
        panel.setMinimumWidth(220)
        panel.setMaximumWidth(300)
        panel.setAccessibleName("Fichiers ouverts")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(10)

        self.documents_panel_title = QLabel("Fichiers ouverts")
        self.documents_panel_title.setObjectName("sectionTitle")
        layout.addWidget(self.documents_panel_title)
        self.documents_panel_description = QLabel(
            "Les fichiers sources restent toujours inchangés."
        )
        self.documents_panel_description.setObjectName("optionsDescription")
        self.documents_panel_description.setWordWrap(True)
        layout.addWidget(self.documents_panel_description)

        (
            self.workspace_documents_card,
            self.workspace_documents,
            self.workspace_documents_heading,
            self.workspace_remove_document_button,
            self.workspace_add_documents_button,
        ) = self._create_documents_card(
            "Liste des fichiers ouverts",
            "Ajouter un ou plusieurs fichiers PDF au workspace",
        )
        self.workspace_remove_document_button.setText("Fermer ce PDF")
        layout.addWidget(self.workspace_documents_card, 1)

        self.close_all_documents_button = self._button(
            "⌂  Fermer tous les fichiers",
            self.home_requested.emit,
            "dangerButton",
            "Fermer tous les fichiers et créer un workspace vide",
        )
        self.close_all_documents_button.setAccessibleName(
            "Fermer tous les fichiers et revenir à l’accueil"
        )
        layout.addWidget(self.close_all_documents_button)

        self.documents = self.workspace_documents
        self.documents_heading = self.workspace_documents_heading
        self.organize_documents_card = self.workspace_documents_card
        self.organize_documents = self.workspace_documents
        self.organize_documents_heading = self.workspace_documents_heading
        self.organize_remove_document_button = self.workspace_remove_document_button
        self.organize_add_documents_button = self.workspace_add_documents_button
        self.merge_documents_card = self.workspace_documents_card
        self.merge_documents = self.workspace_documents
        self.merge_documents_heading = self.workspace_documents_heading
        self.merge_remove_document_button = self.workspace_remove_document_button
        self.split_documents_card = self.workspace_documents_card
        self.split_documents = self.workspace_documents
        self.split_documents_heading = self.workspace_documents_heading
        self.split_remove_document_button = self.workspace_remove_document_button
        self.split_add_documents_button = self.workspace_add_documents_button
        self.split_clear_workspace_button = self.close_all_documents_button
        return panel

    def _create_empty_state(self) -> QWidget:
        empty = QWidget()
        layout = QVBoxLayout(empty)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QLabel("▱")
        icon.setObjectName("emptyIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)
        self.empty_title = QLabel("Aucune page")
        self.empty_title.setObjectName("emptyTitle")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_title)
        self.empty_detail = QLabel(
            "Ajoutez un PDF ou créez une page blanche.\n"
            "Les vignettes apparaîtront ici, sans modifier vos fichiers originaux."
        )
        self.empty_detail.setObjectName("muted")
        self.empty_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_detail)
        self.empty_add_button = self._button(
            "⊞  Choisir des fichiers PDF", self.add_requested.emit
        )
        self.empty_add_button.setObjectName("primaryButton")
        layout.addWidget(self.empty_add_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self.empty_blank_button = self._button(
            "＋  Créer une page blanche A4",
            self.request_default_blank_page,
            tooltip="Commencer avec une page blanche A4",
        )
        layout.addWidget(self.empty_blank_button, alignment=Qt.AlignmentFlag.AlignCenter)
        return empty

    def _create_pages_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("pagesPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 8)
        layout.setSpacing(10)
        heading_row = QHBoxLayout()
        heading_box = QVBoxLayout()
        self.pages_heading = QLabel("Toutes les pages")
        self.pages_heading.setObjectName("sectionTitle")
        heading_box.addWidget(self.pages_heading)
        self.pages_count = QLabel("0 page")
        self.pages_count.setObjectName("muted")
        heading_box.addWidget(self.pages_count)
        heading_row.addLayout(heading_box)
        heading_row.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("⌕  Rechercher une page")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(270)
        self.search.textChanged.connect(self._filter_pages)
        heading_row.addWidget(self.search)
        layout.addLayout(heading_row)
        self.page_stack = QStackedWidget()
        self.empty_state = self._create_empty_state()
        self.pages = PageListWidget()
        self.pages.setAccessibleName("Pages du projet")
        self.page_delegate = PageItemDelegate(self.pages)
        self.pages.setItemDelegate(self.page_delegate)
        self.pages.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.pages.setViewMode(QListWidget.ViewMode.IconMode)
        self.pages.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.pages.setMovement(QListWidget.Movement.Static)
        self.pages.setIconSize(QSize(126, 164))
        self.pages.setGridSize(QSize(150, 205))
        self.pages.setSpacing(8)
        self.pages.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.pages.setDragEnabled(True)
        self.pages.viewport().setAcceptDrops(True)
        self.pages.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.pages.setDropIndicatorShown(False)
        self.pages.itemSelectionChanged.connect(self._update_selection)
        self.pages.reordered.connect(self.reorder_requested)
        self.pages.delete_pressed.connect(self._request_delete)
        self.page_stack.addWidget(self.empty_state)
        self.page_stack.addWidget(self.pages)
        layout.addWidget(self.page_stack, 1)
        selection_bar = QFrame()
        selection_bar.setObjectName("statusbar")
        selection_layout = QHBoxLayout(selection_bar)
        self.selection_label = QLabel("Aucune page sélectionnée")
        selection_layout.addWidget(self.selection_label)
        selection_layout.addSpacing(8)
        self.moved_pages_legend = QLabel()
        self.moved_pages_legend.setObjectName("changeLegend")
        self.moved_pages_legend.setProperty("changeKind", "moved")
        selection_layout.addWidget(self.moved_pages_legend)
        self.modified_pages_legend = QLabel()
        self.modified_pages_legend.setObjectName("changeLegend")
        self.modified_pages_legend.setProperty("changeKind", "modified")
        selection_layout.addWidget(self.modified_pages_legend)
        self.deleted_pages_legend = QLabel()
        self.deleted_pages_legend.setObjectName("changeLegend")
        self.deleted_pages_legend.setProperty("changeKind", "deleted")
        selection_layout.addWidget(self.deleted_pages_legend)
        self.split_preview_legend = QLabel("Aperçu : une couleur et un badge par PDF généré")
        self.split_preview_legend.setObjectName("splitPreviewLegend")
        self.split_preview_legend.hide()
        selection_layout.addWidget(self.split_preview_legend)
        selection_layout.addStretch()
        self.select_all_button = self._button(
            "Tout sélectionner",
            self.pages.selectAll,
            tooltip="Sélectionner toutes les pages (Ctrl+A)",
        )
        selection_layout.addWidget(self.select_all_button)
        layout.addWidget(selection_bar)
        return panel

    def _create_options_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contextPanel")
        panel.setAccessibleName("Options de l’outil actif")
        panel.setMinimumWidth(280)
        panel.setMaximumWidth(360)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(10)

        heading_row = QHBoxLayout()
        self.options_icon = QLabel()
        self.options_icon.setObjectName("optionsIcon")
        self.options_icon.setFixedSize(20, 20)
        heading_row.addWidget(self.options_icon)
        self.options_heading = QLabel("Organiser")
        self.options_heading.setObjectName("sectionTitle")
        heading_row.addWidget(self.options_heading)
        heading_row.addStretch()
        self.options_status = QLabel("Disponible")
        self.options_status.setObjectName("modeStatusBadge")
        heading_row.addWidget(self.options_status)
        layout.addLayout(heading_row)

        self.options_description = QLabel()
        self.options_description.setObjectName("optionsDescription")
        self.options_description.setWordWrap(True)
        layout.addWidget(self.options_description)

        self.options_stack = QStackedWidget()
        self.options_stack.setObjectName("optionsStack")
        self.option_panels: dict[WorkspaceMode, QWidget] = {}
        self.mode_specific_actions: dict[WorkspaceMode, list[QPushButton]] = {}
        for mode, spec in MODE_SPECS.items():
            if mode is WorkspaceMode.ORGANIZE:
                page = self._create_organize_options()
            elif mode is WorkspaceMode.MERGE:
                page = self._create_merge_options()
            elif mode is WorkspaceMode.SPLIT:
                page = self._create_split_options()
            elif mode is WorkspaceMode.LAYOUT:
                page = self._create_layout_options()
            else:
                page = self._create_planned_options(spec)
            self.option_panels[mode] = page
            self.options_stack.addWidget(page)
        layout.addWidget(self.options_stack, 1)
        return panel

    def _options_scroll(self, body: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("optionsScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        return scroll

    def _options_body(self) -> tuple[QWidget, QVBoxLayout]:
        body = QWidget()
        body.setObjectName("optionsBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 2, 2, 2)
        body_layout.setSpacing(8)
        return body, body_layout

    def _organize_card(
        self,
        title: str,
        description: str = "",
    ) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("organizeGroupCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(11, 10, 11, 10)
        card_layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("organizeGroupTitle")
        card_layout.addWidget(title_label)
        if description:
            description_label = QLabel(description)
            description_label.setObjectName("organizeGroupDescription")
            description_label.setWordWrap(True)
            card_layout.addWidget(description_label)
        return card, card_layout

    def _split_strategy_card(
        self,
        radio: QRadioButton,
        description: str,
    ) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("splitStrategyCard")
        card.setProperty("selected", False)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(11, 10, 11, 10)
        layout.setSpacing(7)
        layout.addWidget(radio)
        description_label = QLabel(description)
        description_label.setObjectName("splitStrategyDescription")
        description_label.setWordWrap(True)
        layout.addWidget(description_label)
        return card, layout

    def _create_documents_card(
        self,
        accessible_name: str,
        add_tooltip: str,
    ) -> tuple[QFrame, QListWidget, QLabel, QPushButton, QPushButton]:
        card = QFrame()
        card.setObjectName("documentsCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 9, 10, 10)
        card_layout.setSpacing(7)

        heading = QLabel("Documents (0)")
        heading.setObjectName("organizeGroupTitle")
        card_layout.addWidget(heading)

        documents = QListWidget()
        documents.setObjectName("documentsList")
        documents.setAccessibleName(accessible_name)
        documents.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        documents.setMinimumHeight(68)
        documents.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        documents.hide()
        card_layout.addWidget(documents)

        remove_button = self._button(
            "Retirer ce PDF",
            lambda: self._request_remove_document(documents),
            "dangerButton",
            "Retirer le document sélectionné du workspace sans supprimer le fichier original",
        )
        remove_button.setAccessibleName("Retirer le PDF sélectionné du workspace")
        remove_button.setAccessibleDescription(
            "Retire toutes ses pages du projet. Le fichier original reste intact et "
            "l’action peut être annulée."
        )
        remove_button.setEnabled(False)
        documents.itemSelectionChanged.connect(
            lambda: remove_button.setEnabled(documents.currentItem() is not None)
        )
        card_layout.addWidget(remove_button)

        add_button = self._button(
            "＋  Ajouter des PDF",
            self.add_requested.emit,
            "organizeActionButton",
            tooltip=add_tooltip,
        )
        card_layout.addWidget(add_button)
        return card, documents, heading, remove_button, add_button

    def _create_organize_options(self) -> QWidget:
        page = QWidget()
        page.setObjectName("organizeOptions")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(8)

        self.organize_selection_card = QFrame()
        self.organize_selection_card.setObjectName("organizeSelectionCard")
        self.organize_selection_card.setProperty("selectionState", "empty")
        selection_layout = QHBoxLayout(self.organize_selection_card)
        selection_layout.setContentsMargins(11, 10, 8, 10)
        selection_layout.setSpacing(8)
        selection_copy = QVBoxLayout()
        selection_copy.setSpacing(3)
        self.options_selection_label = QLabel("Aucune page sélectionnée")
        self.options_selection_label.setObjectName("organizeSelectionTitle")
        selection_copy.addWidget(self.options_selection_label)
        self.options_selection_detail = QLabel(
            "Sélectionnez une ou plusieurs miniatures pour activer les actions."
        )
        self.options_selection_detail.setObjectName("organizeSelectionDetail")
        self.options_selection_detail.setWordWrap(True)
        self.options_selection_change = QLabel()
        self.options_selection_change.setObjectName("organizeChangeChip")
        self.options_selection_change.hide()
        selection_meta_row = QHBoxLayout()
        selection_meta_row.setSpacing(6)
        selection_meta_row.addWidget(self.options_selection_detail, 1)
        selection_meta_row.addWidget(
            self.options_selection_change,
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )
        selection_copy.addLayout(selection_meta_row)
        selection_layout.addLayout(selection_copy, 1)
        self.clear_selection_button = self._button(
            "×",
            self.pages.clearSelection,
            "clearSelectionButton",
            "Effacer la sélection (Échap)",
        )
        self.clear_selection_button.setAccessibleName("Effacer la sélection")
        self.clear_selection_button.setAccessibleDescription(
            "Désélectionne toutes les pages sans modifier le document."
        )
        self.clear_selection_button.setFixedSize(28, 28)
        selection_layout.addWidget(
            self.clear_selection_button,
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        page_layout.addWidget(self.organize_selection_card)

        self.organize_search_banner = QFrame()
        self.organize_search_banner.setObjectName("organizeSearchBanner")
        search_banner_layout = QVBoxLayout(self.organize_search_banner)
        search_banner_layout.setContentsMargins(10, 9, 10, 9)
        search_banner_layout.setSpacing(4)
        self.organize_search_title = QLabel("Réorganisation suspendue")
        self.organize_search_title.setObjectName("organizeSearchTitle")
        search_banner_layout.addWidget(self.organize_search_title)
        self.organize_search_detail = QLabel(
            "Effacez la recherche pour déplacer de nouveau les pages."
        )
        self.organize_search_detail.setObjectName("organizeSearchDetail")
        self.organize_search_detail.setWordWrap(True)
        search_banner_layout.addWidget(self.organize_search_detail)
        self.clear_search_button = self._button(
            "Effacer la recherche",
            self.search.clear,
            "searchClearButton",
            "Afficher de nouveau toutes les pages",
        )
        self.clear_search_button.setAccessibleName("Effacer la recherche de pages")
        search_banner_layout.addWidget(
            self.clear_search_button,
            0,
            Qt.AlignmentFlag.AlignLeft,
        )
        self.organize_search_banner.hide()
        page_layout.addWidget(self.organize_search_banner)

        body, body_layout = self._options_body()

        self.move_group, move_layout = self._organize_card("Déplacer")
        self.move_group_title = self.move_group.findChild(QLabel, "organizeGroupTitle")
        self.move_position_label = QLabel("Sélectionnez des pages à déplacer.")
        self.move_position_label.setObjectName("organizeActionStatus")
        move_layout.addWidget(self.move_position_label)
        move_grid = QGridLayout()
        move_grid.setHorizontalSpacing(6)
        move_grid.setVerticalSpacing(6)
        self.move_previous_button = self._button(
            "←  Reculer",
            lambda: self._request_move("previous"),
            "moveActionButton",
            "Reculer la sélection d’une position",
        )
        self.move_next_button = self._button(
            "Avancer  →",
            lambda: self._request_move("next"),
            "moveActionButton",
            "Avancer la sélection d’une position",
        )
        self.move_start_button = self._button(
            "Au début",
            lambda: self._request_move("start"),
            "moveActionButton",
            "Placer la sélection au début",
        )
        self.move_end_button = self._button(
            "À la fin",
            lambda: self._request_move("end"),
            "moveActionButton",
            "Placer la sélection à la fin",
        )
        move_grid.addWidget(self.move_previous_button, 0, 0)
        move_grid.addWidget(self.move_next_button, 0, 1)
        move_grid.addWidget(self.move_start_button, 1, 0)
        move_grid.addWidget(self.move_end_button, 1, 1)
        move_layout.addLayout(move_grid)
        self.move_hint = QLabel("Indices fixes · glisser-déposer actif")
        self.move_hint.setObjectName("organizeHint")
        self.move_hint.setWordWrap(True)
        self.move_hint.hide()
        move_layout.addWidget(self.move_hint)
        body_layout.addWidget(self.move_group)

        self.modify_group, modify_layout = self._organize_card("Modifier")
        self.modify_group_title = self.modify_group.findChild(QLabel, "organizeGroupTitle")
        rotation_row = QHBoxLayout()
        rotation_row.setSpacing(6)
        self.rotate_left_button = self._button(
            "90° gauche",
            lambda: self.rotate_requested.emit(self.selected_indices(), -90),
            "organizeActionButton",
            "Tourner à gauche (Ctrl+L)",
        )
        self.rotate_right_button = self._button(
            "90° droite",
            lambda: self.rotate_requested.emit(self.selected_indices(), 90),
            "organizeActionButton",
            "Tourner à droite (Ctrl+R)",
        )
        rotation_row.addWidget(self.rotate_left_button)
        rotation_row.addWidget(self.rotate_right_button)
        modify_layout.addLayout(rotation_row)
        self.duplicate_button = self._button(
            "Dupliquer la page",
            self._request_duplicate,
            "organizeActionButton",
            tooltip="Dupliquer (Ctrl+D)",
        )
        modify_layout.addWidget(self.duplicate_button)
        body_layout.addWidget(self.modify_group)

        self.insert_group, insert_layout = self._organize_card("Insérer une page")
        self.insert_group_title = self.insert_group.findChild(QLabel, "organizeGroupTitle")
        self.blank_page_button = QToolButton()
        self.blank_page_button.setObjectName("organizeInsertButton")
        self.blank_page_button.setText("＋  Page blanche")
        self.blank_page_button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.blank_page_button.setToolTip(
            "Ajouter une page A4 portrait après la sélection, ou à la fin du projet"
        )
        self.blank_page_button.setAccessibleName("Ajouter une page blanche")
        self.blank_page_button.setAccessibleDescription(
            "Le bouton ajoute une page A4 portrait. Le menu permet de choisir sa position "
            "et son format."
        )
        self.blank_page_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.blank_page_button.clicked.connect(self.request_default_blank_page)
        blank_menu = QMenu(self.blank_page_button)
        position_menu = blank_menu.addMenu("Choisir la position")
        self.blank_after_action = position_menu.addAction("Après la sélection · A4 portrait")
        self.blank_before_action = position_menu.addAction("Avant la sélection · A4 portrait")
        self.blank_at_end_action = position_menu.addAction("À la fin du document · A4 portrait")
        format_menu = blank_menu.addMenu("Choisir un autre format")
        self.blank_landscape_action = format_menu.addAction("A4 paysage · après la sélection")
        self.blank_a5_action = format_menu.addAction("A5 portrait · après la sélection")
        self.blank_after_action.triggered.connect(lambda: self._request_blank("after", A4_PORTRAIT))
        self.blank_before_action.triggered.connect(
            lambda: self._request_blank("before", A4_PORTRAIT)
        )
        self.blank_at_end_action.triggered.connect(lambda: self._request_blank("end", A4_PORTRAIT))
        self.blank_landscape_action.triggered.connect(
            lambda: self._request_blank("after", A4_LANDSCAPE)
        )
        self.blank_a5_action.triggered.connect(lambda: self._request_blank("after", A5_PORTRAIT))
        self.blank_page_button.setMenu(blank_menu)
        insert_layout.addWidget(self.blank_page_button)
        self.blank_target_label = QLabel("A4 portrait · à la fin du document")
        self.blank_target_label.setObjectName("organizeActionStatus")
        self.blank_target_label.setWordWrap(True)
        insert_layout.addWidget(self.blank_target_label)
        body_layout.addWidget(self.insert_group)
        body_layout.addStretch()

        page_layout.addWidget(self._options_scroll(body), 1)

        self.organize_danger_zone = QFrame()
        self.organize_danger_zone.setObjectName("organizeDangerZone")
        danger_layout = QVBoxLayout(self.organize_danger_zone)
        danger_layout.setContentsMargins(0, 9, 0, 0)
        self.delete_button = self._button(
            "Supprimer la page",
            self._request_delete,
            "dangerButton",
            "Retirer les pages sélectionnées (Suppr)",
        )
        self.delete_button.setAccessibleName("Supprimer les pages sélectionnées")
        self.delete_button.setAccessibleDescription(
            "Retire les pages du projet. Cette action peut être annulée."
        )
        danger_layout.addWidget(self.delete_button)
        page_layout.addWidget(self.organize_danger_zone)

        self._move_buttons = {
            "start": self.move_start_button,
            "previous": self.move_previous_button,
            "next": self.move_next_button,
            "end": self.move_end_button,
        }
        self._selection_actions = [
            self.delete_button,
            self.duplicate_button,
            self.rotate_left_button,
            self.rotate_right_button,
        ]
        QWidget.setTabOrder(self.clear_selection_button, self.move_previous_button)
        QWidget.setTabOrder(self.move_previous_button, self.move_next_button)
        QWidget.setTabOrder(self.move_next_button, self.move_start_button)
        QWidget.setTabOrder(self.move_start_button, self.move_end_button)
        QWidget.setTabOrder(self.move_end_button, self.rotate_left_button)
        QWidget.setTabOrder(self.rotate_left_button, self.rotate_right_button)
        QWidget.setTabOrder(self.rotate_right_button, self.duplicate_button)
        QWidget.setTabOrder(self.duplicate_button, self.blank_page_button)
        QWidget.setTabOrder(self.blank_page_button, self.delete_button)
        return page

    def _create_merge_options(self) -> QWidget:
        page = QWidget()
        page.setObjectName("mergeOptions")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        body, body_layout = self._options_body()

        self.merge_summary_label = QLabel("Ajoutez au moins deux documents PDF.")
        self.merge_summary_label.setObjectName("selectionSummary")
        self.merge_summary_label.setWordWrap(True)
        body_layout.addWidget(self.merge_summary_label)

        merge_add = self.workspace_add_documents_button

        self.merge_order_heading = self._option_heading("ORDRE ET SORTIE")
        body_layout.addWidget(self.merge_order_heading)
        self.merge_order_hint = QLabel(
            "L’ordre visible des miniatures sera l’ordre du PDF final. "
            "Faites glisser les pages pour l’ajuster."
        )
        self.merge_order_hint.setObjectName("contextHint")
        self.merge_order_hint.setWordWrap(True)
        body_layout.addWidget(self.merge_order_hint)

        self.merge_output_hint = QLabel(
            "Quand deux documents sont prêts, utilisez « Fusionner et exporter » "
            "dans la barre supérieure. Les sources ne sont jamais remplacées."
        )
        self.merge_output_hint.setObjectName("muted")
        self.merge_output_hint.setWordWrap(True)
        body_layout.addWidget(self.merge_output_hint)
        body_layout.addStretch()
        self.merge_export_button = self.export_button
        self.mode_specific_actions[WorkspaceMode.MERGE] = [
            merge_add,
            self.merge_export_button,
        ]
        page_layout.addWidget(self._options_scroll(body), 1)
        return page

    def _create_split_options(self) -> QWidget:
        page = QWidget()
        page.setObjectName("splitOptions")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        body, body_layout = self._options_body()

        self.split_summary_label = QLabel("Ajoutez un PDF pour préparer la division.")
        self.split_summary_label.setObjectName("selectionSummary")
        self.split_summary_label.setWordWrap(True)
        body_layout.addWidget(self.split_summary_label)

        self.split_method_heading = QLabel("Choisissez comment créer les nouveaux PDF")
        self.split_method_heading.setObjectName("optionHeading")
        body_layout.addWidget(self.split_method_heading)

        self.split_strategy_group = QButtonGroup(page)
        self.split_each_radio = QRadioButton("Un PDF par page")
        self.split_batch_radio = QRadioButton("Par lots de pages")
        self.split_ranges_radio = QRadioButton("Plages personnalisées")
        for radio in (
            self.split_each_radio,
            self.split_batch_radio,
            self.split_ranges_radio,
        ):
            self.split_strategy_group.addButton(radio)
            radio.toggled.connect(self._update_split_controls)

        self.split_each_card, _each_layout = self._split_strategy_card(
            self.split_each_radio,
            "Chaque page active devient un fichier PDF distinct.",
        )
        body_layout.addWidget(self.split_each_card)

        self.split_batch_card, batch_layout = self._split_strategy_card(
            self.split_batch_radio,
            "Créez des groupes consécutifs contenant le même nombre de pages.",
        )
        batch_row = QHBoxLayout()
        batch_row.setContentsMargins(23, 0, 0, 0)
        self.split_batch_label = QLabel("Pages par fichier")
        self.split_batch_label.setObjectName("organizeActionStatus")
        batch_row.addWidget(self.split_batch_label)
        batch_row.addStretch()
        self.split_batch_size = QSpinBox()
        self.split_batch_size.setRange(1, 9999)
        self.split_batch_size.setValue(5)
        self.split_batch_size.setAccessibleName("Nombre de pages par fichier")
        self.split_batch_size.valueChanged.connect(self._update_split_controls)
        batch_row.addWidget(self.split_batch_size)
        batch_layout.addLayout(batch_row)
        body_layout.addWidget(self.split_batch_card)

        self.split_ranges_card, ranges_layout = self._split_strategy_card(
            self.split_ranges_radio,
            "Composez chaque PDF manuellement. Séparez les fichiers avec « ; ».",
        )
        self.split_ranges_input = QLineEdit()
        self.split_ranges_input.setPlaceholderText("Ex. 1-3; 4-6; 7")
        self.split_ranges_input.setAccessibleName("Plages de pages à diviser")
        self.split_ranges_input.setToolTip(
            "Séparez les fichiers par « ; » et les pages d’un fichier par « , »"
        )
        self.split_ranges_input.textChanged.connect(self._update_split_controls)
        ranges_layout.addWidget(self.split_ranges_input)
        body_layout.addWidget(self.split_ranges_card)

        self.split_validation_label = QLabel()
        self.split_validation_label.setObjectName("splitPlanSummary")
        self.split_validation_label.setWordWrap(True)
        body_layout.addWidget(self.split_validation_label)

        self.split_hint = QLabel(
            "Pages supprimées ignorées • lancez la division avec le bouton principal en haut."
        )
        self.split_hint.setObjectName("organizeHint")
        self.split_hint.setWordWrap(True)
        body_layout.addWidget(self.split_hint)
        body_layout.addStretch()
        self.mode_specific_actions[WorkspaceMode.SPLIT] = [
            self.split_clear_workspace_button,
            self.export_button,
        ]
        page_layout.addWidget(self._options_scroll(body), 1)
        self.split_each_radio.setChecked(True)
        self._update_split_controls()
        return page

    def _create_layout_options(self) -> QWidget:
        page = QWidget()
        page.setObjectName("layoutOptions")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        body, body_layout = self._options_body()

        self.layout_summary_label = QLabel("Ajoutez une page blanche à l’emplacement choisi.")
        self.layout_summary_label.setObjectName("selectionSummary")
        self.layout_summary_label.setWordWrap(True)
        body_layout.addWidget(self.layout_summary_label)

        body_layout.addWidget(self._option_heading("PAGE BLANCHE"))
        layout_portrait = self._button(
            "＋  A4 portrait",
            lambda: self._request_blank("after", A4_PORTRAIT),
            "accentFlatButton",
            "Ajouter après la sélection, ou à la fin",
        )
        layout_landscape = self._button(
            "＋  A4 paysage",
            lambda: self._request_blank("after", A4_LANDSCAPE),
            tooltip="Ajouter après la sélection, ou à la fin",
        )
        layout_a5 = self._button(
            "＋  A5 portrait",
            lambda: self._request_blank("after", A5_PORTRAIT),
            tooltip="Ajouter après la sélection, ou à la fin",
        )
        body_layout.addWidget(layout_portrait)
        body_layout.addWidget(layout_landscape)
        body_layout.addWidget(layout_a5)

        body_layout.addWidget(self._option_heading("MISE EN PAGE"))
        planned_buttons: list[QPushButton] = []
        for action_name in MODE_SPECS[WorkspaceMode.LAYOUT].planned_actions:
            button = QPushButton(action_name)
            button.setObjectName("plannedAction")
            button.setEnabled(False)
            button.setToolTip("Disponible prochainement")
            body_layout.addWidget(button)
            planned_buttons.append(button)
        note = QLabel(
            "Les pages blanches sont disponibles dès maintenant. "
            "Les formats avancés arrivent prochainement."
        )
        note.setObjectName("contextHint")
        note.setWordWrap(True)
        body_layout.addWidget(note)
        body_layout.addStretch()
        self.layout_blank_buttons = [layout_portrait, layout_landscape, layout_a5]
        self.mode_specific_actions[WorkspaceMode.LAYOUT] = [
            *self.layout_blank_buttons,
            *planned_buttons,
        ]
        page_layout.addWidget(self._options_scroll(body), 1)
        return page

    def _create_planned_options(self, spec: ModeSpec) -> QWidget:
        page = QWidget()
        page.setObjectName(f"{spec.mode.value}Options")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        body, body_layout = self._options_body()

        state = QLabel(
            f"{spec.label} dispose de son propre espace de réglages. "
            "Le traitement final sera activé dans une prochaine version."
        )
        state.setObjectName("comingSoonCard")
        state.setWordWrap(True)
        body_layout.addWidget(state)

        add_button = self._button(
            "Ajouter un PDF",
            lambda: None,
            "plannedAction",
            f"{spec.label} sera disponible prochainement",
        )
        add_button.setEnabled(False)
        body_layout.addWidget(add_button)
        body_layout.addWidget(self._option_heading("RÉGLAGES PRÉVUS"))
        planned_buttons = []
        for action_name in spec.planned_actions:
            button = QPushButton(action_name)
            button.setObjectName("plannedAction")
            button.setEnabled(False)
            button.setToolTip("Disponible prochainement")
            body_layout.addWidget(button)
            planned_buttons.append(button)
        body_layout.addStretch()
        self.mode_specific_actions[spec.mode] = [add_button, *planned_buttons]
        page_layout.addWidget(self._options_scroll(body), 1)
        return page

    def _option_heading(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("optionHeading")
        return label

    def _selected_split_strategy(self) -> SplitStrategy:
        if self.split_batch_radio.isChecked():
            return SplitStrategy.BATCH
        if self.split_ranges_radio.isChecked():
            return SplitStrategy.RANGES
        return SplitStrategy.EACH_PAGE

    def _update_split_controls(self) -> None:
        strategy = self._selected_split_strategy()
        batch_selected = strategy is SplitStrategy.BATCH
        ranges_selected = strategy is SplitStrategy.RANGES
        self.split_batch_label.setVisible(batch_selected)
        self.split_batch_size.setVisible(batch_selected)
        self.split_ranges_input.setVisible(ranges_selected)
        for card, selected in (
            (self.split_each_card, strategy is SplitStrategy.EACH_PAGE),
            (self.split_batch_card, batch_selected),
            (self.split_ranges_card, ranges_selected),
        ):
            card.setProperty("selected", selected)
            description = card.findChild(QLabel, "splitStrategyDescription")
            if description is not None:
                description.setVisible(selected)
            card.style().unpolish(card)
            card.style().polish(card)

        self._split_output_count = 0
        self._split_plan_valid = False
        self._split_groups = None
        if self._active_page_count < 1:
            self.split_summary_label.setText(self.t("split_add_pdf"))
            self.split_validation_label.setText(self.t("split_no_active_page"))
            self.split_validation_label.setProperty("feedback", "error")
        else:
            self.split_summary_label.setText(
                self.tc("split_active_pages", self._active_page_count)
            )
            try:
                groups = build_split_groups(
                    self._active_page_count,
                    strategy,
                    batch_size=self.split_batch_size.value(),
                    ranges=self.split_ranges_input.text(),
                )
            except ValueError as exc:
                self.split_validation_label.setText(str(exc))
                self.split_validation_label.setProperty("feedback", "error")
            else:
                self._split_output_count = len(groups)
                self._split_plan_valid = True
                self._split_groups = groups
                self.split_validation_label.setText(
                    self.tc("split_preview_ready", len(groups))
                )
                self.split_validation_label.setProperty("feedback", "success")
        self._apply_split_preview(
            self._split_groups if self.current_mode is WorkspaceMode.SPLIT else None
        )
        self._update_primary_action()
        self._update_export_state()
        self.split_validation_label.style().unpolish(self.split_validation_label)
        self.split_validation_label.style().polish(self.split_validation_label)

    def request_split(self) -> None:
        if not self._split_plan_valid:
            return
        self.split_requested.emit(
            self._selected_split_strategy().value,
            self.split_batch_size.value(),
            self.split_ranges_input.text(),
        )

    def _request_mode(self, mode: WorkspaceMode) -> None:
        if not MODE_SPECS[mode].is_selectable:
            return
        self.set_mode(mode)
        self.mode_requested.emit(mode.value)

    def t(self, key: str, **values: object) -> str:
        return translate(self.language, key, **values)

    def tc(self, key: str, count: int, **values: object) -> str:
        form = "one" if count == 1 else "other"
        return self.t(f"{key}_{form}", count=count, **values)

    def _request_language(self, _index: int) -> None:
        language = str(self.language_combo.currentData())
        if language not in LANGUAGES:
            return
        self.set_language(language)
        self.language_requested.emit(language)

    def set_language(self, language: str) -> None:
        selected = language if language in LANGUAGES else DEFAULT_LANGUAGE
        if selected == self.language and self._translated_once:
            return
        language_changed = selected != self.language
        self.language = selected
        if language_changed:
            self._blank_thumbnails.clear()
        direction = (
            Qt.LayoutDirection.RightToLeft
            if is_rtl(selected)
            else Qt.LayoutDirection.LeftToRight
        )
        self.setLayoutDirection(direction)
        # A PDF keeps its logical page order regardless of the interface language.
        self.pages.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.page_delegate.language = selected
        combo_index = self.language_combo.findData(selected)
        if combo_index >= 0 and combo_index != self.language_combo.currentIndex():
            blocked = self.language_combo.blockSignals(True)
            self.language_combo.setCurrentIndex(combo_index)
            self.language_combo.blockSignals(blocked)
        self._translate_ui()
        self._translated_once = True
        if self._project is not None:
            self.refresh(self._project)

    def _translate_ui(self) -> None:
        self.home_button.setText(f"⌂  {self.t('home')}")
        self.home_button.setAccessibleName(self.t("home"))
        self.home_button.setToolTip(self.t("home_tooltip"))
        self.undo_button.setText(self.t("undo"))
        self.undo_button.setToolTip(self.t("undo_tooltip"))
        self.redo_button.setText(self.t("redo"))
        self.redo_button.setToolTip(self.t("redo_tooltip"))
        self.add_files_button.setText(f"＋  {self.t('add_pdfs')}")
        self.add_files_button.setToolTip(self.t("add_pdfs_tooltip"))
        self.theme_button.setToolTip(self.t("change_theme"))
        self.theme_button.setAccessibleName(self.t("change_theme"))
        self.language_combo.setAccessibleName(self.t("language"))
        self.language_combo.setToolTip(self.t("language_tooltip"))

        self.home_title.setText(self.t("home_title"))
        self.home_description.setText(self.t("home_description"))
        self.home_open_button.setText(f"＋  {self.t('open_pdfs')}")
        self.home_open_button.setToolTip(self.t("open_pdfs_tooltip"))
        self.home_open_button.setAccessibleName(self.t("open_pdfs"))
        self.home_drop_prompt.setText(self.t("drop_prompt"))
        self.home_privacy.setText(self.t("privacy_local"))

        self.documents_panel.setAccessibleName(self.t("opened_files"))
        self.documents_panel_title.setText(self.t("opened_files"))
        self.documents_panel_description.setText(self.t("sources_unchanged"))
        self.workspace_documents_heading.setText(
            self.t("documents_count", count=self._document_count)
        )
        self.workspace_remove_document_button.setText(self.t("close_pdf"))
        self.workspace_add_documents_button.setText(f"＋  {self.t('add_pdfs')}")
        self.close_all_documents_button.setText(f"⌂  {self.t('close_all_files')}")
        self.close_all_documents_button.setToolTip(self.t("close_all_files_tooltip"))

        self.empty_title.setText(self.t("no_page"))
        self.empty_add_button.setText(f"⊞  {self.t('choose_pdfs')}")
        self.empty_blank_button.setText(f"＋  {self.t('create_blank_a4')}")
        self.search.setPlaceholderText(f"⌕  {self.t('search_page')}")
        self.selection_label.setText(self.t("no_page_selected"))
        self.select_all_button.setText(self.t("select_all"))
        self.split_preview_legend.setText(self.t("split_preview_legend"))
        self.options_selection_label.setText(self.t("no_page_selected"))
        self.options_selection_detail.setText(self.t("select_thumbnails_hint"))
        self.clear_selection_button.setToolTip(self.t("clear_selection"))
        self.organize_search_title.setText(self.t("reorder_paused"))
        self.organize_search_detail.setText(self.t("clear_search_to_reorder"))
        self.clear_search_button.setText(self.t("clear_search"))

        if self.move_group_title is not None:
            self.move_group_title.setText(self.t("move"))
        if self.modify_group_title is not None:
            self.modify_group_title.setText(self.t("modify"))
        if self.insert_group_title is not None:
            self.insert_group_title.setText(self.t("insert_page"))
        self.move_previous_button.setText(f"←  {self.t('move_previous')}")
        self.move_next_button.setText(f"{self.t('move_next')}  →")
        self.move_start_button.setText(self.t("move_start"))
        self.move_end_button.setText(self.t("move_end"))
        self.rotate_left_button.setText(self.t("rotate_left"))
        self.rotate_right_button.setText(self.t("rotate_right"))
        self.duplicate_button.setText(self.t("duplicate_page"))
        self.blank_page_button.setText(f"＋  {self.t('blank_page')}")
        self.delete_button.setText(self.t("delete_page"))

        self.merge_order_heading.setText(self.t("merge_order_output"))
        self.merge_order_hint.setText(self.t("merge_order_hint"))
        self.merge_output_hint.setText(self.t("merge_output_hint"))
        self.split_method_heading.setText(self.t("split_choose_method"))
        self.split_each_radio.setText(self.t("split_each"))
        self.split_batch_radio.setText(self.t("split_batch"))
        self.split_ranges_radio.setText(self.t("split_ranges"))
        self.split_batch_label.setText(self.t("pages_per_file"))
        self.split_ranges_input.setPlaceholderText(self.t("split_ranges_placeholder"))
        self.split_hint.setText(
            self.t("split_ignored_deleted", count=self._deleted_page_count)
        )
        split_descriptions = (
            (self.split_each_card, "split_each_description"),
            (self.split_batch_card, "split_batch_description"),
            (self.split_ranges_card, "split_ranges_description"),
        )
        for card, key in split_descriptions:
            label = card.findChild(QLabel, "splitStrategyDescription")
            if label is not None:
                label.setText(self.t(key))

        for mode, spec in MODE_SPECS.items():
            mode_label = self.t(f"mode_{mode.value}_label")
            description = self.t(f"mode_{mode.value}_home_description")
            action = self.mode_actions[mode]
            button = self.mode_buttons[mode]
            action.setText(mode_label)
            button.setText(mode_label)
            tooltip = (
                description
                if spec.is_selectable
                else self.t("coming_soon_tooltip", description=description)
            )
            action.setToolTip(tooltip)
            button.setToolTip(tooltip)
            button.setAccessibleName(self.t("tool_accessible", tool=mode_label))

        self.set_mode(self.current_mode)
        self._update_split_controls()
        self._update_change_legend()
        self._update_pages_count()
        self._update_selection()

    def _mode_icon(self, spec: ModeSpec) -> QIcon:
        return QIcon(str(asset_path(spec.icon_asset(self._theme.value))))

    def _update_workspace_brand(self) -> None:
        logo_name = "logo_dark.png" if self._theme is Theme.DARK else "logo_white.png"
        pixmap = QPixmap(str(asset_path(logo_name)))
        if pixmap.isNull():
            self.workspace_brand_icon.clear()
        else:
            self.workspace_brand_icon.setPixmap(
                pixmap.scaled(
                    25,
                    31,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        text_color = "#FFFFFF" if self._theme is Theme.DARK else "#172B4D"
        self.workspace_brand_label.setText(
            f'<span style="color:{text_color}">Pixo</span><span style="color:#14B8A6">PDF</span>'
        )

    @property
    def is_home(self) -> bool:
        return self._home_active

    def show_home(self) -> None:
        self._home_active = True
        self.content_stack.setCurrentWidget(self.home_view)
        self.statusbar.hide()
        self.home_button.setProperty("active", True)
        self.home_button.style().unpolish(self.home_button)
        self.home_button.style().polish(self.home_button)
        self.export_button.setEnabled(False)
        self._apply_split_preview(None)
        for task in self._thumbnail_tasks.values():
            task.cancel()
        self._thread_pool.clear()
        self._thumbnail_tasks.clear()
        self._items_by_thumbnail.clear()
        self._thumbnail_cache.clear()

    def show_workspace(self) -> None:
        self._home_active = False
        self.content_stack.setCurrentWidget(self.editor_view)
        self.statusbar.show()
        self.home_button.setProperty("active", False)
        self.home_button.style().unpolish(self.home_button)
        self.home_button.style().polish(self.home_button)
        self._update_export_state()

    def set_mode(self, mode: WorkspaceMode | str) -> None:
        selected = coerce_mode(mode)
        if not MODE_SPECS[selected].is_selectable:
            return
        self.current_mode = selected
        spec = MODE_SPECS[selected]
        mode_label = self.t(f"mode_{selected.value}_label")
        mode_description = self.t(f"mode_{selected.value}_home_description")
        self.options_stack.setCurrentWidget(self.option_panels[selected])
        self.options_heading.setText(mode_label)
        self.options_icon.setPixmap(self._mode_icon(spec).pixmap(QSize(18, 18)))
        self.options_description.setText(
            self.t("organize_short_description")
            if selected is WorkspaceMode.ORGANIZE
            else mode_description
        )
        self.options_description.setVisible(selected is not WorkspaceMode.ORGANIZE)
        self.options_description.setToolTip(mode_description)
        status_key = {
            ModeStatus.READY: "available",
            ModeStatus.PARTIAL: "essential_features",
            ModeStatus.COMING_SOON: "coming_soon",
        }[spec.status]
        self.options_status.setText(self.t(status_key))
        self.options_status.setProperty("status", spec.status.value)
        self.options_status.style().unpolish(self.options_status)
        self.options_status.style().polish(self.options_status)
        self.options_status.setVisible(spec.status is not ModeStatus.READY)
        self.clear_selection_button.setVisible(
            selected is WorkspaceMode.ORGANIZE and bool(self.pages.selectedItems())
        )
        self.pages_heading.setText(self.t(f"mode_{selected.value}_workspace_title"))
        self.mode_button.setText(mode_label)
        self.mode_button.setIcon(self._mode_icon(spec))
        self.mode_button.setToolTip(self.t("active_tool", tool=mode_label))
        self.mode_buttons[selected].setChecked(True)
        for action_mode, action in self.mode_actions.items():
            action.setChecked(action_mode is selected)
        if selected is WorkspaceMode.SPLIT:
            self._update_split_controls()
        else:
            self._apply_split_preview(None)
        self._update_primary_action()
        self._update_export_state()
        self._update_change_legend()
        if not self._page_total:
            self.empty_title.setText(self.t("no_page"))
            self.empty_detail.setText(
                self.t(
                    "empty_mode_detail",
                    title=self.t(f"mode_{selected.value}_home_title"),
                )
            )

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        for mode, action in self.mode_actions.items():
            action.setIcon(self._mode_icon(MODE_SPECS[mode]))
        for mode, button in self.mode_buttons.items():
            button.setIcon(self._mode_icon(MODE_SPECS[mode]))
        self.mode_button.setIcon(self._mode_icon(MODE_SPECS[self.current_mode]))
        self.options_icon.setPixmap(
            self._mode_icon(MODE_SPECS[self.current_mode]).pixmap(QSize(18, 18))
        )
        self._update_workspace_brand()

    def _update_export_state(self) -> None:
        can_export = (
            not self._home_active
            and bool(self._active_page_count)
            and (self.current_mode is not WorkspaceMode.MERGE or self._document_count >= 2)
        )
        if self.current_mode is WorkspaceMode.SPLIT:
            can_export = can_export and self._split_plan_valid
        self.export_button.setEnabled(can_export)

    def _apply_split_preview(self, groups: list[list[int]] | None) -> None:
        preview_active = self.current_mode is WorkspaceMode.SPLIT and groups is not None
        memberships: list[list[int]] = [[] for _ in range(self._active_page_count)]
        if preview_active and groups is not None:
            for group_number, page_indices in enumerate(groups, start=1):
                for page_index in page_indices:
                    if 0 <= page_index < len(memberships):
                        memberships[page_index].append(group_number)

        active_position = 0
        for row in range(self.pages.count()):
            item = self.pages.item(row)
            changes = PageChange(int(item.data(PAGE_CHANGE_ROLE) or 0))
            base_tooltip = str(item.data(BASE_TOOLTIP_ROLE) or item.toolTip())
            if not preview_active or changes & PageChange.DELETED:
                item.setData(SPLIT_GROUPS_ROLE, None)
                item.setToolTip(base_tooltip)
                continue
            item_groups = tuple(memberships[active_position])
            item.setData(SPLIT_GROUPS_ROLE, item_groups)
            page_position = active_position + 1
            active_position += 1
            if item_groups:
                outputs = ", ".join(
                    self.t("pdf_number", number=number) for number in item_groups
                )
                split_detail = self.t(
                    "split_page_outputs",
                    page=page_position,
                    outputs=outputs,
                )
            else:
                split_detail = self.t("split_page_excluded", page=page_position)
            item.setToolTip(f"{base_tooltip}\n{split_detail}")

        self.split_preview_legend.setVisible(preview_active)
        self.pages.viewport().update()

    def _update_primary_action(self) -> None:
        if self.current_mode is WorkspaceMode.MERGE:
            text = self.t("merge_and_export")
            tooltip = self.t("merge_and_export_tooltip")
        elif self.current_mode is WorkspaceMode.SPLIT:
            text = (
                self.t("split_into_count", count=self._split_output_count)
                if self._split_output_count
                else self.t("mode_split_label")
            )
            tooltip = self.t("split_export_tooltip")
        else:
            text = self.t("export")
            tooltip = self.t("export_tooltip")
        self.export_button.setText(text)
        self.export_button.setToolTip(tooltip)

    def _update_change_legend(self) -> None:
        organize_mode = self.current_mode is WorkspaceMode.ORGANIZE
        self.moved_pages_legend.setText(
            f"●  {self.tc('moved_pages_count', self._moved_page_count)}"
        )
        self.modified_pages_legend.setText(
            f"●  {self.tc('modified_pages_count', self._modified_page_count)}"
        )
        self.deleted_pages_legend.setText(
            f"●  {self.tc('deleted_pages_count', self._deleted_page_count)}"
        )
        self.moved_pages_legend.setVisible(organize_mode and self._moved_page_count > 0)
        self.modified_pages_legend.setVisible(organize_mode and self._modified_page_count > 0)
        self.deleted_pages_legend.setVisible(organize_mode and self._deleted_page_count > 0)

    def _create_statusbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("statusbar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 7, 16, 7)
        self.status = QLabel(self._base_status)
        self.status.setObjectName("muted")
        layout.addWidget(self.status)
        layout.addStretch()
        zoom_out = self._button("−", self._zoom_out, "iconButton", "Réduire les miniatures")
        layout.addWidget(zoom_out)
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(90, 180)
        self.zoom_slider.setValue(126)
        self.zoom_slider.setFixedWidth(110)
        self.zoom_slider.setAccessibleName("Taille des miniatures")
        self.zoom_slider.valueChanged.connect(self._set_thumbnail_size)
        layout.addWidget(self.zoom_slider)
        zoom_in = self._button("＋", self._zoom_in, "iconButton", "Agrandir les miniatures")
        layout.addWidget(zoom_in)
        self.zoom_label = QLabel("100 %")
        self.zoom_label.setMinimumWidth(44)
        layout.addWidget(self.zoom_label)
        return bar

    def selected_indices(self) -> list[int]:
        return sorted(self.pages.row(item) for item in self.pages.selectedItems())

    def selected_page_ids(self) -> set[str]:
        return {str(item.data(PAGE_ID_ROLE)) for item in self.pages.selectedItems()}

    def select_page_ids(self, page_ids: Sequence[object]) -> None:
        wanted = {str(page_id) for page_id in page_ids}
        previous_state = self.pages.blockSignals(True)
        first_match: QListWidgetItem | None = None
        try:
            self.pages.clearSelection()
            for row in range(self.pages.count()):
                item = self.pages.item(row)
                if str(item.data(PAGE_ID_ROLE)) in wanted:
                    item.setSelected(True)
                    first_match = first_match or item
        finally:
            self.pages.blockSignals(previous_state)
        self._update_selection()
        if first_match is not None:
            self.pages.scrollToItem(first_match, QAbstractItemView.ScrollHint.EnsureVisible)

    def _request_delete(self) -> None:
        indices = self.selected_indices()
        if not indices:
            return
        deleted_indices = [
            index
            for index in indices
            if PageChange(int(self.pages.item(index).data(PAGE_CHANGE_ROLE) or 0))
            & PageChange.DELETED
        ]
        if len(deleted_indices) == len(indices):
            self.restore_requested.emit(deleted_indices)
            return
        self.delete_requested.emit([index for index in indices if index not in deleted_indices])

    def _request_remove_document(self, documents: QListWidget) -> None:
        item = documents.currentItem()
        if item is None:
            return
        document_id = str(item.data(DOCUMENT_ID_ROLE) or "")
        if document_id:
            self.remove_document_requested.emit(document_id)

    def _request_duplicate(self) -> None:
        indices = self.selected_indices()
        if indices:
            self.duplicate_requested.emit(indices)

    def _request_blank(self, position: str, page_size: tuple[float, float]) -> None:
        indices = self.selected_indices()
        if position == "before" and indices:
            insertion_index = indices[0]
        elif position == "end" or not indices:
            insertion_index = self.pages.count()
        else:
            insertion_index = indices[-1] + 1
        self.blank_page_requested.emit(insertion_index, *page_size)

    def request_default_blank_page(self) -> None:
        self._request_blank("after", A4_PORTRAIT)

    def _ordered_ids_for_move(self, mode: str) -> list[object]:
        current = self.pages._current_ids()
        selected = {item.data(PAGE_ID_ROLE) for item in self.pages.selectedItems()}
        if not selected:
            return current
        if mode == "start":
            return [value for value in current if value in selected] + [
                value for value in current if value not in selected
            ]
        if mode == "end":
            return [value for value in current if value not in selected] + [
                value for value in current if value in selected
            ]
        ordered = list(current)
        if mode == "previous":
            for index in range(1, len(ordered)):
                if ordered[index] in selected and ordered[index - 1] not in selected:
                    ordered[index - 1], ordered[index] = ordered[index], ordered[index - 1]
            return ordered
        if mode == "next":
            for index in range(len(ordered) - 2, -1, -1):
                if ordered[index] in selected and ordered[index + 1] not in selected:
                    ordered[index], ordered[index + 1] = ordered[index + 1], ordered[index]
            return ordered
        raise ValueError(f"Mode de déplacement inconnu : {mode}")

    def _request_move(self, mode: str) -> None:
        if self.search.text().strip() or any(
            PageChange(int(item.data(PAGE_CHANGE_ROLE) or 0)) & PageChange.DELETED
            for item in self.pages.selectedItems()
        ):
            return
        ordered_ids = self._ordered_ids_for_move(mode)
        if ordered_ids != self.pages._current_ids():
            self.reorder_requested.emit(ordered_ids)

    def _summarize_numbers(self, numbers: Sequence[int]) -> str:
        values = [str(number) for number in numbers]
        if len(values) <= 1:
            return "".join(values)
        if len(values) <= 4:
            return self.t(
                "number_list_last",
                values=", ".join(values[:-1]),
                last=values[-1],
            )
        return self.t(
            "number_list_others",
            values=", ".join(values[:3]),
            count=len(values) - 3,
        )

    def _update_selection(self) -> None:
        selected_items = sorted(self.pages.selectedItems(), key=self.pages.row)
        count = len(selected_items)
        has_selection = count > 0
        selected_changes = [
            PageChange(int(item.data(PAGE_CHANGE_ROLE) or 0)) for item in selected_items
        ]
        deleted_selection_count = sum(
            bool(changes & PageChange.DELETED) for changes in selected_changes
        )
        contains_deleted = deleted_selection_count > 0
        all_deleted = has_selection and deleted_selection_count == count
        active_selection_count = count - deleted_selection_count
        can_edit_selection = has_selection and not contains_deleted
        search_active = bool(self.search.text().strip())
        selection_text = (
            self.t("no_page_selected")
            if count == 0
            else self.tc("selected_pages_count", count)
        )
        self.selection_label.setText(selection_text)
        self.options_selection_label.setText(selection_text)
        self.clear_selection_button.setEnabled(has_selection)
        self.clear_selection_button.setVisible(
            has_selection and self.current_mode is WorkspaceMode.ORGANIZE
        )
        self.move_group.setVisible(True)
        self.modify_group.setVisible(True)
        self.organize_danger_zone.setVisible(True)
        self.organize_search_banner.setVisible(search_active)
        self.organize_selection_card.setVisible(not search_active)

        if has_selection:
            stable_numbers = [
                int(item.data(STABLE_NUMBER_ROLE) or self.pages.row(item) + 1)
                for item in selected_items
            ]
            positions = [
                int(item.data(CURRENT_POSITION_ROLE) or self.pages.row(item) + 1)
                for item in selected_items
            ]
            if count == 1:
                changes = PageChange(int(selected_items[0].data(PAGE_CHANGE_ROLE) or 0))
                if change_label := page_change_label(changes, self.language):
                    self.options_selection_change.setText(change_label)
                    self.options_selection_change.setProperty(
                        "changeKind",
                        (
                            "deleted"
                            if changes & PageChange.DELETED
                            else "modified"
                            if changes & (PageChange.MODIFIED | PageChange.ADDED)
                            else "moved"
                        ),
                    )
                    self.options_selection_change.style().unpolish(self.options_selection_change)
                    self.options_selection_change.style().polish(self.options_selection_change)
                    self.options_selection_change.show()
                else:
                    self.options_selection_change.hide()
                self.options_selection_detail.setText(
                    self.t(
                        "selection_single_detail",
                        page=stable_numbers[0],
                        position=positions[0],
                        total=self.pages.count(),
                    )
                )
                self.move_position_label.setText(
                    self.t(
                        "current_position",
                        position=positions[0],
                        total=self.pages.count(),
                    )
                )
                self.blank_target_label.setText(
                    self.t("blank_after_page", page=stable_numbers[0])
                )
            else:
                self.options_selection_change.hide()
                detail = self.t(
                    "selection_multiple_detail",
                    pages=self._summarize_numbers(stable_numbers),
                )
                if deleted_selection_count:
                    detail += self.t(
                        "selection_deleted_suffix",
                        count=deleted_selection_count,
                    )
                self.options_selection_detail.setText(detail)
                self.move_position_label.setText(
                    self.t(
                        "current_positions",
                        positions=self._summarize_numbers(positions),
                    )
                )
                self.blank_target_label.setText(self.t("blank_after_selection"))
        else:
            self.options_selection_change.hide()
            self.options_selection_detail.setText(self.t("select_thumbnails_hint"))
            self.move_position_label.setText(self.t("select_pages_to_move"))
            self.blank_target_label.setText(self.t("blank_at_end"))

        selection_state = "selected" if has_selection else "empty"
        self.organize_selection_card.setProperty("selectionState", selection_state)
        self.organize_selection_card.style().unpolish(self.organize_selection_card)
        self.organize_selection_card.style().polish(self.organize_selection_card)

        for button in self._selection_actions:
            button.setEnabled(can_edit_selection)
        self.delete_button.setEnabled(has_selection)
        self.duplicate_button.setText(
            self.t("duplicate_page")
            if count < 2
            else self.t("duplicate_pages_count", count=count)
        )
        if all_deleted:
            self.delete_button.setText(
                self.t("restore_page")
                if count == 1
                else self.t("restore_pages_count", count=count)
            )
            self.delete_button.setProperty("actionKind", "restore")
            self.delete_button.setToolTip("Réintégrer les pages sélectionnées dans l’export")
        else:
            delete_label_count = active_selection_count or count
            self.delete_button.setText(
                self.t("delete_page")
                if delete_label_count == 1
                else self.t("delete_pages_count", count=delete_label_count)
            )
            self.delete_button.setProperty("actionKind", "delete")
            self.delete_button.setToolTip(
                "Marquer les pages sélectionnées comme supprimées (Suppr)"
            )
        self.delete_button.style().unpolish(self.delete_button)
        self.delete_button.style().polish(self.delete_button)
        if has_selection:
            selection_wording = (
                "la page sélectionnée" if count == 1 else f"les {count} pages sélectionnées"
            )
            if can_edit_selection:
                self.duplicate_button.setAccessibleName(
                    "Dupliquer la page sélectionnée"
                    if count == 1
                    else f"Dupliquer les {count} pages sélectionnées"
                )
                self.duplicate_button.setAccessibleDescription(
                    f"Crée une copie de {selection_wording}."
                )
                self.rotate_left_button.setAccessibleDescription(
                    f"Tourne {selection_wording} de 90 degrés vers la gauche."
                )
                self.rotate_right_button.setAccessibleDescription(
                    f"Tourne {selection_wording} de 90 degrés vers la droite."
                )
            else:
                deleted_description = (
                    "Restaurez les pages supprimées avant de les modifier ou de les déplacer."
                )
                self.duplicate_button.setAccessibleName("Dupliquer des pages")
                self.duplicate_button.setAccessibleDescription(deleted_description)
                self.rotate_left_button.setAccessibleDescription(deleted_description)
                self.rotate_right_button.setAccessibleDescription(deleted_description)
            if all_deleted:
                self.delete_button.setAccessibleName(
                    "Restaurer la page supprimée"
                    if count == 1
                    else f"Restaurer les {count} pages supprimées"
                )
                self.delete_button.setAccessibleDescription(
                    "Réintègre la sélection dans le PDF exporté."
                )
            else:
                self.delete_button.setAccessibleName(
                    "Supprimer la page sélectionnée"
                    if active_selection_count == 1
                    else f"Supprimer les {active_selection_count} pages actives sélectionnées"
                )
                self.delete_button.setAccessibleDescription(
                    "Conserve les vignettes en gris et exclut ces pages du PDF exporté."
                )
        else:
            selection_wording = "la sélection"
            unavailable_description = "Sélectionnez au moins une page pour activer cette action."
            self.duplicate_button.setAccessibleName("Dupliquer des pages")
            self.delete_button.setAccessibleName("Supprimer des pages")
            self.duplicate_button.setAccessibleDescription(unavailable_description)
            self.delete_button.setAccessibleDescription(unavailable_description)
            self.rotate_left_button.setAccessibleDescription(unavailable_description)
            self.rotate_right_button.setAccessibleDescription(unavailable_description)
        self.blank_after_action.setEnabled(has_selection)
        self.blank_before_action.setEnabled(has_selection)
        self.blank_landscape_action.setText(
            self.t("blank_landscape_after_selection")
            if has_selection
            else self.t("blank_landscape_at_end")
        )
        self.blank_a5_action.setText(
            self.t("blank_a5_after_selection")
            if has_selection
            else self.t("blank_a5_at_end")
        )
        reordering_allowed = can_edit_selection and not search_active
        current_ids = self.pages._current_ids()
        move_labels = {
            "start": ("Placer au début", "La sélection est déjà au début."),
            "previous": ("Reculer d’une position", "Impossible de reculer davantage."),
            "next": ("Avancer d’une position", "Impossible d’avancer davantage."),
            "end": ("Placer à la fin", "La sélection est déjà à la fin."),
        }
        for mode, button in self._move_buttons.items():
            changes_order = self._ordered_ids_for_move(mode) != current_ids
            button.setEnabled(reordering_allowed and changes_order)
            action_name, boundary_reason = move_labels[mode]
            button.setAccessibleName(action_name)
            if search_active:
                description = "Effacez la recherche pour réorganiser les pages."
            elif not has_selection:
                description = "Sélectionnez au moins une page."
            elif contains_deleted:
                description = "Restaurez les pages supprimées avant de les déplacer."
            elif not changes_order:
                description = boundary_reason
            else:
                description = f"{action_name} pour {selection_wording}."
            button.setToolTip(description)
            button.setAccessibleDescription(description)
        if search_active:
            self.move_hint.setText(self.t("clear_search_to_reorder_short"))
        elif count > 1:
            self.move_hint.setText(self.t("relative_order_drag_active"))
        else:
            self.move_hint.setText(self.t("stable_indices_drag_active"))
        self.layout_summary_label.setText(
            self.t("layout_after_selected", count=count)
            if count
            else self.t("layout_no_selection")
        )

    def _filter_pages(self, query: str) -> None:
        normalized = query.strip().casefold()
        if normalized:
            self.pages.clearSelection()
            self.pages.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
            self.pages._clear_drop_indicator()
        else:
            self.pages.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        visible = 0
        for row in range(self.pages.count()):
            item = self.pages.item(row)
            matches = not normalized or normalized in str(item.data(SEARCH_ROLE)).casefold()
            item.setHidden(not matches)
            visible += int(matches)
        if normalized:
            self.pages_count.setText(
                self.t("search_results", visible=visible, total=self._page_total)
            )
        else:
            self._update_pages_count()
        self._update_selection()

    def _zoom_out(self) -> None:
        self.zoom_slider.setValue(self.zoom_slider.value() - 12)

    def _zoom_in(self) -> None:
        self.zoom_slider.setValue(self.zoom_slider.value() + 12)

    def _set_thumbnail_size(self, width: int) -> None:
        height = round(width * 1.30)
        self.pages.setIconSize(QSize(width, height))
        self.pages.setGridSize(QSize(width + 26, height + 42))
        percentage = round(width / 126 * 100)
        self.zoom_label.setText(f"{percentage} %")

    def set_history_state(self, can_undo: bool, can_redo: bool) -> None:
        self.undo_button.setEnabled(can_undo)
        self.redo_button.setEnabled(can_redo)

    def show_message(self, message: str, error: bool = False) -> None:
        self._message_token += 1
        token = self._message_token
        self.status.setText(message)
        self.status.setProperty("feedback", "error" if error else "success")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        QTimer.singleShot(4500, lambda: self._restore_status(token))

    def _restore_status(self, token: int | None = None) -> None:
        if token is not None and token != self._message_token:
            return
        self.status.setProperty("feedback", "none")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status.setText(self._base_status)

    def _schedule_thumbnail(self, key: ThumbnailKey) -> None:
        if key in self._thumbnail_tasks:
            return
        task = ThumbnailTask(self.renderer, key, THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)
        task.signals.finished.connect(self._thumbnail_ready)
        task.signals.failed.connect(self._thumbnail_failed)
        self._thumbnail_tasks[key] = task
        self._thread_pool.start(task)

    def shutdown(self) -> None:
        """Stop preview jobs before Qt destroys their signal receivers."""
        for task in self._thumbnail_tasks.values():
            task.cancel()
        self._thread_pool.clear()
        self._thread_pool.waitForDone()
        self._thumbnail_tasks.clear()

    def _pixmap_from_data(self, key: ThumbnailKey, data: bytes) -> QPixmap | None:
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            return None
        rotation = key[2]
        if rotation:
            pixmap = pixmap.transformed(
                QTransform().rotate(rotation),
                Qt.TransformationMode.SmoothTransformation,
            )
        return pixmap

    def _blank_thumbnail(self, page_size: tuple[float, float], rotation: int) -> QPixmap:
        cache_key = (page_size, rotation)
        if cache_key in self._blank_thumbnails:
            return self._blank_thumbnails[cache_key]
        pixmap = QPixmap(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = page_size
        available_width = THUMBNAIL_WIDTH - 8
        available_height = THUMBNAIL_HEIGHT - 8
        scale = min(available_width / width, available_height / height)
        page_width = max(1, round(width * scale))
        page_height = max(1, round(height * scale))
        page_rect = QRect(
            (THUMBNAIL_WIDTH - page_width) // 2,
            (THUMBNAIL_HEIGHT - page_height) // 2,
            page_width,
            page_height,
        )
        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(QPen(QColor("#CBD5E1"), 2))
        painter.drawRoundedRect(page_rect, 5, 5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#F59E0B"))
        fold = 22
        painter.drawPolygon(
            QPolygon(
                [
                    QPoint(page_rect.right() - fold, page_rect.top()),
                    QPoint(page_rect.right(), page_rect.top()),
                    QPoint(page_rect.right(), page_rect.top() + fold),
                ]
            )
        )
        painter.setPen(QColor("#64748B"))
        painter.drawText(
            page_rect,
            Qt.AlignmentFlag.AlignCenter,
            self.t("blank_page").replace(" ", "\n", 1),
        )
        painter.end()
        if rotation:
            pixmap = pixmap.transformed(
                QTransform().rotate(rotation),
                Qt.TransformationMode.SmoothTransformation,
            )
        self._blank_thumbnails[cache_key] = pixmap
        return pixmap

    def _thumbnail_ready(self, key_object: object, data: bytes) -> None:
        key = key_object
        if not isinstance(key, tuple) or len(key) != 3:
            return
        typed_key: ThumbnailKey = key
        self._thumbnail_tasks.pop(typed_key, None)
        if self._home_active:
            return
        pixmap = self._pixmap_from_data(typed_key, data)
        if pixmap is None:
            self._mark_thumbnail_failed(typed_key, self.t("invalid_thumbnail"))
            return
        self._thumbnail_cache[typed_key] = pixmap
        self._thumbnail_cache.move_to_end(typed_key)
        while len(self._thumbnail_cache) > 200:
            self._thumbnail_cache.popitem(last=False)
        for item in self._items_by_thumbnail.get(typed_key, []):
            item.setIcon(QIcon(pixmap))
            item.setText(str(item.data(DISPLAY_ROLE)))
        self._update_pages_count()

    def _thumbnail_failed(self, key_object: object, error: str) -> None:
        key = key_object
        if not isinstance(key, tuple) or len(key) != 3:
            return
        typed_key: ThumbnailKey = key
        self._thumbnail_tasks.pop(typed_key, None)
        if self._home_active:
            return
        self._mark_thumbnail_failed(typed_key, error)

    def _mark_thumbnail_failed(self, key: ThumbnailKey, error: str) -> None:
        for item in self._items_by_thumbnail.get(key, []):
            item.setText(f"{self.t('preview_unavailable')}\n{item.data(DISPLAY_ROLE)}")
            item.setToolTip(self.t("preview_generation_failed", error=error))
        self._update_pages_count()

    def _update_pages_count(self) -> None:
        if self.search.text().strip():
            return
        pending = len(self._thumbnail_tasks)
        suffix = (
            f"  •  {self.tc('previews_in_progress', pending)}" if pending else ""
        )
        deleted_suffix = (
            f"  •  {self.tc('deleted_pages_count', self._deleted_page_count)}"
            if self._deleted_page_count
            else ""
        )
        self.pages_count.setText(
            f"{self.tc('pages_count', self._page_total)}{deleted_suffix}{suffix}"
        )

    def _page_display_text(self, page: PageReference, current_position: int) -> str:
        text = self.t("page_number", number=page.stable_number)
        details: list[str] = []
        if current_position != page.stable_number:
            details.append(self.t("page_position_short", position=current_position))
        if page.rotation:
            details.append(f"↻ {page.rotation}°")
        return f"{text}  ·  {'  ·  '.join(details)}" if details else text

    def _page_tooltip(
        self,
        page: PageReference,
        current_position: int,
        source_detail: str,
    ) -> str:
        lines = [
            self.t("stable_index", number=page.stable_number),
            self.t("current_position_short", position=current_position),
            source_detail,
        ]
        change_label = page_change_label(page.changes, self.language)
        if change_label:
            lines.append(self.t("page_state", state=change_label))
        return "\n".join(lines)

    def _populate_documents_list(
        self,
        documents: QListWidget,
        heading: QLabel,
        remove_button: QPushButton,
        project: PdfProject,
    ) -> None:
        current_item = documents.currentItem()
        selected_id = str(current_item.data(DOCUMENT_ID_ROLE)) if current_item is not None else ""
        documents.clear()
        selected_row = -1
        for row, document in enumerate(project.documents.values()):
            item = QListWidgetItem(
                f"▧  {document.display_name}\n"
                f"     {self.tc('pages_count', document.page_count)}"
            )
            item.setData(DOCUMENT_ID_ROLE, str(document.id))
            item.setToolTip(f"{document.path}\n{self.t('original_file_unchanged')}")
            documents.addItem(item)
            if str(document.id) == selected_id:
                selected_row = row
        heading.setText(self.t("documents_count", count=len(project.documents)))
        documents.setVisible(bool(project.documents))
        if selected_row >= 0:
            documents.setCurrentRow(selected_row)
        remove_button.setEnabled(documents.currentItem() is not None)

    def refresh(self, project: PdfProject) -> None:
        self._project = project
        project.ensure_page_numbers()
        selected_ids = self.selected_page_ids()
        scroll_position = self.pages.verticalScrollBar().value()
        self._populate_documents_list(
            self.workspace_documents,
            self.workspace_documents_heading,
            self.workspace_remove_document_button,
            project,
        )
        self.close_all_documents_button.setEnabled(bool(project.documents or project.pages))
        self._document_count = len(project.documents)
        self._items_by_thumbnail.clear()
        self.pages.clear()
        moved_count = 0
        modified_count = 0
        deleted_count = 0
        for index, page in enumerate(project.pages):
            current_position = index + 1
            display_text = self._page_display_text(page, current_position)
            item = QListWidgetItem(f"{self.t('loading')}\n{display_text}")
            item.setData(PAGE_ID_ROLE, str(page.id))
            item.setData(DISPLAY_ROLE, display_text)
            item.setData(STABLE_NUMBER_ROLE, page.stable_number)
            item.setData(CURRENT_POSITION_ROLE, current_position)
            item.setData(PAGE_CHANGE_ROLE, int(page.changes))
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            if page.is_deleted:
                deleted_count += 1
            else:
                moved_count += int(bool(page.changes & PageChange.MOVED))
                modified_count += int(bool(page.changes & (PageChange.MODIFIED | PageChange.ADDED)))
            deleted_search = f" {self.t('deleted')}" if page.is_deleted else ""
            if page.is_blank:
                item.setData(
                    SEARCH_ROLE,
                    f"{self.t('page')} {page.stable_number} "
                    f"{self.t('position')} {current_position} "
                    f"{self.t('blank_page').lower()}{deleted_search}",
                )
                page_size = page.blank_size or A4_PORTRAIT
                item.setToolTip(
                    self._page_tooltip(
                        page,
                        current_position,
                        self.t(
                            "blank_page_dimensions",
                            width=round(page_size[0]),
                            height=round(page_size[1]),
                        ),
                    )
                )
                item.setIcon(QIcon(self._blank_thumbnail(page_size, page.rotation)))
                item.setText(display_text)
            else:
                source = project.source_for(page)
                if page.source_page_index is None:
                    item.setData(
                        SEARCH_ROLE,
                        f"{self.t('page')} {page.stable_number} "
                        f"{self.t('position')} {current_position} "
                        f"{self.t('invalid_reference')}{deleted_search}",
                    )
                    item.setToolTip(
                        self._page_tooltip(
                            page,
                            current_position,
                            self.t("invalid_source_reference"),
                        )
                    )
                    item.setText(f"{self.t('preview_unavailable')}\n{display_text}")
                else:
                    search_text = (
                        f"{self.t('page')} {page.stable_number} "
                        f"{self.t('position')} {current_position} "
                        f"{source.display_name} {self.t('source_page')} "
                        f"{page.source_page_index + 1}{deleted_search}"
                    )
                    item.setData(SEARCH_ROLE, search_text)
                    item.setToolTip(
                        self._page_tooltip(
                            page,
                            current_position,
                            self.t(
                                "source_page_detail",
                                document=source.display_name,
                                page=page.source_page_index + 1,
                            ),
                        )
                    )
                    key: ThumbnailKey = (
                        source.path,
                        page.source_page_index,
                        page.rotation,
                    )
                    self._items_by_thumbnail.setdefault(key, []).append(item)
                    thumbnail = self._thumbnail_cache.get(key)
                    if thumbnail is not None:
                        self._thumbnail_cache.move_to_end(key)
                        item.setIcon(QIcon(thumbnail))
                        item.setText(display_text)
                    else:
                        self._schedule_thumbnail(key)
            item.setData(BASE_TOOLTIP_ROLE, item.toolTip())
            self.pages.addItem(item)
            if str(page.id) in selected_ids:
                item.setSelected(True)
        self._page_total = len(project.pages)
        self._active_page_count = project.active_page_count
        self._moved_page_count = moved_count
        self._modified_page_count = modified_count
        self._deleted_page_count = deleted_count
        self._update_change_legend()
        if project.documents and not project.pages:
            self.empty_title.setText(self.t("all_pages_removed"))
            self.empty_detail.setText(self.t("restore_or_add_pdf"))
        else:
            self.empty_title.setText(self.t("no_page"))
            self.empty_detail.setText(
                self.t(
                    "empty_mode_detail",
                    title=self.t(f"mode_{self.current_mode.value}_home_title"),
                )
            )
        self.page_stack.setCurrentWidget(self.pages if project.pages else self.empty_state)
        self.search.setEnabled(bool(project.pages))
        self.select_all_button.setEnabled(bool(project.pages))
        self._update_split_controls()
        self._update_export_state()
        if len(project.documents) == 0:
            self.merge_summary_label.setText(self.t("merge_need_two"))
        elif len(project.documents) == 1:
            self.merge_summary_label.setText(
                self.t("merge_one_document", pages=self._active_page_count)
            )
        else:
            self.merge_summary_label.setText(
                self.t(
                    "merge_ready",
                    documents=len(project.documents),
                    pages=self._active_page_count,
                )
            )
        deleted_status = (
            f"     {self.tc('deleted_pages_count', deleted_count)}"
            if deleted_count
            else ""
        )
        self._base_status = (
            f"{self.tc('active_pages_count', self._active_page_count)}"
            f"{deleted_status}     "
            f"{self.t('documents_count', count=len(project.documents))}     "
            f"{self.t('processing_local')}"
        )
        self._message_token += 1
        self._restore_status()
        self._update_pages_count()
        self._update_selection()
        if project.documents or project.pages:
            self.show_workspace()
        else:
            self.show_home()
        QTimer.singleShot(0, lambda: self.pages.verticalScrollBar().setValue(scroll_position))
