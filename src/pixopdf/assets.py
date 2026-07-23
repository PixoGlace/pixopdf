import sys
from pathlib import Path


def asset_path(name: str) -> Path:
    """Resolve an asset in editable, wheel and PyInstaller installations."""
    candidates: list[Path] = []
    bundle_root = getattr(sys, "_MEIPASS", None)
    if isinstance(bundle_root, str):
        candidates.append(Path(bundle_root) / "assets" / name)
    module_path = Path(__file__).resolve()
    candidates.extend(
        (
            module_path.parents[1] / "assets" / name,
            module_path.parents[2] / "assets" / name,
            Path.cwd() / "assets" / name,
        )
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[-1]
