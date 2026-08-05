"""End-to-end factory for WebView-shell HarmonyOS apps.

One call takes a product brief and returns an installable ``.hap``:

    brief -> web assets (LLM) -> ArkTS project -> hvigor build -> AppGallery

This is the track the unattended daemon drives. It is deliberately independent
of the Flutter LangGraph pipeline: the WebView app has no Dart compilation step,
no plugin resolution and no per-platform plugin ports, which is what makes it
reliable enough to run without a human watching.

Every stage records into :class:`WebviewAppResult` so a failure says which stage
broke and with what, rather than surfacing a bare exception.
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import logging
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zerodev.builder.ohos_builder import (
    OhosBuilder,
    OhosSigningConfig,
    OhosToolchainError,
)
from zerodev.builder.publisher import AppInfo, HarmonyOSPublisher, PublishResult
from zerodev.config import get_settings
from zerodev.generator.ohos_project import (
    OhosAppSpec,
    make_bundle_name,
    scaffold_ohos_project,
    slugify_bundle_segment,
)
from zerodev.generator.webapp_generator import (
    WebAppGenerationError,
    WebAppGenerator,
    WebAppSpec,
    asset_summary,
)

logger = logging.getLogger(__name__)

STAGES = ("generate", "scaffold", "build", "publish")


@dataclass
class WebviewAppRequest:
    """What to build."""

    app_name: str
    description: str
    features: list[str] = field(default_factory=list)
    pages: list[str] = field(default_factory=list)
    target_users: str = ""
    design_notes: str = ""
    # Latin slug used for the bundle name and workspace directory. Derived from
    # app_name when omitted, which only works for latin names -- pass one
    # explicitly for Chinese app names.
    slug: str = ""
    theme_color: str = "#0A84FF"
    version_name: str = "1.0.0"
    version_code: int = 1000000
    build_mode: str = "release"
    immersive: bool = False
    publish: bool = False

    def resolved_slug(self) -> str:
        if self.slug:
            return slugify_bundle_segment(self.slug)
        candidate = slugify_bundle_segment(self.app_name, fallback="")
        if candidate and candidate != "app":
            return candidate
        # A CJK app_name slugifies to nothing usable. Derive a digest instead of
        # using hash(), which is salted per process and would send every rerun
        # of the same app to a different workspace directory.
        digest = hashlib.sha1(self.app_name.encode("utf-8")).hexdigest()[:8]
        return f"app{digest}"


@dataclass
class StageRecord:
    name: str
    ok: bool
    seconds: float
    detail: str = ""

    def render(self) -> str:
        mark = "ok" if self.ok else "FAILED"
        return f"[{mark}] {self.name} ({self.seconds:.1f}s)" + (f" -- {self.detail}" if self.detail else "")


@dataclass
class WebviewAppResult:
    """Everything one factory run produced."""

    request: WebviewAppRequest
    started_at: datetime.datetime
    stages: list[StageRecord] = field(default_factory=list)
    project_path: str = ""
    assets: dict[str, str] = field(default_factory=dict)
    hap_path: str = ""
    publish_result: PublishResult | None = None
    # Objective signals the supervisor scores on: what the runtime harness
    # counted, whether it passed, and how large the result is.
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    @property
    def success(self) -> bool:
        return not self.error and all(s.ok for s in self.stages)

    @property
    def failed_stage(self) -> str:
        for stage in self.stages:
            if not stage.ok:
                return stage.name
        return ""

    def render(self) -> str:
        lines = [f"{self.request.app_name} ({self.request.resolved_slug()})"]
        lines += [f"  {s.render()}" for s in self.stages]
        if self.hap_path:
            lines.append(f"  artifact: {self.hap_path}")
        if self.error:
            lines.append(f"  error: {self.error}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_name": self.request.app_name,
            "slug": self.request.resolved_slug(),
            "started_at": self.started_at.isoformat(),
            "success": self.success,
            "failed_stage": self.failed_stage,
            "project_path": self.project_path,
            "hap_path": self.hap_path,
            "assets": sorted(self.assets),
            "metrics": self.metrics,
            "stages": [
                {"name": s.name, "ok": s.ok, "seconds": round(s.seconds, 2), "detail": s.detail} for s in self.stages
            ],
            "publish": (
                {"success": self.publish_result.success, "message": self.publish_result.message}
                if self.publish_result
                else None
            ),
            "error": self.error,
        }


class _Stopwatch:
    """Time one stage and append its record."""

    def __init__(self, result: WebviewAppResult, name: str) -> None:
        self._result = result
        self._name = name

    def __enter__(self) -> _Stopwatch:
        self._start = time.monotonic()
        self.detail = ""
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        elapsed = time.monotonic() - self._start
        ok = exc_type is None
        detail = self.detail if ok else f"{exc_type.__name__}: {exc}"
        self._result.stages.append(StageRecord(self._name, ok, elapsed, str(detail)[:500]))
        return False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


async def create_webview_app(
    request: WebviewAppRequest,
    *,
    workspace: str | Path | None = None,
    build: bool = True,
    generator: WebAppGenerator | None = None,
) -> WebviewAppResult:
    """Run the full factory for one app and return a structured result.

    Stages stop at the first failure; everything completed up to that point is
    preserved on disk so a retry can inspect or reuse it.
    """
    result = WebviewAppResult(request=request, started_at=datetime.datetime.now(datetime.UTC))
    slug = request.resolved_slug()
    root = Path(workspace) if workspace else get_settings().base_dir / "workspace"
    project_path = (root / f"{slug}_ohos").resolve()
    result.project_path = str(project_path)

    # -- 1. web assets -----------------------------------------------------
    icon_spec: Any = None
    try:
        with _Stopwatch(result, "generate") as watch:
            gen = generator or WebAppGenerator()
            web_spec = WebAppSpec(
                app_name=request.app_name,
                description=request.description,
                features=request.features,
                pages=request.pages,
                target_users=request.target_users,
                design_notes=request.design_notes,
            )
            # The two phases are explicit here (rather than gen.generate()) so
            # the icon design can run concurrently with the asset fan-out --
            # both only need the plan.
            plan = await gen.plan(web_spec)
            assets, icon_spec = await asyncio.gather(
                gen.generate_files(web_spec, plan),
                gen.design_icon(web_spec, plan),
            )
            result.assets = assets
            result.metrics = _collect_metrics(gen, assets)
            watch.detail = asset_summary(assets)
    except (WebAppGenerationError, RuntimeError) as exc:
        result.error = f"web asset generation failed: {exc}"
        return result

    # -- 2. ArkTS project --------------------------------------------------
    try:
        with _Stopwatch(result, "scaffold") as watch:
            spec = OhosAppSpec(
                app_name=request.app_name,
                bundle_name=make_bundle_name(slug),
                description=request.description,
                version_name=request.version_name,
                version_code=request.version_code,
                theme_color=request.theme_color,
                immersive=request.immersive,
                icon_spec=icon_spec,
            )
            scaffold_ohos_project(project_path, spec, result.assets)
            watch.detail = f"bundle {spec.bundle_name}"
    except (RuntimeError, OSError) as exc:
        result.error = f"project scaffold failed: {exc}"
        return result

    if not build:
        return result

    # -- 3. hvigor build ---------------------------------------------------
    try:
        with _Stopwatch(result, "build") as watch:
            builder = OhosBuilder()
            build_result = await builder.build_from_scratch(
                project_path,
                build_mode=request.build_mode,
                signing=OhosSigningConfig.from_settings(),
            )
            if not build_result.success:
                raise RuntimeError("; ".join(build_result.errors[:5]) or "hvigor build failed")
            result.hap_path = build_result.artifact_path or ""
            result.metrics["hap_bytes"] = Path(result.hap_path).stat().st_size if result.hap_path else 0
            watch.detail = Path(result.hap_path).name if result.hap_path else ""
    except OhosToolchainError as exc:
        result.error = str(exc)
        return result
    except RuntimeError as exc:
        result.error = f"HarmonyOS build failed: {exc}"
        return result

    # -- 4. publish --------------------------------------------------------
    if request.publish:
        try:
            with _Stopwatch(result, "publish") as watch:
                publisher = HarmonyOSPublisher()
                publish_result = await publisher.publish(
                    str(project_path),
                    AppInfo(
                        package_name=make_bundle_name(slug),
                        app_name=request.app_name,
                        version_name=request.version_name,
                        version_code=request.version_code,
                        short_description=request.description[:80],
                        full_description=request.description,
                        default_language="zh-CN",
                    ),
                )
                result.publish_result = publish_result
                watch.detail = publish_result.message[:200]
                if not publish_result.success:
                    # Raised so the stopwatch records a failed stage; caught
                    # below because the .hap itself is built and valid -- only
                    # the store step did not complete.
                    raise _PublishIncompleteError(publish_result.message)
        except _PublishIncompleteError as exc:
            logger.warning("Publish did not complete for %s: %s", request.app_name, exc)

    return result


class _PublishIncompleteError(RuntimeError):
    """Store upload did not finish; the built artifact is still usable."""


def _collect_metrics(generator: Any, assets: Mapping[str, str]) -> dict[str, Any]:
    """Summarise what was actually produced, for scoring and reporting.

    Counts come from the runtime harness where possible -- it counted what the
    app really registered at boot, which is harder to fake than counting
    declarations in the plan.
    """
    report = getattr(generator, "last_runtime_report", None)
    plan = getattr(generator, "last_plan", {}) or {}
    checks = getattr(report, "checks", {}) or {}

    collections = checks.get("data_collections") or []
    metrics: dict[str, Any] = {
        "views": checks.get("views_registered") or len(plan.get("views", []) or []),
        "features": checks.get("features_registered") or len(plan.get("features", []) or []),
        "charts": checks.get("charts_registered", 0),
        "collections": len(collections) or len(plan.get("collections", []) or []),
        "records": sum(c.get("records", 0) for c in collections),
        "asset_bytes": sum(len(v.encode("utf-8")) for v in assets.values()),
        "files": len(assets),
    }
    if report is None:
        metrics["runtime_ok"] = None
    elif not getattr(report, "available", False):
        metrics["runtime_ok"] = None
        metrics["runtime_note"] = getattr(report, "skipped", "")
    else:
        metrics["runtime_ok"] = bool(getattr(report, "ok", False))
        metrics["runtime_summary"] = report.summary()
    return metrics


# ---------------------------------------------------------------------------
# Brief helpers
# ---------------------------------------------------------------------------


def request_from_demand(demand: dict[str, Any], **overrides: Any) -> WebviewAppRequest:
    """Adapt a crawler/evaluator demand dict into a factory request."""
    data: dict[str, Any] = {
        "app_name": demand.get("title") or demand.get("app_name") or "未命名应用",
        "description": demand.get("description", ""),
        "features": list(demand.get("features") or []),
        "target_users": demand.get("target_users", ""),
        "slug": demand.get("slug", ""),
    }
    data.update(overrides)
    return WebviewAppRequest(**data)


def load_requests(path: str | Path) -> list[WebviewAppRequest]:
    """Read a JSON array of briefs (the daemon's app queue file)."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("apps", [])
    requests: list[WebviewAppRequest] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        known = {f.name for f in WebviewAppRequest.__dataclass_fields__.values()}
        requests.append(WebviewAppRequest(**{k: v for k, v in entry.items() if k in known}))
    return requests


_SAFE_NAME_RE = re.compile(r"[^\w一-鿿 -]")


def safe_display_name(text: str, limit: int = 40) -> str:
    """Trim an app name to something safe for logs and filesystem paths."""
    return _SAFE_NAME_RE.sub("", text).strip()[:limit] or "App"
