# SPEC-014: Bank of England Bank Rate Published Monthly as uk_bank_rate.csv

**Status**: ✅ Complete
**Created**: 2026-11-01
**Type**: Feature (new published file)
**Tracking**: [#93](https://github.com/joneswm/FundPrices/issues/93)

> Portfolio Tracker's Sharpe ratio (risk metrics, stage RK-C, portfolio-tracker#688/#692) needs
> a risk-free rate, and the owner chose the Bank of England Bank Rate (2026-11-01). FundPrices
> supplies its market data, so it publishes the rate as it publishes the UK CPI (SPEC-013): one
> more file in `data/`, written by the daily run.

---

## User Need

**As** the owner of the portfolio
**I want** the official Bank Rate published beside the prices
**So that** a risk-adjusted return can be shown with no second place to fetch data from

## Proposed Solution

`data/uk_bank_rate.csv`, one row per month from January 2015 to the current month, the official
Bank Rate in force at the end of the month, in percent a year. The daily run reads the Bank of
England's **Bank Rate history page** once
(`https://www.bankofengland.co.uk/boeapps/database/Bank-Rate.asp`, a table of `Date Changed` and
`Rate`, newest first, back to 1975) and derives the months from the change dates. The rate changes
a few times a year, so most runs republish what they read.

```csv
Month,Rate,Series,AsOf
2015-01,0.50,UK_BANK_RATE,2026-11-01
2023-08,5.25,UK_BANK_RATE,2026-11-01
2026-10,3.75,UK_BANK_RATE,2026-11-01
```

| Column | Meaning |
|--------|---------|
| `Month` | `YYYY-MM` |
| `Rate` | The Bank Rate in force at the end of the month, percent a year, as the Bank words it (`5.25`, `4.00`; never reformatted). The current month carries the rate in force on the run date |
| `Series` | `UK_BANK_RATE` |
| `AsOf` | The date the row was first published or last changed |

## Success Criteria

### Functional Requirements

- **FR1**: `parse_boe_bank_rate()` returns the change list `[(date, rate text)]` oldest first,
  **the whole table** (back to 1975), the rate text kept exactly (`"4.00"` stays `"4.00"`). The
  page prints two-digit years; a year is read as 20yy unless that date is after the run date,
  then 19yy
- **FR2**: **A page that is not what was recorded is an error, not an empty list**: no Bank Rate
  table, no rows, a date or rate that does not parse (`n/a`, `-1`, `1e3`, `4,25`, a month name
  that is not one), a date listed twice, or a history that does not reach back to the change in
  force on 2014-12-31 (the table truncated)
- **FR3**: `uk_bank_rate_by_month()` gives each month from `UK_BANK_RATE_START` (`2015-01`) to
  the run date's month the rate of the newest change dated on or before the month's last day (for
  the current month, on or before the run date). A change after a month end does not touch that
  month. A month with no change repeats the rate in force, so there is **no gap**. The change in
  force on 2014-12-31 (the 0.50 of March 2009) is why the whole table is parsed
- **FR4**: One GET per run (30 s timeout, `Accept: text/html`, the same browser `User-Agent` as the
  other HTTP sources), retried by `fetch_with_retries()` like every other source. No other request
  is made
- **FR5**: Every derived month replaces the stored row for that month, so a changed rate for a
  past month lands. A new or changed month carries the run date as `AsOf`; an unchanged one keeps
  its `AsOf`, so a run that reads the same numbers leaves the file byte-identical. A stored month
  the derivation lacks is kept
- **FR6**: A fetch that fails after its retries, or a page refused under FR2, leaves
  `uk_bank_rate.csv` untouched (byte-identical; none is created on a first failed run) and is
  listed in the run's failures as `uk_bank_rate: <error>`. The run writes everything else, then
  exits non-zero, as for the other sources
- **FR7**: Written like the other files: sorted by month, LF endings on every platform, the
  `data/` directory created if missing. The update runs in the normal mode only, after the UK CPI
  and independently of it (a crash is a failure line, never a lost summary)
- **FR8**: The tests never touch the network. The page was fetched once on 2026-11-01 and saved as
  `fixtures/boe_bank_rate.html` (whole, as served); edge cases are built in the tests
  (`boe_page()`)

### Non-Functional Requirements

- **Robots and terms.** `https://www.bankofengland.co.uk/robots.txt` disallows
  `/boeapps/database/_iadb-FromShowColumns.asp`, `ShowChart.asp`, `/boeapps/iadb` and
  `/boeapps/titan`; `Bank-Rate.asp` is not disallowed. One request a run
- **Fragility.** The page is an HTML table with a stable id (`stats-table`) that the Bank's own
  site renders; any change fails loudly (FR2) and keeps the last file

## Out of Scope

- Other Bank of England series, the Bank's database endpoints, a daily rate series, a monthly
  average rate
- A manual rebuild command: the page carries the whole history, so every run is a full rebuild
- Computing a Sharpe ratio: that is Portfolio Tracker's

## Decisions

| Decision | Reason |
|----------|--------|
| The Bank Rate history page, not the database series IUMABEDR (owner, 2026-11-01) | The issue named IUMABEDR over the database CSV endpoint, but robots.txt disallows that endpoint (`_iadb-FromShowColumns.asp`) and the rest of the database's routes, and robots is honoured, full stop; no path variant is used. The history page lists the same official Bank Rate and is allowed |
| The rate is derived from change dates, not read per month | The page lists changes, not months; "in force at month end" is the newest change on or before the month's last day |
| The current month is the rate in force on the run date | The month has not ended, and the consumer wants today's rate |
| `AsOf` changes only when a row's value does | As SPEC-013 (owner, 2026-10-28): stamping the run date on every row would rewrite the file in git each day with the same numbers. The header keeps the name `AsOf` because Portfolio Tracker's parser requires it. The current month's row is the one that changes, when the Bank moves the rate or a new month starts |
| The rate is kept as text | The Bank gives two decimals; converting through a float could only add noise |
| A page that does not reach 2014-12-31 is refused | Without the 2009 change every early month would be unknowable, and a wrong rate is worse than a stale file |
| No configuration file | One series, fixed by the issue |
