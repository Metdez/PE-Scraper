"""Tests for the Windows runtime hardening (research/PITFALLS.md Pitfall 8).

These lock down the two Windows seams: the asyncio Proactor event-loop policy
(Playwright subprocess support) and UTF-8 stdio (cp1252/charmap crash avoidance).
Importing ``pescraper`` triggers runtime configuration as a side effect.
"""

from __future__ import annotations

import asyncio
import sys

import pytest

import pescraper


def _normalize(encoding: str | None) -> str:
    return (encoding or "").lower().replace("-", "")


def test_python_version_at_least_311() -> None:
    assert sys.version_info >= (3, 11)


def test_stdout_is_utf8() -> None:
    assert _normalize(getattr(sys.stdout, "encoding", None)) == "utf8"


@pytest.mark.skipif(sys.platform != "win32", reason="Proactor policy is win32-only")
def test_proactor_policy_active_on_win32() -> None:
    policy = asyncio.get_event_loop_policy()
    assert isinstance(policy, asyncio.WindowsProactorEventLoopPolicy)


def test_configure_is_idempotent() -> None:
    first = pescraper.runtime.configure_windows_runtime()
    second = pescraper.runtime.configure_windows_runtime()
    assert first == second
    assert first["python_version"] == "%d.%d.%d" % sys.version_info[:3]
    assert _normalize(first["stdout_encoding"]) == "utf8"
    if sys.platform == "win32":
        assert first["event_loop_policy"] == "WindowsProactorEventLoopPolicy"


def test_crawl4ai_browser_kwargs_use_installed_edge_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(pescraper.runtime.sys, "platform", "win32")

    assert pescraper.runtime.crawl4ai_browser_kwargs() == {
        "headless": True,
        "chrome_channel": "msedge",
    }


def test_crawl4ai_browser_kwargs_keep_playwright_default_off_windows(monkeypatch) -> None:
    monkeypatch.setattr(pescraper.runtime.sys, "platform", "linux")

    assert pescraper.runtime.crawl4ai_browser_kwargs() == {"headless": True}
