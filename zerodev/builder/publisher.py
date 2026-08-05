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
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from zerodev.config import get_settings
from zerodev.settings_store import effective_setting

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
        # Dashboard-saved key path takes precedence over env config.
        json_key = effective_setting(
            "googlePlayKeyPath", settings.google_play_json_key_path
        )
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

        # Dashboard-saved key path takes precedence over env config.
        api_key_path = effective_setting(
            "appStoreKeyPath", settings.apple_api_key_path
        )
        args = [
            "fastlane",
            "deliver",
            "--ipa", str(ipas[0]),
            "--api_key_path", api_key_path,
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


AGC_BASE_URL = "https://connect-api.cloud.huawei.com"

# AGC release channel: 1 = the public AppGallery release.
AGC_RELEASE_TYPE = 1

# File-type discriminator used by the app-file-info binding call.
AGC_FILE_TYPE_PACKAGE = 5

_TIMEOUT_AGC = 60.0
_TIMEOUT_AGC_UPLOAD = 900.0


class AGCError(RuntimeError):
    """An AppGallery Connect API call returned a failure envelope."""


@dataclass
class PublishStep:
    """One step of the AGC publishing flow, for an auditable trail."""

    name: str
    ok: bool
    detail: str = ""

    def render(self) -> str:
        return f"[{'ok' if self.ok else 'FAILED'}] {self.name}" + (f" -- {self.detail}" if self.detail else "")


class HarmonyOSPublisher(BasePublisher):
    """Publish a HarmonyOS ``.hap`` to AppGallery via the AGC Publishing API.

    Distinct from :class:`HuaweiPublisher`, which uploads an Android APK to the
    same store. The full documented flow is implemented here:

    1. ``POST /api/oauth2/v1/token``            -- exchange credentials for a token
    2. ``GET  /api/publish/v2/upload-url``      -- request a one-shot upload slot
    3. ``POST <uploadUrl>``                     -- multipart upload of the .hap
    4. ``PUT  /api/publish/v2/app-file-info``   -- bind the uploaded file to the app
    5. ``PUT  /api/publish/v2/app-language-info`` -- store listing copy
    6. ``POST /api/publish/v2/app-submit``      -- submit for Huawei review

    Without credentials the publisher runs in dry-run mode: it still validates
    the artifact and reports exactly which step it stopped at, so an unattended
    pipeline surfaces a precise reason instead of a generic failure.

    Step 6 is a real submission to Huawei's review queue. It is controlled by
    ``auto_submit`` (Dashboard ``agcAutoSubmit`` / env ``AGC_AUTO_SUBMIT``);
    set it false to upload and fill in the listing but stop before submitting.
    """

    def __init__(
        self,
        client_id: str = "",
        client_secret: str = "",
        app_id: str = "",
        *,
        auto_submit: bool | None = None,
    ) -> None:
        settings = get_settings()
        # Explicit args win; then Dashboard-saved settings; then env config.
        self.client_id = client_id or effective_setting(
            "huaweiAgcClientId", settings.huawei_agc_client_id
        )
        self.client_secret = client_secret or effective_setting(
            "huaweiAgcClientSecret", settings.huawei_agc_client_secret
        )
        self.app_id = app_id or effective_setting(
            "huaweiAgcAppId", settings.huawei_agc_app_id
        )
        if auto_submit is None:
            saved = effective_setting("agcAutoSubmit", os.environ.get("AGC_AUTO_SUBMIT", "true"))
            auto_submit = saved.strip().lower() not in ("false", "0", "no", "off")
        self.auto_submit = auto_submit
        self._steps: List[PublishStep] = []

    # ------------------------------------------------------------------
    # Artifact discovery
    # ------------------------------------------------------------------

    @staticmethod
    def _locate_hap(project_path: str) -> Optional[Path]:
        """Find the built ``.hap``, preferring a signed and recent artifact."""
        haps = [p for p in Path(project_path).rglob("*.hap") if p.is_file()]
        if not haps:
            return None
        signed = [h for h in haps if "unsigned" not in h.name.lower()]
        return max(signed or haps, key=lambda p: p.stat().st_mtime)

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self, token: str) -> Dict[str, str]:
        # AGC authenticates with the bearer token *and* the client id header.
        return {"Authorization": f"Bearer {token}", "client_id": self.client_id}

    @staticmethod
    def _check_envelope(payload: Any, step: str) -> Dict[str, Any]:
        """Validate AGC's ``{"ret": {"code": 0}}`` envelope, raising on failure.

        AGC answers with HTTP 200 even for logical failures, so the envelope --
        not the status code -- is the real result.
        """
        if not isinstance(payload, dict):
            raise AGCError(f"{step}: unexpected response type {type(payload).__name__}")
        ret = payload.get("ret") or {}
        code = ret.get("code")
        if code not in (0, None):
            raise AGCError(f"{step}: AGC returned code {code} - {ret.get('msg', 'no message')}")
        return payload

    async def _get_token(self, client: httpx.AsyncClient) -> str:
        resp = await client.post(
            f"{AGC_BASE_URL}/api/oauth2/v1/token",
            json={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if not token:
            raise AGCError(f"token: no access_token in response: {resp.text[:300]}")
        return str(token)

    async def _request_upload_url(
        self, client: httpx.AsyncClient, token: str, suffix: str
    ) -> tuple[str, str]:
        resp = await client.get(
            f"{AGC_BASE_URL}/api/publish/v2/upload-url",
            params={"appId": self.app_id, "suffix": suffix, "releaseType": AGC_RELEASE_TYPE},
            headers=self._headers(token),
        )
        resp.raise_for_status()
        data = self._check_envelope(resp.json(), "upload-url")
        upload_url = data.get("uploadUrl")
        auth_code = data.get("authCode")
        if not upload_url or not auth_code:
            raise AGCError(f"upload-url: missing uploadUrl/authCode in {str(data)[:300]}")
        return str(upload_url), str(auth_code)

    async def _upload_file(
        self, client: httpx.AsyncClient, upload_url: str, auth_code: str, hap_path: Path
    ) -> Dict[str, Any]:
        with hap_path.open("rb") as handle:
            resp = await client.post(
                upload_url,
                data={"authCode": auth_code, "fileCount": "1", "parseType": "1"},
                files={"file": (hap_path.name, handle, "application/octet-stream")},
                timeout=_TIMEOUT_AGC_UPLOAD,
            )
        resp.raise_for_status()
        payload = resp.json()
        upload_rsp = (payload.get("result") or {}).get("UploadFileRsp") or {}
        if upload_rsp.get("ifSuccess") != 1:
            raise AGCError(f"upload: AGC reported failure: {str(payload)[:400]}")
        files = upload_rsp.get("fileInfoList") or []
        if not files:
            raise AGCError(f"upload: no fileInfoList returned: {str(payload)[:300]}")
        return files[0]

    async def _bind_file(
        self, client: httpx.AsyncClient, token: str, hap_path: Path, file_info: Dict[str, Any]
    ) -> None:
        # The AGC API ships this key with a typo ("Ulr"); accept both spellings
        # so a future correction on their side does not break the pipeline.
        dest_url = file_info.get("fileDestUlr") or file_info.get("fileDestUrl")
        if not dest_url:
            raise AGCError(f"app-file-info: no destination URL in {str(file_info)[:300]}")
        resp = await client.put(
            f"{AGC_BASE_URL}/api/publish/v2/app-file-info",
            params={"appId": self.app_id, "releaseType": AGC_RELEASE_TYPE},
            headers=self._headers(token),
            json={
                "fileType": AGC_FILE_TYPE_PACKAGE,
                "files": [
                    {
                        "fileName": hap_path.name,
                        "fileDestUlr": dest_url,
                        "size": file_info.get("size", hap_path.stat().st_size),
                    }
                ],
            },
        )
        resp.raise_for_status()
        self._check_envelope(resp.json(), "app-file-info")

    async def _update_listing(
        self, client: httpx.AsyncClient, token: str, app_info: AppInfo
    ) -> None:
        lang = app_info.extra.get("agc_lang") or ("zh-CN" if app_info.default_language.startswith("zh") else "en-US")
        resp = await client.put(
            f"{AGC_BASE_URL}/api/publish/v2/app-language-info",
            params={"appId": self.app_id},
            headers=self._headers(token),
            json={
                "lang": lang,
                "appName": app_info.app_name,
                "appDesc": app_info.full_description or app_info.short_description or app_info.app_name,
                "briefInfo": (app_info.short_description or app_info.app_name)[:80],
                "newFeatures": app_info.whats_new,
            },
        )
        resp.raise_for_status()
        self._check_envelope(resp.json(), "app-language-info")

    async def _submit(self, client: httpx.AsyncClient, token: str, app_info: AppInfo) -> None:
        resp = await client.post(
            f"{AGC_BASE_URL}/api/publish/v2/app-submit",
            params={
                "appId": self.app_id,
                "releaseType": AGC_RELEASE_TYPE,
                "remark": app_info.whats_new[:200] or "automated release",
            },
            headers=self._headers(token),
        )
        resp.raise_for_status()
        self._check_envelope(resp.json(), "app-submit")

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def _record(self, name: str, ok: bool, detail: str = "") -> None:
        step = PublishStep(name=name, ok=ok, detail=detail)
        self._steps.append(step)
        (logger.info if ok else logger.warning)("AGC publish %s", step.render())

    def _trail(self) -> str:
        return "\n".join(s.render() for s in self._steps)

    def preflight(self, project_path: str) -> tuple[Optional[Path], List[str]]:
        """Check everything that does not need the network.

        Returns the located ``.hap`` (when found) and a list of blocking issues.
        """
        problems: List[str] = []
        missing = [
            name
            for name, value in (
                ("HUAWEI_AGC_CLIENT_ID", self.client_id),
                ("HUAWEI_AGC_CLIENT_SECRET", self.client_secret),
                ("HUAWEI_AGC_APP_ID", self.app_id),
            )
            if not value
        ]
        if missing:
            problems.append(
                "AGC credentials not configured: " + ", ".join(missing) + ". Create a HarmonyOS app in "
                "AppGallery Connect, enable the Connect API, and set these three values "
                "(env or Dashboard settings)."
            )

        hap_path = self._locate_hap(project_path)
        if hap_path is None:
            problems.append(f"No .hap found under {project_path}. Run the HarmonyOS build first.")
        elif "unsigned" in hap_path.name.lower():
            problems.append(
                f"Only an unsigned artifact exists ({hap_path.name}). AppGallery rejects unsigned "
                "packages -- configure release signing (OHOS_SIGN_* settings) and rebuild."
            )
        return hap_path, problems

    async def publish(self, project_path: str, app_info: AppInfo) -> PublishResult:
        """Run the full upload-and-submit flow, or report why it cannot."""
        self._steps = []
        hap_path, problems = self.preflight(project_path)

        if problems:
            self._record("preflight", False, problems[0])
            return PublishResult(
                success=False,
                message="AGC publish blocked (dry run):\n  - " + "\n  - ".join(problems),
                raw_output=self._trail(),
            )
        assert hap_path is not None  # preflight guarantees this when problems is empty
        self._record("preflight", True, f"{hap_path.name} ({hap_path.stat().st_size // 1024}KB)")

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_AGC) as client:
                token = await self._get_token(client)
                self._record("token", True)

                upload_url, auth_code = await self._request_upload_url(client, token, hap_path.suffix.lstrip("."))
                self._record("upload-url", True)

                file_info = await self._upload_file(client, upload_url, auth_code, hap_path)
                self._record("upload", True, f"{file_info.get('size', 0)} bytes accepted")

                await self._bind_file(client, token, hap_path, file_info)
                self._record("app-file-info", True)

                await self._update_listing(client, token, app_info)
                self._record("app-language-info", True)

                if not self.auto_submit:
                    self._record("app-submit", True, "skipped (auto_submit disabled)")
                    return PublishResult(
                        success=True,
                        message=(
                            f"{app_info.app_name} uploaded to AppGallery and the listing was updated. "
                            "Review submission was skipped because auto_submit is off -- submit it "
                            "from the AGC console when ready."
                        ),
                        store_url=f"https://developer.huawei.com/consumer/cn/service/josp/agc/index.html#/appList/{self.app_id}",
                        raw_output=self._trail(),
                    )

                await self._submit(client, token, app_info)
                self._record("app-submit", True, "submitted for Huawei review")

        except (AGCError, httpx.HTTPError) as exc:
            failed_step = self._steps[-1].name if self._steps else "start"
            self._record("aborted", False, str(exc)[:400])
            logger.error("AGC publish failed after %s: %s", failed_step, exc)
            return PublishResult(
                success=False,
                message=f"AppGallery publish failed after '{failed_step}': {exc}",
                raw_output=self._trail(),
            )

        return PublishResult(
            success=True,
            message=f"{app_info.app_name} submitted to AppGallery for review.",
            store_url=f"https://appgallery.huawei.com/app/detail?id={app_info.package_name}",
            raw_output=self._trail(),
        )
