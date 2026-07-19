# Pitfalls Research

**Domain:** Local-LLM web scraping / structured extraction platform (PE investment criteria, Windows 11, Ollama + qwen3:4b + Crawl4AI + nanoclaw + SearXNG)
**Researched:** 2026-07-19
**Confidence:** HIGH for crawling/Ollama/Windows pitfalls (verified against GitHub issues and official docs); MEDIUM for nanoclaw maturity assessment (young project, issue volume high, moving fast); MEDIUM for qwen3:4b-specific accuracy numbers (behavior class is well documented, exact rates need the project's own benchmark)

## Critical Pitfalls

### Pitfall 1: Small-model numeric hallucination and unit confusion (the accuracy killer)

**What goes wrong:**
qwen3:4b extracts numbers that are not on the page, or mangles the ones that are: "$15M" becomes `15000000` in a `($M)` column (off by 10^6), "$15–50M EBITDA" gets written into the Revenue columns, "up to $100M enterprise value" becomes both EV Min and EV Max, "AUM of $2 billion" becomes `2` in an `($M)` column instead of `2000`. Worse, when a firm publishes *no* criteria, a 4B model under pressure to fill a 24-column schema will invent plausible mid-market numbers ("$10–50M revenue") because that's the statistically likely answer for a PE firm. The reference implementation (Mason Fairfield's Investment-Criteria-Scraper) used Claude Haiku — a much stronger model — and its author still admits it "will miss every once in a while." A 4B local model will miss more often and more confidently.

**Why it happens:**
- 4B models have weak numeric grounding; they pattern-complete rather than copy. Schema pressure ("fill these 14 numeric fields") biases toward fabrication over nulls.
- PE sites express the same fact many ways: "EBITDA of $3–15 million", "$3MM+ EBITDA", "companies with 3-15mm in EBITDA", "enterprise values up to $150M". Unit normalization ($ vs $M vs $B vs "mm") is a separate task from extraction, and doing both in one prompt is where small models fail.
- Revenue/EBITDA/EV/check-size all appear near each other on criteria pages; attention confusion in small models swaps them.

**How to avoid:**
1. **Constrained decoding always.** Use Ollama's `format` parameter with a JSON schema (supported since Ollama 0.5). This eliminates malformed JSON, but *not* wrong values — treat it as necessary, not sufficient.
2. **Nullable-by-default schema with explicit "not stated" instruction.** Every numeric field is `number | null`; the prompt states repeatedly that null is the correct answer when the page doesn't state the value. Penalizing nulls is how you get fabricated mid-market ranges.
3. **Extract verbatim, normalize in code.** Have the model return the *quoted source string* (e.g. `"$3–15 million EBITDA"`) alongside its parsed number. Deterministic Python then re-parses the quote ($B→×1000, "mm"→M, bare numbers) and cross-checks the model's number. Mismatch → Needs Review. This gives per-value traceability (a stated v1 requirement) for free.
4. **Field-group prompts, not one mega-prompt.** One call for financial ranges, one for deal types/sectors, one for firm metadata. Smaller schemas measurably improve small-model compliance and let you use tighter few-shot examples per group.
5. **Few-shot with hard negatives.** Include an example where the correct output is all-nulls (a portfolio-only page) and one with a unit trap ("$2 billion AUM" → `2000`).
6. **Sanity-check bounds in code:** EBITDA Min ≤ EBITDA Max; EBITDA Max ≤ Rev Max (almost always true for PE targets); check size ≤ EV Max; values in $M within plausible ranges (0.1–100,000). Violations → Needs Review, never silently accepted.
7. **Confidence scoring from evidence, not model self-report.** Small models' self-reported confidence is nearly uncorrelated with correctness. Compute confidence from: was a verbatim quote found on the page (string-match verification), did code-reparse agree with model-parse, how many fields were extracted vs null.

**Warning signs:**
- Benchmark rows where extracted numbers don't string-match anything on the source page.
- Suspicious clustering: many firms with identical "nice" ranges ($10–50M revenue, $2–10M EBITDA).
- Fields populated for firms whose sites are portfolio-only with no criteria page.

**Phase to address:**
Extraction phase (core pipeline). The benchmark harness must exist in the *same* phase, not later — you cannot iterate on prompts without it.

---

### Pitfall 2: Ollama silently truncates long inputs (num_ctx) — extraction reads only part of the page

**What goes wrong:**
Ollama's default context window is small (historically 2048–4096 tokens; newer versions default higher but still bounded), and when the prompt exceeds `num_ctx`, **Ollama silently trims from the front with no error or warning** (documented in ollama/ollama#14259 and independent measurements). Five "decongested" HTML pages concatenated is easily 10–30k tokens. Result: the model extracts from whatever fragment survived truncation — often the page footer — and the system prompt itself can be trimmed away, so the model free-forms. Everything *looks* like it works; accuracy is silently garbage.

**Why it happens:**
Developers assume the model's advertised context (qwen3 supports 32k+) is what Ollama uses. It isn't — `num_ctx` must be set per request or in a Modelfile, and nothing fails loudly when exceeded.

**How to avoid:**
- Set `num_ctx` explicitly (e.g. 16384–32768 for qwen3:4b, VRAM permitting) on every Ollama call.
- **Count tokens before sending.** If decongested content exceeds the budget, chunk per-page (extract per page, merge in code) rather than concatenating all 5 pages.
- Log prompt token counts per firm; alert when near the limit.
- Aggressive decongestion is your friend: strip nav/footer/scripts before the LLM ever sees the page — it also cuts extraction latency, which matters at 5,000 firms × 5 pages on local hardware.

**Warning signs:**
- Extractions that reference only content from the *end* of the concatenated input.
- Accuracy that degrades specifically on firms with long/many pages.
- `ollama ps` showing much smaller context than expected.

**Phase to address:**
Core pipeline phase (HTML decongestion + extraction call design).

---

### Pitfall 3: qwen3 thinking mode fights structured output

**What goes wrong:**
qwen3 is a hybrid reasoning model that emits `<think>...</think>` blocks. Combined with Ollama's JSON-schema constrained decoding, this has caused documented breakage (ollama/ollama#10538, Home Assistant community reports): either the constraint suppresses the think tokens and quality drops, or think content leaks and JSON parsing fails, or the model burns hundreds of tokens "thinking" per field before answering — devastating for throughput on a batch of 25,000 page-extractions.

**Why it happens:**
Constrained decoding zeroes the probability of tokens outside the schema — including `<think>`. Support for "think first, then constrained output" has been inconsistent across Ollama versions.

**How to avoid:**
- Pin the Ollama version; test structured output + qwen3 explicitly on that version before building on it.
- Decide thinking policy deliberately: disable it (`think: false` in Ollama API, or `/no_think`) for extraction calls and benchmark the accuracy difference. For a copy-out task like this, no-think + good few-shot usually beats think + token blowup.
- Strip any `<think>` block defensively before JSON parsing regardless.

**Warning signs:**
- Intermittent JSON parse failures on ~identical inputs; extraction latency wildly variable per firm (thinking token count varies).

**Phase to address:**
Extraction phase — model configuration decisions, recorded in a Modelfile/config checked into the repo.

---

### Pitfall 4: Crawler picks the wrong pages — extraction quality is capped by page selection

**What goes wrong:**
The whole design hinges on "grab the ~5 pages most likely to hold criteria." PE sites are heterogeneous: criteria live under `/criteria`, `/investment-criteria`, `/strategy`, `/approach`, `/what-we-look-for`, `/acquisition-profile`, in a PDF one-pager, or split across a homepage hero and an "About" paragraph. Link-text heuristics miss sites with nonstandard nav, JS-rendered menus, or one-page designs. The founding transcript admits exactly this: "the crawl misses pages when link structures differ." When selection fails, the LLM extracts from portfolio/team pages and produces nulls — or worse, hallucinates from portfolio company descriptions (portfolio pages are full of *other companies'* revenue figures, a prime source of cross-contamination).

**Why it happens:**
Page selection is treated as a solved sub-problem when it's actually the highest-variance step. Errors here are invisible: the pipeline still "succeeds," just on the wrong input.

**How to avoid:**
- Score candidate URLs with a keyword-weighted heuristic (mine Mason's heuristics per PROJECT.md) **plus** a fallback: if no page scores above threshold, fetch sitemap.xml, and if still nothing, flag `Needs Review: no criteria page found` instead of extracting from whatever was fetched.
- Record *which pages* were selected and fed to extraction as columns/log fields — this makes wrong-page selection auditable and is required anyway for value traceability.
- Explicitly exclude portfolio/news/team pages from the extraction bundle (they cause cross-contamination, not just dilution).
- Benchmark page selection separately from extraction: on the hand-verified sample, check "did we fetch the page a human would use?" before checking "did the model read it right?" Otherwise you can't tell which stage is failing.

**Warning signs:**
- High null rates on firms that verifiably publish criteria.
- Extracted numbers matching a portfolio company's description rather than the firm's criteria.

**Phase to address:**
Core pipeline phase (page selection), with the split benchmark in the accuracy-benchmark phase.

---

### Pitfall 5: Anti-bot blocks and JS-heavy sites poison results silently

**What goes wrong:**
A meaningful fraction of 5,000 PE sites sit behind Cloudflare/WAFs or are JS-rendered (Webflow/Squarespace/React). Failure modes: 403/challenge pages returned as "content" (the LLM then extracts nulls or garbage from a Cloudflare interstitial), empty `<div id="root">` shells from non-rendered fetches, and soft-blocks (200 status, "Access denied" body). Mason's repo already hit this — it falls back to "direct browser requests to bypass 403 errors." At batch scale from one residential Windows IP, aggressive concurrency can also get your home IP temporarily blocked across many Cloudflare-fronted sites.

**Why it happens:**
Status-code-only success checks; treating any 200 response as valid content; running headless browsers with default fingerprints; hammering domains without delays.

**How to avoid:**
- **Content validation gate before extraction:** minimum text length, absence of block-page signatures ("Just a moment...", "Access denied", "Enable JavaScript"), presence of firm-name or nav text. Failed gate → retry with browser strategy → else mark `Status: crawl_blocked`, never feed to the LLM.
- Use Crawl4AI's Playwright-based strategy (renders JS) as the default for this domain; its HTTP-only strategy will fail on a large minority of modern PE sites.
- **Politeness is cheap here:** you're crawling ~5 pages per domain across 5,000 *different* domains — per-domain rate limiting (2–5s delay between same-domain requests, 1 concurrent per domain) costs almost nothing in wall-clock time because parallelism comes from crossing domains. Respect robots.txt; use a realistic UA; retry with exponential backoff on 429/403.
- Cap global concurrency modestly (Crawl4AI's MemoryAdaptiveDispatcher + RateLimiter) — see Pitfall 6 for why high concurrency also destabilizes the crawler itself.

**Warning signs:**
- Rows whose "source page" content is <500 chars; clusters of all-null extractions for sites that render fine in a normal browser; rising 403/429 rates over a run (IP reputation degrading mid-batch).

**Phase to address:**
Core pipeline phase (crawl layer + validation gate). Rate-limiting etiquette must be in before any scale-up run.

---

### Pitfall 6: Crawl4AI batch instability — `arun_many` memory leaks, dropped URLs, and hangs

**What goes wrong:**
Crawl4AI's batch API has a documented history of exactly the failure modes an overnight unattended run cannot tolerate: unbounded memory growth / tab accumulation in `arun_many` (#1563/#1592, #1608), **silently missing results** — 680 URLs in, 540 results out, no errors reported (#975), leaked background tasks after stream closure (#2071, #2083 — fixed only in 0.9.x), deep-crawl strategies not composing with `arun_many` (#1509), and LLM-extraction strategy serializing instead of parallelizing (#1055). An 8-hour heartbeat run that leaks memory dies at hour 5 on a Windows desktop.

**Why it happens:**
Trusting one giant `arun_many(5000_urls)` call to be reliable. The library is powerful but fast-moving; its long-batch code paths are the least-hardened ones.

**How to avoid:**
- **Own the batch loop; use Crawl4AI per-firm.** Process firms in small chunks (e.g. one firm = one `AsyncWebCrawler` context or one small `arun_many` of ~5 URLs), persist results immediately, and let the orchestrator (nanoclaw skill / Python driver) manage iteration. Restart the browser/crawler instance every N firms to shed leaked memory.
- **Reconcile counts:** URLs submitted vs results received per chunk; missing URLs go back on the queue — never assume the library returned everything (issue #975 proves it may not).
- Pin the Crawl4AI version (≥0.9.2 for the stream-cleanup fixes); test the pinned version's batch behavior on ~50 firms before trusting it overnight.
- Wrap every per-firm unit in a timeout — hung pages must not stall the whole run.

**Warning signs:**
- Python process RSS climbing steadily across a run; result count < input count with clean logs; chromium processes accumulating in Task Manager.

**Phase to address:**
Batch/heartbeat phase design — but the "per-firm unit, persist immediately" architecture must be set in the core pipeline phase, because retrofitting it is a rewrite.

---

### Pitfall 7: No resumability — one crash wastes an entire overnight run

**What goes wrong:**
The naive pipeline holds results in memory (a list of rows) and writes Excel at the end. Any crash at firm 4,200 of 5,000 — OOM, Ollama hiccup, Windows Update reboot, sleep/hibernate — loses everything. On a Windows 11 desktop, **Modern Standby / scheduled maintenance / automatic Windows Update restarts are near-certainties during unattended overnight runs**, not edge cases.

**Why it happens:**
Batch scripts are written as scripts, not as resumable queue consumers. Windows power management is invisible until the first overnight run mysteriously "stopped at 1:47 AM."

**How to avoid:**
- **SQLite as source of truth, written per-firm** (already contemplated in PROJECT.md — make it mandatory). Each firm is a row with `Status` (queued / crawled / extracted / failed / blocked / done) and `Last Checked`. Excel/CSV is an *export*, never the store.
- Startup logic = resume logic: select firms where status ≠ done; the run is idempotent and re-runnable at any time. Crash recovery is then "just run it again."
- Per-firm try/except: one firm's failure logs + flags and moves on (PROJECT.md's unattended-operation constraint). Distinguish retryable (timeout, 429) from permanent (DNS dead, no site) failures with a retry-count column.
- Windows ops checklist for heartbeat runs: disable sleep on AC (`powercfg`), set Windows Update active hours, keep the machine plugged in; have the heartbeat log a heartbeat timestamp so a silent death is detectable next morning.
- Ollama-specific: models unload after 5 minutes idle by default (`keep_alive`); a run that alternates long crawl phases with extraction phases pays repeated multi-second model reloads — set `keep_alive` appropriately (e.g. `-1` or `1h`) during batch runs. Also serialize or strictly bound concurrent Ollama requests: parallel extraction requests against one consumer GPU cause queuing/VRAM thrash, not speedup.

**Warning signs:**
- Any design doc where "write output" appears once, at the end. Runs that can't answer "how far did it get?" from the DB alone.

**Phase to address:**
Core pipeline phase (per-firm persistence + statuses); hardened in the heartbeat phase (power settings, watchdog, retry policy).

---

### Pitfall 8: Windows-specific runtime breakage (asyncio, encodings, Docker networking)

**What goes wrong:**
Three well-documented classes of Windows failure hit this exact stack:
1. **Playwright asyncio subprocess errors:** `NotImplementedError` from `asyncio.create_subprocess_exec` when the wrong event-loop policy is active. Crawl4AI hit this directly (crawl4ai#282); any framework that sets `WindowsSelectorEventLoopPolicy` (uvicorn does this by default, some libs do it "to fix" other Windows issues) breaks Playwright, which needs the Proactor loop. It's a whack-a-mole across the whole ecosystem (browser-use#1875, skyvern#3012/#6494).
2. **cp1252/charmap `UnicodeEncodeError`:** Windows console and default file encodings crash on Unicode in crawled content — crawl4ai itself needed fixes (#1780, #1789, #1784: zero-width spaces in sitemaps killing URL seeding). Any `open()` without `encoding='utf-8'`, or console logging of scraped text, is a landmine.
3. **Docker networking to host Ollama:** containers (SearXNG, nanoclaw agent containers) reaching host-side Ollama on `:11434` must use `host.docker.internal` — and nanoclaw's egress lockdown *hijacks that exact alias* (nanoclaw#2731), silently cutting agents off from host-local Ollama. Bind-mount paths, CRLF line endings in shell scripts, and file-permission semantics add further Windows/Docker friction.

**How to avoid:**
- First lines of every Python entrypoint: on win32, assert/set `WindowsProactorEventLoopPolicy`; never run the crawler under a server framework that resets the policy (or isolate crawling in its own process).
- Set `PYTHONUTF8=1` (or `PYTHONIOENCODING=utf-8`) machine-wide for this project; `encoding='utf-8'` on every `open()`; treat this as a lint rule.
- Decide the topology explicitly in setup: what runs in Docker (SearXNG, nanoclaw containers) vs on host (Ollama — GPU access from Windows Docker is its own pain; keep Ollama on the host). Document and smoke-test container→host Ollama connectivity (`host.docker.internal:11434`) as a setup validation step, especially if nanoclaw egress lockdown is enabled.
- `.gitattributes` enforcing LF for shell scripts that run inside containers.

**Warning signs:**
- `NotImplementedError` deep in `_make_subprocess_transport`; `'charmap' codec can't encode` in logs; nanoclaw agents timing out on every Ollama call while `curl localhost:11434` works fine from the host.

**Phase to address:**
Environment/setup phase (very first phase) — a validation script that proves Playwright launch, UTF-8 I/O, and container→Ollama connectivity before any feature work.

---

### Pitfall 9: nanoclaw platform immaturity — building the whole system on a fast-moving young framework

**What goes wrong:**
nanoclaw is young and evolving quickly. Its issue tracker shows active, recent breakage in core paths: fresh installs where agent containers exit immediately because `/app/src` isn't mounted (#2380), the orchestrator killing its own container when run inside Docker (#1487), egress lockdown breaking host-local services (#2731), and — most relevant — **Windows support is officially "via WSL2 only"** (the `/setup-windows` skill, #188, requires WSL2 + Docker Desktop/Podman, systemd, and warns that SQLite on `/mnt/c/` is unreliable). If every pipeline capability ships as a nanoclaw skill, every nanoclaw regression is a pipeline outage, and debugging happens two layers deep (Windows → WSL2 → container).

**Why it happens:**
Betting core plumbing on the trendiest layer of the stack. The agent framework is the *least* deterministic, least mature component, yet the plan routes deterministic batch work through it.

**How to avoid:**
- **Thin-skill architecture:** the crawl/extract/cache/export pipeline is a plain Python package, fully runnable and testable from a terminal with zero nanoclaw involvement. nanoclaw skills are thin wrappers that invoke it (this also matches the user's global 3-layer directive/execution architecture). If nanoclaw breaks, batch runs and heartbeats still work via CLI/Task Scheduler.
- Pin the nanoclaw commit; treat upgrades as deliberate, tested events, not `git pull`.
- Accept the WSL2 reality early: plan for nanoclaw (and probably the Python pipeline) living in WSL2 with project files on the WSL2 native filesystem, Ollama on the Windows host reached over the network. Do not fight for native-Windows nanoclaw.
- Heartbeats: have a fallback scheduler (Windows Task Scheduler / cron in WSL2 invoking the CLI) so scheduled runs don't depend on nanoclaw's heartbeat mechanism working.

**Warning signs:**
- Any pipeline function that can only be exercised through a chat message; debugging sessions that start with "is it my code or nanoclaw?"

**Phase to address:**
Architecture decision in the roadmap itself + environment phase. Flag the nanoclaw integration phase for deeper research at planning time (check current issue tracker state then — it will have moved).

---

### Pitfall 10: Cache design mistakes — wrong keys, stale data, and cached garbage

**What goes wrong:**
The custom LMCache-inspired cache goes wrong in predictable ways:
- **Caching failures as successes:** a 403 page, Cloudflare interstitial, or empty JS shell gets content-hashed and cached; every future run "hits cache" and never re-fetches the real page. This is the single most damaging cache bug for this project.
- **Keying extraction cache on URL instead of (content hash + prompt version + model + schema version):** you improve the prompt or bump qwen3, and 5,000 stale extractions keep serving — the benchmark improves but the dataset doesn't.
- **Content-hash false negatives:** PE sites embed timestamps, CSRF tokens, rotating hero images — raw-HTML hashing sees "changed" every run and the cache never hits. Hash the *decongested text*, not raw HTML.
- **No TTL/staleness policy:** "unchanged page" is only knowable by re-fetching; a cache that never re-checks turns "continuously self-updating dataset" into a one-shot snapshot. Conversely, re-checking everything nightly wastes the whole benefit.
- Two-writer corruption: heartbeat run and interactive "research this firm" chat skill hitting the same SQLite cache concurrently without WAL mode / busy timeouts.

**How to avoid:**
- Only cache responses that passed the content-validation gate (Pitfall 5). Cache failures separately with short TTLs and retry counts.
- Composite cache keys: crawl cache keyed by URL; extraction cache keyed by `(decongested_content_hash, prompt_version, model_tag, schema_version)`. Bump `prompt_version` in one place; invalidation becomes automatic.
- Staleness tiers driven by `Last Checked`: e.g. re-check firms with criteria every 60–90 days, failed/blocked firms sooner, dead domains rarely. The heartbeat's "re-check stale" requirement needs this policy defined, not implied.
- SQLite in WAL mode with busy timeout; single-writer discipline for batch runs.

**Warning signs:**
- Cache hit rate ~0% (over-sensitive keys) or ~100% forever (no invalidation); firms whose sites changed months ago still showing old criteria; extraction improvements not reflected in exported data.

**Phase to address:**
Dedicated caching phase — but the validation-gate dependency means the gate (Pitfall 5) must land first.

---

### Pitfall 11: Silent dataset quality drift — accuracy degrades and nobody notices

**What goes wrong:**
Accuracy at ship time ≠ accuracy at month three. Sources of drift: sites redesign (page selection heuristics rot), Ollama/model upgrades change extraction behavior, prompt tweaks fix one firm and break twenty, discovery adds firm types the prompts were never tuned on (growth equity, search funds), and cached stale extractions mix with fresh ones. Because every row *looks* identical in Excel, degraded rows are indistinguishable from good ones — the user shares a spreadsheet where 15% of numbers are quietly wrong, which is worse than an empty cell in this domain (someone sources deals off these numbers).

**Why it happens:**
Benchmarks get built once, run once at v1 sign-off, then never re-run. Confidence columns get populated but nothing downstream consumes them.

**How to avoid:**
- **Benchmark as a regression suite, not a milestone:** the hand-verified sample (aim for 50+ firms stratified across site types) is stored in the repo and re-run automatically after any prompt/model/heuristic change and periodically by heartbeat. Track match-rate over time; alert on drops.
- Make Confidence/Needs Review *load-bearing*: exports visually separate or filter low-confidence rows; heartbeat prioritizes re-scraping Needs Review rows; the "research this firm" chat skill surfaces the evidence quote so a human can adjudicate in seconds.
- Adopt Mason's rule: **never overwrite a confirmed value with a null** — a re-scrape that fails page selection must not erase last quarter's good data; it should flag staleness instead.
- Log per-run aggregate stats (null rate per column, Needs Review rate, block rate); drift shows up in these before anyone spots a wrong number.

**Warning signs:**
- Needs Review rate trending up across heartbeat runs; benchmark not re-run in >1 month; a prompt change merged with no benchmark delta recorded.

**Phase to address:**
Accuracy-benchmark phase, but wired into the heartbeat phase (periodic re-run) and the export phase (confidence-aware output).

---

### Pitfall 12: SearXNG discovery — imprecision (banks/brokers/RIAs) and getting rate-limited by upstream engines

**What goes wrong:**
Two distinct failures:
1. **Precision:** "private equity firm" queries return investment banks, M&A advisors/brokers, RIAs/wealth managers (many literally named "X Capital Partners"), fund-of-funds, VC firms, PE *news* sites, and directories (PitchBook/Crunchbase pages, not firm sites). Naively queueing search results pollutes the dataset with non-PE entities that then get confidently extracted (an M&A advisor's "deal size $5–50M" looks exactly like PE criteria — the schema can't tell them apart, which is why the schema has a `Type` column).
2. **Availability:** self-hosted SearXNG instances routinely get rate-limited/CAPTCHA-blocked by Google and other engines (searxng discussion #4429), especially when a script fires bursts of automated queries from one IP. Discovery heartbeats that hammer SearXNG will degrade it within days — "self-hosted" does not mean "unlimited."

**How to avoid:**
- **Discovery is a classification funnel, not a queue-append:** search result → domain-dedupe against the existing 5,000 → exclusion list (news, directories, known aggregators) → fetch homepage → qwen3 classification call ("PE fund investing own/committed capital? vs bank/broker/RIA/VC") with the result written to the `Type` column → only classified-PE firms enter the scrape queue, ideally with a Needs Review flag on the classification itself for the first batches.
- Use precision query patterns (site-structure phrases like "investment criteria" "EBITDA" "platform acquisitions", state-by-state queries) rather than broad "PE firms in the US".
- Throttle discovery hard: it's a background trickle (tens of queries per heartbeat, randomized delays, multiple engines enabled so one engine's block isn't fatal), not a batch job. Monitor SearXNG engine-error stats.
- Expect and accept that seed CSV (5,000 Capital IQ firms) is the dataset; discovery is incremental garnish in v1. Don't let discovery precision block the core pipeline milestone.

**Warning signs:**
- New-firm queue growing with domains like `*.bank`, `*advisors.com`, `pitchbook.com` profile URLs; SearXNG logs showing engine "suspended" / CAPTCHA errors; discovery finding hundreds of "firms" per night (real discovery rate should be low — most US PE firms are already in a 5,000-firm Capital IQ export).

**Phase to address:**
Discovery phase (late — after core pipeline and benchmark exist, so classification accuracy is measurable).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| One mega-prompt extracting all 24 columns in one call | Simpler code, fewer Ollama calls | Small-model accuracy collapse, undebuggable failures | Never for numerics; OK for a first spike only |
| Excel as the data store (no SQLite) | Zero schema work | No resumability, no statuses, no concurrent access, corruption risk | Never — SQLite from day one, Excel is export-only |
| Trusting `arun_many` result count | Less bookkeeping | Silently missing firms (documented crawl4ai behavior) | Never for batches >10 |
| Skipping the content-validation gate | Ships faster | Block pages extracted as data; cache poisoned with garbage | Never |
| Everything as nanoclaw skills, no CLI path | One interface to build | Framework regressions = total outage; untestable pipeline | Never — CLI first, skills wrap it |
| Hand-verifying only 10 benchmark firms | Fast to build | Match-rate statistically meaningless; drift undetectable | OK for week 1, must grow to 50+ before scale-up |
| Unpinned crawl4ai/nanoclaw/Ollama versions | Latest fixes | Behavior changes mid-project invalidate benchmark & cache | Never — pin all three, upgrade deliberately |
| Skipping robots.txt / per-domain delays | Marginally faster runs | IP reputation damage across Cloudflare-fronted sites; ethical exposure | Never at 5,000-domain scale |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Ollama (structured output) | Assuming `format: schema` guarantees *correct* values | It guarantees parseable JSON only; validate values in code, quote-verify against source |
| Ollama (context) | Not setting `num_ctx`; silent front-truncation eats the system prompt | Set `num_ctx` explicitly; count tokens; chunk per page |
| Ollama (batch) | Firing parallel extraction requests at one consumer GPU; default 5-min model unload between phases | Bounded concurrency (1–2); `keep_alive` raised during runs |
| Ollama from Docker containers | Using `localhost:11434` inside a container; nanoclaw egress lockdown hijacking `host.docker.internal` (#2731) | `host.docker.internal` + explicit connectivity smoke test in setup; audit lockdown config |
| Crawl4AI | One giant `arun_many`; trusting stream cleanup pre-0.9.2 | Per-firm units, chunked, reconciled counts, pinned ≥0.9.2, periodic browser restart |
| Playwright on Windows | Selector event loop set by some other lib/framework → `NotImplementedError` | Force Proactor policy at entrypoint; keep crawler out of uvicorn-style processes |
| SearXNG | Treating it as an unlimited API | Trickle queries, randomized delays, multiple engines, monitor engine suspensions |
| nanoclaw on Windows | Expecting native Windows support | WSL2 + Docker Desktop path (#188); project files on WSL2-native FS; SQLite not on `/mnt/c/` |
| SQLite | Heartbeat + chat skill writing concurrently, default journal mode | WAL mode, busy_timeout, single-writer batch discipline |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| qwen3 thinking tokens on 25k extraction calls | Batch ETA in weeks, not nights | Disable thinking for extraction; benchmark no-think accuracy | Immediately at any scale |
| Feeding raw/lightly-cleaned HTML to the LLM | 10–30k-token prompts, truncation, slow inference | Aggressive decongestion (main-content only) before LLM | ~100 firms |
| Browser-per-page with no reuse | Chromium spawn overhead dominates crawl time | Reuse browser context per firm; restart every N firms (leak hygiene) | ~500 firms/run |
| Unbounded crawl concurrency on desktop RAM | System unresponsive, OOM at hour 5 (crawl4ai #1608, archon #722) | MemoryAdaptiveDispatcher w/ conservative threshold + chunking | Overnight runs |
| Re-crawling everything each heartbeat (no staleness tiers) | Nightly runs take as long as the initial run | TTL tiers by status + content-hash short-circuit | Second full cycle |
| Whole-dataset Excel rewrite on every update | Slow exports, corruption on crash mid-write | Export as an explicit command from SQLite; write temp + atomic rename | ~1,000 rows |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Committing exported firm dataset to a public repo | Capital IQ-derived data leaked (license exposure); Mason's repo has exactly this gap (exports not gitignored) | `.gitignore` exports and DB from day one; repo is code-only |
| Feeding raw scraped HTML into an agent framework prompt | Prompt injection: a webpage instructing the agent (nanoclaw runs with real tool access) | Extraction calls are plain Ollama calls with data-only prompts, never agent-tool-enabled contexts; treat scraped content as untrusted input |
| Disabling nanoclaw isolation to "fix" Ollama connectivity | Agents with host filesystem/network access running LLM-driven code | Fix networking properly (`host.docker.internal`, lockdown config), keep isolation |
| SearXNG instance exposed on 0.0.0.0 | Open proxy for others' queries; upstream engines ban your IP | Bind to localhost/Docker network only |
| Ignoring site ToS/robots wholesale | Legal/ethical exposure at 5,000-domain scale | robots.txt respect, identifiable UA, conservative rates, honor 429 |

## UX Pitfalls (operator experience)

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Exports that hide confidence | User shares spreadsheet with silently-wrong numbers; trust destroyed once | Confidence + Needs Review as visible columns; conditional formatting; optional "verified-only" export |
| No morning-after run report | User can't tell if overnight run worked without spelunking logs | Heartbeat writes a summary (processed/succeeded/blocked/flagged, drift stats) as final act |
| Numbers without provenance | Can't adjudicate a suspicious value | Store source URL + verbatim quote per extracted value; chat skill surfaces them |
| All-or-nothing runs | One bad firm kills a batch; user babysits | Per-firm isolation, statuses, resume-on-rerun |
| Chat skill re-scraping on every question | Slow answers, duplicate crawls | Answer from SQLite first; scrape only on request or staleness |

## "Looks Done But Isn't" Checklist

- [ ] **Extraction works on demo firms:** Often missing the null-discipline case — verify against a portfolio-only site with *no* published criteria (correct output: all nulls, low confidence).
- [ ] **JSON parses 100% of the time:** Constrained decoding hides value errors — verify quote-verification + bounds checks reject fabricated numbers.
- [ ] **Batch run completes:** Verify input count == output count reconciliation exists (crawl4ai drops URLs silently).
- [ ] **Crawler returns content:** Verify the validation gate catches Cloudflare interstitials and empty JS shells (test against a known-blocked site).
- [ ] **Cache "works":** Verify a prompt-version bump invalidates extraction cache, and a cached 403 does NOT survive.
- [ ] **Heartbeat scheduled:** Verify the machine survives the night — sleep disabled on AC, Update active hours set, watchdog timestamp checked in the morning report.
- [ ] **Windows setup done:** Verify Proactor loop + UTF-8 I/O + container→host Ollama smoke tests all pass in a fresh clone.
- [ ] **Benchmark passing:** Verify it's stratified (JS-heavy site, PDF criteria, blocked site, no-criteria firm) and wired to re-run on prompt changes — not a one-time manual comparison.
- [ ] **Discovery finds firms:** Verify a classification gate exists and the queue contains zero banks/brokers/directories in a 50-result sample.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Fabricated numbers discovered in dataset | HIGH | Quote-verification pass over all rows (string-match stored quotes against cached pages); rows failing → Needs Review; re-extract with fixed prompts; this is why quotes must be stored from day one |
| Cache poisoned with block pages | MEDIUM | Purge cache entries below content-validation thresholds; re-crawl affected firms; add the gate that was skipped |
| Overnight run died mid-batch | LOW (if per-firm persistence exists) / HIGH (if not) | Re-run; resume logic picks up non-done firms. Without persistence: full re-run — hence Pitfall 7 |
| Prompt change regressed accuracy | LOW | Benchmark diff identifies it pre-merge; revert prompt version, cache keys auto-invalidate the bad extractions |
| nanoclaw upgrade breaks skills | LOW (thin-skill arch) | Pipeline continues via CLI + Task Scheduler; fix skills at leisure. Monolithic arch: pipeline outage |
| Home IP soft-banned by Cloudflare sites | MEDIUM | Pause runs 24–48h; lower concurrency + raise delays; process the blocked-status queue last |
| SearXNG engines suspended | LOW | Discovery pauses (core pipeline unaffected); rotate engines, lengthen delays |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 8. Windows runtime breakage | Phase: Environment & setup (first) | Setup validation script green: Playwright launch, UTF-8 write, container→Ollama curl |
| 9. nanoclaw immaturity | Phase: Architecture/setup (decision) + nanoclaw integration phase (flag for fresh research) | Full pipeline runs from CLI with nanoclaw stopped |
| 4. Wrong-page selection | Phase: Core pipeline (crawl) | Page-selection benchmark: selected pages match human-chosen pages on sample |
| 5. Anti-bot / JS-heavy poisoning | Phase: Core pipeline (crawl + validation gate) | Gate rejects a seeded set of block/shell pages; block rate reported per run |
| 1. Numeric hallucination / unit confusion | Phase: Core pipeline (extraction) + benchmark phase | Match rate on hand-verified sample ≥ agreed threshold; zero unverifiable numbers (no quote match) in sample |
| 2. num_ctx silent truncation | Phase: Core pipeline (extraction) | Token-count logging; test firm with long pages extracts front-of-page facts correctly |
| 3. qwen3 thinking vs structured output | Phase: Core pipeline (extraction config) | Pinned-version test: 100 consecutive schema calls, 0 parse failures, latency stable |
| 7. No resumability | Phase: Core pipeline (persistence) + heartbeat phase | Kill -9 mid-batch; re-run resumes with no loss and no duplicates |
| 6. Crawl4AI batch instability | Phase: Heartbeat/batch phase | 200-firm run: flat memory profile, submitted==received, zero orphan chromium processes |
| 10. Cache mistakes | Phase: Caching phase | Prompt-version bump invalidates; poisoned-entry test; hit-rate metrics sane on second run |
| 11. Quality drift | Phase: Benchmark phase, wired into heartbeat + export | Benchmark re-runs automatically; morning report shows drift stats; Needs Review consumed downstream |
| 12. Discovery precision + engine blocks | Phase: Discovery phase (last) | 50-discovery sample: ≥90% true PE firms post-classification; SearXNG engine-error rate ~0 |

## Sources

- crawl4ai issues/PRs: #282 (Windows asyncio NotImplementedError), #1780/#1789/#1784 (Windows charmap/Unicode crashes), #1563/#1592 (arun_many memory leaks & race conditions), #1608 (Docker memory leak), #975 (arun_many silently missing results, 680→540), #2071/#2083 (dispatcher task-leak on stream close, fixed 0.9.2), #1509 (deep-crawl × arun_many), #1055 (LLM strategy not parallel) — HIGH confidence
- Playwright/ecosystem Windows event-loop reports: microsoft/playwright-python#2696/#2720, browser-use#1875, skyvern#3012/#6494, plus Playwright docs (SelectorEventLoop incompatibility) — HIGH confidence
- nanoclaw issues/PRs: #188 (/setup-windows — WSL2-only path, SQLite-on-/mnt/c warning), #2380 (fresh-install container crash), #1485/#1487 (containerized orchestrator self-kill), #2731 (egress lockdown hijacks host.docker.internal, breaks host Ollama), #1650 (Podman/host fixes), #1732 (container isolation blocking host tools) — HIGH confidence on individual issues; MEDIUM on overall maturity trajectory (fast-moving)
- Ollama: ollama/ollama#14259 (silent context truncation), #2714/#6286 (num_ctx confusion), #10538 (structured outputs × thinking models), ollama.com/blog/structured-outputs, ollama.com/blog/thinking; jangwook.net num_ctx truncation measurement — HIGH confidence
- qwen3 structured output field reports: glukhov.org / Medium (Ollama+Qwen3 structured output), r/LocalLLaMA (qwen3 thinking + JSON), Home Assistant community (/no_think) — MEDIUM confidence
- SearXNG: searxng discussion #4429 (Google engine rate limits on self-hosted instances), docs.searxng.org limiter docs — HIGH confidence
- mfairfld/Investment-Criteria-Scraper README (architecture, 403 workarounds, needs_review flags, "never overwrite confirmed values with nulls", exports-not-gitignored gap) + founding transcript admissions ("will miss every once in a while") — HIGH confidence
- General small-model extraction behavior (numeric hallucination, schema pressure, self-reported confidence unreliability): practitioner consensus across cited posts — MEDIUM confidence; project benchmark will produce ground truth

---
*Pitfalls research for: local-LLM PE investment-criteria scraping platform*
*Researched: 2026-07-19*
