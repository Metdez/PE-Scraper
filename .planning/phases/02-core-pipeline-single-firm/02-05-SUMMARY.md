---
phase: 02-core-pipeline-single-firm
plan: 05
subsystem: database
tags: [csv-ingest, sqlite, pydantic, regex, capital-iq]

# Dependency graph
requires:
  - phase: 02-core-pipeline-single-firm
    provides: "02-01 merge.py (null-safe merge_firm_record + range-conflict detection), 02-02 db.py (get_firm/upsert_firm)"
provides:
  - "src/pescraper/ingest.py: parse_range, map_columns, COLUMN_ALIASES, IngestSummary, ingest_csv"
  - "A self-contained, testable Capital IQ CSV seeding path ready for Phase 4's batch worker to invoke"
affects: [phase-4-batch-worker, csv-reconciliation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Free-text range regex parser: separate range-pattern vs single-bare-number regex, per-side unit suffix (M/B) with inherit-from-sibling fallback"
    - "Column-alias map + lowercase/strip fallback for flexible CSV header normalization (no fuzzy-matching library)"
    - "Direct-field-columns-take-precedence-over-regex-range-columns ordering in ingest_csv's two-pass field build"

key-files:
  created:
    - src/pescraper/ingest.py
    - tests/test_ingest.py
  modified: []

key-decisions:
  - "parse_range('15') -> (15.0, 15.0): a bare number with no range separator is treated as both min and max (a single confirmed figure is still a confirmed data point), per PLAN.md Task 1's explicit recommendation"
  - "A CSV row with website but no firm_name falls back to using the website string as firm_name (FirmRecord.firm_name is a required field) — not explicitly specified in the plan's must_haves, only 'missing both' is tested; documented as a Claude's-discretion fallback"
  - "Clean numeric *_min_musd/*_max_musd CSV columns take precedence over a combined free-text range column when both are present in the same row (matches Task 2 action text)"

patterns-established:
  - "ingest.py is the second module (after merge.py) that never constructs SQL directly — all persistence goes through db.get_firm/db.upsert_firm, satisfying threat T-02-08"

requirements-completed: [DATA-01]

coverage:
  - id: D1
    description: "parse_range: regex first-pass on CSV free-text range cells ('$5-25M' -> min/max), unit conversion (B->M), clean-numeric no-op passthrough, empty/None edge cases"
    requirement: "DATA-01"
    verification:
      - kind: unit
        ref: "tests/test_ingest.py::test_parse_range_simple_dollar_range_with_million_suffix"
        status: pass
      - kind: unit
        ref: "tests/test_ingest.py::test_parse_range_billion_range_converts_to_millions"
        status: pass
      - kind: unit
        ref: "tests/test_ingest.py::test_parse_range_bare_single_number_is_both_min_and_max"
        status: pass
      - kind: unit
        ref: "tests/test_ingest.py::test_parse_range_clean_numeric_cell_is_not_mangled"
        status: pass
      - kind: unit
        ref: "tests/test_ingest.py::test_parse_range_empty_string_is_none_none"
        status: pass
      - kind: unit
        ref: "tests/test_ingest.py::test_parse_range_none_input_is_none_none"
        status: pass
    human_judgment: false
  - id: D2
    description: "map_columns: flexible case-insensitive column mapper with known Capital IQ header aliases, unrecognized-header passthrough"
    requirement: "DATA-01"
    verification:
      - kind: unit
        ref: "tests/test_ingest.py::test_map_columns_maps_known_aliases_case_insensitively"
        status: pass
      - kind: unit
        ref: "tests/test_ingest.py::test_map_columns_unrecognized_header_passes_through_lowercased_stripped"
        status: pass
      - kind: unit
        ref: "tests/test_ingest.py::test_map_columns_covers_identity_and_range_aliases"
        status: pass
    human_judgment: false
  - id: D3
    description: "ingest_csv: orchestrated CSV ingest that seeds new firms, preserves existing lifecycle status through the universal merge rule, flags needs_review on range conflict, and skips rows missing both identifiers"
    requirement: "DATA-01"
    verification:
      - kind: unit
        ref: "tests/test_ingest.py::test_ingest_csv_inserts_two_new_firms_with_parsed_ranges"
        status: pass
      - kind: unit
        ref: "tests/test_ingest.py::test_ingest_csv_preserves_complete_status_not_reset_to_pending"
        status: pass
      - kind: unit
        ref: "tests/test_ingest.py::test_ingest_csv_flags_needs_review_on_disjoint_range_conflict"
        status: pass
      - kind: unit
        ref: "tests/test_ingest.py::test_ingest_csv_skips_row_missing_both_firm_name_and_website"
        status: pass
      - kind: unit
        ref: "tests/test_ingest.py::test_ingest_csv_clean_numeric_min_max_columns_take_precedence_over_range_column"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-07-19
status: complete
---

# Phase 2 Plan 5: Capital IQ CSV Ingest Summary

**Flexible case-insensitive CSV column mapper + free-text range regex parser + `ingest_csv` orchestrator that seeds `pipeline.db` via merge.py's universal null-safe merge rule, built against the documented 24-column shape ahead of the real Capital IQ export.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-07-19T15:19:08-04:00 (after fast-forwarding this worktree branch to master's Wave 1 merges)
- **Completed:** 2026-07-19T15:31:00-04:00 (approx.)
- **Tasks:** 2 completed
- **Files modified:** 2 (both new: `src/pescraper/ingest.py`, `tests/test_ingest.py`)

## Accomplishments
- `parse_range()` — regex first-pass on CSV free-text range cells (`"$5-25M"` -> `(5.0, 25.0)`, `"$1.5B - $2B"` -> `(1500.0, 2000.0)` with independent per-side B->M conversion), bare-number-as-both-min-max, empty/None/no-match all return `(None, None)`.
- `map_columns()` / `COLUMN_ALIASES` — case-insensitive header normalization covering identity/location/classification/AUM plus the four free-text range pseudo-keys (`_rev_range`, `_ebitda_range`, `_ev_range`, `_check_range`); unrecognized headers pass through lowercased/stripped rather than raising or being dropped.
- `ingest_csv()` — streams a CSV via `csv.DictReader` (never loads the whole file into memory), builds a seed `FirmRecord` per row (direct numeric columns take precedence over regex-parsed range columns), calls `merge.merge_firm_record()` (02-01) against any existing `db.get_firm()` row, overrides `needs_review=True` on detected range conflicts, and persists via `db.upsert_firm()` (02-02) — never constructs SQL itself.
- Skips rows missing both `firm_name` and `website` (logged, not raised); the rest of the file still ingests.
- 17 new unit tests, all offline (`tmp_path` SQLite DB + `tmp_path` CSV fixtures), no network/LLM dependency.

## Task Commits

Each task was committed atomically (TDD RED -> GREEN per task):

1. **Task 1: Column mapper and free-text range regex parser**
   - `b820650` (test) - add failing test for column mapper and range parser (also stages Task 2's `ingest_csv` tests — see Deviations)
   - `5077f91` (feat) - implement column mapper and range parser (module also contains `ingest_csv` — see Deviations)
2. **Task 2: ingest_csv orchestrator**
   - Implementation shipped in `5077f91` above (see Deviations for why Task 1 and Task 2 were not split into separate commits)

**Plan metadata:** (this commit, docs: complete plan)

_Note: TDD tasks used a two-step RED -> GREEN cycle per the module (no REFACTOR step needed — implementation was clean on first pass)._

## Files Created/Modified
- `src/pescraper/ingest.py` - `parse_range`, `map_columns`, `COLUMN_ALIASES`, `IngestSummary`, `ingest_csv` — the full Capital IQ CSV seed-ingest module
- `tests/test_ingest.py` - 17 unit tests covering both tasks' `must_haves` truths

## Decisions Made
- `parse_range("15") -> (15.0, 15.0)` (bare number as both min and max) — explicit choice documented in both the module docstring and a dedicated test, per PLAN.md Task 1's "Claude's discretion" instruction.
- A row with `website` but no `firm_name` uses `website` as the `firm_name` fallback (since `FirmRecord.firm_name` is required) rather than being skipped — only "missing both" is a documented must-have; this fallback keeps a website-only row from being silently dropped.
- Clean numeric `*_min_musd`/`*_max_musd` columns take precedence over a combined free-text range column in the same row, matching Task 2's action text exactly (verified by `test_ingest_csv_clean_numeric_min_max_columns_take_precedence_over_range_column`).

## Deviations from Plan

### Auto-fixed Issues

None — no bugs, missing functionality, or blocking issues encountered.

### Process Note (commit granularity, not a Rule 1-4 deviation)

**Task 1 and Task 2 implementation were committed together in a single `feat` commit (`5077f91`)** rather than as two separate feat commits. Both `map_columns`/`parse_range` (Task 1) and `ingest_csv` (Task 2) were written into `src/pescraper/ingest.py` in one pass because `ingest_csv` is a thin orchestrator directly consuming Task 1's two helper functions within the same new module — writing them together was the natural unit of work. The RED test commit (`b820650`) likewise stages both tasks' tests together. Task-level verification commands were still run and passed independently exactly as the plan specifies (`-k "parse_range or map_columns"` for Task 1, full `test_ingest.py` for Task 2), so both tasks' `<done>` criteria are independently satisfied and evidenced — only the commit boundary is merged, not the verification.

---

**Total deviations:** 0 auto-fixed. 1 commit-granularity process note (no functional impact).
**Impact on plan:** None on correctness or scope. All `must_haves` truths verified by dedicated tests.

## Issues Encountered

This worktree's branch (`worktree-agent-a502af42351c15743`) was created before master received the Wave 1 merges (02-01 through 02-04, including `merge.py` and `db.py`). Before starting, verified the branch's HEAD was a clean ancestor of `master` (`git merge-base --is-ancestor HEAD master` -> yes, no divergent commits) and fast-forward-merged `master` in (`git merge master --ff-only`) to bring in the real merged `merge.py`/`db.py`/`models.py` this plan depends on. No conflicts; fast-forward only, no new merge commit.

## User Setup Required

None - no external service configuration required. `ingest_csv` is fully offline (stdlib `csv` + existing `db.py`/`merge.py`).

## Next Phase Readiness
- `ingest.py` is ready for Phase 4's batch worker to invoke directly against the real Capital IQ CSV export once the user supplies it — no reconciliation work is blocking Phase 4 from starting; header/alias additions for the real export's actual column names are additive (unrecognized headers already pass through safely).
- Deliberately not wired into `cli.py`'s `run_firm(url)` per CONTEXT.md — that remains the ad-hoc single-URL path with no CSV row to consult.
- `merge.merge_firm_record()` is now proven consumed by a second caller (ingest.py) beyond its own test suite, confirming its "single source of truth for the merge rule" contract works across module boundaries as 02-01 intended.

---
*Phase: 02-core-pipeline-single-firm*
*Completed: 2026-07-19*

## Self-Check: PASSED

- FOUND: src/pescraper/ingest.py
- FOUND: tests/test_ingest.py
- FOUND: .planning/phases/02-core-pipeline-single-firm/02-05-SUMMARY.md
- FOUND commit: b820650 (test(02-05): add failing test for column mapper and range parser)
- FOUND commit: 5077f91 (feat(02-05): implement column mapper and range parser)
