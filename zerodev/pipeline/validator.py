"""Validate that LLM output is actual code, not prose descriptions."""
from __future__ import annotations

import re

# Patterns that indicate real Dart code (at least one must match at line start)
_DART_CODE_MARKERS = re.compile(
    r"^(import |library |part |export |class |abstract |mixin |enum |typedef |"
    r"void |final |const |var |int |double |String |bool |List[\s<]|Map[\s<]|Widget[\s(<]|"
    r"Future[\s<]|Stream[\s<]|@override|//|/\*)",
    re.MULTILINE,
)

# Patterns that indicate prose/confirmation text (any match = reject)
_PROSE_MARKERS = re.compile(
    r"(The file has been |File written|It includes:|It contains |has been generated|"
    r"has been created|following dependencies|following features)",
    re.IGNORECASE,
)

# Patterns that indicate real YAML content (key: value structure)
_YAML_KEY_VALUE = re.compile(r"^\s*\w[\w\s-]*:\s*\S", re.MULTILINE)


def parse_multi_file_output(text: str) -> dict[str, str]:
    """Parse ===FILE: path===...===END=== blocks into {path: content}."""
    matches = re.findall(
        r"===FILE:\s*(.+?)===\n(.*?)===END===", text, re.DOTALL,
    )
    return {path.strip(): code.strip() for path, code in matches}


def is_valid_dart_code(text: str) -> bool:
    """Return True if *text* looks like actual Dart source code.

    Rejects empty/whitespace-only strings, and rejects LLM confirmation prose
    like "The file has been generated at lib/main.dart. It includes: ...".
    """
    stripped = text.strip()
    if not stripped:
        return False
    if _PROSE_MARKERS.search(stripped):
        return False
    if not _DART_CODE_MARKERS.search(stripped):
        return False
    return True


def is_valid_yaml(text: str) -> bool:
    """Return True if *text* looks like actual YAML content.

    Rejects empty/whitespace-only strings, and rejects LLM confirmation prose.
    Requires at least one key: value line to be present.
    """
    stripped = text.strip()
    if not stripped:
        return False
    if _PROSE_MARKERS.search(stripped):
        return False
    if not _YAML_KEY_VALUE.search(stripped):
        return False
    return True
