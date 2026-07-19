<!-- GSD:project-start source:PROJECT.md -->

## Project

**PE Scraper**

A locally-run agent platform that builds and maintains a structured dataset of US private equity firms' investment criteria. It loops through firm websites, uses Crawl4AI to grab the handful of pages most likely to hold criteria, decongests the HTML, and has a local LLM (qwen3:4b via Ollama) extract EBITDA/revenue/EV ranges, check sizes, deal types, and sectors into a 24-column dataset — all orchestrated through nanoclaw skills so you can batch-run a CSV, ask about a single firm from chat, or let scheduled heartbeats discover new firms via self-hosted SearXNG. Zero marginal API cost.

**Core Value:** Turn a raw list of PE firm URLs into an accurate, continuously self-updating, exportable investment-criteria dataset at zero marginal API cost.

### Constraints

- **Cost**: Zero marginal API spend — local model only, self-hosted search only. This is the founding motivation.
- **Tech stack**: nanoclaw is the agent framework; everything ships as nanoclaw skills/hooks. Crawl4AI for crawling. Ollama serving qwen3:4b for extraction. SearXNG for search.
- **Platform**: Windows 11 host; Docker available for containerized pieces (SearXNG, nanoclaw containers)
- **Data**: Deliverable is local Excel/CSV; a local store (e.g. SQLite) may be source of truth, but no cloud services in the data path
- **Unattended operation**: heartbeat runs must work without a human watching — errors get logged and flagged, not crash the loop

<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->

## Technology Stack

## The Shape of the System (read this first)

### The bridge: nanoclaw skills → Python pipeline

- Package the pipeline as one Python project with two entry points: a **CLI** (`pescraper run --limit 5`, `pescraper firm <url>`, `pescraper export`) and a small **FastAPI HTTP service** (same functions, JSON in/out) on the Docker network shared with nanoclaw's agent containers.
- nanoclaw skills call the service with `curl` from inside the agent container (agents have Bash; they do *not* have your Python environment — the agent-runner container is Bun-based). HTTP is the only bridge that survives nanoclaw's container isolation model. Script gates (which run on the host, not in the container) can call the CLI or hit the HTTP health/queue endpoint.
- **Do NOT** try to import Python from TS, embed the pipeline in the agent container, or have the LLM agent drive the crawler step-by-step. The agent orchestrates ("run the batch", "research this firm", report results); deterministic Python does the work. (Confidence: HIGH on the pattern, MEDIUM on exact nanoclaw container networking details — verify `docker network` reachability in Phase 1.)

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| nanoclaw | v2.1.17+ (track main) | Agent framework: chat interface, skills, scheduled heartbeats, container isolation | Locked decision. Verified: skills-over-features model, cron scheduled tasks with token-free script gates, per-agent-group workspace. Runs on WSL2 on this host |
| Node.js + pnpm | Node 20+ (22 LTS recommended), pnpm 10+ | nanoclaw host runtime | nanoclaw's stated prerequisites; installer bootstraps both |
| Python | 3.11 or 3.12 | Pipeline language | Crawl4AI requires ≥3.10; 3.11+ for perf. 3.12 verified-safe with Playwright/Pydantic v2 |
| Crawl4AI | 0.9.2 (PyPI, verified latest) | Crawling + page selection + HTML decongestion | The two killer features map 1:1 to requirements: `AdaptiveCrawler` (query-driven crawl, `get_relevant_content(top_k=5)` = "5 best subpages") and `fit_markdown` via `PruningContentFilter`/`BM25ContentFilter` (= "decongestion", massive token reduction before qwen3:4b) |
| Playwright (Python) | pulled by crawl4ai; run `crawl4ai-setup` | Browser engine under Crawl4AI | Required for JS-rendered PE sites; `crawl4ai-setup` installs Chromium correctly |
| Ollama | latest stable (Windows native install) | Serves qwen3:4b | Locked decision. Native **structured outputs** (`format=<JSON schema>`) constrain extraction to the 24-column schema — this is the reliability backbone for a 4B model. Built-in prompt-prefix KV reuse rewards a stable prompt prefix (see caching) |
| qwen3:4b | Q4_K_M (~2.5 GB, verified on ollama.com) | Extraction model | Locked decision. Supports tool use and structured output; strong instruction-following for its size. Set `num_ctx` explicitly (8192–16384) — Ollama's default context is far smaller than the model supports and silent truncation is the #1 failure mode (MEDIUM — verify default on installed version) |
| SearXNG | `searxng/searxng:latest` Docker image | Free self-hosted metasearch for firm discovery | Verified: `GET /search?q=...&format=json` returns JSON **only if** `search.formats` includes `json` in `settings.yml` (403 otherwise). Self-hosted = no rate-limit games, zero cost |
| SQLite | 3.x (Python stdlib `sqlite3`) | Source of truth: firms table (24 cols + provenance), crawl cache, queue | Local-first, zero-ops, transactional, crash-safe row-at-a-time writes (Mason's `master.json` rewrite-whole-file approach is the thing to fix). nanoclaw itself is SQLite-based — same operational story |

### Supporting Libraries (Python pipeline)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic | 2.x | Schema for the 24-column record + extraction models | `model_json_schema()` feeds Ollama's `format` param directly; `model_validate_json()` validates the response. This pairing is the extraction contract |
| ollama (python client) | ≥0.4 | Talk to Ollama | Official client; supports `format=` structured outputs and `options={"num_ctx": ...}` |
| httpx | 0.27+ | SearXNG JSON calls, health checks | Async-capable, timeouts by default |
| FastAPI + uvicorn | 0.115+ / 0.30+ | HTTP bridge for nanoclaw skills | Only the thin service layer; keep endpoints mirroring CLI commands |
| typer | 0.12+ | CLI entry points | Same functions exposed as CLI for script gates and manual runs |
| openpyxl | 3.1.x | Formatted, color-coded .xlsx export | Mason's export used it; supports conditional fills for Confidence/Needs Review. CSV via stdlib `csv` |
| tenacity | 9.x | Retry/backoff on crawl + LLM calls | Unattended heartbeat runs must not die on one flaky site |
| python-dotenv | 1.x | Config (Ollama URL, SearXNG URL, paths) | Matches your global 3-layer convention (`execution/` + `.env`) |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| Docker Desktop (WSL2 backend) | SearXNG container, nanoclaw agent containers, optional pipeline container | One shared user-defined network (`pescraper-net`) so skills can `curl http://pipeline:8000` |
| uv | Python env + deps | Fast, lockfile-based; already on this machine |
| pytest | Benchmark harness + unit tests | The accuracy spot-check harness is just a pytest suite comparing extractions to a hand-verified YAML/JSON golden set |
| `crawl4ai-doctor` | Verify browser install | Run after `crawl4ai-setup`; catches 90% of Playwright issues |

## Installation

# WSL2 (Ubuntu) — nanoclaw

# Windows host — Ollama + model

# SearXNG (docker-compose service; enable json in settings.yml)

# then in searxng/settings.yml:  search: { formats: [html, json] }

# Pipeline (WSL2)

## The LMCache-Inspired Cache (build, don't install)

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Crawl4AI AdaptiveCrawler + link heuristics | Crawl4AI `BestFirstCrawlingStrategy` deep-crawl with URL scorers | If adaptive crawl's query-driven stopping proves noisy on marketing-heavy PE sites, best-first with keyword scorers ("criteria", "strategy", "approach", "portfolio") is the deterministic fallback — Mason's crawler did essentially this by hand |
| HTTP service bridge | Subprocess: skill script-gate invokes CLI on host | Fine for heartbeat gates (they run host-side); insufficient as the only bridge because chat-triggered skills execute inside the agent container |
| SQLite stdlib | SQLAlchemy 2.x | Only if the schema grows real relations (funds, deals, people). For one wide table + cache tables it's overhead |
| openpyxl direct | pandas `.to_excel()` | If you stop caring about formatting/color-coding; pandas is a heavyweight dep for one export |
| qwen3:4b for everything | qwen3:8b for the extraction step only | If the benchmark harness shows 4b below the agreed match rate, 8b (~5 GB) is the first knob to turn — same Ollama API, zero code change |
| Ollama structured outputs | Crawl4AI's built-in `LLMExtractionStrategy` (LiteLLM → `ollama/qwen3:4b`) | Viable and keeps extraction inside Crawl4AI; but it couples extraction to the crawl pass, which breaks the content-hash cache (you want crawl and extract as separately cacheable stages). Use only for quick experiments |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| LMCache as a dependency | GPU KV-cache layer for vLLM-class serving engines; wrong abstraction for Ollama | Custom SQLite caches above |
| Windows-native Python for the pipeline | nanoclaw lives in WSL2; split environments mean path hell, duplicate Playwright installs, and `host.docker.internal` confusion in both directions | Everything except Ollama in WSL2/Docker |
| Scrapy / BeautifulSoup-from-scratch | No JS rendering (Scrapy) or no crawling logic at all (bs4); you'd rebuild what Crawl4AI ships: adaptive selection, fit-markdown, browser management | Crawl4AI 0.9.2 |
| Public SearXNG instances or Google scraping | Public instances disable `format=json` (403, verified in docs); Google scraping = bans + brittleness | Self-hosted SearXNG with `json` enabled |
| JSON file as source of truth (Mason's `master.json`) | Whole-file rewrite per firm; no concurrent readers; no indexes; corrupts on crash mid-write at 5k firms | SQLite with per-firm transactions; export to xlsx/csv is a view, not the store |
| Letting the agent LLM do extraction in-chat | Claude in the nanoclaw container costs API tokens — the exact cost the project exists to avoid | qwen3:4b via the pipeline service; the agent only orchestrates and summarizes |
| APScheduler/cron inside the Python service | Duplicate scheduler fighting nanoclaw's; heartbeats belong to nanoclaw scheduled tasks + script gates (token-free when queue is empty) | nanoclaw cron task → script gate checks queue via CLI/HTTP → wakes agent only when work exists |
| n8n / Airflow / Prefect | Whole orchestration platforms; nanoclaw + a linear Python pipeline already covers it; violates local-first simplicity | nanoclaw skills + typer CLI |

## Stack Patterns by Variant

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| crawl4ai 0.9.2 | Python ≥3.10 | Verified from PyPI metadata |
| crawl4ai 0.9.2 | Playwright (bundled) | Must run `crawl4ai-setup` in the SAME env (WSL2); browsers are per-OS |
| nanoclaw v2 | Node 20+, pnpm 10+, Docker, WSL2 on Windows | Verified from README Requirements |
| Ollama structured outputs | ollama-python ≥0.4, Pydantic v2 | `model_json_schema()` / `model_validate_json()` round-trip, per official blog |
| SearXNG JSON API | requires `search.formats: [html, json]` in settings.yml | 403 without it — verified in official API docs |
| Ollama on Windows host ↔ WSL2/containers | `http://host.docker.internal:11434` | Set `OLLAMA_HOST=0.0.0.0` if binding issues appear (MEDIUM — verify on this machine) |

## What We're Rebuilding (Mason's stack, verified 2026-07-19)

## Sources

- https://github.com/nanocoai/nanoclaw — README (v2.1.17, architecture, skills model, WSL2 requirement, Ollama provider) — HIGH
- https://raw.githubusercontent.com/nanocoai/nanoclaw/main/docs/scheduled-tasks.md — cron + script gates, wakeAgent JSON, 4×/day ungated limit — HIGH
- https://raw.githubusercontent.com/nanocoai/nanoclaw/main/docs/customizing.md — skill definition/recipe model — HIGH
- https://pypi.org/pypi/crawl4ai/json — 0.9.2 latest, Python ≥3.10 — HIGH
- https://docs.crawl4ai.com/core/adaptive-crawling/ — AdaptiveCrawler, `get_relevant_content(top_k)`, confidence_threshold — HIGH
- https://docs.crawl4ai.com/core/fit-markdown/ — PruningContentFilter/BM25ContentFilter, `result.markdown.fit_markdown` — HIGH
- https://docs.searxng.org/dev/search_api.html — `/search` params, `format=json` gating — HIGH
- https://github.com/LMCache/LMCache — KV/prefix/CacheBlend/offload concepts; serving-engine layer — HIGH (for the "reference-only" conclusion)
- https://ollama.com/library/qwen3:4b — 4.02B params, Q4_K_M 2.5 GB, tool support — HIGH
- https://ollama.com/blog/structured-outputs — `format=` JSON schema + Pydantic pattern, temperature 0 — HIGH
- https://github.com/mfairfld/Investment-Criteria-Scraper — full README: pipeline stages, deps, schema, status lifecycle — HIGH
- Ollama prompt-prefix KV reuse & default `num_ctx` behavior — training knowledge, version-dependent — MEDIUM (measure in Phase 1)

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
