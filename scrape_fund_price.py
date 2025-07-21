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
        return [line.strip() for line in f if line.strip()]

def get_fund_url(identifier):
    return f"https://markets.ft.com/data/funds/tearsheet/summary?s={identifier}"

fund_ids = read_fund_ids(FUNDS_FILE)
results = []
today = datetime.date.today().isoformat()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    for fund_id in fund_ids:
        url = get_fund_url(fund_id)
        page.goto(url, timeout=60000)
        page.wait_for_selector(".mod-ui-data-list__value")
        price = page.locator(".mod-ui-data-list__value").first.text_content().strip()
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

