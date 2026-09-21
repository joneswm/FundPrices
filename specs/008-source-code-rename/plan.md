# Technical Plan: Rename the GF Source Code to YA

**Spec**: SPEC-008
**Status**: ✅ Complete
**Created**: 2026-09-21

---

## Overview

A configuration-level rename with a deprecation alias.

## Technical Approach

### Canonicalisation at parse time

```python
SOURCE_ALIASES = {"GF": "YA"}   # GF meant Google Finance; it has been Yahoo since 2025-10-19

def canonical_source(code, line_number=None) -> str
```

`read_fund_specs()` canonicalises each line's source, warning once per line when a
deprecated code is used. Everything downstream sees only the canonical code, so
`scrape_fund_quotes()` and `source_requires_browser()` need a one-word change rather
than alias handling of their own.

### Why the alias lives in the parser

The alternative, accepting `GF` inside `scrape_fund_quotes()`, would leave every other
call site to remember the alias. Canonicalising once at the edge keeps the rest of the
code aware of exactly one spelling.

### Architecture Changes

| Component | Change |
|---|---|
| `canonical_source()` | New; maps deprecated codes and warns |
| `read_fund_specs()` | Canonicalises, so `FundSpec.source` is always canonical |
| `scrape_fund_quotes()` | `"GF"` becomes `"YA"` |
| `source_requires_browser()` | `("GF", "FT")` becomes `("YA", "FT")` |
| `funds.txt` | 20 lines rewritten |

## Data Flow

```
funds.txt line "GF,QQQ"
   ↓ read_fund_specs -> canonical_source("GF") -> warns, returns "YA"
FundSpec(source="YA", lookup_id="QQQ")
   ↓ unchanged from here on
```

## Testing Strategy

Parser tests for both spellings, a routing test proving `YA` uses the API and no
browser, and a test that `YH` is not swept into the alias. Existing `GF` fixtures move
to `YA`, with a couple kept deliberately on `GF` to cover the deprecation path.

## Backwards Compatibility

An existing `funds.txt` keeps working and warns. Stored data is untouched, since no
output file records the source code.

## Rollback Plan

Revert the commit. A `funds.txt` written with `YA` would then fail to parse, so a
rollback means reverting that file too; it is one commit either way.
