# SPEC-010: The Dividend Calendar

**Status**: 🔄 In progress
**Created**: 2026-10-26
**Type**: Feature
**Tracking**: [#85](https://github.com/joneswm/FundPrices/issues/85)

> Stage DV-F of the Portfolio Tracker dividend design (joneswm/portfolio-tracker#637,
> `docs/05-features/dividends/DIVIDEND_DESIGN.md` section 3). FundPrices publishes the
> per-share facts; the holder's side (units held, withholding, receipt mode, the
> receivable) lives entirely in Portfolio Tracker.

---

## Context

FundPrices publishes dated prices and FX rates per identifier. A downstream portfolio
system now wants to show what its holdings will pay and when, which needs one more
dated fact per instrument: the ex-dividend date, the pay date and the gross amount per
share.

## User Need

**As** the owner of the portfolio
**I want** every instrument's past and next dividend published beside its price
**So that** expected income can be shown before it arrives, and checked after

## Problem Statement

- Yahoo returns dividend events with the same `yfinance` call that returns the daily
  bars, and sometimes a declared next ex-date, but nothing in this repository keeps them
- The six FT-sourced OEIC share classes have no source at all. Their ex-dates and pay
  dates are fixed by the fund and known from the factsheet
- A declared dividend and a projected one are different facts and must not look alike

## Proposed Solution

Two CSVs beside the price files, keyed by the same identifiers and published under every
alias (spec 004), fetched in the daily run with the same retry rule, plus a hand-kept
`distributions.txt` for instruments no source covers.

## Files

### `data/dividends_history.csv`

`Fund,ExDate,PayDate,Amount,Currency,Source`

- One row per instrument and ex-date, sorted by `ExDate` then `Fund`
- `Amount` is the gross per-share amount **as the source reports it, in the
  instrument's price currency**: a pence line stays in `GBp`, exactly as its prices do
- `PayDate` is empty unless the source gives it (Yahoo's history does not)
- `Source` is `YA` (Yahoo) or `config` (a past occurrence asserted in
  `distributions.txt`)

### `data/dividends_upcoming.csv`

`Fund,ExDate,PayDate,Amount,Currency,Status,AsOf`

- `Status` is `declared` (the source announced the ex-date) or `estimated` (projected)
- `AsOf` is the run date on which the row was produced or confirmed
- An instrument with no dividends in the history and no declared one has no row

### `distributions.txt`

For instruments no source covers. One line per instrument:

```
<identifier>,<frequency>,<xd-dates>,<pay-offset-days>[,<last-amounts>[,<as-of>]]
```

| Field | Rule |
|-------|------|
| `identifier` | A published identifier: one of `funds.txt` (lookup id or alias), or an identifier of `closed_holdings.txt` |
| `frequency` | `monthly`, `quarterly`, `semiannual` or `annual` (case-insensitive) |
| `xd-dates` | `;`-separated `MM-DD` ex-dividend dates, as many as the frequency pays a year (12, 4, 2, 1), no repeats. `02-29` is allowed and means 28 February in a common year |
| `pay-offset-days` | Whole days from each ex-date to its payment, 0 to 365 |
| `last-amounts` | Optional. `;`-separated gross per-share amounts, one per `xd-dates` entry **in the same order**; an entry may be empty for "not known". Positive decimals. In the unit the identifier's price is quoted in |
| `as-of` | Optional `YYYY-MM-DD`: the date the amounts were last checked. Only valid with `last-amounts` |

```
GB00B1FXTF86,semiannual,03-01;09-01,30,0.0821;0.0794,2026-10-01
```

Blank lines, full-line `#` comments and trailing comments are ignored. The file ships
with a commented header and no entries.

## Success Criteria

### Functional Requirements

- **FR1**: `distributions.txt` is validated in full before any network call. A
  malformed line, an unknown frequency, a wrong number of ex-dates or amounts, an
  invalid `MM-DD`, a bad offset, amount or date, a repeated identifier, or an identifier
  in neither `funds.txt` nor `closed_holdings.txt` raises `ValueError` naming the line.
  A missing file means no entries
- **FR2**: For every `YA` instrument in `funds.txt`, the daily run fetches Yahoo's
  dividend events and upserts them into `dividends_history.csv`, keyed on `(Fund,
  ExDate)`. A changed amount replaces the row. Rows are published under every alias
- **FR3**: Amounts and currencies are as Yahoo reports them in the instrument's price
  currency (the currency logic is the prices'), with no conversion and no float noise
- **FR4**: Fetches are retried by `fetch_with_retries()`. One failing instrument never
  stops the others or the rest of the run; the run still exits non-zero once everything
  has been written. A failed instrument keeps every row it had
- **FR5**: The first time an instrument has no stored dividends its whole Yahoo history
  is fetched; afterwards the daily run reads a window of `DIVIDEND_WINDOW_DAYS` (400)
  days
- **FR6**: `--backfill-dividends [--from DATE]` rebuilds the `YA` rows of every `YA`
  instrument from the source, from `DATE` or from the beginning. Rows the source no
  longer reports are removed; `config` rows are kept. A failing instrument keeps what
  it had
- **FR7**: `dividends_upcoming.csv` carries a `declared` row when Yahoo gives a next
  ex-date that is not in the past (`Ticker.calendar`, falling back to
  `Ticker.info.exDividendDate`), with the pay date where Yahoo gives one
- **FR8**: Otherwise it carries an `estimated` row: the frequency is read from the
  spacing of the ex-dates in the twelve months to the last one (median gap: up to 45
  days monthly, to 135 quarterly, to 270 semi-annual, longer annual; a single ex-date
  is annual), the next ex-date is the last plus that period (rolled forward in whole
  periods until it is today or later), the amount is the last paid. An instrument whose
  last ex-date is older than one period plus 45 days is treated as having stopped and
  has no estimate
- **FR9**: A declared row replaces an estimated one for the same period: while a
  declared ex-date later than the last historical one exists, no estimate is written.
  A moved declared date replaces the earlier declared row
- **FR10**: A row whose ex-date is more than 7 days past and that is in the history is
  dropped. A row more than 30 days past is dropped whether or not it reached the history
- **FR11**: An identifier with a line in `distributions.txt` takes its estimate from
  that line, not from the pattern: the next occurrence of one of its `xd-dates` on or
  after today, paid `pay-offset-days` later, for that slot's amount (empty if unknown)
- **FR12**: A line with `last-amounts` **and** `as-of` also asserts history: for each
  `xd-dates` entry with an amount, the latest occurrence on or before `as-of` (and
  today) becomes a `config` row in `dividends_history.csv` with its pay date. A line
  without `as-of` writes no history, because nothing says when its amounts were true.
  A `YA` row for the same ex-date always wins over a `config` row
- **FR13**: The currency of a `config` row or estimate is the currency of the
  identifier's newest stored price
- **FR14**: `daily_summary.md` gains a "Dividends" section listing, once per
  instrument, each upcoming row that is new today or whose pay date or status changed,
  with ex-date, pay date, amount, currency and status. It reads "None" when nothing
  changed. The CSV summary, which has one row per instrument, is unchanged
- **FR15**: Closed holdings are never fetched from Yahoo and never get an upcoming row;
  their only dividend rows are `config` history rows from `distributions.txt`

### Non-Functional Requirements

- **NFR1**: No synthetic rows. Nothing is written for a dividend no source or config
  line states or projects; no error text is ever written to a data file
- **NFR2**: Output is deterministic: sorted, LF endings, an unchanged day is an empty
  diff apart from `AsOf`
- **NFR3**: Nothing about holders, withholding, tax or currency conversion
- **NFR4**: Coverage of the new code is 100%; the project gates (90% overall, 95% on
  `scrape_fund_price.py`) hold

## Out of Scope

- A yield-based estimate: that is a planning assumption, not a fact
- Special and one-off dividends as such: they enter the history as Yahoo reports them
  and can distort the estimate for a year
- Dividends in a currency other than the instrument's price currency (an ADR paying in
  another currency would be mis-labelled)
- Detecting a dividend Yahoo re-dated: the old row stays until a rebuild
- A workflow for the rebuild

## Decisions

| Decision | Reason |
|----------|--------|
| Amount of a `declared` row is the last paid amount | Neither `Ticker.calendar` nor `Ticker.info` carries the declared per-share amount; the date is the fact that is declared. The last paid is the best figure available and the history shows what it was |
| A calendar lookup that fails is a warning, not a failure | Yahoo has no calendar for most funds and ETFs and raises for some; failing the run daily for a missing optional fact would hide real failures |
| Estimate window is the twelve months to the **last** ex-date, not to today | A semi-annual payer whose next dividend is not yet reported has one ex-date in the twelve months to today and would read as annual |
| A line in `distributions.txt` beats the pattern | The owner's statement of a fund's fixed dates is better evidence than a projection, and the file exists for instruments the pattern cannot see |
| `as-of` gates config history | Without it the file would turn the old amount into a "paid" row for every later occurrence |
| `YA` beats `config` for the same ex-date | The source is authoritative once it knows |
| Daily run is upsert-only, rebuild replaces | Same ownership rule as the prices (spec 006): a daily run cannot delete |
| AsOf is the run that confirmed a row | A row carried over because a lookup failed keeps its older date, so staleness stays visible |
| Summary section is Markdown only | `daily_summary.csv` has one row per instrument and a fixed header that consumers read |
