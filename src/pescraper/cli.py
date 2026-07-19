"""pescraper command-line interface.

Phase 1 skeleton: the command surface (run, run-firm, export, status, doctor,
init-db) is the stable seam that later phases and the Windows Task Scheduler /
nanoclaw orchestration invoke. The four data-pipeline commands are stubs here;
real behavior arrives in later phases.

Importing this module imports ``pescraper``, which activates the Windows runtime
hardening (Proactor policy + UTF-8) as a side effect, so the console entry point
runs under the hardened runtime.

``doctor`` and ``init-db`` deliberately import their implementation modules
(``pescraper.doctor`` / ``pescraper.db``) *lazily inside the function body*. Those
modules land in wave 2; keeping the imports lazy means ``pescraper --help`` and
every stub work now, before those modules exist.
"""

from __future__ import annotations

import typer

app = typer.Typer(
    help="PE Scraper — build and maintain a dataset of US private equity firms' investment criteria.",
    no_args_is_help=True,
)


@app.command()
def run() -> None:
    """Run the batch pipeline over the queued firms (Phase 1 skeleton)."""
    typer.echo("pescraper run: Phase 1 skeleton — batch pipeline lands in a later phase.")


@app.command("run-firm")
def run_firm(url: str = typer.Argument(..., help="Firm website URL to research.")) -> None:
    """Research a single firm by URL (Phase 1 skeleton)."""
    typer.echo(f"pescraper run-firm {url}: Phase 1 skeleton — single-firm research lands in a later phase.")


@app.command()
def export() -> None:
    """Export the dataset to Excel/CSV (Phase 1 skeleton)."""
    typer.echo("pescraper export: Phase 1 skeleton — export lands in a later phase.")


@app.command()
def status() -> None:
    """Show pipeline/queue status (Phase 1 skeleton)."""
    typer.echo("pescraper status: Phase 1 skeleton — status reporting lands in a later phase.")


@app.command()
def doctor() -> None:
    """Run the Windows environment smoke test (Proactor, Ollama, Crawl4AI)."""
    # Lazy import: pescraper.doctor lands in wave 2. Keeping this inside the
    # function body means --help and the other commands work before it exists.
    from pescraper.doctor import main

    raise typer.Exit(code=main())


@app.command("init-db")
def init_db() -> None:
    """Initialize pipeline.db (schema + WAL) at its configured path."""
    # Lazy import: pescraper.db lands in wave 2.
    from pescraper.db import init_db as _init_db

    db_path = _init_db()
    typer.echo(f"Initialized pipeline database at: {db_path}")


if __name__ == "__main__":
    app()
