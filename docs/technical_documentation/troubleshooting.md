# Troubleshooting Guide

Solutions for common problems with the Fund Price Scraping project. For how the system
is put together see [architecture](architecture.md); for how it runs see
[deployment](deployment.md).

## How failures are reported

Knowing the contract makes most problems quick to read:

- A fetcher **raises** when it cannot get a price. `fetch_with_retries()` retries it up to
  `MAX_PRICE_ATTEMPTS` (3) times.
- A fund that fails every attempt is recorded on the result object's `failures` list, as
  `<identifier>: <error>`, and its last known price is carried into `latest_prices.csv`
  under its original date. Nothing is invented for today.
- **No error text is ever written to a data file.** A price column holding anything but a
  number is a bug, not an expected state.
- Everything obtainable is written first. Only then are the failures printed, one
  `Error: <failure>` line each, and the process exits non-zero.
- A step that crashes as a whole is reported with its name in front, for example
  `prices: <error>`, `fx: <error>`, `uk_cpi: <error>` or `uk_bank_rate: <error>`, so the
  other steps still write their files.

Result rows are `[identifier, date, price, currency]`.

## Common Issues and Solutions

### 1. Playwright Browser Issues

Playwright is only a fallback: Yahoo, investing.com and the FT's dated HTTP endpoint need
no browser, and the browser is started lazily when an FT lookup has failed. If a run
needed no fallback, a missing browser is harmless.

#### Issue: "Browser not found" or "Executable doesn't exist"
**Symptoms:**
```
Executable doesn't exist at /path/to/chromium
```

**Solutions:**
```bash
playwright install chromium
```

#### Issue: Browser hangs or times out
**Symptoms:**
- A fund that fell back to scraping takes minutes and then fails
- Timeout errors from `wait_for_selector`

**Solutions:**
- Establish first why the FT HTTP endpoint failed: the scraping fallback only runs after a
  `Warning: FT historical lookup failed for ...` line.
- Kill a stuck Chromium and re-run: `pkill -f chromium`.
- If FT changed its page, the selector lives in `get_source_config()`; see
  [Wrong CSS selectors](#issue-wrong-css-selectors).

### 2. Network and Connectivity Issues

#### Issue: Connection timeout errors
**Solutions:**
```bash
# Check that the source answers
curl -I "https://markets.ft.com/data/funds/tearsheet/summary?s=GB00B1FXTF86"
```
A one-off timeout is absorbed by the retries. If a fund fails on every run, the failure
line names it.

#### Issue: SSL/TLS certificate errors
**Symptoms:**
```
SSL: CERTIFICATE_VERIFY_FAILED
```

**Solutions:**
```bash
pip install --upgrade certifi
openssl s_client -connect markets.ft.com:443
```

#### Issue: Rate limiting or IP blocking
**Symptoms:**
- HTTP 429 (Too Many Requests) or 403 (Forbidden) in a failure line
- A source that works from your machine but not from GitHub Actions

**Solutions:** wait and re-run. The two daily runs give a second attempt within hours,
and the last known price is carried meanwhile.

### 3. Data and File Issues

#### Issue: "File not found" errors
**Symptoms:**
```
FileNotFoundError: [Errno 2] No such file or directory: 'funds.txt'
```

**Solutions:** the configuration files and `data/` are read from the working directory,
so run from the repository root. `data/` is created on demand.

#### Issue: A configuration file is rejected
**Symptoms:** the run stops before any network call with a message naming a line.

**Solutions:** `funds.txt`, `fx_pairs.txt`, `closed_holdings.txt`, `distributions.txt` and
`dividend_sources.txt` are validated up front. Fix the line named; the formats are in the
[README](../../README.md#configuration). A repeated identifier, an empty or
self-referencing alias, or a slash-spelled FX pair (`GBP/USD`) are the usual causes.

#### Issue: CSV file corruption or empty files
**Symptoms:**
- Empty CSV files
- Malformed CSV data

**Solutions:** the `data/` files are tracked in git, so restore rather than delete:
```bash
git status data/
git checkout -- data/latest_prices.csv
```
Do not delete `data/`: `prices_history.csv` holds closed-holding rows that a daily run
never fetches again. To rebuild ordinary history from the sources use
`python scrape_fund_price.py --backfill --from 2021-12-01`.

### 4. Configuration Issues

#### Issue: Invalid fund identifiers
**Symptoms:**
- A fund fails every run
- Wrong price data

**Solutions:**
```bash
# Look at what the source returns for one identifier
python -c "
from scrape_fund_price import fetch_yahoo_quotes
for quote in fetch_yahoo_quotes('IDTG.L', '2026-10-01'):
    print(quote)
"
```
Use `fetch_ft_quotes` for an `FT` line. Each quote is a `Quote(date, price, currency)`.

#### Issue: Wrong CSS selectors
**Symptoms:**
- A fund on the scraping fallback fails with a selector timeout

**Solutions:**
```bash
# What the fallback would load
python -c "
from scrape_fund_price import get_source_config
print(get_source_config('FT', 'GB00B1FXTF86'))
"
```
Open the URL in a browser and check the selector still matches. If it does not, update it
in `get_source_config()`, test first.

### 5. GitHub Actions Issues

#### Issue: Workflow fails to start
**Symptoms:**
- No workflow runs appearing

**Solutions:**
- Verify `.github/workflows/scrape.yml` exists (`backfill.yml` and `test.yml` sit beside
  it) and that Actions is enabled in the repository settings.
- Scheduled runs start hours late and can be skipped; a manual run from the Actions tab
  (`workflow_dispatch`) is always available.

#### Issue: A run is red but the data was committed
**Symptoms:**
- The scrape workflow shows as failed
- `Update fund prices` was still pushed

**Explanation:** this is by design. A fund or FX pair that failed every attempt makes
the run exit non-zero, but only after everything obtainable has been written, and the
commit steps run with `if: always()`. Check the run's job summary or
`data/daily_summary.md`: failed instruments are marked `!`, and stale ones `~`.

#### Issue: A source returns prices that look plausible but are wrong
**Symptoms:**
- A long run of identical closes, often with zero volume
- A currency you did not expect
- Rows dated on a day the exchange was shut

**Explanation:** all three have happened. Yahoo repeated one close for 60 trading days
across a fund rename; FT's ISIN lookup resolved a USD holding to its EUR listing; and
FT prices LSE-listed ETFs on UK bank holidays. Prefer an explicit FT symbol such as
`SEAL:LSE:GBX` over an ISIN for anything exchange-listed, and compare a new source
against a second one before relying on it. `closed_holdings.txt` records worked examples.

#### Issue: Workflow runs but fails
**Symptoms:**
- The job fails before the scraper runs, or the tests fail

**Solutions:**
- Read the failing step in the Actions tab. A dependency problem shows at "Install
  dependencies"; a scrape failure shows at "Run scraper" with the `Error: ...` lines.
- Reproduce with the same requirements:
  `pip install -r requirements.txt && ./run_tests.sh unit`.

## Debugging Techniques

### 1. Run the tests
```bash
./run_tests.sh unit        # mocks only, seconds
./run_tests.sh live        # hits the live sources; skips a source that is down
```

### 2. Test Individual Components
```bash
# Test fund reading
python -c "from scrape_fund_price import read_fund_specs; print(read_fund_specs('funds.txt'))"

# Test one fund with the same retry behaviour as the daily run
python -c "
from scrape_fund_price import FundSpec, scrape_funds
results = scrape_funds([FundSpec('YA', 'IDTG.L')], data_dir='/tmp/fp-debug')
print(list(results), results.failures)
"
```
Use a scratch `data_dir` so the repository's `.price` files are untouched.

### 3. Browser Debugging
Only the FT fallback uses a browser. To watch it, temporarily change `headless=True` to
`headless=False` in `LazyBrowser.page()`; do not commit that.

### 4. Network Debugging
```bash
nslookup markets.ft.com
curl -v "https://markets.ft.com/data/funds/tearsheet/summary?s=GB00B1FXTF86"
```

## Recovery Procedures

### 1. Restore a bad day's data
The data is in git history:
```bash
git log --oneline -- data/latest_prices.csv
git checkout <commit> -- data/latest_prices.csv
```
or revert the "Update fund prices" commit. Latest prices never step backwards, so repair
stored history with `--backfill` rather than expecting a later run to overwrite a newer
row with an older one.

### 2. Reinstall the environment
```bash
pip install -r requirements.txt
playwright install chromium
./run_tests.sh unit
```

## Getting Help

- Check the failing run in the GitHub Actions tab, and `data/daily_summary.md`.
- Report bugs and request features as
  [GitHub Issues](https://github.com/joneswm/FundPrices/issues).
- When reporting, include `python --version`, the `Error: ...` lines from the run and the
  relevant line of the configuration file.
