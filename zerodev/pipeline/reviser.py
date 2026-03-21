"""App revision module -- modifies existing generated apps via Claude."""

import asyncio
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from zerodev.config import get_settings

logger = logging.getLogger(__name__)


class AppReviser:
    """Revise an existing Flutter app project using Claude."""

    async def revise(self, app_dir: str, instruction: str) -> dict:
        """
        Read the app's main.dart (and other key files), send to Claude
        with the revision instruction, apply changes, analyze, commit and push.

        Args:
            app_dir: Path to the Flutter project directory
            instruction: What to change/fix (natural language)

        Returns:
            dict with status, changes_made, errors
        """
        settings = get_settings()
        app_path = Path(app_dir)

        if not app_path.exists():
            return {"status": "error", "message": f"Directory not found: {app_dir}"}

        # Step 1: Read existing code files
        code_files: dict[str, str] = {}
        lib_dir = app_path / "lib"
        if lib_dir.exists():
            for dart_file in lib_dir.rglob("*.dart"):
                rel_path = dart_file.relative_to(app_path)
                code_files[str(rel_path)] = dart_file.read_text(encoding="utf-8")

        # Also read pubspec.yaml
        pubspec = app_path / "pubspec.yaml"
        if pubspec.exists():
            code_files["pubspec.yaml"] = pubspec.read_text(encoding="utf-8")

        if not code_files:
            return {"status": "error", "message": "No source files found"}

        # Step 2: Build context for Claude
        files_context = ""
        for path, content in code_files.items():
            files_context += f"\n--- {path} ---\n{content}\n"

        # Step 3: Call Claude for revision
        from zerodev.llm import get_claude_async_client

        client = get_claude_async_client()

        system_prompt = (
            "You are a Flutter code modifier. You are given existing Flutter project files and a modification request. "
            "Apply the requested changes and return ALL modified files. "
            "For each file, output in this exact format:\n"
            "===FILE: path/to/file.dart===\n"
            "<complete file content>\n"
            "===END===\n\n"
            "Rules:\n"
            "- Only output files that need changes\n"
            "- Output the COMPLETE file content, not just the diff\n"
            "- Target Dart 2.19 / Flutter 3.7+ (no super parameters, no records, no patterns, no sealed classes)\n"
            "- useMaterial3: false, no colorSchemeSeed\n"
            "- No emoji anywhere\n"
            "- If the instruction asks to add a dependency, also output the modified pubspec.yaml\n"
            "- Make minimal changes - don't rewrite code that doesn't need changing\n"
        )

        user_prompt = (
            f"Current project files:\n{files_context}\n\n"
            f"Modification request:\n{instruction}\n\n"
            "Apply the changes and output all modified files."
        )

        os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")

        resp = await client.messages.create(
            model=settings.claude_model,
            max_tokens=16384,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        response_text = resp.content[0].text.strip()

        # Step 4: Parse response and write files
        file_pattern = r"===FILE:\s*(.+?)===\n(.*?)===END==="
        matches = re.findall(file_pattern, response_text, re.DOTALL)

        if not matches:
            # Try alternative format (```dart blocks with file headers)
            alt_pattern = r"(?:^|\n)(?:#+\s*)?`?([^\n`]+\.(?:dart|yaml))`?\s*\n```(?:dart|yaml)?\n(.*?)```"
            matches = re.findall(alt_pattern, response_text, re.DOTALL)

        if not matches:
            return {
                "status": "error",
                "message": "Could not parse Claude's response into file changes",
                "raw_response": response_text[:500],
            }

        changes_made = []
        for file_path, content in matches:
            file_path = file_path.strip()
            content = content.strip()

            full_path = app_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content + "\n", encoding="utf-8")
            changes_made.append(file_path)
            logger.info("Updated: %s", file_path)

        # Step 5: Run flutter analyze
        proc = await asyncio.create_subprocess_exec(
            "flutter",
            "analyze",
            cwd=str(app_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        analyze_output = stdout.decode() + stderr.decode()
        analyze_ok = "No issues found" in analyze_output or proc.returncode == 0

        # Step 6: Commit and push
        env = {
            **os.environ,
            "GIT_TERMINAL_PROMPT": "0",
            "NO_PROXY": "127.0.0.1,localhost",
        }

        commit_msg = f"refine: {instruction[:80]}"
        for cmd in [
            ["git", "add", "-A"],
            ["git", "commit", "-m", commit_msg],
            ["git", "push"],
        ]:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(app_path),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()

        return {
            "status": "success",
            "changes_made": changes_made,
            "analyze_ok": analyze_ok,
            "analyze_output": analyze_output[-500:] if not analyze_ok else "No issues",
            "instruction": instruction,
        }
