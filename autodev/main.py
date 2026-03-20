"""CLI entry point using Typer."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(
    name="autodev",
    help="AutoDev Agent: Autonomous app development pipeline.",
    add_completion=False,
)
console = Console()


@app.command()
def run() -> None:
    """Start the full AutoDev pipeline as a long-running service."""
    from autodev.pipeline.orchestrator import PipelineOrchestrator

    console.print(Panel("[bold green]Starting AutoDev Agent[/bold green]", title="AutoDev"))
    orchestrator = PipelineOrchestrator()
    orchestrator.run_forever()


@app.command()
def crawl(
    source: str = typer.Option("all", help="Crawl source: reddit, producthunt, appstore, all"),
) -> None:
    """Run crawlers to gather app demands."""
    from autodev.pipeline.orchestrator import PipelineOrchestrator

    console.print(f"[cyan]Crawling from: {source}[/cyan]")
    orchestrator = PipelineOrchestrator()
    orchestrator.run_crawl(source=source)
    console.print("[green]Crawl complete.[/green]")


@app.command()
def evaluate() -> None:
    """Evaluate and score pending demands."""
    from autodev.pipeline.orchestrator import PipelineOrchestrator

    console.print("[cyan]Evaluating pending demands...[/cyan]")
    orchestrator = PipelineOrchestrator()
    count = orchestrator.run_evaluate()
    console.print(f"[green]Evaluated {count} demands.[/green]")


@app.command()
def generate(
    demand_id: int = typer.Option(None, help="Generate code for a specific demand ID"),
) -> None:
    """Generate Flutter app code for approved demands."""
    from autodev.pipeline.orchestrator import PipelineOrchestrator

    console.print("[cyan]Generating Flutter app code...[/cyan]")
    orchestrator = PipelineOrchestrator()
    orchestrator.run_generate(demand_id=demand_id)
    console.print("[green]Code generation complete.[/green]")


@app.command()
def build(
    demand_id: int = typer.Option(None, help="Build a specific demand ID"),
) -> None:
    """Build Flutter apps for generated code."""
    from autodev.pipeline.orchestrator import PipelineOrchestrator

    console.print("[cyan]Building Flutter apps...[/cyan]")
    orchestrator = PipelineOrchestrator()
    orchestrator.run_build(demand_id=demand_id)
    console.print("[green]Build complete.[/green]")


@app.command()
def pipeline() -> None:
    """Run the complete pipeline once: crawl -> evaluate -> generate -> build."""
    from autodev.pipeline.orchestrator import PipelineOrchestrator

    console.print(Panel("[bold cyan]Running full pipeline[/bold cyan]", title="AutoDev"))
    orchestrator = PipelineOrchestrator()
    orchestrator.run_once()
    console.print("[bold green]Pipeline run complete.[/bold green]")


@app.command()
def dashboard() -> None:
    """Launch the FastAPI dashboard server."""
    import uvicorn

    console.print("[cyan]Starting dashboard at http://0.0.0.0:8000[/cyan]")
    uvicorn.run("autodev.api.app:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    app()
