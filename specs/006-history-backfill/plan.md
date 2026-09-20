# Technical Plan: History Backfill and Rebuild

**Spec**: SPEC-006
**Status**: ✅ Complete
**Created**: 2026-09-20

---

## Overview

Backfill is the daily mechanism with a longer window and a delete-then-insert rule.

## Technical Approach

### Entry point

```
python scrape_fund_price.py --backfill --from 2023-01-01
```

`--from` is required with `--backfill`, must be `YYYY-MM-DD`, and must not be in the
future. `--backfill` and `--history` are mutually exclusive.

### Core function

```python
def backfill_history(specs, start, data_dir=None) -> BackfillReport
```

Per instrument:

1. Fetch `scrape_fund_quotes(source, lookup_id, start)` through `fetch_with_retries`
2. On failure: record it, change nothing
3. On success: for every `publish_id`, drop stored rows with `Date >= start`, then
   insert the fetched quotes under that identifier

Rows earlier than `start`, and rows whose identifier is not configured, are carried
through untouched apart from dropping unusable prices.

### Why delete rather than upsert

An upsert keys on (Fund, Date). Carry-forward rows sit on dates the source never
reports — weekends, holidays, and the day after a fund's true price date — so they have
no incoming row to replace them and would survive. Deleting the rebuilt range first is
what actually removes them.

### Sanity checks

- **Quoting unit change**: warn when consecutive prices differ by more than a factor of
  50. A pence/pounds switch is a factor of 100, while a genuine one-day move is not.
- **Splits**: `fetch_yahoo_quotes` warns if the split column is non-zero inside the
  requested range. None of the 20 tickers had a split since 2023, but a future rebuild
  might.

### Reconciliation report

Per identifier: rows before, deleted, inserted, first and last date, currency, status.
Printed to stdout, and appended to `$GITHUB_STEP_SUMMARY` when that variable is set.
Exit code is non-zero if any instrument failed, **after** everything obtainable is
written.

### FX

If `read_fx_pairs()` exists (SPEC-005), the same delete-then-insert rule is applied to
`fx_history.csv`. Until then the FX step is skipped, so the mechanism is ready without
depending on SPEC-005 landing first.

### Workflow

`.github/workflows/backfill.yml`, `workflow_dispatch` only, input `from_date`
(default `2023-01-01`). Shares a `concurrency` group with `scrape.yml` so a rebuild and a
daily scrape can never push at once.

## Data Flow

```
funds.txt → FundSpecs
   ↓ per instrument, sequentially with a pause between FT funds
fetch quotes from 2023-01-01 (retries)
   ↓ success                      ↓ failure
drop stored rows >= start          keep existing rows
insert fetched quotes              record in report
   ↓
rewrite prices_history.csv, then regenerate
latest_prices.csv, prices_history_90_days.csv, latest_<id>.price
```

## Testing Strategy

- Delete-then-insert proven by a test where a weekend carry-forward row exists on a date
  the source does not report, and must be gone afterwards
- Failure isolation proven by a two-instrument test where one fails
- Idempotency by running twice and comparing bytes
- Sanity warnings triggered by synthetic data

## Backwards Compatibility

Output schema is unchanged from SPEC-003. The daily run is untouched; backfill is a
separate mode behind its own flag.

## Rollback Plan

`git revert` the data commit. The previous `prices_history.csv` is in git history, and
the rebuild can be re-run at any time because it is idempotent and derives everything
from the sources.
