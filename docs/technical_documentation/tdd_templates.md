# TDD Templates and Examples

This document provides templates and examples for Test-Driven Development in the Fund Price Scraping project.

## TDD Test Template

### Basic Test Method Template

```python
def test_[feature_name]_[specific_behavior](self):
    """
    Test [specific behavior] for [feature name].
    
    RED Phase: This test should fail initially
    GREEN Phase: Implement minimal code to make it pass
    REFACTOR Phase: Improve implementation while keeping test green
    """
    # Arrange: Set up test data and conditions
    # ... setup code ...
    
    # Act: Execute the functionality being tested
    # ... execution code ...
    
    # Assert: Verify the expected behavior
    # ... assertion code ...
```

### Example: Adding New Fund Source

```python
def test_get_source_config_bloomberg(self):
    """
    Test Bloomberg source configuration.
    
    RED Phase: This test should fail because Bloomberg source not implemented
    GREEN Phase: Add minimal Bloomberg configuration
    REFACTOR Phase: Improve configuration structure
    """
    # Arrange
    source = "BB"
    fund_id = "TEST123"
    
    # Act
    url, selector = get_source_config(source, fund_id)
    
    # Assert
    expected_url = "https://www.bloomberg.com/quote/TEST123"
    expected_selector = ".price-value"
    self.assertEqual(url, expected_url)
    self.assertEqual(selector, expected_selector)
```

### Example: Adding New Data Field

```python
def test_scrape_funds_includes_currency(self):
    """
    Test that scraped results include currency information.
    
    RED Phase: This test should fail because currency field not implemented
    GREEN Phase: Add minimal currency field
    REFACTOR Phase: Add proper currency detection logic
    """
    # Arrange
    funds = [("FT", "GB00B1FXTF86")]
    
    # Act
    results = scrape_funds(funds, data_dir=self.test_dir)
    
    # Assert
    self.assertEqual(len(results), 1)
    self.assertIn("currency", results[0])
    self.assertIsNotNone(results[0]["currency"])
    self.assertIsInstance(results[0]["currency"], str)
```

### Example: Error Handling

```python
def test_scrape_funds_handles_network_timeout(self):
    """
    Test that network timeouts are handled gracefully.
    
    RED Phase: This test should fail because timeout handling not implemented
    GREEN Phase: Add minimal timeout handling
    REFACTOR Phase: Improve error handling and logging
    """
    # Arrange
    funds = [("FT", "INVALID_ID")]
    
    # Act
    results = scrape_funds(funds, data_dir=self.test_dir)
    
    # Assert
    self.assertEqual(len(results), 1)
    self.assertIn("Error:", results[0]["price"])
    self.assertEqual(results[0]["status"], "error")
```

## TDD Implementation Templates

### Minimal Implementation Template (GREEN Phase)

```python
def [function_name]([parameters]):
    """
    [Function description]
    
    GREEN Phase: Minimal implementation to make tests pass
    """
    # Minimal implementation
    if [condition]:
        return [minimal_value]
    else:
        return [default_value]
```

### Refactored Implementation Template (REFACTOR Phase)

```python
def [function_name]([parameters]):
    """
    [Function description]
    
    REFACTOR Phase: Improved implementation with better structure
    """
    # Configuration dictionary for better maintainability
    configs = {
        "key1": {"url": "...", "selector": "..."},
        "key2": {"url": "...", "selector": "..."}
    }
    
    # Error handling
    try:
        # Main logic
        result = process_data()
        return result
    except SpecificException as e:
        logger.error(f"Specific error: {e}")
        return handle_error(e)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return handle_unexpected_error(e)
```

## TDD Workflow Checklist

### Before Starting Development

- [ ] **Understand Requirements**: What needs to be implemented?
- [ ] **Identify Test Cases**: What behaviors need to be tested?
- [ ] **Plan TDD Cycle**: Which test to write first?

### RED Phase Checklist

- [ ] **Write Test**: Create test that describes desired behavior
- [ ] **Run Test**: Verify test fails (RED)
- [ ] **Commit**: Commit failing test
- [ ] **Document**: Add comment explaining why test fails

### GREEN Phase Checklist

- [ ] **Write Minimal Code**: Implement only what's needed to pass test
- [ ] **Run Test**: Verify test passes (GREEN)
- [ ] **Run All Tests**: Ensure no other tests broke
- [ ] **Commit**: Commit passing implementation

### REFACTOR Phase Checklist

- [ ] **Improve Code**: Better structure, readability, performance
- [ ] **Run Tests**: Verify all tests still pass
- [ ] **Check Coverage**: Ensure test coverage maintained
- [ ] **Commit**: Commit refactored code

### Post-Development Checklist

- [ ] **All Tests Pass**: Complete test suite passes
- [ ] **Coverage Maintained**: Test coverage above 90%
- [ ] **Code Quality**: Linting and formatting checks pass
- [ ] **Documentation**: Docstrings and comments updated
- [ ] **Integration**: Feature works with existing system

## Common TDD Patterns

### Pattern 1: Configuration Extension

```python
# RED: Test new configuration
def test_get_source_config_reuters(self):
    url, selector = get_source_config("RT", "TEST123")
    self.assertEqual(url, "https://reuters.com/quote/TEST123")
    self.assertEqual(selector, ".price")

# GREEN: Minimal implementation
def get_source_config(source, fund_id):
    # ... existing code ...
    elif source.upper() == "RT":
        return f"https://reuters.com/quote/{fund_id}", ".price"
    # ... rest of function ...

# REFACTOR: Improve structure
def get_source_config(source, fund_id):
    configs = {
        "FT": ("https://markets.ft.com/data/funds/tearsheet/summary?s={}", ".mod-ui-data-list__value"),
        "RT": ("https://reuters.com/quote/{}", ".price")
    }
    template, selector = configs.get(source.upper(), (None, None))
    return template.format(fund_id) if template else None, selector
```

### Pattern 2: Data Structure Extension

```python
# RED: Test new data field
def test_scrape_funds_includes_timestamp(self):
    funds = [("FT", "GB00B1FXTF86")]
    results = scrape_funds(funds, data_dir=self.test_dir)
    
    self.assertIn("timestamp", results[0])
    self.assertIsNotNone(results[0]["timestamp"])

# GREEN: Minimal implementation
def scrape_funds(funds, data_dir=None):
    # ... existing code ...
    results.append({
        "source": source,
        "fund_id": fund_id,
        "price": price,
        "timestamp": "2024-01-01 00:00:00",  # Hardcoded for now
        "status": "success"
    })

# REFACTOR: Proper timestamp generation
def scrape_funds(funds, data_dir=None):
    # ... existing code ...
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results.append({
        "source": source,
        "fund_id": fund_id,
        "price": price,
        "timestamp": timestamp,
        "status": "success"
    })
```

### Pattern 3: Error Handling

```python
# RED: Test error handling
def test_scrape_funds_handles_invalid_source(self):
    funds = [("INVALID", "TEST123")]
    results = scrape_funds(funds, data_dir=self.test_dir)
    
    self.assertEqual(results[0]["price"], "N/A")
    self.assertEqual(results[0]["status"], "error")

# GREEN: Minimal error handling
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

# REFACTOR: Better error handling
def scrape_funds(funds, data_dir=None):
    # ... existing code ...
    url, selector = get_source_config(source, fund_id)
    if url and selector:
        try:
            price = scrape_price_with_common_settings(page, url, selector)
            status = "success"
        except TimeoutError:
            price = "Timeout"
            status = "timeout"
        except Exception as e:
            price = f"Error: {e}"
            status = "error"
    else:
        price = "N/A"
        status = "invalid_source"
```

## TDD Best Practices

### Test Writing

1. **One Behavior Per Test**: Each test should verify one specific behavior
2. **Descriptive Names**: Test names should clearly describe what's being tested
3. **Arrange-Act-Assert**: Structure tests with clear setup, execution, and verification
4. **Edge Cases**: Test boundary conditions and error scenarios
5. **Mock Dependencies**: Use mocks for external dependencies

### Implementation

1. **Minimal Code**: Write only what's needed to pass tests
2. **Clean Code**: Follow PEP 8 and project standards
3. **Refactor Continuously**: Improve code structure while maintaining tests
4. **Document Changes**: Update docstrings and comments

### Workflow

1. **Small Steps**: Make small, incremental changes
2. **Frequent Testing**: Run tests after every change
3. **Commit Often**: Commit after each TDD phase
4. **Review Code**: Ensure code quality and test coverage

## Troubleshooting TDD Issues

### Test Doesn't Fail Initially

**Problem**: Test passes without implementation
**Solution**: 
- Check if feature already exists
- Verify test is testing the right thing
- Make test more specific

### Test Fails After Implementation

**Problem**: Implementation doesn't match test expectations
**Solution**:
- Review test and implementation
- Check for typos or logic errors
- Ensure test and implementation are consistent

### Refactoring Breaks Tests

**Problem**: Tests are too tightly coupled to implementation
**Solution**:
- Focus tests on behavior, not implementation
- Use interfaces and abstractions
- Mock internal dependencies

### Tests Pass But Feature Doesn't Work

**Problem**: Test doesn't cover real-world usage
**Solution**:
- Add integration tests
- Test with real data
- Improve test coverage

Remember: **TDD is mandatory for this project. Follow the RED-GREEN-REFACTOR cycle strictly.**
