# SPEC-011: Dividend Pay Dates from the Issuer

**Status**: ✅ Built, on branch `pay-dates` (not yet merged)
**Created**: 2026-10-26
**Type**: Feature
**Tracking**: [#87](https://github.com/joneswm/FundPrices/issues/87) (option 2)
**Research**: [docs/research/dividend_pay_date_sources.md](../../docs/research/dividend_pay_date_sources.md)

> Extends SPEC-010. Yahoo gives the ex-date and the amount of a past dividend and nothing
> else, so the first scrape published 421 history rows and 13 upcoming rows with no pay
> date. This spec adds the issuer's own distribution table as a second source.

---

## Context

The research page compares thirteen candidate sources. The iShares UK product page is the
only one that is the issuer, reachable over plain HTTP and allowed by its `robots.txt`: it
carries ex-date, record date, pay date and amount for every distribution, equal to Yahoo's
wherever the two overlap. It covers the ten iShares distributing instruments, one of which
(`IE00B0M63516`) is priced from the FT and so has no dividend source at all today. The four
other instruments that pay (QQQ, GLTL.L, KNSL, 0639.HK) stay on Yahoo's calendar; the
research page says why and what would close the gap.

## User Need

**As** the owner of the portfolio
**I want** the real pay date, and the declared amount, on every dividend the issuer states
**So that** the receivable is shown for the day the money arrives, not a guess

## Proposed Solution

A new source code, `IS` (iShares UK), configured in a new file `dividend_sources.txt`, one
line per instrument. The daily run fetches each configured instrument's distribution table
and merges it into the two files of SPEC-010. `funds.txt` is not touched: its source code
says where a **price** comes from, an instrument has exactly one, while a dividend source
is an extra fact about an instrument that already has a price source (an FT-priced fund
can take its dividends from iShares).

## Files

### `dividend_sources.txt`

```
<identifier>,<source>,<source-id>
```

| Field | Rule |
|-------|------|
| `identifier` | An identifier published by `funds.txt` (lookup id or alias). A closed holding is not fetched, so it cannot be named |
| `source` | `IS` (case-insensitive) |
| `source-id` | For `IS`, the iShares UK product id: the number in the fund's URL, `https://www.ishares.com/uk/individual/en/products/<id>/...`, one per share class (digits, at most nine) |

```
IGLS.L,IS,251804
IE00B0M63516,IS,251853
```

Blank lines, full-line `#` comments and trailing comments are ignored. A missing file
means no entries. The shipped file lists the ten verified instruments (below).

### The two data files

**No column is added and none moves.** `dividends_history.csv` is
`Fund,ExDate,PayDate,Amount,Currency,Source` and `dividends_upcoming.csv` is
`Fund,ExDate,PayDate,Amount,Currency,Status,AsOf`, as in SPEC-010, so the downstream parser
reads them unchanged. The record date is read from the issuer and **not published**: the
downstream needs the ex-date (entitlement) and the pay date (cash), and a column is a
contract change that is better made when something needs it. `Source` gains the value `IS`.

## Success Criteria

### Functional Requirements

- **FR1**: `dividend_sources.txt` is validated in full before any network call, with
  `funds.txt` and `distributions.txt`. A line that is not three fields, an unknown source, a
  source id that is not 1 to 9 digits, an identifier that `funds.txt` does not publish, a
  repeated identifier, or two lines for one instrument (its lookup id and an alias) raises
  `ValueError` naming the line. A missing file means no entries
- **FR2**: For each configured instrument the daily run fetches
  `https://www.ishares.com/uk/individual/en/products/<id>` once (30 s timeout, retried by
  `fetch_with_retries()`, one second between instruments) and reads the table behind the
  page's "Distributions" section: ex-date, record date, payable date and total distribution
  for every distribution, newest first, plus the share class's currency when the page names
  it. A page with no such table (an accumulating class, or a page that changed) is an error
  for that instrument, not an empty table
- **FR3**: One instrument failing, by network, HTTP status or format, never stops the others
  or the rest of the run. It is reported with the SPEC-010 failures (the run exits non-zero
  once everything is written), prints `"<identifier>: pay dates: <error>"`, and the
  instrument keeps every row it had
- **FR4**: **Pay dates.** An issuer row whose ex-date is today or earlier is merged into
  `dividends_history.csv` on `(Fund, ExDate)`, for every alias. A stored row gains the
  issuer's `PayDate` and its `Source` becomes `IS`. A row the issuer has and the history
  lacks is inserted with `Source` `IS` (Yahoo misses some: INXG.L lacks 18). An issuer pay
  date that is not after its ex-date is treated as absent and the stored pay date is kept
- **FR5**: **Amount.** The issuer states an amount in the share class's currency in major
  units; the history holds Yahoo's amount in the instrument's price currency. The issuer's
  amount is converted to the stored row's currency (a `GBp` row takes `GBP` times 100, an
  equal currency is unchanged; anything else cannot be compared). **Yahoo's amount is kept
  when the two agree**, meaning they differ by no more than half a unit in the issuer's
  last decimal place (Yahoo's has more digits for a small amount in pence); **the issuer's
  wins when they differ**. An issuer amount that is zero or cannot be converted leaves the
  stored amount alone, and for a row the history lacks it means no row. A row inserted
  carries the instrument's price currency (the stored price's currency when the history has
  no row for it, the issuer's when neither is known)
- **FR6**: **A date a day out.** A stored `YA` row with no issuer row on its date, within
  three days of an issuer row and with an amount that agrees with it, is the same dividend
  dated differently (FLOS.L and IUAG.L, 2021-11-12 at Yahoo against 2021-11-11 at the
  issuer). The issuer's date wins and the Yahoo row is removed, so no twin remains
- **FR7**: **Declared.** An issuer row with an ex-date after today is not history. It
  becomes the instrument's `declared` upcoming row (the earliest, if there are several),
  with the issuer's pay date and the stated amount in the price currency, replacing the
  `estimated` row for that period and any `declared` row Yahoo reported (the issuer wins).
  Nothing is written when the issuer has no future row, and a row Yahoo declared stands
- **FR8**: **Authority.** `IS` beats `YA` beats `config`. The daily Yahoo upsert and the
  `distributions.txt` rows never replace an `IS` row, so a day on which the issuer fetch
  fails does not take the pay dates away; the issuer corrects an `IS` row on the next day it
  answers
- **FR9**: Idempotent: a second run with the same inputs changes nothing but `AsOf`
- **FR10**: `--backfill-dividends [--from DATE]` also fetches the configured issuer pages.
  For an instrument whose page fetched, its `YA` and `IS` rows from the start date are
  replaced by what Yahoo and the issuer report now (the issuer's applied last); an
  instrument with no Yahoo route (the FT-priced `IE00B0M63516`) gets its `IS` rows rebuilt
  alone and a line in the report table. A page that fails keeps its rows and is a failure
- **FR11**: The "Dividends" section of `daily_summary.md` lists each upcoming row that is
  new, or whose status or pay date changed, so a newly declared issuer row appears there
  once (estimated to declared) with its ex-date, pay date and amount
- **FR12**: An `estimated` row projects its pay date from the last history row's real lag
  (SPEC-010 FR8), so the pay dates this spec fills now flow into the estimates; this is the
  existing rule, not a guess added here

### Non-Functional Requirements

- **NFR1**: No network in tests. The parser is tested against two recorded pages
  (`fixtures/ishares_251804_igls.html`, `fixtures/ishares_290356_flos.html`: the table and the
  share-class entry cut unchanged from the live pages on 2026-10-26)
- **NFR2**: Coverage of the new code is 100%; the project gates hold
- **NFR3**: One request per configured instrument per day, `robots.txt` honoured (the
  product pages are allowed), the pages are 1.5 to 3 MB each
- **NFR4**: No error text is ever written to a data file

## The ten verified instruments

Product ids were read from iShares UK's own sitemap and checked by fetching: the fund name,
the share class (GBP hedged, distributing), the ISIN on the page and, for the nine LSE
lines, that every ex-date and amount equals Yahoo's (research page).

| Identifier | Product id | Fund |
|------------|-----------|------|
| IGLS.L | 251804 | iShares UK Gilts 0-5yr UCITS ETF GBP (Dist) |
| FLOS.L | 290356 | iShares $ Floating Rate Bond UCITS ETF GBP Hedged (Dist) |
| INXG.L | 251717 | iShares £ Index-Linked Gilts UCITS ETF GBP (Dist) |
| AGBP.L | 291771 | iShares Core Global Aggregate Bond UCITS ETF GBP Hedged (Dist) |
| DPYG.L | 295693 | iShares Developed Markets Property Yield UCITS ETF GBP Hedged (Dist) |
| IDTG.L | 311465 | iShares $ Treasury Bond 20+yr UCITS ETF GBP Hedged (Dist) |
| IWDG.L | 287737 | iShares Core MSCI World UCITS ETF GBP Hedged (Dist) |
| GHYS.L | 253488 | iShares Global High Yield Corp Bond GBP Hedged UCITS ETF (Dist) |
| IUAG.L | 251750 | iShares US Aggregate Bond UCITS ETF USD (Dist) |
| IE00B0M63516 | 251853 | iShares MSCI Brazil UCITS ETF USD (Dist), FT-priced |

## Validation Performed

One real run of `update_dividends()` against a scratch copy of the committed `data/` (the
repository's `data/` untouched), with the live Yahoo and iShares UK pages, for IGLS.L,
FLOS.L, QQQ and `IE00B0M63516`, on 2026-10-27:

| Instrument | Before | After |
|------------|--------|-------|
| IGLS.L | 27 rows, none with a pay date | 36 rows, all `IS` with a pay date (the nine older ones from 2009-06-24 to 2012-12-27 are new); no amount changed |
| FLOS.L | 17 rows, none | 17 rows, all with a pay date (2026-05-21 paid 2026-05-29, 2025-11-13 paid 2025-11-26); Yahoo's 2021-11-12 row replaced by the issuer's 2021-11-11 |
| IE00B0M63516 | no rows (FT-priced) | 81 rows from the issuer, all with a pay date; a new `estimated` upcoming row, 2026-12-17 paid 2026-12-30 |
| QQQ | 90 rows, none | unchanged: no issuer source |

The upcoming file: FLOS.L 2026-11-21 `estimated` gained the pay date 2026-11-29 and IGLS.L
2027-01-16 the pay date 2027-01-29 (FR12: projected from the last real lag, which is 8 days
for FLOS.L's May dividend and 13 for its November one, so it is an estimate like the row).
**No `declared` row appeared**: none of the three issuers had announced its next
distribution (their newest ex-dates are 2026-05-21, 2026-07-16 and 2026-09-17), so the
declared path is covered by the unit tests and the recorded-page shapes only, and will first
run for real when iShares publishes one. No failures; no other instrument's rows changed.

## Out of Scope

- QQQ, GLTL.L, KNSL, 0639.HK: no compliant plain-HTTP source was found (research page).
  KNSL's pay date arrives with Yahoo's calendar once a dividend is declared
- A `RecordDate` column
- A projection of a pay date from an offset (the owner rejected it); `distributions.txt`
  still holds an owner-stated offset for instruments with no source at all
- Detecting an issuer page that is wrong; the page is the issuer's own statement
- A functional test against the live site: the shape was checked by hand (the real run in
  the status page) and the parser fails loudly when it changes

## Decisions

| Decision | Reason |
|----------|--------|
| A new file, not a fourth field in `funds.txt` | `funds.txt`'s source code names the one source of a **price**; a dividend source is a second, independent fact, and an FT-priced fund can take its dividends from iShares. The existing parser, its validations and the many tests that build funds lines stay as they are |
| Key by the product id, not by ticker or ISIN | The site's search is excluded by its `robots.txt`; the sitemap lists ids; the page's own ticker is the share class's, not necessarily the instrument's line (`SUAG` on the page of IUAG.L's class). The ISIN is on the page for a human check |
| The issuer wins an amount that differs | It is the issuer's statement; where it differs from Yahoo it is Yahoo that is wrong (IWDG.L 2020-01-16: 1.77p against 1.75p) |
| Yahoo's amount is kept when they agree | The issuer shows four decimals of pounds, so a pence amount loses digits (1.2841p against 1.28p); equal within the issuer's rounding is equal |
| The issuer's whole table every day | It arrives in one page anyway, the merge is idempotent, and it fills what Yahoo lacks |
| Authority `IS` > `YA` > `config` | The daily Yahoo upsert would otherwise blank the pay date it just received |
| Record date read, not published | See Files |
