# Deployment Guide

How the Fund Price Scraping project runs. In production it is a GitHub Actions
workflow that commits its results back to this repository; there is no server, container
or service to deploy. The workflow files are canonical: if this page and
`.github/workflows/` disagree, the workflows are right.

## Prerequisites

- Python 3.10 or higher (CI tests 3.10, 3.12 and 3.14; the scrape workflow runs 3.12)
- Git
- Network access to Yahoo Finance, the Financial Times, investing.com, the issuers'
  distribution pages, the ONS and the Bank of England

Dependencies are listed, with their version floors, in
[`requirements.txt`](../../requirements.txt): `yfinance`, `requests`, `numpy`,
`playwright` and `coverage`. Playwright is only used as the Financial Times fallback.

## Installation

```bash
git clone https://github.com/joneswm/FundPrices.git
cd FundPrices
pip install -r requirements.txt
playwright install chromium     # only needed for the FT scraping fallback
python test_scrape_fund_price.py
```

For a full development environment see the [development guide](development_guide.md).

## Configuration

The configuration files sit in the repository root and are read from the working
directory:

| File | Holds |
|------|-------|
| `funds.txt` | Instruments priced by the daily run |
| `fx_pairs.txt` | FX pairs to snap |
| `closed_holdings.txt` | One-off historical imports |
| `distributions.txt` | Hand-kept dividend schedules for instruments no source covers |
| `dividend_sources.txt` | Issuer distribution tables, per instrument |

The formats are documented once, in the [README](../../README.md#configuration) and
[AGENTS.md](../../AGENTS.md). Each file is validated before any network call, so a
malformed line fails fast and names the line.

There are no environment variables or command-line options for relocating the
configuration or the `data/` directory; the only environment variable read is
`GITHUB_STEP_SUMMARY`, which GitHub Actions sets.

## Output

Results are written to `data/`. The files and their columns are
listed in the README's [Output Files](../../README.md#output-files) section. The files are
gitignored but tracked, so the workflow stages them with `git add -f`.

## Running

```bash
# Daily run: prices, FX rates, dividends, CPI, Bank Rate and the summary
python scrape_fund_price.py

# Rebuild stored history from the sources
python scrape_fund_price.py --backfill --from 2021-12-01

# One-off import of closed holdings
python scrape_fund_price.py --import-closed

# Rebuild the Yahoo rows of the dividend history (--from is optional)
python scrape_fund_price.py --backfill-dividends
```

Prices are end-of-day and history is keyed on the source's own price date, so running
more often than the schedule below fetches the same rows again.

## GitHub Actions

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `scrape.yml` | Two scheduled runs, 21:05 and 09:17 UTC, and manual | The daily run; commits its results |
| `backfill.yml` | Manual only | Rebuild of stored history |
| `test.yml` | Every push and pull request | Tests on Python 3.10, 3.12 and 3.14 with both coverage gates; commits nothing |

`scrape.yml` is the canonical source for the schedule. The 21:05 UTC run is after the
US close all year round; the 09:17 UTC run picks up the funds' previous-day NAVs and any
close the evening run missed. GitHub starts scheduled runs hours late, which is safe:
latest prices never step backwards.

The scrape commits its results even when some instruments failed, then exits non-zero so
the failure is visible. `scrape.yml` and `backfill.yml` share a concurrency group so a
rebuild and a daily run cannot push at once.

To set it up on a fork:

1. Enable GitHub Actions in the repository settings.
2. No secrets are needed: the workflows push with the built-in `GITHUB_TOKEN`.
3. Change the `cron` lines in `scrape.yml` if you want other times.

## Monitoring

- The Actions run page shows the daily summary table and the run output; a partial
  failure exits non-zero (see [troubleshooting](troubleshooting.md)).
- `data/daily_summary.md` shows what moved and marks stale (`~`) and failed (`!`)
  instruments.
- The data is in git history, so a bad day's data can be undone with an ordinary
  `git revert` of the "Update fund prices" commit, or repaired with the backfill.
