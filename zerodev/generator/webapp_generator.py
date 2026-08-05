"""Generate the rich, self-contained web UI that a WebView app shell displays.

The generated assets are packaged into a HarmonyOS ``.hap`` under
``resources/rawfile`` (see :mod:`zerodev.generator.ohos_project`), so they must
run with **no network at all**: no CDN scripts, no web fonts, no remote images.
Everything -- layout, iconography, illustration, sample content -- is inlined.

Generation is **contract-first and concurrent**. One planning call fixes the
design tokens, the element ids, the class names and the data field names; every
later call is written against that contract and none of them see each other's
output. That is what makes the fan-out safe:

1. **Plan** (1 call) -- the interface contract.
2. **Everything else**, concurrently -- interface copy, one call per data
   collection, ``styles.css``, ``index.html`` and ``app.js``.
3. **Repair** (only the files that failed validation), also concurrent.

Sharding content per collection is what buys depth: each worker gets one
focused brief and a large ``min_entries`` budget instead of one call trying to
invent every record in the app. ``data.js`` is then assembled in Python from
the validated JSON shards, so the largest data file is valid by construction
and always defines ``window.APP_DATA``.

Validation is deliberately strict about the offline constraint: a page that
references ``https://cdn...`` looks fine in a browser and renders blank inside
the packaged app, which is exactly the failure a fully automated pipeline must
not ship.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zerodev.llm import LLMError, acomplete, get_llm_model

logger = logging.getLogger(__name__)

# Files the generator always produces. All are written concurrently against the
# plan's contract; this order is also the script load order in the page.
ASSET_FILES: tuple[str, ...] = (
    "styles.css",
    "data.js",
    "core.js",
    "charts.js",
    "views.js",
    "features.js",
    "index.html",
)

# The scripts, in the order index.html must load them. Each later file depends
# on the global the earlier ones installed.
SCRIPT_ORDER: tuple[str, ...] = ("data.js", "core.js", "charts.js", "views.js", "features.js")

MAX_REPAIR_ROUNDS = 2

# Runtime rework rounds. Fewer than the static ones on purpose: a static defect
# is usually a typo the model fixes first try, while an app that still does not
# run after two rewrites with real stack traces in hand is not going to on a
# third -- better to fail loudly and let the daemon move on.
MAX_RUNTIME_ROUNDS = 2

# Emoji are banned project-wide because they render inconsistently across
# HarmonyOS system font versions. The test is Unicode's Emoji_Presentation
# property -- "does this render as a colour pictograph by default" -- not
# "is this in a symbol block".
#
# The distinction matters: arrows (U+2190-U+21FF), check marks, stars and
# geometric shapes live in those blocks but have default *text* presentation.
# Banning them wholesale made it impossible to typeset a limit as "x -> 0" with
# a real arrow, which a maths app cannot do without.
#
# Members of the Miscellaneous Symbols / Dingbats blocks that really do default
# to colour emoji. Everything else in those blocks stays allowed.
_EMOJI_PRESENTATION_SYMBOLS = "⌚⌛⏩-⏬⏰⏳◽◾☔☕♈-♓♿⚓⚡⚪⚫⚽⚾⛄⛅⛎⛔⛪⛲⛳⛵⛺⛽✅✊✋✨❌❎❓-❕❗➕-➗➰➿"

_EMOJI_RE = re.compile(
    # Pictographic planes (emoticons, transport, supplemental symbols, flags).
    f"[\U0001f000-\U0001faff{_EMOJI_PRESENTATION_SYMBOLS}]"
    # U+FE0F forces emoji presentation onto an otherwise textual base character.
    "|️"
)

# Resource loading that points off-device: src=, url(), @import. A remote
# <a href> is only a dead link, but a remote src/stylesheet is a blank screen,
# so those are what get flagged.
_REMOTE_ASSET_RE = re.compile(
    r"""(?:\bsrc\s*=\s*|@import\s+(?:url\()?|\burl\()\s*['"]?\s*(?:https?:)?//""",
    re.IGNORECASE,
)

# <link rel="stylesheet" href="https://..."> in any attribute order.
_REMOTE_LINK_RE = re.compile(
    r"""<link\b[^>]*\bhref\s*=\s*['"]?\s*(?:https?:)?//""",
    re.IGNORECASE,
)

_FENCE_RE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*\n(.*?)\n?\s*```\s*$", re.DOTALL)


class WebAppGenerationError(RuntimeError):
    """Raised when usable web assets could not be produced."""


@dataclass
class WebAppSpec:
    """Input brief for one generated web application."""

    app_name: str
    description: str
    features: list[str] = field(default_factory=list)
    pages: list[str] = field(default_factory=list)
    target_users: str = ""
    # Free-form guidance appended verbatim to the design prompt.
    design_notes: str = ""
    language: str = "zh-CN"
    # Bottom tab navigation is the right default for a phone app; set False for
    # a single-surface tool.
    tabbed: bool = True

    @classmethod
    def from_prd(cls, prd: Any, **overrides: Any) -> WebAppSpec:
        """Adapt a :class:`~zerodev.generator.prd_generator.PRD` into a brief."""
        pages = []
        for page in getattr(prd, "pages", []) or []:
            name = getattr(page, "name", None) or (page.get("name") if isinstance(page, dict) else None)
            purpose = getattr(page, "purpose", None) or (page.get("purpose") if isinstance(page, dict) else "")
            if name:
                pages.append(f"{name}: {purpose}" if purpose else str(name))
        data = {
            "app_name": getattr(prd, "app_name", "App"),
            "description": getattr(prd, "description", ""),
            "features": list(getattr(prd, "features", []) or []),
            "pages": pages,
            "design_notes": getattr(prd, "ui_guidelines", "") or "",
        }
        data.update(overrides)
        return cls(**data)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

DESIGN_SYSTEM_RULES = """\
DESIGN SYSTEM (non-negotiable):
  - Mobile-first. Design for a 390x844 logical viewport, scaling gracefully to tablets.
  - Respect the device safe areas: the page must use env(safe-area-inset-top/bottom/left/right)
    for its outermost padding. Content must never sit under a status bar or home indicator.
  - Support light and dark automatically via @media (prefers-color-scheme: dark).
    Define every colour as a CSS custom property on :root and override the set in the dark block.
  - Typography: system stack only --
    font-family: 'HarmonyOS Sans SC', -apple-system, BlinkMacSystemFont, 'Noto Sans SC', 'PingFang SC', sans-serif;
    Use a clear type scale (for example 28/22/17/15/13px) with deliberate line-height and letter-spacing.
  - Spacing on a 4px grid. Consistent radii (for example 12px cards, 20px sheets, 999px pills).
  - Depth through layered surfaces and soft shadows, not heavy borders.
  - Every tappable target is at least 44x44px, with a visible :active state.
  - Motion: 150-250ms ease transitions on state changes. Honour
    @media (prefers-reduced-motion: reduce) by disabling transitions and animations.
  - Accessibility: text contrast at least 4.5:1, focus-visible outlines, semantic landmarks
    (header/nav/main), aria-labels on icon-only controls.

HARD TECHNICAL CONSTRAINTS:
  - COMPLETELY OFFLINE. No CDN, no web fonts, no remote images, no fetch/XHR to any host.
    Any src/href/url() pointing at http://, https:// or // is a defect.
  - All iconography is INLINE SVG (stroke-based, currentColor, 24x24 viewBox). Never an icon font.
  - All imagery is CSS gradients, CSS shapes or inline SVG illustration. Never a raster URL.
  - Vanilla HTML/CSS/JS only. No frameworks, no build step, no ES modules
    (files load via plain <script> tags, so declare globals, do not use import/export).
  - Must run in ArkWeb (Chromium-based, modern). ES2020 is fine.
  - NEVER use emoji characters anywhere -- not in markup, CSS content, JS strings or comments.
    Ordinary typographic and mathematical symbols ARE allowed and encouraged where they carry
    meaning: arrows, comparison and set operators, Greek letters, check marks, stars, bullets.
  - All user-facing text in Simplified Chinese, unless the brief says otherwise.
"""

PLAN_PROMPT = """\
You are a senior product designer and front-end engineer. Plan a polished, content-rich
mobile web application that will be packaged inside a native app shell and displayed full screen.

APP BRIEF
  Name: {app_name}
  Description: {description}
  Target users: {target_users}
  Requested features: {features}
  Requested screens: {pages}
  Extra design notes: {design_notes}

{design_rules}

This plan is an INTERFACE CONTRACT. The stylesheet, the markup, the behaviour and the seed
content are all written independently and in parallel against it, by workers that never see
each other's output. Anything you leave vague becomes a mismatch that shows up as a blank
screen. Name every id and class here, exactly as they will appear.

Produce a JSON object -- and nothing else -- with exactly this shape:

{{
  "app_name": "...",
  "tagline": "one short line shown in the app",
  "design": {{
    "mood": "2-3 words describing the visual direction",
    "light": {{"bg": "#...", "surface": "#...", "surface_alt": "#...", "text": "#...",
               "text_muted": "#...", "accent": "#...", "accent_soft": "#...", "border": "#...",
               "success": "#...", "warning": "#...", "danger": "#..."}},
    "dark":  {{"bg": "#...", "surface": "#...", "surface_alt": "#...", "text": "#...",
               "text_muted": "#...", "accent": "#...", "accent_soft": "#...", "border": "#...",
               "success": "#...", "warning": "#...", "danger": "#..."}},
    "radius": {{"card": "16px", "control": "12px", "pill": "999px"}},
    "signature_element": "the one visual device that makes this app recognisable",
    "css_classes": ["every class name the markup uses, so the stylesheet can cover all of them"]
  }},
  "views": [
    {{
      "id": "lowercase_ascii_id",
      "title": "中文标题",
      "icon_hint": "what the tab icon depicts, for example 'house outline'",
      "purpose": "what the user does here",
      "sections": [
        {{"kind": "hero|stat_row|list|grid|chart|form|timeline|detail|empty_state|cta",
          "title": "中文小标题",
          "mount_id": "the exact element id app.js fills, or null for static markup",
          "collection": "which data collection feeds it, or null",
          "description": "what it shows and how it behaves"}}
      ]
    }}
  ],
  "collections": [
    {{
      "name": "lowercase_ascii_name",
      "purpose": "what these records are",
      "min_entries": 24,
      "fields": [
        {{"name": "id", "type": "string", "description": "stable ascii slug"}},
        {{"name": "...", "type": "string|number|boolean|string[]", "description": "..."}}
      ],
      "categories": ["the groupings entries should spread across"]
    }}
  ],
  "element_ids": ["every id the scripts will look up, including all mount_id values"],
  "features": [
    {{
      "id": "lowercase_ascii_id",
      "title": "中文功能名",
      "description": "exactly what it does from the user's point of view",
      "element_ids": ["the controls and surfaces this feature touches"],
      "collection": "which collection it operates on, or null"
    }}
  ]
}}

CONTRACT REQUIREMENTS -- parallel workers depend on these being exact:
  - Every "mount_id" MUST also appear in "element_ids". The scripts only touch ids listed there.
  - Every "collection" referenced by a section MUST exist in "collections" by that exact name.
  - Every id in a feature's "element_ids" MUST also appear in the top-level "element_ids".
  - Field names are the literal keys the records will use. Pick them once, here.

FEATURE REQUIREMENTS -- a browsable list is not an app:
  - Declare AT LEAST {feature_count} features. These are the mandatory baseline, and you should
    add more that are specific to this subject matter:
      search        full-text search across the primary collection
      filter        multi-dimension filtering by the collections' categories
      sort          sorting by at least two numeric or date keys, with direction toggle
      detail        a detail sheet opened from any list row, showing every field of the record
      favorite      favouriting that survives a restart
      stats         a statistics surface computed from the data, with a chart
  - Give each feature the exact control ids it needs so the markup can carry them.
  - Prefer features that only make sense for THIS app over generic CRUD.

CONTENT REQUIREMENTS -- this is what separates a real app from a mockup:
  - {view_count} views, each genuinely different in layout, not the same list repeated.
  - Declare {collection_count} to 5 collections. Set min_entries to at least 20 for the primary
    collection -- content is generated per collection in parallel, so a large ask is cheap.
  - Records must be specific and varied: real names, real-sounding titles, plausible numbers,
    dates spread over time. No "示例1 / 示例2", no lorem ipsum, no filler.
  - Content must be immediately useful on first launch, before the user enters anything.
  - Include at least one collection with quantitative fields suitable for an inline SVG chart.

Return only the JSON object.
"""

CONTENT_SHARD_PROMPT = """\
You are writing the seed content for one collection of a mobile app. Depth and specificity are
the whole job -- this content is what the user sees on first launch.

APP: {app_name}
{tagline}
Overall description: {description}

COLLECTION TO WRITE
  Name: {name}
  Purpose: {purpose}
  Spread entries across these categories: {categories}
  Required fields (use these exact keys on every record):
{fields}

Write AT LEAST {min_entries} records.

QUALITY BAR:
  - Every record must be individually researched-feeling and concrete. A reader who knows the
    subject should find it correct and non-obvious, not generic.
  - Vary length, category, and values across records. No two records should read as templates
    of each other.
  - Where a field invites explanation, write a real sentence with actual substance, not a label.
  - Simplified Chinese for all human-readable text.
  - NEVER use emoji. Ordinary typographic and mathematical symbols (arrows, operators, Greek
    letters, comparison signs) ARE allowed and encouraged where they carry meaning.
  - Values must be JSON-safe: strings, numbers, booleans, arrays of strings, plain objects.
    Dates as 'YYYY-MM-DD'. Numbers as numbers, not strings.

Return ONLY a JSON array of record objects. No wrapper object, no commentary, no fences.
"""

APP_COPY_PROMPT = """\
Write the static interface copy for this app as a JSON object.

APP: {app_name}
Tagline: {tagline}
Description: {description}
Views: {views}

Return ONLY a JSON object with this shape (add any other static strings the UI needs):

{{
  "name": "...", "tagline": "...",
  "sections": {{"<view_id>": "中文标题"}},
  "actions": {{"open": "...", "save": "...", "close": "...", "clear": "...", "retry": "..."}},
  "empty": {{"<view_id>": "空状态下显示的中文提示"}},
  "search_placeholder": "..."
}}

Simplified Chinese. No emoji. No commentary.
"""

# The behaviour layer is split across several scripts, generated concurrently.
# Two reasons, both load-bearing:
#   1. A single app.js reached ~70KB, which is close enough to the output-token
#      cap that adding features would start truncating it mid-function.
#   2. Independent modules can be written in parallel, so richer behaviour costs
#      no extra wall-clock.
# They only compose because the namespace below is FIXED here rather than
# invented by the model -- every module is told the same API and codes to it.
RUNTIME_CONTRACT = """\
SHARED RUNTIME (fixed -- do not redesign it, other modules are written against it right now):

  Load order in the page is:  data.js -> core.js -> charts.js -> views.js -> features.js

  core.js creates the single global and nothing else may replace it:

    window.APP = {
      data,                          // === window.APP_DATA
      state,                         // plain object, UI state, persisted to localStorage
      save(), load(),                // persist / restore state, both try/catch guarded
      el(tag, className, text),      // create an element
      mount(id),                     // getElementById(id), returns null when absent
      clear(node),                   // remove all children
      on(id, event, handler),        // addEventListener, no-op when the id is absent
      fmt: { num(n), date(s), pct(n), compact(n) },
      router: { go(viewId), current() },   // view switching + active tab state
      charts: {},                    // charts.js fills this in
      views: {},                     // views.js registers render functions by view id
      features: {},                  // features.js registers init functions by name
      boot()                         // clears, renders every view, inits every feature
    };

  charts.js assigns renderers onto APP.charts (bar, line, donut, sparkline...). Each takes
  (mountNode, series) and draws inline SVG built with createElementNS. No chart library.

  views.js assigns one function per view id onto APP.views. Each renders that view's sections
  into their mount ids from APP.data.

  features.js assigns initialisers onto APP.features, then calls APP.boot() once the DOM is
  ready. It owns cross-view behaviour: search, filtering, sorting, comparison, detail sheets,
  favourites, and anything else in the contract's "features" list.

  Rules for every module:
    - Plain script, no import/export. Wrap in an IIFE.
    - Never assume an element exists: use APP.mount / APP.on, which tolerate absence.
    - Never innerHTML with interpolated data -- createElement + textContent only.
    - Only look up ids listed in the contract's "element_ids".
"""

FILE_PROMPTS: Mapping[str, str] = {
    "styles.css": """\
Write `styles.css` -- the complete stylesheet for this application.

Requirements:
  - Declare every colour from the plan's light palette as a custom property on :root,
    then override the whole set inside @media (prefers-color-scheme: dark).
  - Include: reset/base, safe-area layout scaffolding, the app shell (header, scrollable main,
    bottom tab bar when tabbed), cards, lists, stat tiles, pills/badges, buttons, form controls,
    the chart container, empty states, skeleton loading, and the view transition.
  - Style every section kind named in the plan. Nothing in the markup should be left unstyled.
  - Realise the plan's "signature_element" so the app has a recognisable look.
  - Include @media (prefers-reduced-motion: reduce) and a tablet breakpoint at 768px.

Output only CSS. No markdown fences, no commentary.
""",
    "index.html": """\
Write `index.html` -- the application shell.

Requirements:
  - <!doctype html>, <html lang="{language}">, and
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover,
    user-scalable=no">.
  - <meta name="color-scheme" content="light dark">.
  - Link `styles.css` in <head>. At the end of <body>, load the scripts in EXACTLY this order:
    data.js, core.js, charts.js, views.js, features.js -- plain <script> tags, no type=module.
  - Markup for the full shell: header, one <section class="view" id="view-{{id}}"> per planned view,
    and the bottom tab bar with an inline SVG icon per tab when the app is tabbed.
  - Write the static structure of every section from the contract. A section with a "mount_id"
    gets an EMPTY container carrying exactly that id -- the scripts fill it. Use the contract's
    ids verbatim; the scripts are written in parallel against the same list and will not find
    anything else.
  - Include the controls every declared feature needs: search input, filter chips, sort control,
    the detail sheet container, the comparison surface -- each carrying its contract id.
  - Use only class names listed in the contract's design.css_classes, so the stylesheet (also
    written in parallel) covers every element.
  - All icons inline SVG with stroke="currentColor". Semantic landmarks and aria-labels throughout.

Output only HTML. No markdown fences, no commentary.
""",
    "core.js": """\
Write `core.js` -- the shared runtime described in SHARED RUNTIME above.

Requirements:
  - Create `window.APP` with every documented member. This file is the only one that creates it.
  - `state` holds the UI state the contract's features need: current view, query string, active
    filters, sort key and direction, favourites (a set-like object of ids), comparison selection,
    and anything else the declared features require. Give every key a sensible default.
  - `save()`/`load()` persist `state` to localStorage under one namespaced key, both wrapped in
    try/catch so a storage failure never blanks the app.
  - `router.go(viewId)` toggles the `is-active` class on views and tab buttons, remembers and
    restores per-view scroll position, writes the current view into `state`, and persists it.
  - `fmt` helpers format numbers, dates and percentages for a Chinese interface.
  - `boot()` restores state, renders every function registered on `APP.views`, then runs every
    initialiser on `APP.features`, each in its own try/catch so one broken feature cannot take
    down the whole app. Log failures with console.error.

Output only JavaScript. No markdown fences, no commentary.
""",
    "charts.js": """\
Write `charts.js` -- inline SVG chart renderers assigned onto `APP.charts`.

Requirements:
  - Provide at least: bar, line, donut and sparkline. Each takes (mountNode, series, options)
    and builds SVG with document.createElementNS. No chart library, no canvas.
  - Charts must be responsive: use a viewBox and percentage width, never fixed pixel width.
  - Colours come from CSS custom properties via `currentColor` and `var(--accent)` so the charts
    follow light and dark mode automatically.
  - Include axis labels or value labels where they aid reading, and an accessible role="img"
    with an aria-label summarising the series.
  - Handle empty or single-point series without throwing.

Output only JavaScript. No markdown fences, no commentary.
""",
    "views.js": """\
Write `views.js` -- one render function per view, assigned onto `APP.views`.

Requirements:
  - For every view in the contract, assign `APP.views['<view_id>'] = function () {{ ... }}`.
  - Each function renders that view's sections into their `mount_id` containers, reading from
    `APP.data[<collection>]` and respecting the current `APP.state` (query, filters, sort).
  - Build rich rows: not just a title, but the secondary fields that make each record worth
    reading -- badges for category, numeric stats, dates, status pills.
  - Render the view's charts by calling into `APP.charts`.
  - Show the contract's empty-state copy when a filtered list comes back empty.
  - Every list item that opens a detail must carry a `data-id` attribute so features.js can
    delegate clicks without re-querying.

Output only JavaScript. No markdown fences, no commentary.
""",
    "features.js": """\
Write `features.js` -- cross-view behaviour, assigned onto `APP.features`, then boot.

Requirements:
  - Implement EVERY entry in the contract's "features" list as its own initialiser on
    `APP.features`, named after the feature id.
  - At minimum that means: full-text search across the primary collection, multi-dimension
    filtering by category, sorting by at least two numeric or date keys with direction toggle,
    a detail sheet opened from any list row (populated from the record, closable, focus-trapped),
    favouriting that persists across restarts, and a statistics surface computed from the data.
  - Use event delegation on list containers via the `data-id` attributes views.js emits.
  - Every state change writes through `APP.save()` and re-renders only the affected view.
  - Wire the tab bar to `APP.router.go`.
  - At the end of the file, call `APP.boot()` on DOMContentLoaded (or immediately when the
    document is already interactive).

Output only JavaScript. No markdown fences, no commentary.
""",
}


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class WebAppGenerator:
    """Produce a complete offline web application from a brief.

    Work is organised so that everything after the plan runs concurrently.
    The plan is an interface contract -- it fixes the element ids, class names
    and data field names up front -- which is what lets the stylesheet, the
    markup, the behaviour and every content shard be written by independent
    calls that never see each other's output.

    Rounds:

    1. plan (1 call)
    2. app copy + one call per data collection + styles.css + index.html + app.js,
       all concurrent
    3. repair, only for files that failed validation, also concurrent

    ``data.js`` is assembled in Python from the validated JSON shards rather
    than written by the model, so it is syntactically valid by construction and
    always defines ``window.APP_DATA``.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        max_tokens: int = 16000,
        concurrency: int = 6,
        verify_runtime: bool = True,
    ) -> None:
        self._model = model or get_llm_model()
        self._max_tokens = max_tokens
        # The runtime gate needs Node and jsdom. It degrades to a warning when
        # they are absent, but callers that never want the subprocess (unit
        # tests, content-only iteration) can switch it off outright.
        self._verify_runtime = verify_runtime
        # Kept so callers can score the result without re-running anything.
        self.last_plan: dict[str, Any] = {}
        self.last_runtime_report: Any = None
        # Bounds in-flight requests so a wide fan-out cannot trip a relay's
        # rate limit and turn a fast build into a retry storm.
        self._gate = asyncio.Semaphore(max(1, concurrency))

    async def _complete(self, prompt: str, *, label: str, max_tokens: int | None = None) -> str:
        """Rate-limited completion. The gate lives here, the call in
        :meth:`_raw_complete`, so a subclass can stub the transport and still be
        subject to the same concurrency bound."""
        async with self._gate:
            started = time.monotonic()
            raw = await self._raw_complete(prompt, label=label, max_tokens=max_tokens)
            logger.info("%s done in %.0fs (%d chars)", label, time.monotonic() - started, len(raw))
            return raw

    async def _raw_complete(self, prompt: str, *, label: str, max_tokens: int | None = None) -> str:
        try:
            return await acomplete(prompt, max_tokens=max_tokens or self._max_tokens, model=self._model)
        except LLMError as exc:
            raise WebAppGenerationError(f"LLM failed on {label}: {exc}") from exc

    async def generate(self, spec: WebAppSpec) -> dict[str, str]:
        """Return ``{relative_path: content}`` ready for the rawfile directory."""
        plan = await self.plan(spec)
        return await self.generate_files(spec, plan)

    # -- round 1: the contract ---------------------------------------------

    async def plan(self, spec: WebAppSpec) -> dict[str, Any]:
        """Ask the model for the design system, contract and content outline."""
        # Views scale with what the brief actually asks for. The old floor of 4
        # produced thin apps whenever the caller passed no explicit page list.
        view_count = max(5, min(7, len(spec.pages) or len(spec.features) or 5))
        prompt = PLAN_PROMPT.format(
            app_name=spec.app_name,
            description=spec.description or spec.app_name,
            target_users=spec.target_users or "普通中文用户",
            features="; ".join(spec.features) if spec.features else "由你根据描述推导",
            pages="; ".join(spec.pages) if spec.pages else "由你规划",
            design_notes=spec.design_notes or "无",
            design_rules=DESIGN_SYSTEM_RULES,
            view_count=view_count,
            collection_count=max(3, min(5, view_count - 1)),
            feature_count=max(8, len(spec.features) + 6),
        )
        logger.info("Planning web app '%s' (model=%s)", spec.app_name, self._model)
        plan = _parse_json_object(await self._complete(prompt, label="plan"))
        self.last_plan = plan
        if not plan.get("views"):
            raise WebAppGenerationError(f"Plan for {spec.app_name!r} contained no views.")
        if not plan.get("collections"):
            raise WebAppGenerationError(f"Plan for {spec.app_name!r} declared no data collections.")
        if not plan.get("features"):
            raise WebAppGenerationError(f"Plan for {spec.app_name!r} declared no features.")
        logger.info(
            "Contract: %d view(s), %d collection(s), %d feature(s), %d element id(s)",
            len(plan.get("views", [])),
            len(plan.get("collections", [])),
            len(plan.get("features", [])),
            len(plan.get("element_ids", [])),
        )
        return plan

    # -- round 2 + 3: everything else, concurrently -------------------------

    async def generate_files(self, spec: WebAppSpec, plan: Mapping[str, Any]) -> dict[str, str]:
        """Generate every asset concurrently, then repair what failed."""
        contract = json.dumps(plan, ensure_ascii=False, indent=2)

        code_files = [name for name in ASSET_FILES if name in FILE_PROMPTS]
        jobs: list[Any] = [self._generate_content(spec, plan)]
        jobs += [self._generate_file(spec, contract, name) for name in code_files]

        results = await asyncio.gather(*jobs, return_exceptions=True)
        for outcome in results:
            if isinstance(outcome, BaseException):
                raise outcome

        assets: dict[str, str] = {"data.js": results[0]}
        assets.update(dict(zip(code_files, results[1:], strict=True)))

        assets = await self._repair_all(spec, contract, assets)
        assets = await self._verify_and_rework(spec, contract, plan, assets)

        problems = validate_assets(assets) + syntax_check_js(assets)
        if problems:
            # Cross-file issues (a dangling id, a missing script tag) are reported
            # rather than silently shipped -- the caller decides whether to retry.
            raise WebAppGenerationError("Generated web assets failed validation:\n  - " + "\n  - ".join(problems))
        logger.info("Generated %d web asset file(s) for '%s': %s", len(assets), spec.app_name, asset_summary(assets))
        return assets

    async def _verify_and_rework(
        self,
        spec: WebAppSpec,
        contract: str,
        plan: Mapping[str, Any],
        assets: dict[str, str],
    ) -> dict[str, str]:
        """Run the app for real, and rework whatever broke.

        This is the only check that answers "does it work" rather than "is it
        well-formed". A page whose boot throws parses perfectly, passes every
        static rule, packages into a valid .hap, and shows the user nothing --
        so without this gate the factory ships blank screens.

        Failures carry real stack traces attributed to a file, which is what
        makes the rework useful: the model is told what actually threw and
        where, not asked to guess.
        """
        if not self._verify_runtime:
            return assets

        from zerodev.generator.runtime_verifier import (  # noqa: PLC0415
            attribute_problems,
            verify_assets,
        )

        for round_no in range(1, MAX_RUNTIME_ROUNDS + 1):
            # The harness is a subprocess; keep the event loop free for it.
            report = await asyncio.to_thread(verify_assets, assets, plan)
            self.last_runtime_report = report

            if not report.available:
                logger.warning("Runtime gate is OFF for '%s': %s", spec.app_name, report.skipped)
                return assets
            if report.ok:
                logger.info("Runtime check passed for '%s': %s", spec.app_name, report.summary())
                return assets

            by_file = attribute_problems(report, list(assets))
            if not by_file:
                # Something is wrong but not attributable to a file; reworking
                # at random would be worse than shipping and reporting.
                logger.warning("Runtime check failed unattributably for '%s': %s", spec.app_name, report.problems())
                return assets

            logger.warning(
                "Runtime rework %d/%d for '%s': %s",
                round_no,
                MAX_RUNTIME_ROUNDS,
                spec.app_name,
                ", ".join(f"{name} ({len(items)})" for name, items in by_file.items()),
            )
            repaired = await asyncio.gather(
                *(self._repair_one(spec, contract, name, assets[name], problems) for name, problems in by_file.items()),
                return_exceptions=True,
            )
            for outcome in repaired:
                if isinstance(outcome, BaseException):
                    raise outcome
            assets.update(dict(zip(by_file, repaired, strict=True)))
            # A rework can reintroduce a static defect, so re-settle those first.
            assets = await self._repair_all(spec, contract, assets)

        final = await asyncio.to_thread(verify_assets, assets, plan)
        self.last_runtime_report = final
        if final.available and not final.ok:
            raise WebAppGenerationError(
                f"App still broken after {MAX_RUNTIME_ROUNDS} runtime rework round(s):\n  - "
                + "\n  - ".join(final.problems())
            )
        return assets

    async def _generate_file(self, spec: WebAppSpec, contract: str, filename: str) -> str:
        # Every file that participates in the shared namespace gets the runtime
        # contract verbatim, so the concurrently written modules agree on an API
        # none of them had to invent.
        runtime = RUNTIME_CONTRACT if filename.endswith((".js", ".html")) else ""
        prompt = (
            f"APP: {spec.app_name}\n"
            f"CONTRACT (authoritative -- other files are being written against it right now, "
            f"in parallel, and cannot see your output):\n{contract}\n\n"
            f"{DESIGN_SYSTEM_RULES}\n{runtime}\n"
            f"{FILE_PROMPTS[filename].format(language=spec.language)}"
        )
        return strip_code_fence(await self._complete(prompt, label=filename))

    # -- content: one concurrent call per collection ------------------------

    async def _generate_content(self, spec: WebAppSpec, plan: Mapping[str, Any]) -> str:
        """Fan out per collection, then assemble ``data.js`` deterministically."""
        collections = [c for c in plan.get("collections", []) if isinstance(c, dict) and c.get("name")]
        jobs = [self._generate_app_copy(spec, plan)]
        jobs += [self._generate_shard(spec, plan, c) for c in collections]

        results = await asyncio.gather(*jobs, return_exceptions=True)
        for outcome in results:
            if isinstance(outcome, BaseException):
                raise outcome

        payload: dict[str, Any] = {"app": results[0]}
        for collection, records in zip(collections, results[1:], strict=True):
            payload[str(collection["name"])] = records
            logger.info("collection %s: %d record(s)", collection["name"], len(records))

        # Serialising with json guarantees valid JavaScript, so the model never
        # gets a chance to emit a syntax error in the largest data file.
        body = json.dumps(payload, ensure_ascii=False, indent=2)
        return f"window.APP_DATA = {body};\n"

    async def _generate_shard(
        self, spec: WebAppSpec, plan: Mapping[str, Any], collection: Mapping[str, Any]
    ) -> list[Any]:
        fields = collection.get("fields") or []
        rendered_fields = (
            "\n".join(
                f"    - {f.get('name')} ({f.get('type', 'string')}): {f.get('description', '')}"
                for f in fields
                if isinstance(f, dict) and f.get("name")
            )
            or "    - id (string), title (string), description (string)"
        )

        min_entries = collection.get("min_entries")
        try:
            min_entries = max(10, int(min_entries))
        except (TypeError, ValueError):
            min_entries = 20

        prompt = CONTENT_SHARD_PROMPT.format(
            app_name=spec.app_name,
            tagline=plan.get("tagline", ""),
            description=spec.description or spec.app_name,
            name=collection.get("name"),
            purpose=collection.get("purpose", ""),
            categories=", ".join(str(c) for c in (collection.get("categories") or [])) or "由你合理划分",
            fields=rendered_fields,
            min_entries=min_entries,
        )
        raw = await self._complete(prompt, label=f"content:{collection.get('name')}")
        records = _parse_json_array(raw)
        if not records:
            raise WebAppGenerationError(f"Collection {collection.get('name')!r} came back empty.")
        return records

    async def design_icon(self, spec: WebAppSpec, plan: Mapping[str, Any]) -> Any:
        """Design the launcher icon. Runs concurrently with asset generation.

        Never raises: an app with a fallback icon is worth far more than a
        failed build, so any problem degrades to the deterministic geometric
        mark keyed on the app name.
        """
        from zerodev.generator.icon_designer import (  # noqa: PLC0415
            ICON_PROMPT,
            IconDesignError,
            fallback_spec,
            parse_icon_response,
        )

        design = plan.get("design") if isinstance(plan.get("design"), dict) else {}
        accent = str(design.get("light", {}).get("accent") or design.get("accent") or "#0A84FF")
        prompt = ICON_PROMPT.format(
            app_name=spec.app_name,
            description=spec.description or spec.app_name,
            mood=design.get("mood", ""),
            accent=accent,
        )
        try:
            icon = parse_icon_response(await self._complete(prompt, label="icon", max_tokens=2048))
            logger.info("Icon concept: %s", icon.concept[:120])
            return icon
        except (WebAppGenerationError, IconDesignError) as exc:
            logger.warning("Icon design failed (%s); falling back to a generated mark.", exc)
            return fallback_spec(spec.app_name, accent)

    async def _generate_app_copy(self, spec: WebAppSpec, plan: Mapping[str, Any]) -> dict[str, Any]:
        prompt = APP_COPY_PROMPT.format(
            app_name=spec.app_name,
            tagline=plan.get("tagline", ""),
            description=spec.description or spec.app_name,
            views=", ".join(f"{v.get('id')}({v.get('title')})" for v in plan.get("views", []) if isinstance(v, dict)),
        )
        copy = _parse_json_object(await self._complete(prompt, label="app-copy", max_tokens=4096))
        copy.setdefault("name", spec.app_name)
        copy.setdefault("tagline", plan.get("tagline", ""))
        return copy

    # -- round 3: concurrent repair ----------------------------------------

    async def _repair_all(self, spec: WebAppSpec, contract: str, assets: dict[str, str]) -> dict[str, str]:
        """Repair every failing file, all rounds concurrent across files."""
        for round_no in range(1, MAX_REPAIR_ROUNDS + 1):
            broken = {name: validate_file(name, body) for name, body in assets.items()}
            broken = {name: problems for name, problems in broken.items() if problems}
            if not broken:
                return assets

            logger.warning(
                "Repair round %d/%d for: %s",
                round_no,
                MAX_REPAIR_ROUNDS,
                ", ".join(f"{n} ({len(p)})" for n, p in broken.items()),
            )
            repaired = await asyncio.gather(
                *(self._repair_one(spec, contract, name, assets[name], problems) for name, problems in broken.items()),
                return_exceptions=True,
            )
            for outcome in repaired:
                if isinstance(outcome, BaseException):
                    raise outcome
            assets.update(dict(zip(broken, repaired, strict=True)))

        still_broken = {name: validate_file(name, body) for name, body in assets.items()}
        still_broken = {name: problems for name, problems in still_broken.items() if problems}
        if still_broken:
            flattened = [p for problems in still_broken.values() for p in problems]
            raise WebAppGenerationError(
                f"Assets still invalid after {MAX_REPAIR_ROUNDS} repair round(s):\n  - " + "\n  - ".join(flattened)
            )
        return assets

    async def _repair_one(
        self, spec: WebAppSpec, contract: str, filename: str, content: str, problems: list[str]
    ) -> str:
        prompt = (
            f"The file `{filename}` produced for app {spec.app_name!r} has defects that break it "
            f"inside the packaged offline app:\n\n"
            + "\n".join(f"  - {p}" for p in problems)
            + f"\n\nCONTRACT:\n{contract}\n\n{DESIGN_SYSTEM_RULES}\n"
            f"Here is the current file:\n\n{content}\n\n"
            f"Rewrite `{filename}` in full, fixing every defect and keeping everything else "
            f"intact. Output only the file content, no fences, no commentary."
        )
        return strip_code_fence(await self._complete(prompt, label=f"repair:{filename}"))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_file(filename: str, content: str) -> list[str]:
    """Return human-readable defects for one generated file."""
    problems: list[str] = []
    if not content.strip():
        return [f"{filename} is empty."]

    for pattern in (_REMOTE_ASSET_RE, _REMOTE_LINK_RE):
        match = pattern.search(content)
        if match:
            snippet = content[max(0, match.start() - 40) : match.end() + 60].replace("\n", " ")
            problems.append(
                f"references a remote resource (the app runs offline, so it will not load): ...{snippet.strip()}..."
            )
            break

    if _EMOJI_RE.search(content):
        found = sorted({m.group(0) for m in _EMOJI_RE.finditer(content)})[:5]
        problems.append(f"contains emoji characters {found}, which are banned in generated apps.")

    if filename.endswith(".js"):
        if re.search(r"^\s*(import|export)\s", content, re.MULTILINE):
            problems.append("uses ES module import/export, but files load via plain <script> tags.")
        if re.search(r"\bfetch\s*\(\s*['\"]https?:", content):
            problems.append("calls fetch() against a remote URL; the app has no network guarantee.")

    if filename == "data.js" and "window.APP_DATA" not in content:
        problems.append("does not assign window.APP_DATA, which the scripts read.")

    if filename == "core.js" and not re.search(r"window\.APP\s*=", content):
        problems.append("does not create window.APP; every other script builds on it.")

    # The dependent modules must attach to the shared namespace rather than
    # quietly defining their own globals, or nothing they build gets rendered.
    for module, member in (("charts.js", "charts"), ("views.js", "views"), ("features.js", "features")):
        if filename == module and not re.search(rf"APP\s*\.\s*{member}", content):
            problems.append(f"never assigns onto APP.{member}, so {module} would have no effect.")

    if filename == "features.js" and not re.search(r"APP\s*\.\s*boot\s*\(", content):
        problems.append("never calls APP.boot(), so the app would never render.")

    if filename == "index.html":
        lowered = content.lower()
        if "<!doctype html" not in lowered:
            problems.append("is missing the <!doctype html> declaration.")
        if "styles.css" not in content:
            problems.append("does not reference styles.css -- the stylesheet is never linked.")
        missing_scripts = [name for name in SCRIPT_ORDER if name not in content]
        if missing_scripts:
            problems.append(f"does not load {', '.join(missing_scripts)}, so those modules never run.")
        else:
            positions = [content.index(name) for name in SCRIPT_ORDER]
            if positions != sorted(positions):
                problems.append("loads the scripts out of order; required order is " + " -> ".join(SCRIPT_ORDER))
        if "viewport-fit=cover" not in content:
            problems.append("viewport meta lacks viewport-fit=cover, so safe-area insets resolve to 0.")

    if filename == "styles.css":
        if "prefers-color-scheme" not in content:
            problems.append("has no dark-mode block; the shell follows the system colour mode.")
        if "safe-area-inset" not in content:
            problems.append("never uses env(safe-area-inset-*), so content can sit under system bars.")

    return [f"{filename} {p}" if not p.startswith(filename) else p for p in problems]


def syntax_check_js(assets: Mapping[str, str]) -> list[str]:
    """Parse every generated ``.js`` file with Node, when Node is available.

    A syntax error inside the packaged app produces a silent blank screen --
    ArkWeb has no visible console -- and the build itself still succeeds, so
    nothing downstream would catch it. Node's parser catches the whole class
    before the assets are ever written into the project. Skipped (rather than
    failed) when no Node binary exists, so this stays a bonus check.
    """
    node = shutil.which("node") or _bundled_node()
    if not node:
        logger.info("Node not found; skipping JavaScript syntax check on generated assets.")
        return []

    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="zerodev-jscheck-") as tmp:
        for name, content in assets.items():
            if not name.endswith(".js"):
                continue
            path = Path(tmp) / Path(name).name
            path.write_text(content, encoding="utf-8")
            try:
                proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                    [node, "--check", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                logger.warning("Could not syntax-check %s: %s", name, exc)
                continue
            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout).strip().splitlines()
                message = next((line for line in detail if "SyntaxError" in line), detail[-1] if detail else "")
                problems.append(f"{name} is not valid JavaScript: {message[:200]}")
    return problems


def _bundled_node() -> str:
    """Fall back to the Node runtime shipped inside DevEco Studio."""
    candidate = Path("/Applications/DevEco-Studio.app/Contents/tools/node/bin/node")
    return str(candidate) if candidate.exists() else ""


def validate_assets(assets: Mapping[str, str]) -> list[str]:
    """Cross-file checks run once every asset exists."""
    problems: list[str] = []
    for required in ASSET_FILES:
        if required not in assets:
            problems.append(f"missing generated file {required}.")

    html = assets.get("index.html", "")
    if html:
        # Every id the scripts target should exist in the markup; a mismatch is
        # the most common cause of a blank screen inside the packaged app. With
        # modules generated in parallel this check is the safety net that makes
        # the fan-out safe, so it covers all of them.
        html_ids = set(re.findall(r"""\bid\s*=\s*['"]([^'"]+)['"]""", html))
        for name, body in assets.items():
            if not name.endswith(".js"):
                continue
            js_ids = set(re.findall(r"""getElementById\(\s*['"]([^'"]+)['"]""", body))
            js_ids |= set(re.findall(r"""APP\s*\.\s*mount\(\s*['"]([^'"]+)['"]""", body))
            js_ids |= set(re.findall(r"""APP\s*\.\s*on\(\s*['"]([^'"]+)['"]""", body))
            missing = sorted(js_ids - html_ids)
            if missing:
                problems.append(f"{name} looks up element id(s) absent from index.html: " + ", ".join(missing[:8]))
    return problems


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def strip_code_fence(text: str) -> str:
    """Remove a wrapping markdown fence the model may have added anyway."""
    match = _FENCE_RE.match(text.strip())
    return (match.group(1) if match else text).strip() + "\n"


def _parse_json_array(text: str) -> list[Any]:
    """Parse a JSON array out of a model response, tolerating stray prose."""
    cleaned = strip_code_fence(text)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("["), cleaned.rfind("]")
        if start == -1 or end <= start:
            raise WebAppGenerationError(f"Model did not return a JSON array. Response began: {cleaned[:300]}") from None
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise WebAppGenerationError(f"Could not parse content JSON: {exc}") from exc

    # A shard that wraps its array in an object is common enough to unwrap
    # rather than fail the whole app over.
    if isinstance(parsed, dict):
        for value in parsed.values():
            if isinstance(value, list):
                return value
        raise WebAppGenerationError(f"Content shard returned an object with no array: {str(parsed)[:200]}")
    if not isinstance(parsed, list):
        raise WebAppGenerationError(f"Content shard returned {type(parsed).__name__}, expected a list.")
    return parsed


def _parse_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object out of a model response, tolerating stray prose."""
    cleaned = strip_code_fence(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise WebAppGenerationError(f"Could not parse plan JSON: {exc}. Response began: {cleaned[:300]}") from exc
    raise WebAppGenerationError(f"Model did not return a JSON object. Response began: {cleaned[:300]}")


def asset_summary(assets: Mapping[str, str]) -> str:
    """One-line size summary, used in logs and Dashboard events."""
    return ", ".join(f"{name} {len(content) // 1024 or 1}KB" for name, content in assets.items())


def iter_asset_paths(assets: Mapping[str, str]) -> Iterable[str]:
    return assets.keys()
