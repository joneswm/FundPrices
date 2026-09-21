# SPEC-008: Rename the GF Source Code to YA

**Status**: ✅ Complete
**Created**: 2026-09-21
**Type**: Maintenance
**Tracking**: [#70](https://github.com/joneswm/FundPrices/issues/70)

---

## Context

`GF` stands for Google Finance. The project scraped Google Finance for about eleven
minutes on 2025-10-19 before replacing it with the Yahoo Finance API, and kept the
source code for `funds.txt` compatibility. It has meant Yahoo ever since, and now
covers 20 of the 26 instruments.

## User Need

**As** someone maintaining this configuration
**I want** the source code to name the source it actually uses
**So that** `funds.txt` can be read without knowing the project's history

## Problem Statement

- `GF` names a source the project does not use and cannot return to: the old selector no
  longer matches, the libraries are abandoned, and the endpoints they call return 404
- The README still documents Google's URL constraint ("standard ticker symbols without
  exchange prefixes") as though it applied to Yahoo
- `YH` is already Yahoo **scraping**, so reusing it would silently redefine an existing
  code and change which handler a stale `funds.txt` line selects

## Proposed Solution

Add `YA`, for Yahoo API, as the name for the current `GF` behaviour. Keep `GF` working
as a deprecated alias that warns, so an existing configuration keeps running.

## Success Criteria

### Functional Requirements

- `YA` routes to the Yahoo API and needs no browser
- `GF` continues to work, routing identically, and warns once per line
- `YH` keeps its current meaning of Yahoo web scraping
- An unknown source code is still reported as a failure

### Quality Requirements

- Unit tests use mocks only
- Coverage gates hold: ≥90% overall, ≥95% on `scrape_fund_price.py`
- Runs on Python 3.10, 3.12 and 3.14

## Out of Scope

- Retiring the unused `YH` and `MS` scraping configurations, which is separately
  decidable. The browser path stays regardless, because the FT fallback uses it
- Changing any stored data: the source code is configuration only

## Acceptance Criteria

- [x] `funds.txt` uses `YA` for all 20 Yahoo API instruments
- [x] A file still using `GF` parses, runs, and warns
- [x] `YH` still resolves to the scraping configuration
- [x] Docs no longer describe `GF`, and the Google URL note is gone
- [x] CI green on all three Python versions

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| A stale `funds.txt` breaks | `GF` keeps working as a deprecated alias |
| Reusing `YH` would change a line's handler silently | Use `YA`, leaving `YH` untouched |
| Stored data might embed the source code | It does not; every file keys on the instrument identifier |

## Constraints

- No data migration, and no rebuild
