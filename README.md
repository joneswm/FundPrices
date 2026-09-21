# FundPrices

A Python application that collects dated fund, ETF and stock prices and end-of-day FX rates from several sources, stores them as CSV in this repository, and publishes a daily summary of what moved.

## Features

- **Multi-source support**: Yahoo Finance API, the Financial Times and investing.com over plain HTTP, with Playwright scraping (Yahoo, Morningstar) kept as a fallback
- **True price dates and currencies**: every row carries the date and currency the source reports, so weekends and holidays are absent rather than repeated
- **FX rates**: end-of-day rates for a configured set of currency pairs
- **Daily summary**: new price, old price, delta and percent delta for every instrument
- **History rebuild**: stored history can be rebuilt from the sources back to any date
- **Closed holdings**: one-off imports for instruments no longer held, kept out of the daily run
- **Identifier aliases**: one fetch published under several identifiers
- **Historical data retrieval**: ad-hoc OHLCV export for any Yahoo symbol and date range
- **Automated execution**: a scheduled GitHub Actions workflow collects and commits the data
- **Resilience**: retries, then the last known price; one failure never stops the run
- **Testing**: unit and functional test suite with both coverage gates enforced in CI

## Quick Start

### Using the Dev Container

The repository includes a standard [Dev Container](https://containers.dev/) (`.devcontainer/`),
which works with VS Code ("Reopen in Container") and GitHub Codespaces. It will automatically:
- Set up Python 3.12 environment
- Install all dependencies from requirements.txt
- Install Playwright with Chromium browser
- Configure VS Code with Python extensions

### Manual Setup

#### Prerequisites
- Python 3.10 or higher (CI tests 3.10, 3.12 and 3.14)
- Internet connection

#### Installation
```bash
# Clone repository
git clone https://github.com/joneswm/FundPrices.git
cd FundPrices

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### Configuration
Create or edit `funds.txt`. Each line is `<source>,<lookup_id>[,<alias>[;<alias>...]]`.
Blank lines and `#` comments are ignored.
```
FT,GB00B1FXTF86             # Financial Times
YA,AAPL                     # Yahoo Finance API
YA,0P00000YAN,JFM0003373    # fetched once, published under both identifiers
```

**Identifier aliases**: the optional third field lists extra identifiers to publish
the same price under, separated by `;`. The price is fetched **once** using the
second field. This lets a fund change source without breaking anything keyed on its
old identifier: its history simply continues under both.

The configuration is validated before any network call, so a malformed line, an
empty or self-referencing alias, or an identifier repeated anywhere in the file
fails immediately with the line number.

**Note**: `YA` uses the Yahoo Finance API and takes that service's own ticker
symbols (e.g. `AAPL`, `IDTG.L`, `0P00000YAN`). The older code `GF` still works and
warns; it dated from a brief spell using Google Finance.

### Closed Holdings

Instruments that were held once and are no longer priced daily live in
`closed_holdings.txt`, deliberately apart from `funds.txt`. Each line is
`<identifier>,<source>,<lookup_id>,<currency>,<start>,<end>`.

```
BKCH,YA,BKCH.L,USD,2023-01-03,2024-02-16
BMV7ZZ3,FT,SEAL:LSE:GBX,GBX,2024-03-21,2024-10-25
```

The daily scrape reads only `funds.txt`, so nothing here is ever fetched on a
schedule. The windows are imported once:

```bash
python scrape_fund_price.py --import-closed
```

The import writes `prices_history.csv` and nothing else. `latest_prices.csv`, the
90-day window and the `.price` files all answer "what is this worth now", and a
fund that stopped trading has no answer; writing one would churn against the next
daily run. A rebuild leaves these rows alone, because `--backfill` only touches
the identifiers it is given.

`identifier` is what the history is published under and `lookup_id` is what the
source is asked for. The two differ when a SEDOL outlives the ticker its fund
traded under: `BMV7ZZ3` is one HANetf sub-fund that has traded under three names.

`currency` is asserted against what the source reports, so a lookup that resolves
to a different listing fails loudly instead of importing a full window of
plausible wrong prices. That check exists because FT's ISIN lookup silently
redirected one of these funds to its German EUR line and returned 288 quotes for
a holding priced in USD.

The end date is inclusive for every source. Yahoo's daily bars treat it as
exclusive, so the import asks for one day more and clips the result.

### Usage

#### Rebuild History (Backfill)

Rebuild stored history from source data, e.g. after changing a fund's source:

```bash
python scrape_fund_price.py --backfill --from 2023-01-01
```

This replaces stored rows from that date onward with what the sources report, and
prints a reconciliation report. It can also be run from the Actions tab via the
**Rebuild Price History** workflow. It is manual only and never scheduled.

Rows the sources omit are kept if they were themselves source-derived, so an
intermittent gap in a source cannot delete real trading days.

#### Normal Mode (Scrape Current Prices)
```bash
# Run once to scrape current prices from configured funds
python scrape_fund_price.py

# Run tests
python test_scrape_fund_price.py
```

#### Price Resilience

If a source fails, the scraper does not write an error into your price files. Each fund is
retried up to 3 times (`MAX_PRICE_ATTEMPTS`), and if every attempt fails its most recent
stored row is carried into `latest_prices.csv` under the date that price really belongs to.
No row is invented for today, and a fund with no stored history simply has no row. Funds
that fell back are listed on the returned results' `.failures`, marked `!` in the daily
summary, and turn the Actions run red once everything else has been written.

### Historical Data Mode
```bash
# Get historical data for a specific date range
python scrape_fund_price.py --history AAPL --start 2024-01-01 --end 2024-12-31

# Get historical data from start date to today
python scrape_fund_price.py --history MSFT --start 2024-11-01

# View help for all options
python scrape_fund_price.py --help
```

### Daily Summary

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

### FX Rates

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

| Source | Code | Method | Example | Status |
|--------|------|--------|---------|--------|
| Yahoo Finance API | YA | API (yfinance) | `yf.Ticker("AAPL").history(...)` daily bars | 20 funds + 5 closed holdings |
| Financial Times | FT | HTTP endpoint, scraping fallback | `https://markets.ft.com/data/funds/tearsheet/historical?s=GB00B1FXTF86` | 6 funds + 1 closed holding |
| investing.com | IV | HTTP endpoint (undocumented) | `https://api.investing.com/api/financialdata/historical/1182866` | 2 closed holdings |
| Yahoo Finance | YH | Web Scraping | `https://sg.finance.yahoo.com/quote/IDTG.L/` | supported, unused |
| Morningstar | MS | Web Scraping | `https://asialt.morningstar.com/DSB/QuickTake/overview.aspx?code=LU0196696453` | supported, unused |

`IV` exists for two closed funds that Yahoo and FT no longer price. Like the FT historical route it is an undocumented endpoint, so it is
used only for one-off imports and never on a schedule.

## Output Files

The application creates the following files in the `data/` directory:

### Normal Mode
- `latest_prices.csv`: Most recent prices for each fund (overwritten each run)
- `prices_history.csv`: Complete historical price data, including closed
  holdings imported once from `closed_holdings.txt`
- `prices_history_90_days.csv`: Rolling window of the most recent 90 calendar days
  for the funds currently being priced, derived from the full history on every run.
  A closed holding can have real prices inside that window without being priced now,
  so it is excluded, as it is from `latest_prices.csv`
- `fx_history.csv`: Exchange rates, GBP per 1 unit of the foreign currency
- `latest_fx.csv`: Most recent rate per currency pair
- `latest_<identifier>.price`: Individual price files for each fund

### Historical Data Mode
- `history_<SYMBOL>_<START>_<END>.csv`: Historical OHLCV data for the specified date range

### CSV Formats

**Normal Mode (latest_prices.csv)**:
```csv
Fund,Date,Price,Currency
GB00B1FXTF86,2026-09-18,7.15,GBP
SGLN.L,2026-09-18,6317,GBp
```

`Date` is the date the **source** reports the price for, not the date it was
collected. No row is written for a day a source publishes no price, so weekends and
holidays are absent rather than repeating the previous close.

`Currency` is recorded exactly as the source quotes it. `GBp` (pence) and `GBP`
(pounds) are both used by LSE-listed instruments and are deliberately kept distinct;
prices are stored as quoted and are never converted.

**Historical Mode (history_AAPL_2024-01-01_2024-12-31.csv)**:
```csv
Date,Open,High,Low,Close,Volume,Dividends,Stock Splits
2024-01-02,185.58,186.86,182.35,184.08,82488700,0.0,0.0
2024-01-03,182.67,184.32,181.89,182.70,58414500,0.0,0.0
```

## Automation

### GitHub Actions
The project includes automated execution via GitHub Actions:

- **Schedule**: daily at 22:30 UTC, after the US close all year round (`30 22 * * *` in `scrape.yml`)
- **Manual triggers**: Run on-demand from GitHub Actions tab
- **Output**: Automatically commits results to the repository

### Local Automation
```bash
# Add to crontab for a daily run at 22:30 UTC. Prices are end-of-day, so running
# more often fetches the same rows again.
30 22 * * * cd /path/to/FundPrices && python scrape_fund_price.py
```

## Documentation

### Core Documentation
- [Constitution](constitution.md) - **Project principles and standards**
- [**GitHub Issues**](https://github.com/joneswm/FundPrices/issues) - **Task tracking (source of truth for work to be done)**
- [Specifications](specs/README.md) - **Spec Kit specifications for features (primary development approach)**
- [Implementation Status](docs/user_stories/implementation_status.md) - Historical record of completed work

### Technical Documentation
- [Technical Documentation](docs/technical_documentation/README.md)
- [API Reference](docs/technical_documentation/api_reference.md)
- [Architecture](docs/technical_documentation/architecture.md)
- [Deployment Guide](docs/technical_documentation/deployment.md)
- [Troubleshooting](docs/technical_documentation/troubleshooting.md)

### Development Guides
- [Development Guide](docs/technical_documentation/development_guide.md)
- [TDD Workflow](docs/technical_documentation/tdd_workflow.md) - **🚨 MANDATORY**
- [IDE Setup Guide](docs/technical_documentation/ide_setup.md)
- [Development Tools Config](docs/technical_documentation/dev_tools_config.md)

### Historical Reference
- [Archived User Stories](docs/archive/user_stories/README.md) - **Legacy user stories (100% complete)**
- [Spec Kit Assessment](docs/archive/spec_kit_assessment.md) - **Archived: why Spec Kit was adopted**

## Development Status

**Current Implementation**: 100% Complete (27/27 legacy user stories, archived)  
**Spec Kit Migration**: ✅ Complete — Spec Kit is the primary development approach  
**Task Tracking**: [GitHub Issues](https://github.com/joneswm/FundPrices/issues)  
**New Features**: Open an issue, then create a spec in `specs/XXX-feature-name/`

- ✅ **Core Functionality**: Multi-source dated price collection (Yahoo Finance API, FT and investing.com over HTTP; scraping fallback), FX rates, daily summary, history rebuild, closed-holding imports
- ✅ **Historical Data**: Retrieve historical price data for any stock/fund over custom date ranges
- ✅ **Data Quality**: Duplicate prevention in price history
- ✅ **Automation**: GitHub Actions workflows, automated data persistence
- ✅ **Testing**: Comprehensive unit and functional tests; coverage gates of 90% overall and 95% on the main module enforced in CI
- ✅ **IDE Integration**: VS Code/Cursor test integration with debugging support
- ✅ **TDD Enforcement**: Mandatory Test-Driven Development workflow
- ✅ **Code Quality**: Standards, tools, and quality gates implemented
- ✅ **Development Environment**: Complete setup scripts and validation tools

**🎉 All User Stories Complete - Production Ready!**

Current and planned work is tracked in [GitHub Issues](https://github.com/joneswm/FundPrices/issues).
See [Implementation Status](docs/user_stories/implementation_status.md) for the historical record of completed work.

## Testing

Run the complete test suite:
```bash
python test_scrape_fund_price.py
```

The test suite includes:
- Unit tests for all functions
- Integration tests with real fund data
- Error handling and edge case testing
- Mock testing for external dependencies

## Dependencies

- `yfinance`: Yahoo Finance API for prices, FX rates and historical data
- `requests`: FT and investing.com HTTP endpoints
- `numpy`: float32 round-tripping, so prices are stored exactly as quoted
- `playwright`: Scraping fallback and browser automation
- `coverage`: Code coverage measurement

**Versions are defined in [`requirements.txt`](requirements.txt)** and kept current by Dependabot.
The list above names what each dependency is for; it deliberately omits version pins so it
cannot drift out of sync with the actual requirements.


## Development Environment

- **Dev Container**: Python 3.12 environment with automatic dependency installation
- **AGENTS.md**: Project-specific guidelines for AI coding agents
- **TDD Workflow**: Enforced test-driven development process

### AI Agent Guidelines

AI coding agents should read `AGENTS.md` for project-specific instructions including:
- Common commands and testing procedures
- Project structure and key files
- Code style and TDD requirements
- Configuration formats and data sources

## Contributing

**🚨 MANDATORY: All contributions MUST follow Test-Driven Development (TDD)**

The maintainer commits directly to `main` (see the [constitution](constitution.md),
section 7). Everyone else:

1. Fork the repository
2. Create a feature branch
3. **Follow TDD workflow**: RED-GREEN-REFACTOR cycle
4. Write tests first, then implementation
5. Ensure all tests pass and coverage >90%
6. Update documentation
7. Submit a pull request

### TDD Requirements
- **RED Phase**: Write failing test first
- **GREEN Phase**: Write minimal code to pass test
- **REFACTOR Phase**: Improve code while keeping tests green
- **No exceptions**: TDD is mandatory for all development

See [TDD Workflow](docs/technical_documentation/tdd_workflow.md) and [Development Guide](docs/technical_documentation/development_guide.md) for detailed guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For issues and questions:
- Check the [Troubleshooting Guide](docs/technical_documentation/troubleshooting.md)
- Open an issue on GitHub
- Review existing issues and discussions