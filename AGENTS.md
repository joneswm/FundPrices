# FundPrices - Agent Guidelines

## Project Overview
Python application for scraping fund prices from multiple financial data sources (Financial Times, Yahoo Finance, Morningstar) and Yahoo Finance API for stock quotes.

## Task Tracking

**GitHub Issues is the single source of truth for work that needs doing.**

- Open work: https://github.com/joneswm/FundPrices/issues
- File new work as an issue — do **not** add to-do checkboxes to markdown files
- Reference the issue number in branches, commits and PRs (e.g. `Fixes #12`)
- Checkboxes remaining in `docs/` and `specs/` are either historical records of completed
  work, reusable process checklists, or template placeholders — none are open tasks

## Common Commands

### Testing
- `python test_scrape_fund_price.py` - Run full test suite (42 tests)
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
- `scrape_fund_price.py` - Main scraping logic (215 statements, 92% coverage)
- `test_scrape_fund_price.py` - Comprehensive test suite (462 statements, 98% coverage)
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
- Maintain code coverage above 90% overall; `constitution.md` additionally requires 95% for `scrape_fund_price.py`
- Write tests BEFORE implementation
- All tests must pass before committing

### Commit Messages
- Follow conventional commit format
- Include `Co-authored-by: Ona <no-reply@ona.com>` in commits
- Reference the GitHub issue number when applicable (e.g., "Fixes #12")
- Legacy commits reference user story IDs (e.g., "US-026"); these are historical
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
- Overall: 96% coverage
- Main code (scrape_fund_price.py): 92% coverage
- 42 total tests: 30 core unit tests + 7 historical-data tests + 5 functional tests

Run `make test-coverage` for current figures rather than relying on this snapshot.

## TDD Workflow (MANDATORY)

**IMPORTANT**: All development MUST follow this workflow:

1. **RED Phase**: Write failing test first
   - Commit with message prefix "RED:"
   
2. **GREEN Phase**: Write minimal code to pass test
   - Commit with message prefix "GREEN:"
   
3. **REFACTOR Phase**: Improve code while keeping tests green
   - Commit with message prefix "REFACTOR:"

See `docs/technical_documentation/tdd_workflow.md` for detailed guidelines.

## Spec Kit Integration

**Status**: Active for new features (Phase 1 complete)

### When to Use Spec Kit
- **New features** or major enhancements
- **Complex features** needing decomposition
- **AI-assisted development** requiring clear guidance
- **Features with multiple stakeholders**

### When to Use Traditional Approach
- **Bug fixes** and minor patches
- **Quick iterations** and small tweaks
- **Maintenance tasks**
- **Emergency hotfixes**

### Spec Kit Workflow
1. **SPECIFY**: Create `specs/XXX-feature-name/spec.md` defining what and why
2. **CLARIFY**: Resolve ambiguities (optional, document in spec)
3. **PLAN**: Create `plan.md` defining technical approach
4. **TASKS**: Create `tasks.md` breaking into small units
5. **IMPLEMENT**: Execute each task with TDD (RED-GREEN-REFACTOR)

### Commit Message Format
Reference spec ID in commits:
```
RED: Add test for Bloomberg scraper (SPEC-002)
GREEN: Implement Bloomberg scraper (SPEC-002)
REFACTOR: Extract common logic (SPEC-002)

Co-authored-by: Ona <no-reply@ona.com>
```

### Key Files
- `constitution.md` - Non-negotiable project principles
- `specs/README.md` - Specification index and guidelines
- `.specify/config.yaml` - Spec Kit configuration
- `.specify/templates/` - Spec, plan, and task templates

## User Stories (Legacy)

**Status**: 27/27 user stories complete (100%) - Archived after Spec Kit migration

**Historical Reference**: See `docs/user_stories/` for original requirements

When referencing legacy features:
1. Check `docs/user_stories/implementation_status.md` for completion status
2. Original user stories preserved for historical context
3. New features use Spec Kit format in `specs/` directory

## Dependencies

- `playwright` - Web scraping and browser automation
- `coverage` - Code coverage measurement
- `yfinance` - Yahoo Finance API for stock/fund prices and historical data

**Versions are defined in [`requirements.txt`](requirements.txt)** and kept current by Dependabot.
The list above names what each dependency is for; it deliberately omits version pins so it
cannot drift out of sync with the actual requirements.


## GitHub Actions

- **Test Workflow**: Runs on every push/PR
- **Scrape Workflow**: Scheduled daily at 22:00 UTC
- Both workflows automatically commit results

## Notes for Ona Agent

- This project has high test coverage (96% overall) - maintain it!
- Always run tests after making changes
- **Use Spec Kit workflow for new features** (SPECIFY → PLAN → TASKS → IMPLEMENT)
- **Follow TDD for all implementation** (RED-GREEN-REFACTOR mandatory)
- **Consult constitution.md** for non-negotiable principles
- Check `docs/user_stories/implementation_status.md` for historical project status
- Check `specs/README.md` for active specifications
- The codebase is well-documented - read existing code before making changes
- When creating specs, use templates in `.specify/templates/`
