---
phase: 01-environment-contract-foundation
plan: 01
subsystem: pipeline-foundation
tags: [python, uv, typer, cli, windows-runtime, asyncio, utf-8]
requires: []
provides:
  - pescraper-package
  - pescraper-cli-entrypoint
  - windows-runtime-hardening
affects:
  - src/pescraper/
tech-stack:
  added:
    - crawl4ai==0.9.2
    - ollama>=0.4
    - pydantic>=2,<3
    - typer>=0.12
    - httpx>=0.27
    - tenacity>=9
    - python-dotenv>=1
    - openpyxl>=3.1
    - pytest>=8 (dev)
  patterns:
    - "src/ layout with hatchling wheel packaging"
    - "uv-managed venv + committed uv.lock for reproducible installs"
    - "import-time Windows runtime hardening (Proactor + UTF-8) in package __init__"
    - "lazy imports in CLI commands to decouple entrypoint from not-yet-built modules"
key-files:
  created:
    - pyproject.toml
    - .python-version
    - uv.lock
    - src/pescraper/__init__.py
    - src/pescraper/runtime.py
    - src/pescraper/cli.py
    - tests/test_runtime.py
    - tests/test_cli.py
  modified: []
decisions:
  - "Committed uv.lock (per threat T-01-SC) so PyPI installs are reproducible and pinned."
  - "Guarded reconfigure() with try/except so pytest's captured/non-reconfigurable streams don't crash runtime init."
  - "Proactor policy only set when the active policy is not already Proactor, so we never fight another library that already set it (T-01-01)."
metrics:
  duration: 5m
  completed: 2026-07-19
  tasks: 3
  files: 8
status: complete
---

# Phase 1 Plan 01: Windows-Native Package Skeleton Summary

Installable `pescraper` uv package with import-time Windows runtime hardening (asyncio Proactor event-loop policy + UTF-8 stdio) and a runnable typer CLI exposing six commands (run, run-firm, export, status, doctor, init-db), all covered by green runtime and CLI tests.

## What Was Built

- **uv-managed project** (`pyproject.toml`, `.python-version`, `uv.lock`): hatchling build backend, `requires-python = ">=3.11,<3.13"`, dependencies pinned per STACK.md, `[project.scripts] pescraper = "pescraper.cli:app"`, and a dev group with pytest. `uv sync` provisions a Windows venv; `crawl4ai-setup` installed the Playwright Chromium headless shell for the wave-2 smoke test.
- **`src/pescraper/runtime.py`**: idempotent `configure_windows_runtime()` — on win32 sets `WindowsProactorEventLoopPolicy` only if not already active; forces UTF-8 by reconfiguring stdout/stderr (`errors="replace"`) and setting `PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8`; returns a diagnostics dict. Safe on non-win32 and safe to call repeatedly.
- **`src/pescraper/__init__.py`**: calls `configure_windows_runtime()` at import time so every consumer inherits the hardened runtime; exposes `__version__ = "0.1.0"`.
- **`src/pescraper/cli.py`**: typer `app` (`no_args_is_help=True`) with `run`, `run-firm <url>`, `export`, `status` stubs (exit 0), plus `doctor` and `init-db` that lazily import `pescraper.doctor` / `pescraper.db` inside their function bodies so `--help` and every stub work before those wave-2 modules exist.
- **Tests**: `tests/test_runtime.py` (Python>=3.11, UTF-8 stdout, win32 Proactor policy, idempotency) and `tests/test_cli.py` (command surface + stub exit codes via `CliRunner`).

## Files

Created: `pyproject.toml`, `.python-version`, `uv.lock`, `src/pescraper/__init__.py`, `src/pescraper/runtime.py`, `src/pescraper/cli.py`, `tests/test_runtime.py`, `tests/test_cli.py`.

## Commits

| Task | Commit | Description |
| ---- | ------ | ----------- |
| 1 | 7869ffe | feat(01-01): scaffold uv project with Windows runtime hardening |
| 2 | 3b9051c | feat(01-01): add typer CLI skeleton with six commands |
| 3 | e017e6b | test(01-01): add runtime and CLI skeleton tests |

## Verification Results

- `uv sync` — succeeded; Windows uv-managed venv created with pinned deps.
- Runtime import assertion (Task 1 verify) — `OK {'platform': 'win32', 'python_version': '3.11.15', 'event_loop_policy': 'WindowsProactorEventLoopPolicy', 'stdout_encoding': 'utf-8', 'pythonutf8': '1'}`.
- `uv run crawl4ai-setup` — completed; Chromium headless shell v1228 installed.
- `uv run pescraper --help` — lists run, run-firm, export, status, doctor, init-db.
- Stubs `run` / `run-firm https://example.com` / `export` / `status` — each exit 0.
- `uv run pytest -q tests/` — 9 passed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Guarded stdio `reconfigure()` against non-reconfigurable streams**
- **Found during:** Task 1 (writing `runtime.py`, anticipating pytest capture).
- **Issue:** Under pytest capture (and in some redirected-stdio contexts) `sys.stdout`/`sys.stderr` may be a wrapper without a working `reconfigure`, or raise `ValueError`/`OSError`. An unguarded call would crash runtime init on every package import in the test suite.
- **Fix:** Wrapped `reconfigure(...)` in a `try/except (ValueError, OSError)` and a `callable()` check; UTF-8 env vars are still set regardless.
- **Files modified:** `src/pescraper/runtime.py`
- **Commit:** 7869ffe

All other work executed exactly as written.

## Known Stubs

The following are intentional Phase 1 skeleton stubs (documented in the plan; real behavior lands in later phases):

| Stub | File | Reason / Resolution |
| ---- | ---- | ------------------- |
| `run`, `run-firm`, `export`, `status` echo a "Phase 1 skeleton" message | `src/pescraper/cli.py` | Command surface established now; pipeline behavior arrives in Phase 2+ (crawl/extract/export/queue phases). |
| `doctor` lazily imports `pescraper.doctor` | `src/pescraper/cli.py` | `pescraper.doctor` module lands in wave 2 (smoke-test plan). Lazy import keeps `--help`/stubs working now. |
| `init-db` lazily imports `pescraper.db` | `src/pescraper/cli.py` | `pescraper.db` module lands in wave 2 (SQLite contract plan). Lazy import keeps `--help`/stubs working now. |

These are the exact wave-2 seams the plan's `key_links` call out — not accidental gaps.

## Self-Check: PASSED

Created files verified present on disk:
- FOUND: pyproject.toml, .python-version, uv.lock
- FOUND: src/pescraper/__init__.py, src/pescraper/runtime.py, src/pescraper/cli.py
- FOUND: tests/test_runtime.py, tests/test_cli.py

Commits verified in git log:
- FOUND: 7869ffe (Task 1)
- FOUND: 3b9051c (Task 2)
- FOUND: e017e6b (Task 3)
