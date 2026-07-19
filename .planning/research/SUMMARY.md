# Project Research Summary

**Project:** PE Scraper — local-first PE investment-criteria dataset builder
**Domain:** Local-LLM agentic web scraping + structured extraction (zero-marginal-cost alternative to PitchBook/Grata/SourceScrub)
**Researched:** 2026-07-19
**Confidence:** HIGH overall (repos, docs, and the reference implementation verified directly; MEDIUM on Ollama KV-cache internals, nanoclaw maturity trajectory, and qwen3:4b exact accuracy rates)

## Executive Summary

This is a two-language, three-runtime system: nanoclaw (Node/TS host + Bun agent containers, running in WSL2 on this Windows 11 machine) provides the chat interface, skills, and cron heartbeats with token-free script gates; a Python 3.11+ pipeline (Crawl4AI 0.9.2 → HTML decongestion → qwen3:4b via Ollama structured outputs → SQLite → openpyxl export) does all deterministic data work; Ollama runs natively on Windows for GPU access, reachable from WSL2/containers at `host.docker.internal:11434`. The reference implementation (mfairfld/Investment-Criteria-Scraper) was read in full and provides a proven blueprint for ~60% of the pipeline: page-priority heuristics, null-discipline extraction prompts with deal-type disambiguation, objective field-count confidence scoring, never-overwrite-confirmed-with-null merge rules, and a status lifecycle with 90-day staleness. What we change: Claude Haiku → local qwen3:4b (zero cost), JSON-file store → SQLite WAL, Exa → self-hosted SearXNG, ad-hoc loop → nanoclaw skills/heartbeats, and a bespoke three-tier cache (content-hash skip, extraction memoization, prompt-prefix KV reuse) that LMCache inspires but cannot provide (it is vLLM-only).

**Seam reconciliation (Stack said HTTP/FastAPI; Architecture said shared SQLite):** the resolved recommendation is **SQLite queue-as-contract as the primary seam, with CLI entrypoints — no always-on HTTP service in v1.** A `jobs` table in `pipeline.db` (WAL mode, one writer per direction) is what nanoclaw skills actually touch: skills enqueue rows and read state via SQLite from the agent container (the DB file is volume-mounted); script gates run host-side and call the typer CLI (`pescraper status`). A detached Python worker claims jobs and commits per firm. This wins because it mirrors nanoclaw's own internal two-SQLite-DB idiom, is crash-safe by construction (state never lives in a process or in transit — essential for unattended overnight runs and the #1 pitfall class), works across the container boundary without networking, and avoids betting reliability on cross-container HTTP that the Stack researcher itself flagged as unverified (MEDIUM). The Stack researcher's core concern — agents can't exec host Python — is fully satisfied by the mounted DB. FastAPI is retained only as a documented v1.x evolution if synchronous single-firm calls ever need streaming progress; the ~2s job-poll latency is fine for chat.

The dominant risks are accuracy and unattended reliability, not plumbing. A 4B model under 24-column schema pressure fabricates plausible mid-market numbers, Ollama silently front-truncates prompts exceeding `num_ctx`, qwen3's thinking mode fights constrained decoding, Crawl4AI's `arun_many` silently drops URLs and leaks memory on long batches, and Windows adds asyncio/encoding/Docker-networking landmines. Mitigations are all known and cheap if designed in from day one: per-page extraction + deterministic merge (never a mega-prompt), verbatim-quote extraction with code-side re-parse and bounds checks, explicit `num_ctx` + token counting, thinking disabled and versions pinned, per-firm crash-safe commits with resume-on-rerun, a content-validation gate before anything is extracted or cached, and a stratified 50+-firm benchmark harness built in the same phase as extraction (not after) and wired in as a permanent regression suite.

## Key Findings

### Recommended Stack

Full detail in STACK.md. Everything except Ollama lives in WSL2/Docker (one Linux environment, one filesystem — do not split the pipeline across Windows-native Python and WSL2). Pin nanoclaw, Crawl4AI, and Ollama versions; upgrade deliberately.

**Core technologies:**
- **nanoclaw v2.1.17+ (WSL2)**: chat interface, skills, cron heartbeats with token-free script gates — locked decision; skills are thin adapters only
- **Python 3.11/3.12 + uv**: pipeline language — Crawl4AI is Python-only
- **Crawl4AI 0.9.2 (pinned)**: AdaptiveCrawler + `fit_markdown` (PruningContentFilter) map 1:1 to "5 best pages" and "decongestion"; ≥0.9.2 required for stream-cleanup fixes
- **Ollama (Windows-native) + qwen3:4b**: structured outputs (`format=` JSON schema from Pydantic) are the extraction contract; `temperature 0`, explicit `num_ctx` 16384, `keep_alive` raised during batches, thinking disabled
- **SQLite (WAL)**: source of truth — jobs queue, firms (24-col), pages, extractions, cache; the Node↔Python contract
- **SearXNG (Docker, self-hosted)**: free discovery/URL recovery; requires `search.formats: [html, json]` in settings.yml or the API 403s
- **Supporting:** pydantic 2.x, ollama-python ≥0.4, typer CLI, openpyxl (color-coded export), tenacity, pytest (benchmark harness)

**Explicitly rejected:** LMCache as a dependency (vLLM-only), Windows-native Python pipeline, paid-API extraction fallback, n8n/Airflow, APScheduler inside the service (heartbeats belong to nanoclaw), JSON file as store, public SearXNG instances.

### Expected Features

Full detail in FEATURES.md. The 24-column schema IS the product; trustworthiness features (provenance, confidence, needs-review) are table stakes, not polish.

**Must have (table stakes / v1):**
- CapIQ CSV preprocess + regex first-pass seeding (free accuracy)
- Firm store: 24-col schema, status lifecycle (`pending → in_progress → complete/needs_review`, `stale` at 90d), per-firm crash-safe writes
- Page selection (~5 pages cap): Crawl4AI adaptive + priority-link fallback + skip-lists
- HTML decongestion + page-priority prompt assembly under a char budget
- qwen3:4b extraction: null discipline, controlled vocabularies, deal-type disambiguation rules (mine Mason's prompts verbatim)
- Objective field-count confidence + Needs Review + **per-field** provenance (stronger than reference's record-level)
- Merge rules: non-null wins, null never overwrites confirmed, conflicts flagged
- Color-coded Excel/CSV export; CLI seams (`--limit`/`--slug`/`--summary`)
- Accuracy benchmark harness vs hand-verified sample — **the v1 acceptance gate**
- nanoclaw batch skill + single-firm chat skill

**Should have (differentiators, v1.x):**
- Three-tier cache (content-hash skip, extraction memoization, prefix reuse) — the zero-marginal-cost engine and the project's main engineering novelty
- Scheduled heartbeats (overnight stale re-checks)
- SearXNG discovery + URL recovery (with classification funnel and dedupe)
- Freeform "ask the dataset" skill; PDF criteria parsing

**Defer (v2+):** phone integration, trend reports, SEC filing watcher, embedding similarity search, per-field change history.

**Anti-features:** web UI, paid-API fallback, full 5,000-firm run as a v1 gate, contact/people data, deal-history DB, deep whole-site crawls, LLM self-assessed confidence.

### Architecture Approach

Full detail in ARCHITECTURE.md. Two halves joined only by the SQLite contract: nanoclaw skills translate chat/CSV into `jobs` rows and read state; a single long-lived Python worker polls, claims atomically, executes crawl → decongest → extract → merge → commit per firm. Interactive "research this firm" is just `priority=0` preempting the batch at `priority=9`. Heartbeats use script gates (`any queued work / stale firms?`) so idle sweeps cost zero tokens.

**Major components:**
1. **nanoclaw skills + scheduled tasks (Node/TS, thin)** — enqueue, query, report; never pipeline work
2. **pipeline.db (SQLite WAL)** — jobs, firms, pages, extractions, cache; `db.py` is the only module writing SQL
3. **Python worker + pipeline stages** — discovery, crawler (homepage-first link scoring, not deep crawl), decongest (+content hash), extractor (per-page, static prompt prefix), merge (deterministic, null-safe, per-field provenance), exporter
4. **External services** — SearXNG (Docker), Ollama (Windows host), Playwright/Chromium (managed by Crawl4AI)

**Key patterns:** queue-as-contract with detached worker; three-tier application-level cache; **per-page extraction then deterministic merge** (never one mega-prompt); homepage-first page selection. Prompts are versioned files (`prompt_version` in cache keys).

### Critical Pitfalls

Top 5 of 12 from PITFALLS.md:

1. **Small-model numeric hallucination / unit confusion** — nullable-by-default schema, extract verbatim quotes and re-parse/normalize in code, field-group prompts, bounds sanity checks, evidence-based (not self-reported) confidence; benchmark built in the same phase as extraction
2. **Ollama silent `num_ctx` front-truncation** — set `num_ctx` explicitly, count tokens per call, chunk per page; silent truncation is the #1 "looks fine, is garbage" failure
3. **Wrong-page selection caps accuracy** — keyword scoring + sitemap fallback + `no criteria page found` flag (never extract from whatever was fetched); exclude portfolio/team pages (cross-contamination source); benchmark page selection separately from extraction
4. **Anti-bot / JS-shell poisoning + Crawl4AI batch instability** — content-validation gate before extraction AND before caching; per-firm crawl units with reconciled counts (never one giant `arun_many`); per-domain politeness; periodic browser restart
5. **No resumability + Windows runtime breakage** — per-firm SQLite commits, idempotent resume, Proactor event-loop policy, `PYTHONUTF8=1`, container→host-Ollama smoke test (nanoclaw egress lockdown hijacks `host.docker.internal` — #2731), powercfg/Update active hours for overnight runs

Cross-cutting: pin all versions; thin-skill architecture so the pipeline runs fully from CLI with nanoclaw stopped (nanoclaw is the least mature layer); cache only validated content with composite keys `(content_hash, prompt_version, model, schema_version)`.

## Implications for Roadmap

### Phase 1: Environment & Contract Foundation
**Rationale:** Windows/WSL2 landmines (Pitfall 8) and the SQLite contract must exist before either half is written; risk-first ordering.
**Delivers:** WSL2 + nanoclaw install, Docker network, SearXNG container (json enabled), Ollama + qwen3:4b pulled, `pipeline.db` schema (jobs/firms/pages/extractions/cache) + `db.py` + CLI skeleton, setup-validation script (Playwright launch, UTF-8 I/O, container→Ollama curl, structured-output smoke test on pinned versions).
**Addresses:** CLI seams substrate; firm store + status lifecycle.
**Avoids:** Pitfalls 8, 9 (thin-skill decision locked here), 3 (version pinning + no-think test).

### Phase 2: Core Pipeline, Single Firm
**Rationale:** Extraction quality on qwen3:4b is the go/no-go for the entire project; prove it on 3–5 known firms before any scale or integration work.
**Delivers:** `pescraper run-firm <url>` end-to-end: homepage-first page selection + fallback + skip-lists → decongestion + content hashing → per-page extraction (null discipline, verbatim quotes, field-group prompts, `num_ctx` set, tokens counted) → deterministic merge with per-field provenance, objective confidence, Needs Review → CapIQ preprocess/regex seed → content-validation gate.
**Uses:** Crawl4AI, Ollama structured outputs, Pydantic schema.
**Avoids:** Pitfalls 1, 2, 3, 4, 5.

### Phase 3: Benchmark Harness (v1 gate)
**Rationale:** Cannot iterate on prompts, judge the 4B model, or ever scale up without a measured match rate; features research makes this the explicit v1 acceptance gate.
**Delivers:** Hand-verified stratified sample (grow toward 50+: JS-heavy, PDF-criteria, blocked, no-criteria firms), pytest harness comparing pipeline output, page-selection benchmark separate from extraction benchmark, wired to re-run on any prompt/model change.
**Avoids:** Pitfall 11 (drift) — designed as a regression suite from birth.

### Phase 4: Queue, Worker & Crash-Safe Batch
**Rationale:** Batch semantics (claim/retry/resume, per-firm commit) must be proven before unattended operation; retrofitting per-firm persistence is a rewrite.
**Delivers:** `run-worker` poll loop, atomic claims, priority preemption, per-firm chunked crawling with reconciled counts and browser restarts, kill-mid-batch/resume test green, Excel/CSV export command.
**Avoids:** Pitfalls 6, 7.

### Phase 5: nanoclaw Skills & Heartbeats
**Rationale:** Thin adapters over a working CLI/DB; building earlier means integrating against a moving target on the least mature framework.
**Delivers:** batch-scrape, research-firm (priority-0 enqueue + poll), ask-dataset (read-only) skills; scheduled tasks with script gates; morning-after run report; Windows Task Scheduler fallback path; egress-lockdown/Ollama connectivity verified.
**Avoids:** Pitfall 9.

### Phase 6: Caching Layer
**Rationale:** Deliberately after the benchmark exists — cache-staleness bugs are subtle and the benchmark is what catches them; required before heartbeats run at scale.
**Delivers:** Tier 1 content-hash crawl skip, Tier 2 extraction memoization with composite keys, Tier 3 prefix-stable prompts + `keep_alive`; poisoned-entry and prompt-version-bump invalidation tests; staleness-tier policy.
**Avoids:** Pitfall 10.

### Phase 7: Discovery & Scale-Up
**Rationale:** Last — discovery is incremental garnish on a 5,000-firm seed; scale-up is gated by benchmark hitting the agreed match rate.
**Delivers:** SearXNG discovery as a classification funnel (dedupe → exclusion list → qwen3 PE-vs-not classification → queue), URL recovery, throttled query patterns; then staged scale-up runs (50 → 500 → 5,000) with drift stats.
**Avoids:** Pitfall 12.

### Phase Ordering Rationale

- **Contract before code:** both halves are written against the SQLite schema; it must exist first (Architecture build order).
- **Risk-first:** qwen3:4b extraction quality (Phase 2) is the highest-variance unknown and the project's go/no-go; everything else is known engineering.
- **Benchmark before cache and before scale:** the benchmark detects both cache-staleness regressions and prompt regressions; scaling amplifies every bug 5,000×.
- **Skills last-ish and thin:** the pipeline must be fully operable via CLI with nanoclaw stopped — insurance against framework immaturity and the user's own 3-layer directive pattern.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1:** verify nanoclaw container networking / DB volume-mount into agent containers and Bun-side SQLite access (Stack flagged MEDIUM; nanoclaw moves fast — re-check issue tracker at planning time)
- **Phase 5:** nanoclaw skill authoring + script-gate specifics against the then-current version (Pitfall 9 explicitly flags this phase for fresh research)
- **Phase 6:** empirically measure Ollama prompt-prefix KV reuse benefit (MEDIUM confidence, version-dependent — measure, don't assume)

Phases with standard patterns (skip research-phase):
- **Phase 3:** pytest harness vs golden set — standard testing pattern
- **Phase 4:** SQLite job queue with atomic claims — well-documented pattern
- **Phase 7 (export/scale mechanics):** openpyxl export and staged batch runs are established practice

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Repos/PyPI/official docs verified 2026-07-19; MEDIUM on Ollama prefix-cache behavior and exact container networking |
| Features | HIGH | Reference implementation read in full (primary source); commercial landscape MEDIUM (vendor marketing) |
| Architecture | HIGH | nanoclaw/Crawl4AI/reference verified against repos; MEDIUM on Ollama KV internals |
| Pitfalls | HIGH | Backed by specific GitHub issues for crawl4ai/Ollama/nanoclaw/Playwright; qwen3:4b exact accuracy rates MEDIUM (project benchmark produces ground truth) |

**Overall confidence:** HIGH

### Gaps to Address

- **Cross-runtime seam details:** volume-mounting `pipeline.db` into nanoclaw agent containers and Bun-compatible SQLite access is asserted but unverified — smoke-test in Phase 1; the FastAPI fallback remains documented if it fails.
- **qwen3:4b accuracy ceiling:** unknowable until the Phase 3 benchmark; qwen3:8b is the pre-agreed first escalation knob (same API, zero code change).
- **Ollama prefix KV reuse magnitude:** version-dependent; measure in Phase 6 before counting on it for throughput.
- **nanoclaw drift:** young, fast-moving; pin the commit and re-research at Phase 5 planning.
- **SearXNG settings key names / limiter config:** confirm against current docs during Phase 1 setup.

## Sources

### Primary (HIGH confidence)
- github.com/nanocoai/nanoclaw — README, docs/scheduled-tasks.md, docs/customizing.md; issues #188, #2380, #1487, #2731
- github.com/unclecode/crawl4ai + docs.crawl4ai.com (adaptive-crawling, fit-markdown) + issues #282, #975, #1563/#1592/#1608, #2071/#2083
- github.com/mfairfld/Investment-Criteria-Scraper — full source read (reference blueprint)
- ollama.com (qwen3:4b library page, structured-outputs blog) + ollama/ollama issues #14259, #10538
- docs.searxng.org/dev/search_api.html; pypi.org crawl4ai metadata; github.com/LMCache/LMCache (reference-only conclusion)

### Secondary (MEDIUM confidence)
- SearXNG discussion #4429 (upstream engine rate limits); qwen3 structured-output field reports (r/LocalLLaMA, Home Assistant community)
- Commercial landscape comparisons (grata.com, sourcecodeals.com, g2.com) — pricing approximate

### Tertiary (LOW confidence)
- Ollama prompt-prefix KV reuse magnitude and default `num_ctx` on the installed version — needs empirical validation

---
*Research completed: 2026-07-19*
*Ready for roadmap: yes*
