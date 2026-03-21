"""LangGraph graph definitions for the ZeroDev pipeline.

Two graphs are constructed here:

1. **Main pipeline graph** (batch mode):
   crawl -> process -> evaluate_batch -> decide_batch -> fan_out_approved

2. **Per-demand graph** (single demand):
   generate -> build -> assets -> publish

Each node is an async function that receives the full state dict and returns
a *partial* update dict.  LangGraph merges the update into the running state.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import uuid
from typing import Any, Dict, List

from langgraph.graph import END, StateGraph

from zerodev.config import get_settings
from zerodev.pipeline.retry import with_retry
from zerodev.pipeline.state import DemandState, PipelineState, RetryPolicy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _retry_policy() -> RetryPolicy:
    """Build a RetryPolicy from application settings."""
    s = get_settings()
    return RetryPolicy(
        max_retries=s.pipeline_max_retries,
        backoff_base=s.pipeline_retry_backoff_base,
        backoff_max=s.pipeline_retry_backoff_max,
    )


# ═══════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE GRAPH  (batch)
# ═══════════════════════════════════════════════════════════════════════════


# -- Node: crawl -----------------------------------------------------------

@with_retry(node_name="crawl")
async def node_crawl(state: Dict[str, Any]) -> Dict[str, Any]:
    """Crawl demands from all configured sources."""
    from zerodev.crawler.producthunt import ProductHuntCrawler
    from zerodev.crawler.reddit import RedditCrawler

    logger.info("[crawl] Starting demand crawl.")

    try:
        from zerodev.api.events import emit_stage_change
        await emit_stage_change("crawl", status="started")
    except Exception:
        pass

    crawlers = [RedditCrawler(), ProductHuntCrawler()]
    all_demands: List[Dict[str, Any]] = []

    for crawler in crawlers:
        try:
            demands = await crawler.crawl()
            for d in demands:
                all_demands.append(d.model_dump())
            logger.info(
                "[crawl] %s returned %d demands.",
                type(crawler).__name__,
                len(demands),
            )
        except Exception:
            logger.exception("[crawl] %s failed.", type(crawler).__name__)

    logger.info("[crawl] Total raw demands: %d.", len(all_demands))

    try:
        from zerodev.api.events import emit_stage_change
        await emit_stage_change("crawl", status="completed", detail={"count": len(all_demands)})
    except Exception:
        pass

    return {
        "demands_raw": all_demands,
        "demands_crawled_count": len(all_demands),
        "stage": "crawl",
    }


# -- Node: process ---------------------------------------------------------

@with_retry(node_name="process")
async def node_process(state: Dict[str, Any]) -> Dict[str, Any]:
    """Process raw demands into structured form via Claude."""
    raw_demands: List[Dict[str, Any]] = state.get("demands_raw", [])
    logger.info("[process] Processing %d raw demands.", len(raw_demands))

    try:
        from zerodev.api.events import emit_stage_change
        await emit_stage_change("process", status="started")
    except Exception:
        pass

    try:
        from zerodev.crawler.processor import DemandProcessor

        processor = DemandProcessor()
        structured: List[Dict[str, Any]] = []
        for raw in raw_demands:
            try:
                result = await processor.process(raw)
                structured.append(
                    result.model_dump() if hasattr(result, "model_dump") else result
                )
            except Exception:
                logger.exception(
                    "[process] Failed to process demand: %s",
                    raw.get("title", "?"),
                )
        logger.info("[process] Structured %d demands.", len(structured))

        try:
            from zerodev.api.events import emit_stage_change
            await emit_stage_change("process", status="completed", detail={"count": len(structured)})
        except Exception:
            pass

        return {"demands_structured": structured, "stage": "process"}

    except ImportError:
        logger.warning(
            "[process] DemandProcessor not available; using raw demands."
        )
        for d in raw_demands:
            d.setdefault("id", uuid.uuid4().hex[:12])
            d.setdefault("title", d.get("title", "Untitled"))
            d.setdefault("description", d.get("raw_text", ""))
            d.setdefault("core_features", "")

        try:
            from zerodev.api.events import emit_stage_change
            await emit_stage_change("process", status="completed", detail={"count": len(raw_demands)})
        except Exception:
            pass

        return {"demands_structured": raw_demands, "stage": "process"}


# -- Node: evaluate_batch --------------------------------------------------

@with_retry(node_name="evaluate_batch")
async def node_evaluate_batch(state: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate feasibility and competition for all structured demands."""
    from zerodev.evaluator.competition import analyse_competition
    from zerodev.evaluator.feasibility import evaluate_feasibility

    structured: List[Dict[str, Any]] = state.get("demands_structured", [])
    logger.info("[evaluate] Evaluating %d demands.", len(structured))

    try:
        from zerodev.api.events import emit_stage_change
        await emit_stage_change("evaluate_batch", status="started")
    except Exception:
        pass

    evaluated: List[Dict[str, Any]] = []
    errors: list[str] = list(state.get("errors") or [])

    for demand in structured:
        demand_id = demand.get("id", "unknown")
        try:
            feasibility = await evaluate_feasibility(demand)
            competition = await analyse_competition(demand)
            evaluated.append({
                **demand,
                "evaluation": {
                    "feasibility": feasibility.model_dump(),
                    "competition": competition.model_dump(),
                },
            })
        except Exception as exc:
            msg = f"[evaluate] Failed for {demand_id}: {exc}"
            logger.exception(msg)
            errors.append(msg)

    logger.info("[evaluate] Evaluated %d / %d demands.", len(evaluated), len(structured))

    try:
        from zerodev.api.events import emit_stage_change
        await emit_stage_change("evaluate_batch", status="completed", detail={"evaluated": len(evaluated), "total": len(structured)})
    except Exception:
        pass

    return {
        "demands_evaluated": evaluated,
        "errors": errors,
        "stage": "evaluate",
    }


# -- Node: decide_batch ----------------------------------------------------

async def node_decide_batch(state: Dict[str, Any]) -> Dict[str, Any]:
    """Apply decision rules to evaluated demands."""
    settings = get_settings()
    evaluated: List[Dict[str, Any]] = state.get("demands_evaluated", [])
    logger.info("[decide] Deciding on %d demands.", len(evaluated))

    try:
        from zerodev.api.events import emit_stage_change
        await emit_stage_change("decide_batch", status="started")
    except Exception:
        pass

    approved: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for demand in evaluated:
        demand_id = demand.get("id", "unknown")
        feas = demand.get("evaluation", {}).get("feasibility", {})
        comp = demand.get("evaluation", {}).get("competition", {})

        # Reject if not feasible.
        if not feas.get("feasible", False):
            rejected.append(demand)
            logger.info("[decide] %s rejected: not feasible.", demand_id)
            continue

        # Reject if too complex + needs backend.
        if feas.get("complexity") == "high" and feas.get("needs_backend"):
            rejected.append(demand)
            logger.info("[decide] %s rejected: high complexity + backend.", demand_id)
            continue

        # Score computation.
        comp_score = comp.get("competition_score", 0.5)
        opportunity = 1.0 - comp_score
        complexity_map = {"low": 0.3, "medium": 0.15, "high": 0.0}
        complexity_bonus = complexity_map.get(feas.get("complexity", "high"), 0.0)
        final_score = min(1.0, max(0.0, opportunity * 0.7 + complexity_bonus))

        if final_score >= settings.pipeline_auto_approve_threshold:
            approved.append(demand)
            logger.info("[decide] %s approved (score=%.3f).", demand_id, final_score)
        elif final_score <= settings.pipeline_auto_reject_threshold:
            rejected.append(demand)
            logger.info("[decide] %s rejected (score=%.3f).", demand_id, final_score)
        else:
            # "review" -- treat as approved for pipeline (can add human-in-the-loop later).
            approved.append(demand)
            logger.info("[decide] %s review/approved (score=%.3f).", demand_id, final_score)

    logger.info(
        "[decide] %d approved, %d rejected.",
        len(approved),
        len(rejected),
    )

    try:
        from zerodev.api.events import emit_stage_change
        await emit_stage_change("decide_batch", status="completed", detail={"approved": len(approved), "rejected": len(rejected)})
    except Exception:
        pass

    return {
        "demands_approved": approved,
        "demands_rejected": rejected,
        "demands_approved_count": len(approved),
        "demands_rejected_count": len(rejected),
        "stage": "decide",
    }


# -- Node: fan_out_approved ------------------------------------------------

async def node_fan_out_approved(state: Dict[str, Any]) -> Dict[str, Any]:
    """Process each approved demand through the per-demand sub-graph.

    Runs approved demands concurrently (bounded by pipeline_max_concurrent_builds).
    """
    settings = get_settings()
    approved: List[Dict[str, Any]] = state.get("demands_approved", [])
    logger.info("[fan_out] Processing %d approved demands.", len(approved))

    if not approved:
        return {
            "demand_results": [],
            "stage": "done",
        }

    semaphore = asyncio.Semaphore(settings.pipeline_max_concurrent_builds)
    demand_graph = build_demand_graph()

    async def _process_one(demand: Dict[str, Any]) -> Dict[str, Any]:
        async with semaphore:
            demand_id = demand.get("id", uuid.uuid4().hex[:12])
            initial_state: Dict[str, Any] = {
                "demand_id": demand_id,
                "demand": demand,
                "project_path": None,
                "build_artifacts": {},
                "assets": {},
                "publish_results": {},
                "stage": "generate",
                "errors": [],
                "retry_count": 0,
                "failed": False,
            }
            try:
                result = await demand_graph.ainvoke(initial_state)
                return result
            except Exception as exc:
                logger.exception("[fan_out] Demand %s failed.", demand_id)
                return {
                    "demand_id": demand_id,
                    "failed": True,
                    "errors": [str(exc)],
                    "stage": "failed",
                }

    results = await asyncio.gather(
        *[_process_one(d) for d in approved],
        return_exceptions=True,
    )

    demand_results: List[Dict[str, Any]] = []
    built_count = 0
    published_count = 0
    errors: list[str] = list(state.get("errors") or [])

    for r in results:
        if isinstance(r, Exception):
            errors.append(f"[fan_out] Exception: {r}")
            continue
        demand_results.append(r)
        if r.get("build_artifacts"):
            built_count += 1
        if r.get("publish_results"):
            published_count += 1

    logger.info(
        "[fan_out] Complete: %d built, %d published, %d errors.",
        built_count,
        published_count,
        len(errors) - len(state.get("errors") or []),
    )
    return {
        "demand_results": demand_results,
        "demands_built_count": built_count,
        "demands_published_count": published_count,
        "errors": errors,
        "stage": "done",
    }


# -- Conditional: has approved demands? ------------------------------------

def _has_approved(state: Dict[str, Any]) -> str:
    """Route after decide: continue if there are approved demands, else end."""
    approved = state.get("demands_approved", [])
    if approved:
        return "fan_out_approved"
    logger.info("[decide] No approved demands; ending pipeline.")
    return END


# -- Conditional: has raw demands? -----------------------------------------

def _has_raw_demands(state: Dict[str, Any]) -> str:
    """Route after crawl: continue if demands found, else end."""
    raw = state.get("demands_raw", [])
    if raw:
        return "process"
    logger.info("[crawl] No demands found; ending pipeline.")
    return END


# -- Build main graph ------------------------------------------------------

def build_main_graph(checkpointer=None) -> Any:
    """Construct and compile the main (batch) pipeline StateGraph.

    Parameters
    ----------
    checkpointer : optional
        A LangGraph checkpointer for persistence. If ``None``, no
        checkpointing is used.

    Returns
    -------
    CompiledGraph
        The compiled LangGraph ready for ``ainvoke`` / ``astream``.
    """
    graph = StateGraph(PipelineState)

    # Add nodes.
    graph.add_node("crawl", node_crawl)
    graph.add_node("process", node_process)
    graph.add_node("evaluate_batch", node_evaluate_batch)
    graph.add_node("decide_batch", node_decide_batch)
    graph.add_node("fan_out_approved", node_fan_out_approved)

    # Edges.
    graph.set_entry_point("crawl")
    graph.add_conditional_edges("crawl", _has_raw_demands)
    graph.add_edge("process", "evaluate_batch")
    graph.add_edge("evaluate_batch", "decide_batch")
    graph.add_conditional_edges("decide_batch", _has_approved)
    graph.add_edge("fan_out_approved", END)

    compile_kwargs: Dict[str, Any] = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer

    # Interrupt before expensive / reviewable stages.
    compile_kwargs["interrupt_before"] = ["fan_out_approved"]

    return graph.compile(**compile_kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# PER-DEMAND GRAPH  (single demand processing)
# ═══════════════════════════════════════════════════════════════════════════


# -- Node: generate --------------------------------------------------------

@with_retry(node_name="generate")
async def node_generate(state: Dict[str, Any]) -> Dict[str, Any]:
    """Select template, generate PRD, generate code, fix errors."""
    demand = state.get("demand", {})
    demand_id = state.get("demand_id", "unknown")
    logger.info("[generate] Starting code generation for %s.", demand_id)

    try:
        from zerodev.api.events import emit_stage_change
        await emit_stage_change("generate", demand_id=demand_id, status="started")
    except Exception:
        pass

    try:
        from zerodev.generator import (
            auto_fix_project,
            check_and_fix_dependencies,
            generate_prd,
            generate_project,
            select_template,
        )

        template = await select_template(demand)
        logger.info("[generate] Template for %s: %s.", demand_id, template)

        prd = await generate_prd(demand)
        logger.info("[generate] PRD generated for %s.", demand_id)

        project = await generate_project(prd, template=template)
        logger.info("[generate] Code at %s for %s.", project.path, demand_id)

        await check_and_fix_dependencies(project.path)

        fix_result = await auto_fix_project(project.path)
        if not fix_result.success:
            logger.warning(
                "[generate] Auto-fix issues for %s: %s",
                demand_id,
                fix_result.errors[:3],
            )

        try:
            from zerodev.api.events import emit_stage_change
            await emit_stage_change("generate", demand_id=demand_id, status="completed")
        except Exception:
            pass

        return {"project_path": project.path, "stage": "generate"}

    except ImportError as exc:
        logger.warning(
            "[generate] Generator not available (%s); flutter create fallback.",
            exc,
        )
        from zerodev.builder.flutter_builder import FlutterBuilder

        builder = FlutterBuilder()
        result = await builder.create_project(
            demand_id,
            demand.get("title", "app"),
        )
        if result.success:
            try:
                from zerodev.api.events import emit_stage_change
                await emit_stage_change("generate", demand_id=demand_id, status="completed")
            except Exception:
                pass
            return {"project_path": result.artifact_path, "stage": "generate"}
        raise RuntimeError(f"flutter create failed: {result.errors}")


# -- Node: build -----------------------------------------------------------

@with_retry(node_name="build")
async def node_build(state: Dict[str, Any]) -> Dict[str, Any]:
    """Run the full build pipeline: pub get, analyze, sign, build APK/AAB."""
    from zerodev.builder.flutter_builder import FlutterBuilder
    from zerodev.builder.signer import SigningManager

    demand = state.get("demand", {})
    demand_id = state.get("demand_id", "unknown")
    project = state.get("project_path")

    if not project:
        raise RuntimeError("No project_path in state -- cannot build.")

    logger.info("[build] Building %s at %s.", demand_id, project)

    try:
        from zerodev.api.events import emit_stage_change
        await emit_stage_change("build", demand_id=demand_id, status="started")
    except Exception:
        pass

    builder = FlutterBuilder()

    result = await builder.pub_get(project)
    if not result.success:
        raise RuntimeError(f"pub get failed: {result.errors}")

    result = await builder.analyze(project)
    if not result.success:
        logger.warning("[build] Analyze issues for %s: %s", demand_id, result.errors[:5])

    signer = SigningManager()
    try:
        await signer.generate_keystore(project, demand.get("title", "app"))
        signer.configure_gradle_signing(project)
    except Exception as exc:
        logger.warning("[build] Signing setup failed: %s (continuing).", exc)

    artifacts: Dict[str, str] = {}

    apk_result = await builder.build_apk(project)
    if apk_result.success and apk_result.artifact_path:
        artifacts["apk"] = apk_result.artifact_path

    aab_result = await builder.build_appbundle(project)
    if aab_result.success and aab_result.artifact_path:
        artifacts["aab"] = aab_result.artifact_path

    if not artifacts:
        raise RuntimeError(
            f"No build artifacts. APK: {apk_result.errors}, AAB: {aab_result.errors}"
        )

    logger.info("[build] Artifacts for %s: %s.", demand_id, list(artifacts.keys()))

    try:
        from zerodev.api.events import emit_stage_change
        await emit_stage_change("build", demand_id=demand_id, status="completed", detail={"artifacts": list(artifacts.keys())})
    except Exception:
        pass

    return {"build_artifacts": artifacts, "stage": "build"}


# -- Node: assets ----------------------------------------------------------

@with_retry(node_name="assets")
async def node_assets(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate icon and store listing assets."""
    from zerodev.assets.icon_generator import IconGenerator
    from zerodev.assets.store_listing import StoreListingGenerator

    demand = state.get("demand", {})
    demand_id = state.get("demand_id", "unknown")
    project = state.get("project_path")

    if not project:
        raise RuntimeError("No project_path in state -- cannot generate assets.")

    logger.info("[assets] Generating assets for %s.", demand_id)

    try:
        from zerodev.api.events import emit_stage_change
        await emit_stage_change("assets", demand_id=demand_id, status="started")
    except Exception:
        pass
    assets: Dict[str, Any] = {}

    try:
        icon_gen = IconGenerator()
        icons = await icon_gen.generate(
            app_name=demand.get("title", "App"),
            description=demand.get("description", ""),
            output_dir=f"{project}/assets/icons",
        )
        assets["icons"] = {
            "master": icons.master_icon,
            "android": icons.android_icons,
            "ios": icons.ios_icons,
        }
    except Exception as exc:
        logger.warning("[assets] Icon generation failed for %s: %s", demand_id, exc)

    try:
        listing_gen = StoreListingGenerator()
        listing = await listing_gen.generate(
            app_name=demand.get("title", "App"),
            description=demand.get("description", ""),
            features=demand.get("core_features", ""),
        )
        assets["listing"] = listing.model_dump()
    except Exception as exc:
        logger.warning("[assets] Store listing failed for %s: %s", demand_id, exc)

    logger.info("[assets] Generated assets for %s: %s.", demand_id, list(assets.keys()))

    try:
        from zerodev.api.events import emit_stage_change
        await emit_stage_change("assets", demand_id=demand_id, status="completed", detail={"assets": list(assets.keys())})
    except Exception:
        pass

    return {"assets": assets, "stage": "assets"}


# -- Node: publish ---------------------------------------------------------

@with_retry(node_name="publish")
async def node_publish(state: Dict[str, Any]) -> Dict[str, Any]:
    """Publish to configured app stores."""
    from zerodev.builder.publisher import AppInfo, AppStorePublisher, GooglePlayPublisher

    demand = state.get("demand", {})
    demand_id = state.get("demand_id", "unknown")
    project = state.get("project_path")

    if not project:
        raise RuntimeError("No project_path in state -- cannot publish.")

    logger.info("[publish] Publishing %s.", demand_id)

    try:
        from zerodev.api.events import emit_stage_change
        await emit_stage_change("publish", demand_id=demand_id, status="started")
    except Exception:
        pass

    listing = (state.get("assets") or {}).get("listing", {})
    en = listing.get("en", {})

    app_info = AppInfo(
        package_name=f"com.zerodev.{demand_id[:12].lower()}",
        app_name=demand.get("title", "App"),
        short_description=en.get("short_description", ""),
        full_description=en.get("full_description", ""),
        category=listing.get("category_suggestion", "TOOLS"),
    )

    publish_results: Dict[str, Any] = {}

    gp = GooglePlayPublisher()
    gp_result = await gp.publish(project, app_info)
    publish_results["google_play"] = {
        "success": gp_result.success,
        "url": gp_result.store_url,
        "message": gp_result.message,
    }
    if gp_result.success:
        logger.info("[publish] Google Play: %s", gp_result.store_url)

    ap = AppStorePublisher()
    ap_result = await ap.publish(project, app_info)
    publish_results["app_store"] = {
        "success": ap_result.success,
        "url": ap_result.store_url,
        "message": ap_result.message,
    }
    if ap_result.success:
        logger.info("[publish] App Store: %s", ap_result.store_url)

    logger.info("[publish] Publish complete for %s.", demand_id)

    try:
        from zerodev.api.events import emit_stage_change
        await emit_stage_change("publish", demand_id=demand_id, status="completed")
    except Exception:
        pass

    return {"publish_results": publish_results, "stage": "publish"}


# -- Conditional: build failed? --------------------------------------------

def _after_build(state: Dict[str, Any]) -> str:
    """Route after build: if failed go to END, otherwise assets."""
    if state.get("failed"):
        logger.warning("[build] Build failed; skipping assets/publish.")
        return END
    return "assets"


def _after_generate(state: Dict[str, Any]) -> str:
    """Route after generate: if failed go to END, otherwise build."""
    if state.get("failed"):
        logger.warning("[generate] Generation failed; ending demand pipeline.")
        return END
    return "build"


# -- Build demand graph ----------------------------------------------------

def build_demand_graph(checkpointer=None) -> Any:
    """Construct and compile the per-demand processing StateGraph.

    Parameters
    ----------
    checkpointer : optional
        A LangGraph checkpointer for persistence.

    Returns
    -------
    CompiledGraph
        The compiled per-demand graph.
    """
    graph = StateGraph(DemandState)

    graph.add_node("generate", node_generate)
    graph.add_node("build", node_build)
    graph.add_node("assets", node_assets)
    graph.add_node("publish", node_publish)

    graph.set_entry_point("generate")
    graph.add_conditional_edges("generate", _after_generate)
    graph.add_conditional_edges("build", _after_build)
    graph.add_edge("assets", "publish")
    graph.add_edge("publish", END)

    compile_kwargs: Dict[str, Any] = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer

    return graph.compile(**compile_kwargs)
