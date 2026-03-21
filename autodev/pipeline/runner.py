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

# Files to generate for each app (in order)
APP_FILES = [
    ("lib/main.dart", "App entry point with MaterialApp, theme, and AdMob initialization"),
    ("lib/app.dart", "Root MaterialApp widget with route configuration and theme"),
    ("lib/config/theme.dart", "Light and dark ThemeData definitions using indigo primary color"),
    ("lib/config/routes.dart", "Route table / named route definitions"),
    ("lib/config/constants.dart", "App-wide constants: colors, sizes, AdMob unit IDs (test IDs)"),
    ("lib/screens/home_screen.dart", "Main screen with core functionality and AdMob banner"),
    ("lib/screens/settings_screen.dart", "Settings page: theme toggle, about section"),
    ("lib/screens/stats_screen.dart", "Statistics/history page with charts or summary cards"),
    ("lib/widgets/ad_banner.dart", "Reusable AdMob banner widget using google_mobile_ads"),
    ("lib/services/storage_service.dart", "Local data persistence using shared_preferences"),
    ("lib/models/app_model.dart", "Data model classes for the app"),
    ("pubspec.yaml", "Flutter project dependencies including google_mobile_ads, shared_preferences, fl_chart, intl"),
]


def _strip_fences(text: str) -> str:
    """Remove markdown code fences if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        end = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                end = i
                break
        text = "\n".join(lines[1:end])
    return text


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
        self._logs: list[dict] = []

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
        """Run one full pipeline cycle with multi-file generation + AdMob."""
        settings = get_settings()
        output_dir = Path(settings.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        run_id = self._current_run_id
        env = {**os.environ, "NO_PROXY": "127.0.0.1,localhost"}

        from autodev.llm import get_claude_async_client
        client = get_claude_async_client()

        # ── Stage 1: Generate app idea ────────────────────────────────
        await emit_stage_change("crawl", run_id, "active", {"message": "正在生成 App 创意..."})
        await self._log("正在生成 App 创意...", "stage_change")

        resp = await client.messages.create(
            model=settings.claude_model,
            max_tokens=500,
            system="You are an app idea generator. Reply with JSON only. No markdown fences.",
            messages=[{"role": "user", "content": (
                "Suggest ONE practical utility mobile app idea that is complex enough for app store submission. "
                "It should have at least 3 screens, local data storage, and be ad-supported. "
                "Examples: habit tracker, expense splitter, unit converter with history, meditation timer, "
                "workout log, recipe book, color palette generator, mood journal. "
                "Do NOT suggest: pomodoro timer, water reminder, noise meter, bill splitter. "
                'Return JSON: {"name": "AppName", "description": "2 sentence description", '
                '"features": ["f1", "f2", "f3", "f4", "f5", "f6"], '
                '"screens": ["HomeScreen", "Screen2", "Screen3", "SettingsScreen"]}. '
                "PascalCase name, no spaces."
            )}],
        )
        raw = _strip_fences(resp.content[0].text)
        idea = json.loads(raw)

        app_name = idea["name"]
        app_id = app_name.lower().replace(" ", "_")[:30]
        app_dir = output_dir / app_id

        await emit_stage_change("crawl", run_id, "completed", {"message": f"创意: {app_name}"})
        await self._log(f"创意生成完成: {app_name}", "stage_change")
        await self._log(f"  描述: {idea['description']}", "info")
        await self._log(f"  功能: {', '.join(idea.get('features', []))}", "info")
        await self._log(f"  页面: {', '.join(idea.get('screens', []))}", "info")
        await self._log(f"  目录: {app_dir}", "info")

        # ── Stage 2: Generate PRD ─────────────────────────────────────
        await emit_stage_change("process", run_id, "active", {"message": f"正在生成 {app_name} PRD..."})
        await self._log(f"正在生成产品需求文档 (PRD)...", "stage_change")

        prd_resp = await client.messages.create(
            model=settings.claude_model,
            max_tokens=2000,
            system="You are a product manager. Output a concise PRD in plain text. No markdown fences.",
            messages=[{"role": "user", "content": (
                f"Write a brief PRD for this Flutter app:\n"
                f"Name: {app_name}\n"
                f"Description: {idea['description']}\n"
                f"Features: {json.dumps(idea.get('features', []))}\n"
                f"Screens: {json.dumps(idea.get('screens', []))}\n\n"
                f"Include: screen descriptions, data models, navigation flow, AdMob ad placements.\n"
                f"The app must include google_mobile_ads banner ads on the home screen.\n"
                f"Keep it concise (under 800 words)."
            )}],
        )
        prd = _strip_fences(prd_resp.content[0].text)

        await emit_stage_change("process", run_id, "completed", {"message": "PRD 生成完成"})
        await self._log(f"PRD 生成完成: {len(prd)} 字符", "stage_change")

        # ── Stage 3: Create Flutter project ───────────────────────────
        await emit_stage_change("build", run_id, "active", {"message": "正在创建 Flutter 项目..."})
        await self._log("正在创建 Flutter 项目...", "stage_change")

        if app_dir.exists():
            shutil.rmtree(app_dir)

        proc = await asyncio.create_subprocess_exec(
            "flutter", "create", "--org", "com.autodev", str(app_dir),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
        )
        await proc.wait()
        await self._log(f"Flutter 项目已创建: {app_dir}", "info")

        # Remove default files
        for f in ["test/widget_test.dart"]:
            p = app_dir / f
            if p.exists():
                p.unlink()

        # ── Stage 4: Generate code file by file ──────────────────────
        await emit_stage_change("generate", run_id, "active", {"message": f"正在逐文件生成代码 (0/{len(APP_FILES)})..."})
        await self._log(f"开始逐文件生成代码，共 {len(APP_FILES)} 个文件...", "stage_change")

        generated_files: dict[str, str] = {}
        total_lines = 0

        system_prompt = (
            "You are an expert Flutter developer generating production-quality code.\n\n"
            "HARD RULES:\n"
            "- Dart 2.19 / Flutter 3.7+ (NO super parameters, NO records, NO patterns, NO sealed classes)\n"
            "- Constructor style: Key? key parameter, pass via super(key: key)\n"
            "- Material Design 2: useMaterial3: false, NO colorSchemeSeed\n"
            "- Use primarySwatch: Colors.indigo for theming\n"
            "- Include google_mobile_ads for AdMob banner ads (use test ad unit IDs)\n"
            "- Include shared_preferences for local storage\n"
            "- NO emoji anywhere in code, UI, or comments\n"
            "- All package imports (never relative imports)\n"
            "- Complete working code, no TODOs\n\n"
            "OUTPUT: Raw file content only. No markdown fences, no explanation, no file path header."
        )

        for idx, (file_path, file_purpose) in enumerate(APP_FILES):
            await emit_stage_change(
                "generate", run_id, "active",
                {"message": f"正在生成 ({idx+1}/{len(APP_FILES)}): {file_path}"}
            )
            await self._log(f"  生成文件 [{idx+1}/{len(APP_FILES)}]: {file_path}", "info")

            # Build context from already generated files (abbreviated)
            context_parts = []
            for prev_path, prev_code in generated_files.items():
                # Show first 30 lines of each previous file for context
                preview = "\n".join(prev_code.split("\n")[:30])
                context_parts.append(f"--- {prev_path} (preview) ---\n{preview}\n")
            context = "\n".join(context_parts[-5:])  # Last 5 files for context window

            user_prompt = (
                f"App: {app_name}\nDescription: {idea['description']}\n\n"
                f"PRD:\n{prd[:1500]}\n\n"
                f"Generate the file: {file_path}\n"
                f"Purpose: {file_purpose}\n"
                f"Package name: {app_id}\n\n"
            )
            if context:
                user_prompt += f"Already generated files (for reference):\n{context}\n\n"
            user_prompt += "Output ONLY the complete file content."

            resp = await client.messages.create(
                model=settings.claude_model,
                max_tokens=8192,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            code = _strip_fences(resp.content[0].text)
            generated_files[file_path] = code

            # Write file
            full_path = app_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(code, encoding="utf-8")
            file_lines = len(code.split("\n"))
            total_lines += file_lines

        await emit_stage_change("generate", run_id, "completed", {"message": f"代码生成完成: {len(APP_FILES)} 文件, {total_lines} 行"})
        await self._log(f"代码生成完成: {len(APP_FILES)} 个文件, 共 {total_lines} 行", "stage_change")

        # ── Stage 5: Analyze and fix ──────────────────────────────────
        await emit_stage_change("build", run_id, "active", {"message": "正在安装依赖..."})
        await self._log("正在运行 flutter pub get...", "stage_change")

        proc = await asyncio.create_subprocess_exec(
            "flutter", "pub", "get", cwd=str(app_dir),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
        )
        await proc.wait()

        await emit_stage_change("build", run_id, "active", {"message": "正在运行 dart analyze..."})
        await self._log("正在运行 dart analyze...", "stage_change")

        proc = await asyncio.create_subprocess_exec(
            "flutter", "analyze", cwd=str(app_dir),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
        )
        stdout, stderr = await proc.communicate()
        analyze_out = stdout.decode() + stderr.decode()

        has_errors = (
            "error" in analyze_out.lower()
            and "0 issues" not in analyze_out.lower()
            and "No issues found" not in analyze_out
        )
        error_count = 0
        if has_errors:
            error_lines = [l for l in analyze_out.split("\n") if "error" in l.lower() and "info" not in l.lower()]
            error_count = len(error_lines)

            # Auto-fix attempt: send errors to Claude for fix
            if error_count > 0 and error_count < 20:
                await self._log(f"发现 {error_count} 个错误，尝试自动修复...", "stage_change")

                fix_resp = await client.messages.create(
                    model=settings.claude_model,
                    max_tokens=16384,
                    system=(
                        "You are fixing Flutter/Dart compilation errors. "
                        "For each file that needs fixing, output in this format:\n"
                        "===FILE: path/to/file.dart===\n<complete fixed file>\n===END===\n"
                        "Rules: Dart 2.19, no super parameters, no records, useMaterial3: false, no emoji."
                    ),
                    messages=[{"role": "user", "content": (
                        f"Fix these dart analyze errors:\n\n{analyze_out[-3000:]}\n\n"
                        f"Relevant source files:\n"
                        + "\n".join(
                            f"--- {p} ---\n{c}\n"
                            for p, c in generated_files.items()
                            if any(p.split("/")[-1] in el for el in error_lines[:10])
                        )[:8000]
                    )}],
                )

                import re
                fix_text = fix_resp.content[0].text
                matches = re.findall(r"===FILE:\s*(.+?)===\n(.*?)===END===", fix_text, re.DOTALL)
                for fix_path, fix_code in matches:
                    fix_path = fix_path.strip()
                    fix_code = fix_code.strip()
                    full_path = app_dir / fix_path
                    if full_path.exists() or fix_path in generated_files:
                        full_path.parent.mkdir(parents=True, exist_ok=True)
                        full_path.write_text(fix_code + "\n", encoding="utf-8")
                        await self._log(f"  已修复: {fix_path}", "info")

                # Re-analyze
                proc = await asyncio.create_subprocess_exec(
                    "flutter", "analyze", cwd=str(app_dir),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
                )
                stdout, stderr = await proc.communicate()
                analyze_out = stdout.decode() + stderr.decode()
                has_errors = "error" in analyze_out.lower() and "No issues found" not in analyze_out
                if not has_errors:
                    await self._log("自动修复成功，零错误", "stage_change")
                    error_count = 0

        analyze_status = "零错误" if not has_errors else f"{error_count} 个错误"
        self._stats["apps_generated"] += 1

        await emit_stage_change("build", run_id, "completed", {"message": f"构建完成: {analyze_status}"})
        await self._log(f"dart analyze 结果: {analyze_status}", "stage_change")

        # ── Stage 6: Push to GitHub ───────────────────────────────────
        await emit_stage_change("publish", run_id, "active", {"message": "正在推送到 GitHub..."})
        await self._log("正在推送到 GitHub...", "stage_change")

        await self._push_to_github(app_dir, app_id, idea)

        gh_org = settings.github_org
        github_url = f"https://github.com/{gh_org}/{app_id}" if gh_org else f"https://github.com/{app_id}"

        await emit_stage_change("publish", run_id, "completed", {"message": f"已推送: {github_url}"})
        await self._log(f"已推送到 GitHub: {github_url}", "stage_change")

        await emit_pipeline_summary(run_id, {
            "app_name": app_name, "app_id": app_id,
            "description": idea["description"], "path": str(app_dir),
            "github_url": github_url, "status": "completed",
            "message": f"周期完成: {app_name}",
        })

        await self._log(f"========== 周期完成 ==========", "stage_change")
        await self._log(f"  App: {app_name}", "info")
        await self._log(f"  描述: {idea['description']}", "info")
        await self._log(f"  文件: {len(APP_FILES)} 个, 共 {total_lines} 行", "info")
        await self._log(f"  目录: {app_dir}", "info")
        await self._log(f"  GitHub: {github_url}", "info")
        await self._log(f"  分析: {analyze_status}", "info")
        await self._log(f"==============================", "stage_change")

    async def _push_to_github(self, app_dir: Path, app_id: str, idea: dict):
        """Initialize git, create GitHub repo, and push."""
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "NO_PROXY": "127.0.0.1,localhost"}

        for cmd in [
            ["git", "init"],
            ["git", "add", "-A"],
            ["git", "commit", "-m",
             f"feat: {idea.get('name', app_id)} - {idea.get('description', '')[:80]}"],
        ]:
            proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=str(app_dir), env=env,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()

        settings = get_settings()
        gh_org = settings.github_org
        repo_name = f"{gh_org}/{app_id}" if gh_org else app_id

        proc = await asyncio.create_subprocess_exec(
            "gh", "repo", "create", repo_name,
            "--public", "--source", str(app_dir), "--remote", "origin", "--push",
            cwd=str(app_dir), env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            self._stats["apps_pushed"] += 1
            await self._log(f"GitHub 仓库创建成功: {repo_name}", "info")
        else:
            err = stderr.decode()
            if "already exists" in err:
                remote_url = (
                    f"https://github.com/{gh_org}/{app_id}.git" if gh_org
                    else f"https://github.com/{app_id}.git"
                )
                for cmd in [
                    ["git", "remote", "add", "origin", remote_url],
                    ["git", "push", "-u", "origin", "main", "--force"],
                ]:
                    proc = await asyncio.create_subprocess_exec(
                        *cmd, cwd=str(app_dir), env=env,
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    )
                    await proc.wait()
                if proc.returncode == 0:
                    self._stats["apps_pushed"] += 1
            else:
                await self._log(f"GitHub 推送失败: {err[:200]}", "error")
                logger.error("GitHub push failed for %s: %s", app_id, err)
