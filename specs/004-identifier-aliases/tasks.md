# Tasks: Identifier Aliases

**Spec**: SPEC-004
**Status**: ✅ Complete
**Created**: 2026-09-20

---

## Task Overview

Each task follows RED-GREEN-REFACTOR. Tests are written before implementation.

**Total Tasks**: 3

---

## Task 1: Config parser with validation

### Acceptance Criteria
- [x] `FundSpec` with `source`, `lookup_id`, `aliases` and a `publish_ids` property
- [x] `read_fund_specs()` parses 2-field and 3-field lines, `;`-separated aliases,
      blank lines, full-line and trailing `#` comments
- [x] `ValueError` naming the line number for: too few fields, empty source or id,
      empty alias, self-referencing alias, duplicate identifier anywhere in the file
- [x] `read_fund_ids()` still returns `(source, lookup_id)` tuples

### TDD Cycle
RED: parser tests for each grammar and error case.
GREEN: implement the parser.
REFACTOR: document why the comment handling is new.

---

## Task 2: Publish fan-out

### Acceptance Criteria
- [x] One fetch per fund regardless of alias count, asserted with a mock call count
- [x] Every quote produces one row per publish identifier, identical in all but name
- [x] One `latest_<id>.price` file per identifier
- [x] Fallback tries the lookup id, then each alias in order, and publishes the carried
      row under every identifier
- [x] A fund appears once in `failures`, not once per alias
- [x] `scrape_funds()` still accepts plain 2-tuples

---

## Task 3: Config switch and docs

### Acceptance Criteria
- [x] `funds.txt`: `MS,JFM0003373` → `GF,0P00000YAN,JFM0003373`
- [x] `main()` uses `read_fund_specs()` and fails fast on a bad config
- [x] README, AGENTS.md and api_reference.md document the syntax
- [x] Docs note that `GF` means "Yahoo Finance API"
- [x] Live run writes both `.price` files with the same value
