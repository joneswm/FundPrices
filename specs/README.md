# FundPrices Specifications

This directory contains all Spec Kit specifications for the FundPrices project.

## Active Specifications

### SPEC-001: Yahoo Finance API Integration
**Status**: ✅ Complete  
**Location**: [001-yahoo-finance-api/](001-yahoo-finance-api/)  
**Description**: Replace Google Finance web scraping with Yahoo Finance API for more reliable stock/fund price data.

## Specification Workflow

All new features follow the Spec-Driven Development (SDD) workflow:

### 1. SPECIFY
Define **what** to build and **why**:
- User needs and problems
- Success criteria
- Scope and constraints

**Output**: `spec.md`

### 2. CLARIFY (Optional)
Resolve ambiguities:
- Edge cases
- Integration points
- Dependencies
- Open questions

**Output**: `clarify.md` or notes in `spec.md`

### 3. PLAN
Define **how** to build it:
- Technical approach
- Architecture changes
- Technology choices
- Constraints and trade-offs

**Output**: `plan.md`

### 4. TASKS
Break into manageable units:
- Small, discrete tasks
- Each task = one TDD cycle
- Clear acceptance criteria
- Logical sequence

**Output**: `tasks.md`

### 5. IMPLEMENT
Execute with TDD discipline:
- RED: Write failing test
- GREEN: Implement minimal code
- REFACTOR: Improve code
- Review and validate

**Output**: Working code + tests

## Creating New Specifications

### Quick Start

1. **Create spec directory**:
   ```bash
   mkdir -p specs/00X-feature-name
   cd specs/00X-feature-name
   ```

2. **Copy templates**:
   ```bash
   cp ../../.specify/templates/spec-template.md spec.md
   cp ../../.specify/templates/plan-template.md plan.md
   cp ../../.specify/templates/tasks-template.md tasks.md
   ```

3. **Fill in templates** following the workflow

4. **Update tracking**:
   - Add to this README
   - Update `docs/user_stories/implementation_status.md`

### Naming Convention

```
specs/
└── XXX-feature-name/
    ├── spec.md           # SPECIFY phase
    ├── clarify.md        # CLARIFY phase (optional)
    ├── plan.md           # PLAN phase
    ├── tasks.md          # TASKS phase
    └── implementation.md # IMPLEMENT phase notes (optional)
```

**Spec ID Format**: `XXX` = 3-digit number (001, 002, 003, ...)

**Feature Name**: Lowercase with hyphens (e.g., `yahoo-finance-api`, `bloomberg-integration`)

## Specification Status

| Status | Meaning |
|--------|---------|
| ✅ Complete | Fully implemented and tested |
| 🔄 In Progress | Currently being worked on |
| 📋 Planned | Spec created, not started |
| 🤔 Draft | Specification in progress |
| ⏸️ Paused | Work temporarily stopped |
| ❌ Cancelled | Spec abandoned |

## Guidelines

### Spec Quality Standards

1. **Clear User Need**: Every spec must answer "who needs this and why?"
2. **Measurable Success**: Define concrete success criteria
3. **Scoped Appropriately**: Not too big, not too small
4. **Technically Feasible**: Plan must be realistic
5. **Task Breakdown**: Tasks should be 1-4 hours each

### TDD Integration

All implementation follows **mandatory TDD workflow**:
- Each task becomes a RED-GREEN-REFACTOR cycle
- Tests written before code
- 90%+ coverage maintained
- See: `constitution.md` for TDD requirements

### Commit Messages

Reference spec ID in commits:
```
RED: Add test for Bloomberg price scraping (SPEC-002)
GREEN: Implement Bloomberg scraper (SPEC-002)
REFACTOR: Extract common scraping logic (SPEC-002)

Co-authored-by: Ona <no-reply@ona.com>
```

## Templates

Templates are available in `.specify/templates/`:
- `spec-template.md` - Specification template
- `plan-template.md` - Technical plan template
- `tasks-template.md` - Task breakdown template

## Related Documentation

- [Constitution](../constitution.md) - Project principles and standards
- [Spec Kit Assessment](../docs/technical_documentation/spec_kit_assessment.md) - Migration plan
- [TDD Workflow](../docs/technical_documentation/tdd_workflow.md) - TDD guidelines
- [Implementation Status](../docs/user_stories/implementation_status.md) - Overall tracking

## Questions?

See the [Spec Kit Assessment](../docs/technical_documentation/spec_kit_assessment.md) for detailed information about the Spec Kit approach and how it integrates with our TDD workflow.
