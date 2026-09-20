# Tasks: History Backfill and Rebuild

**Spec**: SPEC-006
**Status**: 🔄 In Progress
**Created**: 2026-09-20

---

## Task Overview

Each task follows RED-GREEN-REFACTOR. Tests are written before implementation.

**Total Tasks**: 4

---

## Task 1: Argument parsing

### Acceptance Criteria
- [ ] `--backfill` and `--from` accepted
- [ ] `--from` required with `--backfill`
- [ ] Malformed or future `--from` rejected with a clear message
- [ ] `--backfill` and `--history` rejected together

---

## Task 2: Rebuild rule

### Acceptance Criteria
- [ ] Successful instrument: rows from the start date are deleted, then fetched quotes inserted
- [ ] A carry-forward row on a date the source does not report is removed
- [ ] Failed instrument: existing rows untouched, failure recorded
- [ ] Rows before the start date preserved
- [ ] Rows for unconfigured identifiers preserved
- [ ] Aliased instrument written under every identifier from one fetch
- [ ] Second run byte-identical
- [ ] Derived files regenerated from the rebuilt history

---

## Task 3: Report and sanity checks

### Acceptance Criteria
- [ ] Per-identifier report: before, deleted, inserted, first, last, currency, status
- [ ] Written to `$GITHUB_STEP_SUMMARY` when set
- [ ] Non-zero exit if any instrument failed, after writing
- [ ] Warning when consecutive prices differ by more than a factor of 50
- [ ] Warning when a split falls inside the requested range

---

## Task 4: Workflow, live rebuild and docs

### Acceptance Criteria
- [ ] `backfill.yml` with `workflow_dispatch` and a `from_date` input
- [ ] Shared concurrency group with `scrape.yml`
- [ ] Live rebuild run and committed
- [ ] README and AGENTS.md document the mode
