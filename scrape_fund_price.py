from playwright.sync_api import sync_playwright
import datetime
import csv
import math
import os
import numpy as np
import requests
import yfinance as yf
import argparse
import re
from contextlib import nullcontext
from typing import NamedTuple

# Default configuration - can be overridden for testing
DATA_DIR = "data"
LATEST_CSV = os.path.join(DATA_DIR, "latest_prices.csv")
HISTORY_CSV = os.path.join(DATA_DIR, "prices_history.csv")
FUNDS_FILE = "funds.txt"
MAX_PRICE_ATTEMPTS = 3
ROLLING_HISTORY_DAYS = 90
SNAP_WINDOW_DAYS = 10


class Quote(NamedTuple):
    """A single dated price as reported by a source."""

    date: str  # ISO YYYY-MM-DD, the price date reported by the source
    price: str  # as quoted, thousands separators removed, no float noise
    currency: str  # "GBP", "GBp", "USD", "HKD"; "" when the source gives none


def format_yahoo_price(value):
    """Format a Yahoo bar value without losing or inventing precision.

    Yahoo daily bars are float32. Widening them to Python floats introduces
    artefacts (124.87 arrives as 124.87000274658203), so rounding to a fixed
    number of decimals would store that noise, while a significant-digit
    format would discard real precision (126530.25 -> 126530.2).

    The shortest string that round-trips as float32 recovers exactly what the
    source published.
    """
    text = str(np.float32(value))
    return text[:-2] if text.endswith(".0") else text


class ScrapeResults(list):
    """Scrape results with non-price failure metadata.

    `carried` holds rows for funds that could not be fetched at all. They are
    reported as the latest known price but are deliberately kept out of
    history: writing them there would invent a price for a date the source
    never published.
    """

    def __init__(self, rows=None, failures=None, carried=None):
        super().__init__(rows or [])
        self.failures = failures or []
        self.carried = carried or []


class FundSpec(NamedTuple):
    """One configured instrument.

    A fund is fetched using `lookup_id` but published under every identifier
    in `publish_ids`, so a fund can move to a better source without stranding
    the history recorded under its previous identifier.
    """

    source: str
    lookup_id: str
    aliases: tuple = ()

    @property
    def publish_ids(self):
        """Identifiers this fund is written out under, lookup id first."""
        return (self.lookup_id,) + tuple(self.aliases)


def read_fund_specs(filename):
    """Read instrument configuration from a funds file.

    Each line is `<source>,<lookup_id>[,<alias>[;<alias>...]]`. Blank lines and
    `#` comments are ignored, including trailing comments, which the docs have
    always shown but the parser previously folded into the identifier.

    Raises:
        ValueError: naming the offending line, for malformed lines, empty or
            self-referencing aliases, and identifiers repeated anywhere in the
            file. Validating up front means a bad config fails before any
            network call rather than half way through a run.
    """
    specs = []
    seen = {}

    with open(filename, "r") as f:
        for number, raw_line in enumerate(f, start=1):
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue

            fields = [field.strip() for field in line.split(",")]
            if len(fields) < 2 or not fields[0] or not fields[1]:
                raise ValueError(
                    f"funds file line {number}: expected "
                    f"'<source>,<identifier>[,<alias>]', got {line!r}"
                )

            source, lookup_id = fields[0], fields[1]
            aliases = []
            if len(fields) > 2 and fields[2]:
                aliases = [alias.strip() for alias in fields[2].split(";")]
            elif len(fields) > 2:
                raise ValueError(
                    f"funds file line {number}: alias field is empty; "
                    f"remove the trailing comma if the fund has no alias"
                )

            for alias in aliases:
                if not alias:
                    raise ValueError(
                        f"funds file line {number}: empty alias in {fields[2]!r}"
                    )
                if alias == lookup_id:
                    raise ValueError(
                        f"funds file line {number}: alias {alias!r} repeats its "
                        f"own identifier"
                    )

            spec = FundSpec(source, lookup_id, tuple(aliases))
            for identifier in spec.publish_ids:
                if identifier in seen:
                    raise ValueError(
                        f"funds file line {number}: identifier {identifier!r} "
                        f"already used on line {seen[identifier]}"
                    )
                seen[identifier] = number

            specs.append(spec)

    return specs


def read_fund_ids(filename):
    """Read (source, identifier) pairs from a funds file.

    Compatibility wrapper over read_fund_specs() for callers that only need
    the identifier a fund is looked up by.
    """
    return [(spec.source, spec.lookup_id) for spec in read_fund_specs(filename)]


def as_fund_spec(entry):
    """Accept a FundSpec or a plain (source, identifier) pair."""
    if isinstance(entry, FundSpec):
        return entry
    source, lookup_id = entry
    return FundSpec(source, lookup_id, ())


def get_source_config(source, fund_id):
    """Get URL and CSS selector configuration for web scraping sources.

    Note: GF (Google Finance) source uses API instead of scraping,
    so it's not included in this configuration.

    Args:
        source: Two-character source code (FT, YH, MS)
        fund_id: Fund identifier specific to the source

    Returns:
        Tuple of (url, selector) or (None, None) if source is invalid or uses API
    """
    source_configs = {
        "FT": {
            "url": f"https://markets.ft.com/data/funds/tearsheet/summary?s={fund_id}",
            "selector": ".mod-ui-data-list__value",
        },
        "YH": {
            "url": f"https://sg.finance.yahoo.com/quote/{fund_id}/",
            "selector": 'span[data-testid="qsp-price"]',
        },
        "MS": {
            "url": f"https://asialt.morningstar.com/DSB/QuickTake/overview.aspx?code={fund_id}",
            "selector": "#mainContent_quicktakeContent_fvOverview_lblNAV",
        },
    }

    config = source_configs.get(source.upper())
    if config:
        return config["url"], config["selector"]
    return None, None


def fetch_yahoo_quotes(symbol, start, end=None):
    """Fetch dated daily quotes for a symbol from Yahoo Finance.

    Uses daily bars rather than the summary endpoint: the summary carries no
    price date and is stale for mutual funds (0P00000YAN reported 192.23 while
    the latest bar was 192.43).

    Args:
        symbol: Yahoo ticker (e.g. "IDTG.L", "0P00000YAN")
        start: Inclusive ISO start date
        end: Exclusive ISO end date, or None for up to the latest bar

    Returns:
        list[Quote], oldest first

    Raises:
        Exception: transport and API errors propagate so fetch_with_retries
            can retry them
    """
    ticker = yf.Ticker(symbol)
    # auto_adjust=False keeps Close as the price actually quoted that day;
    # adjusted values would not match prices snapped at the time.
    history = ticker.history(start=start, end=end, auto_adjust=False)

    currency = ""
    try:
        currency = ticker.fast_info["currency"] or ""
    except Exception:
        currency = ""

    quotes = []
    for timestamp, close in history["Close"].items() if len(history) else []:
        if close is None or (isinstance(close, float) and math.isnan(close)):
            continue
        quotes.append(
            Quote(timestamp.date().isoformat(), format_yahoo_price(close), currency)
        )
    return quotes


FT_HISTORICAL_PAGE = "https://markets.ft.com/data/funds/tearsheet/historical?s={isin}"
FT_HISTORICAL_AJAX = (
    "https://markets.ft.com/data/equities/ajax/get-historical-prices"
    "?startDate={start}&endDate={end}&symbol={xid}"
)
FT_REQUEST_TIMEOUT = 30


def fetch_ft_quotes(isin, start, end=None):
    """Fetch dated daily quotes for a fund from Financial Times.

    Uses the historical-prices endpoint rather than scraping the summary
    page, so quotes carry the price date FT reports. Two plain HTTP requests,
    no browser: the first resolves FT's internal numeric id for the fund, the
    second returns the rows.

    Args:
        isin: Fund ISIN as used in funds.txt
        start: Inclusive ISO start date
        end: Inclusive ISO end date, or None for today

    Returns:
        list[Quote], oldest first

    Raises:
        ValueError: the internal id could not be found, or no rows were
            returned. Callers fall back to scraping the summary page.
    """
    end = end or datetime.date.today().isoformat()

    page = requests.get(
        FT_HISTORICAL_PAGE.format(isin=isin), timeout=FT_REQUEST_TIMEOUT
    )
    page.raise_for_status()

    ids = re.findall(r"&quot;symbol&quot;:&quot;(\d+)&quot;", page.text)
    if not ids:
        raise ValueError(f"FT internal id not found for {isin}")

    currency_match = re.search(r"Price \(([A-Za-z]{3})\)", page.text)
    currency = currency_match.group(1) if currency_match else ""

    response = requests.get(
        FT_HISTORICAL_AJAX.format(
            start=start.replace("-", "/"), end=end.replace("-", "/"), xid=ids[0]
        ),
        timeout=FT_REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    quotes = []
    for row in re.findall(r"<tr>(.*?)</tr>", response.json().get("html", ""), re.S):
        date_match = re.search(
            r"<span[^>]*>([A-Za-z]+, [A-Za-z]+ \d{1,2}, \d{4})</span>", row
        )
        # Only Open/High/Low/Close are plain cells; the date and volume cells
        # wrap their contents in spans.
        cells = re.findall(r"<td[^>]*>([^<]*)</td>", row)
        if not date_match or len(cells) < 4:
            continue
        price_date = datetime.datetime.strptime(
            date_match.group(1), "%A, %B %d, %Y"
        ).date()
        # FT prices are text; keep the digits exactly as published.
        quotes.append(
            Quote(price_date.isoformat(), normalize_price(cells[3].strip()), currency)
        )

    if not quotes:
        raise ValueError(f"FT returned no historical rows for {isin}")

    quotes.sort(key=lambda quote: quote.date)
    return quotes


def fetch_price_api(symbol):
    """Fetch the latest price for a symbol using Yahoo Finance.

    Args:
        symbol: Stock/fund ticker symbol (e.g., AAPL, MSFT)

    Returns:
        Price as string or error message
    """
    try:
        start = (
            datetime.date.today() - datetime.timedelta(days=SNAP_WINDOW_DAYS)
        ).isoformat()
        quotes = fetch_yahoo_quotes(symbol, start)
        if not quotes:
            return "Error: Price not available"
        return quotes[-1].price
    except Exception as e:
        return f"Error: {str(e)}"


def scrape_price_with_common_settings(page, url, selector):
    """Scrape price using common settings for all sources."""
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    )
    page.context.set_extra_http_headers({"User-Agent": user_agent})
    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_selector(selector, timeout=60000)
    return page.locator(selector).first.text_content().strip()


def is_error_price(price):
    """Return True when a value is an error marker, not a price."""
    return isinstance(price, str) and price.startswith("Error:")


def normalize_price(price):
    """Remove thousands separators from a price before storing it."""
    return price.replace(",", "")


def is_usable_price(price):
    """Return True when a stored value can be reused as a prior price."""
    return bool(price) and price != "N/A" and not is_error_price(price)


def read_latest_price_file(fund_id, data_dir):
    """Read the per-fund latest price file if it contains a usable value."""
    latest_price_file = os.path.join(data_dir, f"latest_{fund_id}.price")
    if not os.path.isfile(latest_price_file):
        return None

    with open(latest_price_file, "r") as f:
        price = f.read().strip()

    return price if is_usable_price(price) else None


def read_latest_csv_price(fund_id, data_dir):
    """Read the latest CSV price for a fund if it contains a usable value."""
    latest_csv = os.path.join(data_dir, "latest_prices.csv")
    if not os.path.isfile(latest_csv):
        return None

    with open(latest_csv, mode="r", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row.get("Fund") == fund_id and is_usable_price(row.get("Price")):
                return row["Price"]

    return None


def read_history_price(fund_id, data_dir):
    """Read the most recent usable historical price for a fund."""
    history_csv = os.path.join(data_dir, "prices_history.csv")
    if not os.path.isfile(history_csv):
        return None

    with open(history_csv, mode="r", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    for row in reversed(rows):
        if row.get("Fund") == fund_id and is_usable_price(row.get("Price")):
            return row["Price"]

    return None


def read_last_known_row(fund_id, data_dir):
    """Return a fund's most recent stored [date, price, currency], or None.

    Used when every fetch attempt failed, so the fund keeps reporting its real
    last price against the date that price actually belongs to.
    """
    candidates = []
    for name in ("latest_prices.csv", "prices_history.csv"):
        path = os.path.join(data_dir, name)
        if not os.path.isfile(path):
            continue
        with open(path, mode="r", newline="") as file:
            for row in csv.DictReader(file):
                if row.get("Fund") == fund_id and is_usable_price(row.get("Price")):
                    candidates.append(
                        [row.get("Date", ""), row["Price"], row.get("Currency") or ""]
                    )

    if not candidates:
        price = read_latest_price_file(fund_id, data_dir)
        return [datetime.date.today().isoformat(), price, ""] if price else None

    return max(candidates, key=lambda row: row[0])


def get_last_known_price(fund_id, data_dir):
    """Return the last non-error price available for a fund."""
    return (
        read_latest_price_file(fund_id, data_dir)
        or read_latest_csv_price(fund_id, data_dir)
        or read_history_price(fund_id, data_dir)
    )


def fetch_with_retries(fetch_price, attempts=MAX_PRICE_ATTEMPTS):
    """Fetch a price, retrying exceptions and returned Error values."""
    last_error = None

    for _ in range(attempts):
        try:
            price = fetch_price()
        except Exception as e:
            last_error = str(e)
            continue

        if not is_error_price(price):
            return price, None

        last_error = price

    return None, last_error


def source_requires_browser(source, fund_id):
    """Return True when a fund source needs Playwright scraping.

    GF uses the Yahoo API and FT uses a plain HTTP endpoint, so neither needs
    a browser on its normal path. FT can still fall back to scraping, which
    starts the browser lazily at that point.
    """
    if source.upper() in ("GF", "FT"):
        return False

    url, selector = get_source_config(source, fund_id)
    return bool(url and selector)


class LazyBrowser:
    """Start Playwright only if a fund actually needs scraping.

    Most sources are now plain HTTP, so launching Chromium up front wastes
    seconds on every run. The browser starts on first use and is reused.
    """

    def __init__(self):
        self._context_manager = None
        self._browser = None
        self._page = None

    def page(self):
        if self._page is None:
            self._context_manager = sync_playwright()
            playwright = self._context_manager.__enter__()
            self._browser = playwright.chromium.launch(headless=True)
            self._page = self._browser.new_context().new_page()
        return self._page

    def close(self):
        if self._browser is not None:
            self._browser.close()
        if self._context_manager is not None:
            self._context_manager.__exit__(None, None, None)


def scrape_fund_quotes(source, fund_id, start, end=None, browser=None):
    """Return dated quotes for one fund from its configured source.

    FT and GF use dated HTTP routes. YH and MS scrape a page that shows only
    the current price, so their quotes carry the run date and no currency.
    An FT failure falls back to scraping rather than losing the fund.
    """
    code = source.upper()

    if code == "GF":
        return fetch_yahoo_quotes(fund_id, start, end)

    if code == "FT":
        try:
            return fetch_ft_quotes(fund_id, start, end)
        except Exception as error:
            print(f"Warning: FT historical lookup failed for {fund_id}: {error}")

    url, selector = get_source_config(source, fund_id)
    if not (url and selector):
        raise ValueError(f"Unsupported source {source} for {fund_id}")

    price = scrape_price_with_common_settings(browser.page(), url, selector)
    return [Quote(datetime.date.today().isoformat(), normalize_price(price), "")]


def write_latest_price_file(fund_id, price, data_dir):
    """Write a fund's single-value price file."""
    with open(os.path.join(data_dir, f"latest_{fund_id}.price"), "w") as f:
        f.write(price + "\n")


def scrape_funds(funds, data_dir=None):
    """Scrape a window of dated prices for each fund and return results.

    Args:
        funds: FundSpec instances, or plain (source, identifier) pairs
        data_dir: Directory for per-fund price files (default: DATA_DIR)
    """
    if data_dir is None:
        data_dir = DATA_DIR

    os.makedirs(data_dir, exist_ok=True)
    results = ScrapeResults()
    start = (
        datetime.date.today() - datetime.timedelta(days=SNAP_WINDOW_DAYS)
    ).isoformat()
    browser = LazyBrowser()

    try:
        for entry in funds:
            spec = as_fund_spec(entry)
            # Fetched once on the lookup identifier, then published under every
            # identifier, so aliases cost no extra network calls.
            quotes, error = fetch_with_retries(
                lambda: scrape_fund_quotes(
                    spec.source, spec.lookup_id, start, browser=browser
                )
            )

            if error:
                # Keep reporting the fund's last known price, dated as the
                # source originally published it, rather than inventing a row
                # for today. Record the failure once for the fund, not once
                # per identifier.
                results.failures.append(f"{spec.lookup_id}: {error}")
                last_known = None
                for identifier in spec.publish_ids:
                    # A newly introduced lookup id has nothing stored yet,
                    # while an alias may carry the fund's whole history.
                    last_known = read_last_known_row(identifier, data_dir)
                    if last_known is not None:
                        break

                if last_known is not None:
                    for identifier in spec.publish_ids:
                        results.carried.append([identifier] + last_known)
                        # Heal the published price file: it may still hold an
                        # error string written before this behaviour existed.
                        write_latest_price_file(identifier, last_known[1], data_dir)
                continue

            for quote in quotes:
                for identifier in spec.publish_ids:
                    results.append(
                        [identifier, quote.date, quote.price, quote.currency]
                    )

            latest = max(quotes, key=lambda quote: quote.date, default=None)
            if latest is not None:
                for identifier in spec.publish_ids:
                    write_latest_price_file(identifier, latest.price, data_dir)
    finally:
        browser.close()

    return results


def read_history_rows(history_csv):
    """Read stored history, tolerating legacy rows that carry no currency."""
    if not os.path.isfile(history_csv):
        return {}

    rows = {}
    with open(history_csv, mode="r", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)  # Skip header
        for row in reader:
            if len(row) < 3:
                continue
            fund, date_text, price = row[0], row[1], row[2]
            currency = row[3] if len(row) > 3 else ""
            rows[(fund, date_text)] = [fund, date_text, price, currency]
    return rows


def write_results(results, data_dir=None):
    """Write dated results to CSV files.

    History is keyed on (Fund, Date): an incoming row replaces an existing row
    with the same key, so corrections apply and re-runs cannot duplicate. Rows
    are sorted by date then fund, which keeps daily diffs readable and makes
    repeated runs byte-identical.

    Args:
        results: List of [fund_id, date, price, currency] rows
        data_dir: Directory for output files (default: DATA_DIR)
    """
    if data_dir is None:
        data_dir = DATA_DIR

    os.makedirs(data_dir, exist_ok=True)
    latest_csv = os.path.join(data_dir, "latest_prices.csv")
    history_csv = os.path.join(data_dir, "prices_history.csv")
    rolling_history_csv = os.path.join(data_dir, "prices_history_90_days.csv")
    header = ["Fund", "Date", "Price", "Currency"]

    incoming = []
    for row in results:
        fund, date_text, price = row[0], row[1], row[2]
        currency = row[3] if len(row) > 3 else ""
        if is_usable_price(price):
            incoming.append([fund, date_text, price, currency])

    history_rows = read_history_rows(history_csv)
    for row in incoming:
        history_rows[(row[0], row[1])] = row

    ordered = sorted(history_rows.values(), key=lambda row: (row[1], row[0]))

    with open(history_csv, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(ordered)

    latest_by_fund = {}
    for row in incoming:
        current = latest_by_fund.get(row[0])
        if current is None or row[1] > current[1]:
            latest_by_fund[row[0]] = row

    for row in getattr(results, "carried", []):
        latest_by_fund.setdefault(row[0], list(row))

    with open(latest_csv, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(latest_by_fund[fund] for fund in sorted(latest_by_fund))

    reference_date = (
        max(row[1] for row in incoming)
        if incoming
        else datetime.date.today().isoformat()
    )
    reference = datetime.date.fromisoformat(reference_date)
    cutoff = reference - datetime.timedelta(days=ROLLING_HISTORY_DAYS - 1)

    rolling_rows = []
    for row in ordered:
        try:
            row_date = datetime.date.fromisoformat(row[1])
        except ValueError:
            continue
        if cutoff <= row_date <= reference:
            rolling_rows.append(row)

    with open(rolling_history_csv, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rolling_rows)


def parse_arguments(args=None):
    """Parse command-line arguments.

    Args:
        args: List of arguments to parse (for testing). If None, uses sys.argv.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Fund Price Scraper with Historical Data Support",
        epilog="Examples:\n"
        "  Normal mode: python scrape_fund_price.py\n"
        "  Historical: python scrape_fund_price.py --history AAPL --start 2024-01-01 --end 2024-12-31",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--history",
        type=str,
        metavar="SYMBOL",
        help="Symbol to fetch historical data for (e.g., AAPL, MSFT)",
    )
    parser.add_argument(
        "--start",
        type=str,
        metavar="YYYY-MM-DD",
        help="Start date in YYYY-MM-DD format (required with --history)",
    )
    parser.add_argument(
        "--end",
        type=str,
        metavar="YYYY-MM-DD",
        help="End date in YYYY-MM-DD format (optional, defaults to today)",
    )

    return parser.parse_args(args)


def fetch_historical_data(symbol, start_date, end_date, data_dir=DATA_DIR):
    """Fetch historical price data for a symbol.

    Args:
        symbol: Stock/fund symbol
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format (can be None)
        data_dir: Directory to save the CSV file

    Returns:
        Filename of saved CSV or error message starting with "Error:"
    """
    # Validate date format
    date_pattern = r"^\d{4}-\d{2}-\d{2}$"
    if not re.match(date_pattern, start_date):
        return "Error: Invalid start date format. Use YYYY-MM-DD"

    if end_date and not re.match(date_pattern, end_date):
        return "Error: Invalid end date format. Use YYYY-MM-DD"

    # Validate start date is before end date
    if end_date and start_date > end_date:
        return "Error: Start date must be before end date"

    try:
        # Fetch historical data using yfinance
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start_date, end=end_date)

        # Check if data was returned
        if hist.empty:
            return f"Error: No data found for symbol {symbol}"

        # Create filename
        end_str = end_date if end_date else datetime.date.today().isoformat()
        filename = f"history_{symbol}_{start_date}_{end_str}.csv"
        filepath = os.path.join(data_dir, filename)

        # Ensure data directory exists
        os.makedirs(data_dir, exist_ok=True)

        # Save to CSV
        hist.to_csv(filepath)

        return filepath

    except Exception as e:
        return f"Error: {str(e)}"


def main():
    """Main function to run the fund price scraper."""
    args = parse_arguments()

    # Check if historical data mode
    if args.history:
        if not args.start:
            print("Error: --start date is required when using --history")
            return

        result = fetch_historical_data(args.history, args.start, args.end)

        if result.startswith("Error:"):
            print(result)
        else:
            print(f"Historical data saved to: {result}")
    else:
        # Normal scraping mode
        funds = read_fund_specs(FUNDS_FILE)
        results = scrape_funds(funds)
        write_results(results)
        if getattr(results, "failures", []):
            for failure in results.failures:
                print(f"Error: {failure}")
            raise SystemExit(1)


if __name__ == "__main__":
    main()
