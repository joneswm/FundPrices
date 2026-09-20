# User Stories

**Status**: Migrated to Spec Kit (2024-11-20) — migration complete

> **Task tracking lives in [GitHub Issues](https://github.com/joneswm/FundPrices/issues).**
> Everything in this directory is a historical record of completed work.

---

## Current Status

This directory now contains only the **implementation status tracking** document. The original user story files have been archived.

### Active File

- **implementation_status.md** - Historical record of completed legacy user stories (US-XXX) and Spec Kit specifications (SPEC-XXX). No longer updated for new work — use GitHub Issues.

---

## What Happened to User Stories?

As of 2024-11-20, the project migrated to **Spec Kit** for spec-driven development. The original user story files have been moved to:

```
docs/archive/user_stories/
├── README.md              # Archive overview
├── automation.md          # 6 automation user stories
├── configuration.md       # 6 configuration user stories
├── core_functionality.md  # 6 core functionality user stories
├── historical_data.md     # 3 historical data user stories
└── testing.md             # 6 testing user stories
```

**All 27 user stories were completed (100%) before archiving.**

---

## New Feature Development

For new features, use the **Spec Kit** approach:

### Spec Kit Workflow

0. **ISSUE**: Open a [GitHub Issue](https://github.com/joneswm/FundPrices/issues/new) describing the work

1. **SPECIFY**: Create `specs/XXX-feature-name/spec.md` (reference the issue number)
   - Define what to build and why
   - User needs and success criteria

2. **CLARIFY**: Resolve ambiguities (optional)
   - Document questions and answers

3. **PLAN**: Create `plan.md`
   - Technical approach and architecture
   - Dependencies and constraints

4. **TASKS**: Create `tasks.md`
   - Break into small, manageable tasks
   - Each task = one TDD cycle

5. **IMPLEMENT**: Execute with TDD
   - RED: Write failing test
   - GREEN: Implement minimal code
   - REFACTOR: Improve code

### Resources

- **Templates**: `.specify/templates/`
- **Examples**: `specs/002-rolling-price-history/` (written spec-first), `specs/001-yahoo-finance-api/` (retrospective)
- **Guidelines**: `specs/README.md`
- **Principles**: `constitution.md`

---

## Why Spec Kit?

The Spec Kit approach provides:
- ✅ **Better structure**: Clear SPECIFY → PLAN → TASKS → IMPLEMENT workflow
- ✅ **AI collaboration**: Constitution guides AI behavior
- ✅ **Traceability**: Every change traces to spec → plan → task
- ✅ **Scalability**: Better for complex features and team growth
- ✅ **TDD integration**: Preserves mandatory RED-GREEN-REFACTOR cycle

---

## Historical Reference

To view the original user stories:
- See `docs/archive/user_stories/`
- All 27 stories documented with acceptance criteria
- Complete implementation history preserved

---

## Questions?

- **Current status / open work**: See [GitHub Issues](https://github.com/joneswm/FundPrices/issues)
- **Historical status**: See `implementation_status.md` in this directory
- **New features**: See `specs/README.md`
- **Archived stories**: See `docs/archive/user_stories/README.md`
- **Spec Kit background**: See `docs/archive/spec_kit_assessment.md` (archived)
- **Spec Kit workflow**: See `specs/README.md`
