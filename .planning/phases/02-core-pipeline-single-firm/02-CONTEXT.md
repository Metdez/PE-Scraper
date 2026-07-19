# Phase 2: Core Pipeline, Single Firm - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning

<domain>
## Phase Boundary

A single firm URL runs end-to-end through `pescraper run-firm <url>`: page selection → HTML decongestion → qwen3:4b structured extraction → merged 24-column `FirmRecord` row with per-field provenance and code-computed confidence, persisted to `pipeline.db`. Also: Capital IQ CSV ingest seeds the store with regex first-pass values before any LLM call, with merge rules that never let extraction silently destroy confirmed data.

Out of boundary: batch/queue worker, benchmarking, caching, nanoclaw skills, discovery — later phases. The real Capital IQ CSV file is not yet available (user will supply later) — build against the documented expected 24-column-aligned shape now.

</domain>

<decisions>
## Implementation Decisions

All grey areas accepted as recommended ("best practices") — user confirmed real CSV data arrives later; build ingest against the documented shape now and reconcile then.

### Page Selection & Crawl Boundaries
- Crawl strategy: Crawl4AI `AdaptiveCrawler`, query-driven, `top_k=5` (STACK.md's documented primary). `BestFirstCrawlingStrategy` + keyword scorers is the explicit fallback if adaptive proves noisy in practice — a swap, not a rewrite.
- Skip-list scope: team/portfolio (locked by ROADMAP) plus news/press, blog/insights, careers, legal/privacy/terms — common PE-site boilerplate that never carries criteria.
- No-criteria-page detection: if zero crawled pages clear the relevance threshold, flag the firm `needs_review` with a specific reason code — do not extract from irrelevant junk and do not silently fall through to low confidence.
- 403/blocked fallback: guess well-known paths (`/about`, `/investment-criteria`, `/strategy`, `/approach`) before giving up on a firm.

### Extraction Prompt & Numeric Discipline
- Unit-scale defense-in-depth (informed by a live qwen3:4b probe this session that returned `5000000` instead of `5` for "$5 million", and once mis-transcribed `$40M`→`40001000`): explicit prompt + Pydantic field-description instruction that values are already in millions USD (e.g. "$5M" → `5.0`), **plus** a code-side sanity clamp — any numeric value >100,000 is assumed raw-dollar and auto-divided by 1e6, logged as a warning for the benchmark to later audit.
- Thinking mode: `think:false` for extraction calls (matches the probe, keeps latency down), with defensive stripping of any `<think>...</think>` block that leaks through despite the flag.
- Deal-type vocabulary: enforced via a hard JSON-schema `enum` (Buyout, Recap, Minority, Growth Equity, Venture, Mezzanine Debt, Other) so Ollama's structured output cannot return anything outside the controlled vocabulary.
- Multi-page prompt assembly: rank the ~5 selected pages by relevance/keyword score, concatenate under an explicit char budget (~6,000 chars/page, ~20,000 total), with page-URL headers preserved so provenance stays traceable; truncate lowest-priority pages first if over budget.

### Confidence Scoring & Needs Review
- Confidence formula: simple ratio — non-null criteria fields populated ÷ fields that are typically populatable (excludes commonly-absent fields like `fund_name`/`last_deal` from the denominator). Deterministic, explainable, code-computed (never LLM self-report, per ROADMAP).
- Needs Review threshold: `needs_review=true` when confidence < 0.3 OR zero core numeric fields (EBITDA/EV/check size) are populated at all.
- Seed-vs-extraction numeric conflict: only flag as conflicting when ranges don't overlap at all; overlapping or nested ranges count as agreement (extracted non-null wins silently, no flag).
- Per-field provenance: populate Phase 1's existing `extractions` table (already has `field`, `value`, `quote`, `source_page_url`, `model`, `prompt_version`, `content_hash` columns) — one row per extracted field per firm run.

### Capital IQ Seeding & Merge Rules
- Real CSV not yet available — build ingest against the documented expected 24-column-aligned shape with a flexible, case-insensitive column-mapper (plus a few known header aliases). Reconcile against the actual export format when the user supplies it (deferred, not blocking).
- "Regex first-pass" targets the CSV's own free-text cells (e.g. an "EBITDA Range" column like `"$5-25M"` needing regex to split into min/max) — not web pages. If a CSV column is already clean/numeric, regex is a no-op passthrough.
- `run-firm <url>` (the ad-hoc single-URL path) does **not** consult seed data — pure crawl+extract, since no CSV row exists for an ad-hoc URL. Seeding applies only to the future CSV-batch path (Phase 4).
- Merge-rule scope is universal, not seed-time-only: on every write path (initial seed merge AND any future re-extraction on a stale re-check), a new value only overwrites a field if it is non-null; null never clears a previously confirmed value. Protects the dataset from regressing when a re-crawl temporarily fails to render a page.

### Claude's Discretion
- Exact adaptive-crawl relevance-threshold tuning, exact keyword list for page-priority scoring, exact regex patterns for CSV free-text range parsing, exact column-mapper alias list, module/file layout within `src/pescraper/` extending the Phase 1 package.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets (from Phase 1, verified working this session)
- `pescraper.models.FirmRecord` / `FIRM_COLUMNS` — the single-source-of-truth 24-column pydantic model; `FirmRecord.model_json_schema()` feeds directly into Ollama's `format=` parameter.
- `pescraper.db` — `connect()` (WAL + busy_timeout), `upsert_firm()`, `advance_status()` (validates `ALLOWED_TRANSITIONS`), `stale_firms()`. The `extractions` table already has the exact columns (`field`, `value`, `quote`, `source_page_url`, `model`, `prompt_version`, `content_hash`) this phase's provenance requirement needs — no schema change required, just population.
- `pescraper.cli` — `run_firm(url)` is a typer stub; this phase replaces its body with real crawl→extract→persist logic. `pescraper.doctor` already proves the Ollama structured-output round-trip pattern (`format=schema`, `num_ctx=8192`, `think=False`) — reuse that call pattern for real extraction.
- `pescraper.runtime.configure_windows_runtime()` already activates Proactor + UTF-8 on package import — nothing new needed for Windows correctness.

### Established Patterns
- Single-module-owns-its-SQL convention (`db.py` is the only file with SQL) — extend `db.py`, don't scatter queries.
- Lazy-import-in-CLI-body pattern for heavier modules (crawl4ai, ollama client) — keeps `pescraper --help` fast, matches Phase 1's `doctor`/`init-db` precedent.
- Pydantic v2 + `model_json_schema()` → Ollama `format=` → `model_validate_json()` round-trip, proven live this session against real qwen3:4b.

### Integration Points
- `run_firm()` in `cli.py` is the entry seam.
- `extractions` and `pages` tables are the provenance/cache-precursor seam later phases (3, 6) build on.
- `FirmRecord.confidence` / `.needs_review` are the fields this phase's scoring logic must set before `upsert_firm()`.

</code_context>

<specifics>
## Specific Ideas

- The qwen3:4b unit-scale and numeric-transcription issues found in this session's live probe are not hypothetical — they are the concrete failure modes this phase's prompt design and sanity-clamp must defend against.
- `run-firm <url>` and the future CSV-batch path are two distinct entry points with different seed behavior — this was a real ambiguity in ROADMAP's phrasing, now resolved (see Decisions).

</specifics>

<deferred>
## Deferred Ideas

- Reconciling the ingest against the *actual* Capital IQ CSV export format — deferred until the user supplies the real file. Build against the documented expected shape now; do not block on this.
- PDF criteria one-pagers (PDF-01, v2) — out of Phase 2 scope entirely.
- Full crawl4ai `AdaptiveCrawler` vs `BestFirstCrawlingStrategy` A/B — start with AdaptiveCrawler; only swap if it proves noisy (captured as a research note, not a Phase 2 task).

</deferred>
