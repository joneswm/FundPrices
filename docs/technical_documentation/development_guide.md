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
- Python 3.7 or higher
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

### 1. New Fund Source
To add a new fund source (e.g., "Bloomberg"):

```python
def get_source_config(source, fund_id):
    """Get URL and selector for a given source and fund_id."""
    if source.upper() == "FT":
        url = f"https://markets.ft.com/data/funds/tearsheet/summary?s={fund_id}"
        selector = ".mod-ui-data-list__value"
    elif source.upper() == "YH":
        url = f"https://sg.finance.yahoo.com/quote/{fund_id}/"
        selector = 'span[data-testid="qsp-price"]'
    elif source.upper() == "MS":
        url = f"https://asialt.morningstar.com/DSB/QuickTake/overview.aspx?code={fund_id}"
        selector = '#mainContent_quicktakeContent_fvOverview_lblNAV'
    elif source.upper() == "BB":  # New Bloomberg source
        url = f"https://www.bloomberg.com/quote/{fund_id}"
        selector = ".priceText__1853e8a5"
    else:
        return None, None
    return url, selector
```

### 2. New Data Fields
To add new data fields (e.g., fund name):

```python
def scrape_funds(funds, data_dir=None):
    """Scrape prices for a list of funds and return results."""
    # ... existing code ...
    
    for source, fund_id in funds:
        try:
            url, selector = get_source_config(source, fund_id)
            if url and selector:
                price = scrape_price_with_common_settings(page, url, selector)
                
                # Add fund name scraping
                name_selector = ".fund-name"  # Example selector
                try:
                    page.wait_for_selector(name_selector, timeout=5000)
                    fund_name = page.locator(name_selector).first.text_content().strip()
                except:
                    fund_name = "Unknown"
                
                results.append({
                    "source": source,
                    "fund_id": fund_id,
                    "fund_name": fund_name,  # New field
                    "price": price,
                    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "success"
                })
        except Exception as e:
            # ... error handling ...
```

### 3. New Output Formats
To add JSON output support:

```python
import json

def write_results_json(results, data_dir=None):
    """Write results to JSON file."""
    if data_dir is None:
        data_dir = DATA_DIR
    
    os.makedirs(data_dir, exist_ok=True)
    
    json_file = os.path.join(data_dir, "latest_prices.json")
    with open(json_file, "w") as f:
        json.dump(results, f, indent=2)
```

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
Implement robust error handling:
```python
def robust_scrape_funds(funds, max_retries=3):
    """Scrape funds with retry logic."""
    for attempt in range(max_retries):
        try:
            return scrape_funds(funds)
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)  # Exponential backoff
```

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
