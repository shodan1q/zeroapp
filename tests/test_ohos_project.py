"""Tests for the HarmonyOS ArkTS project scaffolder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zerodev.generator.ohos_project import (
    ENTRY_HTML,
    OhosAppSpec,
    OhosScaffoldError,
    make_bundle_name,
    scaffold_ohos_project,
    slugify_bundle_segment,
)


def _spec(**overrides) -> OhosAppSpec:
    base = {
        "app_name": "静心冥想",
        "bundle_name": "com.zerodev.mindful",
        "description": "每日冥想与呼吸练习",
    }
    base.update(overrides)
    return OhosAppSpec(**base)


# ── Naming ──────────────────────────────────────────────────────


def test_slugify_replaces_illegal_characters() -> None:
    assert slugify_bundle_segment("Habit Tracker 2.0!") == "habit_tracker_2_0"


def test_slugify_prefixes_when_starting_with_digit() -> None:
    # Bundle segments must start with a letter.
    assert slugify_bundle_segment("2048game").startswith("app")


def test_slugify_falls_back_for_unmappable_names() -> None:
    assert slugify_bundle_segment("静心冥想") == "app"


def test_make_bundle_name_uses_reverse_domain() -> None:
    assert make_bundle_name("mindful") == "com.zerodev.mindful"


# ── Validation ──────────────────────────────────────────────────


@pytest.mark.parametrize("bundle", ["nodot", "1bad.start", "com..empty", "com.has-dash", ""])
def test_invalid_bundle_names_rejected(bundle: str) -> None:
    with pytest.raises(OhosScaffoldError, match="bundleName"):
        _spec(bundle_name=bundle).validate()


def test_blank_app_name_rejected() -> None:
    with pytest.raises(OhosScaffoldError, match="app_name"):
        _spec(app_name="  ").validate()


def test_scaffold_requires_entry_html(tmp_path: Path) -> None:
    with pytest.raises(OhosScaffoldError, match=ENTRY_HTML):
        scaffold_ohos_project(tmp_path / "proj", _spec(), {"about.html": "<p>x</p>"})


def test_asset_path_cannot_escape_project(tmp_path: Path) -> None:
    with pytest.raises(OhosScaffoldError, match="escapes"):
        scaffold_ohos_project(
            tmp_path / "proj",
            _spec(),
            {ENTRY_HTML: "<html></html>", "../../evil.html": "<html></html>"},
        )


# ── Layout ──────────────────────────────────────────────────────


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return scaffold_ohos_project(
        tmp_path / "proj",
        _spec(),
        {ENTRY_HTML: "<!doctype html><title>t</title>", "styles.css": ":root{}"},
    )


def test_scaffold_writes_every_required_file(project: Path) -> None:
    required = [
        "build-profile.json5",
        "hvigorfile.ts",
        "oh-package.json5",
        "hvigor/hvigor-config.json5",
        "AppScope/app.json5",
        "entry/build-profile.json5",
        "entry/hvigorfile.ts",
        "entry/src/main/module.json5",
        "entry/src/main/ets/entryability/EntryAbility.ets",
        "entry/src/main/ets/pages/Index.ets",
        "entry/src/main/resources/base/profile/main_pages.json",
        "entry/src/main/resources/base/media/startIcon.png",
    ]
    missing = [name for name in required if not (project / name).exists()]
    assert missing == []


def test_web_assets_land_in_rawfile(project: Path) -> None:
    rawfile = project / "entry/src/main/resources/rawfile"
    assert (rawfile / ENTRY_HTML).read_text(encoding="utf-8").startswith("<!doctype html>")
    assert (rawfile / "styles.css").exists()


def test_app_identity_written_to_appscope(project: Path) -> None:
    app_json = json.loads((project / "AppScope/app.json5").read_text(encoding="utf-8"))["app"]
    assert app_json["bundleName"] == "com.zerodev.mindful"
    assert app_json["versionName"] == "1.0.0"

    strings = json.loads((project / "AppScope/resources/base/element/string.json").read_text(encoding="utf-8"))
    assert strings["string"][0]["value"] == "静心冥想"


def test_index_page_loads_entry_html_from_rawfile(project: Path) -> None:
    page = (project / "entry/src/main/ets/pages/Index.ets").read_text(encoding="utf-8")
    assert f"$rawfile('{ENTRY_HTML}')" in page
    # Back navigation should walk web history before leaving the app.
    assert "accessBackward" in page


def test_internet_permission_declared(project: Path) -> None:
    module = json.loads((project / "entry/src/main/module.json5").read_text(encoding="utf-8"))["module"]
    names = [p["name"] for p in module["requestPermissions"]]
    assert "ohos.permission.INTERNET" in names


def test_generated_icons_are_valid_pngs(project: Path) -> None:
    from PIL import Image

    for name in ("background.png", "foreground.png", "startIcon.png"):
        image = Image.open(project / "entry/src/main/resources/base/media" / name)
        assert image.size == (1024, 1024)


def test_immersive_is_the_default(project: Path) -> None:
    # Confining the web view to the safe area makes every env(safe-area-inset-*)
    # in the generated CSS evaluate to zero, and leaves the system-bar strips
    # painted in the shell's colour rather than the app's -- white bands above
    # and below a beige page on a real device.
    assert "expandSafeArea" in (project / "entry/src/main/ets/pages/Index.ets").read_text(encoding="utf-8")


def test_immersive_can_be_switched_off(tmp_path: Path) -> None:
    plain = scaffold_ohos_project(tmp_path / "plain", _spec(immersive=False), {ENTRY_HTML: "<html></html>"})
    assert "expandSafeArea" not in (plain / "entry/src/main/ets/pages/Index.ets").read_text(encoding="utf-8")


def test_shell_background_follows_the_app_palette(tmp_path: Path) -> None:
    project = scaffold_ohos_project(
        tmp_path / "tint",
        _spec(start_background="#F6EFDF", start_background_dark="#14100C"),
        {ENTRY_HTML: "<html></html>"},
    )
    light = json.loads((project / "entry/src/main/resources/base/element/color.json").read_text(encoding="utf-8"))
    dark = json.loads((project / "entry/src/main/resources/dark/element/color.json").read_text(encoding="utf-8"))
    assert light["color"][0]["value"] == "#F6EFDF"
    assert dark["color"][0]["value"] == "#14100C"


def test_rescaffold_clears_stale_pages(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    scaffold_ohos_project(root, _spec(), {ENTRY_HTML: "<html></html>", "old.html": "<p>old</p>"})
    scaffold_ohos_project(root, _spec(), {ENTRY_HTML: "<html></html>"})
    assert not (root / "entry/src/main/resources/rawfile/old.html").exists()
