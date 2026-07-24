from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtCore import QRunnable, QSettings, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import QApplication, QDialog, QMenuBar

from pixopdf.config import KOFI_URL, PROJECT_URL, VERSION
from pixopdf.domain.project import PdfProject
from pixopdf.pdf.backend import PdfBackend
from pixopdf.services.project_service import ProjectService
from pixopdf.services.update_service import UpdateResult, UpdateStatus
from pixopdf.ui import main_window as main_window_module
from pixopdf.ui.main_window import MainWindow
from pixopdf.ui.themes.theme_manager import Theme
from pixopdf.ui.tool_modes import MODE_SPECS, ModeStatus, WorkspaceMode


class EmptyBackend(PdfBackend):
    def page_count(self, path: Path) -> int:
        return 0

    def export(self, project: PdfProject, destination: Path) -> None:
        destination.write_bytes(b"")


class FakeUpdateService:
    def __init__(
        self,
        operation: Callable[[str], UpdateResult] | None = None,
    ) -> None:
        self._operation = operation or (
            lambda current: UpdateResult(
                status=UpdateStatus.CURRENT,
                current_version=current,
                latest_version=current,
                release_url=PROJECT_URL,
                release_notes="",
            )
        )
        self.checked_versions: list[str] = []

    def check(self, current_version: str) -> UpdateResult:
        self.checked_versions.append(current_version)
        return self._operation(current_version)


class CapturingThreadPool:
    def __init__(self) -> None:
        self.tasks: list[QRunnable] = []

    def start(self, task: QRunnable) -> None:
        self.tasks.append(task)


def _configure_settings(tmp_path: Path, **values: object) -> QSettings:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        str(tmp_path),
    )
    settings = QSettings("PixoGlace", "PixoPDF")
    settings.clear()
    for key, value in values.items():
        settings.setValue(key.replace("__", "/"), value)
    settings.sync()
    return settings


def _window(
    tmp_path: Path,
    *,
    update_service: FakeUpdateService | None = None,
) -> MainWindow:
    _configure_settings(tmp_path)
    return MainWindow(
        ProjectService(EmptyBackend()),
        update_service=update_service,
    )


def _close_clean(window: MainWindow, qapp: QApplication) -> None:
    window.commands.mark_clean()
    window.refresh()
    window.close()
    qapp.setLayoutDirection(Qt.LayoutDirection.LeftToRight)


def _non_separator_actions(menu_actions: list[QAction]) -> list[QAction]:
    return [action for action in menu_actions if not action.isSeparator()]


def test_main_menu_has_expected_sections_actions_and_unique_shortcuts(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    window = _window(tmp_path)
    try:
        assert window.menuBar().actions() == [
            window.file_menu.menuAction(),
            window.edit_menu.menuAction(),
            window.view_menu.menuAction(),
            window.tools_menu.menuAction(),
            window.help_menu.menuAction(),
        ]
        assert all(
            menu.title()
            for menu in (
                window.file_menu,
                window.edit_menu,
                window.view_menu,
                window.tools_menu,
                window.help_menu,
            )
        )

        file_actions = _non_separator_actions(window.file_menu.actions())
        edit_actions = _non_separator_actions(window.edit_menu.actions())
        view_actions = _non_separator_actions(window.view_menu.actions())
        tools_actions = _non_separator_actions(window.tools_menu.actions())
        help_actions = _non_separator_actions(window.help_menu.actions())
        all_menu_actions = [
            *file_actions,
            *edit_actions,
            *view_actions,
            *tools_actions,
            *help_actions,
        ]

        assert window.new_workspace_action in file_actions
        assert window.open_action in file_actions
        assert window.export_action in file_actions
        assert window.quit_action in file_actions
        assert window.undo_action in edit_actions
        assert window.redo_action in edit_actions
        assert window.blank_page_action in edit_actions
        assert window.delete_selection_action in edit_actions
        assert window.toggle_theme_action in view_actions
        assert window.settings_action in tools_actions
        assert set(window.tool_mode_actions.values()).issubset(set(tools_actions))
        assert window.quick_help_action in help_actions
        assert window.project_action in help_actions
        assert window.sponsor_action in help_actions
        assert window.check_updates_action in help_actions
        assert window.about_action in help_actions
        assert len(all_menu_actions) == len(set(all_menu_actions))

        shortcuts = [
            action.shortcut().toString(QKeySequence.SequenceFormat.PortableText)
            for action in [
                *window.shortcut_actions,
                window.settings_action,
            ]
            if not action.shortcut().isEmpty()
        ]
        assert len(shortcuts) == len(set(shortcuts))
        preference_shortcuts = QKeySequence.keyBindings(QKeySequence.StandardKey.Preferences)
        expected_preferences = (
            preference_shortcuts[0] if preference_shortcuts else QKeySequence("Ctrl+,")
        )
        assert window.settings_action.shortcut() == expected_preferences
    finally:
        _close_clean(window, qapp)


@pytest.mark.parametrize(
    ("platform", "native_menu", "native_roles"),
    [
        ("darwin", True, True),
        ("win32", False, False),
        ("linux", False, False),
    ],
)
def test_menu_uses_platform_native_conventions(
    platform: str,
    native_menu: bool,
    native_roles: bool,
    tmp_path: Path,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_window_module.sys, "platform", platform)
    native_requests: list[bool] = []
    original_set_native = QMenuBar.setNativeMenuBar

    def record_native_request(menu_bar: QMenuBar, native: bool) -> None:
        native_requests.append(native)
        original_set_native(menu_bar, native)

    monkeypatch.setattr(QMenuBar, "setNativeMenuBar", record_native_request)
    window = _window(tmp_path)
    try:
        assert native_requests[-1] is native_menu
        if qapp.platformName() != "offscreen":
            assert window.menuBar().isNativeMenuBar() is native_menu
        assert window._is_macos is native_menu
        assert all(
            action.text()
            for action in (
                window.settings_action,
                window.about_action,
                window.quit_action,
            )
        )

        if native_roles:
            assert window.settings_action.menuRole() is QAction.MenuRole.PreferencesRole
            assert window.about_action.menuRole() is QAction.MenuRole.AboutRole
            assert window.quit_action.menuRole() is QAction.MenuRole.QuitRole
        else:
            assert window.settings_action.menuRole() is QAction.MenuRole.ApplicationSpecificRole
            assert window.about_action.menuRole() is QAction.MenuRole.ApplicationSpecificRole
            assert window.quit_action.menuRole() is QAction.MenuRole.ApplicationSpecificRole
            assert window.settings_action in window.tools_menu.actions()
            assert window.about_action in window.help_menu.actions()
            assert window.quit_action in window.file_menu.actions()
    finally:
        _close_clean(window, qapp)


def test_future_tool_modes_stay_visible_but_disabled(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    window = _window(tmp_path)
    try:
        for mode, spec in MODE_SPECS.items():
            action = window.tool_mode_actions[mode]
            assert action.isVisible()
            assert bool(action.text())
            if spec.status is ModeStatus.COMING_SOON:
                assert not action.isEnabled()
                assert not action.isChecked()
            else:
                assert action.isEnabled()

        before = window.active_mode
        window.tool_mode_actions[WorkspaceMode.CONVERT].trigger()
        assert window.active_mode is before
    finally:
        _close_clean(window, qapp)


def test_kofi_sponsor_link_is_visible_on_home_and_workspace(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    window = _window(tmp_path)
    window.show()
    qapp.processEvents()
    try:
        sponsor = window.workspace.kofi_label
        assert window.workspace.is_home
        assert sponsor.isVisibleTo(window.workspace)
        assert KOFI_URL in sponsor.text()
        assert window.t("sponsor_kofi") in sponsor.text()

        window.workspace.show_workspace()
        qapp.processEvents()

        assert not window.workspace.is_home
        assert sponsor.isVisibleTo(window.workspace)
        assert KOFI_URL in sponsor.text()
    finally:
        _close_clean(window, qapp)


def test_menu_translation_and_arabic_direction_are_applied_immediately(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    window = _window(tmp_path)
    try:
        window.set_language("en")
        assert window.file_menu.title() == window.t("menu_file")
        assert window.settings_action.text() == window.t("menu_settings")
        assert window.sponsor_action.text() == window.t("sponsor_kofi")
        assert window.workspace.kofi_label.accessibleName() == window.t("sponsor_kofi")
        assert window.layoutDirection() is Qt.LayoutDirection.LeftToRight

        window.set_language("ar")

        assert qapp.layoutDirection() is Qt.LayoutDirection.RightToLeft
        assert window.layoutDirection() is Qt.LayoutDirection.RightToLeft
        assert window.menuBar().layoutDirection() is Qt.LayoutDirection.RightToLeft
        assert window.file_menu.title() == window.t("menu_file")
        assert window.about_action.text() == window.t("about_title", app="PixoPDF")
        assert window.workspace.pages.layoutDirection() is Qt.LayoutDirection.LeftToRight
        assert window.workspace.kofi_label.accessibleName() == window.t("sponsor_kofi")
    finally:
        window.set_language("fr")
        _close_clean(window, qapp)


def test_project_and_sponsor_menu_actions_open_official_links(
    tmp_path: Path,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened_urls: list[str] = []
    monkeypatch.setattr(
        QDesktopServices,
        "openUrl",
        lambda url: opened_urls.append(url.toString()) or True,
    )
    window = _window(tmp_path)
    try:
        window.project_action.trigger()
        window.sponsor_action.trigger()

        assert opened_urls == [
            QUrl(PROJECT_URL).toString(),
            QUrl(KOFI_URL).toString(),
        ]
    finally:
        _close_clean(window, qapp)


def test_settings_menu_persists_language_theme_and_automatic_updates(
    tmp_path: Path,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class AcceptedSettingsDialog:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Accepted

        def selected_language(self) -> str:
            return "zh"

        def selected_theme(self) -> Theme:
            return Theme.LIGHT

        def automatic_updates_enabled(self) -> bool:
            return False

    monkeypatch.setattr(
        main_window_module,
        "SettingsDialog",
        AcceptedSettingsDialog,
    )
    window = _window(tmp_path)
    try:
        window.settings_action.trigger()
        window.settings.sync()

        persisted = QSettings("PixoGlace", "PixoPDF")
        assert persisted.value("language") == "zh"
        assert persisted.value("appearance/theme") == Theme.LIGHT.value
        assert persisted.value("updates/automatic", type=bool) is False
        assert window.language == "zh"
        assert window.theme is Theme.LIGHT
        assert not window.automatic_update_checks
    finally:
        _close_clean(window, qapp)


def test_update_check_is_non_blocking_and_rejects_a_second_start(
    tmp_path: Path,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeUpdateService()
    pool = CapturingThreadPool()
    monkeypatch.setattr(
        main_window_module.QThreadPool,
        "globalInstance",
        staticmethod(lambda: pool),
    )
    window = _window(tmp_path, update_service=service)
    shown_results: list[UpdateResult] = []
    monkeypatch.setattr(window, "show_no_update_dialog", shown_results.append)
    try:
        window.start_update_check(manual=True)

        assert len(pool.tasks) == 1
        assert service.checked_versions == []
        assert window._update_task is pool.tasks[0]
        assert not window.check_updates_action.isEnabled()

        window.start_update_check(manual=True)
        assert len(pool.tasks) == 1
        assert service.checked_versions == []

        pool.tasks[0].run()
        qapp.processEvents()

        assert service.checked_versions == [VERSION]
        assert window._update_task is None
        assert window.check_updates_action.isEnabled()
        assert len(shown_results) == 1
        assert shown_results[0].status is UpdateStatus.CURRENT
    finally:
        _close_clean(window, qapp)


def test_current_automatic_update_is_silent_and_records_check_time(
    tmp_path: Path,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeUpdateService()
    pool = CapturingThreadPool()
    monkeypatch.setattr(
        main_window_module.QThreadPool,
        "globalInstance",
        staticmethod(lambda: pool),
    )
    window = _window(tmp_path, update_service=service)
    no_update_dialogs: list[UpdateResult] = []
    monkeypatch.setattr(window, "show_no_update_dialog", no_update_dialogs.append)
    try:
        window.start_update_check(manual=False)
        pool.tasks[0].run()
        qapp.processEvents()

        assert service.checked_versions == [VERSION]
        assert no_update_dialogs == []
        assert int(str(window.settings.value("updates/last_checked", 0))) > 0
    finally:
        _close_clean(window, qapp)


def test_failed_manual_update_is_reported_without_network_access(
    tmp_path: Path,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(_current: str) -> UpdateResult:
        raise RuntimeError("offline")

    service = FakeUpdateService(fail)
    pool = CapturingThreadPool()
    monkeypatch.setattr(
        main_window_module.QThreadPool,
        "globalInstance",
        staticmethod(lambda: pool),
    )
    window = _window(tmp_path, update_service=service)
    failures: list[bool] = []
    monkeypatch.setattr(
        window,
        "show_update_check_failed_dialog",
        lambda: failures.append(True),
    )
    try:
        window.start_update_check(manual=True)
        pool.tasks[0].run()
        qapp.processEvents()

        assert service.checked_versions == [VERSION]
        assert failures == [True]
        assert window._update_task is None
        assert window.check_updates_action.isEnabled()
    finally:
        _close_clean(window, qapp)
