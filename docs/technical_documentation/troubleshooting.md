# Troubleshooting Guide

This document provides solutions for common issues encountered with the Fund Price Scraping project.

## Common Issues and Solutions

### 1. Playwright Browser Issues

#### Issue: "Browser not found" or "Executable doesn't exist"
**Symptoms:**
```
Error: Executable doesn't exist at /path/to/chromium
```

**Solutions:**
```bash
# Install Playwright browsers
playwright install chromium

# Install all browsers
playwright install

# Install with specific version
playwright install chromium@latest
```

#### Issue: Browser crashes or hangs
**Symptoms:**
- Browser process becomes unresponsive
- Memory usage increases significantly
- Timeout errors

**Solutions:**
```bash
# Check system resources
free -h
df -h

# Restart with fresh browser instance
pkill -f chromium
python scrape_fund_price.py

# Use headless mode to reduce resource usage
# (Already enabled by default)
```

### 2. Network and Connectivity Issues

#### Issue: Connection timeout errors
**Symptoms:**
```
TimeoutError: Navigation timeout of 30000 ms exceeded
```

**Solutions:**
```bash
# Check internet connectivity
ping google.com

# Test specific fund URLs manually
curl -I "https://markets.ft.com/data/funds/tearsheet/summary?s=GB00B1FXTF86"

# Increase timeout values in code
# Modify scrape_price_with_common_settings function
```

#### Issue: SSL/TLS certificate errors
**Symptoms:**
```
SSL: CERTIFICATE_VERIFY_FAILED
```

**Solutions:**
```bash
# Update certificates
sudo apt-get update && sudo apt-get install ca-certificates

# For Python SSL issues
pip install --upgrade certifi

# Test SSL connection
openssl s_client -connect markets.ft.com:443
```

#### Issue: Rate limiting or IP blocking
**Symptoms:**
- HTTP 429 (Too Many Requests)
- HTTP 403 (Forbidden)
- CAPTCHA challenges

**Solutions:**
```bash
# Add delays between requests
# Implement exponential backoff
# Use different User-Agent strings
# Consider using proxy servers
```

### 3. Data and File Issues

#### Issue: "File not found" errors
**Symptoms:**
```
FileNotFoundError: [Errno 2] No such file or directory: 'funds.txt'
```

**Solutions:**
```bash
# Check if files exist
ls -la funds.txt
ls -la data/

# Create missing files
touch funds.txt
mkdir -p data

# Check file permissions
ls -la funds.txt
chmod 644 funds.txt
```

#### Issue: CSV file corruption or empty files
**Symptoms:**
- Empty CSV files
- Malformed CSV data
- Encoding issues

**Solutions:**
```bash
# Check file contents
head -5 data/latest_prices.csv
file data/latest_prices.csv

# Recreate data directory
rm -rf data/
mkdir data
python scrape_fund_price.py

# Check for disk space
df -h
```

#### Issue: Permission denied errors
**Symptoms:**
```
PermissionError: [Errno 13] Permission denied: 'data/latest_prices.csv'
```

**Solutions:**
```bash
# Check directory permissions
ls -la data/
chmod 755 data/

# Check file ownership
ls -la data/latest_prices.csv
sudo chown $USER:$USER data/latest_prices.csv

# Run with appropriate permissions
sudo python scrape_fund_price.py
```

### 4. Configuration Issues

#### Issue: Invalid fund identifiers
**Symptoms:**
- Empty results for specific funds
- "Not found" errors
- Wrong price data

**Solutions:**
```bash
# Verify fund identifiers
# Check fund URLs manually in browser
# Validate fund format in funds.txt

# Test individual fund
python -c "
from scrape_fund_price import get_source_config
url, selector = get_source_config('FT', 'GB00B1FXTF86')
print(f'URL: {url}')
print(f'Selector: {selector}')
"
```

#### Issue: Wrong CSS selectors
**Symptoms:**
- Price data not found
- Empty price values
- Selector timeout errors

**Solutions:**
```bash
# Inspect page source manually
# Check if website structure changed
# Update selectors in get_source_config function

# Test selectors
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto('https://markets.ft.com/data/funds/tearsheet/summary?s=GB00B1FXTF86')
    elements = page.locator('.mod-ui-data-list__value').all()
    print(f'Found {len(elements)} elements')
    browser.close()
"
```

### 5. Performance Issues

#### Issue: Slow execution
**Symptoms:**
- Long execution times
- High memory usage
- System becomes unresponsive

**Solutions:**
```bash
# Monitor system resources
top
htop

# Run with reduced concurrency
# Modify scrape_funds function to process sequentially

# Check for memory leaks
python -c "
import psutil
import os
process = psutil.Process(os.getpid())
print(f'Memory usage: {process.memory_info().rss / 1024 / 1024:.2f} MB')
"
```

#### Issue: High CPU usage
**Symptoms:**
- CPU usage near 100%
- System becomes slow
- Browser processes consuming resources

**Solutions:**
```bash
# Check running processes
ps aux | grep python
ps aux | grep chromium

# Kill stuck processes
pkill -f chromium
pkill -f python

# Restart with fresh environment
```

### 6. GitHub Actions Issues

#### Issue: Workflow fails to start
**Symptoms:**
- No workflow runs appearing
- "Workflow not found" errors

**Solutions:**
```bash
# Check workflow file syntax
# Verify .github/workflows/scrape-funds.yml exists
# Check GitHub Actions permissions in repository settings

# Test workflow locally
act -j scrape-funds
```

#### Issue: Workflow runs but fails
**Symptoms:**
- Workflow starts but fails with errors
- Missing dependencies in CI environment

**Solutions:**
```bash
# Check workflow logs in GitHub Actions tab
# Verify all dependencies are installed
# Check file paths and permissions

# Test locally with same environment
docker run -it --rm -v $(pwd):/workspace python:3.9 bash
cd /workspace
pip install -r requirements.txt
playwright install chromium
python test_scrape_fund_price.py
```

## Debugging Techniques

### 1. Enable Verbose Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Add debug prints in code
print(f"Scraping {source}:{fund_id}")
print(f"URL: {url}")
print(f"Selector: {selector}")
```

### 2. Test Individual Components
```bash
# Test fund reading
python -c "from scrape_fund_price import read_fund_ids; print(read_fund_ids('funds.txt'))"

# Test source configuration
python -c "from scrape_fund_price import get_source_config; print(get_source_config('FT', 'GB00B1FXTF86'))"

# Test single fund scraping
python -c "
from scrape_fund_price import scrape_funds
funds = [('FT', 'GB00B1FXTF86')]
results = scrape_funds(funds)
print(results)
"
```

### 3. Browser Debugging
```python
# Run with visible browser
browser = p.chromium.launch(headless=False, slow_mo=1000)

# Take screenshots
page.screenshot(path="debug.png")

# Get page content
content = page.content()
with open("page_source.html", "w") as f:
    f.write(content)
```

### 4. Network Debugging
```bash
# Monitor network traffic
tcpdump -i any -w network.pcap

# Check DNS resolution
nslookup markets.ft.com

# Test HTTP requests
curl -v "https://markets.ft.com/data/funds/tearsheet/summary?s=GB00B1FXTF86"
```

## Recovery Procedures

### 1. Complete Reset
```bash
# Stop all processes
pkill -f python
pkill -f chromium

# Clean up data
rm -rf data/
mkdir data

# Reinstall dependencies
pip uninstall playwright coverage
pip install -r requirements.txt
playwright install chromium

# Test installation
python test_scrape_fund_price.py
```

### 2. Partial Recovery
```bash
# Keep data, reset configuration
cp data/latest_prices.csv data/latest_prices.csv.backup
rm data/latest_prices.csv

# Re-run scraper
python scrape_fund_price.py
```

### 3. Data Recovery
```bash
# Restore from backup
cp data/latest_prices.csv.backup data/latest_prices.csv

# Or restore from Git history
git checkout HEAD~1 -- data/latest_prices.csv
```

## Getting Help

### 1. Check Logs
```bash
# Application logs
tail -f logs/scraper.log

# System logs
journalctl -u fund-prices -f

# GitHub Actions logs
# Check Actions tab in GitHub repository
```

### 2. Community Resources
- GitHub Issues: Report bugs and request features
- Playwright Documentation: https://playwright.dev/python/
- Python Documentation: https://docs.python.org/

### 3. Diagnostic Information
When reporting issues, include:
```bash
# System information
uname -a
python --version
pip list

# Application status
ls -la data/
head -5 data/latest_prices.csv
tail -10 logs/scraper.log
```
