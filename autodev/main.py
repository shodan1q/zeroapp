"""CLI entry point using Typer."""

from __future__ import annotations

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="autodev",
    help="AutoDev Agent: Autonomous app development pipeline.",
    add_completion=False,
)
pipeline_app = typer.Typer(
    name="pipeline",
    help="LangGraph-based pipeline commands.",
)
app.add_typer(pipeline_app, name="pipeline")
console = Console()


# ── Legacy top-level commands (kept for backward compatibility) ───────


@app.command()
def run() -> None:
    """Start the full AutoDev pipeline as a long-running service."""
    console.print(Panel("[bold green]Starting AutoDev Agent[/bold green]", title="AutoDev"))
    asyncio.run(_run_loop())


@app.command()
def crawl(
    source: str = typer.Option("all", help="Crawl source: reddit, producthunt, appstore, all"),
) -> None:
    """Run crawlers to gather app demands."""
    console.print(f"[cyan]Crawling from: {source}[/cyan]")
    from autodev.pipeline.orchestrator import run_pipeline

    asyncio.run(run_pipeline())
    console.print("[green]Crawl complete.[/green]")


@app.command()
def evaluate() -> None:
    """Evaluate and score pending demands."""
    console.print("[cyan]Evaluating pending demands...[/cyan]")
    from autodev.pipeline.orchestrator import run_pipeline

    asyncio.run(run_pipeline())
    console.print("[green]Evaluation complete.[/green]")


@app.command()
def generate(
    demand_id: Optional[int] = typer.Option(None, help="Generate code for a specific demand ID"),
) -> None:
    """Generate Flutter app code for approved demands."""
    console.print("[cyan]Generating Flutter app code...[/cyan]")
    from autodev.pipeline.orchestrator import run_pipeline

    asyncio.run(run_pipeline())
    console.print("[green]Code generation complete.[/green]")


@app.command()
def build(
    demand_id: Optional[int] = typer.Option(None, help="Build a specific demand ID"),
) -> None:
    """Build Flutter apps for generated code."""
    console.print("[cyan]Building Flutter apps...[/cyan]")
    from autodev.pipeline.orchestrator import run_pipeline

    asyncio.run(run_pipeline())
    console.print("[green]Build complete.[/green]")


@app.command()
def dashboard() -> None:
    """Launch the FastAPI dashboard server."""
    import uvicorn

    console.print("[cyan]Starting dashboard at http://0.0.0.0:8000[/cyan]")
    uvicorn.run("autodev.api.app:app", host="0.0.0.0", port=8000, reload=True)


# ── Pipeline sub-commands ────────────────────────────────────────────


@pipeline_app.command("run")
def pipeline_run() -> None:
    """Run one complete pipeline cycle: crawl -> evaluate -> generate -> build -> publish."""
    console.print(Panel("[bold cyan]Running full pipeline[/bold cyan]", title="AutoDev"))
    from autodev.pipeline.orchestrator import run_pipeline

    summary = asyncio.run(run_pipeline())
    _print_summary(summary)


@pipeline_app.command("resume")
def pipeline_resume(
    thread_id: str = typer.Option(..., help="Thread ID of the pipeline run to resume"),
) -> None:
    """Resume a pipeline run from its last checkpoint."""
    console.print(f"[cyan]Resuming pipeline (thread_id={thread_id})...[/cyan]")
    from autodev.pipeline.orchestrator import resume_pipeline

    summary = asyncio.run(resume_pipeline(thread_id))
    _print_summary(summary)


@pipeline_app.command("loop")
def pipeline_loop(
    interval: int = typer.Option(None, help="Hours between cycles (default: from settings)"),
) -> None:
    """Run the pipeline in continuous loop mode."""
    console.print(
        Panel("[bold green]Starting continuous pipeline loop[/bold green]", title="AutoDev")
    )
    asyncio.run(_run_loop(interval_hours=interval))


@pipeline_app.command("status")
def pipeline_status(
    thread_id: str = typer.Option(..., help="Thread ID to check"),
) -> None:
    """Check the status of a pipeline run by thread ID."""
    from autodev.pipeline.orchestrator import get_pipeline_status

    status = asyncio.run(get_pipeline_status(thread_id))

    if not status.get("found"):
        console.print(f"[yellow]No checkpoint found for thread_id={thread_id}.[/yellow]")
        if status.get("error"):
            console.print(f"[red]Error: {status['error']}[/red]")
        return

    table = Table(title=f"Pipeline Status: {thread_id}")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Stage", str(status.get("stage", "?")))
    table.add_row("Demands Crawled", str(status.get("demands_crawled", 0)))
    table.add_row("Demands Approved", str(status.get("demands_approved", 0)))
    table.add_row("Demands Built", str(status.get("demands_built", 0)))
    table.add_row("Demands Published", str(status.get("demands_published", 0)))
    table.add_row("Errors", str(len(status.get("errors", []))))
    table.add_row("Next Steps", ", ".join(status.get("next_steps", [])) or "none")

    console.print(table)

    if status.get("errors"):
        console.print("\n[bold red]Errors:[/bold red]")
        for err in status["errors"][:10]:
            console.print(f"  [red]- {err}[/red]")


# ── Helpers ──────────────────────────────────────────────────────────


async def _run_loop(*, interval_hours: int | None = None) -> None:
    """Async wrapper for the continuous loop."""
    from autodev.pipeline.orchestrator import run_loop

    await run_loop(interval_hours=interval_hours)


def _print_summary(summary) -> None:
    """Pretty-print a PipelineRunSummary."""
    table = Table(title=f"Pipeline Run: {summary.run_id}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Thread ID", summary.thread_id)
    table.add_row("Resumed", str(summary.resumed))
    table.add_row("Started", str(summary.started_at))
    table.add_row("Finished", str(summary.finished_at))
    table.add_row("Demands Crawled", str(summary.demands_crawled))
    table.add_row("Demands Approved", str(summary.demands_approved))
    table.add_row("Demands Rejected", str(summary.demands_rejected))
    table.add_row("Demands Built", str(summary.demands_built))
    table.add_row("Demands Published", str(summary.demands_published))
    table.add_row("Errors", str(len(summary.errors)))

    console.print(table)

    if summary.errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for err in summary.errors[:10]:
            console.print(f"  [red]- {err}[/red]")
    else:
        console.print("\n[bold green]No errors.[/bold green]")


if __name__ == "__main__":
    app()
