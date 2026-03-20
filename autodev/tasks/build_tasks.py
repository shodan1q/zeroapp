"""Celery tasks for building and publishing Flutter apps.

Handles the full build pipeline: pub get, analyze, sign, build APK/AAB,
generate assets, and publish to stores.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from autodev.celery_app import celery
from autodev.config import get_settings

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


async def _build_project(
    project_path: str, demand: Dict[str, Any]
) -> Dict[str, Any]:
    """Run the full build pipeline for a generated project."""
    from autodev.builder.flutter_builder import FlutterBuilder
    from autodev.builder.signer import SigningManager

    builder = FlutterBuilder()
    result: Dict[str, Any] = {
        "status": "failed",
        "artifacts": {},
        "errors": [],
    }

    # pub get
    pub_result = await builder.pub_get(project_path)
    if not pub_result.success:
        result["errors"].append(f"pub get: {pub_result.errors}")
        return result

    # analyze
    analyze_result = await builder.analyze(project_path)
    if not analyze_result.success:
        logger.warning("Analysis issues: %s", analyze_result.errors[:5])

    # sign
    signer = SigningManager()
    try:
        await signer.generate_keystore(
            project_path, demand.get("title", "app")
        )
        signer.configure_gradle_signing(project_path)
    except Exception as exc:
        logger.warning("Signing setup failed: %s (continuing)", exc)

    # build APK
    apk = await builder.build_apk(project_path)
    if apk.success and apk.artifact_path:
        result["artifacts"]["apk"] = apk.artifact_path

    # build AAB
    aab = await builder.build_appbundle(project_path)
    if aab.success and aab.artifact_path:
        result["artifacts"]["aab"] = aab.artifact_path

    if result["artifacts"]:
        result["status"] = "success"
    else:
        result["errors"].append(
            f"APK: {apk.errors}, AAB: {aab.errors}"
        )

    return result


async def _generate_and_publish_assets(
    project_path: str, demand: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate icons, store listing, and publish."""
    from autodev.assets.icon_generator import IconGenerator
    from autodev.assets.store_listing import StoreListingGenerator
    from autodev.builder.publisher import (
        GooglePlayPublisher,
        AppStorePublisher,
        AppInfo,
    )

    assets_result: Dict[str, Any] = {}

    # Icon generation.
    try:
        icon_gen = IconGenerator()
        icons = await icon_gen.generate(
            app_name=demand.get("title", "App"),
            description=demand.get("description", ""),
            output_dir=f"{project_path}/assets/icons",
        )
        assets_result["icons"] = icons.master_icon
    except Exception as exc:
        logger.warning("Icon generation failed: %s", exc)

    # Store listing.
    listing_data = {}
    try:
        listing_gen = StoreListingGenerator()
        listing = await listing_gen.generate(
            app_name=demand.get("title", "App"),
            description=demand.get("description", ""),
            features=demand.get("core_features", ""),
        )
        listing_data = listing.model_dump()
        assets_result["listing"] = listing_data
    except Exception as exc:
        logger.warning("Store listing generation failed: %s", exc)

    # Publish.
    en = listing_data.get("en", {})
    demand_id = str(demand.get("id", "unknown"))
    app_info = AppInfo(
        package_name=f"com.autodev.{demand_id[:12].lower()}",
        app_name=demand.get("title", "App"),
        short_description=en.get("short_description", ""),
        full_description=en.get("full_description", ""),
        category=listing_data.get("category_suggestion", "TOOLS"),
    )

    publish_results = {}

    gp = GooglePlayPublisher()
    gp_result = await gp.publish(project_path, app_info)
    publish_results["google_play"] = {
        "success": gp_result.success,
        "url": gp_result.store_url,
        "message": gp_result.message,
    }

    ap = AppStorePublisher()
    ap_result = await ap.publish(project_path, app_info)
    publish_results["app_store"] = {
        "success": ap_result.success,
        "url": ap_result.store_url,
        "message": ap_result.message,
    }

    assets_result["publish"] = publish_results
    return assets_result


@celery.task(
    name="autodev.tasks.build_tasks.build_app",
    bind=True,
    max_retries=1,
    default_retry_delay=300,
    time_limit=3600,
    soft_time_limit=3300,
)
def build_app(self, demand_id: int) -> dict:
    """Build a Flutter app for a demand with generated code.

    Runs the full build pipeline: dependencies, analysis, signing,
    APK/AAB compilation.
    """
    logger.info("Starting build for demand %d.", demand_id)

    try:
        # TODO: Fetch demand + project_path from DB.
        demand: Dict[str, Any] = {
            "id": demand_id,
            "title": "Placeholder",
            "description": "Placeholder demand.",
        }
        project_path = ""  # TODO: Get from DB.

        if not project_path:
            return {
                "demand_id": demand_id,
                "status": "skipped",
                "message": "No project path found.",
            }

        result = _run_async(_build_project(project_path, demand))

        logger.info(
            "Build for demand %d: status=%s artifacts=%s",
            demand_id,
            result["status"],
            list(result["artifacts"].keys()),
        )
        return {
            "demand_id": demand_id,
            "status": result["status"],
            "artifacts": result["artifacts"],
            "errors": result["errors"],
        }
    except Exception as exc:
        logger.exception("Build failed for demand %d.", demand_id)
        raise self.retry(exc=exc)


@celery.task(
    name="autodev.tasks.build_tasks.build_and_publish",
    bind=True,
    time_limit=7200,
    soft_time_limit=6900,
)
def build_and_publish(self, demand_id: int) -> dict:
    """Full pipeline: build, generate assets, and publish.

    This is the end-to-end task that takes a generated project through
    building, asset creation, and store publishing.
    """
    logger.info(
        "Starting build-and-publish for demand %d.", demand_id
    )

    try:
        # TODO: Fetch demand + project_path from DB.
        demand: Dict[str, Any] = {
            "id": demand_id,
            "title": "Placeholder",
            "description": "Placeholder demand.",
        }
        project_path = ""  # TODO: Get from DB.

        if not project_path:
            return {
                "demand_id": demand_id,
                "status": "skipped",
                "message": "No project path found.",
            }

        # Build.
        build_result = _run_async(
            _build_project(project_path, demand)
        )
        if build_result["status"] != "success":
            return {
                "demand_id": demand_id,
                "status": "build_failed",
                "errors": build_result["errors"],
            }

        # Assets + publish.
        assets_result = _run_async(
            _generate_and_publish_assets(project_path, demand)
        )

        return {
            "demand_id": demand_id,
            "status": "complete",
            "artifacts": build_result["artifacts"],
            "assets": assets_result,
        }
    except Exception as exc:
        logger.exception(
            "Build-and-publish failed for demand %d.", demand_id
        )
        raise self.retry(exc=exc)


@celery.task(name="autodev.tasks.build_tasks.build_pending")
def build_pending() -> dict:
    """Build all apps with generated code that haven't been built yet.

    Queries the database for demands with generated code but no build
    artifacts, and dispatches build tasks.
    """
    logger.info("Building all pending generated apps.")

    # TODO: Query demands with project_path but no build artifacts.
    pending_ids: list[int] = []

    dispatched = 0
    for demand_id in pending_ids:
        build_and_publish.delay(demand_id)
        dispatched += 1

    logger.info("Dispatched %d build-and-publish tasks.", dispatched)
    return {"dispatched": dispatched}
