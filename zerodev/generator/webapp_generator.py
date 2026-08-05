"""Generate the rich, self-contained web UI that a WebView app shell displays.

The generated assets are packaged into a HarmonyOS ``.hap`` under
``resources/rawfile`` (see :mod:`zerodev.generator.ohos_project`), so they must
run with **no network at all**: no CDN scripts, no web fonts, no remote images.
Everything -- layout, iconography, illustration, sample content -- is inlined.

Generation runs in two phases:

1. **Plan** -- one LLM call produces a JSON design system plus a content plan
   with real, specific entries (not placeholder text). Having the palette,
   typography and data settled up front is what keeps the separately generated
   files visually coherent.
2. **Files** -- ``styles.css``, ``data.js``, ``index.html`` and ``app.js`` are
   generated against that shared plan, then validated and repaired.

Validation is deliberately strict about the offline constraint: a page that
references ``https://cdn...`` looks fine in a browser and renders blank inside
the packaged app, which is exactly the failure a fully automated pipeline must
not ship.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zerodev.llm import LLMError, acomplete, get_llm_model

logger = logging.getLogger(__name__)

# Files the generator always produces, in generation order. Later files see the
# already-generated earlier ones as context.
ASSET_FILES: tuple[str, ...] = ("styles.css", "data.js", "index.html", "app.js")

MAX_REPAIR_ROUNDS = 2

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
    "signature_element": "the one visual device that makes this app recognisable"
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
          "description": "what it shows and how it behaves"}}
      ]
    }}
  ],
  "data": {{
    "<collection_name>": [ {{ "...": "at least 10 realistic, specific records" }} ]
  }},
  "interactions": ["concrete behaviours the JS must implement"]
}}

CONTENT REQUIREMENTS -- this is what separates a real app from a mockup:
  - {view_count} views, each genuinely different in layout, not the same list repeated.
  - Every collection in "data" holds AT LEAST 10 entries with realistic, specific, varied values.
    Real names, real-sounding titles, plausible numbers, dates spread over time. Absolutely no
    "示例1 / 示例2", no lorem ipsum, no repeated filler.
  - Content must be immediately useful on first launch, before the user has entered anything.
  - Include at least one view with quantitative data suitable for an inline SVG chart.

Return only the JSON object.
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
    "data.js": """\
Write `data.js` -- the application's seed content.

Requirements:
  - Assign one global: `window.APP_DATA = {{ ... }}`. No imports, no exports.
  - Include every collection from the plan's "data" object, with AT LEAST 10 entries each,
    keeping the realistic specificity from the plan (expand it further where it helps).
  - Include an `app` key with name, tagline and any static copy the UI needs.
  - Values must be JSON-safe: strings, numbers, booleans, arrays, plain objects. No functions.
  - Dates as 'YYYY-MM-DD' strings. Numbers as numbers, not strings.

Output only JavaScript. No markdown fences, no commentary.
""",
    "index.html": """\
Write `index.html` -- the application shell.

Requirements:
  - <!doctype html>, <html lang="{language}">, and
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover,
    user-scalable=no">.
  - <meta name="color-scheme" content="light dark">.
  - Link `styles.css` in <head>; load `data.js` then `app.js` with plain <script> tags at the end
    of <body> (data.js first -- app.js depends on window.APP_DATA).
  - Markup for the full shell: header, one <section class="view" id="view-{{id}}"> per planned view,
    and the bottom tab bar with an inline SVG icon per tab when the app is tabbed.
  - Write the static structure of every section from the plan. Lists and grids that are populated
    from data get an empty container with a stable id that app.js fills.
  - All icons inline SVG with stroke="currentColor". Semantic landmarks and aria-labels throughout.

Output only HTML. No markdown fences, no commentary.
""",
    "app.js": """\
Write `app.js` -- all application behaviour.

Requirements:
  - Plain script, no imports/exports. Wrap in an IIFE and read from `window.APP_DATA`.
  - Render every data-driven list, grid, stat and detail section declared in index.html.
    Build nodes with document.createElement or set textContent -- never innerHTML with
    interpolated data.
  - Implement view switching for the tab bar, including the active tab state and
    restoring scroll position per view.
  - Implement every behaviour in the plan's "interactions": filtering, sorting, search,
    toggling, detail drill-down, form handling -- whatever the plan lists.
  - Persist user-modified state to localStorage under one namespaced key, and restore it on load
    inside a try/catch so a storage failure never blanks the app.
  - Draw the planned chart as inline SVG generated in JS from the data. No chart library.
  - Guard every DOM lookup: if an element is absent, skip that feature rather than throwing.
  - Wrap initialisation in try/catch and log failures to console.error.

Output only JavaScript. No markdown fences, no commentary.
""",
}


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class WebAppGenerator:
    """Produce a complete offline web application from a brief."""

    def __init__(self, *, model: str | None = None, max_tokens: int = 16000) -> None:
        self._model = model or get_llm_model()
        self._max_tokens = max_tokens

    async def generate(self, spec: WebAppSpec) -> dict[str, str]:
        """Return ``{relative_path: content}`` ready for the rawfile directory."""
        plan = await self.plan(spec)
        assets = await self.generate_files(spec, plan)
        return assets

    # -- phase 1 -----------------------------------------------------------

    async def plan(self, spec: WebAppSpec) -> dict[str, Any]:
        """Ask the model for the design system and content plan."""
        view_count = max(3, min(6, len(spec.pages) or 4))
        prompt = PLAN_PROMPT.format(
            app_name=spec.app_name,
            description=spec.description or spec.app_name,
            target_users=spec.target_users or "普通中文用户",
            features="; ".join(spec.features) if spec.features else "由你根据描述推导",
            pages="; ".join(spec.pages) if spec.pages else "由你规划",
            design_notes=spec.design_notes or "无",
            design_rules=DESIGN_SYSTEM_RULES,
            view_count=view_count,
        )
        logger.info("Planning web app '%s' (model=%s)", spec.app_name, self._model)
        raw = await acomplete(prompt, max_tokens=self._max_tokens, model=self._model)
        plan = _parse_json_object(raw)
        if not plan.get("views"):
            raise WebAppGenerationError(f"Plan for {spec.app_name!r} contained no views; model returned: {raw[:400]}")
        logger.info(
            "Planned %d view(s), %d data collection(s) for '%s'",
            len(plan.get("views", [])),
            len(plan.get("data", {})),
            spec.app_name,
        )
        return plan

    # -- phase 2 -----------------------------------------------------------

    async def generate_files(self, spec: WebAppSpec, plan: Mapping[str, Any]) -> dict[str, str]:
        """Generate, validate and repair every asset file."""
        plan_json = json.dumps(plan, ensure_ascii=False, indent=2)
        assets: dict[str, str] = {}

        for filename in ASSET_FILES:
            content = await self._generate_file(spec, plan_json, filename, assets)
            content = await self._repair_until_valid(spec, plan_json, filename, content, assets)
            assets[filename] = content

        problems = validate_assets(assets) + syntax_check_js(assets)
        if problems:
            # Cross-file issues (a missing script tag, a dangling reference) are
            # reported rather than silently shipped -- the caller decides whether
            # to retry the whole app.
            raise WebAppGenerationError("Generated web assets failed validation:\n  - " + "\n  - ".join(problems))
        logger.info("Generated %d web asset file(s) for '%s'", len(assets), spec.app_name)
        return assets

    async def _generate_file(
        self,
        spec: WebAppSpec,
        plan_json: str,
        filename: str,
        done: Mapping[str, str],
    ) -> str:
        instruction = FILE_PROMPTS[filename].format(language=spec.language)
        prompt = (
            f"APP: {spec.app_name}\n"
            f"PLAN (authoritative -- follow it exactly):\n{plan_json}\n\n"
            f"{DESIGN_SYSTEM_RULES}\n"
            f"{_context_block(done)}\n"
            f"{instruction}"
        )
        try:
            raw = await acomplete(prompt, max_tokens=self._max_tokens, model=self._model)
        except LLMError as exc:
            raise WebAppGenerationError(f"LLM failed generating {filename}: {exc}") from exc
        return strip_code_fence(raw)

    async def _repair_until_valid(
        self,
        spec: WebAppSpec,
        plan_json: str,
        filename: str,
        content: str,
        done: Mapping[str, str],
    ) -> str:
        """Feed per-file defects back to the model until clean or out of rounds."""
        for attempt in range(1, MAX_REPAIR_ROUNDS + 1):
            problems = validate_file(filename, content)
            if not problems:
                return content
            logger.warning(
                "%s failed validation (round %d/%d): %s",
                filename,
                attempt,
                MAX_REPAIR_ROUNDS,
                "; ".join(problems),
            )
            prompt = (
                f"The file `{filename}` you produced for app {spec.app_name!r} has defects that "
                f"break it inside the packaged offline app:\n\n"
                + "\n".join(f"  - {p}" for p in problems)
                + f"\n\nPLAN:\n{plan_json}\n\n{DESIGN_SYSTEM_RULES}\n"
                f"{_context_block(done)}\n"
                f"Here is the current file:\n\n{content}\n\n"
                f"Rewrite `{filename}` in full, fixing every defect and keeping everything else "
                f"intact. Output only the file content, no fences, no commentary."
            )
            try:
                content = strip_code_fence(await acomplete(prompt, max_tokens=self._max_tokens, model=self._model))
            except LLMError as exc:
                raise WebAppGenerationError(f"LLM failed repairing {filename}: {exc}") from exc

        remaining = validate_file(filename, content)
        if remaining:
            raise WebAppGenerationError(
                f"{filename} still invalid after {MAX_REPAIR_ROUNDS} repair round(s): " + "; ".join(remaining)
            )
        return content


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
        problems.append("does not assign window.APP_DATA, which app.js reads.")

    if filename == "app.js" and "APP_DATA" not in content:
        problems.append("never reads window.APP_DATA, so no content would render.")

    if filename == "index.html":
        lowered = content.lower()
        if "<!doctype html" not in lowered:
            problems.append("is missing the <!doctype html> declaration.")
        for required, why in (
            ("styles.css", "the stylesheet is never linked"),
            ("data.js", "seed content is never loaded"),
            ("app.js", "application logic is never loaded"),
        ):
            if required not in content:
                problems.append(f"does not reference {required} -- {why}.")
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
        # Every id app.js targets should exist in the markup; a mismatch is the
        # most common cause of a blank screen inside the packaged app.
        js_ids = set(re.findall(r"getElementById\(\s*['\"]([^'\"]+)['\"]", assets.get("app.js", "")))
        html_ids = set(re.findall(r"""\bid\s*=\s*['"]([^'"]+)['"]""", html))
        missing = sorted(js_ids - html_ids)
        if missing:
            problems.append("app.js looks up element id(s) absent from index.html: " + ", ".join(missing[:8]))
    return problems


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def strip_code_fence(text: str) -> str:
    """Remove a wrapping markdown fence the model may have added anyway."""
    match = _FENCE_RE.match(text.strip())
    return (match.group(1) if match else text).strip() + "\n"


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


def _context_block(done: Mapping[str, str], max_chars: int = 6000) -> str:
    """Abbreviated already-generated files, so later files stay consistent."""
    if not done:
        return ""
    parts = ["ALREADY GENERATED FILES (match their conventions, class names and ids exactly):"]
    for name, content in done.items():
        body = content if len(content) <= max_chars else content[:max_chars] + "\n/* ... truncated ... */"
        parts.append(f"\n----- {name} -----\n{body}")
    return "\n".join(parts) + "\n"


def asset_summary(assets: Mapping[str, str]) -> str:
    """One-line size summary, used in logs and Dashboard events."""
    return ", ".join(f"{name} {len(content) // 1024 or 1}KB" for name, content in assets.items())


def iter_asset_paths(assets: Mapping[str, str]) -> Iterable[str]:
    return assets.keys()
