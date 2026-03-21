"""Check imports in generated Dart code and update pubspec.yaml accordingly.

Scans all ``.dart`` files under ``lib/`` for ``package:`` import statements,
cross-references them with the dependencies already declared in
``pubspec.yaml``, and adds any missing packages.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


# Common package mappings: import prefix -> (pub.dev package name, default version)
KNOWN_PACKAGES: dict[str, tuple[str, str]] = {
    "flutter_riverpod": ("flutter_riverpod", "^2.5.0"),
    "riverpod_annotation": ("riverpod_annotation", "^2.3.0"),
    "hooks_riverpod": ("hooks_riverpod", "^2.5.0"),
    "google_mobile_ads": ("google_mobile_ads", "^5.1.0"),
    "go_router": ("go_router", "^14.0.0"),
    "intl": ("intl", "^0.19.0"),
    "shared_preferences": ("shared_preferences", "^2.2.0"),
    "hive": ("hive", "^2.2.3"),
    "hive_flutter": ("hive_flutter", "^1.1.0"),
    "path_provider": ("path_provider", "^2.1.0"),
    "url_launcher": ("url_launcher", "^6.2.0"),
    "http": ("http", "^1.2.0"),
    "dio": ("dio", "^5.4.0"),
    "cached_network_image": ("cached_network_image", "^3.3.0"),
    "flutter_svg": ("flutter_svg", "^2.0.0"),
    "equatable": ("equatable", "^2.0.5"),
    "freezed_annotation": ("freezed_annotation", "^2.4.0"),
    "json_annotation": ("json_annotation", "^4.8.0"),
    "uuid": ("uuid", "^4.3.0"),
    "collection": ("collection", "^1.18.0"),
    "provider": ("provider", "^6.1.0"),
    "sqflite": ("sqflite", "^2.3.0"),
    "audioplayers": ("audioplayers", "^6.0.0"),
    "fl_chart": ("fl_chart", "^0.68.0"),
    "table_calendar": ("table_calendar", "^3.1.0"),
    "percent_indicator": ("percent_indicator", "^4.2.0"),
    "flutter_slidable": ("flutter_slidable", "^3.1.0"),
    "google_fonts": ("google_fonts", "^6.2.0"),
}

# Packages that ship with Flutter SDK and must NOT be added to dependencies.
_SDK_PACKAGES: frozenset[str] = frozenset({
    "flutter",
    "flutter_test",
    "flutter_driver",
    "flutter_web_plugins",
    "flutter_localizations",
    "material",
    "cupertino",
    "widgets",
    "services",
    "painting",
    "foundation",
    "dart",
})

IMPORT_PATTERN = re.compile(r"import\s+'package:(\w+)/")


class DependencyChecker:
    """Scan generated Dart files and ensure pubspec.yaml has all needed packages."""

    def scan_imports(self, project_path: Path) -> set[str]:
        """Scan all .dart files under lib/ for package imports.

        Returns:
            Set of package names found in import statements (the part
            between ``package:`` and ``/``).
        """
        packages: set[str] = set()
        lib_dir = project_path / "lib"
        if not lib_dir.exists():
            logger.warning("No lib/ directory in %s", project_path)
            return packages

        for dart_file in lib_dir.rglob("*.dart"):
            try:
                content = dart_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                logger.warning("Could not read %s", dart_file)
                continue
            for match in IMPORT_PATTERN.finditer(content):
                pkg = match.group(1)
                if pkg in KNOWN_PACKAGES:
                    packages.add(KNOWN_PACKAGES[pkg][0])
                elif pkg not in _SDK_PACKAGES:
                    packages.add(pkg)

        logger.info("Scanned imports, found %d external packages", len(packages))
        return packages

    @staticmethod
    def _parse_existing_deps(pubspec_content: str) -> set[str]:
        """Extract dependency names already declared in pubspec.yaml."""
        deps: set[str] = set()
        in_deps = False

        for line in pubspec_content.splitlines():
            stripped = line.strip()

            # Detect section headers.
            if re.match(r"^(dependencies|dev_dependencies)\s*:", stripped):
                in_deps = True
                continue
            if re.match(r"^\w+\s*:", stripped) and not line.startswith(" "):
                in_deps = False
                continue

            if in_deps and stripped and not stripped.startswith("#"):
                m = re.match(r"^(\w[\w-]*)\s*:", stripped)
                if m:
                    deps.add(m.group(1))

        return deps

    def _insert_dep(self, content: str, name: str, version: str) -> str:
        """Insert a single dependency line after the ``dependencies:`` header."""
        lines = content.splitlines()
        result: list[str] = []
        inserted = False

        for i, line in enumerate(lines):
            result.append(line)
            if not inserted and line.strip() == "dependencies:":
                if version.startswith("sdk:"):
                    result.append(f"  {name}:")
                    result.append(f"    {version}")
                else:
                    result.append(f"  {name}: {version}")
                inserted = True

        if not inserted:
            result.append("")
            result.append("dependencies:")
            if version.startswith("sdk:"):
                result.append(f"  {name}:")
                result.append(f"    {version}")
            else:
                result.append(f"  {name}: {version}")

        return "\n".join(result)

    def update_pubspec(self, project_path: Path, packages: set[str] | None = None) -> str:
        """Add missing packages to pubspec.yaml dependencies section.

        If *packages* is ``None``, imports are scanned automatically via
        :meth:`scan_imports`.

        Args:
            project_path: Root of the Flutter project.
            packages: Optional pre-computed set of required package names.

        Returns:
            The updated pubspec.yaml content (also written to disk).
        """
        pubspec_path = project_path / "pubspec.yaml"
        if not pubspec_path.exists():
            raise FileNotFoundError(f"pubspec.yaml not found in {project_path}")

        content = pubspec_path.read_text(encoding="utf-8")

        if packages is None:
            packages = self.scan_imports(project_path)

        # Determine the project's own package name so we can exclude self-imports.
        name_match = re.search(r"^name:\s*(\S+)", content, re.MULTILINE)
        own_name = name_match.group(1) if name_match else ""

        external = packages - _SDK_PACKAGES - {own_name}
        existing = self._parse_existing_deps(content)
        missing = external - existing

        if not missing:
            logger.info("All dependencies are present in pubspec.yaml")
            return content

        logger.info("Missing dependencies to add: %s", sorted(missing))

        for pkg_name in sorted(missing):
            if pkg_name in KNOWN_PACKAGES:
                dep_name, dep_version = KNOWN_PACKAGES[pkg_name]
            else:
                dep_name = pkg_name
                dep_version = "any"
                logger.warning(
                    "Unknown package '%s' - adding with 'any' version; pin manually.",
                    pkg_name,
                )
            content = self._insert_dep(content, dep_name, dep_version)
            logger.info("Added dependency: %s: %s", dep_name, dep_version)

        pubspec_path.write_text(content, encoding="utf-8")
        logger.info("Updated pubspec.yaml with %d new dependencies", len(missing))
        return content
