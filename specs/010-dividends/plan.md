# Technical Plan: The Dividend Calendar

**Spec**: SPEC-010
**Status**: ✅ Built, on branch `dividends-calendar`
**Created**: 2026-10-26

---

## Architecture

Everything lives in `scrape_fund_price.py`, beside the features it shares code with.

```
distributions.txt ─ read_distributions()        validated up front with funds.txt
                          │
funds.txt ─ read_fund_specs()
      │
      ▼
update_dividends(specs, distributions)           the daily run, after prices and FX
      │ collect_dividends(): per YA fund, retried
      │     fetch_yahoo_dividends()   Ticker.history(actions=True)  → DividendEvent
      │     fetch_yahoo_declared()    Ticker.calendar, then .info   → DeclaredDividend
      │ merge_dividend_rows()   upsert on (Fund, ExDate); YA beats config
      │ config_history_rows()   distributions.txt lines with amounts + as-of
      │ write_dividend_history()                 dividends_history.csv
      ▼
publish_upcoming()
      │ build_dividend_upcoming(): per funds.txt instrument, once, then per alias
      │     estimate_next_dividend()   pattern of the last twelve months
      │     distribution_estimate()    when the instrument has a distributions.txt line
      │     upcoming_rows_for()        declared / estimated / carried-over rules
      │ write_dividend_upcoming()                dividends_upcoming.csv
      ▼
build_dividend_summary(previous, today)          → daily_summary.md "Dividends"
```

`--backfill-dividends` runs `backfill_dividends()` instead: the same fetch, but the YA
rows from `--from` are replaced by what Yahoo reports, `config` rows stay, and the
upcoming file is rebuilt without a calendar lookup.

## New Code

| Item | Purpose |
|------|---------|
| `DISTRIBUTIONS_FILE`, `Distribution`, `read_distributions()`, `parse_xd_date()` | the hand-kept schedule |
| `configured_identifiers()` | the identifiers a schedule line may name |
| `DividendEvent`, `DeclaredDividend`, `fetch_yahoo_dividends()`, `fetch_yahoo_declared()` | the Yahoo routes |
| `format_dividend_amount()`, `parse_yahoo_date()`, `ticker_currency()` | formatting and parsing |
| `DividendResults`, `collect_dividends()` | the daily fetch with `fetch_with_retries()` |
| `read/write_dividend_history()`, `merge_dividend_rows()` | the history file |
| `add_months()`, `detect_period_months()`, `next_period_start()`, `estimate_next_dividend()`, `EstimatedDividend` | the projection |
| `distribution_estimate()`, `distribution_history_rows()` | the schedule's rows |
| `read/write_dividend_upcoming()`, `upcoming_rows_for()`, `build_dividend_upcoming()` | the upcoming file |
| `update_dividends()`, `backfill_dividends()`, `publish_upcoming()` | orchestration |
| `DividendSummaryRow`, `build_dividend_summary()`, `display_name()` | the summary section |
| `validate_dividend_backfill_args()`, `validate_start_date()`, `--backfill-dividends` | the rebuild mode |

## Changes to Existing Code

- `fetch_yahoo_quotes()` uses `ticker_currency()`, so prices and dividends share one
  currency lookup
- `render_summary_markdown()` and `write_summary()` take an optional `dividend_rows`;
  without it their output is unchanged
- `validate_backfill_args()` shares `validate_start_date()` with the new mode
- `main()` reads `distributions.txt` with `funds.txt`, runs `update_dividends()` after FX
  inside a `try`, and adds the `--backfill-dividends` branch
- The existing `main()` tests patch `update_dividends` and set `backfill_dividends`

## Reuse

- `fetch_with_retries()` for the retry rule; `BackfillReport` for the rebuild's table
- `as_fund_spec()` and `FundSpec.publish_ids` for the alias rule
- `newest_stored_rows()` for the price currency of an OEIC's schedule
- `open_for_write()` and `csv_writer()` for LF endings

## Ownership of Rows

| Mode | Owns | Deletes |
|------|------|---------|
| Daily run | YA rows in the window; `config` rows; upcoming rows | upcoming rows only |
| Dividend rebuild | YA rows of the instruments that fetch, from `--from` | those YA rows |
| Anything else | nothing | nothing |

## Testing

Unit tests mock `yf.Ticker` (a fake with `calendar` and `info` properties for the
declared route) and the two fetch functions; the end-to-end classes run
`update_dividends()` and `backfill_dividends()` in a temporary directory with Yahoo
faked. A test over the committed `distributions.txt` and `funds.txt` catches a typo
before the nightly run does. There is deliberately no live functional test: Yahoo's
calendar for a stock changes weekly, and the shapes were checked by hand (see the spec).

## Risks

| Risk | Mitigation |
|------|------------|
| Yahoo has no calendar for ETFs and raises for some funds | A failing calendar only warns; `info` is the fallback; ETFs are `estimated` |
| An old amount in `distributions.txt` is projected for ever | The `as-of` date gates history rows; the README says to update both after each payment |
| A re-dated Yahoo dividend leaves its old row | Documented; `--backfill-dividends` removes it |
| A special dividend distorts the next estimate | The median gap keeps the frequency; the amount is the last paid, so one estimate is off |
| The first run is heavy | One full dividend history per instrument, once |
