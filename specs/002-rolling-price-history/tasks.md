# Tasks: Rolling 90-Day Price History

**Spec**: SPEC-002
**Status**: ✅ Complete
**Created**: 2026-08-16

---

## Task Overview

Implement the derived recent-history CSV through one focused TDD cycle, then validate documentation and coverage.

## Task 1: Define Rolling-History Behavior

**Status**: ✅ Complete

- [x] Confirm calendar-day semantics and inclusive boundary.
- [x] Preserve `prices_history.csv` as complete history.
- [x] Select `prices_history_90_days.csv` as the new filename.

## Task 2: RED - Add Rolling-History Tests

**Status**: ✅ Complete

- [x] Test file creation and header.
- [x] Test inclusion at 89 days and exclusion at 90 days.
- [x] Test complete-history retention.
- [x] Run the focused test and verify failure before implementation.

## Task 3: GREEN - Implement Rolling Output

**Status**: ✅ Complete

- [x] Derive rolling rows from complete history.
- [x] Write the new CSV after the complete-history update.
- [x] Make focused tests pass.

## Task 4: REFACTOR and Validate

**Status**: ✅ Complete

- [x] Improve naming and documentation while tests remain green.
- [x] Run the complete test suite.
- [x] Verify overall coverage remains above the required threshold.
- [x] Mark SPEC-002 complete.
