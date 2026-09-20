# API Reference

This document provides detailed API documentation for the Fund Price Scraping project.

## Core Functions

### `FundSpec(source, lookup_id, aliases=())`

One configured instrument.

- `source` (str): source code (`FT`, `GF`, `YH`, `MS`)
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
# [FundSpec(source="GF", lookup_id="0P00000YAN", aliases=("JFM0003373",)), ...]
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
- `source`: Data source identifier (FT, YH, MS, GF)
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
- **GF**: Yahoo Finance API via `fetch_price_api()` - no scraping, returns `(None, None)` here
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

Returns dated quotes for one fund from its configured source, falling back from FT's
endpoint to scraping when needed. `YH` and `MS` scrape a page showing only the current
price, so their quotes carry the run date and an empty currency.

### `LazyBrowser`

Starts Playwright on first use, so a configuration that needs no scraping never
launches Chromium. `page()` returns a live page; `close()` is safe if unused.

### `read_last_known_row(fund_id, data_dir)`

Returns a fund's most recent stored `[date, price, currency]`, or `None`.

Used when every fetch attempt failed: the fund keeps reporting its real last price
against the date that price belongs to, instead of a row invented for today.

### `fetch_price_api(symbol)`

Fetches a price via the Yahoo Finance API instead of scraping. Used for the `GF` source.

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
- `ScrapeResults`: a `list` subclass of `[fund_id, date, price]` rows, carrying an
  additional `.failures` attribute listing `"<fund_id>: <error>"` strings for funds
  that fell back to a last known price

**Result Format:**
```python
results = scrape_funds([("GF", "AAPL"), ("FT", "GB00B1FXTF86")])
# [["AAPL", "2026-09-20", "150.25"], ["GB00B1FXTF86", "2026-09-20", "1.2345"]]
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
  date and the preceding 89 calendar days (90 inclusive, `ROLLING_HISTORY_DAYS`)

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

Parses the command line. Supports `--history SYMBOL`, `--start YYYY-MM-DD` and
`--end YYYY-MM-DD`. With no `--history`, the scraper runs in normal mode.

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
- `str` price, or `None` if no usable historical price exists (the fund is then recorded as `"N/A"`)

### Supporting helpers

- `is_error_price(price)` - True when a value is an `"Error: ..."` string
- `normalize_price(price)` - normalises a price value for storage
- `is_usable_price(price)` - True when a value is a real price rather than an error or placeholder
- `source_requires_browser(source, fund_id)` - False for `GF` (API) and unknown sources, so
  Playwright is only launched when genuinely needed

## Configuration Constants

### Data Directory Settings
- `DATA_DIR`: Default data directory ("data")
- `LATEST_CSV`: Latest prices file path
- `HISTORY_CSV`: Historical prices file path
- `FUNDS_FILE`: Default funds configuration file ("funds.txt")

### Behaviour Settings
- `MAX_PRICE_ATTEMPTS`: Fetch attempts before falling back to the last known price (3)
- `ROLLING_HISTORY_DAYS`: Inclusive window for `prices_history_90_days.csv` (90)

## Error Handling

### Common Exceptions
- `FileNotFoundError`: When funds file doesn't exist
- `TimeoutError`: When page load or selector wait times out
- `ValueError`: When invalid source is provided

### Error Status Values
- `"success"`: Scraping completed successfully
- `"error"`: Scraping failed with an exception
- `"timeout"`: Request timed out
- `"not_found"`: Price element not found on page

## Usage Examples

### Basic Usage
```python
from scrape_fund_price import scrape_funds, read_fund_ids

# Read fund configuration
funds = read_fund_ids("funds.txt")

# Scrape prices
results = scrape_funds(funds)

# Results are automatically saved to CSV files
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

- `playwright`: Web scraping and browser automation
- `datetime`: Timestamp generation
- `csv`: CSV file operations
- `os`: File system operations
