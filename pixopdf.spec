from pathlib import Path

from PyInstaller.utils.hooks import collect_all

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
exe = EXE(  # noqa: F821
    pyz, a.scripts, a.binaries, a.datas, [], name="PixoPDF", console=False
)
