from __future__ import annotations

import pytest

from zerodev.pipeline.validator import parse_multi_file_output


def test_single_file():
    text = "===FILE: lib/main.dart===\nvoid main() {}\n===END==="
    result = parse_multi_file_output(text)
    assert result == {"lib/main.dart": "void main() {}"}


def test_multiple_files():
    text = (
        "===FILE: lib/main.dart===\nvoid main() {}\n===END===\n"
        "===FILE: lib/app.dart===\nclass App {}\n===END==="
    )
    result = parse_multi_file_output(text)
    assert result == {
        "lib/main.dart": "void main() {}",
        "lib/app.dart": "class App {}",
    }


def test_strips_whitespace_from_path():
    text = "===FILE:  lib/main.dart ===\nvoid main() {}\n===END==="
    result = parse_multi_file_output(text)
    assert "lib/main.dart" in result
    assert result["lib/main.dart"] == "void main() {}"


def test_no_matches():
    result = parse_multi_file_output("no files here")
    assert result == {}


def test_preserves_internal_newlines():
    content = "line one\nline two\nline three"
    text = f"===FILE: lib/main.dart===\n{content}\n===END==="
    result = parse_multi_file_output(text)
    assert "lib/main.dart" in result
    assert "line one" in result["lib/main.dart"]
    assert "line two" in result["lib/main.dart"]
    assert "line three" in result["lib/main.dart"]
