# Technical Plan: True Price Dates and Currency

**Spec**: SPEC-003
**Status**: ✅ Complete
**Created**: 2026-09-20

---

## Overview

Replace single undated price fetches with dated quote windows, and make storage key on
(Fund, Date) with upsert semantics.

## Technical Approach

### New record type

```python
class Quote(NamedTuple):
    date: str      # ISO YYYY-MM-DD, the price date reported by the source
    price: str     # as quoted; thousands separators removed; no float noise
    currency: str  # "GBP", "GBp", "USD", "HKD"; "" when unknown
```

### Price formatting

Yahoo bars are float32. Python floats therefore carry noise (`124.87000274658203`).
Rounding to fixed decimals stores that noise (`round(x, 6)` → `124.870003`); significant
digit formats lose real precision (`format(126530.25, ".7g")` → `126530.2`).

Use the shortest string that round-trips as float32:

```python
def format_yahoo_price(x):
    s = str(np.float32(x))
    return s[:-2] if s.endswith(".0") else s
```

FT prices arrive as text and stay text — commas stripped, never passed through `float()`.

### Source fetchers

```python
def fetch_yahoo_quotes(symbol, start, end=None) -> list[Quote]
def fetch_ft_quotes(isin, start, end=None) -> list[Quote]
```

**Yahoo**: `yf.Ticker(s).history(start=, end=, auto_adjust=False)`, column `Close`, NaN
rows dropped, currency from `fast_info["currency"]`. `end` is exclusive in yfinance.
`.info` is not used — it is stale for mutual funds and undated.

**FT**: two plain HTTP requests, no browser.
1. `.../funds/tearsheet/historical?s=<ISIN>` → internal xid via
   `&quot;symbol&quot;:&quot;(\d+)&quot;`, currency via `Price \(([A-Za-z]{3})\)`
2. `.../equities/ajax/get-historical-prices?startDate=&endDate=&symbol=<xid>` → JSON
   whose `html` key holds `<tr>` rows; date from the first `<span>`, close from the
   4th `<td>`

On any FT failure, fall back to the Playwright scrape for that fund, producing an
undated quote with a warning.

### Architecture Changes

| Component | Change |
|---|---|
| `fetch_price_api()` | Thin wrapper over `fetch_yahoo_quotes`, same `"Error: ..."` contract |
| `scrape_funds()` | Returns `[fund_id, date, price, currency]`, several rows per fund |
| `write_results()` | Upsert on (Fund, Date); 4-column output; sorted; legacy-tolerant |
| `source_requires_browser()` | False for `FT` and `GF`; browser launches lazily |
| `main()` | No longer raises before output is committed |

### Data Flow

```
funds.txt
   ↓
for each fund → fetch_*_quotes(start = today - 10 days)
   ↓ (retries, then last-known-price fallback on total failure)
ScrapeResults: [fund_id, date, price, currency] × window
   ↓
write_results() → upsert into prices_history.csv on (Fund, Date)
   ↓
latest_prices.csv (max date per fund) + prices_history_90_days.csv + latest_<id>.price
```

## Testing Strategy

- Unit tests mock `yf.Ticker`, `requests.get` and `sync_playwright`; no network
- Precision regression tests assert exact strings for known float32 inputs
- Idempotency asserted by writing twice and comparing file bytes
- Functional tests (real network) added per route, tolerant of source outages

## Backwards Compatibility

- `Fund,Date,Price` remain the first three columns; `Currency` is appended
- Legacy 3-column rows load with an empty currency
- `read_fund_ids()` keeps its current signature and return shape
- `fetch_price_api()` keeps returning a price string or `"Error: ..."`

## Rollback Plan

Data files are in git; revert the commit and the previous CSVs return. No schema
migration step is required because readers tolerate both column counts.
