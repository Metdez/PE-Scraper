# Phase 1: Environment & Contract Foundation - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning
**Mode:** Infrastructure phase (smart-discuss auto-classified) + Windows-native pivot decisions

<domain>
## Phase Boundary

Stand up and empirically verify the **Windows-native** runtime, and create the SQLite contract (`pipeline.db`) the pipeline builds against — before any crawl/extraction pipeline code is written. Delivers exactly three things:

1. A one-command **Windows smoke test** proving Python 3.11 (asyncio Proactor + UTF-8), Ollama `localhost:11434` qwen3:4b structured-output round-trip, and Crawl4AI/Playwright health.
2. `pipeline.db` (WAL) with jobs/firms/pages/extractions/cache tables, the 24-column firms schema, status lifecycle, and 90-day staleness surfacing.
3. A runnable `pescraper` CLI skeleton (uv-managed venv) with stub subcommands.

Out of boundary: actual crawling, extraction, benchmarking, batch/queue workers, nanoclaw skills, caching logic, discovery — all later phases.

</domain>

<decisions>
## Implementation Decisions

### Locked — Windows-native pivot (2026-07-19, user directive)
- Everything runs **natively on Windows 11**. No WSL2 distro, no container in the data path.
- Ollama = the Windows app on `localhost:11434` (installed this session; qwen3:4b pulled). No `host.docker.internal`, no container→host hop.
- Crawl4AI + Playwright install into the Windows uv venv; `crawl4ai-setup` installs Chromium; verify with `crawl4ai-doctor`.
- Set `asyncio.WindowsProactorEventLoopPolicy` (Playwright needs subprocess support on Windows) and force UTF-8 (`PYTHONUTF8=1` + encoding guards) — the top two Windows failure modes.
- SQLite via stdlib `sqlite3`, WAL mode, per-firm transactions. `pipeline.db` is the source of truth; exports are a view.

### Locked — Stack (from research/ + CLAUDE.md)
- Python 3.11 + **uv** (lockfile). `pescraper` **CLI via typer**. **Pydantic v2** for the 24-column record + extraction models. httpx / tenacity / python-dotenv / openpyxl are later-phase deps (may be declared now).
- **24-column firms schema is fixed** (PROJECT.md): Firm Name, Type, State, City, Website, US Investments, Rev Min/Max ($M), EBITDA Min/Max ($M), EV Min/Max ($M), Check Min/Max ($M), Deal Types, Sector Tier 1, AUM ($M), Activity, Last Deal, Fund Name, Confidence, Needs Review, Last Checked, Status.
- Status lifecycle: pending → in_progress → complete | needs_review; rows older than 90 days flagged stale for re-queue.

### Claude's Discretion
- Project directory layout (e.g. `src/pescraper/` package), module names, exact SQLite DDL + indexes, schema-init approach (raw SQL vs tiny initializer), smoke-test script location/name, and how CLI stubs are wired. Choose conventional Python-on-Windows layouts — these set the conventions later phases inherit.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Greenfield** — no pipeline code exists yet; this phase establishes conventions.
- Reference-only: Mason Fairfield's Investment-Criteria-Scraper (schema, page-selection heuristics, criteria prompts) — mine, do not copy.
- Research in `.planning/research/` (STACK.md, ARCHITECTURE.md, PITFALLS.md) carries verified stack/versions.

### Established Patterns
- None yet — Phase 1 defines them (package layout, DB access pattern, CLI structure).

### Integration Points
- `pipeline.db` schema is the contract every later phase reads/writes.
- The CLI entry point is the seam Phase 5's orchestration layer (Task Scheduler / nanoclaw) will invoke.

</code_context>

<specifics>
## Specific Ideas

- The smoke test is **one documented command** that exits non-zero on any failed seam (green/red), suitable for unattended re-runs.
- The Ollama check must exercise **structured outputs** (`format=<json schema>`) with `num_ctx` set explicitly (8192–16384) — not a bare completion — since that is the extraction contract validated in Phase 2+.
- The Crawl4AI check must actually **launch Chromium headless once** (Playwright), not merely import.

</specifics>

<deferred>
## Deferred Ideas

- nanoclaw ↔ `pipeline.db` integration seam → **Phase 5** (with the nanoclaw-in-WSL2 vs Windows Task Scheduler + CLI decision).
- SearXNG / discovery infra (DISC-01) → **Phase 7** (Docker Desktop or a native metasearch).
- Later-phase dependency installs (openpyxl, etc.) may be declared now but are exercised in their own phases.

</deferred>
