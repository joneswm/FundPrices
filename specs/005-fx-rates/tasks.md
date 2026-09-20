# Tasks: End-of-Day FX Rates

**Spec**: SPEC-005
**Status**: ✅ Complete
**Created**: 2026-09-20

---

## Task Overview

Each task follows RED-GREEN-REFACTOR. Tests are written before implementation.

**Total Tasks**: 3

---

## Task 1: Pair configuration

### Acceptance Criteria
- [x] `read_fx_pairs()` parses one pair per line, ignoring comments and blanks
- [x] Rejects a malformed pair, e.g. `GBP/NZD`, `gbpnzd`, five letters
- [x] Rejects duplicates, naming the line
- [x] A missing file returns an empty list

---

## Task 2: Fetching and storage

### Acceptance Criteria
- [x] `fetch_fx_quotes()` requests `<PAIR>=X` and drops weekend bars
- [x] Rates stored at exactly 6 decimal places
- [x] `fx_history.csv` upserts on (Pair, Date), sorted, idempotent
- [x] A provisional same-day rate is replaced by a later value
- [x] `latest_fx.csv` holds the newest row per pair
- [x] Failures isolated: FX and prices are written independently

---

## Task 3: Wiring, backfill and docs

### Acceptance Criteria
- [x] `fx_pairs.txt` committed with the four pairs
- [x] Daily run writes FX after prices
- [x] Backfill rebuilds FX with the same rule
- [x] README, AGENTS.md and api_reference.md document direction and files
