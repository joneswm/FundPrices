# Tasks: End-of-Day FX Rates

**Spec**: SPEC-005
**Status**: 🔄 In Progress
**Created**: 2026-09-20

---

## Task Overview

Each task follows RED-GREEN-REFACTOR. Tests are written before implementation.

**Total Tasks**: 3

---

## Task 1: Pair configuration

### Acceptance Criteria
- [ ] `read_fx_pairs()` parses one pair per line, ignoring comments and blanks
- [ ] Rejects a malformed pair, e.g. `GBP/NZD`, `gbpnzd`, five letters
- [ ] Rejects duplicates, naming the line
- [ ] A missing file returns an empty list

---

## Task 2: Fetching and storage

### Acceptance Criteria
- [ ] `fetch_fx_quotes()` requests `<PAIR>=X` and drops weekend bars
- [ ] Rates stored at exactly 6 decimal places
- [ ] `fx_history.csv` upserts on (Pair, Date), sorted, idempotent
- [ ] A provisional same-day rate is replaced by a later value
- [ ] `latest_fx.csv` holds the newest row per pair
- [ ] Failures isolated: FX and prices are written independently

---

## Task 3: Wiring, backfill and docs

### Acceptance Criteria
- [ ] `fx_pairs.txt` committed with the four pairs
- [ ] Daily run writes FX after prices
- [ ] Backfill rebuilds FX with the same rule
- [ ] README, AGENTS.md and api_reference.md document direction and files
