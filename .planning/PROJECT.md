# PE Scraper

## What This Is

A locally-run agent platform that builds and maintains a structured dataset of US private equity firms' investment criteria. It loops through firm websites, uses Crawl4AI to grab the handful of pages most likely to hold criteria, decongests the HTML, and has a local LLM (qwen3:4b via Ollama) extract EBITDA/revenue/EV ranges, check sizes, deal types, and sectors into a 24-column dataset — all orchestrated through nanoclaw skills so you can batch-run a CSV, ask about a single firm from chat, or let scheduled heartbeats discover new firms via self-hosted SearXNG. Zero marginal API cost.

## Core Value

Turn a raw list of PE firm URLs into an accurate, continuously self-updating, exportable investment-criteria dataset at zero marginal API cost.

## Requirements

### Validated

- [x] Windows-native runtime seams (ENVR-01) — Ollama qwen3:4b structured-output round-trip on `localhost:11434`, Crawl4AI/Playwright Chromium launch, asyncio Proactor + UTF-8 — Validated in Phase 1
- [x] `pipeline.db` SQLite contract (DATA-02) — WAL, 5 tables, fixed 24-column firms schema, status lifecycle, 90-day staleness — Validated in Phase 1
- [x] Single-firm core pipeline (DATA-01, DATA-04, PIPE-01..05) — `run-firm <url>`: AdaptiveCrawler page selection with skip-list/well-known-path fallback → manual fit_markdown decongestion → qwen3:4b structured extraction (financial + categorical field-group schemas, numeric sanity clamp) → null-safe merge → code-computed confidence/needs_review → per-field provenance → persisted row. Capital IQ CSV ingest (column mapping + free-text range regex) built and tested against the documented shape. Live-verified against 3 real PE firms — Validated in Phase 2

- [x] Accuracy benchmark (QUAL-01) — hand-verified golden set (3 real firms), per-field match rate report, `pescraper benchmark` — Validated in Phase 3 (50% match rate on n=3; a real, ongoing accuracy question, not a code gap — see STATE.md)
- [x] Batch/queue worker (DATA-03, DATA-05, PIPE-06, PIPE-07, QUAL-02) — atomic job claims, crash-safe resume, priority ordering, Excel/CSV export, CSV ingest wired into `pescraper run --csv` — Validated in Phase 4
- [x] Windows Task Scheduler + CLI in place of nanoclaw (SKIL-01..03, AUTO-01, AUTO-02) — `heartbeat` (script-gated no-op when idle), `find` (structured dataset filters), `run-firm`/`run --slug` (single-firm chat-skill equivalent) — Validated in Phase 5
- [x] Extraction memoization + same-day crawl skip (CACH-01, CACH-02) — Validated in Phase 6 (prefix-KV-reuse benefit, CACH-03, not separately measured — deferred, not blocking)
- [x] Firm discovery + dead-URL recovery (DISC-01..03) — native DuckDuckGo-based fallback since Docker isn't installed; live-verified working but rate-limit-fragile (self-hosted SearXNG remains the more reliable path if discovery needs frequent unattended runs) — Validated in Phase 7

### Active

None — all v1 phases (1-7) are built and tested. Remaining work is refinement (page-selection tuning, extraction accuracy, reconciling the real Capital IQ CSV format) rather than new features.

### Out of Scope

- Phone integration (nanoclaw → phone) — explicitly deferred to v2 in the founding conversation
- PowerPoint/Excel trend reports with citations ("what does the data mean") — v2; depends on a trustworthy dataset existing first
- SEC filing watcher for newly formed firms — v2 discovery channel; SearXNG covers discovery for v1
- Claude/paid-API extraction — local-only decision; qwen3:4b does 100% of extraction (Haiku cost ~$7/500 firms)
- Full 5,000-firm production run as a v1 gate — v1 proves the loop on a short sample batch; scale-up follows
- Web app UI — nanoclaw chat + Excel export are the interfaces
- LMCache as a dependency — it requires vLLM; we build our own cache using its ideas

## Context

- **Reference implementation:** Mason Fairfield's Investment-Criteria-Scraper (https://github.com/mfairfld/Investment-Criteria-Scraper) already does crawl → extract → table with Claude Haiku. Decision: reference only — mine its criteria prompts, page-selection heuristics, and column schema, but rebuild fresh with clean architecture.
- **Seed data:** ~5,000 US private equity firms exported from Capital IQ as a CSV of URLs (user retains access from a prior internship).
- **Reference repos:** nanoclaw (https://github.com/nanocoai/nanoclaw.git — agent framework this is built on), Crawl4AI (https://github.com/unclecode/crawl4ai.git — crawling), SearXNG (https://github.com/searxng/searxng — free self-hosted metasearch), LMCache (https://github.com/LMCache/LMCache — KV-cache ideas only)
- **24-column schema** (from Requirements.md sample rows): Firm Name, Type, State, City, Website, US Investments, Rev Min ($M), Rev Max ($M), EBITDA Min ($M), EBITDA Max ($M), EV Min ($M), EV Max ($M), Check Min ($M), Check Max ($M), Deal Types, Sector Tier 1, AUM ($M), Activity, Last Deal, Fund Name, Confidence, Needs Review, Last Checked, Status
- **Deal types vocabulary:** Buyout, Recap, Minority, Growth Equity, Venture, Mezzanine Debt, Other
- **Known accuracy reality:** the crawl misses pages when link structures differ; extraction is imperfect — hence Confidence/Needs Review columns and the benchmark requirement
- **Prerequisites** (Windows-native): Git, Python 3.11 + uv, Ollama + qwen3:4b, Crawl4AI/Playwright (Chromium). Node.js 20+ already present. Docker Desktop only if SearXNG-in-Docker is chosen at Phase 7.

## Constraints

- **Cost**: Zero marginal API spend — local model only, self-hosted search only. This is the founding motivation.
- **Tech stack**: Windows-native Python pipeline — Crawl4AI for crawling, Ollama serving qwen3:4b for extraction, SQLite (`pipeline.db`) as source of truth. Orchestration + heartbeats via Windows Task Scheduler + CLI by default (nanoclaw-in-WSL2 reconsidered at Phase 5). SearXNG (or a native metasearch) for discovery.
- **Platform**: Windows 11 host, native. Pipeline runs on Windows Python 3.11 via uv — no WSL2 distro, no container in the data path. Docker Desktop optional, only if SearXNG-in-Docker is chosen at Phase 7.
- **Data**: Deliverable is local Excel/CSV; a local store (e.g. SQLite) may be source of truth, but no cloud services in the data path
- **Unattended operation**: heartbeat runs must work without a human watching — errors get logged and flagged, not crash the loop

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Dedicated git repo in Desktop/PE Scraper | Home directory was itself a git repo; nested dedicated repo gives clean history and safe atomic commits | — Pending |
| Local-only extraction (qwen3:4b via Ollama) | Haiku cost ~$7/500 firms; local is free and the whole point | — Pending |
| Mason's scraper is reference-only | Rebuild fresh with clean architecture; mine prompts, heuristics, schema | — Pending |
| LMCache reference-only; build custom cache | LMCache requires vLLM (not Ollama); we want its token-saving ideas, not its stack | — Pending |
| Local Excel/CSV as deliverable | Local-first ethos; shareable exports without cloud dependency | — Pending |
| Phone + trend reports deferred to v2 | Core loop must be trustworthy before presentation layers | — Pending |
| v1 proven on short sample batch, not full 5k | Fast validation loop; scale is an ops exercise once accuracy is proven | — Pending |
| Windows-native runtime (no WSL2 distro, no container in data path) | User directive 2026-07-19 "make it good for Windows"; Windows Python/uv + Ollama + Playwright + SQLite all run natively, removing path-hell and the container↔host Ollama landmine | — Adopted |
| nanoclaw reconsidered → Windows Task Scheduler + CLI (default) | nanoclaw's WSL2 requirement is the least-Windows-native piece; the skills-stay-thin principle already lets the CLI run standalone. Finalize at Phase 5 | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

## Current State

**All 7 v1 phases complete** (built in one session, 2026-07-19, at the user's explicit request to move fast with minimal ceremony). Full CLI: `run-firm`, `run [--csv/--limit/--slug/--summary]`, `benchmark`, `find`, `heartbeat`, `discover`, `recover-urls`, `export`, `status`, `doctor`, `init-db`. 132/132 tests passing (`uv run pytest -q`, ~27s including one live-Ollama benchmark test).

Real, known-open items (not blockers, tracked in STATE.md Blockers/Concerns): extraction accuracy is a genuine, ongoing tuning question (benchmark scores 50% on a 3-firm sample after one prompt fix); page-selection sometimes lands on low-value pages on real sites; the native (Docker-free) discovery fallback works but is rate-limit-fragile; the real Capital IQ CSV export hasn't been reconciled against `ingest.py`'s column mapper yet; no git repo has been initialized.

Picked up this session on a new machine — GSD planning framework (`gsd-core`/`/gsd-*` commands) wasn't installed here; user chose to proceed without it, so this file (and ROADMAP/STATE) were updated by hand throughout rather than via `/gsd-transition`.

---
*Last updated: 2026-07-19 after Phases 3-7 completion (all v1 phases done)*
