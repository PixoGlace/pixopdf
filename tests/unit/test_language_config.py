import ast
from pathlib import Path

import pytest

from pixopdf.language_config import (
    DEFAULT_LANGUAGE,
    LANGUAGES,
    TRANSLATIONS,
    is_rtl,
    language_name,
    translate,
)


def test_supported_languages_have_native_names_and_direction() -> None:
    assert DEFAULT_LANGUAGE == "fr"
    assert list(LANGUAGES) == ["fr", "en", "zh", "ar"]
    assert language_name("fr") == "Français"
    assert language_name("en") == "English"
    assert language_name("zh") == "中文"
    assert language_name("ar") == "العربية"
    assert not is_rtl("fr")
    assert not is_rtl("en")
    assert not is_rtl("zh")
    assert is_rtl("ar")


def test_every_language_catalogue_has_the_same_complete_key_set() -> None:
    french_keys = set(TRANSLATIONS[DEFAULT_LANGUAGE])

    assert len(french_keys) >= 280
    assert all(set(catalogue) == french_keys for catalogue in TRANSLATIONS.values())


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("fr", "Bienvenue dans PixoPDF"),
        ("en", "Welcome to PixoPDF"),
        ("zh", "欢迎使用 PixoPDF"),
        ("ar", "مرحباً بك في PixoPDF"),
    ],
)
def test_translate_uses_requested_catalogue(language: str, expected: str) -> None:
    assert translate(language, "home_title") == expected


def test_translate_interpolates_named_values() -> None:
    assert translate("fr", "documents_count", count=4) == "Documents (4)"
    assert translate("en", "split_preview_ready", count=3) == (
        "Preview ready • 3 PDF files will be created."
    )
    assert translate("fr", "merge_ready", documents=3, pages=12) == (
        "3 documents • 12 pages actives\n"
        "Prêt à fusionner dans l’ordre affiché."
    )


@pytest.mark.parametrize(
    ("language", "key", "count", "expected"),
    [
        ("fr", "selected_pages_count", 1, "1 page sélectionnée"),
        ("fr", "selected_pages_count", 4, "4 pages sélectionnées"),
        ("en", "pages_count", 1, "1 page"),
        ("en", "pages_count", 4, "4 pages"),
        ("zh", "previews_in_progress", 4, "正在生成 4 个预览"),
        ("ar", "split_preview_ready", 1, "المعاينة جاهزة • سيتم إنشاء ملف PDF واحد."),
    ],
)
def test_translate_selects_natural_count_variant(
    language: str,
    key: str,
    count: int,
    expected: str,
) -> None:
    assert translate(language, key, count=count) == expected


def test_workspace_static_translation_keys_are_present() -> None:
    workspace_file = (
        Path(__file__).parents[2]
        / "src"
        / "pixopdf"
        / "ui"
        / "workspace"
        / "workspace_page.py"
    )
    tree = ast.parse(workspace_file.read_text(encoding="utf-8"))
    referenced_keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        is_count_call = isinstance(node.func, ast.Attribute) and node.func.attr == "tc"
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"t", "tc"}:
            key_index = 0
        elif isinstance(node.func, ast.Name) and node.func.id == "translate":
            key_index = 1
        else:
            continue
        if len(node.args) <= key_index:
            continue
        key_node = node.args[key_index]
        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
            if is_count_call:
                referenced_keys.add(f"{key_node.value}_one")
                referenced_keys.add(f"{key_node.value}_other")
            else:
                referenced_keys.add(key_node.value)

    assert referenced_keys <= set(TRANSLATIONS[DEFAULT_LANGUAGE])


def test_unknown_language_and_key_have_safe_visible_fallbacks() -> None:
    assert translate("unsupported", "home") == "Accueil"
    assert translate("en", "missing.translation.key") == "missing.translation.key"
    assert language_name("unsupported") == "Français"
    assert not is_rtl("unsupported")
