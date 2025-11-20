# Tasks: [Feature Name]

**Spec**: SPEC-XXX  
**Status**: 📋 Planned  
**Created**: YYYY-MM-DD

---

## Task Overview

[Brief description of how the work is broken down]

**Total Tasks**: [Number]  
**Completed**: 0  
**Estimated Time**: [X hours/days]

---

## Task 1: [Task Name]

**Status**: 📋 Planned  
**Time Estimate**: [X hours]  
**Dependencies**: None

### Description
[Clear description of what this task accomplishes]

### Acceptance Criteria
- [ ] [Specific criterion 1]
- [ ] [Specific criterion 2]
- [ ] [Specific criterion 3]

### Steps
1. [Step 1]
2. [Step 2]
3. [Step 3]

### TDD Cycle

#### RED Phase
[Describe the failing test to write]

```python
def test_[feature_name](self):
    """Test [what is being tested]."""
    # This will fail because [reason]
    [test code]
```

**Commit**: `RED: [description] (SPEC-XXX)`

#### GREEN Phase
[Describe the minimal implementation]

```python
def [function_name]([parameters]):
    """[Docstring]."""
    [minimal implementation]
```

**Commit**: `GREEN: [description] (SPEC-XXX)`

#### REFACTOR Phase
[Describe improvements to make]

```python
def [function_name]([parameters]):
    """[Improved docstring]."""
    [improved implementation]
```

**Commit**: `REFACTOR: [description] (SPEC-XXX)`

---

## Task 2: [Task Name]

**Status**: 📋 Planned  
**Time Estimate**: [X hours]  
**Dependencies**: Task 1

### Description
[Clear description of what this task accomplishes]

### Acceptance Criteria
- [ ] [Specific criterion 1]
- [ ] [Specific criterion 2]
- [ ] [Specific criterion 3]

### Steps
1. [Step 1]
2. [Step 2]
3. [Step 3]

### TDD Cycle

#### RED Phase
[Describe the failing test to write]

**Commit**: `RED: [description] (SPEC-XXX)`

#### GREEN Phase
[Describe the minimal implementation]

**Commit**: `GREEN: [description] (SPEC-XXX)`

#### REFACTOR Phase
[Describe improvements to make]

**Commit**: `REFACTOR: [description] (SPEC-XXX)`

---

## Task 3: [Task Name]

**Status**: 📋 Planned  
**Time Estimate**: [X hours]  
**Dependencies**: Task 2

### Description
[Clear description of what this task accomplishes]

### Acceptance Criteria
- [ ] [Specific criterion 1]
- [ ] [Specific criterion 2]
- [ ] [Specific criterion 3]

### Steps
1. [Step 1]
2. [Step 2]
3. [Step 3]

### TDD Cycle

#### RED Phase
[Describe the failing test to write]

**Commit**: `RED: [description] (SPEC-XXX)`

#### GREEN Phase
[Describe the minimal implementation]

**Commit**: `GREEN: [description] (SPEC-XXX)`

#### REFACTOR Phase
[Describe improvements to make]

**Commit**: `REFACTOR: [description] (SPEC-XXX)`

---

## Task 4: [Task Name]

**Status**: 📋 Planned  
**Time Estimate**: [X hours]  
**Dependencies**: Task 3

### Description
[Clear description of what this task accomplishes]

### Acceptance Criteria
- [ ] [Specific criterion 1]
- [ ] [Specific criterion 2]
- [ ] [Specific criterion 3]

### Steps
1. [Step 1]
2. [Step 2]
3. [Step 3]

### TDD Cycle

#### RED Phase
[Describe the failing test to write]

**Commit**: `RED: [description] (SPEC-XXX)`

#### GREEN Phase
[Describe the minimal implementation]

**Commit**: `GREEN: [description] (SPEC-XXX)`

#### REFACTOR Phase
[Describe improvements to make]

**Commit**: `REFACTOR: [description] (SPEC-XXX)`

---

## Task 5: Documentation and Validation

**Status**: 📋 Planned  
**Time Estimate**: [X hours]  
**Dependencies**: All previous tasks

### Description
Update documentation and validate the complete implementation.

### Acceptance Criteria
- [ ] All documentation updated
- [ ] All tests pass
- [ ] Coverage maintained at 90%+
- [ ] Code follows constitution standards
- [ ] Implementation status updated

### Steps
1. Update README.md
2. Update AGENTS.md
3. Update implementation_status.md
4. Add code comments
5. Run full test suite
6. Verify coverage
7. Manual validation

### Commit Message
```
docs: Update documentation for [feature name] (SPEC-XXX)

- Update README with [changes]
- Update AGENTS.md with [changes]
- Mark SPEC-XXX complete in implementation_status.md
- Add code comments explaining [feature]

Co-authored-by: Ona <no-reply@ona.com>
```

---

## Summary

### Task Checklist

- [ ] Task 1: [Name]
- [ ] Task 2: [Name]
- [ ] Task 3: [Name]
- [ ] Task 4: [Name]
- [ ] Task 5: Documentation and Validation

### Estimated Timeline

| Task | Estimate | Dependencies |
|------|----------|--------------|
| Task 1 | [X hrs] | None |
| Task 2 | [X hrs] | Task 1 |
| Task 3 | [X hrs] | Task 2 |
| Task 4 | [X hrs] | Task 3 |
| Task 5 | [X hrs] | All |
| **Total** | **[X hrs]** | |

### Expected Outcomes

- [ ] [Outcome 1]
- [ ] [Outcome 2]
- [ ] [Outcome 3]

### Files to Modify

- `[file1.py]` - [Changes]
- `[file2.py]` - [Changes]
- `[test_file.py]` - [New tests]
- `requirements.txt` - [New dependencies]
- `README.md` - [Documentation]
- `AGENTS.md` - [Documentation]

### Test Coverage

- **Target**: 90%+ overall
- **New Code**: 100% coverage
- **Tests to Add**: [Number] unit tests, [Number] functional tests

---

## Guidelines

### Task Size
- Each task should be 1-4 hours
- If larger, break into smaller tasks
- Each task = one TDD cycle (RED-GREEN-REFACTOR)

### Task Dependencies
- List dependencies clearly
- Tasks should be sequential when possible
- Parallel tasks should be independent

### Commit Messages
- Use RED/GREEN/REFACTOR prefixes
- Reference SPEC-XXX in all commits
- Include Co-authored-by: Ona <no-reply@ona.com>

### Testing
- Write tests BEFORE implementation (RED)
- Implement minimal code to pass (GREEN)
- Improve code while keeping tests green (REFACTOR)

---

**Tasks Status**: 📋 Planned  
**Next Steps**: Begin Task 1 with RED phase
