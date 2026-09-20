# Tasks: History Backfill and Rebuild

**Spec**: SPEC-006
**Status**: ✅ Complete
**Created**: 2026-09-20

---

## Task Overview

Each task follows RED-GREEN-REFACTOR. Tests are written before implementation.

**Total Tasks**: 4

---

## Task 1: Argument parsing

### Acceptance Criteria
- [x] `--backfill` and `--from` accepted
- [x] `--from` required with `--backfill`
- [x] Malformed or future `--from` rejected with a clear message
- [x] `--backfill` and `--history` rejected together

---

## Task 2: Rebuild rule

### Acceptance Criteria
- [x] Successful instrument: rows from the start date are deleted, then fetched quotes inserted
- [x] A carry-forward row on a date the source does not report is removed
- [x] Failed instrument: existing rows untouched, failure recorded
- [x] Rows before the start date preserved
- [x] Rows for unconfigured identifiers preserved
- [x] Aliased instrument written under every identifier from one fetch
- [x] Second run byte-identical
- [x] Derived files regenerated from the rebuilt history

---

## Task 3: Report and sanity checks

### Acceptance Criteria
- [x] Per-identifier report: before, deleted, inserted, first, last, currency, status
- [x] Written to `$GITHUB_STEP_SUMMARY` when set
- [x] Non-zero exit if any instrument failed, after writing
- [x] Warning when consecutive prices differ by more than a factor of 50
- [x] Warning when a split falls inside the requested range

---

## Task 4: Workflow, live rebuild and docs

### Acceptance Criteria
- [x] `backfill.yml` with `workflow_dispatch` and a `from_date` input
- [x] Shared concurrency group with `scrape.yml`
- [x] Live rebuild run and committed
- [x] README and AGENTS.md document the mode
