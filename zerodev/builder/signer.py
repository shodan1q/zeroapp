"""Android signing configuration management.

Handles keystore generation, gradle signing config injection, and
status reporting.
"""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from zerodev.config import get_settings

logger = logging.getLogger(__name__)

_TIMEOUT_KEYTOOL = 30


@dataclass
class SigningStatus:
    """Current signing configuration state for a project."""

    configured: bool = False
    keystore_path: Optional[str] = None
    key_alias: str = ""
    errors: List[str] = field(default_factory=list)


@dataclass
class KeystoreInfo:
    """Details of a generated or loaded keystore."""

    path: str
    store_password: str
    key_alias: str
    key_password: str


def _generate_password(length: int = 24) -> str:
    """Generate a strong random password."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class SigningManager:
    """Manage Android signing keystores and gradle configuration."""

    def __init__(self) -> None:
        self._settings = get_settings()

    # ------------------------------------------------------------------
    # Keystore generation
    # ------------------------------------------------------------------

    async def generate_keystore(
        self,
        project_path: str,
        app_name: str,
        org_name: str = "ZeroDev",
    ) -> KeystoreInfo:
        """Generate a new Android signing keystore for *app_name*.

        The keystore is placed under ``<project_path>/android/keystore/``.
        Returns a :class:`KeystoreInfo` with all credentials.

        Raises
        ------
        RuntimeError
            If ``keytool`` is not available or the command fails.
        """
        keystore_dir = Path(project_path) / "android" / "keystore"
        keystore_dir.mkdir(parents=True, exist_ok=True)
        keystore_file = keystore_dir / "release.jks"

        store_password = _generate_password()
        key_password = _generate_password()
        key_alias = "release"

        args = [
            "keytool",
            "-genkeypair",
            "-v",
            "-keystore", str(keystore_file),
            "-alias", key_alias,
            "-keyalg", "RSA",
            "-keysize", "2048",
            "-validity", "10000",
            "-storepass", store_password,
            "-keypass", key_password,
            "-dname", f"CN={app_name},O={org_name},C=US",
        ]

        logger.info("Generating keystore at %s", keystore_file)
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_TIMEOUT_KEYTOOL
            )
        except FileNotFoundError:
            raise RuntimeError(
                "keytool not found. Ensure a JDK is installed and on PATH."
            )
        except asyncio.TimeoutError:
            raise RuntimeError("keytool timed out.")

        if proc.returncode != 0:
            raise RuntimeError(
                f"keytool failed (rc={proc.returncode}): "
                f"{stderr.decode(errors='replace')}"
            )

        # Persist credentials to a key.properties file (gitignored by Flutter).
        props_file = Path(project_path) / "android" / "key.properties"
        props_file.write_text(
            f"storePassword={store_password}\n"
            f"keyPassword={key_password}\n"
            f"keyAlias={key_alias}\n"
            f"storeFile=keystore/release.jks\n",
            encoding="utf-8",
        )
        logger.info("key.properties written to %s", props_file)

        return KeystoreInfo(
            path=str(keystore_file),
            store_password=store_password,
            key_alias=key_alias,
            key_password=key_password,
        )

    # ------------------------------------------------------------------
    # Gradle signing configuration
    # ------------------------------------------------------------------

    def configure_gradle_signing(self, project_path: str) -> SigningStatus:
        """Inject signing config into the Android build.gradle.

        Reads ``android/key.properties`` and patches
        ``android/app/build.gradle`` to reference the release keystore
        for the ``release`` build type.
        """
        props_file = Path(project_path) / "android" / "key.properties"
        gradle_file = Path(project_path) / "android" / "app" / "build.gradle"

        if not props_file.exists():
            return SigningStatus(
                configured=False,
                errors=["key.properties not found. Generate a keystore first."],
            )

        if not gradle_file.exists():
            gradle_file = gradle_file.with_suffix(".gradle.kts")
            if not gradle_file.exists():
                return SigningStatus(
                    configured=False,
                    errors=["build.gradle(.kts) not found under android/app/."],
                )

        content = gradle_file.read_text(encoding="utf-8")

        # Guard: don't double-inject.
        if "key.properties" in content:
            logger.info("Gradle signing already configured.")
            return SigningStatus(
                configured=True,
                keystore_path=str(
                    props_file.parent / "keystore" / "release.jks"
                ),
                key_alias="release",
            )

        is_kts = gradle_file.suffix == ".kts"

        if is_kts:
            injection = self._gradle_kts_signing_block()
        else:
            injection = self._gradle_groovy_signing_block()

        # Insert the key.properties loader before the `android {` block.
        pattern = r"(android\s*\{)"
        replacement = injection + r"\n\1"
        new_content, count = re.subn(pattern, replacement, content, count=1)

        if count == 0:
            return SigningStatus(
                configured=False,
                errors=[
                    "Could not locate 'android {' block in build.gradle."
                ],
            )

        # Add signingConfigs and buildTypes reference inside android {}.
        signing_config_block = (
            self._signing_configs_kts()
            if is_kts
            else self._signing_configs_groovy()
        )
        new_content = self._inject_signing_configs(
            new_content, signing_config_block, is_kts
        )

        gradle_file.write_text(new_content, encoding="utf-8")
        logger.info("Gradle signing configured in %s", gradle_file)

        return SigningStatus(
            configured=True,
            keystore_path=str(
                props_file.parent / "keystore" / "release.jks"
            ),
            key_alias="release",
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_signing_status(self, project_path: str) -> SigningStatus:
        """Check current signing status of a project."""
        props_file = Path(project_path) / "android" / "key.properties"
        keystore_file = (
            Path(project_path) / "android" / "keystore" / "release.jks"
        )

        if not props_file.exists():
            return SigningStatus(
                configured=False,
                errors=["key.properties missing."],
            )

        if not keystore_file.exists():
            return SigningStatus(
                configured=False,
                keystore_path=None,
                errors=[
                    "Keystore file missing despite key.properties being present."
                ],
            )

        # Verify gradle references.
        gradle_file = Path(project_path) / "android" / "app" / "build.gradle"
        if not gradle_file.exists():
            gradle_file = gradle_file.with_suffix(".gradle.kts")

        gradle_ok = False
        if gradle_file.exists():
            gradle_ok = "key.properties" in gradle_file.read_text(
                encoding="utf-8"
            )

        if not gradle_ok:
            return SigningStatus(
                configured=False,
                keystore_path=str(keystore_file),
                key_alias="release",
                errors=[
                    "Gradle is not configured to use the keystore."
                ],
            )

        return SigningStatus(
            configured=True,
            keystore_path=str(keystore_file),
            key_alias="release",
        )

    # ------------------------------------------------------------------
    # Private template helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _gradle_groovy_signing_block() -> str:
        return (
            'def keystorePropertiesFile = rootProject.file("key.properties")\n'
            "def keystoreProperties = new Properties()\n"
            "if (keystorePropertiesFile.exists()) {\n"
            "    keystoreProperties.load("
            "new FileInputStream(keystorePropertiesFile))\n"
            "}\n"
        )

    @staticmethod
    def _gradle_kts_signing_block() -> str:
        return (
            'val keystorePropertiesFile = rootProject.file("key.properties")\n'
            "val keystoreProperties = java.util.Properties()\n"
            "if (keystorePropertiesFile.exists()) {\n"
            "    keystoreProperties.load("
            "java.io.FileInputStream(keystorePropertiesFile))\n"
            "}\n"
        )

    @staticmethod
    def _signing_configs_groovy() -> str:
        return (
            "    signingConfigs {\n"
            "        release {\n"
            '            keyAlias keystoreProperties["keyAlias"]\n'
            '            keyPassword keystoreProperties["keyPassword"]\n'
            '            storeFile keystoreProperties["storeFile"]'
            ' ? file(keystoreProperties["storeFile"]) : null\n'
            '            storePassword keystoreProperties["storePassword"]\n'
            "        }\n"
            "    }\n"
        )

    @staticmethod
    def _signing_configs_kts() -> str:
        return (
            "    signingConfigs {\n"
            '        create("release") {\n'
            "            keyAlias = "
            'keystoreProperties["keyAlias"] as String?\n'
            "            keyPassword = "
            'keystoreProperties["keyPassword"] as String?\n'
            "            storeFile = "
            'keystoreProperties["storeFile"]?.let { file(it) }\n'
            "            storePassword = "
            'keystoreProperties["storePassword"] as String?\n'
            "        }\n"
            "    }\n"
        )

    @staticmethod
    def _inject_signing_configs(
        content: str, signing_block: str, is_kts: bool
    ) -> str:
        """Insert signingConfigs block and update buildTypes.release."""
        content = re.sub(
            r"(android\s*\{)",
            r"\1\n" + signing_block,
            content,
            count=1,
        )

        if is_kts:
            ref = (
                "            signingConfig = "
                'signingConfigs.getByName("release")'
            )
        else:
            ref = "            signingConfig signingConfigs.release"

        pattern = r"(buildTypes\s*\{[^}]*release\s*\{)"
        replacement = r"\1\n" + ref
        content = re.sub(pattern, replacement, content, count=1)

        return content
