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

    Rejects empty/whitespace-only strings. Rejects text that is entirely prose
    (no code markers found). Allows text that has some preamble prose as long
    as actual code markers are present.
    """
    stripped = text.strip()
    if not stripped:
        return False
    # Must contain at least one code marker
    if not _DART_CODE_MARKERS.search(stripped):
        return False
    # If prose markers are found but code markers are also present,
    # only reject if the text is very short (likely just a description).
    if _PROSE_MARKERS.search(stripped) and len(stripped.splitlines()) < 5:
        return False
    return True


def is_valid_yaml(text: str) -> bool:
    """Return True if *text* looks like actual YAML content.

    Rejects empty/whitespace-only strings. Requires at least one key: value line.
    Only rejects prose if no YAML structure is found.
    """
    stripped = text.strip()
    if not stripped:
        return False
    # Must have key: value structure
    if not _YAML_KEY_VALUE.search(stripped):
        return False
    # If prose markers are found but YAML is also present,
    # only reject if the text is very short.
    if _PROSE_MARKERS.search(stripped) and len(stripped.splitlines()) < 3:
        return False
    return True
