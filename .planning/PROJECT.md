# PE Scraper

## What This Is

A locally-run agent platform that builds and maintains a structured dataset of US private equity firms' investment criteria. It loops through firm websites, uses Crawl4AI to grab the handful of pages most likely to hold criteria, decongests the HTML, and has a local LLM (qwen3:4b via Ollama) extract EBITDA/revenue/EV ranges, check sizes, deal types, and sectors into a 24-column dataset — all orchestrated through nanoclaw skills so you can batch-run a CSV, ask about a single firm from chat, or let scheduled heartbeats discover new firms via self-hosted SearXNG. Zero marginal API cost.

## Core Value

Turn a raw list of PE firm URLs into an accurate, continuously self-updating, exportable investment-criteria dataset at zero marginal API cost.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Core pipeline: CSV of firm URLs → Crawl4AI page selection (~5 best pages/site) → HTML decongestion → qwen3:4b extraction → rows in the 24-column schema → Excel/CSV export
- [ ] nanoclaw skills layer: batch CSV input skill, single-URL "research this firm" chat skill, freeform find/ask skill
- [ ] SearXNG discovery: self-hosted SearXNG finds US PE firms not yet in the dataset and queues them for scraping
- [ ] Heartbeats: scheduled (e.g. overnight) runs that scrape queued firms and re-check stale ones
- [ ] Custom caching layer (LMCache-inspired): avoid re-crawling unchanged pages and re-spending tokens — content hashing, prompt-prefix reuse, extraction result cache
- [ ] Accuracy benchmark: spot-check harness comparing local-model extractions against a hand-verified sample at an agreed match rate
- [ ] Confidence + Needs Review flags per firm so weak extractions are surfaced, with every extracted value traceable to its source page

### Out of Scope

- Phone integration (nanoclaw → phone) — explicitly deferred to v2 in the founding conversation
- PowerPoint/Excel trend reports with citations ("what does the data mean") — v2; depends on a trustworthy dataset existing first
- SEC filing watcher for newly formed firms — v2 discovery channel; SearXNG covers discovery for v1
- Claude/paid-API extraction — local-only decision; qwen3:4b does 100% of extraction (Haiku cost ~$7/500 firms)
- Full 5,000-firm production run as a v1 gate — v1 proves the loop on a short sample batch; scale-up follows
- Web app UI — nanoclaw chat + Excel export are the interfaces
- LMCache as a dependency — it requires vLLM; we build our own cache using its ideas

## Context

- **Reference implementation:** Mason Fairfield's Investment-Criteria-Scraper (https://github.com/mfairfld/Investment-Criteria-Scraper) already does crawl → extract → table with Claude Haiku. Decision: reference only — mine its criteria prompts, page-selection heuristics, and column schema, but rebuild fresh with clean architecture.
- **Seed data:** ~5,000 US private equity firms exported from Capital IQ as a CSV of URLs (user retains access from a prior internship).
- **Reference repos:** nanoclaw (https://github.com/nanocoai/nanoclaw.git — agent framework this is built on), Crawl4AI (https://github.com/unclecode/crawl4ai.git — crawling), SearXNG (https://github.com/searxng/searxng — free self-hosted metasearch), LMCache (https://github.com/LMCache/LMCache — KV-cache ideas only)
- **24-column schema** (from Requirements.md sample rows): Firm Name, Type, State, City, Website, US Investments, Rev Min ($M), Rev Max ($M), EBITDA Min ($M), EBITDA Max ($M), EV Min ($M), EV Max ($M), Check Min ($M), Check Max ($M), Deal Types, Sector Tier 1, AUM ($M), Activity, Last Deal, Fund Name, Confidence, Needs Review, Last Checked, Status
- **Deal types vocabulary:** Buyout, Recap, Minority, Growth Equity, Venture, Mezzanine Debt, Other
- **Known accuracy reality:** the crawl misses pages when link structures differ; extraction is imperfect — hence Confidence/Needs Review columns and the benchmark requirement
- **Prerequisites** (install via safest standard package manager): Git, Docker, Node.js 20+, pnpm 10+, Ollama, qwen3:4b

## Constraints

- **Cost**: Zero marginal API spend — local model only, self-hosted search only. This is the founding motivation.
- **Tech stack**: nanoclaw is the agent framework; everything ships as nanoclaw skills/hooks. Crawl4AI for crawling. Ollama serving qwen3:4b for extraction. SearXNG for search.
- **Platform**: Windows 11 host; Docker available for containerized pieces (SearXNG, nanoclaw containers)
- **Data**: Deliverable is local Excel/CSV; a local store (e.g. SQLite) may be source of truth, but no cloud services in the data path
- **Unattended operation**: heartbeat runs must work without a human watching — errors get logged and flagged, not crash the loop

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Dedicated git repo in Desktop/PE Scraper | Home directory was itself a git repo; nested dedicated repo gives clean history and safe atomic commits | — Pending |
| Local-only extraction (qwen3:4b via Ollama) | Haiku cost ~$7/500 firms; local is free and the whole point | — Pending |
| Mason's scraper is reference-only | Rebuild fresh with clean architecture; mine prompts, heuristics, schema | — Pending |
| LMCache reference-only; build custom cache | LMCache requires vLLM (not Ollama); we want its token-saving ideas, not its stack | — Pending |
| Local Excel/CSV as deliverable | Local-first ethos; shareable exports without cloud dependency | — Pending |
| Phone + trend reports deferred to v2 | Core loop must be trustworthy before presentation layers | — Pending |
| v1 proven on short sample batch, not full 5k | Fast validation loop; scale is an ops exercise once accuracy is proven | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-19 after initialization*
