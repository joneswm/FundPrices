# SPEC-005: End-of-Day FX Rates

**Status**: ✅ Complete
**Created**: 2026-09-20
**Type**: Feature
**Tracking**: [#66](https://github.com/joneswm/FundPrices/issues/66)

---

## Context

Holdings are priced in four currencies (USD, GBP, GBp, HKD) but the repository stores no
exchange rates, so a sterling view of the portfolio cannot be produced from the data.

## User Need

**As** a holder of foreign-currency instruments
**I want** a daily record of exchange rates into sterling
**So that** I can value foreign holdings in GBP from stored data alone

## Problem Statement

- No FX data is stored at all
- FX trades continuously, so "end of day" needs an explicit, reproducible definition
- The direction of a currency pair is easy to get backwards, and a wrong direction is
  silently plausible: a rate of 0.43 and one of 2.34 both look reasonable

## Proposed Solution

Snap Yahoo's daily FX bars for a configured list of pairs, stored alongside prices and
using the same windowed upsert as SPEC-003.

### Direction (confirmed with the owner)

Rates are **GBP per 1 unit of foreign currency**, for valuing foreign holdings in sterling.

| Stored name | Yahoo ticker | Rate on 2026-09-20 |
|---|---|---|
| `NZDGBP` | `NZDGBP=X` | 0.4267 |
| `SGDGBP` | `SGDGBP=X` | 0.5848 |
| `USDGBP` | `USDGBP=X` | 0.7467 |
| `HKDGBP` | `HKDGBP=X` | 0.0951 |

The owner described these as "GBP/NZD around 0.4269". By market convention `GBP/NZD`
means 2.34, the inverse. Files and headings therefore use the six-letter name and
describe the value explicitly; `GBP/xxx` is never used as a label.

Yahoo's **direct** tickers are used. Inverting `GBPNZD=X` gives a slightly different
number (0.4273 against the direct 0.4267).

### What "end of day" means

FX has no official close. Yahoo's daily bar for a date runs on London time, and a
partial in-progress bar appears for the current day.

- Each run fetches the last `SNAP_WINDOW_DAYS` days and upserts them
- Today's bar is provisional and is overwritten once complete; no flag is stored,
  because the upsert makes it self-correcting
- Saturday and Sunday bars are skipped; Yahoo shows a transient Sunday bar at market
  reopen (1 weekend row in 5,929 of `GBPUSD=X` history)
- With the 22:30 UTC schedule, the provisional value is taken just after the New York
  5pm close, the conventional FX end of day

## Success Criteria

### Functional Requirements

- Pairs configured in `fx_pairs.txt`, validated before any network call
- `data/fx_history.csv` keyed on (Pair, Date), upserted, sorted, re-runnable
- `data/latest_fx.csv` holding the most recent rate per pair
- Rates stored to 6 decimal places
- Weekend bars never stored
- An FX failure never prevents prices being written, and vice versa
- Backfill rebuilds FX by the same rule as prices

### Quality Requirements

- Unit tests use mocks only
- Coverage gates hold: ≥90% overall, ≥95% on `scrape_fund_price.py`
- Runs on Python 3.10, 3.12 and 3.14

## Out of Scope

- Converting stored prices into GBP — the daily summary (SPEC-007) may use the rates,
  but prices remain as quoted
- Intraday or tick FX
- ECB reference rates as an alternative source

## Acceptance Criteria

- [x] `fx_pairs.txt` committed with the four pairs
- [x] A local run produces `data/fx_history.csv` and `data/latest_fx.csv`
- [x] Sanity: `NZDGBP` near 0.43, `SGDGBP` near 0.58, `USDGBP` near 0.75, `HKDGBP` near
      0.095. A value near 2.3 or 10.5 means the direction is inverted
- [x] Rates at 6dp
- [x] No weekend rows
- [x] A second run changes nothing
- [x] FX history backfilled to 2023
- [x] CI green on all three Python versions

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Direction inverted, giving plausible but wrong values | Six-letter names, explicit column documentation, and an acceptance check on expected magnitudes |
| 4dp storage loses ~0.1% on `HKDGBP` (≈0.0951) | Store 6dp |
| Today's partial bar stored as final | Windowed upsert overwrites it next run |
| An FX outage blocks the price run | Failures isolated per pair; prices and FX written independently |

## Constraints

- Storage remains CSV files committed to this repository
- Reuses the existing retry and last-known-value behaviour
