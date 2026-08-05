"""Tests for the headless-DOM runtime gate.

These exercise the real Node harness, because the whole point of the gate is
that it runs the app for real. When jsdom is not installed the harness reports
itself as unavailable and the tests assert that degradation instead.
"""

from __future__ import annotations

import pytest

from zerodev.generator.runtime_verifier import (
    RuntimeReport,
    attribute_problems,
    harness_available,
    verify_assets,
)

HTML = """<!doctype html>
<html lang="zh-CN"><head>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<link rel="stylesheet" href="styles.css"></head>
<body>
<section class="view" id="view-home"><div id="item-list"></div></section>
<nav><button data-view="home">首页</button></nav>
<input type="search" id="search-input">
<script src="data.js"></script><script src="core.js"></script>
<script src="charts.js"></script><script src="views.js"></script>
<script src="features.js"></script>
</body></html>
"""

CORE = """
(function () {
  window.APP = {
    data: window.APP_DATA, state: {}, views: {}, features: {}, charts: {},
    mount: function (id) { return document.getElementById(id); },
    el: function (tag, cls, text) {
      var n = document.createElement(tag);
      if (cls) { n.className = cls; }
      if (text !== undefined) { n.textContent = text; }
      return n;
    },
    boot: function () {
      Object.keys(APP.views).forEach(function (k) { APP.views[k](); });
      Object.keys(APP.features).forEach(function (k) { APP.features[k](); });
    }
  };
})();
"""
CHARTS = "(function(){ APP.charts.bar = function(){}; })();"
VIEWS = """
(function () {
  APP.views.home = function () {
    var host = APP.mount('item-list');
    if (!host) { return; }
    (APP.data.items || []).forEach(function (it) {
      var row = APP.el('div', 'card', it.name);
      row.setAttribute('data-id', it.id);
      host.appendChild(row);
    });
  };
})();
"""
FEATURES = """
(function () {
  APP.features.search = function () {
    var box = APP.mount('search-input');
    if (box) { box.addEventListener('input', function () {}); }
  };
  APP.boot();
})();
"""
DATA = 'window.APP_DATA = { items: [{"id": "a", "name": "甲"}, {"id": "b", "name": "乙"}] };'
CSS = ":root{--bg:#fff}@media (prefers-color-scheme: dark){:root{--bg:#000}}body{padding:env(safe-area-inset-top)}"

CONTRACT = {
    "views": [{"id": "home", "sections": [{"mount_id": "item-list", "collection": "items"}]}],
    "element_ids": ["item-list", "search-input"],
}


def _assets(**overrides) -> dict[str, str]:
    base = {
        "index.html": HTML,
        "styles.css": CSS,
        "data.js": DATA,
        "core.js": CORE,
        "charts.js": CHARTS,
        "views.js": VIEWS,
        "features.js": FEATURES,
    }
    base.update(overrides)
    return base


needs_harness = pytest.mark.skipif(not harness_available()[0], reason=harness_available()[1])


# ── Availability ────────────────────────────────────────────────


def test_unavailable_harness_does_not_block(monkeypatch: pytest.MonkeyPatch) -> None:
    # A machine without Node must still be able to build apps.
    monkeypatch.setattr("zerodev.generator.runtime_verifier.harness_available", lambda: (False, "node missing"))
    report = verify_assets(_assets(), CONTRACT)
    assert report.ok and not report.available


def test_harness_crash_reports_as_unavailable_not_as_a_defect() -> None:
    # Infrastructure failure must not be blamed on the app, or a broken harness
    # would halt the whole factory.
    from zerodev.generator.runtime_verifier import _parse_report

    report = _parse_report('{"fatal": "TypeError: boom"}', "")
    assert report.ok is True
    assert not report.available
    assert "boom" in report.fatal


# ── Real execution ──────────────────────────────────────────────


@needs_harness
def test_working_app_passes() -> None:
    report = verify_assets(_assets(), CONTRACT)
    assert report.ok, report.problems()
    assert report.checks["app_global"] is True
    assert report.checks["self_booted"] is True
    assert report.checks["mounts"]["item-list"]["children"] == 2


@needs_harness
def test_boot_exception_is_caught_and_attributed() -> None:
    # The failure static checks cannot see: parses fine, ships a blank screen.
    broken = _assets()
    broken["views.js"] = "(function(){ APP.views.home = function(){ undefinedHelper(); }; })();"
    report = verify_assets(broken, CONTRACT)

    assert not report.ok
    assert any("undefinedHelper" in p for p in report.problems())
    assert "views.js" in attribute_problems(report, list(broken))


@needs_harness
def test_missing_boot_call_is_reported() -> None:
    broken = _assets()
    broken["features.js"] = "(function(){ APP.features.search = function(){}; })();"
    report = verify_assets(broken, CONTRACT)

    assert not report.ok
    assert report.checks["boot_forced"] is True
    assert any("APP.boot()" in p for p in report.problems())


@needs_harness
def test_empty_mount_is_reported() -> None:
    broken = _assets()
    broken["views.js"] = "(function(){ APP.views.home = function(){ /* renders nothing */ }; })();"
    report = verify_assets(broken, CONTRACT)

    assert not report.ok
    assert "item-list" in report.empty_mounts
    assert "views.js" in attribute_problems(report, list(broken))


@needs_harness
def test_missing_container_is_blamed_on_the_markup() -> None:
    broken = _assets()
    broken["index.html"] = HTML.replace('<div id="item-list"></div>', "")
    report = verify_assets(broken, CONTRACT)

    assert not report.ok
    assert "item-list" in report.missing_mounts
    assert "index.html" in attribute_problems(report, list(broken))


@needs_harness
def test_mount_without_a_collection_may_be_empty() -> None:
    # A search-results container is empty until someone searches; flagging it
    # would send the rework loop chasing a defect that does not exist.
    contract = {
        "views": [{"id": "home", "sections": [{"mount_id": "search-input", "collection": None}]}],
        "element_ids": ["search-input"],
    }
    assert verify_assets(_assets(), contract).ok


@needs_harness
def test_browser_apis_jsdom_lacks_are_not_reported_as_app_bugs() -> None:
    # window.scrollTo is unimplemented in jsdom; using it is not a defect.
    using_scroll = _assets()
    using_scroll["features.js"] = FEATURES.replace("APP.boot();", "window.scrollTo(0, 0); APP.boot();")
    report = verify_assets(using_scroll, CONTRACT)
    assert report.ok, report.problems()


@needs_harness
def test_interaction_errors_are_caught() -> None:
    broken = _assets()
    broken["features.js"] = FEATURES.replace(
        "if (box) { box.addEventListener('input', function () {}); }",
        "if (box) { box.addEventListener('input', function () { missingFn(); }); }",
    )
    report = verify_assets(broken, CONTRACT)
    assert not report.ok
    assert any(not p["ok"] for p in report.checks["interactions"])


# ── Reporting ───────────────────────────────────────────────────


def test_failing_report_always_explains_itself() -> None:
    # A gate that fails with an empty problem list would block a build with no
    # actionable reason.
    report = RuntimeReport(ok=False, fatal="the app did not finish booting within 120s")
    assert report.problems()


def test_summary_survives_an_empty_report() -> None:
    assert "skipped" in RuntimeReport(ok=True, skipped="node missing").summary()
