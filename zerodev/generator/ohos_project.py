"""Scaffold a native HarmonyOS (ArkTS, Stage model) project around web assets.

The generated app is a thin ArkTS shell whose entire UI is an ArkWeb ``Web``
component pointing at ``$rawfile('index.html')``. Everything the user sees is
the HTML/CSS/JS produced by :mod:`zerodev.generator.webapp_generator`, packaged
into ``entry/src/main/resources/rawfile`` so the app runs fully offline.

Why native ArkTS instead of Flutter-for-OHOS: the DevEco Studio toolchain that
ships with the OpenHarmony SDK (hvigor + ohpm + node) can build this project to
a real ``.hap`` with no additional SDK install, while the flutter-ohos path
needs a separate ~10GB fork of the Flutter SDK. See
:mod:`zerodev.builder.ohos_builder`.

The file layout mirrors the canonical DevEco "Empty Ability" Stage-model
project, verified against the SDK bundled with DevEco Studio (API 24).
"""

from __future__ import annotations

import io
import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Lowest SDK the generated app declares. Keeping this at the HarmonyOS NEXT
# baseline (API 12) rather than the newest installed API maximises the range of
# devices that can install the result; newer SDKs build it fine.
DEFAULT_COMPATIBLE_SDK = "5.0.0(12)"

DEFAULT_DEVICE_TYPES: tuple[str, ...] = ("phone", "tablet", "2in1")

# Entry HTML file inside rawfile/ that the Web component loads.
ENTRY_HTML = "index.html"

_BUNDLE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$")


class OhosScaffoldError(RuntimeError):
    """Raised when the project spec cannot produce a valid HarmonyOS project."""


@dataclass
class OhosAppSpec:
    """Everything needed to stamp out a HarmonyOS WebView shell."""

    app_name: str
    bundle_name: str
    description: str = ""
    version_name: str = "1.0.0"
    version_code: int = 1000000
    vendor: str = "zerodev"
    # Splash-screen background; also the fallback page background.
    start_background: str = "#FFFFFF"
    start_background_dark: str = "#000000"
    # Brand colour used for the generated launcher icon.
    theme_color: str = "#0A84FF"
    compatible_sdk: str = DEFAULT_COMPATIBLE_SDK
    target_sdk: str = DEFAULT_COMPATIBLE_SDK
    device_types: tuple[str, ...] = DEFAULT_DEVICE_TYPES
    # Draw the web view under the status/navigation bars. The HTML then owns
    # its own safe-area padding via env(safe-area-inset-*). Off by default so a
    # generated page can never hide content behind system bars.
    immersive: bool = False
    # Declared so the shell can load remote content or call APIs from JS.
    permissions: tuple[str, ...] = ("ohos.permission.INTERNET",)
    module_name: str = "entry"
    extra_files: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        """Reject specs that hvigor would fail on, with an actionable message."""
        if not self.app_name.strip():
            raise OhosScaffoldError("app_name must not be empty.")
        if not _BUNDLE_RE.match(self.bundle_name):
            raise OhosScaffoldError(
                f"Invalid bundleName {self.bundle_name!r}. Expected reverse-domain form "
                "such as 'com.zerodev.myapp' (letters, digits and underscores, at least one dot)."
            )
        if not 0 < self.version_code < 2**31:
            raise OhosScaffoldError(f"versionCode out of range: {self.version_code}")


# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------


def slugify_bundle_segment(text: str, fallback: str = "app") -> str:
    """Turn arbitrary text into one legal bundleName segment.

    HarmonyOS bundle segments must start with a letter and contain only
    letters, digits and underscores, so CJK app names cannot be transliterated
    directly -- callers should pass a latin slug when they have one.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"{fallback}_{cleaned}" if cleaned else fallback
    return cleaned[:32].rstrip("_") or fallback


def make_bundle_name(app_slug: str, org: str = "com.zerodev") -> str:
    """Build a valid bundleName from an app slug under ``org``."""
    return f"{org}.{slugify_bundle_segment(app_slug)}"


# ---------------------------------------------------------------------------
# Launcher icon generation (no external assets required)
# ---------------------------------------------------------------------------


def _parse_hex_color(value: str, fallback: tuple[int, int, int] = (10, 132, 255)) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    if len(text) != 6:
        return fallback
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return fallback


def _icon_glyph(app_name: str) -> str:
    """Pick 1-2 characters to stamp on the generated icon."""
    stripped = app_name.strip()
    if not stripped:
        return "A"
    first = stripped[0]
    # CJK characters read well alone; latin words read better as two letters.
    if ord(first) > 0x2E80:
        return first
    letters = re.sub(r"[^A-Za-z0-9]", "", stripped)
    return (letters[:2] or first).upper()


def render_icon_layers(spec: OhosAppSpec, size: int = 1024) -> tuple[bytes, bytes]:
    """Render ``(background_png, foreground_png)`` for the layered app icon.

    HarmonyOS layered icons composite a full-bleed background under a
    transparent foreground, so the launcher can animate them independently.
    """
    from PIL import Image, ImageDraw  # noqa: PLC0415 - optional heavy import

    base = _parse_hex_color(spec.theme_color)
    # A subtle vertical gradient reads as intentional design rather than a flat
    # placeholder, and stays legible behind the foreground glyph.
    top = tuple(min(255, int(c * 0.75 + 60)) for c in base)
    bottom = tuple(int(c * 0.62) for c in base)

    background = Image.new("RGB", (size, size), base)
    draw = ImageDraw.Draw(background)
    for y in range(size):
        ratio = y / max(1, size - 1)
        draw.line(
            [(0, y), (size, y)],
            fill=tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3)),
        )

    foreground = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    fdraw = ImageDraw.Draw(foreground)
    glyph = _icon_glyph(spec.app_name)
    font = _load_icon_font(int(size * (0.40 if len(glyph) > 1 else 0.46)))
    if font is not None:
        box = fdraw.textbbox((0, 0), glyph, font=font)
        fdraw.text(
            ((size - (box[2] - box[0])) / 2 - box[0], (size - (box[3] - box[1])) / 2 - box[1]),
            glyph,
            font=font,
            fill=(255, 255, 255, 235),
        )
    else:
        # No usable font: fall back to a geometric mark so the icon is never blank.
        inset = size * 0.3
        fdraw.ellipse([inset, inset, size - inset, size - inset], outline=(255, 255, 255, 235), width=int(size * 0.05))

    return _png_bytes(background), _png_bytes(foreground)


def _load_icon_font(px: int):
    """Load a font that can render CJK, falling back through common macOS paths."""
    from PIL import ImageFont  # noqa: PLC0415

    candidates = (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    )
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, px)
            except OSError:
                continue
    return None


def _png_bytes(image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# ArkTS sources
# ---------------------------------------------------------------------------


def _index_page_ets(spec: OhosAppSpec) -> str:
    """The single ArkTS page: a full-bleed Web component over local rawfile."""
    safe_area = (
        "\n        .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])"
        if spec.immersive
        else ""
    )
    return f"""\
import {{ webview }} from '@kit.ArkWeb';
import {{ BusinessError }} from '@kit.BasicServicesKit';
import {{ hilog }} from '@kit.PerformanceAnalysisKit';

const DOMAIN = 0x0000;

@Entry
@Component
struct Index {{
  private controller: webview.WebviewController = new webview.WebviewController();
  @State loadError: string = '';

  build() {{
    Stack() {{
      Web({{ src: $rawfile('{ENTRY_HTML}'), controller: this.controller }})
        .width('100%')
        .height('100%')
        .backgroundColor($r('app.color.start_window_background'))
        .darkMode(WebDarkMode.Auto)
        .forceDarkAccess(false)
        .fileAccess(true)
        .domStorageAccess(true)
        .databaseAccess(true)
        .javaScriptAccess(true)
        .imageAccess(true)
        .mixedMode(MixedMode.Compatible)
        .zoomAccess(false)
        .horizontalScrollBarAccess(false)
        .verticalScrollBarAccess(false)
        .overviewModeAccess(false)
        .cacheMode(CacheMode.Default)
        .onErrorReceive((event) => {{
          if (event) {{
            this.loadError = event.error.getErrorInfo();
            hilog.error(DOMAIN, 'zerodev', 'web load error: %{{public}}s', this.loadError);
          }}
        }}){safe_area}

      if (this.loadError !== '') {{
        Column() {{
          Text('页面加载失败')
            .fontSize(18)
            .fontWeight(FontWeight.Medium)
          Text(this.loadError)
            .fontSize(13)
            .opacity(0.6)
            .margin({{ top: 8 }})
          Button('重新加载')
            .margin({{ top: 20 }})
            .onClick(() => {{
              this.loadError = '';
              try {{
                this.controller.refresh();
              }} catch (err) {{
                hilog.error(DOMAIN, 'zerodev', 'refresh failed: %{{public}}s', (err as BusinessError).message);
              }}
            }})
        }}
        .width('100%')
        .height('100%')
        .justifyContent(FlexAlign.Center)
        .backgroundColor($r('app.color.start_window_background'))
      }}
    }}
    .width('100%')
    .height('100%')
  }}

  // Hardware/gesture back navigates web history before leaving the app.
  onBackPress(): boolean {{
    try {{
      if (this.controller.accessBackward()) {{
        this.controller.backward();
        return true;
      }}
    }} catch (err) {{
      hilog.warn(DOMAIN, 'zerodev', 'backward failed: %{{public}}s', (err as BusinessError).message);
    }}
    return false;
  }}
}}
"""


def _entry_ability_ets(spec: OhosAppSpec) -> str:
    immersive_block = (
        """
      const win = windowStage.getMainWindowSync();
      win.setWindowLayoutFullScreen(true).catch((err: BusinessError) => {
        hilog.warn(DOMAIN, 'zerodev', 'fullscreen failed: %{public}s', err.message);
      });
"""
        if spec.immersive
        else ""
    )
    return f"""\
import {{ AbilityConstant, ConfigurationConstant, UIAbility, Want }} from '@kit.AbilityKit';
import {{ BusinessError }} from '@kit.BasicServicesKit';
import {{ hilog }} from '@kit.PerformanceAnalysisKit';
import {{ window }} from '@kit.ArkUI';

const DOMAIN = 0x0000;

export default class EntryAbility extends UIAbility {{
  onCreate(want: Want, launchParam: AbilityConstant.LaunchParam): void {{
    this.context.getApplicationContext().setColorMode(ConfigurationConstant.ColorMode.COLOR_MODE_NOT_SET);
    hilog.info(DOMAIN, 'zerodev', '%{{public}}s', 'Ability onCreate');
  }}

  onDestroy(): void {{
    hilog.info(DOMAIN, 'zerodev', '%{{public}}s', 'Ability onDestroy');
  }}

  onWindowStageCreate(windowStage: window.WindowStage): void {{{immersive_block}
    windowStage.loadContent('pages/Index', (err) => {{
      if (err.code) {{
        hilog.error(DOMAIN, 'zerodev', 'Failed to load content: %{{public}}s', JSON.stringify(err));
        return;
      }}
      hilog.info(DOMAIN, 'zerodev', '%{{public}}s', 'Succeeded in loading the content.');
    }});
  }}

  onWindowStageDestroy(): void {{
    hilog.info(DOMAIN, 'zerodev', '%{{public}}s', 'Ability onWindowStageDestroy');
  }}

  onForeground(): void {{
    hilog.info(DOMAIN, 'zerodev', '%{{public}}s', 'Ability onForeground');
  }}

  onBackground(): void {{
    hilog.info(DOMAIN, 'zerodev', '%{{public}}s', 'Ability onBackground');
  }}
}}
"""


_BACKUP_ABILITY_ETS = """\
import { hilog } from '@kit.PerformanceAnalysisKit';
import { BackupExtensionAbility, BundleVersion } from '@kit.CoreFileKit';

const DOMAIN = 0x0000;

export default class EntryBackupAbility extends BackupExtensionAbility {
  async onBackup() {
    hilog.info(DOMAIN, 'zerodev', 'onBackup ok');
    await Promise.resolve();
  }

  async onRestore(bundleVersion: BundleVersion) {
    hilog.info(DOMAIN, 'zerodev', 'onRestore ok %{public}s', JSON.stringify(bundleVersion));
    await Promise.resolve();
  }
}
"""


# ---------------------------------------------------------------------------
# Config files
# ---------------------------------------------------------------------------


def _json5(payload: dict) -> str:
    """Serialise config as JSON (a strict subset of JSON5, which hvigor reads)."""
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _module_json5(spec: OhosAppSpec) -> str:
    module: dict = {
        "name": spec.module_name,
        "type": "entry",
        "description": "$string:module_desc",
        "mainElement": "EntryAbility",
        "deviceTypes": list(spec.device_types),
        "deliveryWithInstall": True,
        "installationFree": False,
        "pages": "$profile:main_pages",
        "abilities": [
            {
                "name": "EntryAbility",
                "srcEntry": "./ets/entryability/EntryAbility.ets",
                "description": "$string:EntryAbility_desc",
                "icon": "$media:layered_image",
                "label": "$string:EntryAbility_label",
                "startWindowIcon": "$media:startIcon",
                "startWindowBackground": "$color:start_window_background",
                "exported": True,
                "skills": [{"entities": ["entity.system.home"], "actions": ["action.system.home"]}],
            }
        ],
        "extensionAbilities": [
            {
                "name": "EntryBackupAbility",
                "srcEntry": "./ets/entrybackupability/EntryBackupAbility.ets",
                "type": "backup",
                "exported": False,
                "metadata": [{"name": "ohos.extension.backup", "resource": "$profile:backup_config"}],
            }
        ],
    }
    if spec.permissions:
        module["requestPermissions"] = [{"name": name} for name in spec.permissions]
    return _json5({"module": module})


def _build_profile_json5(spec: OhosAppSpec) -> str:
    return _json5(
        {
            "app": {
                "signingConfigs": [],
                "products": [
                    {
                        "name": "default",
                        "signingConfig": "default",
                        "compatibleSdkVersion": spec.compatible_sdk,
                        "targetSdkVersion": spec.target_sdk,
                        "runtimeOS": "HarmonyOS",
                    }
                ],
                "buildModeSet": [{"name": "debug"}, {"name": "release"}],
            },
            "modules": [
                {
                    "name": spec.module_name,
                    "srcPath": f"./{spec.module_name}",
                    "targets": [{"name": "default", "applyToProducts": ["default"]}],
                }
            ],
        }
    )


_ENTRY_BUILD_PROFILE = _json5(
    {
        "apiType": "stageMode",
        "buildOption": {},
        "buildOptionSet": [
            {
                "name": "release",
                "arkOptions": {"obfuscation": {"ruleOptions": {"enable": False, "files": ["./obfuscation-rules.txt"]}}},
            }
        ],
        "targets": [{"name": "default"}],
    }
)

_APP_HVIGORFILE = """\
import { appTasks } from '@ohos/hvigor-ohos-plugin';

export default {
    system: appTasks,
    plugins: []
}
"""

_MODULE_HVIGORFILE = """\
import { hapTasks } from '@ohos/hvigor-ohos-plugin';

export default {
    system: hapTasks,
    plugins: []
}
"""

_HVIGOR_CONFIG = _json5({"modelVersion": "5.0.0", "dependencies": {}, "execution": {}, "logging": {}})

_OBFUSCATION_RULES = """\
# Obfuscation is disabled for generated apps so crash reports stay readable.
-enable-property-obfuscation
-enable-toplevel-obfuscation
"""


# ---------------------------------------------------------------------------
# Scaffolding
# ---------------------------------------------------------------------------


def scaffold_ohos_project(
    project_dir: str | Path,
    spec: OhosAppSpec,
    web_assets: Mapping[str, str],
    *,
    binary_assets: Mapping[str, bytes] | None = None,
    clean: bool = True,
) -> Path:
    """Write a complete, buildable HarmonyOS project to ``project_dir``.

    Parameters
    ----------
    project_dir:
        Destination directory; created if missing.
    spec:
        App identity and shell behaviour.
    web_assets:
        Text assets keyed by path relative to ``resources/rawfile`` -- must
        contain ``index.html``.
    binary_assets:
        Optional binary rawfile entries (images, fonts) keyed the same way.
    clean:
        Remove a previous scaffold's ``entry/src`` and ``AppScope`` first so a
        regenerated app never inherits stale pages.

    Returns the project root path.
    """
    spec.validate()
    if ENTRY_HTML not in web_assets:
        raise OhosScaffoldError(
            f"web_assets must contain {ENTRY_HTML!r} (the Web component loads it as the entry page); "
            f"got: {sorted(web_assets)[:10]}"
        )

    root = Path(project_dir).expanduser().resolve()
    module = root / spec.module_name
    main = module / "src" / "main"

    if clean:
        for stale in (module / "src", root / "AppScope"):
            if stale.exists():
                _rmtree(stale)

    resources = main / "resources"
    rawfile = resources / "rawfile"
    for directory in (
        main / "ets" / "entryability",
        main / "ets" / "entrybackupability",
        main / "ets" / "pages",
        resources / "base" / "element",
        resources / "base" / "media",
        resources / "base" / "profile",
        resources / "dark" / "element",
        rawfile,
        root / "AppScope" / "resources" / "base" / "element",
        root / "AppScope" / "resources" / "base" / "media",
        root / "hvigor",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    # -- project level -----------------------------------------------------
    _write(root / "build-profile.json5", _build_profile_json5(spec))
    _write(root / "hvigorfile.ts", _APP_HVIGORFILE)
    _write(
        root / "oh-package.json5",
        _json5(
            {
                "modelVersion": "5.0.0",
                "description": spec.description or spec.app_name,
                "dependencies": {},
                "devDependencies": {},
            }
        ),
    )
    _write(root / "hvigor" / "hvigor-config.json5", _HVIGOR_CONFIG)

    # -- AppScope ----------------------------------------------------------
    _write(
        root / "AppScope" / "app.json5",
        _json5(
            {
                "app": {
                    "bundleName": spec.bundle_name,
                    "vendor": spec.vendor,
                    "versionCode": spec.version_code,
                    "versionName": spec.version_name,
                    "icon": "$media:layered_image",
                    "label": "$string:app_name",
                }
            }
        ),
    )
    _write(
        root / "AppScope" / "resources" / "base" / "element" / "string.json",
        _json5({"string": [{"name": "app_name", "value": spec.app_name}]}),
    )
    _write(
        root / "AppScope" / "resources" / "base" / "media" / "layered_image.json",
        _json5({"layered-image": {"background": "$media:background", "foreground": "$media:foreground"}}),
    )

    # -- module level ------------------------------------------------------
    _write(module / "build-profile.json5", _ENTRY_BUILD_PROFILE)
    _write(module / "hvigorfile.ts", _MODULE_HVIGORFILE)
    _write(module / "obfuscation-rules.txt", _OBFUSCATION_RULES)
    _write(
        module / "oh-package.json5",
        _json5(
            {
                "name": spec.module_name,
                "version": "1.0.0",
                "description": spec.description or spec.app_name,
                "main": "",
                "author": spec.vendor,
                "license": "",
                "dependencies": {},
            }
        ),
    )
    _write(main / "module.json5", _module_json5(spec))

    # -- ArkTS sources -----------------------------------------------------
    _write(main / "ets" / "entryability" / "EntryAbility.ets", _entry_ability_ets(spec))
    _write(main / "ets" / "entrybackupability" / "EntryBackupAbility.ets", _BACKUP_ABILITY_ETS)
    _write(main / "ets" / "pages" / "Index.ets", _index_page_ets(spec))

    # -- resources ---------------------------------------------------------
    _write(resources / "base" / "profile" / "main_pages.json", _json5({"src": ["pages/Index"]}))
    _write(resources / "base" / "profile" / "backup_config.json", _json5({"allowToBackupRestore": True}))
    _write(
        resources / "base" / "element" / "string.json",
        _json5(
            {
                "string": [
                    {"name": "module_desc", "value": spec.description or spec.app_name},
                    {"name": "EntryAbility_desc", "value": spec.description or spec.app_name},
                    {"name": "EntryAbility_label", "value": spec.app_name},
                ]
            }
        ),
    )
    _write(
        resources / "base" / "element" / "color.json",
        _json5({"color": [{"name": "start_window_background", "value": spec.start_background}]}),
    )
    _write(
        resources / "dark" / "element" / "color.json",
        _json5({"color": [{"name": "start_window_background", "value": spec.start_background_dark}]}),
    )
    _write(
        resources / "base" / "media" / "layered_image.json",
        _json5({"layered-image": {"background": "$media:background", "foreground": "$media:foreground"}}),
    )

    background_png, foreground_png = render_icon_layers(spec)
    for target in (resources / "base" / "media", root / "AppScope" / "resources" / "base" / "media"):
        (target / "background.png").write_bytes(background_png)
        (target / "foreground.png").write_bytes(foreground_png)
    # startWindowIcon must be a plain (non-layered) image.
    (resources / "base" / "media" / "startIcon.png").write_bytes(foreground_png)

    # -- web assets --------------------------------------------------------
    written = 0
    for rel_path, content in web_assets.items():
        target = _safe_join(rawfile, rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written += 1
    for rel_path, blob in (binary_assets or {}).items():
        target = _safe_join(rawfile, rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
        written += 1

    for rel_path, content in spec.extra_files.items():
        target = _safe_join(root, rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    logger.info(
        "Scaffolded HarmonyOS project %s (bundle=%s) with %d web asset(s) at %s",
        spec.app_name,
        spec.bundle_name,
        written,
        root,
    )
    return root


def _safe_join(base: Path, relative: str) -> Path:
    """Join ``relative`` under ``base``, refusing to escape the base directory."""
    target = (base / relative).resolve()
    if base.resolve() not in target.parents and target != base.resolve():
        raise OhosScaffoldError(f"Asset path escapes the project directory: {relative!r}")
    return target


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _rmtree(path: Path) -> None:
    import shutil  # noqa: PLC0415

    shutil.rmtree(path, ignore_errors=True)
