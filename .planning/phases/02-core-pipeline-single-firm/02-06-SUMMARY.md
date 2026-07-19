---
phase: 02-core-pipeline-single-firm
plan: 06
status: complete
---

# 02-06 Summary: cli.py integration — run-firm end-to-end

**Note:** no `02-06-PLAN.md` exists (see 02-04-SUMMARY.md — GSD framework unavailable this session); built directly from `02-CONTEXT.md`'s Phase Boundary and Integration Points sections, wiring together every module from 02-01 through 02-05.

- `run_firm_pipeline(url) -> FirmRecord` (async, in `cli.py`) — the orchestration core, factored out from the typer command so it's directly unit-testable: `crawl.select_pages` -> (if empty) flag `needs_review` with confidence recomputed from the *merged* record, not hardcoded to 0 (so a transient blocked re-crawl never wipes a previously confirmed firm's real confidence) -> (if non-empty) `extract.extract` -> build a candidate `FirmRecord` from the two extraction schemas -> `merge.merge_firm_record` against any existing row -> `confidence.compute_confidence`/`is_needs_review` (OR'd with merge conflicts) -> `db.upsert_firm` -> per-field `provenance.find_source_page` + `db.insert_extraction` for every populated quote-tracked field (financial fields, `deal_types`, `sector_tier1`).
- `_firm_name_from_url(url)` derives a placeholder firm name from the hostname — code-derived, never trusted from the model; the ad-hoc `run-firm <url>` path has no CSV row to seed a real name from, and extraction is intentionally never trusted for identity, only criteria fields.
- `run-firm` typer command is now a thin sync wrapper: `asyncio.run(run_firm_pipeline(url))` + a one-line summary echo.

9 new tests: 2 CLI-wiring tests in `test_cli.py` (monkeypatching `run_firm_pipeline` itself, per the "thin CLI, tested orchestration separately" split), 3 full-orchestration tests in `test_run_firm_pipeline.py` (mocking `crawl.select_pages`/`extract.extract`, exercising a real tmp_path SQLite db) — covering the no-pages/needs_review path, the happy path (persisted row + provenance rows with correct `source_page_url`/`quote`), and the critical re-check case (a blocked re-crawl must not lose a previously confirmed `ebitda_min_musd`).

**Manual live verification** (RESEARCH.md's required manual step, not part of the automated gate): ran `pescraper run-firm` against 3 real PE firms (a-mcapital.com, aeroequity.com, agellus.com). All completed without crashing; nulls-not-fabrication held throughout (sparse rows, not wrong ones); see 02-03-SUMMARY.md for the page-selection tuning fix this surfaced and fixed live.

## Phase 2 exit check (against ROADMAP.md's 5 success criteria)

1. ✅ `run-firm <url>` produces a populated row with nulls, never fabricated values — verified live and offline.
2. ✅ ~5 pages max, skip-list, 403/well-known-path fallback, no-criteria-page flagged — implemented, tested, live-tuned.
3. ✅ Every extracted value traceable to its source page — `find_source_page` + `insert_extraction`, verified offline with real quote/page matching.
4. ✅ Confidence computed in code (never LLM self-report); sparse rows flagged `needs_review` — implemented, tested both directions (ratio threshold and zero-core-numerics).
5. ✅ CSV ingest regex-parses free-text ranges; merge rules hold (non-null wins, null never overwrites, conflicts flagged) — implemented and tested; not yet wired to a CLI command (Phase 4's job) and not yet reconciled against the real Capital IQ export (deferred, not blocking, per CONTEXT.md).

Full suite: 99/99 passing (`uv run pytest -q`).
