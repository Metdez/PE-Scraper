---
phase: 02-core-pipeline-single-firm
plan: 04
status: complete
---

# 02-04 Summary: extract_schemas.py, extract.py

**Note:** no `02-04-PLAN.md` exists — the GSD planning framework (`gsd-core`, `/gsd-*` commands) was not installed on this machine when this session picked the project back up, so this plan/execute pair was built directly from `02-RESEARCH.md`'s already-detailed Pattern 4/5 and Pitfalls 2/3/5 (which fully specified the call shape, schema split, and defenses) rather than through a separate GSD planning pass. Implementation follows RESEARCH.md's design without deviation.

- `src/pescraper/extract_schemas.py` — `FinancialCriteria` and `CategoricalCriteria` (RESEARCH Pattern 5's field-group split, not the bare 24-field `FirmRecord`), each numeric/categorical field paired with a sibling `*_quote` field; `deal_types` constrained to a `Literal` enum (Buyout/Recap/Minority/Growth Equity/Venture/Mezzanine Debt/Other).
- `src/pescraper/extract.py` — two `ollama.chat()` calls per firm (financial + categorical), both `think=False` + `num_ctx=16384` (Pitfall 2 — Ollama's default 4096 silently truncates a multi-page prompt) + hardened `strip_think` that handles a leaked reasoning block with no opening `<think>` tag (Pitfall 3). Numeric sanity clamp (`apply_numeric_clamp`): any `*_musd` value whose magnitude exceeds 100,000 is assumed raw-dollar and divided by 1e6, logged as a warning — defends against the exact `$40M -> 40001000` bug this project's live probe found (Pitfall 5). `assemble_pages()` concatenates selected pages under a 6,000-char/page, 20,000-char-total budget, dropping lowest-priority (later) pages entirely rather than partially truncating across the board.

15 tests, offline, mocking `ollama.chat` per `test_doctor.py`'s established pattern — covers schema round-trip, both think-strip cases (anchored/unanchored), and the sanity clamp on the exact `5_000_000 -> 5.0` bug case.
