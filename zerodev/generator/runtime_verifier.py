"""Run a generated web app for real, before anything ships it.

Every other check in this pipeline is static. ``node --check`` proves a file
parses; the cross-file id check proves the markup and the scripts agree on
names. Neither notices that ``APP.boot()`` threw on the first line and the user
is looking at a blank screen -- and nothing downstream would catch it either,
because hvigor packages a broken page exactly as happily as a working one.

So this module executes the app: it loads ``index.html`` in a headless DOM,
evaluates every script in document order, boots, and then interacts with the
result -- switching tabs, typing in the search box, opening a detail row. What
comes back is a structured report whose failures carry real stack traces, which
is what makes automatic rework possible: the model is handed the actual error
rather than a guess about what might be wrong.

The harness lives in ``tools/webverify`` because it has to be JavaScript. When
its dependency is not installed the check reports itself as skipped rather than
failing the build, so the pipeline still runs on a machine that never set it up.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

HARNESS_DIR = Path(__file__).resolve().parent.parent.parent / "tools" / "webverify"
HARNESS = HARNESS_DIR / "verify.mjs"

_TIMEOUT = 120

# A generated app is expected to fill the containers its own contract declares.
# An empty mount is the signature of a render function that silently did
# nothing, which looks identical to success in every static check.
MAX_REPORTED_PROBLEMS = 12


@dataclass
class RuntimeReport:
    """What happened when the generated app was actually executed."""

    ok: bool = False
    skipped: str = ""
    fatal: str = ""
    errors: list[dict[str, str]] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    missing_mounts: list[str] = field(default_factory=list)
    empty_mounts: list[str] = field(default_factory=list)
    checks: dict[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        """False when the harness could not run at all."""
        return not self.skipped

    def problems(self) -> list[str]:
        """Human-readable defects, phrased so the model can act on them."""
        issues: list[str] = []
        # A failing report with no listed problems would block the build with no
        # explanation, so anything fatal is surfaced first.
        if self.fatal and not self.skipped:
            issues.append(self.fatal)

        for error in self.errors:
            stage = error.get("stage", "runtime")
            message = error.get("message", "")
            stack = error.get("stack", "")
            detail = f" | {stack.splitlines()[0]}" if stack else ""
            issues.append(f"threw while running {stage}: {message}{detail}")

        for message in self.console_errors:
            issues.append(f"logged a console error at runtime: {message}")

        if not self.checks.get("app_global", True):
            issues.append("window.APP was never created, so nothing could render.")

        if self.missing_mounts:
            issues.append(
                "index.html is missing container id(s) the contract declares: " + ", ".join(self.missing_mounts[:8])
            )
        if self.empty_mounts:
            issues.append(
                "these containers were still empty after boot, so their section renders nothing: "
                + ", ".join(self.empty_mounts[:8])
            )
        if self.checks.get("boot_forced"):
            issues.append("nothing called APP.boot(); the app only rendered because the harness forced it.")

        for probe in self.checks.get("interactions", []):
            if not probe.get("ok", True):
                issues.append(f"interaction {probe.get('name')} raised an error.")

        return issues[:MAX_REPORTED_PROBLEMS]

    def summary(self) -> str:
        if self.skipped:
            return f"runtime check skipped ({self.skipped})"
        if self.fatal:
            return f"runtime check crashed: {self.fatal[:200]}"
        checks = self.checks
        records = sum(c.get("records", 0) for c in checks.get("data_collections", []))
        return (
            f"{'ok' if self.ok else 'FAILED'} -- "
            f"{checks.get('views_registered', 0)} view(s), "
            f"{checks.get('features_registered', 0)} feature(s), "
            f"{records} record(s), "
            f"{len(self.errors)} error(s)"
        )


def harness_available() -> tuple[bool, str]:
    """Whether the headless-DOM harness can run, and why not when it cannot."""
    if shutil.which("node") is None:
        return False, "node is not on PATH"
    if not HARNESS.exists():
        return False, f"harness missing at {HARNESS}"
    if not (HARNESS_DIR / "node_modules" / "jsdom").exists():
        return False, "jsdom is not installed (run: npm install --prefix tools/webverify)"
    return True, ""


def verify_assets(assets: Mapping[str, str], contract: Mapping[str, Any]) -> RuntimeReport:
    """Execute ``assets`` in a headless DOM and report what broke.

    The assets are written to a scratch directory rather than verified in place,
    so this can run before anything is committed to a project tree.
    """
    ready, reason = harness_available()
    if not ready:
        logger.info("Runtime verification unavailable: %s", reason)
        return RuntimeReport(ok=True, skipped=reason)

    with tempfile.TemporaryDirectory(prefix="zerodev-verify-") as tmp:
        root = Path(tmp)
        for name, content in assets.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        job = root / "_job.json"
        job.write_text(
            json.dumps({"dir": str(root), "contract": _minimal_contract(contract)}, ensure_ascii=False),
            encoding="utf-8",
        )

        try:
            completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
                ["node", str(HARNESS), str(job)],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
                cwd=str(HARNESS_DIR),
            )
        except subprocess.TimeoutExpired:
            return RuntimeReport(
                ok=False,
                fatal=f"the app did not finish booting within {_TIMEOUT}s (an infinite loop on startup?)",
            )
        except OSError as exc:
            return RuntimeReport(ok=True, skipped=f"could not run the harness: {exc}")

    return _parse_report(completed.stdout, completed.stderr)


def _parse_report(stdout: str, stderr: str) -> RuntimeReport:
    payload = None
    for line in reversed(stdout.strip().splitlines()):
        try:
            payload = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    if payload is None:
        return RuntimeReport(ok=True, skipped=f"harness produced no report ({(stderr or stdout)[:200]})")

    if payload.get("skipped"):
        return RuntimeReport(ok=True, skipped=str(payload["skipped"]))

    if payload.get("fatal"):
        # The harness itself broke. That is an infrastructure problem, not a
        # defect in the generated app, so it must not block the factory -- but
        # it has to be loud, because it silently disables the quality gate.
        fatal = str(payload["fatal"])
        logger.error("Runtime verification harness crashed; the quality gate is OFF: %s", fatal[:400])
        return RuntimeReport(ok=True, skipped=f"harness error: {fatal[:200]}", fatal=fatal)

    return RuntimeReport(
        ok=bool(payload.get("ok")),
        errors=[e for e in payload.get("errors", []) if isinstance(e, dict)],
        console_errors=[str(c) for c in payload.get("console_errors", [])],
        missing_mounts=[str(m) for m in payload.get("missing_mounts", [])],
        empty_mounts=[str(m) for m in payload.get("empty_mounts", [])],
        checks=payload.get("checks") or {},
    )


def _minimal_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Only the parts of the plan the harness needs, keeping the job file small."""
    views = []
    for view in contract.get("views", []) or []:
        if not isinstance(view, dict):
            continue
        sections = [
            {"mount_id": s.get("mount_id"), "collection": s.get("collection")}
            for s in view.get("sections", []) or []
            if isinstance(s, dict) and s.get("mount_id")
        ]
        views.append({"id": view.get("id"), "sections": sections})
    return {"views": views, "element_ids": list(contract.get("element_ids", []) or [])}


def attribute_problems(report: RuntimeReport, asset_names: list[str]) -> dict[str, list[str]]:
    """Group runtime defects by the file most likely responsible.

    Rework is per file, so a defect has to name one. Errors carry the script
    they were thrown from; structural failures are attributed by convention --
    a missing container is the markup's fault, an empty one is the renderer's.
    """
    by_file: dict[str, list[str]] = {}

    def add(name: str, problem: str) -> None:
        if name in asset_names:
            by_file.setdefault(name, []).append(problem)

    for error in report.errors:
        stage = str(error.get("stage", ""))
        message = error.get("message", "")
        target = stage if stage in asset_names else _stage_owner(stage, asset_names)
        add(target, f"threw at runtime ({stage}): {message}")

    for message in report.console_errors:
        add("features.js", f"logged a console error at runtime: {message}")

    if report.missing_mounts:
        add(
            "index.html",
            "is missing container id(s) the contract declares, so nothing can render into them: "
            + ", ".join(report.missing_mounts[:8]),
        )
    if report.empty_mounts:
        add(
            "views.js",
            "left these containers empty after boot -- their render functions produced nothing: "
            + ", ".join(report.empty_mounts[:8]),
        )
    if report.checks.get("boot_forced"):
        add("features.js", "never called APP.boot(), so the app would never render on its own.")

    for probe in report.checks.get("interactions", []):
        if not probe.get("ok", True):
            add("features.js", f"interaction {probe.get('name')} raised an error.")

    return by_file


def _stage_owner(stage: str, asset_names: list[str]) -> str:
    """Map a non-file stage label onto the file that owns that behaviour."""
    if stage in ("APP.boot()", "lifecycle", "promise") or stage.startswith(("tab:", "search", "detail")):
        return "features.js" if "features.js" in asset_names else "app.js"
    return "core.js" if "core.js" in asset_names else "app.js"
