"""Application dialogs shared by the main menu.

The dialogs intentionally depend only on public configuration and translation
helpers.  They can therefore be opened from the main window without carrying
workspace state or starting background work.
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from pixopdf.assets import asset_path
from pixopdf.config import (
    APP_NAME,
    DONATION_URL,
    PROJECT_LICENSE,
    PROJECT_URL,
    VERSION,
)
from pixopdf.language_config import (
    DEFAULT_LANGUAGE,
    LANGUAGES,
    is_rtl,
    language_name,
    translate,
)
from pixopdf.ui.themes.theme_manager import Theme


def _layout_direction(language: str) -> Qt.LayoutDirection:
    return Qt.LayoutDirection.RightToLeft if is_rtl(language) else Qt.LayoutDirection.LeftToRight


def _wrapped_label(text: str, object_name: str = "optionsDescription") -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    label.setWordWrap(True)
    return label


def _section(title: str, description: str = "") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("actionCard")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 15, 16, 15)
    layout.setSpacing(9)

    title_label = QLabel(title)
    title_label.setObjectName("sectionTitle")
    layout.addWidget(title_label)
    if description:
        layout.addWidget(_wrapped_label(description))
    return frame, layout


def _dialog_footer(
    dialog: QDialog,
    language: str,
    *,
    accept_text_key: str | None = None,
) -> tuple[QWidget, QPushButton | None, QPushButton]:
    footer = QWidget()
    layout = QHBoxLayout(footer)
    layout.setContentsMargins(0, 4, 0, 0)
    layout.setSpacing(8)
    layout.addStretch(1)

    cancel_button: QPushButton | None = None
    if accept_text_key is not None:
        cancel_button = QPushButton(translate(language, "cancel"))
        cancel_button.setObjectName("secondaryButton")
        cancel_button.clicked.connect(dialog.reject)
        layout.addWidget(cancel_button)

    accept_key = accept_text_key or "close"
    accept_button = QPushButton(translate(language, accept_key))
    accept_button.setObjectName("primaryButton")
    accept_button.setDefault(True)
    accept_button.clicked.connect(dialog.accept)
    layout.addWidget(accept_button)
    return footer, cancel_button, accept_button


class SettingsDialog(QDialog):
    """Edit persistent appearance and update preferences."""

    def __init__(
        self,
        language: str,
        theme: Theme,
        automatic_updates: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._language = language if language in LANGUAGES else DEFAULT_LANGUAGE
        self.setObjectName("settingsDialog")
        self.setWindowTitle(translate(self._language, "settings_title"))
        self.setLayoutDirection(_layout_direction(self._language))
        self.setModal(True)
        self.setMinimumWidth(520)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 20)
        root.setSpacing(14)

        title = QLabel(translate(self._language, "settings_title"))
        title.setObjectName("pageTitle")
        root.addWidget(title)
        root.addWidget(_wrapped_label(translate(self._language, "settings_description")))

        appearance, appearance_layout = _section(translate(self._language, "settings_appearance"))
        appearance_grid = QGridLayout()
        appearance_grid.setHorizontalSpacing(18)
        appearance_grid.setVerticalSpacing(7)

        language_label = QLabel(translate(self._language, "settings_language"))
        language_label.setObjectName("sectionTitle")
        self.language_combo = QComboBox()
        self.language_combo.setObjectName("languageCombo")
        for code in LANGUAGES:
            self.language_combo.addItem(language_name(code), code)
        language_index = self.language_combo.findData(self._language)
        self.language_combo.setCurrentIndex(max(0, language_index))
        self.language_combo.setAccessibleName(language_label.text())
        language_hint = _wrapped_label(translate(self._language, "settings_language_hint"))
        appearance_grid.addWidget(language_label, 0, 0)
        appearance_grid.addWidget(self.language_combo, 0, 1)
        appearance_grid.addWidget(language_hint, 1, 0, 1, 2)

        theme_label = QLabel(translate(self._language, "settings_theme"))
        theme_label.setObjectName("sectionTitle")
        self.theme_combo = QComboBox()
        self.theme_combo.setObjectName("languageCombo")
        self.theme_combo.addItem(translate(self._language, "theme_dark"), Theme.DARK.value)
        self.theme_combo.addItem(
            translate(self._language, "theme_light"),
            Theme.LIGHT.value,
        )
        theme_index = self.theme_combo.findData(theme.value)
        self.theme_combo.setCurrentIndex(max(0, theme_index))
        self.theme_combo.setAccessibleName(theme_label.text())
        theme_hint = _wrapped_label(translate(self._language, "settings_theme_hint"))
        appearance_grid.addWidget(theme_label, 2, 0)
        appearance_grid.addWidget(self.theme_combo, 2, 1)
        appearance_grid.addWidget(theme_hint, 3, 0, 1, 2)
        appearance_grid.setColumnStretch(0, 1)
        appearance_grid.setColumnStretch(1, 1)
        appearance_layout.addLayout(appearance_grid)
        root.addWidget(appearance)

        updates, updates_layout = _section(translate(self._language, "settings_updates"))
        self.automatic_updates_checkbox = QCheckBox(
            translate(self._language, "settings_automatic_updates")
        )
        self.automatic_updates_checkbox.setChecked(automatic_updates)
        updates_layout.addWidget(self.automatic_updates_checkbox)
        updates_layout.addWidget(
            _wrapped_label(translate(self._language, "settings_automatic_updates_hint"))
        )
        root.addWidget(updates)

        footer, cancel_button, save_button = _dialog_footer(
            self,
            self._language,
            accept_text_key="save",
        )
        self.cancel_button = cancel_button
        self.save_button = save_button
        root.addWidget(footer)

    def selected_language(self) -> str:
        """Return the selected supported language code."""

        value: object = self.language_combo.currentData()
        return value if isinstance(value, str) and value in LANGUAGES else DEFAULT_LANGUAGE

    def selected_theme(self) -> Theme:
        """Return the selected application theme."""

        value: object = self.theme_combo.currentData()
        try:
            return Theme(value) if isinstance(value, str) else Theme.DARK
        except ValueError:
            return Theme.DARK

    def automatic_updates_enabled(self) -> bool:
        """Return whether automatic update checks are enabled."""

        return self.automatic_updates_checkbox.isChecked()


class AboutDialog(QDialog):
    """Display project identity, legal details and official external links."""

    def __init__(
        self,
        language: str,
        theme: Theme,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._language = language if language in LANGUAGES else DEFAULT_LANGUAGE
        self.setObjectName("aboutDialog")
        self.setWindowTitle(translate(self._language, "about_title", app=APP_NAME))
        self.setLayoutDirection(_layout_direction(self._language))
        self.setModal(True)
        self.setMinimumWidth(500)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(14)

        identity = QHBoxLayout()
        identity.setSpacing(16)
        self.logo_label = QLabel()
        self.logo_label.setObjectName("aboutLogo")
        logo_name = "logo_dark.png" if theme is Theme.DARK else "logo_white.png"
        logo = QPixmap(str(asset_path(logo_name)))
        if not logo.isNull():
            self.logo_label.setPixmap(
                logo.scaledToHeight(
                    66,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        self.logo_label.setFixedSize(72, 72)
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        identity.addWidget(self.logo_label)

        identity_text = QVBoxLayout()
        identity_text.setSpacing(3)
        self.app_name_label = QLabel(APP_NAME)
        self.app_name_label.setObjectName("pageTitle")
        identity_text.addWidget(self.app_name_label)
        identity_text.addWidget(_wrapped_label(translate(self._language, "about_tagline")))
        identity.addLayout(identity_text, 1)
        root.addLayout(identity)

        metadata, metadata_layout = _section(translate(self._language, "about_local_privacy"))
        metadata_grid = QGridLayout()
        metadata_grid.setHorizontalSpacing(20)
        metadata_grid.setVerticalSpacing(8)
        version_title = QLabel(translate(self._language, "about_version"))
        version_title.setObjectName("optionsDescription")
        self.version_value = QLabel(VERSION)
        self.version_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        license_title = QLabel(translate(self._language, "about_license"))
        license_title.setObjectName("optionsDescription")
        self.license_value = QLabel(PROJECT_LICENSE)
        self.license_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        metadata_grid.addWidget(version_title, 0, 0)
        metadata_grid.addWidget(self.version_value, 0, 1)
        metadata_grid.addWidget(license_title, 1, 0)
        metadata_grid.addWidget(self.license_value, 1, 1)
        metadata_grid.setColumnStretch(1, 1)
        metadata_layout.addLayout(metadata_grid)
        metadata_layout.addWidget(
            _wrapped_label(translate(self._language, "about_local_privacy_detail"))
        )
        root.addWidget(metadata)

        credits, credits_layout = _section(translate(self._language, "about_credits"))
        credits_layout.addWidget(_wrapped_label(translate(self._language, "about_credits_text")))
        root.addWidget(credits)

        links = QHBoxLayout()
        links.setSpacing(8)
        self.project_button = QPushButton(translate(self._language, "project_website"))
        self.project_button.setObjectName("linkButton")
        self.project_button.setToolTip(PROJECT_URL)
        self.project_button.setAccessibleDescription(PROJECT_URL)
        self.project_button.clicked.connect(
            lambda _checked=False: self._open_external_url(PROJECT_URL)
        )
        links.addWidget(self.project_button)

        self.donation_button = QPushButton(translate(self._language, "support_project"))
        self.donation_button.setObjectName("accentFlatButton")
        self.donation_button.setToolTip(DONATION_URL)
        self.donation_button.setAccessibleDescription(DONATION_URL)
        self.donation_button.clicked.connect(
            lambda _checked=False: self._open_external_url(DONATION_URL)
        )
        links.addWidget(self.donation_button)
        links.addStretch(1)
        root.addLayout(links)

        footer, _cancel_button, close_button = _dialog_footer(self, self._language)
        self.close_button = close_button
        root.addWidget(footer)

    @staticmethod
    def _open_external_url(url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))


class QuickHelpDialog(QDialog):
    """A concise offline workflow guide with the application's shortcuts."""

    def __init__(
        self,
        language: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._language = language if language in LANGUAGES else DEFAULT_LANGUAGE
        self.setObjectName("quickHelpDialog")
        self.setWindowTitle(translate(self._language, "quick_help_title"))
        self.setLayoutDirection(_layout_direction(self._language))
        self.setModal(True)
        self.resize(600, 620)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 22, 22, 18)
        outer.setSpacing(12)

        self.title_label = QLabel(translate(self._language, "quick_help_title"))
        self.title_label.setObjectName("pageTitle")
        outer.addWidget(self.title_label)
        outer.addWidget(_wrapped_label(translate(self._language, "quick_help_description")))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(2, 2, 8, 2)
        body_layout.setSpacing(12)

        guide_sections = (
            ("help_get_started_title", "help_get_started_body"),
            ("help_workflow_title", "help_workflow_body"),
            ("help_privacy_title", "help_privacy_body"),
        )
        self.guide_labels: list[QLabel] = []
        for title_key, body_key in guide_sections:
            card, card_layout = _section(translate(self._language, title_key))
            body_label = _wrapped_label(translate(self._language, body_key))
            self.guide_labels.append(body_label)
            card_layout.addWidget(body_label)
            body_layout.addWidget(card)

        shortcuts_card, shortcuts_layout = _section(translate(self._language, "keyboard_shortcuts"))
        shortcuts_grid = QGridLayout()
        shortcuts_grid.setHorizontalSpacing(22)
        shortcuts_grid.setVerticalSpacing(9)
        self.shortcut_rows: list[tuple[QLabel, QLabel]] = []
        for row, (translation_key, standard_key) in enumerate(self._shortcut_definitions()):
            action_label = QLabel(translate(self._language, translation_key))
            sequence_label = QLabel(
                QKeySequence(standard_key).toString(QKeySequence.SequenceFormat.NativeText)
            )
            sequence_label.setObjectName("trustChip")
            sequence_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            shortcuts_grid.addWidget(action_label, row, 0)
            shortcuts_grid.addWidget(sequence_label, row, 1)
            self.shortcut_rows.append((action_label, sequence_label))
        shortcuts_grid.setColumnStretch(0, 1)
        shortcuts_layout.addLayout(shortcuts_grid)
        body_layout.addWidget(shortcuts_card)
        body_layout.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        footer, _cancel_button, close_button = _dialog_footer(self, self._language)
        self.close_button = close_button
        outer.addWidget(footer)

    @staticmethod
    def _shortcut_definitions() -> Iterable[tuple[str, QKeySequence.StandardKey]]:
        return (
            ("add_pdfs", QKeySequence.StandardKey.Open),
            ("export", QKeySequence.StandardKey.Save),
            ("undo", QKeySequence.StandardKey.Undo),
            ("redo", QKeySequence.StandardKey.Redo),
            ("select_all", QKeySequence.StandardKey.SelectAll),
        )
