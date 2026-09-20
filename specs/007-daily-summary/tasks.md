# Tasks: Daily Price-Change Summary

**Spec**: SPEC-007
**Status**: ✅ Complete
**Created**: 2026-09-20

---

## Task Overview

Each task follows RED-GREEN-REFACTOR. Tests are written before implementation.

**Total Tasks**: 3

---

## Task 1: Summary construction

### Acceptance Criteria
- [x] Compares against the previous distinct price date, not the calendar day before
- [x] Exact decimal arithmetic
- [x] First-ever price, zero previous price and no-history cases handled
- [x] Stale boundary at 4 and 5 days
- [x] Failed instruments flagged; aliased instruments appear once

---

## Task 2: Rendering and output

### Acceptance Criteria
- [x] CSV with the documented columns
- [x] Markdown with prices, FX, Attention and biggest movers
- [x] Appended to `$GITHUB_STEP_SUMMARY` only when set
- [x] FX values at 6dp; FX heading states the direction

---

## Task 3: Wiring and docs

### Acceptance Criteria
- [x] Written by the daily run, including when part of it failed
- [x] Not written by `--backfill` or `--history`
- [x] `scrape.yml` commits `data/*.md`
- [x] README, AGENTS.md and api_reference.md updated
