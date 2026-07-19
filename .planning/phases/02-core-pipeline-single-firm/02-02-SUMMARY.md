---
phase: 02-core-pipeline-single-firm
plan: 02
subsystem: database
tags: [sqlite, pydantic, provenance, db.py]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "pescraper.db (connect/init_db/upsert_firm/advance_status/stale_firms), pescraper.models (FirmRecord/FIRM_COLUMNS/FirmStatus), the extractions skeleton table"
provides:
  - "get_firm(conn, website) -> FirmRecord | None — read a full firm row back out, with status/needs_review type coercion"
  - "insert_extraction(conn, ...) -> None — append-only per-field provenance row into the extractions table"
affects: [02-05 ingest.py (calls get_firm before seeding), 02-06 cli.py run_firm (calls get_firm before merge, insert_extraction per extracted field)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Read-path type coercion mirrors upsert_firm's write-path coercion: status TEXT <-> FirmStatus, needs_review INTEGER 0/1 <-> bool"
    - "insert_extraction follows upsert_firm's named-placeholder (:name) parameterization style, never string-formats caller values into SQL"
    - "extractions table is an append-only log (INSERT only, no upsert) — one row per extraction run per field, distinct from firms' INSERT OR REPLACE upsert semantics"

key-files:
  created: []
  modified:
    - src/pescraper/db.py
    - tests/test_db.py

key-decisions:
  - "get_firm builds the FirmRecord from dict(row) after coercing status/needs_review, rather than hand-listing all 24 fields, so it stays in sync with FIRM_COLUMNS automatically"
  - "insert_extraction takes all fields as required keyword-only args (value/quote/source_page_url/content_hash individually nullable) rather than accepting a partial dict, matching the plan's explicit signature"

patterns-established:
  - "Read helpers for firms table live in db.py alongside write helpers (get_firm next to upsert_firm) — single-module-owns-SQL convention preserved"

requirements-completed: [PIPE-05]

coverage:
  - id: D1
    description: "get_firm(conn, website) reads a full FirmRecord back by website, returning None when no row exists and correctly coercing status/needs_review on a hit"
    requirement: "PIPE-05"
    verification:
      - kind: unit
        ref: "tests/test_db.py#test_get_firm_returns_none_for_missing_website"
        status: pass
      - kind: unit
        ref: "tests/test_db.py#test_get_firm_round_trips_fully_populated_record"
        status: pass
      - kind: unit
        ref: "tests/test_db.py#test_get_firm_round_trips_minimal_record_nulls_stay_none"
        status: pass
    human_judgment: false
  - id: D2
    description: "insert_extraction(conn, ...) appends one parameterized, append-only provenance row per call to the extractions table, tolerating None source_page_url/quote/value/content_hash"
    requirement: "PIPE-05"
    verification:
      - kind: unit
        ref: "tests/test_db.py#test_insert_extraction_adds_one_row_with_matching_columns"
        status: pass
      - kind: unit
        ref: "tests/test_db.py#test_insert_extraction_allows_null_source_page_url_and_quote"
        status: pass
      - kind: unit
        ref: "tests/test_db.py#test_insert_extraction_is_append_only_not_upsert"
        status: pass
      - kind: unit
        ref: "tests/test_db.py#test_insert_extraction_sql_metacharacter_values_round_trip_as_data"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-07-19
status: complete
---

# Phase 02 Plan 02: db.py get_firm / insert_extraction Summary

**Added `get_firm()` (parameterized read-by-website with FirmStatus/bool coercion) and `insert_extraction()` (append-only parameterized provenance-row writer) to `pescraper/db.py`, both TDD'd against a tmp_path SQLite file including a SQL-injection-metacharacter regression test.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-19T19:09:46Z
- **Completed:** 2026-07-19T19:14:20Z
- **Tasks:** 2 completed
- **Files modified:** 2 (src/pescraper/db.py, tests/test_db.py)

## Accomplishments
- `get_firm(conn, website)` round-trips a `FirmRecord` byte/field-equivalent to what was upserted, including correct `FirmStatus` enum and `needs_review` bool coercion, and returns `None` for a missing website
- `insert_extraction(conn, ...)` writes exactly one committed, parameterized row per call into the existing `extractions` table, tolerating `None` for `source_page_url`/`quote`/`value`/`content_hash`, and never overwrites — repeated calls append
- Added a dedicated SQL-metacharacter regression test (`'`, `;`, `--` payloads) proving both `firms` and `extractions` tables survive intact and the malicious strings round-trip as inert data, satisfying threat T-02-03's mitigation requirement

## Task Commits

Each task followed the plan's RED -> GREEN TDD cycle with two commits apiece:

1. **Task 1: get_firm** - `47c37ed` (test, RED) -> `878be73` (feat, GREEN)
2. **Task 2: insert_extraction** - `0533794` (test, RED) -> `20d5597` (feat, GREEN)

**Plan metadata:** (this commit, to follow)

## Files Created/Modified
- `src/pescraper/db.py` - Added `get_firm()` and `insert_extraction()`, plus a `datetime`/`timezone` stdlib import for `created_at` timestamps; both added to `__all__`
- `tests/test_db.py` - Added 7 new test cases (3 for `get_firm`, 4 for `insert_extraction`, including the SQL-metacharacter round-trip case)

## Decisions Made
- `get_firm` constructs the `FirmRecord` via `FirmRecord(**dict(row))` after coercing `status`/`needs_review`, rather than manually listing all 24 fields — keeps it automatically in sync with `FIRM_COLUMNS`/`FirmRecord` if either changes later.
- Both functions follow `upsert_firm`'s existing named-placeholder (`:name`) parameterization convention for consistency across `db.py`, rather than introducing `?`-style positional placeholders for the new code.

## Deviations from Plan

None - plan executed exactly as written. Both tasks matched their `<action>`/`<behavior>` specs precisely; no architectural changes, no missing critical functionality found, no blocking issues encountered.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `get_firm` and `insert_extraction` are both importable from `pescraper.db` and fully unit-tested (17/17 tests passing in `tests/test_db.py`, including Phase 1's existing lifecycle/staleness suite with no regressions)
- Ready for 02-05 (`ingest.py`, calls `get_firm` before seeding a row) and 02-06 (`cli.py`'s `run_firm()`, calls `get_firm` before merging and `insert_extraction` once per extracted field) to build on directly
- No blockers or concerns

---
*Phase: 02-core-pipeline-single-firm*
*Completed: 2026-07-19*

## Self-Check: PASSED

- FOUND: src/pescraper/db.py
- FOUND: tests/test_db.py
- FOUND: .planning/phases/02-core-pipeline-single-firm/02-02-SUMMARY.md
- FOUND commit: 47c37ed
- FOUND commit: 878be73
- FOUND commit: 0533794
- FOUND commit: 20d5597
