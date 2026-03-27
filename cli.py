"""
SwarmDev CLI — Rich terminal interface for submitting and monitoring swarm tasks.
Run: python cli.py
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()
API_BASE = "http://localhost:8000"

BANNER = """[bold cyan]
  ███████╗██╗    ██╗ █████╗ ██████╗ ███╗   ███╗██████╗ ███████╗██╗   ██╗
  ██╔════╝██║    ██║██╔══██╗██╔══██╗████╗ ████║██╔══██╗██╔════╝██║   ██║
  ███████╗██║ █╗ ██║███████║██████╔╝██╔████╔██║██║  ██║█████╗  ██║   ██║
  ╚════██║██║███╗██║██╔══██║██╔══██╗██║╚██╔╝██║██║  ██║██╔══╝  ╚██╗ ██╔╝
  ███████║╚███╔███╔╝██║  ██║██║  ██║██║ ╚═╝ ██║██████╔╝███████╗ ╚████╔╝ 
  ╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═════╝ ╚══════╝  ╚═══╝  
[/bold cyan][dim]  Swarm Intelligence Code Generator — CLI Interface[/dim]
"""

STACKS = {
    "1": ("fullstack", "React + FastAPI + PostgreSQL"),
    "2": ("react",     "React SPA"),
    "3": ("python",    "Python / FastAPI only"),
    "4": ("ml",        "ML / PyTorch pipeline"),
}

DEMOS = {
    "1": ("collab_editor",   "Real-Time Collaborative Code Editor"),
    "2": ("ecommerce",       "E-Commerce Platform"),
    "3": ("ml_pipeline",     "ML Training Pipeline"),
    "4": ("rest_api",        "REST API with Auth"),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _check_server() -> bool:
    try:
        r = httpx.get(f"{API_BASE}/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def _format_status(status: str) -> Text:
    colors = {
        "queued":    "yellow",
        "running":   "cyan",
        "done":      "green",
        "failed":    "red",
        "cancelled": "dim",
    }
    return Text(status.upper(), style=f"bold {colors.get(status, 'white')}")


def _history_table(jobs: list) -> Table:
    t = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta",
              border_style="dim", expand=True)
    t.add_column("ID",       style="dim",        width=10)
    t.add_column("Project",  style="bold white",  width=20)
    t.add_column("Stack",    style="cyan",        width=12)
    t.add_column("Status",                        width=12)
    t.add_column("Files",    justify="right",     width=7)
    t.add_column("Tokens",   justify="right",     width=10)
    t.add_column("Started",  style="dim",         width=20)

    for j in jobs:
        t.add_row(
            j["id"][:8],
            j["project_name"],
            j["stack"],
            _format_status(j["status"]),
            str(j.get("files_generated", "-")),
            f"{j.get('tokens_used', 0):,}" if j.get("tokens_used") else "-",
            j.get("created_at", "-")[:19].replace("T", " "),
        )
    return t


# ── Screens ───────────────────────────────────────────────────────────────────

def screen_submit():
    console.print(Panel("[bold]Submit a New Task[/bold]", border_style="cyan"))

    # Project name
    project = Prompt.ask("[cyan]Project name[/cyan]", default="my_project")
    project = project.strip().lower().replace(" ", "_")

    # Description
    console.print("\n[dim]Describe what you want to build (be as detailed as you like):[/dim]")
    description = Prompt.ask("[cyan]Description[/cyan]")

    # Stack
    console.print("\n[bold]Select stack:[/bold]")
    for k, (_, label) in STACKS.items():
        console.print(f"  [cyan]{k}[/cyan] → {label}")
    stack_choice = Prompt.ask("[cyan]Stack[/cyan]", choices=list(STACKS.keys()), default="1")
    stack, stack_label = STACKS[stack_choice]

    # Confirm
    console.print()
    console.print(Panel(
        f"[bold]Project:[/bold] {project}\n"
        f"[bold]Stack:[/bold]   {stack_label}\n"
        f"[bold]Task:[/bold]    {description}",
        title="Confirm", border_style="green"
    ))

    if not Confirm.ask("Submit this task?", default=True):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    # Submit
    try:
        r = httpx.post(f"{API_BASE}/jobs", json={
            "project_name": project,
            "description":  description,
            "stack":        stack,
        }, timeout=10)
        r.raise_for_status()
        job = r.json()
        console.print(f"\n[green]✓ Job submitted![/green] ID: [bold cyan]{job['id'][:8]}[/bold cyan]")

        if Confirm.ask("Watch live progress?", default=True):
            screen_watch(job["id"])
    except Exception as e:
        console.print(f"[red]Error submitting job: {e}[/red]")


def screen_watch(job_id: str = None):
    if not job_id:
        job_id = Prompt.ask("[cyan]Job ID[/cyan] (or partial)")
        # resolve partial
        try:
            jobs = httpx.get(f"{API_BASE}/jobs", timeout=5).json()
            matches = [j for j in jobs if j["id"].startswith(job_id)]
            if not matches:
                console.print("[red]No matching job found.[/red]")
                return
            job_id = matches[0]["id"]
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return

    console.print(f"\n[dim]Watching job [bold]{job_id[:8]}[/bold] — Ctrl+C to stop[/dim]\n")

    log_seen = set()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[cyan]{task.completed}/{task.total}[/cyan] tasks"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:

        task_bar = progress.add_task("Initialising…", total=100, completed=0)

        try:
            while True:
                try:
                    r = httpx.get(f"{API_BASE}/jobs/{job_id}", timeout=5)
                    job = r.json()
                except Exception:
                    time.sleep(2)
                    continue

                status  = job.get("status", "queued")
                ts      = job.get("task_status", {})
                done    = ts.get("done", 0)
                total   = ts.get("done", 0) + ts.get("running", 0) + ts.get("pending", 0)
                total   = max(total, 1)
                pct     = int(done / total * 100)

                progress.update(
                    task_bar,
                    description=f"[bold]{job['project_name']}[/bold] [{status}]",
                    completed=pct,
                    total=100,
                )

                # Print new logs
                for entry in job.get("logs", []):
                    key = entry.get("ts", "") + entry.get("msg", "")
                    if key not in log_seen:
                        log_seen.add(key)
                        lvl = entry.get("level", "info")
                        color = {"info": "white", "warning": "yellow", "error": "red"}.get(lvl, "white")
                        console.print(f"  [dim]{entry.get('ts','')[-8:]}[/dim] [{color}]{entry.get('msg','')}[/{color}]")

                if status in ("done", "failed", "cancelled"):
                    break

                time.sleep(2)

        except KeyboardInterrupt:
            pass

    # Final summary
    try:
        job = httpx.get(f"{API_BASE}/jobs/{job_id}", timeout=5).json()
        _print_job_summary(job)
    except Exception:
        pass


def _print_job_summary(job: dict):
    status = job.get("status", "?")
    color  = "green" if status == "done" else "red"

    files = job.get("files_generated", [])
    file_list = "\n".join(f"  [dim]•[/dim] {f}" for f in files) if files else "  [dim]none[/dim]"

    console.print(Panel(
        f"[bold]Status:[/bold]  [{color}]{status.upper()}[/{color}]\n"
        f"[bold]Tokens:[/bold]  {job.get('tokens_used', 0):,}\n"
        f"[bold]Elapsed:[/bold] {job.get('elapsed_seconds', 0):.1f}s\n"
        f"[bold]Files:[/bold]\n{file_list}",
        title=f"Job {job['id'][:8]} — {job['project_name']}",
        border_style=color,
    ))


def screen_history():
    try:
        jobs = httpx.get(f"{API_BASE}/jobs", timeout=5).json()
    except Exception as e:
        console.print(f"[red]Could not reach API: {e}[/red]")
        return

    if not jobs:
        console.print("[dim]No jobs yet.[/dim]")
        return

    console.print(_history_table(jobs))

    job_id = Prompt.ask("\n[cyan]Enter job ID to inspect (or Enter to skip)[/cyan]", default="")
    if job_id:
        matches = [j for j in jobs if j["id"].startswith(job_id)]
        if matches:
            _print_job_summary(matches[0])


def screen_files(job_id: str = None):
    try:
        jobs = httpx.get(f"{API_BASE}/jobs", timeout=5).json()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return

    if not job_id:
        console.print(_history_table(jobs))
        job_id = Prompt.ask("[cyan]Job ID[/cyan]")

    matches = [j for j in jobs if j["id"].startswith(job_id)]
    if not matches:
        console.print("[red]Not found.[/red]")
        return

    job = matches[0]
    files = job.get("files_generated", [])
    if not files:
        console.print("[dim]No files generated.[/dim]")
        return

    console.print(Panel(f"[bold]Files for {job['project_name']}[/bold]", border_style="cyan"))
    for i, f in enumerate(files, 1):
        console.print(f"  [cyan]{i:2}.[/cyan] {f}")

    choice = Prompt.ask("\n[cyan]Preview file # (or Enter to skip)[/cyan]", default="")
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(files):
            path = Path(files[idx])
            if path.exists():
                content = path.read_text(encoding="utf-8", errors="replace")
                ext = path.suffix
                lang = {".py": "python", ".jsx": "javascript", ".yml": "yaml", ".md": "markdown"}.get(ext, "text")
                console.print(Panel(content[:3000], title=str(path.name),
                                    border_style="dim", subtitle=lang))
            else:
                console.print("[red]File not found on disk.[/red]")


def screen_demo():
    console.print(Panel("[bold]Run a Demo Preset[/bold]", border_style="cyan"))
    for k, (name, label) in DEMOS.items():
        console.print(f"  [cyan]{k}[/cyan] → {label}")
    choice = Prompt.ask("[cyan]Choose demo[/cyan]", choices=list(DEMOS.keys()), default="1")
    demo_name, demo_label = DEMOS[choice]

    try:
        r = httpx.post(f"{API_BASE}/jobs/demo/{demo_name}", timeout=10)
        r.raise_for_status()
        job = r.json()
        console.print(f"\n[green]✓ Demo started![/green] ID: [bold cyan]{job['id'][:8]}[/bold cyan]")
        if Confirm.ask("Watch live progress?", default=True):
            screen_watch(job["id"])
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


# ── Main menu ─────────────────────────────────────────────────────────────────

def main_menu():
    console.print(BANNER)

    if not _check_server():
        console.print(Panel(
            "[yellow]API server is not running.[/yellow]\n\n"
            "Start it with:\n  [bold cyan]python server.py[/bold cyan]\n\n"
            "Then relaunch the CLI.",
            title="⚠ Server Offline", border_style="red"
        ))
        sys.exit(1)

    console.print("[green]✓ API server connected[/green]\n")

    MENU = {
        "1": ("Submit new task",    screen_submit),
        "2": ("Run demo preset",    screen_demo),
        "3": ("Watch live job",     lambda: screen_watch()),
        "4": ("Job history",        screen_history),
        "5": ("Browse output files",screen_files),
        "q": ("Quit",               None),
    }

    while True:
        console.print("\n[bold]Main Menu[/bold]")
        for k, (label, _) in MENU.items():
            console.print(f"  [cyan]{k}[/cyan]  {label}")

        choice = Prompt.ask("\n[cyan]>[/cyan]", choices=list(MENU.keys()), default="1")

        if choice == "q":
            console.print("[dim]Goodbye.[/dim]")
            break

        _, fn = MENU[choice]
        console.print()
        try:
            fn()
        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted.[/dim]")


if __name__ == "__main__":
    main_menu()
