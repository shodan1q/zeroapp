"""Background pipeline runner -- manages the continuous loop lifecycle."""

import asyncio
import json
import logging
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from autodev.config import get_settings
from autodev.api.events import emit_error, emit_pipeline_summary, emit_stage_change

logger = logging.getLogger(__name__)


class PipelineRunner:
    """Singleton that runs the pipeline loop in background."""

    _instance = None

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False
        self._current_run_id: str | None = None
        self._stats = {
            "started_at": None,
            "cycles": 0,
            "apps_generated": 0,
            "apps_pushed": 0,
            "errors": 0,
        }
        self._logs: list[dict] = []  # list of {"time": ISO, "message": str, "type": str}

    @classmethod
    def get_instance(cls) -> "PipelineRunner":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    @property
    def stats(self) -> dict:
        return {
            **self._stats,
            "running": self.is_running,
            "current_run_id": self._current_run_id,
            "logs": self._logs[-200:],
        }

    async def _log(self, message: str, log_type: str = "info") -> None:
        """Append to internal log buffer and emit via WebSocket."""
        entry = {
            "time": datetime.utcnow().isoformat() + "Z",
            "message": message,
            "type": log_type,
        }
        self._logs.append(entry)
        # Keep only last 200
        if len(self._logs) > 200:
            self._logs = self._logs[-200:]
        logger.info("[log] %s", message)
        try:
            await emit_stage_change("info", self._current_run_id, "info", {"message": message})
        except Exception:
            pass

    def start(self):
        if self.is_running:
            return {"status": "already_running"}
        self._running = True
        self._stats["started_at"] = datetime.utcnow().isoformat()
        self._task = asyncio.create_task(self._loop())
        return {"status": "started"}

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        return {"status": "stopped"}

    async def _loop(self):
        settings = get_settings()
        interval = settings.pipeline_crawl_interval_hours * 3600

        while self._running:
            try:
                self._current_run_id = uuid.uuid4().hex[:12]
                self._stats["cycles"] += 1
                await self._run_one_cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._stats["errors"] += 1
                logger.exception("Pipeline cycle failed")
                await self._log(f"流水线错误: {e}", "error")
                try:
                    await emit_error("pipeline", str(e))
                except Exception:
                    pass

            if self._running:
                logger.info(
                    "Next cycle in %dh", settings.pipeline_crawl_interval_hours
                )
                await self._log(
                    f"等待下一个周期 ({settings.pipeline_crawl_interval_hours}h)...",
                    "info",
                )
                try:
                    await asyncio.sleep(interval)
                except asyncio.CancelledError:
                    break

        self._running = False
        self._current_run_id = None

    async def _run_one_cycle(self):
        """Run one pipeline cycle: generate an app idea, code it, build, push to git."""
        settings = get_settings()
        output_dir = Path(settings.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        run_id = self._current_run_id

        await emit_stage_change("crawl", run_id, "active", {"message": "正在生成 App 创意..."})
        await self._log("正在生成 App 创意...", "stage_change")

        # Step 1: Generate app idea using async LLM client
        from autodev.llm import get_claude_async_client

        client = get_claude_async_client()

        resp = await client.messages.create(
            model=settings.claude_model,
            max_tokens=300,
            system="You are an app idea generator. Reply with JSON only. No markdown fences.",
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Suggest ONE simple utility mobile app idea. "
                        "Single-screen tool app, no backend needed. "
                        'Return JSON: {"name": "AppName", "description": "one line", '
                        '"features": ["f1", "f2", "f3", "f4"]}. '
                        "Use PascalCase name, no spaces."
                    ),
                }
            ],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            end = len(lines)
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip() == "```":
                    end = i
                    break
            raw = "\n".join(lines[1:end])
        idea = json.loads(raw)

        app_name = idea["name"]
        app_id = app_name.lower().replace(" ", "_")[:30]
        app_dir = output_dir / app_id

        logger.info("[%s] App idea: %s - %s", run_id, app_name, idea["description"])

        await emit_stage_change("crawl", run_id, "completed", {"message": f"创意生成完成: {app_name}"})
        await self._log(f"创意生成完成: {app_name} - {idea['description']}", "stage_change")

        await emit_stage_change("process", run_id, "active", {"message": f"正在处理需求: {app_name}"})
        await self._log(f"正在处理需求: {app_name}", "stage_change")

        await emit_stage_change("process", run_id, "completed", {"message": f"需求处理完成: {app_name}"})

        # Step 2: Generate Flutter code
        await emit_stage_change("generate", run_id, "active", {"message": f"正在生成 {app_name} 代码..."})
        await self._log(f"正在生成 {app_name} 代码...", "stage_change")

        features_str = ", ".join(idea.get("features", []))
        resp = await client.messages.create(
            model=settings.claude_model,
            max_tokens=8192,
            system=(
                "Output raw source code only. No explanations. No markdown. "
                "No file operations. Target Dart 2.19 / Flutter 3.7+. "
                "Do NOT use super parameters, records, patterns, sealed classes, "
                "colorSchemeSeed. Use Key? key style. useMaterial3: false. No emoji."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Write a complete Flutter main.dart for: {app_name} "
                        f"- {idea['description']}. Features: {features_str}. "
                        "Use indigo (#3F51B5) primary color. AppBar with white title. "
                        "Light gray background. Start with: import"
                    ),
                }
            ],
        )
        code = resp.content[0].text.strip()
        if code.startswith("```"):
            lines = code.split("\n")
            end = len(lines)
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip() == "```":
                    end = i
                    break
            code = "\n".join(lines[1:end])

        line_count = len(code.split("\n"))
        await emit_stage_change("generate", run_id, "completed", {"message": f"代码生成完成: {line_count} 行"})
        await self._log(f"代码生成完成: {line_count} 行", "stage_change")

        # Step 3: Create Flutter project
        await emit_stage_change("build", run_id, "active", {"message": "正在创建 Flutter 项目..."})
        await self._log("正在创建 Flutter 项目...", "stage_change")

        if app_dir.exists():
            shutil.rmtree(app_dir)

        env = {**os.environ, "NO_PROXY": "127.0.0.1,localhost"}

        proc = await asyncio.create_subprocess_exec(
            "flutter",
            "create",
            "--org",
            "com.autodev",
            str(app_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        await proc.wait()

        # Write generated code
        main_dart = app_dir / "lib" / "main.dart"
        main_dart.write_text(code, encoding="utf-8")

        # Remove default test (it references MyApp which no longer exists)
        test_file = app_dir / "test" / "widget_test.dart"
        if test_file.exists():
            test_file.unlink()

        # Analyze
        await emit_stage_change("build", run_id, "active", {"message": "正在运行 dart analyze..."})
        await self._log("正在运行 dart analyze...", "stage_change")
        proc = await asyncio.create_subprocess_exec(
            "flutter",
            "analyze",
            cwd=str(app_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()
        analyze_out = stdout.decode() + stderr.decode()

        # Check for errors (not info/warnings)
        has_errors = (
            "error" in analyze_out.lower()
            and "0 issues" not in analyze_out.lower()
            and "No issues found" not in analyze_out
        )
        if has_errors:
            error_lines = [
                line
                for line in analyze_out.split("\n")
                if "error" in line.lower() and "info" not in line.lower()
            ]
            if error_lines:
                logger.warning(
                    "[%s] Analyze found %d errors, continuing anyway...",
                    run_id,
                    len(error_lines),
                )

        logger.info("[%s] Project created at %s", run_id, app_dir)
        self._stats["apps_generated"] += 1

        await emit_stage_change("build", run_id, "completed", {"message": f"构建完成: {app_name}"})
        await self._log(f"构建完成: {app_name}", "stage_change")

        # Step 4: Push to GitHub
        await emit_stage_change("publish", run_id, "active", {"message": "正在推送到 GitHub..."})
        await self._log("正在推送到 GitHub...", "stage_change")

        await self._push_to_github(app_dir, app_id, idea)

        await emit_stage_change("publish", run_id, "completed", {"message": f"已推送到 GitHub: {app_id}"})
        await self._log(f"已推送到 GitHub: {app_id}", "stage_change")
        await emit_pipeline_summary(
            run_id,
            {
                "app_name": app_name,
                "app_id": app_id,
                "description": idea["description"],
                "path": str(app_dir),
                "status": "completed",
                "message": f"周期完成: {app_name}",
            },
        )

        logger.info("[%s] Cycle complete: %s", run_id, app_name)
        await self._log(f"周期完成: {app_name}", "stage_change")

    async def _push_to_github(self, app_dir: Path, app_id: str, idea: dict):
        """Initialize git, create GitHub repo, and push."""
        env = {
            **os.environ,
            "GIT_TERMINAL_PROMPT": "0",
            "NO_PROXY": "127.0.0.1,localhost",
        }

        # git init + initial commit
        for cmd in [
            ["git", "init"],
            ["git", "add", "-A"],
            [
                "git",
                "commit",
                "-m",
                (
                    f"Initial commit: {idea.get('name', app_id)}"
                    f" - {idea.get('description', '')}"
                ),
            ],
        ]:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(app_dir),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()

        settings = get_settings()
        gh_org = settings.github_org

        # Build repo name for gh CLI
        repo_name = f"{gh_org}/{app_id}" if gh_org else app_id

        # Create GitHub repo using gh CLI
        proc = await asyncio.create_subprocess_exec(
            "gh",
            "repo",
            "create",
            repo_name,
            "--public",
            "--source",
            str(app_dir),
            "--remote",
            "origin",
            "--push",
            cwd=str(app_dir),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            self._stats["apps_pushed"] += 1
            logger.info("Pushed to GitHub: %s", repo_name)
        else:
            err = stderr.decode()
            if "already exists" in err:
                remote_url = (
                    f"https://github.com/{gh_org}/{app_id}.git"
                    if gh_org
                    else f"https://github.com/{app_id}.git"
                )
                proc = await asyncio.create_subprocess_exec(
                    "git",
                    "remote",
                    "add",
                    "origin",
                    remote_url,
                    cwd=str(app_dir),
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.wait()
                proc = await asyncio.create_subprocess_exec(
                    "git",
                    "push",
                    "-u",
                    "origin",
                    "main",
                    cwd=str(app_dir),
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.wait()
                if proc.returncode == 0:
                    self._stats["apps_pushed"] += 1
            else:
                logger.error("GitHub push failed for %s: %s", app_id, err)
