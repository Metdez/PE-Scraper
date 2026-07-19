# Roadmap: PE Scraper

## Overview

Seven phases take a raw Capital IQ CSV of ~5,000 PE firm URLs to a self-updating, benchmarked investment-criteria dataset at zero marginal API cost. The order is risk-first: Phase 1 clears the Windows-native runtime landmines (Ollama on localhost, Playwright, asyncio/UTF-8) and establishes the SQLite contract the pipeline builds against; Phase 2 proves the highest-variance unknown — qwen3:4b extraction quality — on single firms; Phase 3 makes that quality measurable (the v1 acceptance gate); Phase 4 makes batches crash-safe and exportable; Phase 5 layers thin nanoclaw skills and heartbeats over the proven CLI; Phase 6 adds the three-tier cache (deliberately after the benchmark exists, so cache-staleness bugs are detectable); Phase 7 turns on SearXNG discovery and URL recovery so the dataset grows itself.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Environment & Contract Foundation** - Verified Windows-native runtime (Windows Python 3.11 + Ollama/qwen3:4b + Crawl4AI/Playwright) plus the pipeline.db SQLite contract and CLI skeleton (completed 2026-07-19)
- [x] **Phase 2: Core Pipeline, Single Firm** - One firm URL runs end-to-end: page selection → decongestion → qwen3:4b extraction → merged 24-column row with provenance and confidence (completed 2026-07-19)
- [x] **Phase 3: Accuracy Benchmark** - Hand-verified sample harness reporting per-field match rate; the v1 acceptance gate and permanent regression suite (completed 2026-07-19)
- [x] **Phase 4: Queue, Worker & Crash-Safe Batch** - Detached worker with atomic claims, per-firm commits, resume-on-rerun, failure logging, and Excel/CSV export (completed 2026-07-19)
- [x] **Phase 5: nanoclaw Skills & Heartbeats** - Windows Task Scheduler + CLI (`heartbeat`, `find`) replaces nanoclaw per the already-decided default; gated scheduled heartbeats for unattended runs (completed 2026-07-19)
- [x] **Phase 6: Caching Layer** - Extraction memoization + same-day crawl skip so refresh runs cost near zero (completed 2026-07-19)
- [x] **Phase 7: Discovery & URL Recovery** - Native DuckDuckGo-based discovery (Docker unavailable) finds new US PE firms, dedupes, queues them; dead firm URLs get resolved and recovered (completed 2026-07-19)

## Phase Details

### Phase 1: Environment & Contract Foundation

**Goal**: Every Windows-native runtime seam is empirically verified working and the SQLite contract the pipeline builds against exists, before any pipeline code is written
**Depends on**: Nothing (first phase)
**Requirements**: ENVR-01, DATA-02
**Success Criteria** (what must be TRUE):

  1. Developer can run one documented smoke-test command that validates Windows Python 3.11 (asyncio Proactor policy + UTF-8 I/O), Ollama reachable on `localhost:11434` with a qwen3:4b structured-output round-trip, and Crawl4AI health (`crawl4ai-doctor` + a Playwright Chromium launch) — and it passes green
  2. `pipeline.db` (WAL) exists with jobs/firms/pages/extractions/cache tables; a firm row moves through pending → in_progress → complete/needs_review, and rows older than 90 days are surfaced as stale for re-queue
  3. The `pescraper` CLI skeleton installs into the uv-managed Windows venv and runs (`pescraper --help` plus stub `run`/`run-firm`/`export`/`status` subcommands), confirming the Windows Python entry point works

**Plans**: 3/3 plans complete

- [x] 01-01-PLAN.md — Package scaffold, Windows runtime (Proactor + UTF-8), and typer CLI skeleton [ENVR-01]
- [x] 01-02-PLAN.md — SQLite contract pipeline.db (5 tables, 24-column firms, status lifecycle, 90-day staleness) [DATA-02]
- [x] 01-03-PLAN.md — One-command Windows smoke test (Python 3.11 + Ollama qwen3:4b structured round-trip + Crawl4AI/Chromium) [ENVR-01]

Research note: Windows-native pivot (2026-07-19) — pipeline, Ollama, Crawl4AI/Playwright, and SQLite all run natively on Windows; no WSL2 distro and no container mount in the pipeline data path. Set the asyncio `WindowsProactorEventLoopPolicy` (Playwright needs subprocess support) and force UTF-8 (`PYTHONUTF8=1`, mojibake guards) — the top Windows failure modes. The nanoclaw↔store integration seam moves to Phase 5 and SearXNG/Docker discovery infra (DISC-01) to Phase 7, each verified when that phase is built rather than assumed up front.

### Phase 2: Core Pipeline, Single Firm

**Goal**: A single firm URL produces an accurate, trustworthy 24-column row — the project's go/no-go on qwen3:4b extraction quality
**Depends on**: Phase 1
**Requirements**: DATA-01, DATA-04, PIPE-01, PIPE-02, PIPE-03, PIPE-04, PIPE-05
**Success Criteria** (what must be TRUE):

  1. User can run `pescraper run-firm <url>` on a known PE firm and get a populated 24-column row, with nulls (never fabricated values) wherever the site is silent
  2. The pipeline fetches at most ~5 criteria-likely pages per site with priority-link fallback for 403s, skip-lists exclude team/portfolio pages, and a firm with no criteria page is flagged rather than extracted from junk
  3. Every extracted value is traceable to the source page URL it came from (per-field provenance)
  4. Confidence is computed in code from field-population counts (never LLM self-report), and sparse rows are flagged Needs Review
  5. Capital IQ CSV ingest seeds the store with regex first-pass values before any LLM call, and merge rules hold: extracted non-null wins, null never overwrites a confirmed value, seed conflicts are flagged Needs Review

**Plans**: 6/6 plans complete

- [x] 02-01-PLAN.md — merge.py, confidence.py, provenance.py: null-safe merge, code-computed confidence, quote-to-page matching [DATA-04, PIPE-04, PIPE-05]
- [x] 02-02-PLAN.md — db.py: get_firm, insert_extraction [PIPE-05]
- [x] 02-03-PLAN.md — decongest.py, crawl.py: manual fit_markdown, AdaptiveCrawler page selection with skip-list/fallback [PIPE-01, PIPE-02]
- [x] 02-04 — extract_schemas.py, extract.py: qwen3:4b structured extraction, think-strip, numeric sanity clamp [PIPE-03] (built directly from RESEARCH.md — no GSD tooling this session, see 02-04-SUMMARY.md)
- [x] 02-05 — ingest.py: Capital IQ CSV column mapping + free-text range parsing [DATA-01] (see 02-05-SUMMARY.md)
- [x] 02-06 — cli.py: run_firm_pipeline wiring crawl→extract→merge→score→persist end-to-end [PIPE-01..05, DATA-04] (see 02-06-SUMMARY.md)

Verified: full suite 99/99 tests green; `pescraper run-firm` live-tested against 3 real PE firms (a-mcapital.com, aeroequity.com, agellus.com) — no crashes, correct null-discipline, one live page-selection tuning fix applied (see 02-03-SUMMARY.md). Page-selection accuracy remains low on real sites (confidence 0.06–0.18) — expected and explicitly Phase 3's job to measure/drive further.

### Phase 3: Accuracy Benchmark

**Goal**: Extraction quality is a measured number, not a vibe — the v1 acceptance gate that every later prompt, model, or cache change is judged against
**Depends on**: Phase 2
**Requirements**: QUAL-01
**Success Criteria** (what must be TRUE):

  1. User can run the benchmark harness against a hand-verified stratified sample (JS-heavy, PDF-criteria, blocked, and no-criteria firms represented) and see a per-field match-rate report
  2. Page-selection accuracy is reported separately from extraction accuracy, so the two failure modes are distinguishable
  3. Re-running the harness after any prompt or model change shows whether accuracy moved — it functions as a pytest regression suite, not a one-off script

**Plans**: TBD

### Phase 4: Queue, Worker & Crash-Safe Batch

**Goal**: Batches run unattended and crash-safe — a kill mid-run never loses finished work — and the dataset exports to Excel/CSV
**Depends on**: Phase 3
**Requirements**: DATA-03, DATA-05, PIPE-06, PIPE-07, QUAL-02
**Success Criteria** (what must be TRUE):

  1. User can run a single firm (`--slug`), a limited batch (`--limit`), and a status summary (`--summary`) from the CLI
  2. Killing the worker mid-batch loses zero completed firms; re-running resumes exactly where it stopped (per-firm commits, idempotent resume)
  3. A failing firm (404/timeout/JS-wall) is logged with a failure reason and the batch continues to completion
  4. A priority-0 job enqueued during a running batch is claimed next (interactive requests preempt batch work)
  5. A ~50-firm sample batch runs unattended to completion and exports a populated, color-coded Excel workbook (with summary sheet) and CSV

**Plans**: TBD

### Phase 5: nanoclaw Skills & Heartbeats

**Goal**: The user drives everything from nanoclaw chat, and scheduled heartbeats keep the dataset fresh without a human watching
**Depends on**: Phase 4
**Requirements**: SKIL-01, SKIL-02, SKIL-03, AUTO-01, AUTO-02
**Success Criteria** (what must be TRUE):

  1. User can trigger a batch run from nanoclaw chat by pointing it at a CSV or firm count
  2. User can send a firm URL or name in chat and receive its extracted criteria as a formatted reply
  3. User can ask freeform dataset questions in chat ("find firms that do $5-25M EBITDA buyouts in industrials") and get answers from the firm store
  4. Scheduled heartbeats process queued and stale firms unattended, and a script gate skips agent wake entirely when the queue is empty (zero tokens on idle sweeps)
  5. Heartbeat errors are logged and surfaced in chat/status output — the loop never crashes and never silently corrupts the dataset

**Plans**: TBD

Research note: Needs fresh research at plan time — nanoclaw is young and fast-moving. Re-verify skill authoring, scheduled-task and script-gate specifics, and egress-lockdown/Ollama connectivity against the then-current pinned version. Keep skills thin: the pipeline must remain fully operable via CLI with nanoclaw stopped.

Windows-native pivot (2026-07-19): nanoclaw's WSL2 requirement makes it the least Windows-native piece. At plan time decide between (a) **Windows Task Scheduler** heartbeats + the CLI (and optionally a lightweight local chat/TUI) as the interface, dropping nanoclaw as a hard dependency, or (b) nanoclaw running in WSL2 purely as a thin chat front-end talking to the Windows pipeline over `localhost`. Default leans (a) — the "skills stay thin, CLI runs standalone" principle already de-risks dropping nanoclaw, and Task Scheduler is the native equivalent of nanoclaw's cron heartbeats + token-free script gate.

### Phase 6: Caching Layer

**Goal**: Refresh runs cost near-zero — unchanged content never re-crawls or re-spends tokens — without ever serving stale or poisoned data
**Depends on**: Phase 5 (and Phase 3 — the benchmark is what catches cache-staleness bugs)
**Requirements**: CACH-01, CACH-02, CACH-03
**Success Criteria** (what must be TRUE):

  1. A refresh run over already-scraped firms skips re-crawl and re-extraction for content-hash-matched pages, visibly faster and observable in status counts
  2. Identical (model, prompt_version, content_hash) inputs are served from the extraction cache — identical work is never re-spent
  3. Prompts assemble prefix-stable (shared system/schema prefix, per-firm suffix), and the Ollama KV-reuse benefit is measured, not assumed
  4. Bumping `prompt_version` invalidates affected cache entries, blocked/JS-shell content is never cached, and the Phase 3 benchmark still passes with caching enabled

**Plans**: TBD

Research note: Needs fresh research at plan time — Ollama prompt-prefix KV-cache reuse magnitude is version-dependent (MEDIUM confidence). Measure the actual benefit empirically before counting on it for throughput.

### Phase 7: Discovery & URL Recovery

**Goal**: The dataset grows and heals itself — SearXNG finds firms the seed CSV missed and recovers dead firm URLs
**Depends on**: Phase 6
**Requirements**: DISC-01, DISC-02, DISC-03
**Success Criteria** (what must be TRUE):

  1. Self-hosted SearXNG is reachable with the JSON API enabled (returns results, not 403) from the Windows pipeline — via Docker Desktop or a native free-metasearch fallback (DISC-01, relocated from Phase 1)
  2. A discovery run finds candidate US PE firms not in the dataset, classifies PE-vs-not, dedupes against existing firms by name/domain, and queues genuine new firms as pending
  3. Firms with missing or 404 websites get their URL resolved via SearXNG and re-enter the queue
  4. Newly discovered firms flow through the normal pipeline on the next heartbeat and appear in the export

**Plans**: TBD

Research note: Windows-native pivot (2026-07-19) — SearXNG discovery infra (DISC-01) relocated here from Phase 1. On Windows, stand it up via Docker Desktop (`searxng/searxng`, enable `search.formats: [html, json]`) or swap in a native free-metasearch path if avoiding Docker entirely; decided at plan time. All other Phase 7 work is native Windows Python.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Environment & Contract Foundation | 3/3 | Complete    | 2026-07-19 |
| 2. Core Pipeline, Single Firm | 6/6 | Complete    | 2026-07-19 |
| 3. Accuracy Benchmark | 1/1 | Complete    | 2026-07-19 |
| 4. Queue, Worker & Crash-Safe Batch | 1/1 | Complete    | 2026-07-19 |
| 5. nanoclaw Skills & Heartbeats | 1/1 | Complete    | 2026-07-19 |
| 6. Caching Layer | 1/1 | Complete    | 2026-07-19 |
| 7. Discovery & URL Recovery | 1/1 | Complete    | 2026-07-19 |

---
*Roadmap created: 2026-07-19*
*Coverage: 26/26 v1 requirements mapped*
