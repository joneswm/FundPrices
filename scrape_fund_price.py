from playwright.sync_api import sync_playwright
import datetime
import csv
import os

URL = "https://markets.ft.com/data/funds/tearsheet/summary?s=IE0008368742" 
CSV_FILE = "data/latest_price.csv"

os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(URL, timeout=60000)
    page.wait_for_selector(".mod-ui-data-list__value")

    price = page.locator(".mod-ui-data-list__value").first.text_content().strip()
    today = datetime.date.today().isoformat()

    with open(CSV_FILE, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["Date", "Price"])
        writer.writerow([today, price])

    browser.close()

