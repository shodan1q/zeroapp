"""Unattended app factory: keep producing apps, around the clock.

The daemon owns the "never stops" property the pipeline needs to be useful
without a human present:

- **Never exits on one bad app.** A failed build is recorded and the loop moves
  to the next idea. Only an unrecoverable startup problem (no toolchain) stops
  it, and that is reported loudly.
- **Backs off when everything fails.** Consecutive failures grow the sleep
  between attempts, so a broken API key or an expired certificate does not burn
  the whole quota in a tight loop.
- **Never runs dry.** Ideas come from a user-editable queue file first, then
  from crawled demands, then from the model itself -- so an empty queue at 3am
  does not idle the machine.
- **Never repeats itself.** Names already built are fed back into idea
  generation and skipped on collision.
- **Is observable.** A heartbeat file and a rolling state file let the Dashboard
  (or `zerodev factory status`) see what it is doing without attaching to it.

State lives in ``data/factory/``; nothing is kept only in memory, so a restart
resumes with full history.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import json
import logging
import os
import signal
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zerodev.builder.ohos_builder import OhosToolchainError, find_toolchain
from zerodev.config import get_settings
from zerodev.llm import LLMError, acomplete
from zerodev.pipeline.webview_app import (
    WebviewAppRequest,
    WebviewAppResult,
    create_webview_app,
    load_requests,
)

logger = logging.getLogger(__name__)

_STATE_DIRNAME = "factory"
_MAX_HISTORY = 500

# Backoff schedule (seconds) indexed by consecutive-failure count.
_BACKOFF = (30, 60, 300, 900, 1800, 3600)

IDEA_PROMPT = """\
你是一位专注中文移动应用市场的产品经理。请提出 {count} 个可以做成"离线优先的 WebView 单机应用"的产品创意。

每个创意必须满足：
  - 纯本地可用，不依赖任何联网接口、账号体系或第三方服务
  - 内容型或工具型，首次打开就有丰富的内置内容可看可用
  - 面向中国用户，界面语言为简体中文
  - 三到五个清晰的功能页面

已经做过的应用（不要重复，也不要做同类换皮）：
{existing}

严格输出一个 JSON 数组，不要有任何其他文字：
[
  {{
    "app_name": "中文应用名",
    "slug": "latin_lowercase_slug",
    "description": "一句话说明这个应用解决什么问题、给谁用",
    "features": ["功能1", "功能2", "功能3", "功能4"],
    "pages": ["页面名: 用途", "页面名: 用途", "页面名: 用途"],
    "target_users": "目标用户",
    "theme_color": "#RRGGBB"
  }}
]
"""


@dataclass
class DaemonConfig:
    """Tunables for one daemon process."""

    workspace: Path | None = None
    state_dir: Path | None = None
    # Seconds to wait between successful apps. Zero means start the next one
    # immediately -- the intended "around the clock" setting.
    idle_seconds: float = 0.0
    # How many apps to build before stopping. None means forever.
    max_apps: int | None = None
    # Build .hap artifacts (off is useful for content-only iteration).
    build: bool = True
    # Submit to AppGallery. Requires AGC credentials; safe to leave on because
    # the publisher refuses to run without them.
    publish: bool = False
    # Ideas requested per model call when the queue runs dry.
    idea_batch: int = 5
    queue_file: Path | None = None

    def resolve(self) -> DaemonConfig:
        settings = get_settings()
        base = settings.base_dir
        self.workspace = Path(self.workspace) if self.workspace else base / "workspace"
        self.state_dir = Path(self.state_dir) if self.state_dir else base / "data" / _STATE_DIRNAME
        self.queue_file = Path(self.queue_file) if self.queue_file else self.state_dir / "queue.json"
        return self


@dataclass
class FactoryState:
    """Durable daemon state, mirrored to ``state.json``."""

    started_at: str = ""
    updated_at: str = ""
    running: bool = False
    current_app: str = ""
    apps_built: int = 0
    apps_failed: int = 0
    consecutive_failures: int = 0
    built_names: list[str] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    # Demand rows already turned into apps. Tracked here rather than by writing
    # demand.status, which the Flutter LangGraph pipeline owns.
    consumed_demand_ids: list[int] = field(default_factory=list)
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "running": self.running,
            "current_app": self.current_app,
            "apps_built": self.apps_built,
            "apps_failed": self.apps_failed,
            "consecutive_failures": self.consecutive_failures,
            "built_names": self.built_names[-_MAX_HISTORY:],
            "history": self.history[-_MAX_HISTORY:],
            "consumed_demand_ids": self.consumed_demand_ids[-_MAX_HISTORY:],
            "last_error": self.last_error,
        }

    @classmethod
    def load(cls, path: Path) -> FactoryState:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                state = cls()
                for key, value in data.items():
                    if hasattr(state, key):
                        setattr(state, key, value)
                return state
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not read factory state at %s (%s); starting fresh.", path, exc)
        return cls()


class AppFactoryDaemon:
    """Runs the WebView app factory continuously."""

    def __init__(self, config: DaemonConfig | None = None) -> None:
        self.config = (config or DaemonConfig()).resolve()
        assert self.config.state_dir is not None
        self.state_dir = self.config.state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.state_dir / "state.json"
        self.heartbeat_path = self.state_dir / "heartbeat"
        self.runs_dir = self.state_dir / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.state = FactoryState.load(self.state_path)
        self._stop = asyncio.Event()

    # -- lifecycle ---------------------------------------------------------

    def request_stop(self) -> None:
        """Ask the loop to finish the current app and exit."""
        logger.info("Stop requested; will exit after the current app.")
        self._stop.set()

    def install_signal_handlers(self) -> None:
        """Turn SIGINT/SIGTERM into a graceful stop, when a loop is running."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError, ValueError):
                loop.add_signal_handler(sig, self.request_stop)

    def preflight(self) -> list[str]:
        """Startup checks that would make every single run fail."""
        problems: list[str] = []
        if self.config.build:
            try:
                toolchain = find_toolchain()
                logger.info("HarmonyOS toolchain ready: SDK API %s", toolchain.api_version)
            except OhosToolchainError as exc:
                problems.append(str(exc))
        return problems

    # -- persistence -------------------------------------------------------

    def _now(self) -> str:
        return datetime.datetime.now(datetime.UTC).isoformat()

    def _save_state(self) -> None:
        self.state.updated_at = self._now()
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        # Atomic replace so a reader (Dashboard) never sees a half-written file.
        tmp.replace(self.state_path)

    def _beat(self) -> None:
        self.heartbeat_path.write_text(self._now(), encoding="utf-8")

    def _record_run(self, result: WebviewAppResult) -> None:
        stamp = result.started_at.strftime("%Y%m%d-%H%M%S")
        slug = result.request.resolved_slug()
        path = self.runs_dir / f"{stamp}-{slug}.json"
        path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

        self.state.history.append(
            {
                "at": result.started_at.isoformat(),
                "app_name": result.request.app_name,
                "slug": slug,
                "success": result.success,
                "failed_stage": result.failed_stage,
                "hap": result.hap_path,
                "error": result.error[:300],
            }
        )
        if result.success:
            self.state.apps_built += 1
            self.state.consecutive_failures = 0
            if result.request.app_name not in self.state.built_names:
                self.state.built_names.append(result.request.app_name)
        else:
            self.state.apps_failed += 1
            self.state.consecutive_failures += 1
            self.state.last_error = (result.error or result.failed_stage)[:500]
        self._save_state()

    # -- idea sourcing -----------------------------------------------------

    async def next_requests(self) -> list[WebviewAppRequest]:
        """Get the next batch of app briefs, from the best available source."""
        queued = self._drain_queue()
        if queued:
            logger.info("Took %d brief(s) from the queue file.", len(queued))
            return queued

        crawled = await self._from_demands()
        if crawled:
            logger.info("Took %d brief(s) from crawled demands.", len(crawled))
            return crawled

        generated = await self._generate_ideas(self.config.idea_batch)
        logger.info("Generated %d new idea(s) with the model.", len(generated))
        return generated

    def _drain_queue(self) -> list[WebviewAppRequest]:
        """Pop every brief from the queue file, leaving it empty."""
        path = self.config.queue_file
        if path is None or not path.exists():
            return []
        try:
            requests = load_requests(path)
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            logger.warning("Queue file %s is unreadable (%s); ignoring it.", path, exc)
            return []
        if requests:
            # Consume atomically so a concurrent editor cannot lose entries
            # silently: the drained copy is archived next to the queue.
            archive = self.state_dir / "queue-consumed.json"
            archive.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            path.write_text("[]\n", encoding="utf-8")
        return requests

    async def _from_demands(self, limit: int = 3) -> list[WebviewAppRequest]:
        """Pull approved demands the crawler/evaluator layer already scored.

        Demand rows are read but never mutated: the LangGraph Flutter pipeline
        owns their status field, so the daemon tracks what it has consumed in
        its own state instead of competing for those writes.
        """
        try:
            from sqlalchemy import select  # noqa: PLC0415

            from zerodev.database import get_async_session_factory  # noqa: PLC0415
            from zerodev.models.demand import Demand, DemandStatus  # noqa: PLC0415
            from zerodev.pipeline.webview_app import request_from_demand  # noqa: PLC0415
        except ImportError as exc:
            logger.debug("Demand source unavailable: %s", exc)
            return []

        consumed = set(self.state.consumed_demand_ids)
        try:
            factory = get_async_session_factory()
            async with factory() as session:
                rows = await session.execute(
                    select(Demand)
                    .where(Demand.status == DemandStatus.APPROVED)
                    .order_by(Demand.overall_score.desc().nulls_last())
                    .limit(limit * 4)
                )
                demands = list(rows.scalars())
        except Exception as exc:  # noqa: BLE001 - optional source, never fatal
            logger.debug("Could not read demands (%s); falling back to generated ideas.", exc)
            return []

        requests: list[WebviewAppRequest] = []
        for demand in demands:
            if demand.demand_id in consumed or len(requests) >= limit:
                continue
            self.state.consumed_demand_ids.append(demand.demand_id)
            requests.append(
                request_from_demand(
                    {
                        "title": demand.title,
                        "description": demand.description or "",
                        "features": _json_list(demand.core_features),
                        "target_users": demand.target_users or "",
                    }
                )
            )
        if requests:
            self._save_state()
        return requests

    async def _generate_ideas(self, count: int) -> list[WebviewAppRequest]:
        """Ask the model for fresh app ideas that avoid what was already built."""
        existing = self.state.built_names[-40:]
        prompt = IDEA_PROMPT.format(
            count=count,
            existing="\n".join(f"  - {name}" for name in existing) if existing else "  （暂无）",
        )
        try:
            raw = await acomplete(prompt, max_tokens=4096)
        except (LLMError, RuntimeError) as exc:
            logger.error("Idea generation failed: %s", exc)
            return []

        ideas = _parse_idea_array(raw)
        known = {name.strip() for name in self.state.built_names}
        requests: list[WebviewAppRequest] = []
        fields = {f.name for f in WebviewAppRequest.__dataclass_fields__.values()}
        for idea in ideas:
            name = str(idea.get("app_name", "")).strip()
            if not name or name in known:
                continue
            known.add(name)
            requests.append(WebviewAppRequest(**{k: v for k, v in idea.items() if k in fields}))
        return requests

    # -- main loop ---------------------------------------------------------

    async def run_forever(self) -> FactoryState:
        """Produce apps until stopped, a limit is hit, or startup fails."""
        problems = self.preflight()
        if problems:
            self.state.last_error = problems[0]
            self._save_state()
            raise OhosToolchainError("Factory cannot start:\n  - " + "\n  - ".join(problems))

        self.install_signal_handlers()
        self.state.started_at = self._now()
        self.state.running = True
        self._save_state()
        logger.info(
            "App factory started (build=%s, publish=%s, max_apps=%s).",
            self.config.build,
            self.config.publish,
            self.config.max_apps or "unlimited",
        )

        try:
            while not self._stop.is_set():
                if self.config.max_apps is not None and self.state.apps_built >= self.config.max_apps:
                    logger.info("Reached max_apps=%d; stopping.", self.config.max_apps)
                    break

                self._beat()
                requests = await self.next_requests()
                if not requests:
                    # No queue, no demands, and idea generation failed -- almost
                    # always a provider problem, so back off rather than spin.
                    self.state.consecutive_failures += 1
                    delay = self._backoff_delay()
                    logger.warning("No app briefs available; retrying in %ds.", delay)
                    self._save_state()
                    if await self._sleep(delay):
                        break
                    continue

                for request in requests:
                    if self._stop.is_set():
                        break
                    if self.config.max_apps is not None and self.state.apps_built >= self.config.max_apps:
                        break
                    await self._build_one(request)

                    if self.state.consecutive_failures:
                        delay = self._backoff_delay()
                        logger.warning(
                            "%d consecutive failure(s); backing off %ds.",
                            self.state.consecutive_failures,
                            delay,
                        )
                        if await self._sleep(delay):
                            break
                    elif self.config.idle_seconds > 0 and await self._sleep(self.config.idle_seconds):
                        break
        finally:
            self.state.running = False
            self.state.current_app = ""
            self._save_state()
            logger.info("App factory stopped. built=%d failed=%d", self.state.apps_built, self.state.apps_failed)
        return self.state

    async def _build_one(self, request: WebviewAppRequest) -> WebviewAppResult:
        """Build one app, absorbing any failure into the run record."""
        self.state.current_app = request.app_name
        self._save_state()
        self._beat()
        logger.info("Building '%s' ...", request.app_name)

        request.publish = request.publish or self.config.publish
        try:
            result = await create_webview_app(
                request,
                workspace=self.config.workspace,
                build=self.config.build,
            )
        except Exception as exc:  # noqa: BLE001 - the loop must survive anything
            logger.exception("Unhandled error building '%s'", request.app_name)
            result = WebviewAppResult(
                request=request,
                started_at=datetime.datetime.now(datetime.UTC),
                error=f"unhandled: {type(exc).__name__}: {exc}",
            )

        logger.info("%s", result.render())
        self._record_run(result)
        self.state.current_app = ""
        self._save_state()
        return result

    def _backoff_delay(self) -> int:
        index = min(self.state.consecutive_failures, len(_BACKOFF)) - 1
        return _BACKOFF[max(0, index)]

    async def _sleep(self, seconds: float) -> bool:
        """Sleep, waking early on stop. Returns True when a stop was requested."""
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        return self._stop.is_set()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _json_list(raw: Any) -> list[str]:
    """Decode a JSON-array column that may hold text, a list, or nothing."""
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if isinstance(raw, str) and raw.strip():
        with contextlib.suppress(json.JSONDecodeError):
            decoded = json.loads(raw)
            if isinstance(decoded, list):
                return [str(item) for item in decoded]
        return [part.strip() for part in raw.split(",") if part.strip()]
    return []


def _parse_idea_array(text: str) -> list[dict[str, Any]]:
    """Parse the model's JSON array of ideas, tolerating fences and prose."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("["), cleaned.rfind("]")
        if start == -1 or end <= start:
            logger.error("Idea response was not a JSON array: %s", cleaned[:300])
            return []
        try:
            payload = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            logger.error("Could not parse idea JSON: %s", exc)
            return []
    if isinstance(payload, dict):
        payload = payload.get("apps") or payload.get("ideas") or []
    return [item for item in payload if isinstance(item, dict)]


def read_state(state_dir: str | Path | None = None) -> dict[str, Any]:
    """Read the factory's state file, for the CLI and Dashboard."""
    base = Path(state_dir) if state_dir else get_settings().base_dir / "data" / _STATE_DIRNAME
    path = base / "state.json"
    if not path.exists():
        return {"running": False, "note": f"No factory state yet at {path}."}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"running": False, "error": str(exc)}

    heartbeat = base / "heartbeat"
    if heartbeat.exists():
        beat = heartbeat.read_text(encoding="utf-8").strip()
        state["heartbeat"] = beat
        with contextlib.suppress(ValueError):
            age = (datetime.datetime.now(datetime.UTC) - datetime.datetime.fromisoformat(beat)).total_seconds()
            state["heartbeat_age_seconds"] = round(age, 1)
            # A process killed with SIGKILL leaves running=true behind; the
            # heartbeat age is what actually says whether it is alive.
            state["alive"] = age < 3600
    return state


def write_queue(requests: list[dict[str, Any]], state_dir: str | Path | None = None) -> Path:
    """Append briefs to the daemon's queue file and return its path."""
    base = Path(state_dir) if state_dir else get_settings().base_dir / "data" / _STATE_DIRNAME
    base.mkdir(parents=True, exist_ok=True)
    path = base / "queue.json"
    existing: list[dict[str, Any]] = []
    if path.exists():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            loaded = json.loads(path.read_text(encoding="utf-8"))
            existing = loaded if isinstance(loaded, list) else loaded.get("apps", [])
    existing.extend(requests)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


async def run_factory(config: DaemonConfig | None = None) -> FactoryState:
    """Entry point used by the CLI and by ``python -m zerodev.pipeline.daemon``."""
    return await AppFactoryDaemon(config).run_forever()


if __name__ == "__main__":
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    asyncio.run(run_factory())
