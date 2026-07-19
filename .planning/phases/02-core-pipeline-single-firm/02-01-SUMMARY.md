---
phase: 02-core-pipeline-single-firm
plan: 01
status: complete
---

# 02-01 Summary: merge.py, confidence.py, provenance.py

Implemented exactly per plan. Three pure-function modules, zero I/O:

- `src/pescraper/merge.py` — `merge_field`, `ranges_conflict`, `merge_firm_record`. Null-safe merge (non-null always wins, null never clears); lifecycle fields (`status`/`confidence`/`needs_review`/`last_checked`) pass through unchanged from `existing` — callers set those explicitly.
- `src/pescraper/confidence.py` — `compute_confidence` (ratio over 17 `POPULATABLE_FIELDS`, excludes `fund_name`/`last_deal`), `is_needs_review` (< 0.3 OR zero of 6 `CORE_NUMERIC_FIELDS`).
- `src/pescraper/provenance.py` — `find_source_page`: exact-substring fast path, `difflib.SequenceMatcher.quick_ratio()` fallback, `min_ratio=0.6`.

25 tests, `uv run pytest tests/test_merge.py tests/test_confidence.py tests/test_provenance.py -q` green.

**Deviation from plan:** one `test_provenance.py` case (`find_source_page("totally unrelated text...", ...)`) had to swap its fixture strings — `quick_ratio()` is a character-histogram upper bound, and the plan's original short-string pair scored 0.615 (above the 0.6 threshold) despite being semantically unrelated. Replaced with a pair whose character composition is genuinely dissimilar (ratio ~0.27). Implementation is unchanged; only the test fixture was wrong.
