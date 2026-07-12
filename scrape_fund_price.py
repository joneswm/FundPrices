from playwright.sync_api import sync_playwright
import datetime
import csv
import os
import yfinance as yf
import argparse
import re
from contextlib import nullcontext

# Default configuration - can be overridden for testing
DATA_DIR = "data"
LATEST_CSV = os.path.join(DATA_DIR, "latest_prices.csv")
HISTORY_CSV = os.path.join(DATA_DIR, "prices_history.csv")
FUNDS_FILE = "funds.txt"
MAX_PRICE_ATTEMPTS = 3


class ScrapeResults(list):
    """Scrape results with non-price failure metadata."""

    def __init__(self, rows=None, failures=None):
        super().__init__(rows or [])
        self.failures = failures or []


def read_fund_ids(filename):
    """Read fund identifiers from a file."""
    with open(filename, "r") as f:
        # Each line: <source>,<identifier>
        return [tuple(line.strip().split(",", 1)) for line in f if line.strip()]

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
            "selector": ".mod-ui-data-list__value"
        },
        "YH": {
            "url": f"https://sg.finance.yahoo.com/quote/{fund_id}/",
            "selector": 'span[data-testid="qsp-price"]'
        },
        "MS": {
            "url": f"https://asialt.morningstar.com/DSB/QuickTake/overview.aspx?code={fund_id}",
            "selector": '#mainContent_quicktakeContent_fvOverview_lblNAV'
        }
    }
    
    config = source_configs.get(source.upper())
    if config:
        return config["url"], config["selector"]
    return None, None

def fetch_price_api(symbol):
    """Fetch price using Yahoo Finance API.
    
    Args:
        symbol: Stock/fund ticker symbol (e.g., AAPL, MSFT)
        
    Returns:
        Price as string or error message
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        if price is None:
            return "Error: Price not available"
        return str(price)
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
    """Return True when a fund source needs Playwright scraping."""
    if source.upper() == "GF":
        return False

    url, selector = get_source_config(source, fund_id)
    return bool(url and selector)


def scrape_funds(funds, data_dir=None):
    """Scrape prices for a list of funds and return results."""
    if data_dir is None:
        data_dir = DATA_DIR
    
    os.makedirs(data_dir, exist_ok=True)
    results = ScrapeResults()
    today = datetime.date.today().isoformat()
    needs_browser = any(
        source_requires_browser(source, fund_id) for source, fund_id in funds
    )

    with sync_playwright() if needs_browser else nullcontext(None) as p:
        browser = None
        page = None
        if needs_browser:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
        for source, fund_id in funds:
            # Use API for GF source, scraping for others
            if source.upper() == "GF":
                price, error = fetch_with_retries(lambda: fetch_price_api(fund_id))
            else:
                url, selector = get_source_config(source, fund_id)
                if url and selector:
                    price, error = fetch_with_retries(
                        lambda: scrape_price_with_common_settings(page, url, selector)
                    )
                else:
                    price = "N/A"
                    error = None

            if error:
                fallback_price = get_last_known_price(fund_id, data_dir)
                price = fallback_price if fallback_price is not None else "N/A"
                results.failures.append(f"{fund_id}: {error}")

            results.append([fund_id, today, price])
            # Write latest_<identifier>.price file
            latest_price_file = os.path.join(data_dir, f"latest_{fund_id}.price")
            with open(latest_price_file, "w") as f:
                f.write(price + "\n")
        if browser:
            browser.close()
    
    return results

def write_results(results, data_dir=None):
    """Write results to CSV files.
    
    Latest prices file is overwritten on each run.
    History file prevents duplicates by removing any existing entries
    for today's date before appending new results.
    
    Args:
        results: List of [fund_id, date, price] results
        data_dir: Directory for output files (default: DATA_DIR)
    """
    if data_dir is None:
        data_dir = DATA_DIR
    
    latest_csv = os.path.join(data_dir, "latest_prices.csv")
    history_csv = os.path.join(data_dir, "prices_history.csv")
    
    # Write latest prices (overwrite)
    with open(latest_csv, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["Fund", "Date", "Price"])
        writer.writerows(results)

    # Get today's date from results (all results have same date)
    today = results[0][1] if results else datetime.date.today().isoformat()
    
    # Read existing history and filter out today's entries
    history_rows = []
    file_exists = os.path.isfile(history_csv)
    
    if file_exists:
        with open(history_csv, mode="r", newline="") as file:
            reader = csv.reader(file)
            next(reader, None)  # Skip header
            for row in reader:
                if len(row) >= 3 and row[1] != today:
                    history_rows.append(row)
    
    # Append new results for today
    history_rows.extend(results)
    
    # Write complete history back to file
    with open(history_csv, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["Fund", "Date", "Price"])
        writer.writerows(history_rows)

def parse_arguments(args=None):
    """Parse command-line arguments.
    
    Args:
        args: List of arguments to parse (for testing). If None, uses sys.argv.
        
    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description='Fund Price Scraper with Historical Data Support',
        epilog='Examples:\n'
               '  Normal mode: python scrape_fund_price.py\n'
               '  Historical: python scrape_fund_price.py --history AAPL --start 2024-01-01 --end 2024-12-31',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--history', type=str, metavar='SYMBOL',
                        help='Symbol to fetch historical data for (e.g., AAPL, MSFT)')
    parser.add_argument('--start', type=str, metavar='YYYY-MM-DD',
                        help='Start date in YYYY-MM-DD format (required with --history)')
    parser.add_argument('--end', type=str, metavar='YYYY-MM-DD',
                        help='End date in YYYY-MM-DD format (optional, defaults to today)')
    
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
    date_pattern = r'^\d{4}-\d{2}-\d{2}$'
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
        funds = read_fund_ids(FUNDS_FILE)
        results = scrape_funds(funds)
        write_results(results)
        if getattr(results, "failures", []):
            for failure in results.failures:
                print(f"Error: {failure}")
            raise SystemExit(1)

if __name__ == "__main__":
    main()
