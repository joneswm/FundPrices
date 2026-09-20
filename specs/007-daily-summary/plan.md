# Technical Plan: Daily Price-Change Summary

**Spec**: SPEC-007
**Status**: 🔄 In Progress
**Created**: 2026-09-20

---

## Overview

Pure functions over stored history, rendered to CSV and Markdown.

## Technical Approach

### Record

```python
class SummaryRow(NamedTuple):
    name: str          # lookup identifier, or FX pair
    aliases: tuple
    currency: str      # "" for FX
    new_date: str
    new: str
    old_date: str      # "" when there is no previous price
    old: str
    delta: str
    pct_delta: str
    age_days: int
    stale: bool
    failed: bool
```

### Functions

```python
def build_price_summary(history_rows, specs, failures, run_date) -> list[SummaryRow]
def build_fx_summary(fx_rows, pairs, failures, run_date) -> list[SummaryRow]
def render_summary_markdown(price_rows, fx_rows, run_date) -> str
def write_summary(price_rows, fx_rows, run_date, data_dir=None)
```

No network, and the run date is a parameter rather than read from the clock, so every
case is directly testable.

### Comparison rule

For each identifier, take its rows sorted by date. `new` is the last, `old` is the row
before it — the previous **distinct** date, which is what makes a Friday-to-Monday
comparison correct without any holiday calendar.

`AgeDays` is the run date minus the new price date. `stale` is `AgeDays >
STALE_AFTER_DAYS` (4), which covers a normal long weekend and stays stateless.

### Arithmetic

`decimal.Decimal` throughout: `7.15 - 7.09` must be `0.06`, not `0.0600000000000005`.
Percent delta is rendered to 2dp with an explicit sign; price deltas keep up to 6dp with
trailing zeros stripped; FX values stay at 6dp.

### Outputs

- `data/daily_summary.csv`:
  `Name,Aliases,Currency,NewDate,New,OldDate,Old,Delta,PctDelta,AgeDays,Stale,Failed`
- `data/daily_summary.md`: prices table, FX table, an Attention section, and the biggest
  movers by absolute percent delta excluding stale rows
- The same Markdown appended to `$GITHUB_STEP_SUMMARY` when set

Past summaries are recoverable from git history and recomputable from
`prices_history.csv`, so no dated archive is kept.

## Data Flow

```
prices_history.csv + funds.txt + this run's failures
   ↓ build_price_summary(run_date)
SummaryRows  ──┐
fx_history.csv ┘ build_fx_summary
   ↓
daily_summary.csv + daily_summary.md + job summary
```

## Testing Strategy

Pure functions make every case a direct assertion: Friday-to-Monday gaps, differing
latest dates between a fund and an exchange instrument, first-ever price, zero previous
price, the stale boundary at exactly 4 and 5 days, aliases, GBp instruments, and FX
formatting.

## Backwards Compatibility

Purely additive. Prices, FX and the backfill are untouched.

## Rollback Plan

Delete the two output files and the call from `main()`. Nothing else depends on them.
