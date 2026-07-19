---
phase: 02-core-pipeline-single-firm
plan: 02
status: complete
---

# 02-02 Summary: db.py — get_firm, insert_extraction

Implemented exactly per plan, plus one unplanned fix surfaced during 02-06 integration testing.

- `get_firm(conn, website) -> FirmRecord | None` — parameterized read, converts `status` TEXT back to `FirmStatus` and `needs_review` INTEGER back to `bool`.
- `insert_extraction(conn, *, firm_website, field, value, quote, source_page_url, model, prompt_version, content_hash) -> None` — append-only, parameterized, commits per call.

17 tests including a SQL-metacharacter round-trip case (`'; DROP TABLE firms; --` as a field value) confirming no injection surface.

**Unplanned fix (found live, not in the original plan scope):** `ALLOWED_TRANSITIONS` made `complete`/`needs_review` fully terminal (Phase 1). This makes re-checking an already-processed firm — the documented 90-day staleness re-queue requirement — impossible: `advance_status` raised `ValueError: Disallowed status transition: 'needs_review' -> 'in_progress'` the moment 02-06's integration test tried to re-run `run-firm` on a firm that had already reached a terminal state. Fixed by allowing `complete -> in_progress` and `needs_review -> in_progress` (re-check re-entry) while still disallowing any direct jump back to `pending` (Phase 1's existing locked test for that case still passes unchanged). New transition is covered by an added case in `test_status_lifecycle_walk_and_rejects_disallowed`.
