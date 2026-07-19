"""Tests for the pescraper CLI skeleton.

Proves the command surface and the stub exit-code contract via typer's CliRunner.
doctor and init-db are NOT invoked here: their target modules (pescraper.doctor /
pescraper.db) land in wave 2. This test only pins the skeleton.
"""

from __future__ import annotations

from typer.testing import CliRunner

from pescraper.cli import app

runner = CliRunner()


def test_help_lists_all_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("run", "run-firm", "export", "status", "doctor"):
        assert command in result.output
    # init-db is also registered
    assert "init-db" in result.output


def test_run_stub_exits_zero() -> None:
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 0


def test_run_firm_stub_exits_zero() -> None:
    result = runner.invoke(app, ["run-firm", "https://example.com"])
    assert result.exit_code == 0


def test_export_stub_exits_zero() -> None:
    result = runner.invoke(app, ["export"])
    assert result.exit_code == 0


def test_status_stub_exits_zero() -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
