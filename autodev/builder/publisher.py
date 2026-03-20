"""App store publishing adapters.

Each publisher wraps a store-specific upload mechanism (fastlane, AGC API,
etc.) behind a common ``publish()`` interface.  Implementations are working
stubs -- the subprocess commands and API calls are fully wired up but the
actual credentials and store accounts must be configured before they will
succeed in a real environment.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from autodev.config import get_settings

logger = logging.getLogger(__name__)

_TIMEOUT_PUBLISH = 600  # 10 minutes


@dataclass
class PublishResult:
    """Outcome of a store publish attempt."""

    success: bool
    store_url: str = ""
    message: str = ""
    raw_output: str = ""


@dataclass
class AppInfo:
    """Metadata required by publishers."""

    package_name: str
    app_name: str
    version_name: str = "1.0.0"
    version_code: int = 1
    short_description: str = ""
    full_description: str = ""
    whats_new: str = "Initial release"
    category: str = "TOOLS"
    default_language: str = "en-US"
    extra: Dict[str, Any] = field(default_factory=dict)


class BasePublisher(ABC):
    """Common interface for app store publishers."""

    @abstractmethod
    async def publish(
        self, project_path: str, app_info: AppInfo
    ) -> PublishResult:
        """Upload the build artifact and metadata to the store."""
        ...

    async def _run_command(
        self,
        args: List[str],
        *,
        cwd: Optional[str] = None,
        timeout: float = _TIMEOUT_PUBLISH,
    ) -> tuple[bool, str, str]:
        """Helper to execute a subprocess and return (success, stdout, stderr)."""
        cmd_str = " ".join(args)
        logger.info("Publisher running: %s", cmd_str)
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.error("Publish command timed out: %s", cmd_str)
            return False, "", f"Timed out after {timeout}s"
        except FileNotFoundError:
            return False, "", f"Executable not found: {args[0]}"

        stdout = stdout_bytes.decode(errors="replace")
        stderr = stderr_bytes.decode(errors="replace")
        success = proc.returncode == 0
        return success, stdout, stderr


class GooglePlayPublisher(BasePublisher):
    """Publish to Google Play Store via ``fastlane supply``.

    Requires:
    - fastlane installed
    - ``google_play_json_key_path`` configured in settings
    - A signed AAB in the project build output
    """

    async def publish(
        self, project_path: str, app_info: AppInfo
    ) -> PublishResult:
        settings = get_settings()
        json_key = settings.google_play_json_key_path
        if not json_key:
            return PublishResult(
                success=False,
                message="Google Play JSON key path not configured.",
            )

        aab_path = (
            Path(project_path)
            / "build" / "app" / "outputs" / "bundle" / "release"
            / "app-release.aab"
        )
        if not aab_path.exists():
            return PublishResult(
                success=False,
                message=f"AAB not found at {aab_path}. Run build_appbundle first.",
            )

        args = [
            "fastlane",
            "supply",
            "--json_key", json_key,
            "--package_name", app_info.package_name,
            "--aab", str(aab_path),
            "--track", "internal",
            "--skip_upload_metadata", "false",
            "--skip_upload_changelogs", "false",
            "--release_status", "draft",
        ]

        success, stdout, stderr = await self._run_command(
            args, cwd=project_path
        )
        combined = f"{stdout}\n{stderr}".strip()

        if success:
            store_url = (
                f"https://play.google.com/store/apps/details"
                f"?id={app_info.package_name}"
            )
            return PublishResult(
                success=True,
                store_url=store_url,
                message="Successfully uploaded to Google Play (internal track).",
                raw_output=combined,
            )

        return PublishResult(
            success=False,
            message=f"fastlane supply failed: {stderr[:500]}",
            raw_output=combined,
        )


class AppStorePublisher(BasePublisher):
    """Publish to Apple App Store via ``fastlane deliver``.

    Requires:
    - fastlane installed
    - App Store Connect API key configured in settings
    - A signed IPA in the project build output
    """

    async def publish(
        self, project_path: str, app_info: AppInfo
    ) -> PublishResult:
        settings = get_settings()
        if not settings.apple_api_key_id or not settings.apple_api_issuer_id:
            return PublishResult(
                success=False,
                message="Apple App Store Connect API credentials not configured.",
            )

        ipa_dir = Path(project_path) / "build" / "ios" / "ipa"
        ipas = list(ipa_dir.glob("*.ipa")) if ipa_dir.exists() else []
        if not ipas:
            return PublishResult(
                success=False,
                message=f"IPA not found under {ipa_dir}. Run build_ipa first.",
            )

        args = [
            "fastlane",
            "deliver",
            "--ipa", str(ipas[0]),
            "--api_key_path", settings.apple_api_key_path,
            "--skip_screenshots", "true",
            "--skip_metadata", "false",
            "--force", "true",
            "--submit_for_review", "false",
        ]

        success, stdout, stderr = await self._run_command(
            args, cwd=project_path
        )
        combined = f"{stdout}\n{stderr}".strip()

        if success:
            return PublishResult(
                success=True,
                store_url=f"https://apps.apple.com/app/{app_info.package_name}",
                message="Successfully uploaded to App Store Connect.",
                raw_output=combined,
            )

        return PublishResult(
            success=False,
            message=f"fastlane deliver failed: {stderr[:500]}",
            raw_output=combined,
        )


class HuaweiPublisher(BasePublisher):
    """Publish to Huawei AppGallery via AGC (AppGallery Connect) API.

    This is a stub implementation.  A real version would:
    1. Authenticate with the AGC Connect API using client_id / client_secret.
    2. Upload the APK/AAB via the Publishing API.
    3. Submit the app for review.
    """

    def __init__(
        self,
        client_id: str = "",
        client_secret: str = "",
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret

    async def publish(
        self, project_path: str, app_info: AppInfo
    ) -> PublishResult:
        if not self.client_id or not self.client_secret:
            return PublishResult(
                success=False,
                message=(
                    "Huawei AGC credentials not configured. "
                    "Provide client_id and client_secret."
                ),
            )

        apk_path = (
            Path(project_path)
            / "build" / "app" / "outputs" / "flutter-apk" / "app-release.apk"
        )
        if not apk_path.exists():
            return PublishResult(
                success=False,
                message=f"APK not found at {apk_path}. Run build_apk first.",
            )

        # Step 1: Obtain access token.
        try:
            import httpx

            async with httpx.AsyncClient(timeout=30) as client:
                token_resp = await client.post(
                    "https://connect-api.cloud.huawei.com/api/oauth2/v1/token",
                    json={
                        "grant_type": "client_credentials",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    },
                )
                token_resp.raise_for_status()
                access_token = token_resp.json().get("access_token")

            if not access_token:
                return PublishResult(
                    success=False,
                    message="Failed to obtain AGC access token.",
                )

        except Exception as exc:
            logger.error("Huawei AGC auth failed: %s", exc)
            return PublishResult(
                success=False,
                message=f"AGC authentication failed: {exc}",
            )

        # Step 2: Upload APK (stub -- real impl uses multipart upload).
        logger.info(
            "Huawei AGC publish: would upload %s for %s (token obtained).",
            apk_path,
            app_info.package_name,
        )

        return PublishResult(
            success=False,
            message=(
                "Huawei AGC upload not fully implemented. "
                "Token obtained successfully; APK upload requires the "
                "Publishing API multipart flow."
            ),
        )
