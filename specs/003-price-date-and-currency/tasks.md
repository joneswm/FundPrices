# Tasks: True Price Dates and Currency

**Spec**: SPEC-003
**Status**: ✅ Complete
**Created**: 2026-09-20

---

## Task Overview

Each task follows RED-GREEN-REFACTOR. Tests are written before implementation.

**Total Tasks**: 6

Every criterion below was met when the spec shipped (2026-09-20); the boxes were
ticked on 2026-11-02 to say so. Task 6's single cron has since given way to two runs
a day, 21:05 and 09:17 UTC; `.github/workflows/scrape.yml` is canonical.

---

## Task 1: Quote record and price formatting

### Acceptance Criteria
- [x] `Quote` NamedTuple with `date`, `price`, `currency`
- [x] `format_yahoo_price()` returns the shortest float32 round-trip string
- [x] `124.87000274658203` → `124.87`; `126530.25` preserved; `6317.0` → `6317`

### TDD Cycle
RED: precision tests with exact float32 inputs.
GREEN: implement via `str(np.float32(x))`.
REFACTOR: document why rounding and `.7g` are both wrong.

---

## Task 2: Yahoo dated fetcher

### Acceptance Criteria
- [x] `fetch_yahoo_quotes(symbol, start, end=None)` returns `list[Quote]`
- [x] Uses `Close` with `auto_adjust=False`; drops NaN rows
- [x] Currency from `fast_info`, preserving `GBp`
- [x] Empty frame returns `[]`; exceptions propagate to the retry wrapper
- [x] `fetch_price_api()` delegates to it and no longer touches `.info`

---

## Task 3: FT dated fetcher

### Acceptance Criteria
- [x] `fetch_ft_quotes(isin, start, end=None)` parses xid, currency and rows
- [x] Date from the first `<span>`; close from the 4th `<td>`; commas stripped
- [x] Missing xid or zero rows raises
- [x] Failure falls back to the Playwright scrape with a warning
- [x] Prices never pass through `float()`

---

## Task 4: Windowed scraping and lazy browser

### Acceptance Criteria
- [x] `scrape_funds()` emits `[fund_id, date, price, currency]` per quote in the window
- [x] Browser launches only when a fund actually needs scraping
- [x] Total failure adds no history rows and records a failure
- [x] Fallback row uses the last known stored date, price and currency

---

## Task 5: Upsert storage

### Acceptance Criteria
- [x] History keyed on (Fund, Date); incoming rows replace matching rows
- [x] Output sorted by (Date, Fund); second identical write is byte-identical
- [x] Unusable prices never written
- [x] Legacy 3-column rows read with empty currency and rewritten as 4-column
- [x] `latest_prices.csv` takes the max date per fund
- [x] 90-day window filters on price date

---

## Task 6: Workflow, config and docs

### Acceptance Criteria
- [x] `scrape.yml` cron `30 22 * * *` with a correct comment
- [x] Commit step runs `if: always()`
- [x] `main()` writes output before signalling failure
- [x] `funds.txt`: `YH,SGLN.L` → `GF,SGLN.L`
- [x] `requests` added to `requirements.txt`
- [x] README, AGENTS.md and api_reference.md updated
