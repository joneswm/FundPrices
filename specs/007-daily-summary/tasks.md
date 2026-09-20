# Tasks: Daily Price-Change Summary

**Spec**: SPEC-007
**Status**: 🔄 In Progress
**Created**: 2026-09-20

---

## Task Overview

Each task follows RED-GREEN-REFACTOR. Tests are written before implementation.

**Total Tasks**: 3

---

## Task 1: Summary construction

### Acceptance Criteria
- [ ] Compares against the previous distinct price date, not the calendar day before
- [ ] Exact decimal arithmetic
- [ ] First-ever price, zero previous price and no-history cases handled
- [ ] Stale boundary at 4 and 5 days
- [ ] Failed instruments flagged; aliased instruments appear once

---

## Task 2: Rendering and output

### Acceptance Criteria
- [ ] CSV with the documented columns
- [ ] Markdown with prices, FX, Attention and biggest movers
- [ ] Appended to `$GITHUB_STEP_SUMMARY` only when set
- [ ] FX values at 6dp; FX heading states the direction

---

## Task 3: Wiring and docs

### Acceptance Criteria
- [ ] Written by the daily run, including when part of it failed
- [ ] Not written by `--backfill` or `--history`
- [ ] `scrape.yml` commits `data/*.md`
- [ ] README, AGENTS.md and api_reference.md updated
