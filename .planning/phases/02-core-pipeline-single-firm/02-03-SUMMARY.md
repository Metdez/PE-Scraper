---
phase: 02-core-pipeline-single-firm
plan: 03
status: complete
---

# 02-03 Summary: decongest.py, crawl.py

Implemented per plan, plus one live-validated tuning fix beyond the original scope.

- `src/pescraper/decongest.py` — `decongest(cleaned_html, base_url)` via manual `DefaultMarkdownGenerator(content_filter=PruningContentFilter(threshold=0.48))`, never raises; `content_hash(text)` sha256 hex digest.
- `src/pescraper/crawl.py` — `select_pages(url) -> dict[str, str]`: `AdaptiveCrawler` (`confidence_threshold=0.5, max_pages=5, top_k_links=3, strategy=statistical`), skip-list (team/portfolio/news/press/blog/insights/careers/legal/privacy/terms), well-known-path fallback, never raises (returns `{}` on total failure).

9 tests (4 decongest, 5 crawl — offline, mocked `AsyncWebCrawler`/`AdaptiveCrawler`).

**Live validation finding (RESEARCH.md Open Question 1, confirmed):** ran `run-firm` against 3 real PE firm sites (a-mcapital.com, aeroequity.com, agellus.com) as the plan's manual-verification step. All three completed without crashing (handled redirects, 404s, and PDF links gracefully), but extraction yield was low (confidence 0.06–0.18) — the adaptive crawler was landing on portfolio/investments-listing pages that score marginally above zero rather than an actual criteria page, so the "empty pages -> fallback" trigger never fired even though the found page was low-value. Fixed by broadening the fallback trigger from "adaptive found zero pages" to "adaptive found fewer than 2 pages" (merging well-known-path hits in alongside whatever adaptive found, rather than only as a total-failure fallback), and adding common path variants (`/strategies`, `/what-we-look-for`, `/criteria`) to `WELL_KNOWN_PATHS` after observing `aeroequity.com` uses the plural `/strategies/`. Covered by a new `test_select_pages_augments_thin_adaptive_result_with_well_known_paths` case. This is a real, expected accuracy gap — page-selection tuning is explicitly Phase 3's job (separating page-selection accuracy from extraction accuracy is Phase 3 success criterion 2); this fix is a cheap, evidence-based improvement, not a substitute for the formal benchmark.
