# Dividend Pay Date Sources

**Date**: 2026-10-26
**Issue**: [#87](https://github.com/joneswm/FundPrices/issues/87) (option 2: find a source with the real dates)
**Result**: the iShares UK product page for the iShares ETFs (primary, built as SPEC-011);
Yahoo's calendar stays the only route for the rest

## Question

SPEC-010's first run published 421 history rows and 13 upcoming rows with no pay date on any
row. Yahoo's dividend history carries only the ex-date and the amount, and `Ticker.calendar`
and `Ticker.info` are empty for the LSE ETFs and the funds. Which source gives the real ex,
record and pay dates and the declared amount for the 32 instruments in `funds.txt`?

Everything below was fetched on 2026-10-26 with plain HTTP (`curl`, `requests`) or, where
stated, Playwright. Raw responses are in `~/development/pt-logs/fp-pd-research/` (not in the
repository).

## Who actually pays a dividend

Before choosing a source it matters how many of the 32 need one. Yahoo's history
(`data/dividends_history.csv`), the FT tearsheets' "Income treatment" row and Yahoo's names
split the 32 like this:

| Group | Instruments | Needs a pay date |
|-------|-------------|------------------|
| iShares distributing ETFs | IGLS.L, FLOS.L, INXG.L, AGBP.L, DPYG.L, IDTG.L, IWDG.L, GHYS.L, IUAG.L, and **IE00B0M63516** (FT-sourced: it is iShares MSCI Brazil UCITS ETF USD (Dist), LSE `IDBZ`) | yes: 10 |
| Others that pay | QQQ (Invesco), GLTL.L (State Street SPDR), KNSL, 0639.HK | yes: 4 |
| Accumulating, nothing to pay | SGLN.L (an ETC), CNX1.L, ISPE.L, IGWD.L, SWDA.L, WLDS.L, EMIM.L (iShares), BCHS.L, EWQX.L, EQGB.L (Invesco), QNTG.L (VanEck), GRAB, `0P00000YAN` (a fund NAV) | no |
| FT-sourced accumulation share classes | GB00B1FXTF86, IE0008368742, LU0196696453, MU0129U00005, LU0164881194 (each "Income treatment: Accumulation" on its FT tearsheet) | no |

So the "OEICs" turned out to need nothing but one: five of the six FT-sourced funds
accumulate, and the sixth is an iShares ETF. 14 of 32 instruments have something to find, and
10 of them are iShares.

## Candidates

| Source | Ex | Record | Pay | Amount | Declared future | Plain HTTP | Verdict |
|--------|----|--------|-----|--------|-----------------|------------|---------|
| (a) iShares UK product page | yes | yes | yes | yes | see below | yes | **primary** |
| (a) Invesco (QQQ) | not found | | | | | | no endpoint found |
| (a) State Street SPDR (GLTL) | not tested | | | | | | page URL not resolved |
| (b) London Stock Exchange | not reached | | | | | no | API 403, pages need a browser |
| (c) justETF | no | no | no | yearly totals in EUR | no | yes | no per-date table |
| (d) dividenddata.co.uk | not reached | | | | | no | Cloudflare 403 on every URL |
| (e) FT markets | no | no | no | no | no | yes | no dividend data for funds |
| (e) investing.com | no | no | no | no | no | partly | no dividend data in the page |
| (f) Yahoo `quoteSummary` | ex | no | stocks only | last only | stocks only | via yfinance | already used |
| (g) Morningstar | not reached | | | | | no | JavaScript page, 404 and 202 |
| Nasdaq `api.nasdaq.com` | yes | yes | yes | yes | yes | yes | **robots.txt disallows all; NYSE symbols unavailable** |
| stockanalysis.com | yes | yes | yes | yes | yes | yes | **terms forbid scripts and scrapers** |

### (a) The issuer: iShares UK product pages

`https://www.ishares.com/uk/individual/en/products/<product id>/<slug>`. The product id is the
number in the URL (`251804` is iShares UK Gilts 0-5yr). Without the right id a fund cannot be
found: the site's search page is excluded by `robots.txt` (`Disallow: /search/`), but the
product pages are not, and `https://www.ishares.com/uk/product-sitemap.xml` lists all 3,065 of
them with their ids. The id is per share class, so the same fund has one id for the GBP-hedged
distributing class and another for the accumulating one.

What a fetch gives: one HTTP GET of about 1.5 to 3 MB. The page embeds, HTML-entity-escaped
inside an attribute, the whole data model of the fund page. The table behind the
"Distributions" section is `performance.distributions.table` with four parallel lists, newest
first: `exDate`, `recordDate`, `payableDate` (integers such as `20260716`) and
`totalDistribution` (decimal text such as `'2.4146'`). It is the same table the page shows.
The share class's currency is in the share-class selector next to the product id
(`"currency":"GBP","pId":251804`), and the distribution frequency and the ISIN are on the page.
There is no CSV or JSON download in the new page: the old `.ajax?fileType=csv` links are gone
(no `.ajax`, `fileType` or `dataType` string anywhere in the page).

Verified against Yahoo, all nine distributing LSE ETFs (the fetch is
`~/development/pt-logs/fp-pd-research/compare.py`):

| Fund | Yahoo rows | iShares rows | Same ex-date | Notes |
|------|-----------|--------------|--------------|-------|
| IGLS.L | 27 | 36 | 27 | amounts equal; the issuer reaches back to 2009 |
| FLOS.L | 17 | 18 | 16 | one ex-date a day apart (Yahoo 2021-11-12, issuer 2021-11-11) |
| INXG.L | 22 | 40 | 22 | amounts equal |
| AGBP.L | 18 | 18 | 18 | amounts equal |
| DPYG.L | 34 | 34 | 34 | amounts equal |
| IDTG.L | 14 | 14 | 14 | one 2019 row: Yahoo 0.0037, issuer 0.0 |
| IWDG.L | 38 | 38 | 38 | in pence, the issuer's four-decimal pounds lose precision; 2020-01-16 differs (Yahoo 1.77p, issuer 1.75p) |
| GHYS.L | 29 | 29 | 29 | amounts equal |
| IUAG.L | 27 | 29 | 26 | one ex-date a day apart (Yahoo 2021-11-12, issuer 2021-11-11) |

Three things follow. 224 of Yahoo's 226 rows for these nine funds have the same ex-date at the
issuer, so the issuer can be joined to the stored rows on `(Fund, ExDate)`, with a tolerance
of a few days for the two that are a day out. The issuer states amounts in the **share-class currency in major
units** (FLOS.L: `0.0991` for a GBP-hedged class) while Yahoo states them in the **price
currency** (`9.91` GBp), so a pence line needs a factor of 100. And the issuer's decimals are
shorter for small amounts, so "agree" has to mean "within the issuer's rounding".

Spot checks on the issuer's dates (a payment lag is not constant, which is why a guess is
wrong): IGLS 0-5yr pays 13 days after the ex-date (2026-07-16 to 2026-07-29), FLOS and its
siblings 8 days (2026-05-21 to 2026-05-29) and 13 days in November (2025-11-13 to
2025-11-26), IWDG 13 days (2026-10-15 to 2026-10-28, a date still to come today).

Declared future rows: the newest ex-date on each page, today, is the last one passed (IWDG
2026-10-15, GHYS 2026-10-15, IBZL 2026-09-17, AGBP and IGLS 2026-07-16). No page shows a row
with a future ex-date, because none is announced yet; IWDG's row shows a pay date two days
ahead, which proves that a row appears at or before its ex-date and carries a pay date that
has not happened. Whether a row appears before the ex-date, and how long before, cannot be
read from a quiet week, so SPEC-011 handles both: a row with a future ex-date is `declared`.

Access: `robots.txt` allows the product pages (it disallows `/search/`, `*.dl$`, `?truepdf`
and `?norepdf`). BlackRock's site terms (`blackrock.com/corporate/compliance/terms-and-conditions`)
forbid "any robot, spider ... to ... copy this Website or the data", the same class of
restriction the FT and Yahoo sources already live under; the project's rule is `robots.txt`,
a delay between requests and one request per instrument per day, and SPEC-011 keeps to it.
No rate limit was met (about 40 page fetches during this research, three seconds apart).

Identification: the **product id**, which the owner reads from the fund's URL or the sitemap.
The ISIN is on the page, so a typo is checkable. The page's own main ticker is the share
class's, not necessarily the instrument's LSE line (the page for IUAG.L's class says `SUAG`).
Stability: the data model is the same JSON the site's own components read; it changed once
(the CSV links went) and will change again, which is why the build fails soft and tests against
a recorded page.

Coverage: 10 of 14 (the whole iShares group, including the FT-sourced IE00B0M63516).

### (a) Invesco and State Street

Invesco's QQQ site (`invesco.com/qqq-etf/en/performance.html`) has no distribution table in
its HTML. Its pages call `dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/...`
for performance; guessed `distributions`, `dividends` and `distribution-history` paths return
`501 Api Not Implemented`. The distribution endpoint, if there is one, was not found.
State Street's page for GLTL.L (SPGL) was not reached: the guessed URL redirected to the fund
finder, and `ssga.com`'s `robots.txt` is long and was not worked through. Neither is covered.

### (b) London Stock Exchange

`api.londonstockexchange.com/api/gw/lse/instruments/alldata/IGLS` answers 403 from CloudFront
to a plain client. The instrument pages redirect to the Price Explorer unless the exact slug
is known, and a headless Chromium (Playwright) rendered only the Price Explorer, whose data
comes from `apidata.londonstockexchange.com`. No dividend table was found for an ETF.
`robots.txt` is permissive. Not usable without a browser and a bot-protection bypass.

### (c) justETF

Plain HTTP works and `robots.txt` allows `/en/etf-profile.html`. The Dividends section holds
only yearly totals (EUR 0.49 for 2025, yield 4.11%) and a chart whose data is requested by
Wicket Ajax; no ex-dates, no pay dates, no per-payment amounts in the page.

### (d) dividenddata.co.uk

Every URL, `robots.txt` included, returns Cloudflare's "Attention Required" 403 to `curl`.
Getting past it is bypassing bot detection, which is not done.

### (e) FT and investing.com

`markets.ft.com/data/funds/tearsheet/summary?s=<ISIN>` answers (it is the price source) and
states "Income treatment" (Accumulation or Income), but `.../tearsheet/dividends` is an error
page for funds. investing.com's `etfs/powershares-qqqq-dividends` returns 200 with no
dividend data in its `__NEXT_DATA__` (and `uk.investing.com` serves a Cloudflare challenge).

### (f) Yahoo `quoteSummary`

Fetched through yfinance's own session for QQQ, KNSL, 0639.HK, IGLS.L, FLOS.L, GLTL.L:

| Instrument | `calendarEvents` | `summaryDetail` / `defaultKeyStatistics` |
|------------|------------------|------------------------------------------|
| KNSL | `exDividendDate` 2026-08-28, `dividendDate` 2026-09-14 | `lastDividendValue` 0.25, `lastDividendDate` |
| 0639.HK | `exDividendDate` only | `lastDividendValue` 0.1 |
| QQQ | none | trailing rate only |
| IGLS.L, FLOS.L, GLTL.L | 404 "No fundamentals data found" | empty |

Yahoo gives a pay date for US stocks and only the latest one; it has nothing for the ETFs.
SPEC-010 already uses it (`fetch_yahoo_declared`), and it stays the route for KNSL and
0639.HK.

### (g) Morningstar

`morningstar.co.uk/uk/etf/snapshot/snapshot.aspx` returns `202` with an empty body (the page
is built in the browser), `morningstar.com/etfs/xnas/qqq/dividends` is a 404, and the API host
wants a login. Not usable over plain HTTP.

### Aggregators that do have the table, and why they are not built on

- **Nasdaq** (`api.nasdaq.com/api/quote/QQQ/dividends?assetclass=etf`) returns ex, record,
  payment date and amount for QQQ in one small JSON document, including the next dividend. Its
  `robots.txt` is a blanket `Disallow: /`, and for KNSL it answers "Dividend History for
  Non-Nasdaq symbols is not available". Rejected on both counts.
- **stockanalysis.com** (`/etf/qqq/dividend/`, `/stocks/knsl/dividend/`,
  `/quote/lon/IGLS/dividend/`, `/quote/hkg/0639/dividend/`) has a static HTML table of ex-date,
  amount, record date and pay date for QQQ, KNSL, IGLS and 0639.HK, and its numbers equal the
  issuer's. It would cover three of the four uncovered instruments. Its terms of use say "You
  may not use bots, scripts, scrapers ... or any other automated or programmatic methods to
  access the platform", exempting crawlers that follow `robots.txt` only for search engines
  and AI agents. A daily script that republishes the figures in a public repository is
  neither. Rejected; the owner may decide otherwise, and the integration point is the same one
  SPEC-011 builds (a second source code in `dividend_sources.txt`).
- MarketBeat answered 200 and was not examined further (its terms were not read); Digrin and
  dividend.com returned 404 for the guessed URL, MarketScreener 403, DividendMax a "Page Not
  Found"; none was pursued.

## Recommendation

**Primary: the iShares UK product page (source code `IS`)**, because it is the issuer (exact
dates and amounts, equal to Yahoo's wherever they overlap), plain HTTP, permitted by
`robots.txt`, identified by a stable product id, and covers 10 of the 14 instruments that
pay, including one the FT cannot describe. It also corrects Yahoo (two ex-dates a day out, one
amount that differs) and fills its gaps (INXG.L: 18 rows Yahoo lacks, the latest 2023-05-19;
IGLS.L: 9 older rows, back to 2009).

**Fallback for the rest: Yahoo's calendar**, which SPEC-010 already reads. It gives KNSL's pay
date when the dividend is declared; it gives 0639.HK's ex-date but not its pay date; it gives
QQQ and GLTL.L nothing. Those three have no pay date after SPEC-011 either, and that is a
finding, not an oversight: no source tested that is both reachable over plain HTTP and
permitted by its `robots.txt` and terms carries them. The ways to close it, in the order the
owner might choose:

1. QQQ: find Invesco's distribution endpoint (a browser's network tab on the QQQ distributions
   section would show it) and add it as source `IV`-like code beside `IS`.
2. GLTL.L: State Street's fund page has a distributions table; same method.
3. Accept stockanalysis.com's terms risk for the four, or ask for permission.
4. Add a Playwright route for the LSE.

The pay-offset guess the owner rejected stays out: none of this projects a pay date.

## Follow-up 2026-10-27: the four remaining payers (#89, SPEC-012)

The sections above stand as the record of 2026-10-26. A second pass found a source for each
of the four instruments the recommendation left on Yahoo's calendar, all plain HTTP, no key,
no JavaScript, each document fetched once and saved in `fixtures/`:

| Instrument | Source (code) | Why it was missed |
|------------|---------------|-------------------|
| QQQ | Invesco's fund-data API, `dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/<CUSIP>/distribution?idType=cusip&productType=ETF` (`IV`) | The product page's own call; keyed by CUSIP (`idType=ticker` answers empty, and the guess `shareclasses/QQQ` was a ticker) |
| GLTL.L | SSGA's historical-distributions workbook for every SPDR EMEA ETF, `ssga.com/library-content/products/fund-data/etfs/emea/spdr-etf-historical-distributions-uk-en.xlsx` (`SS`) | Linked from the dividend-distributions documents page, not from the fund page; allowed by `robots.txt` |
| KNSL | The Q4 Inc feed behind the company's IR site, `ir.kinsalecapitalgroup.com/feed/StockQuote.svc/GetDividendList` (`Q4`) | EDGAR's 8-Ks state no dates; the IR feed carries declared, ex, record and pay dates; `robots.txt` is `Allow: /` with a 10 s crawl delay |
| 0639.HK | etnet's dividend records, `etnet.com.hk/www/eng/stocks/realtime/quote_dividend.php?code=639` (`ET`) | aastocks and HKEX's widget need JavaScript; etnet's page is static HTML and its `/www/eng/stocks/` is open to robots |

Two things the fixtures showed that the parsers handle: etnet lists rights issues (`Rts 1 for
30 @HKD 2.6`) and "No Int Div" placeholders beside the cash dividends, and a final and a special
dividend can share an ex-date (2018-05-31), which the history, keyed on `(Fund, ExDate)`, holds
as one row. Not observed: how early before the ex-date each source shows a declared row (none
had a future row on the day). The design is `specs/012-pay-date-sources/spec.md`.
