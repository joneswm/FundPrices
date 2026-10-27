# SPEC-013: UK CPI Published Monthly as uk_cpi.csv

**Status**: ✅ Built, on branch `uk-cpi` (not yet merged)
**Created**: 2026-10-27
**Type**: Feature (new published file)
**Tracking**: [#91](https://github.com/joneswm/FundPrices/issues/91)

> Portfolio Tracker's real returns deflate by UK CPI (owner, 2026-10-27). FundPrices supplies
> its market data, so it publishes the index as it publishes prices, FX rates and dividends:
> one more file in `data/`, written by the daily run.

---

## User Need

**As** the owner of the portfolio
**I want** the UK consumer price index published beside the prices
**So that** returns can be shown in today's pounds without a second place to fetch data from

## Proposed Solution

`data/uk_cpi.csv`, built from the ONS series **D7BT** (CPI INDEX 00: ALL ITEMS 2015=100),
monthly, from January 2015. The daily run reads the ONS time-series endpoint once
(`https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/d7bt/mm23/data`, JSON, its
`months` array); the series changes once a month, so most runs republish what they read.

```csv
Month,Index,Series,AsOf
2015-01,99.3,D7BT,2026-10-27
2026-09,144.1,D7BT,2026-10-27
```

| Column | Meaning |
|--------|---------|
| `Month` | `YYYY-MM` |
| `Index` | The published index, 2015 = 100, as the ONS words it (a decimal string; never reformatted) |
| `Series` | `D7BT` |
| `AsOf` | The date of the run that read the value |

## Success Criteria

### Functional Requirements

- **FR1**: `parse_ons_cpi()` returns `{month: index text}` oldest first, from `2015-01`
  (`UK_CPI_START`) on. The index text is kept exactly (`"100"` stays `"100"`). A month listed
  with an empty value, which the ONS does before it publishes it, is absent
- **FR2**: **A response that is not what was recorded is an error, not an empty series**: not
  JSON, a series id other than D7BT, no months, no `2015-01`, a missing month between `2015-01`
  and the newest, a month listed twice, an unknown month name, or an index that is not a
  positive plain decimal (`n/a`, `-1`, `0`, `1e3`, `99,3`)
- **FR3**: One GET per run (30 s timeout, `Accept: application/json`, the same browser
  `User-Agent` as the investing.com source), retried by `fetch_with_retries()` like every other
  source. No other request is made
- **FR4**: Every month in the response replaces the stored row for that month, so a revision
  lands, and carries the run date as `AsOf`. A stored month the response lacks is kept
- **FR5**: A fetch that fails after its retries, or a response refused under FR2, leaves
  `uk_cpi.csv` untouched (byte-identical; none is created on a first failed run) and is listed in
  the run's failures as `uk_cpi: <error>`. The run writes everything else, then exits non-zero,
  as for the other sources
- **FR6**: Written like the other files: sorted by month, LF endings on every platform, the
  `data/` directory created if missing. The update runs in the normal mode only, after the
  dividends and independently of them (a crash is a failure line, never a lost summary)
- **FR7**: The tests never touch the network. The response was fetched once on 2026-10-27 and
  saved as `fixtures/ons_d7bt_cpi.json`, trimmed to `description` and the months from
  2014 (values unchanged); edge cases are built in the tests (`ons_payload()`)

### Non-Functional Requirements

- **Robots and terms.** `https://www.ons.gov.uk/robots.txt` answers 404 (no rule), the endpoint
  is the one the ONS's own time-series pages call and its data is published under the Open
  Government Licence. One request a run
- **Fragility.** The JSON shape is the ONS's public time-series format, stable for years; any
  change fails loudly (FR2) and keeps the last file

## Out of Scope

- Other ONS series (CPIH, RPI, the quarterly or annual arrays), seasonal adjustment, rebasing
- Backfilling from before 2015, or a manual rebuild command: the response carries the whole
  series, so every run is a full rebuild
- Computing real returns: that is Portfolio Tracker's

## Decisions

| Decision | Reason |
|----------|--------|
| `AsOf` is the run date on every row, not only on changed ones | The issue defines it as when the value was read; it is what `dividends_upcoming.csv` already does. The cost is one changed column a day in git |
| A stored month the response lacks is kept | The ONS has never dropped a month; if it did, losing published history silently would be worse than keeping it |
| A gap inside the series refuses the whole response | A deflator with a hole in it gives wrong real returns without any sign of it |
| The index is kept as text | The ONS gives one decimal; converting through a float could only add noise |
| No `uk_cpi.txt` configuration file | One series, fixed by the issue; nothing for the owner to choose |
