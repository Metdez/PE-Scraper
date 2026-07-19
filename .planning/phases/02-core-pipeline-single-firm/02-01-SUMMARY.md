---
phase: 02-core-pipeline-single-firm
plan: 01
subsystem: business-rules
tags: [pydantic, pure-functions, difflib, merge-rules, confidence-scoring, provenance]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "FirmRecord/FIRM_COLUMNS (models.py), db.py extractions table schema"
provides:
  - "merge.py: merge_field/ranges_conflict/merge_firm_record — null-safe field merge and disjoint-range conflict detection"
  - "confidence.py: compute_confidence/is_needs_review — deterministic ratio-based confidence and needs_review threshold logic"
  - "provenance.py: find_source_page — quote-to-page string matching for source_page_url"
affects: [02-05-ingest, 02-06-integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure business-rule modules with zero I/O/LLM/crawl imports, independently unit-tested offline"
    - "quick_ratio() used as a cheap O(n) upper-bound prefilter, with the more accurate ratio() only computed for candidates that clear the prefilter — corrects quick_ratio's tendency to overestimate similarity for short, character-overlapping strings"

key-files:
  created:
    - src/pescraper/merge.py
    - src/pescraper/confidence.py
    - src/pescraper/provenance.py
    - tests/test_merge.py
    - tests/test_confidence.py
    - tests/test_provenance.py
  modified: []

key-decisions:
  - "provenance.find_source_page uses quick_ratio() only as a fast pre-filter (skip pages whose quick_ratio can't clear min_ratio, since quick_ratio is a guaranteed upper bound on the real ratio), then confirms candidates with the accurate ratio() before accepting a match — plain quick_ratio()-only matching (as the plan's <action> literally specified) produced false-positive matches on the plan's own worked 'unrelated text' example (quick_ratio=0.615 >= 0.6 threshold for two genuinely unrelated short strings), which would have violated the plan's own <behavior> spec and the must_haves truth about unverified quotes returning None"

patterns-established:
  - "Pattern: business-rule modules import only pescraper.models (never db/crawl/ollama) — keeps them independently testable and safe to reuse from both ingest.py and cli.py without pulling in I/O"

requirements-completed: [DATA-04, PIPE-04, PIPE-05]

coverage:
  - id: D1
    description: "merge.py — merge_field never lets null clear a confirmed value; non-null new always wins; merge_firm_record copies lifecycle fields unchanged and flags disjoint-range conflicts per field pair"
    requirement: "DATA-04"
    verification:
      - kind: unit
        ref: "tests/test_merge.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "confidence.py — compute_confidence is a deterministic populated/populatable ratio excluding fund_name/last_deal/lifecycle fields; is_needs_review combines the <0.3 threshold and zero-core-numerics OR-condition"
    requirement: "PIPE-04"
    verification:
      - kind: unit
        ref: "tests/test_confidence.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "provenance.py — find_source_page returns None for null/empty/unmatched quotes, exact-substring fast path for verbatim matches, and the best-confirmed fuzzy match across multiple pages otherwise"
    requirement: "PIPE-05"
    verification:
      - kind: unit
        ref: "tests/test_provenance.py"
        status: pass
    human_judgment: false

# Metrics
duration: 14min
completed: 2026-07-19
status: complete
---

# Phase 2 Plan 1: Business Rules (merge/confidence/provenance) Summary

**Three pure-function modules — null-safe field merge with disjoint-range conflict detection, ratio-based confidence scoring with a dual-condition needs_review threshold, and quote-to-page provenance matching hardened against quick_ratio's false-positive overestimation — all offline-tested with zero I/O/LLM/crawl4ai dependencies.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-07-19T19:00:00Z (approx, first commit c7b2dc6)
- **Completed:** 2026-07-19T19:14:32Z
- **Tasks:** 3
- **Files modified:** 6 (3 source, 3 test)

## Accomplishments
- `merge.py` implements the universal null-safe merge rule (`merge_field`) and disjoint-only range-conflict detection (`ranges_conflict`), composed into `merge_firm_record` which copies lifecycle fields (status/confidence/needs_review/last_checked) unchanged from `existing` and returns a conflicts list for the four numeric range pairs
- `confidence.py` implements a deterministic 17-field populated/populatable ratio (`compute_confidence`) excluding `fund_name`/`last_deal`/lifecycle fields from the denominator, and `is_needs_review` combining the `<0.3` threshold with an independent zero-core-numerics OR-condition
- `provenance.py` implements `find_source_page` with an exact-substring fast path and a two-stage fuzzy match (cheap `quick_ratio()` prefilter, confirmed by accurate `ratio()`) that correctly returns `None` for genuinely unrelated quotes instead of a false-positive match
- All three modules import only `pescraper.models` — zero sqlite3/ollama/crawl4ai imports, verified by the module contents themselves and by the full offline test suite passing with no network/DB fixtures

## Task Commits

Each task followed the RED → GREEN TDD cycle with atomic commits:

1. **Task 1: merge.py** — test: `c7b2dc6`, feat: `355583d`
2. **Task 2: confidence.py** — test: `ef707eb`, feat: `2b51d60`
3. **Task 3: provenance.py** — test: `799fd30`, feat: `9b5f8bc`

**Plan metadata:** (pending — final docs commit follows this SUMMARY)

_Note: no refactor commits were needed — implementations passed on first GREEN attempt except provenance.py's quick_ratio fix, folded into its single feat commit before that commit was made (test stayed RED against the corrected implementation until it passed)._

## Files Created/Modified
- `src/pescraper/merge.py` - `merge_field`, `ranges_conflict`, `merge_firm_record`, `LIFECYCLE_FIELDS`, `RANGE_FIELD_PAIRS`
- `src/pescraper/confidence.py` - `compute_confidence`, `is_needs_review`, `POPULATABLE_FIELDS`, `CORE_NUMERIC_FIELDS`, `NEEDS_REVIEW_THRESHOLD`
- `src/pescraper/provenance.py` - `find_source_page`
- `tests/test_merge.py` - 21 tests: null-safe merge, disjoint/overlap/nested/boundary/missing-data range conflicts, lifecycle pass-through, brand-new-firm pass-through
- `tests/test_confidence.py` - 9 tests: constants shape, zero/full/half ratio, fund_name/last_deal exclusion, both is_needs_review OR-branches independently
- `tests/test_provenance.py` - 6 tests: None/empty quote, exact substring, below-threshold no-match, multi-page best-match, empty pages dict

## Decisions Made
- **quick_ratio() as prefilter, not final decision:** the plan's `<action>` block specified matching purely on `SequenceMatcher.quick_ratio()` with `min_ratio=0.6`. Verified live against the plan's own worked "unrelated text" example, this produced a false-positive match (`quick_ratio=0.615 >= 0.6` for two strings sharing no real semantic content — `quick_ratio()` is a fast character-histogram upper bound, not a true similarity measure, and overestimates for short strings with common letter distributions). Fixed by using `quick_ratio()` only to cheaply reject pages that cannot possibly clear the threshold (a guaranteed-safe pruning step, since `quick_ratio() >= ratio()` always), then confirming any surviving candidate with the accurate `ratio()` before accepting it as a match. This preserves the threat model's stated DoS mitigation intent (most non-matching pages are still rejected via the cheap O(n) quick_ratio path) while satisfying the plan's own `<behavior>` spec and the must-haves truth that unverified quotes return `None` rather than a guessed URL.
- All other implementation matched the plan's `<action>` blocks exactly (constants, function signatures, formulas) with no other deviations.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] provenance.find_source_page: quick_ratio()-only matching produced a false positive on the plan's own worked example**
- **Found during:** Task 3 (provenance.py implementation, GREEN phase)
- **Issue:** Implementing exactly per the plan's `<action>` (bare `quick_ratio()` compared against `min_ratio=0.6`) caused `test_find_source_page_no_match_below_threshold_returns_none` to fail — the plan's own example ("totally unrelated text not on any page" vs. "some other content entirely") scores `quick_ratio=0.615`, above the 0.6 threshold, contradicting the plan's `<behavior>` spec that this exact case must return `None`.
- **Fix:** Added a two-stage match: `quick_ratio()` is used only to cheaply reject candidates that cannot possibly clear `min_ratio` (a mathematically safe prune, since `quick_ratio() >= ratio()` always holds), then the accurate `ratio()` is computed only for pages that survive the prefilter, and that confirmed ratio decides the final match.
- **Files modified:** `src/pescraper/provenance.py`
- **Verification:** `uv run pytest tests/test_provenance.py -q` — all 6 tests pass, including the previously-failing no-match case and the multi-page best-match case
- **Committed in:** `9b5f8bc` (Task 3 feat commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Necessary for correctness — without the fix, `find_source_page` would return false-positive `source_page_url` values for extraction quotes that don't actually appear on any fetched page, directly contradicting this plan's must_haves truth ("a quote that doesn't string-match any fetched page's text returns None"). No scope creep; the fix stayed within `provenance.py`'s single function.

## Issues Encountered
None beyond the deviation documented above.

## User Setup Required
None - no external service configuration required. All three modules are pure Python stdlib + pydantic, no new dependencies, no environment variables.

## Next Phase Readiness
- `merge.merge_firm_record`, `confidence.compute_confidence`/`is_needs_review`, and `provenance.find_source_page` are importable and fully unit-tested, ready to be consumed by `ingest.py` (02-05) and `cli.py`'s `run_firm()` (02-06) exactly per this plan's `key_links`.
- No blockers. Full repo test suite (62 tests across all modules) passes offline with no network/Ollama/crawl4ai touched by this plan's tests.

---
*Phase: 02-core-pipeline-single-firm*
*Completed: 2026-07-19*

## Self-Check: PASSED

All 7 created files verified present on disk; all 6 task commit hashes verified present in `git log --oneline --all`.
