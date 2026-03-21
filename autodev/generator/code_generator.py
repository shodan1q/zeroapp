"""Generate Flutter code file by file using Claude API.

This is the CORE module of Layer 3.  It takes a PRD and template name, creates
a project directory, then generates each source file in dependency order by
calling Claude with full project context.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import anthropic

from autodev.config import get_settings
from autodev.generator.prd_generator import PRD
from autodev.generator.templates import TEMPLATE_REGISTRY

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System prompt for code generation
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert Flutter/Dart developer. You generate production-quality Flutter \
source code that compiles and runs without errors.

HARD CONSTRAINTS - every file you produce MUST follow these rules:
  - Flutter 3.22+, Dart 3.4+
  - State management: flutter_riverpod (Riverpod 2.x with code generation where appropriate)
  - Ads: google_mobile_ads - place an AdMob banner widget on the main screen. \
Use test ad unit IDs for now.
  - Theming: Material Design 3 (useMaterial3: true), provide both light and dark ThemeData.
  - Navigation: go_router for declarative routing.
  - Internationalisation: intl package, provide English and Japanese localisations.
  - Local storage: shared_preferences or hive as appropriate.
  - Follow clean architecture: models/, services/, providers/, widgets/, screens/ directories.
  - Every Dart file must have proper imports - never use relative imports, always package imports.
  - All provider definitions should be in lib/providers/.
  - No TODO comments - write complete, working code.
  - Use const constructors wherever possible.
  - Include proper error handling and loading states.

OUTPUT FORMAT:
  - Respond ONLY with the raw file content. No markdown fences, no explanation.
  - Do not include the file path - just the content.
"""

FILE_GENERATION_PROMPT = """\
Generate the content for the following file in a Flutter project.

PROJECT CONTEXT:
  App name: {app_name}
  Package name: {package_name}
  Description: {description}

PRD (full):
{prd_json}

TEMPLATE TYPE: {template}

FILE TO GENERATE:
  Path: {file_path}
  Purpose: {file_purpose}

ALREADY GENERATED FILES (abbreviated):
{context_files}

Generate ONLY the content for {file_path}. No explanations, no markdown fences.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _abbreviate_file(content: str, max_lines: int = 60) -> str:
    """Return an abbreviated version of a file for context."""
    lines = content.splitlines()
    if len(lines) <= max_lines:
        return content
    kept = lines[:40] + ["  // ... (truncated) ..."] + lines[-15:]
    return "\n".join(kept)


def _build_context_files(generated: dict[str, str], max_files: int = 15) -> str:
    """Build abbreviated context of already-generated files."""
    if not generated:
        return "  (none yet - this is the first file)"

    priority_dirs = ("models/", "providers/", "config", "app.dart", "main.dart", "theme/")
    items = sorted(
        generated.items(),
        key=lambda kv: (
            0 if any(d in kv[0] for d in priority_dirs) else 1,
            kv[0],
        ),
    )

    lines: list[str] = []
    for file_path, content in items[:max_files]:
        abbreviated = _abbreviate_file(content)
        lines.append(f"--- {file_path} ---")
        lines.append(abbreviated)
        lines.append("")

    if len(generated) > max_files:
        remaining = [fp for fp, _ in items[max_files:]]
        lines.append(f"(also generated but omitted for brevity: {', '.join(remaining)})")

    return "\n".join(lines)


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences if Claude wrapped the output."""
    text = text.strip()
    match = re.match(r"^```(?:dart|yaml|xml|json|arb)?\s*\n(.*?)```\s*$", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def _to_snake_case(name: str) -> str:
    """Convert PascalCase or camelCase to snake_case."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _get_file_list_for_template(template: str, prd: PRD) -> list[dict[str, str]]:
    """Determine the ordered list of files to generate.

    Merges the template registry's default file list with dynamic pages/models
    from the PRD.
    """
    registry_entry = TEMPLATE_REGISTRY.get(template, TEMPLATE_REGISTRY["single_page_tool"])
    base_files: list[dict[str, str]] = list(registry_entry["files"])

    # Add model files from PRD that are not already covered.
    for dm in prd.data_models:
        model_file = f"lib/models/{_to_snake_case(dm.name)}.dart"
        if not any(f["path"] == model_file for f in base_files):
            base_files.append({
                "path": model_file,
                "purpose": (
                    f"Data model: {dm.name} - {dm.description}. "
                    f"Fields: {json.dumps(dm.fields)}"
                ),
            })

    # Add screen files from PRD.
    for page in prd.pages:
        screen_file = f"lib/screens/{_to_snake_case(page.name)}.dart"
        if not any(f["path"] == screen_file for f in base_files):
            widgets_str = ", ".join(page.widgets) if page.widgets else "none specified"
            base_files.append({
                "path": screen_file,
                "purpose": (
                    f"Screen: {page.name} (route: {page.route}) - {page.description}. "
                    f"Widgets: {widgets_str}"
                ),
            })

    # Sort by generation order.
    order_map: dict[str, int] = {
        "pubspec.yaml": 0,
        "analysis_options.yaml": 1,
        "lib/theme/": 15,
        "lib/models/": 10,
        "lib/services/": 20,
        "lib/providers/": 30,
        "lib/router/": 35,
        "lib/widgets/": 40,
        "lib/screens/": 50,
        "lib/main.dart": 60,
        "lib/app.dart": 61,
        "lib/config/": 70,
        "lib/l10n/": 80,
    }

    def sort_key(f: dict[str, str]) -> int:
        path = f["path"]
        for prefix, order in sorted(order_map.items(), key=lambda x: -len(x[0])):
            if path.startswith(prefix) or path == prefix:
                return order
        return 99

    base_files.sort(key=sort_key)
    return base_files


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class CodeGenerator:
    """Generate Flutter app code file by file via Claude.

    This is the core code generation engine.  It creates a project directory,
    then iterates through the file list calling Claude for each file with full
    context of what has already been generated.
    """

    def __init__(self) -> None:
        settings = get_settings()
        from autodev.llm import get_claude_client
        self._client = get_claude_client()
        self._model = settings.claude_model
        self._workspace_dir = settings.workspace_dir

    async def plan_files(self, prd: str) -> list[str]:
        """Ask Claude to plan the file structure for the app.

        This is a legacy/fallback method.  Prefer :meth:`generate_project` which
        uses the template registry.

        Returns:
            List of file paths relative to lib/.
        """
        prompt = (
            "Given this PRD for a Flutter app, list all the Dart files that need to "
            "be created.\n\nPRD:\n{prd}\n\nReturn a JSON array of file paths relative "
            "to the lib/ directory.\nExample: [\"main.dart\", \"screens/home_screen.dart\"]\n\n"
            "Respond ONLY with the JSON array."
        ).format(prd=prd)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        try:
            return json.loads(text)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            return ["main.dart"]

    async def generate_file(
        self, prd: str, file_path: str, existing_files: dict[str, str]
    ) -> str:
        """Generate code for a single file (legacy interface).

        Args:
            prd: The PRD document as text.
            file_path: Path relative to lib/.
            existing_files: Dict mapping already-generated file paths to their code.

        Returns:
            Generated Dart source code.
        """
        existing_summary = "\n".join(
            f"- {fp} ({len(code.splitlines())} lines)"
            for fp, code in existing_files.items()
        )

        prompt = (
            f"You are generating Flutter/Dart code for a mobile app.\n\n"
            f"PRD:\n{prd}\n\n"
            f"Files already generated:\n{existing_summary or '(none yet)'}\n\n"
            f"Now generate the complete code for: {file_path}\n\n"
            f"Requirements:\n"
            f"- Flutter 3.22+ / Dart 3.4+ syntax\n"
            f"- Material Design 3\n"
            f"- flutter_riverpod for state management\n"
            f"- go_router for navigation\n"
            f"- Include proper package imports\n"
            f"- Complete, runnable code with no TODOs\n\n"
            f"Respond ONLY with the Dart code, no markdown fences."
        )

        response = self._client.messages.create(
            model=self._model,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return _strip_markdown_fences(response.content[0].text)

    async def generate_all(self, prd: str, project_path: Path) -> list[str]:
        """Generate all files for a Flutter app (legacy interface).

        Args:
            prd: The PRD document as text.
            project_path: Root path of the Flutter project.

        Returns:
            List of generated file paths.
        """
        files = await self.plan_files(prd)
        lib_dir = project_path / "lib"
        lib_dir.mkdir(parents=True, exist_ok=True)

        generated: dict[str, str] = {}
        generated_paths: list[str] = []

        for file_path in files:
            code = await self.generate_file(prd, file_path, generated)
            full_path = lib_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(code, encoding="utf-8")
            generated[file_path] = code
            generated_paths.append(str(full_path))

        return generated_paths

    # ------------------------------------------------------------------
    # New structured interface
    # ------------------------------------------------------------------

    async def generate_project(
        self,
        demand_id: str,
        prd: PRD,
        template: str,
        *,
        workspace_dir: str | None = None,
    ) -> dict[str, Any]:
        """Generate a complete Flutter project from a PRD.

        Creates the project directory under ``workspace/{demand_id}/`` and
        generates each file in dependency order, passing already-generated
        files as context to Claude.

        Args:
            demand_id: Unique identifier for the demand (becomes the folder name).
            prd: The structured PRD.
            template: Template name from TemplateSelector.
            workspace_dir: Override the default workspace directory.

        Returns:
            Dict with keys ``project_dir``, ``files`` (list of relative paths),
            and ``errors`` (list of error strings).
        """
        workspace = Path(workspace_dir or self._workspace_dir).resolve()
        project_dir = workspace / demand_id
        project_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Generating Flutter project '%s' in %s (template=%s)",
            prd.app_name,
            project_dir,
            template,
        )

        file_list = _get_file_list_for_template(template, prd)
        prd_json = prd.model_dump_json(indent=2)
        generated: dict[str, str] = {}
        generated_paths: list[str] = []
        errors: list[str] = []

        logger.info("Will generate %d files", len(file_list))

        for file_spec in file_list:
            file_path = file_spec["path"]
            file_purpose = file_spec["purpose"]

            logger.info("Generating %s ...", file_path)

            prompt = FILE_GENERATION_PROMPT.format(
                app_name=prd.app_name,
                package_name=prd.package_name,
                description=prd.description,
                prd_json=prd_json,
                template=template,
                file_path=file_path,
                file_purpose=file_purpose,
                context_files=_build_context_files(generated),
            )

            try:
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=8192,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )
            except anthropic.APIError as exc:
                error_msg = f"Claude API error generating {file_path}: {exc}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue

            content = _strip_markdown_fences(response.content[0].text)

            # Write to disk
            full_path = project_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                full_path.write_text(content, encoding="utf-8")
            except OSError as exc:
                error_msg = f"Failed to write {file_path}: {exc}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue

            generated[file_path] = content
            generated_paths.append(file_path)
            logger.info("Generated %s (%d bytes)", file_path, len(content))

        logger.info(
            "Project generation complete: %d files, %d errors",
            len(generated_paths),
            len(errors),
        )

        return {
            "project_dir": str(project_dir),
            "files": generated_paths,
            "errors": errors,
        }
