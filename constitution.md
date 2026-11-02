# FundPrices Project Constitution

**Version**: 1.3.1  
**Last Updated**: 2026-11-02  
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

### Linting and format checks
- CI checks formatting with Black and isort on every push (`test.yml`, the
  `make format-check` target and the pre-commit hooks run the same commands)
- flake8 runs through the pre-commit hooks where they are installed; fix what it
  reports before committing
- No warnings in production code

### Module Layout
- The application is one module, `scrape_fund_price.py`, with one test module beside
  it. That is a fact about the code today, not a principle: nothing here requires it to
  stay one file, and a split that keeps the tests green and the coverage gates met needs
  no amendment

---

## 4. Error Handling

### Resilience Requirements
- **System must continue** processing if individual funds fail
- **No silent failures** - every failure is reported on the run's result object and
  printed at the end of the run, which then exits non-zero
- **Invalid inputs** handled gracefully with clear error messages: configuration is
  validated before any network call, and a malformed line raises `ValueError` naming
  the line

### Error Contract
- **Fetchers raise.** A fetcher that cannot return a dated price raises (`ValueError`
  for a source that answered with nothing usable, the library's own exception
  otherwise). It never returns an error string and never returns a made-up row
- **`fetch_with_retries()` retries.** Every fetch goes through it, up to
  `MAX_PRICE_ATTEMPTS` (3) attempts; after the last it returns `(None, <error text>)`
  and the caller carries on with the next instrument
- **Failures collect on the result object.** `ScrapeResults.failures` (and the
  equivalent on the FX, dividend, CPI and Bank Rate results) lists each failure as
  `<identifier>: <error>`; a step that fails as a whole is listed under its name
  (`uk_cpi: <error>`). A failed fund is carried under its last stored date
  (`ScrapeResults.carried`); nothing is invented for today
- **No error text in data files.** Error text goes to the console and the failure
  list, never to a CSV, `.price` or summary file; the summary marks a failed
  instrument with `!` and a stale one with `~`
- The former contract, a returned `"Error: ..."` string, is gone from the daily
  run; `fetch_with_retries()` retries exceptions only. The `--history` path
  (`fetch_historical_data()`) keeps the old form until that path is rebuilt

```python
# Good: raise; the retry wrapper and the result object do the rest
raise ValueError(f"FT returned no historical rows for {isin}")

# Bad: an error string the caller has to recognise
return "Error: Invalid symbol XYZ"

# Bad: a silent failure
return None
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
- Specifications live at `specs/<NNN>-<feature-name>/`, indexed by `specs/README.md`
- All specs must include **acceptance criteria**
- A `plan.md` defines the **architecture** and a `tasks.md` breaks the work into
  **small, reviewable** units. Both are optional for a small spec, where `spec.md`
  alone carries the plan (SPEC-012 to SPEC-014 have neither)
- Open work is tracked in GitHub Issues, not in a status file

### Code Documentation
- Document the "why," not the "what"
- Avoid redundant comments that restate code
- Only comment non-obvious logic or trade-offs
- Keep docstrings up to date

### Documentation Structure
```
constitution.md            # This document
specs/                     # Spec Kit specifications, one directory per spec
.specify/                  # Spec Kit configuration and templates
docs/
├── user_stories/          # Legacy (frozen after the Spec Kit migration)
├── technical_documentation/
├── research/
└── archive/
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
- **Main branch**: Production-ready code, and where the maintainer works
- **The maintainer commits directly to `main`**, including work done with an AI
  assistant under the maintainer's direction. This is a single-maintainer project, and
  a pull request with no second reviewer adds ceremony without adding a check
- **What stands in for a merge gate**: a GitHub issue before the work starts, TDD
  commits that show the failing test before the fix, and CI on every push. A red run on
  `main` is fixed or reverted before anything else is done
- **Branches and pull requests are for**: outside contributors, Dependabot, and any
  change the maintainer wants to try without landing it, such as a large refactor or an
  experiment. Name them `feature/<description>`, `fix/<description>` or
  `spec/<spec-id>-<description>`
- **Parallel refactoring streams use branches.** When several streams of a programme
  run at once (one branch each, in its own worktree, with disjoint file ownership), each
  is rebased onto `main` and squash-merged in the order the programme's plan gives.
  A branch is deleted when its squash merge lands
- **Data and code are committed separately.** Files under `data/` are tracked, so stage
  code by filename rather than with `git add -A`

---

## 8. AI Coding Practices

### Spec-Driven Development
- **Specs guide AI** implementation
- **Constitution enforces** standards
- **Plans prevent** AI from guessing architecture
- **Tasks provide** manageable units for AI

### Human Oversight
- **The maintainer directs and reviews** AI-assisted work: the assistant researches and
  reports back before implementing anything that involves a judgement call, and reports
  what it did, what it verified and what it got wrong
- **Tests validate** AI implementations
- **Review happens in the session and on `main`**, not in a pull request; contributions
  from anyone else are reviewed in a pull request before merging
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
def test_total_failure_writes_no_history_row(self):
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
<SOURCE>,<LOOKUP_ID>[,<ALIAS>[;<ALIAS>...]]    # Comment

# Examples:
FT,GB00B1FXTF86             # Financial Times
YA,AAPL                     # Yahoo Finance API
YA,0P00000YAN,JFM0003373    # fetched as 0P00000YAN, published as both
```

The price is fetched once using the lookup id and written under every identifier.
Blank lines and `#` comments are ignored.

### Source Codes
- `YA` - Yahoo Finance API (uses yfinance library)
- `FT` - Financial Times (HTTP endpoint, scraping fallback)
- `IV` - investing.com (HTTP endpoint; one-off imports only)
- `GF` - deprecated alias for `YA`; warns and still resolves
- `YH` (Yahoo Finance) and `MS` (Morningstar), the web scrapers, were removed in
  #110; a line naming either is a validation error that names the line, and
  Playwright serves only the FT fallback

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
- **Scrape workflow**: two runs a day, at 21:05 UTC (after the US close all year
  round) and 09:17 UTC (the funds' previous-day NAVs, and any close the evening run
  missed). `.github/workflows/scrape.yml` is canonical for the schedule; GitHub starts
  scheduled runs hours late, so each time is a "not before"
- **Scrape and rebuild workflows** share a concurrency group, so the two cannot push at
  the same time
- **All tests must pass** on every push to `main`, and before any pull request is merged
- **Coverage reports** generated automatically

### Workflow Standards
- Set up Python environment automatically
- Install all dependencies (including Playwright)
- Run tests in headless environment
- Commit results automatically (scrape workflow), even when some instruments failed

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
- `requirements.txt` holds version floors (`>=`), not pinned majors, and Dependabot
  raises them; CI runs against whatever those floors resolve to
- A floor is raised by hand only when the code needs the newer behaviour, with the
  reason in the commit
- Document breaking changes

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
- Test suite: the mocked suite under 30 seconds; live tests (those that reach a real
  source, run only when `FUNDPRICES_LIVE` is set) are excluded from that figure

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
- CI runs the tests on Python 3.10, 3.12 and 3.14 and enforces both coverage gates on
  every push and pull request
- CI checks Black and isort formatting on every push and pull request; the pre-commit
  hooks (`.pre-commit-config.yaml`) run the same checks plus flake8 where installed
- A failing run on `main` is fixed or reverted before other work continues

### Manual Review
- The maintainer reviews every change: their own as they make it, AI-assisted work in
  the session that produced it, and outside contributions in a pull request
- Spec review before implementation
- Architecture review for major changes
- Documentation review for completeness

### Violations
- **Minor violations**: Fix in the next commit, or before merge for a pull request
- **Major violations**: Revert from `main`, or reject the pull request and request rework
- **Repeated violations**: Amend this constitution or the tooling so it cannot recur

---

## Amendments

This constitution is a living document. Amendments require:
1. Discussion with team/stakeholders
2. Documentation of rationale
3. Update to this document
4. Communication to all contributors
5. Version increment

**Amendment History**:
- v1.0 (2025-11-20): Initial constitution created during Spec Kit migration. Earlier
  versions of this history dated it 2024-11-20; `git log` shows the migration commit on
  2025-11-20, four months after the repository's first commit
- v1.1 (2026-09-21): Brought into line with the code, with no change of principle.
  Section 5 describes the keyed upsert that replaced date-based filtering and states
  the no-synthetic-data rule the implementation already followed; section 10 lists the
  current source codes (`YA`, `IV`, `GF` as a deprecated alias) and the separate
  closed-holdings file; section 11 gives the real schedule (22:30 UTC); section 12
  names every runtime dependency
- v1.2 (2026-09-21): Branching and review rewritten to match how the project is run.
  v1.0 required feature branches and reviewed pull requests for every change, but every
  feature since the Spec Kit migration was committed directly to `main` by a single
  maintainer, with pull requests used only by Dependabot. Section 7 now makes direct
  commits the rule for the maintainer and names what replaces the merge gate; sections
  8 and Enforcement describe review as it actually happens and stop claiming CI lints
- v1.3 (2026-11-02): Six amendments from the documentation review of 2026-11-02 (#97),
  each bringing a section into line with the code rather than changing a principle.
  Section 4 states the real error contract: fetchers raise, `fetch_with_retries()`
  retries, failures collect on the result object, and no error text reaches a data
  file; the `"Error: <message>"` return form it used to require had been gone since
  SPEC-003. Section 6 says specs live at `specs/`, makes `plan.md` and `tasks.md`
  optional for small specs, and no longer asks for `implementation_status.md` to be
  kept updated, that file being frozen. Section 7 adds branches for parallel
  refactoring streams and deletion on squash merge. Section 10 shows the `;` alias
  grammar, drops the `YH,IDTG.L` example and notes `YH` and `MS` as unused. Section
  11 gives the two daily runs (21:05 and 09:17 UTC) with `scrape.yml` canonical.
  Section 12 describes version floors maintained by Dependabot instead of pinned
  majors. Section 14 limits the 30-second budget to the mocked suite. Section 3 notes
  that the single module is a fact, not a principle
- v1.3.1 (2026-11-02): Wording after Bundle 3 of #97. Section 3 and Enforcement now say
  CI checks Black and isort formatting (it does, since #116) and that flake8 runs in the
  pre-commit hooks; section 4 and section 10 record that `YH` and `MS` were removed
  (#110) and that a configuration line naming them is a validation error (#113)

---

## References

- [PEP 8 Style Guide](https://pep8.org/)
- [Black Code Formatter](https://black.readthedocs.io/)
- [TDD Workflow Documentation](docs/technical_documentation/tdd_workflow.md)
- [Spec Kit Assessment](docs/archive/spec_kit_assessment.md) - Archived: why Spec Kit was adopted
- [Development Guide](docs/technical_documentation/development_guide.md)

---

**Remember**: These principles exist to maintain code quality, ensure reliability, and enable effective collaboration between humans and AI. When in doubt, refer to this constitution.
