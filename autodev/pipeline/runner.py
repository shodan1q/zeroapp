"""Background pipeline runner -- manages the continuous loop lifecycle."""

import asyncio
import json
import logging
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from autodev.config import get_settings
from autodev.api.events import emit_error, emit_pipeline_summary, emit_stage_change

logger = logging.getLogger(__name__)


async def _save_demand(idea: dict, app_id: str, status: str = "pending") -> int | None:
    """Persist a demand record to the database. Returns demand_id or None."""
    try:
        from autodev.database import get_async_session
        from autodev.models.demand import Demand, DemandStatus

        status_map = {
            "pending": DemandStatus.PENDING,
            "generating": DemandStatus.GENERATING,
            "generated": DemandStatus.GENERATED,
            "building": DemandStatus.BUILDING,
            "built": DemandStatus.BUILT,
            "publishing": DemandStatus.PUBLISHING,
            "published": DemandStatus.PUBLISHED,
            "failed": DemandStatus.FAILED,
        }

        async with get_async_session() as session:
            demand = Demand(
                title=idea.get("name", app_id),
                description=idea.get("description", ""),
                category="utility",
                target_users=", ".join(idea.get("screens", [])),
                core_features=json.dumps(idea.get("features", []), ensure_ascii=False),
                monetization="ads",
                complexity="medium",
                trend_score=0.7,
                source="autodev_pipeline",
                status=status_map.get(status, DemandStatus.PENDING),
            )
            session.add(demand)
            await session.flush()
            did = demand.demand_id
            return did
    except Exception as e:
        logger.warning("Failed to save demand: %s", e)
        return None


async def _update_demand_status(demand_id: int | None, status: str) -> None:
    """Update demand status in database."""
    if demand_id is None:
        return
    try:
        from autodev.database import get_async_session
        from autodev.models.demand import Demand, DemandStatus

        status_map = {
            "generating": DemandStatus.GENERATING,
            "generated": DemandStatus.GENERATED,
            "building": DemandStatus.BUILDING,
            "built": DemandStatus.BUILT,
            "publishing": DemandStatus.PUBLISHING,
            "published": DemandStatus.PUBLISHED,
            "failed": DemandStatus.FAILED,
        }
        ds = status_map.get(status)
        if ds is None:
            return
        async with get_async_session() as session:
            demand = await session.get(Demand, demand_id)
            if demand:
                demand.status = ds
    except Exception as e:
        logger.warning("Failed to update demand status: %s", e)


async def _save_app(demand_id: int | None, idea: dict, app_id: str, app_dir: str, github_url: str = "") -> int | None:
    """Persist an app registry record. Returns app_id or None."""
    if demand_id is None:
        return None
    try:
        from autodev.database import get_async_session
        from autodev.models.app_registry import AppRegistry, AppStatus

        async with get_async_session() as session:
            app = AppRegistry(
                demand_id=demand_id,
                app_name=idea.get("name", app_id),
                package_name=f"com.autodev.{app_id}",
                description=idea.get("description", ""),
                category="utility",
                project_path=app_dir,
                status=AppStatus.CODE_GENERATED,
                google_play_url=github_url,
            )
            session.add(app)
            await session.flush()
            return app.app_id
    except Exception as e:
        logger.warning("Failed to save app: %s", e)
        return None


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

    def _default_file_list(self, screens: list[str]) -> list[dict]:
        """Build a sensible default file list from the screens in the idea."""
        files = [
            {"path": "pubspec.yaml",
             "purpose": "Flutter project dependencies including google_mobile_ads, shared_preferences"},
            {"path": "lib/main.dart",
             "purpose": "App entry point with MaterialApp, theme, and AdMob initialization"},
            {"path": "lib/config/theme.dart",
             "purpose": "Light and dark ThemeData definitions"},
            {"path": "lib/config/constants.dart",
             "purpose": "App-wide constants: colors, sizes, AdMob unit IDs (test IDs)"},
            {"path": "lib/models/app_model.dart",
             "purpose": "Data model classes for the app"},
            {"path": "lib/services/storage_service.dart",
             "purpose": "Local data persistence using shared_preferences"},
            {"path": "lib/widgets/ad_banner.dart",
             "purpose": "Reusable AdMob banner widget using google_mobile_ads"},
        ]
        for screen in screens:
            snake = re.sub(r'(?<!^)(?=[A-Z])', '_', screen).lower()
            if not snake.endswith("_screen"):
                snake = snake + "_screen"
            files.append({
                "path": f"lib/screens/{snake}.dart",
                "purpose": f"{screen} screen implementation",
            })
        return files

    async def _run_one_cycle(self):
        """Run one full pipeline cycle with dynamic file planning and testing."""
        settings = get_settings()
        output_dir = Path(settings.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        run_id = self._current_run_id
        env = {**os.environ, "NO_PROXY": "127.0.0.1,localhost"}

        from autodev.llm import get_claude_async_client
        client = get_claude_async_client()

        # ── Stage: crawl -- 生成 App 创意 ─────────────────────────────
        await emit_stage_change("crawl", run_id, "active", {"message": "正在生成 App 创意..."})
        await self._log("正在生成 App 创意...", "stage_change")

        resp = await client.messages.create(
            model=settings.claude_model,
            max_tokens=800,
            system="You are an app idea generator. Reply with JSON only. No markdown fences.",
            messages=[{"role": "user", "content": (
                "Suggest ONE practical utility mobile app idea that is complex enough "
                "for app store submission. "
                "It should have at least 3 screens, local data storage, and be ad-supported. "
                "Examples: habit tracker, expense splitter, unit converter with history, "
                "meditation timer, workout log, recipe book, color palette generator, mood journal. "
                "Do NOT suggest: pomodoro timer, water reminder, noise meter, bill splitter. "
                'Return JSON: {"name": "AppName", "description": "2 sentence description", '
                '"features": ["f1", "f2", "f3", "f4", "f5", "f6"], '
                '"screens": ["HomeScreen", "Screen2", "Screen3", "SettingsScreen"], '
                '"data_models": ["Model1", "Model2"]}. '
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

        # Save demand to database
        demand_id = await _save_demand(idea, app_id, "generating")
        if demand_id:
            await self._log(f"  需求已保存到数据库 (ID: {demand_id})", "info")

        # ── Stage: process -- 生成 PRD 并规划文件列表 ─────────────────
        await emit_stage_change("process", run_id, "active", {"message": f"正在生成 {app_name} PRD..."})
        await self._log("正在生成产品需求文档 (PRD)...", "stage_change")

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

        await self._log(f"PRD 生成完成: {len(prd)} 字符", "info")

        # Ask Claude to plan the project files
        await self._log("正在规划项目文件结构...", "stage_change")

        plan_resp = await client.messages.create(
            model=settings.claude_model,
            max_tokens=2000,
            system="You are a Flutter project architect. Return JSON only. No markdown fences.",
            messages=[{"role": "user", "content": (
                f"Based on this PRD, plan the complete file structure for the Flutter app.\n\n"
                f"PRD:\n{prd}\n\n"
                f"Return a JSON array of files to generate, in dependency order "
                f"(files that others depend on first).\n"
                f"Each entry: {{\"path\": \"lib/...\", \"purpose\": \"description\"}}\n\n"
                f"MUST include:\n"
                f"- pubspec.yaml (first)\n"
                f"- lib/main.dart (app entry point)\n"
                f"- All model/service/screen/widget files needed\n"
                f"- AdMob integration (google_mobile_ads banner widget)\n"
                f"- At least 3 screens\n"
                f"- Local storage service\n"
                f"- Data models\n\n"
                f"Return ONLY the JSON array, nothing else."
            )}],
        )

        # Parse file plan; fall back to default if parsing fails
        try:
            plan_raw = _strip_fences(plan_resp.content[0].text)
            file_plan = json.loads(plan_raw)
            if not isinstance(file_plan, list) or len(file_plan) == 0:
                raise ValueError("empty or non-list plan")
            # Validate each entry has path and purpose
            for entry in file_plan:
                if "path" not in entry or "purpose" not in entry:
                    raise ValueError("missing path or purpose in plan entry")
            await self._log(f"文件规划完成: {len(file_plan)} 个文件", "info")
        except Exception as e:
            await self._log(f"文件规划解析失败 ({e})，使用默认列表", "info")
            file_plan = self._default_file_list(idea.get("screens", [
                "HomeScreen", "SettingsScreen", "StatsScreen",
            ]))

        # Safety limit: truncate to 20 files
        if len(file_plan) > 20:
            await self._log(f"文件列表过长 ({len(file_plan)})，截断为 20 个", "info")
            file_plan = file_plan[:20]

        await emit_stage_change("process", run_id, "completed", {
            "message": f"PRD 和文件规划完成: {len(file_plan)} 个文件"
        })
        await self._log(f"规划文件列表: {', '.join(e['path'] for e in file_plan)}", "info")

        # ── Stage: generate -- 逐文件生成代码 ─────────────────────────
        await emit_stage_change("generate", run_id, "active", {
            "message": f"正在逐文件生成代码 (0/{len(file_plan)})..."
        })
        await self._log(f"开始逐文件生成代码，共 {len(file_plan)} 个文件...", "stage_change")

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

        for idx, entry in enumerate(file_plan):
            file_path = entry["path"]
            file_purpose = entry["purpose"]

            await emit_stage_change(
                "generate", run_id, "active",
                {"message": f"正在生成 ({idx+1}/{len(file_plan)}): {file_path}"}
            )
            await self._log(f"  生成文件 [{idx+1}/{len(file_plan)}]: {file_path}", "info")

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

        await emit_stage_change("generate", run_id, "completed", {
            "message": f"代码生成完成: {len(file_plan)} 文件, {total_lines} 行"
        })
        await self._log(
            f"代码生成完成: {len(file_plan)} 个文件, 共 {total_lines} 行", "stage_change"
        )

        # ── Stage: build -- 创建项目、安装依赖、分析修复 ──────────────
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

        # Remove default test file
        default_test = app_dir / "test" / "widget_test.dart"
        if default_test.exists():
            default_test.unlink()

        # Write all generated files into the project
        await self._log("正在写入生成的代码文件...", "info")
        for file_path, code in generated_files.items():
            full_path = app_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(code, encoding="utf-8")

        # Update demand status
        await _update_demand_status(demand_id, "generated")

        # Run flutter pub get after writing pubspec.yaml
        await emit_stage_change("build", run_id, "active", {"message": "正在安装依赖..."})
        await self._log("正在运行 flutter pub get...", "stage_change")

        proc = await asyncio.create_subprocess_exec(
            "flutter", "pub", "get", cwd=str(app_dir),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
        )
        await proc.wait()

        # Run dart analyze
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
            error_lines = [
                l for l in analyze_out.split("\n")
                if "error" in l.lower() and "info" not in l.lower()
            ]
            error_count = len(error_lines)

            # Auto-fix attempt: send errors to Claude for fix
            if 0 < error_count < 20:
                await self._log(f"发现 {error_count} 个错误，尝试自动修复...", "stage_change")

                fix_resp = await client.messages.create(
                    model=settings.claude_model,
                    max_tokens=16384,
                    system=(
                        "You are fixing Flutter/Dart compilation errors. "
                        "For each file that needs fixing, output in this format:\n"
                        "===FILE: path/to/file.dart===\n<complete fixed file>\n===END===\n"
                        "Rules: Dart 2.19, no super parameters, no records, "
                        "useMaterial3: false, no emoji."
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

                fix_text = fix_resp.content[0].text
                matches = re.findall(
                    r"===FILE:\s*(.+?)===\n(.*?)===END===", fix_text, re.DOTALL
                )
                for fix_path, fix_code in matches:
                    fix_path = fix_path.strip()
                    fix_code = fix_code.strip()
                    full_path = app_dir / fix_path
                    if full_path.exists() or fix_path in generated_files:
                        full_path.parent.mkdir(parents=True, exist_ok=True)
                        full_path.write_text(fix_code + "\n", encoding="utf-8")
                        generated_files[fix_path] = fix_code
                        await self._log(f"  已修复: {fix_path}", "info")

                # Re-analyze
                proc = await asyncio.create_subprocess_exec(
                    "flutter", "analyze", cwd=str(app_dir),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
                stdout, stderr = await proc.communicate()
                analyze_out = stdout.decode() + stderr.decode()
                has_errors = (
                    "error" in analyze_out.lower()
                    and "No issues found" not in analyze_out
                )
                if not has_errors:
                    await self._log("自动修复成功，零错误", "stage_change")
                    error_count = 0

        analyze_status = "零错误" if not has_errors else f"{error_count} 个错误"
        self._stats["apps_generated"] += 1

        await emit_stage_change("build", run_id, "completed", {
            "message": f"构建完成: {analyze_status}"
        })
        await self._log(f"dart analyze 结果: {analyze_status}", "stage_change")

        # ── Stage: evaluate -- 生成测试并运行 ─────────────────────────
        await emit_stage_change("evaluate", run_id, "active", {
            "message": "正在生成测试用例..."
        })
        await self._log("正在生成功能测试用例...", "stage_change")

        # Collect screen files for test generation context
        screen_sources = "\n".join(
            f"--- {p} ---\n{c}\n"
            for p, c in generated_files.items()
            if "screen" in p.lower() or "main.dart" in p.lower()
        )[:10000]

        test_files_prompt = (
            f"Based on these source files, generate Flutter widget tests.\n\n"
            f"{screen_sources}\n\n"
            f"App: {app_name}\n"
            f"Test each screen's key widgets and interactions.\n"
            f"Return in format:\n"
            f"===FILE: test/screen_name_test.dart===\n<test code>\n===END===\n\n"
            f"Rules: Dart 2.19, no super parameters, use flutter_test package.\n"
            f"Test that key widgets exist and can be rendered without errors.\n"
            f"Use pumpWidget with MaterialApp wrapper.\n"
            f"Keep tests simple and focused on widget rendering."
        )

        test_resp = await client.messages.create(
            model=settings.claude_model,
            max_tokens=8192,
            system=(
                "You are a Flutter test engineer. Generate widget tests.\n"
                "Output format: ===FILE: test/xxx_test.dart===\n<code>\n===END===\n"
                "Rules: Dart 2.19, no super parameters, flutter_test, simple pump tests.\n"
                "No markdown fences. No explanations."
            ),
            messages=[{"role": "user", "content": test_files_prompt}],
        )

        test_text = test_resp.content[0].text
        test_matches = re.findall(
            r"===FILE:\s*(.+?)===\n(.*?)===END===", test_text, re.DOTALL
        )

        test_files_written = 0
        for test_path, test_code in test_matches:
            test_path = test_path.strip()
            test_code = test_code.strip()
            full_path = app_dir / test_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(test_code, encoding="utf-8")
            test_files_written += 1
            await self._log(f"  写入测试: {test_path}", "info")

        await self._log(
            f"测试用例生成完成: {test_files_written} 个测试文件", "info"
        )

        # Run flutter test
        await self._log("正在运行 flutter test...", "stage_change")
        proc = await asyncio.create_subprocess_exec(
            "flutter", "test", "--no-pub",
            cwd=str(app_dir), env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        test_output = stdout.decode() + stderr.decode()

        test_pass = proc.returncode == 0

        # If tests fail, try to fix (max 2 attempts)
        fix_attempts = 0
        while not test_pass and fix_attempts < 2:
            fix_attempts += 1
            await self._log(
                f"测试失败，尝试修复 (第 {fix_attempts} 次)...", "stage_change"
            )

            # Collect current test files
            test_dir = app_dir / "test"
            current_tests = {}
            if test_dir.exists():
                for tf in test_dir.rglob("*.dart"):
                    rel = str(tf.relative_to(app_dir))
                    current_tests[rel] = tf.read_text(encoding="utf-8")

            test_fix_resp = await client.messages.create(
                model=settings.claude_model,
                max_tokens=8192,
                system=(
                    "You are fixing failing Flutter widget tests. "
                    "For each file that needs fixing, output in this format:\n"
                    "===FILE: test/xxx_test.dart===\n<complete fixed file>\n===END===\n"
                    "Rules: Dart 2.19, no super parameters, flutter_test, simple tests.\n"
                    "No markdown fences."
                ),
                messages=[{"role": "user", "content": (
                    f"Test output:\n{test_output[-3000:]}\n\n"
                    f"Current test files:\n"
                    + "\n".join(
                        f"--- {p} ---\n{c}\n"
                        for p, c in current_tests.items()
                    )[:6000]
                    + f"\n\nSource files:\n{screen_sources[:4000]}\n\n"
                    f"Fix the failing tests so they pass."
                )}],
            )

            fix_text = test_fix_resp.content[0].text
            fix_matches = re.findall(
                r"===FILE:\s*(.+?)===\n(.*?)===END===", fix_text, re.DOTALL
            )
            for fix_path, fix_code in fix_matches:
                fix_path = fix_path.strip()
                fix_code = fix_code.strip()
                full_path = app_dir / fix_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(fix_code, encoding="utf-8")
                await self._log(f"  已修复测试: {fix_path}", "info")

            # Re-run tests
            proc = await asyncio.create_subprocess_exec(
                "flutter", "test", "--no-pub",
                cwd=str(app_dir), env=env,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            test_output = stdout.decode() + stderr.decode()
            test_pass = proc.returncode == 0

        test_status = "全部通过" if test_pass else "存在失败"
        await emit_stage_change("evaluate", run_id, "completed", {
            "message": f"测试完成: {test_status}"
        })
        await self._log(f"测试结果: {test_status}", "stage_change")

        # ── Stage: publish -- 推送到 GitHub ───────────────────────────
        await emit_stage_change("publish", run_id, "active", {"message": "正在推送到 GitHub..."})
        await self._log("正在推送到 GitHub...", "stage_change")

        await self._push_to_github(app_dir, app_id, idea)

        gh_org = settings.github_org
        github_url = (
            f"https://github.com/{gh_org}/{app_id}" if gh_org
            else f"https://github.com/{app_id}"
        )

        await emit_stage_change("publish", run_id, "completed", {
            "message": f"已推送: {github_url}"
        })
        await self._log(f"已推送到 GitHub: {github_url}", "stage_change")

        await emit_pipeline_summary(run_id, {
            "app_name": app_name, "app_id": app_id,
            "description": idea["description"], "path": str(app_dir),
            "github_url": github_url, "status": "completed",
            "message": f"周期完成: {app_name}",
        })

        # Save app to database and update demand status
        await _update_demand_status(demand_id, "published")
        db_app_id = await _save_app(demand_id, idea, app_id, str(app_dir), github_url)
        if db_app_id:
            await self._log(f"  应用已保存到数据库 (ID: {db_app_id})", "info")

        await self._log("========== 周期完成 ==========", "stage_change")
        await self._log(f"  App: {app_name}", "info")
        await self._log(f"  描述: {idea['description']}", "info")
        await self._log(f"  文件: {len(file_plan)} 个, 共 {total_lines} 行", "info")
        await self._log(f"  测试: {test_files_written} 个, {test_status}", "info")
        await self._log(f"  目录: {app_dir}", "info")
        await self._log(f"  GitHub: {github_url}", "info")
        await self._log(f"  分析: {analyze_status}", "info")
        await self._log("==============================", "stage_change")

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
