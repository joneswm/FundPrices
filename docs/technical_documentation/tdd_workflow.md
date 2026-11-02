# Test-Driven Development (TDD) Workflow

This document defines the mandatory TDD workflow for the Fund Price Scraping project. The
rule itself is section 1 of [`constitution.md`](../../constitution.md); this page is the
practical detail. Templates and checklists are in [tdd_templates.md](tdd_templates.md).

**ALL code changes follow this workflow. No exceptions.** Documentation-only changes use
a `docs:` commit and need no test.

## The RED-GREEN-REFACTOR Cycle

### RED: write a failing test

**Goal**: a test that describes the desired behaviour and fails for the right reason.

1. Understand what needs to change, and which existing test class it belongs in.
2. Write the test.
3. Run it and read the failure. A test that fails because of a typo or an import error has
   not yet proved anything; it must fail on the behaviour.
4. Commit with the prefix `RED:`.

### GREEN: make it pass

**Goal**: the minimum code that passes the test.

1. Implement only what the test needs.
2. Run the new test, then the whole suite.
3. Commit with the prefix `GREEN:`. The suite must be green at every non-RED commit.

### REFACTOR: improve the code

**Goal**: better structure with the suite green.

1. Remove duplication, improve names, tighten the code.
2. Run the whole suite after each step.
3. Commit with the prefix `REFACTOR:`.

Reference the GitHub issue or spec in the commit (`Fixes #12`, `(SPEC-010)`); see
[AGENTS.md](../../AGENTS.md) and constitution section 7 for the commit format.

## What a test looks like in this project

The code under test follows one contract, and tests assert it:

- **Fetchers raise.** A source that cannot get a price raises; it does not return an error
  string and it does not return a placeholder.
- **`fetch_with_retries()` retries.** Every fetch is retried up to `MAX_PRICE_ATTEMPTS`
  (3). Do not reimplement retry logic in a new fetcher or its test.
- **Failures are collected, not raised past the run.** The result object carries a
  `failures` list (`<identifier>: <error>`, or a step prefix such as `uk_cpi: <error>`).
  The run writes everything it obtained and only then exits non-zero.
- **No error text ever reaches a data file.** A failed fetch leaves the previous file or
  row in place.
- **Result rows are `[identifier, date, price, currency]`**, with the date the source
  reports.

Rather than repeat sketches that drift out of date, copy the shape of two real test
classes in [`test_scrape_fund_price.py`](../../test_scrape_fund_price.py):

- **`TestNewYorkFxCloses`**: a pure function (`new_york_fx_closes`) tested with a fixed
  clock. The tests build hourly bars with a small `utc()` helper, pass `now=` explicitly,
  and assert the exact result. Read `test_takes_the_bar_that_ends_at_five_pm_new_york` for
  the basic shape, `test_follows_the_us_clock_change` for a boundary case, and
  `test_the_rate_does_not_depend_on_when_the_job_runs` for a property of the contract.
- **`TestUkCpiUpdate`**: a step that reads and writes a file, tested with the network
  fetch patched. `setUp` makes a temporary directory, `tearDown` removes it, and `_run()`
  patches `fetch_uk_cpi`. `test_the_first_run_writes_the_whole_series` is the happy path;
  `test_a_failed_fetch_keeps_the_last_published_file` is the failure contract (file
  byte-identical, one failure beginning `uk_cpi: `); and
  `test_a_transient_failure_is_retried` shows the shared retry in action.

New tests should read like these: one behaviour each, a name that says what is expected,
and exact assertions on the real row or file shape.

## TDD Rules and Guidelines

### DO

1. **Write the test first** and watch it fail
2. **Write minimal code**: only what is needed to pass
3. **Run the tests after every small change**
4. **Refactor continuously**, with the suite green
5. **Test edge cases**: boundaries, failures, weekends, bank holidays, the US clock change
6. **Use descriptive names**: the name says the behaviour
7. **Mock external dependencies**: unit tests never touch the network or the real `data/`
8. **Inject the clock** (`now=`, `today=`) rather than depending on when the test runs

### DO NOT

1. **Do not write code without a test that failed first**
2. **Do not skip the RED phase** or write the test after the code
3. **Do not over-engineer**
4. **Do not ignore a failing test**: fix it now
5. **Do not commit a failing test except in a RED commit**
6. **Do not assert on an error string in a data file**: there must never be one

## Running the tests

```bash
./run_tests.sh unit        # mocks only, seconds (the default)
./run_tests.sh live        # live sources; a source that is down is skipped
./run_tests.sh coverage    # unit tests with both coverage gates
./run_tests.sh all         # everything
```

A single class or method through unittest:

```bash
python -m unittest test_scrape_fund_price.TestNewYorkFxCloses -v
python -m unittest test_scrape_fund_price.TestUkCpiUpdate.test_a_transient_failure_is_retried -v
```

Live tests are enabled by `FUNDPRICES_LIVE`, which `./run_tests.sh live` sets; without it
they skip.

## TDD Quality Gates

### Pre-Commit Checklist

Before committing any code, verify:

- [ ] **RED**: the test was written first and failed on the behaviour
- [ ] **GREEN**: it now passes with a minimal implementation
- [ ] **REFACTOR**: the code has been improved with the suite green
- [ ] **All tests pass**: `./run_tests.sh unit`
- [ ] **Coverage holds both gates**: 90% overall and 95% for `scrape_fund_price.py`
- [ ] **Formatted**: `./format_code.sh`, or the pre-commit hooks
- [ ] **Documentation**: docstrings, and the file that owns the fact, updated

### Continuous Integration

`test.yml` runs on every push and pull request, across Python 3.10, 3.12 and 3.14:

- **Test execution**: the whole suite must pass
- **Coverage thresholds**: 90% overall, and 95% for `scrape_fund_price.py`

CI does not lint or check formatting. Black, isort and flake8 run locally, through
`./format_code.sh` and the pre-commit hooks in
[dev_tools_config.md](dev_tools_config.md). TDD compliance (a failing test first) is
checked by review of the commit history, not by CI.

## Troubleshooting TDD Issues

1. **The test does not fail initially**: it is not testing the right thing, or the
   behaviour already exists. Make the assertion more specific.
2. **The test fails after implementation**: the implementation and the test disagree;
   review both for consistency.
3. **Tests pass but the feature does not work**: the test does not cover real use. Record
   a real source response in `fixtures/` and test the parser against it, or add a live
   test that skips when the source is down.
4. **Refactoring breaks tests**: the tests are coupled to the implementation. Assert
   behaviour (rows and files), not internals.

Look at the existing tests for the pattern to follow before writing a new one.

**Remember: TDD is not optional. It is mandatory for this project.**
