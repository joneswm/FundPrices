# FundPrices - Agent Guidelines

## Project Overview
Python application that collects dated fund, ETF and stock prices and end-of-day FX rates (Yahoo Finance API, Financial Times and investing.com over HTTP, with Playwright scraping as a fallback), stores them as CSV in this repository, and publishes a daily price-change summary.

## Task Tracking

**GitHub Issues is the single source of truth for work that needs doing.**

- Open work: https://github.com/joneswm/FundPrices/issues
- File new work as an issue — do **not** add to-do checkboxes to markdown files
- Reference the issue number in branches, commits and PRs (e.g. `Fixes #12`)
- Checkboxes remaining in `docs/` and `specs/` are either historical records of completed
  work, reusable process checklists, or template placeholders — none are open tasks

## Common Commands

### Testing
- `python test_scrape_fund_price.py` - Run full test suite
- `python -m unittest test_scrape_fund_price.TestFundPriceScraper -v` - Run unit tests only
- `python -m coverage run test_scrape_fund_price.py && python -m coverage report` - Run with coverage report
- `./run_tests.sh coverage` - Run tests with coverage

### Rebuilding History
- `python scrape_fund_price.py --backfill --from 2023-01-01` - rebuild stored history
  from source data. Manual only; also available as the **Rebuild Price History**
  workflow. Shares a concurrency group with the daily scrape so the two cannot push
  at the same time.

### Importing Closed Holdings
- `python scrape_fund_price.py --import-closed` - one-off import of the windows in
  `closed_holdings.txt`. Writes `prices_history.csv` and nothing else. Run locally and
  commit; there is deliberately no workflow for it.

### Running the Scraper
- `python scrape_fund_price.py` - Run the fund price scraper once
- Results are saved to `data/latest_prices.csv`, `data/prices_history.csv` and
  `data/prices_history_90_days.csv` (rolling 90-calendar-day window, currently priced
  funds only), plus one `data/latest_<identifier>.price` file per fund, the FX files
  `data/fx_history.csv` and `data/latest_fx.csv`, and `data/daily_summary.{csv,md}`

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
- `scrape_fund_price.py` - The whole application, in one module
- `test_scrape_fund_price.py` - Comprehensive test suite
- `funds.txt` - Instruments priced by the daily run
- `fx_pairs.txt` - FX pairs snapped by the daily run
- `closed_holdings.txt` - Instruments imported once and never fetched again
- `requirements.txt` - Python dependencies

### Key Directories
- `data/` - Output directory. Gitignored, but its files are **tracked**: stage new ones
  with `git add -f data/*.csv data/*.price data/*.md`. Because they are tracked, a plain
  `git add -A` stages data changes too, so stage code by filename when the two should
  land in separate commits
- `docs/` - Documentation including user stories and technical docs
- `.devcontainer/` - Dev Container configuration (VS Code / GitHub Codespaces)
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
- Maintain code coverage above 90% overall and 95% for `scrape_fund_price.py` (both enforced in CI)
- Write tests BEFORE implementation
- All tests must pass before committing

### Commit Messages
- Follow conventional commit format
- If an AI assistant contributed to a commit, include that assistant's `Co-authored-by:` trailer
- Reference the GitHub issue number when applicable (e.g., "Fixes #12")
- Legacy commits reference user story IDs (e.g., "US-026"); these are historical
- Use prefixes: RED, GREEN, REFACTOR for TDD commits

## Configuration

### Fund Configuration Format
File: `funds.txt`

Each line is `<source>,<lookup_id>[,<alias>[;<alias>...]]`. Blank lines, full-line
`#` comments and trailing comments are ignored.

```
FT,GB00B1FXTF86             # Financial Times (dated HTTP endpoint)
YA,AAPL                     # Yahoo Finance API
YA,0P00000YAN,JFM0003373    # fetched as 0P00000YAN, published as both
```

**Source Codes:**
- `FT` - Financial Times (dated HTTP endpoint; falls back to scraping)
- `YA` - **Yahoo Finance API** via yfinance daily bars. Used by 20 of 26 instruments
- `IV` - investing.com (undocumented HTTP endpoint). Used only by closed holdings, for
  funds Yahoo and FT no longer price; never put it on a schedule
- `GF` - deprecated spelling of `YA`; still accepted, warns, and names the line
- `YH` - Yahoo Finance (web scraping). Undated, so prefer `YA`. Currently unused
- `MS` - Morningstar (web scraping). Supported but unused: the one fund that
  needed it now comes from Yahoo

**Identifier aliases**: the optional third field lists extra identifiers to publish
under, separated by `;`. The price is fetched **once** using the second field and
written under every identifier, so a fund can move to a better source without
stranding history recorded under its old identifier.

Configuration is validated before any network call. A malformed line, an empty or
self-referencing alias, or an identifier repeated anywhere in the file raises an
error naming the line.

## Closed Holdings

File: `closed_holdings.txt`, one line per instrument:
`<identifier>,<source>,<lookup_id>,<currency>,<start>,<end>` (dates inclusive).

Instruments held once and no longer priced. The file is separate from `funds.txt`
precisely so the daily run cannot reach them. The import asserts the configured currency
against what the source reports and skips the holding on a mismatch, which is how a
lookup that resolved to the wrong listing gets caught. Imported rows live only in
`prices_history.csv`; a rebuild preserves them and never promotes them into
`latest_prices.csv`, the rolling window or the `.price` files.

Before adding one, check the candidate source the hard way: Yahoo can repeat a close
with zero volume across a ticker change, FT's ISIN lookup can pick a different listing,
and FT prices LSE-listed ETFs on UK bank holidays. `closed_holdings.txt` records the
evidence for each choice.

## Daily Summary

Each run writes a summary of what moved, as both
[`data/daily_summary.md`](data/daily_summary.md) for reading and
`data/daily_summary.csv` for machines. The same table appears on the Actions run page.

Each instrument is compared with its **previous distinct price date**, not with
yesterday: funds, LSE, US and HK instruments keep different calendars, and fund NAVs
arrive a day later than exchange prices. A Friday-to-Monday move is therefore a real
comparison rather than a flat day.

Instruments with no recent price are marked stale (`~`) and those that could not be
fetched are marked `!`, so neither is mistaken for a 0% day. Percent changes are
unit-independent, so `GBp` and `GBP` instruments are directly comparable; absolute
deltas are in each instrument's own currency.

## FX Rates

`fx_pairs.txt` lists the exchange rates to snap, one six-letter pair per line:

```
NZDGBP
SGDGBP
USDGBP
HKDGBP
```

**Direction**: rates are **GBP per 1 unit of the foreign currency**. `USDGBP` is about
0.75, meaning one dollar buys 0.75 pounds. This is the inverse of the market convention
`GBP/USD` (about 1.34), and the pairs file rejects the slash spelling so the two cannot
be confused. Rates are stored at 6 decimal places, which `HKDGBP` (about 0.0951) needs.

Output: `data/fx_history.csv` and `data/latest_fx.csv`, both `Pair,Date,Rate`.

FX trades continuously, so the current day's bar is provisional and is replaced by the
final value on the next run. Weekend bars are never stored.

## Data Sources

| Source | Method | Status |
|--------|--------|--------|
| Yahoo Finance API (`YA`) | yfinance daily bars | 20 funds, 5 closed holdings |
| Financial Times (`FT`) | Dated HTTP endpoint; Playwright fallback | 6 funds, 1 closed holding |
| investing.com (`IV`) | Dated HTTP endpoint | 2 closed holdings |
| Yahoo Finance (`YH`) | Web Scraping (Playwright) | Supported, unused |
| Morningstar (`MS`) | Web Scraping (Playwright) | Supported, unused |

## Important Implementation Details

### Duplicate Prevention
- History is keyed on `(Fund, Date)`, where the date is the one the **source** reports
- An incoming row replaces the stored row with the same key, so corrections apply and
  re-runs cannot duplicate
- Rows are sorted by date then fund and written with LF endings on every platform, so
  repeated runs are byte-identical

### Error Handling
- A failed fetch is reported on `ScrapeResults.failures`; it never crashes the run and
  no error text is ever written to a data file
- An unsupported source code is a failure for that fund like any other
- System continues processing even if individual funds fail, writes everything it
  obtained, and only then exits non-zero

### Retries and Last Known Price
- Every fetch is retried up to `MAX_PRICE_ATTEMPTS` (3) via `fetch_with_retries()`
- After exhausting retries, `read_last_known_row()` supplies the fund's most recent stored
  row, which is carried into `latest_prices.csv` under its original date
  (`ScrapeResults.carried`). No row is invented for today
- A fund with no stored history simply has no row; nothing is recorded as "N/A"
- `ScrapeResults.failures` lists the funds that fell back
- **This already exists - do not reimplement retry logic**

### Test Coverage
- Overall: 99% coverage
- Main code (scrape_fund_price.py): 97% coverage (constitution requires >=95%, enforced in CI)
- Unit tests use mocks only and run in seconds; functional tests hit live sources and
  skip when a source is down

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

- `yfinance` - Yahoo Finance API for prices, FX rates and historical data
- `requests` - FT and investing.com HTTP endpoints
- `numpy` - float32 round-tripping, so prices are stored exactly as quoted
- `playwright` - Scraping fallback and browser automation
- `coverage` - Code coverage measurement

**Versions are defined in [`requirements.txt`](requirements.txt)** and kept current by Dependabot.
The list above names what each dependency is for; it deliberately omits version pins so it
cannot drift out of sync with the actual requirements.


## GitHub Actions

- **Test Workflow** (`test.yml`): Runs on every push/PR across Python 3.10, 3.12 and
  3.14 with both coverage gates. Commits nothing
- **Scrape Workflow** (`scrape.yml`): Scheduled daily at 22:30 UTC, after the US close
  all year round. Commits its results even when some funds failed
- **Rebuild Workflow** (`backfill.yml`): Manual only. Shares a concurrency group with
  the scrape so the two cannot push at once

## Notes for AI Agents

- This project has high test coverage (99% overall) - maintain it!
- Always run tests after making changes
- **Use Spec Kit workflow for new features** (SPECIFY → PLAN → TASKS → IMPLEMENT)
- **Follow TDD for all implementation** (RED-GREEN-REFACTOR mandatory)
- **Consult constitution.md** for non-negotiable principles
- Check `docs/user_stories/implementation_status.md` for historical project status
- Check `specs/README.md` for active specifications
- The codebase is well-documented - read existing code before making changes
- When creating specs, use templates in `.specify/templates/`
