# Development Guide

This document provides guidelines for developers working on the Fund Price Scraping project.

## 🚨 MANDATORY: Test-Driven Development (TDD)

**ALL development MUST follow strict Test-Driven Development practices.**

### TDD Rules (NON-NEGOTIABLE)

1. **RED-GREEN-REFACTOR CYCLE**: Every feature MUST follow this exact sequence:
   - 🔴 **RED**: Write a failing test first
   - 🟢 **GREEN**: Write minimal code to make the test pass
   - 🔵 **REFACTOR**: Improve code while keeping tests green

2. **NO CODE WITHOUT TESTS**: Never write production code without a corresponding test
3. **TEST FIRST**: Always write the test before implementing the feature
4. **FAILING TESTS**: Tests must fail initially (proving they test something real)
5. **MINIMAL IMPLEMENTATION**: Write only the code needed to make tests pass
6. **CONTINUOUS TESTING**: Run tests after every small change

### TDD Workflow Enforcement

**Before writing ANY code:**
1. Write a failing test that describes the desired behavior
2. Run the test to confirm it fails (RED)
3. Write the minimal code to make the test pass (GREEN)
4. Run tests to confirm they pass
5. Refactor the code while keeping tests green (REFACTOR)
6. Repeat for the next feature

**Violation of TDD rules will result in code rejection.**

### TDD Best Practices

#### Test Writing Guidelines
- **Descriptive Names**: Test names should clearly describe what is being tested
- **Single Responsibility**: Each test should verify one specific behavior
- **Arrange-Act-Assert**: Structure tests with clear setup, execution, and verification
- **Edge Cases**: Test boundary conditions, error cases, and edge scenarios
- **Mock External Dependencies**: Use mocks for network calls, file operations, etc.

#### Code Quality Standards
- **Minimal Implementation**: Write only code needed to pass tests
- **Clean Code**: Follow PEP 8 and project formatting standards
- **Refactoring**: Continuously improve code structure while maintaining test coverage
- **Documentation**: Update docstrings and comments as code evolves

#### TDD Examples

**Example 1: Adding a New Fund Source**
```python
# 1. RED: Write failing test first
def test_get_source_config_bloomberg(self):
    """Test Bloomberg source configuration."""
    url, selector = get_source_config("BB", "TEST123")
    expected_url = "https://www.bloomberg.com/quote/TEST123"
    expected_selector = ".priceText__1853e8a5"
    self.assertEqual(url, expected_url)
    self.assertEqual(selector, expected_selector)

# 2. GREEN: Write minimal implementation
def get_source_config(source, fund_id):
    # ... existing code ...
    elif source.upper() == "BB":
        url = f"https://www.bloomberg.com/quote/{fund_id}"
        selector = ".priceText__1853e8a5"
    # ... rest of function ...

# 3. REFACTOR: Improve while keeping tests green
# Add error handling, improve readability, etc.
```

**Example 2: Adding New Data Field**
```python
# 1. RED: Write failing test
def test_scrape_funds_includes_fund_name(self):
    """Test that scraped results include fund name."""
    funds = [("FT", "GB00B1FXTF86")]
    results = scrape_funds(funds, data_dir=self.test_dir)
    
    self.assertEqual(len(results), 1)
    self.assertIn("fund_name", results[0])
    self.assertIsNotNone(results[0]["fund_name"])

# 2. GREEN: Minimal implementation
def scrape_funds(funds, data_dir=None):
    # ... existing code ...
    results.append({
        "source": source,
        "fund_id": fund_id,
        "fund_name": "Unknown",  # Minimal implementation
        "price": price,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "success"
    })

# 3. REFACTOR: Add proper fund name scraping
```

### TDD Tools and Shortcuts

#### Cursor/VS Code TDD Shortcuts
- `Ctrl+Shift+T`: Run all tests (verify RED/GREEN state)
- `Ctrl+Shift+R`: Run current test (quick verification)
- `Ctrl+Shift+D`: Debug current test (step through TDD cycle)
- `F5`: Start debugging with breakpoints

#### Test Execution Commands
```bash
# Run all tests (verify RED/GREEN state)
python -m unittest -v test_scrape_fund_price.py

# Run specific test class
python -m unittest test_scrape_fund_price.TestFundPriceScraper -v

# Run specific test method
python -m unittest test_scrape_fund_price.TestFundPriceScraper.test_read_fund_ids -v

# Run with coverage
coverage run -m unittest test_scrape_fund_price.py
coverage report -m
```

## Development Environment Setup

### Prerequisites
- Python 3.10 or higher (CI tests 3.10, 3.12 and 3.14)
- Git
- Code editor (VS Code, PyCharm, Vim, etc.)
- Terminal/Command line access

### Initial Setup
```bash
# Clone repository
git clone https://github.com/joneswm/FundPrices.git
cd FundPrices

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Verify setup
python test_scrape_fund_price.py
```

### IDE Configuration

#### VS Code
Create `.vscode/settings.json`:
```json
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": true,
    "python.formatting.provider": "black",
    "python.testing.pytestEnabled": true,
    "python.testing.unittestEnabled": true
}
```

#### PyCharm
1. Open project in PyCharm
2. Configure Python interpreter to use virtual environment
3. Enable code inspection and formatting
4. Configure test runner for unittest

## Code Style and Standards

### Python Style Guide
Follow PEP 8 guidelines:
- Use 4 spaces for indentation
- Maximum line length: 88 characters
- Use descriptive variable and function names
- Add docstrings for all functions and classes

### Code Formatting
```bash
# Install formatting tools
pip install black isort flake8

# Format code
black scrape_fund_price.py
isort scrape_fund_price.py

# Check style
flake8 scrape_fund_price.py
```

### Documentation Standards
- Use Google-style docstrings
- Include type hints where appropriate
- Document all public functions and classes
- Keep README files up to date

## Project Structure

```
FundPrices/
├── scrape_fund_price.py      # Main application
├── test_scrape_fund_price.py  # Test suite
├── requirements.txt           # Dependencies
├── funds.txt                 # Fund configuration
├── test_funds.txt           # Test fund configuration
├── data/                    # Data output directory
│   ├── latest_prices.csv    # Latest price data
│   └── prices_history.csv   # Historical data
├── docs/                    # Documentation
│   ├── technical_documentation/
│   └── user_stories/
└── .github/                 # GitHub Actions
    └── workflows/
```

## Development Workflow

### 1. Feature Development
```bash
# Create feature branch
git checkout -b feature/new-fund-source

# Make changes
# Write tests
# Update documentation

# Test changes
python test_scrape_fund_price.py

# Commit changes
git add .
git commit -m "Add new fund source support"

# Push branch
git push origin feature/new-fund-source
```

### 2. Testing
```bash
# Run all tests
python test_scrape_fund_price.py

# Run specific test
python -m unittest test_scrape_fund_price.TestFundPriceScraper.test_read_fund_ids

# Run with coverage
coverage run test_scrape_fund_price.py
coverage report
coverage html  # Generate HTML report
```

### 3. Code Review Process
1. Create pull request
2. Ensure all tests pass
3. Request review from maintainers
4. Address feedback
5. Merge after approval

## Adding New Features

Open a GitHub issue, write a spec under `specs/`, then implement with TDD. The
sketches below show where each kind of change lands in the current design.

### 1. New Fund Source

Every source is a function returning `list[Quote]`, oldest first, where a `Quote` is
`(date, price, currency)` with the date **as the source reports it**. Prefer a dated
HTTP or API route; scraping a page that shows only the current price yields the run
date and no currency.

```python
def fetch_example_quotes(identifier, start, end=None):
    """Fetch dated daily quotes from Example."""
    end = end or datetime.date.today().isoformat()
    response = requests.get(EXAMPLE_URL.format(id=identifier, start=start, end=end),
                            timeout=EXAMPLE_REQUEST_TIMEOUT)
    response.raise_for_status()

    quotes = [
        Quote(row["date"], normalize_price(row["close"]), row["currency"])
        for row in response.json().get("rows") or []
    ]
    if not quotes:
        raise ValueError(f"Example returned no rows for {identifier}")
    return sorted(quotes, key=lambda quote: quote.date)
```

Then wire it in, test-first at each step:

1. Add a branch for the new two-letter code in `scrape_fund_quotes()`, the single
   dispatch point.
2. Add the code to `source_requires_browser()` if it needs no browser.
3. Raise `ValueError` for "no rows" so `fetch_with_retries()` and the import treat it
   as a failure rather than an empty success.
4. Add a live functional test that **skips** when the source is down.
5. Document the code in `README.md`, `AGENTS.md`, `constitution.md` and
   `api_reference.md`.

Before trusting a new source, validate it against a series you can verify another way.
Sources found wanting so far: Yahoo repeating one close with zero volume across a
ticker change, FT resolving an ISIN to a different listing and currency, FT pricing
LSE-listed ETFs on UK bank holidays, and justETF serving a converted series 1.6% away
from real closes.

### 2. New Data Fields

Stored rows are `[fund, date, price, currency]`, written through `write_history_csv()`
with `HISTORY_HEADER`. A new field is a new trailing column, as `Currency` was:

- extend `Quote`, `HISTORY_HEADER` and the row built in `scrape_funds()`
- make `read_history_rows()` tolerate rows written before the column existed
- keep the first columns in place, so positional readers are unaffected

### 3. New Output Formats

Derive new outputs from the rows already in hand, and write them through
`open_for_write()` so they get LF endings on every platform:

```python
def write_results_json(rows, data_dir):
    """Write the latest row per fund as JSON."""
    latest = latest_rows_by_fund(rows)
    with open_for_write(os.path.join(data_dir, "latest_prices.json")) as f:
        json.dump([latest[fund] for fund in sorted(latest)], f, indent=2)
        f.write("\n")
```

If the file should be committed by the daily run, add its pattern to the `git add -f`
line in `.github/workflows/scrape.yml`.

## Testing Guidelines

### Unit Testing
- Test all public functions
- Use descriptive test names
- Test both success and failure cases
- Mock external dependencies

```python
def test_get_source_config_invalid_source(self):
    """Test get_source_config with invalid source."""
    url, selector = get_source_config("INVALID", "TEST123")
    self.assertIsNone(url)
    self.assertIsNone(selector)
```

### Integration Testing
- Test complete workflows
- Use real fund identifiers
- Test with different data sources

```python
def test_end_to_end_scraping(self):
    """Test complete scraping workflow."""
    funds = [("FT", "GB00B1FXTF86")]
    results = scrape_funds(funds, data_dir=self.test_dir)
    
    self.assertEqual(len(results), 1)
    self.assertEqual(results[0]["status"], "success")
    self.assertIsNotNone(results[0]["price"])
```

### Test Data Management
- Use temporary directories for test data
- Clean up after tests
- Use mock data when possible

## Debugging and Profiling

### Debugging Techniques
```python
# Add debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Use breakpoints in IDE
# Add print statements for debugging
print(f"Debug: Processing {source}:{fund_id}")

# Use pdb for interactive debugging
import pdb; pdb.set_trace()
```

### Performance Profiling
```python
import cProfile
import pstats

# Profile function execution
profiler = cProfile.Profile()
profiler.enable()

# Run your code
scrape_funds(funds)

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(10)
```

## Documentation Updates

### When to Update Documentation
- Adding new features
- Changing API interfaces
- Fixing bugs that affect behavior
- Updating dependencies

### Documentation Types
1. **Code Comments**: Explain complex logic
2. **Docstrings**: Document function interfaces
3. **README Files**: Provide overview and setup instructions
4. **API Reference**: Detailed function documentation
5. **User Stories**: Feature requirements and acceptance criteria

## Version Control Best Practices

### Commit Messages
Use clear, descriptive commit messages:
```
feat: add Bloomberg fund source support
fix: resolve timeout issues with Yahoo Finance
docs: update API reference for new functions
test: add integration tests for new sources
```

### Branch Naming
- `feature/description`: New features
- `bugfix/description`: Bug fixes
- `hotfix/description`: Critical fixes
- `docs/description`: Documentation updates

### Pull Request Guidelines
1. Keep PRs focused and small
2. Include tests for new features
3. Update documentation
4. Ensure all tests pass
5. Request appropriate reviewers

## Dependencies Management

### Adding Dependencies
```bash
# Install new package
pip install new-package

# Update requirements.txt
pip freeze > requirements.txt

# Test with clean environment
pip uninstall -r requirements.txt -y
pip install -r requirements.txt
```

### Updating Dependencies
```bash
# Check for updates
pip list --outdated

# Update specific package
pip install --upgrade package-name

# Update all packages
pip install --upgrade -r requirements.txt

# Test after updates
python test_scrape_fund_price.py
```

## Deployment Considerations

### Environment Variables
Use environment variables for configuration:
```python
import os

DATA_DIR = os.getenv("DATA_DIR", "data")
FUNDS_FILE = os.getenv("FUNDS_FILE", "funds.txt")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
```

### Error Handling

**Retry logic already exists - do not add your own.** `scrape_funds()` wraps every fetch in
`fetch_with_retries()` (up to `MAX_PRICE_ATTEMPTS`, default 3) and, when all attempts
fail, carries the fund's last stored row forward under its original date. Nothing is
invented for today and nothing is recorded as "N/A":

```python
# scrape_fund_price.py - existing behaviour, abridged
quotes, error = fetch_with_retries(
    lambda: scrape_fund_quotes(spec.source, spec.lookup_id, start, browser=browser)
)
if error:
    results.failures.append(f"{spec.lookup_id}: {error}")
    last_known = read_last_known_row(identifier, data_dir)
    if last_known is not None:
        results.carried.append([identifier] + last_known)
    continue
```

If you need to change retry behaviour, adjust `MAX_PRICE_ATTEMPTS` or `fetch_with_retries()`
rather than wrapping `scrape_funds()`. See `api_reference.md` for the full contract.

## Contributing Guidelines

### Before Contributing
1. Check existing issues and pull requests
2. Discuss major changes in issues first
3. Ensure you have permission to contribute

### Contribution Process
1. Fork the repository
2. Create feature branch
3. Make changes with tests
4. Update documentation
5. Submit pull request
6. Address review feedback
7. Wait for maintainer approval

### Code Review Checklist
- [ ] Code follows style guidelines
- [ ] Tests pass and cover new functionality
- [ ] Documentation is updated
- [ ] No breaking changes without discussion
- [ ] Performance impact considered
- [ ] Security implications reviewed
