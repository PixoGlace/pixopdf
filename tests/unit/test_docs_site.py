import json
import re
import tomllib
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
DOCS_ROOT = ROOT / "docs"

PROJECT_URL = "https://github.com/PixoGlace/pixopdf"
KOFI_URL = "https://ko-fi.com/pixoglace"
HOSTING_PROJECT_ID = "appgprj_6a63e88b539081919dfb8a1070ccfbae"

PAGES = {
    "fr": (DOCS_ROOT / "index.html", "fr", "ltr"),
    "en": (DOCS_ROOT / "en" / "index.html", "en", "ltr"),
    "zh": (DOCS_ROOT / "zh" / "index.html", "zh-CN", "ltr"),
    "ar": (DOCS_ROOT / "ar" / "index.html", "ar", "rtl"),
}
ASSET_LINK_RELATIONS = {"icon", "manifest", "preload", "stylesheet"}
WEB_SOURCE_SUFFIXES = {".cjs", ".js", ".jsx", ".mjs", ".ts", ".tsx"}
CSS_URL_PATTERN = re.compile(r"url\\(\\s*([\"']?)(?P<url>[^)\"']+)\\1\\s*\\)")


class _SiteHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.html_attributes: dict[str, str] = {}
        self.hrefs: list[str] = []
        self.asset_references: list[str] = []
        self.script_count = 0
        self.event_handlers: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = {name: value or "" for name, value in attrs}

        if tag == "html":
            self.html_attributes = attributes
        if tag == "script":
            self.script_count += 1

        self.event_handlers.extend(name for name in attributes if name.lower().startswith("on"))

        href = attributes.get("href")
        if href:
            self.hrefs.append(href)
            relations = set(attributes.get("rel", "").lower().split())
            if tag == "link" and relations & ASSET_LINK_RELATIONS:
                self.asset_references.append(href)

        source = attributes.get("src")
        if source:
            self.asset_references.append(source)


def _parse_page(page: Path) -> tuple[str, _SiteHTMLParser]:
    markup = page.read_text(encoding="utf-8")
    parser = _SiteHTMLParser()
    parser.feed(markup)
    return markup, parser


def _assert_local_asset_exists(page: Path, reference: str) -> None:
    parsed = urlsplit(reference)
    assert not parsed.scheme and not parsed.netloc, (
        f"{page.relative_to(ROOT)} loads a remote asset: {reference}"
    )

    asset_path = (page.parent / unquote(parsed.path)).resolve()
    assert asset_path.is_relative_to(DOCS_ROOT.resolve()), (
        f"{page.relative_to(ROOT)} references an asset outside docs/: {reference}"
    )
    assert asset_path.is_file(), f"{page.relative_to(ROOT)} references a missing asset: {reference}"


def test_docs_site_has_exactly_four_static_locales() -> None:
    expected_pages = {page.resolve() for page, _language, _direction in PAGES.values()}
    actual_pages = {page.resolve() for page in DOCS_ROOT.rglob("index.html")}

    assert actual_pages == expected_pages
    assert set(PAGES) == {"fr", "en", "zh", "ar"}


def test_docs_pages_have_language_direction_links_and_gpl() -> None:
    for locale, (page, language, direction) in PAGES.items():
        markup, parser = _parse_page(page)

        assert parser.html_attributes.get("lang") == language, locale
        assert parser.html_attributes.get("dir") == direction, locale
        assert PROJECT_URL in parser.hrefs, locale
        assert KOFI_URL in parser.hrefs, locale
        assert "GNU GPL v3" in markup, locale
        assert "GPL-3.0-only" in markup, locale


def test_docs_pages_use_only_existing_local_assets() -> None:
    for locale, (page, _language, _direction) in PAGES.items():
        _markup, parser = _parse_page(page)

        assert parser.asset_references, locale
        assert any(reference.endswith(".css") for reference in parser.asset_references), locale
        assert any(
            reference.lower().endswith((".png", ".svg")) for reference in parser.asset_references
        ), locale
        for reference in parser.asset_references:
            _assert_local_asset_exists(page, reference)

    stylesheet = DOCS_ROOT / "static" / "style.css"
    css = stylesheet.read_text(encoding="utf-8")
    assert "@import" not in css.lower()
    for match in CSS_URL_PATTERN.finditer(css):
        _assert_local_asset_exists(stylesheet, match.group("url").strip())


def test_docs_site_contains_no_javascript_next_or_npm_runtime() -> None:
    forbidden_source_files = sorted(
        path.relative_to(DOCS_ROOT)
        for path in DOCS_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in WEB_SOURCE_SUFFIXES
    )
    assert not forbidden_source_files

    forbidden_project_files = (
        "next.config.js",
        "next.config.mjs",
        "next.config.ts",
        "package-lock.json",
        "package.json",
    )
    assert not any((DOCS_ROOT / filename).exists() for filename in forbidden_project_files)
    assert not (DOCS_ROOT / "node_modules").exists()

    for locale, (page, _language, _direction) in PAGES.items():
        markup, parser = _parse_page(page)
        lowered = markup.lower()

        assert parser.script_count == 0, locale
        assert not parser.event_handlers, locale
        assert "javascript:" not in lowered, locale
        assert ".js" not in lowered, locale
        assert "_next" not in lowered, locale
        assert "node_modules" not in lowered, locale
        assert "next.js" not in lowered, locale
        assert "npm" not in lowered, locale


def test_docs_site_keeps_gplv3_and_hosting_configuration() -> None:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]
    assert project["license"] == "GPL-3.0-only"

    hosting_path = ROOT / ".openai" / "hosting.json"
    with hosting_path.open(encoding="utf-8") as stream:
        hosting = json.load(stream)
    assert hosting.get("project_id") == HOSTING_PROJECT_ID
