# SPEC-007: Daily Price-Change Summary

**Status**: 🔄 In Progress
**Created**: 2026-09-20
**Type**: Feature
**Tracking**: [#68](https://github.com/joneswm/FundPrices/issues/68)

---

## Context

The repository now holds true-dated prices for 27 identifiers and rates for 4 currency
pairs, but reading what actually moved means opening a 24,000-row CSV.

## User Need

**As** a holder of these instruments
**I want** a daily summary of what changed
**So that** I can see the day's movements without querying the raw history

## Problem Statement

- Nothing summarises the data; the CSVs are for machines
- "Yesterday's price" is not well defined: funds, LSE, US and HK instruments have
  different holidays, and fund NAVs arrive a day later than exchange prices
- A source outage or a holiday must be distinguishable from a genuine 0% day

## Proposed Solution

Compare each instrument's latest price with the price on its **previous distinct price
date**, and publish the result as both machine-readable CSV and human-readable Markdown
in the repository.

## Success Criteria

### Functional Requirements

- Per instrument: new price and date, previous price and date, delta, percent delta
- The comparison uses the previous distinct price date for that instrument, never a
  calendar assumption
- Instruments with no fresh price are flagged as stale rather than shown as unchanged
- Instruments that fell back to a last known price are flagged as failed
- FX pairs summarised in their own section
- An aliased instrument appears once, with its aliases named
- Output is written even when part of the run failed

### Quality Requirements

- Summary construction is pure: history in, rows out, no network and no clock
- Unit tests use mocks only
- Coverage gates hold: ≥90% overall, ≥95% on `scrape_fund_price.py`
- Runs on Python 3.10, 3.12 and 3.14

## Out of Scope

- Notifications by email or issue comment
- Portfolio valuation, and converting prices into GBP with the FX rates
- Charts, and serving the summary through GitHub Pages

## Acceptance Criteria

- [ ] `data/daily_summary.csv` and `data/daily_summary.md` are produced
- [ ] The Markdown renders cleanly on GitHub
- [ ] Spot check: `JFM0003373` for price date 2026-09-17 shows New 192.43, Old 192.23
      from 2026-09-16, Delta 0.2, % Delta +0.10
- [ ] A Monday shows Friday-to-Monday deltas for exchange instruments, not 0%
- [ ] Deltas use exact decimal arithmetic, so 7.15 − 7.09 is 0.06
- [ ] FX section present, rates at 6dp
- [ ] `scrape.yml` commits `data/*.md`
- [ ] CI green on all three Python versions

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Binary floats give 0.0600000000000005 | Use `decimal.Decimal` for delta arithmetic |
| A holiday looks like a flat day | Compare against the previous distinct price date and flag staleness |
| Division by zero on a zero previous price | Percent delta left empty |
| GBp and GBP confusion in absolute deltas | Show the currency; percent deltas are unit-independent |

## Constraints

- Written into the repository alongside the data
- No new dependencies
