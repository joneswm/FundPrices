import unittest
import tempfile
import os
import shutil
from contextlib import ExitStack, contextmanager
from unittest.mock import patch, MagicMock
import csv
import decimal
import html
import json
import urllib.parse
import datetime
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import scrape_fund_price

from scrape_fund_price import (
    read_fund_ids,
    get_source_config,
    scrape_funds,
    write_results,
    fetch_price_api,
    fetch_historical_data,
    parse_arguments,
    main,
    read_latest_csv_price,
    read_history_price,
    get_last_known_price,
    Quote,
    format_yahoo_price,
    fetch_yahoo_quotes,
    fetch_ft_quotes,
    source_requires_browser,
    ScrapeResults,
    FundSpec,
    read_fund_specs,
    backfill_history,
    validate_backfill_args,
    BackfillReport,
    check_quoting_unit,
    read_fx_pairs,
    fetch_fx_quotes,
    fetch_yahoo_hourly,
    new_york_fx_closes,
    write_fx_results,
    snap_fx_rates,
    backfill_fx,
    build_price_summary,
    build_fx_summary,
    render_summary_markdown,
    write_summary,
    canonical_source,
    scrape_fund_quotes,
    write_history_files,
    write_fx_files,
    write_latest_price_file,
    ClosedHolding,
    read_closed_holdings,
    fetch_investing_quotes,
    import_closed_holdings,
    read_history_rows,
)

# Point the module's default output directory at a scratch location for the
# whole suite. A test that forgets to pass data_dir would otherwise write into
# the repository's committed data/, which is how a stray latest_AAPL.price and
# live FX rewrites got in before.
_REAL_DATA_DIR = scrape_fund_price.DATA_DIR
_SUITE_DATA_DIR = None
# The same for the issuer list (SPEC-011): no test reads the shipped
# dividend_sources.txt by accident, so a main() test never fetches a page.
_REAL_DIVIDEND_SOURCES_FILE = scrape_fund_price.DIVIDEND_SOURCES_FILE
# And the CPI update (SPEC-013): the daily run ends by fetching the ONS, so every
# other main() test gets a stub and the UK CPI tests keep the real function.
REAL_UPDATE_UK_CPI = scrape_fund_price.update_uk_cpi
_UK_CPI_PATCH = None
# And the Bank Rate update (SPEC-014), stubbed the same way.
REAL_UPDATE_UK_BANK_RATE = scrape_fund_price.update_uk_bank_rate
_UK_BANK_RATE_PATCH = None


def setUpModule():
    global _SUITE_DATA_DIR, _UK_CPI_PATCH, _UK_BANK_RATE_PATCH
    _SUITE_DATA_DIR = tempfile.mkdtemp(prefix="fundprices-tests-")
    scrape_fund_price.DATA_DIR = _SUITE_DATA_DIR
    scrape_fund_price.DIVIDEND_SOURCES_FILE = os.path.join(
        _SUITE_DATA_DIR, "no-dividend-sources.txt"
    )
    _UK_CPI_PATCH = patch(
        "scrape_fund_price.update_uk_cpi",
        return_value=MagicMock(failures=[]),
    )
    _UK_CPI_PATCH.start()
    _UK_BANK_RATE_PATCH = patch(
        "scrape_fund_price.update_uk_bank_rate",
        return_value=MagicMock(failures=[]),
    )
    _UK_BANK_RATE_PATCH.start()


def tearDownModule():
    _UK_BANK_RATE_PATCH.stop()
    _UK_CPI_PATCH.stop()
    scrape_fund_price.DATA_DIR = _REAL_DATA_DIR
    scrape_fund_price.DIVIDEND_SOURCES_FILE = _REAL_DIVIDEND_SOURCES_FILE
    if _SUITE_DATA_DIR:
        shutil.rmtree(_SUITE_DATA_DIR, ignore_errors=True)


# ---------------------------------------------------------------------------
# Shared test support (Bundle 2 of #97).
#
# DataDirCase gives a test its own scratch directory and file helpers, and
# stubs the pacing sleeps. fake_ticker and history_metadata stand in for
# yf.Ticker, daily_run_stubs for the daily run's collaborators in main() tests.
# BackfillCase, DividendRunCase (with its row builders) and IssuerRunCase are
# the feature-level bases that build on DataDirCase.
# ---------------------------------------------------------------------------

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture_text(name):
    """Return a page recorded from the live site (see fixtures/)."""
    with open(os.path.join(FIXTURE_DIR, name), encoding="utf-8") as f:
        return f.read()


def fixture_bytes(name):
    """Return a file recorded from the live site, as bytes (see fixtures/)."""
    with open(os.path.join(FIXTURE_DIR, name), "rb") as f:
        return f.read()


def utc(year, month, day, hour):
    """A timezone-aware UTC datetime, the shape the hourly bars take."""
    return datetime.datetime(year, month, day, hour, tzinfo=datetime.timezone.utc)


def epoch(text):
    """Midnight UTC of an ISO date, as Yahoo's info endpoint reports dates."""
    day = datetime.date.fromisoformat(text)
    midnight = datetime.datetime.combine(day, datetime.time(), datetime.timezone.utc)
    return int(midnight.timestamp())


class DataDirCase(unittest.TestCase):
    """A scratch directory per test, removed afterwards, with file helpers.

    The backfill and issuer pacing pauses (`time.sleep`) are stubbed for the
    whole test; the seconds asked for are recorded on `self.sleeps`.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.test_dir, ignore_errors=True)
        self.sleeps = []
        sleeper = patch.object(scrape_fund_price.time, "sleep", self.sleeps.append)
        sleeper.start()
        self.addCleanup(sleeper.stop)

    def path(self, name):
        return os.path.join(self.test_dir, name)

    def read_text(self, name):
        with open(self.path(name), newline="") as f:
            return f.read()

    def read_rows(self, name):
        """The CSV's rows without its header; a missing file is no rows."""
        if not os.path.exists(self.path(name)):
            return []
        with open(self.path(name), newline="") as f:
            return list(csv.reader(f))[1:]

    def write_text(self, name, text):
        with open(self.path(name), "w", newline="") as f:
            f.write(text)
        return self.path(name)

    def write_csv(self, name, header, rows):
        with open(self.path(name), "w", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows)
        return self.path(name)


def fake_ticker(
    mock_ticker,
    bars=(),
    currency="GBP",
    volumes=None,
    dividends=None,
    tz=None,
    meta=None,
    index=None,
):
    """Make a patched `yf.Ticker` serve one history frame; returns the instance.

    `bars` is [(date text, close)]; `volumes` and `dividends` are lists aligned
    with it and add the Volume and Dividends columns; `tz` names the index's
    zone (naive when None); `index` replaces the dates (hourly bars); `meta`
    is what get_history_metadata returns, or an exception it raises.
    """
    import pandas as pd

    if index is None:
        dates = [day for day, _ in bars]
        if tz:
            index = pd.DatetimeIndex([pd.Timestamp(day, tz=tz) for day in dates])
        else:
            index = pd.to_datetime(dates)
    columns = {"Close": [close for _, close in bars]}
    if volumes is not None:
        columns["Volume"] = volumes
    if dividends is not None:
        columns["Dividends"] = dividends
    inst = MagicMock()
    inst.history.return_value = pd.DataFrame(columns, index=index)
    inst.fast_info = {"currency": currency}
    if isinstance(meta, Exception):
        inst.get_history_metadata.side_effect = meta
    elif meta is not None:
        inst.get_history_metadata.return_value = meta
    mock_ticker.return_value = inst
    return inst


def history_metadata(price, traded, end, tz="Europe/London"):
    """What yf.Ticker.get_history_metadata reports for a finished session."""
    import pandas as pd

    def stamp(text):
        return pd.Timestamp(text, tz=tz)

    return {
        "regularMarketPrice": price,
        "regularMarketTime": stamp(traded),
        "exchangeTimezoneName": tz,
        "currentTradingPeriod": {"regular": {"end": stamp(end)}},
    }


class FakeCalendarTicker:
    """A stand-in for yf.Ticker exposing only calendar and info."""

    def __init__(self, calendar=None, info=None, calendar_error=None, info_error=None):
        self._calendar, self._info = calendar, info
        self._calendar_error, self._info_error = calendar_error, info_error

    @property
    def calendar(self):
        if self._calendar_error:
            raise self._calendar_error
        return self._calendar

    @property
    def info(self):
        if self._info_error:
            raise self._info_error
        return self._info


DAILY_RUN_STUBS = (
    "scrape_funds",
    "write_results",
    "snap_fx_rates",
    "write_fx_results",
    "update_dividends",
    "write_summary",
)


@contextmanager
def daily_run_stubs(test_dir=None, specs=(), pairs=(), **outcomes):
    """Patch the daily run's collaborators around a `main([])` call.

    Yields the stubs by name (plus "print"). Each name in DAILY_RUN_STUBS is
    stubbed with an empty result unless `outcomes` gives it a return value, an
    exception to raise, or a dict of patch keyword arguments; any other module
    name in `outcomes` is patched the same way.
    """
    defaults = {
        "scrape_funds": ScrapeResults(),
        "write_results": None,
        "snap_fx_rates": ScrapeResults(),
        "write_fx_results": None,
        "update_dividends": scrape_fund_price.DividendResults(),
        "write_summary": None,
    }
    stubs = {}
    with ExitStack() as stack:
        enter = stack.enter_context
        if test_dir is not None:
            enter(patch("scrape_fund_price.DATA_DIR", test_dir))
        enter(patch("scrape_fund_price.read_fund_specs", return_value=list(specs)))
        enter(patch("scrape_fund_price.read_fx_pairs", return_value=list(pairs)))
        for name, value in {**defaults, **outcomes}.items():
            if isinstance(value, dict):
                kwargs = value
            elif isinstance(value, BaseException):
                kwargs = {"side_effect": value}
            else:
                kwargs = {"return_value": value}
            stubs[name] = enter(patch(f"scrape_fund_price.{name}", **kwargs))
        stubs["print"] = enter(patch("builtins.print"))
        yield stubs


class BackfillCase(DataDirCase):
    """A DataDirCase for the price rebuild, with the FX rebuild kept out.

    backfill_history ends by rebuilding whatever fx_pairs.txt in the working
    directory lists, and the repository's lists four pairs: left alone, every
    test below would fetch years of Yahoo FX bars for them.
    """

    def setUp(self):
        super().setUp()
        no_pairs = patch("scrape_fund_price.read_fx_pairs", return_value=[])
        no_pairs.start()
        self.addCleanup(no_pairs.stop)


class DividendRunCase(DataDirCase):
    """Shared scaffolding for the dividend tests (SPEC-010).

    The run date, builders for the two files' rows, a distributions.txt
    parser, and the dividend update run with Yahoo faked.
    """

    TODAY = date(2026, 10, 26)

    # The IssuerRunCase classes (SPEC-011, SPEC-012) still call these; step
    # 2.Z of #97 removes them once those callers use the DataDirCase methods.
    @staticmethod
    def row(fund, ex, pay, amount, currency, source):
        """A dividends_history.csv row."""
        return [fund, ex, pay, amount, currency, source]

    @classmethod
    def upcoming(cls, fund, ex, pay, amount, currency, status, as_of=None):
        """A dividends_upcoming.csv row, as of the run date unless given."""
        as_of = as_of or cls.TODAY.isoformat()
        return [fund, ex, pay, amount, currency, status, as_of]

    def write_history(self, *rows):
        """Store dividends_history.csv rows, as an earlier run would have."""
        header = ["Fund", "ExDate", "PayDate", "Amount", "Currency", "Source"]
        return self.write_csv("dividends_history.csv", header, rows)

    def _dists(self, *lines):
        """Parse distributions.txt lines, without the identifier check."""
        path = self.write_text("distributions.txt", "\n".join(lines) + "\n")
        return scrape_fund_price.read_distributions(path, None)

    def _run(self, specs, events=None, declared=None, distributions=(), runner=None):
        """Run update_dividends (or `runner`) with Yahoo faked."""
        events = events or {}
        declared = declared or {}
        self.windows = []

        def fake_events(symbol, window_start, end=None):
            self.windows.append((symbol, window_start))
            value = events.get(symbol, [])
            if isinstance(value, Exception):
                raise value
            return value

        def fake_declared(symbol, today=None):
            return declared.get(symbol)

        runner = runner or scrape_fund_price.update_dividends
        with patch.object(scrape_fund_price, "fetch_yahoo_dividends", fake_events):
            with patch.object(scrape_fund_price, "fetch_yahoo_declared", fake_declared):
                return runner(specs, list(distributions), self.test_dir, self.TODAY)


class IssuerRunCase(DividendRunCase):
    """Run the dividend update with Yahoo and the issuer's pages faked."""

    IGLS = scrape_fund_price.DividendSource("IGLS.L", "IS", "251804")
    FLOS = scrape_fund_price.DividendSource("FLOS.L", "IS", "290356")
    EVENT = scrape_fund_price.DividendEvent

    PAST = ("2026-07-16", "2026-07-17", "2026-07-29", "2.4146")
    NEXT = ("2026-11-12", "2026-11-13", "2026-11-25", "2.5")

    def _issuer_run(
        self,
        specs,
        sources,
        tables=None,
        events=None,
        declared=None,
        runner=None,
        distributions=(),
    ):
        """Run update_dividends (or `runner`), `tables` keyed by source id.

        The pacing pauses are recorded on `self.sleeps` by DataDirCase.
        """
        tables = tables or {}
        self.fetched = []

        def fake_fetch(source):
            self.fetched.append(source.source_id)
            value = tables[source.source_id]
            if isinstance(value, Exception):
                raise value
            return value

        def update(specs, dists, data_dir, today):
            return scrape_fund_price.update_dividends(
                specs, dists, data_dir, today, sources=sources
            )

        with patch.object(scrape_fund_price, "fetch_issuer_table", fake_fetch):
            return self._run(
                specs, events, declared, distributions, runner=runner or update
            )


# ===========================================================================
# Configuration files
# ===========================================================================


class TestFundSpecParsing(DataDirCase):
    """Test funds.txt parsing, including aliases and validation."""

    def specs(self, text):
        return read_fund_specs(self.write_text("funds.txt", text))

    def assertRejectedAt(self, text, line):
        """Assert the file is rejected with an error naming `line`."""
        with self.assertRaises(ValueError) as error:
            self.specs(text)
        self.assertIn(f"line {line}", str(error.exception))

    def test_two_field_line_has_no_aliases(self):
        """Test existing config lines keep their meaning."""
        specs = self.specs("YA,QQQ\n")
        self.assertEqual(specs, [FundSpec("YA", "QQQ", ())])
        self.assertEqual(specs[0].publish_ids, ("QQQ",))

    def test_third_field_adds_an_alias(self):
        """Test a fund can publish under a second identifier."""
        specs = self.specs("YA,0P00000YAN,JFM0003373\n")
        self.assertEqual(specs[0].lookup_id, "0P00000YAN")
        self.assertEqual(specs[0].aliases, ("JFM0003373",))
        self.assertEqual(specs[0].publish_ids, ("0P00000YAN", "JFM0003373"))

    def test_multiple_aliases_are_semicolon_separated(self):
        """Test more than one alias can be given."""
        specs = self.specs("YA,ABC,ONE;TWO\n")
        self.assertEqual(specs[0].publish_ids, ("ABC", "ONE", "TWO"))

    def test_whitespace_and_blank_lines_are_ignored(self):
        """Test untidy config files still parse."""
        specs = self.specs("\n  YA , QQQ , ALIAS \n\n  \nFT,ISIN1\n")
        self.assertEqual(
            specs, [FundSpec("YA", "QQQ", ("ALIAS",)), FundSpec("FT", "ISIN1", ())]
        )

    def test_comments_are_stripped(self):
        """Test the inline comments the docs have always shown actually work."""
        specs = self.specs("# a heading\nFT,GB00B1FXTF86    # Financial Times\n")
        self.assertEqual(specs, [FundSpec("FT", "GB00B1FXTF86", ())])

    def test_read_fund_ids_still_returns_pairs(self):
        """Test the existing helper keeps its shape for existing callers."""
        path = self.write_text("funds.txt", "YA,0P00000YAN,JFM0003373\nFT,ISIN1\n")
        self.assertEqual(read_fund_ids(path), [("YA", "0P00000YAN"), ("FT", "ISIN1")])

    def test_line_with_one_field_is_rejected(self):
        """Test an incomplete line names its line number."""
        self.assertRejectedAt("YA,QQQ\nJUSTONE\n", 2)

    def test_empty_source_or_identifier_is_rejected(self):
        """Test blank fields are not silently accepted."""
        self.assertRejectedAt("YA,QQQ\n,MISSING_SOURCE\n", 2)

    def test_empty_alias_is_rejected(self):
        """Test a stray separator is treated as a typo, not an empty alias."""
        self.assertRejectedAt("YA,ABC,ONE;;TWO\n", 1)

    def test_alias_matching_its_own_lookup_id_is_rejected(self):
        """Test a self-referencing alias is rejected rather than double-writing."""
        self.assertRejectedAt("YA,ABC,ABC\n", 1)

    def test_duplicate_identifier_across_lines_is_rejected(self):
        """Test a repeated fund cannot silently produce duplicate rows."""
        self.assertRejectedAt("YA,QQQ\nFT,ISIN1\nYA,QQQ\n", 3)

    def test_alias_colliding_with_another_funds_id_is_rejected(self):
        """Test an alias cannot shadow a different instrument."""
        self.assertRejectedAt("YA,QQQ\nYA,ABC,QQQ\n", 2)

    def test_trailing_comma_is_an_empty_alias_field(self):
        """Test `YA,QQQ,` is rejected rather than read as a line with no alias."""
        self.assertRejectedAt("YA,QQQ,\n", 1)


class TestSourceCodeCanonicalisation(DataDirCase):
    """Test the GF -> YA rename and its deprecation alias."""

    def _write(self, text):
        return self.write_text("funds.txt", text)

    def test_current_codes_pass_through_unchanged(self):
        """Test canonical codes are left alone."""
        for code in ("YA", "FT", "IV"):
            self.assertEqual(canonical_source(code), code)

    def test_deprecated_gf_maps_to_ya(self):
        """Test GF still resolves, to the Yahoo API."""
        self.assertEqual(canonical_source("GF"), "YA")

    def test_retired_scraping_codes_are_rejected_naming_the_line(self):
        """Test a stale YH or MS line fails validation rather than fetching.

        The scraping sources were retired (#97). Neither code is swept into
        the GF alias: reusing YH for the API would silently change which
        handler a stale funds.txt line selects, which is why the rename chose
        YA, so a line naming one is an error that names the line and the code.
        """
        for code in ("YH", "MS", "yh"):
            with self.subTest(code=code):
                with self.assertRaisesRegex(ValueError, f"funds file line 2.*{code}"):
                    read_fund_specs(self._write(f"YA,QQQ\n{code},IDTG.L\n"))

    def test_closed_holdings_reject_the_retired_codes_too(self):
        """Test the one-off import shares the rejection with funds.txt."""
        for code in ("YH", "MS"):
            with self.subTest(code=code):
                path = self.write_text(
                    "closed_holdings.txt",
                    f"X,{code},IDTG.L,GBP,2023-01-03,2024-02-16\n",
                )
                with self.assertRaisesRegex(
                    ValueError, f"closed holdings line 1.*{code}"
                ):
                    read_closed_holdings(path)

    @patch("builtins.print")
    def test_deprecated_code_warns_naming_the_line(self, mock_print):
        """Test the warning says where to fix the configuration."""
        read_fund_specs(self._write("YA,QQQ\nGF,GRAB\n"))
        warned = " ".join(str(c) for c in mock_print.call_args_list)
        self.assertIn("GF", warned)
        self.assertIn("YA", warned)
        self.assertIn("line 2", warned)

    def test_parser_returns_canonical_sources(self):
        """Test downstream code only ever sees one spelling."""
        specs = read_fund_specs(self._write("GF,QQQ\nYA,GRAB\nFT,ISIN1\n"))
        self.assertEqual([s.source for s in specs], ["YA", "YA", "FT"])

    def test_ya_uses_the_api_and_needs_no_browser(self):
        """Test the renamed code routes exactly as GF did."""
        self.assertFalse(source_requires_browser("YA", "QQQ"))
        with patch(
            "scrape_fund_price.fetch_yahoo_quotes",
            return_value=[Quote("2026-09-18", "721.45", "USD")],
        ) as mock_quotes:
            quotes = scrape_fund_quotes("YA", "QQQ", "2026-09-10")
        self.assertEqual(quotes[0].price, "721.45")
        mock_quotes.assert_called_once()

    @patch("scrape_fund_price.sync_playwright")
    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_deprecated_code_still_scrapes_correctly(self, mock_quotes, mock_pw):
        """Test an unmigrated funds.txt keeps producing prices."""
        mock_quotes.return_value = [Quote("2026-09-18", "721.45", "USD")]
        results = scrape_funds(read_fund_specs(self._write("GF,QQQ\n")), self.test_dir)
        self.assertEqual(list(results), [["QQQ", "2026-09-18", "721.45", "USD"]])
        mock_pw.assert_not_called()

    def test_closed_holdings_share_the_alias(self):
        """Test closed_holdings.txt uses funds.txt's source vocabulary."""
        path = self.write_text(
            "closed_holdings.txt", "BKCH,GF,BKCH.L,USD,2023-01-03,2024-02-16\n"
        )
        [holding] = read_closed_holdings(path)
        self.assertEqual(holding.source, "YA")

    def test_dividend_collection_shares_the_alias(self):
        """Test a (source, identifier) pair spelt GF is still fetched from Yahoo."""
        event = scrape_fund_price.DividendEvent("2026-09-18", "1", "USD")
        with patch.object(
            scrape_fund_price, "fetch_yahoo_dividends", lambda s, w, e=None: [event]
        ):
            with patch.object(
                scrape_fund_price, "fetch_yahoo_declared", lambda s, t=None: None
            ):
                results = scrape_fund_price.collect_dividends(
                    [("GF", "QQQ")], date(2026, 10, 26)
                )
        self.assertEqual(len(results), 1)


class TestFxPairConfiguration(DataDirCase):
    """Test fx_pairs.txt parsing and validation."""

    def pairs(self, text):
        return read_fx_pairs(self.write_text("fx_pairs.txt", text))

    def test_reads_one_pair_per_line(self):
        """Test the configured pairs are read in order."""
        pairs = self.pairs("NZDGBP\nSGDGBP\nUSDGBP\nHKDGBP\n")
        self.assertEqual(pairs, ["NZDGBP", "SGDGBP", "USDGBP", "HKDGBP"])

    def test_ignores_comments_and_blank_lines(self):
        """Test the file can be annotated."""
        pairs = self.pairs("# GBP per 1 unit\n\nUSDGBP   # dollar\n\n")
        self.assertEqual(pairs, ["USDGBP"])

    def test_rejects_a_slash_separated_pair(self):
        """Test the market-convention spelling is rejected, not misread.

        'GBP/NZD' conventionally means NZD per GBP, the inverse of what is
        wanted, so accepting it would store plausible but wrong values.
        """
        with self.assertRaises(ValueError) as error:
            self.pairs("GBP/NZD\n")
        self.assertIn("line 1", str(error.exception))

    def test_rejects_lowercase_and_wrong_length(self):
        """Test only six uppercase letters are accepted."""
        for bad in ("usdgbp", "USDGB", "USDGBPX"):
            with self.subTest(pair=bad):
                with self.assertRaises(ValueError) as error:
                    self.pairs(bad + "\n")
                self.assertIn("line 1", str(error.exception))

    def test_rejects_duplicate_pairs(self):
        """Test a repeated pair cannot produce duplicate rows."""
        with self.assertRaises(ValueError) as error:
            self.pairs("USDGBP\nSGDGBP\nUSDGBP\n")
        self.assertIn("line 3", str(error.exception))

    def test_missing_file_means_no_fx(self):
        """Test FX is optional, so an absent file is not an error."""
        self.assertEqual(read_fx_pairs(self.path("absent.txt")), [])

    def test_the_default_file_is_fx_pairs_txt(self):
        """Test the daily run's call names no file and reads FX_PAIRS_FILE."""
        path = self.write_text("fx_pairs.txt", "USDGBP\n")
        with patch.object(scrape_fund_price, "FX_PAIRS_FILE", path):
            self.assertEqual(read_fx_pairs(), ["USDGBP"])


class TestClosedHoldingConfiguration(DataDirCase):
    """Test the closed-holdings config, which is deliberately not funds.txt.

    These instruments are no longer held. Keeping them out of funds.txt is
    what stops the daily run fetching prices for a fund that stopped trading
    years ago, so the two files must stay separate.
    """

    def _write(self, text):
        return self.write_text("closed_holdings.txt", text)

    def test_parses_a_holding_into_its_fields(self):
        """Test every field a one-off import needs is carried."""
        holdings = read_closed_holdings(
            self._write("BKCH,YA,BKCH.L,USD,2023-01-03,2024-02-16\n")
        )
        self.assertEqual(
            holdings,
            [ClosedHolding("BKCH", "YA", "BKCH.L", "USD", "2023-01-03", "2024-02-16")],
        )

    def test_identifier_and_lookup_id_are_independent(self):
        """Test a holding is published under the identifier, not the symbol.

        BMV7ZZ3 is a SEDOL; the price comes from an FT symbol that names a
        fund since renamed twice. Neither spelling belongs in the other's slot.
        """
        holding = read_closed_holdings(
            self._write("BMV7ZZ3,FT,SEAL:LSE:GBX,GBX,2024-03-21,2024-10-25\n")
        )[0]
        self.assertEqual(holding.identifier, "BMV7ZZ3")
        self.assertEqual(holding.lookup_id, "SEAL:LSE:GBX")

    def test_blank_lines_and_comments_are_ignored(self):
        """Test the file can be documented, including trailing comments."""
        holdings = read_closed_holdings(
            self._write(
                "# closed holdings\n"
                "\n"
                "BKCH,YA,BKCH.L,USD,2023-01-03,2024-02-16  # last held Feb 2024\n"
            )
        )
        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0].end, "2024-02-16")

    def test_short_line_names_the_line_number(self):
        """Test a malformed line fails before any network call."""
        with self.assertRaises(ValueError) as caught:
            read_closed_holdings(self._write("BKCH,YA,BKCH.L\n"))
        self.assertIn("line 1", str(caught.exception))

    def test_invalid_date_is_rejected(self):
        """Test a date typo cannot silently import the wrong window."""
        with self.assertRaises(ValueError) as caught:
            read_closed_holdings(
                self._write("BKCH,YA,BKCH.L,USD,2023-13-01,2024-02-16\n")
            )
        self.assertIn("line 1", str(caught.exception))

    def test_end_before_start_is_rejected(self):
        """Test a reversed window is caught rather than importing nothing."""
        with self.assertRaises(ValueError) as caught:
            read_closed_holdings(
                self._write("BKCH,YA,BKCH.L,USD,2024-02-16,2023-01-03\n")
            )
        self.assertIn("line 1", str(caught.exception))

    def test_duplicate_identifier_is_rejected(self):
        """Test two windows for one identifier cannot fight over the same rows."""
        with self.assertRaises(ValueError) as caught:
            read_closed_holdings(
                self._write(
                    "BKCH,YA,BKCH.L,USD,2023-01-03,2024-02-16\n"
                    "BKCH,YA,BKCH.L,USD,2022-01-03,2022-02-16\n"
                )
            )
        self.assertIn("line 2", str(caught.exception))

    def test_committed_file_holds_the_closed_holdings(self):
        """Test the repository's own configuration matches what was researched."""
        holdings = read_closed_holdings(scrape_fund_price.CLOSED_HOLDINGS_FILE)
        self.assertEqual(
            {h.identifier: h.source for h in holdings},
            {
                "BKCH": "YA",
                "BMV7ZZ3": "FT",
                "BN4MYX3": "IV",
                "SPOG": "YA",
                "R2SC": "YA",
                "CNDX": "YA",
                "FBTC": "YA",
                "JFM50541951": "IV",
            },
        )

    def test_closed_holdings_are_absent_from_the_daily_configuration(self):
        """Test the daily run cannot pick up an instrument that stopped trading."""
        daily = {
            identifier
            for spec in read_fund_specs("funds.txt")
            for identifier in spec.publish_ids
        }
        closed = {h.identifier for h in read_closed_holdings("closed_holdings.txt")}
        self.assertEqual(daily & closed, set())

    def test_the_default_file_is_closed_holdings_txt(self):
        """Test the import's call names no file and reads CLOSED_HOLDINGS_FILE."""
        path = self._write("BKCH,YA,BKCH.L,USD,2023-01-03,2024-02-16\n")
        with patch.object(scrape_fund_price, "CLOSED_HOLDINGS_FILE", path):
            [holding] = read_closed_holdings()
        self.assertEqual(holding.identifier, "BKCH")


class TestDistributionConfiguration(DataDirCase):
    """Test distributions.txt parsing and validation (SPEC-010, #85)."""

    KNOWN = {"GB00B1FXTF86", "IE0008368742", "BMV7ZZ3"}

    def _read(self, text, known="default"):
        path = self.write_text("distributions.txt", text)
        if known == "default":
            known = self.KNOWN
        return scrape_fund_price.read_distributions(path, known)

    def test_reads_a_full_line(self):
        """Test every field of the documented example is parsed."""
        [dist] = self._read(
            "GB00B1FXTF86,semiannual,03-01;09-01,30,0.0821;0.0794,2026-10-01\n"
        )
        self.assertEqual(dist.identifier, "GB00B1FXTF86")
        self.assertEqual(dist.frequency, "semiannual")
        self.assertEqual(dist.xd_dates, ((3, 1), (9, 1)))
        self.assertEqual(dist.pay_offset_days, 30)
        self.assertEqual(dist.amounts, ("0.0821", "0.0794"))
        self.assertEqual(dist.as_of, "2026-10-01")

    def test_amounts_and_as_of_are_optional(self):
        """Test the shortest legal line has four fields."""
        [dist] = self._read("IE0008368742,annual,12-15,28\n")
        self.assertEqual(dist.amounts, ("",))
        self.assertEqual(dist.as_of, "")

    def test_amounts_without_as_of_are_kept(self):
        """Test five fields are legal: the amounts then feed estimates only."""
        [dist] = self._read("IE0008368742,annual,12-15,28,0.31\n")
        self.assertEqual(dist.amounts, ("0.31",))
        self.assertEqual(dist.as_of, "")

    def test_an_unknown_amount_may_be_left_empty(self):
        """Test a slot with no known amount is an empty entry."""
        [dist] = self._read("GB00B1FXTF86,semiannual,03-01;09-01,30,;0.0794\n")
        self.assertEqual(dist.amounts, ("", "0.0794"))

    def test_dates_are_sorted_and_amounts_follow_their_dates(self):
        """Test the amount stays with the date it was written against."""
        [dist] = self._read("GB00B1FXTF86,semiannual,09-01;03-01,30,0.0794;0.0821\n")
        self.assertEqual(dist.xd_dates, ((3, 1), (9, 1)))
        self.assertEqual(dist.amounts, ("0.0821", "0.0794"))

    def test_frequency_is_case_insensitive(self):
        """Test the frequency is normalised to lower case."""
        [dist] = self._read("GB00B1FXTF86,Quarterly,01-05;04-05;07-05;10-05,20\n")
        self.assertEqual(dist.frequency, "quarterly")

    def test_every_frequency_needs_its_own_number_of_dates(self):
        """Test the date count must match the payments a year."""
        monthly = ";".join(f"{month:02d}-10" for month in range(1, 13))
        [dist] = self._read(f"GB00B1FXTF86,monthly,{monthly},5\n")
        self.assertEqual(len(dist.xd_dates), 12)
        wrong = {
            "quarterly": "2 ex-dates",
            "annual": "1 ex-date",
        }
        for frequency, complaint in wrong.items():
            with self.subTest(frequency=frequency):
                with self.assertRaisesRegex(ValueError, f"line 1.*{complaint}"):
                    self._read(f"GB00B1FXTF86,{frequency},03-01;09-01,30\n")

    def test_leap_day_is_allowed(self):
        """Test 02-29 is a real ex-date for the years that have one."""
        [dist] = self._read("GB00B1FXTF86,annual,02-29,10\n")
        self.assertEqual(dist.xd_dates, ((2, 29),))

    def test_comments_and_blank_lines_are_ignored(self):
        """Test full-line and trailing comments, and blank lines."""
        dists = self._read(
            "# header\n\n"
            "GB00B1FXTF86,annual,03-01,30   # factsheet p.2\n"
            "   \n"
            "IE0008368742,annual,06-01,30\n"
        )
        self.assertEqual(
            [d.identifier for d in dists], ["GB00B1FXTF86", "IE0008368742"]
        )

    def test_a_header_only_file_has_no_entries(self):
        """Test the shipped file, comments only, yields nothing."""
        self.assertEqual(self._read("# nothing yet\n"), [])

    def test_a_missing_file_has_no_entries(self):
        """Test the file is optional."""
        path = self.path("absent.txt")
        self.assertEqual(scrape_fund_price.read_distributions(path, set()), [])

    def test_the_configured_file_is_read_by_default(self):
        """Test the production call names no file."""
        path = self.write_text("distributions.txt", "X,annual,03-01,30\n")
        with patch.object(scrape_fund_price, "DISTRIBUTIONS_FILE", path):
            [dist] = scrape_fund_price.read_distributions()
        self.assertEqual(dist.identifier, "X")

    def test_identifier_must_be_configured(self):
        """Test a line for an unknown instrument names the line."""
        with self.assertRaisesRegex(ValueError, "line 2.*'NOPE'"):
            self._read("GB00B1FXTF86,annual,03-01,30\nNOPE,annual,03-01,30\n")

    def test_membership_is_not_checked_without_a_known_set(self):
        """Test callers that only want the grammar can skip the lookup."""
        [dist] = self._read("ANYTHING,annual,03-01,30\n", known=None)
        self.assertEqual(dist.identifier, "ANYTHING")

    def test_repeated_identifier_names_both_lines(self):
        """Test an identifier may have one line."""
        with self.assertRaisesRegex(ValueError, "line 2.*already used on line 1"):
            self._read("GB00B1FXTF86,annual,03-01,30\nGB00B1FXTF86,annual,04-01,30\n")

    def test_malformed_lines_name_the_line_number(self):
        """Test each way a line can be wrong fails with its line number."""
        bad = {
            "GB00B1FXTF86,annual": "expected",
            "GB00B1FXTF86,annual,03-01": "expected",
            ",annual,03-01,30": "expected",
            "GB00B1FXTF86,annual,03-01,30,0.3,2026-10-01,extra": "expected",
            "GB00B1FXTF86,weekly,03-01,30": "frequency",
            "GB00B1FXTF86,annual,3-1,30": "ex-date",
            "GB00B1FXTF86,annual,13-01,30": "ex-date",
            "GB00B1FXTF86,annual,02-30,30": "ex-date",
            "GB00B1FXTF86,annual,,30": "ex-date",
            "GB00B1FXTF86,semiannual,03-01;03-01,30": "repeats",
            "GB00B1FXTF86,annual,03-01,thirty": "pay offset",
            "GB00B1FXTF86,annual,03-01,-5": "pay offset",
            "GB00B1FXTF86,annual,03-01,366": "pay offset",
            "GB00B1FXTF86,annual,03-01,30,abc": "amount",
            "GB00B1FXTF86,annual,03-01,30,0": "amount",
            "GB00B1FXTF86,annual,03-01,30,-0.5": "amount",
            "GB00B1FXTF86,annual,03-01,30,NaN": "amount",
            "GB00B1FXTF86,annual,03-01,30,1;2": "amounts",
            "GB00B1FXTF86,annual,03-01,30,": "amounts field is empty",
            "GB00B1FXTF86,annual,03-01,30,,2026-10-01": "amounts field is empty",
            "GB00B1FXTF86,annual,03-01,30,0.3,yesterday": "as-of",
            "GB00B1FXTF86,annual,03-01,30,0.3,2026-13-01": "as-of",
            "GB00B1FXTF86,annual,03-01,30,0.3,": "as-of",
        }
        for line, fragment in bad.items():
            with self.subTest(line=line):
                with self.assertRaisesRegex(ValueError, f"line 3.*{fragment}"):
                    self._read(f"# one\n\n{line}\n")


class TestDividendSourceConfiguration(DataDirCase):
    """Test dividend_sources.txt parsing and validation (SPEC-011, #87)."""

    SPECS = [
        FundSpec("YA", "IGLS.L"),
        FundSpec("FT", "IE00B0M63516", ("IDBZ",)),
        FundSpec("YA", "QQQ"),
    ]

    def _read(self, text, specs="default"):
        path = self.write_text("dividend_sources.txt", text)
        if specs == "default":
            specs = self.SPECS
        return scrape_fund_price.read_dividend_sources(path, specs)

    def test_reads_lines_comments_and_blank_lines(self):
        """Test the documented grammar."""
        sources = self._read(
            "# the issuers\n"
            "\n"
            "IGLS.L,IS,251804   # 0-5yr gilts\n"
            "IE00B0M63516 , is , 251853\n"
        )
        self.assertEqual(
            sources,
            [
                scrape_fund_price.DividendSource("IGLS.L", "IS", "251804"),
                scrape_fund_price.DividendSource("IE00B0M63516", "IS", "251853"),
            ],
        )

    def test_an_alias_may_name_the_instrument(self):
        """Test any published identifier is accepted."""
        [source] = self._read("IDBZ,IS,251853\n")
        self.assertEqual(source.identifier, "IDBZ")

    def test_a_missing_file_means_no_sources(self):
        """Test the file is optional."""
        missing = self.path("none.txt")
        self.assertEqual(scrape_fund_price.read_dividend_sources(missing, []), [])

    def test_the_default_file_is_the_configured_one(self):
        """Test the production call names no file."""
        path = self.write_text("dividend_sources.txt", "QQQ,IS,1\n")
        with patch.object(scrape_fund_price, "DIVIDEND_SOURCES_FILE", path):
            [source] = scrape_fund_price.read_dividend_sources(specs=self.SPECS)
        self.assertEqual(source.identifier, "QQQ")

    def test_without_specs_the_identifier_is_not_checked(self):
        """Test the grammar can be read on its own."""
        [source] = self._read("ANYTHING,IS,5\n", specs=None)
        self.assertEqual(source.identifier, "ANYTHING")

    def test_bad_lines_name_the_line(self):
        """Test every malformed field fails before any network call."""
        cases = {
            "IGLS.L,IS": "line 1.*expected",
            "IGLS.L,IS,251804,extra": "line 1.*expected",
            ",IS,251804": "line 1.*expected",
            "IGLS.L,XX,251804": "line 1.*source 'XX'",
            "IGLS.L,IS,abc": "line 1.*source id 'abc'",
            "IGLS.L,IS,": "line 1.*source id ''",
            "IGLS.L,IS,1234567890": "line 1.*source id '1234567890'",
            "IGLS.L,IS,0": "line 1.*source id '0'",
            "NOPE,IS,251804": "line 1.*'NOPE'.*funds.txt",
        }
        for text, pattern in cases.items():
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, pattern):
                    self._read(text + "\n")

    def test_the_error_names_the_right_line(self):
        """Test line numbers count comments and blanks."""
        with self.assertRaisesRegex(ValueError, "line 3"):
            self._read("# c\n\nIGLS.L,IS,x\n")

    def test_a_repeated_identifier_is_an_error(self):
        """Test one line per identifier."""
        with self.assertRaisesRegex(ValueError, "line 2.*already used on line 1"):
            self._read("IGLS.L,IS,1\nIGLS.L,IS,2\n")

    def test_two_lines_for_one_instrument_are_an_error(self):
        """Test a lookup id and its alias are the same instrument."""
        with self.assertRaisesRegex(ValueError, "line 2.*same instrument.*line 1"):
            self._read("IE00B0M63516,IS,1\nIDBZ,IS,1\n")


class TestPayDateSourceConfiguration(DataDirCase):
    """Test dividend_sources.txt accepts the four new codes (SPEC-012, #89)."""

    SPECS = [
        FundSpec("YA", "QQQ"),
        FundSpec("YA", "GLTL.L"),
        FundSpec("YA", "KNSL"),
        FundSpec("YA", "0639.HK"),
    ]

    def _read(self, text):
        path = self.write_text("dividend_sources.txt", text)
        return scrape_fund_price.read_dividend_sources(path, self.SPECS)

    def test_the_four_codes_are_known(self):
        """Test the code list and the authority of each."""
        for code in ("IS", "IV", "SS", "Q4", "ET"):
            self.assertIn(code, scrape_fund_price.DIVIDEND_SOURCE_CODES)
            self.assertEqual(scrape_fund_price.SOURCE_AUTHORITY[code], 2)

    def test_reads_one_line_per_source(self):
        """Test the documented ids parse, codes case-insensitively."""
        sources = self._read(
            "QQQ,IV,46090E103\n"
            "GLTL.L,ss,IE00B6YX5L24  # SPDR\n"
            "KNSL,Q4,ir.kinsalecapitalgroup.com/XNYS\n"
            "0639.HK,ET,639\n"
        )
        self.assertEqual(
            [(s.identifier, s.source, s.source_id) for s in sources],
            [
                ("QQQ", "IV", "46090E103"),
                ("GLTL.L", "SS", "IE00B6YX5L24"),
                ("KNSL", "Q4", "ir.kinsalecapitalgroup.com/XNYS"),
                ("0639.HK", "ET", "639"),
            ],
        )

    def test_a_malformed_source_id_names_the_line(self):
        """Test each code checks its own id before any network call."""
        cases = {
            "QQQ,IV,46090E10": "line 1.*CUSIP",
            "QQQ,IV,46090e103": "line 1.*CUSIP",
            "QQQ,IV,": "line 1.*CUSIP",
            "GLTL.L,SS,IE00B6YX5L2": "line 1.*ISIN",
            "GLTL.L,SS,251804": "line 1.*ISIN",
            "KNSL,Q4,ir.kinsalecapitalgroup.com": "line 1.*host/MIC",
            "KNSL,Q4,ir.kinsale.com/xnys": "line 1.*host/MIC",
            "KNSL,Q4,https://ir.kinsale.com/XNYS": "line 1.*host/MIC",
            "KNSL,Q4,ir.kinsale.com/XNYS/x": "line 1.*host/MIC",
            "0639.HK,ET,0639": "line 1.*HK code",
            "0639.HK,ET,abc": "line 1.*HK code",
            "0639.HK,ET,123456": "line 1.*HK code",
        }
        for text, pattern in cases.items():
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, pattern):
                    self._read(text + "\n")


class TestConfiguredIdentifiers(DataDirCase):
    """Test which identifiers a distributions.txt line may name (SPEC-010, #85)."""

    def test_funds_aliases_and_closed_holdings_are_all_known(self):
        """Test the three sources of identifiers."""
        closed = self.write_text(
            "closed_holdings.txt", "BKCH,YA,BKCH.L,USD,2023-01-03,2024-02-16\n"
        )
        known = scrape_fund_price.configured_identifiers(
            [FundSpec("YA", "0P00000YAN", ("JFM0003373",)), ("FT", "GB00B1FXTF86")],
            closed,
        )
        self.assertEqual(known, {"0P00000YAN", "JFM0003373", "GB00B1FXTF86", "BKCH"})

    def test_a_missing_closed_holdings_file_adds_nothing(self):
        """Test the file is optional here."""
        known = scrape_fund_price.configured_identifiers(
            [("FT", "GB00B1FXTF86")], self.path("no-such-file")
        )
        self.assertEqual(known, {"GB00B1FXTF86"})


# ===========================================================================
# Yahoo prices
# ===========================================================================


class TestPriceFormatting(unittest.TestCase):
    """Test precision-preserving formatting of Yahoo float32 bar values."""

    def test_format_strips_float32_noise(self):
        """Test float32 artefacts are not stored as extra decimal places."""
        self.assertEqual(format_yahoo_price(124.87000274658203), "124.87")
        self.assertEqual(format_yahoo_price(192.42999267578125), "192.43")
        self.assertEqual(format_yahoo_price(595.0499877929688), "595.05")
        self.assertEqual(format_yahoo_price(721.4500122070312), "721.45")

    def test_format_preserves_genuine_decimals(self):
        """Test real precision is kept, not rounded away."""
        self.assertEqual(format_yahoo_price(2.7785000801086426), "2.7785")
        self.assertEqual(format_yahoo_price(5.060999870300293), "5.061")
        self.assertEqual(format_yahoo_price(21.395000457763672), "21.395")

    def test_format_drops_trailing_point_zero(self):
        """Test whole numbers are stored without a trailing .0."""
        self.assertEqual(format_yahoo_price(6317.0), "6317")
        self.assertEqual(format_yahoo_price(126530.0), "126530")
        self.assertEqual(format_yahoo_price(13339.0), "13339")

    def test_format_keeps_precision_on_large_values(self):
        """Test large values keep their decimals (a .7g format would not)."""
        import numpy as np

        self.assertEqual(format_yahoo_price(np.float32(126530.25)), "126530.25")


class TestYahooQuoteFetching(unittest.TestCase):
    """Test dated quote retrieval from the Yahoo daily-bar route.

    fetch_price_api, the legacy single-price wrapper over the same route, is
    covered here too.
    """

    @patch("scrape_fund_price.yf.Ticker")
    def test_drops_zero_volume_spike_quoted_in_wrong_currency(self, mock_ticker):
        """Test an untraded bar far above both neighbours is not stored (#83).

        Yahoo's SWDA.L bar for 2025-10-24 carried the USD listing's price
        (128.64) in the GBp line, with zero volume.
        """
        fake_ticker(
            mock_ticker,
            [
                ("2025-10-23", 9564.0),
                ("2025-10-24", 12837.80957),
                ("2025-10-27", 9720.0),
            ],
            currency="GBp",
            volumes=[127553, 0, 62649],
        )
        quotes = fetch_yahoo_quotes("SWDA.L", "2025-10-20")
        self.assertEqual([q.date for q in quotes], ["2025-10-23", "2025-10-27"])

    @patch("scrape_fund_price.yf.Ticker")
    def test_drops_zero_volume_dip_far_below_both_neighbours(self, mock_ticker):
        """Test the guard is symmetric: a wrong price can be too low too."""
        fake_ticker(
            mock_ticker,
            [("2025-10-23", 100.0), ("2025-10-24", 70.0), ("2025-10-27", 101.0)],
            volumes=[500, 0, 500],
        )
        quotes = fetch_yahoo_quotes("XXXX.L", "2025-10-20")
        self.assertEqual([q.date for q in quotes], ["2025-10-23", "2025-10-27"])

    @patch("scrape_fund_price.yf.Ticker")
    def test_keeps_traded_bar_however_far_it_moves(self, mock_ticker):
        """Test a bar with volume is trusted: real trades can spike."""
        fake_ticker(
            mock_ticker,
            [("2022-09-26", 39.4), ("2022-09-27", 60.0), ("2022-09-28", 42.9)],
            volumes=[43405, 71342, 123451],
        )
        quotes = fetch_yahoo_quotes("GLTL.L", "2022-09-20")
        self.assertEqual(len(quotes), 3)

    @patch("scrape_fund_price.yf.Ticker")
    def test_keeps_zero_volume_step_that_the_next_bar_confirms(self, mock_ticker):
        """Test a level change is not a spike: funds report no volume at all."""
        fake_ticker(
            mock_ticker,
            [("2026-09-16", 100.0), ("2026-09-17", 130.0), ("2026-09-18", 131.0)],
            volumes=[0, 0, 0],
        )
        quotes = fetch_yahoo_quotes("0P00000YAN", "2026-09-10")
        self.assertEqual(len(quotes), 3)

    @patch("scrape_fund_price.yf.Ticker")
    def test_keeps_newest_bar_which_has_no_next_bar_to_judge_by(self, mock_ticker):
        """Test the newest bar is kept: one neighbour cannot show a spike."""
        fake_ticker(
            mock_ticker,
            [("2026-09-17", 100.0), ("2026-09-18", 140.0)],
            volumes=[500, 0],
        )
        quotes = fetch_yahoo_quotes("XXXX.L", "2026-09-10")
        self.assertEqual(len(quotes), 2)

    @patch("scrape_fund_price.yf.Ticker")
    def test_spike_neighbours_skip_bars_without_a_price(self, mock_ticker):
        """Test a null-close bar does not hide a spike's neighbour."""
        fake_ticker(
            mock_ticker,
            [
                ("2025-10-22", 6.5655),
                ("2025-10-23", float("nan")),
                ("2025-10-24", 8.9258),
                ("2025-10-27", 6.7285),
            ],
            volumes=[83899, 0, 0, 292481],
        )
        quotes = fetch_yahoo_quotes("WLDS.L", "2025-10-20")
        self.assertEqual([q.date for q in quotes], ["2025-10-22", "2025-10-27"])

    @patch("scrape_fund_price.yf.Ticker")
    def test_returns_dated_quotes(self, mock_ticker):
        """Test each bar becomes a Quote carrying the bar's own date."""
        fake_ticker(
            mock_ticker, [("2026-09-17", 192.42999267578125), ("2026-09-18", 193.5)]
        )
        quotes = fetch_yahoo_quotes("0P00000YAN", "2026-09-10")
        self.assertEqual(
            quotes,
            [Quote("2026-09-17", "192.43", "GBP"), Quote("2026-09-18", "193.5", "GBP")],
        )

    @patch("scrape_fund_price.yf.Ticker")
    def test_requests_unadjusted_close(self, mock_ticker):
        """Test history is requested unadjusted so prices match those snapped."""
        inst = fake_ticker(mock_ticker, [("2026-09-18", 7.15)])
        fetch_yahoo_quotes("IDTG.L", "2026-09-10", "2026-09-19")
        kwargs = inst.history.call_args.kwargs
        self.assertFalse(kwargs["auto_adjust"])
        self.assertEqual(kwargs["start"], "2026-09-10")
        self.assertEqual(kwargs["end"], "2026-09-19")

    @patch("scrape_fund_price.yf.Ticker")
    def test_preserves_pence_currency(self, mock_ticker):
        """Test GBp is not silently normalised to GBP."""
        fake_ticker(mock_ticker, [("2026-09-18", 6317.0)], currency="GBp")
        self.assertEqual(fetch_yahoo_quotes("SGLN.L", "2026-09-10")[0].currency, "GBp")

    @patch("scrape_fund_price.yf.Ticker")
    def test_drops_rows_without_a_price(self, mock_ticker):
        """Test NaN closes are skipped rather than stored."""
        fake_ticker(mock_ticker, [("2026-09-17", float("nan")), ("2026-09-18", 7.15)])
        quotes = fetch_yahoo_quotes("IDTG.L", "2026-09-10")
        self.assertEqual([q.date for q in quotes], ["2026-09-18"])

    @patch("scrape_fund_price.yf.Ticker")
    def test_empty_history_returns_no_quotes(self, mock_ticker):
        """Test an empty result is not an error."""
        fake_ticker(mock_ticker, [])
        self.assertEqual(fetch_yahoo_quotes("IDTG.L", "2026-09-10"), [])

    @patch("scrape_fund_price.yf.Ticker")
    def test_exception_propagates_to_retry_wrapper(self, mock_ticker):
        """Test transport errors are raised so fetch_with_retries can retry."""
        mock_ticker.side_effect = ConnectionError("Network error")
        with self.assertRaises(ConnectionError):
            fetch_yahoo_quotes("IDTG.L", "2026-09-10")

    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_fetch_price_api_uses_latest_quote(self, mock_quotes):
        """Test the price API wrapper returns the newest quote, not .info."""
        mock_quotes.return_value = [
            Quote("2026-09-16", "192.23", "USD"),
            Quote("2026-09-17", "192.43", "USD"),
        ]
        self.assertEqual(fetch_price_api("0P00000YAN"), "192.43")
        self.assertEqual(mock_quotes.call_args.args[0], "0P00000YAN")

    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_fetch_price_api_reports_missing_price(self, mock_quotes):
        """Test the error contract is kept when no quotes come back."""
        mock_quotes.return_value = []
        self.assertEqual(fetch_price_api("BADSYM"), "Error: Price not available")

    @patch("scrape_fund_price.yf.Ticker")
    def test_fetch_price_api_reports_exception(self, mock_ticker):
        """Test an error below the wrapper keeps the "Error: <message>" contract."""
        mock_ticker.side_effect = ConnectionError("Network error")
        self.assertEqual(fetch_price_api("IDTG.L"), "Error: Network error")


class TestYahooEmptyLatestBar(unittest.TestCase):
    """Regression: Yahoo can return the newest daily bar with a null close.

    On 2026-10-10 CNX1.L's 2026-10-09 bar existed with Close = NaN, while the
    chart metadata still carried that day's closing price. Skipping the NaN
    left Thursday as the newest quote.
    """

    ROWS = [("2026-10-08", 134720.0), ("2026-10-09", float("nan"))]

    @staticmethod
    def _meta(price=133800.0, traded="2026-10-09 16:35", end="2026-10-09 16:30"):
        return history_metadata(price, traded, end)

    def _fetch(self, mock_ticker, meta, rows=None):
        fake_ticker(
            mock_ticker,
            bars=self.ROWS if rows is None else rows,
            currency="GBp",
            tz="Europe/London",
            meta=meta,
        )
        return fetch_yahoo_quotes("CNX1.L", "2026-09-30")

    @patch("scrape_fund_price.yf.Ticker")
    def test_closing_price_from_metadata_fills_the_empty_bar(self, mock_ticker):
        """Test the finished session's price stands in for the null close."""
        quotes = self._fetch(mock_ticker, self._meta())
        self.assertEqual(
            quotes,
            [
                Quote("2026-10-08", "134720", "GBp"),
                Quote("2026-10-09", "133800", "GBp"),
            ],
        )

    @patch("scrape_fund_price.yf.Ticker")
    def test_a_session_still_open_is_not_filled(self, mock_ticker):
        """Test an intraday price is never stored as a close."""
        meta = self._meta(traded="2026-10-09 15:00", end="2026-10-09 16:30")
        quotes = self._fetch(mock_ticker, meta)
        self.assertEqual([q.date for q in quotes], ["2026-10-08"])

    @patch("scrape_fund_price.yf.Ticker")
    def test_metadata_from_another_day_is_not_used(self, mock_ticker):
        """Test the price must belong to the empty bar's own date."""
        meta = self._meta(traded="2026-10-08 16:35", end="2026-10-08 16:30")
        quotes = self._fetch(mock_ticker, meta)
        self.assertEqual([q.date for q in quotes], ["2026-10-08"])

    @patch("scrape_fund_price.yf.Ticker")
    def test_trading_period_that_moved_on_counts_as_closed(self, mock_ticker):
        """Test a later session end shows the bar's day is over."""
        quotes = self._fetch(mock_ticker, self._meta(end="2026-10-12 16:30"))
        self.assertEqual(quotes[-1], Quote("2026-10-09", "133800", "GBp"))

    @patch("scrape_fund_price.yf.Ticker")
    def test_only_the_newest_bar_is_filled(self, mock_ticker):
        """Test an empty bar in the middle of the window stays dropped."""
        rows = [("2026-10-07", float("nan")), ("2026-10-08", 134720.0)]
        quotes = self._fetch(mock_ticker, self._meta(), rows)
        self.assertEqual([q.date for q in quotes], ["2026-10-08"])

    @patch("scrape_fund_price.yf.Ticker")
    def test_unusable_metadata_falls_back_to_dropping_the_bar(self, mock_ticker):
        """Test bad metadata never raises or invents a price."""
        shapes = {
            "raises": RuntimeError("boom"),
            "empty": {},
            "no price": self._meta(price=float("nan")),
        }
        for shape, meta in shapes.items():
            with self.subTest(metadata=shape):
                quotes = self._fetch(mock_ticker, meta)
                self.assertEqual([q.date for q in quotes], ["2026-10-08"])


class TestYahooUnfinishedSession(unittest.TestCase):
    """Regression: the newest bar is stored before its session has closed (#84).

    A rebuild run at 12:56 UTC on 2026-10-19 stored SWDA.L's 2026-10-19 bar,
    a 13:46 London trade, while the session ran until 16:30.
    """

    ROWS = [("2026-10-16", 11000.0), ("2026-10-19", 10970.0)]

    @staticmethod
    def _meta(traded, end):
        return history_metadata(10970.0, traded, end)

    @staticmethod
    def _now(text):
        """A London wall-clock time, as the run's `now`."""
        london = ZoneInfo("Europe/London")
        return datetime.datetime.fromisoformat(text).replace(tzinfo=london)

    def _fetch(self, mock_ticker, meta, now, rows=None):
        fake_ticker(
            mock_ticker,
            bars=self.ROWS if rows is None else rows,
            currency="GBp",
            tz="Europe/London",
            meta=meta,
        )
        return fetch_yahoo_quotes("SWDA.L", "2026-10-01", now=self._now(now))

    @patch("scrape_fund_price.yf.Ticker")
    def test_drops_newest_bar_while_its_session_is_open(self, mock_ticker):
        """Test an intraday price is not stored as the day's close."""
        meta = self._meta(traded="2026-10-19 13:46", end="2026-10-19 16:30")
        quotes = self._fetch(mock_ticker, meta, "2026-10-19 13:56")
        self.assertEqual([q.date for q in quotes], ["2026-10-16"])

    @patch("scrape_fund_price.yf.Ticker")
    def test_keeps_newest_bar_once_its_session_has_ended(self, mock_ticker):
        """Test the bar is stored once the session's end has passed."""
        meta = self._meta(traded="2026-10-19 16:35", end="2026-10-19 16:30")
        quotes = self._fetch(mock_ticker, meta, "2026-10-19 21:05")
        self.assertEqual([q.date for q in quotes], ["2026-10-16", "2026-10-19"])

    @patch("scrape_fund_price.yf.Ticker")
    def test_keeps_previous_session_while_today_is_open(self, mock_ticker):
        """Test only a bar dated on the open session's day is held back."""
        rows = [("2026-10-15", 10900.0), ("2026-10-16", 11000.0)]
        meta = self._meta(traded="2026-10-19 13:46", end="2026-10-19 16:30")
        quotes = self._fetch(mock_ticker, meta, "2026-10-19 13:56", rows)
        self.assertEqual([q.date for q in quotes], ["2026-10-15", "2026-10-16"])

    @patch("scrape_fund_price.yf.Ticker")
    def test_unusable_metadata_keeps_the_newest_bar(self, mock_ticker):
        """Test a price is not lost because the session cannot be judged."""
        shapes = {"raises": RuntimeError("boom"), "empty": {}}
        for shape, meta in shapes.items():
            with self.subTest(metadata=shape):
                quotes = self._fetch(mock_ticker, meta, "2026-10-19 13:56")
                self.assertEqual([q.date for q in quotes], ["2026-10-16", "2026-10-19"])


# ===========================================================================
# Financial Times
# ===========================================================================


FT_ROWS = """
<tr>
  <td><span class="mod-ui-hide-small-below">Friday, September 18, 2026</span>
      <span class="mod-ui-hide-medium-above">Fri, Sep 18, 2026</span></td>
  <td>7.10</td><td>7.20</td><td>7.05</td><td>7.15</td>
  <td><span>0</span></td>
</tr>
<tr>
  <td><span class="mod-ui-hide-small-below">Thursday, September 17, 2026</span>
      <span class="mod-ui-hide-medium-above">Thu, Sep 17, 2026</span></td>
  <td>1,230.00</td><td>1,240.00</td><td>1,225.00</td><td>1,234.5600</td>
  <td><span>0</span></td>
</tr>
"""


class TestFTQuoteFetching(unittest.TestCase):
    """Test dated quote retrieval from the FT historical-prices endpoint.

    The page and the rows are GB00B1FXTF86's, recorded 2026-11-02 (see
    fixtures/): the tearsheet trimmed to the elements the parser reads, and
    the ajax response for 2026-10-19 to 2026-10-30 unchanged. FT reports no
    row for Tuesday 2026-10-20, the kind of omission the rebuild's retention
    rule exists for. FT_ROWS stands in only for shapes the recording lacks.
    """

    ISIN = "GB00B1FXTF86"
    NOW = utc(2026, 11, 2, 12)  # every recorded day has settled in New York
    PAGE = fixture_text("ft_GB00B1FXTF86_tearsheet.html")
    HISTORY = json.loads(fixture_text("ft_GB00B1FXTF86_history.json"))
    RECORDED_DATES = [
        "2026-10-19",
        "2026-10-21",
        "2026-10-22",
        "2026-10-23",
        "2026-10-26",
        "2026-10-27",
        "2026-10-28",
        "2026-10-29",
        "2026-10-30",
    ]

    @staticmethod
    def _responses(page=None, rows=None):
        """The page response then the ajax response, recorded unless given.

        A staticmethod because TestFTUnfinishedDay borrows it by class.
        """
        page_resp = MagicMock()
        page_resp.text = TestFTQuoteFetching.PAGE if page is None else page
        ajax_resp = MagicMock()
        ajax_resp.json.return_value = (
            TestFTQuoteFetching.HISTORY if rows is None else {"html": rows}
        )
        return [page_resp, ajax_resp]

    def fetch(self, start="2026-10-19", end="2026-10-30"):
        return fetch_ft_quotes(self.ISIN, start, end, now=self.NOW)

    @patch("scrape_fund_price.requests.get")
    def test_returns_dated_quotes_with_currency(self, mock_get):
        """Test the recorded rows become Quotes carrying FT's date and currency."""
        mock_get.side_effect = self._responses()
        quotes = self.fetch()
        self.assertEqual([q.date for q in quotes], self.RECORDED_DATES)
        self.assertEqual(quotes[0], Quote("2026-10-19", "6.99", "GBP"))
        self.assertEqual(quotes[-1], Quote("2026-10-30", "6.84", "GBP"))

    @patch("scrape_fund_price.requests.get")
    def test_uses_close_not_open(self, mock_get):
        """Test the closing price is taken, not the opening price."""
        mock_get.side_effect = self._responses(rows=FT_ROWS)
        quotes = self.fetch("2026-09-01", "2026-09-20")
        self.assertEqual([q.price for q in quotes], ["1234.5600", "7.15"])

    @patch("scrape_fund_price.requests.get")
    def test_strips_thousands_separators_without_float_conversion(self, mock_get):
        """Test FT text prices keep their exact digits, commas removed."""
        mock_get.side_effect = self._responses(rows=FT_ROWS)
        quotes = self.fetch("2026-09-01", "2026-09-20")
        self.assertEqual(quotes[0], Quote("2026-09-17", "1234.5600", "GBP"))

    @patch("scrape_fund_price.requests.get")
    def test_requests_the_page_then_the_endpoint_with_slash_dates(self, mock_get):
        """Test the page gives the numeric xid and the ajax call YYYY/MM/DD dates.

        The page carries the FT symbol GB00B1FXTF86:GBP in another module's
        config; only the historical module's numeric id is the xid.
        """
        mock_get.side_effect = self._responses()
        self.fetch()
        page_url, ajax_url = (call.args[0] for call in mock_get.call_args_list)
        self.assertEqual(
            page_url, scrape_fund_price.FT_HISTORICAL_PAGE.format(isin=self.ISIN)
        )
        self.assertEqual(
            ajax_url,
            scrape_fund_price.FT_HISTORICAL_AJAX.format(
                start="2026/10/19", end="2026/10/30", xid="28305998"
            ),
        )

    @patch("scrape_fund_price.requests.get")
    def test_missing_internal_id_raises(self, mock_get):
        """Test a page without the internal id is an error, not empty data."""
        mock_get.side_effect = self._responses(page="<html>no config here</html>")
        with self.assertRaises(ValueError) as error:
            self.fetch()
        self.assertIn(self.ISIN, str(error.exception))

    @patch("scrape_fund_price.requests.get")
    def test_no_rows_raises(self, mock_get):
        """Test an empty result set is an error so the fallback can run."""
        mock_get.side_effect = self._responses(rows="")
        with self.assertRaises(ValueError) as error:
            self.fetch()
        self.assertIn(self.ISIN, str(error.exception))

    @patch("scrape_fund_price.requests.get")
    def test_missing_currency_label_is_tolerated(self, mock_get):
        """Test quotes are still returned when no currency label is present."""
        page = self.PAGE.replace("Price (GBP)", "Price")
        mock_get.side_effect = self._responses(page=page)
        self.assertEqual(self.fetch()[0], Quote("2026-10-19", "6.99", ""))

    @patch("scrape_fund_price.requests.get")
    def test_a_row_without_four_price_cells_is_skipped(self, mock_get):
        """Test a truncated row is dropped rather than read as a quote."""
        short = (
            '<tr><td><span class="mod-ui-hide-small-below">Friday, September 18, '
            "2026</span></td><td>7.10</td></tr>"
        )
        mock_get.side_effect = self._responses(rows=short + FT_ROWS)
        quotes = self.fetch("2026-09-01", "2026-09-20")
        self.assertEqual([q.date for q in quotes], ["2026-09-17", "2026-09-18"])


class TestFTUnfinishedDay(unittest.TestCase):
    """Regression: FT rows dated today are stored before the day is over (#84).

    The 09:17 UTC run on 2026-10-16, which committed at 13:57 UTC, stored
    IE00B0M63516 at 33.45 for 2026-10-16; the evening run corrected it to
    33.34. FT carries no session metadata, so a row is held back until the
    US close (16:00 New York) on its own date has passed.
    """

    @staticmethod
    def _row(day, close):
        label = day.strftime("%A, %B %d, %Y").replace(" 0", " ")
        return (
            f'<tr><td><span class="mod-ui-hide-small-below">{label}</span></td>'
            f"<td>{close}</td><td>{close}</td><td>{close}</td><td>{close}</td>"
            "<td><span>0</span></td></tr>"
        )

    def _fetch(self, mock_get, days, now):
        rows = "".join(self._row(date.fromisoformat(d), "33.45") for d in days)
        mock_get.side_effect = TestFTQuoteFetching._responses(rows=rows)
        now = datetime.datetime.fromisoformat(now)
        return fetch_ft_quotes("IE00B0M63516", "2026-10-01", now=now)

    @patch("scrape_fund_price.requests.get")
    def test_drops_a_row_dated_today_before_the_us_close(self, mock_get):
        """Test a daytime run does not store today's provisional price."""
        quotes = self._fetch(
            mock_get, ["2026-10-15", "2026-10-16"], "2026-10-16T13:57:00+00:00"
        )
        self.assertEqual([q.date for q in quotes], ["2026-10-15"])

    @patch("scrape_fund_price.requests.get")
    def test_keeps_a_row_dated_today_after_the_us_close(self, mock_get):
        """Test the evening run stores the day's final price."""
        quotes = self._fetch(
            mock_get, ["2026-10-15", "2026-10-16"], "2026-10-16T21:05:00+00:00"
        )
        self.assertEqual([q.date for q in quotes], ["2026-10-15", "2026-10-16"])

    @patch("scrape_fund_price.requests.get")
    def test_the_cut_follows_new_york_daylight_saving(self, mock_get):
        """Test the cut is 21:00 UTC in winter, not 20:00 UTC all year."""
        days = ["2026-11-02", "2026-11-03"]
        early = self._fetch(mock_get, days, "2026-11-03T20:30:00+00:00")
        self.assertEqual([q.date for q in early], ["2026-11-02"])
        late = self._fetch(mock_get, days, "2026-11-03T21:00:00+00:00")
        self.assertEqual([q.date for q in late], days)

    @patch("scrape_fund_price.requests.get")
    def test_only_held_back_rows_is_not_an_error(self, mock_get):
        """Test a window holding only today's row returns nothing, not a failure.

        Raising would send the fund to the undated scraping fallback, which
        would store the same provisional price under today's date.
        """
        quotes = self._fetch(mock_get, ["2026-10-16"], "2026-10-16T13:57:00+00:00")
        self.assertEqual(quotes, [])

    @patch("scrape_fund_price.fetch_ft_quotes", return_value=[])
    def test_held_back_rows_do_not_fall_back_to_scraping(self, mock_fetch):
        """Test an empty dated result is returned rather than scraped."""
        browser = MagicMock()
        quotes = scrape_fund_quotes("FT", "IE00B0M63516", "2026-10-16", browser=browser)
        self.assertEqual(quotes, [])
        browser.page.assert_not_called()


# ===========================================================================
# investing.com
# ===========================================================================


class TestInvestingQuotes(unittest.TestCase):
    """Test the IV handler, the only source that still carries a dead fund.

    BN4MYX3 was liquidated in March 2024 and is absent from Yahoo and FT.
    justETF retains it but serves a converted, rounded series measured at a
    median 1.6% from the real closes, so it is not a substitute.
    """

    def _response(self, rows):
        response = MagicMock()
        response.json.return_value = {"data": rows}
        response.raise_for_status.return_value = None
        return response

    @patch("scrape_fund_price.requests.get")
    def test_returns_quotes_oldest_first(self, mock_get):
        """Test the newest-first payload is reversed for storage."""
        mock_get.return_value = self._response(
            [
                {
                    "rowDateTimestamp": "2024-03-13T00:00:00Z",
                    "last_closeRaw": "247.87500000000000",
                },
                {
                    "rowDateTimestamp": "2024-01-04T00:00:00Z",
                    "last_closeRaw": "218.94999694824219",
                },
            ]
        )
        quotes = fetch_investing_quotes("1182866", "2024-01-04", "2024-03-13")
        self.assertEqual([q.date for q in quotes], ["2024-01-04", "2024-03-13"])

    @patch("scrape_fund_price.requests.get")
    def test_float32_noise_is_removed_without_losing_the_half_penny(self, mock_get):
        """Test precision is preserved, not rounded to the displayed 2 dp.

        The endpoint stores float32, so 218.95 arrives as 218.94999694824219
        while a genuine half-penny close stays exact. Rounding both to the
        displayed value would throw away a real tick.
        """
        mock_get.return_value = self._response(
            [
                {
                    "rowDateTimestamp": "2024-01-04T00:00:00Z",
                    "last_closeRaw": "218.94999694824219",
                },
                {
                    "rowDateTimestamp": "2024-03-13T00:00:00Z",
                    "last_closeRaw": "247.87500000000000",
                },
            ]
        )
        quotes = fetch_investing_quotes("1182866", "2024-01-04", "2024-03-13")
        self.assertEqual([q.price for q in quotes], ["218.95", "247.875"])

    @patch("scrape_fund_price.requests.get")
    def test_window_is_passed_to_the_endpoint(self, mock_get):
        """Test the request asks for the window rather than filtering later."""
        mock_get.return_value = self._response(
            [{"rowDateTimestamp": "2024-01-04T00:00:00Z", "last_closeRaw": "218.95"}]
        )
        fetch_investing_quotes("1182866", "2024-01-04", "2024-03-13")
        url = mock_get.call_args[0][0]
        self.assertIn("1182866", url)
        self.assertIn("2024-01-04", url)
        self.assertIn("2024-03-13", url)

    @patch("scrape_fund_price.requests.get")
    def test_unusable_rows_are_skipped(self, mock_get):
        """Test a malformed row does not abort an otherwise good window."""
        mock_get.return_value = self._response(
            [
                {"rowDateTimestamp": "2024-01-05T00:00:00Z", "last_closeRaw": "-"},
                {"rowDateTimestamp": "2024-01-04T00:00:00Z", "last_closeRaw": "218.95"},
            ]
        )
        quotes = fetch_investing_quotes("1182866", "2024-01-04", "2024-01-05")
        self.assertEqual([q.date for q in quotes], ["2024-01-04"])

    @patch("scrape_fund_price.requests.get")
    def test_a_row_without_a_date_is_skipped(self, mock_get):
        """Test a row that cannot be dated is dropped, not stored under ''."""
        mock_get.return_value = self._response(
            [
                {"last_closeRaw": "200.00"},
                {"rowDateTimestamp": "2024-01-04T00:00:00Z", "last_closeRaw": "218.95"},
            ]
        )
        quotes = fetch_investing_quotes("1182866", "2024-01-04", "2024-01-05")
        self.assertEqual([q.date for q in quotes], ["2024-01-04"])

    @patch("scrape_fund_price.requests.get")
    def test_empty_payload_raises(self, mock_get):
        """Test an empty response is an error, not an empty import."""
        mock_get.return_value = self._response([])
        with self.assertRaises(ValueError):
            fetch_investing_quotes("1182866", "2024-01-04", "2024-03-13")

    def test_source_needs_no_browser(self):
        """Test IV is a plain HTTP source like YA and FT."""
        self.assertFalse(source_requires_browser("IV", "1182866"))

    @patch("scrape_fund_price.fetch_investing_quotes")
    def test_dispatch_routes_iv_to_the_handler(self, mock_fetch):
        """Test the shared dispatch knows the source code."""
        mock_fetch.return_value = [Quote("2024-01-04", "218.95", "")]
        quotes = scrape_fund_quotes("IV", "1182866", "2024-01-04", "2024-03-13")
        self.assertEqual(quotes[0].price, "218.95")
        mock_fetch.assert_called_once_with("1182866", "2024-01-04", "2024-03-13")


class TestInvestingEmptyPayloads(DataDirCase):
    """Test the IV handler survives the shapes a dead window returns.

    Asking investing.com for a window after a fund stopped publishing returns
    a body whose `data` key is present but null, which raised TypeError
    ("'NoneType' object is not iterable") instead of the ValueError callers
    catch.
    """

    def _response(self, payload):
        response = MagicMock()
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        return response

    @patch("scrape_fund_price.requests.get")
    def test_null_data_raises_value_error(self, mock_get):
        """Test a null payload is reported as no rows, not a crash."""
        mock_get.return_value = self._response({"data": None})
        with self.assertRaises(ValueError):
            fetch_investing_quotes("1190399", "2026-09-01", "2026-09-21")

    @patch("scrape_fund_price.requests.get")
    def test_missing_data_key_raises_value_error(self, mock_get):
        """Test an unexpected body shape is handled the same way."""
        mock_get.return_value = self._response({})
        with self.assertRaises(ValueError):
            fetch_investing_quotes("1190399", "2026-09-01", "2026-09-21")

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_the_import_records_it_as_a_failure(self, mock_quotes):
        """Test a holding whose window returns nothing is reported, not fatal."""
        mock_quotes.side_effect = ValueError("investing.com returned no rows")
        holding = ClosedHolding("X", "IV", "1190399", "USD", "2026-09-01", "2026-09-21")
        report = import_closed_holdings([holding], self.test_dir)
        self.assertTrue(report.failures)


# ===========================================================================
# Sources, retries and the scrape loop
# ===========================================================================


class TestFundPriceScraper(DataDirCase):

    TIMEOUT = (
        "Failed to perform, curl: (28) Operation timed out after "
        "30002 milliseconds with 0 bytes received."
    )

    def _browser_page(self, mock_playwright):
        """Wire the mocked Playwright up to one page and return it."""
        page = MagicMock()
        launch = mock_playwright.return_value.__enter__.return_value.chromium.launch
        launch.return_value.new_context.return_value.new_page.return_value = page
        return page

    def test_read_fund_ids(self):
        """Test reading fund IDs from a file."""
        funds_file = self.write_text(
            "test_funds.txt",
            "FT,IE0008368742\nYA,IDTG.L\nFT,JFM0003373\n  \nFT,GB00B1FXTF86\n",
        )
        self.assertEqual(
            read_fund_ids(funds_file),
            [
                ("FT", "IE0008368742"),
                ("YA", "IDTG.L"),
                ("FT", "JFM0003373"),
                ("FT", "GB00B1FXTF86"),
            ],
        )

    def test_get_source_config_ft(self):
        """Test FT source configuration."""
        url, selector = get_source_config("FT", "IE0008368742")
        expected_url = (
            "https://markets.ft.com/data/funds/tearsheet/summary?s=IE0008368742"
        )
        expected_selector = ".mod-ui-data-list__value"
        self.assertEqual(url, expected_url)
        self.assertEqual(selector, expected_selector)

    def test_get_source_config_yahoo(self):
        """Test Yahoo source configuration."""
        url, selector = get_source_config("YH", "IDTG.L")
        expected_url = "https://sg.finance.yahoo.com/quote/IDTG.L/"
        expected_selector = 'span[data-testid="qsp-price"]'
        self.assertEqual(url, expected_url)
        self.assertEqual(selector, expected_selector)

    def test_get_source_config_morningstar(self):
        """Test Morningstar source configuration."""
        url, selector = get_source_config("MS", "JFM0003373")
        expected_url = (
            "https://asialt.morningstar.com/DSB/QuickTake/overview.aspx?code=JFM0003373"
        )
        expected_selector = "#mainContent_quicktakeContent_fvOverview_lblNAV"
        self.assertEqual(url, expected_url)
        self.assertEqual(selector, expected_selector)

    def test_get_source_config_google_finance_returns_none(self):
        """Test that Google Finance source returns None (uses API instead)."""
        url, selector = get_source_config("GF", "AAPL")
        self.assertIsNone(url)
        self.assertIsNone(selector)

    def test_get_source_config_invalid(self):
        """Test invalid source configuration."""
        url, selector = get_source_config("INVALID", "TEST123")
        self.assertIsNone(url)
        self.assertIsNone(selector)

    def test_get_source_config_case_insensitive(self):
        """Test that source configuration is case insensitive."""
        url1, selector1 = get_source_config("ft", "IE0008368742")
        url2, selector2 = get_source_config("FT", "IE0008368742")
        self.assertEqual(url1, url2)
        self.assertEqual(selector1, selector2)

    @patch("scrape_fund_price.sync_playwright")
    def test_scrape_funds_mock(self, mock_playwright):
        """Test the scraping sources store the page's price, dated today."""
        page = self._browser_page(mock_playwright)
        page.locator.return_value.first.text_content.return_value = "123.45"

        # YH and MS still scrape a page; FT and YA use HTTP routes.
        results = scrape_funds([("YH", "IDTG.L"), ("MS", "JFM0003373")], self.test_dir)

        today = date.today().isoformat()
        self.assertEqual(
            list(results),
            [["IDTG.L", today, "123.45", ""], ["JFM0003373", today, "123.45", ""]],
        )
        self.assertEqual(self.read_text("latest_IDTG.L.price").strip(), "123.45")
        self.assertEqual(self.read_text("latest_JFM0003373.price").strip(), "123.45")

    @patch("scrape_fund_price.sync_playwright")
    def test_scrape_funds_removes_commas_from_all_price_sources(self, mock_playwright):
        """Test that every source stores prices without thousands separators."""
        page = self._browser_page(mock_playwright)
        page.locator.return_value.first.text_content.return_value = "1,234.56"

        test_funds = [
            ("FT", "FT_FUND"),
            ("YH", "SGLN.L"),
            ("MS", "MS_FUND"),
            ("YA", "API_FUND"),
        ]

        today = date.today().isoformat()
        with patch(
            "scrape_fund_price.fetch_ft_quotes",
            return_value=[Quote(today, "1234.56", "GBP")],
        ), patch(
            "scrape_fund_price.fetch_yahoo_quotes",
            return_value=[Quote(today, "1234.56", "USD")],
        ):
            results = scrape_funds(test_funds, self.test_dir)

        self.assertEqual([row[2] for row in results], ["1234.56"] * 4)
        for _, fund_id in test_funds:
            with self.subTest(fund=fund_id):
                price_file = self.read_text(f"latest_{fund_id}.price")
                self.assertEqual(price_file.strip(), "1234.56")

    def test_write_results(self):
        """Test the latest, history and rolling files share one sorted layout."""
        write_results(
            [
                ["IE0008368742", "2025-01-20", "123.45", "USD"],
                ["IDTG.L", "2025-01-20", "2.92", "GBP"],
            ],
            self.test_dir,
        )

        # Rows are sorted by date then fund, so output is deterministic.
        expected = (
            "Fund,Date,Price,Currency\n"
            "IDTG.L,2025-01-20,2.92,GBP\n"
            "IE0008368742,2025-01-20,123.45,USD\n"
        )
        for name in (
            "latest_prices.csv",
            "prices_history.csv",
            "prices_history_90_days.csv",
        ):
            with self.subTest(file=name):
                self.assertEqual(self.read_text(name), expected)

    def test_write_results_limits_rolling_history_to_90_calendar_days(self):
        """Test rolling history uses an inclusive 90-calendar-day window.

        TOO_OLD and AT_CUTOFF are fetched this run so that the only thing
        separating them is the date: the window also covers currently priced
        funds only, and excluding them for both reasons at once would stop
        this testing the cutoff at all.
        """
        self.write_csv(
            "prices_history.csv",
            ["Fund", "Date", "Price"],
            [
                ["TOO_OLD", "2025-01-01", "1.00"],
                ["AT_CUTOFF", "2025-01-02", "2.00"],
                ["FUTURE", "2025-04-02", "3.00"],
                ["INVALID", "not-a-date", "4.00"],
            ],
        )

        write_results(
            [
                ["TODAY", "2025-04-01", "5.00", "GBP"],
                ["AT_CUTOFF", "2025-01-02", "2.00", ""],
                ["TOO_OLD", "2025-01-01", "1.00", ""],
            ],
            self.test_dir,
        )

        # Legacy rows are preserved and upgraded with an empty currency.
        self.assertEqual(
            self.read_rows("prices_history.csv"),
            [
                ["TOO_OLD", "2025-01-01", "1.00", ""],
                ["AT_CUTOFF", "2025-01-02", "2.00", ""],
                ["TODAY", "2025-04-01", "5.00", "GBP"],
                ["FUTURE", "2025-04-02", "3.00", ""],
                ["INVALID", "not-a-date", "4.00", ""],
            ],
        )
        self.assertEqual(
            self.read_rows("prices_history_90_days.csv"),
            [
                ["AT_CUTOFF", "2025-01-02", "2.00", ""],
                ["TODAY", "2025-04-01", "5.00", "GBP"],
            ],
        )

    def test_write_results_empty_results_creates_empty_rolling_history(self):
        """Test an empty run still writes a valid rolling-history CSV."""
        write_results([], self.test_dir)
        self.assertEqual(
            self.read_text("prices_history_90_days.csv"), "Fund,Date,Price,Currency\n"
        )

    def test_write_results_append_history(self):
        """Test that history file appends new data."""
        write_results([["IE0008368742", "2025-01-20", "123.45", "USD"]], self.test_dir)
        write_results([["IDTG.L", "2025-01-21", "2.92", "GBP"]], self.test_dir)

        self.assertEqual(
            self.read_rows("prices_history.csv"),
            [
                ["IE0008368742", "2025-01-20", "123.45", "USD"],
                ["IDTG.L", "2025-01-21", "2.92", "GBP"],
            ],
        )

    def test_write_results_mixed_updates_and_new_entries(self):
        """Test that system handles both updates and new entries correctly."""
        write_results(
            [
                ["IE0008368742", "2025-01-20", "123.45", "USD"],
                ["IDTG.L", "2025-01-20", "2.92", "GBP"],
            ],
            self.test_dir,
        )

        write_results(
            [
                ["IE0008368742", "2025-01-20", "125.67", "USD"],
                ["IDTG.L", "2025-01-20", "2.92", "GBP"],
                ["AAPL", "2025-01-20", "150.25", "USD"],
            ],
            self.test_dir,
        )

        self.assertEqual(
            self.read_rows("prices_history.csv"),
            [
                ["AAPL", "2025-01-20", "150.25", "USD"],
                ["IDTG.L", "2025-01-20", "2.92", "GBP"],
                ["IE0008368742", "2025-01-20", "125.67", "USD"],
            ],
        )

    def test_scrape_funds_error_handling(self):
        """Test an unsupported source is a failure for that fund, no browser."""
        results = scrape_funds([("INVALID", "TEST123")], self.test_dir)

        # An unsupported source yields no dated price, and is reported
        # rather than stored as a fabricated N/A row.
        self.assertEqual(list(results), [])
        self.assertEqual(len(results.failures), 1)
        self.assertIn("TEST123", results.failures[0])

    def test_scrape_funds_with_api_source(self):
        """Test the Yahoo API source stores the quote's own date, no browser."""
        with patch(
            "scrape_fund_price.fetch_yahoo_quotes",
            return_value=[Quote("2026-09-18", "150.25", "USD")],
        ):
            results = scrape_funds([("YA", "AAPL")], self.test_dir)

        self.assertEqual(list(results), [["AAPL", "2026-09-18", "150.25", "USD"]])

    @patch("scrape_fund_price.sync_playwright")
    def test_scrape_funds_scraping_exception(self, mock_playwright):
        """Test error handling when scraping raises exception."""
        page = self._browser_page(mock_playwright)
        page.goto.side_effect = Exception("Timeout")

        results = scrape_funds([("YH", "TEST123")], self.test_dir)

        # No price could be obtained, so no dated row is invented.
        self.assertEqual(list(results), [])
        self.assertEqual(len(results.failures), 1)
        self.assertIn("TEST123", results.failures[0])
        self.assertEqual(page.goto.call_count, 3)

    @patch("scrape_fund_price.sync_playwright")
    def test_scrape_funds_retries_timeout_and_succeeds(self, mock_playwright):
        """Test transient timeout errors are retried before writing a price."""
        page = self._browser_page(mock_playwright)
        page.goto.side_effect = [Exception(self.TIMEOUT), None]
        page.locator.return_value.first.text_content.return_value = "123.45"

        results = scrape_funds([("YH", "TEST123")], self.test_dir)

        self.assertEqual(
            list(results), [["TEST123", date.today().isoformat(), "123.45", ""]]
        )
        self.assertEqual(results.failures, [])
        self.assertEqual(page.goto.call_count, 2)
        self.assertEqual(self.read_text("latest_TEST123.price").strip(), "123.45")

    @patch("scrape_fund_price.sync_playwright")
    def test_scrape_funds_uses_last_good_price_after_retry_failure(
        self, mock_playwright
    ):
        """Test persistent timeout errors keep the last good stored price."""
        page = self._browser_page(mock_playwright)
        page.goto.side_effect = Exception(self.TIMEOUT)

        self.write_csv(
            "prices_history.csv",
            ["Fund", "Date", "Price"],
            [
                ["TEST123", "2025-01-19", "111.11"],
                ["TEST123", date.today().isoformat(), f"Error: {self.TIMEOUT}"],
            ],
        )
        self.write_text("latest_TEST123.price", f"Error: {self.TIMEOUT}\n")

        results = scrape_funds([("YH", "TEST123")], self.test_dir)

        # No fabricated row for today; the real last price is carried instead,
        # against the date it actually belongs to.
        self.assertEqual(list(results), [])
        self.assertEqual(results.carried, [["TEST123", "2025-01-19", "111.11", ""]])
        self.assertEqual(len(results.failures), 1)
        self.assertIn("TEST123", results.failures[0])
        self.assertEqual(page.goto.call_count, 3)
        self.assertEqual(self.read_text("latest_TEST123.price").strip(), "111.11")

    def test_scrape_funds_retries_api_error_and_succeeds(self):
        """Test transient API errors are retried before writing a price."""
        with patch(
            "scrape_fund_price.fetch_yahoo_quotes",
            side_effect=[
                Exception("curl: (28) Operation timed out"),
                [Quote("2026-09-18", "220.50", "GBp")],
            ],
        ) as mock_quotes:
            results = scrape_funds([("YA", "IWDG.L")], self.test_dir)

        self.assertEqual(list(results), [["IWDG.L", "2026-09-18", "220.50", "GBp"]])
        self.assertEqual(results.failures, [])
        self.assertEqual(mock_quotes.call_count, 2)

    def test_scrape_funds_keeps_last_good_price_after_api_retry_failure(self):
        """Test persistent API errors keep the last good stored price."""
        self.write_csv(
            "prices_history.csv",
            ["Fund", "Date", "Price", "Currency"],
            [["IWDG.L", "2025-01-19", "210.75", "GBp"]],
        )

        with patch(
            "scrape_fund_price.fetch_yahoo_quotes",
            side_effect=Exception("curl: (28) Operation timed out"),
        ) as mock_quotes:
            results = scrape_funds([("YA", "IWDG.L")], self.test_dir)

        # The last good price is carried for reporting, against the date it
        # really belongs to, and is kept out of history.
        self.assertEqual(list(results), [])
        self.assertEqual(results.carried, [["IWDG.L", "2025-01-19", "210.75", "GBp"]])
        self.assertEqual(len(results.failures), 1)
        self.assertIn("IWDG.L", results.failures[0])
        self.assertEqual(mock_quotes.call_count, 3)

    def test_write_results_default_data_dir(self):
        """Test write_results without a data_dir writes under DATA_DIR."""
        with patch("scrape_fund_price.DATA_DIR", self.test_dir):
            write_results([["TEST123", "2025-01-20", "100.00", "GBP"]])

        self.assertEqual(
            self.read_rows("latest_prices.csv"),
            [["TEST123", "2025-01-20", "100.00", "GBP"]],
        )


class TestWindowedScraping(DataDirCase):
    """Test scrape_funds over dated windows, and lazy browser startup."""

    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_emits_a_row_per_quote_with_currency(self, mock_quotes):
        """Test every quote in the window becomes a dated result row."""
        mock_quotes.return_value = [
            Quote("2026-09-17", "1.50", "GBp"),
            Quote("2026-09-18", "1.60", "GBp"),
        ]
        results = scrape_funds([("YA", "SGLN.L")], self.test_dir)
        self.assertEqual(
            list(results),
            [
                ["SGLN.L", "2026-09-17", "1.50", "GBp"],
                ["SGLN.L", "2026-09-18", "1.60", "GBp"],
            ],
        )

    @patch("scrape_fund_price.sync_playwright")
    @patch("scrape_fund_price.fetch_ft_quotes")
    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_browser_not_started_for_api_only_config(self, mock_y, mock_ft, mock_pw):
        """Test Playwright is not launched when no fund needs scraping."""
        mock_y.return_value = [Quote("2026-09-18", "1.60", "USD")]
        mock_ft.return_value = [Quote("2026-09-18", "7.15", "GBP")]
        scrape_funds([("YA", "QQQ"), ("FT", "GB00B1FXTF86")], self.test_dir)
        mock_pw.assert_not_called()

    def test_ft_and_api_sources_do_not_require_a_browser(self):
        """Test source_requires_browser reflects the HTTP-only routes."""
        self.assertFalse(source_requires_browser("FT", "GB00B1FXTF86"))
        self.assertFalse(source_requires_browser("YA", "QQQ"))
        self.assertTrue(source_requires_browser("YH", "IDTG.L"))

    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_total_failure_writes_no_history_row(self, mock_quotes):
        """Test a fund that cannot be fetched contributes no dated row."""
        mock_quotes.side_effect = Exception("Network error")
        results = scrape_funds([("YA", "QQQ")], self.test_dir)
        self.assertEqual(list(results), [])
        self.assertEqual(len(results.failures), 1)
        self.assertIn("QQQ", results.failures[0])

    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_failed_fund_keeps_its_last_known_price_file(self, mock_quotes):
        """Test the per-fund price file is not overwritten with an error."""
        self.write_text("latest_QQQ.price", "700.00\n")
        mock_quotes.side_effect = Exception("Network error")
        scrape_funds([("YA", "QQQ")], self.test_dir)
        self.assertEqual(self.read_text("latest_QQQ.price"), "700.00\n")

    @patch("scrape_fund_price.sync_playwright")
    @patch("scrape_fund_price.scrape_price_with_common_settings")
    @patch("scrape_fund_price.fetch_ft_quotes")
    def test_ft_failure_falls_back_to_scraping(self, mock_ft, mock_scrape, mock_pw):
        """Test an FT endpoint failure still yields a price, dated as today."""
        mock_ft.side_effect = ValueError("FT internal id not found")
        mock_scrape.return_value = "7.15"
        results = scrape_funds([("FT", "GB00B1FXTF86")], self.test_dir)
        today = date.today().isoformat()
        self.assertEqual(list(results), [["GB00B1FXTF86", today, "7.15", ""]])
        mock_pw.assert_called()


class TestAliasPublishing(DataDirCase):
    """Test that one fetch publishes under every configured identifier."""

    SPEC = FundSpec("YA", "0P00000YAN", ("JFM0003373",))
    QUOTE = Quote("2026-09-17", "192.43", "USD")

    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_price_is_fetched_once_for_all_identifiers(self, mock_quotes):
        """Test aliases cost no extra network calls."""
        mock_quotes.return_value = [self.QUOTE]
        scrape_funds(
            [FundSpec("YA", "0P00000YAN", ("JFM0003373", "EXTRA"))], self.test_dir
        )
        self.assertEqual(mock_quotes.call_count, 1)

    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_each_identifier_gets_an_identical_row(self, mock_quotes):
        """Test every identifier records the same date, price and currency."""
        mock_quotes.return_value = [self.QUOTE]
        results = scrape_funds([self.SPEC], self.test_dir)
        self.assertEqual(
            list(results),
            [
                ["0P00000YAN", "2026-09-17", "192.43", "USD"],
                ["JFM0003373", "2026-09-17", "192.43", "USD"],
            ],
        )

    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_a_price_file_is_written_per_identifier(self, mock_quotes):
        """Test per-fund price files exist for aliases too."""
        mock_quotes.return_value = [self.QUOTE]
        scrape_funds([self.SPEC], self.test_dir)
        for fund_id in ("0P00000YAN", "JFM0003373"):
            with self.subTest(fund=fund_id):
                price_file = self.read_text(f"latest_{fund_id}.price")
                self.assertEqual(price_file.strip(), "192.43")

    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_fallback_uses_an_alias_stored_price(self, mock_quotes):
        """Test day-one failure can fall back to the alias's existing history.

        The lookup identifier is new and has nothing stored, while the alias
        carries the fund's whole history.
        """
        self.write_csv(
            "prices_history.csv",
            ["Fund", "Date", "Price", "Currency"],
            [["JFM0003373", "2026-09-17", "192.43", "USD"]],
        )

        mock_quotes.side_effect = Exception("Network error")
        results = scrape_funds([self.SPEC], self.test_dir)

        self.assertEqual(list(results), [])
        self.assertEqual(
            results.carried,
            [
                ["0P00000YAN", "2026-09-17", "192.43", "USD"],
                ["JFM0003373", "2026-09-17", "192.43", "USD"],
            ],
        )

    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_failure_is_reported_once_per_fund(self, mock_quotes):
        """Test an aliased fund is not reported twice for one failure."""
        mock_quotes.side_effect = Exception("Network error")
        results = scrape_funds([self.SPEC], self.test_dir)
        self.assertEqual(len(results.failures), 1)
        self.assertIn("0P00000YAN", results.failures[0])

    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_plain_tuples_are_still_accepted(self, mock_quotes):
        """Test existing callers passing (source, id) pairs keep working."""
        mock_quotes.return_value = [Quote("2026-09-18", "721.45", "USD")]
        results = scrape_funds([("YA", "QQQ")], self.test_dir)
        self.assertEqual(list(results), [["QQQ", "2026-09-18", "721.45", "USD"]])


# ===========================================================================
# Price storage
# ===========================================================================


class TestHistoryUpsert(DataDirCase):
    """Test (Fund, Date) keyed storage with upsert semantics."""

    def test_history_has_currency_column(self):
        """Test Currency is appended after Price, keeping column order stable."""
        write_results([["AAA", "2026-09-17", "1.50", "GBp"]], self.test_dir)
        self.assertEqual(
            self.read_text("prices_history.csv").splitlines()[0],
            "Fund,Date,Price,Currency",
        )

    def test_same_fund_and_date_is_replaced_not_duplicated(self):
        """Test a corrected price overwrites the row with the same key.

        The rolling window follows the history, so a re-run on the same day
        cannot duplicate there either.
        """
        write_results([["AAA", "2026-09-17", "1.50", "GBP"]], self.test_dir)
        write_results([["AAA", "2026-09-17", "1.55", "GBP"]], self.test_dir)
        for name in ("prices_history.csv", "prices_history_90_days.csv"):
            with self.subTest(file=name):
                self.assertEqual(
                    self.read_rows(name), [["AAA", "2026-09-17", "1.55", "GBP"]]
                )

    def test_same_fund_different_dates_both_kept(self):
        """Test distinct price dates accumulate."""
        rows = [
            ["AAA", "2026-09-17", "1.50", "GBP"],
            ["AAA", "2026-09-18", "1.60", "GBP"],
        ]
        write_results(rows, self.test_dir)
        self.assertEqual(self.read_rows("prices_history.csv"), rows)

    def test_rows_are_sorted_by_date_then_fund(self):
        """Test deterministic ordering so diffs stay readable."""
        write_results(
            [
                ["BBB", "2026-09-18", "2.00", "GBP"],
                ["AAA", "2026-09-18", "1.00", "GBP"],
                ["BBB", "2026-09-17", "1.90", "GBP"],
            ],
            self.test_dir,
        )
        rows = self.read_rows("prices_history.csv")
        self.assertEqual(
            [(r[0], r[1]) for r in rows],
            [("BBB", "2026-09-17"), ("AAA", "2026-09-18"), ("BBB", "2026-09-18")],
        )

    def test_rewriting_identical_data_changes_nothing(self):
        """Test the run is idempotent, so a re-run produces no diff."""
        rows = [
            ["AAA", "2026-09-17", "1.50", "GBP"],
            ["BBB", "2026-09-17", "2.50", "USD"],
        ]
        write_results(rows, self.test_dir)
        first = self.read_text("prices_history.csv")
        write_results(rows, self.test_dir)
        self.assertEqual(self.read_text("prices_history.csv"), first)

    def test_unusable_prices_are_never_stored(self):
        """Test error markers and N/A never enter the history file."""
        write_results(
            [
                ["AAA", "2026-09-17", "Error: Timeout", ""],
                ["BBB", "2026-09-17", "N/A", ""],
                ["CCC", "2026-09-17", "3.00", "GBP"],
            ],
            self.test_dir,
        )
        self.assertEqual(
            self.read_rows("prices_history.csv"), [["CCC", "2026-09-17", "3.00", "GBP"]]
        )

    def test_legacy_three_column_history_is_upgraded(self):
        """Test pre-existing rows without a currency remain readable."""
        self.write_csv(
            "prices_history.csv",
            ["Fund", "Date", "Price"],
            [["OLD", "2026-09-01", "9.99"]],
        )
        write_results([["AAA", "2026-09-17", "1.50", "GBP"]], self.test_dir)
        self.assertEqual(
            self.read_text("prices_history.csv"),
            "Fund,Date,Price,Currency\nOLD,2026-09-01,9.99,\nAAA,2026-09-17,1.50,GBP\n",
        )

    def test_latest_prices_takes_the_newest_date_per_fund(self):
        """Test latest_prices.csv reports each fund's most recent price date."""
        write_results(
            [
                ["AAA", "2026-09-16", "1.40", "GBP"],
                ["AAA", "2026-09-18", "1.60", "GBP"],
                ["AAA", "2026-09-17", "1.50", "GBP"],
            ],
            self.test_dir,
        )
        self.assertEqual(
            self.read_text("latest_prices.csv"),
            "Fund,Date,Price,Currency\nAAA,2026-09-18,1.60,GBP\n",
        )

    def test_rolling_window_filters_on_price_date(self):
        """Test the 90-day window is measured against price dates."""
        write_results(
            [
                ["OLD", "2026-06-01", "1.00", "GBP"],
                ["NEW", "2026-09-18", "2.00", "GBP"],
            ],
            self.test_dir,
        )
        self.assertEqual(
            self.read_rows("prices_history_90_days.csv"),
            [["NEW", "2026-09-18", "2.00", "GBP"]],
        )

    def test_a_damaged_history_row_is_skipped_on_read(self):
        """Test a row shorter than Fund,Date,Price is ignored, not a crash."""
        path = self.write_text(
            "prices_history.csv",
            "Fund,Date,Price,Currency\nAAA,2026-09-17\nAAA,2026-09-18,1.50,GBP\n",
        )
        self.assertEqual(list(read_history_rows(path)), [("AAA", "2026-09-18")])

    def test_read_keyed_csv_pads_truncates_and_skips_what_the_key_rejects(self):
        """Test the reader every storage file shares (#112).

        A missing file is empty; a short row is padded and a long one cut to
        the header's width; the key decides what a row is stored under and
        a row it maps to None is left out, in file order.
        """
        header = ["Name", "Date", "Value"]
        key = lambda row: (row[0], row[1]) if row[0] else None  # noqa: E731
        self.assertEqual(
            scrape_fund_price.read_keyed_csv(self.path("none.csv"), header, key), {}
        )
        path = self.write_text(
            "keyed.csv",
            "Name,Date,Value\nB,2026-01-02,2,extra\n,2026-01-03,3\nA,2026-01-01\n",
        )
        self.assertEqual(
            scrape_fund_price.read_keyed_csv(path, header, key),
            {
                ("B", "2026-01-02"): ["B", "2026-01-02", "2"],
                ("A", "2026-01-01"): ["A", "2026-01-01", ""],
            },
        )

    def test_write_sorted_csv_creates_the_directory_and_returns_the_order(self):
        """Test the writer every storage file shares (#112).

        The directory is created, the header comes first, the rows follow in
        key order with LF endings, and the rows are returned as written.
        """
        path = self.path(os.path.join("new", "sorted.csv"))
        rows = [["B", "2026-01-02", "2"], ["A", "2026-01-01", "1"]]
        ordered = scrape_fund_price.write_sorted_csv(
            path, ["Name", "Date", "Value"], rows, key=lambda row: row[1]
        )
        self.assertEqual(ordered, [rows[1], rows[0]])
        with open(path, "rb") as file:
            self.assertEqual(
                file.read(), b"Name,Date,Value\nA,2026-01-01,1\nB,2026-01-02,2\n"
            )


class TestLatestNeverGoesBackwards(DataDirCase):
    """Regression: a stale fetch replaced newer latest prices with older ones.

    On 2026-10-10 Yahoo served no Friday close for the London ETFs, so the run
    fetched Thursday as its newest bar and latest_prices.csv (and the per-fund
    .price files) were rewritten from 2026-10-09 back to 2026-10-08. History
    kept the Friday rows; only the "latest" views regressed.
    """

    FRIDAY = [
        ["CNX1.L", "2026-10-09", "133800", "GBp"],
        ["IWDG.L", "2026-10-09", "1270.5", "GBp"],
        ["QQQ", "2026-10-09", "751.27", "USD"],
        ["SGLN.L", "2026-10-09", "6141", "GBp"],
    ]
    THURSDAY = [
        ["CNX1.L", "2026-10-08", "134720", "GBp"],
        ["IWDG.L", "2026-10-08", "1263", "GBp"],
        ["QQQ", "2026-10-08", "747.58", "USD"],
        ["SGLN.L", "2026-10-08", "6039", "GBp"],
    ]

    def _read(self, name):
        return self.read_rows(name)

    def _price_file(self, fund):
        return self.read_text(f"latest_{fund}.price").strip()

    def _stale_run(self):
        """Friday is stored, then a run whose newest bar is Thursday."""
        write_results(list(self.FRIDAY), self.test_dir)
        write_results(list(self.THURSDAY), self.test_dir)

    def test_latest_prices_keeps_the_newer_row(self):
        """Test an older fetched date does not replace the stored newer row."""
        self._stale_run()
        self.assertEqual(self._read("latest_prices.csv"), self.FRIDAY)

    def test_stale_fetch_is_logged(self):
        """Test the ignored stale row is reported, not silently dropped."""
        write_results(list(self.FRIDAY), self.test_dir)
        with patch("builtins.print") as mock_print:
            write_results([self.THURSDAY[0]], self.test_dir)
        output = " ".join(str(c.args[0]) for c in mock_print.call_args_list)
        self.assertIn("CNX1.L", output)
        self.assertIn("2026-10-08", output)
        self.assertIn("2026-10-09", output)

    def test_history_keeps_the_newer_row(self):
        """Test a stale fetch never costs history its newer rows."""
        self._stale_run()
        history = self._read("prices_history.csv")
        for row in self.FRIDAY + self.THURSDAY:
            self.assertIn(row, history)

    def test_rolling_window_keeps_the_newer_row(self):
        """Test the 90-day file also still holds the newer rows."""
        self._stale_run()
        rolling = self._read("prices_history_90_days.csv")
        for row in self.FRIDAY:
            self.assertIn(row, rolling)

    def test_same_date_still_replaces_the_stored_row(self):
        """Test a correction to the stored date is still applied."""
        write_results(list(self.FRIDAY), self.test_dir)
        write_results([["CNX1.L", "2026-10-09", "133850", "GBp"]], self.test_dir)
        latest = {r[0]: r for r in self._read("latest_prices.csv")}
        self.assertEqual(latest["CNX1.L"][2], "133850")

    def test_newer_date_still_advances_the_row(self):
        """Test the guard does not stop a genuinely newer price."""
        write_results(list(self.THURSDAY), self.test_dir)
        write_results(list(self.FRIDAY), self.test_dir)
        self.assertEqual(self._read("latest_prices.csv"), self.FRIDAY)

    def test_fund_with_nothing_stored_takes_what_it_is_given(self):
        """Test the guard only applies against a stored row."""
        write_results([self.THURSDAY[0]], self.test_dir)
        self.assertEqual(self._read("latest_prices.csv"), [self.THURSDAY[0]])

    def test_stored_latest_row_newer_than_history_is_kept(self):
        """Test latest_prices.csv itself is a floor, not only the history."""
        write_results(list(self.FRIDAY), self.test_dir)
        os.remove(self.path("prices_history.csv"))
        write_results([self.THURSDAY[0]], self.test_dir)
        latest = {r[0]: r for r in self._read("latest_prices.csv")}
        self.assertEqual(latest["CNX1.L"], self.FRIDAY[0])

    def test_carried_row_does_not_regress_latest(self):
        """Test a failed fund keeps its newest stored row."""
        write_results(list(self.FRIDAY), self.test_dir)
        results = ScrapeResults(rows=[self.THURSDAY[1]])
        results.carried.append(list(self.FRIDAY[0]))
        write_results(results, self.test_dir)
        latest = {r[0]: r for r in self._read("latest_prices.csv")}
        self.assertEqual(latest["CNX1.L"], self.FRIDAY[0])
        self.assertEqual(latest["IWDG.L"], self.FRIDAY[1])

    @patch("scrape_fund_price.sync_playwright")
    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_price_file_keeps_the_newer_price(self, mock_quotes, mock_pw):
        """Test latest_<id>.price is not rewritten from an older bar."""
        write_results(list(self.FRIDAY), self.test_dir)
        write_latest_price_file("CNX1.L", "133800", self.test_dir)
        mock_quotes.return_value = [
            Quote("2026-10-07", "135120", "GBp"),
            Quote("2026-10-08", "134720", "GBp"),
        ]
        scrape_funds([("YA", "CNX1.L")], self.test_dir)
        self.assertEqual(self._price_file("CNX1.L"), "133800")

    @patch("scrape_fund_price.sync_playwright")
    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_price_file_advances_on_a_newer_bar(self, mock_quotes, mock_pw):
        """Test the price file still follows a newer bar."""
        write_results(list(self.THURSDAY), self.test_dir)
        write_latest_price_file("CNX1.L", "134720", self.test_dir)
        mock_quotes.return_value = [Quote("2026-10-09", "133800", "GBp")]
        scrape_funds([("YA", "CNX1.L")], self.test_dir)
        self.assertEqual(self._price_file("CNX1.L"), "133800")

    @patch("scrape_fund_price.sync_playwright")
    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_whole_daily_run_with_stale_bars(self, mock_quotes, mock_pw):
        """Test the exact 2026-10-10 sequence end to end."""
        write_results(list(self.FRIDAY), self.test_dir)
        for row in self.FRIDAY:
            write_latest_price_file(row[0], row[2], self.test_dir)
        quotes = {row[0]: [Quote(row[1], row[2], row[3])] for row in self.THURSDAY}
        mock_quotes.side_effect = lambda symbol, start, end=None: quotes[symbol]
        results = scrape_funds([("YA", s) for s in quotes], self.test_dir)
        write_results(results, self.test_dir)
        self.assertEqual(self._read("latest_prices.csv"), self.FRIDAY)
        self.assertEqual(self._price_file("CNX1.L"), "133800")
        self.assertEqual(self._price_file("IWDG.L"), "1270.5")

    def test_latest_fx_keeps_the_newer_rate(self):
        """Test latest_fx.csv is derived from history and cannot regress.

        TestFxStorage covers the newest date winning within one write; this
        is the stale second run, an older date written after a newer one.
        """
        write_fx_results([["USDGBP", "2026-10-09", "0.75568"]], self.test_dir)
        write_fx_results([["USDGBP", "2026-10-08", "0.75672"]], self.test_dir)
        self.assertEqual(
            self._read("latest_fx.csv"), [["USDGBP", "2026-10-09", "0.75568"]]
        )


class TestRollingWindowCoversCurrentFundsOnly(DataDirCase):
    """Test the 90-day window tracks latest_prices.csv, not raw history.

    A closed holding can have real prices inside the last 90 days: FBTC ran to
    2026-08-17. Those rows belong in history, but the rolling window answers
    "what is being priced now" alongside latest_prices.csv, and the daily run
    would otherwise start emitting rows for an instrument it no longer fetches.
    """

    def setUp(self):
        super().setUp()
        self.recent = (date.today() - timedelta(days=5)).isoformat()

    def _rolling(self):
        return self.read_rows("prices_history_90_days.csv")

    def test_closed_holdings_are_excluded_from_the_window(self):
        """Test a recent closed-holding row stays out of the rolling file."""
        rows = [
            ["QQQ", self.recent, "266.28", "USD"],
            ["FBTC", self.recent, "55.94", "USD"],
        ]
        write_history_files(
            rows, self.test_dir, latest={"QQQ": ["QQQ", self.recent, "266.28", "USD"]}
        )
        self.assertEqual([row[0] for row in self._rolling()], ["QQQ"])

    def test_history_still_keeps_every_row(self):
        """Test excluding them from the window does not drop them."""
        rows = [
            ["QQQ", self.recent, "266.28", "USD"],
            ["FBTC", self.recent, "55.94", "USD"],
        ]
        write_history_files(
            rows, self.test_dir, latest={"QQQ": ["QQQ", self.recent, "266.28", "USD"]}
        )
        stored = self.read_rows("prices_history.csv")
        self.assertEqual(sorted(row[0] for row in stored), ["FBTC", "QQQ"])

    def test_derived_latest_still_covers_everything(self):
        """Test the default path is unchanged when no latest is supplied.

        A caller that does not pass `latest` has no notion of a closed
        holding, so the window must keep its old meaning for it.
        """
        rows = [
            ["QQQ", self.recent, "266.28", "USD"],
            ["AAA", self.recent, "1.50", "GBP"],
        ]
        write_history_files(rows, self.test_dir)
        self.assertEqual(sorted(row[0] for row in self._rolling()), ["AAA", "QQQ"])


class TestLineEndings(DataDirCase):
    """Test every written file uses LF, independent of platform.

    csv.writer defaults to CRLF on every platform. Combined with git's
    autocrlf on Windows normalising to LF while a Linux runner stores CRLF,
    that made the data files flip on every handover between a local commit and
    a scheduled run: one overnight commit showed 3,906 insertions for 4 rows
    of real data.
    """

    def assertNoCarriageReturns(self, *names):
        for name in names:
            path = self.path(name)
            self.assertTrue(os.path.exists(path), f"{name} was not written")
            with open(path, "rb") as f:
                raw = f.read()
            self.assertNotIn(b"\r", raw, f"{name} contains carriage returns")
            self.assertGreater(raw.count(b"\n"), 0, f"{name} has no line breaks")

    def test_price_files_use_lf(self):
        """Test history, latest and rolling files are LF."""
        write_history_files(
            [
                ["AAA", "2026-09-18", "1.50", "GBP"],
                ["BBB", "2026-09-18", "2.50", "USD"],
            ],
            self.test_dir,
        )
        self.assertNoCarriageReturns(
            "prices_history.csv", "latest_prices.csv", "prices_history_90_days.csv"
        )

    def test_fx_files_use_lf(self):
        """Test FX history and latest rates are LF."""
        write_fx_files([["USDGBP", "2026-09-18", "0.748615"]], self.test_dir)
        self.assertNoCarriageReturns("fx_history.csv", "latest_fx.csv")

    def test_summary_files_use_lf(self):
        """Test the summary CSV and Markdown are LF."""
        rows = build_price_summary(
            [
                ["AAA", "2026-09-17", "1.00", "GBP"],
                ["AAA", "2026-09-18", "1.50", "GBP"],
            ],
            [FundSpec("YA", "AAA", ())],
            [],
            "2026-09-18",
        )
        write_summary(rows, [], "2026-09-18", self.test_dir)
        self.assertNoCarriageReturns("daily_summary.csv", "daily_summary.md")

    @patch("scrape_fund_price.yf.Ticker")
    def test_historical_mode_csv_uses_lf(self, mock_ticker):
        """Test the --history export is LF too."""
        fake_ticker(mock_ticker, bars=[("2026-09-18", 1.5)])
        result = fetch_historical_data(
            "AAPL", "2026-09-01", "2026-09-18", self.test_dir
        )
        self.assertFalse(result.startswith("Error:"), result)
        self.assertNoCarriageReturns(os.path.basename(result))

    def test_price_file_per_fund_uses_lf(self):
        """Test the single-value .price files are LF."""
        write_latest_price_file("AAA", "1.50", self.test_dir)
        self.assertNoCarriageReturns("latest_AAA.price")


class TestPriceFallbackSources(DataDirCase):
    """Test the last-known-price fallback chain used when fetches fail."""

    HEADER = ["Fund", "Date", "Price"]

    def test_read_latest_csv_price_returns_usable_price(self):
        """Test latest_prices.csv supplies a fallback price for a known fund."""
        self.write_csv(
            "latest_prices.csv", self.HEADER, [["AAPL", "2026-01-01", "150.25"]]
        )
        self.assertEqual(read_latest_csv_price("AAPL", self.test_dir), "150.25")

    def test_read_latest_csv_price_skips_unusable_values(self):
        """Test error and N/A entries are not reused as prices."""
        self.write_csv(
            "latest_prices.csv",
            self.HEADER,
            [
                ["AAPL", "2026-01-01", "Error: timeout"],
                ["MSFT", "2026-01-01", "N/A"],
            ],
        )
        self.assertIsNone(read_latest_csv_price("AAPL", self.test_dir))
        self.assertIsNone(read_latest_csv_price("MSFT", self.test_dir))

    def test_read_latest_csv_price_unknown_fund_returns_none(self):
        """Test a fund absent from latest_prices.csv yields no fallback."""
        self.write_csv(
            "latest_prices.csv", self.HEADER, [["AAPL", "2026-01-01", "150.25"]]
        )
        self.assertIsNone(read_latest_csv_price("TSLA", self.test_dir))

    def test_read_history_price_returns_most_recent_usable(self):
        """Test history fallback prefers the last usable row for the fund."""
        self.write_csv(
            "prices_history.csv",
            self.HEADER,
            [
                ["AAPL", "2026-01-01", "100.00"],
                ["AAPL", "2026-01-02", "110.00"],
                ["MSFT", "2026-01-02", "200.00"],
            ],
        )
        self.assertEqual(read_history_price("AAPL", self.test_dir), "110.00")

    def test_read_history_price_all_unusable_returns_none(self):
        """Test history with only error rows provides no fallback price."""
        self.write_csv(
            "prices_history.csv",
            self.HEADER,
            [
                ["AAPL", "2026-01-01", "Error: timeout"],
                ["AAPL", "2026-01-02", "N/A"],
            ],
        )
        self.assertIsNone(read_history_price("AAPL", self.test_dir))

    def test_get_last_known_price_prefers_price_file_over_csv(self):
        """Test the fallback chain checks the per-fund price file first."""
        self.write_text("latest_AAPL.price", "999.99\n")
        self.write_csv(
            "latest_prices.csv", self.HEADER, [["AAPL", "2026-01-01", "150.25"]]
        )
        self.assertEqual(get_last_known_price("AAPL", self.test_dir), "999.99")

    def test_get_last_known_price_falls_through_to_history(self):
        """Test the chain reaches prices_history.csv when earlier sources are unusable."""
        self.write_csv(
            "latest_prices.csv", self.HEADER, [["AAPL", "2026-01-01", "Error: timeout"]]
        )
        self.write_csv(
            "prices_history.csv", self.HEADER, [["AAPL", "2025-12-31", "123.45"]]
        )
        self.assertEqual(get_last_known_price("AAPL", self.test_dir), "123.45")

    def test_get_last_known_price_returns_none_when_nothing_stored(self):
        """Test an unknown fund with no stored data has no fallback."""
        self.assertIsNone(get_last_known_price("AAPL", self.test_dir))


class TestDefaultDataDirectory(unittest.TestCase):
    """Every writer and runner defaults data_dir to DATA_DIR at call time.

    Call-time binding is what lets setUpModule redirect the whole suite; a
    default bound at import would write into the repository's data/ (#103).
    """

    def test_each_entry_point_writes_under_the_module_data_dir(self):
        """Test each default lands in DATA_DIR as patched, with nothing elsewhere."""
        calls = {
            "scrape_funds": lambda: scrape_funds([]),
            "write_summary": lambda: write_summary([], [], "2026-11-02"),
            "snap_fx_rates": lambda: snap_fx_rates([]),
            "write_fx_results": lambda: write_fx_results(ScrapeResults()),
            "backfill_fx": lambda: backfill_fx([], "2026-11-01"),
            "backfill_history": lambda: backfill_history([], "2026-11-01"),
            "import_closed_holdings": lambda: import_closed_holdings([]),
        }
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "out")
            with ExitStack() as stack:
                stack.enter_context(patch("scrape_fund_price.DATA_DIR", target))
                stack.enter_context(
                    patch("scrape_fund_price.read_fx_pairs", return_value=[])
                )
                stack.enter_context(patch("builtins.print"))
                for name, call in calls.items():
                    with self.subTest(name):
                        call()
            written = os.listdir(target)
            self.assertIn("daily_summary.csv", written)
            self.assertIn("fx_history.csv", written)


# ===========================================================================
# Backfill and rebuild
# ===========================================================================


class TestBackfillArguments(unittest.TestCase):
    """Test the backfill command-line mode."""

    def test_backfill_requires_a_start_date(self):
        """Test --backfill without --from is rejected."""
        args = parse_arguments(["--backfill"])
        self.assertTrue(args.backfill)
        self.assertIsNone(args.start)

    def test_backfill_accepts_a_start_date(self):
        """Test --backfill --from parses."""
        args = parse_arguments(["--backfill", "--from", "2023-01-01"])
        self.assertTrue(args.backfill)
        self.assertEqual(args.start, "2023-01-01")

    def test_validate_rejects_missing_start(self):
        """Test the missing start date is reported, not assumed."""
        self.assertIn("--from", validate_backfill_args(parse_arguments(["--backfill"])))

    def test_validate_rejects_malformed_start(self):
        """Test a non-ISO date is rejected."""
        args = parse_arguments(["--backfill", "--from", "01/01/2023"])
        self.assertIn("YYYY-MM-DD", validate_backfill_args(args))

    def test_validate_rejects_future_start(self):
        """Test a future start date is rejected rather than fetching nothing."""
        future = (date.today() + timedelta(days=1)).isoformat()
        args = parse_arguments(["--backfill", "--from", future])
        self.assertIn("future", validate_backfill_args(args).lower())

    def test_validate_rejects_backfill_with_history(self):
        """Test the two bulk modes cannot be combined."""
        args = parse_arguments(
            ["--backfill", "--from", "2023-01-01", "--history", "AAPL"]
        )
        self.assertIn("--history", validate_backfill_args(args))

    def test_validate_accepts_a_good_start(self):
        """Test a valid invocation produces no error."""
        args = parse_arguments(["--backfill", "--from", "2023-01-01"])
        self.assertIsNone(validate_backfill_args(args))


class TestBackfillRebuild(BackfillCase):
    """Test the delete-then-insert rebuild rule."""

    HEADER = ["Fund", "Date", "Price", "Currency"]

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_carry_forward_rows_are_removed(self, mock_quotes):
        """Test rows on dates the source never reports do not survive.

        This is why the rebuild deletes rather than upserting: a weekend
        carry-forward has no incoming row to replace it.
        """
        self.write_csv(
            "prices_history.csv",
            self.HEADER,
            [
                ["QQQ", "2026-09-18", "721.45", ""],
                ["QQQ", "2026-09-19", "721.45", ""],  # Saturday carry-forward
                ["QQQ", "2026-09-20", "721.45", ""],  # Sunday carry-forward
            ],
        )
        mock_quotes.return_value = [Quote("2026-09-18", "721.45", "USD")]

        backfill_history([FundSpec("YA", "QQQ", ())], "2026-09-01", self.test_dir)

        self.assertEqual(
            self.read_rows("prices_history.csv"),
            [["QQQ", "2026-09-18", "721.45", "USD"]],
        )

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_failed_instrument_keeps_its_existing_rows(self, mock_quotes):
        """Test a fetch failure never destroys unreplaceable data.

        The report says so per identifier, with the row count it kept.
        """
        self.write_csv(
            "prices_history.csv", self.HEADER, [["QQQ", "2026-09-18", "721.45", "USD"]]
        )
        mock_quotes.side_effect = Exception("Network error")

        report = backfill_history(
            [FundSpec("YA", "QQQ", ())], "2026-09-01", self.test_dir
        )

        self.assertEqual(
            self.read_rows("prices_history.csv"),
            [["QQQ", "2026-09-18", "721.45", "USD"]],
        )
        self.assertEqual(len(report.failures), 1)
        self.assertIn("QQQ", report.failures[0])
        entry = next(e for e in report.entries if e["identifier"] == "QQQ")
        self.assertEqual(
            (entry["status"], entry["before"], entry["deleted"]),
            ("failed, kept existing", 1, 0),
        )

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_one_failure_does_not_block_other_instruments(self, mock_quotes):
        """Test instruments are rebuilt independently."""
        self.write_csv(
            "prices_history.csv",
            self.HEADER,
            [
                ["QQQ", "2026-09-19", "700.00", ""],
                ["GRAB", "2026-09-19", "2.50", ""],
            ],
        )

        def side_effect(source, fund_id, start, end=None, browser=None):
            if fund_id == "QQQ":
                raise Exception("Network error")
            return [Quote("2026-09-18", "2.795", "USD")]

        mock_quotes.side_effect = side_effect

        backfill_history(
            [FundSpec("YA", "QQQ", ()), FundSpec("YA", "GRAB", ())],
            "2026-09-01",
            self.test_dir,
        )

        self.assertEqual(
            self.read_rows("prices_history.csv"),
            [
                ["GRAB", "2026-09-18", "2.795", "USD"],
                ["QQQ", "2026-09-19", "700.00", ""],
            ],
        )

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_rows_before_the_start_date_are_preserved(self, mock_quotes):
        """Test the rebuild only touches the requested range."""
        self.write_csv(
            "prices_history.csv",
            self.HEADER,
            [
                ["QQQ", "2022-06-01", "300.00", "USD"],
                ["QQQ", "2026-09-19", "700.00", ""],
            ],
        )
        mock_quotes.return_value = [Quote("2026-09-18", "721.45", "USD")]

        backfill_history([FundSpec("YA", "QQQ", ())], "2023-01-01", self.test_dir)

        self.assertEqual(
            self.read_rows("prices_history.csv"),
            [
                ["QQQ", "2022-06-01", "300.00", "USD"],
                ["QQQ", "2026-09-18", "721.45", "USD"],
            ],
        )

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_unconfigured_identifiers_are_preserved(self, mock_quotes):
        """Test a fund removed from funds.txt keeps its recorded history."""
        self.write_csv(
            "prices_history.csv",
            self.HEADER,
            [
                ["RETIRED", "2026-09-18", "1.23", "GBP"],
                ["QQQ", "2026-09-19", "700.00", ""],
            ],
        )
        mock_quotes.return_value = [Quote("2026-09-18", "721.45", "USD")]

        backfill_history([FundSpec("YA", "QQQ", ())], "2023-01-01", self.test_dir)

        self.assertEqual(
            self.read_rows("prices_history.csv"),
            [
                ["QQQ", "2026-09-18", "721.45", "USD"],
                ["RETIRED", "2026-09-18", "1.23", "GBP"],
            ],
        )

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_aliases_are_rebuilt_from_a_single_fetch(self, mock_quotes):
        """Test both identifiers get the same rebuilt series."""
        mock_quotes.return_value = [Quote("2026-09-17", "192.43", "USD")]

        backfill_history(
            [FundSpec("YA", "0P00000YAN", ("JFM0003373",))],
            "2023-01-01",
            self.test_dir,
        )

        self.assertEqual(mock_quotes.call_count, 1)
        self.assertEqual(
            self.read_rows("prices_history.csv"),
            [
                ["0P00000YAN", "2026-09-17", "192.43", "USD"],
                ["JFM0003373", "2026-09-17", "192.43", "USD"],
            ],
        )

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_rebuild_is_idempotent(self, mock_quotes):
        """Test re-running the rebuild produces no diff."""
        mock_quotes.return_value = [
            Quote("2026-09-17", "192.43", "USD"),
            Quote("2026-09-18", "193.00", "USD"),
        ]
        specs = [FundSpec("YA", "0P00000YAN", ("JFM0003373",))]

        backfill_history(specs, "2023-01-01", self.test_dir)
        first = self.read_text("prices_history.csv")
        backfill_history(specs, "2023-01-01", self.test_dir)

        self.assertEqual(self.read_text("prices_history.csv"), first)

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_derived_files_are_regenerated(self, mock_quotes):
        """Test latest prices, the rolling window and price files follow."""
        mock_quotes.return_value = [
            Quote("2026-09-17", "192.00", "USD"),
            Quote("2026-09-18", "192.43", "USD"),
        ]

        backfill_history([FundSpec("YA", "AAA", ())], "2023-01-01", self.test_dir)

        self.assertEqual(
            self.read_rows("latest_prices.csv"),
            [["AAA", "2026-09-18", "192.43", "USD"]],
        )
        self.assertEqual(self.read_text("latest_AAA.price").strip(), "192.43")

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_legacy_three_column_history_is_rebuilt(self, mock_quotes):
        """Test a pre-SPEC-003 file is readable and comes out with currencies."""
        self.write_csv(
            "prices_history.csv",
            ["Fund", "Date", "Price"],
            [["QQQ", "2026-09-19", "700.00"]],
        )
        mock_quotes.return_value = [Quote("2026-09-18", "721.45", "USD")]

        backfill_history([FundSpec("YA", "QQQ", ())], "2023-01-01", self.test_dir)

        self.assertEqual(
            self.read_rows("prices_history.csv"),
            [["QQQ", "2026-09-18", "721.45", "USD"]],
        )

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_unusable_prices_are_dropped_everywhere(self, mock_quotes):
        """Test stored error strings do not survive a rebuild."""
        self.write_csv(
            "prices_history.csv",
            self.HEADER,
            [
                ["RETIRED", "2026-09-18", "Error: Timeout", ""],
                ["QQQ", "2026-09-19", "N/A", ""],
            ],
        )
        mock_quotes.return_value = [Quote("2026-09-18", "721.45", "USD")]

        backfill_history([FundSpec("YA", "QQQ", ())], "2023-01-01", self.test_dir)

        self.assertEqual(
            self.read_rows("prices_history.csv"),
            [["QQQ", "2026-09-18", "721.45", "USD"]],
        )

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_an_unusable_price_from_the_source_is_not_stored(self, mock_quotes):
        """Test a source row with no price is skipped, never written as text."""
        mock_quotes.return_value = [
            Quote("2026-09-18", "N/A", "USD"),
            Quote("2026-09-19", "721.45", "USD"),
        ]
        backfill_history([FundSpec("YA", "QQQ", ())], "2026-09-01", self.test_dir)
        self.assertEqual(
            self.read_rows("prices_history.csv"),
            [["QQQ", "2026-09-19", "721.45", "USD"]],
        )

    @patch("scrape_fund_price.backfill_fx")
    @patch("scrape_fund_price.scrape_fund_quotes", return_value=[])
    def test_the_fx_rebuild_follows_for_the_configured_pairs(self, _, mock_fx):
        """Test backfill_history ends with backfill_fx for fx_pairs.txt's pairs."""
        with patch("scrape_fund_price.read_fx_pairs", return_value=["USDGBP"]):
            report = backfill_history([], "2026-09-01", self.test_dir)
        mock_fx.assert_called_once_with(
            ["USDGBP"], "2026-09-01", self.test_dir, report=report
        )


class TestBackfillReporting(BackfillCase):
    """Test the reconciliation report and sanity warnings."""

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_report_counts_rows_changed(self, mock_quotes):
        """Test the report says what it replaced, for review before committing."""
        self.write_csv(
            "prices_history.csv",
            ["Fund", "Date", "Price", "Currency"],
            [
                ["QQQ", "2026-09-19", "700.00", ""],
                ["QQQ", "2026-09-20", "700.00", ""],
            ],
        )
        mock_quotes.return_value = [Quote("2026-09-18", "721.45", "USD")]

        report = backfill_history(
            [FundSpec("YA", "QQQ", ())], "2023-01-01", self.test_dir
        )

        entry = next(e for e in report.entries if e["identifier"] == "QQQ")
        self.assertEqual(entry["before"], 2)
        self.assertEqual(entry["deleted"], 2)
        self.assertEqual(entry["inserted"], 1)
        self.assertEqual(entry["first"], "2026-09-18")
        self.assertEqual(entry["currency"], "USD")
        self.assertEqual(entry["status"], "rebuilt")

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_report_renders_a_markdown_table(self, mock_quotes):
        """Test the report can be dropped into the Actions job summary."""
        mock_quotes.return_value = [Quote("2026-09-18", "721.45", "USD")]
        report = backfill_history(
            [FundSpec("YA", "QQQ", ())], "2023-01-01", self.test_dir
        )
        self.assertEqual(
            report.to_markdown().splitlines(),
            [
                "| Identifier | Before | Deleted | Kept | Inserted | First | Last "
                "| Ccy | Status |",
                "|---|---:|---:|---:|---:|---|---|---|---|",
                "| QQQ | 0 | 0 | 0 | 1 | 2026-09-18 | 2026-09-18 | USD | rebuilt |",
            ],
        )

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_quoting_unit_change_is_flagged(self, mock_quotes):
        """Test a pence/pounds switch is surfaced rather than stored silently."""
        mock_quotes.return_value = [
            Quote("2026-09-17", "5.06", "GBP"),
            Quote("2026-09-18", "506.00", "GBp"),
        ]
        report = backfill_history(
            [FundSpec("YA", "DPYG.L", ())], "2023-01-01", self.test_dir
        )
        self.assertTrue(any("DPYG.L" in w for w in report.warnings))

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_normal_price_moves_are_not_flagged(self, mock_quotes):
        """Test an ordinary daily move does not raise a false alarm."""
        mock_quotes.return_value = [
            Quote("2026-09-17", "100.00", "USD"),
            Quote("2026-09-18", "112.00", "USD"),
        ]
        report = backfill_history(
            [FundSpec("YA", "AAA", ())], "2023-01-01", self.test_dir
        )
        self.assertEqual(report.warnings, [])


class TestBackfillReportRendering(unittest.TestCase):
    """Test report rendering details."""

    def test_warnings_and_failures_are_listed(self):
        """Test problems are visible in the rendered report."""
        report = BackfillReport()
        report.warnings.append("DPYG.L: possible quoting unit change")
        report.failures.append("QQQ: Error: Timeout")
        text = report.to_markdown()
        self.assertIn("**Warnings**", text)
        self.assertIn("DPYG.L", text)
        self.assertIn("**Failures**", text)
        self.assertIn("QQQ", text)

    def test_clean_report_has_no_problem_sections(self):
        """Test a clean rebuild does not print empty sections."""
        text = BackfillReport().to_markdown()
        self.assertNotIn("**Warnings**", text)
        self.assertNotIn("**Failures**", text)

    def test_validate_ignores_non_backfill_runs(self):
        """Test the daily run is not subject to backfill validation."""
        args = parse_arguments([])
        self.assertIsNone(validate_backfill_args(args))

    def test_quoting_unit_check_skips_non_numeric_prices(self):
        """Test a stray non-numeric value does not crash the check."""
        quotes = [
            Quote("2026-09-17", "not-a-number", "GBP"),
            Quote("2026-09-18", "5.06", "GBP"),
        ]
        self.assertIsNone(check_quoting_unit("AAA", quotes))


class TestBackfillPacing(BackfillCase):
    """Test the rebuild is polite to the unofficial FT endpoint."""

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_pauses_between_ft_funds(self, mock_quotes):
        """Test consecutive FT fetches are spaced out: one pause after each FT
        fund but the last, of the configured length."""
        mock_quotes.return_value = [Quote("2026-09-18", "7.15", "GBP")]
        backfill_history(
            [
                FundSpec("FT", "ISIN1", ()),
                FundSpec("FT", "ISIN2", ()),
                FundSpec("FT", "ISIN3", ()),
            ],
            "2023-01-01",
            self.test_dir,
        )
        pause = scrape_fund_price.FT_BACKFILL_PAUSE_SECONDS
        self.assertGreaterEqual(pause, 1)
        self.assertEqual(self.sleeps, [pause, pause])

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_does_not_pause_for_api_funds(self, mock_quotes):
        """Test the API route is not slowed down unnecessarily."""
        mock_quotes.return_value = [Quote("2026-09-18", "721.45", "USD")]
        backfill_history(
            [FundSpec("YA", "QQQ", ()), FundSpec("YA", "GRAB", ())],
            "2023-01-01",
            self.test_dir,
        )
        self.assertEqual(self.sleeps, [])


class TestBackfillProtectsSourceDerivedRows(BackfillCase):
    """Test a flaky source cannot silently delete real trading days.

    FT's historical endpoint intermittently omits a row or two from the same
    request (893 vs 895 rows for identical queries, verified against the live
    endpoint). Delete-then-insert would drop those days on the next rebuild.
    Rows that already carry a currency were themselves source-derived, so they
    are kept when the source omits them; legacy rows, which predate the
    currency column, are still removed.
    """

    HEADER = ["Fund", "Date", "Price", "Currency"]

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_previously_sourced_row_survives_an_omission(self, mock_quotes):
        """Test a day the source skipped this run is not lost."""
        self.write_csv(
            "prices_history.csv",
            self.HEADER,
            [
                ["ISIN1", "2025-08-14", "8.29", "GBP"],
                ["ISIN1", "2025-08-18", "8.48", "GBP"],
            ],
        )
        mock_quotes.return_value = [Quote("2025-08-18", "8.48", "GBP")]

        report = backfill_history(
            [FundSpec("FT", "ISIN1", ())], "2023-01-01", self.test_dir
        )

        self.assertEqual(
            self.read_rows("prices_history.csv"),
            [
                ["ISIN1", "2025-08-14", "8.29", "GBP"],
                ["ISIN1", "2025-08-18", "8.48", "GBP"],
            ],
        )
        entry = next(e for e in report.entries if e["identifier"] == "ISIN1")
        self.assertEqual(entry["retained"], 1)

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_legacy_rows_without_currency_are_still_removed(self, mock_quotes):
        """Test pre-SPEC-003 rows are not protected by the retention rule."""
        self.write_csv(
            "prices_history.csv", self.HEADER, [["ISIN1", "2025-08-14", "8.29", ""]]
        )
        mock_quotes.return_value = [Quote("2025-08-18", "8.48", "GBP")]

        backfill_history([FundSpec("FT", "ISIN1", ())], "2023-01-01", self.test_dir)

        self.assertEqual(
            self.read_rows("prices_history.csv"),
            [["ISIN1", "2025-08-18", "8.48", "GBP"]],
        )

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_weekend_rows_are_never_retained(self, mock_quotes):
        """Test a carry-forward is removed even if it carries a currency."""
        self.write_csv(
            "prices_history.csv",
            self.HEADER,
            [
                ["QQQ", "2026-09-18", "721.45", "USD"],
                ["QQQ", "2026-09-19", "721.45", "USD"],  # Saturday
                ["QQQ", "2026-09-20", "721.45", "USD"],  # Sunday
            ],
        )
        mock_quotes.return_value = [Quote("2026-09-18", "721.45", "USD")]

        backfill_history([FundSpec("YA", "QQQ", ())], "2023-01-01", self.test_dir)

        self.assertEqual(
            self.read_rows("prices_history.csv"),
            [["QQQ", "2026-09-18", "721.45", "USD"]],
        )


class TestRebuildLeavesClosedHoldingsAlone(DataDirCase):
    """Test a rebuild preserves imported history without promoting it."""

    def _rows(self, name):
        return self.read_rows(name)

    @patch("scrape_fund_price.read_fx_pairs", return_value=[])
    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_imported_rows_survive_a_rebuild(self, mock_quotes, _pairs):
        """Test rows for an unconfigured identifier are never deleted."""
        write_history_files([["BN4MYX3", "2024-01-04", "218.95", "GBX"]], self.test_dir)
        mock_quotes.return_value = [Quote("2024-01-04", "266.28", "USD")]
        backfill_history([FundSpec("YA", "QQQ")], "2023-01-01", self.test_dir)
        self.assertIn(
            ["BN4MYX3", "2024-01-04", "218.95", "GBX"], self._rows("prices_history.csv")
        )

    @patch("scrape_fund_price.read_fx_pairs", return_value=[])
    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_rebuild_does_not_promote_them_to_latest(self, mock_quotes, _pairs):
        """Test latest_prices.csv covers configured funds only.

        The daily run builds latest from what it just fetched, so a rebuild
        that added closed holdings would have them appear and then vanish on
        the next run: churn in the committed data for no information.
        """
        write_history_files([["BN4MYX3", "2024-01-04", "218.95", "GBX"]], self.test_dir)
        mock_quotes.return_value = [Quote("2024-01-04", "266.28", "USD")]
        backfill_history([FundSpec("YA", "QQQ")], "2023-01-01", self.test_dir)
        self.assertEqual([row[0] for row in self._rows("latest_prices.csv")], ["QQQ"])
        self.assertFalse(os.path.exists(self.path("latest_BN4MYX3.price")))


class TestBackfillMainMode(DataDirCase):
    """Test the --backfill entry point."""

    QQQ_ROW = "| QQQ | 1 | 1 | 0 | 2 | 2023-01-03 | 2026-09-18 | USD | rebuilt |"

    @staticmethod
    def report_with_qqq():
        report = BackfillReport()
        report.entries.append(
            {
                "identifier": "QQQ",
                "before": 1,
                "deleted": 1,
                "retained": 0,
                "inserted": 2,
                "first": "2023-01-03",
                "last": "2026-09-18",
                "currency": "USD",
                "status": "rebuilt",
            }
        )
        return report

    @patch("builtins.print")
    def test_invalid_invocation_exits_two_without_fetching(self, mock_print):
        """Test a bad invocation is rejected before any network call."""
        with self.assertRaises(SystemExit) as error:
            main(["--backfill"])

        self.assertEqual(error.exception.code, 2)
        self.assertEqual(mock_print.call_args.args[0][:7], "Error: ")

    @patch("builtins.print")
    @patch("scrape_fund_price.backfill_history")
    @patch("scrape_fund_price.read_fund_specs")
    def test_successful_backfill_prints_the_report(
        self, mock_specs, mock_backfill, mock_print
    ):
        """Test the reconciliation report reaches stdout."""
        mock_specs.return_value = [FundSpec("YA", "QQQ", ())]
        mock_backfill.return_value = self.report_with_qqq()

        main(["--backfill", "--from", "2023-01-01"])

        mock_backfill.assert_called_once_with(mock_specs.return_value, "2023-01-01")
        printed = mock_print.call_args.args[0]
        self.assertIn(self.QQQ_ROW, printed.splitlines())

    @patch("builtins.print")
    @patch("scrape_fund_price.backfill_history")
    @patch("scrape_fund_price.read_fund_specs")
    def test_failures_exit_non_zero_after_writing(
        self, mock_specs, mock_backfill, mock_print
    ):
        """Test the job fails loudly, but only after the report is produced."""
        mock_specs.return_value = [FundSpec("YA", "QQQ", ())]
        report = BackfillReport()
        report.failures.append("QQQ: Error: Timeout")
        mock_backfill.return_value = report

        with self.assertRaises(SystemExit) as error:
            main(["--backfill", "--from", "2023-01-01"])

        self.assertEqual(error.exception.code, 1)
        printed = mock_print.call_args.args[0].splitlines()
        self.assertIn("**Failures**", printed)
        self.assertIn("- QQQ: Error: Timeout", printed)

    @patch("builtins.print")
    @patch("scrape_fund_price.backfill_history")
    @patch("scrape_fund_price.read_fund_specs")
    def test_report_is_added_to_the_actions_job_summary(
        self, mock_specs, mock_backfill, mock_print
    ):
        """Test the report appears on the workflow run page when in Actions."""
        mock_specs.return_value = [FundSpec("YA", "QQQ", ())]
        mock_backfill.return_value = self.report_with_qqq()

        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": self.path("summary.md")}):
            main(["--backfill", "--from", "2023-01-01"])

        written = self.read_text("summary.md").splitlines()
        self.assertEqual(written[0], "## Backfill from 2023-01-01")
        self.assertIn(self.QQQ_ROW, written)

    @patch("builtins.print")
    @patch("scrape_fund_price.backfill_history")
    @patch("scrape_fund_price.read_fund_specs")
    def test_no_summary_written_outside_actions(
        self, mock_specs, mock_backfill, mock_print
    ):
        """Test a local run prints the report and needs no Actions environment."""
        mock_specs.return_value = [FundSpec("YA", "QQQ", ())]
        mock_backfill.return_value = BackfillReport()

        env = {k: v for k, v in os.environ.items() if k != "GITHUB_STEP_SUMMARY"}
        with patch.dict(os.environ, env, clear=True):
            main(["--backfill", "--from", "2023-01-01"])

        mock_print.assert_called_once_with(BackfillReport().to_markdown())


# ===========================================================================
# Closed-holdings import
# ===========================================================================


class TestClosedHoldingImport(DataDirCase):
    """Test the one-off import writes history and nothing else."""

    def setUp(self):
        super().setUp()
        self.holding = ClosedHolding(
            "BKCH", "YA", "BKCH.L", "USD", "2023-01-03", "2023-01-05"
        )

    def _history(self):
        return self.read_rows("prices_history.csv")

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_rows_are_stored_under_the_identifier(self, mock_quotes):
        """Test the published identifier is the SEDOL, not the lookup symbol."""
        mock_quotes.return_value = [Quote("2023-01-03", "2.4705", "USD")]
        holding = self.holding._replace(identifier="BMV7ZZ3")
        import_closed_holdings([holding], self.test_dir)
        self.assertEqual(self._history(), [["BMV7ZZ3", "2023-01-03", "2.4705", "USD"]])

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_quotes_outside_the_window_are_dropped(self, mock_quotes):
        """Test a source that over-returns cannot extend a closed holding.

        The window is the period actually held; a source returning the fund's
        whole life would otherwise import years of irrelevant prices. Both
        ends are inclusive: a quote on the window's last day is stored.
        """
        mock_quotes.return_value = [
            Quote("2022-12-30", "2.40", "USD"),
            Quote("2023-01-03", "2.4705", "USD"),
            Quote("2023-01-05", "2.50", "USD"),
            Quote("2023-01-06", "2.60", "USD"),
        ]
        import_closed_holdings([self.holding], self.test_dir)
        self.assertEqual(
            [row[1] for row in self._history()], ["2023-01-03", "2023-01-05"]
        )

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_configured_currency_is_stored(self, mock_quotes):
        """Test rows carry a currency, so a rebuild treats them as real."""
        mock_quotes.return_value = [Quote("2023-01-03", "849.00", "GBX")]
        holding = self.holding._replace(currency="GBX")
        import_closed_holdings([holding], self.test_dir)
        self.assertEqual(self._history()[0][3], "GBX")

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_currency_mismatch_skips_the_holding(self, mock_quotes):
        """Test a source that resolves to the wrong listing imports nothing.

        FT's ISIN lookup silently redirected BKCH's ISIN to the German EUR
        line and returned 288 plausible EUR quotes for an LSE USD holding.
        Asserting the currency is what turns that into a visible failure.
        """
        mock_quotes.return_value = [Quote("2023-01-03", "2.34", "EUR")]
        report = import_closed_holdings([self.holding], self.test_dir)
        self.assertEqual(self._history(), [])
        self.assertTrue(any("EUR" in failure for failure in report.failures))

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_a_source_reporting_no_currency_is_accepted(self, mock_quotes):
        """Test IV, which reports no currency, is stamped from config."""
        mock_quotes.return_value = [Quote("2023-01-03", "218.95", "")]
        holding = self.holding._replace(source="IV", currency="GBX")
        import_closed_holdings([holding], self.test_dir)
        self.assertEqual(self._history()[0][3], "GBX")

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_existing_rows_for_other_funds_are_untouched(self, mock_quotes):
        """Test the import adds to history and never rewrites it."""
        write_history_files([["QQQ", "2023-01-03", "266.28", "USD"]], self.test_dir)
        mock_quotes.return_value = [Quote("2023-01-03", "2.4705", "USD")]
        import_closed_holdings([self.holding], self.test_dir)
        self.assertIn(["QQQ", "2023-01-03", "266.28", "USD"], self._history())
        self.assertIn(["BKCH", "2023-01-03", "2.4705", "USD"], self._history())

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_import_is_idempotent(self, mock_quotes):
        """Test re-running corrects rather than duplicating."""
        mock_quotes.return_value = [Quote("2023-01-03", "2.4705", "USD")]
        import_closed_holdings([self.holding], self.test_dir)
        import_closed_holdings([self.holding], self.test_dir)
        self.assertEqual(len(self._history()), 1)

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_latest_and_rolling_files_are_not_written(self, mock_quotes):
        """Test a closed holding never reaches the files that describe today.

        latest_prices.csv, the 90-day window and the .price files all answer
        "what is this worth now". A fund that stopped trading in 2024 has no
        answer, and writing one would churn against the next daily run.
        """
        mock_quotes.return_value = [Quote("2023-01-03", "2.4705", "USD")]
        import_closed_holdings([self.holding], self.test_dir)
        for name in (
            "latest_prices.csv",
            "prices_history_90_days.csv",
            "latest_BKCH.price",
        ):
            self.assertFalse(
                os.path.exists(self.path(name)),
                f"{name} should not be written by a closed-holding import",
            )

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_a_failed_fetch_is_reported_and_isolated(self, mock_quotes):
        """Test one dead source does not cost the other holdings their import."""
        mock_quotes.side_effect = [
            ValueError("no rows"),
            [Quote("2023-01-03", "849.00", "GBX")],
        ]
        other = ClosedHolding(
            "BMV7ZZ3", "FT", "SEAL:LSE:GBX", "GBX", "2023-01-03", "2023-01-05"
        )
        report = import_closed_holdings([self.holding, other], self.test_dir)
        self.assertEqual([row[0] for row in self._history()], ["BMV7ZZ3"])
        self.assertTrue(report.failures)

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_report_counts_what_was_imported(self, mock_quotes):
        """Test the report reconciles the import for review."""
        mock_quotes.return_value = [
            Quote("2023-01-03", "2.4705", "USD"),
            Quote("2023-01-04", "2.69325", "USD"),
        ]
        report = import_closed_holdings([self.holding], self.test_dir)
        entry = report.entries[0]
        self.assertEqual(entry["identifier"], "BKCH")
        self.assertEqual(entry["inserted"], 2)
        self.assertEqual(entry["deleted"], 0)
        self.assertIn("BKCH", report.to_markdown())

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_a_quoting_unit_jump_is_reported(self, mock_quotes):
        """Test a pence/pounds switch inside a window is flagged for review.

        An import runs once and is then trusted, so a source that changes
        quoting unit mid-window has to be visible in the report.
        """
        mock_quotes.return_value = [
            Quote("2023-01-03", "8.49", "GBX"),
            Quote("2023-01-04", "849.00", "GBX"),
        ]
        holding = ClosedHolding(
            "BMV7ZZ3", "FT", "SEAL:LSE:GBX", "GBX", "2023-01-03", "2023-01-05"
        )
        report = import_closed_holdings([holding], self.test_dir)
        self.assertTrue(any("quoting unit" in w for w in report.warnings))


class TestClosedHoldingWindowEnds(DataDirCase):
    """Test the last day of a window survives, whatever the source's convention.

    Yahoo's daily bars treat the end date as exclusive while FT and investing
    .com treat it as inclusive, so passing the configured end straight through
    silently dropped the final day from Yahoo holdings only: BKCH imported 284
    rows ending 2024-02-15 for a window ending 2024-02-16. That the stored
    rows are then clipped to the inclusive window is
    TestClosedHoldingImport.test_quotes_outside_the_window_are_dropped.
    """

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_sources_are_asked_past_the_window_end(self, mock_quotes):
        """Test the fetch reaches beyond the end so nothing depends on it."""
        mock_quotes.return_value = [Quote("2024-02-16", "10.115", "USD")]
        holding = ClosedHolding(
            "BKCH", "YA", "BKCH.L", "USD", "2024-02-14", "2024-02-16"
        )
        import_closed_holdings([holding], self.test_dir)
        self.assertEqual(mock_quotes.call_args[0][3], "2024-02-17")


class TestClosedImportMainMode(DataDirCase):
    """Test the CLI entry point for the one-off import."""

    def test_flag_is_parsed(self):
        """Test --import-closed is available."""
        args = parse_arguments(["--import-closed"])
        self.assertTrue(args.import_closed)

    def test_flag_defaults_off(self):
        """Test a normal run is unaffected."""
        self.assertFalse(parse_arguments([]).import_closed)

    @patch("scrape_fund_price.import_closed_holdings")
    @patch("scrape_fund_price.read_closed_holdings")
    @patch("scrape_fund_price.scrape_funds")
    def test_import_mode_skips_the_daily_run(self, mock_scrape, mock_read, mock_import):
        """Test importing never triggers a scrape or an FX snap."""
        mock_read.return_value = [
            ClosedHolding("BKCH", "YA", "BKCH.L", "USD", "2023-01-03", "2024-02-16")
        ]
        mock_import.return_value = BackfillReport()
        main(["--import-closed"])
        mock_import.assert_called_once()
        mock_scrape.assert_not_called()

    @patch("scrape_fund_price.import_closed_holdings")
    @patch("scrape_fund_price.read_closed_holdings")
    def test_failures_exit_non_zero(self, mock_read, mock_import):
        """Test a partial import is visible to CI."""
        mock_read.return_value = []
        report = BackfillReport()
        report.failures.append("BN4MYX3: no rows")
        mock_import.return_value = report
        with self.assertRaises(SystemExit):
            main(["--import-closed"])

    @patch("scrape_fund_price.import_closed_holdings")
    @patch("scrape_fund_price.read_closed_holdings", return_value=[])
    def test_import_mode_writes_the_actions_job_summary(self, _read, mock_import):
        """Test the reconciliation table reaches the Actions run page."""
        report = BackfillReport()
        report.entries.append(
            {
                "identifier": "BKCH",
                "before": 0,
                "deleted": 0,
                "retained": 0,
                "inserted": 285,
                "first": "2023-01-03",
                "last": "2024-02-16",
                "currency": "USD",
                "status": "imported",
            }
        )
        mock_import.return_value = report
        summary_path = self.path("step_summary.md")
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": summary_path}):
            main(["--import-closed"])
        written = self.read_text("step_summary.md")
        self.assertIn("Closed-holding import", written)
        self.assertIn("BKCH", written)


# ===========================================================================
# FX rates
# ===========================================================================


class TestNewYorkFxCloses(unittest.TestCase):
    """Test a day's FX rate is the 17:00 New York close (#80)."""

    AFTER = utc(2026, 10, 19, 12)  # Monday: every day below has closed

    def test_takes_the_bar_that_ends_at_five_pm_new_york(self):
        """Test the close of the 16:00 New York bar is the day's rate (EDT)."""
        bars = [
            (utc(2026, 10, 16, 19), 0.75026),  # 15:00 New York
            (utc(2026, 10, 16, 20), 0.75023),  # 16:00, ends 17:00
            (utc(2026, 10, 16, 21), 0.75022),  # 17:00, after the cut
        ]
        self.assertEqual(
            new_york_fx_closes(bars, now=self.AFTER), [("2026-10-16", 0.75023)]
        )

    def test_follows_the_us_clock_change(self):
        """Test the cut is 22:00 UTC in winter, when New York is on EST."""
        bars = [
            (utc(2026, 1, 16, 20), 0.80100),  # 15:00 New York
            (utc(2026, 1, 16, 21), 0.80200),  # 16:00, ends 17:00
            (utc(2026, 1, 16, 22), 0.80300),  # 17:00, after the cut
        ]
        self.assertEqual(
            new_york_fx_closes(bars, now=utc(2026, 1, 19, 12)),
            [("2026-01-16", 0.80200)],
        )

    def test_a_day_whose_cut_has_not_passed_is_not_stored(self):
        """Test there is no provisional rate for a day still trading."""
        bars = [(utc(2026, 10, 16, 14), 0.75100), (utc(2026, 10, 16, 15), 0.75105)]
        self.assertEqual(new_york_fx_closes(bars, now=utc(2026, 10, 16, 16)), [])

    def test_the_rate_does_not_depend_on_when_the_job_runs(self):
        """Test a run hours or days after the cut gives the same rate."""
        bars = [(utc(2026, 10, 16, 20), 0.75023), (utc(2026, 10, 16, 23), 0.75019)]
        early = new_york_fx_closes(bars, now=utc(2026, 10, 16, 21))
        late = new_york_fx_closes(bars, now=utc(2026, 10, 20, 9))
        self.assertEqual(early, [("2026-10-16", 0.75023)])
        self.assertEqual(late, early)

    def test_weekend_bars_make_no_rate(self):
        """Test Friday-evening and weekend bars are not a weekend day's rate."""
        bars = [
            (utc(2026, 10, 16, 20), 0.75023),  # Friday close
            (utc(2026, 10, 17, 10), 0.75019),  # Saturday
            (utc(2026, 10, 18, 22), 0.75100),  # Sunday reopening, 18:00 New York
        ]
        self.assertEqual(
            new_york_fx_closes(bars, now=utc(2026, 10, 19, 12)),
            [("2026-10-16", 0.75023)],
        )

    def test_monday_is_the_monday_close_not_the_reopening(self):
        """Test Monday's rate is Monday's 17:00 close, not Sunday evening's."""
        bars = [
            (utc(2026, 10, 18, 22), 0.75100),  # Sunday 18:00 New York
            (utc(2026, 10, 19, 20), 0.75400),  # Monday 16:00, ends 17:00
        ]
        self.assertEqual(
            new_york_fx_closes(bars, now=utc(2026, 10, 20, 12)),
            [("2026-10-19", 0.75400)],
        )

    def test_a_missing_last_bar_falls_back_to_the_latest_before_the_cut(self):
        """Test a gap in the hourly data uses the newest earlier bar."""
        bars = [(utc(2026, 10, 15, 18), 0.75332), (utc(2026, 10, 15, 19), 0.75344)]
        self.assertEqual(
            new_york_fx_closes(bars, now=self.AFTER), [("2026-10-15", 0.75344)]
        )

    def test_days_come_out_oldest_first(self):
        """Test several days are returned in date order."""
        bars = [(utc(2026, 10, 16, 20), 0.75023), (utc(2026, 10, 15, 20), 0.75315)]
        self.assertEqual(
            [day for day, _ in new_york_fx_closes(bars, now=self.AFTER)],
            ["2026-10-15", "2026-10-16"],
        )


class TestFxQuoteFetching(unittest.TestCase):
    """Test FX rate retrieval."""

    TODAY = date(2026, 10, 19)
    NOW = utc(2026, 10, 19, 12)

    def fetch(self, pair, start):
        return fetch_fx_quotes(pair, start, today=self.TODAY, now=self.NOW)

    @patch("scrape_fund_price.fetch_yahoo_hourly")
    def test_requests_the_yahoo_fx_ticker_hourly(self, mock_hourly):
        """Test the pair is turned into Yahoo's FX ticker for the hourly bars."""
        mock_hourly.return_value = []
        self.fetch("USDGBP", "2026-10-09")
        self.assertEqual(mock_hourly.call_args.args[:2], ("USDGBP=X", "2026-10-09"))

    @patch("scrape_fund_price.fetch_yahoo_hourly")
    def test_rate_is_the_new_york_close(self, mock_hourly):
        """Test a recent day's rate comes from the 17:00 New York bar."""
        mock_hourly.return_value = [
            (utc(2026, 10, 16, 20), 0.75023),
            (utc(2026, 10, 16, 21), 0.75022),
        ]
        self.assertEqual(
            self.fetch("USDGBP", "2026-10-09"),
            [Quote("2026-10-16", "0.750230", "USDGBP")],
        )

    @patch("scrape_fund_price.fetch_yahoo_hourly")
    def test_days_before_the_start_are_not_returned(self, mock_hourly):
        """Test a bar from before the start date does not leak an earlier day."""
        mock_hourly.return_value = [
            (utc(2026, 10, 8, 20), 0.75600),
            (utc(2026, 10, 9, 20), 0.75568),
        ]
        quotes = self.fetch("USDGBP", "2026-10-09")
        self.assertEqual([q.date for q in quotes], ["2026-10-09"])

    @patch("scrape_fund_price.fetch_yahoo_hourly")
    def test_rates_are_stored_at_six_decimal_places(self, mock_hourly):
        """Test precision is enough for small rates such as HKDGBP."""
        mock_hourly.return_value = [(utc(2026, 10, 16, 20), 0.0951234567)]
        quote = self.fetch("HKDGBP", "2026-10-09")[0]
        self.assertEqual((quote.price, quote.currency), ("0.095123", "HKDGBP"))

    @patch("scrape_fund_price.fetch_yahoo_hourly")
    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_days_older_than_the_hourly_history_keep_the_daily_bars(
        self, mock_daily, mock_hourly
    ):
        """Test a rebuild from 2021 uses daily bars where hourly ones are gone."""
        mock_daily.return_value = [
            Quote("2021-12-03", "0.7531", "GBP"),  # Friday
            Quote("2021-12-04", "0.7531", "GBP"),  # Saturday, dropped
        ]
        mock_hourly.return_value = [(utc(2026, 10, 16, 20), 0.75023)]
        quotes = self.fetch("USDGBP", "2021-12-01")
        hourly_from = (self.TODAY - timedelta(days=729)).isoformat()
        self.assertEqual(
            mock_daily.call_args.args, ("USDGBP=X", "2021-12-01", hourly_from)
        )
        self.assertEqual(mock_hourly.call_args.args[1], hourly_from)
        self.assertEqual(
            quotes,
            [
                Quote("2021-12-03", "0.753100", "USDGBP"),
                Quote("2026-10-16", "0.750230", "USDGBP"),
            ],
        )

    @patch("scrape_fund_price.fetch_yahoo_hourly")
    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_whole_number_rate_keeps_six_places(self, mock_daily, mock_hourly):
        """Test formatting is fixed width, not shortest representation."""
        mock_daily.return_value = [Quote("2021-12-03", "1", "GBP")]
        mock_hourly.return_value = []
        self.assertEqual(self.fetch("GBPGBP", "2021-12-01")[0].price, "1.000000")

    @patch("scrape_fund_price.fetch_yahoo_hourly")
    def test_defaults_to_today_and_now(self, mock_hourly):
        """Test the daily run needs no clock arguments."""
        mock_hourly.return_value = []
        start = (date.today() - timedelta(days=10)).isoformat()
        self.assertEqual(fetch_fx_quotes("USDGBP", start), [])


class TestYahooHourly(unittest.TestCase):
    """Test the hourly bar fetch."""

    @patch("scrape_fund_price.yf.Ticker")
    def test_asks_for_hourly_bars_and_skips_gaps(self, mock_ticker):
        """Test interval=1h is requested, bars are UTC and NaN closes dropped."""
        inst = fake_ticker(
            mock_ticker,
            [("2026-10-16 20:00", 0.75023), ("2026-10-16 21:00", float("nan"))],
            tz="Europe/London",
        )
        bars = fetch_yahoo_hourly("USDGBP=X", "2026-10-16")
        kwargs = inst.history.call_args.kwargs
        self.assertEqual((kwargs["interval"], kwargs["start"]), ("1h", "2026-10-16"))
        self.assertEqual(bars, [(utc(2026, 10, 16, 19), 0.75023)])

    @patch("scrape_fund_price.yf.Ticker")
    def test_no_bars_is_an_empty_list(self, mock_ticker):
        """Test an empty history (e.g. beyond Yahoo's 730 days) is no bars."""
        fake_ticker(mock_ticker, [])
        self.assertEqual(fetch_yahoo_hourly("USDGBP=X", "2024-01-01"), [])


class TestFxStorage(DataDirCase):
    """Test FX output files."""

    def test_history_header_names_the_rate(self):
        """Test the header does not use an ambiguous GBP/xxx label."""
        write_fx_results([["USDGBP", "2026-09-18", "0.746700"]], self.test_dir)
        self.assertEqual(
            self.read_text("fx_history.csv"),
            "Pair,Date,Rate\nUSDGBP,2026-09-18,0.746700\n",
        )

    def test_same_pair_and_date_is_replaced(self):
        """Test a provisional rate is overwritten once the day completes."""
        write_fx_results([["USDGBP", "2026-09-18", "0.746000"]], self.test_dir)
        write_fx_results([["USDGBP", "2026-09-18", "0.746700"]], self.test_dir)
        self.assertEqual(
            self.read_rows("fx_history.csv"), [["USDGBP", "2026-09-18", "0.746700"]]
        )

    def test_rows_are_sorted_by_date_then_pair(self):
        """Test deterministic ordering."""
        write_fx_results(
            [
                ["USDGBP", "2026-09-18", "0.746700"],
                ["HKDGBP", "2026-09-18", "0.095100"],
                ["USDGBP", "2026-09-17", "0.745000"],
            ],
            self.test_dir,
        )
        self.assertEqual(
            [(r[0], r[1]) for r in self.read_rows("fx_history.csv")],
            [
                ("USDGBP", "2026-09-17"),
                ("HKDGBP", "2026-09-18"),
                ("USDGBP", "2026-09-18"),
            ],
        )

    def test_rewriting_identical_data_changes_nothing(self):
        """Test the FX run is idempotent."""
        rows = [["USDGBP", "2026-09-18", "0.746700"]]
        write_fx_results(rows, self.test_dir)
        first = self.read_text("fx_history.csv")
        write_fx_results(rows, self.test_dir)
        self.assertEqual(self.read_text("fx_history.csv"), first)

    def test_latest_fx_takes_the_newest_date_per_pair(self):
        """Test latest_fx.csv reports the most recent rate."""
        write_fx_results(
            [
                ["USDGBP", "2026-09-17", "0.745000"],
                ["USDGBP", "2026-09-18", "0.746700"],
            ],
            self.test_dir,
        )
        self.assertEqual(
            self.read_rows("latest_fx.csv"), [["USDGBP", "2026-09-18", "0.746700"]]
        )

    def test_a_damaged_fx_row_is_skipped_on_read(self):
        """Test a row shorter than Pair,Date,Rate is ignored, not a crash."""
        path = self.write_text(
            "fx_history.csv",
            "Pair,Date,Rate\nUSDGBP,2026-09-18\nUSDGBP,2026-09-19,0.750000\n",
        )
        rows = scrape_fund_price.read_fx_rows(path)
        self.assertEqual(list(rows), [("USDGBP", "2026-09-19")])


class TestFxFailureIsolation(DataDirCase):
    """Test FX and price failures do not block each other."""

    @patch("scrape_fund_price.fetch_fx_quotes")
    def test_one_failing_pair_does_not_block_the_others(self, mock_quotes):
        """Test a dead pair does not cost the rest of the day's rates."""

        def side_effect(pair, start, end=None):
            if pair == "USDGBP":
                raise Exception("Network error")
            return [Quote("2026-09-18", "0.426700", pair)]

        mock_quotes.side_effect = side_effect
        results = snap_fx_rates(["USDGBP", "NZDGBP"], self.test_dir)

        self.assertEqual(list(results), [["NZDGBP", "2026-09-18", "0.426700"]])
        self.assertEqual(len(results.failures), 1)
        self.assertIn("USDGBP", results.failures[0])

    @patch("scrape_fund_price.fetch_fx_quotes")
    def test_retries_before_giving_up_on_a_pair(self, mock_quotes):
        """Test a transient FX error is retried like a price fetch."""
        mock_quotes.side_effect = [
            Exception("timeout"),
            [Quote("2026-09-18", "0.746700", "USDGBP")],
        ]
        results = snap_fx_rates(["USDGBP"], self.test_dir)
        self.assertEqual(list(results), [["USDGBP", "2026-09-18", "0.746700"]])
        self.assertEqual(results.failures, [])


class TestFxBackfill(DataDirCase):
    """Test FX history is rebuilt by the same rule as prices."""

    HEADER = ["Pair", "Date", "Rate"]

    @patch("scrape_fund_price.fetch_fx_quotes")
    def test_rebuilds_rates_from_the_start_date(self, mock_quotes):
        """Test rates are rebuilt from source data."""
        mock_quotes.return_value = [
            Quote("2023-01-03", "0.830000", "USDGBP"),
            Quote("2026-09-18", "0.746700", "USDGBP"),
        ]
        report = backfill_fx(["USDGBP"], "2023-01-01", self.test_dir)
        self.assertEqual(
            self.read_rows("fx_history.csv"),
            [
                ["USDGBP", "2023-01-03", "0.830000"],
                ["USDGBP", "2026-09-18", "0.746700"],
            ],
        )
        entry = next(e for e in report.entries if e["identifier"] == "USDGBP")
        self.assertEqual(entry["inserted"], 2)

    @patch("scrape_fund_price.fetch_fx_quotes")
    def test_stale_rows_in_range_are_removed(self, mock_quotes):
        """Test a rate the source no longer reports does not linger."""
        self.write_csv(
            "fx_history.csv",
            self.HEADER,
            [["USDGBP", "2026-09-19", "0.999999"]],  # Saturday
        )
        mock_quotes.return_value = [Quote("2026-09-18", "0.746700", "USDGBP")]

        backfill_fx(["USDGBP"], "2023-01-01", self.test_dir)

        self.assertEqual(
            self.read_rows("fx_history.csv"), [["USDGBP", "2026-09-18", "0.746700"]]
        )

    @patch("scrape_fund_price.fetch_fx_quotes")
    def test_failed_pair_keeps_its_rows(self, mock_quotes):
        """Test a failed fetch never destroys stored rates."""
        self.write_csv(
            "fx_history.csv", self.HEADER, [["USDGBP", "2026-09-18", "0.746700"]]
        )
        mock_quotes.side_effect = Exception("Network error")

        report = backfill_fx(["USDGBP"], "2023-01-01", self.test_dir)

        self.assertEqual(
            self.read_rows("fx_history.csv"), [["USDGBP", "2026-09-18", "0.746700"]]
        )
        self.assertEqual(len(report.failures), 1)
        self.assertIn("USDGBP", report.failures[0])


class TestFxInTheDailyRun(DataDirCase):
    """Test main() snaps and writes the configured pairs beside the prices.

    Every other main() test stubs the pairs to [], so the FX branch of the
    daily run was never exercised.
    """

    PAIRS = ["USDGBP", "HKDGBP"]

    def setUp(self):
        super().setUp()
        # A stored rate for one pair only, so the FX summary can tell a pair
        # that failed from one that simply has no history.
        self.write_csv(
            "fx_history.csv",
            ["Pair", "Date", "Rate"],
            [["USDGBP", "2026-10-29", "0.750000"]],
        )

    def _run(self, fx_results):
        """Run the daily mode with `fx_results` snapped.

        Returns the stubs by name together with the exit code (None for a
        clean run) and what was printed.
        """
        with daily_run_stubs(
            self.test_dir,
            specs=[FundSpec("YA", "QQQ")],
            pairs=self.PAIRS,
            snap_fx_rates=fx_results,
        ) as stubs:
            try:
                main([])
            except SystemExit as error:
                stubs["exit_code"] = error.code
            else:
                stubs["exit_code"] = None
        stubs["printed"] = [str(c.args[0]) for c in stubs["print"].call_args_list]
        return stubs

    def test_the_configured_pairs_are_snapped_and_written(self):
        """Test the snap gets the pairs and the write gets its rows."""
        rates = ScrapeResults([["USDGBP", "2026-10-30", "0.751234"]])
        ran = self._run(rates)
        ran["snap_fx_rates"].assert_called_once_with(self.PAIRS)
        ran["write_fx_results"].assert_called_once_with(rates)
        ran["write_summary"].assert_called_once()
        self.assertIsNone(ran["exit_code"])

    def test_a_pairs_failure_reaches_the_exit_code_after_the_summary(self):
        """Test a dead pair fails the run, marked in the FX summary."""
        rates = ScrapeResults(failures=["HKDGBP: Error: Timeout"])
        ran = self._run(rates)
        self.assertEqual(ran["exit_code"], 1)
        ran["write_fx_results"].assert_called_once_with(rates)
        fx_rows = ran["write_summary"].call_args.args[1]
        self.assertEqual(
            [(row.name, row.failed) for row in fx_rows],
            [("USDGBP", False), ("HKDGBP", True)],
        )
        self.assertIn("Error: HKDGBP: Error: Timeout", ran["printed"])


# ===========================================================================
# Daily summary
# ===========================================================================


class TestPriceSummary(unittest.TestCase):
    """Test day-on-day change calculation."""

    def test_compares_against_the_previous_distinct_price_date(self):
        """Test a Friday-to-Monday gap is a real comparison, not 0%."""
        rows = [
            ["QQQ", "2026-09-18", "700.00", "USD"],  # Friday
            ["QQQ", "2026-09-21", "714.00", "USD"],  # Monday
        ]
        summary = build_price_summary(
            rows, [FundSpec("YA", "QQQ", ())], [], "2026-09-21"
        )
        row = summary[0]
        self.assertEqual(row.new_date, "2026-09-21")
        self.assertEqual(row.old_date, "2026-09-18")
        self.assertEqual(row.delta, "14")
        self.assertEqual(row.pct_delta, "+2.00")

    def test_delta_uses_exact_decimal_arithmetic(self):
        """Test 7.15 - 7.09 is 0.06, not a binary-float artefact."""
        rows = [
            ["ISIN1", "2026-09-17", "7.09", "GBP"],
            ["ISIN1", "2026-09-18", "7.15", "GBP"],
        ]
        row = build_price_summary(
            rows, [FundSpec("FT", "ISIN1", ())], [], "2026-09-18"
        )[0]
        self.assertEqual(row.delta, "0.06")

    def test_negative_move_is_signed(self):
        """Test a fall is reported with its sign."""
        rows = [
            ["AAA", "2026-09-17", "100.00", "USD"],
            ["AAA", "2026-09-18", "98.00", "USD"],
        ]
        row = build_price_summary(rows, [FundSpec("YA", "AAA", ())], [], "2026-09-18")[
            0
        ]
        self.assertEqual(row.delta, "-2")
        self.assertEqual(row.pct_delta, "-2.00")

    def test_instruments_with_different_latest_dates(self):
        """Test a fund lagging an exchange instrument is handled per instrument."""
        rows = [
            ["FUND", "2026-09-16", "100.00", "USD"],
            ["FUND", "2026-09-17", "101.00", "USD"],
            ["ETF", "2026-09-17", "50.00", "USD"],
            ["ETF", "2026-09-18", "52.00", "USD"],
        ]
        summary = build_price_summary(
            rows,
            [FundSpec("YA", "FUND", ()), FundSpec("YA", "ETF", ())],
            [],
            "2026-09-18",
        )
        by_name = {r.name: r for r in summary}
        self.assertEqual(by_name["FUND"].new_date, "2026-09-17")
        self.assertEqual(by_name["ETF"].new_date, "2026-09-18")

    def test_single_price_has_no_comparison(self):
        """Test a newly added instrument does not invent a delta."""
        rows = [["NEW", "2026-09-18", "10.00", "GBP"]]
        row = build_price_summary(rows, [FundSpec("YA", "NEW", ())], [], "2026-09-18")[
            0
        ]
        self.assertEqual(row.old, "")
        self.assertEqual(row.delta, "")
        self.assertEqual(row.pct_delta, "")

    def test_zero_previous_price_gives_no_percentage(self):
        """Test a zero prior price does not divide by zero."""
        rows = [
            ["AAA", "2026-09-17", "0", "USD"],
            ["AAA", "2026-09-18", "5.00", "USD"],
        ]
        row = build_price_summary(rows, [FundSpec("YA", "AAA", ())], [], "2026-09-18")[
            0
        ]
        self.assertEqual(row.delta, "5")
        self.assertEqual(row.pct_delta, "")

    def test_instrument_with_no_history_is_reported_as_failed(self):
        """Test a configured instrument with nothing stored is visible."""
        summary = build_price_summary([], [FundSpec("YA", "AAA", ())], [], "2026-09-18")
        self.assertEqual(summary[0].new, "")
        self.assertTrue(summary[0].failed)

    def test_stale_boundary(self):
        """Test the stale threshold covers a long weekend but not longer."""
        rows = [["AAA", "2026-09-14", "10.00", "USD"]]
        spec = [FundSpec("YA", "AAA", ())]
        self.assertFalse(build_price_summary(rows, spec, [], "2026-09-18")[0].stale)
        self.assertTrue(build_price_summary(rows, spec, [], "2026-09-19")[0].stale)

    def test_failed_instrument_is_flagged(self):
        """Test a fund that fell back to its last price is marked."""
        rows = [["AAA", "2026-09-18", "10.00", "USD"]]
        summary = build_price_summary(
            rows, [FundSpec("YA", "AAA", ())], ["AAA: Error: Timeout"], "2026-09-18"
        )
        self.assertTrue(summary[0].failed)

    def test_aliased_instrument_appears_once_with_its_aliases(self):
        """Test an alias is not reported as a second, identical instrument."""
        rows = [
            ["0P00000YAN", "2026-09-16", "192.23", "USD"],
            ["0P00000YAN", "2026-09-17", "192.43", "USD"],
            ["JFM0003373", "2026-09-16", "192.23", "USD"],
            ["JFM0003373", "2026-09-17", "192.43", "USD"],
        ]
        summary = build_price_summary(
            rows, [FundSpec("YA", "0P00000YAN", ("JFM0003373",))], [], "2026-09-17"
        )
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0].name, "0P00000YAN")
        self.assertEqual(summary[0].aliases, ("JFM0003373",))

    def test_pence_instrument_keeps_its_unit(self):
        """Test GBp is shown, and the percentage is unit-independent."""
        rows = [
            ["IGWD.L", "2026-09-17", "13000", "GBp"],
            ["IGWD.L", "2026-09-18", "13339", "GBp"],
        ]
        row = build_price_summary(
            rows, [FundSpec("YA", "IGWD.L", ())], [], "2026-09-18"
        )[0]
        self.assertEqual(row.currency, "GBp")
        self.assertEqual(row.delta, "339")
        self.assertEqual(row.pct_delta, "+2.61")

    def test_rows_follow_funds_file_order(self):
        """Test the summary reads in the order the config lists instruments."""
        rows = [
            ["BBB", "2026-09-18", "2.00", "USD"],
            ["AAA", "2026-09-18", "1.00", "USD"],
        ]
        summary = build_price_summary(
            rows,
            [FundSpec("YA", "BBB", ()), FundSpec("YA", "AAA", ())],
            [],
            "2026-09-18",
        )
        self.assertEqual([r.name for r in summary], ["BBB", "AAA"])

    def test_spot_check_from_the_issue(self):
        """Test the documented ASEAN fund example."""
        rows = [
            ["0P00000YAN", "2026-09-16", "192.23", "USD"],
            ["0P00000YAN", "2026-09-17", "192.43", "USD"],
        ]
        row = build_price_summary(
            rows, [FundSpec("YA", "0P00000YAN", ())], [], "2026-09-17"
        )[0]
        self.assertEqual(
            (row.new, row.old, row.old_date), ("192.43", "192.23", "2026-09-16")
        )
        self.assertEqual(row.delta, "0.2")
        self.assertEqual(row.pct_delta, "+0.10")


class TestFxSummary(unittest.TestCase):
    """Test the FX section of the summary."""

    def test_rates_keep_six_decimal_places(self):
        """Test FX deltas and rates are not truncated."""
        rows = [
            ["USDGBP", "2026-09-17", "0.745000"],
            ["USDGBP", "2026-09-18", "0.748615"],
        ]
        row = build_fx_summary(rows, ["USDGBP"], [], "2026-09-18")[0]
        self.assertEqual(row.new, "0.748615")
        self.assertEqual(row.delta, "0.003615")
        self.assertEqual(row.pct_delta, "+0.49")
        self.assertEqual(row.currency, "")

    def test_failed_pair_is_flagged(self):
        """Test an unavailable pair is visible rather than silently absent."""
        rows = [["USDGBP", "2026-09-18", "0.748615"]]
        summary = build_fx_summary(rows, ["USDGBP"], ["USDGBP: Error"], "2026-09-18")
        self.assertTrue(summary[0].failed)


class TestSummaryRendering(DataDirCase):
    """Test the Markdown and CSV output."""

    def setUp(self):
        super().setUp()
        self.price_rows = build_price_summary(
            [
                ["QQQ", "2026-09-17", "700.00", "USD"],
                ["QQQ", "2026-09-18", "714.00", "USD"],
                ["IGWD.L", "2026-09-17", "13000", "GBp"],
                ["IGWD.L", "2026-09-18", "13339", "GBp"],
            ],
            [FundSpec("YA", "QQQ", ()), FundSpec("YA", "IGWD.L", ())],
            [],
            "2026-09-18",
        )
        self.fx_rows = build_fx_summary(
            [
                ["USDGBP", "2026-09-17", "0.745000"],
                ["USDGBP", "2026-09-18", "0.748615"],
            ],
            ["USDGBP"],
            [],
            "2026-09-18",
        )

    def test_markdown_has_both_sections(self):
        """Test prices and FX are both rendered."""
        text = render_summary_markdown(self.price_rows, self.fx_rows, "2026-09-18")
        self.assertIn("QQQ", text)
        self.assertIn("USDGBP", text)
        self.assertIn("2026-09-18", text)

    def test_fx_heading_states_the_direction(self):
        """Test the heading cannot be read as the market convention.

        'GBP/USD' conventionally means the inverse of what is stored, so the
        direction is spelled out rather than implied by a pair label.
        """
        text = render_summary_markdown(self.price_rows, self.fx_rows, "2026-09-18")
        self.assertIn("GBP per 1 unit of foreign currency", text)

    def test_clean_run_reports_nothing_needing_attention(self):
        """Test a clean day says so explicitly."""
        text = render_summary_markdown(self.price_rows, self.fx_rows, "2026-09-18")
        self.assertIn("None", text)

    def test_stale_and_failed_rows_are_listed(self):
        """Test problems are surfaced in their own section."""
        rows = build_price_summary(
            [["OLD", "2026-09-01", "1.00", "USD"]],
            [FundSpec("YA", "OLD", ())],
            [],
            "2026-09-18",
        )
        text = render_summary_markdown(rows, [], "2026-09-18")
        self.assertIn("OLD", text)
        self.assertIn("stale", text.lower())

    def test_biggest_movers_are_ordered_by_absolute_change(self):
        """Test the movers list ranks by size of move, either direction."""
        text = render_summary_markdown(self.price_rows, self.fx_rows, "2026-09-18")
        movers = text.split("Biggest movers")[1]
        self.assertLess(movers.index("IGWD.L"), movers.index("QQQ"))

    def test_write_summary_produces_both_files(self):
        """Test the CSV and Markdown are written together."""
        write_summary(self.price_rows, self.fx_rows, "2026-09-18", self.test_dir)
        self.assertEqual(
            self.read_text("daily_summary.csv").splitlines()[0],
            ",".join(scrape_fund_price.SUMMARY_HEADER),
        )
        names = [row[0] for row in self.read_rows("daily_summary.csv")]
        self.assertEqual(names, ["QQQ", "IGWD.L", "USDGBP"])
        self.assertEqual(
            self.read_text("daily_summary.md"),
            render_summary_markdown(self.price_rows, self.fx_rows, "2026-09-18"),
        )

    def test_summary_is_added_to_the_actions_job_summary(self):
        """Test the table appears on the workflow run page."""
        path = self.path("step_summary.md")
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": path}):
            write_summary(self.price_rows, self.fx_rows, "2026-09-18", self.test_dir)
        self.assertIn("QQQ", self.read_text("step_summary.md"))

    def test_no_job_summary_outside_actions(self):
        """Test a local run does not need the Actions environment."""
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_STEP_SUMMARY"}
        with patch.dict(os.environ, env, clear=True):
            write_summary(self.price_rows, self.fx_rows, "2026-09-18", self.test_dir)
        self.assertTrue(os.path.exists(self.path("daily_summary.md")))

    def test_the_csv_header_is_summary_row_in_field_order(self):
        """Test SUMMARY_HEADER names SummaryRow's fields, in order (#112).

        write_summary writes each SummaryRow as the tuple it is, so the
        header must follow the NamedTuple's own field order.
        """
        self.assertEqual(
            [
                "".join(part.title() for part in field.split("_"))
                for field in scrape_fund_price.SummaryRow._fields
            ],
            scrape_fund_price.SUMMARY_HEADER,
        )

    def test_the_csv_joins_aliases_with_semicolons(self):
        """Test an instrument's aliases share one cell, not the tuple's repr."""
        row = self.price_rows[0]._replace(aliases=("A1", "A2"))
        write_summary([row], [], "2026-09-18", self.test_dir)
        self.assertEqual(self.read_rows("daily_summary.csv")[0][:2], ["QQQ", "A1;A2"])


class TestSummaryRowMarkers(unittest.TestCase):
    """Test the name column carries aliases and the failure marker.

    The documentation promises that a failed instrument is marked `!` and that
    an aliased fund shows both identifiers; neither was asserted anywhere.
    """

    def _row(self, **overrides):
        values = dict(
            name="0P00000YAN",
            aliases=(),
            currency="USD",
            new_date="2026-09-18",
            new="192.43",
            old_date="2026-09-17",
            old="193.03",
            delta="-0.60",
            pct_delta="-0.31",
            age_days=0,
            stale=False,
            failed=False,
        )
        values.update(overrides)
        return scrape_fund_price.SummaryRow(**values)

    def test_aliases_are_shown_beside_the_lookup_identifier(self):
        """Test a fund published under two identifiers names both."""
        markdown = render_summary_markdown(
            [self._row(aliases=("JFM0003373",))], [], "2026-09-18"
        )
        self.assertIn("0P00000YAN (JFM0003373)", markdown)

    def test_a_failed_fetch_is_marked(self):
        """Test a failure is not mistaken for a flat day."""
        markdown = render_summary_markdown([self._row(failed=True)], [], "2026-09-18")
        self.assertIn("0P00000YAN !", markdown)

    def test_failure_takes_precedence_over_staleness(self):
        """Test a fund that is both failed and stale shows the failure."""
        markdown = render_summary_markdown(
            [self._row(failed=True, stale=True)], [], "2026-09-18"
        )
        self.assertIn("0P00000YAN !", markdown)
        self.assertNotIn("0P00000YAN ~", markdown)


# ===========================================================================
# Dividends
# ===========================================================================


class TestYahooDividendEvents(unittest.TestCase):
    """Test dividend events from the Yahoo daily-bar route (SPEC-010, #85)."""

    def _ticker(self, mock_ticker, rows, currency="GBP", column=True):
        """Bars closing at 1.0, with `rows` as [(date, dividend)]."""
        return fake_ticker(
            mock_ticker,
            bars=[(day, 1.0) for day, _ in rows],
            currency=currency,
            dividends=[amount for _, amount in rows] if column else None,
        )

    @patch("scrape_fund_price.yf.Ticker")
    def test_returns_one_event_per_ex_date_with_the_price_currency(self, mock_ticker):
        """Test only bars carrying a dividend become events."""
        self._ticker(
            mock_ticker,
            [("2026-09-17", 0.0), ("2026-09-18", 0.0821), ("2026-09-21", 0.0)],
        )
        events = scrape_fund_price.fetch_yahoo_dividends("IGLS.L", "2026-09-01")
        self.assertEqual(
            events, [scrape_fund_price.DividendEvent("2026-09-18", "0.0821", "GBP")]
        )

    @patch("scrape_fund_price.yf.Ticker")
    def test_a_pence_line_stays_in_pence(self, mock_ticker):
        """Test GBp is kept, as it is for prices."""
        self._ticker(mock_ticker, [("2026-09-18", 24.5)], currency="GBp")
        [event] = scrape_fund_price.fetch_yahoo_dividends("SWDA.L", "2026-09-01")
        self.assertEqual((event.amount, event.currency), ("24.5", "GBp"))

    @patch("scrape_fund_price.yf.Ticker")
    def test_amounts_are_plain_decimal_text(self, mock_ticker):
        """Test whole numbers, small values and noise-free decimals."""
        self._ticker(
            mock_ticker,
            [("2026-01-02", 3.0), ("2026-02-02", 1e-05), ("2026-03-02", 0.1234567)],
        )
        events = scrape_fund_price.fetch_yahoo_dividends("QQQ", "2026-01-01")
        self.assertEqual([e.amount for e in events], ["3", "0.00001", "0.1234567"])

    @patch("scrape_fund_price.yf.Ticker")
    def test_float32_noise_is_removed_like_it_is_for_prices(self, mock_ticker):
        """Test 12.349999, what Yahoo serves for FLOS.L's 12.35p, is stored as 12.35."""
        self._ticker(
            mock_ticker,
            [("2025-11-13", 12.349999), ("2026-05-21", 9.91), ("2026-06-01", 2.4146)],
            currency="GBp",
        )
        events = scrape_fund_price.fetch_yahoo_dividends("FLOS.L", "2025-01-01")
        self.assertEqual([e.amount for e in events], ["12.35", "9.91", "2.4146"])

    @patch("scrape_fund_price.yf.Ticker")
    def test_requests_actions_unadjusted_for_the_window(self, mock_ticker):
        """Test the same call as the bars, with the corporate actions on."""
        inst = self._ticker(mock_ticker, [("2026-09-18", 0.5)])
        scrape_fund_price.fetch_yahoo_dividends("QQQ", "2026-09-01", "2026-09-19")
        kwargs = inst.history.call_args.kwargs
        self.assertTrue(kwargs["actions"])
        self.assertFalse(kwargs["auto_adjust"])
        self.assertEqual((kwargs["start"], kwargs["end"]), ("2026-09-01", "2026-09-19"))

    @patch("scrape_fund_price.yf.Ticker")
    def test_no_start_asks_for_the_whole_history(self, mock_ticker):
        """Test the first fetch of an instrument reads everything Yahoo has."""
        inst = self._ticker(mock_ticker, [("2026-09-18", 0.5)])
        scrape_fund_price.fetch_yahoo_dividends("QQQ", None)
        kwargs = inst.history.call_args.kwargs
        self.assertEqual(kwargs["period"], "max")
        self.assertNotIn("start", kwargs)

    @patch("scrape_fund_price.yf.Ticker")
    def test_missing_values_and_columns_give_no_events(self, mock_ticker):
        """Test NaN, an absent column and an empty frame are not errors."""
        shapes = {
            "nan": dict(rows=[("2026-09-18", float("nan"))]),
            "no column": dict(rows=[("2026-09-18", 1.0)], column=False),
            "empty frame": dict(rows=[]),
        }
        for shape, frame in shapes.items():
            with self.subTest(frame=shape):
                self._ticker(mock_ticker, **frame)
                events = scrape_fund_price.fetch_yahoo_dividends("A", "2026-09-01")
                self.assertEqual(events, [])

    @patch("scrape_fund_price.yf.Ticker")
    def test_unknown_currency_is_empty_not_an_error(self, mock_ticker):
        """Test a missing currency leaves the field empty, as the prices do."""
        inst = self._ticker(mock_ticker, [("2026-09-18", 0.5)])
        inst.fast_info = {}
        [event] = scrape_fund_price.fetch_yahoo_dividends("QQQ", "2026-09-01")
        self.assertEqual(event.currency, "")

    @patch("scrape_fund_price.yf.Ticker")
    def test_exception_propagates_to_the_retry_wrapper(self, mock_ticker):
        """Test transport errors are raised so fetch_with_retries can retry."""
        mock_ticker.side_effect = Exception("Network error")
        with self.assertRaisesRegex(Exception, "Network error"):
            scrape_fund_price.fetch_yahoo_dividends("QQQ", "2026-09-01")


class TestYahooDeclaredDividends(unittest.TestCase):
    """Test the next declared ex-date and pay date from Yahoo (SPEC-010, #85)."""

    TODAY = date(2026, 10, 26)

    def _declared(self, mock_ticker, **kwargs):
        mock_ticker.return_value = FakeCalendarTicker(**kwargs)
        return scrape_fund_price.fetch_yahoo_declared("QQQ", self.TODAY)

    @patch("scrape_fund_price.yf.Ticker")
    def test_calendar_gives_the_ex_date_and_pay_date(self, mock_ticker):
        """Test the calendar's two dividend dates are taken."""
        declared = self._declared(
            mock_ticker,
            calendar={
                "Dividend Date": date(2026, 11, 28),
                "Ex-Dividend Date": date(2026, 11, 12),
            },
        )
        self.assertEqual(
            declared, scrape_fund_price.DeclaredDividend("2026-11-12", "2026-11-28")
        )

    @patch("scrape_fund_price.yf.Ticker")
    def test_an_ex_date_today_is_still_upcoming(self, mock_ticker):
        """Test the boundary: today's ex-date is declared, yesterday's is not."""
        today = self._declared(mock_ticker, calendar={"Ex-Dividend Date": self.TODAY})
        self.assertEqual(today.ex_date, "2026-10-26")
        yesterday = self._declared(
            mock_ticker, calendar={"Ex-Dividend Date": date(2026, 10, 25)}, info={}
        )
        self.assertIsNone(yesterday)

    @patch("scrape_fund_price.yf.Ticker")
    def test_a_missing_or_earlier_pay_date_is_left_empty(self, mock_ticker):
        """Test the pay date is only kept when it follows the ex-date."""
        no_pay = self._declared(
            mock_ticker, calendar={"Ex-Dividend Date": date(2026, 11, 12)}
        )
        self.assertEqual(no_pay.pay_date, "")
        early = self._declared(
            mock_ticker,
            calendar={
                "Ex-Dividend Date": date(2026, 11, 12),
                "Dividend Date": date(2026, 11, 1),
            },
        )
        self.assertEqual(early.pay_date, "")

    @patch("scrape_fund_price.yf.Ticker")
    def test_info_is_the_fallback_when_the_calendar_has_no_ex_date(self, mock_ticker):
        """Test epoch seconds from info are read as UTC dates."""
        declared = self._declared(
            mock_ticker,
            calendar={},
            info={
                "exDividendDate": epoch("2026-11-12"),
                "dividendDate": epoch("2026-11-28"),
            },
        )
        self.assertEqual(
            declared, scrape_fund_price.DeclaredDividend("2026-11-12", "2026-11-28")
        )

    @patch("scrape_fund_price.yf.Ticker")
    def test_a_failing_calendar_falls_back_to_info(self, mock_ticker):
        """Test Yahoo's calendar error does not hide what info knows."""
        declared = self._declared(
            mock_ticker,
            calendar_error=RuntimeError("404"),
            info={"exDividendDate": epoch("2026-11-12")},
        )
        self.assertEqual(declared.ex_date, "2026-11-12")

    @patch("scrape_fund_price.yf.Ticker")
    def test_info_failure_propagates_to_the_retry_wrapper(self, mock_ticker):
        """Test the last resort failing is an error, not 'nothing declared'."""
        with self.assertRaises(RuntimeError):
            self._declared(
                mock_ticker, calendar={}, info_error=RuntimeError("Network error")
            )

    @patch("scrape_fund_price.yf.Ticker")
    def test_nothing_declared_gives_none(self, mock_ticker):
        """Test neither source naming an ex-date is not an error."""
        self.assertIsNone(self._declared(mock_ticker, calendar={}, info={}))
        self.assertIsNone(self._declared(mock_ticker, calendar=None, info=None))

    @patch("scrape_fund_price.yf.Ticker")
    def test_date_values_come_in_several_shapes(self, mock_ticker):
        """Test datetimes, ISO text and garbage are each handled."""
        readable = {
            "datetime": datetime.datetime(2026, 11, 12, 9, 30),
            "text": "2026-11-12",
        }
        for shape, value in readable.items():
            with self.subTest(shape=shape):
                declared = self._declared(
                    mock_ticker, calendar={"Ex-Dividend Date": value}
                )
                self.assertEqual(declared.ex_date, "2026-11-12")
        for junk in ("soon", "", None, True, 1e30, [date(2026, 11, 12)]):
            with self.subTest(junk=junk):
                declared = self._declared(
                    mock_ticker, calendar={"Ex-Dividend Date": junk}, info={}
                )
                self.assertIsNone(declared)


class TestDividendHistoryStorage(DataDirCase):
    """Test dividends_history.csv reading and writing (SPEC-010, #85)."""

    def test_rows_are_written_sorted_with_a_header_and_lf_endings(self):
        """Test the file is ordered by ex-date then fund, deterministically."""
        scrape_fund_price.write_dividend_history(
            [
                ["QQQ", "2026-06-23", "", "0.9", "USD", "YA"],
                ["IGLS.L", "2026-06-23", "", "0.1", "GBP", "YA"],
                ["QQQ", "2026-03-24", "", "0.8", "USD", "YA"],
            ],
            self.test_dir,
        )
        self.assertEqual(
            self.read_text("dividends_history.csv"),
            "Fund,ExDate,PayDate,Amount,Currency,Source\n"
            "QQQ,2026-03-24,,0.8,USD,YA\n"
            "IGLS.L,2026-06-23,,0.1,GBP,YA\n"
            "QQQ,2026-06-23,,0.9,USD,YA\n",
        )

    def test_rows_round_trip_keyed_on_fund_and_ex_date(self):
        """Test reading gives back what was written, keyed for upserting."""
        rows = [["QQQ", "2026-03-24", "2026-04-01", "0.8", "USD", "YA"]]
        scrape_fund_price.write_dividend_history(rows, self.test_dir)
        stored = scrape_fund_price.read_dividend_history(self.test_dir)
        self.assertEqual(stored, {("QQQ", "2026-03-24"): rows[0]})

    def test_a_missing_file_reads_as_empty(self):
        """Test the first run has no history."""
        self.assertEqual(scrape_fund_price.read_dividend_history(self.test_dir), {})

    def test_rows_without_a_fund_or_ex_date_are_skipped(self):
        """Test a damaged line cannot stop the run."""
        self.write_text(
            "dividends_history.csv",
            "Fund,ExDate,PayDate,Amount,Currency,Source\n"
            ",2026-03-24,,0.8,USD,YA\n"
            "QQQ,,,0.8,USD,YA\n"
            "QQQ,2026-06-23,,0.9,USD,YA\n",
        )
        stored = scrape_fund_price.read_dividend_history(self.test_dir)
        self.assertEqual(list(stored), [("QQQ", "2026-06-23")])

    def test_short_rows_are_padded(self):
        """Test a row missing its trailing columns still reads."""
        self.write_text(
            "dividends_history.csv",
            "Fund,ExDate,PayDate,Amount,Currency,Source\nQQQ,2026-06-23\n",
        )
        stored = scrape_fund_price.read_dividend_history(self.test_dir)
        self.assertEqual(
            stored[("QQQ", "2026-06-23")], ["QQQ", "2026-06-23", "", "", "", ""]
        )


class TestDividendHistoryMerge(unittest.TestCase):
    """Test the upsert rules for dividends_history.csv (SPEC-010, #85)."""

    def _stored(self, *rows):
        return {(row[0], row[1]): list(row) for row in rows}

    def test_new_rows_are_added(self):
        """Test an unseen ex-date is stored."""
        stored = self._stored(["QQQ", "2026-03-24", "", "0.8", "USD", "YA"])
        scrape_fund_price.merge_dividend_rows(
            stored, [["QQQ", "2026-06-23", "", "0.9", "USD", "YA"]]
        )
        self.assertEqual(len(stored), 2)

    def test_a_changed_amount_replaces_the_row(self):
        """Test a correction applies and a rerun cannot duplicate."""
        stored = self._stored(["QQQ", "2026-03-24", "", "0.8", "USD", "YA"])
        scrape_fund_price.merge_dividend_rows(
            stored, [["QQQ", "2026-03-24", "", "0.85", "USD", "YA"]]
        )
        self.assertEqual(stored[("QQQ", "2026-03-24")][3], "0.85")
        self.assertEqual(len(stored), 1)

    def test_a_source_row_replaces_a_config_row(self):
        """Test Yahoo is authoritative once it knows the dividend."""
        stored = self._stored(
            ["QQQ", "2026-03-24", "2026-04-23", "0.8", "USD", "config"]
        )
        scrape_fund_price.merge_dividend_rows(
            stored, [["QQQ", "2026-03-24", "", "0.81", "USD", "YA"]]
        )
        self.assertEqual(stored[("QQQ", "2026-03-24")][3:], ["0.81", "USD", "YA"])

    def test_a_config_row_never_replaces_a_source_row(self):
        """Test the owner's assertion cannot overwrite Yahoo's figure."""
        stored = self._stored(["QQQ", "2026-03-24", "", "0.8", "USD", "YA"])
        scrape_fund_price.merge_dividend_rows(
            stored, [["QQQ", "2026-03-24", "2026-04-23", "0.9", "USD", "config"]]
        )
        self.assertEqual(stored[("QQQ", "2026-03-24")][3], "0.8")

    def test_a_config_row_replaces_an_earlier_config_row(self):
        """Test the owner correcting an amount in distributions.txt."""
        stored = self._stored(["X", "2026-03-01", "2026-03-31", "0.1", "GBP", "config"])
        scrape_fund_price.merge_dividend_rows(
            stored, [["X", "2026-03-01", "2026-03-31", "0.2", "GBP", "config"]]
        )
        self.assertEqual(stored[("X", "2026-03-01")][3], "0.2")


class TestSourceAuthority(unittest.TestCase):
    """Test IS beats YA beats config in the history merge (SPEC-011, #87)."""

    def test_yahoo_does_not_replace_an_issuer_row(self):
        """Test the daily upsert cannot blank a pay date."""
        stored = {
            ("Q", "2026-07-16"): ["Q", "2026-07-16", "2026-07-29", "2", "GBP", "IS"]
        }
        scrape_fund_price.merge_dividend_rows(
            stored, [["Q", "2026-07-16", "", "9", "GBP", "YA"]]
        )
        self.assertEqual(stored[("Q", "2026-07-16")][2:4], ["2026-07-29", "2"])

    def test_config_does_not_replace_an_issuer_row(self):
        """Test the owner's schedule is below the issuer."""
        stored = {
            ("Q", "2026-07-16"): ["Q", "2026-07-16", "2026-07-29", "2", "GBP", "IS"]
        }
        scrape_fund_price.merge_dividend_rows(
            stored, [["Q", "2026-07-16", "", "9", "GBP", "config"]]
        )
        self.assertEqual(stored[("Q", "2026-07-16")][5], "IS")

    def test_an_issuer_row_replaces_yahoo_and_itself(self):
        """Test the order the other way, and a correction."""
        stored = {("Q", "2026-07-16"): ["Q", "2026-07-16", "", "9", "GBP", "YA"]}
        scrape_fund_price.merge_dividend_rows(
            stored, [["Q", "2026-07-16", "2026-07-29", "2", "GBP", "IS"]]
        )
        scrape_fund_price.merge_dividend_rows(
            stored, [["Q", "2026-07-16", "2026-07-30", "3", "GBP", "IS"]]
        )
        self.assertEqual(stored[("Q", "2026-07-16")][2:4], ["2026-07-30", "3"])


class TestDividendCollection(unittest.TestCase):
    """Test the daily fetch of Yahoo dividends (SPEC-010, #85)."""

    TODAY = date(2026, 10, 26)

    def _collect(self, specs, events=None, declared=None, start=None):
        events = events or {}
        declared = declared or {}

        def fake_events(symbol, window_start, end=None):
            value = events.get(symbol, [])
            if isinstance(value, Exception):
                raise value
            return value

        def fake_declared(symbol, today=None):
            value = declared.get(symbol)
            if isinstance(value, Exception):
                raise value
            return value

        with patch.object(scrape_fund_price, "fetch_yahoo_dividends", fake_events):
            with patch.object(scrape_fund_price, "fetch_yahoo_declared", fake_declared):
                return scrape_fund_price.collect_dividends(specs, self.TODAY, start)

    def test_rows_are_published_under_every_alias(self):
        """Test one fetch, every identifier, Source YA, no pay date."""
        spec = FundSpec("YA", "0P00000YAN", ("JFM0003373",))
        results = self._collect(
            [spec],
            events={
                "0P00000YAN": [
                    scrape_fund_price.DividendEvent("2026-09-18", "1.5", "GBP")
                ]
            },
        )
        self.assertEqual(
            sorted(results),
            [
                ["0P00000YAN", "2026-09-18", "", "1.5", "GBP", "YA"],
                ["JFM0003373", "2026-09-18", "", "1.5", "GBP", "YA"],
            ],
        )

    def test_only_yahoo_instruments_are_fetched(self):
        """Test FT, IV and the scraped sources have no dividend route."""
        calls = []

        def fake_events(symbol, window_start, end=None):
            calls.append(symbol)
            return []

        specs = [
            FundSpec("FT", "GB00B1FXTF86"),
            FundSpec("YA", "QQQ"),
            FundSpec("IV", "1"),
        ]
        with patch.object(scrape_fund_price, "fetch_yahoo_dividends", fake_events):
            with patch.object(
                scrape_fund_price, "fetch_yahoo_declared", lambda s, t: None
            ):
                scrape_fund_price.collect_dividends(specs, self.TODAY)
        self.assertEqual(calls, ["QQQ"])

    def test_plain_pairs_are_accepted(self):
        """Test callers may pass (source, identifier) pairs."""
        results = self._collect(
            [("YA", "QQQ")],
            events={"QQQ": [scrape_fund_price.DividendEvent("2026-09-18", "1", "USD")]},
        )
        self.assertEqual(len(results), 1)

    def test_the_window_start_is_passed_to_the_fetch(self):
        """Test the caller decides how far back to read."""
        seen = []

        def fake_events(symbol, window_start, end=None):
            seen.append(window_start)
            return []

        with patch.object(scrape_fund_price, "fetch_yahoo_dividends", fake_events):
            with patch.object(
                scrape_fund_price, "fetch_yahoo_declared", lambda s, t: None
            ):
                scrape_fund_price.collect_dividends(
                    [FundSpec("YA", "QQQ")], self.TODAY, "2025-09-01"
                )
                scrape_fund_price.collect_dividends([FundSpec("YA", "QQQ")], self.TODAY)
        self.assertEqual(seen, ["2025-09-01", None])

    def test_events_after_today_are_ignored(self):
        """Test a future-dated event is not history."""
        results = self._collect(
            [FundSpec("YA", "QQQ")],
            events={
                "QQQ": [
                    scrape_fund_price.DividendEvent("2026-10-26", "1", "USD"),
                    scrape_fund_price.DividendEvent("2026-10-27", "1", "USD"),
                ]
            },
        )
        self.assertEqual([row[1] for row in results], ["2026-10-26"])

    def test_the_declared_dividend_is_kept_by_lookup_id(self):
        """Test the calendar answer travels with the results."""
        declared = scrape_fund_price.DeclaredDividend("2026-11-12", "2026-11-28")
        results = self._collect([FundSpec("YA", "QQQ")], declared={"QQQ": declared})
        self.assertEqual(results.declared, {"QQQ": declared})
        self.assertEqual(results.fetched, {"QQQ"})

    def test_a_failing_fetch_is_retried_then_reported_without_stopping_others(self):
        """Test one failure costs only that instrument its day."""
        attempts = []

        def fake_events(symbol, window_start, end=None):
            attempts.append(symbol)
            if symbol == "BAD":
                raise RuntimeError("Network error")
            return [scrape_fund_price.DividendEvent("2026-09-18", "1", "USD")]

        with patch.object(scrape_fund_price, "fetch_yahoo_dividends", fake_events):
            with patch.object(
                scrape_fund_price, "fetch_yahoo_declared", lambda s, t: None
            ):
                results = scrape_fund_price.collect_dividends(
                    [FundSpec("YA", "BAD"), FundSpec("YA", "QQQ")], self.TODAY
                )
        self.assertEqual(attempts.count("BAD"), scrape_fund_price.MAX_PRICE_ATTEMPTS)
        self.assertEqual(results.failures, ["BAD: dividends: Network error"])
        self.assertEqual(results.fetched, {"QQQ"})
        self.assertEqual([row[0] for row in results], ["QQQ"])

    def test_a_failing_calendar_is_a_warning_not_a_failure(self):
        """Test a missing optional fact does not turn the run red."""
        with patch("builtins.print") as mock_print:
            results = self._collect(
                [FundSpec("YA", "QQQ")], declared={"QQQ": RuntimeError("boom")}
            )
        self.assertEqual(results.failures, [])
        self.assertEqual(results.declared, {})
        printed = " ".join(str(call.args[0]) for call in mock_print.call_args_list)
        self.assertIn("QQQ", printed)
        self.assertIn("declared", printed)

    def test_the_declared_lookup_is_skipped_for_an_instrument_that_failed(self):
        """Test nothing is asked of a ticker that is already failing."""
        results = self._collect(
            [FundSpec("YA", "QQQ")],
            events={"QQQ": RuntimeError("down")},
            declared={"QQQ": scrape_fund_price.DeclaredDividend("2026-11-12", "")},
        )
        self.assertEqual(results.declared, {})


class TestAddMonths(unittest.TestCase):
    """Test calendar-month arithmetic for projecting ex-dates (SPEC-010, #85)."""

    def test_adds_whole_months(self):
        """Test the plain case and a year wrap."""
        add = scrape_fund_price.add_months
        self.assertEqual(add(date(2026, 9, 18), 3), date(2026, 12, 18))
        self.assertEqual(add(date(2026, 11, 30), 3), date(2027, 2, 28))
        self.assertEqual(add(date(2026, 12, 15), 12), date(2027, 12, 15))

    def test_clamps_to_the_end_of_a_shorter_month(self):
        """Test 31 January plus one month is the last day of February."""
        add = scrape_fund_price.add_months
        self.assertEqual(add(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(add(date(2028, 1, 31), 1), date(2028, 2, 29))
        self.assertEqual(add(date(2028, 2, 29), 12), date(2029, 2, 28))


class TestDividendFrequency(unittest.TestCase):
    """Test reading the payment frequency from ex-date spacing (SPEC-010, #85)."""

    def _period(self, *days):
        return scrape_fund_price.detect_period_months(
            [date.fromisoformat(day) for day in days]
        )

    def test_monthly(self):
        """Test gaps of about a month."""
        self.assertEqual(self._period("2026-07-10", "2026-08-11", "2026-09-10"), 1)

    def test_quarterly(self):
        """Test gaps of about three months."""
        self.assertEqual(
            self._period("2025-12-18", "2026-03-19", "2026-06-18", "2026-09-17"), 3
        )

    def test_semi_annual(self):
        """Test gaps of about six months."""
        self.assertEqual(self._period("2026-03-05", "2026-09-03"), 6)

    def test_annual(self):
        """Test gaps of about a year."""
        self.assertEqual(self._period("2025-06-12", "2026-06-11"), 12)

    def test_a_single_ex_date_is_read_as_annual(self):
        """Test one date in the window cannot show a spacing."""
        self.assertEqual(self._period("2026-06-11"), 12)

    def test_a_special_dividend_does_not_change_the_frequency(self):
        """Test the median gap, not the shortest, decides."""
        self.assertEqual(
            self._period(
                "2025-12-18", "2026-03-19", "2026-03-29", "2026-06-18", "2026-09-17"
            ),
            3,
        )

    def test_the_band_edges(self):
        """Test the thresholds: 45, 135 and 270 days."""
        base = date(2026, 1, 1)

        def period(gap):
            return scrape_fund_price.detect_period_months(
                [base, base + timedelta(days=gap)]
            )

        self.assertEqual([period(45), period(46)], [1, 3])
        self.assertEqual([period(135), period(136)], [3, 6])
        self.assertEqual([period(270), period(271)], [6, 12])


class TestEstimateNextDividend(unittest.TestCase):
    """Test projecting the next dividend from the history (SPEC-010, #85)."""

    TODAY = date(2026, 10, 26)

    def _rows(self, *specs):
        """History rows [fund, ex, pay, amount, currency, source] for one fund."""
        return [
            ["IGLS.L", ex, pay, amount, currency, "YA"]
            for ex, pay, amount, currency in specs
        ]

    def _estimate(self, rows, today=None):
        return scrape_fund_price.estimate_next_dividend(rows, today or self.TODAY)

    def test_quarterly_payer_next_ex_date_is_the_last_plus_three_months(self):
        """Test the rule: last ex-date plus the period, last amount paid."""
        rows = self._rows(
            ("2025-12-18", "", "0.30", "GBP"),
            ("2026-03-19", "", "0.31", "GBP"),
            ("2026-06-18", "", "0.32", "GBP"),
            ("2026-09-17", "", "0.33", "GBP"),
        )
        self.assertEqual(
            self._estimate(rows),
            scrape_fund_price.EstimatedDividend("2026-12-17", "", "0.33", "GBP"),
        )

    def test_a_pence_amount_and_currency_are_carried_unchanged(self):
        """Test GBp stays GBp."""
        rows = self._rows(
            ("2026-03-05", "", "24.5", "GBp"), ("2026-09-03", "", "25", "GBp")
        )
        estimate = self._estimate(rows)
        self.assertEqual((estimate.amount, estimate.currency), ("25", "GBp"))
        self.assertEqual(estimate.ex_date, "2027-03-03")

    def test_input_order_does_not_matter(self):
        """Test the newest row is found, not the last one given."""
        rows = self._rows(
            ("2026-09-03", "", "25", "GBp"), ("2026-03-05", "", "24.5", "GBp")
        )
        self.assertEqual(self._estimate(rows).amount, "25")

    def test_a_missed_period_rolls_forward_to_the_next_future_date(self):
        """Test a projected date already past is moved on by whole periods."""
        rows = self._rows(
            ("2026-02-20", "", "0.30", "GBP"),
            ("2026-05-21", "", "0.31", "GBP"),
            ("2026-08-20", "", "0.32", "GBP"),
        )
        self.assertEqual(self._estimate(rows, date(2026, 11, 30)).ex_date, "2027-02-20")

    def test_the_projected_date_may_be_today(self):
        """Test a dividend due today is still upcoming."""
        rows = self._rows(
            ("2026-01-26", "", "1", "USD"), ("2026-07-26", "", "1", "USD")
        )
        self.assertEqual(self._estimate(rows).ex_date, "2027-01-26")
        self.assertEqual(self._estimate(rows, date(2027, 1, 26)).ex_date, "2027-01-26")

    def test_the_pay_date_follows_the_last_offset_when_it_is_known(self):
        """Test a source that gives pay dates carries their spacing forward."""
        rows = self._rows(
            ("2026-03-01", "2026-03-31", "0.08", "GBP"),
            ("2026-09-01", "2026-10-01", "0.08", "GBP"),
        )
        estimate = self._estimate(rows)
        self.assertEqual(
            (estimate.ex_date, estimate.pay_date), ("2027-03-01", "2027-03-31")
        )

    def test_the_period_comes_from_the_twelve_months_to_the_last_ex_date(self):
        """Test old irregular payments do not set the frequency."""
        rows = self._rows(
            ("2024-01-10", "", "1", "USD"),
            ("2024-02-01", "", "1", "USD"),
            ("2026-03-05", "", "2", "USD"),
            ("2026-09-03", "", "2", "USD"),
        )
        self.assertEqual(self._estimate(rows).ex_date, "2027-03-03")

    def test_a_payer_that_missed_a_whole_period_has_stopped(self):
        """Test no estimate once the last ex-date is a period and 45 days old."""
        rows = self._rows(
            ("2026-03-19", "", "1", "USD"), ("2026-06-18", "", "1", "USD")
        )
        # Quarterly: the guard is 3 * 31 + 45 = 138 days after 18 June.
        self.assertIsNotNone(self._estimate(rows, date(2026, 11, 3)))
        self.assertIsNone(self._estimate(rows, date(2026, 11, 4)))

    def test_an_annual_payer_is_given_a_little_more_than_a_year(self):
        """Test a payment two days late does not end the series."""
        rows = self._rows(("2025-10-24", "", "1", "USD"))
        self.assertEqual(self._estimate(rows).ex_date, "2027-10-24")

    def test_an_unreadable_pay_date_is_left_empty(self):
        """Test a damaged pay date cannot break the projection."""
        rows = self._rows(
            ("2026-03-01", "n/a", "1", "USD"), ("2026-09-01", "n/a", "1", "USD")
        )
        self.assertEqual(self._estimate(rows).pay_date, "")

    def test_nothing_to_project_from_gives_none(self):
        """Test no rows, and rows without a usable date."""
        self.assertIsNone(self._estimate([]))
        self.assertIsNone(self._estimate(self._rows(("soon", "", "1", "USD"))))

    def test_rows_dated_after_today_are_not_history(self):
        """Test a future row cannot be the last payment."""
        rows = self._rows(
            ("2026-09-03", "", "1", "USD"), ("2027-03-03", "", "9", "USD")
        )
        self.assertEqual(self._estimate(rows).amount, "1")


class TestDistributionSchedules(DividendRunCase):
    """Test turning a distributions.txt line into rows (SPEC-010, #85)."""

    def _dist(self, text):
        """Parse a single distributions.txt line."""
        [dist] = self._dists(text)
        return dist

    def test_the_estimate_is_the_next_occurrence_of_an_ex_date(self):
        """Test next XD on or after today, paid the offset later, for its amount."""
        dist = self._dist("X,semiannual,03-01;09-01,30,0.0821;0.0794,2026-10-01")
        self.assertEqual(
            scrape_fund_price.distribution_estimate(dist, "GBP", self.TODAY),
            scrape_fund_price.EstimatedDividend(
                "2027-03-01", "2027-03-31", "0.0821", "GBP"
            ),
        )

    def test_an_ex_date_today_is_the_estimate(self):
        """Test the boundary."""
        dist = self._dist("X,semiannual,03-01;09-01,30,0.0821;0.0794")
        estimate = scrape_fund_price.distribution_estimate(
            dist, "GBP", date(2026, 9, 1)
        )
        self.assertEqual((estimate.ex_date, estimate.amount), ("2026-09-01", "0.0794"))

    def test_an_unknown_amount_is_left_empty(self):
        """Test no amount is invented for a slot with none."""
        dist = self._dist("X,annual,12-15,28")
        estimate = scrape_fund_price.distribution_estimate(dist, "GBP", self.TODAY)
        self.assertEqual(
            (estimate.ex_date, estimate.pay_date), ("2026-12-15", "2027-01-12")
        )
        self.assertEqual(estimate.amount, "")

    def test_the_search_crosses_the_year_end(self):
        """Test the next date may be next year's earliest."""
        dist = self._dist("X,quarterly,01-15;04-15;07-15;10-15,20")
        estimate = scrape_fund_price.distribution_estimate(
            dist, "GBP", date(2026, 10, 16)
        )
        self.assertEqual(estimate.ex_date, "2027-01-15")

    def test_a_leap_day_is_the_28th_in_a_common_year(self):
        """Test 02-29 clamps, and is exact in a leap year."""
        dist = self._dist("X,annual,02-29,10")
        self.assertEqual(
            scrape_fund_price.distribution_estimate(dist, "GBP", self.TODAY).ex_date,
            "2027-02-28",
        )
        self.assertEqual(
            scrape_fund_price.distribution_estimate(
                dist, "GBP", date(2027, 10, 1)
            ).ex_date,
            "2028-02-29",
        )

    def test_history_rows_come_from_the_latest_occurrence_on_or_before_as_of(self):
        """Test each amount becomes the config row for its last occurrence."""
        dist = self._dist("X,semiannual,03-01;09-01,30,0.0821;0.0794,2026-10-01")
        rows = scrape_fund_price.distribution_history_rows(dist, "GBP", self.TODAY)
        self.assertEqual(
            rows,
            [
                self.row("X", "2026-03-01", "2026-03-31", "0.0821", "GBP", "config"),
                self.row("X", "2026-09-01", "2026-10-01", "0.0794", "GBP", "config"),
            ],
        )

    def test_as_of_bounds_the_history(self):
        """Test an occurrence after as-of is not asserted, one on it is."""
        dist = self._dist("X,semiannual,03-01;09-01,30,0.0821;0.0794,2026-09-01")
        rows = scrape_fund_price.distribution_history_rows(dist, "GBP", self.TODAY)
        self.assertEqual([row[1] for row in rows], ["2026-03-01", "2026-09-01"])
        earlier = self._dist("X,semiannual,03-01;09-01,30,0.0821;0.0794,2026-08-31")
        rows = scrape_fund_price.distribution_history_rows(earlier, "GBP", self.TODAY)
        self.assertEqual([row[1] for row in rows], ["2026-03-01", "2025-09-01"])

    def test_today_bounds_the_history_when_as_of_is_later(self):
        """Test a future as-of cannot assert a dividend that has not happened."""
        dist = self._dist("X,annual,12-15,28,0.5,2027-01-01")
        rows = scrape_fund_price.distribution_history_rows(dist, "GBP", self.TODAY)
        self.assertEqual([row[1] for row in rows], ["2025-12-15"])

    def test_no_as_of_asserts_no_history(self):
        """Test amounts without a date feed estimates only."""
        dist = self._dist("X,annual,12-15,28,0.5")
        self.assertEqual(
            scrape_fund_price.distribution_history_rows(dist, "GBP", self.TODAY), []
        )

    def test_a_slot_with_no_amount_asserts_nothing(self):
        """Test only dividends with a stated amount enter the history."""
        dist = self._dist("X,semiannual,03-01;09-01,30,;0.0794,2026-10-01")
        rows = scrape_fund_price.distribution_history_rows(dist, "GBP", self.TODAY)
        self.assertEqual([row[1] for row in rows], ["2026-09-01"])


class TestDividendUpcomingStorage(DividendRunCase):
    """Test dividends_upcoming.csv reading and writing (SPEC-010, #85)."""

    def test_rows_are_written_sorted_with_a_header(self):
        """Test the file is ordered by ex-date then fund."""
        scrape_fund_price.write_dividend_upcoming(
            [
                self.upcoming("QQQ", "2026-12-22", "", "0.9", "USD", "estimated"),
                self.upcoming(
                    "IGLS.L", "2026-11-12", "2026-11-28", "0.1", "GBP", "declared"
                ),
                self.upcoming("AAA", "2026-12-22", "", "", "", "estimated"),
            ],
            self.test_dir,
        )
        self.assertEqual(
            self.read_text("dividends_upcoming.csv"),
            "Fund,ExDate,PayDate,Amount,Currency,Status,AsOf\n"
            "IGLS.L,2026-11-12,2026-11-28,0.1,GBP,declared,2026-10-26\n"
            "AAA,2026-12-22,,,,estimated,2026-10-26\n"
            "QQQ,2026-12-22,,0.9,USD,estimated,2026-10-26\n",
        )

    def test_rows_round_trip(self):
        """Test reading gives back what was written."""
        rows = [self.upcoming("QQQ", "2026-12-22", "", "0.9", "USD", "estimated")]
        scrape_fund_price.write_dividend_upcoming(rows, self.test_dir)
        self.assertEqual(scrape_fund_price.read_dividend_upcoming(self.test_dir), rows)

    def test_a_missing_file_reads_as_empty(self):
        """Test the first run has no upcoming rows."""
        self.assertEqual(scrape_fund_price.read_dividend_upcoming(self.test_dir), [])

    def test_damaged_rows_are_skipped_and_short_rows_padded(self):
        """Test a bad line cannot stop the run."""
        self.write_text(
            "dividends_upcoming.csv",
            "Fund,ExDate,PayDate,Amount,Currency,Status,AsOf\n"
            ",2026-12-22,,,,estimated,2026-10-26\n"
            "QQQ,,,,,estimated,2026-10-26\n"
            "QQQ,2026-12-22\n",
        )
        self.assertEqual(
            scrape_fund_price.read_dividend_upcoming(self.test_dir),
            [["QQQ", "2026-12-22", "", "", "", "", ""]],
        )


class TestUpcomingRowsForOneInstrument(DividendRunCase):
    """Test the declared, estimated and carried-over rules (SPEC-010, #85)."""

    def _rows(
        self,
        stored=(),
        history_dates=(),
        last_paid=("0.33", "GBP"),
        declared=None,
        estimate=None,
    ):
        return scrape_fund_price.upcoming_rows_for(
            "IGLS.L",
            [list(row) for row in stored],
            set(history_dates),
            last_paid,
            declared,
            estimate,
            self.TODAY,
        )

    ESTIMATE = scrape_fund_price.EstimatedDividend("2026-12-17", "", "0.33", "GBP")

    def _stored(self, ex, status="estimated", pay="", as_of=None):
        """A stored upcoming row for the instrument, as of the day before."""
        as_of = as_of or (date.fromisoformat(ex) - timedelta(days=1)).isoformat()
        return self.upcoming("IGLS.L", ex, pay, "0.3", "GBP", status, as_of)

    def test_an_estimate_becomes_an_estimated_row_as_of_today(self):
        """Test the projection is published with the run date."""
        self.assertEqual(
            self._rows(estimate=self.ESTIMATE),
            [self.upcoming("IGLS.L", "2026-12-17", "", "0.33", "GBP", "estimated")],
        )

    def test_a_declared_dividend_carries_the_last_paid_amount(self):
        """Test Yahoo gives the dates; the amount is the last paid."""
        declared = scrape_fund_price.DeclaredDividend("2026-11-12", "2026-11-28")
        self.assertEqual(
            self._rows(declared=declared, estimate=self.ESTIMATE),
            [
                self.upcoming(
                    "IGLS.L", "2026-11-12", "2026-11-28", "0.33", "GBP", "declared"
                )
            ],
        )

    def test_a_declared_dividend_with_no_history_has_no_amount(self):
        """Test nothing is invented when there is nothing to base an amount on."""
        declared = scrape_fund_price.DeclaredDividend("2026-11-12", "")
        [row] = self._rows(declared=declared, last_paid=("", ""))
        self.assertEqual(row[3:5], ["", ""])

    def test_a_declared_row_replaces_the_estimate_for_the_same_period(self):
        """Test there is one row per period, not an estimate beside the fact."""
        declared = scrape_fund_price.DeclaredDividend("2026-11-12", "")
        statuses = [r[5] for r in self._rows(declared=declared, estimate=self.ESTIMATE)]
        self.assertEqual(statuses, ["declared"])

    def test_a_declared_dividend_already_in_the_history_does_not_hide_the_next_estimate(
        self,
    ):
        """Test today's ex-date, recorded by Yahoo, is no longer 'upcoming'."""
        declared = scrape_fund_price.DeclaredDividend("2026-10-26", "")
        rows = self._rows(
            declared=declared, history_dates={"2026-10-26"}, estimate=self.ESTIMATE
        )
        self.assertEqual([r[5] for r in rows], ["declared", "estimated"])

    def test_a_stored_estimate_is_replaced_not_accumulated(self):
        """Test a moved estimate leaves one row, the new one."""
        stored = [self._stored("2026-12-10", as_of="2026-10-25")]
        rows = self._rows(stored=stored, estimate=self.ESTIMATE)
        self.assertEqual([r[1] for r in rows], ["2026-12-17"])

    def test_a_stored_estimate_goes_when_there_is_no_estimate_any_more(self):
        """Test an instrument that stopped paying loses its projection."""
        stored = [self._stored("2026-12-10", as_of="2026-10-25")]
        self.assertEqual(self._rows(stored=stored), [])

    def test_a_stored_declared_row_survives_a_day_yahoo_says_nothing(self):
        """Test a flaky calendar does not retract an announcement."""
        stored = [
            self._stored("2026-11-12", "declared", pay="2026-11-28", as_of="2026-10-20")
        ]
        rows = self._rows(stored=stored, estimate=self.ESTIMATE)
        self.assertEqual(rows, stored)

    def test_a_moved_declaration_replaces_the_stored_one(self):
        """Test a new declared date supersedes the old, with the new AsOf."""
        stored = [
            self._stored("2026-11-12", "declared", pay="2026-11-28", as_of="2026-10-20")
        ]
        declared = scrape_fund_price.DeclaredDividend("2026-11-19", "2026-12-03")
        rows = self._rows(stored=stored, declared=declared)
        self.assertEqual([(r[1], r[6]) for r in rows], [("2026-11-19", "2026-10-26")])

    def test_a_row_stays_for_seven_days_after_its_ex_date_even_if_in_history(self):
        """Test the downstream has a week to match it."""
        stored = [self._stored("2026-10-19"), self._stored("2026-10-18")]
        rows = self._rows(stored=stored, history_dates={"2026-10-19", "2026-10-18"})
        self.assertEqual([r[1] for r in rows], ["2026-10-19"])

    def test_a_row_older_than_seven_days_stays_while_it_is_not_in_the_history(self):
        """Test a missing dividend stays visible for the downstream's 'missing'."""
        stored = [self._stored("2026-10-10")]
        self.assertEqual(self._rows(stored=stored), stored)

    def test_a_row_older_than_thirty_days_goes_either_way(self):
        """Test nothing lingers for ever, and day thirty is the last."""
        old = [self._stored("2026-09-25"), self._stored("2026-09-20", "declared")]
        thirty = [self._stored("2026-09-26")]
        rules = {
            "not in history": (self._rows(stored=old), []),
            "in history": (
                self._rows(stored=old, history_dates={"2026-09-25", "2026-09-20"}),
                [],
            ),
            "day thirty": (self._rows(stored=thirty), thirty),
        }
        for rule, (rows, expected) in rules.items():
            with self.subTest(rule=rule):
                self.assertEqual(rows, expected)

    def test_a_stored_row_with_an_unreadable_date_is_dropped(self):
        """Test a damaged file heals itself instead of stopping the run."""
        stored = [self._stored("soon", "declared", as_of="2026-10-01")]
        self.assertEqual(self._rows(stored=stored, last_paid=("", "")), [])

    def test_rows_are_ordered_by_ex_date(self):
        """Test a carried row precedes the new estimate."""
        stored = [self._stored("2026-10-22")]
        rows = self._rows(stored=stored, estimate=self.ESTIMATE)
        self.assertEqual([r[1] for r in rows], ["2026-10-22", "2026-12-17"])


class TestDeclaredRowsCarryTheStatedAmount(unittest.TestCase):
    """Test the upcoming row of a declaration with an amount (SPEC-011, #87)."""

    TODAY = date(2026, 10, 26)

    def _rows(self, declared, estimate=None, stored=()):
        return scrape_fund_price.upcoming_rows_for(
            "IGLS.L",
            [list(row) for row in stored],
            set(),
            ("0.33", "GBP"),
            declared,
            estimate,
            self.TODAY,
        )

    def test_the_stated_amount_replaces_the_last_paid(self):
        """Test the declared amount is the issuer's, not an echo."""
        declared = scrape_fund_price.DeclaredDividend(
            "2026-11-12", "2026-11-25", "2.5", "GBp"
        )
        self.assertEqual(
            self._rows(declared),
            [
                [
                    "IGLS.L",
                    "2026-11-12",
                    "2026-11-25",
                    "2.5",
                    "GBp",
                    "declared",
                    "2026-10-26",
                ]
            ],
        )

    def test_a_declaration_without_an_amount_still_carries_the_last_paid(self):
        """Test Yahoo's declaration, as in SPEC-010."""
        declared = scrape_fund_price.DeclaredDividend("2026-11-12", "2026-11-25")
        [row] = self._rows(declared)
        self.assertEqual(row[3:5], ["0.33", "GBP"])

    def test_it_replaces_the_estimate_and_an_earlier_declaration(self):
        """Test the issuer's date wins over a Yahoo date stored yesterday."""
        stored = [
            ["IGLS.L", "2026-11-19", "", "0.33", "GBP", "declared", "2026-10-25"],
            ["IGLS.L", "2026-11-21", "", "0.33", "GBP", "estimated", "2026-10-25"],
        ]
        estimate = scrape_fund_price.EstimatedDividend("2026-11-21", "", "0.33", "GBP")
        declared = scrape_fund_price.DeclaredDividend(
            "2026-11-12", "2026-11-25", "2.5", "GBP"
        )
        rows = self._rows(declared, estimate, stored)
        self.assertEqual(
            [(row[1], row[5]) for row in rows], [("2026-11-12", "declared")]
        )


class TestBuildDividendUpcoming(DividendRunCase):
    """Test the whole upcoming file from the day's inputs (SPEC-010, #85)."""

    def _history(self, *rows):
        return {(row[0], row[1]): list(row) for row in rows}

    def _dist(self, text):
        return self._dists(text)

    def _build(
        self,
        specs,
        history=None,
        distributions=(),
        stored=(),
        declared=None,
        currencies=None,
    ):
        return scrape_fund_price.build_dividend_upcoming(
            specs,
            list(distributions),
            history or {},
            [list(row) for row in stored],
            declared or {},
            self.TODAY,
            currencies or {},
        )

    def test_a_pattern_estimate_is_published_under_every_alias(self):
        """Test one projection, every identifier."""
        history = self._history(
            self.row("0P00000YAN", "2026-03-05", "", "1", "GBP", "YA"),
            self.row("0P00000YAN", "2026-09-03", "", "1.1", "GBP", "YA"),
            self.row("JFM0003373", "2026-03-05", "", "1", "GBP", "YA"),
            self.row("JFM0003373", "2026-09-03", "", "1.1", "GBP", "YA"),
        )
        rows = self._build([FundSpec("YA", "0P00000YAN", ("JFM0003373",))], history)
        self.assertEqual(
            rows,
            [
                self.upcoming(
                    "0P00000YAN", "2027-03-03", "", "1.1", "GBP", "estimated"
                ),
                self.upcoming(
                    "JFM0003373", "2027-03-03", "", "1.1", "GBP", "estimated"
                ),
            ],
        )

    def test_history_held_only_under_an_alias_is_still_used(self):
        """Test an alias may carry the whole history."""
        history = self._history(
            self.row("OLD", "2026-03-05", "", "1", "GBP", "YA"),
            self.row("OLD", "2026-09-03", "", "1.1", "GBP", "YA"),
        )
        rows = self._build([FundSpec("YA", "NEW", ("OLD",))], history)
        self.assertEqual(sorted({r[0] for r in rows}), ["NEW", "OLD"])

    def test_no_history_and_nothing_declared_gives_no_row(self):
        """Test an instrument that has never paid has no row."""
        self.assertEqual(self._build([FundSpec("YA", "GRAB")]), [])

    def test_a_declared_dividend_is_published_for_the_lookup_id_and_aliases(self):
        """Test the calendar answer is keyed by lookup id, published everywhere."""
        history = self._history(self.row("QQQ", "2026-09-22", "", "0.9", "USD", "YA"))
        declared = {
            "QQQ": scrape_fund_price.DeclaredDividend("2026-11-12", "2026-11-28")
        }
        rows = self._build([FundSpec("YA", "QQQ")], history, declared=declared)
        self.assertEqual(
            rows,
            [
                self.upcoming(
                    "QQQ", "2026-11-12", "2026-11-28", "0.9", "USD", "declared"
                )
            ],
        )

    def test_a_distributions_line_supplies_the_estimate_for_an_oeic(self):
        """Test the FT-sourced fund gets its schedule, in its price currency."""
        dists = self._dist("GB00B1FXTF86,semiannual,03-01;09-01,30,0.0821;0.0794")
        rows = self._build(
            [FundSpec("FT", "GB00B1FXTF86")],
            distributions=dists,
            currencies={"GB00B1FXTF86": "GBP"},
        )
        self.assertEqual(
            rows,
            [
                self.upcoming(
                    "GB00B1FXTF86",
                    "2027-03-01",
                    "2027-03-31",
                    "0.0821",
                    "GBP",
                    "estimated",
                )
            ],
        )

    def test_a_distributions_line_for_an_alias_covers_the_whole_instrument(self):
        """Test the schedule applies whichever identifier the owner used."""
        dists = self._dist("JFM0003373,annual,12-15,28,0.5")
        rows = self._build(
            [FundSpec("YA", "0P00000YAN", ("JFM0003373",))],
            distributions=dists,
            currencies={"JFM0003373": "GBP"},
        )
        self.assertEqual({r[0] for r in rows}, {"0P00000YAN", "JFM0003373"})
        self.assertEqual({r[4] for r in rows}, {"GBP"})

    def test_a_distributions_line_beats_the_pattern(self):
        """Test the owner's statement of the dates wins over a projection."""
        history = self._history(
            self.row("X", "2026-03-05", "", "1", "GBP", "YA"),
            self.row("X", "2026-09-03", "", "1", "GBP", "YA"),
        )
        dists = self._dist("X,annual,12-15,28,0.5")
        [row] = self._build([FundSpec("YA", "X")], history, dists)
        self.assertEqual(row[1], "2026-12-15")

    def test_a_distributions_line_with_no_known_currency_leaves_it_empty(self):
        """Test a fund with no stored price has no currency to claim."""
        dists = self._dist("X,annual,12-15,28,0.5")
        [row] = self._build([FundSpec("FT", "X")], distributions=dists)
        self.assertEqual(row[4], "")

    def test_closed_holdings_get_no_upcoming_row(self):
        """Test a line for an instrument outside funds.txt produces nothing."""
        dists = self._dist("BMV7ZZ3,annual,12-15,28,0.5")
        self.assertEqual(self._build([FundSpec("YA", "QQQ")], distributions=dists), [])

    def test_stored_rows_of_unconfigured_funds_are_dropped(self):
        """Test the file follows funds.txt."""
        stored = [
            self.upcoming(
                "GONE", "2026-12-17", "", "1", "GBP", "estimated", "2026-10-25"
            )
        ]
        self.assertEqual(self._build([FundSpec("YA", "QQQ")], stored=stored), [])

    def test_a_stored_declared_row_is_carried_for_every_alias(self):
        """Test a lookup that fails today keeps yesterday's announcement."""
        stored = [
            self.upcoming(
                "QQQ", "2026-11-12", "", "0.9", "USD", "declared", "2026-10-25"
            )
        ]
        rows = self._build([FundSpec("YA", "QQQ", ("QQQ.US",))], stored=stored)
        self.assertEqual(
            [(r[0], r[6]) for r in rows],
            [("QQQ", "2026-10-25"), ("QQQ.US", "2026-10-25")],
        )

    def test_plain_pairs_are_accepted(self):
        """Test callers may pass (source, identifier) pairs."""
        history = self._history(self.row("QQQ", "2026-09-22", "", "0.9", "USD", "YA"))
        self.assertEqual(len(self._build([("YA", "QQQ")], history)), 1)


class TestDailyDividendUpdate(DividendRunCase):
    """Test the daily dividend run (SPEC-010, #85)."""

    EVENT = scrape_fund_price.DividendEvent

    def test_the_first_run_reads_the_whole_history(self):
        """Test no dividends_history.csv yet means no window."""
        self._run([FundSpec("YA", "QQQ")])
        self.assertEqual(self.windows, [("QQQ", None)])

    def test_later_runs_read_a_window_of_four_hundred_days(self):
        """Test the daily call is cheap once the history exists."""
        self._run([FundSpec("YA", "QQQ")])
        self._run([FundSpec("YA", "QQQ")])
        self.assertEqual(self.windows, [("QQQ", "2025-09-21")])

    def test_both_files_are_written_for_every_alias(self):
        """Test history and upcoming, published under each identifier."""
        events = {
            "0P00000YAN": [
                self.EVENT("2026-03-05", "1", "GBP"),
                self.EVENT("2026-09-03", "1.1", "GBP"),
            ]
        }
        self._run([FundSpec("YA", "0P00000YAN", ("JFM0003373",))], events)
        self.assertEqual(
            self.read_rows("dividends_history.csv"),
            [
                self.row("0P00000YAN", "2026-03-05", "", "1", "GBP", "YA"),
                self.row("JFM0003373", "2026-03-05", "", "1", "GBP", "YA"),
                self.row("0P00000YAN", "2026-09-03", "", "1.1", "GBP", "YA"),
                self.row("JFM0003373", "2026-09-03", "", "1.1", "GBP", "YA"),
            ],
        )
        self.assertEqual(
            self.read_rows("dividends_upcoming.csv"),
            [
                self.upcoming(
                    "0P00000YAN", "2027-03-03", "", "1.1", "GBP", "estimated"
                ),
                self.upcoming(
                    "JFM0003373", "2027-03-03", "", "1.1", "GBP", "estimated"
                ),
            ],
        )

    def test_a_declared_dividend_reaches_the_upcoming_file(self):
        """Test Yahoo's next ex-date is published as declared."""
        events = {"QQQ": [self.EVENT("2026-09-22", "0.9", "USD")]}
        declared = {
            "QQQ": scrape_fund_price.DeclaredDividend("2026-11-12", "2026-11-28")
        }
        self._run([FundSpec("YA", "QQQ")], events, declared)
        self.assertEqual(
            self.read_rows("dividends_upcoming.csv"),
            [
                self.upcoming(
                    "QQQ", "2026-11-12", "2026-11-28", "0.9", "USD", "declared"
                )
            ],
        )

    def test_a_rerun_changes_nothing(self):
        """Test the files are byte-identical on a second identical run."""
        events = {"QQQ": [self.EVENT("2026-09-22", "0.9", "USD")]}
        self._run([FundSpec("YA", "QQQ")], events)
        names = ("dividends_history.csv", "dividends_upcoming.csv")
        first = [self.read_text(name) for name in names]
        self._run([FundSpec("YA", "QQQ")], events)
        second = [self.read_text(name) for name in names]
        self.assertEqual(first, second)

    def test_a_changed_amount_replaces_the_stored_row(self):
        """Test a correction from Yahoo applies."""
        self._run(
            [FundSpec("YA", "QQQ")], {"QQQ": [self.EVENT("2026-09-22", "0.9", "USD")]}
        )
        self._run(
            [FundSpec("YA", "QQQ")], {"QQQ": [self.EVENT("2026-09-22", "0.95", "USD")]}
        )
        self.assertEqual(
            self.read_rows("dividends_history.csv"),
            [self.row("QQQ", "2026-09-22", "", "0.95", "USD", "YA")],
        )

    def test_older_history_is_kept_when_the_window_moves_on(self):
        """Test the daily run only ever upserts."""
        self.write_history(self.row("QQQ", "2020-03-24", "", "0.5", "USD", "YA"))
        self._run(
            [FundSpec("YA", "QQQ")], {"QQQ": [self.EVENT("2026-09-22", "0.9", "USD")]}
        )
        self.assertEqual(len(self.read_rows("dividends_history.csv")), 2)

    def test_a_failed_instrument_keeps_its_rows_and_is_reported(self):
        """Test one failure costs only that instrument; the files are still written."""
        self.write_history(
            self.row("BAD", "2026-03-05", "", "1", "USD", "YA"),
            self.row("BAD", "2026-09-03", "", "1", "USD", "YA"),
        )
        results = self._run(
            [FundSpec("YA", "BAD"), FundSpec("YA", "QQQ")],
            {
                "BAD": RuntimeError("down"),
                "QQQ": [self.EVENT("2026-09-22", "0.9", "USD")],
            },
        )
        self.assertEqual(results.failures, ["BAD: dividends: down"])
        funds = {row[0] for row in self.read_rows("dividends_history.csv")}
        self.assertEqual(funds, {"BAD", "QQQ"})
        # The failed fund's upcoming row is still projected from what it had.
        funds = {row[0] for row in self.read_rows("dividends_upcoming.csv")}
        self.assertEqual(funds, {"BAD", "QQQ"})

    def test_config_rows_enter_the_history_in_the_price_currency(self):
        """Test a distributions.txt line asserts its past dividends."""
        self.write_csv(
            "latest_prices.csv",
            ["Fund", "Date", "Price", "Currency"],
            [["GB00B1FXTF86", "2026-10-23", "7.15", "GBP"]],
        )
        dists = self._dists(
            "GB00B1FXTF86,semiannual,03-01;09-01,30,0.0821;0.0794,2026-10-01"
        )
        self._run([FundSpec("FT", "GB00B1FXTF86")], distributions=dists)
        fund = "GB00B1FXTF86"
        self.assertEqual(
            self.read_rows("dividends_history.csv"),
            [
                self.row(fund, "2026-03-01", "2026-03-31", "0.0821", "GBP", "config"),
                self.row(fund, "2026-09-01", "2026-10-01", "0.0794", "GBP", "config"),
            ],
        )
        self.assertEqual(
            self.read_rows("dividends_upcoming.csv"),
            [
                self.upcoming(
                    fund, "2027-03-01", "2027-03-31", "0.0821", "GBP", "estimated"
                )
            ],
        )

    def test_config_rows_are_published_under_every_alias_and_yahoo_wins(self):
        """Test the alias rule, and that a Yahoo row beats the owner's."""
        dists = self._dists("JFM0003373,annual,09-03,28,1.2,2026-10-01")
        self._run(
            [FundSpec("YA", "0P00000YAN", ("JFM0003373",))],
            {"0P00000YAN": [self.EVENT("2026-09-03", "1.25", "GBP")]},
            distributions=dists,
        )
        rows = self.read_rows("dividends_history.csv")
        with self.subTest(rule="every alias"):
            self.assertEqual({row[0] for row in rows}, {"0P00000YAN", "JFM0003373"})
        with self.subTest(rule="Yahoo wins"):
            self.assertEqual({(row[3], row[5]) for row in rows}, {("1.25", "YA")})

    def test_a_closed_holding_gets_history_but_no_upcoming_row(self):
        """Test closed holdings are never fetched and never expected to pay."""
        dists = self._dists("BMV7ZZ3,annual,03-05,20,0.4,2026-10-01")
        results = self._run([FundSpec("YA", "QQQ")], distributions=dists)
        self.assertEqual(self.windows, [("QQQ", None)])
        self.assertEqual(results.failures, [])
        self.assertEqual(
            self.read_rows("dividends_history.csv"),
            [self.row("BMV7ZZ3", "2026-03-05", "2026-03-25", "0.4", "", "config")],
        )
        self.assertEqual(self.read_rows("dividends_upcoming.csv"), [])

    def test_the_default_directory_and_date_are_used_when_omitted(self):
        """Test the production call has no arguments to get wrong."""
        with patch.object(scrape_fund_price, "DATA_DIR", self.test_dir):
            with patch.object(
                scrape_fund_price, "fetch_yahoo_dividends", lambda s, w, e=None: []
            ):
                with patch.object(
                    scrape_fund_price, "fetch_yahoo_declared", lambda s, t=None: None
                ):
                    scrape_fund_price.update_dividends([FundSpec("YA", "QQQ")], [])
        self.assertTrue(os.path.isfile(self.path("dividends_history.csv")))
        self.assertTrue(os.path.isfile(self.path("dividends_upcoming.csv")))


class TestDividendBackfill(DividendRunCase):
    """Test rebuilding the dividend history from the sources (SPEC-010, #85)."""

    EVENT = scrape_fund_price.DividendEvent

    def _backfill(self, specs, events, start=None, distributions=()):
        def runner(specs, dists, data_dir, today):
            return scrape_fund_price.backfill_dividends(
                specs, dists, start, data_dir, today
            )

        return self._run(specs, events, distributions=distributions, runner=runner)

    def test_the_rebuild_replaces_source_rows_from_the_start_date(self):
        """Test rows Yahoo no longer reports go, and earlier ones stay."""
        self.write_history(
            self.row("QQQ", "2025-03-24", "", "0.5", "USD", "YA"),
            self.row("QQQ", "2026-03-24", "", "0.6", "USD", "YA"),
            self.row("QQQ", "2026-06-23", "", "0.7", "USD", "YA"),
        )
        report = self._backfill(
            [FundSpec("YA", "QQQ")],
            {
                "QQQ": [
                    self.EVENT("2026-03-25", "0.65", "USD"),
                    self.EVENT("2026-06-23", "0.71", "USD"),
                ]
            },
            start="2026-01-01",
        )
        self.assertEqual(
            self.read_rows("dividends_history.csv"),
            [
                self.row("QQQ", "2025-03-24", "", "0.5", "USD", "YA"),
                self.row("QQQ", "2026-03-25", "", "0.65", "USD", "YA"),
                self.row("QQQ", "2026-06-23", "", "0.71", "USD", "YA"),
            ],
        )
        self.assertEqual(self.windows, [("QQQ", "2026-01-01")])
        [entry] = report.entries
        self.assertEqual(
            (
                entry["identifier"],
                entry["before"],
                entry["deleted"],
                entry["retained"],
                entry["inserted"],
            ),
            ("QQQ", 3, 2, 1, 2),
        )
        self.assertEqual(
            (entry["first"], entry["last"], entry["status"]),
            ("2026-03-25", "2026-06-23", "rebuilt"),
        )

    def test_no_start_date_rebuilds_everything_from_the_source(self):
        """Test the whole of Yahoo's history is read and the source rows replaced."""
        self.write_history(self.row("QQQ", "2019-03-24", "", "0.5", "USD", "YA"))
        self._backfill(
            [FundSpec("YA", "QQQ")], {"QQQ": [self.EVENT("2026-06-23", "0.71", "USD")]}
        )
        self.assertEqual(self.windows, [("QQQ", None)])
        self.assertEqual(
            [row[1] for row in self.read_rows("dividends_history.csv")],
            ["2026-06-23"],
        )

    def test_config_rows_survive_a_rebuild(self):
        """Test the owner's rows are not the source's to delete."""
        self.write_history(
            self.row("QQQ", "2026-03-24", "2026-04-23", "0.5", "USD", "config")
        )
        self._backfill([FundSpec("YA", "QQQ")], {"QQQ": []})
        self.assertEqual(len(self.read_rows("dividends_history.csv")), 1)

    def test_a_failing_instrument_keeps_what_it_had(self):
        """Test a source outage cannot wipe an instrument's history."""
        self.write_history(self.row("BAD", "2026-03-05", "", "1", "USD", "YA"))
        report = self._backfill(
            [FundSpec("YA", "BAD"), FundSpec("YA", "QQQ")],
            {
                "BAD": RuntimeError("down"),
                "QQQ": [self.EVENT("2026-06-23", "0.71", "USD")],
            },
            start="2026-01-01",
        )
        self.assertEqual(report.failures, ["BAD: dividends: down"])
        self.assertEqual(
            {row[0] for row in self.read_rows("dividends_history.csv")},
            {"BAD", "QQQ"},
        )
        bad = [e for e in report.entries if e["identifier"] == "BAD"][0]
        self.assertEqual((bad["deleted"], bad["status"]), (0, "failed, kept existing"))

    def test_every_alias_is_rebuilt_and_reported(self):
        """Test one fetch, each identifier replaced."""
        report = self._backfill(
            [FundSpec("YA", "0P00000YAN", ("JFM0003373",))],
            {"0P00000YAN": [self.EVENT("2026-06-23", "0.71", "GBP")]},
        )
        self.assertEqual(
            [e["identifier"] for e in report.entries], ["0P00000YAN", "JFM0003373"]
        )
        self.assertEqual(len(self.read_rows("dividends_history.csv")), 2)

    def test_an_instrument_with_nothing_to_report_is_rebuilt_empty(self):
        """Test the report copes with no events (first and last are dashes)."""
        report = self._backfill([FundSpec("YA", "GRAB")], {"GRAB": []})
        [entry] = report.entries
        self.assertEqual(
            (entry["first"], entry["last"], entry["currency"]), ("-", "-", "-")
        )

    def test_only_yahoo_instruments_are_rebuilt_and_the_upcoming_file_follows(self):
        """Test FT funds are untouched by the source and estimates are refreshed."""
        dists = self._dists("GB00B1FXTF86,annual,12-15,28,0.5,2026-10-01")
        report = self._backfill(
            [FundSpec("FT", "GB00B1FXTF86"), FundSpec("YA", "QQQ")],
            {"QQQ": [self.EVENT("2026-06-23", "0.71", "USD")]},
            distributions=dists,
        )
        self.assertEqual([e["identifier"] for e in report.entries], ["QQQ"])
        funds = {row[0] for row in self.read_rows("dividends_history.csv")}
        self.assertEqual(funds, {"GB00B1FXTF86", "QQQ"})
        funds = {row[0] for row in self.read_rows("dividends_upcoming.csv")}
        self.assertEqual(funds, {"GB00B1FXTF86", "QQQ"})

    def test_the_default_directory_and_date_are_used_when_omitted(self):
        """Test the production call needs only the start date."""
        with patch.object(scrape_fund_price, "DATA_DIR", self.test_dir):
            with patch.object(
                scrape_fund_price, "fetch_yahoo_dividends", lambda s, w, e=None: []
            ):
                scrape_fund_price.backfill_dividends(
                    [FundSpec("YA", "QQQ")], [], "2026-01-01"
                )
        self.assertTrue(os.path.isfile(self.path("dividends_history.csv")))


class TestDividendSummary(DividendRunCase):
    """Test the daily summary's Dividends section (SPEC-010, #85)."""

    def _row(self, fund, ex, pay="", amount="0.9", ccy="USD", status="estimated"):
        return self.upcoming(fund, ex, pay, amount, ccy, status)

    def _build(self, previous, upcoming, specs=None):
        specs = specs or [FundSpec("YA", "QQQ")]
        return scrape_fund_price.build_dividend_summary(previous, upcoming, specs)

    def test_a_new_ex_date_is_listed(self):
        """Test the headline case: nothing before, a row today."""
        rows = self._build([], [self._row("QQQ", "2026-12-22")])
        self.assertEqual(
            rows,
            [
                scrape_fund_price.DividendSummaryRow(
                    "QQQ", (), "2026-12-22", "", "0.9", "USD", "estimated"
                )
            ],
        )

    def test_an_unchanged_row_is_not_news(self):
        """Test yesterday's row repeated today is left out."""
        same = [self._row("QQQ", "2026-12-22")]
        self.assertEqual(self._build(same, same), [])

    def test_a_new_pay_date_is_listed(self):
        """Test the pay date arriving for a known ex-date."""
        before = [self._row("QQQ", "2026-11-12", status="declared")]
        after = [self._row("QQQ", "2026-11-12", pay="2026-11-28", status="declared")]
        [row] = self._build(before, after)
        self.assertEqual((row.ex_date, row.pay_date), ("2026-11-12", "2026-11-28"))

    def test_an_estimate_that_becomes_declared_is_listed(self):
        """Test the status change is news even with the same dates."""
        before = [self._row("QQQ", "2026-11-12", pay="2026-11-28")]
        after = [self._row("QQQ", "2026-11-12", pay="2026-11-28", status="declared")]
        [row] = self._build(before, after)
        self.assertEqual(row.status, "declared")

    def test_a_changed_amount_alone_is_not_news(self):
        """Test only dates and status make an entry."""
        before = [self._row("QQQ", "2026-12-22", amount="0.9")]
        after = [self._row("QQQ", "2026-12-22", amount="0.95")]
        self.assertEqual(self._build(before, after), [])

    def test_an_instrument_is_listed_once_under_its_aliases(self):
        """Test the aliases carry identical rows and appear in the name."""
        specs = [FundSpec("YA", "0P00000YAN", ("JFM0003373",))]
        upcoming = [
            self._row("0P00000YAN", "2027-03-03", ccy="GBP"),
            self._row("JFM0003373", "2027-03-03", ccy="GBP"),
        ]
        [row] = self._build([], upcoming, specs)
        self.assertEqual((row.name, row.aliases), ("0P00000YAN", ("JFM0003373",)))

    def test_rows_follow_the_order_of_funds_txt_then_ex_date(self):
        """Test a stable, readable order."""
        specs = [FundSpec("YA", "QQQ"), FundSpec("YA", "AAA")]
        upcoming = [
            self._row("AAA", "2026-11-01"),
            self._row("QQQ", "2026-12-22"),
            self._row("QQQ", "2026-11-12"),
        ]
        rows = self._build([], upcoming, specs)
        self.assertEqual(
            [(r.name, r.ex_date) for r in rows],
            [("QQQ", "2026-11-12"), ("QQQ", "2026-12-22"), ("AAA", "2026-11-01")],
        )

    def test_markdown_gains_a_dividends_section(self):
        """Test the section, with dashes for the cells that are empty."""
        rows = [
            scrape_fund_price.DividendSummaryRow(
                "0P00000YAN",
                ("JFM0003373",),
                "2027-03-03",
                "",
                "1.1",
                "GBP",
                "estimated",
            ),
            scrape_fund_price.DividendSummaryRow(
                "QQQ", (), "2026-11-12", "2026-11-28", "", "", "declared"
            ),
        ]
        text = render_summary_markdown([], [], "2026-10-26", dividend_rows=rows)
        self.assertIn("## Dividends", text)
        self.assertIn("| Name | Ex-date | Pay date | Amount | Ccy | Status |", text)
        self.assertIn(
            "| 0P00000YAN (JFM0003373) | 2027-03-03 | - | 1.1 | GBP | estimated |", text
        )
        self.assertIn("| QQQ | 2026-11-12 | 2026-11-28 | - | - | declared |", text)

    def test_markdown_says_none_when_nothing_changed(self):
        """Test an empty list is a section that reads None."""
        text = render_summary_markdown([], [], "2026-10-26", dividend_rows=[])
        self.assertIn("## Dividends\n\nNone\n", text)

    def test_markdown_is_unchanged_without_dividend_rows(self):
        """Test callers that know nothing of dividends see the old output."""
        self.assertNotIn("Dividends", render_summary_markdown([], [], "2026-10-26"))

    def test_write_summary_puts_the_section_in_the_markdown_only(self):
        """Test the CSV keeps one row per instrument and its header."""
        rows = [
            scrape_fund_price.DividendSummaryRow(
                "QQQ", (), "2026-11-12", "", "0.9", "USD", "declared"
            )
        ]
        write_summary([], [], "2026-10-26", self.test_dir, dividend_rows=rows)
        self.assertIn(
            "| QQQ | 2026-11-12 | - | 0.9 | USD | declared |",
            self.read_text("daily_summary.md"),
        )
        self.assertNotIn("QQQ", self.read_text("daily_summary.csv"))


class TestDailyDividendSummaryFlow(DividendRunCase):
    """Test the update hands the summary what is new today (SPEC-010, #85)."""

    def test_the_first_run_lists_every_row_and_the_second_none(self):
        """Test news is the difference from the previous file."""
        events = {"QQQ": [scrape_fund_price.DividendEvent("2026-09-22", "0.9", "USD")]}
        first = self._run([FundSpec("YA", "QQQ")], events)
        self.assertEqual([row.name for row in first.summary], ["QQQ"])
        second = self._run([FundSpec("YA", "QQQ")], events)
        self.assertEqual(second.summary, [])

    def test_a_declaration_appearing_later_is_listed_that_day(self):
        """Test the estimate-to-declared hand-over reaches the summary."""
        events = {"QQQ": [scrape_fund_price.DividendEvent("2026-09-22", "0.9", "USD")]}
        self._run([FundSpec("YA", "QQQ")], events)
        declared = {
            "QQQ": scrape_fund_price.DeclaredDividend("2026-11-12", "2026-11-28")
        }
        third = self._run([FundSpec("YA", "QQQ")], events, declared)
        [row] = third.summary
        self.assertEqual((row.ex_date, row.status), ("2026-11-12", "declared"))


class TestDividendBackfillArguments(unittest.TestCase):
    """Test the --backfill-dividends command line (SPEC-010, #85)."""

    def _args(self, **overrides):
        values = dict(
            backfill=False,
            history=None,
            import_closed=False,
            backfill_dividends=True,
            start=None,
        )
        values.update(overrides)
        return MagicMock(**values)

    def test_flag_is_parsed_and_defaults_off(self):
        """Test the flag exists, alone or with --from."""
        self.assertFalse(parse_arguments([]).backfill_dividends)
        args = parse_arguments(["--backfill-dividends", "--from", "2024-01-01"])
        self.assertTrue(args.backfill_dividends)
        self.assertEqual(args.start, "2024-01-01")

    def test_no_start_date_is_valid(self):
        """Test the whole history is the default."""
        validate = scrape_fund_price.validate_dividend_backfill_args
        self.assertIsNone(validate(self._args()))
        self.assertIsNone(validate(self._args(start="2024-01-01")))

    def test_other_modes_cannot_be_combined(self):
        """Test one mode at a time."""
        validate = scrape_fund_price.validate_dividend_backfill_args
        for combined in (
            {"backfill": True},
            {"history": "AAPL"},
            {"import_closed": True},
        ):
            with self.subTest(combined=combined):
                self.assertIn("cannot be combined", validate(self._args(**combined)))

    def test_a_bad_or_future_start_date_is_rejected(self):
        """Test the same date rules as --backfill."""
        validate = scrape_fund_price.validate_dividend_backfill_args
        self.assertIn("Invalid --from", validate(self._args(start="01/01/2024")))
        self.assertIn("Invalid --from", validate(self._args(start="2024-13-45")))
        future = (date.today() + timedelta(days=2)).isoformat()
        self.assertIn("future", validate(self._args(start=future)))

    def test_not_asked_for_is_not_validated(self):
        """Test a daily run skips the check."""
        validate = scrape_fund_price.validate_dividend_backfill_args
        self.assertIsNone(validate(self._args(backfill_dividends=False, backfill=True)))


class TestDividendsInTheDailyRun(DataDirCase):
    """Test main() runs the dividend update beside the prices (SPEC-010, #85)."""

    def setUp(self):
        super().setUp()
        self.distributions_file = self.write_text(
            "distributions.txt", "# nothing yet\n"
        )

    def _run(self, update=None):
        """Run main() with prices faked, keeping the stubs that matter."""
        if update is None:
            update = scrape_fund_price.DividendResults()
        with daily_run_stubs(
            specs=[FundSpec("YA", "QQQ")],
            update_dividends=update,
            DISTRIBUTIONS_FILE={"new": self.distributions_file},
        ) as stubs:
            self.scrape = stubs["scrape_funds"]
            self.summary = stubs["write_summary"]
            self.update = stubs["update_dividends"]
            self.printed = stubs["print"]
            main([])

    def test_the_update_runs_after_the_prices_with_the_configuration(self):
        """Test update_dividends gets the funds and the validated schedules."""
        self._run()
        self.update.assert_called_once()
        specs, distributions = self.update.call_args.args
        self.assertEqual([spec.lookup_id for spec in specs], ["QQQ"])
        self.assertEqual(distributions, [])

    def test_the_summary_receives_the_days_dividend_rows(self):
        """Test news from the update reaches daily_summary.md."""
        results = scrape_fund_price.DividendResults()
        results.summary = [
            scrape_fund_price.DividendSummaryRow(
                "QQQ", (), "2026-11-12", "", "", "", "declared"
            )
        ]
        self._run(update=results)
        self.assertEqual(
            self.summary.call_args.kwargs["dividend_rows"], results.summary
        )

    def test_a_bad_distributions_file_fails_before_any_network_call(self):
        """Test validation comes first, as it does for funds.txt."""
        self.write_text("distributions.txt", "NOPE,annual,03-01,30\n")
        with self.assertRaisesRegex(ValueError, "line 1.*NOPE"):
            self._run()
        self.scrape.assert_not_called()
        self.update.assert_not_called()

    def test_dividend_failures_fail_the_run_after_everything_is_written(self):
        """Test a dividend failure is reported like a price failure."""
        results = scrape_fund_price.DividendResults(failures=["QQQ: dividends: down"])
        with self.assertRaises(SystemExit) as error:
            self._run(update=results)
        self.assertEqual(error.exception.code, 1)
        self.summary.assert_called_once()

    def test_a_crash_in_the_dividend_update_does_not_cost_the_summary(self):
        """Test the price summary is still written, and the run still fails."""
        with self.assertRaises(SystemExit):
            self._run(update=RuntimeError("disk full"))
        self.summary.assert_called_once()
        self.assertEqual(self.summary.call_args.kwargs["dividend_rows"], [])
        printed = " ".join(str(call.args[0]) for call in self.printed.call_args_list)
        self.assertIn("dividends: disk full", printed)


class TestDividendBackfillMainMode(DataDirCase):
    """Test main() with --backfill-dividends (SPEC-010, #85)."""

    def _argv(self, start="2024-01-01"):
        return ["--backfill-dividends"] + (["--from", start] if start else [])

    def _report(self, failures=()):
        report = BackfillReport()
        report.entries.append(
            {
                "identifier": "QQQ",
                "before": 3,
                "deleted": 2,
                "retained": 1,
                "inserted": 2,
                "first": "2026-03-25",
                "last": "2026-06-23",
                "currency": "USD",
                "status": "rebuilt",
            }
        )
        report.failures.extend(failures)
        return report

    @patch("builtins.print")
    @patch("scrape_fund_price.backfill_dividends")
    @patch("scrape_fund_price.read_distributions", return_value=[])
    @patch("scrape_fund_price.read_fund_specs")
    @patch("scrape_fund_price.scrape_funds")
    def test_rebuilds_from_the_start_date_and_prints_the_report(
        self, mock_scrape, mock_specs, _dists, mock_backfill, mock_print
    ):
        """Test the rebuild runs alone and its table reaches stdout."""
        mock_specs.return_value = [FundSpec("YA", "QQQ")]
        mock_backfill.return_value = self._report()
        main(self._argv())
        mock_scrape.assert_not_called()
        [call] = mock_backfill.call_args_list
        self.assertEqual(call.args[0][0].lookup_id, "QQQ")
        self.assertEqual(call.args[2], "2024-01-01")
        printed = " ".join(str(c.args[0]) for c in mock_print.call_args_list)
        self.assertIn("| QQQ |", printed)

    @patch("scrape_fund_price.backfill_dividends")
    @patch("scrape_fund_price.read_distributions", return_value=[])
    @patch("scrape_fund_price.read_fund_specs", return_value=[])
    def test_no_start_date_rebuilds_everything(self, _specs, _dists, mock_backfill):
        """Test --from is optional."""
        mock_backfill.return_value = self._report()
        main(self._argv(start=None))
        self.assertIsNone(mock_backfill.call_args.args[2])

    @patch("scrape_fund_price.backfill_dividends")
    @patch("scrape_fund_price.read_distributions", return_value=[])
    @patch("scrape_fund_price.read_fund_specs", return_value=[])
    def test_failures_exit_non_zero_after_the_report(
        self, _specs, _dists, mock_backfill
    ):
        """Test a partial rebuild is visible to the workflow."""
        mock_backfill.return_value = self._report(failures=["BAD: dividends: down"])
        with self.assertRaises(SystemExit) as error:
            main(self._argv())
        self.assertEqual(error.exception.code, 1)

    @patch("scrape_fund_price.backfill_dividends")
    @patch("scrape_fund_price.read_distributions", return_value=[])
    @patch("scrape_fund_price.read_fund_specs", return_value=[])
    def test_the_report_reaches_the_actions_job_summary(
        self, _specs, _dists, mock_backfill
    ):
        """Test the rebuild is visible on the run page."""
        mock_backfill.return_value = self._report()
        path = self.path("step_summary.md")
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": path}):
            main(self._argv())
        written = self.read_text("step_summary.md")
        self.assertIn("Dividend rebuild from 2024-01-01", written)
        self.assertIn("QQQ", written)

    @patch("builtins.print")
    @patch("scrape_fund_price.backfill_dividends")
    def test_an_invalid_invocation_exits_with_two(self, mock_backfill, mock_print):
        """Test a bad --from date stops before any work."""
        with self.assertRaises(SystemExit) as error:
            main(self._argv(start="yesterday"))
        self.assertEqual(error.exception.code, 2)
        mock_backfill.assert_not_called()


# ===========================================================================
# Issuer pay-date sources
# ===========================================================================


def embedded(value):
    """Return JSON as the live page holds it: compact, entity-escaped."""
    return html.escape(json.dumps(value, separators=(",", ":")))


def ishares_page(rows, currency="GBP", product_id=1):
    """Build a page shaped like iShares UK's from (ex, record, pay, amount) rows.

    Dates are YYYYMMDD integers or None, exactly as the live page holds them,
    newest first; the data is entity-escaped inside attributes, as there.
    """

    def points(index, label):
        values = [row[index] for row in rows]
        return {"name": label, "value": values}

    table = {
        "name": "table",
        "fullName": "performance.distributions.table",
        "dataPointsByNameMap": {
            "exDate": points(0, "exDate"),
            "recordDate": points(1, "recordDate"),
            "payableDate": points(2, "payableDate"),
            "totalDistribution": points(3, "totalDistribution"),
        },
    }
    selector = {"currency": currency, "pId": product_id}
    return (
        "<html><body>"
        f'<div data-component="{embedded(table)}"></div>'
        f'<div data-selector="{embedded([selector])}"></div>'
        "</body></html>"
    )


def issuer_table(*rows, currency="GBP"):
    """Build an IssuerTable from (ex, record, pay, amount) rows, oldest first."""
    return scrape_fund_price.IssuerTable(
        currency,
        tuple(scrape_fund_price.IssuerDistribution(*row) for row in rows),
        "IS",
    )


def make_xlsx(rows, sheet_name="Open Fund", inline=False):
    """Build a minimal workbook of one sheet from rows of strings and numbers."""
    import io
    import zipfile

    def cell(row, column, value):
        ref = f"{'ABCDEFGHIJKL'[column]}{row}"
        if isinstance(value, (int, float)):
            return f'<c r="{ref}" t="n"><v>{value}</v></c>'
        if inline:
            return f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>'
        strings.append(value)
        return f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>'

    strings = []
    body = "".join(
        f'<row r="{n}">'
        + "".join(cell(n, c, v) for c, v in enumerate(row) if v is not None)
        + "</row>"
        for n, row in enumerate(rows, start=1)
    )
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    parts = {
        "xl/workbook.xml": (
            f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets>'
            f'<sheet name="{sheet_name}" sheetId="2" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
            'relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" '
            f'Type="{rel}/worksheet"/></Relationships>'
        ),
        "xl/worksheets/sheet1.xml": (
            f'<worksheet xmlns="{ns}"><sheetData>{body}</sheetData></worksheet>'
        ),
        "xl/sharedStrings.xml": (
            f'<sst xmlns="{ns}">'
            + "".join(f"<si><t>{s}</t></si>" for s in strings)
            + "</sst>"
        ),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in parts.items():
            archive.writestr(name, text)
    return buffer.getvalue()


class TestIsharesPageParsing(unittest.TestCase):
    """Test reading the distributions table of an iShares UK page (SPEC-011, #87)."""

    def _parse(self, text, product_id="251804"):
        return scrape_fund_price.parse_ishares_distributions(text, product_id)

    def test_the_recorded_igls_page(self):
        """Test the live page of iShares UK Gilts 0-5yr, newest last."""
        table = self._parse(fixture_text("ishares_251804_igls.html"))
        self.assertEqual(table.currency, "GBP")
        self.assertEqual(len(table.rows), 36)
        self.assertEqual(
            table.rows[-1],
            scrape_fund_price.IssuerDistribution(
                "2026-07-16", "2026-07-17", "2026-07-29", "2.4146"
            ),
        )
        self.assertEqual(
            table.rows[-2],
            scrape_fund_price.IssuerDistribution(
                "2026-01-15", "2026-01-16", "2026-01-28", "2.5662"
            ),
        )
        self.assertEqual(table.rows[0].ex_date, "2009-06-24")
        self.assertEqual(table.rows[0].amount, "0.6824")

    def test_the_recorded_flos_page(self):
        """Test a GBP-hedged class of a dollar fund, with a zero amount."""
        table = self._parse(fixture_text("ishares_290356_flos.html"), "290356")
        self.assertEqual(table.currency, "GBP")
        self.assertEqual(len(table.rows), 18)
        self.assertEqual(
            table.rows[-1],
            scrape_fund_price.IssuerDistribution(
                "2026-05-21", "2026-05-22", "2026-05-29", "0.0991"
            ),
        )
        self.assertEqual(table.rows[0].amount, "0.0")

    def test_the_share_class_currency_is_read_for_the_product(self):
        """Test another class's entry on the page is not taken."""
        page = ishares_page([(20260716, 20260717, 20260729, "1.5")], "USD", 7)
        self.assertEqual(self._parse(page, "7").currency, "USD")
        self.assertEqual(self._parse(page, "8").currency, "")

    def test_a_missing_pay_date_or_record_date_is_empty(self):
        """Test null cells are empty text."""
        page = ishares_page([(20260716, None, None, "1.5")])
        [row] = self._parse(page).rows
        self.assertEqual(row, ("2026-07-16", "", "", "1.5"))

    def test_a_pay_date_before_the_ex_date_is_not_trusted(self):
        """Test a pay date that cannot be right is dropped."""
        page = ishares_page([(20260716, 20260717, 20260715, "1.5")])
        self.assertEqual(self._parse(page).rows[0].pay_date, "")

    def test_a_pay_date_on_the_ex_date_is_kept(self):
        """Test same-day payment is allowed."""
        page = ishares_page([(20260716, 20260716, 20260716, "1.5")])
        self.assertEqual(self._parse(page).rows[0].pay_date, "2026-07-16")

    def test_a_page_with_no_table_is_an_error(self):
        """Test an accumulating class, or a changed page, is not an empty table."""
        with self.assertRaisesRegex(ValueError, "251804.*no distributions table"):
            self._parse("<html><body>nothing here</body></html>")

    def test_a_table_without_dates_is_an_error(self):
        """Test the lists must be there."""
        table = {
            "fullName": "performance.distributions.table",
            "dataPointsByNameMap": {},
        }
        page = f'<div data-x="{embedded(table)}"></div>'
        with self.assertRaisesRegex(ValueError, "251804.*no distributions table"):
            self._parse(page)

    def test_a_ragged_table_is_an_error(self):
        """Test lists of different lengths are refused rather than zipped."""
        table = {
            "fullName": "performance.distributions.table",
            "dataPointsByNameMap": {
                "exDate": {"value": [20260716, 20260115]},
                "recordDate": {"value": [20260717]},
                "payableDate": {"value": [20260729]},
                "totalDistribution": {"value": ["1.5"]},
            },
        }
        page = f'<div data-x="{embedded(table)}"></div>'
        with self.assertRaisesRegex(ValueError, "251804.*malformed"):
            self._parse(page)

    def test_a_bad_ex_date_is_an_error(self):
        """Test a date that is not one stops the page, not just the row."""
        for bad in (20261340, "x", 2026071, True):
            with self.subTest(bad=bad):
                page = ishares_page([(bad, 20260717, 20260729, "1.5")])
                with self.assertRaisesRegex(ValueError, "251804.*malformed date"):
                    self._parse(page)

    def test_a_missing_ex_date_is_an_error(self):
        """Test the ex-date is the row's key, so a null one stops the page."""
        page = ishares_page([(None, 20260717, 20260729, "1.5")])
        with self.assertRaisesRegex(ValueError, "251804.*missing date"):
            self._parse(page)

    def test_a_bad_record_or_pay_date_is_an_error(self):
        """Test a date that is not one is refused in any column, as the other issuers do."""
        for bad in (20261340, "x", 2026071, True):
            for column in (1, 2):
                row = [20260716, 20260717, 20260729, "1.5"]
                row[column] = bad
                with self.subTest(bad=bad, column=column):
                    page = ishares_page([tuple(row)])
                    with self.assertRaisesRegex(ValueError, "251804.*malformed"):
                        self._parse(page)

    def test_a_bad_amount_is_an_error(self):
        """Test the amount must be a decimal."""
        for bad in (None, "x", "", "-1.5", "NaN", "Infinity"):
            with self.subTest(bad=bad):
                page = ishares_page([(20260716, 20260717, 20260729, bad)])
                with self.assertRaisesRegex(ValueError, "251804.*malformed"):
                    self._parse(page)

    def test_an_empty_table_has_no_rows(self):
        """Test a new fund with no distribution yet."""
        self.assertEqual(self._parse(ishares_page([])).rows, ())


class TestIsharesPageFetch(unittest.TestCase):
    """Test the one request per instrument (SPEC-011, #87)."""

    @patch("scrape_fund_price.requests.get")
    def test_one_get_of_the_product_page(self, mock_get):
        """Test the url carries the product id and the call has a timeout."""
        response = MagicMock(text=ishares_page([(20260716, 20260717, 20260729, "2.5")]))
        mock_get.return_value = response
        table = scrape_fund_price.fetch_ishares_distributions("251804")
        mock_get.assert_called_once()
        self.assertEqual(
            mock_get.call_args.args[0],
            "https://www.ishares.com/uk/individual/en/products/251804",
        )
        self.assertEqual(mock_get.call_args.kwargs["timeout"], 30)
        response.raise_for_status.assert_called_once()
        self.assertEqual(table.rows[0].amount, "2.5")

    @patch("scrape_fund_price.requests.get")
    def test_an_http_error_propagates_for_the_retry(self, mock_get):
        """Test a status error is raised, not swallowed."""
        mock_get.return_value.raise_for_status.side_effect = (
            scrape_fund_price.requests.HTTPError("503")
        )
        with self.assertRaises(scrape_fund_price.requests.HTTPError):
            scrape_fund_price.fetch_ishares_distributions("251804")

    def test_the_dispatcher_calls_the_source_for_its_code(self):
        """Test fetch_issuer_table routes IS to the iShares fetch."""
        source = scrape_fund_price.DividendSource("IGLS.L", "IS", "251804")
        with patch.object(
            scrape_fund_price, "fetch_ishares_distributions", return_value="table"
        ) as fetch:
            self.assertEqual(scrape_fund_price.fetch_issuer_table(source), "table")
        fetch.assert_called_once_with("251804")


class TestInvescoParsing(unittest.TestCase):
    """Test reading Invesco's distribution API (IV, SPEC-012, #89)."""

    def _parse(self, text, cusip="46090E103"):
        return scrape_fund_price.parse_invesco_distributions(text, cusip)

    @staticmethod
    def _payload(rows, currency="USD"):
        return json.dumps(
            {"cusip": "X", "currencyCode": currency, "distributions": rows}
        )

    @staticmethod
    def _row(ex="2026-09-21", record="2026-09-21", pay="2026-10-08", amount=0.75143):
        return {
            "exDate": ex,
            "recordDate": record,
            "payDate": pay,
            "distributionAmountPerUnit": amount,
        }

    def test_the_recorded_qqq_response(self):
        """Test the real response: oldest first, newest with its pay date."""
        table = self._parse(fixture_text("invesco_46090E103_qqq.json"))
        self.assertEqual(table.source, "IV")
        self.assertEqual(table.currency, "USD")
        self.assertEqual(len(table.rows), 89)
        self.assertEqual(table.rows[0].ex_date, "2003-12-24")
        self.assertEqual(
            table.rows[-1],
            scrape_fund_price.IssuerDistribution(
                "2026-09-21", "2026-09-21", "2026-10-08", "0.75143"
            ),
        )
        self.assertEqual(
            [r.ex_date for r in table.rows], sorted(r.ex_date for r in table.rows)
        )

    def test_a_missing_pay_date_is_empty_and_one_before_the_ex_date_too(self):
        """Test the SPEC-011 rule: no pay date, or one before the ex-date, is absent."""
        text = self._payload(
            [
                self._row("2026-01-05", pay=None),
                self._row("2026-04-06", pay="2026-04-01"),
            ]
        )
        self.assertEqual([r.pay_date for r in self._parse(text).rows], ["", ""])

    def test_two_cash_rows_on_one_ex_date_are_one_distribution(self):
        """Test the history is keyed on the ex-date, so the amounts add."""
        text = self._payload(
            [
                self._row("2026-03-02", pay="2026-03-10", amount=0.5),
                self._row("2026-03-02", pay="2026-03-12", amount=0.25),
            ]
        )
        [row] = self._parse(text).rows
        self.assertEqual((row.pay_date, row.amount), ("2026-03-12", "0.75"))

    def test_no_table_is_an_error(self):
        """Test a changed response is an error for the instrument."""
        for text in ("not json", "[]", "{}", '{"distributions": {}}'):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "Invesco"):
                    self._parse(text)

    def test_malformed_rows_are_errors(self):
        """Test a bad date or amount never becomes a row."""
        bad = [
            self._row(ex="21/09/2026"),
            self._row(ex=None),
            self._row(amount="x"),
            self._row(amount=None),
            self._row(amount=-1),
            self._row(pay="soon"),
            "text",
        ]
        for row in bad:
            with self.subTest(row=row):
                with self.assertRaisesRegex(ValueError, "Invesco"):
                    self._parse(self._payload([row]))

    def test_an_empty_list_is_an_empty_table(self):
        """Test a fund with no distributions yet."""
        self.assertEqual(self._parse(self._payload([])).rows, ())

    def test_the_currency_may_be_absent(self):
        """Test the row's currency then decides, as for iShares."""
        self.assertEqual(self._parse(self._payload([], currency=None)).currency, "")


class TestInvescoFetch(unittest.TestCase):
    """Test the one request per instrument for IV (SPEC-012, #89)."""

    @patch("scrape_fund_price.requests.get")
    def test_one_get_of_the_distribution_endpoint(self, mock_get):
        """Test the url carries the CUSIP and the call has a timeout."""
        response = MagicMock(text=fixture_text("invesco_46090E103_qqq.json"))
        mock_get.return_value = response
        table = scrape_fund_price.fetch_invesco_distributions("46090E103")
        mock_get.assert_called_once()
        self.assertEqual(
            mock_get.call_args.args[0],
            "https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/"
            "46090E103/distribution?idType=cusip&productType=ETF",
        )
        self.assertEqual(mock_get.call_args.kwargs["timeout"], 30)
        response.raise_for_status.assert_called_once()
        self.assertEqual(table.rows[-1].pay_date, "2026-10-08")

    @patch("scrape_fund_price.requests.get")
    def test_an_http_error_propagates_for_the_retry(self, mock_get):
        """Test a status error is raised, not swallowed."""
        mock_get.return_value.raise_for_status.side_effect = (
            scrape_fund_price.requests.HTTPError("503")
        )
        with self.assertRaises(scrape_fund_price.requests.HTTPError):
            scrape_fund_price.fetch_invesco_distributions("46090E103")


class TestQ4Parsing(unittest.TestCase):
    """Test reading a Q4 Inc investor-relations dividend feed (Q4, SPEC-012, #89)."""

    def _parse(self, text, symbol="KNSL"):
        return scrape_fund_price.parse_q4_distributions(text, symbol)

    @staticmethod
    def _payload(rows):
        return json.dumps({"GetDividendListResult": rows})

    @staticmethod
    def _row(ex="08/28/2026", record="08/28/2026", pay="09/14/2026", amount=0.25):
        def stamp(value):
            return None if value is None else f"{value} 00:00:00"

        return {
            "Currency": "USD",
            "DeclaredDate": "08/12/2026 00:00:00",
            "DividendAmount": amount,
            "ExDate": stamp(ex),
            "PayDate": stamp(pay),
            "RecordDate": stamp(record),
            "Type": "OrdinaryDividend",
        }

    def test_the_recorded_knsl_response(self):
        """Test the real response: oldest first, newest with its pay date."""
        table = self._parse(fixture_text("q4_knsl_dividends.json"))
        self.assertEqual(table.source, "Q4")
        self.assertEqual(table.currency, "USD")
        self.assertEqual(len(table.rows), 41)
        self.assertEqual(
            table.rows[-1],
            scrape_fund_price.IssuerDistribution(
                "2026-08-28", "2026-08-28", "2026-09-14", "0.25"
            ),
        )
        self.assertEqual(table.rows[0].ex_date, "2016-09-13")

    def test_rows_are_sorted_by_ex_date(self):
        """Test the order does not depend on the feed's."""
        text = self._payload([self._row("08/28/2026"), self._row("05/28/2026")])
        self.assertEqual(
            [r.ex_date for r in self._parse(text).rows], ["2026-05-28", "2026-08-28"]
        )

    def test_a_missing_pay_date_is_empty(self):
        """Test a declared dividend whose pay date is not set."""
        [row] = self._parse(self._payload([self._row(pay=None)])).rows
        self.assertEqual(row.pay_date, "")

    def test_mixed_currencies_are_an_error(self):
        """Test a table is in one currency."""
        other = dict(self._row("05/28/2026"), Currency="CAD")
        with self.assertRaisesRegex(ValueError, "Q4.*currenc"):
            self._parse(self._payload([self._row(), other]))

    def test_a_changed_response_is_an_error(self):
        """Test the shape check."""
        bad = [
            "not json",
            "{}",
            '{"GetDividendListResult": null}',
            self._payload([self._row(ex="2026-08-28")]),
            self._payload([self._row(amount="n/a")]),
            self._payload([self._row(amount=-1)]),
            self._payload([self._row(ex=None)]),
            self._payload(["x"]),
        ]
        for text in bad:
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "Q4"):
                    self._parse(text)

    def test_an_empty_list_is_an_empty_table(self):
        """Test a company with no dividends."""
        table = self._parse(self._payload([]))
        self.assertEqual((table.rows, table.currency), ((), ""))


class TestQ4Fetch(unittest.TestCase):
    """Test the one request per instrument for Q4 (SPEC-012, #89)."""

    @patch("scrape_fund_price.requests.get")
    def test_one_get_of_the_feed(self, mock_get):
        """Test the url is built from the host/MIC and the symbol."""
        response = MagicMock(text=fixture_text("q4_knsl_dividends.json"))
        mock_get.return_value = response
        table = scrape_fund_price.fetch_q4_distributions(
            "ir.kinsalecapitalgroup.com/XNYS", "KNSL"
        )
        mock_get.assert_called_once()
        self.assertEqual(
            mock_get.call_args.args[0],
            "https://ir.kinsalecapitalgroup.com/feed/StockQuote.svc/"
            "GetDividendList?exchange=XNYS&symbol=KNSL&pageSize=-1",
        )
        self.assertEqual(mock_get.call_args.kwargs["timeout"], 30)
        response.raise_for_status.assert_called_once()
        self.assertEqual(table.rows[-1].pay_date, "2026-09-14")

    @patch("scrape_fund_price.requests.get")
    def test_the_symbol_is_url_encoded(self, mock_get):
        """Test an identifier with a punctuation mark cannot change the query."""
        response = MagicMock(text='{"GetDividendListResult": []}')
        mock_get.return_value = response
        scrape_fund_price.fetch_q4_distributions("ir.x.com/XNYS", "A&B")
        self.assertIn("symbol=A%26B&", mock_get.call_args.args[0])

    @patch("scrape_fund_price.requests.get")
    def test_an_http_error_propagates_for_the_retry(self, mock_get):
        """Test a status error is raised, not swallowed."""
        mock_get.return_value.raise_for_status.side_effect = (
            scrape_fund_price.requests.HTTPError("503")
        )
        with self.assertRaises(scrape_fund_price.requests.HTTPError):
            scrape_fund_price.fetch_q4_distributions("ir.x.com/XNYS", "KNSL")


class TestEtnetParsing(unittest.TestCase):
    """Test reading etnet's dividend records (ET, SPEC-012, #89)."""

    def _parse(self, text, code="639"):
        return scrape_fund_price.parse_etnet_distributions(text, code)

    @staticmethod
    def _page(*rows):
        """Build a page like etnet's from (announced, particular, ex, pay) rows."""

        def line(announced, particular, ex, pay):
            cells = [announced, "2026/12", particular, ex, ex, "--", pay]
            return (
                '<tr class="evenRow" align="right">'
                + "".join(f'<td align="left">{cell}</td>' for cell in cells)
                + "</tr>"
            )

        return (
            '<table class="figureTable"><tr>'
            '<td><span class="TableHeader">Announcement Date</span></td>'
            '<td><span class="TableHeader">Payable Date</span></td></tr>'
            + "".join(line(*row) for row in rows)
            + "</table>"
        )

    def test_the_recorded_shougang_page(self):
        """Test the real page: cash dividends only, oldest first."""
        table = self._parse(fixture_text("etnet_639_dividends.html"))
        self.assertEqual(table.source, "ET")
        self.assertEqual(table.currency, "HKD")
        self.assertEqual(
            table.rows[-1],
            scrape_fund_price.IssuerDistribution("2026-09-18", "", "2026-11-05", "0.1"),
        )
        self.assertEqual(
            [r.ex_date for r in table.rows], sorted(r.ex_date for r in table.rows)
        )
        self.assertNotIn("2024-10-10", [r.ex_date for r in table.rows])

    def test_the_rights_issue_is_not_a_dividend(self):
        """Test the Rts row (ex 2024-10-10) is skipped, its neighbours kept."""
        table = self._parse(fixture_text("etnet_639_dividends.html"))
        ex_dates = [r.ex_date for r in table.rows]
        self.assertIn("2024-10-03", ex_dates)
        self.assertIn("2024-06-07", ex_dates)
        self.assertNotIn("2024-10-10", ex_dates)

    def test_a_special_and_a_final_dividend_on_one_ex_date_add_up(self):
        """Test 2018-06-04: Fin 0.072 and Sp 0.063 are one entitlement date."""
        table = self._parse(fixture_text("etnet_639_dividends.html"))
        [row] = [r for r in table.rows if r.ex_date == "2018-05-31"]
        self.assertEqual((row.pay_date, row.amount), ("2018-07-12", "0.135"))

    def test_no_dividend_rows_are_skipped(self):
        """Test the 'No Int Div' placeholders carry no dates."""
        text = self._page(
            ("--", "No Int Div", "--", "--"),
            ("27/08/2026", "Int Div HKD 0.1", "18/09/2026", "05/11/2026"),
        )
        self.assertEqual([r.ex_date for r in self._parse(text).rows], ["2026-09-18"])

    def test_a_missing_pay_date_is_empty(self):
        """Test an announced dividend whose payable date is not yet set."""
        text = self._page(("27/08/2026", "Int Div HKD 0.1", "18/09/2026", "--"))
        [row] = self._parse(text).rows
        self.assertEqual(row.pay_date, "")

    def test_a_page_with_no_cash_dividend_is_an_empty_table(self):
        """Test a listed company that has never paid."""
        table = self._parse(self._page(("--", "No Fin Div", "--", "--")))
        self.assertEqual((table.rows, table.currency), ((), ""))

    def test_a_changed_page_is_an_error(self):
        """Test a page without the dividend table, or with bad cells."""
        bad = [
            "<html>no table</html>",
            self._page(("27/08/2026", "Int Div HKD 0.1", "2026-09-18", "05/11/2026")),
            self._page(("27/08/2026", "Int Div HKD 0.1", "31/02/2026", "05/11/2026")),
            self._page(("27/08/2026", "Int Div HKD 0.1", "18/09/2026", "soon")),
            self._page(
                ("27/08/2026", "Int Div HKD 0.1", "18/09/2026", "05/11/2026")
            ).replace('<td align="left">2026/12</td>', ""),
        ]
        for text in bad:
            with self.subTest(text=text[:60]):
                with self.assertRaisesRegex(ValueError, "etnet"):
                    self._parse(text)

    def test_mixed_currencies_are_an_error(self):
        """Test a table is in one currency."""
        text = self._page(
            ("27/08/2026", "Int Div HKD 0.1", "18/09/2026", "05/11/2026"),
            ("27/03/2026", "Fin Div USD 0.1", "08/07/2026", "23/07/2026"),
        )
        with self.assertRaisesRegex(ValueError, "etnet.*currenc"):
            self._parse(text)


class TestEtnetFetch(unittest.TestCase):
    """Test the one request per instrument for ET (SPEC-012, #89)."""

    @patch("scrape_fund_price.requests.get")
    def test_one_get_of_the_dividend_page(self, mock_get):
        """Test the url carries the HK code and the call has a timeout."""
        response = MagicMock(text=fixture_text("etnet_639_dividends.html"))
        mock_get.return_value = response
        table = scrape_fund_price.fetch_etnet_distributions("639")
        mock_get.assert_called_once()
        self.assertEqual(
            mock_get.call_args.args[0],
            "https://www.etnet.com.hk/www/eng/stocks/realtime/"
            "quote_dividend.php?code=639",
        )
        self.assertEqual(mock_get.call_args.kwargs["timeout"], 30)
        response.raise_for_status.assert_called_once()
        self.assertEqual(table.rows[-1].pay_date, "2026-11-05")

    @patch("scrape_fund_price.requests.get")
    def test_an_http_error_propagates_for_the_retry(self, mock_get):
        """Test a status error is raised, not swallowed."""
        mock_get.return_value.raise_for_status.side_effect = (
            scrape_fund_price.requests.HTTPError("503")
        )
        with self.assertRaises(scrape_fund_price.requests.HTTPError):
            scrape_fund_price.fetch_etnet_distributions("639")


class TestSsgaParsing(unittest.TestCase):
    """Test reading SSGA's historical-distributions workbook (SS, SPEC-012, #89)."""

    HEADER = [
        "FUND UMBRELLA",
        "FUND NAME",
        "TICKER",
        "ISIN",
        "CURRENCY",
        "Announcement Date",
        "EX-DATE",
        "EX-DATE NAV",
        "RECORD DATE",
        "PAYMENT DATE",
        "DISTRIBUTION",
        "FREQUENCY",
    ]

    @classmethod
    def _line(
        cls,
        isin="IE00B6YX5L24",
        ex="03/08/2026",
        record="04/08/2026",
        pay="17/08/2026",
        amount="0.8811",
        currency="GBP",
    ):
        return [
            "U",
            "N",
            "T",
            isin,
            currency,
            "27/07/2026",
            ex,
            32.8802,
            record,
            pay,
            amount,
            "Semi-Annually",
        ]

    def _parse(self, content, isin="IE00B6YX5L24"):
        return scrape_fund_price.parse_ssga_distributions(content, isin)

    def test_the_recorded_workbook(self):
        """Test the real workbook: GLTL.L's fund, oldest first."""
        table = self._parse(fixture_bytes("ssga_historical_distributions.xlsx"))
        self.assertEqual(table.source, "SS")
        self.assertEqual(table.currency, "GBP")
        self.assertEqual(
            table.rows[-1],
            scrape_fund_price.IssuerDistribution(
                "2026-08-03", "2026-08-04", "2026-08-17", "0.8811"
            ),
        )
        self.assertEqual(
            [r.ex_date for r in table.rows], sorted(r.ex_date for r in table.rows)
        )
        self.assertEqual(len({r.ex_date for r in table.rows}), len(table.rows))

    def test_only_the_funds_own_rows_are_read(self):
        """Test the other funds of the workbook are ignored."""
        content = make_xlsx(
            [
                self.HEADER,
                self._line(isin="IE00OTHER000", amount="9"),
                self._line(),
            ]
        )
        [row] = self._parse(content).rows
        self.assertEqual(row.amount, "0.8811")

    def test_inline_strings_and_numeric_cells_are_read(self):
        """Test a workbook written without a shared-strings table."""
        line = self._line(amount=0.8811)
        content = make_xlsx([self.HEADER, line], inline=True)
        [row] = self._parse(content).rows
        self.assertEqual(row.amount, "0.8811")

    def test_the_columns_are_found_by_header_not_by_position(self):
        """Test a reordered workbook still reads."""
        order = [3, 4, 6, 8, 9, 10]
        header = [self.HEADER[i] for i in order]
        line = [self._line()[i] for i in order]
        [row] = self._parse(make_xlsx([header, line])).rows
        self.assertEqual((row.ex_date, row.pay_date), ("2026-08-03", "2026-08-17"))

    def test_a_missing_pay_date_is_empty(self):
        """Test an announced distribution whose payment date is blank."""
        content = make_xlsx([self.HEADER, self._line(pay=None)])
        [row] = self._parse(content).rows
        self.assertEqual(row.pay_date, "")

    def test_a_fund_with_no_rows_is_an_error(self):
        """Test a wrong ISIN or a changed workbook is not an empty table."""
        with self.assertRaisesRegex(ValueError, "SSGA.*IE00B6YX5L24"):
            self._parse(make_xlsx([self.HEADER, self._line(isin="IE00OTHER000")]))

    def test_a_changed_workbook_is_an_error(self):
        """Test the shape checks."""
        bad = {
            "not a workbook": b"<html>moved</html>",
            "no header": make_xlsx([["a", "b"], ["c", "d"]]),
            "bad ex-date": make_xlsx([self.HEADER, self._line(ex="2026-08-03")]),
            "bad pay date": make_xlsx([self.HEADER, self._line(pay="soon")]),
            "bad amount": make_xlsx([self.HEADER, self._line(amount="n/a")]),
            "negative": make_xlsx([self.HEADER, self._line(amount="-1")]),
            "mixed currency": make_xlsx(
                [self.HEADER, self._line(), self._line(ex="02/02/2026", currency="USD")]
            ),
        }
        for name, content in bad.items():
            with self.subTest(name):
                with self.assertRaisesRegex(ValueError, "SSGA"):
                    self._parse(content)

    def test_the_first_sheet_is_the_open_funds(self):
        """Test the sheet is resolved from the workbook, not assumed by name."""
        content = make_xlsx([self.HEADER, self._line()], sheet_name="Anything")
        self.assertEqual(len(self._parse(content).rows), 1)


class TestSsgaFetch(unittest.TestCase):
    """Test the one download per run for SS (SPEC-012, #89)."""

    URL = (
        "https://www.ssga.com/library-content/products/fund-data/etfs/emea/"
        "spdr-etf-historical-distributions-uk-en.xlsx"
    )

    def setUp(self):
        scrape_fund_price.clear_issuer_caches()

    def tearDown(self):
        scrape_fund_price.clear_issuer_caches()

    @patch("scrape_fund_price.requests.get")
    def test_one_get_of_the_workbook(self, mock_get):
        """Test the url, the timeout and the parsed table."""
        response = MagicMock(
            content=fixture_bytes("ssga_historical_distributions.xlsx")
        )
        mock_get.return_value = response
        table = scrape_fund_price.fetch_ssga_distributions("IE00B6YX5L24")
        mock_get.assert_called_once()
        self.assertEqual(mock_get.call_args.args[0], self.URL)
        self.assertEqual(mock_get.call_args.kwargs["timeout"], 60)
        response.raise_for_status.assert_called_once()
        self.assertEqual(table.rows[-1].pay_date, "2026-08-17")

    @patch("scrape_fund_price.requests.get")
    def test_a_second_instrument_reuses_the_download(self, mock_get):
        """Test one workbook serves every SPDR fund of the run."""
        content = make_xlsx(
            [
                TestSsgaParsing.HEADER,
                TestSsgaParsing._line(),
                TestSsgaParsing._line(isin="IE00OTHER000", amount="2"),
            ]
        )
        response = MagicMock(content=content)
        mock_get.return_value = response
        first = scrape_fund_price.fetch_ssga_distributions("IE00B6YX5L24")
        second = scrape_fund_price.fetch_ssga_distributions("IE00OTHER000")
        mock_get.assert_called_once()
        self.assertEqual(first.rows[0].amount, "0.8811")
        self.assertEqual(second.rows[0].amount, "2")

    @patch("scrape_fund_price.requests.get")
    def test_clearing_the_cache_downloads_again(self, mock_get):
        """Test a new run does not reuse yesterday's workbook."""
        response = MagicMock(
            content=fixture_bytes("ssga_historical_distributions.xlsx")
        )
        mock_get.return_value = response
        scrape_fund_price.fetch_ssga_distributions("IE00B6YX5L24")
        scrape_fund_price.clear_issuer_caches()
        scrape_fund_price.fetch_ssga_distributions("IE00B6YX5L24")
        self.assertEqual(mock_get.call_count, 2)

    @patch("scrape_fund_price.requests.get")
    def test_a_failed_download_is_not_cached(self, mock_get):
        """Test the retry fetches again."""
        mock_get.return_value.raise_for_status.side_effect = (
            scrape_fund_price.requests.HTTPError("404")
        )
        with self.assertRaises(scrape_fund_price.requests.HTTPError):
            scrape_fund_price.fetch_ssga_distributions("IE00B6YX5L24")
        mock_get.return_value = MagicMock(
            content=fixture_bytes("ssga_historical_distributions.xlsx")
        )
        table = scrape_fund_price.fetch_ssga_distributions("IE00B6YX5L24")
        self.assertTrue(table.rows)


class TestIssuerDispatch(unittest.TestCase):
    """Test fetch_issuer_table routes each code to its fetch (SPEC-012, #89)."""

    def test_each_code_calls_its_fetch(self):
        """Test the arguments each source needs."""
        cases = [
            (("QQQ", "IV", "46090E103"), "fetch_invesco_distributions", ("46090E103",)),
            (
                ("GLTL.L", "SS", "IE00B6YX5L24"),
                "fetch_ssga_distributions",
                ("IE00B6YX5L24",),
            ),
            (
                ("KNSL", "Q4", "ir.kinsalecapitalgroup.com/XNYS"),
                "fetch_q4_distributions",
                ("ir.kinsalecapitalgroup.com/XNYS", "KNSL"),
            ),
            (("0639.HK", "ET", "639"), "fetch_etnet_distributions", ("639",)),
        ]
        for line, name, args in cases:
            with self.subTest(source=line[1]):
                source = scrape_fund_price.DividendSource(*line)
                with patch.object(
                    scrape_fund_price, name, return_value="table"
                ) as fetch:
                    result = scrape_fund_price.fetch_issuer_table(source)
                self.assertEqual(result, "table")
                fetch.assert_called_once_with(*args)

    def test_an_unknown_code_is_an_error(self):
        """Test a code with no fetch fails loudly rather than as iShares."""
        source = scrape_fund_price.DividendSource("X", "ZZ", "1")
        with self.assertRaisesRegex(ValueError, "ZZ"):
            scrape_fund_price.fetch_issuer_table(source)

    def test_the_codes_are_the_fetchers(self):
        """Test DIVIDEND_SOURCE_CODES is derived from ISSUER_FETCHERS, so neither drifts."""
        self.assertEqual(
            scrape_fund_price.DIVIDEND_SOURCE_CODES,
            tuple(scrape_fund_price.ISSUER_FETCHERS),
        )
        self.assertEqual(
            set(scrape_fund_price.DIVIDEND_SOURCE_CODES),
            set(scrape_fund_price.DIVIDEND_SOURCE_ID_RULES),
        )


class TestIssuerAmounts(unittest.TestCase):
    """Test the issuer's amount in the stored row's currency (SPEC-011, #87)."""

    def _convert(self, text, class_currency, target):
        return scrape_fund_price.issuer_amount(text, class_currency, target)

    def test_an_equal_currency_is_unchanged(self):
        """Test GBP for a GBP row."""
        amount = self._convert("2.4146", "GBP", "GBP")
        self.assertEqual((amount.text, amount.currency), ("2.4146", "GBP"))

    def test_pounds_become_pence_for_a_pence_row(self):
        """Test the factor of 100 and the rounding it brings."""
        amount = self._convert("0.0991", "GBP", "GBp")
        self.assertEqual((amount.text, amount.currency), ("9.91", "GBp"))
        self.assertEqual(amount.tolerance, decimal.Decimal("0.005"))
        self.assertEqual(self._convert("0.1", "GBP", "GBp").text, "10")

    def test_a_page_that_names_no_currency_is_taken_in_the_row_currency(self):
        """Test the shipped pages without a share-class entry."""
        self.assertEqual(self._convert("1.5", "", "USD").currency, "USD")
        self.assertEqual(self._convert("0.015", "", "GBp").text, "1.5")

    def test_no_target_currency_takes_the_issuers(self):
        """Test an instrument with no stored currency."""
        amount = self._convert("1.5", "USD", "")
        self.assertEqual((amount.text, amount.currency), ("1.5", "USD"))

    def test_different_currencies_cannot_be_compared(self):
        """Test USD against GBP is no amount."""
        self.assertIsNone(self._convert("1.5", "USD", "GBP"))
        self.assertIsNone(self._convert("1.5", "USD", "GBp"))

    def test_zero_is_no_amount(self):
        """Test the 0.0 rows the issuer lists for a fund's first, empty period."""
        self.assertIsNone(self._convert("0.0", "GBP", "GBP"))

    def test_the_tolerance_is_half_the_last_decimal_place(self):
        """Test agreement means equal within the issuer's rounding."""
        amount = self._convert("0.0128", "GBP", "GBp")
        self.assertTrue(scrape_fund_price.amounts_agree("1.2841", amount))
        self.assertTrue(scrape_fund_price.amounts_agree("1.28", amount))
        self.assertFalse(scrape_fund_price.amounts_agree("1.29", amount))
        self.assertFalse(scrape_fund_price.amounts_agree("x", amount))


class TestApplyIssuerTable(unittest.TestCase):
    """Test merging an issuer's table into the history (SPEC-011, #87)."""

    TODAY = date(2026, 10, 26)

    def _apply(self, history, table, currency="GBP", identifier="IGLS.L", start=None):
        return scrape_fund_price.apply_issuer_table(
            history, identifier, table, currency, self.TODAY, start
        )

    @staticmethod
    def _keyed(*rows):
        return {(row[0], row[1]): list(row) for row in rows}

    def test_a_yahoo_row_gains_its_pay_date(self):
        """Test the point of the spec."""
        history = self._keyed(["IGLS.L", "2026-07-16", "", "2.4146", "GBP", "YA"])
        written = self._apply(
            history, issuer_table(("2026-07-16", "2026-07-17", "2026-07-29", "2.4146"))
        )
        self.assertEqual(written, 1)
        self.assertEqual(
            history[("IGLS.L", "2026-07-16")],
            ["IGLS.L", "2026-07-16", "2026-07-29", "2.4146", "GBP", "IS"],
        )

    def test_yahoos_amount_is_kept_when_they_agree(self):
        """Test the more precise figure stays."""
        history = self._keyed(["IWDG.L", "2017-07-13", "", "1.2841", "GBp", "YA"])
        self._apply(
            history,
            issuer_table(("2017-07-13", "", "2017-07-27", "0.0128")),
            identifier="IWDG.L",
        )
        self.assertEqual(
            history[("IWDG.L", "2017-07-13")],
            ["IWDG.L", "2017-07-13", "2017-07-27", "1.2841", "GBp", "IS"],
        )

    def test_the_issuers_amount_wins_when_they_differ(self):
        """Test IWDG.L 2020-01-16: Yahoo 1.77p, the issuer 1.75p."""
        history = self._keyed(["IWDG.L", "2020-01-16", "", "1.77", "GBp", "YA"])
        self._apply(
            history,
            issuer_table(("2020-01-16", "", "2020-01-30", "0.0175")),
            identifier="IWDG.L",
        )
        self.assertEqual(history[("IWDG.L", "2020-01-16")][3], "1.75")
        self.assertEqual(history[("IWDG.L", "2020-01-16")][4], "GBp")

    def test_an_amount_in_another_currency_is_left_alone(self):
        """Test the dates are taken and the figure that cannot be compared stays."""
        history = self._keyed(["X", "2026-07-16", "", "2.4", "USD", "YA"])
        self._apply(
            history,
            issuer_table(("2026-07-16", "", "2026-07-29", "1.9")),
            identifier="X",
        )
        self.assertEqual(
            history[("X", "2026-07-16")],
            ["X", "2026-07-16", "2026-07-29", "2.4", "USD", "IS"],
        )

    def test_a_zero_issuer_amount_leaves_the_stored_amount(self):
        """Test IDTG.L 2019-12-12: Yahoo 0.0037, the issuer 0.0."""
        history = self._keyed(["IDTG.L", "2019-12-12", "", "0.0037", "GBP", "YA"])
        self._apply(
            history,
            issuer_table(("2019-12-12", "", "2019-12-30", "0.0")),
            identifier="IDTG.L",
        )
        self.assertEqual(history[("IDTG.L", "2019-12-12")][3], "0.0037")

    def test_a_blank_pay_date_keeps_the_stored_one(self):
        """Test the issuer cannot take a date away."""
        history = self._keyed(
            ["IGLS.L", "2026-07-16", "2026-07-30", "2.4146", "GBP", "YA"]
        )
        self._apply(history, issuer_table(("2026-07-16", "", "", "2.4146")))
        self.assertEqual(history[("IGLS.L", "2026-07-16")][2], "2026-07-30")

    def test_a_row_yahoo_lacks_is_inserted_in_the_price_currency(self):
        """Test the gaps in Yahoo's history (INXG.L lacks 18)."""
        history = {}
        self._apply(
            history,
            issuer_table(("2026-05-21", "2026-05-22", "2026-05-29", "0.0991")),
            currency="GBp",
            identifier="FLOS.L",
        )
        self.assertEqual(
            history[("FLOS.L", "2026-05-21")],
            ["FLOS.L", "2026-05-21", "2026-05-29", "9.91", "GBp", "IS"],
        )

    def test_an_inserted_row_without_a_price_currency_takes_the_issuers(self):
        """Test an instrument with no stored price."""
        history = {}
        self._apply(
            history,
            issuer_table(("2026-05-21", "", "2026-05-29", "0.5"), currency="USD"),
            currency="",
        )
        self.assertEqual(history[("IGLS.L", "2026-05-21")][3:5], ["0.5", "USD"])

    def test_nothing_is_inserted_without_a_usable_amount(self):
        """Test a zero, or an amount that cannot be put in the currency."""
        history = {}
        self._apply(history, issuer_table(("2017-11-16", "", "2017-11-30", "0.0")))
        self._apply(
            history,
            issuer_table(("2026-05-21", "", "2026-05-29", "0.5"), currency="USD"),
        )
        self.assertEqual(history, {})

    def test_a_blank_stored_currency_is_filled(self):
        """Test Yahoo gave none."""
        history = self._keyed(["IGLS.L", "2026-07-16", "", "2.4146", "", "YA"])
        self._apply(history, issuer_table(("2026-07-16", "", "2026-07-29", "2.4146")))
        self.assertEqual(history[("IGLS.L", "2026-07-16")][4], "GBP")

    def test_a_date_a_day_out_is_one_dividend(self):
        """Test FLOS.L and IUAG.L 2021: Yahoo 11-12, the issuer 11-11."""
        history = self._keyed(["FLOS.L", "2021-11-12", "", "7.1", "GBp", "YA"])
        written = self._apply(
            history,
            issuer_table(("2021-11-11", "2021-11-12", "2021-11-25", "0.071")),
            identifier="FLOS.L",
        )
        self.assertEqual(written, 2)  # the new row, and the twin removed
        self.assertEqual(
            history,
            self._keyed(["FLOS.L", "2021-11-11", "2021-11-25", "7.1", "GBp", "IS"]),
        )

    def test_a_twin_is_removed_beside_an_exact_match(self):
        """Test the YA twin Yahoo's window would re-insert every day."""
        history = self._keyed(
            ["FLOS.L", "2021-11-11", "2021-11-25", "7.1", "GBp", "IS"],
            ["FLOS.L", "2021-11-12", "", "7.1", "GBp", "YA"],
        )
        self._apply(
            history,
            issuer_table(("2021-11-11", "", "2021-11-25", "0.071")),
            identifier="FLOS.L",
        )
        self.assertEqual(list(history), [("FLOS.L", "2021-11-11")])

    def test_a_near_row_with_another_amount_is_a_different_dividend(self):
        """Test a special dividend two days away stays."""
        history = self._keyed(["IGLS.L", "2026-07-18", "", "9.9", "GBP", "YA"])
        self._apply(history, issuer_table(("2026-07-16", "", "2026-07-29", "2.4146")))
        self.assertIn(("IGLS.L", "2026-07-18"), history)
        self.assertIn(("IGLS.L", "2026-07-16"), history)

    def test_a_near_row_that_is_itself_an_issuer_date_stays(self):
        """Test a monthly payer's neighbours are not twins."""
        history = self._keyed(["X", "2026-06-02", "", "1.0", "GBP", "YA"])
        self._apply(
            history,
            issuer_table(
                ("2026-06-02", "", "2026-06-20", "1.0"),
                ("2026-06-04", "", "2026-06-22", "1.0"),
            ),
            identifier="X",
        )
        self.assertEqual(sorted(ex for _, ex in history), ["2026-06-02", "2026-06-04"])

    def test_another_funds_and_other_sources_rows_are_not_twins(self):
        """Test only this fund's Yahoo rows are candidates."""
        history = self._keyed(
            ["OTHER", "2026-07-17", "", "2.4146", "GBP", "YA"],
            ["IGLS.L", "2026-07-17", "2026-07-30", "2.4146", "GBP", "config"],
        )
        self._apply(history, issuer_table(("2026-07-16", "", "2026-07-29", "2.4146")))
        self.assertIn(("OTHER", "2026-07-17"), history)
        self.assertIn(("IGLS.L", "2026-07-17"), history)

    def test_a_config_row_on_the_same_date_gives_way(self):
        """Test the issuer beats the owner's schedule."""
        history = self._keyed(
            ["IGLS.L", "2026-07-16", "2026-07-30", "2.4", "GBP", "config"]
        )
        self._apply(history, issuer_table(("2026-07-16", "", "2026-07-29", "2.4146")))
        self.assertEqual(
            history[("IGLS.L", "2026-07-16")],
            ["IGLS.L", "2026-07-16", "2026-07-29", "2.4146", "GBP", "IS"],
        )

    def test_future_rows_are_not_history(self):
        """Test a declared dividend belongs to the upcoming file."""
        history = {}
        written = self._apply(
            history, issuer_table(("2026-10-27", "", "2026-11-10", "2.4146"))
        )
        self.assertEqual((written, history), (0, {}))

    def test_today_is_history(self):
        """Test the boundary matches Yahoo's."""
        history = {}
        self._apply(history, issuer_table(("2026-10-26", "", "2026-11-09", "2.4146")))
        self.assertIn(("IGLS.L", "2026-10-26"), history)

    def test_rows_before_the_start_date_are_not_touched(self):
        """Test a rebuild from a date."""
        history = {}
        self._apply(
            history,
            issuer_table(
                ("2025-07-17", "", "2025-07-30", "2.4917"),
                ("2026-01-15", "", "2026-01-28", "2.5662"),
            ),
            start="2026-01-01",
        )
        self.assertEqual(list(history), [("IGLS.L", "2026-01-15")])

    def test_a_second_apply_changes_nothing(self):
        """Test idempotence."""
        history = self._keyed(["IGLS.L", "2026-07-16", "", "2.4146", "GBP", "YA"])
        table = issuer_table(("2026-07-16", "", "2026-07-29", "2.4146"))
        self._apply(history, table)
        before = {key: list(row) for key, row in history.items()}
        self.assertEqual(self._apply(history, table), 0)
        self.assertEqual(history, before)

    def test_a_damaged_history_row_is_skipped_not_fatal(self):
        """Test an unreadable ex-date among the neighbours."""
        history = self._keyed(["IGLS.L", "soon", "", "2.4146", "GBP", "YA"])
        self._apply(history, issuer_table(("2026-07-16", "", "2026-07-29", "2.4146")))
        self.assertIn(("IGLS.L", "soon"), history)
        self.assertIn(("IGLS.L", "2026-07-16"), history)

    def test_the_recorded_igls_page_agrees_with_yahoos_rows(self):
        """Test the real table over the rows the committed history holds."""
        history = self._keyed(
            ["IGLS.L", "2026-07-16", "", "2.4146", "GBP", "YA"],
            ["IGLS.L", "2026-01-15", "", "2.5662", "GBP", "YA"],
        )
        table = scrape_fund_price.parse_ishares_distributions(
            fixture_text("ishares_251804_igls.html"), "251804"
        )
        self._apply(history, table)
        self.assertEqual(len(history), 36)
        self.assertEqual(
            history[("IGLS.L", "2026-01-15")],
            ["IGLS.L", "2026-01-15", "2026-01-28", "2.5662", "GBP", "IS"],
        )
        self.assertEqual({row[5] for row in history.values()}, {"IS"})


class TestIssuerDeclaredDividend(unittest.TestCase):
    """Test a future issuer row as the declared dividend (SPEC-011, #87)."""

    TODAY = date(2026, 10, 26)

    def _declared(self, table, currency="GBP"):
        return scrape_fund_price.issuer_declared(table, currency, self.TODAY)

    def test_the_earliest_future_row_is_declared(self):
        """Test ex-dates after today, oldest of them."""
        table = issuer_table(
            ("2026-07-16", "", "2026-07-29", "2.4146"),
            ("2026-11-12", "2026-11-13", "2026-11-25", "2.5"),
            ("2027-01-14", "", "2027-01-27", "2.6"),
        )
        self.assertEqual(
            self._declared(table),
            scrape_fund_price.DeclaredDividend(
                "2026-11-12", "2026-11-25", "2.5", "GBP"
            ),
        )

    def test_today_is_history_not_declared(self):
        """Test the boundary matches apply_issuer_table."""
        table = issuer_table(("2026-10-26", "", "2026-11-09", "2.5"))
        self.assertIsNone(self._declared(table))

    def test_no_future_row_is_none(self):
        """Test nothing is declared until the issuer says so."""
        table = issuer_table(("2026-07-16", "", "2026-07-29", "2.4146"))
        self.assertIsNone(self._declared(table))

    def test_the_amount_is_in_the_price_currency(self):
        """Test pounds become pence for a pence line."""
        table = issuer_table(("2026-11-12", "", "2026-11-25", "0.0991"))
        declared = self._declared(table, "GBp")
        self.assertEqual((declared.amount, declared.currency), ("9.91", "GBp"))

    def test_an_amount_that_cannot_be_stated_is_empty(self):
        """Test zero, or another currency, leaves the amount to the last paid."""
        for text, currency in (("0.0", "GBP"), ("1.5", "USD")):
            with self.subTest(text=text, currency=currency):
                table = issuer_table(
                    ("2026-11-12", "", "2026-11-25", text), currency=currency
                )
                declared = self._declared(table, "GBP")
                self.assertEqual((declared.amount, declared.currency), ("", ""))
                self.assertEqual(declared.ex_date, "2026-11-12")

    def test_a_row_without_a_pay_date_is_declared_without_one(self):
        """Test the ex-date alone is a declaration."""
        table = issuer_table(("2026-11-12", "", "", "2.5"))
        self.assertEqual(self._declared(table).pay_date, "")


class TestDailyIssuerDates(IssuerRunCase):
    """Test the daily run with an issuer source (SPEC-011, #87)."""

    def test_the_pay_date_and_the_declared_row_reach_both_files(self):
        """Test the point of the spec, end to end."""
        results = self._issuer_run(
            [FundSpec("YA", "IGLS.L")],
            [self.IGLS],
            {"251804": issuer_table(self.PAST, self.NEXT)},
            {"IGLS.L": [self.EVENT("2026-07-16", "2.4146", "GBP")]},
        )
        self.assertEqual(results.failures, [])
        self.assertEqual(
            self.read_rows("dividends_history.csv"),
            [["IGLS.L", "2026-07-16", "2026-07-29", "2.4146", "GBP", "IS"]],
        )
        self.assertEqual(
            self.read_rows("dividends_upcoming.csv"),
            [
                [
                    "IGLS.L",
                    "2026-11-12",
                    "2026-11-25",
                    "2.5",
                    "GBP",
                    "declared",
                    "2026-10-26",
                ]
            ],
        )

    def test_the_issuer_declaration_replaces_yahoos_and_the_estimate(self):
        """Test one declared row, the issuer's."""
        self._issuer_run(
            [FundSpec("YA", "IGLS.L")],
            [self.IGLS],
            {"251804": issuer_table(self.PAST, self.NEXT)},
            {"IGLS.L": [self.EVENT("2026-07-16", "2.4146", "GBP")]},
            declared={"IGLS.L": scrape_fund_price.DeclaredDividend("2026-11-19", "")},
        )
        rows = self.read_rows("dividends_upcoming.csv")
        self.assertEqual(
            [(row[1], row[5]) for row in rows], [("2026-11-12", "declared")]
        )

    def test_yahoos_declaration_stands_when_the_issuer_has_none(self):
        """Test the issuer adds, it does not retract."""
        self._issuer_run(
            [FundSpec("YA", "IGLS.L")],
            [self.IGLS],
            {"251804": issuer_table(self.PAST)},
            {"IGLS.L": [self.EVENT("2026-07-16", "2.4146", "GBP")]},
            declared={"IGLS.L": scrape_fund_price.DeclaredDividend("2026-11-19", "")},
        )
        rows = self.read_rows("dividends_upcoming.csv")
        self.assertEqual(
            [(row[1], row[5]) for row in rows], [("2026-11-19", "declared")]
        )

    def test_rows_are_published_under_every_alias(self):
        """Test a source line may name an alias; every identifier gets the rows."""
        source = scrape_fund_price.DividendSource("JFM0003373", "IS", "251804")
        self._issuer_run(
            [FundSpec("YA", "0P00000YAN", ("JFM0003373",))],
            [source],
            {"251804": issuer_table(self.PAST, self.NEXT)},
        )
        self.assertEqual(
            [
                (row[0], row[1], row[5])
                for row in self.read_rows("dividends_history.csv")
            ],
            [
                ("0P00000YAN", "2026-07-16", "IS"),
                ("JFM0003373", "2026-07-16", "IS"),
            ],
        )
        self.assertEqual(
            [(row[0], row[1]) for row in self.read_rows("dividends_upcoming.csv")],
            [("0P00000YAN", "2026-11-12"), ("JFM0003373", "2026-11-12")],
        )

    def test_an_instrument_with_no_yahoo_route_is_filled_from_the_issuer(self):
        """Test the FT-priced iShares fund, in its stored price currency."""
        self.write_text(
            "latest_prices.csv",
            "Fund,Date,Price,Currency\nIE00B0M63516,2026-10-23,40.5,USD\n",
        )
        source = scrape_fund_price.DividendSource("IE00B0M63516", "IS", "251853")
        self._issuer_run(
            [FundSpec("FT", "IE00B0M63516", ("IDBZ",))],
            [source],
            {
                "251853": issuer_table(
                    ("2026-03-19", "2026-03-20", "2026-03-27", "0.26"),
                    ("2026-09-17", "2026-09-18", "2026-09-30", "0.31"),
                    currency="USD",
                )
            },
        )
        self.assertEqual(
            self.read_rows("dividends_history.csv"),
            [
                ["IDBZ", "2026-03-19", "2026-03-27", "0.26", "USD", "IS"],
                ["IE00B0M63516", "2026-03-19", "2026-03-27", "0.26", "USD", "IS"],
                ["IDBZ", "2026-09-17", "2026-09-30", "0.31", "USD", "IS"],
                ["IE00B0M63516", "2026-09-17", "2026-09-30", "0.31", "USD", "IS"],
            ],
        )

    def test_a_pence_line_takes_the_issuers_pounds_as_pence(self):
        """Test the declared amount of a GBp instrument."""
        self.write_text(
            "latest_prices.csv",
            "Fund,Date,Price,Currency\nFLOS.L,2026-10-23,5000,GBp\n",
        )
        self._issuer_run(
            [FundSpec("YA", "FLOS.L")],
            [self.FLOS],
            {
                "290356": issuer_table(
                    ("2026-05-21", "", "2026-05-29", "0.0991"),
                    ("2026-11-12", "", "2026-11-25", "0.1"),
                )
            },
            {"FLOS.L": [self.EVENT("2026-05-21", "9.91", "GBp")]},
        )
        self.assertEqual(
            self.read_rows("dividends_history.csv"),
            [["FLOS.L", "2026-05-21", "2026-05-29", "9.91", "GBp", "IS"]],
        )
        [row] = self.read_rows("dividends_upcoming.csv")
        self.assertEqual(row[3:6], ["10", "GBp", "declared"])

    def test_one_failing_page_costs_nothing_else(self):
        """Test the failure is reported and the other instrument is written."""
        results = self._issuer_run(
            [FundSpec("YA", "IGLS.L"), FundSpec("YA", "FLOS.L")],
            [self.IGLS, self.FLOS],
            {
                "251804": RuntimeError("boom"),
                "290356": issuer_table(("2026-05-21", "", "2026-05-29", "0.0991")),
            },
            {
                "IGLS.L": [self.EVENT("2026-07-16", "2.4146", "GBP")],
                "FLOS.L": [self.EVENT("2026-05-21", "0.0991", "GBP")],
            },
        )
        self.assertEqual(results.failures, ["IGLS.L: pay dates: boom"])
        self.assertEqual(self.fetched.count("251804"), 3)
        self.assertEqual(
            {(row[0], row[2]) for row in self.read_rows("dividends_history.csv")},
            {("IGLS.L", ""), ("FLOS.L", "2026-05-29")},
        )

    def test_a_page_that_has_changed_is_a_reported_failure(self):
        """Test a parse error is handled like any other fetch error."""
        results = self._issuer_run(
            [FundSpec("YA", "IGLS.L")],
            [self.IGLS],
            {"251804": ValueError("iShares product 251804: no distributions table")},
        )
        self.assertEqual(
            results.failures,
            ["IGLS.L: pay dates: iShares product 251804: no distributions table"],
        )

    def test_a_day_the_issuer_fails_does_not_take_the_pay_dates_away(self):
        """Test Yahoo's daily upsert cannot blank what the issuer gave."""
        specs = [FundSpec("YA", "IGLS.L")]
        events = {"IGLS.L": [self.EVENT("2026-07-16", "2.4146", "GBP")]}
        self._issuer_run(
            specs, [self.IGLS], {"251804": issuer_table(self.PAST)}, events
        )
        self._issuer_run(specs, [self.IGLS], {"251804": OSError("down")}, events)
        self.assertEqual(
            self.read_rows("dividends_history.csv"),
            [["IGLS.L", "2026-07-16", "2026-07-29", "2.4146", "GBP", "IS"]],
        )

    def test_the_pages_are_fetched_a_second_apart(self):
        """Test a pause between instruments, none before the first."""
        self._issuer_run(
            [FundSpec("YA", "IGLS.L"), FundSpec("YA", "FLOS.L")],
            [self.IGLS, self.FLOS],
            {"251804": issuer_table(self.PAST), "290356": issuer_table(self.PAST)},
        )
        self.assertEqual(self.sleeps, [scrape_fund_price.ISSUER_PAUSE_SECONDS])
        self.assertEqual(scrape_fund_price.ISSUER_PAUSE_SECONDS, 1)

    def test_no_sources_means_no_requests(self):
        """Test the file is optional."""
        self._issuer_run([FundSpec("YA", "IGLS.L")], [])
        self.assertEqual((self.fetched, self.sleeps), ([], []))

    def test_a_second_run_changes_nothing_and_reports_nothing(self):
        """Test the declared row is news once."""
        args = (
            [FundSpec("YA", "IGLS.L")],
            [self.IGLS],
            {"251804": issuer_table(self.PAST, self.NEXT)},
            {"IGLS.L": [self.EVENT("2026-07-16", "2.4146", "GBP")]},
        )
        first = self._issuer_run(*args)
        files = {
            name: self.read_text(name)
            for name in ("dividends_history.csv", "dividends_upcoming.csv")
        }
        second = self._issuer_run(*args)
        self.assertEqual(
            files,
            {name: self.read_text(name) for name in files},
        )
        [news] = first.summary
        self.assertEqual(
            (news.name, news.ex_date, news.pay_date, news.amount, news.status),
            ("IGLS.L", "2026-11-12", "2026-11-25", "2.5", "declared"),
        )
        self.assertEqual(second.summary, [])


class TestIssuerDatesInTheRebuild(IssuerRunCase):
    """Test --backfill-dividends with an issuer source (SPEC-011, #87)."""

    def _rebuild(self, specs, sources, tables, events=None, start=None):
        def runner(specs, dists, data_dir, today):
            return scrape_fund_price.backfill_dividends(
                specs, dists, start, data_dir, today, sources=sources
            )

        return self._issuer_run(specs, sources, tables, events, runner=runner)

    def test_yahoo_and_issuer_rows_from_the_start_are_replaced(self):
        """Test the rebuild applies the issuer last and drops what it dropped."""
        self.write_text(
            "dividends_history.csv",
            "Fund,ExDate,PayDate,Amount,Currency,Source\n"
            "IGLS.L,2025-07-17,2025-07-30,2.4917,GBP,IS\n"
            "IGLS.L,2026-01-15,2026-01-28,9,GBP,IS\n"
            "IGLS.L,2026-02-02,2026-02-20,1,GBP,IS\n"
            "IGLS.L,2026-03-03,,1,GBP,config\n",
        )
        report = self._rebuild(
            [FundSpec("YA", "IGLS.L")],
            [self.IGLS],
            {
                "251804": issuer_table(
                    ("2025-07-17", "", "2025-07-30", "2.4917"),
                    ("2026-01-15", "", "2026-01-28", "2.5662"),
                    self.PAST,
                    self.NEXT,
                )
            },
            {
                "IGLS.L": [
                    self.EVENT("2026-01-15", "2.5662", "GBP"),
                    self.EVENT("2026-07-16", "2.4146", "GBP"),
                ]
            },
            start="2026-01-01",
        )
        self.assertEqual(
            self.read_rows("dividends_history.csv"),
            [
                ["IGLS.L", "2025-07-17", "2025-07-30", "2.4917", "GBP", "IS"],
                ["IGLS.L", "2026-01-15", "2026-01-28", "2.5662", "GBP", "IS"],
                ["IGLS.L", "2026-03-03", "", "1", "GBP", "config"],
                ["IGLS.L", "2026-07-16", "2026-07-29", "2.4146", "GBP", "IS"],
            ],
        )
        [entry] = report.entries
        self.assertEqual((entry["deleted"], entry["status"]), (2, "rebuilt"))
        self.assertEqual(report.failures, [])
        [upcoming] = self.read_rows("dividends_upcoming.csv")
        self.assertEqual(upcoming[1:3], ["2026-11-12", "2026-11-25"])
        self.assertEqual(upcoming[5], "declared")

    def test_an_instrument_with_no_yahoo_route_is_rebuilt_from_the_issuer(self):
        """Test the FT-priced fund has its own line in the report."""
        self.write_text(
            "dividends_history.csv",
            "Fund,ExDate,PayDate,Amount,Currency,Source\n"
            "IE00B0M63516,2025-09-18,2025-09-30,0.2,USD,IS\n"
            "IE00B0M63516,2026-03-19,2026-03-27,9,USD,IS\n"
            "IE00B0M63516,2026-04-01,2026-04-10,1,USD,IS\n",
        )
        source = scrape_fund_price.DividendSource("IE00B0M63516", "IS", "251853")
        report = self._rebuild(
            [FundSpec("FT", "IE00B0M63516")],
            [source],
            {
                "251853": issuer_table(
                    ("2025-09-18", "", "2025-09-30", "0.2"),
                    ("2026-03-19", "", "2026-03-27", "0.26"),
                    currency="USD",
                )
            },
            start="2026-01-01",
        )
        self.assertEqual(
            self.read_rows("dividends_history.csv"),
            [
                ["IE00B0M63516", "2025-09-18", "2025-09-30", "0.2", "USD", "IS"],
                ["IE00B0M63516", "2026-03-19", "2026-03-27", "0.26", "USD", "IS"],
            ],
        )
        [entry] = report.entries
        self.assertEqual(
            entry,
            {
                "identifier": "IE00B0M63516",
                "before": 3,
                "deleted": 2,
                "retained": 1,
                "inserted": 1,
                "first": "2026-03-19",
                "last": "2026-03-19",
                "currency": "USD",
                "status": "rebuilt",
            },
        )

    def test_a_failing_page_keeps_its_rows_and_fails_the_report(self):
        """Test nothing is lost when the issuer does not answer."""
        text = (
            "Fund,ExDate,PayDate,Amount,Currency,Source\n"
            "IE00B0M63516,2026-03-19,2026-03-27,0.26,USD,IS\n"
            "IGLS.L,2026-07-16,2026-07-29,2.4146,GBP,IS\n"
        )
        self.write_text("dividends_history.csv", text)
        report = self._rebuild(
            [FundSpec("FT", "IE00B0M63516"), FundSpec("YA", "IGLS.L")],
            [
                scrape_fund_price.DividendSource("IE00B0M63516", "IS", "251853"),
                self.IGLS,
            ],
            {"251853": OSError("down"), "251804": OSError("down")},
            {"IGLS.L": [self.EVENT("2026-07-16", "2.4146", "GBP")]},
        )
        self.assertEqual(self.read_text("dividends_history.csv"), text)
        self.assertEqual(
            report.failures,
            ["IE00B0M63516: pay dates: down", "IGLS.L: pay dates: down"],
        )
        self.assertEqual(
            [entry["status"] for entry in report.entries],
            ["failed, kept existing", "rebuilt"],
        )

    def test_a_failing_yahoo_fetch_still_takes_the_issuers_rows(self):
        """Test the two sources are independent."""
        self.write_text(
            "dividends_history.csv",
            "Fund,ExDate,PayDate,Amount,Currency,Source\n"
            "IGLS.L,2026-07-16,,2.4146,GBP,YA\n",
        )
        report = self._rebuild(
            [FundSpec("YA", "IGLS.L")],
            [self.IGLS],
            {"251804": issuer_table(self.PAST)},
            {"IGLS.L": RuntimeError("down")},
        )
        self.assertEqual(report.failures, ["IGLS.L: dividends: down"])
        self.assertEqual(
            self.read_rows("dividends_history.csv"),
            [["IGLS.L", "2026-07-16", "2026-07-29", "2.4146", "GBP", "IS"]],
        )


class TestPayDateSourcesInTheRun(IssuerRunCase):
    """Test the new sources through the daily run and the rebuild (SPEC-012, #89)."""

    QQQ = scrape_fund_price.DividendSource("QQQ", "IV", "46090E103")
    KNSL = scrape_fund_price.DividendSource(
        "KNSL", "Q4", "ir.kinsalecapitalgroup.com/XNYS"
    )

    @staticmethod
    def _table(source, *rows, currency="USD"):
        return scrape_fund_price.IssuerTable(
            currency,
            tuple(scrape_fund_price.IssuerDistribution(*row) for row in rows),
            source,
        )

    def test_the_table_names_its_source(self):
        """Test IssuerTable has no default source: every parser states its own."""
        with self.assertRaises(TypeError):
            scrape_fund_price.IssuerTable("GBP", ())

    def test_a_yahoo_row_gains_the_pay_date_and_the_source_of_the_table(self):
        """Test the point of the issue, end to end for QQQ."""
        past = ("2026-09-21", "2026-09-21", "2026-10-08", "0.75143")
        results = self._issuer_run(
            [FundSpec("YA", "QQQ")],
            [self.QQQ],
            {"46090E103": self._table("IV", past)},
            {"QQQ": [self.EVENT("2026-09-21", "0.75143", "USD")]},
        )
        self.assertEqual(results.failures, [])
        self.assertEqual(
            self.read_rows("dividends_history.csv"),
            [["QQQ", "2026-09-21", "2026-10-08", "0.75143", "USD", "IV"]],
        )

    def test_a_future_row_is_declared(self):
        """Test FR7 holds for a new source: a future ex-date is announced."""
        future = ("2026-11-27", "2026-11-27", "2026-12-15", "0.25")
        self._issuer_run(
            [FundSpec("YA", "KNSL")],
            [self.KNSL],
            {"ir.kinsalecapitalgroup.com/XNYS": self._table("Q4", future)},
            {"KNSL": [self.EVENT("2026-08-28", "0.25", "USD")]},
        )
        [row] = self.read_rows("dividends_upcoming.csv")
        self.assertEqual(
            row[:6], ["KNSL", "2026-11-27", "2026-12-15", "0.25", "USD", "declared"]
        )

    def test_a_pound_table_puts_pence_amounts_in_the_yahoo_currency(self):
        """Test GLTL.L: SSGA states pounds, Yahoo's row is in pence."""
        past = ("2026-08-03", "2026-08-04", "2026-08-17", "0.8811")
        source = scrape_fund_price.DividendSource("GLTL.L", "SS", "IE00B6YX5L24")
        self._issuer_run(
            [FundSpec("YA", "GLTL.L")],
            [source],
            {"IE00B6YX5L24": self._table("SS", past, currency="GBP")},
            {"GLTL.L": [self.EVENT("2026-08-03", "88.11", "GBp")]},
        )
        self.assertEqual(
            self.read_rows("dividends_history.csv"),
            [["GLTL.L", "2026-08-03", "2026-08-17", "88.11", "GBp", "SS"]],
        )

    def test_one_source_failing_leaves_the_others_and_the_yahoo_row(self):
        """Test a changed response logs and keeps the instrument's rows."""
        past = ("2026-09-21", "2026-09-21", "2026-10-08", "0.75143")
        results = self._issuer_run(
            [FundSpec("YA", "QQQ"), FundSpec("YA", "KNSL")],
            [self.QQQ, self.KNSL],
            {
                "46090E103": self._table("IV", past),
                "ir.kinsalecapitalgroup.com/XNYS": ValueError("Q4: changed"),
            },
            {
                "QQQ": [self.EVENT("2026-09-21", "0.75143", "USD")],
                "KNSL": [self.EVENT("2026-08-28", "0.25", "USD")],
            },
        )
        self.assertEqual(len(results.failures), 1)
        self.assertIn("KNSL: pay dates: Q4: changed", results.failures[0])
        by_fund = {r[0]: r for r in self.read_rows("dividends_history.csv")}
        self.assertEqual(by_fund["QQQ"][2], "2026-10-08")
        self.assertEqual(by_fund["KNSL"][2:], ["", "0.25", "USD", "YA"])

    def test_collecting_starts_each_run_with_empty_caches(self):
        """Test the SSGA workbook is downloaded once per run, not once per process."""
        with patch.object(scrape_fund_price, "clear_issuer_caches") as clear:
            with patch.object(scrape_fund_price, "fetch_issuer_table") as fetch:
                fetch.return_value = scrape_fund_price.IssuerTable("USD", (), "IS")
                scrape_fund_price.collect_issuer_tables(
                    [self.QQQ], [FundSpec("YA", "QQQ")]
                )
        clear.assert_called_once_with()

    def test_the_rebuild_replaces_rows_of_the_new_sources(self):
        """Test --backfill-dividends owns IV rows like IS rows."""
        history = {
            ("QQQ", "2026-06-22"): [
                "QQQ",
                "2026-06-22",
                "2026-07-10",
                "0.81349",
                "USD",
                "IV",
            ],
            ("QQQ", "2026-09-21"): [
                "QQQ",
                "2026-09-21",
                "",
                "0.75143",
                "USD",
                "YA",
            ],
        }
        table = self._table("IV", ("2026-09-21", "2026-09-21", "2026-10-08", "0.75143"))
        scrape_fund_price.apply_issuer_table(
            history, "QQQ", table, "USD", date(2026, 10, 26)
        )
        self.assertEqual(history[("QQQ", "2026-09-21")][5], "IV")
        self.assertEqual(history[("QQQ", "2026-09-21")][2], "2026-10-08")


class TestIssuerSourcesInMain(DataDirCase):
    """Test main() reads and passes dividend_sources.txt (SPEC-011, #87)."""

    def _write(self, text):
        self.write_text("dividend_sources.txt", text)

    def _argv(self, backfill):
        return ["--backfill-dividends", "--from", "2024-01-01"] if backfill else []

    def _main(self, backfill=False):
        """Run main() on the test directory's files, the run's steps stubbed.

        distributions.txt is pointed at a file that does not exist, so the
        committed schedules are not validated against the one stubbed fund.
        """
        with ExitStack() as stack:
            enter = stack.enter_context
            enter(
                patch(
                    "scrape_fund_price.DIVIDEND_SOURCES_FILE",
                    self.path("dividend_sources.txt"),
                )
            )
            enter(
                patch(
                    "scrape_fund_price.DISTRIBUTIONS_FILE",
                    self.path("distributions.txt"),
                )
            )
            stubs = enter(
                daily_run_stubs(
                    specs=[FundSpec("YA", "IGLS.L")],
                    backfill_dividends=BackfillReport(),
                )
            )
            self.scrape = stubs["scrape_funds"]
            self.update = stubs["update_dividends"]
            self.rebuild = stubs["backfill_dividends"]
            main(self._argv(backfill))

    def test_the_daily_run_passes_the_validated_sources(self):
        """Test update_dividends gets them by keyword."""
        self._write("IGLS.L,IS,251804\n")
        self._main()
        [source] = self.update.call_args.kwargs["sources"]
        self.assertEqual((source.identifier, source.source_id), ("IGLS.L", "251804"))

    def test_the_rebuild_passes_the_validated_sources(self):
        """Test --backfill-dividends gets them by keyword."""
        self._write("IGLS.L,IS,251804\n")
        self._main(backfill=True)
        [source] = self.rebuild.call_args.kwargs["sources"]
        self.assertEqual(source.identifier, "IGLS.L")

    def test_a_bad_file_fails_before_any_network_call(self):
        """Test validation comes first, in both modes."""
        self._write("NOPE,IS,251804\n")
        for backfill in (False, True):
            with self.subTest(backfill=backfill):
                with self.assertRaisesRegex(ValueError, "line 1.*NOPE"):
                    self._main(backfill)
        self.scrape.assert_not_called()
        self.update.assert_not_called()
        self.rebuild.assert_not_called()


# ===========================================================================
# UK CPI
# ===========================================================================


def ons_payload(months, cdid="D7BT"):
    """Build an ONS time-series response from (year, month name, value) rows."""
    return json.dumps(
        {
            "description": {"cdid": cdid, "title": "CPI INDEX 00: ALL ITEMS 2015=100"},
            "months": [
                {
                    "date": f"{year} {name[:3].upper()}",
                    "value": value,
                    "year": year,
                    "month": name,
                }
                for year, name, value in months
            ],
        }
    )


def ons_months(first_year=2015, last_year=2024):
    """A full run of monthly rows from January of one year to December of another."""
    names = [datetime.date(2000, number, 1).strftime("%B") for number in range(1, 13)]
    return [
        (str(year), name, f"{100 + (year - 2015) * 2 + number / 10:.1f}")
        for year in range(first_year, last_year + 1)
        for number, name in enumerate(names, start=1)
    ]


class TestOnsCpiParsing(unittest.TestCase):
    """Test reading the ONS D7BT response (SPEC-013, #91)."""

    def test_the_recorded_response_gives_the_published_months(self):
        """Test the live fixture: 2015-01 on, the index as the ONS words it."""
        index = scrape_fund_price.parse_ons_cpi(fixture_text("ons_d7bt_cpi.json"))
        months = list(index)
        self.assertEqual(months[0], "2015-01")
        self.assertEqual(months[-1], "2026-09")
        self.assertEqual(len(months), 11 * 12 + 9)
        self.assertEqual(months, sorted(months))
        self.assertEqual(index["2015-01"], "99.3")
        self.assertEqual(index["2015-02"], "99.5")
        self.assertEqual(index["2026-09"], "144.1")

    def test_months_before_2015_are_not_published(self):
        """Test the fixture holds 2014 and the parser drops it."""
        text = fixture_text("ons_d7bt_cpi.json")
        self.assertIn('"2014 DEC"', text)
        self.assertNotIn("2014-12", scrape_fund_price.parse_ons_cpi(text))

    def test_the_index_is_kept_exactly_as_published(self):
        """Test no float round trip: '100' stays '100', '99.30' stays '99.30'."""
        months = ons_months(2015, 2015)
        months[0] = ("2015", "January", "100")
        months[1] = ("2015", "February", "99.30")
        index = scrape_fund_price.parse_ons_cpi(ons_payload(months))
        self.assertEqual(index["2015-01"], "100")
        self.assertEqual(index["2015-02"], "99.30")

    def test_a_month_without_a_value_is_not_yet_published(self):
        """Test the ONS lists a month with an empty value before it is out."""
        months = ons_months(2015, 2015) + [("2016", "January", "")]
        index = scrape_fund_price.parse_ons_cpi(ons_payload(months))
        self.assertNotIn("2016-01", index)
        self.assertEqual(len(index), 12)

    def test_another_series_is_refused(self):
        """Test a response for a different series id is a changed response."""
        with self.assertRaisesRegex(ValueError, "D7BT"):
            scrape_fund_price.parse_ons_cpi(
                ons_payload(ons_months(2015, 2015), cdid="CHZQ")
            )

    def test_a_response_that_is_not_json_is_refused(self):
        """Test the ONS's HTML error page is a bad response."""
        with self.assertRaises(ValueError):
            scrape_fund_price.parse_ons_cpi("<html>Page not found</html>")

    def test_a_response_without_months_is_refused(self):
        """Test a changed shape is refused, not read as no months."""
        for text in ('{"description": {"cdid": "D7BT"}}', "[]", '{"months": []}'):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    scrape_fund_price.parse_ons_cpi(text)

    def test_a_month_entry_that_is_not_an_object_is_refused(self):
        """Test a month listed as bare text, not an object, is a changed shape."""
        text = ons_payload(ons_months(2015, 2015)).replace(
            '"months": [', '"months": ["2015 JAN", '
        )
        with self.assertRaisesRegex(ValueError, "not an object.*2015 JAN"):
            scrape_fund_price.parse_ons_cpi(text)

    def test_a_series_that_no_longer_reaches_back_to_2015_is_refused(self):
        """Test a truncated series cannot replace the published file."""
        with self.assertRaisesRegex(ValueError, "2015-01"):
            scrape_fund_price.parse_ons_cpi(ons_payload(ons_months(2016, 2024)))

    def test_a_gap_in_the_series_is_refused(self):
        """Test a missing month inside the range is a bad response."""
        months = [row for row in ons_months(2015, 2020) if row[:2] != ("2017", "May")]
        with self.assertRaisesRegex(ValueError, "2017-05"):
            scrape_fund_price.parse_ons_cpi(ons_payload(months))

    def test_a_value_that_is_not_a_number_is_refused(self):
        """Test a non-numeric or non-positive index is a bad response."""
        for value in ("n/a", "-1", "0", "1e3", "99,3"):
            with self.subTest(value=value):
                months = ons_months(2015, 2015)
                months[3] = ("2015", "April", value)
                with self.assertRaisesRegex(ValueError, "2015-04"):
                    scrape_fund_price.parse_ons_cpi(ons_payload(months))

    def test_a_month_listed_twice_is_refused(self):
        """Test a duplicated month is ambiguous, so it is a bad response."""
        months = ons_months(2015, 2015) + [("2015", "March", "101.0")]
        with self.assertRaisesRegex(ValueError, "2015-03"):
            scrape_fund_price.parse_ons_cpi(ons_payload(months))

    def test_an_unknown_month_name_is_refused(self):
        """Test a label the parser does not know is a changed response."""
        months = ons_months(2015, 2015)
        months[0] = ("2015", "Smarch", "99.3")
        with self.assertRaises(ValueError):
            scrape_fund_price.parse_ons_cpi(ons_payload(months))


class TestOnsCpiFetch(unittest.TestCase):
    """Test the one request per run (SPEC-013, #91)."""

    @patch("scrape_fund_price.requests.get")
    def test_one_get_of_the_time_series(self, mock_get):
        """Test the url, the browser User-Agent, the timeout and the status check."""
        response = MagicMock(text=fixture_text("ons_d7bt_cpi.json"))
        mock_get.return_value = response
        index = scrape_fund_price.fetch_uk_cpi()
        mock_get.assert_called_once()
        self.assertEqual(
            mock_get.call_args.args[0],
            "https://www.ons.gov.uk/economy/inflationandpriceindices/"
            "timeseries/d7bt/mm23/data",
        )
        self.assertTrue(
            mock_get.call_args.kwargs["headers"]["User-Agent"].startswith("Mozilla/5.0")
        )
        self.assertEqual(mock_get.call_args.kwargs["timeout"], 30)
        response.raise_for_status.assert_called_once()
        self.assertEqual(index["2026-09"], "144.1")

    @patch("scrape_fund_price.requests.get")
    def test_an_http_error_propagates_for_the_retry(self, mock_get):
        """Test a status error is raised, not swallowed."""
        mock_get.return_value.raise_for_status.side_effect = (
            scrape_fund_price.requests.HTTPError("503")
        )
        with self.assertRaises(scrape_fund_price.requests.HTTPError):
            scrape_fund_price.fetch_uk_cpi()


class TestUkCpiUpdate(DataDirCase):
    """Test the daily update of uk_cpi.csv (SPEC-013, #91)."""

    TODAY = date(2026, 10, 27)
    HEADER = "Month,Index,Series,AsOf\n"
    FILE = "uk_cpi.csv"

    def _run(self, fetch):
        with patch.object(scrape_fund_price, "fetch_uk_cpi", fetch):
            return REAL_UPDATE_UK_CPI(self.test_dir, self.TODAY)

    def test_the_first_run_writes_the_whole_series(self):
        """Test header, a row per month sorted, series id and the run date."""
        index = {"2015-02": "99.5", "2015-01": "99.3"}
        results = self._run(lambda: index)
        self.assertEqual(results.failures, [])
        self.assertEqual(
            self.read_text(self.FILE),
            self.HEADER
            + "2015-01,99.3,D7BT,2026-10-27\n"
            + "2015-02,99.5,D7BT,2026-10-27\n",
        )

    def test_the_file_has_lf_endings(self):
        """Test no CRLF, on any platform."""
        self._run(lambda: {"2015-01": "99.3"})
        with open(self.path(self.FILE), "rb") as file:
            self.assertNotIn(b"\r", file.read())

    def test_the_real_response_gives_a_file_from_2015_01(self):
        """Test the recorded response end to end."""
        text = fixture_text("ons_d7bt_cpi.json")
        self._run(lambda: scrape_fund_price.parse_ons_cpi(text))
        lines = self.read_text(self.FILE).splitlines()
        self.assertEqual(lines[0], "Month,Index,Series,AsOf")
        self.assertEqual(lines[1], "2015-01,99.3,D7BT,2026-10-27")
        self.assertEqual(lines[-1], "2026-09,144.1,D7BT,2026-10-27")
        self.assertEqual(len(lines), 1 + 11 * 12 + 9)

    def test_a_revised_month_replaces_the_published_one(self):
        """Test the ONS's number wins, and only changed rows take the run date.

        AsOf is when the row's value was last published or revised, so an
        unchanged month keeps its date and the file does not churn daily.
        """
        self.write_text(
            self.FILE,
            self.HEADER
            + "2015-01,99.3,D7BT,2026-09-01\n"
            + "2015-02,99.5,D7BT,2026-09-01\n",
        )
        self._run(lambda: {"2015-01": "99.3", "2015-02": "99.6", "2015-03": "99.7"})
        self.assertEqual(
            self.read_text(self.FILE),
            self.HEADER
            + "2015-01,99.3,D7BT,2026-09-01\n"
            + "2015-02,99.6,D7BT,2026-10-27\n"
            + "2015-03,99.7,D7BT,2026-10-27\n",
        )

    def test_an_unchanged_series_leaves_the_file_byte_identical(self):
        """Test a run that reads the same numbers writes the same file."""
        stored = (
            self.HEADER
            + "2015-01,99.3,D7BT,2026-09-01\n"
            + "2015-02,99.5,D7BT,2026-09-15\n"
        )
        self.write_text(self.FILE, stored)
        self._run(lambda: {"2015-01": "99.3", "2015-02": "99.5"})
        self.assertEqual(self.read_text(self.FILE), stored)

    def test_a_stored_row_from_another_series_is_replaced(self):
        """Test a matching index under a different series id is not kept."""
        self.write_text(self.FILE, self.HEADER + "2015-01,99.3,OTHER,2026-09-01\n")
        self._run(lambda: {"2015-01": "99.3"})
        self.assertEqual(
            self.read_text(self.FILE), self.HEADER + "2015-01,99.3,D7BT,2026-10-27\n"
        )

    def test_a_published_month_the_response_lacks_is_kept(self):
        """Test the file never loses a month the ONS once published."""
        self.write_text(self.FILE, self.HEADER + "2014-12,99.0,D7BT,2026-09-01\n")
        self._run(lambda: {"2015-01": "99.3"})
        self.assertIn("2014-12,99.0,D7BT,2026-09-01\n", self.read_text(self.FILE))
        self.assertIn("2015-01,99.3,D7BT,2026-10-27\n", self.read_text(self.FILE))

    def test_a_failed_fetch_keeps_the_last_published_file(self):
        """Test the file is byte-identical and the failure is listed."""
        stored = self.HEADER + "2015-01,99.3,D7BT,2026-09-01\n"
        self.write_text(self.FILE, stored)

        def refuse():
            raise ValueError("ONS D7BT: months missing")

        results = self._run(refuse)
        self.assertEqual(self.read_text(self.FILE), stored)
        self.assertEqual(len(results.failures), 1)
        self.assertTrue(results.failures[0].startswith("uk_cpi: "))
        self.assertIn("months missing", results.failures[0])

    def test_a_failure_with_no_file_writes_none(self):
        """Test no empty or error file is created."""

        def refuse():
            raise ConnectionError("down")

        results = self._run(refuse)
        self.assertFalse(os.path.exists(self.path(self.FILE)))
        self.assertEqual(len(results.failures), 1)

    def test_a_transient_failure_is_retried(self):
        """Test the shared retry applies, as for every other source."""
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionError("blip")
            return {"2015-01": "99.3"}

        results = self._run(flaky)
        self.assertEqual(len(calls), 3)
        self.assertEqual(results.failures, [])
        self.assertIn("2015-01,99.3", self.read_text(self.FILE))

    def test_the_data_directory_is_created(self):
        """Test a missing data/ is made, as for the other files."""
        nested = self.path("nested")
        with patch.object(scrape_fund_price, "fetch_uk_cpi", lambda: {"2015-01": "1"}):
            REAL_UPDATE_UK_CPI(nested, self.TODAY)
        self.assertTrue(os.path.isfile(os.path.join(nested, "uk_cpi.csv")))

    def test_the_defaults_are_the_data_directory_and_today(self):
        """Test the arguments are optional."""
        with patch.object(scrape_fund_price, "DATA_DIR", self.test_dir):
            with patch.object(
                scrape_fund_price, "fetch_uk_cpi", lambda: {"2015-01": "99.3"}
            ):
                REAL_UPDATE_UK_CPI()
        self.assertIn(date.today().isoformat(), self.read_text(self.FILE))


class TestUkCpiInMain(unittest.TestCase):
    """Test the daily run publishes the index beside the prices (#91)."""

    def _main(self, outcome):
        """Run the daily mode with update_uk_cpi patched as `outcome` says."""
        with daily_run_stubs(
            specs=[FundSpec("YA", "QQQ")],
            read_distributions=[],
            update_uk_cpi=outcome,
        ) as stubs:
            self.write = stubs["write_results"]
            self.summary = stubs["write_summary"]
            self.update = stubs["update_uk_cpi"]
            main([])

    def test_the_daily_run_updates_the_index_once(self):
        """Test update_uk_cpi runs in the normal mode."""
        self._main({"return_value": scrape_fund_price.UkCpiResults()})
        self.update.assert_called_once_with()

    def test_a_failure_is_in_the_runs_failure_list_after_everything_is_written(self):
        """Test the run exits non-zero, with prices and summary already written."""
        results = scrape_fund_price.UkCpiResults(failures=["uk_cpi: down"])
        with self.assertRaises(SystemExit):
            self._main({"return_value": results})
        self.write.assert_called_once()
        self.summary.assert_called_once()

    def test_a_crash_in_the_update_does_not_cost_the_summary(self):
        """Test an unexpected exception is a failure, as for the dividends."""
        with self.assertRaises(SystemExit):
            self._main({"side_effect": RuntimeError("boom")})
        self.summary.assert_called_once()

    def test_the_other_modes_do_not_fetch_it(self):
        """Test --backfill and the rest never touch the ONS."""
        with daily_run_stubs(
            backfill_history=BackfillReport(), update_uk_cpi={}
        ) as stubs:
            main(["--backfill", "--from", "2024-01-01"])
        stubs["update_uk_cpi"].assert_not_called()


# ===========================================================================
# UK Bank Rate
# ===========================================================================


def boe_page(rows, table_id="stats-table"):
    """Build a Bank Rate history page from (date text, rate text) rows."""
    body = "".join(
        f'<tr><td align="left">{when}</td><td align="right"> {rate}</td></tr>'
        for when, rate in rows
    )
    return (
        '<html><body><table class="cookie-notice__table"><tr><td>x</td></tr>'
        f'</table><table class="display" id="{table_id}"><thead><tr>'
        "<th>Date Changed</th><th>Rate</th></tr></thead>"
        f"<tbody>{body}</tbody></table></body></html>"
    )


# Newest first, as the page lists them.
BOE_ROWS = [
    ("18 Dec 25", "3.75"),
    ("07 Aug 25", "4.00"),
    ("03 Aug 23", "5.25"),
    ("04 Aug 16", "0.25"),
    ("05 Mar 09", "0.50"),
    ("05 Feb 09", "1.00"),
]


class TestBankRateParsing(unittest.TestCase):
    """Test reading the Bank Rate history page (SPEC-014, #93)."""

    TODAY = date(2026, 11, 1)

    def _parse(self, text):
        return scrape_fund_price.parse_boe_bank_rate(text, self.TODAY)

    def test_the_recorded_page_gives_the_whole_history_oldest_first(self):
        """Test the live fixture: every change back to 1975, the rate as worded."""
        changes = self._parse(fixture_text("boe_bank_rate.html"))
        self.assertEqual(len(changes), 258)
        self.assertEqual(changes[0], (date(1975, 1, 20), "11.25"))
        self.assertEqual(changes[-1], (date(2025, 12, 18), "3.75"))
        self.assertEqual(changes, sorted(changes))

    def test_two_digit_years_are_read_as_20yy_unless_in_the_future(self):
        """Test 25 is 2025 and 75 is 1975."""
        changes = self._parse(boe_page([("18 Dec 25", "3.75"), ("20 Jan 75", "11.25")]))
        self.assertEqual(changes[0][0], date(1975, 1, 20))
        self.assertEqual(changes[1][0], date(2025, 12, 18))

    def test_the_rate_is_kept_exactly_as_published(self):
        """Test no float round trip: '4.00' stays '4.00'."""
        changes = self._parse(boe_page(BOE_ROWS))
        self.assertIn((date(2025, 8, 7), "4.00"), changes)

    def test_a_page_without_the_table_is_refused(self):
        """Test an error page or a changed layout is a bad response."""
        for text in (
            "<html>Page not found</html>",
            boe_page(BOE_ROWS, table_id="other"),
            boe_page([]),
        ):
            with self.subTest(text=text[:40]):
                with self.assertRaises(ValueError):
                    self._parse(text)

    def test_a_row_that_does_not_parse_is_refused(self):
        """Test a bad rate or date is a changed page."""
        for when, rate in (
            ("18 Dec 25", "n/a"),
            ("18 Dec 25", "-1"),
            ("18 Dec 25", "1e3"),
            ("18 Dec 25", "4,25"),
            ("18 Smarch 25", "3.75"),
            ("31 Feb 25", "3.75"),
            ("Dec 2025", "3.75"),
        ):
            with self.subTest(when=when, rate=rate):
                with self.assertRaises(ValueError):
                    self._parse(boe_page([(when, rate)] + BOE_ROWS))

    def test_a_date_listed_twice_is_refused(self):
        """Test a duplicated date is ambiguous, so it is a bad response."""
        with self.assertRaisesRegex(ValueError, "2025-12-18"):
            self._parse(boe_page([("18 Dec 25", "3.50")] + BOE_ROWS))

    def test_a_row_with_the_wrong_number_of_cells_is_refused(self):
        """Test a changed layout is a bad response, not a skipped row."""
        text = boe_page(BOE_ROWS).replace(
            "</tbody>", "<tr><td>18 Dec 25</td><td>3.75</td><td>x</td></tr></tbody>"
        )
        with self.assertRaisesRegex(ValueError, "not a date and a rate"):
            self._parse(text)

    def test_a_table_nested_in_the_page_table_is_not_read_as_rows(self):
        """Test only the history table's own rows count."""
        nested = "<tr><td><table><tr><td>x</td></tr></table></td><td>x</td></tr>"
        text = boe_page(BOE_ROWS).replace("</tbody>", nested + "</tbody>")
        with self.assertRaises(ValueError):
            self._parse(text)
        text = boe_page(BOE_ROWS).replace(
            "</thead>", "</thead><caption><table><tr><td>x</td></tr></table></caption>"
        )
        self.assertEqual(len(self._parse(text)), len(BOE_ROWS))

    def test_a_history_that_stops_after_2014_is_refused(self):
        """Test a truncated table cannot replace the published file."""
        with self.assertRaisesRegex(ValueError, "2014-12-31"):
            self._parse(boe_page(BOE_ROWS[:3]))


class TestBankRateByMonth(unittest.TestCase):
    """Test deriving the month-end rate from the change dates (SPEC-014, #93)."""

    TODAY = date(2026, 11, 1)

    def _months(self, changes=None, today=None):
        if changes is None:
            changes = scrape_fund_price.parse_boe_bank_rate(
                fixture_text("boe_bank_rate.html"), self.TODAY
            )
        return scrape_fund_price.uk_bank_rate_by_month(changes, today or self.TODAY)

    def test_known_month_ends_from_the_recorded_page(self):
        """Test the rate in force at the end of the month, change dates included."""
        rates = self._months()
        self.assertEqual(rates["2015-01"], "0.50")
        self.assertEqual(rates["2016-07"], "0.50")  # cut on 4 Aug 2016
        self.assertEqual(rates["2016-08"], "0.25")
        self.assertEqual(rates["2020-03"], "0.10")  # cut on 19 Mar 2020
        self.assertEqual(rates["2023-08"], "5.25")
        self.assertEqual(rates["2024-08"], "5.00")
        self.assertEqual(rates["2026-10"], "3.75")

    def test_every_month_from_2015_01_to_the_current_month_has_a_row(self):
        """Test the series has no gap and starts at UK_BANK_RATE_START."""
        months = list(self._months())
        self.assertEqual(months[0], "2015-01")
        self.assertEqual(months[-1], "2026-11")
        self.assertEqual(len(months), 11 * 12 + 11)
        self.assertEqual(months, sorted(months))
        month = months[0]
        for expected in months[1:]:
            month = scrape_fund_price.next_month(month)
            self.assertEqual(month, expected)

    def test_a_change_on_the_last_day_counts_and_one_after_does_not(self):
        """Test the cut is the month's last day, inclusive."""
        changes = [
            (date(2009, 3, 5), "0.50"),
            (date(2015, 2, 28), "0.75"),
            (date(2015, 4, 1), "1.00"),
        ]
        rates = self._months(changes, date(2015, 4, 20))
        self.assertEqual(rates["2015-01"], "0.50")
        self.assertEqual(rates["2015-02"], "0.75")
        self.assertEqual(rates["2015-03"], "0.75")  # repeated, no change
        self.assertEqual(rates["2015-04"], "1.00")

    def test_the_current_month_is_the_rate_in_force_on_the_run_date(self):
        """Test a change later in the month is not yet in force."""
        changes = [(date(2009, 3, 5), "0.50"), (date(2015, 2, 20), "0.75")]
        self.assertEqual(self._months(changes, date(2015, 2, 10))["2015-02"], "0.50")
        self.assertEqual(self._months(changes, date(2015, 2, 20))["2015-02"], "0.75")

    def test_a_year_boundary_is_crossed(self):
        """Test December rolls to January."""
        changes = [(date(2009, 3, 5), "0.50")]
        rates = self._months(changes, date(2016, 2, 3))
        self.assertEqual(rates["2015-12"], "0.50")
        self.assertEqual(rates["2016-01"], "0.50")


class TestBankRateFetch(unittest.TestCase):
    """Test the one request per run (SPEC-014, #93)."""

    @patch("scrape_fund_price.requests.get")
    def test_one_get_of_the_history_page(self, mock_get):
        """Test the url, the browser User-Agent, the timeout and the status check."""
        response = MagicMock(text=fixture_text("boe_bank_rate.html"))
        mock_get.return_value = response
        changes = scrape_fund_price.fetch_uk_bank_rate()
        mock_get.assert_called_once()
        self.assertEqual(
            mock_get.call_args.args[0],
            "https://www.bankofengland.co.uk/boeapps/database/Bank-Rate.asp",
        )
        self.assertTrue(
            mock_get.call_args.kwargs["headers"]["User-Agent"].startswith("Mozilla/5.0")
        )
        self.assertEqual(mock_get.call_args.kwargs["timeout"], 30)
        response.raise_for_status.assert_called_once()
        self.assertEqual(changes[-1], (date(2025, 12, 18), "3.75"))

    def test_the_source_is_not_a_robots_disallowed_route(self):
        """Test the url is on none of the paths robots.txt disallows."""
        path = urllib.parse.urlparse(scrape_fund_price.UK_BANK_RATE_URL).path.lower()
        for disallowed in (
            "/boeapps/database/showchart.asp",
            "/boeapps/database/_iadb-fromshowcolumns.asp",
            "/boeapps/iadb",
            "/boeapps/titan",
        ):
            self.assertFalse(path.startswith(disallowed), disallowed)

    @patch("scrape_fund_price.requests.get")
    def test_an_http_error_propagates_for_the_retry(self, mock_get):
        """Test a status error is raised, not swallowed."""
        mock_get.return_value.raise_for_status.side_effect = (
            scrape_fund_price.requests.HTTPError("503")
        )
        with self.assertRaises(scrape_fund_price.requests.HTTPError):
            scrape_fund_price.fetch_uk_bank_rate()


class TestUkBankRateUpdate(DataDirCase):
    """Test the daily update of uk_bank_rate.csv (SPEC-014, #93)."""

    TODAY = date(2015, 3, 10)
    HEADER = "Month,Rate,Series,AsOf\n"
    CHANGES = [(date(2009, 3, 5), "0.50")]
    FILE = "uk_bank_rate.csv"

    def _run(self, fetch):
        with patch.object(scrape_fund_price, "fetch_uk_bank_rate", fetch):
            return REAL_UPDATE_UK_BANK_RATE(self.test_dir, self.TODAY)

    def test_the_first_run_writes_every_month(self):
        """Test header, a row per month sorted, series id and the run date."""
        results = self._run(lambda: self.CHANGES)
        self.assertEqual(results.failures, [])
        self.assertEqual(
            self.read_text(self.FILE),
            self.HEADER
            + "2015-01,0.50,UK_BANK_RATE,2015-03-10\n"
            + "2015-02,0.50,UK_BANK_RATE,2015-03-10\n"
            + "2015-03,0.50,UK_BANK_RATE,2015-03-10\n",
        )

    def test_the_file_has_lf_endings(self):
        """Test no CRLF, on any platform."""
        self._run(lambda: self.CHANGES)
        with open(self.path(self.FILE), "rb") as file:
            self.assertNotIn(b"\r", file.read())

    def test_the_real_page_gives_a_file_from_2015_01(self):
        """Test the recorded page end to end."""
        changes = scrape_fund_price.parse_boe_bank_rate(
            fixture_text("boe_bank_rate.html"), date(2026, 11, 1)
        )
        with patch.object(scrape_fund_price, "fetch_uk_bank_rate", lambda: changes):
            REAL_UPDATE_UK_BANK_RATE(self.test_dir, date(2026, 11, 1))
        lines = self.read_text(self.FILE).splitlines()
        self.assertEqual(lines[0], "Month,Rate,Series,AsOf")
        self.assertEqual(lines[1], "2015-01,0.50,UK_BANK_RATE,2026-11-01")
        self.assertEqual(lines[-1], "2026-11,3.75,UK_BANK_RATE,2026-11-01")
        self.assertEqual(len(lines), 1 + 11 * 12 + 11)

    def test_a_changed_month_replaces_the_published_one(self):
        """Test the page's rate wins, and only changed rows take the run date."""
        self.write_text(
            self.FILE,
            self.HEADER
            + "2015-01,0.50,UK_BANK_RATE,2015-02-01\n"
            + "2015-02,0.75,UK_BANK_RATE,2015-02-01\n",
        )
        self._run(lambda: self.CHANGES)
        self.assertEqual(
            self.read_text(self.FILE),
            self.HEADER
            + "2015-01,0.50,UK_BANK_RATE,2015-02-01\n"
            + "2015-02,0.50,UK_BANK_RATE,2015-03-10\n"
            + "2015-03,0.50,UK_BANK_RATE,2015-03-10\n",
        )

    def test_an_unchanged_series_leaves_the_file_byte_identical(self):
        """Test a run that reads the same numbers writes the same file."""
        stored = (
            self.HEADER
            + "2015-01,0.50,UK_BANK_RATE,2015-02-01\n"
            + "2015-02,0.50,UK_BANK_RATE,2015-02-15\n"
            + "2015-03,0.50,UK_BANK_RATE,2015-03-02\n"
        )
        self.write_text(self.FILE, stored)
        self._run(lambda: self.CHANGES)
        self.assertEqual(self.read_text(self.FILE), stored)

    def test_a_stored_row_from_another_series_is_replaced(self):
        """Test a matching rate under a different series id is not kept."""
        self.write_text(self.FILE, self.HEADER + "2015-01,0.50,OTHER,2015-02-01\n")
        self._run(lambda: self.CHANGES)
        self.assertIn(
            "2015-01,0.50,UK_BANK_RATE,2015-03-10\n", self.read_text(self.FILE)
        )

    def test_a_published_month_the_page_lacks_is_kept(self):
        """Test the file never loses a month it once published."""
        self.write_text(
            self.FILE, self.HEADER + "2014-12,0.50,UK_BANK_RATE,2015-01-02\n"
        )
        self._run(lambda: self.CHANGES)
        self.assertIn(
            "2014-12,0.50,UK_BANK_RATE,2015-01-02\n", self.read_text(self.FILE)
        )

    def test_a_failed_fetch_keeps_the_last_published_file(self):
        """Test the file is byte-identical and the failure is listed."""
        stored = self.HEADER + "2015-01,0.50,UK_BANK_RATE,2015-02-01\n"
        self.write_text(self.FILE, stored)

        def refuse():
            raise ValueError("Bank Rate table missing")

        results = self._run(refuse)
        self.assertEqual(self.read_text(self.FILE), stored)
        self.assertEqual(len(results.failures), 1)
        self.assertTrue(results.failures[0].startswith("uk_bank_rate: "))
        self.assertIn("table missing", results.failures[0])

    def test_a_failure_with_no_file_writes_none(self):
        """Test no empty or error file is created."""

        def refuse():
            raise ConnectionError("down")

        results = self._run(refuse)
        self.assertFalse(os.path.exists(self.path(self.FILE)))
        self.assertEqual(len(results.failures), 1)

    def test_a_transient_failure_is_retried(self):
        """Test the shared retry applies, as for every other source."""
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionError("blip")
            return self.CHANGES

        results = self._run(flaky)
        self.assertEqual(len(calls), 3)
        self.assertEqual(results.failures, [])
        self.assertIn("2015-01,0.50", self.read_text(self.FILE))

    def test_a_page_that_starts_after_2014_gives_a_failure_not_a_file(self):
        """Test a history with no rate in force at 2014-12-31 is refused."""
        results = self._run(lambda: [(date(2015, 2, 5), "0.75")])
        self.assertEqual(len(results.failures), 1)
        self.assertFalse(os.path.exists(self.path(self.FILE)))

    def test_the_data_directory_is_created(self):
        """Test a missing data/ is made, as for the other files."""
        nested = self.path("nested")
        with patch.object(
            scrape_fund_price, "fetch_uk_bank_rate", lambda: self.CHANGES
        ):
            REAL_UPDATE_UK_BANK_RATE(nested, self.TODAY)
        self.assertTrue(os.path.isfile(os.path.join(nested, "uk_bank_rate.csv")))

    def test_the_defaults_are_the_data_directory_and_today(self):
        """Test the arguments are optional."""
        with patch.object(scrape_fund_price, "DATA_DIR", self.test_dir):
            with patch.object(
                scrape_fund_price, "fetch_uk_bank_rate", lambda: self.CHANGES
            ):
                REAL_UPDATE_UK_BANK_RATE()
        self.assertIn(date.today().isoformat(), self.read_text(self.FILE))


class TestUkBankRateInMain(unittest.TestCase):
    """Test the daily run publishes the rate beside the prices (#93)."""

    def _main(self, outcome):
        """Run the daily mode with update_uk_bank_rate patched as `outcome` says."""
        with daily_run_stubs(
            specs=[FundSpec("YA", "QQQ")],
            read_distributions=[],
            update_uk_bank_rate=outcome,
        ) as stubs:
            self.write = stubs["write_results"]
            self.summary = stubs["write_summary"]
            self.update = stubs["update_uk_bank_rate"]
            main([])

    def test_the_daily_run_updates_the_rate_once(self):
        """Test update_uk_bank_rate runs in the normal mode."""
        self._main({"return_value": scrape_fund_price.UkBankRateResults()})
        self.update.assert_called_once_with()

    def test_a_failure_is_in_the_runs_failure_list_after_everything_is_written(self):
        """Test the run exits non-zero, with prices and summary already written."""
        results = scrape_fund_price.UkBankRateResults(failures=["uk_bank_rate: down"])
        with self.assertRaises(SystemExit):
            self._main({"return_value": results})
        self.write.assert_called_once()
        self.summary.assert_called_once()

    def test_a_crash_in_the_update_does_not_cost_the_summary(self):
        """Test an unexpected exception is a failure, as for the dividends."""
        with self.assertRaises(SystemExit):
            self._main({"side_effect": RuntimeError("boom")})
        self.summary.assert_called_once()

    def test_the_other_modes_do_not_fetch_it(self):
        """Test --backfill and the rest never touch the Bank's page."""
        with daily_run_stubs(
            backfill_history=BackfillReport(), update_uk_bank_rate={}
        ) as stubs:
            main(["--backfill", "--from", "2024-01-01"])
        stubs["update_uk_bank_rate"].assert_not_called()


# ===========================================================================
# main() and the command line
# ===========================================================================


class TestMainEntryPoint(DataDirCase):
    """Test the main() command-line entry point."""

    @patch("builtins.print")
    def test_main_history_without_start_date_errors(self, mock_print):
        """Test --history without --start reports an error and stops.

        main(argv) parses the list it is given, as parse_arguments(args)
        does, so a test drives a mode with the real flags instead of patching
        parse_arguments with a namespace whose unset attributes are truthy.
        """
        main(["--history", "AAPL"])
        mock_print.assert_called_once_with(
            "Error: --start date is required when using --history"
        )

    @patch("builtins.print")
    @patch("scrape_fund_price.fetch_historical_data")
    def test_main_history_success_prints_path(self, mock_fetch, mock_print):
        """Test successful historical retrieval reports the saved file."""
        mock_fetch.return_value = "data/history_AAPL_2024-01-01_2024-12-31.csv"
        main(["--history", "AAPL", "--start", "2024-01-01"])
        mock_fetch.assert_called_once_with("AAPL", "2024-01-01", None)
        mock_print.assert_called_once_with(
            "Historical data saved to: data/history_AAPL_2024-01-01_2024-12-31.csv"
        )

    @patch("builtins.print")
    @patch("scrape_fund_price.fetch_historical_data")
    def test_main_history_error_is_reported(self, mock_fetch, mock_print):
        """Test a failed historical retrieval surfaces the error message."""
        mock_fetch.return_value = "Error: No data found for symbol BADSYM"
        main(["--history", "BADSYM", "--start", "2024-01-01"])
        mock_print.assert_called_once_with("Error: No data found for symbol BADSYM")

    def test_the_summary_reads_the_history_in_the_data_directory(self):
        """Test main() follows DATA_DIR rather than a path fixed at import.

        The suite redirects DATA_DIR in setUpModule; a path bound at import
        time to the literal data/prices_history.csv made every main() test
        summarise the repository's committed history instead.
        """
        self.write_csv(
            "prices_history.csv",
            ["Fund", "Date", "Price", "Currency"],
            [
                ["TESTFUND", "2026-10-29", "100.00", "GBP"],
                ["TESTFUND", "2026-10-30", "101.00", "GBP"],
            ],
        )
        with daily_run_stubs(self.test_dir, specs=[FundSpec("YA", "TESTFUND")]) as s:
            main([])
        [row] = s["write_summary"].call_args.args[0]
        self.assertEqual(
            (row.name, row.new_date, row.new, row.old),
            ("TESTFUND", "2026-10-30", "101.00", "100.00"),
        )


class TestFailureDoesNotSuppressOutput(unittest.TestCase):
    """Test a partially failed run still publishes everything it obtained."""

    SPECS = [FundSpec("YA", "QQQ"), FundSpec("YA", "GRAB")]

    def test_results_are_written_before_failure_is_signalled(self):
        """Test output is written even when some funds failed, then the job fails."""
        results = ScrapeResults(
            [["QQQ", "2026-09-18", "721.45", "USD"]],
            failures=["GRAB: Error: Timeout"],
        )
        with daily_run_stubs(specs=self.SPECS, scrape_funds=results) as stubs:
            with self.assertRaises(SystemExit) as error:
                main([])

        # The write must happen, otherwise a single failing fund would
        # discard a whole day of good prices.
        stubs["write_results"].assert_called_once_with(results)
        self.assertEqual(error.exception.code, 1)

    def test_clean_run_does_not_exit_non_zero(self):
        """Test a run with no failures completes normally."""
        results = ScrapeResults([["QQQ", "2026-09-18", "721.45", "USD"]])
        with daily_run_stubs(specs=self.SPECS[:1], scrape_funds=results) as stubs:
            main([])
        stubs["write_results"].assert_called_once_with(results)

    def _crashing_run(self, crash):
        """Run the daily mode with every step stubbed and `crash` raising.

        Returns the stubs by name together with the exit code and what was
        printed, so a test can assert which steps still ran.
        """
        outcomes = {
            "update_uk_cpi": scrape_fund_price.UkCpiResults(),
            "update_uk_bank_rate": scrape_fund_price.UkBankRateResults(),
            crash: RuntimeError(f"{crash} exploded"),
        }
        with daily_run_stubs(
            specs=[FundSpec("YA", "QQQ")], pairs=["USDGBP"], **outcomes
        ) as stubs:
            with self.assertRaises(SystemExit) as error:
                main([])
        stubs["exit_code"] = error.exception.code
        stubs["printed"] = [str(c.args[0]) for c in stubs["print"].call_args_list]
        return stubs

    def test_a_crash_in_the_price_step_does_not_cost_the_other_files(self):
        """Test an exception outside the per-fund retries is a price failure.

        AGENTS.md promises the run writes everything it obtained and only
        then exits non-zero; the dividend, CPI and Bank Rate steps keep that
        promise, so the price step must too.
        """
        ran = self._crashing_run("scrape_funds")
        ran["write_fx_results"].assert_called_once()
        ran["update_dividends"].assert_called_once()
        ran["update_uk_cpi"].assert_called_once()
        ran["update_uk_bank_rate"].assert_called_once()
        ran["write_summary"].assert_called_once()
        self.assertEqual(ran["exit_code"], 1)
        self.assertIn("Error: prices: scrape_funds exploded", ran["printed"])

    def test_a_crash_writing_the_prices_is_a_price_failure_too(self):
        """Test the whole step is covered, not only the fetch."""
        ran = self._crashing_run("write_results")
        ran["write_summary"].assert_called_once()
        self.assertEqual(ran["exit_code"], 1)
        self.assertIn("Error: prices: write_results exploded", ran["printed"])

    def test_a_crash_in_the_fx_step_does_not_cost_the_other_files(self):
        """Test the FX step is isolated the same way, as `fx: <error>`."""
        ran = self._crashing_run("snap_fx_rates")
        ran["write_results"].assert_called_once()
        ran["update_dividends"].assert_called_once()
        ran["update_uk_cpi"].assert_called_once()
        ran["update_uk_bank_rate"].assert_called_once()
        ran["write_summary"].assert_called_once()
        self.assertEqual(ran["exit_code"], 1)
        self.assertIn("Error: fx: snap_fx_rates exploded", ran["printed"])


class TestHistoricalData(DataDirCase):
    """Test historical data retrieval functionality."""

    def test_parse_arguments_history_with_dates(self):
        """Test parsing command-line arguments for historical data with start and end dates."""
        args = parse_arguments(
            ["--history", "AAPL", "--start", "2024-01-01", "--end", "2024-12-31"]
        )
        self.assertEqual(args.history, "AAPL")
        self.assertEqual(args.start, "2024-01-01")
        self.assertEqual(args.end, "2024-12-31")

    def test_parse_arguments_history_start_only(self):
        """Test parsing command-line arguments with only start date."""
        args = parse_arguments(["--history", "MSFT", "--start", "2024-11-01"])
        self.assertEqual(args.history, "MSFT")
        self.assertEqual(args.start, "2024-11-01")
        self.assertIsNone(args.end)

    def test_parse_arguments_no_history(self):
        """Test parsing command-line arguments without history flag."""
        args = parse_arguments([])
        self.assertIsNone(args.history)
        self.assertIsNone(args.start)
        self.assertIsNone(args.end)

    @patch("scrape_fund_price.yf.Ticker")
    def test_fetch_historical_data_valid_symbol(self, mock_ticker):
        """Test the bars are saved as history_<symbol>_<start>_<end>.csv."""
        fake_ticker(mock_ticker, [("2024-01-02", 185.64), ("2024-01-03", 184.25)])

        result = fetch_historical_data(
            "AAPL", "2024-01-01", "2024-12-31", self.test_dir
        )

        mock_ticker.assert_called_once_with("AAPL")
        mock_ticker.return_value.history.assert_called_once_with(
            start="2024-01-01", end="2024-12-31"
        )
        name = "history_AAPL_2024-01-01_2024-12-31.csv"
        self.assertEqual(result, self.path(name))
        self.assertEqual(
            self.read_rows(name), [["2024-01-02", "185.64"], ["2024-01-03", "184.25"]]
        )

    @patch("scrape_fund_price.yf.Ticker")
    def test_fetch_historical_data_invalid_symbol(self, mock_ticker):
        """Test an error from Yahoo comes back as an error message."""
        mock_ticker.return_value.history.side_effect = Exception("Invalid symbol")

        result = fetch_historical_data(
            "INVALID_XYZ", "2024-01-01", "2024-12-31", self.test_dir
        )

        self.assertEqual(result, "Error: Invalid symbol")

    def test_fetch_historical_data_invalid_date_format(self):
        """Test fetching historical data with invalid date format."""
        result = fetch_historical_data(
            "AAPL", "01-01-2024", "2024-12-31", self.test_dir
        )
        self.assertEqual(result, "Error: Invalid start date format. Use YYYY-MM-DD")

    def test_fetch_historical_data_invalid_end_date_format(self):
        """Test fetching historical data with a malformed end date."""
        result = fetch_historical_data("AAPL", "2024-01-01", "31-12-2024")
        self.assertEqual(result, "Error: Invalid end date format. Use YYYY-MM-DD")

    @patch("scrape_fund_price.yf.Ticker")
    def test_fetch_historical_data_empty_range_returns_error(self, mock_ticker):
        """Test a date range yielding no rows reports no data found."""
        fake_ticker(mock_ticker, [])
        result = fetch_historical_data("AAPL", "2024-01-01", "2024-01-02")
        self.assertEqual(result, "Error: No data found for symbol AAPL")

    def test_fetch_historical_data_start_after_end(self):
        """Test fetching historical data with start date after end date."""
        result = fetch_historical_data(
            "AAPL", "2024-12-31", "2024-01-01", self.test_dir
        )
        self.assertEqual(result, "Error: Start date must be before end date")


# ===========================================================================
# Committed configuration
# ===========================================================================


REPO = os.path.dirname(os.path.abspath(__file__))


class TestCommittedConfiguration(unittest.TestCase):
    """The repository's own configuration and data, read from the checkout.

    These are the one place the suite reads committed files: a typo in a
    configuration file fails the suite rather than the nightly run, and the
    one-off closed-holding imports are checked against the stored history.
    `len(specs)` changes whenever an instrument is added or retired.
    """

    def test_committed_funds_file_uses_only_current_codes(self):
        """Test the repository's own configuration has been migrated."""
        specs = read_fund_specs(os.path.join(REPO, "funds.txt"))
        self.assertEqual({s.source for s in specs}, {"YA", "FT"})
        self.assertEqual(len(specs), 32)

    def test_committed_windows_are_fully_present_in_history(self):
        """Test the committed history actually covers every configured window.

        The import is a one-off, so nothing re-runs to catch a window that
        silently came back short: Yahoo treats the end date as exclusive and
        BKCH first imported 284 rows for a 285-day window.
        """
        stored = read_history_rows(os.path.join(REPO, "data", "prices_history.csv"))
        for holding in read_closed_holdings(os.path.join(REPO, "closed_holdings.txt")):
            dates = sorted(key[1] for key in stored if key[0] == holding.identifier)
            self.assertTrue(dates, f"{holding.identifier} has no stored history")
            self.assertEqual(dates[0], holding.start, holding.identifier)
            self.assertEqual(dates[-1], holding.end, holding.identifier)

    def test_the_shipped_file_parses_and_has_no_entries(self):
        """Test the committed distributions.txt is a valid, empty file."""
        path = os.path.join(REPO, "distributions.txt")
        self.assertEqual(scrape_fund_price.read_distributions(path, set()), [])

    def test_the_committed_distributions_file_is_valid_for_the_committed_funds(self):
        """Test a typo in the owner's file fails the suite, not the nightly run."""
        specs = read_fund_specs(os.path.join(REPO, "funds.txt"))
        known = scrape_fund_price.configured_identifiers(specs)
        scrape_fund_price.read_distributions(
            os.path.join(REPO, "distributions.txt"), known
        )

    def test_the_committed_dividend_sources_are_valid_for_the_committed_funds(self):
        """Test a typo in the owner's file fails the suite, not the nightly run."""
        sources = scrape_fund_price.read_dividend_sources(
            os.path.join(REPO, "dividend_sources.txt"),
            read_fund_specs(os.path.join(REPO, "funds.txt")),
        )
        self.assertTrue(sources)
        self.assertTrue(
            all(s.source in scrape_fund_price.DIVIDEND_SOURCE_CODES for s in sources)
        )

    def test_the_committed_dividend_sources_name_the_four_instruments(self):
        """Test the shipped rows validate against the committed funds.txt."""
        sources = scrape_fund_price.read_dividend_sources(
            os.path.join(REPO, "dividend_sources.txt"),
            read_fund_specs(os.path.join(REPO, "funds.txt")),
        )
        by_code = {s.source: s for s in sources if s.source != "IS"}
        self.assertEqual(
            {code: (s.identifier, s.source_id) for code, s in by_code.items()},
            {
                "IV": ("QQQ", "46090E103"),
                "SS": ("GLTL.L", "IE00B6YX5L24"),
                "Q4": ("KNSL", "ir.kinsalecapitalgroup.com/XNYS"),
                "ET": ("0639.HK", "639"),
            },
        )


# ===========================================================================
# Live sources
# ===========================================================================


@unittest.skipUnless(
    os.environ.get("FUNDPRICES_LIVE"), "live sources; set FUNDPRICES_LIVE=1"
)
class TestFunctionalScraping(DataDirCase):
    """Functional tests that can run against real websites (optional).

    Every fetch is given the scratch directory: without one these write into
    the repository's data/, leaving files such as latest_AAPL.price for a
    symbol that is not in funds.txt.
    """

    def assertUsableQuotes(self, results, fund_id, expect_dated=True):
        """Assert a live fetch produced at least one usable dated price.

        Sources go down; that is a fact of life for this project rather than a
        code defect, so an outage skips instead of failing. Anything that does
        come back must still be well formed.
        """
        if results.failures:
            self.skipTest(f"source unavailable: {results.failures[0]}")

        self.assertGreaterEqual(len(results), 1)
        today = date.today().isoformat()
        for fund, price_date, price, currency in results:
            self.assertEqual(fund, fund_id)
            # A price date must be real, and never in the future.
            parsed = date.fromisoformat(price_date)
            self.assertLessEqual(parsed.isoformat(), today)
            if expect_dated:
                # Dated sources report the market's date, not the run date.
                self.assertLess(parsed.weekday(), 5, f"{price_date} is a weekend")
            self.assertNotEqual(price, "N/A")
            self.assertNotEqual(price, "")
            self.assertFalse(price.startswith("Error:"))
            try:
                float(price)
            except ValueError:
                self.fail(f"Price should be a valid number, got: {price}")

    def test_functional_ft_scraping(self):
        """Functional test for FT prices (requires internet connection)."""
        results = scrape_funds([("FT", "IE0008368742")], self.test_dir)
        self.assertUsableQuotes(results, "IE0008368742")
        # FT reports the quoting currency alongside the price.
        self.assertTrue(all(row[3] for row in results))

    def test_functional_yahoo_scraping(self):
        """Functional test for Yahoo scraping (requires internet connection)."""
        results = scrape_funds([("YH", "IDTG.L")], self.test_dir)
        # The scrape route reads a page showing only the current price, so its
        # quote carries the run date and may fall on a weekend.
        self.assertUsableQuotes(results, "IDTG.L", expect_dated=False)

    def test_functional_morningstar_scraping(self):
        """Functional test for Morningstar scraping (requires internet connection)."""
        results = scrape_funds([("MS", "JFM0003373")], self.test_dir)
        self.assertUsableQuotes(results, "JFM0003373", expect_dated=False)

    def test_functional_yahoo_api(self):
        """Functional test for the Yahoo Finance API (requires internet)."""
        results = scrape_funds([("YA", "AAPL")], self.test_dir)
        self.assertUsableQuotes(results, "AAPL")
        self.assertTrue(all(row[3] == "USD" for row in results))

    def test_functional_api_reports_the_sources_own_price_date(self):
        """Functional test that stored dates come from the source, not the clock."""
        quotes = fetch_yahoo_quotes(
            "QQQ", (date.today() - timedelta(days=15)).isoformat()
        )
        if not quotes:
            self.skipTest("Yahoo returned no bars")
        self.assertTrue(all(date.fromisoformat(q.date).weekday() < 5 for q in quotes))
        self.assertTrue(all(q.currency == "USD" for q in quotes))
        # Consecutive trading days must be distinct, not a carried-forward run.
        self.assertEqual(len({q.date for q in quotes}), len(quotes))

    def test_fetch_price_api_valid_symbol(self):
        """Functional test for fetch_price_api with a real symbol."""
        price = fetch_price_api("AAPL")
        self.assertIsNotNone(price)
        self.assertNotEqual(price, "N/A")
        try:
            float(price)
        except ValueError:
            self.fail(f"Price should be a valid number, got: {price}")

    def test_fetch_price_api_invalid_symbol(self):
        """Functional test for fetch_price_api with a symbol Yahoo lacks."""
        price = fetch_price_api("INVALID_SYMBOL_XYZ123")
        self.assertTrue(price.startswith("Error:") or price == "N/A")


@unittest.skipUnless(
    os.environ.get("FUNDPRICES_LIVE"), "live sources; set FUNDPRICES_LIVE=1"
)
class TestFunctionalClosedHoldingSources(unittest.TestCase):
    """Functional test for the source only closed holdings use (optional)."""

    def test_functional_investing_history(self):
        """Functional test for investing.com (requires internet connection).

        Uses a liquidated fund, so the window is fixed and the values cannot
        change; an outage or a block skips rather than fails.
        """
        try:
            quotes = fetch_investing_quotes("1182866", "2024-01-04", "2024-01-10")
        except Exception as error:
            self.skipTest(f"source unavailable: {error}")
        self.assertEqual(quotes[0], Quote("2024-01-04", "218.95", ""))
        self.assertTrue(all(date.fromisoformat(q.date).weekday() < 5 for q in quotes))


if __name__ == "__main__":
    unittest.main(buffer=True)
