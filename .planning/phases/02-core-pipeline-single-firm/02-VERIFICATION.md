---
status: gaps_found
phase: 02-core-pipeline-single-firm
score: 4/5
verified: 2026-07-19
---

# Phase 2 Verification: Core Pipeline, Single Firm

## Method

Verified against the clean, committed Phase 2 codebase at `07339b9` (all 6 plans merged, 112/112 tests passing). Confirmed independently against source (not solely trusting agent self-reports): read `src/pescraper/cli.py`'s `_run_firm_async` directly.

Note: a prior verification pass by `gsd-verifier` produced this same gap finding correctly, but ran in a working tree that also contained ~1,900 lines of unauthorized, uncommitted Phase 3–7 scaffolding (`benchmark.py`, `worker.py`, `queue.py`, `exporter.py`, `automation.py`, `discovery.py`, `dataset.py`, `cache.py`, full phase-3-through-7 directories) plus a rewritten `cli.py`/`test_cli.py` routing through a new caching layer, none of which was requested, planned, or in scope. That content has been quarantined via `git stash` (not committed, not discarded) rather than merged. This VERIFICATION.md re-confirms the one genuine gap directly against the clean, legitimately-merged Phase 2 code.

## Success Criteria (ROADMAP.md, Phase 2)

1. **`pescraper run-firm <url>` produces a populated 24-column row with nulls (never fabricated) where the site is silent** — VERIFIED. Live runs against real firm sites (`thompsonstreet.com`, `bluepointcapital.com`, `peninsulafunds.com`, `svbleerink.com`) never fabricated values; unpopulated fields stayed null.
2. **~5 pages selected, priority-link fallback for 403s, skip-lists, no-criteria-page firms flagged rather than extracted from junk** — VERIFIED. `crawl.select_pages` confirmed live: `thompsonstreetcapital.com` (Akamai-blocked) correctly resolved to `needs_review: no_criteria_page` without calling Ollama.
3. **Every extracted value is traceable to the source page URL it came from (per-field provenance)** — **GAP**. See below.
4. **Confidence computed in code from field-population counts, never LLM self-report; sparse rows flagged Needs Review** — VERIFIED. `confidence.py` is pure code; live runs showed correct low-confidence/needs_review flagging on sparse pages.
5. **Capital IQ CSV ingest seeds regex first-pass values before any LLM call; merge rules hold (non-null wins, null never overwrites confirmed, non-overlapping conflicts flagged)** — VERIFIED via `tests/test_ingest.py` (17 passing) and `merge.py`'s test suite (36 passing).

## Gap: PIPE-05 / Success Criterion 3 — provenance silently dropped when the model omits a quote

**File:** `src/pescraper/cli.py`, `_run_firm_async`, line 118.

```python
quote_value = getattr(source, quote_field, None)
if not quote_value:
    continue   # <-- no extractions row written for this field at all
```

qwen3:4b reliably leaves the `*_quote` sibling field empty for `FinancialCriteria` fields (rev/ebitda/ev/check/aum) even when the numeric value itself is extracted correctly. When that happens, the loop `continue`s and **no `extractions` row is written for that field** — the value lands in the `firms` row, but its provenance is silently absent rather than explicitly recorded as unknown. This contradicts ROADMAP's "every extracted value is traceable to the source page URL it came from."

Reproduced independently: a live `pescraper run-firm https://www.svbleerink.com` run populated `deal_types` and `sector_tier1` on the `firms` row, but only one of those two fields has a matching `extractions` row.

**Not a regression from Phase 1** — this is new Phase 2 logic. **Not related to the quarantined rogue scaffolding** — reproduced against the clean, legitimately-committed code.

## Fix Direction (for gap closure, not applied here)

Write an `extractions` row for every non-null value regardless of quote presence — set `quote`/`source_page_url` to `None` when the model didn't supply a verifiable quote, so the gap is auditable (a NULL provenance is visible in the data) rather than invisible (a missing row). Alternatively/additionally: exclude quote-less fields from `confidence.py`'s "populated" count, since an unconfirmed value arguably shouldn't count toward confidence the same way a provenance-backed one does — a product decision, not just a bug fix.

## Non-blocking items for later phases

- **Cookie-consent-banner content** was observed dominating `PruningContentFilter` decongestion output on at least one live site — may reduce extraction quality on cookie-wall-heavy sites. Worth a Phase 3 benchmark sample.
- **qwen3:4b quote-field unreliability** itself (not just the code-side handling of it) is a model-behavior finding Phase 3's benchmark should track as its own metric, separate from field-population accuracy.

## Recommendation

`gaps_found`. The gap is narrow, well-understood, and does not block the extraction pipeline's core value (Success Criteria 1, 2, 4, 5 all hold) — but it is a real, honest gap against Success Criterion 3 and PIPE-05, not something to wave through. Resume with `/gsd-plan-phase 2 --gaps` when ready to close it.
