from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_ROOT = ROOT / ".github" / "workflows"
EXPECTED_WORKFLOWS = {
    "build.yml",
    "dev-build.yml",
    "pages.yml",
    "release.yml",
    "tests.yml",
}


def _workflow(name: str) -> str:
    return (WORKFLOW_ROOT / name).read_text(encoding="utf-8")


def test_ci_workflow_set_is_complete_and_specific_to_pixopdf() -> None:
    workflow_names = {path.name for path in WORKFLOW_ROOT.glob("*.yml")}
    assert workflow_names == EXPECTED_WORKFLOWS

    combined = "\n".join(_workflow(name) for name in sorted(EXPECTED_WORKFLOWS))
    lowered = combined.lower()
    for forbidden_reference in (
        "pixocrop",
        "src/pixocrop",
        "release-linux",
        "create_packaging_art.py",
        "inno setup",
        "hidden-import fitz",
        '".[dev,build]"',
        'python-version: "3.10"',
    ):
        assert forbidden_reference not in lowered


def test_reusable_build_uses_poetry_spec_and_real_portable_artifacts() -> None:
    build = _workflow("build.yml")
    assert "workflow_call:" in build
    assert 'PYTHON_VERSION: "3.12"' in build
    assert 'POETRY_VERSION: "2.4.1"' in build
    assert "poetry check --lock" in build
    assert "poetry install --with dev,build" in build
    assert "pyinstaller --clean --noconfirm pixopdf.spec" in build
    assert "actions/checkout@v7" in build
    assert "actions/setup-python@v7" in build
    assert "actions/upload-artifact@v7" in build

    for artifact in (
        "PixoPDF-linux-x86_64.tar.gz",
        "PixoPDF-windows-x86_64.exe",
        "PixoPDF-windows-x86_64.zip",
        "PixoPDF-macos-${{ matrix.arch }}.zip",
    ):
        assert artifact in build

    assert "macos-15-intel" in build
    assert "runner: macos-15" in build
    assert "com.pixoglace.pixopdf" in build


def test_release_is_tag_guarded_and_limits_write_permission_to_publication() -> None:
    release = _workflow("release.yml")
    assert 'tags: ["v*"]' in release
    assert 'test "$GITHUB_REF_NAME" = "v$project_version"' in release
    assert "actions/download-artifact@v8" in release
    assert "SHA256SUMS.txt" in release
    assert "gh release create" in release
    assert release.count("contents: write") == 1
    assert release.index("contents: write") > release.index("publish:")
    assert "permissions:\n  contents: read" in release


def test_ci_and_pages_validate_before_delivery() -> None:
    tests = _workflow("tests.yml")
    pages = _workflow("pages.yml")

    assert "ruff check ." in tests
    assert "ruff format --check ." in tests
    assert "mypy src" in tests
    assert "--cov-fail-under=80" in tests
    assert "windows-2025" in tests
    assert "macos-15" in tests

    assert "pytest tests/unit/test_docs_site.py -q" in pages
    assert "actions/configure-pages@v6" in pages
    assert "actions/upload-pages-artifact@v5" in pages
    assert "actions/deploy-pages@v5" in pages
    assert pages.index("pages: write") > pages.index("deploy:")
