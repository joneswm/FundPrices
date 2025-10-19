# FundPrices - Agent Guidelines

## Project Overview
Python application for scraping fund prices from multiple financial data sources (Financial Times, Yahoo Finance, Morningstar) and Yahoo Finance API for stock quotes.

## Common Commands

### Testing
- `python test_scrape_fund_price.py` - Run full test suite (26 tests)
- `python -m unittest test_scrape_fund_price.TestFundPriceScraper -v` - Run unit tests only
- `python -m coverage run test_scrape_fund_price.py && python -m coverage report` - Run with coverage report
- `./run_tests.sh` - Run tests with coverage (if script exists)

### Running the Scraper
- `python scrape_fund_price.py` - Run the fund price scraper once
- Results are saved to `data/latest_prices.csv` and `data/prices_history.csv`

### Code Quality
- `./format_code.sh` - Format code with Black and isort
- `make format` - Alternative formatting command
- `make test` - Run tests via Makefile
- `make validate` - Validate development environment

### Development Environment
- `./setup_dev_env.sh` - Set up development environment (Linux/Mac)
- `setup_dev_env.bat` - Set up development environment (Windows)
- `python validate_dev_env.py` - Validate environment setup

## Project Structure

### Key Files
- `scrape_fund_price.py` - Main scraping logic (90 statements, 99% coverage)
- `test_scrape_fund_price.py` - Comprehensive test suite (251 statements, 96% coverage)
- `funds.txt` - Configuration file for fund identifiers
- `requirements.txt` - Python dependencies

### Key Directories
- `data/` - Output directory for CSV files and price files (gitignored)
- `docs/` - Documentation including user stories and technical docs
- `.devcontainer/` - Dev Container configuration for Ona
- `.github/workflows/` - GitHub Actions for CI/CD

### Documentation
- `docs/user_stories/` - User stories organized by category
- `docs/technical_documentation/` - Technical documentation and guides
- `docs/user_stories/implementation_status.md` - **Track development progress here**

## Code Style and Conventions

### Python Style
- Follow PEP 8 guidelines
- Use Black formatter for code formatting
- Use isort for import sorting
- Maximum line length: 88 characters (Black default)
- Type hints encouraged but not required

### Testing Requirements
- **MANDATORY**: Follow Test-Driven Development (TDD) workflow
- **RED-GREEN-REFACTOR** cycle for all changes
- Maintain code coverage above 90% (currently at 97%)
- Write tests BEFORE implementation
- All tests must pass before committing

### Commit Messages
- Follow conventional commit format
- Include `Co-authored-by: Ona <no-reply@ona.com>` in commits
- Reference user story IDs when applicable (e.g., "US-026")
- Use prefixes: RED, GREEN, REFACTOR for TDD commits

## Configuration

### Fund Configuration Format
File: `funds.txt`
```
FT,GB00B1FXTF86    # Financial Times
YH,IDTG.L          # Yahoo Finance (web scraping)
MS,LU0196696453    # Morningstar
GF,AAPL            # Yahoo Finance API (for stocks)
```

**Source Codes:**
- `FT` - Financial Times (web scraping)
- `YH` - Yahoo Finance (web scraping)
- `MS` - Morningstar (web scraping)
- `GF` - Yahoo Finance API (uses yfinance library)

## Data Sources

| Source | Method | Status |
|--------|--------|--------|
| Financial Times | Web Scraping (Playwright) | ✅ Implemented |
| Yahoo Finance | Web Scraping (Playwright) | ✅ Implemented |
| Morningstar | Web Scraping (Playwright) | ✅ Implemented |
| Yahoo Finance API | API (yfinance) | ✅ Implemented |

## Important Implementation Details

### Duplicate Prevention
- History file prevents duplicates by filtering out today's entries before appending
- Multiple runs per day are safe - latest prices replace earlier ones
- Implementation: Simple date-based filtering (no complex dictionaries)

### Error Handling
- Failed scrapes return "Error: <message>" instead of crashing
- Invalid source codes return "N/A"
- System continues processing even if individual funds fail

### Test Coverage
- Overall: 97% coverage
- Main code (scrape_fund_price.py): 99% coverage
- 26 total tests: 22 unit tests + 4 functional tests

## TDD Workflow (MANDATORY)

**IMPORTANT**: All development MUST follow this workflow:

1. **RED Phase**: Write failing test first
   - Commit with message prefix "RED:"
   
2. **GREEN Phase**: Write minimal code to pass test
   - Commit with message prefix "GREEN:"
   
3. **REFACTOR Phase**: Improve code while keeping tests green
   - Commit with message prefix "REFACTOR:"

See `docs/technical_documentation/tdd_workflow.md` for detailed guidelines.

## User Stories

**Current Status**: 26/26 user stories complete (100%)

When implementing new features:
1. Create user story in `docs/user_stories/`
2. Update `docs/user_stories/implementation_status.md`
3. Follow TDD workflow
4. Update documentation when complete

## Dependencies

- `playwright>=1.35.0` - Web scraping and browser automation
- `coverage>=7.2.7` - Code coverage measurement
- `yfinance>=0.2.0` - Yahoo Finance API for stock/fund prices

## GitHub Actions

- **Test Workflow**: Runs on every push/PR
- **Scrape Workflow**: Scheduled daily at 22:00 UTC
- Both workflows automatically commit results

## Notes for Ona Agent

- This project has excellent test coverage (97%) - maintain it!
- Always run tests after making changes
- Use TDD workflow for all new features
- Check `docs/user_stories/implementation_status.md` for project status
- The codebase is well-documented - read existing code before making changes
