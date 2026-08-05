"""Build native HarmonyOS projects into ``.hap`` packages.

Unlike the Flutter path (which needs a separate ~10GB flutter-ohos SDK fork),
this builder drives the toolchain that ships inside DevEco Studio -- hvigor,
ohpm and its bundled Node runtime -- so a machine with DevEco Studio installed
can produce a real ``.hap`` with nothing else set up.

Discovery order for the DevEco installation:

1. ``DEVECO_HOME`` / ``DEVECO_SDK_HOME`` env or the matching Dashboard setting
2. the standard install location for the current platform
3. any sibling install found next to it

The build environment (``DEVECO_SDK_HOME``, ``NODE_HOME``, ``PATH``) is set up
per invocation rather than assumed to be in the user's shell profile, because
the pipeline runs unattended from a daemon with a minimal environment.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from zerodev.builder.flutter_builder import BuildResult
from zerodev.settings_store import effective_setting

logger = logging.getLogger(__name__)

_TIMEOUT_BUILD = 1800  # 30 minutes -- cold ArkTS compiles can be slow
_TIMEOUT_SHORT = 300

# Standard DevEco Studio install roots, in probe order.
_DEVECO_CANDIDATES: tuple[str, ...] = (
    "/Applications/DevEco-Studio.app/Contents",
    "/Applications/DevEco Studio.app/Contents",
    str(Path.home() / "Applications" / "DevEco-Studio.app" / "Contents"),
    "C:/Program Files/Huawei/DevEco Studio",
    "/opt/deveco-studio",
)

# hvigor/ArkTS diagnostics worth surfacing to the auto-fixer.
_ERROR_LINE_RE = re.compile(
    r"^.*(ERROR|ArkTS:ERROR|COMPILE ERROR|error:).*$",
    re.IGNORECASE | re.MULTILINE,
)


class OhosToolchainError(RuntimeError):
    """Raised when no usable HarmonyOS toolchain can be located."""


@dataclass(frozen=True)
class OhosToolchain:
    """Resolved paths to everything needed for a HarmonyOS build."""

    deveco_home: Path
    sdk_home: Path
    hvigorw: Path
    ohpm: Path
    node_home: Path

    @property
    def api_version(self) -> str:
        """API level of the bundled SDK, or "unknown" when undetectable."""
        meta = self.sdk_home / "default" / "openharmony" / "ets" / "oh-uni-package.json"
        if meta.exists():
            try:
                return str(json.loads(meta.read_text(encoding="utf-8")).get("apiVersion", "unknown"))
            except (json.JSONDecodeError, OSError):
                pass
        return "unknown"

    def env(self) -> dict[str, str]:
        """Environment overlay that makes hvigor find the SDK and Node."""
        path_parts = [
            str(self.node_home / "bin"),
            str(self.ohpm.parent),
            os.environ.get("PATH", ""),
        ]
        return {
            "DEVECO_SDK_HOME": str(self.sdk_home),
            "NODE_HOME": str(self.node_home),
            "PATH": os.pathsep.join(p for p in path_parts if p),
        }


@dataclass
class OhosSigningConfig:
    """Release signing material issued by AppGallery Connect.

    All five artifacts come from the AGC console ("Manage APP Certificates" /
    "HarmonyOS App Provision Profile"). Without them hvigor still builds, but
    emits an ``-unsigned.hap`` that AppGallery will reject on upload.
    """

    store_file: str
    store_password: str
    key_alias: str
    key_password: str
    cert_path: str
    profile_path: str
    sign_alg: str = "SHA256withECDSA"

    @classmethod
    def from_settings(cls) -> OhosSigningConfig | None:
        """Build from Dashboard settings / env; ``None`` when incomplete."""
        values = {
            "store_file": effective_setting("ohosSignStoreFile", os.environ.get("OHOS_SIGN_STORE_FILE", "")),
            "store_password": effective_setting(
                "ohosSignStorePassword", os.environ.get("OHOS_SIGN_STORE_PASSWORD", "")
            ),
            "key_alias": effective_setting("ohosSignKeyAlias", os.environ.get("OHOS_SIGN_KEY_ALIAS", "")),
            "key_password": effective_setting("ohosSignKeyPassword", os.environ.get("OHOS_SIGN_KEY_PASSWORD", "")),
            "cert_path": effective_setting("ohosSignCertPath", os.environ.get("OHOS_SIGN_CERT_PATH", "")),
            "profile_path": effective_setting("ohosSignProfilePath", os.environ.get("OHOS_SIGN_PROFILE_PATH", "")),
        }
        missing = [key for key, value in values.items() if not value]
        if missing:
            logger.info("HarmonyOS signing not configured (missing: %s); builds will be unsigned.", ", ".join(missing))
            return None
        return cls(**values)

    def missing_files(self) -> list[str]:
        """Configured paths that do not exist on disk."""
        return [p for p in (self.store_file, self.cert_path, self.profile_path) if not Path(p).expanduser().exists()]

    def to_build_profile_entry(self) -> dict:
        """Render the ``signingConfigs`` entry hvigor expects."""
        return {
            "name": "default",
            "type": "HarmonyOS",
            "material": {
                "storeFile": str(Path(self.store_file).expanduser()),
                "storePassword": self.store_password,
                "keyAlias": self.key_alias,
                "keyPassword": self.key_password,
                "signAlg": self.sign_alg,
                "profile": str(Path(self.profile_path).expanduser()),
                "certpath": str(Path(self.cert_path).expanduser()),
            },
        }


# ---------------------------------------------------------------------------
# Toolchain discovery
# ---------------------------------------------------------------------------


def find_toolchain(deveco_home: str | Path | None = None) -> OhosToolchain:
    """Locate a usable DevEco toolchain or raise :class:`OhosToolchainError`."""
    candidates: list[Path] = []
    explicit = str(deveco_home or "") or effective_setting("devecoHome", os.environ.get("DEVECO_HOME", ""))
    if explicit:
        candidates.append(Path(explicit).expanduser())

    # DEVECO_SDK_HOME points at <deveco>/sdk; accept it and step up one level.
    sdk_env = effective_setting("devecoSdkHome", os.environ.get("DEVECO_SDK_HOME", ""))
    if sdk_env:
        sdk_path = Path(sdk_env).expanduser()
        candidates.append(sdk_path.parent if sdk_path.name == "sdk" else sdk_path)

    candidates.extend(Path(c) for c in _DEVECO_CANDIDATES)

    tried: list[str] = []
    for home in candidates:
        tried.append(str(home))
        toolchain = _probe(home)
        if toolchain is not None:
            logger.info("HarmonyOS toolchain: %s (SDK API %s)", toolchain.deveco_home, toolchain.api_version)
            return toolchain

    raise OhosToolchainError(
        "No DevEco Studio toolchain found. Install DevEco Studio (which bundles the "
        "OpenHarmony SDK, hvigor, ohpm and Node), or set DEVECO_HOME to its "
        f"Contents directory. Probed: {', '.join(dict.fromkeys(tried))}"
    )


def _probe(home: Path) -> OhosToolchain | None:
    """Return a toolchain rooted at ``home`` when every required part exists."""
    if not home.is_dir():
        return None
    sdk = home / "sdk"
    hvigorw = home / "tools" / "hvigor" / "bin" / "hvigorw"
    ohpm = home / "tools" / "ohpm" / "bin" / "ohpm"
    node_home = home / "tools" / "node"
    if not (sdk.is_dir() and hvigorw.exists() and node_home.is_dir()):
        return None
    return OhosToolchain(deveco_home=home, sdk_home=sdk, hvigorw=hvigorw, ohpm=ohpm, node_home=node_home)


def toolchain_available() -> bool:
    """Cheap check used by the Dashboard / preflight reporting."""
    try:
        find_toolchain()
    except OhosToolchainError:
        return False
    return True


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class OhosBuilder:
    """Drive hvigor to turn a scaffolded ArkTS project into a ``.hap``."""

    def __init__(self, deveco_home: str | Path | None = None) -> None:
        self.toolchain = find_toolchain(deveco_home)

    # -- internals ---------------------------------------------------------

    async def _run(
        self,
        args: Sequence[str],
        *,
        cwd: str | Path,
        timeout: float = _TIMEOUT_SHORT,
        label: str = "",
    ) -> BuildResult:
        cmd_str = " ".join(str(a) for a in args)
        label = label or cmd_str
        logger.info("Running: %s (cwd=%s)", label, cwd)

        try:
            proc = await asyncio.create_subprocess_exec(
                *[str(a) for a in args],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
                env={**os.environ, **self.toolchain.env()},
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            logger.error("HarmonyOS build timed out after %ss: %s", timeout, label)
            try:
                proc.kill()  # type: ignore[union-attr]
            except ProcessLookupError:
                pass
            return BuildResult(success=False, command=cmd_str, errors=[f"Timed out after {timeout}s"])
        except FileNotFoundError:
            msg = f"Executable not found: {args[0]}"
            logger.error(msg)
            return BuildResult(success=False, command=cmd_str, errors=[msg])

        stdout = stdout_bytes.decode(errors="replace")
        stderr = stderr_bytes.decode(errors="replace")
        rc = proc.returncode or 0
        return BuildResult(
            success=rc == 0,
            command=cmd_str,
            stdout=stdout,
            stderr=stderr,
            return_code=rc,
            errors=[] if rc == 0 else extract_errors(stdout + "\n" + stderr) or [f"Exit code {rc}"],
        )

    # -- public API --------------------------------------------------------

    async def ohpm_install(self, project_path: str | Path) -> BuildResult:
        """Install ohpm dependencies. A no-op for dependency-free projects."""
        return await self._run(
            [self.toolchain.ohpm, "install", "--all"],
            cwd=project_path,
            timeout=_TIMEOUT_SHORT,
            label="ohpm install",
        )

    async def clean(self, project_path: str | Path) -> BuildResult:
        return await self._run(
            [self.toolchain.hvigorw, "clean", "--no-daemon"],
            cwd=project_path,
            timeout=_TIMEOUT_SHORT,
            label="hvigor clean",
        )

    async def build_hap(
        self,
        project_path: str | Path,
        *,
        build_mode: str = "release",
        signing: OhosSigningConfig | None = None,
        product: str = "default",
        use_daemon: bool = False,
    ) -> BuildResult:
        """Assemble a ``.hap``, applying release signing when configured.

        ``build_mode`` is ``debug`` or ``release``. When ``signing`` is given it
        is written into the project's ``build-profile.json5`` first, so the
        artifact comes out signed and uploadable to AppGallery; otherwise hvigor
        emits ``*-unsigned.hap`` and this is reported in the result.
        """
        project = Path(project_path).expanduser().resolve()
        if not (project / "build-profile.json5").exists():
            return BuildResult(
                success=False,
                errors=[f"Not a HarmonyOS project (no build-profile.json5): {project}"],
            )

        if signing is not None:
            missing = signing.missing_files()
            if missing:
                return BuildResult(
                    success=False,
                    errors=[f"Signing material not found on disk: {', '.join(missing)}"],
                )
            apply_signing_config(project, signing)

        args = [
            self.toolchain.hvigorw,
            "assembleHap",
            "--mode",
            "module",
            "-p",
            f"product={product}",
            "-p",
            f"buildMode={build_mode}",
        ]
        if not use_daemon:
            # Unattended runs favour a clean process over daemon reuse: a stale
            # daemon holding an old SDK path is a recurring source of failures.
            args.append("--no-daemon")

        result = await self._run(args, cwd=project, timeout=_TIMEOUT_BUILD, label=f"hvigor assembleHap ({build_mode})")

        hap = find_hap(project)
        if result.success:
            if hap is None:
                result.success = False
                result.errors.append("hvigor reported success but no .hap was produced.")
            else:
                result.artifact_path = str(hap)
                if "unsigned" in hap.name:
                    logger.warning("Built an UNSIGNED hap: %s (AppGallery upload requires signing).", hap.name)
        return result

    async def build_from_scratch(
        self,
        project_path: str | Path,
        *,
        build_mode: str = "release",
        signing: OhosSigningConfig | None = None,
    ) -> BuildResult:
        """Full pipeline: dependency install then assemble."""
        project = Path(project_path)
        if _has_dependencies(project):
            install = await self.ohpm_install(project)
            if not install.success:
                return install
        return await self.build_hap(project, build_mode=build_mode, signing=signing)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_dependencies(project: Path) -> bool:
    """True when any oh-package.json5 declares dependencies worth installing."""
    for package_file in project.rglob("oh-package.json5"):
        if "node_modules" in package_file.parts or "oh_modules" in package_file.parts:
            continue
        try:
            text = package_file.read_text(encoding="utf-8")
        except OSError:
            continue
        # Cheap structural check -- these files are JSON5 and may carry comments.
        if re.search(r'"(dev)?[Dd]ependencies"\s*:\s*\{\s*"', text):
            return True
    return False


def apply_signing_config(project: Path, signing: OhosSigningConfig) -> None:
    """Write ``signingConfigs`` into the project's ``build-profile.json5``.

    The scaffolder emits strict JSON, so this reads and rewrites it as JSON. A
    hand-edited JSON5 file with comments is left untouched (with a warning)
    rather than corrupted.
    """
    profile_path = project / "build-profile.json5"
    raw = profile_path.read_text(encoding="utf-8")
    try:
        profile = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "build-profile.json5 at %s is not plain JSON (JSON5 comments?); "
            "skipping automatic signing injection. Configure signingConfigs manually.",
            profile_path,
        )
        return

    profile.setdefault("app", {})["signingConfigs"] = [signing.to_build_profile_entry()]
    for product in profile["app"].get("products", []):
        product["signingConfig"] = "default"
    profile_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("Applied HarmonyOS signing config to %s", profile_path)


def find_hap(project: Path) -> Path | None:
    """Locate the built ``.hap``, preferring a signed artifact and newest mtime."""
    haps = [p for p in project.rglob("*.hap") if p.is_file()]
    if not haps:
        return None
    signed = [h for h in haps if "unsigned" not in h.name.lower()]
    pool = signed or haps
    return max(pool, key=lambda p: p.stat().st_mtime)


def extract_errors(output: str, limit: int = 20) -> list[str]:
    """Pull compiler/hvigor error lines out of build output for the auto-fixer."""
    seen: list[str] = []
    for match in _ERROR_LINE_RE.finditer(output):
        line = match.group(0).strip()
        # hvigor colourises output; strip ANSI so downstream matching is stable.
        line = re.sub(r"\x1b\[[0-9;]*m", "", line)
        if line and line not in seen:
            seen.append(line)
        if len(seen) >= limit:
            break
    return seen
