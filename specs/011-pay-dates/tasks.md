# Tasks: Dividend Pay Dates from the Issuer

**Spec**: SPEC-011
**Status**: ✅ Built, on branch `pay-dates` (not yet merged)
**Created**: 2026-10-26

---

## Task Overview

RED-GREEN-REFACTOR. Tests first; every task has its RED and GREEN commits, and a REFACTOR
commit at the end.

**Total Tasks**: 6

---

## Task 1: `dividend_sources.txt`

### Acceptance Criteria
- [x] `read_dividend_sources()` returns `DividendSource` tuples
- [x] Every malformed field fails with the line number; repeats, an alias of the same
  instrument and unknown identifiers too
- [x] A missing file is no entries; the shipped file is valid against `funds.txt`

## Task 2: The iShares page

### Acceptance Criteria
- [x] `parse_ishares_distributions()` reads the recorded IGLS.L and FLOS.L pages
- [x] A page without the table, a ragged table and a bad date are errors
- [x] `fetch_ishares_distributions()` is one GET with a timeout and an HTTP error check

## Task 3: Merging into the history

### Acceptance Criteria
- [x] Pay date added to a Yahoo row; row inserted when Yahoo lacks it; `IS` source
- [x] Amount: Yahoo's kept when they agree, the issuer's when they differ, pence converted
- [x] A date a day out is one dividend; authority `IS` > `YA` > `config`; idempotent

## Task 4: Declared rows

### Acceptance Criteria
- [x] A future issuer row is the `declared` upcoming row with its amount and pay date
- [x] It replaces the estimate and Yahoo's declaration; the summary lists it once

## Task 5: Orchestration

### Acceptance Criteria
- [x] `update_dividends()` fetches, merges and publishes; one failing page costs nothing else
- [x] `backfill_dividends()` rebuilds `YA` and `IS` rows; an FT-priced fund is rebuilt alone
- [x] `main()` validates the file first and passes the sources to both modes

## Task 6: Documentation and the real run

### Acceptance Criteria
- [x] README, AGENTS.md, architecture, API reference, status, specs index updated
- [x] One real run against a scratch copy of `data/` for IGLS.L, FLOS.L, QQQ and
  IE00B0M63516, before and after
