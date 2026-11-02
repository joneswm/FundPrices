# Development Guide

Guidelines for developers working on the Fund Price Scraping project. The
non-negotiable rules are in [`constitution.md`](../../constitution.md); this guide is the
practical companion to them.

## Test-Driven Development (mandatory)

All code changes follow RED, GREEN, REFACTOR, with a commit per phase:

1. **RED**: write a failing test and confirm it fails for the right reason
2. **GREEN**: write the minimum code to pass it
3. **REFACTOR**: improve the code with the suite green

No production code without a test that failed first. Documentation-only changes use a
`docs:` commit prefix and need no test.

The full workflow, commit conventions and checklists are in
[tdd_workflow.md](tdd_workflow.md) and [tdd_templates.md](tdd_templates.md). They point at
real tests in `test_scrape_fund_price.py` rather than repeating examples here.

### Test Writing Guidelines
- **Descriptive names**: a test name says what is being tested and the expected outcome
- **Single responsibility**: each test verifies one behaviour
- **Arrange-Act-Assert**: clear setup, execution and verification
- **Edge cases**: boundaries, failures and awkward dates (weekends, bank holidays, the
  US clock change)
- **Mock external dependencies**: unit tests use mocks only and never touch the network

### Test Execution Commands
```bash
# Unit tests: mocks only, run in seconds. The default
./run_tests.sh unit

# The same through unittest, one class or one method
python -m unittest test_scrape_fund_price -v
python -m unittest test_scrape_fund_price.TestFundPriceScraper -v
python -m unittest test_scrape_fund_price.TestFundPriceScraper.test_write_results -v

# Tests that hit the live sources (they skip a source that is down)
./run_tests.sh live

# Coverage, with both gates (90% overall, 95% for scrape_fund_price.py)
./run_tests.sh coverage
```

## Development Environment Setup

### Prerequisites
- Python 3.10 or higher (CI tests 3.10, 3.12 and 3.14)
- Git
- A code editor (see [ide_setup.md](ide_setup.md))

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

# Install Playwright browsers (the FT scraping fallback only)
playwright install chromium

# Verify setup
./run_tests.sh unit
```

`./setup_dev_env.sh` (or `setup_dev_env.bat` on Windows) does the same and also installs
the formatters and linter; `python validate_dev_env.py` checks the result. The
`.devcontainer/` configuration gives the same environment in VS Code and Codespaces.

Editor setup is in [ide_setup.md](ide_setup.md); the formatter, linter and pre-commit
configuration is in [dev_tools_config.md](dev_tools_config.md).

## Code Style and Standards

Follow PEP 8, with Black and isort at an 88-character line length. Add docstrings to
functions and classes and type hints where they help.

```bash
./format_code.sh    # Black and isort
```

Dependencies are in `requirements.txt` and are kept current by Dependabot; the file has
environment markers (for example, numpy has a separate floor for Python below 3.11), so
edit it by hand and do not regenerate it from an installed environment.

## Project Structure

```
FundPrices/
├── scrape_fund_price.py        # The whole application, in one module
├── test_scrape_fund_price.py   # Test suite (unittest)
├── requirements.txt            # Dependencies
├── funds.txt                   # Instruments priced by the daily run
├── fx_pairs.txt                # FX pairs to snap
├── closed_holdings.txt         # Instruments imported once, never fetched again
├── distributions.txt           # Hand-kept dividend schedules
├── dividend_sources.txt        # Issuer sources of dividend dates
├── fixtures/                   # Recorded source responses used by tests
├── data/                       # Output (gitignored but tracked; see AGENTS.md)
├── specs/                      # Spec Kit specifications, one directory each
├── docs/
│   ├── technical_documentation/   # These guides
│   ├── research/                  # Source research
│   ├── user_stories/              # Legacy requirements (historical)
│   └── archive/
├── constitution.md             # Non-negotiable project principles
├── AGENTS.md                   # Guidance for AI agents and the command summary
├── Makefile                    # Common commands
├── run_tests.sh, format_code.sh, setup_dev_env.sh, setup_dev_env.bat,
│   validate_dev_env.py         # Development scripts
├── .devcontainer/              # Dev Container configuration
├── .specify/                   # Spec Kit configuration and templates
└── .github/workflows/          # scrape.yml, backfill.yml, test.yml
```

## Development Workflow

### 1. Feature Development

The maintainer works directly on `main`, one RED/GREEN/REFACTOR commit at a time, with
CI on every push as the gate (constitution, section 7). Outside contributors use a
branch and a pull request:

```bash
# Create feature branch
git checkout -b feature/new-fund-source

# Write the failing test, then the code, then run the suite
./run_tests.sh unit

# Commit. Stage by filename: files under data/ are tracked, and
# `git add .` would sweep data changes into a code commit
git add scrape_fund_price.py test_scrape_fund_price.py
git commit -m "GREEN: Add new fund source support"

# Push branch
git push origin feature/new-fund-source
```

### 2. Code Review Process

For pull requests from outside contributors:

1. Create pull request
2. Ensure all tests pass
3. Request review from maintainers
4. Address feedback
5. Merge after approval

## Adding New Features

Open a GitHub issue, write a spec under `specs/` for anything substantial, then implement
with TDD. The sketches below show where each kind of change lands in the current design.

### 1. New Fund Source

Every source is a function returning `list[Quote]`, oldest first, where a `Quote` is
`(date, price, currency)` with the date **as the source reports it**. Prefer a dated
HTTP or API route; scraping a page that shows only the current price yields the run
date and no currency.

```python
def fetch_example_quotes(identifier, start, end=None):
    """Fetch dated daily quotes from Example."""
    end = end or datetime.date.today().isoformat()
    response = http_get(EXAMPLE_URL.format(id=identifier, start=start, end=end))

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
2. Raise `ValueError` for "no rows" so `fetch_with_retries()` and the import treat it
   as a failure rather than an empty success.
3. Add a live functional test that **skips** when the source is down.
4. Update the documents that list sources. Which file owns which fact is in the table in
   [`README.md`](README.md) in this directory; update the owner rather than copying the
   fact into each guide.

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
- Test both success and failure cases
- Mock external dependencies
- Use temporary directories for files and clean up after the test
- Inject the clock (`now=`, `today=`) rather than patching time

```python
def test_a_source_with_no_route_is_an_error(self):
    """Test a code with neither a fetch nor a fallback raises naming it."""
    with self.assertRaisesRegex(ValueError, "Unsupported source XX for ABC"):
        scrape_fund_quotes("XX", "ABC", "2026-10-01")
```

[tdd_templates.md](tdd_templates.md) points at `TestNewYorkFxCloses` (a pure function with
an injected clock) and `TestUkCpiUpdate` (a file-writing step with the fetch patched) as
the models to copy.

### Functional Testing
Functional tests exercise the live sources and **skip** when a source is down, so an
outage never turns the suite red. Run them with `./run_tests.sh live`. Record a source's
real response in `fixtures/` and test the parser against it for the unit-level check.

## Debugging

```python
# Add debug output
print(f"Debug: Processing {source}:{fund_id}")

# Use pdb for interactive debugging
import pdb; pdb.set_trace()
```

To profile a run, wrap the call in `cProfile` and print the top cumulative entries. See
[troubleshooting.md](troubleshooting.md) for debugging a failing source.

## Documentation Updates

### When to Update Documentation
- Adding new features
- Changing behaviour or interfaces
- Fixing bugs that affect behaviour
- Updating dependencies

Update the file that owns the fact, as listed in the table in [`README.md`](README.md) in
this directory, and link to it from elsewhere instead of repeating it.

## Version Control Best Practices

### Commit Messages
Follow the conventional format with the TDD phase or spec ID where they apply, and
reference the GitHub issue (see constitution, section 7):
```
RED: Add test for Bloomberg scraper (SPEC-002)
GREEN: Implement Bloomberg scraper (SPEC-002)
docs: update the deployment guide. Refs #101
```

### Branch Naming
For contributors and experiments; the maintainer otherwise commits to `main`.
- `feature/description`: New features
- `fix/description`: Bug fixes
- `spec/<spec-id>-description`: Work on a spec

### Pull Request Guidelines
1. Keep PRs focused and small
2. Include tests for new features
3. Update documentation
4. Ensure all tests pass

## Dependencies Management

Versions live in `requirements.txt`, which uses environment markers and is kept current by
Dependabot. Edit it by hand; do not regenerate it from an installed environment, which
would drop the markers.

```bash
# Check for updates
pip list --outdated

# Test after updating
./run_tests.sh unit
```

## Error Handling

**Retry logic already exists - do not add your own.** `scrape_funds()` wraps every fetch in
`fetch_with_retries()` (up to `MAX_PRICE_ATTEMPTS`, default 3) and, when all attempts
fail, carries the fund's last stored row forward under its original date. Nothing is
invented for today and no error text is ever written to a data file:

```python
# scrape_fund_price.py - existing behaviour, abridged
quotes, error = fetch_with_retries(
    lambda: scrape_fund_quotes(spec.source, spec.lookup_id, start, browser=browser)
)
if error:
    results.failures.append(f"{spec.lookup_id}: {error}")
    if identifier in stored:  # newest_stored_rows(), read once per run
        results.carried.append([identifier, *stored[identifier][1:]])
    continue
```

New fetchers raise on failure and let `fetch_with_retries()` do the rest. If you need to
change retry behaviour, adjust `MAX_PRICE_ATTEMPTS` or `fetch_with_retries()` rather than
wrapping `scrape_funds()`. See `api_reference.md` for the full contract.

## Contributing Guidelines

### Before Contributing
1. Check existing issues and pull requests
2. Discuss major changes in issues first

### Contribution Process
1. Fork the repository
2. Create feature branch
3. Make changes with tests
4. Update documentation
5. Submit pull request
6. Address review feedback

### Code Review Checklist
- [ ] Code follows style guidelines
- [ ] Tests pass and cover new functionality
- [ ] Documentation is updated
- [ ] No breaking changes without discussion
