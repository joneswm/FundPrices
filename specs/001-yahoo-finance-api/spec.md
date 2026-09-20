# SPEC-001: Yahoo Finance API Integration

> ## 📌 Task tracking has moved to GitHub Issues
>
> The acceptance criteria below were migrated to GitHub Issues and **closed as completed** —
> see [all SPEC-001 issues](https://github.com/joneswm/FundPrices/issues?q=is%3Aissue+label%3Aspec-001).
>
> The checkboxes were historically left unticked because this spec was written *retrospectively*,
> after the feature had already shipped. They are ticked below to reflect reality.
> New work belongs in [GitHub Issues](https://github.com/joneswm/FundPrices/issues), not in this file.

**Status**: ✅ Complete  
**Created**: 2024-11-20 (Retrospective)  
**Implemented**: 2024 (as US-025)  
**Type**: Feature Enhancement

---

## Context

Google Finance web scraping was proving unreliable due to frequent selector changes and website structure updates. The project needed a more stable data source for stock and fund prices that wouldn't break with website redesigns.

## User Need

**As** a financial analyst  
**I want** reliable stock and fund price data  
**So that** I can trust my price history without frequent scraping failures

**As** a system maintainer  
**I want** a stable API instead of web scraping  
**So that** I don't have to constantly update selectors when websites change

## Problem Statement

Web scraping Google Finance (GF source) has several issues:
1. **Fragility**: CSS selectors break when Google updates their website
2. **Maintenance**: Requires constant monitoring and updates
3. **Reliability**: Scraping failures cause data gaps
4. **Performance**: Browser automation is slower than API calls
5. **Rate Limiting**: Risk of being blocked by Google

## Proposed Solution

Replace Google Finance web scraping with Yahoo Finance API integration using the `yfinance` library, which provides:
- Official API access to Yahoo Finance data
- Structured JSON responses
- Better error handling
- Faster execution (no browser needed)
- More reliable data access

## Success Criteria

### Functional Requirements
- ✅ Fetch stock/fund prices via API (not web scraping)
- ✅ Support same symbols as Google Finance (e.g., AAPL, MSFT, GOOGL)
- ✅ Handle API errors gracefully with clear error messages
- ✅ Return prices in same format as other sources
- ✅ Maintain backwards compatibility with existing `funds.txt` format

### Non-Functional Requirements
- ✅ Maintain 90%+ test coverage
- ✅ No performance degradation compared to web scraping
- ✅ API calls complete within 30 seconds
- ✅ Clear error messages for invalid symbols
- ✅ Proper timeout handling

### Quality Requirements
- ✅ Comprehensive unit tests with mocked API responses
- ✅ Functional test with real API call
- ✅ Error handling for all failure scenarios
- ✅ Documentation updated

## Out of Scope

The following are explicitly **not** included in this specification:
- Historical data retrieval (separate spec: SPEC-027)
- Real-time streaming prices
- Multiple API providers (only Yahoo Finance)
- Cryptocurrency prices
- Options or derivatives data
- Portfolio tracking features

## Acceptance Criteria

1. **API Integration**
   - [x] `yfinance` library added to `requirements.txt`
   - [x] New `fetch_price_api()` function created
   - [x] Function accepts symbol as parameter
   - [x] Function returns price as string or error message

2. **Source Routing**
   - [x] `scrape_funds()` routes GF source to API instead of scraping
   - [x] Other sources (FT, YH, MS) continue using web scraping
   - [x] No breaking changes to existing functionality

3. **Error Handling**
   - [x] Invalid symbols return `"Error: Invalid symbol"`
   - [x] API failures return `"Error: API unavailable"`
   - [x] Network timeouts handled (30 second limit)
   - [x] All errors logged appropriately

4. **Testing**
   - [x] Unit test: Valid symbol returns price
   - [x] Unit test: Invalid symbol returns error
   - [x] Unit test: Mocked API responses
   - [x] Functional test: Real API call succeeds
   - [x] Coverage maintained at 90%+

5. **Documentation**
   - [x] README updated with GF source explanation
   - [x] AGENTS.md updated with API approach
   - [x] `implementation_status.md` updated
   - [x] Code comments explain API usage

## Stakeholders

- **Primary**: Financial analysts using the tool
- **Secondary**: System maintainers
- **Tertiary**: Future contributors

## Dependencies

- `yfinance>=0.2.0` library
- Internet connectivity for API access
- Yahoo Finance API availability

## Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Yahoo Finance API changes | High | Medium | Use official library that handles API changes |
| API rate limiting | Medium | Low | Implement reasonable delays, respect limits |
| API downtime | Medium | Low | Return clear error, system continues with other sources |
| Symbol format differences | Low | Medium | Document symbol format, provide examples |

## Assumptions

- Yahoo Finance API will remain free for basic price data
- `yfinance` library will be maintained
- Symbol formats are compatible between Google and Yahoo Finance
- API response time is acceptable (< 5 seconds per symbol)

## Constraints

- Must maintain backwards compatibility with existing `funds.txt` format
- Must not break existing web scraping for FT, YH, MS sources
- Must follow TDD workflow (RED-GREEN-REFACTOR)
- Must maintain 90%+ test coverage

## Timeline

**Retrospective Note**: This feature was implemented in 2024 as US-025.

- Specification: 1 hour
- Planning: 1 hour
- Implementation: 4 hours
- Testing: 2 hours
- Documentation: 1 hour
- **Total**: ~9 hours

## Related Specifications

- **SPEC-027**: Historical Price Data Retrieval (extends this spec)
- **US-025**: Original user story (legacy format)

## Notes

This is a **retrospective specification** created during the Spec Kit migration. The feature was originally implemented as US-025 using traditional user story format. This spec documents what was built to serve as an example for future specifications.

## References

- [yfinance Documentation](https://pypi.org/project/yfinance/)
- [Yahoo Finance](https://finance.yahoo.com/)
- [Original User Story: US-025](../../docs/user_stories/implementation_status.md#us-025)
