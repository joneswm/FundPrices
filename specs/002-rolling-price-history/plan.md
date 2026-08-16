# Technical Plan: Rolling 90-Day Price History

**Spec**: SPEC-002
**Status**: ✅ Complete
**Created**: 2026-08-16

---

## Overview

Extend `write_results()` so each write continues to update the complete history and also writes a recent-history projection covering 90 calendar days including the result date.

## Technical Approach

After same-day rows are replaced and the complete history is assembled, parse the reference date and filter those rows with an inclusive range from `reference_date - 89 days` through `reference_date`. Write the filtered rows to `prices_history_90_days.csv` with the existing header.

The result date is used as the reference date when results are present because it represents the scraper run date and makes the behavior deterministic in tests. For empty results, use the system date, matching existing behavior.

## Architecture Changes

### Modified Component: `write_results()`

- Continue writing `latest_prices.csv` and `prices_history.csv` unchanged.
- Add `prices_history_90_days.csv` as a derived output.
- Keep the function signature and current full-history behavior backwards compatible.

### Helper Logic

Add a small date-filtering helper if it improves readability. Invalid dates will not crash a run: their rows remain in complete history and are excluded from the rolling view.

## Data Flow

```text
new results + existing prices_history.csv
                 |
                 v
     replace rows for result date
                 |
          +------+------+
          |             |
          v             v
 complete history   filter inclusive
     CSV            90-day window
                        |
                        v
             rolling history CSV
```

## Testing Strategy

- Verify both files are created with identical headers.
- Seed rows at 90 and 89 days before the reference date and assert the boundary.
- Verify full history retains the excluded old row.
- Verify future and malformed dates are excluded without data loss from full history.
- Re-run existing unit and functional tests, then report coverage.

## Backwards Compatibility

No breaking changes. Existing filenames, columns, and `write_results()` arguments are preserved.

## Rollback Plan

Remove the rolling-file write and helper; the complete history remains unaffected.

**Risk Level**: Low
