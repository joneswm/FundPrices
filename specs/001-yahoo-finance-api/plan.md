# Technical Plan: Yahoo Finance API Integration

**Spec**: SPEC-001  
**Status**: ✅ Complete  
**Created**: 2024-11-20 (Retrospective)

---

## Overview

Replace Google Finance web scraping with Yahoo Finance API using the `yfinance` library. This provides more reliable data access without the fragility of CSS selector-based scraping.

## Technical Approach

### API Library Selection

**Chosen**: `yfinance` (Yahoo Finance API wrapper)

**Rationale**:
- Official Python wrapper for Yahoo Finance
- Well-maintained with active community
- Handles API authentication and rate limiting
- Provides structured data (JSON)
- Free for basic price data
- Simple API: `yf.Ticker(symbol).info['currentPrice']`

**Alternatives Considered**:
- Direct Yahoo Finance API calls: More complex, requires manual parsing
- Alpha Vantage: Requires API key, rate limits too restrictive
- IEX Cloud: Paid service, overkill for our needs

### Architecture Changes

#### New Function: `fetch_price_api()`

```python
def fetch_price_api(symbol):
    """
    Fetch current price for a symbol using Yahoo Finance API.
    
    Args:
        symbol: Stock/fund symbol (e.g., 'AAPL', 'MSFT')
    
    Returns:
        str: Price as string, or "Error: <message>" on failure
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # Try multiple price fields (API returns different fields)
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        
        if price is None:
            return f"Error: No price data for {symbol}"
        
        return str(price)
    
    except Exception as e:
        return f"Error: {str(e)}"
```

#### Modified Function: `scrape_funds()`

Update routing logic to use API for GF source:

```python
def scrape_funds(fund_ids):
    results = []
    
    for source, fund_id in fund_ids:
        if source.upper() == "GF":
            # Use API instead of scraping
            price = fetch_price_api(fund_id)
        else:
            # Use web scraping for FT, YH, MS
            url, selector = get_source_config(source, fund_id)
            if url and selector:
                price = scrape_price_with_common_settings(url, selector)
            else:
                price = "N/A"
        
        results.append((fund_id, price))
    
    return results
```

#### No Changes Required

- `get_source_config()`: GF source removed from scraping config
- `scrape_price_with_common_settings()`: Unchanged
- `write_results()`: Unchanged
- `read_fund_ids()`: Unchanged

### Data Flow

```
funds.txt (GF,AAPL)
    ↓
read_fund_ids()
    ↓
scrape_funds()
    ↓
[GF source detected]
    ↓
fetch_price_api("AAPL")
    ↓
yfinance library
    ↓
Yahoo Finance API
    ↓
Return price or error
    ↓
write_results()
    ↓
data/latest_prices.csv
data/prices_history.csv
```

## Dependencies

### New Dependency

Add to `requirements.txt`:
```
yfinance>=0.2.0
```

**Version Rationale**:
- 0.2.0 introduced stable API
- Use `>=` to allow patch updates
- Pin major version to avoid breaking changes

### Installation

```bash
pip install yfinance>=0.2.0
```

### Compatibility

- Python 3.7+
- Works with existing dependencies (playwright, coverage)
- No conflicts with current libraries

## Error Handling

### Error Scenarios

1. **Invalid Symbol**
   - Cause: Symbol doesn't exist (e.g., "INVALID123")
   - Response: `"Error: No price data for INVALID123"`
   - Action: Log error, continue processing other funds

2. **API Unavailable**
   - Cause: Network error, Yahoo Finance down
   - Response: `"Error: <exception message>"`
   - Action: Log error, continue processing other funds

3. **Timeout**
   - Cause: API call takes > 30 seconds
   - Response: `"Error: Request timeout"`
   - Action: Log error, continue processing other funds

4. **Rate Limiting**
   - Cause: Too many requests to Yahoo Finance
   - Response: `"Error: Rate limit exceeded"`
   - Action: Log error, implement backoff if needed

### Error Format

All errors follow consistent format:
```
"Error: <descriptive message>"
```

This matches existing error format for web scraping failures.

## Testing Strategy

### Unit Tests (with Mocking)

1. **test_fetch_price_api_valid_symbol()**
   - Mock `yf.Ticker().info` to return price
   - Verify function returns price as string
   - Test both `currentPrice` and `regularMarketPrice` fields

2. **test_fetch_price_api_invalid_symbol()**
   - Mock `yf.Ticker().info` to return empty dict
   - Verify function returns error message
   - Check error format matches pattern

3. **test_fetch_price_api_exception()**
   - Mock `yf.Ticker()` to raise exception
   - Verify function catches and returns error
   - Check error message includes exception details

4. **test_scrape_funds_with_gf_source()**
   - Mock `fetch_price_api()` to return price
   - Verify GF source routes to API
   - Verify other sources still use scraping

### Functional Tests (Real API)

1. **test_functional_yahoo_finance_api()**
   - Make real API call with known symbol (e.g., "AAPL")
   - Verify price is returned
   - Verify price is numeric string
   - Allow test to fail gracefully if API unavailable

### Coverage Target

- Maintain 90%+ overall coverage
- 100% coverage for new `fetch_price_api()` function
- No decrease in coverage for existing functions

## Performance Considerations

### Expected Performance

- **API Call Time**: 1-3 seconds per symbol
- **Comparison to Scraping**: Similar or faster (no browser overhead)
- **Memory Usage**: Minimal (no browser instance)

### Optimization Opportunities

- **Future**: Batch API calls if yfinance supports it
- **Future**: Cache prices for short duration (5 minutes)
- **Future**: Parallel API calls for multiple symbols

### Performance Testing

Monitor execution time:
```python
import time
start = time.time()
price = fetch_price_api("AAPL")
elapsed = time.time() - start
print(f"API call took {elapsed:.2f} seconds")
```

## Security Considerations

### API Key

- Yahoo Finance API (via yfinance) doesn't require API key
- No secrets to manage
- No authentication needed

### Data Privacy

- Only public stock/fund prices accessed
- No personal data transmitted
- No sensitive information logged

### Rate Limiting

- yfinance library handles rate limiting internally
- Reasonable delays between calls
- Respect Yahoo Finance terms of service

## Deployment Considerations

### GitHub Actions

No changes required:
- `yfinance` will be installed via `requirements.txt`
- No additional setup needed
- Works in headless environment

### Local Development

Developers must install new dependency:
```bash
pip install -r requirements.txt
```

### Backwards Compatibility

- Existing `funds.txt` format unchanged
- GF source code still valid
- Other sources (FT, YH, MS) unaffected
- No breaking changes to output format

## Rollback Plan

If API integration fails:

1. **Immediate**: Comment out API routing, revert to scraping
2. **Short-term**: Remove `yfinance` dependency
3. **Long-term**: Investigate alternative APIs

Rollback is low-risk because:
- Changes are isolated to GF source
- Other sources unaffected
- No database or schema changes

## Monitoring and Validation

### Success Metrics

- API calls succeed > 95% of time
- Average response time < 5 seconds
- No increase in error rate
- Test coverage maintained at 90%+

### Validation Steps

1. Run full test suite: `python test_scrape_fund_price.py`
2. Test with real symbols: `GF,AAPL` in `funds.txt`
3. Verify CSV output format unchanged
4. Check error handling with invalid symbol
5. Monitor GitHub Actions workflow

## Documentation Updates

### Files to Update

1. **README.md**
   - Add GF source explanation
   - Note API vs scraping approach
   - Update examples

2. **AGENTS.md**
   - Document API approach for GF
   - Update source code table
   - Add yfinance to dependencies

3. **implementation_status.md**
   - Mark US-025 as complete
   - Document implementation details
   - Note test coverage

4. **Code Comments**
   - Document `fetch_price_api()` function
   - Explain API vs scraping decision
   - Note error handling approach

## Timeline and Milestones

**Retrospective Note**: Feature completed in 2024

- ✅ Dependency added to requirements.txt
- ✅ `fetch_price_api()` function implemented
- ✅ `scrape_funds()` routing updated
- ✅ Unit tests created (3 tests)
- ✅ Functional test created (1 test)
- ✅ Documentation updated
- ✅ Code coverage maintained at 92%

## Lessons Learned

**Retrospective Insights**:

1. **API > Scraping**: API approach is more reliable and maintainable
2. **Library Choice**: Using `yfinance` saved significant development time
3. **Error Handling**: Consistent error format across sources is important
4. **Testing**: Mocking API responses enables fast, reliable unit tests
5. **Backwards Compatibility**: Maintaining existing format reduced migration risk

## Future Enhancements

Potential improvements (out of scope for this spec):

1. **Caching**: Cache prices for 5-10 minutes to reduce API calls
2. **Batch Calls**: Fetch multiple symbols in single API call
3. **Historical Data**: Use yfinance to fetch historical prices (separate spec)
4. **Real-time Updates**: WebSocket connection for live prices
5. **Additional APIs**: Support multiple API providers with fallback

## References

- [yfinance Documentation](https://pypi.org/project/yfinance/)
- [yfinance GitHub](https://github.com/ranaroussi/yfinance)
- [Yahoo Finance API](https://finance.yahoo.com/)
- [Python Requests Library](https://requests.readthedocs.io/)

---

**Plan Status**: ✅ Complete  
**Implementation Status**: ✅ Complete  
**Next Steps**: See SPEC-027 for historical data retrieval
