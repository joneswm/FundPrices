# SPEC-002: Rolling 90-Day Price History

**Status**: ✅ Complete
**Created**: 2026-08-16
**Type**: Enhancement

---

## Context

The scraper currently writes the latest prices and one complete historical CSV. Consumers that only need recent prices must repeatedly load and filter the full history.

## User Need

**As** a fund-price data consumer
**I want** both complete and rolling 90-day price-history files
**So that** I can use a compact recent dataset without losing the long-term record

## Problem Statement

The complete history is useful for long-term analysis but grows indefinitely. There is no ready-to-use file containing only recent data.

## Proposed Solution

Keep `data/prices_history.csv` as the complete record and create `data/prices_history_90_days.csv` after every results write. The rolling file will be derived from the complete history and include rows dated from today minus 89 days through today, inclusive.

## Success Criteria

### Functional Requirements

- [x] Preserve every valid historical row in `prices_history.csv`.
- [x] Create `prices_history_90_days.csv` with the same CSV header.
- [x] Include the current day and preceding 89 calendar days.
- [x] Exclude older and future-dated rows from the rolling file.
- [x] Preserve existing same-day replacement behavior in both files.

### Quality Requirements

- [x] Follow RED-GREEN-REFACTOR.
- [x] Maintain at least 90% overall coverage and fully test new logic.
- [x] Keep the existing full-history filename for backwards compatibility.

## Out of Scope

- Configurable retention periods.
- Removing old rows from the complete history.
- Changing CSV columns or sorting existing history.
- Migrating or renaming existing output files.

## Acceptance Criteria

- [x] A row exactly 89 days before the run date is included.
- [x] A row exactly 90 days before the run date is excluded.
- [x] Today's newly written rows appear in both history files.
- [x] Re-running on the same day replaces those rows in both files.
- [x] An empty result set still produces valid CSV outputs using the system date.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Boundary-day off-by-one error | Medium | Test both sides of the cutoff |
| Rolling and full files diverge | Medium | Always derive rolling rows from the newly written full-history rows |
| Invalid historical dates | Low | Retain them in full history but omit them from the rolling view |

## Constraints

- `prices_history.csv` remains the source of truth.
- The feature uses calendar days, not trading days or row counts.
- Existing public function signatures remain compatible.
