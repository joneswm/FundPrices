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

## US-025: Google Finance Price Scraping

**As** a financial analyst  
**I want** to scrape fund prices from Google Finance  
**So that** I can access an additional reliable data source for fund pricing information

### Acceptance Criteria:
- [ ] System can scrape prices from Google Finance using fund symbols
- [ ] Google Finance source uses appropriate URL patterns and selectors
- [ ] System handles Google Finance-specific error cases gracefully
- [ ] Google Finance returns price data in consistent format with other sources
- [ ] Source code "GF" is supported in configuration file
- [ ] System validates Google Finance fund symbols before scraping
- [ ] Network timeouts and rate limiting are handled appropriately

### Definition of Done:
- [ ] Google Finance scraping implemented and tested
- [ ] Error handling for Google Finance source implemented
- [ ] Unit tests for Google Finance scraping pass
- [ ] Functional tests against real Google Finance website pass
- [ ] Documentation updated with Google Finance examples
- [ ] Configuration file format updated to include GF source code
- [ ] Data source table in README updated with Google Finance details

### Technical Requirements:
- URL pattern: `https://www.google.com/finance/quote/<symbol>`
- CSS selector for price element (to be determined during implementation)
- Support for various symbol formats (e.g., NASDAQ:AAPL, LON:IDTG)
- Handle Google Finance's dynamic content loading
- Implement appropriate wait conditions for price element visibility

### Dependencies:
- Requires Playwright for web scraping (already available)
- Depends on US-001 (Multi-Source Fund Price Scraping) architecture
- Depends on US-002 (Configuration-Based Fund Management) for source code support

### Notes:
- Google Finance may have different rate limiting policies than other sources
- Symbol format may vary by exchange (e.g., NASDAQ:AAPL vs LON:IDTG)
- Consider implementing retry logic for transient failures
- May need to handle cookie consent dialogs or regional variations