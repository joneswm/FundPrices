from playwright.sync_api import sync_playwright
import datetime
import csv
import os

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
    """Get URL and selector for a given source and fund_id."""
    if source.upper() == "FT":
        url = f"https://markets.ft.com/data/funds/tearsheet/summary?s={fund_id}"
        selector = ".mod-ui-data-list__value"
    elif source.upper() == "YH":
        url = f"https://sg.finance.yahoo.com/quote/{fund_id}/"
        selector = 'span[data-testid="qsp-price"]'
    elif source.upper() == "MS":
        url = f"https://asialt.morningstar.com/DSB/QuickTake/overview.aspx?code={fund_id}"
        selector = '#mainContent_quicktakeContent_fvOverview_lblNAV'
    elif source.upper() == "GF":
        url = f"https://www.google.com/finance/quote/{fund_id}"
        selector = '.YMlKec.fxKbKc'
    else:
        return None, None
    return url, selector

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
    """Write results to CSV files."""
    if data_dir is None:
        data_dir = DATA_DIR
    
    latest_csv = os.path.join(data_dir, "latest_prices.csv")
    history_csv = os.path.join(data_dir, "prices_history.csv")
    
    # Write latest prices (overwrite)
    with open(latest_csv, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["Fund", "Date", "Price"])
        writer.writerows(results)

    # Append to price history
    file_exists = os.path.isfile(history_csv)
    with open(history_csv, mode="a", newline="") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Fund", "Date", "Price"])
        writer.writerows(results)

def main():
    """Main function to run the fund price scraper."""
    funds = read_fund_ids(FUNDS_FILE)
    results = scrape_funds(funds)
    write_results(results)

if __name__ == "__main__":
    main()

