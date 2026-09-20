# Technical Plan: Identifier Aliases

**Spec**: SPEC-004
**Status**: ✅ Complete
**Created**: 2026-09-20

---

## Overview

Separate a fund's **lookup identifier** (what the source is asked for) from its
**publish identifiers** (what appears in the output files).

## Technical Approach

### Config record

```python
class FundSpec(NamedTuple):
    source: str
    lookup_id: str
    aliases: tuple = ()

    @property
    def publish_ids(self):
        return (self.lookup_id,) + tuple(self.aliases)
```

### Parser

```python
def read_fund_specs(filename) -> list[FundSpec]
def read_fund_ids(filename) -> list[tuple]     # compatibility wrapper
```

Line grammar, after stripping `#` comments and whitespace:

```
SOURCE , LOOKUP_ID [ , ALIAS [ ; ALIAS ... ] ]
```

`AGENTS.md` has always documented inline comments (`FT,GB00B1FXTF86  # Financial Times`)
but the parser never supported them, so they would have become part of the identifier.
The new parser handles them.

### Validation

All checks run before any network call, and each error names its line number:

| Condition | Rejected because |
|---|---|
| fewer than 2 fields, or empty source / lookup id | unusable line |
| empty alias (`GF,ABC,` or `GF,ABC,X;;Y`) | almost certainly a typo |
| alias equal to its own lookup id | would double-write the same identifier |
| identifier repeated anywhere in the file | would produce duplicate rows |

The last check also catches the duplicated `funds.txt` line that produced 206 duplicated
`IE0008368742` rows in the existing history.

### Architecture Changes

| Component | Change |
|---|---|
| `read_fund_specs()` | New parser with validation |
| `read_fund_ids()` | Wrapper returning `(source, lookup_id)` pairs |
| `scrape_funds()` | Accepts `FundSpec`s and plain 2-tuples; fans out per quote |
| Fallback | `read_last_known_row()` tried for lookup id, then each alias |
| `main()` | Uses `read_fund_specs()`, failing fast on a bad config |

### Data Flow

```
funds.txt line: GF,0P00000YAN,JFM0003373
   ↓ read_fund_specs()
FundSpec(source="GF", lookup_id="0P00000YAN", aliases=("JFM0003373",))
   ↓ one fetch on lookup_id
[Quote("2026-09-17", "192.43", "USD"), ...]
   ↓ fan out over publish_ids
["0P00000YAN", "2026-09-17", "192.43", "USD"]
["JFM0003373", "2026-09-17", "192.43", "USD"]
   ↓
history + latest + one .price file per identifier
```

## Testing Strategy

- Parser tested directly for each grammar and error case
- Fan-out asserted by mocking the fetcher and checking it is called **once**
- Fallback tested with a stored price under the alias only, which is the real day-one
  condition for this fund
- Backwards compatibility asserted by passing plain 2-tuples to `scrape_funds()`

## Backwards Compatibility

- Two-field lines parse exactly as before
- `read_fund_ids()` keeps its signature and return shape
- Output schema is unchanged; aliases add rows, not columns

## Rollback Plan

Revert the commit and restore `MS,JFM0003373` in `funds.txt`. History written under both
identifiers remains valid; the `0P00000YAN` rows simply stop updating.
