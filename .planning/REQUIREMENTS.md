# Requirements: PE Scraper

**Defined:** 2026-07-19
**Core Value:** Turn a raw list of PE firm URLs into an accurate, continuously self-updating, exportable investment-criteria dataset at zero marginal API cost.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Environment

- [ ] **ENVR-01**: Developer can run a documented environment smoke test that validates Windows Python 3.11 (asyncio Proactor + UTF-8 fixes), Ollama reachability on `localhost:11434` with a qwen3:4b structured-output round-trip, and Crawl4AI health (`crawl4ai-doctor` + Playwright launch) before any pipeline code runs

### Data Foundation

- [ ] **DATA-01**: User can ingest the Capital IQ CSV; preprocessing seeds the firm store with regex first-pass values (ranges, deal types, activity tier) before any LLM call
- [ ] **DATA-02**: Firm store persists the 24-column schema with status lifecycle (pending → in_progress → complete/needs_review; stale after 90 days re-enters queue)
- [ ] **DATA-03**: Every completed firm is persisted immediately (crash-safe) — a crash mid-run never loses finished work
- [ ] **DATA-04**: Merge rules protect confirmed data — extracted non-null wins, null never overwrites a confirmed value, conflicts vs seed data are flagged Needs Review
- [ ] **DATA-05**: User can export the dataset as color-coded Excel (with summary sheet) and CSV

### Pipeline

- [ ] **PIPE-01**: Pipeline selects the ~5 most criteria-likely pages per firm site (adaptive crawl + priority-link fallback for 403s + skip-lists)
- [ ] **PIPE-02**: HTML is decongested (nav/footer/image stripping, dedupe, mojibake fixes) and assembled into a page-priority prompt under an explicit token/char budget with `num_ctx` set
- [ ] **PIPE-03**: qwen3:4b via Ollama extracts criteria fields using structured outputs with null-for-unknown discipline, controlled vocabularies, and deal-type disambiguation rules
- [ ] **PIPE-04**: Confidence is computed objectively in code from field-population counts (never LLM self-report); weak rows get Needs Review
- [ ] **PIPE-05**: Every extracted value carries per-field provenance (source page URL)
- [ ] **PIPE-06**: A failing firm (404/timeout/JS-wall) is logged with a failure reason and the loop continues
- [ ] **PIPE-07**: User can run the pipeline via CLI seams: single firm (`--slug`), limited batch (`--limit`), and status summary (`--summary`)

### Quality

- [ ] **QUAL-01**: User can run a benchmark harness that compares extractions against a hand-verified sample and reports a per-field match rate
- [ ] **QUAL-02**: A short sample batch (~50 firms) runs unattended to completion and produces a populated, exported dataset

### nanoclaw Skills

- [ ] **SKIL-01**: User can trigger a batch run from nanoclaw chat (point it at a CSV / firm count)
- [ ] **SKIL-02**: User can send a firm URL or name in chat and receive its extracted criteria as a formatted reply
- [ ] **SKIL-03**: User can ask freeform dataset questions from chat ("find firms that do $5-25M EBITDA buyouts in industrials") answered from the firm store

### Caching

- [ ] **CACH-01**: Unchanged pages (content hash match) skip re-crawl and re-extraction on refresh runs
- [ ] **CACH-02**: Extraction results are cached keyed on (model, prompt_version, content_hash) so identical inputs never re-spend tokens
- [ ] **CACH-03**: Prompts are assembled prefix-stable (shared system/schema prefix, per-firm suffix) to exploit Ollama's KV cache reuse

### Automation

- [ ] **AUTO-01**: Scheduled heartbeats process queued + stale firms unattended, with a script gate that skips agent wake when the queue is empty
- [ ] **AUTO-02**: Heartbeat errors are logged and surfaced in chat/status output — never crash the loop or silently corrupt the dataset

### Discovery

- [ ] **DISC-01**: Self-hosted SearXNG (via Docker Desktop) — or a native free-metasearch equivalent — runs with the JSON API enabled and reachable by the Windows pipeline
- [ ] **DISC-02**: Discovery searches find candidate US PE firms not in the dataset, dedupe against existing firms (name/domain), and queue them as pending
- [ ] **DISC-03**: Firms with missing or 404 websites get URL resolution/recovery via SearXNG

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Coverage

- **PDF-01**: Parse PDF criteria one-pagers through the same decongestion path (trigger: benchmark shows PDF-criteria firms scoring Low confidence)
- **DISC-04**: SEC filing watcher (Form D/ADV) as a second discovery channel for newly formed firms

### Presentation

- **PRES-01**: Phone integration via nanoclaw messaging channels
- **PRES-02**: PowerPoint/Excel trend reports ("common trends in the finance sector") with every claim cited to source
- **PRES-03**: Embedding-based similarity search ("find firms like X" beyond field filters)

### Data

- **DATA-06**: Per-field confirmed-date tracking / change history across heartbeat runs
- **SCAL-01**: Full ~5,000-firm production run (trigger: benchmark hits agreed match rate)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Web app UI / dashboard | nanoclaw chat + Excel export are the interfaces; UI adds zero data accuracy |
| Paid API extraction (Claude/OpenAI fallback) | Violates founding zero-cost constraint; hides local-model weaknesses instead of fixing them |
| LMCache as a dependency | Requires vLLM, incompatible with Ollama stack; we borrow its ideas only |
| Contact/people data (partners, emails) | Not in the 24-column schema; legal/ethical surface; team pages are skip-listed anyway |
| Deal-history / transaction database | Needs sources beyond firm websites; a different product |
| Real-time / always-on monitoring | Criteria change quarterly at best; 90-day staleness + heartbeats suffice |
| Full 5k run as v1 acceptance gate | Amplifies every bug 5,000× before the loop is proven; it's an ops exercise post-benchmark |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| ENVR-01 | Phase 1 | Pending |
| DATA-02 | Phase 1 | Pending |
| DATA-01 | Phase 2 | Pending |
| DATA-04 | Phase 2 | Pending |
| PIPE-01 | Phase 2 | Pending |
| PIPE-02 | Phase 2 | Pending |
| PIPE-03 | Phase 2 | Pending |
| PIPE-04 | Phase 2 | Pending |
| PIPE-05 | Phase 2 | Pending |
| QUAL-01 | Phase 3 | Pending |
| DATA-03 | Phase 4 | Pending |
| DATA-05 | Phase 4 | Pending |
| PIPE-06 | Phase 4 | Pending |
| PIPE-07 | Phase 4 | Pending |
| QUAL-02 | Phase 4 | Pending |
| SKIL-01 | Phase 5 | Pending |
| SKIL-02 | Phase 5 | Pending |
| SKIL-03 | Phase 5 | Pending |
| AUTO-01 | Phase 5 | Pending |
| AUTO-02 | Phase 5 | Pending |
| CACH-01 | Phase 6 | Pending |
| CACH-02 | Phase 6 | Pending |
| CACH-03 | Phase 6 | Pending |
| DISC-01 | Phase 7 | Pending |
| DISC-02 | Phase 7 | Pending |
| DISC-03 | Phase 7 | Pending |

**Coverage:**
- v1 requirements: 26 total
- Mapped to phases: 26
- Unmapped: 0 ✓

---
*Requirements defined: 2026-07-19*
*Last updated: 2026-07-19 after roadmap creation (traceability populated)*
