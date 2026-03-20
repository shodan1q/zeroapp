"""Main pipeline orchestrator: crawl -> evaluate -> generate -> build -> publish.

Chains together every layer of the AutoDev Agent:
  crawl -> process -> evaluate -> decide -> generate -> build -> assets -> publish

Can run as a one-shot pipeline for a single demand, or as a continuous loop
that polls for new demands on a configurable interval.
"""

from __future__ import annotations

import asyncio
import datetime
import enum
import logging
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from autodev.config import get_settings

logger = logging.getLogger(__name__)


# ── Pipeline state machine ───────────────────────────────────────────


class PipelineStage(str, enum.Enum):
    CRAWL = "crawl"
    PROCESS = "process"
    EVALUATE = "evaluate"
    DECIDE = "decide"
    GENERATE = "generate"
    BUILD = "build"
    ASSETS = "assets"
    PUBLISH = "publish"
    DONE = "done"
    FAILED = "failed"


@dataclass
class DemandState:
    """Track a single demand as it flows through the pipeline."""

    demand_id: str
    raw: Dict[str, Any] = field(default_factory=dict)
    structured: Dict[str, Any] = field(default_factory=dict)
    evaluation: Dict[str, Any] = field(default_factory=dict)
    decision: str = ""  # "approved", "rejected", "review"
    project_path: Optional[str] = None
    build_artifacts: Dict[str, str] = field(default_factory=dict)
    assets: Dict[str, Any] = field(default_factory=dict)
    publish_results: Dict[str, Any] = field(default_factory=dict)
    stage: PipelineStage = PipelineStage.CRAWL
    error: Optional[str] = None
    started_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    finished_at: Optional[datetime.datetime] = None


@dataclass
class PipelineRun:
    """Summary of a complete pipeline run (one cycle)."""

    run_id: str
    started_at: datetime.datetime
    finished_at: Optional[datetime.datetime] = None
    demands_crawled: int = 0
    demands_approved: int = 0
    demands_rejected: int = 0
    demands_built: int = 0
    demands_published: int = 0
    errors: List[str] = field(default_factory=list)


class PipelineOrchestrator:
    """Orchestrate the full AutoDev pipeline.

    Usage (one-shot)::

        orch = PipelineOrchestrator()
        run = await orch.run_once()

    Usage (continuous)::

        orch = PipelineOrchestrator()
        await orch.run_loop()  # blocks until cancelled
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._running = False
        self._current_run: Optional[PipelineRun] = None

    # ------------------------------------------------------------------
    # One-shot execution
    # ------------------------------------------------------------------

    async def run_once(self) -> PipelineRun:
        """Execute one full pipeline cycle and return the summary."""
        import uuid

        run = PipelineRun(
            run_id=uuid.uuid4().hex[:12],
            started_at=datetime.datetime.now(datetime.timezone.utc),
        )
        self._current_run = run
        logger.info("Pipeline run %s started.", run.run_id)

        try:
            # 1. Crawl demands from all sources.
            raw_demands = await self._crawl()
            run.demands_crawled = len(raw_demands)

            if not raw_demands:
                logger.info("No new demands found. Pipeline run complete.")
                run.finished_at = datetime.datetime.now(
                    datetime.timezone.utc
                )
                return run

            # 2. Process and structure raw demands.
            structured = await self._process(raw_demands)

            # 3-4. Evaluate and decide.
            states: List[DemandState] = []
            for demand in structured:
                state = DemandState(
                    demand_id=demand.get("id", "unknown"),
                    structured=demand,
                    stage=PipelineStage.EVALUATE,
                )
                try:
                    state = await self._evaluate(state)
                    state = await self._decide(state)
                except Exception as exc:
                    state.stage = PipelineStage.FAILED
                    state.error = str(exc)
                    run.errors.append(
                        f"Eval/decide failed for {state.demand_id}: {exc}"
                    )
                    logger.exception(
                        "Eval/decide failed for %s", state.demand_id
                    )
                states.append(state)

            approved = [s for s in states if s.decision == "approved"]
            run.demands_approved = len(approved)
            run.demands_rejected = len(
                [s for s in states if s.decision == "rejected"]
            )
            logger.info(
                "Evaluation complete: %d approved, %d rejected, %d review.",
                run.demands_approved,
                run.demands_rejected,
                len(states) - run.demands_approved - run.demands_rejected,
            )

            # 5-6-7. Generate, build, assets, publish for approved demands.
            semaphore = asyncio.Semaphore(
                self._settings.pipeline_max_concurrent_builds
            )

            async def _process_approved(
                state: DemandState,
            ) -> DemandState:
                async with semaphore:
                    return await self._build_and_publish(state, run)

            results = await asyncio.gather(
                *[_process_approved(s) for s in approved],
                return_exceptions=True,
            )

            for result in results:
                if isinstance(result, DemandState):
                    if result.stage == PipelineStage.DONE:
                        run.demands_published += 1
                    elif result.stage == PipelineStage.BUILD:
                        run.demands_built += 1
                elif isinstance(result, Exception):
                    run.errors.append(str(result))

            # 8. Log everything to database.
            await self._persist_run(run, states)

        except Exception:
            run.errors.append(f"Pipeline error: {traceback.format_exc()}")
            logger.exception("Pipeline run %s failed.", run.run_id)

        run.finished_at = datetime.datetime.now(datetime.timezone.utc)
        logger.info(
            "Pipeline run %s finished. Crawled=%d Approved=%d Built=%d "
            "Published=%d Errors=%d",
            run.run_id,
            run.demands_crawled,
            run.demands_approved,
            run.demands_built,
            run.demands_published,
            len(run.errors),
        )
        return run

    # ------------------------------------------------------------------
    # Continuous loop
    # ------------------------------------------------------------------

    async def run_loop(self) -> None:
        """Run the pipeline in a continuous loop.

        Sleeps for ``pipeline_crawl_interval_hours`` between cycles.
        Cancel the task to stop the loop.
        """
        self._running = True
        interval = self._settings.pipeline_crawl_interval_hours * 3600
        logger.info(
            "Starting continuous pipeline loop (interval=%dh).",
            self._settings.pipeline_crawl_interval_hours,
        )

        while self._running:
            try:
                await self.run_once()
            except Exception:
                logger.exception("Pipeline cycle failed; will retry.")

            logger.info("Sleeping %d seconds until next cycle.", interval)
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("Pipeline loop cancelled.")
                break

        self._running = False

    def stop(self) -> None:
        """Signal the continuous loop to stop after the current cycle."""
        self._running = False

    # ------------------------------------------------------------------
    # Stage implementations
    # ------------------------------------------------------------------

    async def _crawl(self) -> List[Dict[str, Any]]:
        """Crawl demands from all configured sources."""
        from autodev.crawler.reddit import RedditCrawler
        from autodev.crawler.producthunt import ProductHuntCrawler

        crawlers = [RedditCrawler(), ProductHuntCrawler()]
        all_demands: List[Dict[str, Any]] = []

        for crawler in crawlers:
            try:
                demands = await crawler.crawl()
                for d in demands:
                    all_demands.append(d.model_dump())
                logger.info(
                    "%s returned %d demands.",
                    type(crawler).__name__,
                    len(demands),
                )
            except Exception:
                logger.exception(
                    "%s crawl failed.", type(crawler).__name__
                )

        return all_demands

    async def _process(
        self, raw_demands: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Process raw demands into structured form via Claude."""
        try:
            from autodev.crawler.processor import DemandProcessor

            processor = DemandProcessor()
            structured = []
            for raw in raw_demands:
                try:
                    result = await processor.process(raw)
                    structured.append(
                        result.model_dump()
                        if hasattr(result, "model_dump")
                        else result
                    )
                except Exception:
                    logger.exception(
                        "Failed to process demand: %s",
                        raw.get("title", "?"),
                    )
            return structured
        except ImportError:
            logger.warning(
                "DemandProcessor not available; using raw demands as-is."
            )
            import uuid

            for d in raw_demands:
                d.setdefault("id", uuid.uuid4().hex[:12])
                d.setdefault("title", d.get("title", "Untitled"))
                d.setdefault("description", d.get("raw_text", ""))
                d.setdefault("core_features", "")
            return raw_demands

    async def _evaluate(self, state: DemandState) -> DemandState:
        """Run feasibility and competition evaluation."""
        from autodev.evaluator.feasibility import evaluate_feasibility
        from autodev.evaluator.competition import analyse_competition

        demand = state.structured

        feasibility = await evaluate_feasibility(demand)
        competition = await analyse_competition(demand)

        state.evaluation = {
            "feasibility": feasibility.model_dump(),
            "competition": competition.model_dump(),
        }
        state.stage = PipelineStage.DECIDE
        return state

    async def _decide(self, state: DemandState) -> DemandState:
        """Apply decision rules based on evaluation scores."""
        feas = state.evaluation.get("feasibility", {})
        comp = state.evaluation.get("competition", {})

        # Reject if not feasible.
        if not feas.get("feasible", False):
            state.decision = "rejected"
            logger.info(
                "Demand %s rejected: not feasible.", state.demand_id
            )
            return state

        # Reject if too complex or needs backend/hardware.
        if feas.get("complexity") == "high" and feas.get("needs_backend"):
            state.decision = "rejected"
            logger.info(
                "Demand %s rejected: high complexity + backend.",
                state.demand_id,
            )
            return state

        # Score: low competition is good; feasibility is required.
        comp_score = comp.get("competition_score", 0.5)
        opportunity = 1.0 - comp_score

        complexity_map = {"low": 0.3, "medium": 0.15, "high": 0.0}
        complexity_bonus = complexity_map.get(
            feas.get("complexity", "high"), 0.0
        )

        final_score = min(1.0, max(0.0, opportunity * 0.7 + complexity_bonus))

        auto_approve = self._settings.pipeline_auto_approve_threshold
        auto_reject = self._settings.pipeline_auto_reject_threshold

        if final_score >= auto_approve:
            state.decision = "approved"
        elif final_score <= auto_reject:
            state.decision = "rejected"
        else:
            state.decision = "review"

        logger.info(
            "Demand %s decision=%s (score=%.3f, comp=%.3f)",
            state.demand_id,
            state.decision,
            final_score,
            comp_score,
        )
        return state

    async def _build_and_publish(
        self, state: DemandState, run: PipelineRun
    ) -> DemandState:
        """Generate code, build, create assets, and publish."""
        demand = state.structured

        # Step 5: Generate code.
        state.stage = PipelineStage.GENERATE
        try:
            state = await self._generate_code(state)
        except Exception as exc:
            state.stage = PipelineStage.FAILED
            state.error = f"Code generation failed: {exc}"
            run.errors.append(state.error)
            logger.exception(
                "Code generation failed for %s", state.demand_id
            )
            return state

        if not state.project_path:
            state.stage = PipelineStage.FAILED
            state.error = "No project path after generation."
            return state

        # Step 5b: Build.
        state.stage = PipelineStage.BUILD
        try:
            state = await self._build(state)
        except Exception as exc:
            state.stage = PipelineStage.FAILED
            state.error = f"Build failed: {exc}"
            run.errors.append(state.error)
            logger.exception("Build failed for %s", state.demand_id)
            return state

        run.demands_built += 1

        # Step 6: Generate assets (non-fatal).
        state.stage = PipelineStage.ASSETS
        try:
            state = await self._generate_assets(state)
        except Exception as exc:
            logger.warning(
                "Asset generation failed for %s: %s (continuing)",
                state.demand_id,
                exc,
            )

        # Step 7: Publish (non-fatal).
        state.stage = PipelineStage.PUBLISH
        try:
            state = await self._publish(state)
        except Exception as exc:
            logger.warning(
                "Publishing failed for %s: %s", state.demand_id, exc
            )
            state.error = f"Publish failed: {exc}"

        state.stage = PipelineStage.DONE
        state.finished_at = datetime.datetime.now(datetime.timezone.utc)
        return state

    async def _generate_code(self, state: DemandState) -> DemandState:
        """Select template, generate PRD, generate code, fix errors."""
        demand = state.structured

        try:
            from autodev.generator import (
                select_template,
                generate_prd,
                generate_project,
                check_and_fix_dependencies,
                auto_fix_project,
            )

            template = await select_template(demand)
            logger.info(
                "Template selected for %s: %s",
                state.demand_id,
                template,
            )

            prd = await generate_prd(demand)
            logger.info("PRD generated for %s.", state.demand_id)

            project = await generate_project(prd, template=template)
            state.project_path = project.path
            logger.info(
                "Code generated at %s for %s.",
                project.path,
                state.demand_id,
            )

            await check_and_fix_dependencies(project.path)

            fix_result = await auto_fix_project(project.path)
            if not fix_result.success:
                logger.warning(
                    "Auto-fix had issues for %s: %s",
                    state.demand_id,
                    fix_result.errors[:3],
                )

        except ImportError as exc:
            logger.error(
                "Generator modules not available: %s. "
                "Using flutter create fallback.",
                exc,
            )
            from autodev.builder.flutter_builder import FlutterBuilder

            builder = FlutterBuilder()
            result = await builder.create_project(
                state.demand_id,
                demand.get("title", "app"),
            )
            if result.success:
                state.project_path = result.artifact_path
            else:
                raise RuntimeError(
                    f"flutter create failed: {result.errors}"
                )

        return state

    async def _build(self, state: DemandState) -> DemandState:
        """Run the full build pipeline: pub get, analyze, build APK/AAB."""
        from autodev.builder.flutter_builder import FlutterBuilder
        from autodev.builder.signer import SigningManager

        builder = FlutterBuilder()
        project = state.project_path
        assert project is not None

        result = await builder.pub_get(project)
        if not result.success:
            raise RuntimeError(f"pub get failed: {result.errors}")

        result = await builder.analyze(project)
        if not result.success:
            logger.warning(
                "Analyze found issues for %s: %s",
                state.demand_id,
                result.errors[:5],
            )

        signer = SigningManager()
        try:
            await signer.generate_keystore(
                project,
                state.structured.get("title", "app"),
            )
            signer.configure_gradle_signing(project)
        except Exception as exc:
            logger.warning("Signing setup failed: %s (continuing)", exc)

        apk_result = await builder.build_apk(project)
        if apk_result.success and apk_result.artifact_path:
            state.build_artifacts["apk"] = apk_result.artifact_path

        aab_result = await builder.build_appbundle(project)
        if aab_result.success and aab_result.artifact_path:
            state.build_artifacts["aab"] = aab_result.artifact_path

        if not state.build_artifacts:
            raise RuntimeError(
                "No build artifacts produced. "
                f"APK: {apk_result.errors}, AAB: {aab_result.errors}"
            )

        return state

    async def _generate_assets(self, state: DemandState) -> DemandState:
        """Generate icon and store listing."""
        from autodev.assets.icon_generator import IconGenerator
        from autodev.assets.store_listing import StoreListingGenerator

        demand = state.structured
        project = state.project_path
        assert project is not None

        icon_gen = IconGenerator()
        try:
            icons = await icon_gen.generate(
                app_name=demand.get("title", "App"),
                description=demand.get("description", ""),
                output_dir=f"{project}/assets/icons",
            )
            state.assets["icons"] = {
                "master": icons.master_icon,
                "android": icons.android_icons,
                "ios": icons.ios_icons,
            }
        except Exception as exc:
            logger.warning("Icon generation failed: %s", exc)

        listing_gen = StoreListingGenerator()
        try:
            listing = await listing_gen.generate(
                app_name=demand.get("title", "App"),
                description=demand.get("description", ""),
                features=demand.get("core_features", ""),
            )
            state.assets["listing"] = listing.model_dump()
        except Exception as exc:
            logger.warning("Store listing generation failed: %s", exc)

        return state

    async def _publish(self, state: DemandState) -> DemandState:
        """Publish to configured stores."""
        from autodev.builder.publisher import (
            GooglePlayPublisher,
            AppStorePublisher,
            AppInfo,
        )

        demand = state.structured
        project = state.project_path
        assert project is not None

        listing = state.assets.get("listing", {})
        en = listing.get("en", {})

        app_info = AppInfo(
            package_name=f"com.autodev.{state.demand_id[:12].lower()}",
            app_name=demand.get("title", "App"),
            short_description=en.get("short_description", ""),
            full_description=en.get("full_description", ""),
            category=listing.get("category_suggestion", "TOOLS"),
        )

        gp = GooglePlayPublisher()
        gp_result = await gp.publish(project, app_info)
        state.publish_results["google_play"] = {
            "success": gp_result.success,
            "url": gp_result.store_url,
            "message": gp_result.message,
        }
        if gp_result.success:
            logger.info(
                "Published to Google Play: %s", gp_result.store_url
            )

        ap = AppStorePublisher()
        ap_result = await ap.publish(project, app_info)
        state.publish_results["app_store"] = {
            "success": ap_result.success,
            "url": ap_result.store_url,
            "message": ap_result.message,
        }
        if ap_result.success:
            logger.info(
                "Published to App Store: %s", ap_result.store_url
            )

        return state

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _persist_run(
        self,
        run: PipelineRun,
        states: List[DemandState],
    ) -> None:
        """Log the pipeline run and demand states to the database."""
        try:
            from autodev.database import get_async_session

            async with get_async_session() as session:
                logger.info(
                    "Persisting pipeline run %s: %d demands processed.",
                    run.run_id,
                    len(states),
                )
                # TODO: Insert PipelineRun and DemandState ORM records.
        except Exception as exc:
            logger.warning(
                "Failed to persist pipeline run to DB: %s", exc
            )
