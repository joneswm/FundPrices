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

FX has no official close. As shipped, this spec took Yahoo's daily bar for a date,
which runs on London time, with the current day's partial bar stored as a provisional
value and overwritten by the upsert once complete; the single evening run of the time
read that value just after the New York 5pm close, the conventional FX end of day.

#80 replaced that rule, and Yahoo's daily bar is no longer used for recent days: its
Close is the rate at the start of the day (London midnight), not its close.

- A day's rate is the New York close: the rate at 17:00 in New York, read from Yahoo's
  hourly bars (the close of the bar starting at 16:00 New York). New York's own clock
  is used, so the cut is 21:00 UTC in summer and 22:00 UTC in winter
- A day is stored only once its cut has passed, so no rate is provisional and a run at
  any time afterwards gives the same value; each run re-reads the last
  `SNAP_WINDOW_DAYS` (10) days and upserts them
- Saturday and Sunday bars are skipped; Yahoo shows a transient Sunday bar at market
  reopen (1 weekend row in 5,929 of `GBPUSD=X` history)
- Yahoo keeps hourly bars for 730 days. Older dates, which only a rebuild reaches,
  still come from the daily bars, so they are the day's opening rate rather than its
  close
- The schedule is now two runs, 21:05 and 09:17 UTC (`.github/workflows/scrape.yml` is
  canonical). In winter the cut (22:00 UTC) falls after the evening run's cron time,
  so the morning run stores any close the evening run was too early for

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
