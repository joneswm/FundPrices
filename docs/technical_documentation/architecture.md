# System Architecture

## Overview

FundPrices collects dated fund, ETF and stock prices and end-of-day FX rates from
several sources, stores them as CSV in this repository, and publishes a daily summary
of what moved. GitHub is the only storage: a scheduled Actions workflow fetches,
writes and commits.

The whole application is one module, `scrape_fund_price.py`, with one test module,
`test_scrape_fund_price.py`.

## Modes

One entry point, four modes, selected by command-line flags:

| Mode | Flag | Reads | Writes |
|------|------|-------|--------|
| Daily run | *(none)* | `funds.txt`, `fx_pairs.txt` | every output file |
| Rebuild | `--backfill --from DATE` | `funds.txt`, `fx_pairs.txt` | price and FX files (no summary) |
| Closed-holding import | `--import-closed` | `closed_holdings.txt` | `prices_history.csv` only |
| Ad-hoc export | `--history SYMBOL --start DATE` | nothing | `history_<SYMBOL>_<START>_<END>.csv` |

## Components

### 1. Source handlers

Every handler returns a list of `Quote(date, price, currency)`, oldest first.
`scrape_fund_quotes()` is the single dispatch point.

| Code | Source | Route | Reports date | Reports currency |
|------|--------|-------|:---:|:---:|
| `YA` | Yahoo Finance | `yfinance` daily bars | yes | yes |
| `FT` | Financial Times | two plain HTTP requests; falls back to scraping | yes | yes |
| `IV` | investing.com | one plain HTTP request | yes | no — supplied by config |
| `YH` | Yahoo Finance | Playwright scrape of the quote page | no — run date | no |
| `MS` | Morningstar | Playwright scrape | no — run date | no |

`GF` is a deprecated alias of `YA`, canonicalised by `canonical_source()` with a
warning that names the offending line.

**Design decisions**

- **Dated quotes, not "today's price".** The date stored is the date the source
  reports. Weekends and holidays therefore produce no rows instead of repeating the
  previous close.
- **Daily bars over summary endpoints.** Yahoo's summary endpoint carries no price
  date and is stale for mutual funds.
- **Prices are stored as quoted.** Yahoo and investing.com both hold float32; values
  are round-tripped to the shortest exact decimal rather than rounded, so a 4 dp
  price or a half-penny tick survives. Currencies are kept as the source spells them:
  `GBp`, `GBX` and `GBP` are distinct and nothing is converted.
- **The browser is lazy.** `LazyBrowser` starts Chromium only if a fund actually needs
  scraping. With the current configuration no daily run starts it; it remains as the
  FT fallback.

### 2. Configuration

Three text files, each validated in full before any network call, with errors naming
the line.

- **`funds.txt`** — `<source>,<lookup_id>[,<alias>[;<alias>...]]`. The instruments
  priced every day. A fund is fetched once on its lookup id and published under every
  alias, so it can change source without stranding its history.
- **`fx_pairs.txt`** — six-letter pairs such as `USDGBP`, meaning GBP per 1 unit of
  the foreign currency. The slash spelling is rejected so the direction cannot be
  confused with the market convention.
- **`closed_holdings.txt`** —
  `<identifier>,<source>,<lookup_id>,<currency>,<start>,<end>`. Instruments held once
  and no longer priced. Kept apart from `funds.txt` precisely so the daily run cannot
  reach them.

### 3. Storage

All under `data/`, which is gitignored but whose files are tracked: workflows stage
them with `git add -f`. (Because they are tracked, a plain `git add -A` also stages
them.)

| File | Content | Written by |
|------|---------|------------|
| `prices_history.csv` | every `Fund,Date,Price,Currency` row, including closed holdings | daily, rebuild, import |
| `latest_prices.csv` | newest row per currently priced fund | daily, rebuild |
| `prices_history_90_days.csv` | last 90 calendar days, currently priced funds only | daily, rebuild |
| `latest_<identifier>.price` | one price, for single-value consumers | daily, rebuild |
| `fx_history.csv`, `latest_fx.csv` | `Pair,Date,Rate` at 6 dp | daily, rebuild |
| `daily_summary.csv`, `daily_summary.md` | new, old, delta and percent delta | daily |

**Design decisions**

- **Keyed upsert.** History is keyed on `(Fund, Date)`. An incoming row replaces the
  stored row with the same key, so corrections apply and re-runs cannot duplicate.
- **Deterministic output.** Rows are sorted by date then fund, and every file is
  written with LF endings on every platform, so an unchanged day is an empty diff.
- **Three owners, no overlap.** The daily run and the rebuild own the identifiers in
  `funds.txt`; the import owns the identifiers in `closed_holdings.txt`. A rebuild
  only touches identifiers it is given, and only ever promotes configured funds into
  the "current" files, so none of the three can undo another's work.
- **A rebuild deletes carefully.** It removes weekend rows and rows with no currency
  (the scrape-dated legacy data it exists to replace) but keeps currency-bearing rows
  a source happened to omit, because sources intermittently drop real trading days.

### 4. Automation

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `scrape.yml` | daily at 22:30 UTC, and manual | daily run, then commit and push |
| `backfill.yml` | manual only | rebuild from a chosen date |
| `test.yml` | push and pull request | tests on Python 3.10, 3.12 and 3.14 with both coverage gates |

- 22:30 UTC is after the US close all year round.
- `scrape.yml` and `backfill.yml` share a concurrency group so they cannot push at
  the same time.
- Commit steps run with `if: always()`, so a partial run still saves what it fetched.
- The Playwright browser is cached on the resolved Playwright version; on a hit
  nothing is downloaded. `test.yml` launches Chromium as a canary for a runner image
  that drops a needed library.
- The closed-holding import has no workflow. It is a one-off, run locally and
  committed.

## Data flow: daily run

```
funds.txt ──> read_fund_specs ──> scrape_funds ──> write_results
                                     │  per fund: fetch_with_retries(scrape_fund_quotes)
                                     │  on failure: carry the last known row forward
fx_pairs.txt ─> read_fx_pairs ──> snap_fx_rates ──> write_fx_results
                                                        │
history + fx ──> build_price_summary / build_fx_summary ──> write_summary
                                                        │
                                   failures? ──> exit 1 (after everything is written)
```

Prices, FX and the summary are written independently, so a problem with one never
costs another its day of data. The process exits non-zero only after every file that
could be written has been.

## Error handling

- **Per-instrument isolation.** One failing fund, pair or closed holding never stops
  the others.
- **Retries, then the last known price.** Each fetch is tried `MAX_PRICE_ATTEMPTS`
  times. If all fail, the fund's last stored row is carried into `latest_prices.csv`
  under its original date; no row is invented for today and no error string is ever
  written to a data file. A fund with no stored history simply has no row.
- **Failures are loud.** They are listed on `ScrapeResults.failures`, marked `!` in
  the daily summary, printed, and turn the Actions run red.
- **Staleness is visible.** An instrument whose newest price is more than
  `STALE_AFTER_DAYS` old is marked `~` so it is not mistaken for a flat day.
- **Imports assert the currency.** A closed holding whose source reports a different
  currency from the one configured is skipped, because that means the lookup
  resolved to a different listing.

## Security and conduct

- Actions authenticate with the built-in `GITHUB_TOKEN`; there are no secrets in code
  or configuration.
- Only public price data is collected, and the repository is public by design.
- FT and investing.com are reached through undocumented endpoints. FT requests are
  paced during a rebuild, and investing.com is used only for one-off imports, never
  on a schedule.

## Technology stack

- **Python 3.10+** (CI covers 3.10, 3.12 and 3.14)
- **yfinance**, **requests**, **numpy** for fetching and exact price formatting
- **playwright** for the scraping fallback
- **unittest** and **coverage**, with gates of 90% overall and 95% on
  `scrape_fund_price.py`
- **GitHub Actions** for scheduling, storage and CI

## Performance

- **Test suite**: about 10 seconds for ~250 tests, including a handful of live
  functional tests that skip when a source is down.
- **Daily run**: dominated by network time; no browser is started on the normal path.
- **Rebuild from 2023**: a few minutes, paced by the deliberate pause between FT
  requests.
