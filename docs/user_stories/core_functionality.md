# Core Functionality User Stories

## US-001: Multi-Source Fund Price Scraping

**As** a financial analyst  
**I want** to scrape fund prices from multiple sources (FT, Yahoo Finance, Morningstar)  
**So that** I can get comprehensive price data from different providers

### Acceptance Criteria:
- [ ] System can scrape prices from Financial Times (FT)
- [ ] System can scrape prices from Yahoo Finance (YH)
- [ ] System can scrape prices from Morningstar (MS)
- [ ] Each source uses appropriate URL patterns and selectors
- [ ] System handles source-specific error cases gracefully
- [ ] All sources return price data in consistent format

### Definition of Done:
- [ ] All three sources implemented and tested
- [ ] Error handling for each source implemented
- [ ] Functional tests pass for all sources
- [ ] Documentation updated

---

## US-002: Configuration-Based Fund Management

**As** a system administrator  
**I want** to manage fund identifiers through a simple configuration file  
**So that** I can easily add, remove, or modify funds without changing code

### Acceptance Criteria:
- [ ] Funds are defined in `funds.txt` file
- [ ] Each line follows format: `<source>,<identifier>`
- [ ] System supports two-character source codes (FT, YH, MS)
- [ ] Empty lines and whitespace are ignored
- [ ] Invalid source codes are handled gracefully
- [ ] System reads configuration on each run

### Definition of Done:
- [ ] Configuration file format documented
- [ ] Error handling for invalid configurations implemented
- [ ] Unit tests for configuration reading pass
- [ ] Example configuration file provided

---

## US-003: Latest Price File Generation

**As** a data consumer  
**I want** individual price files for each fund  
**So that** I can easily access the most recent price for any specific fund

### Acceptance Criteria:
- [ ] System creates `latest_<identifier>.price` files
- [ ] Each file contains only the latest price value
- [ ] Files are created in the `data/` directory
- [ ] Files are overwritten on each run
- [ ] File naming handles special characters in identifiers

### Definition of Done:
- [ ] File generation works for all fund types
- [ ] File naming convention documented
- [ ] Unit tests for file generation pass
- [ ] Error handling for file operations implemented

---

## US-004: CSV Data Export

**As** a data analyst  
**I want** price data exported to CSV files  
**So that** I can analyze historical trends and current prices

### Acceptance Criteria:
- [ ] System creates `latest_prices.csv` with current prices
- [ ] System appends to `prices_history.csv` for historical data
- [ ] CSV files include Fund, Date, and Price columns
- [ ] Latest prices file is overwritten each run
- [ ] History file appends new data without duplicates
- [ ] CSV format is standard and readable by common tools

### Definition of Done:
- [ ] Both CSV files generated correctly
- [ ] CSV format validated
- [ ] Unit tests for CSV operations pass
- [ ] File structure documented

---

## US-005: Error Handling and Resilience

**As** a system operator  
**I want** the system to handle errors gracefully  
**So that** partial failures don't stop the entire process

### Acceptance Criteria:
- [ ] System continues processing if one fund fails
- [ ] Failed funds are marked as "N/A" or "Error: <message>"
- [ ] System logs errors appropriately
- [ ] Network timeouts are handled
- [ ] Invalid selectors are handled
- [ ] System creates output files even with partial failures

### Definition of Done:
- [ ] Error handling implemented for all failure scenarios
- [ ] Error messages are informative
- [ ] System resilience tested with various failure conditions
- [ ] Error handling documented

---

## US-006: Data Directory Management

**As** a system administrator  
**I want** the system to automatically create necessary directories  
**So that** I don't need to manually set up the file structure

### Acceptance Criteria:
- [ ] System creates `data/` directory if it doesn't exist
- [ ] System handles permission errors gracefully
- [ ] Directory creation works in different environments
- [ ] System works with existing directories

### Definition of Done:
- [ ] Directory creation tested in various environments
- [ ] Error handling for directory operations implemented
- [ ] Unit tests for directory management pass 

---

## US-025: Yahoo Finance API Integration (Alternative to Google Finance)

**As** a financial analyst  
**I want** to retrieve fund prices using Yahoo Finance API instead of screen scraping  
**So that** I can access reliable, structured data without the fragility of web scraping

### Acceptance Criteria:
- [x] System can fetch prices using Yahoo Finance API (yfinance library)
- [x] API-based approach replaces screen scraping for Google Finance source
- [x] System handles API-specific error cases gracefully (rate limits, invalid symbols)
- [x] API returns price data in consistent format with other sources
- [x] Source code "GF" continues to work but uses API instead of scraping
- [x] System validates fund symbols before API calls
- [x] API timeouts and rate limiting are handled appropriately
- [x] yfinance library added to requirements.txt

### Definition of Done:
- [x] yfinance library integrated and tested
- [x] Error handling for API failures implemented
- [x] Unit tests for API integration pass
- [x] Functional tests against real Yahoo Finance API pass
- [x] Documentation updated with API approach
- [x] Configuration file format remains compatible
- [x] Data source table in README updated with API details
- [x] Screen scraping code removed/replaced with API calls

### Technical Requirements:
- Use `yfinance` library for API access
- Symbol format: Standard ticker symbols (e.g., AAPL, MSFT, GOOGL)
- API method: `yf.Ticker(symbol).info['currentPrice']` or `regularMarketPrice`
- Handle API exceptions: HTTPError, JSONDecodeError, KeyError
- Implement retry logic for transient API failures
- No authentication required (public API)

### Dependencies:
- Requires yfinance library (to be added to requirements.txt)
- Depends on US-001 (Multi-Source Fund Price Scraping) architecture
- Depends on US-002 (Configuration-Based Fund Management) for source code support

### Notes:
- Yahoo Finance API is more reliable than screen scraping
- API provides structured JSON data
- No need for Playwright/browser automation for this source
- Symbol format is simpler (no exchange prefix needed for US stocks)
- API may have rate limits (typically generous for free tier)
- Consider caching to reduce API calls if needed

---

## US-026: Prevent Duplicate Price History Entries

**As** a data analyst  
**I want** the system to prevent duplicate price entries for the same fund on the same date  
**So that** I have clean historical data without redundant entries when running the scraper multiple times per day

### Acceptance Criteria:
- [x] System checks for existing entries with same fund ID and date before adding to history
- [x] If an entry exists for the same fund and date, it is updated (replaced) rather than duplicated
- [x] Latest price for a fund on a given date always reflects the most recent scrape
- [x] System handles both new entries and updates correctly
- [x] History file maintains chronological order
- [x] No duplicate entries exist for the same fund and date combination
- [x] Performance is acceptable even with large history files

### Definition of Done:
- [x] Duplicate prevention logic implemented in write_results()
- [x] Unit tests verify no duplicates are created
- [x] Unit tests verify existing entries are updated correctly
- [x] Functional tests confirm behavior with real data
- [x] Documentation updated with new behavior
- [x] All existing tests still pass
- [x] Code coverage maintained above 90%

### Technical Requirements:
- Read existing history file before writing
- Build in-memory map of (fund_id, date) -> row_index
- Update existing rows or append new rows as appropriate
- Write complete history back to file
- Handle edge cases: empty file, missing file, corrupted data
- Maintain CSV format compatibility

### Dependencies:
- Depends on US-004 (CSV Data Export) for history file structure
- No breaking changes to existing functionality

### Notes:
- This is a data quality improvement
- Prevents issues when running scraper multiple times per day
- Useful for testing and manual runs
- Does not affect latest_prices.csv (already overwrites)
- Consider performance with very large history files (thousands of entries)