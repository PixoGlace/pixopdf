import json
import re
import tomllib
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
DOCS_ROOT = ROOT / "docs"
INDEX = DOCS_ROOT / "index.html"
STYLESHEET = DOCS_ROOT / "static" / "style.css"
APP_SCRIPT = DOCS_ROOT / "static" / "app.js"
TRANSLATIONS = DOCS_ROOT / "static" / "translations.json"

PROJECT_URL = "https://github.com/PixoGlace/pixopdf"
KOFI_URL = "https://ko-fi.com/pixoglace"
HOSTING_PROJECT_ID = "appgprj_6a63e88b539081919dfb8a1070ccfbae"
LOCALES = {"fr", "en", "zh", "ar"}
ASSET_LINK_RELATIONS = {"icon", "manifest", "preload", "stylesheet"}
FORBIDDEN_WEB_SOURCE_SUFFIXES = {".cjs", ".jsx", ".mjs", ".ts", ".tsx"}
CSS_URL_PATTERN = re.compile(r"url\(\s*([\"']?)(?P<url>[^)\"']+)\1\s*\)")


class _SiteHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.html_attributes: dict[str, str] = {}
        self.hrefs: list[str] = []
        self.asset_references: list[str] = []
        self.script_sources: list[str] = []
        self.inline_script_count = 0
        self.event_handlers: list[str] = []
        self.translation_keys: list[str] = []
        self.download_platforms: set[str] = set()

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = {name: value or "" for name, value in attrs}

        if tag == "html":
            self.html_attributes = attributes
        if tag == "script":
            source = attributes.get("src")
            if source:
                self.script_sources.append(source)
                self.asset_references.append(source)
            else:
                self.inline_script_count += 1

            dictionary = attributes.get("data-i18n-src")
            if dictionary:
                self.asset_references.append(dictionary)

        self.event_handlers.extend(name for name in attributes if name.lower().startswith("on"))

        translation_key = attributes.get("data-i18n")
        if translation_key:
            self.translation_keys.append(translation_key)

        platform = attributes.get("data-download-platform")
        if platform:
            self.download_platforms.add(platform)

        href = attributes.get("href")
        if href:
            self.hrefs.append(href)
            relations = set(attributes.get("rel", "").lower().split())
            if tag == "link" and relations & ASSET_LINK_RELATIONS:
                self.asset_references.append(href)

        source = attributes.get("src")
        if source and tag != "script":
            self.asset_references.append(source)


def _parse_page() -> tuple[str, _SiteHTMLParser]:
    markup = INDEX.read_text(encoding="utf-8")
    parser = _SiteHTMLParser()
    parser.feed(markup)
    return markup, parser


def _assert_local_asset_exists(reference: str) -> None:
    parsed = urlsplit(reference)
    assert not parsed.scheme and not parsed.netloc, f"index.html loads a remote asset: {reference}"

    asset_path = (INDEX.parent / unquote(parsed.path)).resolve()
    assert asset_path.is_relative_to(DOCS_ROOT.resolve()), (
        f"index.html references an asset outside docs/: {reference}"
    )
    assert asset_path.is_file(), f"index.html references a missing asset: {reference}"


def _leaf_paths(value: object, prefix: str = "") -> set[str]:
    if isinstance(value, dict):
        paths: set[str] = set()
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else key
            paths |= _leaf_paths(child, child_prefix)
        return paths
    if isinstance(value, list):
        paths = set()
        for index, child in enumerate(value):
            child_prefix = f"{prefix}[{index}]"
            paths |= _leaf_paths(child, child_prefix)
        return paths
    return {prefix}


def test_docs_site_is_one_progressively_enhanced_html_page() -> None:
    assert INDEX.is_file()
    assert {path.resolve() for path in DOCS_ROOT.rglob("index.html")} == {INDEX.resolve()}

    markup, parser = _parse_page()
    assert parser.html_attributes.get("lang") == "fr"
    assert parser.html_attributes.get("dir") == "ltr"
    assert parser.inline_script_count == 0
    assert parser.script_sources == ["static/app.js"]
    assert not parser.event_handlers
    assert "javascript:" not in markup.lower()
    assert PROJECT_URL in parser.hrefs
    assert KOFI_URL in parser.hrefs
    assert "GNU GPL v3" in markup
    assert "GPL-3.0-only" in markup


def test_docs_site_has_complete_four_language_dictionary() -> None:
    translations = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    assert set(translations) == LOCALES

    reference_paths = _leaf_paths(translations["fr"])
    assert len(reference_paths) >= 60
    assert all(_leaf_paths(translations[locale]) == reference_paths for locale in LOCALES)

    _markup, parser = _parse_page()
    assert len(set(parser.translation_keys)) >= 60
    assert set(parser.translation_keys).issubset(reference_paths)


def test_docs_site_uses_only_existing_local_assets() -> None:
    _markup, parser = _parse_page()
    assert parser.asset_references
    assert any(reference.endswith(".css") for reference in parser.asset_references)
    assert any(reference.endswith(".js") for reference in parser.asset_references)
    assert any(
        reference.lower().endswith((".png", ".svg")) for reference in parser.asset_references
    )
    for reference in parser.asset_references:
        _assert_local_asset_exists(reference)

    css = STYLESHEET.read_text(encoding="utf-8")
    assert "@import" not in css.lower()
    for match in CSS_URL_PATTERN.finditer(css):
        parsed = urlsplit(match.group("url").strip())
        assert not parsed.scheme and not parsed.netloc
        asset_path = (STYLESHEET.parent / unquote(parsed.path)).resolve()
        assert asset_path.is_relative_to(DOCS_ROOT.resolve())
        assert asset_path.is_file()


def test_docs_javascript_is_vanilla_and_resolves_direct_release_assets() -> None:
    forbidden_source_files = sorted(
        path.relative_to(DOCS_ROOT)
        for path in DOCS_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in FORBIDDEN_WEB_SOURCE_SUFFIXES
    )
    assert not forbidden_source_files
    assert not any(
        (DOCS_ROOT / filename).exists()
        for filename in ("next.config.js", "next.config.mjs", "next.config.ts", "package.json")
    )
    assert not (DOCS_ROOT / "node_modules").exists()

    source = APP_SCRIPT.read_text(encoding="utf-8")
    assert "api.github.com/repos/PixoGlace/pixopdf/releases/latest" in source
    assert "browser_download_url" in source
    assert "IntersectionObserver" in source
    assert "localStorage" in source
    assert "dataset.downloadVersion" in source
    assert "dataset.releaseVersion =" not in source
    assert not any(runtime in source.lower() for runtime in ("react", "vue", "angular", "_next"))

    _markup, parser = _parse_page()
    assert parser.download_platforms == {"auto", "macos", "windows", "linux"}


def test_docs_site_keeps_gplv3_and_hosting_configuration() -> None:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]
    assert project["license"] == "GPL-3.0-only"

    hosting_path = ROOT / ".openai" / "hosting.json"
    with hosting_path.open(encoding="utf-8") as stream:
        hosting = json.load(stream)
    assert hosting.get("project_id") == HOSTING_PROJECT_ID
