from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QDialog

from pixopdf.config import (
    APP_NAME,
    DONATION_URL,
    PROJECT_LICENSE,
    PROJECT_URL,
    VERSION,
)
from pixopdf.language_config import LANGUAGES
from pixopdf.ui.dialogs import AboutDialog, QuickHelpDialog, SettingsDialog
from pixopdf.ui.themes.theme_manager import Theme


def test_settings_dialog_exposes_initial_and_edited_values(
    qapp: QApplication,
) -> None:
    dialog = SettingsDialog(
        language="en",
        theme=Theme.LIGHT,
        automatic_updates=False,
    )

    assert dialog.selected_language() == "en"
    assert dialog.selected_theme() is Theme.LIGHT
    assert not dialog.automatic_updates_enabled()
    assert dialog.language_combo.count() == len(LANGUAGES)
    assert dialog.layoutDirection() is Qt.LayoutDirection.LeftToRight

    dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("zh"))
    dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData(Theme.DARK.value))
    dialog.automatic_updates_checkbox.setChecked(True)

    assert dialog.selected_language() == "zh"
    assert dialog.selected_theme() is Theme.DARK
    assert dialog.automatic_updates_enabled()

    dialog.save_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_settings_dialog_falls_back_and_supports_rtl(
    qapp: QApplication,
) -> None:
    fallback = SettingsDialog("unsupported", Theme.DARK, True)
    arabic = SettingsDialog("ar", Theme.DARK, True)

    assert fallback.selected_language() == "fr"
    assert fallback.layoutDirection() is Qt.LayoutDirection.LeftToRight
    assert arabic.selected_language() == "ar"
    assert arabic.layoutDirection() is Qt.LayoutDirection.RightToLeft
    assert arabic.language_combo.itemText(arabic.language_combo.findData("ar")) == "العربية"


def test_about_dialog_displays_metadata_and_opens_official_links(
    qapp: QApplication,
    monkeypatch,
) -> None:
    opened_urls: list[str] = []
    monkeypatch.setattr(
        QDesktopServices,
        "openUrl",
        lambda url: opened_urls.append(url.toString()) or True,
    )
    dialog = AboutDialog("fr", Theme.DARK)

    assert dialog.app_name_label.text() == APP_NAME
    assert dialog.version_value.text() == VERSION
    assert dialog.license_value.text() == PROJECT_LICENSE
    assert dialog.project_button.toolTip() == PROJECT_URL
    assert dialog.donation_button.toolTip() == DONATION_URL
    assert dialog.logo_label.pixmap() is not None
    assert not dialog.logo_label.pixmap().isNull()

    dialog.project_button.click()
    dialog.donation_button.click()

    assert opened_urls == [QUrl(PROJECT_URL).toString(), QUrl(DONATION_URL).toString()]


def test_about_and_help_dialogs_follow_arabic_direction(
    qapp: QApplication,
) -> None:
    about = AboutDialog("ar", Theme.LIGHT)
    help_dialog = QuickHelpDialog("ar")

    assert about.layoutDirection() is Qt.LayoutDirection.RightToLeft
    assert help_dialog.layoutDirection() is Qt.LayoutDirection.RightToLeft


def test_quick_help_contains_local_guide_and_real_shortcuts(
    qapp: QApplication,
) -> None:
    dialog = QuickHelpDialog("en")

    assert dialog.title_label.text()
    assert len(dialog.guide_labels) == 3
    assert all(label.text() for label in dialog.guide_labels)
    assert len(dialog.shortcut_rows) == 5
    assert all(action.text() for action, _sequence in dialog.shortcut_rows)
    assert all(sequence.text() for _action, sequence in dialog.shortcut_rows)

    dialog.close_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted
