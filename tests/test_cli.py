"""Tests for the pescraper CLI.

Proves the command surface and the stub exit-code contract via typer's CliRunner.
doctor and init-db are NOT invoked here: they touch real Ollama/Chromium/disk
(covered by test_doctor.py / test_db.py instead). run-firm's real orchestration
(crawl -> extract -> merge -> score -> persist) is Phase 2 work — this file only
locks the thin CLI-wiring contract (monkeypatching run_firm_pipeline itself);
the orchestration logic is covered offline in test_run_firm_pipeline.py.
"""

from __future__ import annotations

from functools import partial

from typer.testing import CliRunner

from pescraper import cli, db
from pescraper.cli import app
from pescraper.models import FirmRecord, FirmStatus

runner = CliRunner()


def _use_tmp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "pipeline.db"
    monkeypatch.setattr(db, "init_db", partial(db.init_db, db_path))
    return db_path


def test_help_lists_all_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("run", "run-firm", "export", "status", "doctor"):
        assert command in result.output
    # init-db is also registered
    assert "init-db" in result.output


def test_run_with_empty_queue_exits_zero(monkeypatch, tmp_path) -> None:
    _use_tmp_db(monkeypatch, tmp_path)
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 0
    assert "Processed 0 firm(s)" in result.output


def test_run_summary_flag_exits_zero(monkeypatch, tmp_path) -> None:
    _use_tmp_db(monkeypatch, tmp_path)
    result = runner.invoke(app, ["run", "--summary"])
    assert result.exit_code == 0
    assert "Firms by status" in result.output


def test_run_slug_invokes_pipeline_for_one_firm(monkeypatch, tmp_path) -> None:
    _use_tmp_db(monkeypatch, tmp_path)

    async def fake_pipeline(url: str) -> FirmRecord:
        return FirmRecord(firm_name="Acme", website=url, confidence=0.5, status=FirmStatus.COMPLETE)

    monkeypatch.setattr(cli, "run_firm_pipeline", fake_pipeline)
    result = runner.invoke(app, ["run", "--slug", "https://acme.example"])
    assert result.exit_code == 0
    assert "Acme" in result.output


def test_run_firm_invokes_pipeline_and_prints_summary(monkeypatch) -> None:
    async def fake_pipeline(url: str) -> FirmRecord:
        return FirmRecord(
            firm_name="Acme Capital",
            website=url,
            confidence=0.75,
            needs_review=False,
            status=FirmStatus.COMPLETE,
        )

    monkeypatch.setattr(cli, "run_firm_pipeline", fake_pipeline)

    result = runner.invoke(app, ["run-firm", "https://acme.example"])

    assert result.exit_code == 0
    assert "Acme Capital" in result.output
    assert "confidence=0.75" in result.output
    assert "needs_review=False" in result.output


def test_export_writes_csv_and_xlsx(monkeypatch, tmp_path) -> None:
    _use_tmp_db(monkeypatch, tmp_path)
    out = tmp_path / "out" / "firms"
    result = runner.invoke(app, ["export", "--out", str(out)])
    assert result.exit_code == 0
    assert out.with_suffix(".csv").exists()
    assert out.with_suffix(".xlsx").exists()


def test_status_exits_zero(monkeypatch, tmp_path) -> None:
    _use_tmp_db(monkeypatch, tmp_path)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Firms by status" in result.output


def test_firm_name_from_url_strips_www_and_tld() -> None:
    assert cli._firm_name_from_url("https://www.a-mcapital.com") == "A Mcapital"


def test_firm_name_from_url_handles_bare_host() -> None:
    assert cli._firm_name_from_url("https://acme.example/about") == "Acme"
