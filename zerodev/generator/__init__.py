"""Layer 3: Flutter code generation via Claude API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from zerodev.generator.template_selector import TemplateSelector
from zerodev.generator.prd_generator import PRDGenerator, PRD
from zerodev.generator.code_generator import CodeGenerator
from zerodev.generator.dependency_checker import DependencyChecker
from zerodev.generator.fixer import AutoFixer


# ---------------------------------------------------------------------------
# Wrapper functions bridging class-based API to the function-based API
# expected by zerodev.pipeline.graph
# ---------------------------------------------------------------------------


class _ProjectResult:
    """Lightweight result object returned by :func:`generate_project`."""

    def __init__(self, path: str) -> None:
        self.path = path

    def __repr__(self) -> str:
        return f"_ProjectResult(path={self.path!r})"


class _FixResult:
    """Lightweight result object returned by :func:`auto_fix_project`."""

    def __init__(self, success: bool, errors: list[str]) -> None:
        self.success = success
        self.errors = errors

    def __repr__(self) -> str:
        return f"_FixResult(success={self.success}, errors={len(self.errors)})"


async def select_template(demand: dict[str, Any]) -> str:
    """Select a Flutter template for *demand* using Claude.

    Args:
        demand: Structured demand dict (must contain ``title`` and ``description``).

    Returns:
        Template name string (e.g. ``"single_page_tool"``).
    """
    selector = TemplateSelector()
    result = await selector.select_for_demand(
        title=demand.get("title", "App"),
        description=demand.get("description", ""),
    )
    return result["template"]


async def generate_prd(demand: dict[str, Any]) -> PRD:
    """Generate a PRD document from a structured *demand*.

    Args:
        demand: Structured demand dict.

    Returns:
        A :class:`PRD` instance.
    """
    generator = PRDGenerator()
    features_raw = demand.get("core_features", demand.get("features", ""))
    if isinstance(features_raw, str):
        features = [f.strip() for f in features_raw.split(",") if f.strip()] if features_raw else []
    else:
        features = list(features_raw)

    return await generator.generate(
        title=demand.get("title", "App"),
        description=demand.get("description", ""),
        target_users=demand.get("target_users", ""),
        features=features,
        monetization=demand.get("monetization", ""),
        template=demand.get("_template", "single_page_tool"),
    )


async def generate_project(prd: PRD, *, template: str = "single_page_tool") -> _ProjectResult:
    """Generate a complete Flutter project from *prd*.

    Args:
        prd: The structured PRD.
        template: Template name from :func:`select_template`.

    Returns:
        An object with a ``.path`` attribute pointing to the project directory.
    """
    generator = CodeGenerator()
    result = await generator.generate_project(
        demand_id=prd.package_name,
        prd=prd,
        template=template,
    )
    return _ProjectResult(path=result["project_dir"])


async def check_and_fix_dependencies(project_path: str) -> None:
    """Scan imports and update ``pubspec.yaml`` with missing dependencies.

    Args:
        project_path: Absolute path to the Flutter project root.
    """
    checker = DependencyChecker()
    checker.update_pubspec(Path(project_path))


async def auto_fix_project(project_path: str) -> _FixResult:
    """Run the analyze-fix-build loop on the generated project.

    Args:
        project_path: Absolute path to the Flutter project root.

    Returns:
        An object with ``.success`` (bool) and ``.errors`` (list of str).
    """
    fixer = AutoFixer()
    result = await fixer.fix_loop(Path(project_path))
    return _FixResult(
        success=result.get("success", False),
        errors=result.get("remaining_errors", []),
    )


__all__ = [
    "TemplateSelector",
    "PRDGenerator",
    "PRD",
    "CodeGenerator",
    "DependencyChecker",
    "AutoFixer",
    "auto_fix_project",
    "check_and_fix_dependencies",
    "generate_prd",
    "generate_project",
    "select_template",
]
