---
phase: 01-environment-contract-foundation
plan: 02
subsystem: pipeline-state-contract
tags: [sqlite, wal, pydantic, schema, contract, lifecycle, staleness]
requires:
  - pescraper-package
  - pescraper-cli-entrypoint
provides:
  - pipeline-db-contract
  - firm-record-model
  - firm-status-lifecycle
  - staleness-query
affects:
  - src/pescraper/
  - data/pipeline.db
tech-stack:
  added: []
  patterns:
    - "db.py is the single module that writes SQL (inter-phase contract)"
    - "firms DDL generated from models.FIRM_COLUMNS — one source of truth for schema shape"
    - "WAL + busy_timeout=5000 + foreign_keys on every connection (concurrent-safe)"
    - "per-call commits for crash-safe row writes (no whole-file rewrite)"
    - "nullable-by-default extraction schema (PITFALLS Pitfall 1: no fabricated values)"
key-files:
  created:
    - src/pescraper/models.py
    - src/pescraper/db.py
    - tests/test_db.py
  modified:
    - .gitignore
decisions:
  - "firms uses implicit integer rowid PK + UNIQUE(website) as the natural key for upsert/lifecycle updates; the 24 named FIRM_COLUMNS are the schema contract."
  - "advance_status/stale_firms/upsert_firm implemented alongside the schema in the Task 2 db.py file (db.py is the single SQL module); Task 3 added their test coverage + gitignore rather than a second edit of the same new file."
  - "FirmStatus is a str Enum so it serializes to the bare status string in JSON and stores as TEXT in SQLite without adapters."
metrics:
  duration: 7m
  completed: 2026-07-19
  tasks: 3
  files: 4
status: complete
---

# Phase 1 Plan 02: SQLite Contract (pipeline.db) Summary

The SQLite source-of-truth contract: an idempotent WAL-mode initializer creating the five-table schema (jobs, firms, pages, extractions, cache) with the fixed 24-column firms table generated from a single pydantic `FirmRecord` model, plus a validated pending->in_progress->complete|needs_review lifecycle and a 90-day staleness query for re-queue.

## What Was Built

- **`src/pescraper/models.py`**: `FirmStatus` (str Enum: pending/in_progress/complete/needs_review) and `FirmRecord` (pydantic v2, 24 fields in schema order, all nullable-by-default except `firm_name`). `FIRM_COLUMNS` is the ordered tuple of the 24 field names — the single source of truth that `db.py` builds its firms DDL from and Phase 2 will feed to Ollama's `format` param. A module docstring maps each snake_case field to its display label (Firm Name ... Status). Nullable-by-default is deliberate per PITFALLS Pitfall 1 (schema pressure must not force a 4B model to fabricate mid-market ranges).
- **`src/pescraper/db.py`** (the only module that writes SQL, per ARCHITECTURE.md):
  - `DEFAULT_DB_PATH` from env `PESCRAPER_DB`, default `data/pipeline.db`.
  - `connect(path)` — `sqlite3.Row` factory + `journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON` on every connection.
  - `init_db(path)` — creates the parent dir, executes idempotent `CREATE TABLE IF NOT EXISTS` for all five tables, adds indexes on `firms(status)` and `firms(last_checked)`, returns the resolved Path. Second call is a no-op.
  - firms DDL generated from `FIRM_COLUMNS` with SQLite types (REAL for numerics, INTEGER for us_investments/needs_review, TEXT for text/status/last_checked), `UNIQUE(website)` as the natural key. Skeleton tables jobs/pages/extractions/cache exist now with the columns later phases extend.
  - `ALLOWED_TRANSITIONS` + `advance_status(conn, website, new_status)` — reads current status, validates the move, raises `ValueError` on a disallowed transition, commits per call.
  - `stale_firms(conn, days=90)` — returns websites where `last_checked IS NULL OR julianday('now') - julianday(last_checked) > days`.
  - `upsert_firm(conn, record)` — insert-or-replace by website from a `FirmRecord` (enum->value, bool->0/1), committed.
- **`tests/test_db.py`**: model/schema cases (Task 1), init/wal/tables/columns/pragma cases (Task 2), lifecycle-walk + disallowed-transition and staleness inclusion/exclusion cases (Task 3). Each db test uses `tmp_path` for an isolated DB file.
- **`.gitignore`**: appended a "Pipeline store" section ignoring `*.db`, `*.db-wal`, `*.db-shm`, `data/exports/` (existing rules preserved) — closes threat T-01-03 (Capital IQ-derived data never enters git).

## Files

Created: `src/pescraper/models.py`, `src/pescraper/db.py`, `tests/test_db.py`.
Modified: `.gitignore`.
Generated (gitignored): `data/pipeline.db` (+ WAL sidecars).

## Commits

| Task | Commit | Description |
| ---- | ------ | ----------- |
| 1 | 7d4f82b | feat(01-02): add FirmRecord model and 24-column contract (FIRM_COLUMNS) |
| 2 | c7a8b76 | feat(01-02): add idempotent init_db, WAL connect, five-table schema |
| 3 | 1b32f6f | feat(01-02): status lifecycle, 90-day staleness query, gitignore store |

## Verification Results

- Task 1 (`-k "model or schema"`) — RED (ModuleNotFoundError) then 3 passed.
- Task 2 (`-k "init or tables or wal or columns"`) — RED then 5 passed.
- `uv run python -c "from pescraper.db import init_db; print(init_db())"` — prints `...\data\pipeline.db`; second run identical (idempotent).
- `uv run pescraper init-db` — `Initialized pipeline database at: ...\data\pipeline.db` (the 01-01 lazy-import target is now functional).
- Task 3 / full `uv run pytest -q tests/test_db.py` — 10 passed.
- Full suite `uv run pytest -q tests/` — 19 passed.
- `git check-ignore data/pipeline.db data/pipeline.db-wal` — both ignored; `git status` shows no `*.db` staged.

## Deviations from Plan

**1. [Rule 3 - Cohesion] Lifecycle helpers implemented in the Task 2 db.py file, tested in Task 3**
- **Found during:** Task 2 (writing `db.py`).
- **Issue:** The plan scoped `advance_status`/`stale_firms`/`upsert_firm` and `ALLOWED_TRANSITIONS` as Task 3 additions to `db.py`. Because `db.py` is created whole in Task 2 and ARCHITECTURE.md mandates it be the single SQL-owning module, splitting these functions into a second edit of the same brand-new file added churn with no benefit.
- **Fix:** Included the lifecycle/staleness/upsert functions in the Task 2 `db.py` write; Task 3 delivered their dedicated test coverage (lifecycle walk + rejection, staleness inclusion/exclusion) and the `.gitignore` change. Every function is still test-gated; no behavior was skipped.
- **Files modified:** `src/pescraper/db.py` (Task 2 commit c7a8b76), `tests/test_db.py` (Task 3 commit 1b32f6f).

No other deviations — the schema, lifecycle, staleness, and gitignore all match the plan.

## Known Stubs

Skeleton tables `jobs`, `pages`, `extractions`, `cache` are created with the minimal columns the contract needs now; later phases (queue/worker, crawl, extract, cache) extend their columns. This is the plan's intent ("they must EXIST as part of the contract now"), not an accidental gap. Only the `firms` table is fully specified this phase.

## Self-Check: PASSED

Created files verified present on disk:
- FOUND: src/pescraper/models.py, src/pescraper/db.py, tests/test_db.py

Commits verified in git log:
- FOUND: 7d4f82b (Task 1)
- FOUND: c7a8b76 (Task 2)
- FOUND: 1b32f6f (Task 3)
