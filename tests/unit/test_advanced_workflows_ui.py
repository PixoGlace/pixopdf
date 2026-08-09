from collections.abc import Callable
from pathlib import Path

import pikepdf
from PIL import Image
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from pixopdf.domain.page import PageReference
from pixopdf.pdf.pikepdf_backend import PikePdfBackend
from pixopdf.services.project_service import ProjectService
from pixopdf.ui.main_window import MainWindow
from pixopdf.ui.tool_modes import WorkspaceMode


def _window(tmp_path: Path) -> MainWindow:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    QSettings("PixoGlace", "PixoPDF").clear()
    window = MainWindow(ProjectService(PikePdfBackend()))
    window.project.pages[:] = [PageReference.blank(), PageReference.blank()]
    window.refresh()
    return window


def _run_synchronously(
    operation: Callable[[], object],
    on_success: Callable[[object], None],
    _error_title: str,
) -> None:
    on_success(operation())


def _close(window: MainWindow) -> None:
    window.commands.mark_clean()
    window.refresh()
    window.close()


def test_layout_protection_date_and_compression_run_from_the_active_panel(
    tmp_path: Path,
    qapp: QApplication,
    monkeypatch,
) -> None:
    window = _window(tmp_path)
    monkeypatch.setattr(window, "_start_operation", _run_synchronously)
    try:
        layout_output = tmp_path / "layout.pdf"
        monkeypatch.setattr(window, "_choose_pdf_destination", lambda *_: layout_output)
        window.activate_mode(WorkspaceMode.LAYOUT)
        window.workspace.layout_nup_radio.click()
        window.workspace.layout_nup_count.setCurrentIndex(1)  # 4 pages per sheet
        window.execute_primary_action()
        with pikepdf.open(layout_output) as laid_out:
            assert len(laid_out.pages) == 1

        protected_output = tmp_path / "protected.pdf"
        monkeypatch.setattr(window, "_choose_pdf_destination", lambda *_: protected_output)
        window.activate_mode(WorkspaceMode.PROTECT)
        window.workspace.protect_user_password.setText("secret")
        window.workspace.protect_confirm_password.setText("secret")
        window.execute_primary_action()
        with pikepdf.open(protected_output, password="secret") as protected:
            assert protected.is_encrypted

        dated_output = tmp_path / "dated.pdf"
        monkeypatch.setattr(window, "_choose_pdf_destination", lambda *_: dated_output)
        window.activate_mode(WorkspaceMode.SIGN)
        window.workspace.sign_date_radio.click()
        window.execute_primary_action()
        with pikepdf.open(dated_output) as dated:
            assert len(dated.pages) == 2

        compressed_output = tmp_path / "compressed.pdf"
        monkeypatch.setattr(window, "_choose_pdf_destination", lambda *_: compressed_output)
        window.activate_mode(WorkspaceMode.COMPRESS)
        window.workspace.compress_advanced_radio.click()
        window.workspace.compress_use_target.setChecked(True)
        window.workspace.compress_target_size.setValue(0.1)
        window.execute_primary_action()
        assert compressed_output.is_file()
        assert compressed_output.stat().st_size <= 100_000
    finally:
        _close(window)


def test_images_to_pdf_runs_without_a_pdf_document(
    tmp_path: Path,
    qapp: QApplication,
    monkeypatch,
) -> None:
    window = _window(tmp_path)
    monkeypatch.setattr(window, "_start_operation", _run_synchronously)
    image_path = tmp_path / "input.png"
    Image.new("RGB", (80, 60), "#14B8A6").save(image_path)
    output = tmp_path / "images.pdf"
    monkeypatch.setattr(window, "_choose_pdf_destination", lambda *_: output)
    try:
        window.activate_mode(WorkspaceMode.CONVERT)
        window.workspace.convert_images_pdf_radio.click()
        window.workspace.set_conversion_images([str(image_path)])
        window.execute_primary_action()
        with pikepdf.open(output) as pdf:
            assert len(pdf.pages) == 1
    finally:
        _close(window)
