"""Tests for web asset validation and parsing in the WebView generator."""

from __future__ import annotations

import asyncio
import json

import pytest

from zerodev.generator.webapp_generator import (
    ASSET_FILES,
    SCRIPT_ORDER,
    WebAppGenerationError,
    WebAppGenerator,
    WebAppSpec,
    _parse_json_array,
    _parse_json_object,
    strip_code_fence,
    validate_assets,
    validate_file,
)

GOOD_HTML = (
    '<!doctype html><html lang="zh-CN"><head>'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
    '<link rel="stylesheet" href="styles.css"></head>'
    '<body><main id="list"></main>'
    '<script src="data.js"></script><script src="core.js"></script>'
    '<script src="charts.js"></script><script src="views.js"></script>'
    '<script src="features.js"></script></body></html>'
)
GOOD_CSS = ":root{--bg:#fff}@media (prefers-color-scheme: dark){:root{--bg:#000}}body{padding:env(safe-area-inset-top)}"
GOOD_DATA = "window.APP_DATA = { items: [] };"
GOOD_CORE = "(function(){ window.APP = { data: window.APP_DATA, views: {}, features: {}, charts: {} }; })();"
GOOD_CHARTS = "(function(){ APP.charts.bar = function(n, s){ return n && s; }; })();"
GOOD_VIEWS = "(function(){ APP.views.home = function(){ document.getElementById('list'); }; })();"
GOOD_FEATURES = "(function(){ APP.features.search = function(){}; APP.boot(); })();"


def _assets(**overrides) -> dict[str, str]:
    base = {
        "index.html": GOOD_HTML,
        "styles.css": GOOD_CSS,
        "data.js": GOOD_DATA,
        "core.js": GOOD_CORE,
        "charts.js": GOOD_CHARTS,
        "views.js": GOOD_VIEWS,
        "features.js": GOOD_FEATURES,
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
    problems = validate_file("views.js", "import x from './y.js';\n" + GOOD_VIEWS)
    assert any("import/export" in p for p in problems)


def test_remote_fetch_rejected() -> None:
    problems = validate_file("features.js", GOOD_FEATURES + '\nfetch("https://api.example.com/x");')
    assert any("fetch" in p for p in problems)


def test_data_js_must_define_global() -> None:
    problems = validate_file("data.js", "const data = {};")
    assert any("window.APP_DATA" in p for p in problems)


def test_html_must_reference_every_asset() -> None:
    stripped = GOOD_HTML.replace('<script src="features.js"></script>', "")
    problems = validate_file("index.html", stripped)
    assert any("features.js" in p for p in problems)


def test_html_requires_viewport_fit_cover() -> None:
    problems = validate_file("index.html", GOOD_HTML.replace(", viewport-fit=cover", ""))
    assert any("viewport-fit=cover" in p for p in problems)


def test_css_requires_dark_mode_and_safe_area() -> None:
    problems = validate_file("styles.css", "body{margin:0}")
    assert any("dark-mode" in p for p in problems)
    assert any("safe-area-inset" in p for p in problems)


def test_empty_file_rejected() -> None:
    assert validate_file("core.js", "   ") == ["core.js is empty."]


# ── Cross-file checks ───────────────────────────────────────────


def test_valid_asset_set_passes() -> None:
    assert validate_assets(_assets()) == []


def test_missing_file_reported() -> None:
    incomplete = _assets()
    del incomplete["features.js"]
    assert any("features.js" in p for p in validate_assets(incomplete))


def test_dangling_element_id_reported() -> None:
    # The most common cause of a blank screen inside the packaged app.
    broken = _assets()
    broken["views.js"] = "(function(){ APP.views.home = function(){ APP.mount('does-not-exist'); }; })();"
    problems = validate_assets(broken)
    assert any("does-not-exist" in p for p in problems)


def test_script_order_respects_dependencies() -> None:
    # Each module builds on the global the previous one installed.
    assert SCRIPT_ORDER == ("data.js", "core.js", "charts.js", "views.js", "features.js")
    assert set(SCRIPT_ORDER) <= set(ASSET_FILES)


def test_html_script_order_is_enforced() -> None:
    swapped = GOOD_HTML.replace(
        '<script src="core.js"></script><script src="charts.js"></script>',
        '<script src="charts.js"></script><script src="core.js"></script>',
    )
    assert any("out of order" in p for p in validate_file("index.html", swapped))


def test_core_must_create_the_namespace() -> None:
    assert any("window.APP" in p for p in validate_file("core.js", "(function(){ var x = 1; })();"))


def test_features_must_boot() -> None:
    problems = validate_file("features.js", "(function(){ APP.features.search = function(){}; })();")
    assert any("APP.boot()" in p for p in problems)


@pytest.mark.parametrize(
    ("module", "member"),
    [("charts.js", "charts"), ("views.js", "views"), ("features.js", "features")],
)
def test_modules_must_attach_to_the_namespace(module: str, member: str) -> None:
    problems = validate_file(module, "(function(){ var local = {}; APP.boot(); })();")
    assert any(f"APP.{member}" in p for p in problems)


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


# ── Concurrency and content assembly ────────────────────────────

CONTRACT = {
    "app_name": "测试应用",
    "tagline": "标语",
    "design": {"css_classes": ["card"]},
    "views": [{"id": "home", "title": "首页", "sections": [{"mount_id": "list", "collection": "items"}]}],
    "collections": [
        {"name": "items", "purpose": "条目", "min_entries": 12, "fields": [{"name": "id", "type": "string"}]},
        {"name": "notes", "purpose": "笔记", "min_entries": 10, "fields": [{"name": "id", "type": "string"}]},
    ],
    "element_ids": ["list"],
}


class _RecordingGenerator(WebAppGenerator):
    """Stubs the transport only, so the real semaphore still governs overlap."""

    def __init__(self, replies: dict[str, str], **kwargs) -> None:
        kwargs.setdefault("verify_runtime", False)
        super().__init__(model="stub", **kwargs)
        self._replies = replies
        self.labels: list[str] = []
        self.max_in_flight = 0
        self._in_flight = 0

    async def _raw_complete(self, prompt: str, *, label: str, max_tokens: int | None = None) -> str:
        self.labels.append(label)
        self._in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            await asyncio.sleep(0.01)  # let siblings start before this one resolves
            for key, reply in self._replies.items():
                if label.startswith(key):
                    return reply
            raise AssertionError(f"no stub reply for {label}")
        finally:
            self._in_flight -= 1


def _replies() -> dict[str, str]:
    return {
        "app-copy": '{"name": "测试应用", "tagline": "标语"}',
        "content:": '[{"id": "a"}, {"id": "b"}]',
        "styles.css": GOOD_CSS,
        "index.html": GOOD_HTML,
        "core.js": GOOD_CORE,
        "charts.js": GOOD_CHARTS,
        "views.js": GOOD_VIEWS,
        "features.js": GOOD_FEATURES,
    }


def test_files_and_content_are_generated_concurrently() -> None:
    gen = _RecordingGenerator(_replies())
    assets = asyncio.run(gen.generate_files(WebAppSpec(app_name="测试应用", description="d"), CONTRACT))

    assert set(assets) == set(ASSET_FILES)
    # 6 code files + app copy + 2 collections must overlap, not run one by one.
    assert gen.max_in_flight > 1
    assert len(gen.labels) == 9


def test_concurrency_is_bounded_by_the_semaphore() -> None:
    gen = _RecordingGenerator(_replies(), concurrency=2)
    asyncio.run(gen.generate_files(WebAppSpec(app_name="测试应用", description="d"), CONTRACT))
    assert gen.max_in_flight <= 2


def test_data_js_is_assembled_not_generated() -> None:
    gen = _RecordingGenerator(_replies())
    assets = asyncio.run(gen.generate_files(WebAppSpec(app_name="测试应用", description="d"), CONTRACT))

    # No worker is asked to write data.js -- it is built from the JSON shards,
    # so it cannot come back with a syntax error.
    assert not any(label.startswith("data.js") for label in gen.labels)
    assert assets["data.js"].startswith("window.APP_DATA = {")
    payload = json.loads(assets["data.js"].split("=", 1)[1].strip().rstrip(";"))
    assert set(payload) == {"app", "items", "notes"}
    assert payload["items"] == [{"id": "a"}, {"id": "b"}]
    assert validate_file("data.js", assets["data.js"]) == []


def test_plan_without_collections_is_rejected() -> None:
    gen = _RecordingGenerator({"plan": json.dumps({"views": [{"id": "a"}]})})
    with pytest.raises(WebAppGenerationError, match="collections"):
        asyncio.run(gen.plan(WebAppSpec(app_name="A", description="d")))


def test_content_shard_array_parsed() -> None:
    assert _parse_json_array('前言\n[{"id": "x"}]\n结尾') == [{"id": "x"}]


def test_content_shard_object_wrapper_unwrapped() -> None:
    # Models sometimes wrap the array; unwrapping beats failing the whole app.
    assert _parse_json_array('{"records": [{"id": "x"}]}') == [{"id": "x"}]


def test_content_shard_garbage_raises() -> None:
    with pytest.raises(WebAppGenerationError):
        _parse_json_array("I cannot do that")


# ── Provider protection ─────────────────────────────────────────


def test_llm_gate_is_global_not_per_generator() -> None:
    # Three apps each fanning out six calls put twenty requests on one relay,
    # which answered with empty streams until the whole batch collapsed. The
    # cap has to span generator instances, not live inside one.
    from zerodev.generator import webapp_generator as wg

    peak = {"live": 0, "max": 0}

    class _Counting(WebAppGenerator):
        def __init__(self) -> None:
            super().__init__(model="stub", concurrency=99, verify_runtime=False)

        async def _raw_complete(self, prompt: str, *, label: str, max_tokens: int | None = None) -> str:
            peak["live"] += 1
            peak["max"] = max(peak["max"], peak["live"])
            try:
                await asyncio.sleep(0.01)
                return GOOD_CSS
            finally:
                peak["live"] -= 1

    async def _run() -> None:
        gens = [_Counting() for _ in range(3)]
        await asyncio.gather(*(g._complete("p", label=f"x{i}{j}") for i, g in enumerate(gens) for j in range(8)))

    asyncio.run(_run())
    assert peak["max"] <= wg.LLM_MAX_CONCURRENCY


def test_one_failed_content_shard_does_not_lose_the_app() -> None:
    plan = {
        "tagline": "t",
        "collections": [
            {"name": "good", "purpose": "p", "min_entries": 10, "fields": [{"name": "id"}]},
            {"name": "bad", "purpose": "p", "min_entries": 10, "fields": [{"name": "id"}]},
        ],
        "views": [],
    }

    class _PartialFailure(WebAppGenerator):
        def __init__(self) -> None:
            super().__init__(model="stub", verify_runtime=False)

        async def _raw_complete(self, prompt: str, *, label: str, max_tokens: int | None = None) -> str:
            if label == "content:bad":
                raise WebAppGenerationError("shard truncated")
            if label.startswith("content:"):
                return '[{"id": "a"}]'
            return '{"name": "A", "tagline": "t"}'

    data = asyncio.run(_PartialFailure()._generate_content(WebAppSpec(app_name="A", description="d"), plan))
    payload = json.loads(data.split("=", 1)[1].strip().rstrip(";"))
    # The surviving collection ships; an app missing one section beats no app.
    assert "good" in payload and "bad" not in payload


def test_all_shards_failing_is_still_fatal() -> None:
    plan = {
        "tagline": "t",
        "collections": [{"name": "only", "purpose": "p", "min_entries": 10, "fields": [{"name": "id"}]}],
        "views": [],
    }

    class _TotalFailure(WebAppGenerator):
        def __init__(self) -> None:
            super().__init__(model="stub", verify_runtime=False)

        async def _raw_complete(self, prompt: str, *, label: str, max_tokens: int | None = None) -> str:
            if label.startswith("content:"):
                raise WebAppGenerationError("shard truncated")
            return '{"name": "A"}'

    with pytest.raises(WebAppGenerationError, match="every content shard failed"):
        asyncio.run(_TotalFailure()._generate_content(WebAppSpec(app_name="A", description="d"), plan))


def test_dynamic_element_ids_are_not_reported_as_missing() -> None:
    # getElementById("view-" + id) yields the literal prefix "view-", which is
    # not an id. Reporting it rejected a working app three runs in a row.
    assets = _assets()
    assets["views.js"] = (
        "(function(){ APP.views.home = function(){"
        ' document.getElementById("view-" + id);'
        ' APP.mount("detail-tab-" + n);'
        ' document.getElementById("list"); }; })();'
    )
    assert validate_assets(assets) == []


def test_literal_lookups_are_still_checked() -> None:
    assets = _assets()
    assets["views.js"] = '(function(){ APP.views.home = function(){ document.getElementById("nope"); }; })();'
    assert any("nope" in p for p in validate_assets(assets))


def test_app_on_handler_ids_are_checked() -> None:
    assets = _assets()
    assets["features.js"] = (
        '(function(){ APP.features.s = function(){ APP.on("ghost", "click", f); }; APP.boot(); })();'
    )
    assert any("ghost" in p for p in validate_assets(assets))


def test_design_rules_call_out_fixed_element_insets() -> None:
    # A fixed header does not inherit the body's safe-area padding, so a rule
    # that only mentions "outermost padding" leaves the title under the clock --
    # which is exactly what shipped to the device.
    from zerodev.generator.webapp_generator import DESIGN_SYSTEM_RULES

    assert "position:fixed" in DESIGN_SYSTEM_RULES.replace(" ", "")
    assert "env(safe-area-inset-top)" in DESIGN_SYSTEM_RULES
    assert "EDGE TO EDGE" in DESIGN_SYSTEM_RULES
