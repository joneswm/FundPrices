# Technical Plan: Dividend Pay Dates from the Issuer

**Spec**: SPEC-011
**Status**: ✅ Built, on branch `pay-dates` (not yet merged)
**Created**: 2026-10-26

---

## Architecture

Everything lives in `scrape_fund_price.py`, beside the dividend code it extends.

```
dividend_sources.txt ─ read_dividend_sources()      validated up front with funds.txt
                              │
update_dividends(specs, distributions, sources=...)
      │ collect_dividends()            Yahoo, unchanged (SPEC-010)
      │ collect_issuer_tables()        per source: fetch_issuer_table(), retried, paced
      │     fetch_ishares_distributions()  GET product page → parse_ishares_distributions()
      │ merge_dividend_rows()          authority IS > YA > config
      │ apply_issuer_table()           per alias: pay dates, amounts, twins, declared
      │ write_dividend_history()
      ▼
publish_upcoming()                      a DeclaredDividend now carries amount and currency
```

`backfill_dividends(..., sources=...)` runs the same fetch, replaces the `YA` and `IS` rows
from the start date of every instrument whose page fetched, and applies the tables last.

## New Code

| Item | Purpose |
|------|---------|
| `DIVIDEND_SOURCES_FILE`, `DividendSource`, `read_dividend_sources()` | the configuration |
| `IssuerDistribution`, `IssuerTable`, `parse_ishares_distributions()`, `fetch_ishares_distributions()`, `fetch_issuer_table()` | the iShares page |
| `collect_issuer_tables()` | the daily fetch, with `fetch_with_retries()` |
| `issuer_amount()`, `amounts_agree()` | currency and rounding rules |
| `apply_issuer_table()` | the merge into the history; returns the declared row |

## Changes to Existing Code

- `DeclaredDividend` gains `amount` and `currency` (default `""`), and `upcoming_rows_for()`
  uses them when set, the last paid amount otherwise
- `merge_dividend_rows()` ranks the sources instead of special-casing `config`
- `update_dividends()` and `backfill_dividends()` take `sources=()`
- `backfill_dividends()` deletes `YA` and fetched `IS` rows (it deleted every non-`config` row)
- `main()` reads and validates `dividend_sources.txt` with `funds.txt`, passes
  `sources=` to both modes
- `import html`, `import json`

## Reuse

`fetch_with_retries()`, `as_fund_spec()` / `publish_ids`, `stored_currencies()` /
`first_currency()`, `BackfillReport`, the `DeclaredDividend` route into
`upcoming_rows_for()` and `build_dividend_summary()`.

## Ownership of Rows

| Mode | Owns | Deletes |
|------|------|---------|
| Daily run | `YA` rows in the window, `IS` rows (the whole table), `config` rows, upcoming rows | the `YA` twin of an `IS` row; upcoming rows |
| Dividend rebuild | `YA` rows and, where a page fetched, `IS` rows, from `--from` | those rows |

## Testing

Pure functions (`parse_ishares_distributions`, `issuer_amount`, `apply_issuer_table`,
`read_dividend_sources`) are tested directly with the two recorded pages and small
hand-made tables; the end-to-end classes run `update_dividends()` and `backfill_dividends()`
in a temporary directory with `fetch_issuer_table` and Yahoo faked. A test over the shipped
`dividend_sources.txt` and `funds.txt` catches a typo before the nightly run does. The
suite points `DIVIDEND_SOURCES_FILE` at a missing file so no test reads the shipped list.

## Risks

| Risk | Mitigation |
|------|------------|
| iShares changes the page (it dropped its CSV links once) | The parser fails loudly, per instrument; the rows stay; the failure is reported |
| A wrong product id attaches another fund's dates | The ISIN and fund name are on the page; the shipped ids were checked against Yahoo's ex-dates and amounts |
| The site's terms forbid automated copying | One request per instrument per day, `robots.txt` honoured; the same class of risk as the FT source (research page) |
| The pages are 1.5 to 3 MB | Ten fetches a day, one second apart |
