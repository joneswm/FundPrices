# SPEC-009: One-Off Imports for Closed Holdings

**Status**: ✅ Complete
**Created**: 2026-09-21
**Type**: Feature
**Tracking**: [#73](https://github.com/joneswm/FundPrices/issues/73)

> Written retrospectively. The work was driven from issue #73, which holds the source
> research; this spec records the requirements and decisions as built so the feature
> has the same standing as the others.

---

## Context

A downstream portfolio system had price windows filled by interpolation, flat
extrapolation and proxies, because the instruments concerned were never in this
repository. All of them are holdings that have since been sold, merged or liquidated.

## User Need

**As** the owner of the portfolio history
**I want** real market prices for instruments I no longer hold
**So that** synthetic values can be replaced, without pricing dead instruments every night

## Problem Statement

- `funds.txt` means "price this every day, forever". There was no way to say "price this
  window once"
- Several of these funds have been renamed, merged or liquidated, so the identifier the
  history is published under differs from the symbol a source must be asked for
- A window fetched once and then trusted has nothing that re-runs to expose a bad source

## Proposed Solution

A separate configuration file, `closed_holdings.txt`, and a separate mode,
`--import-closed`, that upserts each configured window into `prices_history.csv` and
writes nothing else.

## Success Criteria

### Functional Requirements

- **FR1**: `closed_holdings.txt` lines are
  `<identifier>,<source>,<lookup_id>,<currency>,<start>,<end>`, with `#` comments. A
  malformed line, an invalid or reversed date, or a repeated identifier raises
  `ValueError` naming the line, before any network call
- **FR2**: No identifier may appear in both `closed_holdings.txt` and `funds.txt`
  (enforced by a test over the committed configuration, not at run time)
- **FR3**: `--import-closed` stores rows under `identifier`, fetched using `lookup_id`
- **FR4**: Only quotes with `start <= date <= end` are stored, whatever the source
  returns and whether it treats an end date as inclusive or exclusive
- **FR5**: The configured currency is stored. If the source reports a different one the
  holding is skipped and a failure recorded
- **FR6**: The import upserts and never deletes, and is idempotent
- **FR7**: The import writes `prices_history.csv` only
- **FR8**: Closed holdings never appear in `latest_prices.csv`, the 90-day rolling
  window, the `.price` files or the daily summary, from any mode
- **FR9**: A rebuild (`--backfill`) preserves every imported row
- **FR10**: One failing holding does not stop the others; the run exits non-zero
- **FR11**: A new `IV` source fetches dated closes from investing.com, preserving the
  source's precision

### Non-Functional Requirements

- **NFR1**: No synthetic rows. A window ends on the last day the instrument actually
  traded, even if the holding nominally ran longer
- **NFR2**: The evidence for each source choice is recorded beside the configuration
- **NFR3**: `IV` is an undocumented endpoint and must never be put on a schedule

## Out of Scope

- A workflow for the import: it is a one-off, run locally and committed
- Bridging a merger gap by re-pricing in the successor fund; the closure facts are
  recorded so a downstream system can do so
- Data from sources whose terms forbid redistribution, this repository being public

## Decisions

| Decision | Reason |
|----------|--------|
| Separate file rather than a flag in `funds.txt` | The daily run reads only `funds.txt`, so separation is what guarantees it cannot reach a dead instrument |
| Currency configured **and** asserted | FT's ISIN lookup resolved an LSE USD holding to its German EUR line and returned a full window of plausible quotes |
| Fetch one day past `end`, then clip | Yahoo treats the end date as exclusive; FT and investing.com as inclusive. The first import lost the last day of a window |
| Rolling window limited to currently priced funds | A closed holding can have real prices inside the last 90 days (FBTC ran to 2026-08-17) and would otherwise leak into the daily output |
| Rebuild promotes configured funds only | Otherwise a rebuild adds closed holdings to `latest_prices.csv` and the next daily run removes them |

## Validation Performed

Each source was checked against a second one before being trusted:

- **BKCH, R2SC, SPOG, FBTC** (Yahoo): no zero-volume carry-forward runs; BKCH and R2SC
  agree with FT to within 0.14% and 0.011%
- **CNDX** (Yahoo, not FT): FT adds four rows dated on UK bank holidays, when the LSE
  was shut
- **BMV7ZZ3** (FT, not Yahoo): Yahoo repeats one close with zero volume for 60 trading
  days from the fund's rename
- **BN4MYX3, JFM50541951** (investing.com): the latter matched an independent
  Morningstar export on all 385 overlapping days exactly. justETF was rejected after
  measuring a median 1.6% error against known-good series
