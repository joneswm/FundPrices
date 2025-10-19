# Test-Driven Development (TDD) Workflow

This document defines the mandatory TDD workflow for the Fund Price Scraping project.

## 🚨 MANDATORY TDD PROCESS

**ALL development MUST follow this exact workflow. No exceptions.**

## The RED-GREEN-REFACTOR Cycle

### 🔴 RED Phase: Write Failing Test

**Goal**: Write a test that describes the desired behavior and fails.

#### Steps:
1. **Analyze Requirements**: Understand what needs to be implemented
2. **Write Test**: Create a test that describes the expected behavior
3. **Run Test**: Verify the test fails (RED)
4. **Commit**: Commit the failing test

#### Example:
```python
def test_get_source_config_bloomberg(self):
    """Test Bloomberg source configuration."""
    url, selector = get_source_config("BB", "TEST123")
    expected_url = "https://www.bloomberg.com/quote/TEST123"
    expected_selector = ".priceText__1853e8a5"
    self.assertEqual(url, expected_url)
    self.assertEqual(selector, expected_selector)
```

**Expected Result**: Test fails because Bloomberg source not implemented.

### 🟢 GREEN Phase: Make Test Pass

**Goal**: Write the minimal code to make the test pass.

#### Steps:
1. **Write Minimal Code**: Implement only what's needed to pass the test
2. **Run Test**: Verify the test passes (GREEN)
3. **Commit**: Commit the passing implementation

#### Example:
```python
def get_source_config(source, fund_id):
    if source.upper() == "FT":
        url = f"https://markets.ft.com/data/funds/tearsheet/summary?s={fund_id}"
        selector = ".mod-ui-data-list__value"
    elif source.upper() == "YH":
        url = f"https://sg.finance.yahoo.com/quote/{fund_id}/"
        selector = 'span[data-testid="qsp-price"]'
    elif source.upper() == "MS":
        url = f"https://asialt.morningstar.com/DSB/QuickTake/overview.aspx?code={fund_id}"
        selector = '#mainContent_quicktakeContent_fvOverview_lblNAV'
    elif source.upper() == "BB":  # NEW: Minimal implementation
        url = f"https://www.bloomberg.com/quote/{fund_id}"
        selector = ".priceText__1853e8a5"
    else:
        return None, None
    return url, selector
```

**Expected Result**: Test passes with minimal implementation.

### 🔵 REFACTOR Phase: Improve Code

**Goal**: Improve code quality while keeping tests green.

#### Steps:
1. **Improve Code**: Refactor for better readability, performance, or structure
2. **Run Tests**: Verify all tests still pass
3. **Commit**: Commit the refactored code

#### Example:
```python
def get_source_config(source, fund_id):
    """Get URL and CSS selector configuration for a given source and fund ID."""
    source_configs = {
        "FT": {
            "url": f"https://markets.ft.com/data/funds/tearsheet/summary?s={fund_id}",
            "selector": ".mod-ui-data-list__value"
        },
        "YH": {
            "url": f"https://sg.finance.yahoo.com/quote/{fund_id}/",
            "selector": 'span[data-testid="qsp-price"]'
        },
        "MS": {
            "url": f"https://asialt.morningstar.com/DSB/QuickTake/overview.aspx?code={fund_id}",
            "selector": '#mainContent_quicktakeContent_fvOverview_lblNAV'
        },
        "BB": {
            "url": f"https://www.bloomberg.com/quote/{fund_id}",
            "selector": ".priceText__1853e8a5"
        }
    }
    
    config = source_configs.get(source.upper())
    if config:
        return config["url"], config["selector"]
    return None, None
```

**Expected Result**: All tests pass with improved code structure.

## TDD Rules and Guidelines

### ✅ DO's

1. **Write Tests First**: Always write the test before the implementation
2. **Make Tests Fail**: Ensure tests fail initially (proves they test something real)
3. **Minimal Implementation**: Write only the code needed to pass tests
4. **Run Tests Frequently**: Run tests after every small change
5. **Refactor Continuously**: Improve code while keeping tests green
6. **Test Edge Cases**: Include boundary conditions and error scenarios
7. **Use Descriptive Names**: Test names should clearly describe behavior
8. **Mock External Dependencies**: Use mocks for network calls, file operations

### ❌ DON'Ts

1. **Don't Write Code Without Tests**: Never implement features without tests
2. **Don't Skip the RED Phase**: Always start with failing tests
3. **Don't Over-Engineer**: Write minimal code to pass tests
4. **Don't Ignore Failing Tests**: Fix failing tests immediately
5. **Don't Write Tests After Code**: Tests must come first
6. **Don't Skip Refactoring**: Always improve code quality
7. **Don't Commit Failing Tests**: Only commit when tests pass (except RED phase)

## TDD Workflow with Cursor/VS Code

### Keyboard Shortcuts for TDD

| Shortcut | Action | TDD Phase |
|----------|--------|-----------|
| `Ctrl+Shift+T` | Run all tests | Verify RED/GREEN state |
| `Ctrl+Shift+R` | Run current test | Quick verification |
| `Ctrl+Shift+D` | Debug current test | Step through TDD cycle |
| `F5` | Start debugging | Debug failing tests |
| `Ctrl+Shift+F5` | Restart debugging | Restart TDD cycle |

### TDD Workflow Steps in IDE

1. **Write Test** (RED Phase)
   - Create new test method
   - Write test code
   - Run test with `Ctrl+Shift+R` (should fail)

2. **Implement Feature** (GREEN Phase)
   - Write minimal implementation
   - Run test with `Ctrl+Shift+R` (should pass)
   - Run all tests with `Ctrl+Shift+T` (should all pass)

3. **Refactor Code** (REFACTOR Phase)
   - Improve code structure
   - Run tests frequently with `Ctrl+Shift+T`
   - Ensure all tests remain green

## TDD Examples for Common Scenarios

### Example 1: Adding New Fund Source

```python
# RED: Write failing test
def test_get_source_config_reuters(self):
    """Test Reuters source configuration."""
    url, selector = get_source_config("RT", "TEST123")
    expected_url = "https://www.reuters.com/markets/stocks/TEST123"
    expected_selector = ".price-value"
    self.assertEqual(url, expected_url)
    self.assertEqual(selector, expected_selector)

# GREEN: Minimal implementation
def get_source_config(source, fund_id):
    # ... existing code ...
    elif source.upper() == "RT":
        url = f"https://www.reuters.com/markets/stocks/{fund_id}"
        selector = ".price-value"
    # ... rest of function ...

# REFACTOR: Improve structure
# Move to configuration dictionary, add error handling, etc.
```

### Example 2: Adding New Data Field

```python
# RED: Write failing test
def test_scrape_funds_includes_currency(self):
    """Test that scraped results include currency information."""
    funds = [("FT", "GB00B1FXTF86")]
    results = scrape_funds(funds, data_dir=self.test_dir)
    
    self.assertEqual(len(results), 1)
    self.assertIn("currency", results[0])
    self.assertIsNotNone(results[0]["currency"])

# GREEN: Minimal implementation
def scrape_funds(funds, data_dir=None):
    # ... existing code ...
    results.append({
        "source": source,
        "fund_id": fund_id,
        "currency": "USD",  # Minimal implementation
        "price": price,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "success"
    })

# REFACTOR: Add proper currency detection
```

### Example 3: Error Handling

```python
# RED: Write failing test
def test_scrape_funds_handles_invalid_source(self):
    """Test that invalid source codes are handled gracefully."""
    funds = [("INVALID", "TEST123")]
    results = scrape_funds(funds, data_dir=self.test_dir)
    
    self.assertEqual(len(results), 1)
    self.assertEqual(results[0]["price"], "N/A")
    self.assertEqual(results[0]["status"], "error")

# GREEN: Minimal implementation
def scrape_funds(funds, data_dir=None):
    # ... existing code ...
    url, selector = get_source_config(source, fund_id)
    if url and selector:
        try:
            price = scrape_price_with_common_settings(page, url, selector)
        except Exception as e:
            price = f"Error: {e}"
    else:
        price = "N/A"  # Handle invalid source
    # ... rest of function ...

# REFACTOR: Improve error handling and logging
```

## TDD Quality Gates

### Pre-Commit Checklist

Before committing any code, verify:

- [ ] **RED Phase**: Test was written first and failed initially
- [ ] **GREEN Phase**: Test now passes with minimal implementation
- [ ] **REFACTOR Phase**: Code has been improved while keeping tests green
- [ ] **All Tests Pass**: Run `python test_scrape_fund_price.py` successfully
- [ ] **Coverage Maintained**: Test coverage remains above 90%
- [ ] **Code Quality**: Code follows PEP 8 and project standards
- [ ] **Documentation**: Docstrings and comments updated

### Continuous Integration

The CI/CD pipeline enforces TDD:

- **Test Execution**: All tests must pass
- **Coverage Threshold**: Minimum 90% test coverage
- **Code Quality**: Linting and formatting checks
- **TDD Compliance**: Code review ensures TDD workflow followed

## Troubleshooting TDD Issues

### Common Problems

1. **Test Doesn't Fail Initially**
   - **Problem**: Test passes without implementation
   - **Solution**: Test is not testing the right thing or implementation already exists

2. **Test Fails After Implementation**
   - **Problem**: Implementation doesn't match test expectations
   - **Solution**: Review test and implementation for consistency

3. **Tests Pass But Feature Doesn't Work**
   - **Problem**: Test doesn't cover real-world usage
   - **Solution**: Add integration tests or improve test coverage

4. **Refactoring Breaks Tests**
   - **Problem**: Tests are too tightly coupled to implementation
   - **Solution**: Focus tests on behavior, not implementation details

### Getting Help

- **Review TDD Examples**: Check existing test patterns in the codebase
- **Ask Questions**: Discuss TDD approach with team members
- **Study Resources**: Review TDD best practices and examples
- **Practice**: Start with simple features to build TDD skills

## TDD Benefits

Following TDD provides:

- **Better Code Quality**: Tests drive better design decisions
- **Fewer Bugs**: Comprehensive test coverage catches issues early
- **Faster Development**: Tests provide immediate feedback
- **Easier Refactoring**: Tests ensure changes don't break existing functionality
- **Better Documentation**: Tests serve as living documentation
- **Confidence**: Tests provide confidence in code changes

**Remember: TDD is not optional. It's mandatory for this project.**
