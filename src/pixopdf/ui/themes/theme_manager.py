from enum import StrEnum

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


class Theme(StrEnum):
    DARK = "dark"
    LIGHT = "light"


BASE_STYLE = """
* { font-size: 13px; }
QMainWindow, QWidget#appRoot { background: %(background)s; color: %(text)s; }
QWidget { color: %(text)s; }
QLabel#brand { color: %(accent_text)s; font-size: 21px; font-weight: 800; }
QWidget#brandWidget { background: transparent; }
QLabel#pageTitle { font-size: 28px; font-weight: 800; }
QLabel#sectionTitle { font-size: 14px; font-weight: 700; }
QLabel#optionsDescription { color: %(muted)s; font-size: 12px; }
QLabel#emptyTitle { font-size: 18px; font-weight: 700; }
QLabel#emptyIcon { color: %(accent_text)s; font-size: 44px; }
QLabel#modeContext { font-size: 14px; font-weight: 700; }
QLabel#dropTitle { font-size: 24px; font-weight: 800; }
QLabel#dropDescription { color: %(muted)s; font-size: 14px; }
QLabel#dropPrompt { color: %(accent_text)s; font-size: 14px; font-weight: 700; }
QLabel#dropPrivacy { color: %(muted)s; font-size: 11px; }
QLabel#trustChip {
    color: %(muted)s; background: %(surface)s; border: 1px solid %(border)s;
    border-radius: 12px; padding: 5px 10px; font-size: 11px;
}
QLabel#changeLegend {
    border-radius: 9px; padding: 4px 8px; font-size: 10px; font-weight: 800;
}
QLabel#changeLegend[changeKind="moved"] {
    color: %(accent_text)s; background: %(teal_bg)s;
}
QLabel#changeLegend[changeKind="modified"] {
    color: %(amber_text)s; background: %(amber_bg)s;
}
QLabel#changeLegend[changeKind="deleted"] {
    color: %(muted)s; background: %(surface_alt)s; border: 1px solid %(border)s;
}
QLabel#splitPreviewLegend {
    color: %(accent_text)s; background: %(teal_bg)s; border: 1px solid #14B8A6;
    border-radius: 9px; padding: 4px 8px; font-size: 10px; font-weight: 800;
}
QLabel#toolIcon { color: %(accent_text)s; font-weight: 700; }
QLabel#optionHeading {
    color: %(muted)s; font-size: 10px; font-weight: 800; padding-top: 7px;
}
QLabel#selectionSummary {
    background: %(teal_bg)s; color: %(accent_text)s; border-radius: 7px;
    padding: 9px 10px; font-weight: 700;
}
QLabel#splitPlanSummary {
    color: %(accent_text)s; background: %(teal_bg)s; border: 1px solid #14B8A6;
    border-radius: 8px; padding: 9px 10px; font-weight: 700;
}
QLabel#splitPlanSummary[feedback="error"] {
    color: %(danger_text)s; background: %(danger_bg)s; border-color: %(danger_border)s;
}
QLabel#organizeSelectionTitle { font-size: 13px; font-weight: 800; }
QLabel#organizeSelectionDetail { color: %(organize_muted)s; font-size: 11px; }
QLabel#organizeChangeChip {
    border-radius: 8px; padding: 3px 7px; font-size: 10px; font-weight: 800;
}
QLabel#organizeChangeChip[changeKind="moved"] {
    color: %(accent_text)s; background: %(teal_bg)s; border: 1px solid #14B8A6;
}
QLabel#organizeChangeChip[changeKind="modified"] {
    color: %(amber_text)s; background: %(amber_bg)s; border: 1px solid #F59E0B;
}
QLabel#organizeChangeChip[changeKind="deleted"] {
    color: %(muted)s; background: %(surface_alt)s; border: 1px solid %(border)s;
}
QLabel#organizeGroupTitle { font-size: 13px; font-weight: 800; }
QLabel#organizeGroupDescription,
QLabel#organizeActionStatus,
QLabel#organizeHint {
    color: %(organize_muted)s; font-size: 11px;
}
QLabel#organizeActionStatus { font-weight: 600; }
QLabel#organizeSearchTitle { color: %(amber_text)s; font-size: 12px; font-weight: 800; }
QLabel#organizeSearchDetail { color: %(organize_muted)s; font-size: 11px; }
QLabel#muted, QLabel[muted="true"] { color: %(muted)s; }
QLabel[feedback="success"] { color: %(accent_text)s; }
QLabel[feedback="error"] { color: %(danger_text)s; }
QLabel#badge {
    color: %(amber_text)s; background: %(amber_bg)s; border-radius: 5px;
    padding: 2px 6px; font-size: 10px; font-weight: 700;
}
QLabel#modeStatusBadge {
    border-radius: 9px; padding: 4px 8px; font-size: 10px; font-weight: 800;
}
QLabel#modeStatusBadge[status="ready"] {
    color: %(accent_text)s; background: %(teal_bg)s;
}
QLabel#modeStatusBadge[status="partial"],
QLabel#modeStatusBadge[status="coming_soon"] {
    color: %(amber_text)s; background: %(amber_bg)s;
}
QLabel#contextHint, QLabel#comingSoonCard {
    color: %(muted)s; background: %(surface_alt)s; border: 1px solid %(border)s;
    border-radius: 8px; padding: 10px;
}
QFrame#sidebar, QFrame#topbar, QFrame#statusbar, QFrame#optionsPanel,
QFrame#contextPanel, QFrame#documentsPanel, QFrame#workspaceCommandBar,
QFrame#workspaceModeBar { background: %(surface)s; border: 0; }
QFrame#sidebar { border-right: 1px solid %(border)s; }
QFrame#optionsPanel { border-left: 1px solid %(border)s; }
QFrame#contextPanel { border-right: 1px solid %(border)s; }
QFrame#topbar { border-bottom: 1px solid %(border)s; }
QFrame#workspaceModeBar { border-top: 1px solid %(border)s; }
QFrame#statusbar { border-top: 1px solid %(border)s; }
QFrame#toolCard, QFrame#actionCard, QFrame#dropZone {
    background: %(surface)s; border: 1px solid %(border)s; border-radius: 9px;
}
QFrame#organizeSelectionCard {
    background: %(surface_alt)s; border: 1px solid %(border)s; border-radius: 10px;
}
QFrame#organizeSelectionCard[selectionState="selected"] {
    background: %(teal_bg)s; border-color: #14B8A6;
}
QFrame#organizeGroupCard {
    background: %(surface_alt)s; border: 1px solid %(border)s; border-radius: 10px;
}
QFrame#splitStrategyCard {
    background: %(surface_alt)s; border: 1px solid %(border)s; border-radius: 10px;
}
QFrame#splitStrategyCard[selected="true"] {
    background: %(teal_bg)s; border: 2px solid #14B8A6;
}
QLabel#splitStrategyDescription {
    color: %(organize_muted)s; font-size: 11px; padding-left: 23px;
}
QFrame#mergeDocumentsCard, QFrame#documentsCard {
    background: %(surface_alt)s; border: 1px solid %(border)s; border-radius: 10px;
}
QFrame#organizeSearchBanner {
    background: %(amber_bg)s; border: 1px solid #F59E0B; border-radius: 9px;
}
QFrame#organizeDangerZone {
    background: transparent; border: 0; border-top: 1px solid %(border)s;
}
QFrame#toolCard:hover { border-color: #14B8A6; }
QPushButton, QToolButton {
    background: transparent; border: 1px solid %(border)s; border-radius: 7px;
    padding: 8px 12px; text-align: left;
}
QPushButton:hover, QToolButton:hover { background: %(hover)s; border-color: #14B8A6; }
QPushButton:pressed, QToolButton:pressed { background: %(pressed)s; }
QPushButton:focus, QToolButton:focus, QLineEdit:focus, QSpinBox:focus, QListWidget:focus {
    border: 2px solid #F59E0B;
}
QPushButton:disabled, QToolButton:disabled {
    color: %(disabled)s; border-color: %(disabled_border)s; background: transparent;
}
QPushButton#navButton { border: 0; padding: 10px 12px; }
QPushButton#modeNavButton {
    border: 1px solid %(border)s; padding: 11px 12px; min-height: 26px;
    text-align: center; font-weight: 700;
}
QPushButton#modeNavButton:checked {
    color: %(accent_text)s; background: %(teal_bg)s; border: 2px solid #14B8A6;
}
QPushButton#workspaceModeNavButton {
    border: 1px solid %(border)s; min-height: 22px; padding: 7px 5px;
    text-align: center; font-size: 12px; font-weight: 700;
}
QPushButton#workspaceModeNavButton:checked {
    color: %(accent_text)s; background: %(teal_bg)s; border: 2px solid #14B8A6;
}
QPushButton#workspaceModeNavButton:disabled {
    color: %(disabled)s; background: %(surface_alt)s; border-color: %(disabled_border)s;
}
QPushButton#topCommandButton {
    border-color: transparent; padding: 7px 9px; text-align: center;
}
QPushButton#topCommandButton:hover { border-color: #14B8A6; }
QPushButton#optionTab { border: 0; padding: 8px 2px; font-size: 10px; }
QPushButton#optionTab:checked { background: %(teal_bg)s; color: %(accent_text)s; font-weight: 700; }
QPushButton#toolButton { border: 0; padding: 4px 2px; color: %(text)s; }
QPushButton#toolButton:hover { color: %(accent_text)s; background: %(hover)s; }
QPushButton#navButton:checked {
    background: %(teal_bg)s; color: %(accent_text)s; font-weight: 700;
}
QPushButton#primaryButton {
    background: #14B8A6; color: #172B4D; border-color: #14B8A6;
    font-weight: 700; padding: 9px 15px;
}
QPushButton#primaryButton:hover { background: #2DD4BF; }
QPushButton#primaryButton:disabled {
    color: %(disabled)s; background: %(surface_alt)s; border-color: %(disabled_border)s;
}
QPushButton#resumeButton { color: %(accent_text)s; border-color: #14B8A6; font-weight: 700; }
QPushButton#accentFlatButton {
    color: %(accent_text)s; background: %(teal_bg)s; border-color: #14B8A6;
    font-weight: 700;
}
QPushButton#plannedAction:disabled {
    color: %(disabled)s; background: %(surface_alt)s; border-color: %(disabled_border)s;
}
QPushButton#moveActionButton, QPushButton#organizeActionButton {
    background: %(surface)s; min-height: 22px; padding: 8px 9px; font-size: 12px;
}
QPushButton#moveActionButton:hover, QPushButton#organizeActionButton:hover {
    background: %(hover)s;
}
QPushButton#moveActionButton:disabled, QPushButton#organizeActionButton:disabled {
    background: transparent;
}
QPushButton#dangerButton {
    color: %(danger_text)s; background: %(danger_bg)s; border-color: %(danger_border)s;
    font-weight: 700; min-height: 22px; text-align: center;
}
QPushButton#dangerButton:hover {
    color: %(danger_text)s; background: %(danger_hover)s; border-color: %(danger_text)s;
}
QPushButton#dangerButton[actionKind="restore"] {
    color: %(accent_text)s; background: %(teal_bg)s; border-color: #14B8A6;
}
QPushButton#dangerButton[actionKind="restore"]:hover {
    color: %(accent_text)s; background: %(hover)s; border-color: #14B8A6;
}
QPushButton#dangerButton:disabled {
    color: %(disabled)s; background: transparent; border-color: %(disabled_border)s;
}
QPushButton#iconButton { padding: 7px; min-width: 18px; text-align: center; }
QPushButton#linkButton {
    color: %(accent_text)s; border: 0; padding: 3px 5px; font-size: 11px;
}
QPushButton#clearSelectionButton {
    color: %(accent_text)s; background: transparent; border: 0; border-radius: 12px;
    min-width: 28px; max-width: 28px; padding: 0; text-align: center;
    font-size: 17px; font-weight: 700;
}
QPushButton#clearSelectionButton:hover { background: %(hover)s; }
QPushButton#searchClearButton {
    color: %(amber_text)s; background: transparent; border: 0;
    padding: 3px 0; font-size: 11px; font-weight: 800;
}
QPushButton#searchClearButton:hover { color: %(text)s; }
QToolButton#accentButton {
    background: %(teal_bg)s; color: %(accent_text)s; border-color: #14B8A6;
    font-weight: 700; min-height: 22px;
}
QToolButton#accentButton::menu-button {
    border-left: 1px solid #14B8A6; width: 28px;
}
QToolButton#organizeInsertButton {
    background: %(teal_bg)s; color: %(accent_text)s; border-color: #14B8A6;
    font-weight: 800; min-height: 24px; padding: 8px 10px;
}
QToolButton#organizeInsertButton:hover { background: %(hover)s; }
QToolButton#organizeInsertButton::menu-button {
    border-left: 1px solid #14B8A6; width: 30px;
}
QToolButton#workspaceModeButton {
    color: %(accent_text)s; background: %(teal_bg)s; border-color: #14B8A6;
    font-weight: 700; min-width: 112px;
}
QLineEdit {
    background: %(surface_alt)s; border: 1px solid %(border)s; border-radius: 7px;
    padding: 8px 11px; selection-background-color: #14B8A6;
}
QSpinBox {
    background: %(surface)s; border: 1px solid %(border)s; border-radius: 7px;
    padding: 6px 8px; min-width: 52px;
}
QRadioButton { spacing: 8px; padding: 3px 0; }
QRadioButton::indicator {
    width: 15px; height: 15px; border: 1px solid %(border)s; border-radius: 8px;
    background: %(surface)s;
}
QRadioButton::indicator:checked {
    background: #14B8A6; border: 4px solid %(surface)s;
}
QListWidget {
    background: transparent; border: 0; outline: 0; padding: 6px;
    alternate-background-color: %(surface_alt)s;
}
QListWidget#mergeDocumentsList, QListWidget#documentsList {
    background: %(surface)s; border: 1px solid %(border)s; border-radius: 7px;
}
QListWidget QAbstractScrollArea, QListWidget::viewport,
QScrollArea QAbstractScrollArea, QScrollArea::viewport { background: %(background)s; }
QListWidget::item { border-radius: 7px; padding: 8px; }
QListWidget::item:hover { background: %(hover)s; }
QListWidget::item:selected { background: %(teal_bg)s; color: %(text)s; border: 1px solid #14B8A6; }
QScrollArea { border: 0; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QAbstractScrollArea::corner { background: transparent; border: 0; }
QScrollArea#optionsScroll, QScrollArea#optionsScroll::viewport,
QWidget#optionsBody { background: transparent; }
QScrollArea#modeNav, QScrollArea#modeNav::viewport,
QWidget#modeNavBody, QStackedWidget#optionsStack { background: transparent; border: 0; }
QMenu {
    background: %(surface_alt)s; color: %(text)s; border: 1px solid %(border)s;
    padding: 5px;
}
QMenu::item { border-radius: 5px; padding: 7px 24px 7px 9px; }
QMenu::item:selected { background: %(teal_bg)s; color: %(accent_text)s; }
QScrollBar:vertical { background: transparent; width: 9px; }
QScrollBar::handle:vertical { background: %(border)s; border-radius: 4px; min-height: 30px; }
QScrollBar:horizontal { background: transparent; height: 5px; }
QScrollBar::handle:horizontal {
    background: %(border)s; border-radius: 2px; min-width: 60px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    background: transparent; border: 0; width: 0;
}
QSplitter::handle { background: %(border)s; width: 1px; }
QSlider::groove:horizontal { height: 4px; background: %(border)s; border-radius: 2px; }
QSlider::handle:horizontal {
    background: #14B8A6; width: 14px; margin: -5px 0; border-radius: 7px;
}
QToolTip { background: %(surface_alt)s; color: %(text)s; border: 1px solid %(border)s; }
"""


PALETTES = {
    Theme.DARK: {
        "background": "#0F172A",
        "surface": "#111827",
        "surface_alt": "#1E293B",
        "border": "#334155",
        "text": "#FFFFFF",
        "muted": "#CBD5E1",
        "organize_muted": "#CBD5E1",
        "hover": "#1E293B",
        "pressed": "#334155",
        "teal_bg": "rgba(20, 184, 166, 0.16)",
        "amber_bg": "rgba(245, 158, 11, 0.18)",
        "accent_text": "#2DD4BF",
        "amber_text": "#FBBF24",
        "danger_text": "#F87171",
        "danger_bg": "rgba(248, 113, 113, 0.10)",
        "danger_hover": "rgba(248, 113, 113, 0.18)",
        "danger_border": "#7F1D1D",
        "disabled": "#64748B",
        "disabled_border": "#334155",
    },
    Theme.LIGHT: {
        "background": "#F8FAFC",
        "surface": "#FFFFFF",
        "surface_alt": "#F1F5F9",
        "border": "#CBD5E1",
        "text": "#172B4D",
        "muted": "#64748B",
        "organize_muted": "#475569",
        "hover": "#F1F5F9",
        "pressed": "#E2E8F0",
        "teal_bg": "rgba(20, 184, 166, 0.12)",
        "amber_bg": "rgba(245, 158, 11, 0.13)",
        "accent_text": "#0F766E",
        "amber_text": "#92400E",
        "danger_text": "#B91C1C",
        "danger_bg": "rgba(185, 28, 28, 0.06)",
        "danger_hover": "rgba(185, 28, 28, 0.12)",
        "danger_border": "#FCA5A5",
        "disabled": "#94A3B8",
        "disabled_border": "#E2E8F0",
    },
}


def apply_theme(app: QApplication, theme: Theme) -> None:
    colors = PALETTES[theme]
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(colors["background"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors["surface"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["surface_alt"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(colors["surface_alt"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#14B8A6"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#172B4D"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(colors["muted"]))
    app.setPalette(palette)
    app.setStyleSheet(BASE_STYLE % colors)
