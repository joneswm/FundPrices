# API Reference

This document provides detailed API documentation for the Fund Price Scraping project.

## Core Functions

### `FundSpec(source, lookup_id, aliases=())`

One configured instrument.

- `source` (str): canonical source code (`YA`, `FT`, `IV`, `YH`, `MS`). `GF` is accepted on input and canonicalised to `YA`
- `lookup_id` (str): the identifier sent to the source
- `aliases` (tuple): extra identifiers to publish under
- `publish_ids` (property): `lookup_id` followed by each alias

### `read_fund_specs(filename)`

Reads instrument configuration.

**Line grammar:** `<source>,<lookup_id>[,<alias>[;<alias>...]]`. Blank lines, full-line
`#` comments and trailing comments are ignored.

**Returns:** `list[FundSpec]`

**Raises:** `ValueError` naming the offending line, for a malformed line, an empty or
self-referencing alias, or an identifier repeated anywhere in the file. Validation runs
before any network call, so a bad config cannot fail half way through a run.

```python
read_fund_specs("funds.txt")
# [FundSpec(source="YA", lookup_id="0P00000YAN", aliases=("JFM0003373",)), ...]
```

### `read_fund_ids(filename)`

Reads `(source, lookup_id)` pairs. A compatibility wrapper over `read_fund_specs()`
for callers that do not need aliases.

**Parameters:**
- `filename` (str): Path to the file containing fund identifiers

**Returns:**
- `list`: List of tuples containing (source, identifier) pairs

**File Format:**
Each line should contain: `<source>,<identifier>`
- `source`: Data source identifier (YA, FT, YH, MS)
- `identifier`: Fund identifier for the specific source

**Example:**
```python
funds = read_fund_ids("funds.txt")
# Returns: [("FT", "GB00B1FXTF86"), ("YH", "IDTG.L"), ...]
```

### `get_source_config(source, fund_id)`

Gets URL and CSS selector configuration for a given source and fund ID.

**Parameters:**
- `source` (str): Source identifier (FT, YH, MS)
- `fund_id` (str): Fund identifier

**Returns:**
- `tuple`: (url, selector) or (None, None) if source not supported

**Supported Sources:**
- **YA**: Yahoo Finance API via `fetch_yahoo_quotes()` - no scraping, returns `(None, None)` here
- **FT**: Financial Times (`https://markets.ft.com/data/funds/tearsheet/summary?s={fund_id}`)
- **YH**: Yahoo Finance (`https://sg.finance.yahoo.com/quote/{fund_id}/`)
- **MS**: Morningstar (`https://asialt.morningstar.com/DSB/QuickTake/overview.aspx?code={fund_id}`)

### `scrape_price_with_common_settings(page, url, selector)`

Scrapes price data using common browser settings.

**Parameters:**
- `page`: Playwright page object
- `url` (str): Target URL to scrape
- `selector` (str): CSS selector for the price element

**Returns:**
- `str`: Scraped price text content

**Browser Settings:**
- User-Agent: Chrome 115.0.0.0 on Windows 10
- Timeout: 30 seconds for page load, 60 seconds for selector
- Wait condition: DOM content loaded

### `Quote(date, price, currency)`

A single dated price as reported by a source.

- `date` (str): ISO `YYYY-MM-DD`, the price date the source reports
- `price` (str): as quoted, thousands separators removed
- `currency` (str): `"GBP"`, `"GBp"`, `"USD"`, `"HKD"`; `""` when the source gives none

### `format_yahoo_price(value)`

Formats a Yahoo bar value without losing or inventing precision.

Yahoo daily bars are float32, so widening them to Python floats introduces artefacts:
124.87 arrives as `124.87000274658203`. Rounding to fixed decimals would store that
noise, while a significant-digit format would discard real precision
(`format(126530.25, ".7g")` gives `126530.2`). The shortest string that round-trips as
float32 recovers exactly what the source published.

**Returns:** `str`, e.g. `"124.87"`, `"2.7785"`, `"6317"`, `"126530.25"`

### `fetch_yahoo_quotes(symbol, start, end=None)`

Fetches dated daily quotes from Yahoo Finance.

**Parameters:**
- `symbol` (str): Yahoo ticker (e.g. `IDTG.L`, `0P00000YAN`)
- `start` (str): Inclusive ISO start date
- `end` (str, optional): **Exclusive** ISO end date; `None` for the latest bar

**Returns:** `list[Quote]`, oldest first

Uses `Close` with `auto_adjust=False`, so values match the price quoted that day rather
than a dividend-adjusted series. Does **not** use the summary endpoint (`.info`), which
carries no date and was observed returning a stale price for mutual funds. Exceptions
propagate so `fetch_with_retries()` can retry them.

### `fetch_ft_quotes(isin, start, end=None)`

Fetches dated daily quotes from Financial Times.

**Parameters:**
- `isin` (str): Fund ISIN as used in `funds.txt`
- `start` (str): Inclusive ISO start date
- `end` (str, optional): Inclusive ISO end date; `None` for today

**Returns:** `list[Quote]`, oldest first

**Raises:** `ValueError` when FT's internal id cannot be resolved or no rows are
returned, so the caller can fall back to scraping.

Two plain HTTP requests, no browser. Prices are kept as text so published digits are
preserved exactly.

### `scrape_fund_quotes(source, fund_id, start, end=None, browser=None)`

Returns dated quotes for one fund from its configured source: `YA` via
`fetch_yahoo_quotes()`, `IV` via `fetch_investing_quotes()`, and `FT` via
`fetch_ft_quotes()`, falling back from FT's endpoint to scraping when needed. `YH` and `MS` scrape a page showing only the current
price, so their quotes carry the run date and an empty currency.

### `LazyBrowser`

Starts Playwright on first use, so a configuration that needs no scraping never
launches Chromium. `page()` returns a live page; `close()` is safe if unused.

### `read_last_known_row(fund_id, data_dir)`

Returns a fund's most recent stored `[date, price, currency]`, or `None`.

Used when every fetch attempt failed: the fund keeps reporting its real last price
against the date that price belongs to, instead of a row invented for today.

### `fetch_price_api(symbol)`

Fetches a price via the Yahoo Finance API instead of scraping. Used for the `YA` source.

**Parameters:**
- `symbol` (str): Ticker symbol (e.g. `AAPL`, `MSFT`) with no exchange prefix

**Returns:**
- `str`: Price as a string, or `"Error: <message>"` on failure

Reads `currentPrice`, falling back to `regularMarketPrice`. Returns
`"Error: Price not available"` when neither field is present.

**Example:**
```python
price = fetch_price_api("AAPL")   # "150.25"
```

### `scrape_funds(funds, data_dir=None)`

Main function to scrape prices for a list of funds. Launches a Playwright browser
only if at least one fund actually needs scraping (see `source_requires_browser`).

**Parameters:**
- `funds` (list): List of (source, identifier) tuples
- `data_dir` (str, optional): Directory to store results (defaults to `"data"`)

**Returns:**
- `ScrapeResults`: a `list` subclass of `[fund_id, date, price, currency]` rows, one
  per dated quote in the last `SNAP_WINDOW_DAYS` (10) days, with two extra attributes:
  - `.failures`: `"<lookup_id>: <error>"` strings for funds whose every attempt failed
  - `.carried`: the last stored row for each of those funds, under its original date,
    so `latest_prices.csv` keeps reporting a real price. A fund with no stored
    history has no carried row and is simply absent

**Result Format:**
```python
results = scrape_funds([("YA", "AAPL"), ("FT", "GB00B1FXTF86")])
# [["AAPL", "2026-09-18", "150.25", "USD"], ["GB00B1FXTF86", "2026-09-18", "7.15", "GBP"], ...]
results.failures
# ["GB00B1FXTF86: Error: Timeout"]   (only for funds that failed all attempts)
```

**Side effect:** writes `data/latest_<identifier>.price` for each fund.

### `write_results(results, data_dir=None)`

Writes scraping results to CSV files.

**Parameters:**
- `results` (list): List of `[fund_id, date, price, currency]` rows
- `data_dir` (str, optional): Directory to write files (defaults to `"data"`)

**Output Files:**
- `latest_prices.csv`: Most recent price per fund, overwritten each run
- `prices_history.csv`: Full history, keyed on **(Fund, Date)**. An incoming row
  replaces an existing row with the same key, so corrections apply and re-runs
  cannot duplicate
- `prices_history_90_days.csv`: Derived rolling window containing the latest result
  date and the preceding 89 calendar days (90 inclusive, `ROLLING_HISTORY_DAYS`), for
  the funds in this run's results or carried rows. Closed holdings are excluded even
  when their dates fall inside the window

**CSV Format:**
- Headers: `Fund,Date,Price,Currency`
- `Date` is the price date reported by the source, not the collection date
- `Currency` is as quoted (`GBp` and `GBP` are distinct); `""` when unknown
- Rows are sorted by date then fund, so repeated runs are byte-identical
- Values that are not usable prices (`Error: ...`, `N/A`) are never stored

**Compatibility**: `Currency` is appended as a fourth column, so readers that use the
first three positions are unaffected. Rows written before SPEC-003 have no currency
and load with an empty value.

### `fetch_historical_data(symbol, start_date, end_date, data_dir=DATA_DIR)`

Fetches historical OHLCV data for a symbol via yfinance and writes it to CSV.

**Parameters:**
- `symbol` (str): Ticker symbol
- `start_date` (str): Start date, `YYYY-MM-DD`
- `end_date` (str or None): End date, `YYYY-MM-DD`; `None` means up to today
- `data_dir` (str, optional): Output directory (defaults to `DATA_DIR`)

**Returns:**
- `str`: Path to the written CSV, or `"Error: <message>"` on failure

**Validation:** rejects malformed dates (`"Error: Invalid start date format. Use YYYY-MM-DD"`),
rejects `start_date > end_date`, and reports `"Error: No data found for symbol <symbol>"`
when the range returns nothing.

**Output:** `data/history_<symbol>_<start>_<end>.csv`, with columns
`Date, Open, High, Low, Close, Volume, Dividends, Stock Splits`.

**Example:**
```python
path = fetch_historical_data("AAPL", "2024-01-01", "2024-12-31")
```

### `parse_arguments(args=None)`

Parses the command line:

- `--history SYMBOL` with `--start YYYY-MM-DD` and optional `--end YYYY-MM-DD`
- `--backfill` with `--from YYYY-MM-DD` (`--from` is an alias of `--start`)
- `--import-closed`

With none of these, the daily run executes.

## Resilience: Retries and Last Known Price

A transient failure does not write an error into the price files. Each fetch is retried,
and if every attempt fails the fund falls back to its most recent good price.

### `fetch_with_retries(fetch_price, attempts=MAX_PRICE_ATTEMPTS)`

Calls `fetch_price()` up to `attempts` times (default 3). Retries both raised exceptions
and returned `"Error: ..."` values.

**Returns:**
- `tuple`: `(price, None)` on success, or `(None, last_error)` if every attempt failed

### `get_last_known_price(fund_id, data_dir)`

Returns the most recent usable price for a fund, checked in order:

1. `read_latest_price_file()` - `data/latest_<fund_id>.price`
2. `read_latest_csv_price()` - `latest_prices.csv`
3. `read_history_price()` - most recent row in `prices_history.csv`

**Returns:**
- `str` price, or `None` if no usable historical price exists

`scrape_funds()` itself uses `read_last_known_row()`, which also returns the date and
currency; this function remains for callers that need only the price.

### Supporting helpers

- `is_error_price(price)` - True when a value is an `"Error: ..."` string
- `normalize_price(price)` - normalises a price value for storage
- `is_usable_price(price)` - True when a value is a real price rather than an error or placeholder
- `source_requires_browser(source, fund_id)` - False for `YA`, `FT` and `IV`, which all
  reach HTTP endpoints, so Playwright is only launched when genuinely needed

## Closed Holdings

Instruments held once and no longer priced daily. Configured in
`closed_holdings.txt`, separate from `funds.txt` so the daily run cannot reach
them, and imported once with `--import-closed`.

### `ClosedHolding(identifier, source, lookup_id, currency, start, end)`

One instrument imported once and then left alone.

- `identifier` (str): what the history is published under
- `source` (str): canonical source code, as for `FundSpec`
- `lookup_id` (str): the identifier sent to the source, which may differ from
  `identifier` when a SEDOL outlives the ticker its fund traded under
- `currency` (str): asserted against what the source reports
- `start`, `end` (str): inclusive ISO window actually held

### `read_closed_holdings(filename=None)`

Reads one-off import configuration, defaulting to `CLOSED_HOLDINGS_FILE`.

**Line grammar:** `<identifier>,<source>,<lookup_id>,<currency>,<start>,<end>`.
Blank lines and `#` comments are ignored.

**Raises** `ValueError` naming the line for a malformed line, an unparseable or
reversed date, or a repeated identifier.

### `fetch_investing_quotes(pair_id, start, end=None)`

Dated daily closes from investing.com, for a delisted line that Yahoo and FT no
longer carry. Returns `list[Quote]` oldest first with **no currency**: the
endpoint does not report one, so the caller supplies it from configuration.
Prices are float32 round-tripped, keeping a genuine half penny that the
displayed two decimals would round away.

**Raises** `ValueError` when no usable rows are returned.

### `import_closed_holdings(holdings, data_dir=None)`

Imports each window and returns a `BackfillReport`.

Writes `prices_history.csv` and nothing else: `latest_prices.csv`, the 90-day
window and the `.price` files describe a current value that a closed holding
does not have. Upserts and never deletes, so it cannot tread on the identifiers
owned by the daily run or a rebuild.

A holding whose source reports a currency other than the configured one is
skipped with a failure recorded, rather than importing a window of prices for
the wrong listing. Sources are asked one day past `end`, because Yahoo treats
the end date as exclusive while FT and investing.com treat it as inclusive; the
window filter clips the extra day.

## Dividends

The dividend calendar (SPEC-010): `data/dividends_history.csv`
(`Fund,ExDate,PayDate,Amount,Currency,Source`) and `data/dividends_upcoming.csv`
(`Fund,ExDate,PayDate,Amount,Currency,Status,AsOf`), written by the daily run and
rebuilt with `--backfill-dividends`. Rows are published under every alias of an
instrument. Rows are plain lists; the file headers are `DIVIDEND_HISTORY_HEADER` and
`DIVIDEND_UPCOMING_HEADER`.

### `Distribution(identifier, frequency, xd_dates, pay_offset_days, amounts, as_of)`

One line of `distributions.txt`. `xd_dates` is a tuple of `(month, day)` in calendar
order and `amounts` a tuple of amount strings in the same order (`""` when unknown);
`as_of` is `""` when the line gives none.

### `read_distributions(filename=None, known_identifiers=None)`

Reads `distributions.txt` (default `DISTRIBUTIONS_FILE`); a missing file has no entries.

**Line grammar:**
`<identifier>,<frequency>,<xd-dates>,<pay-offset-days>[,<last-amounts>[,<as-of>]]`, where
`frequency` is `monthly`, `quarterly`, `semiannual` or `annual`, `xd-dates` are
`;`-separated `MM-DD` (12, 4, 2 or 1 of them), `last-amounts` are `;`-separated positive
decimals, one per ex-date, and `as-of` is `YYYY-MM-DD`. See `specs/010-dividends/spec.md`.

**Raises** `ValueError` naming the line for any malformed field, a repeated identifier,
or (when `known_identifiers` is given) an identifier in neither `funds.txt` nor
`closed_holdings.txt`.

### `configured_identifiers(specs, closed_file=None)`

Every identifier `distributions.txt` may name: the identifiers `funds.txt` publishes under
and those of `closed_holdings.txt`.

### `DividendEvent(ex_date, amount, currency)` and `DeclaredDividend(ex_date, pay_date)`

What Yahoo reports: a past dividend, and the next announced ex-date with its pay date
(`""` when absent or not after the ex-date).

### `fetch_yahoo_dividends(symbol, start, end=None)`

Yahoo's dividend events from `Ticker.history(..., actions=True)`, the `Dividends` column of
the ex-date bars, unadjusted. `start=None` reads everything (`period="max"`). The amount
is the gross per-share amount in the instrument's price currency (`GBp` stays `GBp`),
rounded to the seven digits a float32 holds (Yahoo serves FLOS.L's 12.35p as 12.349999)
and written as plain decimal text. Returns `list[DividendEvent]`, oldest first. Transport
errors propagate so `fetch_with_retries()` can retry them.

### `fetch_yahoo_declared(symbol, today=None)`

The next announced dividend, or `None`. Reads `Ticker.calendar` and falls back to
`Ticker.info` (`exDividendDate`, `dividendDate`) when the calendar has no ex-date from
`today` on. Neither carries the declared amount. A failing calendar is not an error; a
failing `info` propagates.

### `collect_dividends(specs, today, start=None)`

For each `YA` instrument, one retried fetch of the events (published under every alias,
`Source` `YA`, `PayDate` empty, events after `today` ignored) and one of the declared
dividend. Returns `DividendResults`, a list of history rows with `.failures`
(`"<id>: dividends: <error>"`), `.declared` (lookup id to `DeclaredDividend`), `.fetched`
and `.summary`. A failed declared lookup prints a warning and is not a failure.

### `read_dividend_history(data_dir)` and `write_dividend_history(rows, data_dir)`

`read` returns rows keyed `(Fund, ExDate)` (rows without either are skipped); `write`
sorts by ex-date then fund, with LF endings.

### `merge_dividend_rows(stored, incoming)`

Upserts into a history dict. An incoming row replaces the stored one, except that a
`config` row never replaces a row a source supplied.

### `estimate_next_dividend(rows, today)`

Projects one instrument's next dividend from its history rows: the period is the median
gap between the ex-dates in the twelve months to the last one (up to 45 days monthly,
135 quarterly, 270 semi-annual, else annual; one date reads as annual); the next ex-date
is the last plus the period, moved on by whole periods until it is today or later; the
amount and currency are the last paid; a pay date is projected when the last row has one.
Returns `EstimatedDividend(ex_date, pay_date, amount, currency)`, or `None` with nothing
to project from or when the last ex-date is older than the period plus 45 days (the
instrument has stopped). Helpers: `detect_period_months()`, `add_months()`,
`next_period_start()`.

### `distribution_estimate(dist, currency, today)` and `distribution_history_rows(dist, currency, today)`

From a `Distribution`: the next occurrence of one of its ex-dates on or after `today`
(29 February is the 28th in a common year), paid `pay_offset_days` later, for that
slot's amount; and the `config` history rows a line asserts, which exist only when it has
amounts and an `as-of` date (the latest occurrence on or before `as-of` and `today`).

### `upcoming_rows_for(identifier, stored, history_dates, last_paid, declared, estimate, today)`

One instrument's upcoming rows. A stored estimate with an ex-date still to come is
recomputed; a stored declaration is kept until Yahoo names another; a declared ex-date not
yet in the history replaces the estimate for that period; a row leaves 7 days after its
ex-date once it is in the history, and after 30 days regardless. `AsOf` is `today` for
rows produced or confirmed this run.

### `build_dividend_upcoming(specs, distributions, history, stored, declared, today, currencies)`

The whole upcoming file for the instruments in `funds.txt`: the pattern estimate, or the
`distributions.txt` estimate for an instrument that has a line (currency from
`currencies`, identifier to the currency of its newest stored price). Closed holdings and
removed funds get no rows. Returns rows sorted by ex-date then fund.

### `update_dividends(specs, distributions, data_dir=None, today=None)`

The daily run: fetch (the whole history when `dividends_history.csv` does not exist,
otherwise the last `DIVIDEND_WINDOW_DAYS`), upsert, add the `config` rows, write the
history, rebuild and write the upcoming file. Never deletes. Returns `DividendResults`;
`.summary` holds the `DividendSummaryRow` entries that are news today.

### `backfill_dividends(specs, distributions, start=None, data_dir=None, today=None)`

The rebuild: for every `YA` instrument that fetches, its source rows from `start`
(everything when `None`) are replaced by what Yahoo reports; `config` rows stay; an
instrument that fails keeps what it had. Rebuilds the upcoming file without a calendar
lookup. Returns a `BackfillReport`.

### `validate_dividend_backfill_args(args)`

An error message for `--backfill-dividends` combined with another mode or given a bad
`--from`, else `None`. `--from` is optional.

### `build_dividend_summary(previous, upcoming, specs)`, `DividendSummaryRow`

The upcoming rows that are new or whose pay date or status changed since the previous
file, once per instrument under its lookup identifier, in `funds.txt` order.

## History Rebuild

`--backfill --from YYYY-MM-DD` replaces stored history with what the sources report.
Manual only: locally, or through the **Rebuild Price History** workflow.

### `validate_backfill_args(args)`

Returns an error message for an invalid invocation, else `None`. Rejects `--backfill`
combined with `--history`, a missing or malformed `--from`, and a date in the future.

### `backfill_history(specs, start, data_dir=None)`

Rebuilds every identifier in `specs` from `start` and returns a `BackfillReport`.

- **Deletes rather than upserts**, because carry-forward rows sit on dates the sources
  never report and would otherwise survive.
- An instrument whose fetch fails keeps every row it had.
- Rows before `start`, and rows for identifiers not in `specs` — including closed
  holdings — are never touched.
- `latest_prices.csv`, the rolling window and the `.price` files are rebuilt for the
  configured identifiers only.
- FT requests are separated by `FT_BACKFILL_PAUSE_SECONDS`.
- Finishes by calling `backfill_fx()` when `fx_pairs.txt` has pairs.

### `is_removable_row(row)`

True when a rebuild may delete a stored row the source did not return: always for a
weekend row, otherwise only when the row has no currency. A currency-bearing row came
from a dated source fetch and is kept, because FT's endpoint intermittently omits real
trading days from identical requests.

### `check_quoting_unit(identifier, quotes)`

Returns a warning when consecutive prices differ by more than `QUOTING_UNIT_FACTOR`
(50), the signature of a pence/pounds switch. Used by both the rebuild and the
closed-holding import.

### `BackfillReport`

`entries`, `failures` and `warnings`, with `to_markdown()` rendering the reconciliation
table printed to stdout and appended to the Actions job summary. Shared by the rebuild
and the closed-holding import.

## Storage Helpers

### `read_history_rows(history_csv)`

Returns stored history as `{(fund, date): [fund, date, price, currency]}`, loading
legacy three-column rows with an empty currency.

### `write_history_csv(rows, data_dir)`

Writes `prices_history.csv` sorted by date then fund and returns the rows as written.
Used on its own by the closed-holding import, which must not touch any other file.

### `write_history_files(rows, data_dir, latest=None)`

Writes `prices_history.csv`, `latest_prices.csv` and `prices_history_90_days.csv`.
Shared by the daily run and the rebuild so both produce byte-identical output.

When `latest` is supplied it names the funds currently being priced, and the rolling
window is limited to that set. When omitted, `latest` is derived from `rows` and the
window covers every fund.

### `latest_rows_by_fund(rows)`

Returns `{fund: row}` holding each fund's row with the newest price date.

### `write_latest_price_file(fund_id, price, data_dir)`

Writes `latest_<fund_id>.price`.

### `open_for_write(path, **kwargs)` and `csv_writer(file)`

Every output file goes through these. They force LF line endings on every platform:
`csv.writer` defaults to CRLF everywhere and Windows text mode translates LF to CRLF,
which once made a four-row update show as 3,906 changed lines.

## Source Code Helpers

### `canonical_source(code, line_number=None)`

Upper-cases a source code and maps a deprecated one (`GF` → `YA`, via
`SOURCE_ALIASES`), printing a warning that names the line.

### `as_fund_spec(entry)`

Accepts a `FundSpec` or a plain `(source, identifier)` pair and returns a `FundSpec`
with a canonical source, so a spec built in code cannot carry a deprecated spelling
past the dispatch points.

## Entry Point

### `main()`

Dispatches on the parsed arguments, in this order: `--backfill`, `--import-closed`,
`--backfill-dividends`, `--history`, otherwise the daily run. The daily run validates
`distributions.txt` with `funds.txt` before any network call, then writes prices, then FX,
then the dividend files, then the summary, each independently (a crash in the dividend
update is reported as a failure and costs the summary nothing), and exits non-zero only
after everything obtainable has been written. The rebuilds and the import exit non-zero
when their report has failures.

## Daily Summary

### `build_price_summary(history_rows, specs, failures, run_date)`

Summarises each configured instrument's latest movement.

`old` is the price on the previous **distinct** price date, never the calendar day
before. An aliased instrument is reported once, under its lookup identifier.

**Returns:** `list[SummaryRow]` in `funds.txt` order.

### `summarise_series(name, aliases, rows, failures, run_date, places=None)`

Builds one `SummaryRow` from a series' stored rows: the newest value against the
previous **distinct** date, its age in days, and whether it is stale or failed. Shared
by the price and FX summaries.

### `compare_values(new_text, old_text, places=None)` and `format_decimal(value, places=None)`

Return the delta and percent delta as strings, using `decimal.Decimal` so that
7.15 - 7.09 is exactly 0.06. An old value of zero yields no percentage rather than a
division error. `format_decimal()` renders without exponent notation.

### `build_fx_summary(fx_rows, pairs, failures, run_date)`

The same, for currency pairs, with values at 6 decimal places.

### `render_summary_markdown(price_rows, fx_rows, run_date, dividend_rows=None)`

Renders prices, FX, a Dividends section when `dividend_rows` is given (`None` text when
it is empty), an Attention section and the biggest movers. Pure: no clock, no network.

### `write_summary(price_rows, fx_rows, run_date, data_dir=None, dividend_rows=None)`

Writes `data/daily_summary.csv` and `data/daily_summary.md`, and appends the Markdown to
`$GITHUB_STEP_SUMMARY` when set. The CSV has one row per instrument and does not carry
the dividends.

**Arithmetic note**: deltas use `decimal.Decimal`, so `7.15 - 7.09` is `0.06` rather
than the binary float `0.0600000000000005`. A previous price of zero yields an empty
percentage instead of a division error.

## FX Rates

### `read_fx_pairs(filename=FX_PAIRS_FILE)`

Reads currency pairs to snap. One six-letter pair per line; blank lines and `#` comments
ignored. A missing file returns `[]`, so FX is optional.

**Raises:** `ValueError` naming the line, for a malformed or repeated pair. The slash
spelling (`GBP/NZD`) is rejected deliberately: by market convention it means the inverse
of the stored direction, so accepting it would store plausible but wrong values.

### `fetch_fx_quotes(pair, start, end=None, today=None, now=None)`

Fetches dated rates as **GBP per 1 unit of the base currency**, via Yahoo's direct
`<PAIR>=X` ticker. A day's rate is its 17:00 New York close, picked from hourly bars
by `new_york_fx_closes()` (#80). Days older than Yahoo's 730-day hourly history come
from the daily bars, weekends dropped; that daily Close is the day's opening rate.
Rates are formatted at a fixed 6 decimal places, unlike prices, which keep the
source's own precision. `today` and `now` default to the clock and exist for tests.

**Returns:** `list[Quote]`, whose `currency` field carries the pair name.

### `new_york_fx_closes(bars, now=None)` and `fetch_yahoo_hourly(symbol, start, end=None)`

`fetch_yahoo_hourly()` returns `(bar start in UTC, close)` pairs from Yahoo's hourly
bars; a bar's close is the price at the end of its hour. `new_york_fx_closes()` picks,
for each weekday, the close of the last bar ending at or before 17:00 New York, and
returns a day only once that cut has passed, so the result does not depend on when
the job runs.

### `snap_fx_rates(pairs, data_dir=None)`

Fetches a window of rates per pair, isolating failures so one dead pair does not cost
the others.

**Returns:** `ScrapeResults` of `[pair, date, rate]` rows.

### `write_fx_results(results, data_dir=None)`

Upserts rates on **(Pair, Date)** into `data/fx_history.csv` and regenerates
`data/latest_fx.csv`. Headers are `Pair,Date,Rate`.

A day is fetched only after its 17:00 New York cut, so no rate is provisional; the
upsert still lets a later run correct the last 10 days if Yahoo revises a bar.

### `read_fx_rows(fx_csv)`, `write_fx_files(rows, data_dir)` and `format_fx_rate(value)`

`read_fx_rows()` returns stored rates keyed on `(Pair, Date)`. `write_fx_files()` writes
`fx_history.csv` and `latest_fx.csv` from an authoritative row set **without merging**,
so a rebuild that removed rows really removes them; `write_fx_results()` does the
merging for the daily run before calling it. `format_fx_rate()` renders a rate at a
fixed `FX_RATE_DECIMALS` places, unlike prices, which keep the source's own precision.

### `backfill_fx(pairs, start, data_dir=None, report=None)`

Rebuilds stored rates from the start date using the same rule as the price rebuild.
Called automatically by `--backfill` when `fx_pairs.txt` exists.

## Configuration Constants

### Data Directory Settings
- `DATA_DIR`: Default data directory ("data")
- `LATEST_CSV`: Latest prices file path
- `HISTORY_CSV`: Historical prices file path
- `FUNDS_FILE`: Default funds configuration file ("funds.txt")

- `CLOSED_HOLDINGS_FILE`: One-off import configuration ("closed_holdings.txt")
- `FX_PAIRS_FILE`: FX pair configuration ("fx_pairs.txt")
- `DISTRIBUTIONS_FILE`: Distribution schedules for instruments no source covers ("distributions.txt")

### Behaviour Settings
- `MAX_PRICE_ATTEMPTS`: Fetch attempts before falling back to the last known price (3)
- `ROLLING_HISTORY_DAYS`: Inclusive window for `prices_history_90_days.csv` (90)
- `SNAP_WINDOW_DAYS`: Days of dated quotes each daily run requests (10), so a late or
  corrected price is picked up by the upsert
- `STALE_AFTER_DAYS`: Age beyond which the summary marks an instrument `~` (4)
- `QUOTING_UNIT_FACTOR`: Price ratio that triggers a quoting-unit warning (50)
- `FT_BACKFILL_PAUSE_SECONDS`: Pause between FT requests during a rebuild (1)
- `FX_RATE_DECIMALS`: Decimal places stored for FX rates (6)
- `DIVIDEND_WINDOW_DAYS`: Days of Yahoo dividend events each daily run re-reads once a
  history exists (400)
- `ESTIMATE_WINDOW_DAYS`, `ESTIMATE_STOP_MARGIN_DAYS`, `FREQUENCY_BANDS`: the twelve-month
  window, the 45-day margin after which a silent payer has stopped, and the median-gap
  bands that name the frequency (365, 45, 45/135/270 days)
- `UPCOMING_GRACE_DAYS`, `UPCOMING_MAX_AGE_DAYS`: how long an upcoming row outlives its
  ex-date once it is in the history, and at most (7, 30)
- `DISTRIBUTION_FREQUENCIES`: payments a year for each frequency `distributions.txt`
  accepts
- `SOURCE_ALIASES`: Deprecated source codes and their replacements (`{"GF": "YA"}`)
- `LINE_ENDING`: Line ending for every written file (LF)

### Endpoints and Timeouts
- `FT_HISTORICAL_PAGE`, `FT_HISTORICAL_AJAX`, `FT_REQUEST_TIMEOUT` (30s)
- `INVESTING_HISTORICAL_URL`, `INVESTING_HEADERS`, `INVESTING_REQUEST_TIMEOUT` (30s).
  The headers carry a realistic browser user agent; a bare `Mozilla/5.0` gets a 403

### File Headers
- `HISTORY_HEADER`: `Fund,Date,Price,Currency`
- `FX_HEADER`: `Pair,Date,Rate`
- `DIVIDEND_HISTORY_HEADER`: `Fund,ExDate,PayDate,Amount,Currency,Source`
- `DIVIDEND_UPCOMING_HEADER`: `Fund,ExDate,PayDate,Amount,Currency,Status,AsOf`
- `SUMMARY_HEADER`: columns of `daily_summary.csv`

## Error Handling

### Common Exceptions
- `FileNotFoundError`: When a configuration file doesn't exist
- `ValueError`: A malformed configuration line (the message names the line), an
  unsupported source, or a source that returned no rows
- `TimeoutError`: When a scraped page or selector wait times out

Inside a run these are caught per instrument and surface on `.failures` or in a
`BackfillReport`; no error text is ever written to a data file.

## Usage Examples

### Basic Usage
```python
from scrape_fund_price import scrape_funds, read_fund_ids, write_results

# Read fund configuration
funds = read_fund_ids("funds.txt")

# Fetch dated quotes, then store them
results = scrape_funds(funds)
write_results(results)
```

### Custom Data Directory
```python
results = scrape_funds(funds, data_dir="custom_data")
```

### Single Fund Scraping
```python
from scrape_fund_price import get_source_config, scrape_price_with_common_settings
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    
    url, selector = get_source_config("FT", "GB00B1FXTF86")
    price = scrape_price_with_common_settings(page, url, selector)
    
    browser.close()
```

## Dependencies

- `yfinance`: Yahoo Finance daily bars, FX rates and ad-hoc history
- `requests`: FT and investing.com HTTP endpoints
- `numpy`: float32 round-tripping, so prices are stored exactly as quoted
- `playwright`: Scraping fallback
