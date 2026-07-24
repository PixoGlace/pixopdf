import runpy
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

metadata = runpy.run_path("src/pixopdf/config.py")
app_name = str(metadata["APP_NAME"])
app_version = str(metadata["VERSION"])

datas, binaries, hiddenimports = collect_all("pypdfium2")
datas.append((str(Path("LICENSE")), "."))
asset_root = Path("assets")
runtime_extensions = {".json", ".md", ".png", ".svg"}
for path in asset_root.rglob("*"):
    relative_path = path.relative_to(asset_root)
    if (
        path.is_file()
        and path.suffix.lower() in runtime_extensions
        and not any(part.startswith(".") for part in relative_path.parts)
    ):
        destination = Path("assets") / relative_path.parent
        datas.append((str(path), str(destination)))
a = Analysis(  # noqa: F821
    ["src/pixopdf/__main__.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
)
pyz = PYZ(a.pure)  # noqa: F821

if sys.platform == "darwin":
    exe = EXE(  # noqa: F821
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=app_name,
        console=False,
    )
    collected = COLLECT(  # noqa: F821
        exe,
        a.binaries,
        a.datas,
        name=app_name,
    )
    app = BUNDLE(  # noqa: F821
        collected,
        name=f"{app_name}.app",
        bundle_identifier="com.pixoglace.pixopdf",
        info_plist={
            "CFBundleName": app_name,
            "CFBundleDisplayName": app_name,
            "CFBundleShortVersionString": app_version,
            "CFBundleVersion": app_version,
            "NSHighResolutionCapable": True,
        },
    )
else:
    exe = EXE(  # noqa: F821
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=app_name,
        console=False,
    )
