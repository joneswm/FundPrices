# Tasks: The Dividend Calendar

**Spec**: SPEC-010
**Status**: ✅ Built, on branch `dividends-calendar`
**Created**: 2026-10-26

---

## Task Overview

RED-GREEN-REFACTOR. Tests first; every task has its RED, GREEN and REFACTOR commits.

**Total Tasks**: 8

---

## Task 1: `distributions.txt`

### Acceptance Criteria
- [x] `read_distributions()` returns `Distribution` tuples, dates and amounts sorted together
- [x] Every malformed field fails with the line number; repeats and unknown identifiers too
- [x] A missing file is no entries; the shipped file has a header and no entries

## Task 2: The Yahoo routes

### Acceptance Criteria
- [x] `fetch_yahoo_dividends()` reads the `Dividends` column unadjusted, in the price currency
- [x] `period="max"` without a start; amounts are plain decimal text
- [x] `fetch_yahoo_declared()` uses the calendar, falls back to `info`, ignores past ex-dates
- [x] A pay date not after the ex-date is left empty

## Task 3: The history file and the daily fetch

### Acceptance Criteria
- [x] Sorted, LF-ended `dividends_history.csv`, read back keyed on `(Fund, ExDate)`
- [x] A changed amount replaces a row; `config` never replaces a source row
- [x] One fetch per YA instrument, published under every alias, retried, failures isolated
- [x] A failing calendar lookup warns and does not fail the run

## Task 4: Projections

### Acceptance Criteria
- [x] Frequency from the median gap in the twelve months to the last ex-date
- [x] Next ex-date rolled forward to today or later; last amount; pay lag when known
- [x] A silent payer has no estimate; a schedule line projects its next XD
- [x] `config` history rows only for a line with amounts and `as-of`

## Task 5: The upcoming file

### Acceptance Criteria
- [x] Declared replaces estimated for the period; a moved declaration replaces the old one
- [x] Rows leave 7 days after the ex-date once in the history, 30 regardless
- [x] Aliases, schedules, closed holdings and removed funds handled

## Task 6: Orchestration

### Acceptance Criteria
- [x] `update_dividends()` reads everything once, then a 400-day window; never deletes
- [x] `backfill_dividends()` replaces YA rows from the start date, keeps `config` rows
- [x] A failing instrument keeps its rows and is reported

## Task 7: The summary

### Acceptance Criteria
- [x] New ex-dates, new pay dates and estimate-to-declared changes are listed once per instrument
- [x] `daily_summary.md` has the section; `daily_summary.csv` is unchanged

## Task 8: CLI, wiring and documentation

### Acceptance Criteria
- [x] `main()` validates `distributions.txt` first and runs the update after FX
- [x] A crash in the update costs neither the summary nor the exit code
- [x] `--backfill-dividends [--from]` runs alone and exits non-zero on failures
- [x] README, AGENTS.md, architecture, API reference, status and specs index updated
- [x] One real run for three instruments checked against the shapes
