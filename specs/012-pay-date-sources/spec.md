# SPEC-012: Pay Dates from Invesco, SSGA, Q4 Inc and etnet

**Status**: ✅ Built, on branch `pay-date-sources` (not yet merged)
**Created**: 2026-10-27
**Type**: Feature (follow-up to SPEC-011)
**Tracking**: [#89](https://github.com/joneswm/FundPrices/issues/89)
**Research**: [docs/research/dividend_pay_date_sources.md](../../docs/research/dividend_pay_date_sources.md),
"Follow-up: the four remaining payers"

> Extends SPEC-011. After the `IS` source four dividend payers still had no pay date:
> QQQ, GLTL.L, KNSL and 0639.HK. Each has a source that is reachable over plain HTTP, needs
> no key or JavaScript and is permitted by its `robots.txt`. This spec adds one source code
> for each, wired exactly as `IS` is.

---

## User Need

**As** the owner of the portfolio
**I want** the real pay date on every dividend of every instrument that pays
**So that** the receivable is shown for the day the money arrives, not for a guess

## Proposed Solution

Four new source codes for `dividend_sources.txt`. Each fetches one document per instrument
per run, parses it into the `IssuerTable` of SPEC-011 and goes through the same merge
(`apply_issuer_table`, `issuer_declared`), so FR4 to FR8 of SPEC-011 hold unchanged. The
merged row's `Source` is the table's code, and every new code ranks with `IS`
(`SOURCE_AUTHORITY`): above `YA`, above `config`.

| Code | Source | `source-id` | Document |
|------|--------|-------------|----------|
| `IV` | Invesco's fund-data API (the one its product pages call) | the fund's CUSIP (`46090E103`, QQQ) | JSON `distributions[]`: `exDate`, `recordDate`, `payDate`, `distributionAmountPerUnit`, `currencyCode`; ISO dates |
| `SS` | SSGA's historical-distributions workbook for every SPDR EMEA ETF | the fund's ISIN (`IE00B6YX5L24`, GLTL.L) | `.xlsx`, columns `ISIN`, `CURRENCY`, `EX-DATE`, `RECORD DATE`, `PAYMENT DATE`, `DISTRIBUTION`; `dd/mm/yyyy` text |
| `Q4` | A Q4 Inc investor-relations site's own feed | `<ir host>/<exchange MIC>` (`ir.kinsalecapitalgroup.com/XNYS`); the symbol is the line's identifier (`KNSL`) | JSON `GetDividendListResult[]`: `ExDate`, `RecordDate`, `PayDate`, `DividendAmount`, `Currency`; `mm/dd/yyyy HH:MM:SS` |
| `ET` | etnet's dividend records (HKEX Information Services partner) | the HK code without leading zeros (`639`, 0639.HK) | HTML table: Announcement Date, Financial Year, Particular, Ex-date, Book Closed (From, Until), Payable Date; `dd/mm/yyyy` or `--` |

```
QQQ,IV,46090E103
GLTL.L,SS,IE00B6YX5L24
KNSL,Q4,ir.kinsalecapitalgroup.com/XNYS
0639.HK,ET,639
```

## Success Criteria

### Functional Requirements

- **FR1**: `DIVIDEND_SOURCE_CODES` gains `IV`, `SS`, `Q4` and `ET`. Each code has a source-id
  rule (`DIVIDEND_SOURCE_ID_RULES`): a CUSIP is nine capitals or digits, an ISIN twelve
  characters ending in a digit, a Q4 id `host/MIC` (lower-case host, four capitals), an etnet
  code one to five digits without a leading zero. A bad id raises `ValueError` naming the line,
  before any network call, exactly as for `IS`
- **FR2**: One request per instrument per run (30 s timeout, retried by
  `fetch_with_retries()`, `ISSUER_PAUSE_SECONDS` apart), a plain GET with no key and no
  browser. The one exception to "a request per instrument" is `SS`: the workbook is one
  download (60 s timeout) kept for the run and shared by every `SS` line;
  `collect_issuer_tables()` starts each run with `clear_issuer_caches()`, and a failed
  download is not cached
- **FR3**: **A response that is not what was recorded is an error for that instrument, not an
  empty table**: not JSON, no list, no header row, a date or amount that does not parse, a
  table in two currencies, an `SS` workbook with no row for the ISIN. The instrument keeps
  every row it had, the failure is printed as `"<identifier>: pay dates: <error>"` and reported
  with the other failures, and no other instrument is affected (FR3 of SPEC-011). A company
  that has never paid is an empty table (`Q4`, `ET`: an empty list, a page of "No Int Div")
- **FR4**: Each parser returns rows oldest first, **one per ex-date**: the history is keyed
  on `(Fund, ExDate)`, so two cash dividends that go ex on one day (0639.HK 2018-05-31: final
  0.072 and special 0.063) are one row with the amounts added and the later pay date. A pay
  date that is absent, `--` or before the ex-date is `""`
- **FR5**: `ET` keeps cash-dividend rows only: a Particular of the form `<kind> Div <CCY>
  <amount>` (`Int`, `Fin`, `Sp`). A rights issue (`Rts 1 for 30 @HKD 2.6`) and the `No Int
  Div` placeholders are skipped. The book-closed dates are not the record date and are not
  read. A row that does not have the seven columns is an error (a changed page)
- **FR6**: The `IssuerTable` gains `source`, default `IS`, so SPEC-011's construction is
  unchanged. `apply_issuer_table()` stamps the merged row with it, the rebuild
  (`--backfill-dividends`) replaces rows of any `DIVIDEND_SOURCE_CODES` where the issuer's
  document was read, and `merge_dividend_rows()` ranks all five codes above `YA`
- **FR7**: A distribution with an ex-date after today is the instrument's `declared` upcoming
  row, as for `IS`. All four documents carry an announcement or declaration date before the
  ex-date (Kinsale 16 days, SSGA 7, Invesco and etnet at declaration); no future row was on
  offer on 2026-10-27, so how early each appears was **not observed**
- **FR8**: The tests never touch the network. Each document was fetched once on 2026-10-27
  and saved in `fixtures/` (`invesco_46090E103_qqq.json`, `ssga_historical_distributions.xlsx`,
  `q4_knsl_dividends.json`, `etnet_639_dividends.html`); edge cases are built in the tests
  (`make_xlsx()` writes a workbook with the standard library)
- **FR9**: No new dependency. The workbook is read with `zipfile` and
  `xml.etree.ElementTree` (shared strings, inline strings and numbers), the columns found by
  their header text, not their position

### Non-Functional Requirements

- **Robots and terms.** SSGA's `robots.txt` allows `/library-content/products/fund-data/`;
  Kinsale's IR site is `Allow: /` with `Crawl-delay: 10` (one request per run); etnet leaves
  `/www/eng/stocks/` open and its page says "for reference only"; Invesco's API is what its
  own product page calls and no robots rule covers it, but its terms forbid "data mining,
  robots" other than what it makes generally available. The same class of exposure as the FT,
  Yahoo and iShares: one request per instrument per day, no more
- **Fragility.** Invesco's endpoint is an internal cache API with no published contract and
  SSGA's workbook path is an AEM asset that could move. Both fail loudly (FR3); the SSGA
  path can be re-resolved from `/uk/en_gb/institutional/resources/documents/dividend-distributions`

## Out of Scope

- A record-date column in the output files (SPEC-011 reads it and does not publish it)
- Nasdaq's quote API (works for QQQ, but its `robots.txt` is `Disallow: /`), SSGA's 2026
  dividend calendar PDF (planned dates, months ahead), dividendhistory.org, the company's
  announcement PDFs for 0639.HK, EDGAR (Kinsale's 8-Ks state no dates)
- Other Invesco, SPDR, Q4-hosted or Hong Kong instruments: each is one line of
  `dividend_sources.txt` away

## Decisions

| Decision | Reason |
|----------|--------|
| One code per host, not one generic "JSON feed" code | The four documents share nothing but the merge; each parser is thirty lines and its failure is named after its source |
| The Q4 symbol is the identifier on the line | The same feed serves any Q4-hosted site, and the line already names the ticker; the id only needs the host and the exchange MIC (`XNYS`, which the feed requires) |
| Same-ex-date rows are summed in the parser | The history key is `(Fund, ExDate)`; summing keeps the entitlement whole where keeping one row would lose half of it |
| `SS` caches the workbook in a module dictionary cleared at the start of each collection | The workbook covers every SPDR fund, so a second `SS` line costs no request; clearing per run means no stale download survives into the next run of a long-lived process |
| `IssuerTable.source` defaults to `IS` | SPEC-011's tests and call sites build tables with two fields and keep working |
| Etnet's book-closed date is not the record date | The company's announcement for 0639.HK states record 21/09 while etnet shows 22/09 as the first book-closed day |
