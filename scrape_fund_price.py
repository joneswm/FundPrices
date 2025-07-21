from playwright.sync_api import sync_playwright
import datetime
import csv
import os

DATA_DIR = "data"
LATEST_CSV = os.path.join(DATA_DIR, "latest_prices.csv")
HISTORY_CSV = os.path.join(DATA_DIR, "prices_history.csv")
FUNDS_FILE = "funds.txt"

os.makedirs(DATA_DIR, exist_ok=True)

def read_fund_ids(filename):
    with open(filename, "r") as f:
        # Each line: <source>,<identifier>
        return [tuple(line.strip().split(",", 1)) for line in f if line.strip()]

def get_fund_url(identifier):
    return f"https://markets.ft.com/data/funds/tearsheet/summary?s={identifier}"

funds = read_fund_ids(FUNDS_FILE)
results = []
today = datetime.date.today().isoformat()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    for source, fund_id in funds:
        if source.upper() == "FT":
            url = get_fund_url(fund_id)
            page.goto(url, timeout=60000)
            page.wait_for_selector(".mod-ui-data-list__value")
            price = page.locator(".mod-ui-data-list__value").first.text_content().strip()
        elif source.upper() == "YH":
            url = f"https://sg.finance.yahoo.com/quote/{fund_id}/"
            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/115.0.0.0 Safari/537.36"
            )
            page.context.set_extra_http_headers({"User-Agent": user_agent})
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_selector('span[data-testid="qsp-price"]', timeout=60000)
            price = page.locator('span[data-testid="qsp-price"]').first.text_content().strip()
        elif source.upper() == "MS":
            url = f"https://asialt.morningstar.com/DSB/QuickTake/overview.aspx?code={fund_id}"
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_selector('#mainContent_quicktakeContent_fvOverview_lblNAV', timeout=60000)
            price = page.locator('#mainContent_quicktakeContent_fvOverview_lblNAV').first.text_content().strip()
        else:
            price = "N/A"
        results.append([fund_id, today, price])
        # Write latest_<identifier>.price file
        latest_price_file = os.path.join(DATA_DIR, f"latest_{fund_id}.price")
        with open(latest_price_file, "w") as f:
            f.write(price + "\n")
    browser.close()

# Write latest prices (overwrite)
with open(LATEST_CSV, mode="w", newline="") as file:
    writer = csv.writer(file)
    writer.writerow(["Fund", "Date", "Price"])
    writer.writerows(results)

# Append to price history
file_exists = os.path.isfile(HISTORY_CSV)
with open(HISTORY_CSV, mode="a", newline="") as file:
    writer = csv.writer(file)
    if not file_exists:
        writer.writerow(["Fund", "Date", "Price"])
    writer.writerows(results)

