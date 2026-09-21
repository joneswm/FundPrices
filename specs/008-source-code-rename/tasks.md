# Tasks: Rename the GF Source Code to YA

**Spec**: SPEC-008
**Status**: 🔄 In Progress
**Created**: 2026-09-21

---

## Task Overview

RED-GREEN-REFACTOR. Tests first.

**Total Tasks**: 2

---

## Task 1: Canonical source codes

### Acceptance Criteria
- [ ] `canonical_source()` maps `GF` to `YA` and warns, naming the line
- [ ] `YA`, `FT`, `YH` and `MS` pass through unchanged
- [ ] `read_fund_specs()` returns canonical sources
- [ ] `YA` routes to the API and needs no browser
- [ ] `YH` still resolves to the scraping configuration

---

## Task 2: Config and docs

### Acceptance Criteria
- [ ] `funds.txt`: 20 `GF,` lines become `YA,`
- [ ] README, AGENTS.md, api_reference.md updated
- [ ] The Google URL note removed from the README
- [ ] Historical specs and the archive left alone
