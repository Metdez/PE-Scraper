---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 7
current_phase_name: Discovery & URL Recovery
status: complete
stopped_at: All 7 phases complete — full v1 pipeline built (single-firm extraction, benchmark, batch worker + export, heartbeat, caching, discovery)
last_updated: "2026-07-19T20:30:00.000Z"
last_activity: 2026-07-19
last_activity_desc: Phases 3-7 built in one session at user's request ("complete everything, minimal ceremony") directly against ROADMAP.md without GSD tooling; 132/132 tests passing
progress:
  total_phases: 7
  completed_phases: 7
  total_plans: 9
  completed_plans: 9
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-19)

**Core value:** Turn a raw list of PE firm URLs into an accurate, continuously self-updating, exportable investment-criteria dataset at zero marginal API cost.
**Current focus:** Phase 3 — Accuracy Benchmark

## Current Position

Phase: 7 of 7 — ALL COMPLETE
Status: v1 pipeline fully built and tested
Last activity: 2026-07-19 — Phases 3-7 built in one fast session: benchmark harness, crash-safe batch worker + Excel/CSV export, Task Scheduler heartbeat, extraction/crawl caching, and native (Docker-free) firm discovery + dead-URL recovery. 132/132 tests green.

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 9
- Average duration: -
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 3 | - | - |
| 2 | 6 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [2026-07-19] **Windows-native pivot** (user directive "make it good for Windows"): pipeline, Ollama, Crawl4AI/Playwright, and SQLite all run natively on Windows — no WSL2 distro, no container in the data path. Phase 1 now verifies Windows seams (Ollama `localhost:11434` qwen3:4b round-trip, Playwright, asyncio Proactor + UTF-8). nanoclaw↔store seam → Phase 5; SearXNG/Docker discovery infra (DISC-01) → Phase 7.
- [2026-07-19] **GSD planning framework unavailable on this machine** (new-computer pickup session): `gsd-core`/`/gsd-*` commands from the prior machine were not present here (no marketplace/plugin trace found). User directive: proceed without reinstalling it for now — Phase 2 was planned/executed directly against `02-CONTEXT.md`/`02-RESEARCH.md` (already-drafted for 02-01..02-03; 02-04..02-06 built directly from RESEARCH.md's patterns with no separate PLAN.md) and this file was updated by hand instead of via `/gsd-transition`. Revisit if/when GSD tooling is reinstalled.
- [Roadmap]: SQLite is the source-of-truth contract (native `pipeline.db`, WAL, per-firm transactions); Phase 5 decides how the orchestration layer (nanoclaw-in-WSL2 vs Windows Task Scheduler + CLI) reaches it
- [Roadmap]: Benchmark (Phase 3) deliberately precedes caching (Phase 6) — it is the detector for cache-staleness and prompt regressions
- [Roadmap]: Skills stay thin — pipeline must run fully from CLI with nanoclaw stopped (insurance against framework immaturity)

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 3]: **Live-verified this session** — ran `run-firm` against 3 real PE firms (a-mcapital.com, aeroequity.com, agellus.com). Pipeline never crashed and correctly nulled unstated fields, but extraction yield was low (confidence 0.06–0.18): `AdaptiveCrawler` often settles on a low-value page (portfolio/investments listing) that scores marginally above zero, so the true criteria page is missed. Applied one evidence-based fix (broadened the well-known-path fallback trigger from "zero pages found" to "fewer than 2 pages found", added `/strategies`, `/what-we-look-for`, `/criteria` path variants — see 02-03-SUMMARY.md) but this is fundamentally what Phase 3's page-selection-accuracy metric (separate from extraction accuracy, ROADMAP success criterion 2) exists to measure and drive further tuning of.
- [Phase 3]: qwen3:4b structured-output probe (Phase 1 session, ad hoc) returned dollar amounts as absolute values (`5000000`) rather than the `$M`-scaled units the 24-column schema expects, and mis-transcribed one figure (`$40M` → `40001000`) — Phase 2 built a code-side sanity clamp (`extract.apply_numeric_clamp`, values >100,000 assumed raw-dollar and divided by 1e6) as defense-in-depth; Phase 3's benchmark must still weight numeric-transcription accuracy, not just field presence, to confirm the clamp is sufficient
- [Phase 4]: qwen3:4b cold-load latency ~90s for the first call in a session — batch/timeout design should assume a slow first request per worker lifetime, not per firm
- [Phase 5]: nanoclaw needs WSL2 and moves fast — decide nanoclaw-in-WSL2 vs Windows Task Scheduler + CLI (default: Task Scheduler + CLI) and re-research authoring against then-current version at plan time
- [Phase 6]: Ollama prefix KV-cache reuse benefit is version-dependent — measure empirically at plan time
- [Phase 7]: SearXNG (DISC-01, relocated from Phase 1) — run via Docker Desktop or a native metasearch fallback; decide at plan time
- [Phase 3+]: qwen3:4b accuracy ceiling unknown until full benchmark exists; qwen3:8b is the pre-agreed first escalation knob
- [Phase 4]: Capital IQ CSV ingest (`ingest.py`) is built and tested against the documented expected shape and now wired into `pescraper run --csv`; still not reconciled against the real export (user will supply it later)
- [Phase 3, resolved]: Live benchmark against the hand-verified golden set (tests/benchmark/golden_set.py, 3 real firms) initially scored 0% — qwen3:4b found the right passage (quote populated) but failed to convert obvious values ("$5.9B" -> aum_musd, "Greenwich, CT" -> city/state). Fixed with a more explicit system prompt (unit-conversion and field-parsing examples) — now scores 50% on n=3. This is a real, ongoing accuracy ceiling; qwen3:8b remains the pre-agreed escalation knob if it doesn't improve with a larger sample.
- [Phase 7]: Docker isn't installed on this machine, so discovery uses a native fallback (DuckDuckGo Lite HTML scraping, no API key) instead of self-hosted SearXNG. Live-verified working (real PE firm results parsed correctly) but genuinely rate-limit-fragile under repeated automated hits — exactly the brittleness PITFALLS.md predicted for free search-engine scraping. Self-hosted SearXNG (via Docker) remains the recommended reliable path if discovery needs to run frequently/unattended; this fallback is best-effort.
- [Phase 6]: Ollama prompt-prefix KV-cache reuse was not separately measured (out of scope for this fast pass) — the extraction-result memoization cache (CACH-02, exact input match) is what's built and tested; prefix-KV benefit remains an open, not-yet-measured question if throughput becomes a concern at scale.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-07-19
Stopped at: ALL 7 PHASES COMPLETE. Full CLI surface: `run-firm <url>`, `run [--csv --limit --slug --summary]`, `benchmark`, `find [filters]`, `heartbeat`, `discover`, `recover-urls`, `export [--format --out]`, `status`, `doctor`, `init-db`. 132/132 tests green (`uv run pytest -q`, ~27s including the live-Ollama benchmark). No git repo yet.
Resume file: None

### Phases 3-7 (this session, built fast per explicit user directive — "complete everything, no back-and-forth, minimal tests")

- **Phase 3**: `benchmark.py` + `tests/benchmark/golden_set.py` (3 real firms, hand-verified by fetching and reading their actual pages this session). `pescraper benchmark` command. See Blockers above for the prompt-fix finding.
- **Phase 4**: `worker.py` (atomic job claim via `jobs` table, priority ordering, crash-safe resume via `sync_queue_from_firms`), `export.py` (color-coded xlsx + csv via openpyxl). Also fixed a real bug found live: `db.finish_job` was mutating the `payload` column with error text, corrupting the job's identity key.
- **Phase 5**: nanoclaw dropped per the already-decided default; `pescraper heartbeat` (script-gated no-op when idle) + `pescraper find` (structured-filter CLI, the practical equivalent of a freeform dataset "ask") replace the nanoclaw skills. `scripts/register_heartbeat_task.ps1` provided but NOT executed — registering a real recurring Windows Scheduled Task is a persistent unattended change left for the user to opt into explicitly.
- **Phase 6**: `cache.py` — extraction memoization keyed on (kind, model, prompt_version, content_hash); same-day firm-level crawl-skip in `run_firm_pipeline`. Caught and fixed a test-integrity issue this introduced (an existing Phase 2 test was silently exercising the new cache-skip path instead of its intended merge-preserves-data scenario — fixed by backdating `last_checked` in that test).
- **Phase 7**: `discovery.py` — tried DuckDuckGo's main HTML endpoint first (blocked by anomaly.js bot-detection, live-verified even via real headless Chromium), then DuckDuckGo Lite (works, live-verified with real PE firm results) — but is rate-limit-fragile under repeated automated calls, as PITFALLS.md predicted. `pescraper discover` / `recover-urls` commands.
- **No git repo**: work is only on disk, not committed. User declined git init in an earlier turn this session.

### New-machine setup notes (this session)

Picked up on a new computer; Phase 1's runtime deps needed reinstalling: `uv sync` (venv), `uv run crawl4ai-setup` (Playwright Chromium — was missing entirely), `ollama pull qwen3:4b` (only `nomic-embed-text` was present). All three Phase 1 smoke-test seams (`pescraper doctor` / `scripts/smoke_test.py`) are green again. Also still outstanding from before: no git repo initialized yet (`.git` doesn't exist — PROJECT.md's "dedicated git repo" decision is still "Pending"; user declined to init this session), Node/pnpm/Docker not installed (not blocking — deferred to Phase 5/7 per the Windows-native pivot).
