# API Reference

This document provides detailed API documentation for the Fund Price Scraping project.

## Core Functions

### `FundSpec(source, lookup_id, aliases=())`

One configured instrument.

- `source` (str): canonical source code (`YA`, `FT`, `IV`). `GF` is accepted on input and canonicalised to `YA`
- `lookup_id` (str): the identifier sent to the source
- `aliases` (tuple): extra identifiers to publish under
- `publish_ids` (property): `lookup_id` followed by each alias

### `read_fund_specs(filename)`

Reads instrument configuration.

**Line grammar:** `<source>,<lookup_id>[,<alias>[;<alias>...]]`. Blank lines, full-line
`#` comments and trailing comments are ignored.

**Returns:** `list[FundSpec]`

**Raises:** `ValueError` naming the offending line, for a malformed line, a retired
source code (`YH`, `MS`; see `RETIRED_SOURCES`), an empty or self-referencing alias, or
an identifier repeated anywhere in the file. Validation runs before any network call, so
a bad config cannot fail half way through a run.

```python
read_fund_specs("funds.txt")
# [FundSpec(source="YA", lookup_id="0P00000YAN", aliases=("JFM0003373",)), ...]
```

### `get_source_config(source, fund_id)`

Gets the URL and CSS selector for the scraping fallback of a source and fund ID.

**Parameters:**
- `source` (str): Source identifier; only `FT` has an entry
- `fund_id` (str): Fund identifier

**Returns:**
- `tuple`: (url, selector), or (None, None) for a source that is not scraped

**Supported Sources:**
- **FT**: Financial Times (`https://markets.ft.com/data/funds/tearsheet/summary?s={fund_id}`),
  used only when `fetch_ft_quotes()` fails
- **YA** and **IV** fetch rather than scrape and return `(None, None)` here. The `YH` and
  `MS` scrapers were removed in #110

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

### `fetch_yahoo_quotes(symbol, start, end=None, now=None)`

Fetches dated daily quotes from Yahoo Finance.

**Parameters:**
- `symbol` (str): Yahoo ticker (e.g. `IDTG.L`, `0P00000YAN`)
- `start` (str): Inclusive ISO start date
- `end` (str, optional): **Exclusive** ISO end date; `None` for the latest bar
- `now` (datetime, optional): Aware time used to judge whether the newest bar's session
  is over; `None` for the current time. It exists for tests

**Returns:** `list[Quote]`, oldest first

Uses `Close` with `auto_adjust=False`, so values match the price quoted that day rather
than a dividend-adjusted series. Does **not** use the summary endpoint (`.info`), which
carries no date and was observed returning a stale price for mutual funds. Exceptions
propagate so `fetch_with_retries()` can retry them.

Three guards stop a bad bar becoming a stored price (#78, #83, #84); the last two print a
warning naming the symbol and date when they drop a bar:

- **Null newest close.** Yahoo sometimes serves the newest bar with a null close for hours
  after the session ended. Its close is then taken from the chart metadata by
  `closing_price_from_metadata()`, or the bar is dropped when that gives `None`. Only the
  newest bar is filled this way; any other null-close bar is dropped.
- **Open session.** A priced newest bar is dropped while `session_still_open()` says its
  regular session has not ended, so a run during market hours stores no intraday price.
- **Untraded spike.** An interior bar (never the first or last) that
  `is_untraded_spike()` flags is dropped.

### `UNTRADED_SPIKE_RATIO` and `is_untraded_spike(close, volume, previous, following)`

`UNTRADED_SPIKE_RATIO` is `1.2`. `is_untraded_spike()` is true for an isolated, untraded
outlier (#83): the bar's `volume` is exactly `0` and its `close` is more than 20% above
both neighbouring closes, or more than 20% below both. A real move either traded or
persists into the next bar. A volume of `None` or any non-zero number is never a spike
(funds report no volume, so zero volume alone proves nothing). Used by
`fetch_yahoo_quotes()`.

### `session_still_open(ticker, bar_date, now=None)`

True when `bar_date`'s regular session has not ended (#84): the chart metadata's
regular trading period ends on `bar_date` and `now` (default: the current UTC time) is
before that end. Unusable metadata gives `False`, so a price that is probably final is
kept rather than lost.

### `closing_price_from_metadata(ticker, bar_date)`

The finished session's price for `bar_date` from the chart metadata
(`regularMarketPrice`), or `None`. The price must be finite and positive, must have traded
on `bar_date` (exchange time), and the regular session must be over. Any missing or
malformed field gives `None`.

### `fetch_ft_quotes(isin, start, end=None, now=None)`

Fetches dated daily quotes from Financial Times: two plain GETs (`http_get()`), the
tearsheet page that resolves FT's internal id for the fund, then the rows.

**Parameters:**
- `isin` (str): Fund ISIN as used in `funds.txt`
- `start` (str): Inclusive ISO start date
- `end` (str, optional): Inclusive ISO end date; `None` for today
- `now` (datetime, optional): Aware time used to judge whether a row's day is over;
  `None` for the current time

**Returns:** `list[Quote]`, oldest first. Empty when every row was held back as
provisional; that is not an error, because the scraping fallback would store the same
provisional price.

**Raises:** `ValueError` when FT's internal id cannot be resolved or no rows are
returned, so the caller can fall back to scraping.

Two plain HTTP requests, no browser. Prices are kept as text so published digits are
preserved exactly.

A row is stored only once `ft_row_settled()` says 16:00 New York (the US close) on its
own date has passed (#84). FT serves a provisional row for the current day that moves
until the evening and carries no session times to judge it by; the 21:05 UTC run is after
the cut all year round. A held-back row prints a warning. The undated scraping fallback
is not covered.

### `FT_SETTLED_HOUR` and `ft_row_settled(price_date, now=None)`

`FT_SETTLED_HOUR` is `16`, read in the `America/New_York` zone (`FT_SETTLED_ZONE`).
`ft_row_settled()` is true once that hour on `price_date` (a `datetime.date`) has passed;
`now` defaults to the current UTC time. Used by `fetch_ft_quotes()`.

### `scrape_fund_quotes(source, fund_id, start, end=None, browser=None)`

Returns dated quotes for one fund from its configured source: `YA` via
`fetch_yahoo_quotes()`, `IV` via `fetch_investing_quotes()`, and `FT` via
`fetch_ft_quotes()`, falling back from FT's endpoint to scraping when needed. The scraped
page shows only the current price, so a fallback quote carries the run date and an empty
currency. Any other code raises `ValueError`.

### `LazyBrowser`

Starts Playwright on first use, so a configuration that needs no scraping never
launches Chromium. `page()` returns a live page; `close()` is safe if unused.

### `scrape_funds(funds, data_dir=None)`

Main function to scrape prices for a list of funds. Playwright starts only if an FT
fetch falls back to scraping (see `LazyBrowser`).

**Parameters:**
- `funds` (list): `FundSpec` instances, or plain `(source, identifier)` pairs, which
  `as_fund_spec()` converts. Each fund is fetched once on its lookup id and published
  under every alias
- `data_dir` (str, optional): Directory to store results (defaults to `"data"`)

**Returns:**
- `ScrapeResults`: a `list` subclass of `[fund_id, date, price, currency]` rows, one
  per dated quote in the last `SNAP_WINDOW_DAYS` (10) days, with two extra attributes:
  - `.failures`: `"<lookup_id>: <error>"` strings for funds whose every attempt failed
  - `.carried`: the newest stored row (`newest_stored_rows()`) for each of those
    funds, under its original date, so `latest_prices.csv` keeps reporting a real
    price. A fund with no stored row has no carried row and is simply absent; its
    `.price` file alone carries nothing, since the file holds no date

**Result Format:**
```python
results = scrape_funds([("YA", "AAPL"), ("FT", "GB00B1FXTF86")])
# [["AAPL", "2026-09-18", "150.25", "USD"], ["GB00B1FXTF86", "2026-09-18", "7.15", "GBP"], ...]
results.failures
# ["GB00B1FXTF86: Error: Timeout"]   (only for funds that failed all attempts)
```

**Side effect:** writes `data/latest_<identifier>.price` for each fund, except that a
fetch older than the newest stored row for that identifier does not replace it
(`keep_newer_stored_row()`, #78).

### `write_results(results, data_dir=None)`

Writes scraping results to CSV files.

**Parameters:**
- `results` (list): List of `[fund_id, date, price, currency]` rows
- `data_dir` (str, optional): Directory to write files (defaults to `"data"`)

**Output Files:**
- `latest_prices.csv`: Most recent price per fund, overwritten each run. It never goes
  backwards (#78): where the newest stored row (from `latest_prices.csv` or history) is
  newer than the fetched one, the stored row stays and a warning is printed. The same
  date still replaces, so a correction applies
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

### `fetch_historical_data(symbol, start_date, end_date=None, data_dir=None)`

The `--history` export: one symbol's dated closes from Yahoo, written as a CSV of its own
on the daily run's path. The bars come from `fetch_yahoo_quotes()` through
`fetch_with_retries()`, so each row is dated as Yahoo dates it, carries the currency and is
formatted by `format_yahoo_price()`, exactly as `prices_history.csv` would store it.
Nothing else is touched: not `prices_history.csv`, not `latest_prices.csv`, no `.price` file.

**Parameters:**
- `symbol` (str): Yahoo ticker; it need not be in `funds.txt`
- `start_date` (str): Inclusive start date, `YYYY-MM-DD`
- `end_date` (str or None): Inclusive end date; `None` means up to the latest bar. Yahoo
  treats the end as exclusive, so the fetch asks for the day after, as the closed-holding
  import does
- `data_dir` (str, optional): Output directory; `DATA_DIR` at call time when `None`

**Returns:** `HistoryReport`. A symbol that fails after the retries, or returns no bars at
all (Yahoo answers an unknown ticker with an empty frame), is on `failures` as
`<symbol>: <error>` and no file is written.

**Output:** `data/history_<symbol>_<start>_<end>.csv` with the history header
`Fund,Date,Price,Currency`; `<end>` is today's date when `end_date` is `None`.

**Example:**
```python
report = fetch_historical_data("AAPL", "2024-01-01", "2024-12-31")
print(report.path, len(report.rows), report.failures)
```

### `HistoryReport`

What an export wrote: `symbol`, `path`, `rows` (the `[symbol, date, price, currency]` rows
written, oldest first) and `failures`. `to_markdown()` renders one table row
(`Symbol | Rows | First | Last | Ccy | File`) and a **Failures** list, for stdout and the
Actions job summary, like `BackfillReport`.

### `validate_history_args(args)`

Returns an error message for an invalid `--history` invocation, else `None`; `None` too when
`--history` was not given. Rejects a combination with `--backfill`, `--import-closed` or
`--backfill-dividends`, a missing, malformed or future `--start`, a malformed `--end` and an
`--end` before `--start`. `main()` exits 2 on an error, before any network call.

### `validate_iso_date(value, flag)` and `validate_start_date(value, flag="--from")`

`validate_iso_date` returns `Invalid <flag> date format. Use YYYY-MM-DD` for anything but a
real `YYYY-MM-DD` date, else `None`. `validate_start_date` adds `<flag> date is in the
future`; the rebuilds call it for `--from`, the export for `--start` (one argument, two
spellings).

### `parse_arguments(args=None)`

Parses the command line:

- `--history SYMBOL` with `--start YYYY-MM-DD` and optional `--end YYYY-MM-DD`
- `--backfill` with `--from YYYY-MM-DD` (`--from` is an alias of `--start`)
- `--import-closed`
- `--backfill-dividends` with an optional `--from YYYY-MM-DD`

With none of these, the daily run executes. `args=None` reads `sys.argv`; pass a list
in tests. Parsing does not reject combinations: `main()` checks a rebuild with
`validate_backfill_args()` or `validate_dividend_backfill_args()` and an export with
`validate_history_args()`.

## Resilience: Retries and Last Known Price

A transient failure does not write an error into the price files. Each fetch is retried,
and if every attempt fails the fund falls back to its most recent good price.

### `fetch_with_retries(fetch_price, attempts=MAX_PRICE_ATTEMPTS)`

Calls `fetch_price()` up to `attempts` times (default 3), retrying raised exceptions.

**Returns:**
- `tuple`: `(price, None)` on success, or `(None, last_error)` if every attempt failed

### Supporting helpers

- `is_error_price(price)` - True when a stored value is an `"Error: ..."` string left by
  an old run
- `normalize_price(price)` - normalises a price value for storage
- `is_usable_price(price)` - True when a value is a real price rather than an error or placeholder

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

**Raises** `ValueError` naming the line for a malformed line, a retired source code
(`YH`, `MS`), an unparseable or reversed date, or a repeated identifier.

### `fetch_investing_quotes(pair_id, start, end=None)`

Dated daily closes from investing.com, for a delisted line that Yahoo and FT no
longer carry: one GET (`http_get()`, `INVESTING_HEADERS`). Returns `list[Quote]` oldest first with **no currency**: the
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

Each window is fetched through `fetch_with_retries()` with a `LazyBrowser`, so a
transient failure is retried like any other fetch and an FT fallback to scraping has
a page; a holding that still fails is recorded and the rest are imported.

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
instrument. A history row is a `DividendRow(fund, ex_date, pay_date, amount, currency,
source)` NamedTuple whose `HEADER` is the file's header (`DIVIDEND_HISTORY_HEADER` is an
alias of it), and an upcoming row an `UpcomingRow(fund, ex_date, pay_date, amount,
currency, status, as_of)` whose `HEADER` `DIVIDEND_UPCOMING_HEADER` aliases. Both readers
build them through `read_keyed_csv()`'s row factory and `fund_and_ex_date(row)` keys both.

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
(`Universe.all_identifiers`) and those of `closed_holdings.txt`.

### `Universe(specs, lookup_of, publish_ids_of, all_identifiers)`

The configured instruments, mapped once per run: `Universe.from_specs(specs)` canonicalises
each spec (`as_fund_spec()`) and builds `lookup_of` (published identifier to lookup id),
`publish_ids_of` (lookup id to its published identifiers, lookup id first) and
`all_identifiers` (a frozenset). `universe.published(identifier)` is every identifier the
instrument behind `identifier` is published under, or `(identifier,)` for one `funds.txt`
does not publish (a closed holding). The dividend steps take it, through a `DividendRun`,
in place of the specs.

### `DividendRun(today, universe, currencies, data_dir)`

What every step of one dividend run shares: the run date, the `Universe`, identifier to the
currency of its newest stored price (`stored_currencies()`, read once per run) and the data
folder. `DividendRun.prepare(specs, data_dir=None, today=None)` settles one (defaults
`DATA_DIR` and today); `run.price_currency(identifier)` is the first stored currency among
the instrument's identifiers, `""` when none has one. `update_dividends()` and
`backfill_dividends()` prepare one and pass it as the first argument of each step.

### `DividendEvent(ex_date, amount, currency)` and `DeclaredDividend(ex_date, pay_date, amount="", currency="")`

A past dividend as Yahoo reports it, and the next announced one: its ex-date, its pay date
(`""` when absent or not after the ex-date) and, when the source states it (only an
issuer does, SPEC-011), the amount in the price currency. A declared row carries the
amount when set and the last paid otherwise.

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

### `collect_dividends(run, start=None)`

For each `YA` instrument, one retried fetch of the events (published under every alias,
`Source` `YA`, `PayDate` empty, events after `run.today` ignored) and one of the declared
dividend. Returns `DividendResults`, a list of history rows with `.failures`
(`"<id>: dividends: <error>"`), `.declared` (lookup id to `DeclaredDividend`), `.fetched`
and `.summary`. A failed declared lookup prints a warning and is not a failure.

### `read_dividend_history(data_dir)` and `write_dividend_history(rows, data_dir)`

`read` returns rows keyed `(Fund, ExDate)` (rows without either are skipped); `write`
sorts by ex-date then fund, with LF endings. Both are `read_keyed_csv()` and
`write_sorted_csv()` wrappers, as are `read_dividend_upcoming()` (which returns the
rows as a list) and `write_dividend_upcoming()`.

### `merge_dividend_rows(stored, incoming)`

Upserts into a history dict. An incoming row replaces the stored one, except that a row
from a source that knows less never replaces one from a source that knows more
(`SOURCE_AUTHORITY`: `IS`, `IV`, `SS`, `Q4`, `ET` 2, `YA` 1, `config` 0; `source_authority(row)`).

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

### `upcoming_rows_for(run, identifier, stored, history_dates, last_paid, *, declared=None, estimate=None)`

One instrument's upcoming rows. A stored estimate with an ex-date still to come is
recomputed; a stored declaration is kept until Yahoo names another; a declared ex-date not
yet in the history replaces the estimate for that period; a row leaves 7 days after its
ex-date once it is in the history, and after 30 days regardless. `AsOf` is `run.today`
for rows produced or confirmed this run.

### `build_dividend_upcoming(run, distributions, history, stored, declared)`

The whole upcoming file for the instruments in `funds.txt`: the pattern estimate, or the
`distributions.txt` estimate for an instrument that has a line (currency
`run.price_currency()`). Closed holdings and removed funds get no rows. Returns rows sorted
by ex-date then fund. `publish_upcoming(run, distributions, history, declared)` reads the
previous file, builds and writes the new one, and returns `(previous, upcoming)`;
`config_history_rows(run, distributions)` is the `config` rows of every line.

### `update_dividends(specs, distributions, data_dir=None, today=None, sources=())`

The daily run: fetch (the whole history when `dividends_history.csv` does not exist,
otherwise the last `DIVIDEND_WINDOW_DAYS`), upsert, add the `config` rows, apply the
issuers' tables, write the history, rebuild and write the upcoming file. Never deletes.
Returns `DividendResults`; `.summary` holds the `DividendSummaryRow` entries that are news
today, `.failures` also the `"<id>: pay dates: <error>"` lines of issuer pages.

### `backfill_dividends(specs, distributions, start=None, data_dir=None, today=None, sources=())`

The rebuild: for every `YA` instrument that fetches, its `YA` rows from `start`
(everything when `None`) are replaced by what Yahoo reports, and its `IS` rows too where
the issuer's page fetched (the issuer's table is applied last); an instrument with no
Yahoo route has its `IS` rows rebuilt alone and its own line in the report; `config` rows
stay; an instrument that fails keeps what it had. Rebuilds the upcoming file without a
calendar lookup, taking the issuers' declared rows. Returns a `BackfillReport`.

It is a thin writer around two steps: `fetch_rebuild_events(run, start=None)` fetches
Yahoo's events for each `YA` instrument (returns lookup id to its events dated
`run.today` or earlier, and the `"<id>: dividends: <error>"` failures), and
`rebuild_dividend_rows(run, history, distributions, events, issuers, *, start=None)`
computes the rebuilt history without fetching or writing anything, returning
`(history, entries, declared)`: the new history (the argument is not changed), the
`BackfillEntry` of each identifier and the issuers' declared dividends.

## Issuer Dividend Dates

SPEC-011. `dividend_sources.txt` names, per instrument, an issuer page that lists every
distribution with its ex-date, record date, pay date and amount.

### `DividendSource(identifier, source, source_id)`, `read_dividend_sources(filename=None, specs=None)`

One line of `dividend_sources.txt` (`<identifier>,<source>,<source-id>`), read from
`DIVIDEND_SOURCES_FILE` by default. A missing file has no entries. `source` is one of
`DIVIDEND_SOURCE_CODES` (`IS`, `IV`, `SS`, `Q4`, `ET`), uppercased; `source_id` must match `DIVIDEND_SOURCE_ID_RULES[source]` (IS: 1 to 9 digits; IV: CUSIP; SS: ISIN; Q4: `host/MIC`; ET: HK code). With `specs`
the identifier must be one `funds.txt` publishes and two lines may not name one instrument.
Raises `ValueError` naming the line, before any network call.

### `IssuerDistribution(ex_date, record_date, pay_date, amount)`, `IssuerTable(currency, rows, source)`

One distribution as the issuer states it (ISO dates, `""` for a missing record or pay date
or a pay date before the ex-date; `amount` is decimal text in the share class's currency in
major units) and a share class's rows, oldest first, with the class currency (`""` when the
page does not say), and the source code the rows came from (`IS`, `IV`, `SS`, `Q4`, `ET`).

### `parse_ishares_distributions(text, product_id)`

Reads the `performance.distributions.table` container a product page embeds
(entity-escaped, four parallel lists `exDate`, `recordDate`, `payableDate`,
`totalDistribution`) and the class currency from the share-class selector, reading each
row through the issuer helpers the SPEC-012 parsers share (`parse_issuer_date()` takes the
page's YYYYMMDD integers). `ValueError` when there is no table (an accumulating class, or
a changed page) or it is ragged or holds a missing ex-date, a bad date or a bad amount.

### `fetch_ishares_distributions(product_id)` and `fetch_issuer_table(source)`

One GET (`http_get()`) of `https://www.ishares.com/uk/individual/en/products/<id>`
(`ISHARES_PRODUCT_URL`), parsed; `fetch_issuer_table` looks the source code up in
`ISSUER_FETCHERS`, the fetch per code that `DIVIDEND_SOURCE_CODES` is derived from
(`ValueError` for a code it does not know). Errors propagate so `fetch_with_retries()` can
retry them.

### SPEC-012 sources: `fetch_invesco_distributions(cusip)`, `fetch_ssga_distributions(isin)`, `fetch_q4_distributions(source_id, symbol)`, `fetch_etnet_distributions(code)`

Each is one GET (`http_get()`; `SSGA_REQUEST_TIMEOUT`, 60 s, for SSGA's workbook, which is kept for the run and shared:
`clear_issuer_caches()` empties it, `collect_issuer_tables()` calls that first), parsed by
`parse_invesco_distributions(text, cusip)`, `parse_ssga_distributions(content, isin)`,
`parse_q4_distributions(text, symbol)` or `parse_etnet_distributions(text, code)`. Every
parser returns an `IssuerTable` oldest first with one row per ex-date (same-day amounts
add up, `combine_same_ex_date()`) and raises `ValueError` naming the source for a response
that is not the recorded shape; `read_xlsx_rows(content)` reads the first sheet of a
workbook with the standard library. Invesco: URLs `INVESCO_DISTRIBUTION_URL`; SSGA:
`SSGA_WORKBOOK_URL`; Q4: `Q4_DIVIDEND_URL`; etnet: `ETNET_DIVIDEND_URL`, cash-dividend rows
only.

### `collect_issuer_tables(run, sources)`

Fetches each configured page once, retried, `ISSUER_PAUSE_SECONDS` apart. Returns
`IssuerResults`: `.tables` (lookup id to `IssuerTable`), `.requested` (every configured
lookup id) and `.failures` (`"<identifier>: pay dates: <error>"`).

### `issuer_amount(text, class_currency, target_currency)` and `amounts_agree(stored_text, amount)`

The issuer's amount in the stored row's currency as an `IssuerAmount(text, currency,
tolerance)`: equal currencies unchanged, `GBP` into `GBp` times 100, a page that names no
currency taken in the row's, zero or incomparable currencies `None`. The tolerance is half
a unit of the issuer's last decimal place; `amounts_agree` is true within it.

### `apply_issuer_table(run, history, identifier, table, start=None)`

Merges the table's distributions dated `run.today` or earlier (and on or after `start`)
into one identifier's history rows: pay date added, `Source` the table's code, a missing
distribution inserted (in `run.price_currency(identifier)`), Yahoo's amount kept when it
agrees and the issuer's when it differs, and a `YA` twin within `ISSUER_TWIN_DAYS` with the
same amount removed. Returns the merged history as a new dict; `history` is not changed.

### `issuer_declared(table, price_currency, today)` and `merge_issuer_tables(run, history, tables, start=None)`

`issuer_declared` returns the earliest distribution with an ex-date after `today` as a
`DeclaredDividend` (amount in the price currency, empty if not statable), or `None`.
`merge_issuer_tables` applies each fetched table (lookup id to `IssuerTable`) under every
alias of its instrument and returns `(history, declared)`: the merged history and lookup
id to `DeclaredDividend`.

### `validate_dividend_backfill_args(args)`

An error message for `--backfill-dividends` combined with another mode or given a bad
`--from`, else `None`. `--from` is optional.

### `build_dividend_summary(previous, upcoming, universe)`, `DividendSummaryRow`

The upcoming rows that are new or whose pay date or status changed since the previous
file, once per instrument under its lookup identifier, in `funds.txt` order.

## History Rebuild

`--backfill --from YYYY-MM-DD` replaces stored history with what the sources report.
Manual only: locally, or through the **Rebuild Price History** workflow.

### `validate_backfill_args(args)`

Returns an error message for an invalid invocation, else `None`. Rejects `--backfill`
combined with `--history`, a missing or malformed `--from`, and a date in the future.

### `backfill_history(specs, start, data_dir=None, pairs=None)`

Rebuilds every identifier in `specs` from `start` and returns a `BackfillReport`.

- **Deletes rather than upserts**, because carry-forward rows sit on dates the sources
  never report and would otherwise survive.
- An instrument whose fetch fails keeps every row it had.
- Rows before `start`, and rows for identifiers not in `specs` — including closed
  holdings — are never touched.
- `latest_prices.csv`, the rolling window and the `.price` files are rebuilt for the
  configured identifiers only.
- FT requests are separated by `FT_BACKFILL_PAUSE_SECONDS`.
- Finishes by calling `backfill_fx()` for `pairs`; `None` (the default, and what
  `main()` passes) reads `fx_pairs.txt`, and an empty list skips the FX rebuild.

### `is_removable_row(row)`

True when a rebuild may delete a stored row the source did not return: always for a
weekend row, otherwise only when the row has no currency. A currency-bearing row came
from a dated source fetch and is kept, because FT's endpoint intermittently omits real
trading days from identical requests.

### `check_quoting_unit(identifier, quotes)`

Returns a warning when consecutive prices differ by more than `QUOTING_UNIT_FACTOR`
(50), the signature of a pence/pounds switch. Used by both the rebuild and the
closed-holding import.

### `BackfillReport` and `BackfillEntry`

`entries`, `failures` and `warnings`, with `to_markdown()` rendering the reconciliation
table printed to stdout and appended to the Actions job summary. Shared by the rebuild
and the closed-holding import.

Each entry is a `BackfillEntry` (`identifier`, `before`, `deleted`, `retained`,
`inserted`, `first`, `last`, `currency`, `status`), built by one of two constructors:
`BackfillEntry.failed(identifier, existing)` for an identifier whose stored keys all
stay, and `BackfillEntry.rebuilt(identifier, before, deleted, retained, inserted)` for
one replaced from its source, `inserted` being the new rows' `(date, currency)` pairs in
date order. Both take a `status` keyword for the import's `imported` and
`skipped, currency mismatch` lines.

## Storage Helpers

### `read_history_rows(history_csv)`

Returns stored history as `{(fund, date): [fund, date, price, currency]}`, loading
legacy three-column rows with an empty currency; a row without a price is skipped.
A `read_keyed_csv()` wrapper.

### `write_history_csv(rows, data_dir)`

Writes `prices_history.csv` sorted by date then fund and returns the rows as written.
Used on its own by the closed-holding import, which must not touch any other file.
A `write_sorted_csv()` wrapper.

### `write_history_files(rows, data_dir, latest=None)`

Writes `prices_history.csv`, `latest_prices.csv` and `prices_history_90_days.csv`.
Shared by the daily run and the rebuild so both produce byte-identical output.

When `latest` is supplied it names the funds currently being priced, and the rolling
window is limited to that set. When omitted, `latest` is derived from `rows` and the
window covers every fund. The window ends on the newest date in `latest` (today when
there is none, or when that stored date does not parse) and runs back
`ROLLING_HISTORY_DAYS` days inclusive; a row whose date does not parse is left out.

### `latest_rows_by_fund(rows)`

Returns `{fund: row}` holding each fund's row with the newest price date.

### `newest_stored_rows(data_dir)`

Returns `{fund: [fund, date, price, currency]}`, the newest usable row per fund across
`latest_prices.csv` and `prices_history.csv` (a missing file is skipped). It is the floor
for the "latest" files: a fetch may not publish anything older. `stored_currencies()`
reads each instrument's currency from it.

### `keep_newer_stored_row(fund, row, stored)`

Returns `row`, or a copy of `stored[fund]` when that row has a **newer** date, printing a
warning that names the fund and both dates (#78). The same date returns `row`, so
corrections apply. Used by `write_results()` for `latest_prices.csv` and by
`scrape_funds()` for the `.price` files, so a stale fetch (Yahoo served no Friday close for
London ETFs for hours) cannot step either back a day, and the 90-day window with it.

### `write_latest_price_file(fund_id, price, data_dir)`

Writes `latest_<fund_id>.price`.

### `open_for_write(path, **kwargs)` and `csv_writer(file)`

Every output file goes through these. They force LF line endings on every platform:
`csv.writer` defaults to CRLF everywhere and Windows text mode translates LF to CRLF,
which once made a four-row update show as 3,906 changed lines.

### `read_keyed_csv(path, header, key, row=list)` and `write_sorted_csv(path, header, rows, key)`

The one reader and one writer behind every stored CSV (prices, FX, the two dividend
files, UK CPI and the Bank Rate; #112). `read_keyed_csv()` returns `{key(row): row}`
in file order: a missing file is `{}`, every row is padded or truncated to the header's
width so a legacy or damaged row still reads, `row` builds the stored value from that
list of fields (a list by default; pass a NamedTuple's `_make` for typed rows), `key`
sees the built row, and a row the key maps to `None` is skipped. `write_sorted_csv()` creates the directory, writes the header and the rows
sorted by `key` through `open_for_write()` and `csv_writer()`, and returns the rows as
written. Sorting is what makes a repeated run byte-identical. The twelve readers and
writers named in this document keep their own names and signatures as wrappers.

## Source Code Helpers

### `config_lines(filename, label)`

The line iteration the five configuration readers share. Yields `(number, fields, error)`
for each entry line of the file: `number` counts every line, so an error names the line
an editor shows; `fields` are the line's comma-separated fields, stripped, with a trailing
`#` comment removed (blank and comment-only lines are skipped); `error(message)` returns
the `ValueError` for that line, prefixed `<label> line <number>:` (`funds file`,
`closed holdings`, `distributions file`, `fx pairs file`, `dividend sources file`). Each
reader keeps its own field validation. `first_use(seen, noun, value, number, error)`
records a value's first line and raises `<noun> <value> already used on line N` for a
repeat; `configured_source(code, number, error)` is `canonical_source()` plus the
rejection of a retired code.

### `canonical_source(code, line_number=None)`

Upper-cases a source code and maps a deprecated one (`GF` → `YA`, via
`SOURCE_ALIASES`), printing a warning that names the line. A retired code (`YH`, `MS`,
in `RETIRED_SOURCES`) passes through unchanged; `read_fund_specs()` and
`read_closed_holdings()` reject it, naming the line.

### `as_fund_spec(entry)`

Accepts a `FundSpec` or a plain `(source, identifier)` pair and returns a `FundSpec`
with a canonical source, so a spec built in code cannot carry a deprecated spelling
past the dispatch points.

## UK CPI

The UK consumer price index (SPEC-013): `data/uk_cpi.csv` (`Month,Index,Series,AsOf`), written by
the daily run. The header is `UK_CPI_HEADER`; the series id `UK_CPI_SERIES` (`D7BT`), the first
month `UK_CPI_START` (`2015-01`) and the endpoint `UK_CPI_URL`.

### `parse_ons_cpi(text)`

Read the ONS time-series JSON into `{"YYYY-MM": index text}`, oldest first, from `2015-01`. The
index is the ONS's own text. A month listed with an empty value is absent.

**Raises**: `ValueError` for a response that is not JSON, is not series D7BT, has no months, does
not reach `2015-01`, skips or repeats a month, names an unknown month, or holds an index that is
not a positive plain decimal.

### `fetch_uk_cpi()`

One GET (`http_get()`) of `UK_CPI_URL` with `UK_CPI_HEADERS` (the browser `User-Agent`), parsed by `parse_ons_cpi()`. Errors
propagate so `fetch_with_retries()` can retry them.

### `read_uk_cpi(data_dir)` and `write_uk_cpi(rows, data_dir)`

Read `uk_cpi.csv` keyed on `Month` (a missing file is `{}`); write it sorted by month with LF
endings. Rows are `[Month, Index, Series, AsOf]`. `read_keyed_csv()` and `write_sorted_csv()`
wrappers.

### `update_uk_cpi(data_dir=None, today=None)`

Fetch with retries; every month in the response replaces the stored row. A new or changed month
takes the run date as `AsOf`, an unchanged one keeps its `AsOf`, so a run that reads the same
numbers leaves the file byte-identical; stored months the response lacks are kept. On a failed or refused response the file is not
touched and the result's `failures` holds `"uk_cpi: <error>"`.

**Returns**: `UkCpiResults` (`failures`). `main()` calls it after the dividends, in the normal mode
only, and adds its failures to the run's.

## UK Bank Rate

The Bank of England Bank Rate (SPEC-014): `data/uk_bank_rate.csv` (`Month,Rate,Series,AsOf`),
written by the daily run. The header is `UK_BANK_RATE_HEADER`; the series id `UK_BANK_RATE_SERIES`
(`UK_BANK_RATE`), the first month `UK_BANK_RATE_START` (`2015-01`) and the page `UK_BANK_RATE_URL`
(the Bank Rate history page; the database CSV routes are disallowed by the Bank's robots.txt).

### `parse_boe_bank_rate(text, today=None)`

Read the history page's table into `[(datetime.date, rate text)]`, oldest first, the **whole**
table (back to 1975) because the rate in force at 2014-12-31 is an old change. Two-digit years are
20yy unless that is after `today`, then 19yy. The rate is the Bank's own text.

**Raises**: `ValueError` for a page with no `stats-table`, no rows, a row that is not a date and a
rate, a date or rate that does not parse, a date listed twice, or a history that does not reach
2014-12-31.

### `uk_bank_rate_by_month(changes, today)`

`{"YYYY-MM": rate text}` from `2015-01` to the month of `today`: the rate of the newest change on or
before the month's last day (for the current month, on or before `today`). Repeats the rate for a
month with no change, so there is no gap. Raises `ValueError` if no change is in force for a month.

### `fetch_uk_bank_rate()`

One GET (`http_get()`) of `UK_BANK_RATE_URL` with `UK_BANK_RATE_HEADERS` (the browser `User-Agent`), parsed by
`parse_boe_bank_rate()`. Errors propagate so `fetch_with_retries()` can retry them.

### `read_uk_bank_rate(data_dir)` and `write_uk_bank_rate(rows, data_dir)`

Read `uk_bank_rate.csv` keyed on `Month` (a missing file is `{}`); write it sorted by month with LF
endings. Rows are `[Month, Rate, Series, AsOf]`. `read_keyed_csv()` and `write_sorted_csv()`
wrappers.

### `update_uk_bank_rate(data_dir=None, today=None)`

Fetch and derive with retries; every derived month replaces the stored row. A new or changed month
takes the run date as `AsOf`, an unchanged one keeps its `AsOf`, so a run that reads the same page
leaves the file byte-identical; stored months the derivation lacks are kept. On a failed or refused
page the file is not touched and the result's `failures` holds `"uk_bank_rate: <error>"`.

**Returns**: `UkBankRateResults` (`failures`). `main()` calls it after the UK CPI, in the normal
mode only, and adds its failures to the run's.

## Entry Point

### `main(argv=None)`

Dispatches on the parsed arguments (`argv`, or `sys.argv` when `None`), in this order:
`--backfill`, `--import-closed`, `--backfill-dividends`, `--history`, otherwise the daily
run. The daily run validates `distributions.txt` and `dividend_sources.txt` with
`funds.txt` before any network call, then writes prices, then FX, then the dividend files,
then `uk_cpi.csv`, then `uk_bank_rate.csv`, then the summary. Each step is isolated: an
exception in one is recorded on the failure list under its name (`prices: <error>`,
`fx: <error>`, `dividends: <error>`, `uk_cpi: <error>` or `uk_bank_rate: <error>`) and
costs the later files and the summary nothing, so the run exits non-zero only after
everything obtainable has been written. The rebuilds, the import and the `--history` export
publish their report through `publish_report()`; a bad invocation exits 2 before any
network call.

### `publish_report(report, heading)`

Prints `report.to_markdown()`, appends it under `## <heading>` to the file
`GITHUB_STEP_SUMMARY` names when that variable is set (the Actions run page), and raises
`SystemExit(1)` when `report.failures` is non-empty, in that order, so a failed rebuild still
shows what it wrote. `report` is a `BackfillReport` (the rebuilds and the import) or a
`HistoryReport`: anything with `to_markdown()` and `failures`. The daily summary's own
append to the run page is `write_summary()`'s.

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
the dividends. Each `SummaryRow` is written as the tuple it is, so `SUMMARY_HEADER` is
the NamedTuple's field order (a test asserts it); only the aliases are rendered, joined
by `;`.

**Arithmetic note**: deltas use `decimal.Decimal`, so `7.15 - 7.09` is `0.06` rather
than the binary float `0.0600000000000005`. A previous price of zero yields an empty
percentage instead of a division error.

## FX Rates

### `read_fx_pairs(filename=None)`

Reads currency pairs to snap, from `FX_PAIRS_FILE` when `filename` is `None`. One
six-letter pair per line; blank lines and `#` comments ignored. A missing file returns
`[]`, so FX is optional.

**Raises:** `ValueError` naming the line, for a malformed or repeated pair. The slash
spelling (`GBP/NZD`) is rejected deliberately: by market convention it means the inverse
of the stored direction, so accepting it would store plausible but wrong values.

### `fetch_fx_quotes(pair, start, end=None, today=None, now=None)`

Fetches dated rates as **GBP per 1 unit of the base currency**, via Yahoo's direct
`<PAIR>=X` ticker. A day's rate is its 17:00 New York close, picked from hourly bars
by `new_york_fx_closes()` (#80). Days older than Yahoo's hourly history, which is
requested back `FX_HOURLY_HISTORY_DAYS` (729) days from `today`, come from the daily
bars, weekends dropped; that daily Close is the day's opening rate.
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

`read_fx_rows()` returns stored rates keyed on `(Pair, Date)`, skipping a row without a
rate (a `read_keyed_csv()` wrapper). `write_fx_files()` writes `fx_history.csv` and
`latest_fx.csv` through `write_sorted_csv()` from an authoritative row set **without
merging**, so a rebuild that removed rows really removes them; `write_fx_results()`
does the merging for the daily run before calling it. `format_fx_rate()` renders a
rate at a fixed `FX_RATE_DECIMALS` places, unlike prices, which keep the source's own
precision.

### `backfill_fx(pairs, start, data_dir=None, report=None)`

Rebuilds stored rates from the start date using the same rule as the price rebuild.
Called automatically by `--backfill` when `fx_pairs.txt` exists.

## Configuration Constants

### Data Directory Settings
- `DATA_DIR`: Default data directory ("data")
- `FUNDS_FILE`: Default funds configuration file ("funds.txt")

- `CLOSED_HOLDINGS_FILE`: One-off import configuration ("closed_holdings.txt")
- `FX_PAIRS_FILE`: FX pair configuration ("fx_pairs.txt")
- `DISTRIBUTIONS_FILE`: Distribution schedules for instruments no source covers ("distributions.txt")
- `DIVIDEND_SOURCES_FILE`: Issuer sources of dividend dates ("dividend_sources.txt")
- `ISSUER_PAUSE_SECONDS`: Pause between two issuer pages (1)
- `ISSUER_TWIN_DAYS`: Days within which a Yahoo row with the same amount is the issuer's dividend (3)

### Behaviour Settings
- `MAX_PRICE_ATTEMPTS`: Fetch attempts before falling back to the last known price (3)
- `ROLLING_HISTORY_DAYS`: Inclusive window for `prices_history_90_days.csv` (90)
- `SNAP_WINDOW_DAYS`: Days of dated quotes each daily run requests (10), so a late or
  corrected price is picked up by the upsert
- `STALE_AFTER_DAYS`: Age beyond which the summary marks an instrument `~` (4)
- `QUOTING_UNIT_FACTOR`: Price ratio that triggers a quoting-unit warning (50)
- `FT_BACKFILL_PAUSE_SECONDS`: Pause between FT requests during a rebuild (1)
- `FX_RATE_DECIMALS`: Decimal places stored for FX rates (6)
- `FX_CLOSE_ZONE`, `FX_CLOSE_HOUR`: The clock a day's FX rate is read at, 17:00 in
  `America/New_York` (17), #80
- `FX_HOURLY_HISTORY_DAYS`: How far back Yahoo's hourly bars are requested (729; Yahoo
  keeps 730 days, and one day's margin keeps a request in range)
- `UNTRADED_SPIKE_RATIO`: How far a zero-volume bar must sit from both neighbours to be
  dropped as untraded (1.2), #83
- `FT_SETTLED_ZONE`, `FT_SETTLED_HOUR`: The clock an FT row is held back until, 16:00 in
  `America/New_York` (16), #84
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
- `http_get(url, *, headers=None, timeout=HTTP_TIMEOUT)`: the one plain GET every HTTP
  fetcher makes, raising on an error status so `fetch_with_retries()` can retry it
- `HTTP_TIMEOUT` (30 s): the timeout of every plain HTTP fetch; `SSGA_REQUEST_TIMEOUT`
  (60 s) only for SSGA's workbook
- `BROWSER_USER_AGENT`: the realistic browser user agent that `INVESTING_HEADERS`,
  `UK_CPI_HEADERS` and `UK_BANK_RATE_HEADERS` carry; a bare `Mozilla/5.0` gets a 403
  from investing.com
- `FT_HISTORICAL_PAGE`, `FT_HISTORICAL_AJAX`
- `INVESTING_HISTORICAL_URL`, `INVESTING_HEADERS`

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
from scrape_fund_price import scrape_funds, read_fund_specs, write_results

# Read fund configuration
funds = read_fund_specs("funds.txt")

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
