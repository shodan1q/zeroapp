"""Auto-fix loop: run dart analyze, send errors to LLM, apply fixes.

Phase 1 - ``dart analyze`` loop (up to 5 rounds):
    Parse errors, group by file, send each file + errors to Claude, write fixes.

Phase 2 - ``flutter build apk --debug`` loop (up to 3 rounds):
    If the build fails, parse build errors and fix via Claude.
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
from pathlib import Path

import anthropic

from zerodev.config import get_settings

logger = logging.getLogger(__name__)

MAX_FIX_ITERATIONS = 5
MAX_BUILD_ITERATIONS = 3

FIX_PROMPT = """\
Fix the following Dart analysis errors in the file.

File: {file_path}
Current code:
```dart
{code}
```

Errors:
{errors}

Return ONLY the corrected Dart code, no markdown fences or explanations.

Rules:
  - Fix all reported errors while preserving functionality.
  - Do not remove features or replace code with TODOs.
  - Ensure all imports are correct package imports (not relative).
  - Target Dart 2.19 / Flutter 3.7+. Do NOT use super parameters, records, patterns, or sealed classes.
  - Constructors must use `Key? key` named parameter style with `: super(key: key)`.
  - Use Material Design 2 (useMaterial3: false). Do NOT use colorSchemeSeed / ColorScheme.fromSeed().
"""

BUILD_FIX_PROMPT = """\
The Flutter project failed to build.  Fix the errors in this file.

Build output (relevant errors):
{build_errors}

File: {file_path}
Current code:
```dart
{code}
```

Return ONLY the corrected Dart code, no markdown fences or explanations.

Rules:
  - Target Dart 2.19 / Flutter 3.7+. Do NOT use super parameters, records, patterns, or sealed classes.
  - Constructors must use `Key? key` named parameter style with `: super(key: key)`.
"""


def _strip_fences(text: str) -> str:
    """Remove markdown code fences if present."""
    text = text.strip()
    m = re.match(r"^```(?:dart)?\s*\n(.*?)```\s*$", text, re.DOTALL)
    return m.group(1).strip() if m else text


class AutoFixer:
    """Iteratively fix Dart analysis and build errors using Claude."""

    def __init__(self) -> None:
        from zerodev.llm import get_claude_client
        settings = get_settings()
        self._client = get_claude_client()
        self._model = settings.claude_model
        self._dart_bin = settings.dart_bin
        self._flutter_bin = settings.flutter_bin

    # ------------------------------------------------------------------
    # dart analyze
    # ------------------------------------------------------------------

    def run_analyze(self, project_path: Path) -> list[dict[str, str]]:
        """Run ``dart analyze`` and parse output.

        Returns:
            List of dicts with ``file``, ``line``, ``col``, ``message``,
            ``severity``, and ``code`` keys.  Only errors are returned.
        """
        try:
            result = subprocess.run(
                [self._dart_bin, "analyze", "--no-fatal-warnings", str(project_path)],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.error("dart analyze failed to run: %s", exc)
            return []

        errors: list[dict[str, str]] = []
        pattern = re.compile(
            r"(error|warning|info)\s+-\s+"
            r"([\w./\\]+):(\d+):(\d+)\s+-\s+"
            r"(.+?)\s+-\s+"
            r"(\w+)"
        )
        combined = result.stdout + "\n" + result.stderr
        for match in pattern.finditer(combined):
            severity, filepath, line, col, message, code = match.groups()
            if severity == "error":
                errors.append({
                    "file": filepath,
                    "line": line,
                    "col": col,
                    "message": message.strip(),
                    "severity": severity,
                    "code": code,
                    "raw": match.group(0),
                })

        # Fallback: also catch raw lines that mention errors.
        if not errors:
            for raw_line in combined.splitlines():
                raw_line = raw_line.strip()
                if " - " in raw_line and (".dart:" in raw_line or "error" in raw_line.lower()):
                    errors.append({"raw": raw_line, "file": "", "message": raw_line})

        return errors

    # ------------------------------------------------------------------
    # flutter build
    # ------------------------------------------------------------------

    def run_build(self, project_path: Path) -> tuple[bool, str]:
        """Run ``flutter build apk --debug``.

        Returns:
            Tuple of (success, combined_output).
        """
        try:
            result = subprocess.run(
                [self._flutter_bin, "build", "apk", "--debug"],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(project_path),
            )
        except subprocess.TimeoutExpired:
            logger.error("flutter build timed out (300s)")
            return False, "Build timed out after 300 seconds"
        except FileNotFoundError:
            logger.error("flutter binary not found at '%s'", self._flutter_bin)
            return False, f"flutter not found: {self._flutter_bin}"

        combined = result.stdout + "\n" + result.stderr
        return result.returncode == 0, combined

    def _parse_build_errors(self, output: str) -> list[dict[str, str]]:
        """Extract file-level errors from flutter build output."""
        errors: list[dict[str, str]] = []
        pattern = re.compile(r"([\w./\\]+\.dart):(\d+):(\d+):\s*(Error|Warning):\s*(.+)")
        for match in pattern.finditer(output):
            filepath, line, col, severity, message = match.groups()
            if severity == "Error":
                errors.append({
                    "file": filepath,
                    "line": line,
                    "col": col,
                    "message": message.strip(),
                })
        return errors

    # ------------------------------------------------------------------
    # Claude-assisted file fix
    # ------------------------------------------------------------------

    async def fix_file(self, file_path: Path, errors: str) -> str:
        """Send file + errors to Claude and get fixed code."""
        code = file_path.read_text(encoding="utf-8")
        response = self._client.messages.create(
            model=self._model,
            max_tokens=8192,
            messages=[
                {
                    "role": "user",
                    "content": FIX_PROMPT.format(
                        file_path=file_path.name,
                        code=code,
                        errors=errors,
                    ),
                }
            ],
        )
        return _strip_fences(response.content[0].text)

    async def _fix_build_file(self, file_path: Path, build_errors: str) -> str:
        """Send file + build errors to Claude for fixing."""
        code = file_path.read_text(encoding="utf-8")
        response = self._client.messages.create(
            model=self._model,
            max_tokens=8192,
            messages=[
                {
                    "role": "user",
                    "content": BUILD_FIX_PROMPT.format(
                        file_path=file_path.name,
                        code=code,
                        build_errors=build_errors,
                    ),
                }
            ],
        )
        return _strip_fences(response.content[0].text)

    # ------------------------------------------------------------------
    # Group errors by file
    # ------------------------------------------------------------------

    @staticmethod
    def _group_by_file(errors: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
        grouped: dict[str, list[dict[str, str]]] = {}
        for err in errors:
            fpath = err.get("file", "")
            if fpath:
                grouped.setdefault(fpath, []).append(err)
        return grouped

    # ------------------------------------------------------------------
    # Main fix loop
    # ------------------------------------------------------------------

    async def fix_loop(self, project_path: Path) -> dict:
        """Run the full analyze-fix-build loop.

        Returns:
            Dict with ``success``, ``analyze_rounds``, ``build_rounds``,
            ``errors_fixed``, ``remaining_errors``, and ``logs``.
        """
        project_path = Path(project_path).resolve()
        result: dict = {
            "success": False,
            "analyze_rounds": 0,
            "build_rounds": 0,
            "errors_fixed": 0,
            "remaining_errors": [],
            "logs": [],
        }

        # ---- Phase 1: dart analyze loop ----
        for iteration in range(1, MAX_FIX_ITERATIONS + 1):
            result["analyze_rounds"] = iteration
            log_msg = f"[analyze {iteration}/{MAX_FIX_ITERATIONS}] Running dart analyze..."
            logger.info(log_msg)
            result["logs"].append(log_msg)

            errors = self.run_analyze(project_path)
            if not errors:
                result["logs"].append(f"[analyze {iteration}] No errors found.")
                break

            log_msg = f"[analyze {iteration}] Found {len(errors)} error(s)."
            logger.info(log_msg)
            result["logs"].append(log_msg)

            grouped = self._group_by_file(errors)

            # If errors have no parseable file, try fixing main.dart as fallback.
            if not grouped and errors:
                error_text = "\n".join(e.get("raw", e.get("message", "")) for e in errors)
                main_dart = project_path / "lib" / "main.dart"
                if main_dart.exists():
                    fixed = await self.fix_file(main_dart, error_text)
                    main_dart.write_text(fixed, encoding="utf-8")
                    result["errors_fixed"] += len(errors)
                continue

            for rel_path, file_errors in grouped.items():
                full_path = project_path / rel_path
                if not full_path.exists():
                    logger.warning("Error references non-existent file: %s", rel_path)
                    continue

                error_text = "\n".join(
                    f"  Line {e.get('line', '?')}: [{e.get('code', '')}] {e.get('message', e.get('raw', ''))}"
                    for e in file_errors
                )

                try:
                    fixed = await self.fix_file(full_path, error_text)
                    full_path.write_text(fixed, encoding="utf-8")
                    result["errors_fixed"] += len(file_errors)
                    logger.info("Fixed %d error(s) in %s", len(file_errors), rel_path)
                except Exception:
                    logger.exception("Failed to fix %s", rel_path)
        else:
            # Ran out of analyze iterations - check remaining errors.
            remaining = self.run_analyze(project_path)
            if remaining:
                for e in remaining:
                    result["remaining_errors"].append(e.get("raw", e.get("message", "")))
                result["logs"].append(
                    f"Exhausted {MAX_FIX_ITERATIONS} analyze rounds; "
                    f"{len(remaining)} error(s) remain."
                )

        # ---- Phase 2: flutter build loop ----
        for iteration in range(1, MAX_BUILD_ITERATIONS + 1):
            result["build_rounds"] = iteration
            log_msg = f"[build {iteration}/{MAX_BUILD_ITERATIONS}] Running flutter build apk --debug..."
            logger.info(log_msg)
            result["logs"].append(log_msg)

            success, output = self.run_build(project_path)
            if success:
                result["success"] = True
                result["logs"].append(f"[build {iteration}] Build succeeded!")
                return result

            build_errors = self._parse_build_errors(output)
            if not build_errors:
                result["logs"].append(
                    f"[build {iteration}] Build failed but errors could not be parsed. "
                    f"Output: {output[:500]}"
                )
                result["remaining_errors"].append(f"Unparseable build failure: {output[:300]}")
                break

            log_msg = f"[build {iteration}] {len(build_errors)} build error(s) found."
            logger.info(log_msg)
            result["logs"].append(log_msg)

            grouped = self._group_by_file(build_errors)
            for rel_path, file_errors in grouped.items():
                full_path = project_path / rel_path
                if not full_path.exists():
                    logger.warning("Build error references missing file: %s", rel_path)
                    continue

                error_text = "\n".join(
                    f"  Line {e.get('line', '?')}: {e.get('message', '')}"
                    for e in file_errors
                )

                try:
                    fixed = await self._fix_build_file(full_path, error_text)
                    full_path.write_text(fixed, encoding="utf-8")
                    result["errors_fixed"] += len(file_errors)
                    logger.info("Fixed %d build error(s) in %s", len(file_errors), rel_path)
                except Exception:
                    logger.exception("Failed to fix build errors in %s", rel_path)
        else:
            result["logs"].append(f"Exhausted {MAX_BUILD_ITERATIONS} build rounds.")

        # Final build attempt.
        success, _ = self.run_build(project_path)
        result["success"] = success
        result["logs"].append("Final build succeeded." if success else "Build still failing.")

        return result
