# SPEC-003: True Price Dates and Currency

**Status**: ✅ Complete
**Created**: 2026-09-20
**Type**: Foundational Enhancement
**Tracking**: [#64](https://github.com/joneswm/FundPrices/issues/64)

---

## Context

Prices have been stored against the date they were *scraped*, with no record of the
currency they are quoted in. Analysis of `data/prices_history.csv` on 2026-09-20 showed
this produces measurably wrong data, and it blocks the FX, backfill and daily-summary
features (SPEC-005, SPEC-006, SPEC-007).

## User Need

**As** a fund-price data consumer
**I want** each stored price to carry the date the source says it is for, and its currency
**So that** I can compute correct day-on-day changes and convert between currencies

## Problem Statement

Measured on the existing history:

1. **Dates are scrape dates.** For the JPMorgan ASEAN fund, 154 of 202 matched NAVs are
   stored one day late, and 38 are three days late across weekends.
2. **Weekends are carry-forwards.** 87 of QQQ's 305 rows fall on a Saturday or Sunday and
   repeat Friday's price. A daily delta would read 0% every weekend.
3. **Units are mixed and unrecorded.** Yahoo quotes `IGWD.L` in pence (13339 GBp) and
   `DPYG.L` in pounds (5.061 GBP). Nothing distinguishes them.
4. **History is dirty.** `IE0008368742` has duplicate rows on 206 dates, and 5 `Error:`
   strings are stored as prices. `write_results()` de-duplicates on date alone, not on
   (Fund, Date).
5. **Mutual fund prices are stale.** `yf.Ticker("0P00000YAN").info` returned 192.23 when
   the latest daily bar was 192.43. The summary endpoint also carries no date.
6. **The snap runs before the market closes.** Cron is `1 21 * * *`; the US winter close
   is 21:00 UTC.
7. **A single failure suppresses all output.** `main()` raises `SystemExit(1)` when any
   fund falls back, which skips the workflow's commit step entirely.

## Proposed Solution

Fetch **dated windows** of quotes rather than a single undated price, and upsert them on a
(Fund, Date) key. The daily run requests the last 10 days; SPEC-006 reuses the same
fetchers with a 2023 start date. A missed or failed day then heals itself on the next run.

## Success Criteria

### Functional Requirements

- Every stored price carries the price date reported by its source
- Every stored price carries its currency exactly as reported, keeping `GBp` distinct from `GBP`
- History holds exactly one row per (Fund, Date)
- Unusable values (`Error: ...`, `N/A`) are never written to history
- No row is written for a date the source does not report a price for
- Price precision is never reduced relative to what the source publishes
- A run that fails for some funds still publishes everything it obtained

### Quality Requirements

- Re-running with unchanged data leaves output files byte-identical
- Unit tests use mocks only; no network access
- Coverage gates hold: ≥90% overall, ≥95% on `scrape_fund_price.py`
- Runs on Python 3.10, 3.12 and 3.14

## Out of Scope

- Repairing existing rows — SPEC-006 rebuilds them
- Identifier aliases — SPEC-004
- FX rates — SPEC-005
- Converting pence to pounds; prices stay as quoted (owner decision)

## Acceptance Criteria

- [x] `prices_history.csv`, `latest_prices.csv` and `prices_history_90_days.csv` carry a
      `Currency` column appended after `Price`
- [x] Dates in those files are price dates, not scrape dates
- [x] Running the scraper twice produces no diff on the second run
- [x] No stored price contains float noise
- [x] `IDTG.L` is published at 4dp or better
- [ ] CI green on all three Python versions with both coverage gates

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| FT's historical endpoint is unofficial and may break | Fall back to the existing Playwright scrape per fund |
| float32 bar values introduce noise (`124.87000274658203`) | Format via shortest float32 round-trip |
| Legacy 3-column rows fail to parse | Readers tolerate them, defaulting `Currency` to empty |
| Scrape-dated and true-dated rows coexist until SPEC-006 | Accepted and documented; the rebuild resolves it |

## Constraints

- Storage remains CSV files committed to this repository
- Backwards compatible column order: `Fund,Date,Price` stay as the first three columns
