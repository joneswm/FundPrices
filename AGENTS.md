# FundPrices - Agent Guidelines

## Project Overview
Python application that collects dated fund, ETF and stock prices and end-of-day FX rates
(Yahoo Finance API, Financial Times and investing.com over HTTP; only the FT fetch falls
back to Playwright scraping), stores them as CSV in this repository, and publishes a daily
price-change summary. The whole application is one module, `scrape_fund_price.py`.

This file holds what an agent needs to work here: the commands, the invariants, the staging
rules and the configuration grammar. Features, file formats and the rest are stated once
elsewhere; the table of which file owns which fact is
[`docs/technical_documentation/README.md`](docs/technical_documentation/README.md).
Point at it rather than copying from it.

## Task Tracking

**GitHub Issues is the single source of truth for work that needs doing.**

- Open work: https://github.com/joneswm/FundPrices/issues
- File new work as an issue — do **not** add to-do checkboxes to markdown files
- Reference the issue number in commits (e.g. `Fixes #12`)
- The maintainer's work, AI-assisted work included, is committed directly to `main`;
  branches and pull requests are for outside contributors, Dependabot and experiments
  (constitution section 7). Commit only when asked, and keep `main` green
- Checkboxes remaining in `docs/` and `specs/` are either historical records of completed
  work, reusable process checklists, or template placeholders — none are open tasks
- What each spec delivered is recorded in `specs/README.md`;
  `docs/user_stories/implementation_status.md` is a frozen record of the legacy user
  stories and is not updated

## Common Commands

### Testing
- `./run_tests.sh unit` - the default: the mocked suite, no network. Also plain
  `python test_scrape_fund_price.py`
- `./run_tests.sh live` - also the tests that hit live sources; they run only when the
  environment variable `FUNDPRICES_LIVE` is set, and skip when a source is down
- `./run_tests.sh coverage` - the mocked suite with both coverage gates from `.coveragerc`
  (90% overall, 95% on `scrape_fund_price.py`); `make test-coverage` is the same report
- `./run_tests.sh all` - everything, live tests included

### Rebuilding History
- `python scrape_fund_price.py --backfill --from 2021-12-01` - rebuild stored history
  from source data. Manual only; also available as the **Rebuild Price History**
  workflow. Shares a concurrency group with the daily scrape so the two cannot push
  at the same time.

### Dividends
- `python scrape_fund_price.py --backfill-dividends [--from DATE]` - rebuild the Yahoo and
  issuer rows of the dividend history from the source. Manual only
- `distributions.txt` (SPEC-010) and `dividend_sources.txt` (SPEC-011, SPEC-012) are
  described under Configuration below; how each issuer source was found is
  `docs/research/dividend_pay_date_sources.md`

### Importing Closed Holdings
- `python scrape_fund_price.py --import-closed` - one-off import of the windows in
  `closed_holdings.txt`. Writes `prices_history.csv` and nothing else. Run locally and
  commit; there is deliberately no workflow for it.

### Running the Scraper
- `python scrape_fund_price.py` - run the daily collection once
- Results are saved to `data/latest_prices.csv`, `data/prices_history.csv` and
  `data/prices_history_90_days.csv` (rolling 90-calendar-day window, currently priced
  funds only), plus one `data/latest_<identifier>.price` file per fund, the FX files
  `data/fx_history.csv` and `data/latest_fx.csv`, `data/daily_summary.{csv,md}`, the
  dividend files `data/dividends_history.csv` and `data/dividends_upcoming.csv`,
  `data/uk_cpi.csv` (SPEC-013) and `data/uk_bank_rate.csv` (SPEC-014). The formats are in
  the README, Output Files
- A step that fails is listed in the run's failures with a prefix naming it:
  `prices: <error>`, `fx: <error>`, `uk_cpi: <error>`, `uk_bank_rate: <error>`

### Code Quality
- `./format_code.sh` - Format code with Black and isort
- `make format` - Alternative formatting command
- `make test` - Run tests via Makefile
- `make validate` - Validate development environment

### Development Environment
- `./setup_dev_env.sh` - Set up development environment (Linux/Mac)
- `setup_dev_env.bat` - Set up development environment (Windows)
- `python validate_dev_env.py` - Validate environment setup
- Dependencies and their versions: `requirements.txt` (what each one is for is in the
  README, Dependencies)

## Project Structure

### Key Files
- `scrape_fund_price.py` - The whole application, in one module
- `test_scrape_fund_price.py` - The test suite
- `funds.txt` - Instruments priced by the daily run
- `fx_pairs.txt` - FX pairs snapped by the daily run
- `closed_holdings.txt` - Instruments imported once and never fetched again
- `distributions.txt` - Hand-kept distribution schedules for instruments no source covers
- `dividend_sources.txt` - Issuer sources of dividend dates, per instrument (SPEC-011, SPEC-012)
- `requirements.txt` - Python dependencies

### Key Directories
- `data/` - Output directory. Gitignored, but its files are **tracked**: stage new ones
  with `git add -f data/*.csv data/*.price data/*.md`. Because they are tracked, a plain
  `git add -A` stages data changes too, so stage code by filename when the two should
  land in separate commits
- `docs/technical_documentation/` - Technical documentation; its README holds the
  canonical-source table
- `docs/user_stories/` - Only the index and the frozen `implementation_status.md`; the
  user stories themselves are in `docs/archive/user_stories/`
- `docs/research/` - Research notes behind design decisions
- `specs/` - Spec Kit specifications, indexed in `specs/README.md`
- `.devcontainer/` - Dev Container configuration (VS Code / GitHub Codespaces)
- `.github/workflows/` - GitHub Actions for CI/CD

## Code Style and Conventions

### Python Style
- Follow PEP 8 guidelines
- Use Black formatter for code formatting
- Use isort for import sorting
- Maximum line length: 88 characters (Black default)
- Type hints encouraged but not required

### Testing Requirements
- **MANDATORY**: Follow Test-Driven Development (TDD) workflow
- **RED-GREEN-REFACTOR** cycle for all changes
- Maintain code coverage above 90% overall and 95% for `scrape_fund_price.py` (both enforced in CI)
- Write tests BEFORE implementation
- All tests must pass before committing

### Commit Messages
- Follow conventional commit format
- If an AI assistant contributed to a commit, include that assistant's `Co-authored-by:` trailer
- Reference the GitHub issue number when applicable (e.g., "Fixes #12")
- Legacy commits reference user story IDs (e.g., "US-026"); these are historical
- Use prefixes: RED, GREEN, REFACTOR for TDD commits

## Configuration

Every configuration file is validated before any network call. A malformed line, an
empty or self-referencing alias, or an identifier repeated anywhere in a file raises an
error naming the line.

### `funds.txt`

Each line is `<source>,<lookup_id>[,<alias>[;<alias>...]]`. Blank lines, full-line
`#` comments and trailing comments are ignored.

```
FT,GB00B1FXTF86             # Financial Times (dated HTTP endpoint)
YA,AAPL                     # Yahoo Finance API
YA,0P00000YAN,JFM0003373    # fetched as 0P00000YAN, published as both
```

**Source Codes:**
- `FT` - Financial Times (dated HTTP endpoint; falls back to scraping)
- `YA` - **Yahoo Finance API** via yfinance daily bars. Used by 26 of 32 instruments
- `IV` - investing.com (undocumented HTTP endpoint). Used only by closed holdings, for
  funds Yahoo and FT no longer price; never put it on a schedule
- `GF` - deprecated spelling of `YA`; still accepted, warns, and names the line
- `YH` - Yahoo Finance (web scraping). Undated, so prefer `YA`. Currently unused
- `MS` - Morningstar (web scraping). Supported but unused: the one fund that
  needed it now comes from Yahoo

How each source is fetched, and the run modes, are in
`docs/technical_documentation/architecture.md`.

**Identifier aliases**: the optional third field lists extra identifiers to publish
under, separated by `;`. The price is fetched **once** using the second field and
written under every identifier, so a fund can move to a better source without
stranding history recorded under its old identifier.

### `fx_pairs.txt`

One six-letter pair per line, **GBP per 1 unit of the foreign currency** (`USDGBP` is
about 0.75). The slash spelling is rejected so the market convention `GBP/USD` cannot be
confused with it. What a day's rate is and where it comes from is in the README, FX Rates.

### `closed_holdings.txt`

One line per instrument: `<identifier>,<source>,<lookup_id>,<currency>,<start>,<end>`
(dates inclusive).

Instruments held once and no longer priced. The file is separate from `funds.txt`
precisely so the daily run cannot reach them. The import asserts the configured currency
against what the source reports and skips the holding on a mismatch, which is how a
lookup that resolved to the wrong listing gets caught. Imported rows live only in
`prices_history.csv`; a rebuild preserves them and never promotes them into
`latest_prices.csv`, the rolling window or the `.price` files.

Before adding one, check the candidate source the hard way: Yahoo can repeat a close
with zero volume across a ticker change, FT's ISIN lookup can pick a different listing,
and FT prices LSE-listed ETFs on UK bank holidays. `closed_holdings.txt` records the
evidence for each choice.

### `distributions.txt`

Hand-kept schedules for instruments no source covers (the FT-sourced OEICs):
`<identifier>,<frequency>,<xd-dates>,<pay-offset-days>[,<last-amounts>[,<as-of>]]`.
The fields are explained in the README, Dividends.

### `dividend_sources.txt`

The issuer's own distribution table per instrument: `<identifier>,<source>,<source-id>`
(source `IS`: iShares UK, the id its product id; `IV` Invesco by CUSIP; `SS` SSGA by
ISIN; `Q4` a Q4 Inc IR site as `host/MIC`; `ET` etnet by HK code). Validated with
`funds.txt`. Every instrument that pays has a source. The merge rules are in the README,
Dividends.

## Important Implementation Details

These are the invariants. The design behind them is in
`docs/technical_documentation/architecture.md`.

### Duplicate Prevention
- History is keyed on `(Fund, Date)`, where the date is the one the **source** reports
- An incoming row replaces the stored row with the same key, so corrections apply and
  re-runs cannot duplicate
- Rows are sorted by date then fund and written with LF endings on every platform, so
  repeated runs are byte-identical

### Latest Never Goes Backwards (#78)
- `latest_prices.csv` and `latest_<id>.price` never replace a stored row with an older
  date: the newest stored row (from `latest_prices.csv` or history) wins and a warning is
  printed. The same date still replaces, so corrections apply. Without this a stale fetch
  (Yahoo returns the newest daily bar with a null close for hours after a session) stepped
  every London ETF back a day, and the 90-day window with it
- `fetch_yahoo_quotes` fills a null **newest** close from the chart metadata only when that
  price traded on the bar's date and the regular session is over; any doubt drops the bar
- It also holds back a priced newest bar while that day's regular session is still open
  (#84), so a run during market hours stores no intraday price. FT's dated endpoint has
  no session times, so `fetch_ft_quotes` stores a row only once 16:00 New York (the US
  close) on its date has passed; the undated scraping fallback is not covered
- Scheduled runs start hours after the cron time, so a run at 00:40 UTC is normal

### FX Rate Is the New York Close (#80)
- A day's rate is the rate at 17:00 New York, from Yahoo's hourly bars, stored only once
  that cut has passed, so no rate is provisional and a later run gives the same value.
  Weekends have no rate. Yahoo's daily FX bar is not used for recent days: its Close is
  the start of the day, not its close. The full account is in the README, FX Rates

### Error Handling
- A failed fetch is reported on `ScrapeResults.failures`; it never crashes the run and
  no error text is ever written to a data file
- An unsupported source code is a failure for that fund like any other
- System continues processing even if individual funds fail, writes everything it
  obtained, and only then exits non-zero

### Retries and Last Known Price
- Every fetch is retried up to `MAX_PRICE_ATTEMPTS` (3) via `fetch_with_retries()`
- After exhausting retries, the fund's newest stored row (`newest_stored_rows()`, read
  once per run from `latest_prices.csv` and `prices_history.csv`) is carried into
  `latest_prices.csv` under its original date (`ScrapeResults.carried`). No row is
  invented for today: a bare `.price` file holds no date, so it carries nothing
- A fund with no stored history simply has no row; nothing is recorded as "N/A"
- `ScrapeResults.failures` lists the funds that fell back
- **This already exists - do not reimplement retry logic**

### Test Coverage
- Both gates are enforced in CI: 90% overall and 95% on `scrape_fund_price.py`
  (constitution section 2). Run `make test-coverage` for the current figures
- The default run is mocked and needs no network; the live-source tests run only with
  `FUNDPRICES_LIVE` set and skip when a source is down

## TDD Workflow (MANDATORY)

**IMPORTANT**: All development MUST follow this workflow:

1. **RED Phase**: Write failing test first
   - Commit with message prefix "RED:"

2. **GREEN Phase**: Write minimal code to pass test
   - Commit with message prefix "GREEN:"

3. **REFACTOR Phase**: Improve code while keeping tests green
   - Commit with message prefix "REFACTOR:"

See `docs/technical_documentation/tdd_workflow.md` for detailed guidelines.

## Spec Kit

New features and major enhancements get a spec; bug fixes, small tweaks and maintenance
do not.

1. **SPECIFY**: Create `specs/XXX-feature-name/spec.md` defining what and why
2. **CLARIFY**: Resolve ambiguities (optional, document in spec)
3. **PLAN**: Create `plan.md` defining technical approach
4. **TASKS**: Create `tasks.md` breaking into small units
5. **IMPLEMENT**: Execute each task with TDD (RED-GREEN-REFACTOR)

Reference the spec ID in commits, e.g. `RED: Add test for Bloomberg scraper (SPEC-002)`.

- `constitution.md` - Non-negotiable project principles
- `specs/README.md` - Specification index and guidelines
- `.specify/config.yaml` - Spec Kit configuration
- `.specify/templates/` - Spec, plan, and task templates

The 27 legacy user stories (US-001 to US-027) predate Spec Kit, are all complete, and are
archived in `docs/archive/user_stories/`.

## GitHub Actions

- **Test Workflow** (`test.yml`): Runs on every push/PR across Python 3.10, 3.12 and
  3.14 with both coverage gates. Commits nothing
- **Scrape Workflow** (`scrape.yml`): two runs a day, 21:05 UTC (after the US close all
  year round) and 09:17 UTC (the funds' previous-day NAVs, and any close a late evening
  run missed); `scrape.yml` is canonical for the schedule. GitHub starts scheduled runs
  hours late; latest prices never step backwards (#78). Commits its results even when
  some funds failed
- **Rebuild Workflow** (`backfill.yml`): Manual only. Shares a concurrency group with
  the scrape so the two cannot push at once

## Notes for AI Agents

- Keep both coverage gates green; run the tests after every change
- **Use the Spec Kit workflow for new features** (SPECIFY → PLAN → TASKS → IMPLEMENT)
- **Follow TDD for all implementation** (RED-GREEN-REFACTOR mandatory)
- **Consult constitution.md** for non-negotiable principles
- Check `specs/README.md` for what each spec delivered and GitHub Issues for open work
- Read the existing code before changing it; the module is documented
- Before stating a fact in a document, find its owner in the canonical-source table and
  point there
- When creating specs, use templates in `.specify/templates/`
