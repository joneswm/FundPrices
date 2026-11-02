# Recorded source responses

Each file is one response from a live source, fetched once and saved so the
parser tests never touch the network. Tests read them through `fixture_text()`
and `fixture_bytes()` in `test_scrape_fund_price.py`; edge cases are built in
the tests (`ishares_page()`, `make_xlsx()`, `ons_payload()`, `boe_page()`), not
edited into these files. The source URLs are the module's URL constants. The
pre-commit hooks skip this directory.

When a source changes shape, record it again the same way: one fetch, saved as
served, trimmed only where this table says, and the date and trimming noted here.

| File | Source | Recorded | Trimmed | Owning test class |
|------|--------|----------|---------|-------------------|
| `boe_bank_rate.html` | `https://www.bankofengland.co.uk/boeapps/database/Bank-Rate.asp` (`UK_BANK_RATE_URL`) | 2026-11-01 | Nothing: the whole page as served | `TestBankRateParsing` |
| `etnet_639_dividends.html` | `https://www.etnet.com.hk/www/eng/stocks/realtime/quote_dividend.php?code=639` (`ETNET_DIVIDEND_URL`) | 2026-10-27 | Nothing: the whole page as served | `TestEtnetParsing` |
| `invesco_46090E103_qqq.json` | `https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/46090E103/distribution?idType=cusip&productType=ETF` (`INVESCO_DISTRIBUTION_URL`) | 2026-10-27 | Nothing: the whole response as served | `TestInvescoParsing` |
| `ishares_251804_igls.html` | `https://www.ishares.com/uk/individual/en/products/251804` (`ISHARES_PRODUCT_URL`) | 2026-10-26 | Cut to the distributions table and the share-class entry, both unchanged, under a header comment naming the fund | `TestIsharesPageParsing` |
| `ishares_290356_flos.html` | `https://www.ishares.com/uk/individual/en/products/290356` (`ISHARES_PRODUCT_URL`) | 2026-10-26 | As above | `TestIsharesPageParsing` |
| `ons_d7bt_cpi.json` | `https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/d7bt/mm23/data` (`UK_CPI_URL`) | 2026-10-27 | Cut to `description` and the months from 2014, values unchanged | `TestOnsCpiParsing` |
| `q4_knsl_dividends.json` | `https://ir.kinsalecapitalgroup.com/feed/StockQuote.svc/GetDividendList?exchange=XNYS&symbol=KNSL&pageSize=-1` (`Q4_DIVIDEND_URL`) | 2026-10-27 | Nothing: the whole response as served | `TestQ4Parsing` |
| `ssga_historical_distributions.xlsx` | `https://www.ssga.com/library-content/products/fund-data/etfs/emea/spdr-etf-historical-distributions-uk-en.xlsx` (`SSGA_WORKBOOK_URL`) | 2026-10-27 | Nothing: the whole workbook as served | `TestSsgaParsing` |
| FT fixtures | Stream 2A of #97 is recording the Financial Times pages behind `TestFTQuoteFetching`; add their rows here when they land | | | `TestFTQuoteFetching` |

The recording dates are the dates of the commits that added the files
(`git log --follow --format=%ad --date=short -- fixtures/<file>`), which match
the dates the specs give (SPEC-011 to SPEC-014).
