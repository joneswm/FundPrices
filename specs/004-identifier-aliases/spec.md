# SPEC-004: Identifier Aliases

**Status**: ✅ Complete
**Created**: 2026-09-20
**Type**: Enhancement
**Tracking**: [#65](https://github.com/joneswm/FundPrices/issues/65)

---

## Context

The JPMorgan ASEAN Fund is the only instrument sourced from Morningstar, configured as
`MS,JFM0003373`. Morningstar's site has proved unreliable, offers no verified route to
historical data, and requires a browser. Yahoo carries the same share class as
`0P00000YAN`, but changing the identifier outright would split the fund's history in two.

## User Need

**As** a fund-price data consumer
**I want** a fund fetched from one source to be published under more than one identifier
**So that** I can move a fund to a better source without breaking anything keyed on its
old identifier

## Problem Statement

- `MS,JFM0003373` depends on a site that returned "Runtime Error" throughout 2026-09-20
- Morningstar is the only source still requiring Playwright on its normal path, and it
  costs three 60-second timeouts per run when down
- It has no verified backfill route, blocking SPEC-006 for this fund
- Simply renaming it to `0P00000YAN` would strand ~11 months of `JFM0003373` history

Evidence the instruments are the same (ISIN `HK0000055555`, Bloomberg `JFASEAI HK`):
202 of 207 distinct prices scraped from Morningstar (97%) appear identically, to the
cent, in Yahoo's history for `0P00000YAN`. The last four NAVs match exactly.

## Proposed Solution

An optional third field in `funds.txt` lists extra identifiers to publish under. The
price is fetched once from the second field and written under every identifier.

```
GF,0P00000YAN,JFM0003373
```

## Success Criteria

### Functional Requirements

- A fund is fetched once regardless of how many identifiers it publishes under
- Every output carries a row or file per identifier, with identical date, price and currency
- Two-field lines behave exactly as before
- Retries and the last-known-price fallback run once per fund, and the fallback may use
  any alias's stored price
- A fund is reported at most once in `failures`
- Configuration errors are rejected before any network call, naming the line at fault

### Quality Requirements

- Unit tests use mocks only
- Coverage gates hold: ≥90% overall, ≥95% on `scrape_fund_price.py`
- Runs on Python 3.10, 3.12 and 3.14

## Out of Scope

- Backfilling history for the new identifier — SPEC-006
- Renaming the misleading `GF` source code, which means "Yahoo Finance API"
- Removing `MS` as a supported source code; it stays, simply unused

## Acceptance Criteria

- [x] `funds.txt` accepts `SOURCE,LOOKUP_ID[,ALIAS[;ALIAS...]]`
- [x] `data/latest_0P00000YAN.price` and `data/latest_JFM0003373.price` hold the same value
- [x] Both identifiers have rows for the same dates in `prices_history.csv`
- [x] A duplicated identifier anywhere in `funds.txt` is rejected with its line number
- [x] One fetch per fund, asserted by test
- [x] CI green on all three Python versions

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| `read_fund_ids()` splits on the first comma, so a third field breaks the lookup | Replace with a parser returning `FundSpec`; keep `read_fund_ids()` as a compatibility wrapper |
| On day one `0P00000YAN` has no stored price while `JFM0003373` has 11 months | Fallback checks the lookup id, then each alias in order |
| Aliases could collide with another fund's identifier | Reject duplicates across the whole file, before fetching |

## Constraints

- `funds.txt` stays a plain text file, one instrument per line
- Existing two-field lines must not change meaning
