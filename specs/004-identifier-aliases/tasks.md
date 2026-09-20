# Tasks: Identifier Aliases

**Spec**: SPEC-004
**Status**: 🔄 In Progress
**Created**: 2026-09-20

---

## Task Overview

Each task follows RED-GREEN-REFACTOR. Tests are written before implementation.

**Total Tasks**: 3

---

## Task 1: Config parser with validation

### Acceptance Criteria
- [ ] `FundSpec` with `source`, `lookup_id`, `aliases` and a `publish_ids` property
- [ ] `read_fund_specs()` parses 2-field and 3-field lines, `;`-separated aliases,
      blank lines, full-line and trailing `#` comments
- [ ] `ValueError` naming the line number for: too few fields, empty source or id,
      empty alias, self-referencing alias, duplicate identifier anywhere in the file
- [ ] `read_fund_ids()` still returns `(source, lookup_id)` tuples

### TDD Cycle
RED: parser tests for each grammar and error case.
GREEN: implement the parser.
REFACTOR: document why the comment handling is new.

---

## Task 2: Publish fan-out

### Acceptance Criteria
- [ ] One fetch per fund regardless of alias count, asserted with a mock call count
- [ ] Every quote produces one row per publish identifier, identical in all but name
- [ ] One `latest_<id>.price` file per identifier
- [ ] Fallback tries the lookup id, then each alias in order, and publishes the carried
      row under every identifier
- [ ] A fund appears once in `failures`, not once per alias
- [ ] `scrape_funds()` still accepts plain 2-tuples

---

## Task 3: Config switch and docs

### Acceptance Criteria
- [ ] `funds.txt`: `MS,JFM0003373` → `GF,0P00000YAN,JFM0003373`
- [ ] `main()` uses `read_fund_specs()` and fails fast on a bad config
- [ ] README, AGENTS.md and api_reference.md document the syntax
- [ ] Docs note that `GF` means "Yahoo Finance API"
- [ ] Live run writes both `.price` files with the same value
