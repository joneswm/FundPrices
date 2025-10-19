# FundPrices

A Python application for scraping fund prices from multiple financial data sources using Playwright for web automation.

## Features

- **Multi-source support**: Scrapes prices from Financial Times, Yahoo Finance (web + API), Morningstar, and uses Yahoo Finance API for stock quotes
- **Hybrid approach**: Web scraping for funds, API for stocks (faster and more reliable)
- **Automated execution**: GitHub Actions workflow for scheduled price collection
- **Data persistence**: Stores latest prices and historical data in CSV format
- **Robust error handling**: Comprehensive error handling and retry logic
- **Testing**: Full test suite with 26 test cases (97% code coverage)

## Quick Start

### Using Ona (Recommended)

Open this project in Ona for instant setup:

[![Open in Ona](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/joneswm/FundPrices)

The Dev Container will automatically:
- Set up Python 3.12 environment
- Install all dependencies from requirements.txt
- Install Playwright with Chromium browser
- Configure VS Code with Python extensions

### Manual Setup

#### Prerequisites
- Python 3.7 or higher
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
Create or edit `funds.txt` with your fund identifiers:
```
FT,GB00B1FXTF86
YH,IDTG.L
MS,LU0196696453
GF,AAPL
```

**Note**: GF (Google Finance) source uses Yahoo Finance API and requires standard ticker symbols (e.g., AAPL, MSFT, GOOGL) without exchange prefixes.

### Usage
```bash
# Run once
python scrape_fund_price.py

# Run tests
python test_scrape_fund_price.py
```

## Data Sources

| Source | Code | Method | Example | Status |
|--------|------|--------|---------|--------|
| Financial Times | FT | Web Scraping | `https://markets.ft.com/data/funds/tearsheet/summary?s=GB00B1FXTF86` | ✅ Implemented |
| Yahoo Finance | YH | Web Scraping | `https://sg.finance.yahoo.com/quote/IDTG.L/` | ✅ Implemented |
| Morningstar | MS | Web Scraping | `https://asialt.morningstar.com/DSB/QuickTake/overview.aspx?code=LU0196696453` | ✅ Implemented |
| Yahoo Finance API | GF | API (yfinance) | `yf.Ticker("AAPL").info['currentPrice']` | ✅ Implemented |

## Output Files

The application creates the following files in the `data/` directory:

- `latest_prices.csv`: Most recent prices for each fund
- `prices_history.csv`: Historical price data with timestamps

### CSV Format
```csv
source,fund_id,price,timestamp,status
FT,GB00B1FXTF86,1.2345,2024-01-15 10:30:00,success
YH,IDTG.L,2.5678,2024-01-15 10:30:01,success
```

## Automation

### GitHub Actions
The project includes automated execution via GitHub Actions:

- **Schedule**: Configurable cron expression (default: daily at 9 AM UTC)
- **Manual triggers**: Run on-demand from GitHub Actions tab
- **Output**: Automatically commits results to the repository

### Local Automation
```bash
# Add to crontab for hourly execution
0 * * * * cd /path/to/FundPrices && python scrape_fund_price.py
```

## Documentation

- [Technical Documentation](docs/technical_documentation/README.md)
- [User Stories](docs/user_stories/README.md)
- [Implementation Status](docs/user_stories/implementation_status.md) - **Track development progress**
- [API Reference](docs/technical_documentation/api_reference.md)
- [Deployment Guide](docs/technical_documentation/deployment.md)
- [Troubleshooting](docs/technical_documentation/troubleshooting.md)
- [Development Guide](docs/technical_documentation/development_guide.md)
- [TDD Workflow](docs/technical_documentation/tdd_workflow.md) - **🚨 MANDATORY**
- [TDD Templates](docs/technical_documentation/tdd_templates.md)
- [IDE Setup Guide](docs/technical_documentation/ide_setup.md)
- [Development Tools Config](docs/technical_documentation/dev_tools_config.md)

## Development Status

**Current Implementation**: 100% Complete (26/26 user stories)

- ✅ **Core Functionality**: Multi-source data collection (FT, Yahoo, Morningstar via scraping; Yahoo Finance API for stocks), configuration management, data export
- ✅ **Data Quality**: Duplicate prevention in price history
- ✅ **Automation**: GitHub Actions workflows, automated data persistence
- ✅ **Testing**: Comprehensive unit and functional tests with 97% coverage (99% for main code)
- ✅ **IDE Integration**: VS Code/Cursor test integration with debugging support
- ✅ **TDD Enforcement**: Mandatory Test-Driven Development workflow
- ✅ **Code Quality**: Standards, tools, and quality gates implemented
- ✅ **Development Environment**: Complete setup scripts and validation tools

**🎉 All User Stories Complete - Production Ready!**

See [Implementation Status](docs/user_stories/implementation_status.md) for detailed progress tracking.

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

- `playwright>=1.35.0`: Web scraping and browser automation
- `coverage>=7.2.7`: Code coverage measurement
- `yfinance>=0.2.0`: Yahoo Finance API for stock/fund prices

## Development with Ona

This project is optimized for [Ona](https://www.gitpod.io/ona) (formerly Gitpod):

- **AGENTS.md**: Project-specific guidelines automatically loaded by Ona Agent
- **Dev Container**: Python 3.12 environment with automatic dependency installation
- **VS Code Tasks**: Quick access to common commands (Run Tests, Format Code, etc.)
- **TDD Workflow**: Enforced test-driven development process

### Ona Agent Guidelines

Ona Agent automatically reads `AGENTS.md` for project-specific instructions including:
- Common commands and testing procedures
- Project structure and key files
- Code style and TDD requirements
- Configuration formats and data sources

## Contributing

**🚨 MANDATORY: All contributions MUST follow Test-Driven Development (TDD)**

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