"""Tests for pipeline output validator."""
from __future__ import annotations

import pytest

from zerodev.pipeline.validator import is_valid_dart_code, is_valid_yaml


# ---------------------------------------------------------------------------
# is_valid_dart_code
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "import 'package:flutter/material.dart';\n\nvoid main() {}",
        "class MyWidget extends StatelessWidget {}",
        "// constants\nconst String appName = 'Test';",
        "enum AppTheme { light, dark }",
        "abstract class BaseRepo {}",
        "final int x = 42;",
        "/* multi-line\n   comment */\nclass Foo {}",
        "@override\nvoid initState() { super.initState(); }",
        "Widget build(BuildContext context) { return Container(); }",
        "Future<void> fetchData() async {}",
        # Code with preamble prose should still be valid (Claude sometimes adds preamble)
        "The file has been implemented:\n\nimport 'package:flutter/material.dart';\n\nclass MyApp extends StatelessWidget {\n  @override\n  Widget build(BuildContext context) {\n    return Container();\n  }\n}",
    ],
)
def test_is_valid_dart_code_valid(text: str) -> None:
    assert is_valid_dart_code(text) is True, f"Expected valid dart code, got False for: {text!r}"


@pytest.mark.parametrize(
    "text",
    [
        "The file has been generated at lib/main.dart. It includes:\n- A MaterialApp widget",
        "File written. It contains six constant classes:\n- AppColors",
        "",
        "   \n\n  ",
        "The pubspec.yaml has been created with the following dependencies:",
        "has been generated successfully",
        "It includes: a main function",
        "following features:\n- dark mode\n- light mode",
    ],
)
def test_is_valid_dart_code_invalid(text: str) -> None:
    assert is_valid_dart_code(text) is False, f"Expected invalid dart code, got True for: {text!r}"


# ---------------------------------------------------------------------------
# is_valid_yaml
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "name: myapp\ndescription: A Flutter app\n\ndependencies:\n  flutter:\n    sdk: flutter",
        "name: test\nversion: 1.0.0",
        "key: value\nlist:\n  - item1\n  - item2",
    ],
)
def test_is_valid_yaml_valid(text: str) -> None:
    assert is_valid_yaml(text) is True, f"Expected valid yaml, got False for: {text!r}"


@pytest.mark.parametrize(
    "text",
    [
        "The pubspec.yaml file has been created with the following dependencies:",
        "",
        "   \n\n  ",
        "File written successfully.",
        "has been created",
        "following dependencies:\n- flutter",
    ],
)
def test_is_valid_yaml_invalid(text: str) -> None:
    assert is_valid_yaml(text) is False, f"Expected invalid yaml, got True for: {text!r}"
