"""LangGraph supervisor for the WebView app factory.

The factory previously ran as a plain ``await`` chain: one app at a time, no
durable state, and nothing between "the build finished" and "publish it". That
is fine for a single app and wrong for a factory. This graph replaces it with
the three things an unattended production line actually needs:

**Concurrency that is part of the topology, not an afterthought.** ``Send``
fans the batch out into one branch per app, so N apps are built at once and the
graph itself owns the parallelism. ``max_concurrency`` in the run config bounds
it, so a batch of twenty does not open twenty relay connections.

**Supervision.** A node between building and reporting scores every app on
signals that were measured rather than claimed -- did it run, how many views
registered, how many records exist -- and decides per app: accept, send back
for another attempt, or give up. Without this the pipeline publishes whatever
compiles.

**Durability.** State lives in a checkpointer, so a batch that dies halfway
through resumes on the same ``thread_id`` instead of rebuilding what it already
finished.

Graph shape::

    START -> intake -> [Send per app] -> build_app -> supervise -> report -> END
                            ^                             |
                            +----- rework (bounded) ------+
"""

from __future__ import annotations

import datetime
import logging
import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from zerodev.pipeline.quality import ACCEPT, REJECT, REWORK, score_app
from zerodev.pipeline.webview_app import WebviewAppRequest, create_webview_app

logger = logging.getLogger(__name__)

# How many times an app may be regenerated before the supervisor gives up.
DEFAULT_MAX_ROUNDS = 2

# Concurrent app builds. Each app is itself an internal fan-out of LLM calls,
# so this multiplies: three apps at once is already a wide request pattern.
DEFAULT_CONCURRENCY = 3


class FactoryBatchState(TypedDict, total=False):
    """State for one batch of apps."""

    briefs: list[dict[str, Any]]
    # Concurrent branches all append here, so the reducer must merge rather
    # than overwrite -- the default "last write wins" would drop every app but
    # whichever branch happened to finish last.
    results: Annotated[list[dict[str, Any]], operator.add]

    round: int
    max_rounds: int
    workspace: str
    build: bool
    publish: bool

    accepted: list[dict[str, Any]]
    rejected: list[dict[str, Any]]
    pending: list[dict[str, Any]]
    report: dict[str, Any]
    started_at: str


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def node_intake(state: FactoryBatchState) -> dict[str, Any]:
    """Normalise the batch and set the round counter."""
    briefs = [b for b in (state.get("briefs") or []) if isinstance(b, dict) and b.get("app_name")]
    if not briefs:
        raise ValueError("factory batch received no usable briefs (each needs at least app_name).")

    logger.info(
        "Factory batch: %d app(s), build=%s publish=%s",
        len(briefs),
        state.get("build", True),
        state.get("publish", False),
    )
    return {
        "briefs": briefs,
        "pending": briefs,
        "round": 1,
        "max_rounds": state.get("max_rounds", DEFAULT_MAX_ROUNDS),
        "accepted": [],
        "rejected": [],
        "started_at": datetime.datetime.now(datetime.UTC).isoformat(),
    }


def fan_out(state: FactoryBatchState) -> list[Send]:
    """Dispatch one concurrent branch per pending app.

    This is the whole reason the factory is a graph: the batch size is not
    known until runtime, and ``Send`` is how LangGraph expresses a dynamic
    map. Every branch gets its own payload; their returns merge back through
    the ``results`` reducer.
    """
    pending = state.get("pending") or []
    return [
        Send(
            "build_app",
            {
                "brief": brief,
                "round": state.get("round", 1),
                "workspace": state.get("workspace", ""),
                "build": state.get("build", True),
                "publish": state.get("publish", False),
            },
        )
        for brief in pending
    ]


async def node_build_app(payload: dict[str, Any]) -> dict[str, Any]:
    """Build one app. Runs concurrently with its siblings.

    Never raises: one app blowing up must not take down the batch, so failures
    come back as a scored result like any other outcome.
    """
    brief = payload["brief"]
    known = {f.name for f in WebviewAppRequest.__dataclass_fields__.values()}
    request = WebviewAppRequest(**{k: v for k, v in brief.items() if k in known})
    request.publish = request.publish or bool(payload.get("publish"))

    logger.info("[build] %s (round %d)", request.app_name, payload.get("round", 1))
    try:
        result = await create_webview_app(
            request,
            workspace=payload.get("workspace") or None,
            build=bool(payload.get("build", True)),
        )
        record = result.to_dict()
        record["brief"] = brief
        score = score_app(
            result.metrics,
            built=bool(result.hap_path),
            build_required=bool(payload.get("build", True)),
            generation_failed=bool(result.error),
        )
    except Exception as exc:  # noqa: BLE001 - a batch must survive any single app
        logger.exception("[build] %s crashed", request.app_name)
        record = {
            "app_name": request.app_name,
            "slug": request.resolved_slug(),
            "success": False,
            "error": f"unhandled: {type(exc).__name__}: {exc}",
            "brief": brief,
            "metrics": {},
        }
        score = score_app({}, built=False, build_required=bool(payload.get("build", True)), generation_failed=True)

    record["round"] = payload.get("round", 1)
    record["score"] = score.to_dict()
    logger.info("[build] %s -> %s", request.app_name, score.render())
    return {"results": [record]}


async def node_supervise(state: FactoryBatchState) -> dict[str, Any]:
    """Judge this round's results and decide what happens to each app."""
    results = state.get("results") or []
    round_no = state.get("round", 1)
    max_rounds = state.get("max_rounds", DEFAULT_MAX_ROUNDS)

    # Only this round's results are under judgement; earlier rounds already
    # produced a verdict and were filed.
    this_round = [r for r in results if r.get("round") == round_no]

    accepted = list(state.get("accepted") or [])
    rejected = list(state.get("rejected") or [])
    retry: list[dict[str, Any]] = []

    for record in this_round:
        verdict = (record.get("score") or {}).get("verdict", REJECT)
        name = record.get("app_name", "?")
        if verdict == ACCEPT:
            record["disposition"] = ACCEPT
            accepted.append(record)
            logger.info("[supervise] accept %s", name)
        elif verdict == REWORK and round_no < max_rounds:
            retry.append(record.get("brief") or {})
            logger.warning(
                "[supervise] rework %s: %s",
                name,
                "; ".join((record.get("score") or {}).get("reasons", [])[:3]),
            )
        else:
            # The score may have suggested rework, but the rounds ran out. What
            # the report shows is what actually happened to the app, not what
            # the scorer would have preferred.
            record["disposition"] = REJECT
            rejected.append(record)
            logger.warning(
                "[supervise] reject %s (scored %s): %s",
                name,
                verdict,
                "; ".join((record.get("score") or {}).get("reasons", [])[:3]),
            )

    return {
        "accepted": accepted,
        "rejected": rejected,
        "pending": retry,
        "round": round_no + 1,
    }


def after_supervise(state: FactoryBatchState) -> str:
    """Whether the batch loops back for another attempt. Pure decision."""
    if state.get("pending") and state.get("round", 1) <= state.get("max_rounds", DEFAULT_MAX_ROUNDS):
        return "rework"
    return "report"


def route_after_supervise(state: FactoryBatchState) -> list[Send] | str:
    """Route out of supervision.

    Rework must re-enter through ``Send`` rather than a plain edge: a plain
    edge would hand ``build_app`` the whole batch state, and the node expects
    one app's payload. Returning Sends keeps the retry path identical to the
    first pass, which is also what keeps it concurrent.
    """
    if after_supervise(state) == "rework":
        return fan_out(state)
    return "report"


async def node_report(state: FactoryBatchState) -> dict[str, Any]:
    """Summarise the batch."""
    accepted = state.get("accepted") or []
    rejected = state.get("rejected") or []
    results = state.get("results") or []

    scores = [r.get("score", {}).get("total", 0) for r in accepted + rejected]
    report = {
        "started_at": state.get("started_at", ""),
        "finished_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "requested": len(state.get("briefs") or []),
        "attempts": len(results),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "average_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
        "apps": [
            {
                "app_name": r.get("app_name"),
                "slug": r.get("slug"),
                "verdict": r.get("disposition") or (r.get("score") or {}).get("verdict"),
                "scored": (r.get("score") or {}).get("verdict"),
                "score": (r.get("score") or {}).get("total"),
                "hap": r.get("hap_path"),
                "metrics": r.get("metrics", {}),
                "error": r.get("error", ""),
            }
            for r in accepted + rejected
        ],
    }
    logger.info(
        "Factory batch done: %d accepted, %d rejected, avg score %.1f",
        report["accepted"],
        report["rejected"],
        report["average_score"],
    )
    return {"report": report}


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def build_factory_graph(checkpointer: Any = None):
    """Compile the batch factory graph."""
    graph = StateGraph(FactoryBatchState)
    graph.add_node("intake", node_intake)
    graph.add_node("build_app", node_build_app)
    graph.add_node("supervise", node_supervise)
    graph.add_node("report", node_report)

    graph.add_edge(START, "intake")
    # Dynamic fan-out: one concurrent branch per pending app.
    graph.add_conditional_edges("intake", fan_out, ["build_app"])
    graph.add_edge("build_app", "supervise")
    graph.add_conditional_edges("supervise", route_after_supervise, ["build_app", "report"])
    graph.add_edge("report", END)

    return graph.compile(checkpointer=checkpointer)


async def run_factory_batch(
    briefs: list[dict[str, Any]],
    *,
    workspace: str = "",
    build: bool = True,
    publish: bool = False,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    concurrency: int = DEFAULT_CONCURRENCY,
    thread_id: str | None = None,
    checkpointer: Any = None,
) -> dict[str, Any]:
    """Build several apps concurrently under supervision, and report.

    ``concurrency`` bounds how many app branches run at once. Each app is
    itself an internal fan-out of LLM calls, so this is a multiplier -- the
    default of three is already a wide request pattern against one provider.
    """
    import uuid

    config = {
        "configurable": {"thread_id": thread_id or f"factory-{uuid.uuid4().hex[:12]}"},
        "max_concurrency": max(1, concurrency),
        # Each app can take many minutes; the budget is about graph supersteps,
        # and a rework round needs headroom.
        "recursion_limit": 50,
    }
    initial = {
        "briefs": briefs,
        "workspace": workspace,
        "build": build,
        "publish": publish,
        "max_rounds": max_rounds,
    }

    if checkpointer is not None:
        # Caller supplied a saver (or False to disable persistence).
        compiled = build_factory_graph(checkpointer)
        final = await compiled.ainvoke(initial, config=config)
        return final.get("report", {})

    # get_checkpointer is an async context manager: the SQLite saver owns a
    # connection that has to stay open for the whole run and be closed after.
    from zerodev.pipeline.checkpointer import get_checkpointer

    async with get_checkpointer() as saver:
        compiled = build_factory_graph(saver)
        final = await compiled.ainvoke(initial, config=config)
    return final.get("report", {})
