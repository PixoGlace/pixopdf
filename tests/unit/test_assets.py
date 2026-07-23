from pathlib import Path

import pytest

from pixopdf.assets import asset_path


@pytest.mark.parametrize(
    "name",
    [
        "logo_dark.png",
        "logo_white.png",
        "pixopdf-logo-dark.svg",
        "pixopdf-logo-light.svg",
    ],
)
def test_asset_path_finds_branding_logos(
    name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    resolved = asset_path(name)

    assert resolved.is_file()
    assert resolved.name == name
    assert resolved.stat().st_size > 0
