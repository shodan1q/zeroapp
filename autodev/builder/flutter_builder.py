"""Manage the Flutter build lifecycle.

Every public method is async and shells out to the Flutter / Dart CLI via
``asyncio.create_subprocess_exec``.  All calls capture stdout/stderr and
enforce a configurable timeout.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

from autodev.config import get_settings

logger = logging.getLogger(__name__)

# Default subprocess timeouts (seconds).
_TIMEOUT_SHORT = 120       # pub get, analyze
_TIMEOUT_MEDIUM = 300      # build_runner, tests
_TIMEOUT_BUILD = 900       # APK / AAB / IPA builds
_TIMEOUT_CREATE = 60       # flutter create


@dataclass
class BuildResult:
    """Structured result from any builder operation."""

    success: bool
    command: str = ""
    stdout: str = ""
    stderr: str = ""
    errors: List[str] = field(default_factory=list)
    artifact_path: Optional[str] = None
    return_code: int = -1

    @property
    def output(self) -> str:
        """Combined stdout + stderr for convenience."""
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(self.stderr)
        return "\n".join(parts)


class FlutterBuilder:
    """High-level wrapper around the Flutter / Dart CLI."""

    def __init__(self, flutter_path: Optional[str] = None) -> None:
        if flutter_path:
            self._flutter = flutter_path
        else:
            settings = get_settings()
            candidate = settings.flutter_sdk_path / "bin" / "flutter"
            self._flutter = str(candidate) if candidate.exists() else "flutter"
        self._dart = self._flutter.replace("flutter", "dart")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run(
        self,
        args: Sequence[str],
        *,
        cwd: Optional[str] = None,
        timeout: float = _TIMEOUT_SHORT,
        label: str = "",
    ) -> BuildResult:
        """Execute a subprocess and return a :class:`BuildResult`."""
        cmd_str = " ".join(args)
        label = label or cmd_str
        logger.info("Running: %s (cwd=%s, timeout=%ss)", label, cwd, timeout)

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.error("Command timed out after %ss: %s", timeout, label)
            try:
                proc.kill()  # type: ignore[union-attr]
            except Exception:
                pass
            return BuildResult(
                success=False,
                command=cmd_str,
                errors=[f"Timed out after {timeout}s"],
            )
        except FileNotFoundError:
            msg = f"Executable not found: {args[0]}"
            logger.error(msg)
            return BuildResult(success=False, command=cmd_str, errors=[msg])

        stdout = stdout_bytes.decode(errors="replace")
        stderr = stderr_bytes.decode(errors="replace")
        rc = proc.returncode or 0
        success = rc == 0

        if not success:
            logger.warning("Command failed (rc=%d): %s", rc, label)

        return BuildResult(
            success=success,
            command=cmd_str,
            stdout=stdout,
            stderr=stderr,
            return_code=rc,
            errors=[] if success else [f"Exit code {rc}"],
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ensure_flutter(self) -> BuildResult:
        """Verify that Flutter is installed and return its version string."""
        result = await self._run(
            [self._flutter, "--version"],
            label="flutter --version",
        )
        if result.success:
            logger.info(
                "Flutter OK: %s",
                result.stdout.splitlines()[0] if result.stdout else "",
            )
        return result

    async def create_project(
        self,
        demand_id: str,
        app_name: str,
        *,
        output_dir: Optional[str] = None,
    ) -> BuildResult:
        """Run ``flutter create`` with a proper org name.

        The project directory will be placed under ``output_dir`` (defaults
        to ``settings.generated_apps_dir``).  Returns a :class:`BuildResult`
        whose ``artifact_path`` points to the created project directory.
        """
        settings = get_settings()
        dest = Path(output_dir) if output_dir else settings.generated_apps_dir

        # Sanitise app_name to a valid Dart package name.
        pkg_name = self._sanitise_package_name(app_name)
        org = f"com.autodev.{demand_id[:12].lower()}"
        project_path = dest / pkg_name

        if project_path.exists():
            logger.warning(
                "Project directory already exists, removing: %s", project_path
            )
            shutil.rmtree(project_path)

        result = await self._run(
            [
                self._flutter,
                "create",
                "--org", org,
                "--project-name", pkg_name,
                str(project_path),
            ],
            timeout=_TIMEOUT_CREATE,
            label=f"flutter create {pkg_name}",
        )
        if result.success:
            result.artifact_path = str(project_path)
        return result

    async def pub_get(self, project_path: str) -> BuildResult:
        """Run ``flutter pub get`` in *project_path*."""
        return await self._run(
            [self._flutter, "pub", "get"],
            cwd=project_path,
            label="flutter pub get",
        )

    async def build_runner(self, project_path: str) -> BuildResult:
        """Run ``dart run build_runner build --delete-conflicting-outputs``."""
        return await self._run(
            [
                self._dart,
                "run",
                "build_runner",
                "build",
                "--delete-conflicting-outputs",
            ],
            cwd=project_path,
            timeout=_TIMEOUT_MEDIUM,
            label="build_runner build",
        )

    async def run_tests(self, project_path: str) -> BuildResult:
        """Run ``flutter test`` and return the result."""
        return await self._run(
            [self._flutter, "test"],
            cwd=project_path,
            timeout=_TIMEOUT_MEDIUM,
            label="flutter test",
        )

    async def analyze(self, project_path: str) -> BuildResult:
        """Run ``dart analyze`` and parse errors from the output.

        Returns a :class:`BuildResult` whose ``errors`` list contains each
        individual error line reported by the analyzer.
        """
        result = await self._run(
            [self._dart, "analyze", "--fatal-infos"],
            cwd=project_path,
            label="dart analyze",
        )
        if not result.success:
            error_lines: List[str] = []
            for line in (result.stdout + "\n" + result.stderr).splitlines():
                stripped = line.strip()
                if stripped and any(
                    marker in stripped.lower()
                    for marker in ("error ", "warning ", "info ")
                ):
                    error_lines.append(stripped)
            if error_lines:
                result.errors = error_lines
        return result

    async def build_apk(self, project_path: str) -> BuildResult:
        """Build a release APK (``flutter build apk --release``)."""
        result = await self._run(
            [self._flutter, "build", "apk", "--release"],
            cwd=project_path,
            timeout=_TIMEOUT_BUILD,
            label="flutter build apk",
        )
        if result.success:
            apk = (
                Path(project_path)
                / "build" / "app" / "outputs" / "flutter-apk" / "app-release.apk"
            )
            if apk.exists():
                result.artifact_path = str(apk)
        return result

    async def build_appbundle(self, project_path: str) -> BuildResult:
        """Build a release AAB (``flutter build appbundle --release``)."""
        result = await self._run(
            [self._flutter, "build", "appbundle", "--release"],
            cwd=project_path,
            timeout=_TIMEOUT_BUILD,
            label="flutter build appbundle",
        )
        if result.success:
            aab = (
                Path(project_path)
                / "build" / "app" / "outputs" / "bundle" / "release"
                / "app-release.aab"
            )
            if aab.exists():
                result.artifact_path = str(aab)
        return result

    async def build_ipa(self, project_path: str) -> BuildResult:
        """Build a release IPA (``flutter build ipa --release``)."""
        result = await self._run(
            [self._flutter, "build", "ipa", "--release"],
            cwd=project_path,
            timeout=_TIMEOUT_BUILD,
            label="flutter build ipa",
        )
        if result.success:
            ipa_dir = Path(project_path) / "build" / "ios" / "ipa"
            if ipa_dir.exists():
                ipas = list(ipa_dir.glob("*.ipa"))
                if ipas:
                    result.artifact_path = str(ipas[0])
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitise_package_name(name: str) -> str:
        """Convert a human-friendly app name to a valid Dart package name.

        Rules: lowercase, underscores only, must start with a letter,
        no consecutive underscores.
        """
        clean = name.lower().strip()
        clean = re.sub(r"[^a-z0-9]", "_", clean)
        clean = re.sub(r"_+", "_", clean).strip("_")
        if not clean or not clean[0].isalpha():
            clean = "app_" + clean
        return clean[:64]
