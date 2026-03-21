"""Generate a Product Requirements Document from a demand.

Uses Claude API to produce a structured PRD with pages, navigation flows,
data models, dependencies, and UI/UX guidelines - detailed enough for
file-by-file code generation.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from autodev.llm import get_claude_client
from pydantic import BaseModel, Field

from autodev.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PRD Pydantic models
# ---------------------------------------------------------------------------


class PageSpec(BaseModel):
    """Specification for a single screen/page in the app."""

    name: str = Field(description="Page class name, e.g. 'HomePage'")
    route: str = Field(description="Route path, e.g. '/home'")
    description: str = Field(description="What this page does and contains")
    widgets: list[str] = Field(
        default_factory=list,
        description="Key custom widgets used on this page",
    )


class DataModelSpec(BaseModel):
    """Specification for a data model / entity."""

    name: str = Field(description="Model class name")
    fields: dict[str, str] = Field(
        description="Field name -> Dart type mapping, e.g. {'title': 'String', 'count': 'int'}",
    )
    description: str = Field(default="", description="Purpose of this model")


class DependencySpec(BaseModel):
    """A pub.dev package dependency."""

    name: str = Field(description="Package name on pub.dev")
    version: str = Field(default="", description="Version constraint, e.g. '^2.0.0'")
    reason: str = Field(default="", description="Why this dependency is needed")


class NavigationFlow(BaseModel):
    """Describes how pages connect."""

    from_page: str
    to_page: str
    trigger: str = Field(description="User action that triggers this navigation")


class PRD(BaseModel):
    """Complete Product Requirements Document for a Flutter app."""

    app_name: str = Field(description="Human-readable application name")
    package_name: str = Field(description="Dart package name (snake_case)")
    description: str = Field(description="One-paragraph app description")
    pages: list[PageSpec] = Field(description="All screens in the app")
    navigation_flows: list[NavigationFlow] = Field(
        default_factory=list,
        description="Navigation connections between pages",
    )
    data_models: list[DataModelSpec] = Field(
        default_factory=list,
        description="Data models / entities",
    )
    dependencies: list[DependencySpec] = Field(
        default_factory=list,
        description="Required pub.dev packages beyond Flutter SDK",
    )
    ui_guidelines: str = Field(
        default="",
        description="UI/UX design guidelines and notes",
    )
    features: list[str] = Field(
        default_factory=list,
        description="Bullet-point list of features",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Technical constraints and requirements",
    )


# ---------------------------------------------------------------------------
# Claude prompt
# ---------------------------------------------------------------------------

PRD_PROMPT = """\
You are a senior product manager and Flutter architect. Given the app demand below, \
produce a detailed Product Requirements Document (PRD) that is specific enough for a \
developer to generate every source file.

App demand:
  Title: {title}
  Description: {description}
  Target Users: {target_users}
  Core Features: {features}
  Monetization: {monetization}
  Template type: {template}

Technical constraints (MUST be included):
  - Flutter 3.22+, Dart 3.4+
  - State management: flutter_riverpod
  - Ads: google_mobile_ads (AdMob banner on main screen)
  - Theming: Material Design 3, dark and light themes
  - Internationalisation: intl package, support English and Japanese
  - Local storage: shared_preferences or hive as appropriate
  - Navigation: go_router

Reply ONLY with valid JSON (no markdown fences) matching this schema:

{{
  "app_name": "<Human-readable name>",
  "package_name": "<snake_case package name>",
  "description": "<one-paragraph description>",
  "pages": [
    {{
      "name": "<PageClassName>",
      "route": "<route_path>",
      "description": "<what this page does>",
      "widgets": ["<CustomWidget1>", "<CustomWidget2>"]
    }}
  ],
  "navigation_flows": [
    {{"from_page": "<PageA>", "to_page": "<PageB>", "trigger": "<user action>"}}
  ],
  "data_models": [
    {{
      "name": "<ModelName>",
      "fields": {{"field_name": "DartType"}},
      "description": "<purpose>"
    }}
  ],
  "dependencies": [
    {{"name": "<package>", "version": "<constraint>", "reason": "<why>"}}
  ],
  "ui_guidelines": "<Material Design 3 guidelines, colour scheme notes, layout guidance>",
  "features": ["<feature 1>", "<feature 2>"],
  "constraints": ["Flutter 3.22+", "Dart 3.4+", "Riverpod", "AdMob banner", "MD3 theming", "intl i18n"]
}}

Be thorough: list every page, every model, every dependency. The PRD must be \
detailed enough that each file can be generated individually.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_response(raw_text: str) -> dict[str, Any]:
    """Parse JSON from Claude response, tolerating markdown fences."""
    try:
        return json.loads(raw_text)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
        if match:
            return json.loads(match.group(1))  # type: ignore[no-any-return]
        raise ValueError(f"Could not parse JSON from response: {raw_text[:300]}")


_REQUIRED_DEPS: dict[str, str] = {
    "flutter_riverpod": "^2.5.0",
    "riverpod_annotation": "^2.3.0",
    "google_mobile_ads": "^5.1.0",
    "go_router": "^14.0.0",
    "intl": "^0.19.0",
    "shared_preferences": "^2.2.0",
}


def _ensure_core_dependencies(deps: list[DependencySpec]) -> list[DependencySpec]:
    """Make sure mandatory dependencies are present."""
    existing_names = {d.name for d in deps}
    for name, version in _REQUIRED_DEPS.items():
        if name not in existing_names:
            deps.append(DependencySpec(name=name, version=version, reason="Core requirement"))
    return deps


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class PRDGenerator:
    """Generate a PRD from a structured demand using Claude."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = get_claude_client()
        self._model = settings.claude_model

    async def generate(
        self,
        title: str,
        description: str,
        target_users: str = "",
        features: list[str] | None = None,
        monetization: str = "",
        template: str = "single_page_tool",
    ) -> PRD:
        """Generate a structured PRD document.

        Args:
            title: App name / demand title.
            description: Full demand description.
            target_users: Target audience description.
            features: List of core feature strings.
            monetization: Monetization approach.
            template: Template type selected by TemplateSelector.

        Returns:
            A fully populated PRD instance.
        """
        prompt = PRD_PROMPT.format(
            title=title,
            description=description,
            target_users=target_users or "general users",
            features=", ".join(features) if features else "TBD",
            monetization=monetization or "free with AdMob banner ads",
            template=template,
        )

        logger.info("Generating PRD for '%s' (template=%s)", title, template)

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError:
            logger.exception("Claude API call failed during PRD generation")
            raise

        raw_text = response.content[0].text.strip()
        logger.debug("Claude PRD response length: %d chars", len(raw_text))

        data = _parse_json_response(raw_text)

        # Build dependencies and ensure core deps are present.
        deps = [DependencySpec(**d) for d in data.get("dependencies", [])]
        deps = _ensure_core_dependencies(deps)

        prd = PRD(
            app_name=data.get("app_name", title),
            package_name=data.get("package_name", "my_app"),
            description=data.get("description", description),
            pages=[PageSpec(**p) for p in data.get("pages", [])],
            navigation_flows=[NavigationFlow(**n) for n in data.get("navigation_flows", [])],
            data_models=[DataModelSpec(**m) for m in data.get("data_models", [])],
            dependencies=deps,
            ui_guidelines=data.get("ui_guidelines", ""),
            features=data.get("features", []),
            constraints=data.get("constraints", []),
        )

        logger.info(
            "PRD generated: %d pages, %d models, %d dependencies",
            len(prd.pages),
            len(prd.data_models),
            len(prd.dependencies),
        )
        return prd
