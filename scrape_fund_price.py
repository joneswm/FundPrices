from playwright.sync_api import sync_playwright
import datetime
import csv
import decimal
import math
import os
import time
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


HISTORY_HEADER = ["Fund", "Date", "Price", "Currency"]


def latest_rows_by_fund(rows):
    """Return each fund's row with the newest price date."""
    latest = {}
    for row in rows:
        current = latest.get(row[0])
        if current is None or row[1] > current[1]:
            latest[row[0]] = list(row)
    return latest


def write_history_files(rows, data_dir, latest=None):
    """Write the history, latest-price and rolling-window CSVs.

    Shared by the daily run and the backfill so both produce byte-identical
    output for the same data.

    Args:
        rows: Every [fund_id, date, price, currency] row to store
        data_dir: Output directory
        latest: Optional fund -> row mapping for latest_prices.csv; computed
            from `rows` when omitted
    """
    ordered = sorted(rows, key=lambda row: (row[1], row[0]))

    with open(os.path.join(data_dir, "prices_history.csv"), "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(HISTORY_HEADER)
        writer.writerows(ordered)

    if latest is None:
        latest = latest_rows_by_fund(ordered)

    with open(os.path.join(data_dir, "latest_prices.csv"), "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(HISTORY_HEADER)
        writer.writerows(latest[fund] for fund in sorted(latest))

    reference_date = (
        max((row[1] for row in latest.values()), default=None)
        or datetime.date.today().isoformat()
    )
    try:
        reference = datetime.date.fromisoformat(reference_date)
    except ValueError:
        reference = datetime.date.today()
    cutoff = reference - datetime.timedelta(days=ROLLING_HISTORY_DAYS - 1)

    rolling_rows = []
    for row in ordered:
        try:
            row_date = datetime.date.fromisoformat(row[1])
        except ValueError:
            continue
        if cutoff <= row_date <= reference:
            rolling_rows.append(row)

    with open(
        os.path.join(data_dir, "prices_history_90_days.csv"), "w", newline=""
    ) as file:
        writer = csv.writer(file)
        writer.writerow(HISTORY_HEADER)
        writer.writerows(rolling_rows)


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

    incoming = []
    for row in results:
        fund, date_text, price = row[0], row[1], row[2]
        currency = row[3] if len(row) > 3 else ""
        if is_usable_price(price):
            incoming.append([fund, date_text, price, currency])

    history_rows = read_history_rows(os.path.join(data_dir, "prices_history.csv"))
    for row in incoming:
        history_rows[(row[0], row[1])] = row

    latest = latest_rows_by_fund(incoming)
    # A fund that could not be fetched still reports its last real price.
    for row in getattr(results, "carried", []):
        latest.setdefault(row[0], list(row))

    write_history_files(list(history_rows.values()), data_dir, latest=latest)


QUOTING_UNIT_FACTOR = 50
FT_BACKFILL_PAUSE_SECONDS = 1


class BackfillReport:
    """Reconciliation of what a rebuild changed, per identifier."""

    def __init__(self):
        self.entries = []
        self.failures = []
        self.warnings = []

    def to_markdown(self):
        """Render the report for stdout and the Actions job summary."""
        lines = [
            "| Identifier | Before | Deleted | Kept | Inserted | First | Last "
            "| Ccy | Status |",
            "|---|---:|---:|---:|---:|---|---|---|---|",
        ]
        for entry in self.entries:
            lines.append(
                "| {identifier} | {before} | {deleted} | {retained} | {inserted} "
                "| {first} | {last} | {currency} | {status} |".format(**entry)
            )

        if self.warnings:
            lines += ["", "**Warnings**", ""]
            lines += [f"- {warning}" for warning in self.warnings]

        if self.failures:
            lines += ["", "**Failures**", ""]
            lines += [f"- {failure}" for failure in self.failures]

        return "\n".join(lines)


STALE_AFTER_DAYS = 4
SUMMARY_HEADER = [
    "Name",
    "Aliases",
    "Currency",
    "NewDate",
    "New",
    "OldDate",
    "Old",
    "Delta",
    "PctDelta",
    "AgeDays",
    "Stale",
    "Failed",
]


class SummaryRow(NamedTuple):
    """One instrument's or pair's movement for the day."""

    name: str
    aliases: tuple
    currency: str
    new_date: str
    new: str
    old_date: str
    old: str
    delta: str
    pct_delta: str
    age_days: int
    stale: bool
    failed: bool


def format_decimal(value, places=None):
    """Render a Decimal without exponent notation or trailing noise."""
    if places is not None:
        text = f"{value:.{places}f}"
    else:
        text = format(value.normalize(), "f")
    return text


def compare_values(new_text, old_text, places=None):
    """Return (delta, percent delta) as strings for two stored values.

    Uses Decimal so that 7.15 - 7.09 is exactly 0.06 rather than the binary
    float 0.0600000000000005. An old value of zero yields no percentage
    instead of a division error.
    """
    try:
        new_value = decimal.Decimal(new_text)
        old_value = decimal.Decimal(old_text)
    except (decimal.InvalidOperation, TypeError):
        return "", ""

    delta = new_value - old_value
    delta_text = format_decimal(delta, places)

    if old_value == 0:
        return delta_text, ""

    percent = (delta / old_value) * 100
    return delta_text, f"{percent:+.2f}"


def summarise_series(name, aliases, rows, failures, run_date, places=None):
    """Build one SummaryRow from an instrument's dated rows.

    `old` is the price on the previous **distinct** price date, never the
    calendar day before: funds, LSE, US and HK instruments keep different
    calendars, and fund NAVs arrive a day later than exchange prices.
    """
    failed = any(name in failure for failure in failures)
    ordered = sorted(rows, key=lambda row: row[1])

    if not ordered:
        return SummaryRow(name, aliases, "", "", "", "", "", "", "", 0, False, True)

    newest = ordered[-1]
    previous = ordered[-2] if len(ordered) > 1 else None
    currency = newest[3] if len(newest) > 3 else ""

    delta, pct_delta = ("", "")
    if previous is not None:
        delta, pct_delta = compare_values(newest[2], previous[2], places)

    age_days = (
        datetime.date.fromisoformat(run_date) - datetime.date.fromisoformat(newest[1])
    ).days

    return SummaryRow(
        name=name,
        aliases=aliases,
        currency=currency,
        new_date=newest[1],
        new=newest[2],
        old_date=previous[1] if previous is not None else "",
        old=previous[2] if previous is not None else "",
        delta=delta,
        pct_delta=pct_delta,
        age_days=age_days,
        stale=age_days > STALE_AFTER_DAYS,
        failed=failed,
    )


def build_price_summary(history_rows, specs, failures, run_date):
    """Summarise each configured instrument's latest movement.

    An aliased instrument is reported once, under its lookup identifier, since
    its aliases carry an identical series by construction.
    """
    by_fund = {}
    for row in history_rows:
        by_fund.setdefault(row[0], []).append(row)

    rows = []
    for entry in specs:
        # Accept plain (source, identifier) pairs as scrape_funds() does.
        spec = as_fund_spec(entry)
        rows.append(
            summarise_series(
                spec.lookup_id,
                tuple(spec.aliases),
                by_fund.get(spec.lookup_id, []),
                failures,
                run_date,
            )
        )
    return rows


def build_fx_summary(fx_rows, pairs, failures, run_date):
    """Summarise each currency pair's latest movement."""
    by_pair = {}
    for row in fx_rows:
        by_pair.setdefault(row[0], []).append(row)

    return [
        summarise_series(
            pair,
            (),
            by_pair.get(pair, []),
            failures,
            run_date,
            places=FX_RATE_DECIMALS,
        )
        for pair in pairs
    ]


def _summary_table(rows, value_label, include_currency):
    """Render one Markdown table of summary rows."""
    columns = ["Name"]
    if include_currency:
        columns.append("Ccy")
    columns += [f"{value_label} date", "New", "Old", "Delta", "% Delta"]

    lines = [
        "| " + " | ".join(columns) + " |",
        "|" + "|".join(["---"] * len(columns)) + "|",
    ]

    for row in rows:
        name = row.name
        if row.aliases:
            name = f"{name} ({', '.join(row.aliases)})"
        if row.failed:
            name += " !"
        elif row.stale:
            name += " ~"

        cells = [name]
        if include_currency:
            cells.append(row.currency or "-")
        cells += [
            row.new_date or "-",
            row.new or "-",
            row.old or "-",
            row.delta or "-",
            row.pct_delta or "-",
        ]
        lines.append("| " + " | ".join(cells) + " |")

    return lines


def render_summary_markdown(price_rows, fx_rows, run_date):
    """Render the day's movements for reading directly on GitHub."""
    lines = [f"# Daily Price Summary - {run_date}", ""]

    lines += ["## Prices", ""]
    lines += _summary_table(price_rows, "Price", include_currency=True)

    if fx_rows:
        lines += [
            "",
            "## FX (GBP per 1 unit of foreign currency)",
            "",
        ]
        lines += _summary_table(fx_rows, "Rate", include_currency=False)

    attention = [row for row in price_rows + fx_rows if row.stale or row.failed]
    lines += ["", "## Attention", ""]
    if attention:
        for row in attention:
            reason = (
                "no price obtained this run"
                if row.failed
                else (f"stale: last price {row.age_days} days ago")
            )
            lines.append(f"- **{row.name}**: {reason}")
    else:
        lines.append("None")

    movers = [
        row
        for row in price_rows + fx_rows
        if row.pct_delta and not row.stale and not row.failed
    ]
    movers.sort(key=lambda row: abs(decimal.Decimal(row.pct_delta)), reverse=True)
    lines += ["", "## Biggest movers", ""]
    if movers:
        for row in movers[:5]:
            lines.append(f"- **{row.name}**: {row.pct_delta}%")
    else:
        lines.append("None")

    lines.append("")
    lines.append(
        "Legend: `!` no price this run, `~` stale. "
        "Percent changes are unit-independent; absolute deltas are in the "
        "instrument's own currency."
    )
    return "\n".join(lines) + "\n"


def write_summary(price_rows, fx_rows, run_date, data_dir=None):
    """Write the daily summary as CSV and Markdown.

    Past summaries stay recoverable from git history and can be recomputed
    from prices_history.csv, so no dated archive is kept.
    """
    if data_dir is None:
        data_dir = DATA_DIR

    os.makedirs(data_dir, exist_ok=True)

    with open(os.path.join(data_dir, "daily_summary.csv"), "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(SUMMARY_HEADER)
        for row in price_rows + fx_rows:
            writer.writerow(
                [
                    row.name,
                    ";".join(row.aliases),
                    row.currency,
                    row.new_date,
                    row.new,
                    row.old_date,
                    row.old,
                    row.delta,
                    row.pct_delta,
                    row.age_days,
                    row.stale,
                    row.failed,
                ]
            )

    markdown = render_summary_markdown(price_rows, fx_rows, run_date)
    with open(
        os.path.join(data_dir, "daily_summary.md"), "w", encoding="utf-8"
    ) as file:
        file.write(markdown)

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as file:
            file.write(markdown)


def validate_backfill_args(args):
    """Return an error message for an invalid backfill invocation, else None."""
    if not getattr(args, "backfill", False):
        return None

    if getattr(args, "history", None):
        return "--backfill cannot be combined with --history"

    if not args.start:
        return "--from is required when using --backfill"

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", args.start):
        return "Invalid --from date format. Use YYYY-MM-DD"

    try:
        start = datetime.date.fromisoformat(args.start)
    except ValueError:
        return "Invalid --from date format. Use YYYY-MM-DD"

    if start > datetime.date.today():
        return "--from date is in the future"

    return None


def check_quoting_unit(identifier, quotes):
    """Return a warning when a series looks like it changed quoting unit.

    A switch between pence and pounds is a factor of 100. Flagging anything
    above 50 catches it without firing on genuine daily moves, which do not
    come close.
    """
    previous = None
    for quote in quotes:
        try:
            value = float(quote.price)
        except ValueError:
            continue
        if (
            previous
            and value
            and max(previous, value) / min(previous, value) > (QUOTING_UNIT_FACTOR)
        ):
            return (
                f"{identifier}: price moved from {previous} to {value} on "
                f"{quote.date}; check for a quoting unit change"
            )
        previous = value or previous
    return None


FX_PAIRS_FILE = "fx_pairs.txt"
FX_RATE_DECIMALS = 6
FX_HEADER = ["Pair", "Date", "Rate"]


def read_fx_pairs(filename=None):
    """Read currency pairs to snap from a pairs file.

    One six-letter pair per line, e.g. `USDGBP`, meaning GBP per 1 USD. Blank
    lines and `#` comments are ignored. A missing file returns no pairs, so FX
    is optional rather than required.

    The slash spelling is deliberately rejected: by market convention
    `GBP/NZD` means NZD per GBP, the inverse of what these rates are for, and
    accepting it would store plausible but wrong values.

    Raises:
        ValueError: naming the line, for a malformed or repeated pair.
    """
    if filename is None:
        filename = FX_PAIRS_FILE

    if not os.path.isfile(filename):
        return []

    pairs = []
    seen = {}
    with open(filename, "r") as f:
        for number, raw_line in enumerate(f, start=1):
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue

            if not re.match(r"^[A-Z]{6}$", line):
                raise ValueError(
                    f"fx pairs file line {number}: expected six uppercase letters "
                    f"such as 'USDGBP' (GBP per 1 USD), got {line!r}"
                )

            if line in seen:
                raise ValueError(
                    f"fx pairs file line {number}: pair {line!r} already used on "
                    f"line {seen[line]}"
                )

            seen[line] = number
            pairs.append(line)

    return pairs


def format_fx_rate(value):
    """Format a rate at a fixed 6 decimal places.

    Unlike prices, which keep the source's own precision, rates use a fixed
    width: HKDGBP is about 0.0951, where 4dp would lose roughly 0.1%.
    """
    return f"{float(value):.{FX_RATE_DECIMALS}f}"


def fetch_fx_quotes(pair, start, end=None):
    """Fetch dated FX rates for a pair, as GBP per 1 unit of the base currency.

    Weekend bars are dropped: FX trades continuously and Yahoo shows a
    transient Sunday bar when the market reopens, which is not an end-of-day
    rate for any trading session.

    The current day's bar is still in progress and is stored provisionally;
    the windowed upsert overwrites it on the next run once it has completed.

    Args:
        pair: Six-letter pair, e.g. "USDGBP"
        start: Inclusive ISO start date
        end: Exclusive ISO end date, or None for the latest bar

    Returns:
        list[Quote] whose `currency` carries the pair name
    """
    quotes = []
    for quote in fetch_yahoo_quotes(f"{pair}=X", start, end):
        if datetime.date.fromisoformat(quote.date).weekday() >= 5:
            continue
        quotes.append(Quote(quote.date, format_fx_rate(quote.price), pair))
    return quotes


def snap_fx_rates(pairs, data_dir=None):
    """Fetch a window of dated rates for each pair.

    Failures are isolated per pair, so one dead pair does not cost the day's
    other rates.

    Returns:
        ScrapeResults of [pair, date, rate] rows
    """
    if data_dir is None:
        data_dir = DATA_DIR

    os.makedirs(data_dir, exist_ok=True)
    results = ScrapeResults()
    start = (
        datetime.date.today() - datetime.timedelta(days=SNAP_WINDOW_DAYS)
    ).isoformat()

    for pair in pairs:
        quotes, error = fetch_with_retries(lambda: fetch_fx_quotes(pair, start))
        if error:
            results.failures.append(f"{pair}: {error}")
            continue
        for quote in quotes:
            results.append([pair, quote.date, quote.price])

    return results


def read_fx_rows(fx_csv):
    """Read stored FX rates keyed on (Pair, Date)."""
    if not os.path.isfile(fx_csv):
        return {}

    rows = {}
    with open(fx_csv, mode="r", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)  # Skip header
        for row in reader:
            if len(row) < 3:
                continue
            rows[(row[0], row[1])] = [row[0], row[1], row[2]]
    return rows


def write_fx_files(rows, data_dir):
    """Write the FX history and latest-rate CSVs from an authoritative row set.

    Does not merge with what is already stored, so a rebuild that removed rows
    actually removes them. write_fx_results() does the merging for the daily
    run before calling this.
    """
    ordered = sorted(rows, key=lambda row: (row[1], row[0]))

    with open(os.path.join(data_dir, "fx_history.csv"), "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(FX_HEADER)
        writer.writerows(ordered)

    latest = latest_rows_by_fund(ordered)

    with open(os.path.join(data_dir, "latest_fx.csv"), "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(FX_HEADER)
        writer.writerows(latest[pair] for pair in sorted(latest))


def write_fx_results(results, data_dir=None):
    """Write dated FX rates to CSV files.

    Keyed on (Pair, Date) and upserted, so the current day's provisional rate
    is replaced by the final one without duplicating.

    Args:
        results: List of [pair, date, rate] rows
        data_dir: Directory for output files (default: DATA_DIR)
    """
    if data_dir is None:
        data_dir = DATA_DIR

    os.makedirs(data_dir, exist_ok=True)
    fx_csv = os.path.join(data_dir, "fx_history.csv")

    stored = read_fx_rows(fx_csv)
    for row in results:
        if row[2]:
            stored[(row[0], row[1])] = [row[0], row[1], row[2]]

    write_fx_files(list(stored.values()), data_dir)


def backfill_fx(pairs, start, data_dir=None, report=None):
    """Rebuild stored FX rates from source data, from `start` onwards.

    Uses the same rule as the price rebuild: a pair that fetches successfully
    has its rows from the start date replaced, while a pair that fails keeps
    everything it had.

    Args:
        pairs: Six-letter pair names
        start: Inclusive ISO start date
        data_dir: Directory for output files (default: DATA_DIR)
        report: Existing BackfillReport to add to, or None for a new one

    Returns:
        BackfillReport
    """
    if data_dir is None:
        data_dir = DATA_DIR

    os.makedirs(data_dir, exist_ok=True)
    report = report if report is not None else BackfillReport()
    stored = read_fx_rows(os.path.join(data_dir, "fx_history.csv"))

    for pair in pairs:
        quotes, error = fetch_with_retries(lambda: fetch_fx_quotes(pair, start))
        existing = [key for key in stored if key[0] == pair]

        if error:
            report.failures.append(f"{pair}: {error}")
            report.entries.append(
                {
                    "identifier": pair,
                    "before": len(existing),
                    "deleted": 0,
                    "retained": len(existing),
                    "inserted": 0,
                    "first": min((k[1] for k in existing), default="-"),
                    "last": max((k[1] for k in existing), default="-"),
                    "currency": "-",
                    "status": "failed, kept existing",
                }
            )
            continue

        doomed = [key for key in existing if key[1] >= start]
        for key in doomed:
            del stored[key]

        for quote in quotes:
            stored[(pair, quote.date)] = [pair, quote.date, quote.price]

        report.entries.append(
            {
                "identifier": pair,
                "before": len(existing),
                "deleted": len(doomed),
                "retained": 0,
                "inserted": len(quotes),
                "first": quotes[0].date if quotes else "-",
                "last": quotes[-1].date if quotes else "-",
                "currency": "GBP",
                "status": "rebuilt",
            }
        )

    write_fx_files(list(stored.values()), data_dir)
    return report


def is_removable_row(row):
    """Return True when a stored row may be deleted during a rebuild.

    A rebuild replaces what the source reports, but sources are not perfectly
    reliable: FT's historical endpoint intermittently omits a row or two from
    an identical request (893 vs 895 rows, observed against the live endpoint,
    with a narrow-window query confirming the omitted days are real). Deleting
    every row the source did not return this time would silently lose real
    trading days.

    A row that already carries a currency came from a dated source fetch, so it
    is kept when the source omits it. Rows with no currency predate the
    currency column and are exactly the scrape-dated, carry-forward data the
    rebuild exists to remove. A weekend row is never legitimate for these
    sources, so it is always removable.
    """
    row_date = row[1]
    currency = row[3] if len(row) > 3 else ""
    try:
        if datetime.date.fromisoformat(row_date).weekday() >= 5:
            return True
    except ValueError:
        return True
    return not currency


def backfill_history(specs, start, data_dir=None):
    """Rebuild stored history from source data, from `start` onwards.

    Deletes rather than upserting: carry-forward and scrape-dated rows sit on
    dates the sources never report, so they have no incoming row to replace
    them and an upsert alone would leave them in place.

    An instrument whose fetch fails keeps every row it already had. Rows
    earlier than `start`, and rows for identifiers no longer configured, are
    preserved either way.

    Args:
        specs: FundSpec instances to rebuild
        start: Inclusive ISO start date
        data_dir: Directory for output files (default: DATA_DIR)

    Returns:
        BackfillReport
    """
    if data_dir is None:
        data_dir = DATA_DIR

    os.makedirs(data_dir, exist_ok=True)
    history_csv = os.path.join(data_dir, "prices_history.csv")
    stored = read_history_rows(history_csv)
    report = BackfillReport()
    browser = LazyBrowser()

    try:
        for index, spec in enumerate(specs):
            quotes, error = fetch_with_retries(
                lambda: scrape_fund_quotes(
                    spec.source, spec.lookup_id, start, browser=browser
                )
            )

            if error:
                report.failures.append(f"{spec.lookup_id}: {error}")
                for identifier in spec.publish_ids:
                    kept = [key for key in stored if key[0] == identifier]
                    report.entries.append(
                        {
                            "identifier": identifier,
                            "before": len(kept),
                            "deleted": 0,
                            "retained": len(kept),
                            "inserted": 0,
                            "first": min((k[1] for k in kept), default="-"),
                            "last": max((k[1] for k in kept), default="-"),
                            "currency": "-",
                            "status": "failed, kept existing",
                        }
                    )
                continue

            warning = check_quoting_unit(spec.lookup_id, quotes)
            if warning:
                report.warnings.append(warning)

            fetched_dates = {quote.date for quote in quotes}
            for identifier in spec.publish_ids:
                existing = [key for key in stored if key[0] == identifier]
                doomed, retained = [], []
                for key in existing:
                    if key[1] < start or key[1] in fetched_dates:
                        continue
                    if is_removable_row(stored[key]):
                        doomed.append(key)
                    else:
                        retained.append(key)

                for key in doomed:
                    del stored[key]

                for quote in quotes:
                    if not is_usable_price(quote.price):
                        continue
                    stored[(identifier, quote.date)] = [
                        identifier,
                        quote.date,
                        quote.price,
                        quote.currency,
                    ]

                report.entries.append(
                    {
                        "identifier": identifier,
                        "before": len(existing),
                        "deleted": len(doomed),
                        "retained": len(retained),
                        "inserted": len(quotes),
                        "first": quotes[0].date if quotes else "-",
                        "last": quotes[-1].date if quotes else "-",
                        "currency": quotes[0].currency if quotes else "-",
                        "status": "rebuilt",
                    }
                )

            # The FT endpoint is unofficial; do not hammer it across 26 funds.
            if spec.source.upper() == "FT" and index < len(specs) - 1:
                time.sleep(FT_BACKFILL_PAUSE_SECONDS)
    finally:
        browser.close()

    rows = [row for row in stored.values() if is_usable_price(row[2])]
    write_history_files(rows, data_dir)

    for row in latest_rows_by_fund(rows).values():
        write_latest_price_file(row[0], row[2], data_dir)

    pairs = read_fx_pairs()
    if pairs:
        backfill_fx(pairs, start, data_dir, report=report)

    return report


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
        "  Historical: python scrape_fund_price.py --history AAPL --start 2024-01-01 --end 2024-12-31\n"
        "  Backfill:   python scrape_fund_price.py --backfill --from 2023-01-01",
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
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Rebuild stored history from source data (requires --from)",
    )
    parser.add_argument(
        "--from",
        dest="start",
        type=str,
        metavar="YYYY-MM-DD",
        help="Alias for --start; the date to rebuild history from",
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

    if args.backfill:
        error = validate_backfill_args(args)
        if error:
            print(f"Error: {error}")
            raise SystemExit(2)

        specs = read_fund_specs(FUNDS_FILE)
        report = backfill_history(specs, args.start)
        summary = report.to_markdown()
        print(summary)

        step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if step_summary:
            with open(step_summary, "a", encoding="utf-8") as f:
                f.write(f"## Backfill from {args.start}\n\n{summary}\n")

        # Everything obtainable has been written before signalling failure.
        if report.failures:
            raise SystemExit(1)
        return

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
        failures = []

        funds = read_fund_specs(FUNDS_FILE)
        results = scrape_funds(funds)
        write_results(results)
        failures.extend(getattr(results, "failures", []))

        # FX is snapped after prices and written independently, so a problem
        # with one never costs the other a day of data.
        pairs = read_fx_pairs()
        fx_failures = []
        if pairs:
            fx_results = snap_fx_rates(pairs)
            write_fx_results(fx_results)
            fx_failures = list(fx_results.failures)
            failures.extend(fx_failures)

        # Built from what was just written, so it reflects a partial run too;
        # a day with failures is exactly when the summary is most useful.
        run_date = datetime.date.today().isoformat()
        history = list(read_history_rows(HISTORY_CSV).values())
        price_summary = build_price_summary(
            history, funds, getattr(results, "failures", []), run_date
        )
        fx_summary = build_fx_summary(
            list(read_fx_rows(os.path.join(DATA_DIR, "fx_history.csv")).values()),
            pairs,
            fx_failures,
            run_date,
        )
        write_summary(price_summary, fx_summary, run_date)

        if failures:
            for failure in failures:
                print(f"Error: {failure}")
            raise SystemExit(1)


if __name__ == "__main__":
    main()
