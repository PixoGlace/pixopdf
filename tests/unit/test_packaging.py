from pathlib import Path
from xml.etree import ElementTree

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]


def test_generated_installer_branding_assets_are_valid() -> None:
    png = ROOT / "assets" / "PixoPDF.png"
    ico = ROOT / "assets" / "PixoPDF.ico"
    icns = ROOT / "assets" / "PixoPDF.icns"
    dmg = ROOT / "assets" / "dmg" / "pixopdf-dmg-background.png"

    assert png.stat().st_size > 1_000
    assert ico.stat().st_size > 1_000
    assert icns.stat().st_size > 1_000
    assert dmg.stat().st_size > 1_000
    with Image.open(png) as icon:
        assert icon.size == (1024, 1024)
    with Image.open(dmg) as background:
        assert background.size == (660, 420)


def test_native_installer_metadata_is_specific_to_pixopdf() -> None:
    installer = (ROOT / "packaging" / "windows" / "PixoPDF.iss").read_text(encoding="utf-8")
    assert "PixoPDF-windows-x86_64-setup" in installer
    assert "https://github.com/PixoGlace/pixopdf" in installer
    assert "GPL" not in installer  # The canonical license is injected from LICENSE.
    assert "LicenseFile={#RootDir}\\LICENSE" in installer
    assert "pixoCrop" not in installer

    metadata = ElementTree.parse(
        ROOT / "packaging" / "linux" / "io.github.pixoglace.pixopdf.metainfo.xml"
    ).getroot()
    assert metadata.findtext("id") == "io.github.pixoglace.pixopdf"
    assert metadata.findtext("project_license") == "GPL-3.0-only"
    assert metadata.findtext("name") == "PixoPDF"


def test_pyinstaller_spec_uses_native_icons_and_windows_onedir_bundle() -> None:
    specification = (ROOT / "pixopdf.spec").read_text(encoding="utf-8")
    assert 'icon="assets/PixoPDF.icns"' in specification
    assert 'icon="assets/PixoPDF.ico"' in specification
    assert 'icon="assets/PixoPDF.png"' in specification
    assert 'elif sys.platform == "win32":' in specification
    assert specification.count("COLLECT(") == 2
