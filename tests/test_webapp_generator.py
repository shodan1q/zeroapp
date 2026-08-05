"""Tests for web asset validation and parsing in the WebView generator."""

from __future__ import annotations

import pytest

from zerodev.generator.webapp_generator import (
    ASSET_FILES,
    WebAppGenerationError,
    WebAppSpec,
    _parse_json_object,
    strip_code_fence,
    validate_assets,
    validate_file,
)

GOOD_HTML = (
    '<!doctype html><html lang="zh-CN"><head>'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
    '<link rel="stylesheet" href="styles.css"></head>'
    '<body><main id="list"></main><script src="data.js"></script><script src="app.js"></script></body></html>'
)
GOOD_CSS = ":root{--bg:#fff}@media (prefers-color-scheme: dark){:root{--bg:#000}}body{padding:env(safe-area-inset-top)}"
GOOD_DATA = "window.APP_DATA = { items: [] };"
GOOD_APP = "(function(){ var d = window.APP_DATA; document.getElementById('list'); })();"


def _assets(**overrides) -> dict[str, str]:
    base = {
        "index.html": GOOD_HTML,
        "styles.css": GOOD_CSS,
        "data.js": GOOD_DATA,
        "app.js": GOOD_APP,
    }
    base.update(overrides)
    return base


# ── Offline constraint ──────────────────────────────────────────


@pytest.mark.parametrize(
    "content",
    [
        '<script src="https://cdn.example.com/x.js"></script>',
        '<script src="//cdn.example.com/x.js"></script>',
        '<link rel="stylesheet" href="https://fonts.example.com/c.css">',
        '<img src="http://img.example.com/a.png">',
    ],
)
def test_remote_resources_rejected_in_html(content: str) -> None:
    problems = validate_file("index.html", GOOD_HTML + content)
    assert any("remote resource" in p for p in problems)


@pytest.mark.parametrize(
    "content",
    [
        "@import url(https://fonts.example.com/c.css);",
        'body{background:url("//img.example.com/a.png")}',
    ],
)
def test_remote_resources_rejected_in_css(content: str) -> None:
    problems = validate_file("styles.css", GOOD_CSS + content)
    assert any("remote resource" in p for p in problems)


def test_remote_anchor_href_allowed() -> None:
    # A remote <a href> is a dead link, not a blank screen -- it must not block
    # generation, or the repair loop would fight every legitimate outbound link.
    assert validate_file("index.html", GOOD_HTML + '<a href="https://example.com">x</a>') == []


def test_local_relative_paths_allowed() -> None:
    assert validate_file("index.html", GOOD_HTML) == []


# ── Project conventions ─────────────────────────────────────────


@pytest.mark.parametrize("emoji", ["🎉", "🚀", "📚", "⚽", "✅", "❗", "🇨🇳", "❤️"])
def test_emoji_rejected(emoji: str) -> None:
    problems = validate_file("data.js", GOOD_DATA + f'\nvar label = "完成 {emoji}";')
    assert any("emoji" in p for p in problems)


@pytest.mark.parametrize(
    "symbol",
    ["→", "←", "⇒", "✓", "✔", "★", "∑", "∫", "≈", "≤", "∞", "▲", "·", "—"],
)
def test_typographic_symbols_allowed(symbol: str) -> None:
    # These live in the same Unicode blocks as emoji but have default *text*
    # presentation. Rejecting them would make a limit like "x → 0" unwritable,
    # which broke a real generation run.
    assert validate_file("data.js", GOOD_DATA + f'\nvar label = "{symbol}";') == []


def test_math_notation_survives_validation() -> None:
    content = 'window.APP_DATA = { limit: "当 x → 0 时 sin x / x → 1", bound: "∑ ≤ ∫ ≈ ∞" };'
    assert validate_file("data.js", content) == []


def test_es_modules_rejected() -> None:
    problems = validate_file("app.js", "import x from './y.js';\n" + GOOD_APP)
    assert any("import/export" in p for p in problems)


def test_remote_fetch_rejected() -> None:
    problems = validate_file("app.js", GOOD_APP + '\nfetch("https://api.example.com/x");')
    assert any("fetch" in p for p in problems)


def test_data_js_must_define_global() -> None:
    problems = validate_file("data.js", "const data = {};")
    assert any("window.APP_DATA" in p for p in problems)


def test_html_must_reference_every_asset() -> None:
    stripped = GOOD_HTML.replace('<script src="app.js"></script>', "")
    problems = validate_file("index.html", stripped)
    assert any("app.js" in p for p in problems)


def test_html_requires_viewport_fit_cover() -> None:
    problems = validate_file("index.html", GOOD_HTML.replace(", viewport-fit=cover", ""))
    assert any("viewport-fit=cover" in p for p in problems)


def test_css_requires_dark_mode_and_safe_area() -> None:
    problems = validate_file("styles.css", "body{margin:0}")
    assert any("dark-mode" in p for p in problems)
    assert any("safe-area-inset" in p for p in problems)


def test_empty_file_rejected() -> None:
    assert validate_file("app.js", "   ") == ["app.js is empty."]


# ── Cross-file checks ───────────────────────────────────────────


def test_valid_asset_set_passes() -> None:
    assert validate_assets(_assets()) == []


def test_missing_file_reported() -> None:
    incomplete = _assets()
    del incomplete["app.js"]
    assert any("app.js" in p for p in validate_assets(incomplete))


def test_dangling_element_id_reported() -> None:
    # The most common cause of a blank screen inside the packaged app.
    broken = _assets(app_js=None)
    broken["app.js"] = "(function(){ window.APP_DATA; document.getElementById('does-not-exist'); })();"
    problems = validate_assets(broken)
    assert any("does-not-exist" in p for p in problems)


def test_asset_files_order_puts_data_before_app() -> None:
    # app.js is generated last so it can see the real data shape.
    assert ASSET_FILES.index("data.js") < ASSET_FILES.index("app.js")


# ── Parsing ─────────────────────────────────────────────────────


def test_strip_code_fence_removes_wrapper() -> None:
    assert strip_code_fence("```css\nbody{}\n```").strip() == "body{}"


def test_strip_code_fence_leaves_plain_content() -> None:
    assert strip_code_fence("body{}").strip() == "body{}"


def test_parse_json_object_tolerates_surrounding_prose() -> None:
    assert _parse_json_object('Here you go:\n{"a": 1}\nHope that helps!') == {"a": 1}


def test_parse_json_object_raises_on_garbage() -> None:
    with pytest.raises(WebAppGenerationError):
        _parse_json_object("no json at all")


# ── Spec adaptation ─────────────────────────────────────────────


def test_spec_from_prd_flattens_pages() -> None:
    class _Page:
        def __init__(self, name: str, purpose: str) -> None:
            self.name = name
            self.purpose = purpose

    class _PRD:
        app_name = "Focus"
        description = "A timer"
        features = ["timer"]
        ui_guidelines = "calm"
        pages = [_Page("Home", "start a session")]

    spec = WebAppSpec.from_prd(_PRD())
    assert spec.app_name == "Focus"
    assert spec.pages == ["Home: start a session"]
    assert spec.design_notes == "calm"
