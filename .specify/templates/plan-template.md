# Technical Plan: [Feature Name]

**Spec**: SPEC-XXX  
**Status**: 🤔 Draft  
**Created**: YYYY-MM-DD

---

## Overview

[Brief summary of the technical approach. What will be built and how?]

## Technical Approach

### [Component/Area 1]

**Approach**: [Describe the technical approach]

**Rationale**: [Why this approach?]

**Alternatives Considered**:
- **Option A**: [Description] - [Why not chosen]
- **Option B**: [Description] - [Why not chosen]

### [Component/Area 2]

**Approach**: [Describe the technical approach]

**Rationale**: [Why this approach?]

**Alternatives Considered**:
- **Option A**: [Description] - [Why not chosen]
- **Option B**: [Description] - [Why not chosen]

## Architecture Changes

### New Components

**Component Name**: [Name]
- **Purpose**: [What it does]
- **Location**: [File/module path]
- **Interfaces**: [Public API]
- **Dependencies**: [What it depends on]

### Modified Components

**Component Name**: [Name]
- **Changes**: [What will change]
- **Impact**: [How it affects other components]
- **Backwards Compatibility**: [Yes/No - explain]

### Removed Components

**Component Name**: [Name]
- **Reason**: [Why removing]
- **Migration Path**: [How to migrate away]

## Data Flow

```
[Describe or diagram the data flow]

Input → Component A → Component B → Output
```

## Dependencies

### New Dependencies

**Library/Service**: [Name]
- **Version**: [Version requirement]
- **Purpose**: [Why needed]
- **License**: [License type]
- **Alternatives**: [Other options considered]

### Updated Dependencies

**Library/Service**: [Name]
- **Current Version**: [Version]
- **New Version**: [Version]
- **Reason**: [Why updating]
- **Breaking Changes**: [Any breaking changes?]

## Error Handling

### Error Scenarios

1. **[Error Type 1]**
   - **Cause**: [What causes this error]
   - **Response**: [How system responds]
   - **User Impact**: [What user sees]
   - **Recovery**: [How to recover]

2. **[Error Type 2]**
   - **Cause**: [What causes this error]
   - **Response**: [How system responds]
   - **User Impact**: [What user sees]
   - **Recovery**: [How to recover]

### Error Contract

Follow constitution section 4; do not invent a format per feature:

- A fetcher that cannot return a dated value **raises** (`ValueError` when the source
  answered with nothing usable). It never returns an error string or a made-up row
- Every fetch goes through `fetch_with_retries()`, which retries up to
  `MAX_PRICE_ATTEMPTS` and returns `(None, <error text>)` after the last attempt
- Failures **collect on the result object** (`<identifier>: <error>`, or the step's
  name for a step that fails as a whole); the run writes everything it obtained,
  prints the failures and only then exits non-zero
- **No error text is ever written to a data file**

```python
# Example: a source that answered with nothing usable
raise ValueError(f"{label}: no distributions table")
```

## Testing Strategy

### Unit Tests

**Test Category**: [Category name]
- **What to test**: [Specific functionality]
- **Mocking**: [What to mock]
- **Coverage target**: [Percentage]

### Integration Tests

**Test Category**: [Category name]
- **What to test**: [Component interactions]
- **Setup required**: [Test environment needs]
- **Expected behavior**: [What should happen]

### Functional Tests

**Test Category**: [Category name]
- **What to test**: [End-to-end scenarios]
- **Real dependencies**: [What's not mocked]
- **Success criteria**: [How to validate]

### Coverage Target

- **Overall**: 90% minimum
- **`scrape_fund_price.py`**: 95% minimum (both gates are enforced in CI)
- **New Code**: 100% coverage
- **Modified Code**: Maintain or improve existing coverage

## Performance Considerations

### Expected Performance

- **Metric 1**: [Expected value]
- **Metric 2**: [Expected value]
- **Metric 3**: [Expected value]

### Benchmarks

[Provide baseline or target benchmarks]

```
Operation X: < Y seconds
Memory usage: < Z MB
```

### Optimization Opportunities

- **Opportunity 1**: [Description]
- **Opportunity 2**: [Description]

## Security Considerations

### Security Requirements

- **Requirement 1**: [Description]
- **Requirement 2**: [Description]

### Threat Model

| Threat | Impact | Mitigation |
|--------|--------|------------|
| [Threat 1] | [High/Medium/Low] | [How to mitigate] |
| [Threat 2] | [High/Medium/Low] | [How to mitigate] |

### Data Privacy

- [Privacy consideration 1]
- [Privacy consideration 2]

## Deployment Considerations

### Local Development

[Steps for local development setup]

1. [Step 1]
2. [Step 2]
3. [Step 3]

### CI/CD Changes

[Any changes needed to GitHub Actions or other CI/CD]

- [Change 1]
- [Change 2]

### Backwards Compatibility

**Breaking Changes**: [Yes/No]

[If yes, describe breaking changes and migration path]

### Rollback Plan

[How to rollback if issues arise]

1. [Rollback step 1]
2. [Rollback step 2]
3. [Rollback step 3]

**Risk Level**: [Low/Medium/High]

## Monitoring and Validation

### Success Metrics

- **Metric 1**: [How to measure success]
- **Metric 2**: [How to measure success]
- **Metric 3**: [How to measure success]

### Validation Steps

1. [Validation step 1]
2. [Validation step 2]
3. [Validation step 3]

### Monitoring

[What to monitor in production]

- [Metric to monitor]
- [Alert conditions]

## Documentation Updates

### Files to Update

1. **[File name]**
   - [What to update]
   - [Why]

2. **[File name]**
   - [What to update]
   - [Why]

### New Documentation

- **[Document name]**: [Purpose]
- **[Document name]**: [Purpose]

## Timeline and Milestones

- [ ] Dependency setup
- [ ] Component A implementation
- [ ] Component B implementation
- [ ] Integration
- [ ] Testing
- [ ] Documentation
- [ ] Review and validation

**Estimated Time**: [X hours/days]

## Open Questions

1. **[Question 1]**
   - **Context**: [Why this is a question]
   - **Options**: [Possible answers]
   - **Decision needed by**: [When]

2. **[Question 2]**
   - **Context**: [Why this is a question]
   - **Options**: [Possible answers]
   - **Decision needed by**: [When]

## Future Enhancements

[Potential improvements that are out of scope for this spec but worth noting]

1. **[Enhancement 1]**: [Description]
2. **[Enhancement 2]**: [Description]

## References

- [Technical documentation]
- [API references]
- [Related specifications]

---

**Plan Status**: 🤔 Draft  
**Next Steps**: Break into tasks (tasks.md)
