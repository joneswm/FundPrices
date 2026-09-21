# FundPrices Project Constitution

**Version**: 1.1  
**Last Updated**: 2026-09-21  
**Status**: Active

This document defines the non-negotiable principles and standards for the FundPrices project. All contributors (human and AI) must adhere to these rules.

---

## 1. Test-Driven Development (TDD)

### Mandatory RED-GREEN-REFACTOR Cycle

**ALL code changes MUST follow the TDD workflow. No exceptions.**

#### RED Phase: Write Failing Test First
- Write a test that describes the desired behavior
- Run the test and verify it fails
- Commit with prefix: `RED: <description>`

#### GREEN Phase: Make Test Pass
- Write minimal code to make the test pass
- Run the test and verify it passes
- Commit with prefix: `GREEN: <description>`

#### REFACTOR Phase: Improve Code
- Improve code quality while keeping tests green
- Run all tests and verify they still pass
- Commit with prefix: `REFACTOR: <description>`

### Test Requirements
- Write tests BEFORE implementation
- All tests must pass before committing
- No code without corresponding tests
- Tests must be clear and maintainable

---

## 2. Code Coverage Standards

### Minimum Coverage Requirements
- **Overall Project**: 90% minimum
- **Main Application Code**: 95% minimum
- **New Features**: 100% of new code must be tested

### Coverage Enforcement
- Run coverage reports before committing
- CI/CD pipeline enforces coverage thresholds
- Coverage must not decrease with new changes
- Untested code requires explicit justification

### Coverage Commands
```bash
# Run tests with coverage
python -m coverage run test_scrape_fund_price.py

# Generate coverage report
python -m coverage report

# Generate HTML coverage report
python -m coverage html
```

---

## 3. Code Quality Standards

### Python Style Guide
- **Follow PEP 8** guidelines strictly
- **Formatter**: Black (88 character line length)
- **Import Sorting**: isort
- **Type Hints**: Encouraged for public APIs

### Code Formatting
```bash
# Format code with Black
black scrape_fund_price.py test_scrape_fund_price.py

# Sort imports with isort
isort scrape_fund_price.py test_scrape_fund_price.py

# Or use convenience script
./format_code.sh
```

### Linting
- Use flake8 for linting
- Fix all linting errors before committing
- No warnings in production code

---

## 4. Error Handling

### Resilience Requirements
- **System must continue** processing if individual funds fail
- **Failed operations** return `"Error: <message>"` format
- **No silent failures** - all errors must be logged
- **Invalid inputs** handled gracefully with clear error messages

### Error Format
```python
# Good: Clear error message
return "Error: Invalid symbol XYZ"

# Bad: Silent failure
return None

# Bad: Crash
raise Exception("Something went wrong")
```

### Timeout Standards
- Page load timeout: 30 seconds
- Selector wait timeout: 60 seconds
- API call timeout: 30 seconds

---

## 5. Data Integrity

### Duplicate Prevention
- **History file** must prevent duplicate entries: it is keyed on `(Fund, Date)`,
  where the date is the one the source reports
- **Multiple runs per day** are safe - an incoming row replaces the stored row
- **Implementation**: Keyed upsert, sorted output, LF line endings on every platform
- **No synthetic data**: no row is written for a day a source publishes no price, and
  no error text is ever written to a data file

### Data Validation
- Validate all input data before processing
- Check data types and formats
- Handle edge cases (empty strings, special characters, etc.)
- Maintain consistency across all data sources

### File Management
- Create `data/` directory automatically if missing
- Handle file permission errors gracefully
- Use atomic writes where possible
- Maintain CSV format consistency

---

## 6. Documentation Standards

### Specification Documentation
- All specs must include **acceptance criteria**
- Technical plans must define **architecture**
- Tasks must be **small and reviewable**
- Keep `implementation_status.md` updated

### Code Documentation
- Document the "why," not the "what"
- Avoid redundant comments that restate code
- Only comment non-obvious logic or trade-offs
- Keep docstrings up to date

### Documentation Structure
```
docs/
├── user_stories/          # Legacy (archived after migration)
├── technical_documentation/
└── specs/                 # Spec Kit specifications
```

---

## 7. Version Control

### Git Practices
- **All documentation** in Git
- **Meaningful commit messages** following conventional format
- **Reference spec IDs** in commits (e.g., "SPEC-001: Add feature")
- **Attribute AI assistance**: If an AI assistant contributed to a commit, include that assistant's `Co-authored-by:` trailer

### Commit Message Format
```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types**: feat, fix, docs, style, refactor, test, chore

**TDD Prefixes**: RED, GREEN, REFACTOR (takes precedence over type)

### Examples
```
RED: Add test for Bloomberg data source integration

GREEN: Implement Bloomberg scraper with basic functionality

REFACTOR: Extract common scraping logic into helper function

feat(api): Add Yahoo Finance API integration (SPEC-001)
```

### Branching Strategy
- **Main branch**: Production-ready code
- **Spec branches**: `spec/<spec-id>-<description>`
- **Feature branches**: `feature/<description>`
- **Bug fix branches**: `fix/<description>`

---

## 8. AI Coding Practices

### Spec-Driven Development
- **Specs guide AI** implementation
- **Constitution enforces** standards
- **Plans prevent** AI from guessing architecture
- **Tasks provide** manageable units for AI

### Human Oversight
- **Human review required** for all AI-generated code
- **Tests validate** AI implementations
- **Code review** before merging
- **Verify alignment** with spec and constitution

### AI Collaboration Guidelines
- Provide clear, detailed specifications
- Break work into small, discrete tasks
- Use constitution to guide AI behavior
- Review and validate all AI outputs
- Iterate based on test results

---

## 9. Testing Standards

### Test Organization
- **Unit tests**: Test individual functions in isolation
- **Functional tests**: Test against real external services
- **Integration tests**: Test component interactions
- **Test independence**: Tests must not depend on each other

### Test Naming
```python
# Good: Descriptive test name
def test_fetch_price_api_returns_error_for_invalid_symbol(self):
    pass

# Bad: Vague test name
def test_api(self):
    pass
```

### Test Data Management
- Use temporary directories for file operations
- Clean up test data in `tearDown()`
- Keep test data separate from production
- Use realistic but safe test data

---

## 10. Configuration Management

### Fund Configuration Format
File: `funds.txt`

```
<SOURCE>,<IDENTIFIER>[,<ALIAS>]    # Comment

# Examples:
FT,GB00B1FXTF86    # Financial Times
YA,AAPL            # Yahoo Finance API
YH,IDTG.L          # Yahoo Finance (web scraping)
```

### Source Codes
- `YA` - Yahoo Finance API (uses yfinance library)
- `FT` - Financial Times (HTTP endpoint, scraping fallback)
- `IV` - investing.com (HTTP endpoint; one-off imports only)
- `YH` - Yahoo Finance (web scraping)
- `MS` - Morningstar (web scraping)
- `GF` - deprecated alias for `YA`; warns and still resolves

Closed holdings use the same source codes but a separate file,
`closed_holdings.txt`, so the daily run cannot pick them up.

### Configuration Validation
- Validate source codes on read
- Handle invalid configurations gracefully
- Log configuration errors clearly
- Provide helpful error messages

---

## 11. Continuous Integration/Continuous Deployment (CI/CD)

### GitHub Actions Requirements
- **Test workflow**: Runs on every push/PR
- **Scrape workflow**: Scheduled daily at 22:30 UTC, after the US close all year round
- **All tests must pass** before merge
- **Coverage reports** generated automatically

### Workflow Standards
- Set up Python environment automatically
- Install all dependencies (including Playwright)
- Run tests in headless environment
- Commit results automatically (scrape workflow)

---

## 12. Dependencies

### Required Libraries
- `yfinance` - Yahoo Finance API for prices, FX rates and historical data
- `requests` - FT and investing.com HTTP endpoints
- `numpy` - float32 round-tripping, so prices are stored exactly as quoted
- `playwright` - Scraping fallback and browser automation
- `coverage` - Code coverage measurement

**Versions are defined in [`requirements.txt`](requirements.txt)** and kept current by Dependabot.
The list above names what each dependency is for; it deliberately omits version pins so it
cannot drift out of sync with the actual requirements.


### Dependency Management
- Pin major versions in `requirements.txt`
- Test with latest compatible versions
- Document breaking changes
- Keep dependencies up to date

---

## 13. Security and Privacy

### Data Handling
- **No secrets in code** or configuration files
- **No API keys** in version control
- **No sensitive data** in logs
- **Use environment variables** for secrets

### Web Scraping Ethics
- Respect robots.txt
- Implement reasonable delays
- Handle rate limiting gracefully
- Don't overload target servers

---

## 14. Performance Standards

### Execution Time
- Individual fund scrape: < 10 seconds
- Full scrape (all funds): < 2 minutes
- Test suite: < 30 seconds

### Resource Usage
- Minimize memory footprint
- Clean up browser instances
- Close file handles properly
- Avoid resource leaks

---

## 15. Backwards Compatibility

### Breaking Changes
- **Avoid breaking changes** when possible
- **Document breaking changes** clearly
- **Provide migration path** for users
- **Version appropriately** (semantic versioning)

### Data Format Stability
- Maintain CSV format consistency
- Keep file naming conventions stable
- Preserve historical data format
- Document any format changes

---

## Enforcement

### Automated Enforcement
- Pre-commit hooks check formatting
- CI/CD enforces test coverage
- Linting runs automatically
- Tests must pass to merge

### Manual Review
- Code review required for all changes
- Spec review before implementation
- Architecture review for major changes
- Documentation review for completeness

### Violations
- **Minor violations**: Fix before merge
- **Major violations**: Reject PR, request rework
- **Repeated violations**: Team discussion and training

---

## Amendments

This constitution is a living document. Amendments require:
1. Discussion with team/stakeholders
2. Documentation of rationale
3. Update to this document
4. Communication to all contributors
5. Version increment

**Amendment History**:
- v1.0 (2024-11-20): Initial constitution created during Spec Kit migration
- v1.1 (2026-09-21): Brought into line with the code, with no change of principle.
  Section 5 describes the keyed upsert that replaced date-based filtering and states
  the no-synthetic-data rule the implementation already followed; section 10 lists the
  current source codes (`YA`, `IV`, `GF` as a deprecated alias) and the separate
  closed-holdings file; section 11 gives the real schedule (22:30 UTC); section 12
  names every runtime dependency

---

## References

- [PEP 8 Style Guide](https://pep8.org/)
- [Black Code Formatter](https://black.readthedocs.io/)
- [TDD Workflow Documentation](docs/technical_documentation/tdd_workflow.md)
- [Spec Kit Assessment](docs/archive/spec_kit_assessment.md) - Archived: why Spec Kit was adopted
- [Development Guide](docs/technical_documentation/development_guide.md)

---

**Remember**: These principles exist to maintain code quality, ensure reliability, and enable effective collaboration between humans and AI. When in doubt, refer to this constitution.
