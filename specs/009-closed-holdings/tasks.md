# Tasks: One-Off Imports for Closed Holdings

**Spec**: SPEC-009
**Status**: ✅ Complete
**Created**: 2026-09-21

---

## Task Overview

RED-GREEN-REFACTOR. Tests first. Written retrospectively from the commit history.

**Total Tasks**: 5

---

## Task 1: Configuration

### Acceptance Criteria
- [x] `read_closed_holdings()` returns `ClosedHolding` tuples
- [x] Comments and blank lines ignored; deprecated source codes canonicalised
- [x] Short lines, bad dates, reversed windows and repeated identifiers raise, naming the line
- [x] Committed identifiers are disjoint from `funds.txt`

## Task 2: The `IV` source

### Acceptance Criteria
- [x] `fetch_investing_quotes()` returns quotes oldest first
- [x] float32 noise removed without rounding away a half-penny tick
- [x] Undated or unparseable rows skipped; an empty or null payload raises `ValueError`
- [x] Routed by `scrape_fund_quotes()`; needs no browser

## Task 3: The import

### Acceptance Criteria
- [x] Rows stored under the identifier, clipped to the window, with the configured currency
- [x] A currency mismatch skips the holding and records a failure
- [x] Upsert only, idempotent, other funds untouched
- [x] Only `prices_history.csv` is written
- [x] A failed holding is isolated and reported
- [x] The last day of a window is imported whatever the source's end-date convention

## Task 4: Keeping closed holdings out of "current" outputs

### Acceptance Criteria
- [x] A rebuild preserves imported rows
- [x] A rebuild does not add them to `latest_prices.csv` or write `.price` files for them
- [x] The rolling window excludes them even when their dates fall inside it

## Task 5: CLI, data and documentation

### Acceptance Criteria
- [x] `--import-closed` parsed; `main()` runs the import and nothing else
- [x] The report reaches stdout and the Actions job summary; failures exit non-zero
- [x] Eight identifiers imported: 1,748 rows, no weekend rows, duplicates or missing currencies
- [x] README, AGENTS.md, constitution, architecture and API reference updated
