"""Regenerate the product screenshots used by the documentation website."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from pixopdf.config import APP_NAME, ORGANIZATION
from pixopdf.domain.page import PageChange, PageReference
from pixopdf.domain.project import PdfProject
from pixopdf.pdf.pikepdf_backend import PikePdfBackend
from pixopdf.services.project_service import ProjectService
from pixopdf.ui.main_window import MainWindow
from pixopdf.ui.themes.theme_manager import Theme
from pixopdf.ui.tool_modes import WorkspaceMode

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "static" / "assets"


def _demo_project() -> PdfProject:
    pages = [replace(PageReference.blank(), changes=PageChange.NONE) for _ in range(9)]
    pages[1] = replace(pages[1], changes=PageChange.MOVED)
    pages[3] = replace(pages[3].rotated(90), changes=PageChange.MODIFIED)
    pages[5] = replace(pages[5], changes=PageChange.DELETED)
    pages[7] = replace(pages[7], changes=PageChange.ADDED)
    return PdfProject(pages=pages)


def _capture_workspace(app: QApplication, theme: Theme, destination: Path) -> None:
    settings = QSettings(ORGANIZATION, APP_NAME)
    settings.clear()
    settings.setValue("appearance/theme", theme.value)
    settings.setValue("language", "fr")
    settings.sync()

    window = MainWindow(ProjectService(PikePdfBackend()))
    window.resize(1440, 900)
    window.project = _demo_project()
    window.activate_mode(WorkspaceMode.ORGANIZE)
    window.refresh()
    window.workspace.show_workspace()
    window.workspace.pages.setCurrentRow(1)
    window.show()
    for _ in range(4):
        app.processEvents()

    if not window.grab().save(str(destination), "PNG"):
        raise RuntimeError(f"Could not write documentation screenshot: {destination}")
    window.commands.mark_clean()
    window.close()
    app.processEvents()


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        Path("/System/Library/Fonts/SFNS.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")
        if bold
        else Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
        if bold
        else Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def _build_social_card(screenshot_path: Path, destination: Path) -> None:
    width, height = 1200, 630
    canvas = Image.new("RGB", (width, height), "#0F172A")
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((720, -220, 1290, 350), fill=(20, 184, 166, 80))
    glow_draw.ellipse((-180, 360, 330, 840), fill=(245, 158, 11, 45))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    canvas.paste(glow, mask=glow)

    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((56, 54, 1144, 576), radius=44, fill="#111827", outline="#334155")

    logo = Image.open(ROOT / "assets" / "logo_dark.png").convert("RGBA")
    logo.thumbnail((72, 86), Image.Resampling.LANCZOS)
    canvas.paste(logo, (102, 98), logo)

    draw.text((102, 205), "PixoPDF", fill="#F8FAFC", font=_font(64, bold=True))
    draw.text((102, 292), "Your PDFs.", fill="#CBD5E1", font=_font(30))
    draw.text((102, 334), "Your machine.", fill="#14B8A6", font=_font(42, bold=True))
    draw.text(
        (102, 420),
        "ORGANIZE  •  MERGE  •  SPLIT",
        fill="#F59E0B",
        font=_font(18, bold=True),
    )
    draw.text((102, 472), "Open source · Local-first · GPL v3", fill="#94A3B8", font=_font(18))

    screenshot = Image.open(screenshot_path).convert("RGB")
    screenshot.thumbnail((670, 430), Image.Resampling.LANCZOS)
    shot_x, shot_y = 508, 118
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(
        (shot_x + 12, shot_y + 18, shot_x + screenshot.width + 12, shot_y + screenshot.height + 18),
        radius=22,
        fill=(0, 0, 0, 115),
    )
    blurred_shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    canvas.paste(blurred_shadow, mask=blurred_shadow)

    mask = Image.new("L", screenshot.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, screenshot.width, screenshot.height),
        radius=18,
        fill=255,
    )
    canvas.paste(screenshot, (shot_x, shot_y), mask)
    draw.rounded_rectangle(
        (shot_x, shot_y, shot_x + screenshot.width, shot_y + screenshot.height),
        radius=18,
        outline="#475569",
        width=2,
    )
    canvas.save(destination, "PNG", optimize=True)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="pixopdf-docs-settings-") as settings_dir:
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            settings_dir,
        )
        app = QApplication.instance() or QApplication([])
        dark_path = OUTPUT / "pixopdf-workspace-dark.png"
        _capture_workspace(app, Theme.DARK, dark_path)
        _capture_workspace(app, Theme.LIGHT, OUTPUT / "pixopdf-workspace-light.png")
        _build_social_card(dark_path, OUTPUT / "pixopdf-og.png")


if __name__ == "__main__":
    main()
