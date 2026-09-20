# SPEC-006: History Backfill and Rebuild

**Status**: 🔄 In Progress
**Created**: 2026-09-20
**Type**: Data Remediation
**Tracking**: [#67](https://github.com/joneswm/FundPrices/issues/67)

---

## Context

SPEC-003 made new prices carry true price dates and currencies, but the existing
`data/prices_history.csv` was written under the old rules and still holds scrape dates,
weekend carry-forwards, duplicates and stored error strings. SPEC-003 deliberately left
those rows alone.

## User Need

**As** a fund-price data consumer
**I want** the whole stored history to use the dates the sources actually published
**So that** day-on-day changes are correct across the entire series, not only recent rows

## Problem Statement

Measured on the file as committed:

- Dates are scrape dates, typically one day after the true price date and three across weekends
- ~29% of exchange-instrument rows are weekend carry-forwards
- 206 dates carry duplicate `IE0008368742` rows
- 5 rows store `Error: ...` strings in place of prices
- History begins 2025-10-19, while the owner wants data back to 2023
- Legacy rows have no currency

**Decision (owner, confirmed): rebuild rather than prepend.** Adding older rows in front
would leave every defect above in place and mix two meanings of `Date` in one file.

## Proposed Solution

Reuse the SPEC-003 fetchers with a 2023 start date. For each instrument that fetches
successfully, delete its rows from the start date onward and insert the fetched quotes.
An instrument that fails keeps its existing rows untouched.

Deleting is necessary rather than upserting alone: carry-forward and scrape-dated rows
sit on dates the source never reports, so an upsert would leave them behind.

## Success Criteria

### Functional Requirements

- A `--backfill --from YYYY-MM-DD` mode, separate from the daily run
- Every instrument in `funds.txt` rebuilt from its source, under all of its identifiers
- An instrument whose fetch fails keeps its existing data and is reported
- Rows before the start date, and rows for identifiers no longer configured, are preserved
- The run never loses rows: repeated rebuilds converge, and are byte-identical when the source answers consistently
- `latest_prices.csv`, `prices_history_90_days.csv` and the `.price` files are regenerated
- FX pairs are rebuilt by the same mechanism once SPEC-005 exists
- A reconciliation report is printed and added to the Actions job summary

### Quality Requirements

- Unit tests use mocks only
- Coverage gates hold: ≥90% overall, ≥95% on `scrape_fund_price.py`
- Runs on Python 3.10, 3.12 and 3.14

## Out of Scope

- Snapping FX rates — SPEC-005 adds the source; this spec only rebuilds what exists
- The daily summary — SPEC-007
- Changing the storage format, which SPEC-003 settled

## Acceptance Criteria

- [ ] `python scrape_fund_price.py --backfill --from 2023-01-01` rebuilds history
- [ ] Every identifier's first date is 2023-01-02/03, or its listing date if later
- [ ] Zero Saturday or Sunday rows
- [ ] Zero duplicate (Fund, Date) keys
- [ ] Zero `Error:` or `N/A` prices
- [ ] Every row carries a currency
- [ ] `JFM0003373` and `0P00000YAN` hold identical series
- [ ] `JFM0003373` on 2026-09-17 reads 192.43, having been stored against 2026-09-18
- [ ] A repeated run loses no rows (FT intermittently omits rows, so the file converges upward rather than being byte-identical every time)
- [ ] `backfill.yml` runs from the Actions tab and commits the result
- [ ] CI green on all three Python versions

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| A failed fetch could destroy unreplaceable rows | Delete only for instruments that fetched successfully |
| An instrument that changed quoting unit would be mislabelled throughout | Warn when a day-on-day move exceeds a factor of 50 |
| A split inside the window would distort the series | Warn if the split column is non-zero in range |
| FT's unofficial endpoint could rate-limit a 26-fund run | Sequential, with a pause between funds |
| FT intermittently omits rows, so a rebuild could delete real trading days | Keep stored rows the source omits when they already carry a currency, i.e. were themselves source-derived |
| The rebuild replaces a committed data file | Git history retains the previous version |

## Constraints

- Manual trigger only; never scheduled
- Must not run concurrently with the daily scrape
