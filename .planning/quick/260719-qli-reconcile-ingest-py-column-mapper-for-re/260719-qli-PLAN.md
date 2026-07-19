---
quick_id: 260719-qli
mode: quick
status: ready
description: Reconcile ingest.py's column mapper for the real Capital IQ export and ingest data/capiq_test.csv into data/pipeline.db.
must_haves:
  truths:
    - map_columns resolves every header in data/capiq_test.csv (including the embedded-newline "Assets Under Management\n($000)" and "Total Investments\n(actual)" headers) to the correct FirmRecord field or pseudo-key instead of an unmapped lowercase passthrough.
    - The literal cell value "NA" (any case) is treated as missing for every direct FirmRecord field, not just the website column, so a row with "NA" in a numeric column is seeded with that field null rather than being skipped entirely on a Pydantic validation error.
    - Capital IQ's AUM figures, which are denominated in $000s, are converted to the $M scale FirmRecord.aum_musd expects (TR Advisors Ltd's "1,200,000.00" becomes aum_musd == 1200.0).
    - "Fund Status" is never written to FirmRecord.status; every firm seeded from this CSV keeps status == pending.
    - Running the real 472-row data/capiq_test.csv against data/pipeline.db produces a reported rows_read/rows_seeded/rows_skipped/rows_conflicted summary, with a pre-run backup of the database on disk and two spot-checked firms confirmed correct.
  artifacts:
    - path: src/pescraper/ingest.py
      provides: COLUMN_ALIASES entries, map_columns whitespace normalization, shared NA-as-null sentinel handling, and AUM thousands-to-millions conversion reconciled against the real Capital IQ export shape.
    - path: tests/test_ingest.py
      provides: Unit test coverage for the new alias/normalization/coercion/conversion behavior.
  key_links:
    - from: src/pescraper/ingest.py map_columns
      to: data/capiq_test.csv header row
      via: whitespace-collapsed, case-insensitive COLUMN_ALIASES lookup
    - from: src/pescraper/ingest.py ingest_csv
      to: data/pipeline.db firms table
      via: db.upsert_firm after merge.merge_firm_record, invoked directly (not through cli.py's run --csv, which also enqueues every website into the jobs table — out of this task's scope)
---

# Quick Task 260719-qli: Reconcile ingest.py column mapper for the real Capital IQ export

## Goal

`ingest.py`'s `COLUMN_ALIASES` was built against a documented, assumed Capital IQ shape before the real export existed. The real export is now at `data/capiq_test.csv` (472 rows), and its actual headers — `Entity Name`, `Web Address`, `Assets Under Management\n($000)`, `Total Investments\n(actual)`, `Sector Emphasis`, `Fund Status`, etc. — only partially match the existing aliases. Partial reconciliation work is already present but uncommitted in the working tree: `COLUMN_ALIASES` already maps `"entity name"` → `firm_name`, `"web address"` → a `_capiq_website` pseudo-key with URL-scheme normalization, and `"sector emphasis"` → `sector_tier1`, each with a passing test in `tests/test_ingest.py`. Do not duplicate that work. Finish reconciling the remaining gaps — the embedded-newline AUM/investment-count headers, "NA"-as-missing handling beyond the website column, and the thousands-to-millions AUM conversion — then run the real file through the pipeline database and report the result.

## Task 1: Finish reconciling COLUMN_ALIASES, map_columns, and ingest_csv against the real export shape

**Files**

- Modify: `src/pescraper/ingest.py`

**Action**

1. Add a module-level frozenset of missing-value sentinels (e.g. `_MISSING_SENTINELS = frozenset({"", "na", "n/a"})`) placed near `COLUMN_ALIASES`, and use it to replace the inline `{"", "na", "n/a"}` literal already present in the existing `_capiq_website` normalization block in `ingest_csv` — this is pure deduplication of logic that already exists, not new behavior.
2. Generalize the missing-value coercion: in `ingest_csv`'s first pass (the loop that builds `field_values` from direct FirmRecord-field columns), a cell whose stripped value case-insensitively matches `_MISSING_SENTINELS` must become `None` before it ever reaches `FirmRecord(**field_values)`. Today only empty string is treated as missing there, so a cell literally containing "NA" (Capital IQ's convention for "Number of Company Employees", "Total Investments", and AUM columns) raises a Pydantic validation error on a numeric field and causes `ingest_csv` to skip the entire row as malformed — silently losing every other populated column on that row.
3. Change `map_columns` to collapse internal whitespace runs (including embedded newlines) in each header before the alias lookup and before the unmapped passthrough fallback. Capital IQ wraps a column's unit onto a second line inside the header cell itself — `"Assets Under Management\n($000)"`, `"Total Investments\n(actual)"` — so the current `.strip().lower()` never produces a string that can match a single-line alias key. Apply a single regex substitution (collapse one-or-more whitespace characters to one space) to the lowercased/stripped header; keep the existing case-insensitive dict lookup and pass-through-on-miss behavior otherwise unchanged, and keep this fix general (it must not be special-cased to only these two headers).
4. Add two new `COLUMN_ALIASES` entries, keyed by the whitespace-collapsed form the header will have after step 3: `"assets under management ($000)"` → a new pseudo-key `"_capiq_aum_thousands"` (not directly to `aum_musd` — it needs a unit conversion the generic direct-field pass can't apply, mirroring how `_capiq_website` is already handled as a pseudo-key rather than a direct alias), and `"total investments (actual)"` → `"us_investments"` (a direct FirmRecord field; Capital IQ's plain integer count needs no transformation beyond the NA-as-null coercion from step 2 — Pydantic already coerces a numeric string like `"49"` to `int`).
5. In `ingest_csv`, add a normalization step alongside the existing `_capiq_website` block (same precedence pattern: only apply when the direct field isn't already populated from a clean column, and skip when the raw cell is a missing sentinel) that reads the `_capiq_aum_thousands` pseudo-key, strips thousands-separator commas, parses the remainder as a float, divides by 1000 to convert Capital IQ's $000s scale to `FirmRecord.aum_musd`'s $M scale, and assigns the result into `field_values["aum_musd"]`. Wrap the float parse in try/except so one malformed AUM cell degrades to a missing value instead of raising.
6. Do not add a `"fund status"` alias of any kind. Leaving it unmapped means the existing `key not in FirmRecord.model_fields` guard in `ingest_csv` silently drops it, so `FirmRecord.status` keeps its `pending` default rather than receiving a Capital IQ status vocabulary that has no relationship to the `FirmStatus` enum's four values.
7. Update the module's top-of-file docstring: remove the framing that the real Capital IQ export "is not yet available" and that reconciliation "is deferred until the user supplies it" — it has now been supplied and reconciled at `data/capiq_test.csv`. Replace with a short factual note that `COLUMN_ALIASES` covers both the originally-assumed shape and the verified real export headers.

**Verify**

- `uv run pytest tests/test_ingest.py -q` — all 19 existing tests still pass unmodified (this task only adds behavior, it does not change any already-tested code path's observable output).
- Confirm none of steps 1-7 touch `crawl.py`, `extract.py`, `worker.py`, `cli.py`, or any other module outside `ingest.py`.

**Done**

- `map_columns` resolves every one of the 12 real headers in `data/capiq_test.csv` (after whitespace collapse) to `firm_name`, `_capiq_website`, `sector_tier1`, `_capiq_aum_thousands`, `us_investments`, or an unmapped lowercase passthrough — never to `status`.
- `ingest_csv` treats "NA"/"N/A" (any case) as missing for every direct FirmRecord field, not only `_capiq_website`.
- The existing 19 tests in `tests/test_ingest.py` still pass.

## Task 2: Extend tests/test_ingest.py for the newly reconciled behavior

**Files**

- Modify: `tests/test_ingest.py` (extend the existing file — do not create a second test file for `ingest.py`)

**Action**

Add new tests, reusing the file's existing `_write_csv`/`_connect` helpers (do not redefine them), covering exactly the new behavior from Task 1 and nothing already covered by the 19 existing tests:

1. `map_columns` collapses embedded-newline headers to the correct pseudo-key/field: assert that mapping `["Assets Under Management\n($000)", "Total Investments\n(actual)"]` resolves to `_capiq_aum_thousands` and `us_investments` respectively.
2. `ingest_csv` converts a Capital IQ thousands-denominated AUM cell into the millions-scale `aum_musd` — build a row shaped like the real export (`Entity Name`, `Web Address`, and `Assets Under Management\n($000)` = `"1,200,000.00"`) and assert the seeded firm's `aum_musd == 1200.0`.
3. `ingest_csv` treats "NA" as missing for a direct numeric field without skipping the row — build a row where `Total Investments\n(actual)` = `"NA"` and assert `rows_skipped == 0`, `rows_seeded == 1`, and the seeded firm's `us_investments is None`.
4. `ingest_csv` maps a populated `Total Investments\n(actual)` cell to `us_investments` — a row with that column set to `"49"` seeds `us_investments == 49`.
5. `ingest_csv` never writes `Fund Status` into `FirmRecord.status` — a row carrying a `Fund Status` column with some arbitrary non-empty value (not one of the four `FirmStatus` enum values) still seeds with `status == FirmStatus.PENDING`.
6. One combined test using all 12 real header columns from `data/capiq_test.csv` in a single row modeled on the file's actual "Borgman Capital LLC" row (`Web Address` = `"www.borgmancapital.com"`, `Assets Under Management\n($000)` = `"NA"`, `Total Investments\n(actual)` = `"19"`, `Fund Status` = `""`) — assert `firm_name`, the normalized `website` (`https://www.borgmancapital.com`), `sector_tier1`, `us_investments == 19`, `aum_musd is None`, and `status == FirmStatus.PENDING` all resolve together correctly in one row.

**Verify**

- `uv run pytest tests/test_ingest.py -q` — all tests (the existing 19 plus the new ones added here) pass.

**Done**

- Every new behavior introduced in Task 1 has a dedicated or combined regression test in `tests/test_ingest.py`.
- No new test file was created; `tests/test_ingest.py` remains the single home for `ingest.py` coverage.

## Task 3: Run the real Capital IQ export against data/pipeline.db and report the result

**Files**

- Read/execute only (no source changes): `data/capiq_test.csv`, `data/pipeline.db`
- Produces (runtime data, not committed — already covered by `.gitignore`'s `*.db*` rule): timestamped backup copies of `data/pipeline.db` and its `-wal`/`-shm` siblings

**Action**

1. Before mutating anything, copy `data/pipeline.db`, `data/pipeline.db-wal`, and `data/pipeline.db-shm` (whichever exist) to timestamped `.bak` siblings — this run merges into 73 firms already seeded in the live database from prior phases, so a rollback path must exist first.
2. Invoke `ingest_csv` directly against the real database using the same connection pattern `db.py` and `cli.py` already establish: `db.init_db()` followed by `db.connect()` (there is no `db.get_connection` — confirmed by reading `db.py`; do not invent new plumbing or add a new CLI command/script file). Do this as a one-off invocation, not through `cli.py`'s `run --csv` command — that command also enqueues every ingested website into the `jobs` table via `queue.enqueue`, which is outside this task's scope and would leave the pipeline in a state ready to trigger real crawl/extract work this task never asked for.
3. Call `ingest_csv("data/capiq_test.csv", conn)` and capture the returned `IngestSummary`.
4. Print the four `IngestSummary` counters: `rows_read`, `rows_seeded`, `rows_skipped`, `rows_conflicted`.
5. Spot-check two firms by reading them back with `db.get_firm`:
   - `"https://www.tr-capital.com"` (TR Advisors Ltd) — expect `aum_musd` approximately `1200.0` (converted from the `"1,200,000.00"` $000s cell) and `us_investments == 49`.
   - `"https://www.borgmancapital.com"` (Borgman Capital LLC) — expect `aum_musd is None` (its AUM cell is literally `"NA"`), `us_investments == 19`, and `status == FirmStatus.PENDING` (its `Fund Status` cell is blank).
6. Close the connection and report the four counters plus both spot-check results in the task SUMMARY.

**Verify**

- The printed counters show `rows_read == 472` and `rows_skipped == 0` (every row in the file has `Entity Name` populated, so none should be dropped for missing identity).
- Both spot-checked firms are present in `data/pipeline.db` after the run and match the values in step 5.
- A pre-run backup of `data/pipeline.db` (and its `-wal`/`-shm` siblings, if they existed) is present on disk after the run.

**Done**

- `data/pipeline.db` has been seeded from the real 472-row `data/capiq_test.csv` via `ingest_csv`.
- A pre-run backup of `data/pipeline.db` exists on disk.
- `rows_read`/`rows_seeded`/`rows_skipped`/`rows_conflicted` and both spot-checked records are reported to the user.
