# API Reference

This document provides detailed API documentation for the Fund Price Scraping project.

## Core Functions

### `read_fund_ids(filename)`

Reads fund identifiers from a file.

**Parameters:**
- `filename` (str): Path to the file containing fund identifiers

**Returns:**
- `list`: List of tuples containing (source, identifier) pairs

**File Format:**
Each line should contain: `<source>,<identifier>`
- `source`: Data source identifier (FT, YH, MS)
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

### `scrape_funds(funds, data_dir=None)`

Main function to scrape prices for a list of funds.

**Parameters:**
- `funds` (list): List of (source, identifier) tuples
- `data_dir` (str, optional): Directory to store results (defaults to "data")

**Returns:**
- `list`: List of dictionaries containing scraping results

**Result Format:**
```python
[
    {
        "source": "FT",
        "fund_id": "GB00B1FXTF86",
        "price": "1.2345",
        "timestamp": "2024-01-15 10:30:00",
        "status": "success"
    },
    # ... more results
]
```

### `write_results(results, data_dir=None)`

Writes scraping results to CSV files.

**Parameters:**
- `results` (list): List of result dictionaries
- `data_dir` (str, optional): Directory to write files (defaults to "data")

**Output Files:**
- `latest_prices.csv`: Most recent prices for each fund
- `prices_history.csv`: Historical price data

**CSV Format:**
- Headers: `source,fund_id,price,timestamp,status`
- Encoding: UTF-8
- Line endings: Unix (LF)

## Configuration Constants

### Data Directory Settings
- `DATA_DIR`: Default data directory ("data")
- `LATEST_CSV`: Latest prices file path
- `HISTORY_CSV`: Historical prices file path
- `FUNDS_FILE`: Default funds configuration file ("funds.txt")

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
