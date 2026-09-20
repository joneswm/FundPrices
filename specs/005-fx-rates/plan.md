# Technical Plan: End-of-Day FX Rates

**Spec**: SPEC-005
**Status**: ✅ Complete
**Created**: 2026-09-20

---

## Overview

FX is the price pipeline with a different config file and output, reusing the SPEC-003
fetcher, retry wrapper and upsert rules.

## Technical Approach

### Config

`fx_pairs.txt` at the repository root, one six-letter pair per line, `#` comments and
blank lines ignored.

```python
def read_fx_pairs(filename=FX_PAIRS_FILE) -> list[str]
```

Validation, each error naming its line: a pair must match `^[A-Z]{6}$`, and may not
repeat. A missing file yields `[]` rather than an error, so FX is optional.

### Fetching

```python
def fetch_fx_quotes(pair, start, end=None) -> list[Quote]
```

Wraps `fetch_yahoo_quotes(f"{pair}=X", ...)` and drops Saturday and Sunday bars. The
`Quote.currency` field carries the pair name, which keeps the record self-describing
without a second type.

Rates are formatted to exactly 6 decimal places rather than the shortest float32
round-trip used for prices: `HKDGBP` is about 0.0951, where 4dp loses roughly 0.1%, and
a fixed width keeps the column readable.

### Storage

```python
def write_fx_results(rows, data_dir=None)
```

- `data/fx_history.csv`: `Pair,Date,Rate`, keyed on (Pair, Date), upserted, sorted by
  (Date, Pair)
- `data/latest_fx.csv`: `Pair,Date,Rate`, most recent row per pair

Both match `data/*.csv`, which the workflows already force-add, so no workflow change is
needed.

### Failure isolation

`main()` runs prices, then FX. Each is wrapped so that a failure in one still lets the
other write. The exit code is non-zero if either failed, after everything obtainable has
been written.

### Backfill

`backfill_history()` gains an FX pass using the identical delete-then-insert rule and
the same protection for previously-stored rows.

## Data Flow

```
fx_pairs.txt -> ["NZDGBP", "SGDGBP", "USDGBP", "HKDGBP"]
   ↓ fetch_fx_quotes(pair, today - 10 days)   [retries]
Quotes, weekends dropped
   ↓
fx_history.csv (upsert on (Pair, Date)) + latest_fx.csv
```

## Testing Strategy

- Parser tested for grammar and each validation error
- Weekend filtering and 6dp formatting asserted directly
- Upsert, ordering and idempotency mirrored from the price tests
- Failure isolation asserted in both directions
- One functional test against the live endpoint

## Backwards Compatibility

Purely additive: new config file, new outputs, no change to price files.

## Rollback Plan

Delete `fx_pairs.txt` and the FX outputs. With no pairs configured the FX step is a
no-op, so the daily run is unaffected.
