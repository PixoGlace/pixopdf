import tomllib
from pathlib import Path

from pixopdf import __version__
from pixopdf.config import (
    APP_NAME,
    DONATION_TEXT,
    DONATION_URL,
    KOFI_URL,
    ORGANIZATION,
    PROJECT_LICENSE,
    PROJECT_URL,
    UPDATE_CHECK_URL,
    VERSION,
)
from pixopdf.constants import APP_NAME as CONSTANT_APP_NAME
from pixopdf.constants import ORGANIZATION as CONSTANT_ORGANIZATION


def test_application_metadata_matches_project_configuration() -> None:
    project_file = Path(__file__).parents[2] / "pyproject.toml"
    with project_file.open("rb") as stream:
        project = tomllib.load(stream)["project"]

    assert APP_NAME == "PixoPDF"
    assert ORGANIZATION == "PixoGlace"
    assert VERSION == project["version"] == __version__
    assert PROJECT_LICENSE == "GNU GPL v3"


def test_public_links_target_the_pixopdf_project() -> None:
    assert PROJECT_URL == "https://github.com/PixoGlace/pixopdf"
    assert UPDATE_CHECK_URL == (
        "https://api.github.com/repos/PixoGlace/pixopdf/releases/latest"
    )
    assert DONATION_URL == KOFI_URL == "https://ko-fi.com/pixoglace"
    assert "PixoPDF" in DONATION_TEXT


def test_legacy_constants_reexport_central_metadata() -> None:
    assert CONSTANT_APP_NAME == APP_NAME
    assert CONSTANT_ORGANIZATION == ORGANIZATION
