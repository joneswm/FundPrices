# Tasks: True Price Dates and Currency

**Spec**: SPEC-003
**Status**: 🔄 In Progress
**Created**: 2026-09-20

---

## Task Overview

Each task follows RED-GREEN-REFACTOR. Tests are written before implementation.

**Total Tasks**: 6

---

## Task 1: Quote record and price formatting

### Acceptance Criteria
- [ ] `Quote` NamedTuple with `date`, `price`, `currency`
- [ ] `format_yahoo_price()` returns the shortest float32 round-trip string
- [ ] `124.87000274658203` → `124.87`; `126530.25` preserved; `6317.0` → `6317`

### TDD Cycle
RED: precision tests with exact float32 inputs.
GREEN: implement via `str(np.float32(x))`.
REFACTOR: document why rounding and `.7g` are both wrong.

---

## Task 2: Yahoo dated fetcher

### Acceptance Criteria
- [ ] `fetch_yahoo_quotes(symbol, start, end=None)` returns `list[Quote]`
- [ ] Uses `Close` with `auto_adjust=False`; drops NaN rows
- [ ] Currency from `fast_info`, preserving `GBp`
- [ ] Empty frame returns `[]`; exceptions propagate to the retry wrapper
- [ ] `fetch_price_api()` delegates to it and no longer touches `.info`

---

## Task 3: FT dated fetcher

### Acceptance Criteria
- [ ] `fetch_ft_quotes(isin, start, end=None)` parses xid, currency and rows
- [ ] Date from the first `<span>`; close from the 4th `<td>`; commas stripped
- [ ] Missing xid or zero rows raises
- [ ] Failure falls back to the Playwright scrape with a warning
- [ ] Prices never pass through `float()`

---

## Task 4: Windowed scraping and lazy browser

### Acceptance Criteria
- [ ] `scrape_funds()` emits `[fund_id, date, price, currency]` per quote in the window
- [ ] Browser launches only when a fund actually needs scraping
- [ ] Total failure adds no history rows and records a failure
- [ ] Fallback row uses the last known stored date, price and currency

---

## Task 5: Upsert storage

### Acceptance Criteria
- [ ] History keyed on (Fund, Date); incoming rows replace matching rows
- [ ] Output sorted by (Date, Fund); second identical write is byte-identical
- [ ] Unusable prices never written
- [ ] Legacy 3-column rows read with empty currency and rewritten as 4-column
- [ ] `latest_prices.csv` takes the max date per fund
- [ ] 90-day window filters on price date

---

## Task 6: Workflow, config and docs

### Acceptance Criteria
- [ ] `scrape.yml` cron `30 22 * * *` with a correct comment
- [ ] Commit step runs `if: always()`
- [ ] `main()` writes output before signalling failure
- [ ] `funds.txt`: `YH,SGLN.L` → `GF,SGLN.L`
- [ ] `requests` added to `requirements.txt`
- [ ] README, AGENTS.md and api_reference.md updated
