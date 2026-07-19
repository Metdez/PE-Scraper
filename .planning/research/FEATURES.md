# Feature Research

**Domain:** PE-firm investment-criteria extraction / firm-intelligence dataset builders (personal, local, zero-marginal-cost alternative to PitchBook/Grata/SourceScrub)
**Researched:** 2026-07-19
**Confidence:** HIGH (reference implementation code read in full; commercial landscape MEDIUM — vendor marketing + comparison articles)

## Context: What the Ecosystem Products Actually Do

Commercial sourcing platforms cluster around the same feature core:

- **PitchBook** (~$15-30K/seat/yr): deep firm profiles (AUM, dry powder, fund vintages), deal/transaction history, contacts, advanced screening (deal size, sector, geo), saved searches with alerts, Excel plugin export. Strength = curated deal history; weakness = private-company criteria are analyst-entered and stale.
- **Grata**: web-scraped private-company + investor data, "find companies like X" similarity search, buyer/investor criteria matching, bulk CSV enrichment, evidence links back to source pages, CRM sync.
- **SourceScrub**: bootstrapped-company sourcing from list sources (conference exhibitor lists, buyer's guides), signal/growth scores, data refresh cadence guarantees, CSV enrichment, alerts on changes.

The features they ALL share (search/filter, structured schema, provenance, refresh cadence, exports, confidence in data quality) define table stakes for any dataset that claims to be trustworthy. The features that justify their price (similarity search, alerts, enrichment-on-demand) are the differentiation targets for a free local clone.

**Reference implementation (mfairfld/Investment-Criteria-Scraper, read in full — README + all 5 pipeline modules):**

| Behavior | Verdict | Notes |
|----------|---------|-------|
| CapIQ preprocess with regex first-pass (ranges, deal types, sectors, activity tier from descriptions) | **Keep** | Free seeding before any LLM call; activity tier inferred from LTM/active/total investment counts |
| Per-firm crash-safe loop: write master.json back after EVERY firm | **Keep** | No batch loss on crash; essential for unattended runs |
| Status lifecycle `pending → in_progress → complete / needs_review`, `stale` after 90 days re-enters queue | **Keep** | Directly feeds Status + Last Checked columns |
| Crawl4AI AdaptiveCrawler (confidence 0.75, max 15 pages, top-k 4) + query "investment criteria EBITDA revenue..." | **Keep** | Proven page-selection approach |
| Anti-403 fallback: parse homepage links, keyword-filter to priority pages (criteria/strategy/portfolio/about), plain requests.get with browser headers | **Keep, improve** | The PRIORITY/SKIP keyword lists contain firm-specific hardcodes (e.g. "about-broadwing-private-equity-firm") — generalize |
| Page classifier (criteria > strategy > portfolio > pdf > about > homepage) driving prompt ordering | **Keep** | Cheap, effective token prioritization |
| HTML decongestion: strip nav/images/footers, dedupe nav links, fix mojibake, 12K char prompt budget with criteria page first | **Keep, improve** | 12K chars fits qwen3:4b context well; budget may need tuning per model |
| Extraction prompt: null-for-unconfirmed, strict deal-type disambiguation rules (Growth Equity vs Buyout), controlled vocabularies, USD-millions normalization | **Keep** | The disambiguation rules are hard-won domain knowledge — mine verbatim |
| Objective confidence: computed from field-population counts (2+ core sizing fields = High), NOT LLM self-assessment | **Keep** | Critical for a 4B local model whose self-assessment is unreliable |
| Merge rules: extracted non-null wins, null never overwrites confirmed, CapIQ conflicts → needs_review with CONFLICT note | **Keep** | This is the data-integrity core |
| Record-level provenance (source_urls list) | **Improve** | Its own TODO: per-field source + confirmed date; PROJECT.md requires value→page traceability |
| Website resolution via search when missing/404 (stubbed Exa) | **Replace** | Swap in self-hosted SearXNG (free) |
| PDF criteria: noted in `notes` as "criteria PDF found: [url] — not parsed" | **Improve** | Many small PE firms put criteria in one-pager PDFs; parsing them is real coverage gain |
| Color-coded Excel export with summary sheet, status filter | **Keep** | The deliverable format |
| Mock modes for crawler + extractor | **Keep** | Lets pipeline logic be tested without network/model |
| No caching of any kind (full re-crawl + re-extract on stale) | **Gap** | Our custom cache layer is a genuine improvement, not parity |
| Sequential, one-firm-at-a-time processing | **Acceptable for v1** | Local model is the bottleneck anyway; concurrency is a scale-up concern |

**nanoclaw interaction model (from repo):** skills-based customization ("every change is a skill"), scheduled tasks (cron-like, with script support in template tasks), per-group persistent memory, containerized agent execution with mount allowlists, messaging-channel chat as the UI. This maps to: batch runs and heartbeats = scheduled tasks + skills; single-firm lookup and freeform queries = chat skills; the dataset directory = an allowlisted mount.

## Feature Landscape

### Table Stakes (Dataset Is Untrustworthy/Unusable Without These)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| 24-column schema population (identity, sizing ranges, deal types, sectors, AUM, activity, quality fields) | The schema IS the product; every commercial tool is a structured schema first | MEDIUM | Controlled vocabularies from PROJECT.md (deal types, sector tier 1); USD-millions normalization |
| CSV/batch ingest → per-firm loop → Excel/CSV export | Raw input and deliverable formats are fixed by the user's workflow (CapIQ export in, Excel out) | LOW-MEDIUM | Mason's preprocess + export are direct blueprints |
| Targeted page selection (~5 best pages/site) with skip-list | Crawling whole sites wastes hours on a local model; criteria live on 1-3 predictable pages | MEDIUM | Crawl4AI adaptive + homepage-link keyword fallback for 403-heavy sites |
| HTML decongestion before extraction | qwen3:4b has a small effective context; nav/footer noise directly degrades extraction accuracy | MEDIUM | Strip nav/images/dupes, page-priority ordering, hard char budget |
| Null-for-unknown extraction discipline ("never guess") | A fabricated EBITDA range is worse than a blank — sample rows show blanks are normal and fine | LOW (prompt) / HIGH (verifying a 4B model obeys) | The single biggest local-model risk; needs the accuracy benchmark |
| Objective confidence scoring (field-count based) | User must know which rows to trust; commercial tools sell "data confidence" as a headline feature | LOW | Compute in code from populated fields, not LLM self-report |
| Needs Review flagging (failures, conflicts, low confidence) | Surfacing weak rows is an Active requirement; silent bad data poisons the dataset | LOW | Failure reasons in notes; conflicts vs CapIQ seed flagged |
| Per-field provenance (value → source URL) | Active requirement: "every extracted value traceable to its source page"; Grata's evidence links are a selling point | MEDIUM | Improvement over Mason's record-level source_urls; store per-field source at extraction time |
| Crash-safe incremental persistence (write after every firm) | Unattended heartbeat runs constraint: errors logged, loop never loses completed work | LOW | SQLite or JSON store; save per firm, never per batch |
| Status lifecycle + staleness re-queue (pending/in_progress/complete/needs_review, stale after N days) | "Continuously self-updating" is in Core Value; SourceScrub sells refresh cadence | LOW | 90-day staleness from reference is a sensible default |
| Failure tolerance per firm (404/timeout/JS-wall → flag and continue) | ~5,000 heterogeneous sites guarantee failures; one bad site must not kill an overnight run | MEDIUM | Mason's failure_reason taxonomy is a good start |
| Merge rules protecting confirmed data (null never overwrites; conflict → flag) | Re-checks must not degrade the dataset over time | MEDIUM | The core invariant of a self-updating dataset |
| Regex first-pass seeding from CapIQ descriptions | Free accuracy: many ranges are literally in the description text; also gives the LLM a cross-check | LOW-MEDIUM | Port Mason's extract_range/deal-type/activity-tier heuristics |
| Pipeline CLI controls (--limit, --slug/single-firm, --summary) | v1 gate is a short sample batch; debugging one firm end-to-end is the daily dev loop | LOW | Also the natural seam nanoclaw skills call into |

### Differentiators (Why This Beats Paying for PitchBook / Burning API Credits)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| 100% local extraction (qwen3:4b via Ollama), zero marginal cost | The founding motivation: $0 vs ~$7/500 firms (Haiku) or $15-30K/yr (PitchBook); unlimited re-runs | MEDIUM-HIGH | Cost is accuracy risk, mitigated by benchmark + confidence gates |
| Custom caching layer (content hash → skip crawl; extraction cache; prompt-prefix reuse) | Reference re-crawls and re-extracts everything on staleness; caching makes heartbeat refreshes ~free in time AND tokens | HIGH | LMCache-inspired but bespoke (Ollama, not vLLM); biggest engineering novelty in the project |
| nanoclaw chat interface: single-firm "research this firm" skill | PitchBook-style on-demand lookup without a UI build; result lands in the dataset AND the chat | MEDIUM | Wraps the same pipeline entry point as --slug |
| Freeform "find me firms like X" / ask-the-dataset skill | Grata's similarity search is its headline feature; a chat skill querying the local store approximates it free | MEDIUM | v1 = filter/query over structured fields; true embedding similarity is v2 |
| SearXNG discovery of firms not in the seed list | Grows the dataset beyond the CapIQ export at zero cost; commercial tools charge precisely for coverage | MEDIUM-HIGH | Self-hosted in Docker; discovery → dedupe vs existing firms → queue as pending |
| Scheduled heartbeat refresh (overnight unattended runs) | SourceScrub sells "data freshness"; here it's a cron'd nanoclaw task that costs nothing while you sleep | MEDIUM | Depends on failure tolerance + crash-safe persistence + staleness queue |
| Accuracy benchmark harness (local model vs hand-verified sample) | Nobody trusts a 4B model without evidence; converts "probably fine" into a measured match rate; also gates any model swap | MEDIUM | An Active requirement; also de-risks the null-discipline problem |
| PDF criteria parsing | Reference punts on PDFs; many lower-middle-market firms publish criteria one-pagers as PDFs — parsing them is coverage the reference lacks | MEDIUM | Crawl4AI handles PDF extraction; feed through same decongestion path |
| Website resolution via SearXNG (missing URL or 404 recovery) | Reference stubbed this behind a paid Exa key; SearXNG makes URL recovery free | LOW-MEDIUM | Same search stack as discovery — shared component |

### Anti-Features (Deliberately NOT Building)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Web app UI / dashboard | Every commercial comp has one; "feels like a product" | Out of Scope in PROJECT.md; weeks of UI work that adds zero data accuracy | nanoclaw chat + color-coded Excel export are the interfaces |
| Paid API extraction (Claude/OpenAI fallback for hard firms) | Tempting accuracy escape hatch when qwen3:4b struggles | Violates the founding zero-cost constraint; becomes a crutch that hides local-model weaknesses | Needs Review flag + human spot-check; improve prompts/decongestion instead |
| Phone integration (nanoclaw → phone) | nanoclaw supports messaging channels natively | Explicitly deferred to v2; presentation layer before the dataset is trustworthy | Chat via existing nanoclaw channel; v2 decision |
| Trend reports (PowerPoint/Excel "what does the data mean") | The obvious payoff of having the data | v2 per PROJECT.md; garbage-in analysis if built before accuracy is proven | Ship the benchmark first; reports come after a trustworthy dataset exists |
| Full 5,000-firm run as a v1 gate | "We have the list, just run it" | Multi-day local-model runtime; amplifies every bug 5,000x before the loop is proven | v1 gate = short sample batch at agreed accuracy; scale-up is ops afterwards |
| SEC filing watcher (Form D/ADV for new firms) | Great free discovery signal | v2 per PROJECT.md; SearXNG covers v1 discovery | Log as v2 discovery channel |
| LMCache as a dependency | "Don't reinvent KV caching" | Requires vLLM; incompatible with the Ollama stack | Custom cache borrowing its ideas (content hash, prefix reuse) |
| Contact/people data (partners, emails) | SourceScrub/PitchBook headline feature | Not in the 24-column schema; scraping people data adds legal/ethical surface and team pages are already skip-listed | Out of schema; ignore team pages entirely (saves tokens too) |
| Deal-history / transaction database | PitchBook's core asset | Requires sources far beyond firm websites (news, filings); a different product | Last Deal date + Activity tier from firm site + CapIQ counts is the v1 proxy |
| Deep whole-site crawls (max_pages >> 15) | "More pages = more data" | Local-model time budget explodes; criteria density is on ~5 pages; risks bans | Adaptive crawl + priority-link fallback, hard page cap |
| Real-time / always-on monitoring | "Self-updating" sounds like live | Firm criteria change on quarter-to-year timescales; polling faster wastes cycles | 90-day staleness + scheduled heartbeats |
| LLM self-assessed confidence as the Confidence column | The model already outputs a confidence field | 4B models are miscalibrated; self-report is noise | Field-count objective scoring in code (keep LLM notes as color only) |

## Feature Dependencies

```
CSV ingest (CapIQ preprocess + regex seed)
    └──feeds──> Firm store (schema + status lifecycle + crash-safe writes)
                    └──required by──> Pipeline loop (crawl → decongest → extract → merge)
                    │                     ├──requires──> Page selection (Crawl4AI + priority-link fallback)
                    │                     ├──requires──> HTML decongestion (before any extraction)
                    │                     ├──requires──> qwen3:4b extraction (null discipline, controlled vocab)
                    │                     └──produces──> Confidence + Needs Review + per-field provenance
                    └──required by──> Excel/CSV export
                    └──required by──> nanoclaw skills (batch, single-firm, freeform ask)
                    └──required by──> Heartbeats (staleness queue + failure tolerance)

Caching layer ──enhances──> Pipeline loop AND Heartbeats  (skip unchanged pages / cached extractions)
SearXNG      ──required by──> Discovery skill AND URL resolution/recovery
Discovery    ──feeds──> Firm store (new pending firms; requires dedupe vs existing)
Benchmark harness ──gates──> Heartbeats at scale AND any model/prompt change
PDF parsing  ──enhances──> Page selection (coverage of PDF-criteria firms)
Freeform ask skill ──requires──> populated Firm store (useless before data exists)
```

### Dependency Notes

- **Pipeline loop requires the firm store first:** status lifecycle, merge rules, and crash-safe persistence are the substrate everything writes into — build before crawl/extract.
- **Extraction requires decongestion:** on a 4B model this is not optional hygiene; raw HTML noise directly destroys field accuracy and blows the context budget.
- **Heartbeats require failure tolerance + staleness queue + crash-safe writes:** unattended operation is only safe once a single bad firm can't kill or corrupt a run.
- **Caching enhances but must not gate v1:** the loop works (slowly, re-crawling) without it; cache correctness bugs (stale hits) are subtle, so land it after the benchmark exists to catch regressions.
- **Benchmark gates scale-up:** the 5k run and trust in heartbeat auto-updates both depend on a measured accuracy number.
- **Discovery requires dedupe:** SearXNG results will re-find firms already in the store; without name/domain dedupe, discovery pollutes the dataset.
- **Chat skills wrap pipeline seams:** single-firm skill = pipeline `--slug` equivalent; batch skill = `--limit`; build the CLI seams first, skills are thin adapters.

## MVP Definition

### Launch With (v1)

- [ ] CapIQ CSV preprocess + regex first-pass seeding — free accuracy, defines the store
- [ ] Firm store with 24-column schema, status lifecycle, per-firm crash-safe writes — data-integrity substrate
- [ ] Crawl: Crawl4AI adaptive + priority-link fallback + skip-lists (~5 pages/firm cap) — the "grab the right pages" core
- [ ] HTML decongestion + page-priority prompt assembly under a char budget — makes qwen3:4b viable
- [ ] qwen3:4b extraction with null discipline, controlled vocabularies, deal-type disambiguation rules — the extraction core
- [ ] Objective confidence + Needs Review + per-field provenance — trustworthiness columns
- [ ] Merge rules (null never overwrites; conflicts flagged) — self-updating without degradation
- [ ] Color-coded Excel/CSV export with summary sheet — the deliverable
- [ ] CLI seams: --limit / --slug / --summary — dev loop + skill integration points
- [ ] Accuracy benchmark harness vs hand-verified sample — the v1 acceptance gate
- [ ] nanoclaw batch skill + single-firm chat skill — the stated interfaces

### Add After Validation (v1.x)

- [ ] Caching layer (content hash, extraction cache, prompt-prefix reuse) — add once benchmark can detect cache-induced staleness bugs; required before heartbeats run at scale
- [ ] Scheduled heartbeats (queued + stale firms overnight) — once failure tolerance is proven on sample batches
- [ ] SearXNG discovery + URL recovery — once the store and dedupe exist
- [ ] Freeform "find/ask" skill — once there's enough data to query
- [ ] PDF criteria parsing — triggered by benchmark showing PDF-criteria firms scoring Low confidence
- [ ] Scale-up toward 5,000 firms — triggered by benchmark hitting the agreed match rate

### Future Consideration (v2+)

- [ ] Phone integration — deferred by decision
- [ ] Trend reports with citations — requires trustworthy dataset first
- [ ] SEC filing watcher discovery channel — SearXNG suffices for v1
- [ ] Embedding-based similarity search ("firms like X" beyond field filters) — needs populated dataset + eval
- [ ] Per-field confirmed-date tracking / change history — useful once heartbeats have run for months

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Firm store + schema + lifecycle + crash-safe writes | HIGH | LOW | P1 |
| Crawl + page selection + fallback | HIGH | MEDIUM | P1 |
| Decongestion + prompt assembly | HIGH | MEDIUM | P1 |
| qwen3:4b extraction (null discipline, vocab) | HIGH | MEDIUM | P1 |
| Confidence / Needs Review / provenance | HIGH | LOW | P1 |
| Merge rules | HIGH | LOW | P1 |
| Excel export | HIGH | LOW | P1 |
| CLI seams (--limit/--slug/--summary) | MEDIUM | LOW | P1 |
| Accuracy benchmark | HIGH | MEDIUM | P1 (v1 gate) |
| Batch + single-firm nanoclaw skills | HIGH | MEDIUM | P1 |
| Caching layer | HIGH | HIGH | P2 |
| Heartbeats | HIGH | MEDIUM | P2 |
| SearXNG discovery + URL recovery | MEDIUM | MEDIUM | P2 |
| Freeform ask skill | MEDIUM | MEDIUM | P2 |
| PDF parsing | MEDIUM | MEDIUM | P2 |
| Similarity search, trend reports, SEC watcher, phone | MEDIUM | HIGH | P3 |

## Competitor Feature Analysis

| Feature | PitchBook | Grata / SourceScrub | Mason's ICS (reference) | Our Approach |
|---------|-----------|---------------------|-------------------------|--------------|
| Criteria data source | Analyst-curated, often stale | Proprietary web scraping | Firm-website crawl + Claude Haiku | Same crawl approach, local qwen3:4b, $0 |
| Data freshness | Periodic analyst refresh | Refresh cadence as a paid promise | 90-day stale re-queue, full re-crawl | Staleness queue + cache so refreshes are cheap |
| Provenance | Source citations in profiles | Evidence links to pages | Record-level source_urls | Per-field source URL (stronger than reference) |
| Confidence / data quality | Implied by brand | Signal scores | Objective field-count scoring | Keep objective scoring; benchmark makes it measurable |
| On-demand company lookup | Search UI | Search UI + Chrome ext | --slug CLI | Single-firm nanoclaw chat skill |
| Similarity / discovery | Screener filters | "Companies like X", list sources | None | SearXNG discovery v1; embeddings v2 |
| Enrichment of user CSVs | Excel plugin | Bulk CSV enrichment | CapIQ preprocess | Same, plus chat-triggered batch runs |
| Alerts / monitoring | Saved-search alerts | Change alerts | None | Heartbeats + Needs Review surfacing |
| Cost | $15-30K/seat/yr | $10K+/yr | ~$7/500 firms (Haiku) | $0 marginal |

## Sources

- mfairfld/Investment-Criteria-Scraper — README + full source of crawler.py, extractor.py, pipeline.py, preprocess_capiq.py, export_to_xlsx.py (read 2026-07-19; HIGH confidence — primary source)
- nanocoai/nanoclaw — repo README/commit history: skills model, scheduled tasks, per-group memory, container mounts (HIGH confidence — primary source)
- .planning/PROJECT.md + Requirements.md — schema, scope, constraints (HIGH confidence)
- Commercial landscape: sourcecodeals.com 19-provider comparison, grata.com/grata-vs-pitchbook, ctacquisitions.com deal-sourcing tools comparison, g2.com Grata vs SourceScrub (MEDIUM confidence — vendor marketing and third-party comparisons; pricing figures approximate)

---
*Feature research for: PE investment-criteria scraping platform*
*Researched: 2026-07-19*
