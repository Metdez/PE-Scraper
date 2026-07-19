# Architecture Research

**Domain:** Local-first agentic web scraping + LLM extraction platform (PE investment-criteria dataset)
**Researched:** 2026-07-19
**Confidence:** HIGH (nanoclaw/Crawl4AI/reference-scraper verified against repos; MEDIUM on Ollama KV-cache internals)

## Standard Architecture

### The Central Decision: Two Halves, One Contract

This system has a **Node/TypeScript half** (nanoclaw: chat, skills, scheduling) and a **Python half** (Crawl4AI crawling, decongestion, Ollama extraction, export). The single most important architectural decision is **how they talk**.

**Recommendation: they don't talk directly. They share a SQLite database (WAL mode) that acts as job queue + state store + cache + dataset.** Node writes jobs; Python executes them and writes results; both read state.

Why this over the alternatives:

| Seam option | Verdict | Reason |
|-------------|---------|--------|
| **SQLite queue-as-contract** (recommended) | ✅ | Mirrors nanoclaw's own proven design (its host↔container seam is literally two polled SQLite files, one writer each). Crash-safe by construction — a batch survives nanoclaw restarts, agent restarts, and worker crashes because state never lives in a process. Works across the container boundary (mount the `.db` file). Zero servers to keep alive. |
| Node spawns Python subprocess per firm | ❌ | nanoclaw agents run in Docker containers (Bun + Claude Agent SDK); they cannot exec host Python. Baking Playwright + Crawl4AI into the agent image is heavy and couples release cycles. Long batch runs would block/timeout the agent turn. |
| Crawl4AI's Docker REST server as the seam | ❌ | Only covers the crawl step. Decongestion, extraction, merge, and export would then live in Node, splitting the pipeline across the language boundary at its most complex point. Keep the whole pipeline in Python. |
| Python FastAPI wrapping the whole pipeline | ⚠️ Later, maybe | Reasonable evolution if you ever need synchronous single-firm calls with streaming progress. Not needed for v1 — a priority queue polled every ~2s gives near-realtime chat response without another always-on server. |

### System Overview

```
┌────────────────────────────────────────────────────────────────────┐
│  INTERACTION LAYER — nanoclaw (Node 20+/TS host, Bun agent in      │
│  Docker; msg apps → router → inbound.db → agent → outbound.db)     │
│  ┌────────────┐ ┌──────────────┐ ┌───────────┐ ┌────────────────┐  │
│  │ batch-scrape│ │ research-firm│ │ ask-data  │ │ heartbeat tasks│  │
│  │ skill (CSV) │ │ skill (1 URL)│ │ skill     │ │ (sweep, ~60s)  │  │
│  └──────┬─────┘ └──────┬───────┘ └─────┬─────┘ └───────┬────────┘  │
│         │ enqueue jobs │ enqueue(prio) │ read-only     │ gate+kick │
├─────────┴──────────────┴───────────────┴───────────────┴───────────┤
│  STATE LAYER — pipeline.db (SQLite, WAL)  ← THE CONTRACT           │
│  ┌────────┐ ┌───────┐ ┌───────────┐ ┌─────────────┐ ┌───────────┐  │
│  │ jobs   │ │ firms │ │ pages     │ │ extractions │ │ cache     │  │
│  │ (queue)│ │ (24co)│ │ (raw+fit) │ │ (per-page)  │ │ (hashes)  │  │
│  └────────┘ └───────┘ └───────────┘ └─────────────┘ └───────────┘  │
├────────────────────────────────────────────────────────────────────┤
│  PIPELINE WORKER — Python, runs on Windows host as one process     │
│  ┌──────────┐ ┌─────────┐ ┌───────────┐ ┌──────────┐ ┌─────────┐   │
│  │ discovery│→│ crawler │→│ decongest │→│ extractor│→│ merge/  │   │
│  │ (SearXNG │ │(Crawl4AI│ │(fit_mkdn +│ │ (Ollama  │ │ export  │   │
│  │  client) │ │ +scorer)│ │ reducer)  │ │  client) │ │(xlsx/csv│   │
│  └────┬─────┘ └────┬────┘ └───────────┘ └────┬─────┘ └─────────┘   │
├───────┴────────────┴─────────────────────────┴─────────────────────┤
│  SERVICES (external processes)                                     │
│  ┌───────────────────┐ ┌──────────────────┐ ┌───────────────────┐  │
│  │ SearXNG (Docker,  │ │ Ollama (host,    │ │ Playwright/       │  │
│  │ format=json)      │ │ qwen3:4b,        │ │ Chromium (managed │  │
│  │                   │ │ keep_alive)      │ │ by Crawl4AI)      │  │
│  └───────────────────┘ └──────────────────┘ └───────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| nanoclaw skills (Node/TS) | Translate chat/CSV input into job rows; report status; trigger export; never do pipeline work themselves | Skill docs + small scripts in the nanoclaw agent container; agent reads/writes mounted `pipeline.db` via `sqlite3`/CLI |
| nanoclaw scheduled tasks | Overnight batch kick, stale-firm re-check, discovery runs | nanoclaw's 60s host sweep with **script gates** ("is there queued work?") so agents don't wake for nothing |
| Job queue + state store | Single source of truth: queue, firm rows (24-col schema), page snapshots, per-page extractions, cache entries, run logs | One SQLite file, WAL mode, `busy_timeout` set; Node writes `jobs`, Python writes everything else (one-writer-per-table-direction, like nanoclaw's inbound/outbound split) |
| Discovery module (Python) | Query SearXNG for candidate US PE firms not in dataset; dedupe by domain; enqueue | `GET /search?q=...&format=json` against local SearXNG (must enable `json` in `settings.yml` `search.formats`) |
| Crawler module (Python) | Fetch homepage, score internal links, fetch top ~5 priority pages (criteria/strategy/approach/portfolio/about) | Crawl4AI `AsyncWebCrawler.arun_many()` + `MemoryAdaptiveDispatcher` with rate limiter; browser-like headers for 403s (proven need from reference scraper) |
| Decongestion module (Python) | Turn raw HTML into minimal token-cheap markdown; compute content hash | Crawl4AI `DefaultMarkdownGenerator` + `PruningContentFilter` → `fit_markdown`, then custom pass (strip nav/footer remnants, collapse whitespace, truncate boilerplate) |
| Extraction client (Python) | Per-page structured extraction via Ollama; confidence scoring; cache check first | `POST /api/chat` to Ollama with `format` JSON-schema, static prompt prefix, `keep_alive=-1` during batches |
| Merge/reconcile module (Python) | Combine per-page extractions into one firm row; never overwrite confirmed values with nulls; conflicts → `Needs Review` | Pure functions over `extractions` → `firms`; provenance column per value (source page URL) |
| Exporter (Python) | `firms` table → Excel/CSV deliverable | `openpyxl`/`pandas`; triggered by skill or end-of-batch |
| Cache layer | Skip re-crawl of unchanged pages and re-extraction of unchanged content | Tables inside the same SQLite DB — see Pattern 2 |

## Recommended Project Structure

Two top-level packages in one repo, joined only by the DB schema:

```
pe-scraper/
├── pipeline/                  # Python half — ALL heavy lifting
│   ├── pescraper/
│   │   ├── db.py              # schema, migrations, queue ops (single module owns SQL)
│   │   ├── worker.py          # poll loop: claim job → run stage → commit → next
│   │   ├── discovery.py       # SearXNG client + dedupe
│   │   ├── crawler.py         # Crawl4AI wrapper, link scorer, page selection
│   │   ├── decongest.py       # fit_markdown + custom reducer + content hashing
│   │   ├── extract.py         # Ollama client, prompt assembly, JSON-schema output
│   │   ├── prompts/           # versioned prompt files (prompt_version in cache key)
│   │   ├── merge.py           # per-page → firm-row reconciliation, confidence
│   │   ├── export.py          # xlsx/csv writer
│   │   └── cli.py             # `pescraper enqueue-csv | run-worker | run-firm | export | status`
│   └── tests/                 # incl. benchmark harness vs hand-verified sample
├── nanoclaw-skills/           # Node half — thin adapters only
│   ├── batch-scrape/          # CSV → enqueue rows, report queue depth
│   ├── research-firm/         # single URL → high-priority job → poll → answer in chat
│   ├── ask-dataset/           # read-only SQL over firms table
│   └── heartbeat/             # scheduled task defs + script gates
├── deploy/
│   ├── searxng/               # docker-compose + settings.yml (json format enabled)
│   └── README.md              # Ollama pull, model config
└── data/
    ├── pipeline.db            # the contract (gitignored)
    └── exports/               # xlsx/csv deliverables (gitignored)
```

### Structure Rationale

- **pipeline/ owns everything deterministic.** This matches the user's global directives/execution pattern: push complexity into deterministic Python code; the nanoclaw agent makes decisions and calls CLIs, it doesn't scrape.
- **nanoclaw-skills/ are thin by design.** Each skill is docs + a small script; the agent's job is enqueue/query/report. If a skill ever contains crawling logic, the boundary has leaked.
- **db.py is the only module that writes SQL.** The schema is the inter-language contract; centralizing it makes contract changes visible.
- **prompts/ are versioned files, not inline strings.** The extraction cache key includes `prompt_version` — editing a prompt must invalidate cached extractions, and file-based prompts make that auditable.

## Architectural Patterns

### Pattern 1: Queue-as-Contract with Detached Worker

**What:** All work items (`scrape_firm`, `discover`, `recheck_stale`, `export`) are rows in a `jobs` table with `status` (queued/running/done/failed), `priority`, `attempts`, `claimed_at`. A single long-lived Python worker polls, claims atomically (`UPDATE ... WHERE status='queued' ORDER BY priority LIMIT 1 RETURNING`), executes, commits per firm. nanoclaw enqueues and reads.

**When to use:** Any time a chat-latency system (nanoclaw) must drive multi-hour work (5,000-firm batches). This is exactly how nanoclaw itself avoids blocking: its scheduled tasks use script gates, and its host↔agent seam is polled SQLite.

**Trade-offs:** + Crash-safe resume for free (re-queue rows stuck in `running` past a timeout). + Chat "research this firm" is just `priority=0`; batch is `priority=9`. − Polling adds up to ~2s latency for interactive requests (fine). − Requires WAL mode + `busy_timeout` discipline to avoid `SQLITE_BUSY` across processes.

**Example:**
```typescript
// nanoclaw skill script (runs in agent container; pipeline.db is a mounted volume)
db.run(`INSERT INTO jobs (kind, payload, priority) VALUES ('scrape_firm', ?, 0)`,
  JSON.stringify({ url }));
// then poll: SELECT status, result FROM jobs WHERE id = ? — answer in chat when done
```

### Pattern 2: Three-Tier Application-Level Cache (the LMCache translation)

**What:** LMCache's core insight — never recompute what you've already computed — implemented at the application layer since Ollama can't import/export KV tensors:

1. **Crawl cache (bytes tier):** store `content_hash = sha256(fit_markdown)` per page URL. On re-crawl, if hash unchanged → skip decongestion + extraction entirely, just bump `Last Checked`. (Analogous to LMCache disk offload: persist across runs.)
2. **Extraction cache (result tier):** key = `(model, prompt_version, content_hash)` → cached JSON extraction. Prompt edits or content changes invalidate; identical content across firms (rare but real — template sites) hits for free. This is the "memoize completions instead of serializing KV" approach.
3. **Prefix tier (Ollama's own KV cache, exploited not replaced):** assemble every extraction prompt as `[static system prompt + schema + few-shot examples] + [variable page content]` — static part first, byte-identical every call. Ollama reuses the KV prefix for the loaded model between requests with identical prefixes; combined with `keep_alive=-1` during batches, the multi-KB schema/instructions are computed once, not 25,000 times (5k firms × 5 pages).

**When to use:** Always — this is the zero-marginal-cost engine. Tier 1 makes re-checks nearly free; tier 3 is the difference between the 4b model being viable or not at 5k-firm scale.

**Trade-offs:** + No vLLM dependency, no KV serialization. − Tier 3 is best-effort (Ollama evicts on model swap or context overflow) — treat it as a throughput optimization, never a correctness dependency. − Cache tables grow; add a pruning job later.

### Pattern 3: Per-Page Extraction, Then Deterministic Merge

**What:** Extract structured JSON from **each decongested page independently** (small prompt, fits qwen3:4b's effective context), then merge per-page extractions into the firm row with deterministic code: prefer non-null over null, prefer criteria-page values over about-page values, record source URL per value, flag disagreements as `Needs Review`. Never let the LLM see all five pages concatenated.

**When to use:** Always with a 4b model. The reference scraper's proven rules apply here: "never overwrite confirmed values with nulls; flag conflicts as needs_review."

**Trade-offs:** + Each LLM call is small, cacheable, and traceable to one source page (satisfies the provenance requirement). + A bad page can't poison the whole firm. − 5 calls per firm instead of 1 (mitigated by tiers 1–3 above). − Merge logic must be written and tested — but it's pure functions, the easiest thing in the system to test.

### Pattern 4: Homepage-First Page Selection (not deep crawl)

**What:** Fetch homepage → parse internal links → score by URL/anchor-text keywords (`criteria`, `investment`, `strategy`, `approach`, `portfolio`, `about`) → fetch top ~5 scored pages via `arun_many` with `MemoryAdaptiveDispatcher` + rate limiting. Optionally fall back to Crawl4AI's BestFirst deep-crawl (with `Prefetch` for cheap URL discovery) only when the scorer finds nothing.

**When to use:** Default for all firms. PE sites are small brochure sites; unbounded deep crawl wastes time and triggers blocks.

**Trade-offs:** + Bounded cost per firm (~6 fetches). − Scorer misses unconventional link structures (known accuracy reality) — the fallback plus `Needs Review` flag covers this, and SearXNG `site:` queries can serve as a third-chance page finder in v1.x.

## Data Flow

### Batch Flow (primary)

```
CSV of 5,000 URLs
    ↓ (nanoclaw batch-scrape skill)
jobs table (5,000 × scrape_firm, priority=9)
    ↓ (Python worker claims one)
crawler: homepage → link scoring → top ~5 pages     ←── SearXNG (discovery
    ↓                                                    jobs insert new firms
decongest: fit_markdown → custom reduce → sha256         upstream of this)
    ↓
cache check: hash unchanged? ──yes──→ bump Last Checked, done
    ↓ no
extract: per page → Ollama qwen3:4b (static prefix + page) → JSON + confidence
    ↓                       ↑ extraction cache consulted first
merge: per-page JSONs → firm row (null-safe, provenance, Needs Review)
    ↓
firms table (24-column row, committed per firm — crash-safe like reference scraper)
    ↓ (export job or skill)
Excel/CSV in data/exports/
```

### Interactive Flow ("research this firm")

```
Chat message → nanoclaw router → agent container → research-firm skill
    → INSERT job priority=0 → worker preempts batch on next claim
    → skill polls job row (~2s) → reads firm row → formats answer → outbound.db → chat
```

### Heartbeat Flow

```
nanoclaw 60s host sweep → scheduled task due → script gate:
  "SELECT count(*) FROM jobs WHERE status='queued'" or "any firm stale > N days?"
  → gate false: agent never wakes (cheap)
  → gate true: agent wakes → enqueues recheck/discovery jobs → worker drains overnight
```

### Key Data Flows

1. **Node → Python:** only ever `jobs` rows (+ CSV file paths in payloads). No RPC, no stdout parsing.
2. **Python → Node:** only ever DB state (`jobs.status`, `firms.*`, run-log rows). Skills read; they don't listen.
3. **Provenance chain:** every firm-row value → `extractions.source_page_url` → `pages.fit_markdown` snapshot → auditable end-to-end (required for the benchmark and Needs Review workflow).

## Suggested Build Order

Dependencies force this order; each stage is independently testable:

1. **State layer first:** SQLite schema (`jobs`, `firms`, `pages`, `extractions`, `cache`), `db.py`, WAL config, CLI skeleton. Everything else writes to it.
2. **Pipeline core, single firm:** crawler → decongest → extract → merge for ONE firm via `pescraper run-firm <url>`. Prove extraction quality on 3–5 known firms (e.g., the Requirements.md sample rows) before any scale work. Ollama + qwen3:4b must be validated here — it's the highest-risk component.
3. **Confidence + provenance + merge rules:** part of core, not an add-on — the schema has the columns from day one.
4. **Queue + worker + crash-safe batch:** `run-worker`, claim/retry/resume semantics, per-firm commit. Test: kill the worker mid-batch, restart, verify no loss.
5. **Cache tiers 1–3:** measurable once batches exist (re-run a batch; second run should be ~free).
6. **Export:** trivial once `firms` is populated; do it early-ish since Excel is the deliverable users see.
7. **nanoclaw skills + heartbeats:** thin adapters over a working CLI/DB. Building them earlier means integrating against a moving target.
8. **SearXNG discovery:** pure producer of jobs; last because it depends on nothing but the queue and dedupe-by-domain against `firms`.
9. **Benchmark harness:** hand-verified sample vs pipeline output; gates the scale-up decision.

Rationale: risk-first (extraction quality at step 2 is the go/no-go), and the contract (step 1) must exist before either half is written against it.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 3–50 firms (v1 sample batch) | Everything above as-is; single worker, sequential extraction |
| 500–5,000 firms (production run) | Crawling parallelizes (`arun_many` + dispatcher, ~5–10 concurrent); extraction stays effectively sequential (one Ollama, one GPU/CPU) — pipeline the stages so crawling stage N+1 overlaps extracting stage N |
| Beyond / continuous refresh | Cache tier 1 makes re-check runs mostly no-ops; add cache pruning and a second Ollama `num_parallel` slot only if extraction is proven the bottleneck |

### Scaling Priorities

1. **First bottleneck: Ollama throughput.** ~25k extraction calls for a full run. Fixes in order: prefix-stable prompts (tier 3), extraction cache (tier 2), smaller decongested inputs, `keep_alive=-1`, right-sized `num_ctx` (oversized context kills qwen3:4b speed and quality).
2. **Second bottleneck: crawl blocks/403s.** Browser headers (proven fix from reference scraper), dispatcher rate limits, per-domain politeness, retry-with-backoff; failures mark firm `Status=crawl_failed` and continue — never crash the loop (unattended-operation constraint).

## Anti-Patterns

### Anti-Pattern 1: Making nanoclaw the Pipeline Runtime

**What people do:** Implement crawl/extract logic inside the agent (LLM-orchestrated scraping per firm), or have the agent babysit a 10-hour batch in one session.
**Why it's wrong:** Agent turns are chat-scale; containers are isolated from host Python; an agent-in-the-loop per firm reintroduces nondeterminism and token cost into a job that must be deterministic and free.
**Do this instead:** Agent enqueues and reports. The detached Python worker owns execution. (This is also the user's global 3-layer directive pattern.)

### Anti-Pattern 2: Trying to Cache Actual KV Tensors

**What people do:** Port LMCache literally — attempt to snapshot/restore Ollama's KV cache to disk.
**Why it's wrong:** Ollama exposes no KV import/export API; LMCache's mechanism is vLLM-specific. You'd fight internals for a benefit the app layer captures more simply.
**Do this instead:** Pattern 2 — hash-based skip, result memoization, and prefix-stable prompts that let Ollama's internal cache do the KV work.

### Anti-Pattern 3: One Mega-Prompt per Firm

**What people do:** Concatenate all crawled pages into a single extraction prompt "so the model sees everything."
**Why it's wrong:** Blows qwen3:4b's usable context, destroys prefix cache hits (every prompt unique from token ~200), makes provenance impossible, and one noisy page degrades all fields.
**Do this instead:** Pattern 3 — per-page extraction + deterministic merge.

### Anti-Pattern 4: Chatty Cross-Language RPC

**What people do:** Node calls Python per page over HTTP/stdout; results flow back through the agent.
**Why it's wrong:** Every hop is a failure mode in an unattended overnight run; state lives in transit instead of on disk; a crash loses the batch.
**Do this instead:** Queue-as-contract (Pattern 1). State is always on disk; either side can die and resume.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| SearXNG | Docker (searxng-docker compose); Python `GET http://localhost:8080/search?q=...&format=json` | Must add `json` to `search.formats` in `settings.yml` or API returns 403. Disable/relax `limiter` for localhost-only use. Bind to localhost only. |
| Ollama | Host install (Windows); `POST /api/chat` with JSON-schema `format`, `keep_alive=-1` during batches | Pin qwen3:4b; disable thinking mode for extraction calls if latency matters; validate `num_ctx` fits decongested pages |
| Crawl4AI | Python library in-process (NOT its Docker REST server) | Playwright Chromium install on Windows host; use cache mode BYPASS (our own cache decides), dispatcher rate limits on |
| nanoclaw | Repo per its install; skills mounted; `data/pipeline.db` volume-mounted into agent container | Agent container is Bun — skill scripts use Bun-compatible SQLite access; heartbeats use script gates so idle sweeps are free |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| nanoclaw skills ↔ pipeline | SQLite `jobs`/`firms` tables only | One writer per direction (Node→jobs, Python→results) — same contention-avoidance nanoclaw uses internally |
| worker ↔ pipeline stages | In-process function calls, per-firm transaction | Stages are pure-ish functions; commit after each firm (reference scraper's crash-safety model) |
| extract ↔ cache | Cache consulted before every Ollama call | Key: `(model, prompt_version, content_hash)` |
| merge ↔ firms | Deterministic upsert, null-safe | Conflicts with existing values set `Needs Review=Yes`, never silent overwrite |

## Sources

- nanoclaw README/architecture (github.com/nanocoai/nanoclaw) — two-SQLite-DB host↔container seam, 60s sweep, script gates, Docker isolation, TS host + Bun agent — HIGH
- Crawl4AI README (github.com/unclecode/crawl4ai) — `arun_many`, `MemoryAdaptiveDispatcher`, deep-crawl strategies, `fit_markdown`/`PruningContentFilter`, Docker REST option — HIGH
- Investment-Criteria-Scraper (github.com/mfairfld/Investment-Criteria-Scraper) — proven pipeline order (preprocess→search→crawl→extract→export), homepage+priority-link selection, null-safe merge, per-firm crash-safe commit — HIGH
- LMCache README (github.com/LMCache/LMCache) — prefix caching, tiered offload concepts; vLLM-only mechanism confirms application-level translation — HIGH (concepts), MEDIUM (Ollama-side prefix-cache behavior inferred from Ollama docs/community, verify empirically in build step 5)
- SearXNG (github.com/searxng/searxng + docs.searxng.org) — JSON format via `search.formats`, limiter config — MEDIUM (settings key names to confirm against current docs during setup)

---
*Architecture research for: local-first PE investment-criteria scraping platform*
*Researched: 2026-07-19*
