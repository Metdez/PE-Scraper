---
phase: 02-core-pipeline-single-firm
plan: 03
subsystem: pipeline
tags: [crawl4ai, adaptive-crawler, fit-markdown, decongestion, tenacity, pytest]

requires:
  - phase: 01-foundation
    provides: "pescraper package skeleton (runtime hardening, doctor.py's crawl4ai/ollama round-trip proof, pyproject deps already pinned)"
provides:
  - "pescraper.decongest.decongest(cleaned_html, base_url) -> fit_markdown (manual PruningContentFilter pass, never raises)"
  - "pescraper.decongest.content_hash(text) -> sha256 hexdigest"
  - "pescraper.crawl.select_pages(url) -> dict[str, str] (async, adaptive page selection + skip-list + 403 fallback, never raises)"
affects: ["02-04 (extraction)", "02-06 (cli.py run_firm integration)"]

tech-stack:
  added: []
  patterns:
    - "Manual DefaultMarkdownGenerator(PruningContentFilter) pass against CrawlResult.cleaned_html — AdaptiveCrawler.get_relevant_content() returns raw_markdown, not fit_markdown, on crawl4ai 0.9.2"
    - "tenacity.retry(reraise=False) around AdaptiveCrawler.digest() so one transient network blip does not kill a firm's whole run"
    - "select_pages never raises; empty dict IS the caller's no_criteria_page signal (no dedicated exception type)"
    - "Offline TDD via monkeypatched AsyncWebCrawler/AdaptiveCrawler factories (asyncio.run() inside plain def test functions, no pytest-asyncio)"

key-files:
  created:
    - src/pescraper/decongest.py
    - src/pescraper/crawl.py
    - tests/test_decongest.py
    - tests/test_crawl.py
  modified: []

key-decisions:
  - "decongest.py imports crawl4ai eagerly at module top (not lazy) — it is an internal pipeline module, not a CLI command body; the lazy-import convention in cli.py applies only to CLI surfaces"
  - "AdaptiveConfig tuned to confidence_threshold=0.5, max_pages=5, top_k_links=3, strategy=statistical per RESEARCH.md's Open Question 3 recommendation"
  - "select_pages opens exactly one AsyncWebCrawler async context per firm, reused for both the adaptive digest and any well-known-path fallback fetches"

patterns-established:
  - "Pattern: pipeline modules that only transform already-fetched data (decongest.py) test offline against real local fixtures; modules that own network/browser calls (crawl.py) test offline against monkeypatched factory classes matching the real library's shape"

requirements-completed: [PIPE-01, PIPE-02]

coverage:
  - id: D1
    description: "decongest.decongest() manually runs DefaultMarkdownGenerator(PruningContentFilter(threshold=0.48)) against cleaned_html and returns fit_markdown, never raising on empty/malformed input"
    requirement: "PIPE-02"
    verification:
      - kind: unit
        ref: "tests/test_decongest.py::test_decongest_returns_nonempty_transformed_string"
        status: pass
      - kind: unit
        ref: "tests/test_decongest.py::test_decongest_empty_input_never_raises"
        status: pass
    human_judgment: false
  - id: D2
    description: "content_hash() is a deterministic, input-sensitive sha256 hexdigest"
    requirement: "PIPE-02"
    verification:
      - kind: unit
        ref: "tests/test_decongest.py::test_content_hash_is_64_char_lowercase_hex"
        status: pass
      - kind: unit
        ref: "tests/test_decongest.py::test_content_hash_deterministic_and_input_sensitive"
        status: pass
    human_judgment: false
  - id: D3
    description: "select_pages() excludes skip-listed URLs (team/portfolio/news/press/blog/insights/careers/legal/privacy/terms) from AdaptiveCrawler results"
    requirement: "PIPE-01"
    verification:
      - kind: unit
        ref: "tests/test_crawl.py::test_select_pages_excludes_skip_listed_urls"
        status: pass
    human_judgment: false
  - id: D4
    description: "select_pages() falls back to WELL_KNOWN_PATHS (/about, /investment-criteria, /strategy, /approach) when zero pages clear the relevance/skip-list filter, keeping only successful non-empty fetches"
    requirement: "PIPE-01"
    verification:
      - kind: unit
        ref: "tests/test_crawl.py::test_select_pages_falls_back_to_well_known_paths"
        status: pass
    human_judgment: false
  - id: D5
    description: "select_pages() never raises even on total digest+fallback failure (e.g. 403/blocked everywhere); returns {} as the no_criteria_page signal"
    requirement: "PIPE-01"
    verification:
      - kind: unit
        ref: "tests/test_crawl.py::test_select_pages_total_failure_returns_empty_dict_without_raising"
        status: pass
    human_judgment: false
  - id: D6
    description: "Every page select_pages() returns has passed through decongest.decongest() (proven via marker-function substitution), never raw markdown"
    requirement: "PIPE-02"
    verification:
      - kind: unit
        ref: "tests/test_crawl.py::test_select_pages_content_is_always_decongested"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-07-19
status: complete
---

# Phase 2 Plan 3: Crawl + Decongest Summary

**Manual `DefaultMarkdownGenerator(PruningContentFilter)` decongestion pass plus `AdaptiveCrawler`-based page selection with skip-lists and a well-known-path 403 fallback, both offline-unit-tested against crawl4ai 0.9.2's actual (not documented) behavior.**

## Performance

- **Duration:** ~5 min (commit span 15:11:59Z → 15:15:06Z)
- **Started:** 2026-07-19T15:11:59-04:00
- **Completed:** 2026-07-19T15:15:06-04:00
- **Tasks:** 2 completed (both TDD: RED + GREEN each)
- **Files modified:** 4 (2 created source, 2 created test)

## Accomplishments
- `pescraper/decongest.py` — `decongest(cleaned_html, base_url)` runs the manual `DefaultMarkdownGenerator(content_filter=PruningContentFilter(threshold=0.48, threshold_type="fixed"))` pass RESEARCH.md's live verification proved is required (AdaptiveCrawler does not decongest on its own on crawl4ai 0.9.2); `content_hash(text)` is a deterministic sha256 hexdigest for the future crawl-cache seam.
- `pescraper/crawl.py` — `select_pages(url)` runs one `AsyncWebCrawler` async context per firm, drives `AdaptiveCrawler.digest()` (retried via `tenacity` on transient failures), filters `get_relevant_content()` results against `SKIP_KEYWORDS` and a zero/negative relevance score, decongests every survivor's `cleaned_html`, and falls back to `WELL_KNOWN_PATHS` (`/about`, `/investment-criteria`, `/strategy`, `/approach`) fetched via the same crawler when nothing survives. Never raises; returns `{}` on total failure.
- Both modules are fully unit-tested offline: `decongest.py` against real local HTML strings run through the real crawl4ai markdown generator; `crawl.py` against monkeypatched `AsyncWebCrawler`/`AdaptiveCrawler` fake classes matching the real library's async contract shape, with a marker `decongest` substitution proving the decongestion pass-through.

## Task Commits

Each task followed the RED → GREEN TDD cycle:

1. **Task 1: decongest.py** — `26f2ba2` (test: RED, decongest/content_hash raise `NotImplementedError`) → `4c5a911` (feat: GREEN, real implementation)
2. **Task 2: crawl.py** — `f95cb7a` (test: RED, `select_pages` raises `NotImplementedError` / references undefined `AsyncWebCrawler`) → `e0f2e14` (feat: GREEN, real implementation)

No plan-metadata commit was created for this SUMMARY per the invoking instruction (STATE.md/ROADMAP.md updates and the final metadata commit are explicitly out of scope for this run).

## Files Created/Modified
- `src/pescraper/decongest.py` — manual `fit_markdown` generation + `content_hash`
- `src/pescraper/crawl.py` — `AdaptiveCrawler` page selection, skip-list, 403/well-known-path fallback
- `tests/test_decongest.py` — offline tests against real local HTML fixtures
- `tests/test_crawl.py` — offline tests against mocked `AsyncWebCrawler`/`AdaptiveCrawler`

## Decisions Made
- Live-verified (via direct introspection of the installed crawl4ai 0.9.2 source in this repo's `.venv`) that `AdaptiveCrawler.get_relevant_content()` hard-codes `content: result.markdown.raw_markdown` and that `AdaptiveConfig`'s live dataclass fields match RESEARCH.md's documented shape — no surprises versus RESEARCH.md's live-verified corrections, so the plan's exact prescribed API shape was implemented as written.
- Used `tenacity.retry(stop=stop_after_attempt(2), wait=wait_fixed(1), reraise=False)` as a decorator on a small `_digest_with_retry` wrapper rather than inlining retry logic per-call, matching the plan's "tenacity.retry(...)-style guard" instruction; the resulting `RetryError` (or direct exception) is caught by `select_pages`'s own `try/except`, so the "never raise" contract holds regardless of `reraise`'s exact semantics.
- Test doubles for `crawl.py` implement only the subset of the real `AsyncWebCrawler`/`AdaptiveCrawler` surface `select_pages` actually calls (`__aenter__`/`__aexit__`/`arun`, `digest`/`get_relevant_content`), keeping the "monkeypatch to lock contract shape" pattern RESEARCH.md recommends without over-mocking.

## Deviations from Plan

None - plan executed exactly as written. Both `must_haves.truths` and both tasks' `<behavior>`/`<done>` criteria are met by the implementation as specified; no Rule 1-4 auto-fixes were needed.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required. Both modules run fully offline in tests; no new dependency was added (crawl4ai, tenacity, pydantic all already pinned in `pyproject.toml` from Phase 1).

## Next Phase Readiness
- `pescraper.crawl.select_pages(url)` is importable and exposes the exact `dict[str, str]` contract 02-04 (extraction) and 02-06 (`cli.py`'s `run_firm()`) depend on.
- `pescraper.decongest.content_hash` is ready for the `extractions` table's `content_hash` column (02-04/02-05).
- No blockers for 02-04/02-06; `select_pages`'s empty-dict return is the documented `needs_review`/`no_criteria_page` signal those plans should consume.

---
*Phase: 02-core-pipeline-single-firm*
*Completed: 2026-07-19*

## Self-Check: PASSED

All created files verified present (`src/pescraper/decongest.py`, `src/pescraper/crawl.py`, `tests/test_decongest.py`, `tests/test_crawl.py`, this SUMMARY.md); all 4 recorded commit hashes (`26f2ba2`, `4c5a911`, `f95cb7a`, `e0f2e14`) verified present in `git log --oneline --all`.
