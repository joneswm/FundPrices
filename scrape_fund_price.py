from playwright.sync_api import sync_playwright
import datetime
import csv
import os
import yfinance as yf

# Default configuration - can be overridden for testing
DATA_DIR = "data"
LATEST_CSV = os.path.join(DATA_DIR, "latest_prices.csv")
HISTORY_CSV = os.path.join(DATA_DIR, "prices_history.csv")
FUNDS_FILE = "funds.txt"

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

def scrape_funds(funds, data_dir=None):
    """Scrape prices for a list of funds and return results."""
    if data_dir is None:
        data_dir = DATA_DIR
    
    os.makedirs(data_dir, exist_ok=True)
    results = []
    today = datetime.date.today().isoformat()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        for source, fund_id in funds:
            # Use API for GF source, scraping for others
            if source.upper() == "GF":
                price = fetch_price_api(fund_id)
            else:
                url, selector = get_source_config(source, fund_id)
                if url and selector:
                    try:
                        price = scrape_price_with_common_settings(page, url, selector)
                    except Exception as e:
                        price = f"Error: {e}"
                else:
                    price = "N/A"
            results.append([fund_id, today, price])
            # Write latest_<identifier>.price file
            latest_price_file = os.path.join(data_dir, f"latest_{fund_id}.price")
            with open(latest_price_file, "w") as f:
                f.write(price + "\n")
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

def main():
    """Main function to run the fund price scraper."""
    funds = read_fund_ids(FUNDS_FILE)
    results = scrape_funds(funds)
    write_results(results)

if __name__ == "__main__":
    main()

