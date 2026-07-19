---
status: passed
phase: 02-core-pipeline-single-firm
score: 5/5
verified: 2026-07-19
---

# Phase 2 Verification: Core Pipeline, Single Firm

1. `run-firm` produces and persists the 24-column row with null-for-unknown behavior.
2. Page selection, 403 fallback, skip lists, decongestion, and no-criteria handling pass.
3. Every non-null mapped extraction now writes an auditable provenance row; quote-less values explicitly persist `quote=NULL` and `source_page_url=NULL` instead of disappearing.
4. Confidence and Needs Review are computed in code.
5. Capital IQ CSV ingest and null-safe/conflict-aware merge rules pass.

The prior PIPE-05 gap is closed by `test_run_firm_async_records_quote_less_extracted_value`.
Final evidence is the full suite plus the focused Phase 2 tests recorded in the milestone audit.
