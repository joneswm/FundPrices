# Tasks: Rename the GF Source Code to YA

**Spec**: SPEC-008
**Status**: ✅ Complete
**Created**: 2026-09-21

---

## Task Overview

RED-GREEN-REFACTOR. Tests first.

**Total Tasks**: 2

---

## Task 1: Canonical source codes

### Acceptance Criteria
- [x] `canonical_source()` maps `GF` to `YA` and warns, naming the line
- [x] `YA`, `FT`, `YH` and `MS` pass through unchanged
- [x] `read_fund_specs()` returns canonical sources
- [x] `YA` routes to the API and needs no browser
- [x] `YH` still resolves to the scraping configuration

---

## Task 2: Config and docs

### Acceptance Criteria
- [x] `funds.txt`: 20 `GF,` lines become `YA,`
- [x] README, AGENTS.md, api_reference.md updated
- [x] The Google URL note removed from the README
- [x] Historical specs and the archive left alone
