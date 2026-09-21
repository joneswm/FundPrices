# Technical Plan: One-Off Imports for Closed Holdings

**Spec**: SPEC-009
**Status**: ✅ Complete
**Created**: 2026-09-21

---

## Architecture

Everything lives in `scrape_fund_price.py`, alongside the features it shares code with.

```
closed_holdings.txt
      │ read_closed_holdings()            validates every line up front
      ▼
import_closed_holdings(holdings)
      │ per holding:
      │   scrape_fund_quotes(source, lookup_id, start, end + 1 day)
      │   clip to [start, end]  →  assert currency  →  check_quoting_unit
      │   upsert under `identifier` with the configured currency
      ▼
write_history_csv()                       prices_history.csv, and nothing else
      ▼
BackfillReport                            stdout + Actions job summary; failures → exit 1
```

## New Code

| Item | Purpose |
|------|---------|
| `CLOSED_HOLDINGS_FILE` | `"closed_holdings.txt"` |
| `ClosedHolding` | `identifier, source, lookup_id, currency, start, end` |
| `read_closed_holdings(filename=None)` | parse and validate, errors name the line |
| `fetch_investing_quotes(pair_id, start, end=None)` | the `IV` source |
| `import_closed_holdings(holdings, data_dir=None)` | the import |
| `write_history_csv(rows, data_dir)` | extracted from `write_history_files()` so the import can write history alone |
| `--import-closed` | CLI flag and `main()` branch |

## Changes to Existing Code

- `scrape_fund_quotes()` and `source_requires_browser()` learn `IV`
- `write_history_files()`: when `latest` is supplied, the rolling window is limited to
  the funds in it
- `backfill_history()`: `latest_prices.csv`, the rolling window and the `.price` files
  are rebuilt for configured identifiers only

## Reuse

- `scrape_fund_quotes()` for dispatch, so closed holdings use the same handlers as the
  daily run
- `BackfillReport` for the reconciliation table
- `check_quoting_unit()` for pence/pounds switches
- `format_yahoo_price()` for investing.com too: both sources store float32

## Ownership of Rows

| Mode | Owns | Deletes |
|------|------|---------|
| Daily run | identifiers in `funds.txt` | nothing |
| Rebuild | identifiers it is given | removable rows for those identifiers only |
| Import | identifiers in `closed_holdings.txt` | nothing |

FR2 (no identifier in both files) is what keeps these disjoint. It is enforced by a
test over the committed configuration rather than at run time.

## Testing

Unit tests mock `scrape_fund_quotes` or `requests.get`. One live functional test covers
investing.com against a liquidated fund, whose values cannot change, and skips when the
source is unavailable. A test over the committed files asserts every configured window
is fully present in `data/prices_history.csv`, since nothing re-runs an import to catch
a short window.

## Risks

| Risk | Mitigation |
|------|------------|
| investing.com changes or blocks the endpoint | Only matters for a future import; committed data is unaffected. Requires a realistic user agent today |
| A source silently serves wrong data | Currency assertion, quoting-unit warning, and the validation steps recorded in the spec and in `closed_holdings.txt` |
| Closed holdings leak into "current" outputs | Tests on the import, the rebuild and the rolling window |
