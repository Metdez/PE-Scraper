---
phase: 02-core-pipeline-single-firm
plan: 05
status: complete
---

# 02-05 Summary: ingest.py — Capital IQ CSV ingest

**Note:** no `02-05-PLAN.md` exists (see 02-04-SUMMARY.md — GSD framework unavailable this session); built directly from `02-RESEARCH.md` Pattern 7 and `02-CONTEXT.md`'s "Capital IQ Seeding & Merge Rules" section.

- `src/pescraper/ingest.py` — `row_to_firm_record(row) -> FirmRecord | None` and `ingest_csv(path) -> list[FirmRecord]`. Flexible, case-insensitive column mapper (`DIRECT_COLUMN_ALIASES`) covers the documented 24-column shape (Requirements.md's sample rows) plus common header variants (e.g. `"Company"` -> `firm_name`, `"URL"` -> `website`). `RANGE_COLUMN_ALIASES` + `parse_range()` regex-splits free-text combined-range cells (e.g. `"EBITDA Range": "$5-25M"` -> `(5.0, 25.0)`, with `$1-2B` scaling to millions); a direct min/max column takes priority over a range column if both are present. Clean numeric cells pass through as a no-op. Rows with no usable `firm_name` are skipped (logged), not a hard failure for the whole file.

12 tests, offline, including a case mirroring Requirements.md's actual sample row shape.

**Deferred (per CONTEXT.md, not blocking):** the real Capital IQ CSV export isn't available yet — the user will supply it later. The alias list is built against the documented expected shape and will need reconciling against the real export's actual headers when it arrives. `ingest_csv`/`row_to_firm_record` are not yet wired into any CLI command — that's Phase 4's batch-ingest path (`run-firm <url>` deliberately does not consult seed data, per CONTEXT.md).
