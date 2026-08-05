"""CLI entry point using Typer."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="zerodev",
    help="ZeroDev Agent: Autonomous app development pipeline.",
    add_completion=False,
)
pipeline_app = typer.Typer(
    name="pipeline",
    help="LangGraph-based pipeline commands.",
)
app.add_typer(pipeline_app, name="pipeline")

llm_app = typer.Typer(name="llm", help="AI provider connectivity and model discovery.")
app.add_typer(llm_app, name="llm")

factory_app = typer.Typer(
    name="factory",
    help="Round-the-clock WebView app factory (HarmonyOS .hap + AppGallery).",
)
app.add_typer(factory_app, name="factory")

console = Console()


def _resolve_platforms(platform: Optional[str]) -> Optional[list[str]]:
    """Parse a ``--platform`` CLI value into a validated target list.

    Returns ``None`` when no value is supplied (the pipeline then falls back to
    the configured default). Exits with code 2 on an invalid value.
    """
    if not platform:
        return None
    from zerodev.builder.platforms import parse_platforms

    try:
        return parse_platforms(platform)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc


_PLATFORM_OPTION_HELP = "Build targets, comma-separated: android,ios,ohos (default: from settings)"


# ── Legacy top-level commands (kept for backward compatibility) ───────


@app.command()
def run() -> None:
    """Start the full ZeroDev pipeline as a long-running service."""
    console.print(Panel("[bold green]Starting ZeroDev Agent[/bold green]", title="ZeroDev"))
    asyncio.run(_run_loop())


@app.command()
def crawl(
    source: str = typer.Option("all", help="Crawl source: reddit, producthunt, appstore, all"),
) -> None:
    """Run crawlers to gather app demands."""
    console.print(f"[cyan]Crawling from: {source}[/cyan]")
    from zerodev.pipeline.orchestrator import run_pipeline

    asyncio.run(run_pipeline())
    console.print("[green]Crawl complete.[/green]")


@app.command()
def evaluate() -> None:
    """Evaluate and score pending demands."""
    console.print("[cyan]Evaluating pending demands...[/cyan]")
    from zerodev.pipeline.orchestrator import run_pipeline

    asyncio.run(run_pipeline())
    console.print("[green]Evaluation complete.[/green]")


@app.command()
def generate(
    demand_id: Optional[int] = typer.Option(None, help="Generate code for a specific demand ID"),
    platform: Optional[str] = typer.Option(None, "--platform", help=_PLATFORM_OPTION_HELP),
) -> None:
    """Generate Flutter app code for approved demands."""
    platforms = _resolve_platforms(platform)
    console.print(f"[cyan]Generating Flutter app code (platforms={platforms or 'default'})...[/cyan]")
    from zerodev.pipeline.orchestrator import run_pipeline

    asyncio.run(run_pipeline(target_platforms=platforms))
    console.print("[green]Code generation complete.[/green]")


@app.command()
def build(
    demand_id: Optional[int] = typer.Option(None, help="Build a specific demand ID"),
    platform: Optional[str] = typer.Option(None, "--platform", help=_PLATFORM_OPTION_HELP),
) -> None:
    """Build Flutter apps for generated code."""
    platforms = _resolve_platforms(platform)
    console.print(f"[cyan]Building Flutter apps (platforms={platforms or 'default'})...[/cyan]")
    from zerodev.pipeline.orchestrator import run_pipeline

    asyncio.run(run_pipeline(target_platforms=platforms))
    console.print("[green]Build complete.[/green]")


@app.command()
def dashboard() -> None:
    """Launch the FastAPI dashboard server."""
    import uvicorn

    console.print("[cyan]Starting dashboard at http://0.0.0.0:9716[/cyan]")
    uvicorn.run("zerodev.api.app:app", host="0.0.0.0", port=9716, reload=True)


# ── Pipeline sub-commands ────────────────────────────────────────────


@pipeline_app.command("run")
def pipeline_run(
    platform: Optional[str] = typer.Option(None, "--platform", help=_PLATFORM_OPTION_HELP),
) -> None:
    """Run one complete pipeline cycle: crawl -> evaluate -> generate -> build -> publish."""
    platforms = _resolve_platforms(platform)
    console.print(Panel("[bold cyan]Running full pipeline[/bold cyan]", title="ZeroDev"))
    from zerodev.pipeline.orchestrator import run_pipeline

    summary = asyncio.run(run_pipeline(target_platforms=platforms))
    _print_summary(summary)


@pipeline_app.command("resume")
def pipeline_resume(
    thread_id: str = typer.Option(..., help="Thread ID of the pipeline run to resume"),
) -> None:
    """Resume a pipeline run from its last checkpoint."""
    console.print(f"[cyan]Resuming pipeline (thread_id={thread_id})...[/cyan]")
    from zerodev.pipeline.orchestrator import resume_pipeline

    summary = asyncio.run(resume_pipeline(thread_id))
    _print_summary(summary)


@pipeline_app.command("loop")
def pipeline_loop(
    interval: int = typer.Option(None, help="Hours between cycles (default: from settings)"),
) -> None:
    """Run the pipeline in continuous loop mode."""
    console.print(Panel("[bold green]Starting continuous pipeline loop[/bold green]", title="ZeroDev"))
    asyncio.run(_run_loop(interval_hours=interval))


@pipeline_app.command("status")
def pipeline_status(
    thread_id: str = typer.Option(..., help="Thread ID to check"),
) -> None:
    """Check the status of a pipeline run by thread ID."""
    from zerodev.pipeline.orchestrator import get_pipeline_status

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


# ── LLM sub-commands ─────────────────────────────────────────────────


@llm_app.command("probe")
def llm_probe(
    match: str = typer.Option("", "--match", help="Highlight model ids resembling this name, e.g. 'chatgpt5.6'"),
    save_model: bool = typer.Option(
        False, "--save-model", help="Write the best matching model id into data/settings.json"
    ),
) -> None:
    """Verify the configured provider answers, and list the models it serves.

    Use this after pointing the relay at a base URL: it shows the exact model
    aliases that endpoint accepts, so the configured model name is never a guess.
    """
    from zerodev.llm import probe_provider, resolve_llm_config

    cfg = resolve_llm_config()
    fallback_url = "(official endpoint)" if cfg.spec.kind == "anthropic" else "(unset)"
    console.print(
        Panel(
            f"[bold cyan]{cfg.spec.label}[/bold cyan]  model=[green]{cfg.model or '(unset)'}[/green]\n"
            f"base_url={cfg.base_url or fallback_url}",
            title="LLM probe",
        )
    )

    result = probe_provider()

    if result.config_gaps:
        console.print("[bold red]Configuration incomplete:[/bold red]")
        for gap in result.config_gaps:
            console.print(f"  [red]- {gap}[/red]")

    if result.models_error:
        console.print(f"[yellow]Could not list models: {result.models_error}[/yellow]")
    elif result.models_available:
        console.print(f"[green]{len(result.models_available)} model(s) available.[/green]")
        highlighted = result.suggest_models(match or cfg.model)
        if highlighted:
            table = Table(title=f"Models resembling {(match or cfg.model) or 'the configured model'}")
            table.add_column("Model id", style="green")
            for name in highlighted[:15]:
                table.add_row(name)
            console.print(table)
        else:
            console.print("  " + ", ".join(result.models_available[:30]))

    if result.chat_ok:
        console.print(f"[bold green]Chat OK[/bold green] -- replied: {result.chat_reply!r}")
    elif result.chat_error:
        console.print(f"[bold red]Chat failed:[/bold red] {result.chat_error}")

    if save_model:
        candidates = result.suggest_models(match or cfg.model)
        if not candidates:
            console.print("[yellow]No matching model to save.[/yellow]")
        else:
            _save_setting(f"{cfg.provider}Model", candidates[0])
            console.print(f"[green]Saved {cfg.provider}Model = {candidates[0]} to data/settings.json[/green]")

    raise typer.Exit(code=0 if result.ok else 1)


@llm_app.command("providers")
def llm_providers() -> None:
    """List every supported AI provider and its default endpoint."""
    from zerodev.providers import PROVIDERS

    table = Table(title="AI providers")
    table.add_column("id", style="cyan")
    table.add_column("Label", style="green")
    table.add_column("Default model")
    table.add_column("Default base URL")
    for spec in PROVIDERS.values():
        table.add_row(spec.id, spec.label, spec.default_model or "(must configure)", spec.default_base_url or "-")
    console.print(table)


# ── App factory sub-commands ─────────────────────────────────────────


@factory_app.command("doctor")
def factory_doctor() -> None:
    """Check that everything the factory needs is installed and configured."""
    from zerodev.builder.ohos_builder import OhosSigningConfig, OhosToolchainError, find_toolchain
    from zerodev.builder.publisher import HarmonyOSPublisher
    from zerodev.llm import describe_config_gaps, resolve_llm_config

    table = Table(title="Factory preflight")
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Detail")

    cfg = resolve_llm_config()
    gaps = describe_config_gaps(cfg)
    table.add_row(
        "AI provider",
        "[green]ready[/green]" if not gaps else "[red]incomplete[/red]",
        f"{cfg.spec.label} / {cfg.model or '(model unset)'}" if not gaps else gaps[0][:90],
    )

    try:
        toolchain = find_toolchain()
        table.add_row(
            "HarmonyOS toolchain", "[green]ready[/green]", f"{toolchain.deveco_home} (API {toolchain.api_version})"
        )
    except OhosToolchainError as exc:
        table.add_row("HarmonyOS toolchain", "[red]missing[/red]", str(exc)[:90])

    from zerodev.generator.runtime_verifier import harness_available

    ready, reason = harness_available()
    table.add_row(
        "Runtime gate",
        "[green]armed[/green]" if ready else "[red]OFF[/red]",
        "generated apps are executed before shipping" if ready else reason[:90],
    )

    signing = OhosSigningConfig.from_settings()
    if signing is None:
        table.add_row("Release signing", "[yellow]not configured[/yellow]", "builds will be unsigned (OHOS_SIGN_*)")
    else:
        missing = signing.missing_files()
        table.add_row(
            "Release signing",
            "[green]ready[/green]" if not missing else "[red]files missing[/red]",
            ", ".join(missing)[:90] or signing.key_alias,
        )

    publisher = HarmonyOSPublisher()
    has_creds = all((publisher.client_id, publisher.client_secret, publisher.app_id))
    table.add_row(
        "AppGallery (AGC)",
        "[green]ready[/green]" if has_creds else "[yellow]not configured[/yellow]",
        f"auto_submit={publisher.auto_submit}" if has_creds else "HUAWEI_AGC_CLIENT_ID / _SECRET / _APP_ID",
    )

    console.print(table)


@factory_app.command("build")
def factory_build(
    name: str = typer.Option(..., "--name", help="App name shown to users (Chinese is fine)"),
    description: str = typer.Option("", "--desc", help="What the app does and who it is for"),
    slug: str = typer.Option("", "--slug", help="Latin slug for the bundle name; derived when omitted"),
    features: str = typer.Option("", "--features", help="Comma-separated feature list"),
    theme: str = typer.Option("#0A84FF", "--theme", help="Brand colour, used for the generated icon"),
    publish: bool = typer.Option(False, "--publish", help="Upload to AppGallery after a successful build"),
    no_build: bool = typer.Option(False, "--no-build", help="Generate assets and project only, skip hvigor"),
) -> None:
    """Build one WebView app end to end and report every stage."""
    from zerodev.pipeline.webview_app import WebviewAppRequest, create_webview_app

    request = WebviewAppRequest(
        app_name=name,
        description=description or name,
        slug=slug,
        features=[f.strip() for f in features.split(",") if f.strip()],
        theme_color=theme,
        publish=publish,
    )
    console.print(Panel(f"[bold cyan]{name}[/bold cyan]\n{request.description}", title="Building app"))
    result = asyncio.run(create_webview_app(request, build=not no_build))
    console.print(result.render())
    if result.hap_path:
        console.print(f"\n[bold green]Artifact:[/bold green] {result.hap_path}")
    raise typer.Exit(code=0 if result.success else 1)


@factory_app.command("batch")
def factory_batch(
    file: str = typer.Option(..., "--file", help="JSON file holding an array of app briefs"),
    concurrency: int = typer.Option(3, "--concurrency", help="How many apps to build at once"),
    max_rounds: int = typer.Option(2, "--max-rounds", help="Rework attempts before giving up on an app"),
    publish: bool = typer.Option(False, "--publish", help="Submit accepted apps to AppGallery"),
    no_build: bool = typer.Option(False, "--no-build", help="Generate only; skip hvigor builds"),
) -> None:
    """Build several apps concurrently under supervision (LangGraph batch graph).

    Each app is scored on measured signals -- did it run, how many views and
    features registered, how much content it holds -- and either accepted,
    rebuilt, or rejected. Nothing is published on the strength of compiling.
    """
    import json as _json

    from zerodev.pipeline.factory_graph import run_factory_batch

    briefs = _json.loads(Path(file).read_text(encoding="utf-8"))
    if isinstance(briefs, dict):
        briefs = briefs.get("apps", [])
    console.print(
        Panel(
            f"[bold cyan]{len(briefs)} app(s)[/bold cyan] concurrency={concurrency} rounds={max_rounds}",
            title="Factory batch",
        )
    )

    report = asyncio.run(
        run_factory_batch(
            briefs,
            build=not no_build,
            publish=publish,
            max_rounds=max_rounds,
            concurrency=concurrency,
        )
    )
    _print_batch_report(report)
    raise typer.Exit(code=0 if report.get("accepted") else 1)


def _print_batch_report(report: dict) -> None:
    table = Table(title="Batch result")
    table.add_column("App", style="cyan")
    table.add_column("Verdict")
    table.add_column("Score", justify="right")
    table.add_column("Views", justify="right")
    table.add_column("Features", justify="right")
    table.add_column("Records", justify="right")
    table.add_column("Artifact")

    colours = {"accept": "green", "rework": "yellow", "reject": "red"}
    for app in report.get("apps", []):
        metrics = app.get("metrics") or {}
        verdict = app.get("verdict", "?")
        table.add_row(
            str(app.get("app_name", "?")),
            f"[{colours.get(verdict, 'white')}]{verdict}[/{colours.get(verdict, 'white')}]",
            f"{app.get('score', 0):.0f}",
            str(metrics.get("views", "-")),
            str(metrics.get("features", "-")),
            str(metrics.get("records", "-")),
            (app.get("hap") or app.get("error") or "-")[-46:],
        )
    console.print(table)
    console.print(
        f"[bold]{report.get('accepted', 0)} accepted, {report.get('rejected', 0)} rejected, "
        f"average score {report.get('average_score', 0)}[/bold] "
        f"(attempts: {report.get('attempts', 0)})"
    )


@factory_app.command("run")
def factory_run(
    max_apps: Optional[int] = typer.Option(None, "--max-apps", help="Stop after this many successful apps"),
    idle: float = typer.Option(0.0, "--idle", help="Seconds to wait between apps (0 = continuous)"),
    publish: bool = typer.Option(False, "--publish", help="Submit each successful build to AppGallery"),
    no_build: bool = typer.Option(False, "--no-build", help="Generate only; skip hvigor builds"),
) -> None:
    """Run the factory continuously: generate, build and optionally publish apps."""
    from zerodev.pipeline.daemon import DaemonConfig, run_factory

    console.print(Panel("[bold green]App factory starting[/bold green]\nCtrl-C for a graceful stop.", title="ZeroDev"))
    config = DaemonConfig(max_apps=max_apps, idle_seconds=idle, publish=publish, build=not no_build)
    try:
        state = asyncio.run(run_factory(config))
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted.[/yellow]")
        raise typer.Exit(code=130) from None
    console.print(f"[green]Built {state.apps_built}, failed {state.apps_failed}.[/green]")


@factory_app.command("status")
def factory_status() -> None:
    """Show what the factory is doing right now, and its recent history."""
    from zerodev.pipeline.daemon import read_state

    state = read_state()
    if state.get("note"):
        console.print(f"[yellow]{state['note']}[/yellow]")
        return

    table = Table(title="App factory")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Running", str(state.get("running", False)))
    if "alive" in state:
        table.add_row("Alive (heartbeat)", str(state["alive"]))
        table.add_row("Heartbeat age", f"{state.get('heartbeat_age_seconds', '?')}s")
    table.add_row("Current app", state.get("current_app") or "-")
    table.add_row("Built", str(state.get("apps_built", 0)))
    table.add_row("Failed", str(state.get("apps_failed", 0)))
    table.add_row("Consecutive failures", str(state.get("consecutive_failures", 0)))
    if state.get("last_error"):
        table.add_row("Last error", state["last_error"][:120])
    console.print(table)

    history = state.get("history", [])[-10:]
    if history:
        recent = Table(title="Recent runs")
        recent.add_column("When", style="cyan")
        recent.add_column("App")
        recent.add_column("Result")
        for entry in reversed(history):
            mark = (
                "[green]ok[/green]" if entry.get("success") else f"[red]{entry.get('failed_stage') or 'failed'}[/red]"
            )
            recent.add_row(str(entry.get("at", ""))[:19], str(entry.get("app_name", "")), mark)
        console.print(recent)


@factory_app.command("service")
def factory_service(
    label: str = typer.Option("com.zerodev.factory", "--label", help="launchd service label"),
) -> None:
    """Write a launchd agent so the factory starts at login and stays up.

    The file is written into the repository; loading it is left to you, since a
    launchd agent is persistent configuration on your account.
    """
    import plistlib

    from zerodev.config import get_settings

    root = get_settings().base_dir
    launcher = root / "scripts" / "run-factory.sh"
    if not launcher.exists():
        console.print(f"[red]Launcher missing: {launcher}[/red]")
        raise typer.Exit(code=1)
    launcher.chmod(0o755)

    log_dir = root / "data" / "factory"
    log_dir.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": label,
        "ProgramArguments": [str(launcher)],
        "WorkingDirectory": str(root),
        "RunAtLoad": True,
        # launchd restarts the process whenever it exits, which is what makes
        # the factory survive a crash, an OOM kill, or a machine reboot.
        "KeepAlive": True,
        "ThrottleInterval": 60,
        "StandardOutPath": str(log_dir / "daemon.log"),
        "StandardErrorPath": str(log_dir / "daemon.err.log"),
        "ProcessType": "Background",
    }

    target = root / "scripts" / f"{label}.plist"
    target.write_bytes(plistlib.dumps(plist))
    console.print(f"[green]Wrote {target}[/green]\n")
    console.print("To install it (run these yourself):\n")
    console.print(f"  cp {target} ~/Library/LaunchAgents/{label}.plist")
    console.print(f"  launchctl load -w ~/Library/LaunchAgents/{label}.plist\n")
    console.print("To stop and remove it later:\n")
    console.print(f"  launchctl unload -w ~/Library/LaunchAgents/{label}.plist")
    console.print(f"  rm ~/Library/LaunchAgents/{label}.plist\n")
    console.print(f"Logs will go to {log_dir}/daemon.log")


@factory_app.command("queue")
def factory_queue(
    name: str = typer.Option(..., "--name", help="App name to enqueue"),
    description: str = typer.Option("", "--desc", help="What the app does"),
    slug: str = typer.Option("", "--slug", help="Latin slug for the bundle name"),
    features: str = typer.Option("", "--features", help="Comma-separated feature list"),
) -> None:
    """Add an app brief to the factory queue; the daemon picks it up first."""
    from zerodev.pipeline.daemon import write_queue

    entry = {
        "app_name": name,
        "description": description or name,
        "slug": slug,
        "features": [f.strip() for f in features.split(",") if f.strip()],
    }
    path = write_queue([entry])
    console.print(f"[green]Queued '{name}'.[/green] Queue file: {path}")


# ── Helpers ──────────────────────────────────────────────────────────


def _save_setting(key: str, value: str) -> None:
    """Merge one key into data/settings.json, preserving everything else."""
    import json

    from zerodev.config import get_settings

    path = get_settings().base_dir / "data" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            console.print(f"[yellow]{path} was unreadable; rewriting it.[/yellow]")
    payload[key] = value
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def _run_loop(*, interval_hours: int | None = None) -> None:
    """Async wrapper for the continuous loop."""
    from zerodev.pipeline.orchestrator import run_loop

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
