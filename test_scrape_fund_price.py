import unittest
import tempfile
import os
import shutil
from unittest.mock import patch, MagicMock
import csv
from datetime import date, timedelta

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
)

# Point the module's default output directory at a scratch location for the
# whole suite. A test that forgets to pass data_dir would otherwise write into
# the repository's committed data/, which is how a stray latest_AAPL.price and
# live FX rewrites got in before.
_REAL_DATA_DIR = scrape_fund_price.DATA_DIR
_SUITE_DATA_DIR = None


def setUpModule():
    global _SUITE_DATA_DIR
    _SUITE_DATA_DIR = tempfile.mkdtemp(prefix="fundprices-tests-")
    scrape_fund_price.DATA_DIR = _SUITE_DATA_DIR


def tearDownModule():
    scrape_fund_price.DATA_DIR = _REAL_DATA_DIR
    if _SUITE_DATA_DIR:
        shutil.rmtree(_SUITE_DATA_DIR, ignore_errors=True)


class TestFundPriceScraper(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.test_dir)

    def test_read_fund_ids(self):
        """Test reading fund IDs from a file."""
        # Create a temporary funds file
        funds_file = os.path.join(self.test_dir, "test_funds.txt")
        with open(funds_file, "w") as f:
            f.write("FT,IE0008368742\n")
            f.write("YH,IDTG.L\n")
            f.write("MS,JFM0003373\n")
            f.write("  \n")  # Empty line
            f.write("FT,GB00B1FXTF86\n")

        result = read_fund_ids(funds_file)
        expected = [
            ("FT", "IE0008368742"),
            ("YH", "IDTG.L"),
            ("MS", "JFM0003373"),
            ("FT", "GB00B1FXTF86"),
        ]
        self.assertEqual(result, expected)

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

    def test_fetch_price_api_valid_symbol(self):
        """Test fetching price via API with valid symbol."""
        price = fetch_price_api("AAPL")
        self.assertIsNotNone(price)
        self.assertNotEqual(price, "N/A")
        # Price should be a valid number
        try:
            float(price)
        except ValueError:
            self.fail(f"Price should be a valid number, got: {price}")

    def test_fetch_price_api_invalid_symbol(self):
        """Test fetching price via API with invalid symbol."""
        price = fetch_price_api("INVALID_SYMBOL_XYZ123")
        # Should return error message or N/A
        self.assertTrue(price.startswith("Error:") or price == "N/A")

    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_fetch_price_api_mock(self, mock_quotes):
        """Test fetching price via API with mocked quote retrieval."""
        mock_quotes.return_value = [Quote("2026-09-18", "150.25", "USD")]

        price = fetch_price_api("AAPL")
        self.assertEqual(price, "150.25")
        self.assertEqual(mock_quotes.call_args.args[0], "AAPL")

    @patch("scrape_fund_price.yf.Ticker")
    def test_fetch_price_api_exception(self, mock_ticker):
        """Test fetching price via API when exception occurs."""
        # Mock the yfinance Ticker to raise an exception
        mock_ticker.side_effect = Exception("Network error")

        price = fetch_price_api("AAPL")
        self.assertTrue(price.startswith("Error:"))
        self.assertIn("Network error", price)

    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_fetch_price_api_no_price_available(self, mock_quotes):
        """Test fetching price via API when no quotes are returned."""
        mock_quotes.return_value = []

        price = fetch_price_api("AAPL")
        self.assertEqual(price, "Error: Price not available")

    @patch("scrape_fund_price.sync_playwright")
    def test_scrape_funds_mock(self, mock_playwright):
        """Test scraping funds with mocked Playwright."""
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_playwright.return_value.__enter__.return_value.chromium.launch.return_value = (
            mock_browser
        )
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        mock_page.locator.return_value.first.text_content.return_value = "123.45"

        # YH and MS still scrape a page; FT and GF now use HTTP routes.
        test_funds = [("YH", "IDTG.L"), ("MS", "JFM0003373")]

        results = scrape_funds(test_funds, self.test_dir)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0][0], "IDTG.L")
        self.assertEqual(results[0][2], "123.45")
        self.assertEqual(results[1][0], "JFM0003373")
        self.assertEqual(results[1][2], "123.45")

        self.assertTrue(
            os.path.exists(os.path.join(self.test_dir, "latest_IDTG.L.price"))
        )
        self.assertTrue(
            os.path.exists(os.path.join(self.test_dir, "latest_JFM0003373.price"))
        )

    @patch("scrape_fund_price.sync_playwright")
    def test_scrape_funds_removes_commas_from_all_price_sources(self, mock_playwright):
        """Test that every source stores prices without thousands separators."""
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_playwright.return_value.__enter__.return_value.chromium.launch.return_value = (
            mock_browser
        )
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        mock_page.locator.return_value.first.text_content.return_value = "1,234.56"

        test_funds = [
            ("FT", "FT_FUND"),
            ("YH", "SGLN.L"),
            ("MS", "MS_FUND"),
            ("GF", "API_FUND"),
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
            latest_price_file = os.path.join(self.test_dir, f"latest_{fund_id}.price")
            with open(latest_price_file, "r") as f:
                self.assertEqual(f.read().strip(), "1234.56")

    def test_write_results(self):
        """Test writing results to CSV files."""
        test_results = [
            ["IE0008368742", "2025-01-20", "123.45", "USD"],
            ["IDTG.L", "2025-01-20", "2.92", "GBP"],
        ]

        write_results(test_results, self.test_dir)

        latest_csv = os.path.join(self.test_dir, "latest_prices.csv")
        history_csv = os.path.join(self.test_dir, "prices_history.csv")
        rolling_history_csv = os.path.join(self.test_dir, "prices_history_90_days.csv")

        self.assertTrue(os.path.exists(latest_csv))
        self.assertTrue(os.path.exists(history_csv))
        self.assertTrue(os.path.exists(rolling_history_csv))

        # Rows are sorted by date then fund, so output is deterministic.
        expected = [
            ["Fund", "Date", "Price", "Currency"],
            ["IDTG.L", "2025-01-20", "2.92", "GBP"],
            ["IE0008368742", "2025-01-20", "123.45", "USD"],
        ]

        with open(latest_csv, "r") as f:
            self.assertEqual(list(csv.reader(f)), expected)

        with open(history_csv, "r") as f:
            self.assertEqual(list(csv.reader(f)), expected)

        with open(rolling_history_csv, "r") as f:
            self.assertEqual(list(csv.reader(f)), expected)

    def test_write_results_limits_rolling_history_to_90_calendar_days(self):
        """Test rolling history uses an inclusive 90-calendar-day window."""
        history_csv = os.path.join(self.test_dir, "prices_history.csv")
        with open(history_csv, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["Fund", "Date", "Price"])
            writer.writerows(
                [
                    ["TOO_OLD", "2025-01-01", "1.00"],
                    ["AT_CUTOFF", "2025-01-02", "2.00"],
                    ["FUTURE", "2025-04-02", "3.00"],
                    ["INVALID", "not-a-date", "4.00"],
                ]
            )

        write_results([["TODAY", "2025-04-01", "5.00", "GBP"]], self.test_dir)

        with open(history_csv, "r") as file:
            full_history_rows = list(csv.reader(file))

        # Legacy rows are preserved and upgraded with an empty currency.
        self.assertEqual(
            full_history_rows,
            [
                ["Fund", "Date", "Price", "Currency"],
                ["TOO_OLD", "2025-01-01", "1.00", ""],
                ["AT_CUTOFF", "2025-01-02", "2.00", ""],
                ["TODAY", "2025-04-01", "5.00", "GBP"],
                ["FUTURE", "2025-04-02", "3.00", ""],
                ["INVALID", "not-a-date", "4.00", ""],
            ],
        )

        rolling_history_csv = os.path.join(self.test_dir, "prices_history_90_days.csv")
        with open(rolling_history_csv, "r") as file:
            rolling_rows = list(csv.reader(file))

        self.assertEqual(
            rolling_rows,
            [
                ["Fund", "Date", "Price", "Currency"],
                ["AT_CUTOFF", "2025-01-02", "2.00", ""],
                ["TODAY", "2025-04-01", "5.00", "GBP"],
            ],
        )

    def test_write_results_empty_results_creates_empty_rolling_history(self):
        """Test an empty run still writes a valid rolling-history CSV."""
        write_results([], self.test_dir)

        rolling_history_csv = os.path.join(self.test_dir, "prices_history_90_days.csv")
        with open(rolling_history_csv, "r") as file:
            rows = list(csv.reader(file))

        self.assertEqual(rows, [["Fund", "Date", "Price", "Currency"]])

    def test_write_results_append_history(self):
        """Test that history file appends new data."""
        write_results([["IE0008368742", "2025-01-20", "123.45", "USD"]], self.test_dir)
        write_results([["IDTG.L", "2025-01-21", "2.92", "GBP"]], self.test_dir)

        history_csv = os.path.join(self.test_dir, "prices_history.csv")
        with open(history_csv, "r") as f:
            rows = list(csv.reader(f))

        self.assertEqual(
            rows,
            [
                ["Fund", "Date", "Price", "Currency"],
                ["IE0008368742", "2025-01-20", "123.45", "USD"],
                ["IDTG.L", "2025-01-21", "2.92", "GBP"],
            ],
        )

    def test_write_results_no_duplicates_same_day(self):
        """Test that running twice on same day updates price instead of duplicating."""
        write_results([["IE0008368742", "2025-01-20", "123.45", "USD"]], self.test_dir)
        write_results([["IE0008368742", "2025-01-20", "125.67", "USD"]], self.test_dir)

        expected = [
            ["Fund", "Date", "Price", "Currency"],
            ["IE0008368742", "2025-01-20", "125.67", "USD"],
        ]

        history_csv = os.path.join(self.test_dir, "prices_history.csv")
        with open(history_csv, "r") as f:
            self.assertEqual(list(csv.reader(f)), expected)

        rolling_history_csv = os.path.join(self.test_dir, "prices_history_90_days.csv")
        with open(rolling_history_csv, "r") as f:
            self.assertEqual(list(csv.reader(f)), expected)

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

        history_csv = os.path.join(self.test_dir, "prices_history.csv")
        with open(history_csv, "r") as f:
            rows = list(csv.reader(f))

        self.assertEqual(
            rows,
            [
                ["Fund", "Date", "Price", "Currency"],
                ["AAPL", "2025-01-20", "150.25", "USD"],
                ["IDTG.L", "2025-01-20", "2.92", "GBP"],
                ["IE0008368742", "2025-01-20", "125.67", "USD"],
            ],
        )

    def test_scrape_funds_error_handling(self):
        """Test error handling in scraping."""
        test_funds = [("INVALID", "TEST123")]

        with patch("scrape_fund_price.sync_playwright"):
            results = scrape_funds(test_funds, self.test_dir)

        # An unsupported source yields no dated price, and is reported
        # rather than stored as a fabricated N/A row.
        self.assertEqual(list(results), [])
        self.assertEqual(len(results.failures), 1)
        self.assertIn("TEST123", results.failures[0])

    @patch("scrape_fund_price.sync_playwright")
    def test_scrape_funds_with_gf_source(self, mock_playwright):
        """Test scraping with GF source (uses API instead of scraping)."""
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_playwright.return_value.__enter__.return_value.chromium.launch.return_value = (
            mock_browser
        )
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        test_funds = [("GF", "AAPL")]

        with patch(
            "scrape_fund_price.fetch_yahoo_quotes",
            return_value=[Quote("2026-09-18", "150.25", "USD")],
        ):
            results = scrape_funds(test_funds, self.test_dir)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][2], "150.25")
        self.assertEqual(results[0][1], "2026-09-18")

    @patch("scrape_fund_price.sync_playwright")
    def test_scrape_funds_scraping_exception(self, mock_playwright):
        """Test error handling when scraping raises exception."""
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_playwright.return_value.__enter__.return_value.chromium.launch.return_value = (
            mock_browser
        )
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        mock_page.goto.side_effect = Exception("Timeout")

        results = scrape_funds([("YH", "TEST123")], self.test_dir)

        # No price could be obtained, so no dated row is invented.
        self.assertEqual(list(results), [])
        self.assertEqual(len(results.failures), 1)
        self.assertEqual(mock_page.goto.call_count, 3)

    @patch("scrape_fund_price.sync_playwright")
    def test_scrape_funds_retries_timeout_and_succeeds(self, mock_playwright):
        """Test transient timeout errors are retried before writing a price."""
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_playwright.return_value.__enter__.return_value.chromium.launch.return_value = (
            mock_browser
        )
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        timeout_error = (
            "Failed to perform, curl: (28) Operation timed out after "
            "30002 milliseconds with 0 bytes received."
        )
        mock_page.goto.side_effect = [Exception(timeout_error), None]
        mock_page.locator.return_value.first.text_content.return_value = "123.45"

        results = scrape_funds([("YH", "TEST123")], self.test_dir)

        self.assertEqual(
            list(results), [["TEST123", date.today().isoformat(), "123.45", ""]]
        )
        self.assertEqual(results.failures, [])
        self.assertEqual(mock_page.goto.call_count, 2)

        latest_price_file = os.path.join(self.test_dir, "latest_TEST123.price")
        with open(latest_price_file, "r") as f:
            self.assertEqual(f.read().strip(), "123.45")

    @patch("scrape_fund_price.sync_playwright")
    def test_scrape_funds_uses_last_good_price_after_retry_failure(
        self, mock_playwright
    ):
        """Test persistent timeout errors keep the last good stored price."""
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_playwright.return_value.__enter__.return_value.chromium.launch.return_value = (
            mock_browser
        )
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        timeout_error = (
            "Failed to perform, curl: (28) Operation timed out after "
            "30002 milliseconds with 0 bytes received."
        )
        mock_page.goto.side_effect = Exception(timeout_error)

        history_csv = os.path.join(self.test_dir, "prices_history.csv")
        with open(history_csv, mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["Fund", "Date", "Price"])
            writer.writerow(["TEST123", "2025-01-19", "111.11"])
            writer.writerow(
                ["TEST123", date.today().isoformat(), f"Error: {timeout_error}"]
            )

        latest_price_file = os.path.join(self.test_dir, "latest_TEST123.price")
        with open(latest_price_file, "w") as f:
            f.write(f"Error: {timeout_error}\n")

        results = scrape_funds([("YH", "TEST123")], self.test_dir)

        # No fabricated row for today; the real last price is carried instead,
        # against the date it actually belongs to.
        self.assertEqual(list(results), [])
        self.assertEqual(results.carried, [["TEST123", "2025-01-19", "111.11", ""]])
        self.assertEqual(len(results.failures), 1)
        self.assertIn("TEST123", results.failures[0])
        self.assertEqual(mock_page.goto.call_count, 3)

        with open(latest_price_file, "r") as f:
            self.assertEqual(f.read().strip(), "111.11")

    @patch("scrape_fund_price.sync_playwright")
    def test_scrape_funds_retries_api_error_and_succeeds(self, mock_playwright):
        """Test transient API errors are retried before writing a price."""
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_playwright.return_value.__enter__.return_value.chromium.launch.return_value = (
            mock_browser
        )
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        with patch(
            "scrape_fund_price.fetch_yahoo_quotes",
            side_effect=[
                Exception("curl: (28) Operation timed out"),
                [Quote("2026-09-18", "220.50", "GBp")],
            ],
        ) as mock_quotes:
            results = scrape_funds([("GF", "IWDG.L")], self.test_dir)

        self.assertEqual(list(results), [["IWDG.L", "2026-09-18", "220.50", "GBp"]])
        self.assertEqual(results.failures, [])
        self.assertEqual(mock_quotes.call_count, 2)

    @patch("scrape_fund_price.sync_playwright")
    def test_scrape_funds_keeps_last_good_price_after_api_retry_failure(
        self, mock_playwright
    ):
        """Test persistent API errors keep the last good stored price."""
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_playwright.return_value.__enter__.return_value.chromium.launch.return_value = (
            mock_browser
        )
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        history_csv = os.path.join(self.test_dir, "prices_history.csv")
        with open(history_csv, mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["Fund", "Date", "Price", "Currency"])
            writer.writerow(["IWDG.L", "2025-01-19", "210.75", "GBp"])

        with patch(
            "scrape_fund_price.fetch_yahoo_quotes",
            side_effect=Exception("curl: (28) Operation timed out"),
        ) as mock_quotes:
            results = scrape_funds([("GF", "IWDG.L")], self.test_dir)

        # The last good price is carried for reporting, against the date it
        # really belongs to, and is kept out of history.
        self.assertEqual(list(results), [])
        self.assertEqual(results.carried, [["IWDG.L", "2025-01-19", "210.75", "GBp"]])
        self.assertEqual(len(results.failures), 1)
        self.assertIn("IWDG.L", results.failures[0])
        self.assertEqual(mock_quotes.call_count, 3)

    def test_write_results_default_data_dir(self):
        """Test write_results with default data directory."""
        # Create a temporary funds file
        test_results = [["TEST123", "2025-01-20", "100.00"]]

        # Call without data_dir parameter (uses default)
        import scrape_fund_price

        original_data_dir = scrape_fund_price.DATA_DIR
        try:
            scrape_fund_price.DATA_DIR = self.test_dir
            write_results(test_results)

            # Verify files were created in default location
            latest_csv = os.path.join(self.test_dir, "latest_prices.csv")
            self.assertTrue(os.path.exists(latest_csv))
        finally:
            scrape_fund_price.DATA_DIR = original_data_dir

    @patch("scrape_fund_price.write_summary")
    @patch("scrape_fund_price.read_fx_pairs", return_value=[])
    @patch("scrape_fund_price.parse_arguments")
    @patch("scrape_fund_price.read_fund_specs")
    @patch("scrape_fund_price.scrape_funds")
    @patch("scrape_fund_price.write_results")
    def test_main_function(
        self, mock_write, mock_scrape, mock_read, mock_parse, mock_pairs, mock_summary
    ):
        """Test main function orchestration."""
        # Mock the arguments to return normal mode (no history)
        mock_args = MagicMock()
        mock_args.history = None
        mock_args.backfill = False
        mock_parse.return_value = mock_args

        # Mock the functions
        mock_read.return_value = [FundSpec("FT", "TEST123", ())]
        mock_scrape.return_value = [["TEST123", "2025-01-20", "100.00", "GBP"]]

        # Call main
        main()

        # Verify all functions were called
        mock_parse.assert_called_once()
        mock_read.assert_called_once()
        mock_scrape.assert_called_once()
        mock_write.assert_called_once()

    @patch("scrape_fund_price.write_summary")
    @patch("scrape_fund_price.read_fx_pairs", return_value=[])
    @patch("scrape_fund_price.parse_arguments")
    @patch("scrape_fund_price.read_fund_specs")
    @patch("scrape_fund_price.scrape_funds")
    @patch("scrape_fund_price.write_results")
    def test_main_fails_job_when_scrape_failures_remain(
        self, mock_write, mock_scrape, mock_read, mock_parse, mock_pairs, mock_summary
    ):
        """Test main exits non-zero when fallback prices were used after failures."""
        mock_args = MagicMock()
        mock_args.history = None
        mock_args.backfill = False
        mock_parse.return_value = mock_args
        mock_read.return_value = [FundSpec("FT", "TEST123", ())]

        class FailedResults(list):
            failures = ["TEST123: timeout"]

        mock_scrape.return_value = FailedResults([["TEST123", "2025-01-20", "111.11"]])

        with self.assertRaises(SystemExit) as error:
            main()

        self.assertEqual(error.exception.code, 1)
        mock_write.assert_called_once_with(mock_scrape.return_value)


class TestFunctionalScraping(unittest.TestCase):
    """Functional tests that can run against real websites (optional)."""

    def setUp(self):
        # Without an explicit directory these write into the repository's
        # data/, leaving files such as latest_AAPL.price for a symbol that is
        # not in funds.txt.
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

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

    def test_functional_google_finance_scraping(self):
        """Functional test for the Yahoo Finance API (requires internet)."""
        results = scrape_funds([("GF", "AAPL")], self.test_dir)
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


class TestHistoricalData(unittest.TestCase):
    """Test historical data retrieval functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.test_dir)

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
        """Test fetching historical data for a valid symbol."""
        # Mock the yfinance Ticker object
        mock_hist = MagicMock()
        mock_hist.empty = False  # Indicate data was returned
        mock_hist.to_csv = MagicMock()
        mock_ticker.return_value.history.return_value = mock_hist

        result = fetch_historical_data(
            "AAPL", "2024-01-01", "2024-12-31", self.test_dir
        )

        # Verify the function was called correctly
        mock_ticker.assert_called_once_with("AAPL")
        mock_ticker.return_value.history.assert_called_once_with(
            start="2024-01-01", end="2024-12-31"
        )

        # Verify result contains expected filename
        self.assertIn("history_AAPL", result)
        self.assertTrue(result.endswith(".csv"))

    @patch("scrape_fund_price.yf.Ticker")
    def test_fetch_historical_data_invalid_symbol(self, mock_ticker):
        """Test fetching historical data for an invalid symbol."""
        # Mock the yfinance Ticker to raise an exception
        mock_ticker.return_value.history.side_effect = Exception("Invalid symbol")

        result = fetch_historical_data(
            "INVALID_XYZ", "2024-01-01", "2024-12-31", self.test_dir
        )

        # Should return error message
        self.assertTrue(result.startswith("Error:"))

    def test_fetch_historical_data_invalid_date_format(self):
        """Test fetching historical data with invalid date format."""
        result = fetch_historical_data(
            "AAPL", "01-01-2024", "2024-12-31", self.test_dir
        )

        # Should return error message about date format
        self.assertTrue(result.startswith("Error:"))
        self.assertIn("date", result.lower())

    def test_fetch_historical_data_invalid_end_date_format(self):
        """Test fetching historical data with a malformed end date."""
        result = fetch_historical_data("AAPL", "2024-01-01", "31-12-2024")
        self.assertEqual(result, "Error: Invalid end date format. Use YYYY-MM-DD")

    @patch("scrape_fund_price.yf.Ticker")
    def test_fetch_historical_data_empty_range_returns_error(self, mock_ticker):
        """Test a date range yielding no rows reports no data found."""
        mock_hist = MagicMock()
        mock_hist.empty = True
        mock_ticker.return_value.history.return_value = mock_hist
        result = fetch_historical_data("AAPL", "2024-01-01", "2024-01-02")
        self.assertEqual(result, "Error: No data found for symbol AAPL")

    def test_fetch_historical_data_start_after_end(self):
        """Test fetching historical data with start date after end date."""
        result = fetch_historical_data(
            "AAPL", "2024-12-31", "2024-01-01", self.test_dir
        )

        # Should return error message
        self.assertTrue(result.startswith("Error:"))
        self.assertIn("start", result.lower())


class TestPriceFallbackSources(unittest.TestCase):
    """Test the last-known-price fallback chain used when fetches fail."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.test_dir)

    def _write_csv(self, name, rows):
        path = os.path.join(self.test_dir, name)
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Fund", "Date", "Price"])
            writer.writerows(rows)
        return path

    def test_read_latest_csv_price_returns_usable_price(self):
        """Test latest_prices.csv supplies a fallback price for a known fund."""
        self._write_csv("latest_prices.csv", [["AAPL", "2026-01-01", "150.25"]])
        self.assertEqual(read_latest_csv_price("AAPL", self.test_dir), "150.25")

    def test_read_latest_csv_price_skips_unusable_values(self):
        """Test error and N/A entries are not reused as prices."""
        self._write_csv(
            "latest_prices.csv",
            [
                ["AAPL", "2026-01-01", "Error: timeout"],
                ["MSFT", "2026-01-01", "N/A"],
            ],
        )
        self.assertIsNone(read_latest_csv_price("AAPL", self.test_dir))
        self.assertIsNone(read_latest_csv_price("MSFT", self.test_dir))

    def test_read_latest_csv_price_unknown_fund_returns_none(self):
        """Test a fund absent from latest_prices.csv yields no fallback."""
        self._write_csv("latest_prices.csv", [["AAPL", "2026-01-01", "150.25"]])
        self.assertIsNone(read_latest_csv_price("TSLA", self.test_dir))

    def test_read_history_price_returns_most_recent_usable(self):
        """Test history fallback prefers the last usable row for the fund."""
        self._write_csv(
            "prices_history.csv",
            [
                ["AAPL", "2026-01-01", "100.00"],
                ["AAPL", "2026-01-02", "110.00"],
                ["MSFT", "2026-01-02", "200.00"],
            ],
        )
        self.assertEqual(read_history_price("AAPL", self.test_dir), "110.00")

    def test_read_history_price_all_unusable_returns_none(self):
        """Test history with only error rows provides no fallback price."""
        self._write_csv(
            "prices_history.csv",
            [
                ["AAPL", "2026-01-01", "Error: timeout"],
                ["AAPL", "2026-01-02", "N/A"],
            ],
        )
        self.assertIsNone(read_history_price("AAPL", self.test_dir))

    def test_get_last_known_price_prefers_price_file_over_csv(self):
        """Test the fallback chain checks the per-fund price file first."""
        with open(os.path.join(self.test_dir, "latest_AAPL.price"), "w") as f:
            f.write("999.99\n")
        self._write_csv("latest_prices.csv", [["AAPL", "2026-01-01", "150.25"]])
        self.assertEqual(get_last_known_price("AAPL", self.test_dir), "999.99")

    def test_get_last_known_price_falls_through_to_history(self):
        """Test the chain reaches prices_history.csv when earlier sources are unusable."""
        self._write_csv("latest_prices.csv", [["AAPL", "2026-01-01", "Error: timeout"]])
        self._write_csv("prices_history.csv", [["AAPL", "2025-12-31", "123.45"]])
        self.assertEqual(get_last_known_price("AAPL", self.test_dir), "123.45")

    def test_get_last_known_price_returns_none_when_nothing_stored(self):
        """Test an unknown fund with no stored data has no fallback."""
        self.assertIsNone(get_last_known_price("AAPL", self.test_dir))


class TestMainEntryPoint(unittest.TestCase):
    """Test the main() command-line entry point."""

    @patch("builtins.print")
    @patch("scrape_fund_price.parse_arguments")
    def test_main_history_without_start_date_errors(self, mock_args, mock_print):
        """Test --history without --start reports an error and stops."""
        mock_args.return_value = MagicMock(
            history="AAPL", start=None, end=None, backfill=False
        )
        main()
        mock_print.assert_called_once_with(
            "Error: --start date is required when using --history"
        )

    @patch("builtins.print")
    @patch("scrape_fund_price.fetch_historical_data")
    @patch("scrape_fund_price.parse_arguments")
    def test_main_history_success_prints_path(self, mock_args, mock_fetch, mock_print):
        """Test successful historical retrieval reports the saved file."""
        mock_args.return_value = MagicMock(
            history="AAPL", start="2024-01-01", end=None, backfill=False
        )
        mock_fetch.return_value = "data/history_AAPL_2024-01-01_2024-12-31.csv"
        main()
        mock_fetch.assert_called_once_with("AAPL", "2024-01-01", None)
        mock_print.assert_called_once_with(
            "Historical data saved to: data/history_AAPL_2024-01-01_2024-12-31.csv"
        )

    @patch("builtins.print")
    @patch("scrape_fund_price.fetch_historical_data")
    @patch("scrape_fund_price.parse_arguments")
    def test_main_history_error_is_reported(self, mock_args, mock_fetch, mock_print):
        """Test a failed historical retrieval surfaces the error message."""
        mock_args.return_value = MagicMock(
            history="BADSYM", start="2024-01-01", end=None, backfill=False
        )
        mock_fetch.return_value = "Error: No data found for symbol BADSYM"
        main()
        mock_print.assert_called_once_with("Error: No data found for symbol BADSYM")


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
    """Test dated quote retrieval from the Yahoo daily-bar route."""

    def _frame(self, rows):
        import pandas as pd

        idx = pd.to_datetime([d for d, _ in rows])
        return pd.DataFrame({"Close": [c for _, c in rows]}, index=idx)

    def _ticker(self, mock_ticker, rows, currency="GBP"):
        inst = MagicMock()
        inst.history.return_value = self._frame(rows)
        inst.fast_info = {"currency": currency}
        mock_ticker.return_value = inst
        return inst

    @patch("scrape_fund_price.yf.Ticker")
    def test_returns_dated_quotes(self, mock_ticker):
        """Test each bar becomes a Quote carrying the bar's own date."""
        self._ticker(
            mock_ticker, [("2026-09-17", 192.42999267578125), ("2026-09-18", 193.5)]
        )
        quotes = fetch_yahoo_quotes("0P00000YAN", "2026-09-10")
        self.assertEqual(len(quotes), 2)
        self.assertEqual(quotes[0], Quote("2026-09-17", "192.43", "GBP"))
        self.assertEqual(quotes[1].date, "2026-09-18")

    @patch("scrape_fund_price.yf.Ticker")
    def test_requests_unadjusted_close(self, mock_ticker):
        """Test history is requested unadjusted so prices match those snapped."""
        inst = self._ticker(mock_ticker, [("2026-09-18", 7.15)])
        fetch_yahoo_quotes("IDTG.L", "2026-09-10", "2026-09-19")
        kwargs = inst.history.call_args.kwargs
        self.assertFalse(kwargs["auto_adjust"])
        self.assertEqual(kwargs["start"], "2026-09-10")
        self.assertEqual(kwargs["end"], "2026-09-19")

    @patch("scrape_fund_price.yf.Ticker")
    def test_preserves_pence_currency(self, mock_ticker):
        """Test GBp is not silently normalised to GBP."""
        self._ticker(mock_ticker, [("2026-09-18", 6317.0)], currency="GBp")
        self.assertEqual(fetch_yahoo_quotes("SGLN.L", "2026-09-10")[0].currency, "GBp")

    @patch("scrape_fund_price.yf.Ticker")
    def test_drops_rows_without_a_price(self, mock_ticker):
        """Test NaN closes are skipped rather than stored."""
        self._ticker(mock_ticker, [("2026-09-17", float("nan")), ("2026-09-18", 7.15)])
        quotes = fetch_yahoo_quotes("IDTG.L", "2026-09-10")
        self.assertEqual([q.date for q in quotes], ["2026-09-18"])

    @patch("scrape_fund_price.yf.Ticker")
    def test_empty_history_returns_no_quotes(self, mock_ticker):
        """Test an empty result is not an error."""
        self._ticker(mock_ticker, [])
        self.assertEqual(fetch_yahoo_quotes("IDTG.L", "2026-09-10"), [])

    @patch("scrape_fund_price.yf.Ticker")
    def test_exception_propagates_to_retry_wrapper(self, mock_ticker):
        """Test transport errors are raised so fetch_with_retries can retry."""
        mock_ticker.side_effect = Exception("Network error")
        with self.assertRaises(Exception):
            fetch_yahoo_quotes("IDTG.L", "2026-09-10")

    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_fetch_price_api_uses_latest_quote(self, mock_quotes):
        """Test the price API wrapper returns the newest quote, not .info."""
        mock_quotes.return_value = [
            Quote("2026-09-16", "192.23", "USD"),
            Quote("2026-09-17", "192.43", "USD"),
        ]
        self.assertEqual(fetch_price_api("0P00000YAN"), "192.43")

    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_fetch_price_api_reports_missing_price(self, mock_quotes):
        """Test the error contract is kept when no quotes come back."""
        mock_quotes.return_value = []
        self.assertTrue(fetch_price_api("BADSYM").startswith("Error:"))

    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_fetch_price_api_reports_exception(self, mock_quotes):
        """Test exceptions keep the "Error: <message>" contract."""
        mock_quotes.side_effect = Exception("Network error")
        price = fetch_price_api("IDTG.L")
        self.assertTrue(price.startswith("Error:"))
        self.assertIn("Network error", price)


FT_PAGE = """
<html><head><title>Fund</title></head><body>
<div class="mod-ui-data-list__label">Price (GBP)</div>
<div data-mod-config="{&quot;symbol&quot;:&quot;28305998&quot;,&quot;period&quot;:&quot;day&quot;}"></div>
</body></html>
"""

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
    """Test dated quote retrieval from the FT historical-prices endpoint."""

    def _responses(self, page=FT_PAGE, rows=FT_ROWS):
        page_resp = MagicMock()
        page_resp.text = page
        page_resp.raise_for_status.return_value = None
        ajax_resp = MagicMock()
        ajax_resp.json.return_value = {"html": rows}
        ajax_resp.raise_for_status.return_value = None
        return [page_resp, ajax_resp]

    @patch("scrape_fund_price.requests.get")
    def test_returns_dated_quotes_with_currency(self, mock_get):
        """Test rows become Quotes carrying the FT price date and currency."""
        mock_get.side_effect = self._responses()
        quotes = fetch_ft_quotes("GB00B1FXTF86", "2026-09-01")
        self.assertEqual(len(quotes), 2)
        self.assertEqual(quotes[0].date, "2026-09-17")
        self.assertEqual(quotes[1].date, "2026-09-18")
        self.assertEqual(quotes[1].currency, "GBP")

    @patch("scrape_fund_price.requests.get")
    def test_uses_close_not_open(self, mock_get):
        """Test the closing price is taken, not the opening price."""
        mock_get.side_effect = self._responses()
        quotes = fetch_ft_quotes("GB00B1FXTF86", "2026-09-01")
        self.assertEqual(quotes[1].price, "7.15")

    @patch("scrape_fund_price.requests.get")
    def test_strips_thousands_separators_without_float_conversion(self, mock_get):
        """Test FT text prices keep their exact digits, commas removed."""
        mock_get.side_effect = self._responses()
        quotes = fetch_ft_quotes("GB00B1FXTF86", "2026-09-01")
        self.assertEqual(quotes[0].price, "1234.5600")

    @patch("scrape_fund_price.requests.get")
    def test_requests_endpoint_with_slash_dates(self, mock_get):
        """Test the ajax endpoint receives YYYY/MM/DD dates and the xid."""
        mock_get.side_effect = self._responses()
        fetch_ft_quotes("GB00B1FXTF86", "2026-09-01", "2026-09-20")
        ajax_url = mock_get.call_args_list[1].args[0]
        self.assertIn("startDate=2026/09/01", ajax_url)
        self.assertIn("endDate=2026/09/20", ajax_url)
        self.assertIn("symbol=28305998", ajax_url)

    @patch("scrape_fund_price.requests.get")
    def test_missing_internal_id_raises(self, mock_get):
        """Test a page without the internal id is an error, not empty data."""
        mock_get.side_effect = self._responses(page="<html>no config here</html>")
        with self.assertRaises(Exception):
            fetch_ft_quotes("GB00B1FXTF86", "2026-09-01")

    @patch("scrape_fund_price.requests.get")
    def test_no_rows_raises(self, mock_get):
        """Test an empty result set is an error so the fallback can run."""
        mock_get.side_effect = self._responses(rows="")
        with self.assertRaises(Exception):
            fetch_ft_quotes("GB00B1FXTF86", "2026-09-01")

    @patch("scrape_fund_price.requests.get")
    def test_missing_currency_label_is_tolerated(self, mock_get):
        """Test quotes are still returned when no currency label is present."""
        page = FT_PAGE.replace("Price (GBP)", "Price")
        mock_get.side_effect = self._responses(page=page)
        self.assertEqual(fetch_ft_quotes("GB00B1FXTF86", "2026-09-01")[0].currency, "")


class TestHistoryUpsert(unittest.TestCase):
    """Test (Fund, Date) keyed storage with upsert semantics."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.history = os.path.join(self.test_dir, "prices_history.csv")
        self.latest = os.path.join(self.test_dir, "latest_prices.csv")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _rows(self, path):
        with open(path, "r", newline="") as f:
            return list(csv.reader(f))

    def test_history_has_currency_column(self):
        """Test Currency is appended after Price, keeping column order stable."""
        write_results([["AAA", "2026-09-17", "1.50", "GBp"]], self.test_dir)
        self.assertEqual(
            self._rows(self.history)[0], ["Fund", "Date", "Price", "Currency"]
        )

    def test_same_fund_and_date_is_replaced_not_duplicated(self):
        """Test a corrected price overwrites the row with the same key."""
        write_results([["AAA", "2026-09-17", "1.50", "GBP"]], self.test_dir)
        write_results([["AAA", "2026-09-17", "1.55", "GBP"]], self.test_dir)
        rows = self._rows(self.history)[1:]
        self.assertEqual(rows, [["AAA", "2026-09-17", "1.55", "GBP"]])

    def test_same_fund_different_dates_both_kept(self):
        """Test distinct price dates accumulate."""
        write_results(
            [
                ["AAA", "2026-09-17", "1.50", "GBP"],
                ["AAA", "2026-09-18", "1.60", "GBP"],
            ],
            self.test_dir,
        )
        self.assertEqual(len(self._rows(self.history)[1:]), 2)

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
        rows = self._rows(self.history)[1:]
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
        first = open(self.history, "rb").read()
        write_results(rows, self.test_dir)
        self.assertEqual(open(self.history, "rb").read(), first)

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
        rows = self._rows(self.history)[1:]
        self.assertEqual([r[0] for r in rows], ["CCC"])

    def test_legacy_three_column_history_is_upgraded(self):
        """Test pre-existing rows without a currency remain readable."""
        with open(self.history, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Fund", "Date", "Price"])
            w.writerow(["OLD", "2026-09-01", "9.99"])
        write_results([["AAA", "2026-09-17", "1.50", "GBP"]], self.test_dir)
        rows = self._rows(self.history)
        self.assertEqual(rows[0], ["Fund", "Date", "Price", "Currency"])
        self.assertIn(["OLD", "2026-09-01", "9.99", ""], rows)

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
        rows = self._rows(self.latest)
        self.assertEqual(rows[0], ["Fund", "Date", "Price", "Currency"])
        self.assertEqual(rows[1:], [["AAA", "2026-09-18", "1.60", "GBP"]])

    def test_rolling_window_filters_on_price_date(self):
        """Test the 90-day window is measured against price dates."""
        write_results(
            [
                ["OLD", "2026-06-01", "1.00", "GBP"],
                ["NEW", "2026-09-18", "2.00", "GBP"],
            ],
            self.test_dir,
        )
        rolling = os.path.join(self.test_dir, "prices_history_90_days.csv")
        funds = [r[0] for r in self._rows(rolling)[1:]]
        self.assertEqual(funds, ["NEW"])


class TestWindowedScraping(unittest.TestCase):
    """Test scrape_funds over dated windows, and lazy browser startup."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch("scrape_fund_price.sync_playwright")
    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_emits_a_row_per_quote_with_currency(self, mock_quotes, mock_pw):
        """Test every quote in the window becomes a dated result row."""
        mock_quotes.return_value = [
            Quote("2026-09-17", "1.50", "GBp"),
            Quote("2026-09-18", "1.60", "GBp"),
        ]
        results = scrape_funds([("GF", "SGLN.L")], self.test_dir)
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
        scrape_funds([("GF", "QQQ"), ("FT", "GB00B1FXTF86")], self.test_dir)
        mock_pw.assert_not_called()

    def test_ft_and_api_sources_do_not_require_a_browser(self):
        """Test source_requires_browser reflects the HTTP-only routes."""
        self.assertFalse(source_requires_browser("FT", "GB00B1FXTF86"))
        self.assertFalse(source_requires_browser("GF", "QQQ"))
        self.assertTrue(source_requires_browser("YH", "IDTG.L"))

    @patch("scrape_fund_price.sync_playwright")
    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_total_failure_writes_no_history_row(self, mock_quotes, mock_pw):
        """Test a fund that cannot be fetched contributes no dated row."""
        mock_quotes.side_effect = Exception("Network error")
        results = scrape_funds([("GF", "QQQ")], self.test_dir)
        self.assertEqual(list(results), [])
        self.assertEqual(len(results.failures), 1)
        self.assertIn("QQQ", results.failures[0])

    @patch("scrape_fund_price.sync_playwright")
    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_failed_fund_keeps_its_last_known_price_file(self, mock_quotes, mock_pw):
        """Test the per-fund price file is not overwritten with an error."""
        with open(os.path.join(self.test_dir, "latest_QQQ.price"), "w") as f:
            f.write("700.00\n")
        mock_quotes.side_effect = Exception("Network error")
        scrape_funds([("GF", "QQQ")], self.test_dir)
        with open(os.path.join(self.test_dir, "latest_QQQ.price")) as f:
            self.assertEqual(f.read().strip(), "700.00")

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


class TestFailureDoesNotSuppressOutput(unittest.TestCase):
    """Test a partially failed run still publishes everything it obtained."""

    @patch("scrape_fund_price.write_summary")
    @patch("scrape_fund_price.read_fx_pairs", return_value=[])
    @patch("scrape_fund_price.write_results")
    @patch("scrape_fund_price.scrape_funds")
    @patch("scrape_fund_price.read_fund_specs")
    @patch("scrape_fund_price.parse_arguments")
    def test_results_are_written_before_failure_is_signalled(
        self, mock_args, mock_read, mock_scrape, mock_write, mock_pairs, mock_summary
    ):
        """Test output is written even when some funds failed."""
        mock_args.return_value = MagicMock(
            history=None, start=None, end=None, backfill=False
        )
        mock_read.return_value = [("GF", "QQQ"), ("GF", "GRAB")]
        results = ScrapeResults(
            [["QQQ", "2026-09-18", "721.45", "USD"]],
            failures=["GRAB: Error: Timeout"],
        )
        mock_scrape.return_value = results

        with self.assertRaises(SystemExit):
            main()

        # The write must happen, otherwise a single failing fund would
        # discard a whole day of good prices.
        mock_write.assert_called_once_with(results)

    @patch("scrape_fund_price.write_summary")
    @patch("scrape_fund_price.read_fx_pairs", return_value=[])
    @patch("scrape_fund_price.write_results")
    @patch("scrape_fund_price.scrape_funds")
    @patch("scrape_fund_price.read_fund_specs")
    @patch("scrape_fund_price.parse_arguments")
    def test_clean_run_does_not_exit_non_zero(
        self, mock_args, mock_read, mock_scrape, mock_write, mock_pairs, mock_summary
    ):
        """Test a run with no failures completes normally."""
        mock_args.return_value = MagicMock(
            history=None, start=None, end=None, backfill=False
        )
        mock_read.return_value = [("GF", "QQQ")]
        mock_scrape.return_value = ScrapeResults(
            [["QQQ", "2026-09-18", "721.45", "USD"]]
        )

        main()

        mock_write.assert_called_once()


class TestFundSpecParsing(unittest.TestCase):
    """Test funds.txt parsing, including aliases and validation."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _write(self, text):
        path = os.path.join(self.test_dir, "funds.txt")
        with open(path, "w") as f:
            f.write(text)
        return path

    def test_two_field_line_has_no_aliases(self):
        """Test existing config lines keep their meaning."""
        specs = read_fund_specs(self._write("YA,QQQ\n"))
        self.assertEqual(specs, [FundSpec("YA", "QQQ", ())])
        self.assertEqual(specs[0].publish_ids, ("QQQ",))

    def test_third_field_adds_an_alias(self):
        """Test a fund can publish under a second identifier."""
        specs = read_fund_specs(self._write("GF,0P00000YAN,JFM0003373\n"))
        self.assertEqual(specs[0].lookup_id, "0P00000YAN")
        self.assertEqual(specs[0].aliases, ("JFM0003373",))
        self.assertEqual(specs[0].publish_ids, ("0P00000YAN", "JFM0003373"))

    def test_multiple_aliases_are_semicolon_separated(self):
        """Test more than one alias can be given."""
        specs = read_fund_specs(self._write("GF,ABC,ONE;TWO\n"))
        self.assertEqual(specs[0].publish_ids, ("ABC", "ONE", "TWO"))

    def test_whitespace_and_blank_lines_are_ignored(self):
        """Test untidy config files still parse."""
        specs = read_fund_specs(self._write("\n  YA , QQQ , ALIAS \n\n  \nFT,ISIN1\n"))
        self.assertEqual(
            specs, [FundSpec("YA", "QQQ", ("ALIAS",)), FundSpec("FT", "ISIN1", ())]
        )

    def test_comments_are_stripped(self):
        """Test the inline comments the docs have always shown actually work."""
        specs = read_fund_specs(
            self._write("# a heading\nFT,GB00B1FXTF86    # Financial Times\n")
        )
        self.assertEqual(specs, [FundSpec("FT", "GB00B1FXTF86", ())])

    def test_read_fund_ids_still_returns_pairs(self):
        """Test the existing helper keeps its shape for existing callers."""
        path = self._write("YA,0P00000YAN,JFM0003373\nFT,ISIN1\n")
        self.assertEqual(read_fund_ids(path), [("YA", "0P00000YAN"), ("FT", "ISIN1")])

    def test_line_with_one_field_is_rejected(self):
        """Test an incomplete line names its line number."""
        with self.assertRaises(ValueError) as error:
            read_fund_specs(self._write("GF,QQQ\nJUSTONE\n"))
        self.assertIn("line 2", str(error.exception))

    def test_empty_source_or_identifier_is_rejected(self):
        """Test blank fields are not silently accepted."""
        with self.assertRaises(ValueError) as error:
            read_fund_specs(self._write("GF,QQQ\n,MISSING_SOURCE\n"))
        self.assertIn("line 2", str(error.exception))

    def test_empty_alias_is_rejected(self):
        """Test a stray separator is treated as a typo, not an empty alias."""
        with self.assertRaises(ValueError) as error:
            read_fund_specs(self._write("GF,ABC,ONE;;TWO\n"))
        self.assertIn("line 1", str(error.exception))

    def test_alias_matching_its_own_lookup_id_is_rejected(self):
        """Test a self-referencing alias is rejected rather than double-writing."""
        with self.assertRaises(ValueError) as error:
            read_fund_specs(self._write("GF,ABC,ABC\n"))
        self.assertIn("line 1", str(error.exception))

    def test_duplicate_identifier_across_lines_is_rejected(self):
        """Test a repeated fund cannot silently produce duplicate rows."""
        with self.assertRaises(ValueError) as error:
            read_fund_specs(self._write("GF,QQQ\nFT,ISIN1\nGF,QQQ\n"))
        self.assertIn("line 3", str(error.exception))

    def test_alias_colliding_with_another_funds_id_is_rejected(self):
        """Test an alias cannot shadow a different instrument."""
        with self.assertRaises(ValueError) as error:
            read_fund_specs(self._write("GF,QQQ\nGF,ABC,QQQ\n"))
        self.assertIn("line 2", str(error.exception))


class TestAliasPublishing(unittest.TestCase):
    """Test that one fetch publishes under every configured identifier."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch("scrape_fund_price.sync_playwright")
    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_price_is_fetched_once_for_all_identifiers(self, mock_quotes, mock_pw):
        """Test aliases cost no extra network calls."""
        mock_quotes.return_value = [Quote("2026-09-17", "192.43", "USD")]
        scrape_funds(
            [FundSpec("GF", "0P00000YAN", ("JFM0003373", "EXTRA"))], self.test_dir
        )
        self.assertEqual(mock_quotes.call_count, 1)

    @patch("scrape_fund_price.sync_playwright")
    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_each_identifier_gets_an_identical_row(self, mock_quotes, mock_pw):
        """Test every identifier records the same date, price and currency."""
        mock_quotes.return_value = [Quote("2026-09-17", "192.43", "USD")]
        results = scrape_funds(
            [FundSpec("GF", "0P00000YAN", ("JFM0003373",))], self.test_dir
        )
        self.assertEqual(
            list(results),
            [
                ["0P00000YAN", "2026-09-17", "192.43", "USD"],
                ["JFM0003373", "2026-09-17", "192.43", "USD"],
            ],
        )

    @patch("scrape_fund_price.sync_playwright")
    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_a_price_file_is_written_per_identifier(self, mock_quotes, mock_pw):
        """Test per-fund price files exist for aliases too."""
        mock_quotes.return_value = [Quote("2026-09-17", "192.43", "USD")]
        scrape_funds([FundSpec("GF", "0P00000YAN", ("JFM0003373",))], self.test_dir)
        for fund_id in ("0P00000YAN", "JFM0003373"):
            path = os.path.join(self.test_dir, f"latest_{fund_id}.price")
            with open(path) as f:
                self.assertEqual(f.read().strip(), "192.43")

    @patch("scrape_fund_price.sync_playwright")
    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_fallback_uses_an_alias_stored_price(self, mock_quotes, mock_pw):
        """Test day-one failure can fall back to the alias's existing history.

        The lookup identifier is new and has nothing stored, while the alias
        carries the fund's whole history.
        """
        history = os.path.join(self.test_dir, "prices_history.csv")
        with open(history, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Fund", "Date", "Price", "Currency"])
            writer.writerow(["JFM0003373", "2026-09-17", "192.43", "USD"])

        mock_quotes.side_effect = Exception("Network error")
        results = scrape_funds(
            [FundSpec("GF", "0P00000YAN", ("JFM0003373",))], self.test_dir
        )

        self.assertEqual(list(results), [])
        self.assertEqual(
            results.carried,
            [
                ["0P00000YAN", "2026-09-17", "192.43", "USD"],
                ["JFM0003373", "2026-09-17", "192.43", "USD"],
            ],
        )

    @patch("scrape_fund_price.sync_playwright")
    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_failure_is_reported_once_per_fund(self, mock_quotes, mock_pw):
        """Test an aliased fund is not reported twice for one failure."""
        mock_quotes.side_effect = Exception("Network error")
        results = scrape_funds(
            [FundSpec("GF", "0P00000YAN", ("JFM0003373",))], self.test_dir
        )
        self.assertEqual(len(results.failures), 1)

    @patch("scrape_fund_price.sync_playwright")
    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_plain_tuples_are_still_accepted(self, mock_quotes, mock_pw):
        """Test existing callers passing (source, id) pairs keep working."""
        mock_quotes.return_value = [Quote("2026-09-18", "721.45", "USD")]
        results = scrape_funds([("GF", "QQQ")], self.test_dir)
        self.assertEqual(list(results), [["QQQ", "2026-09-18", "721.45", "USD"]])


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


class TestBackfillRebuild(unittest.TestCase):
    """Test the delete-then-insert rebuild rule."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.history = os.path.join(self.test_dir, "prices_history.csv")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _seed(self, rows, header=("Fund", "Date", "Price", "Currency")):
        with open(self.history, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(list(header))
            writer.writerows(rows)

    def _rows(self):
        with open(self.history, newline="") as f:
            return [r for r in csv.reader(f)][1:]

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_carry_forward_rows_are_removed(self, mock_quotes):
        """Test rows on dates the source never reports do not survive.

        This is why the rebuild deletes rather than upserting: a weekend
        carry-forward has no incoming row to replace it.
        """
        self._seed(
            [
                ["QQQ", "2026-09-18", "721.45", ""],
                ["QQQ", "2026-09-19", "721.45", ""],  # Saturday carry-forward
                ["QQQ", "2026-09-20", "721.45", ""],  # Sunday carry-forward
            ]
        )
        mock_quotes.return_value = [Quote("2026-09-18", "721.45", "USD")]

        backfill_history([FundSpec("GF", "QQQ", ())], "2026-09-01", self.test_dir)

        self.assertEqual(self._rows(), [["QQQ", "2026-09-18", "721.45", "USD"]])

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_failed_instrument_keeps_its_existing_rows(self, mock_quotes):
        """Test a fetch failure never destroys unreplaceable data."""
        self._seed([["QQQ", "2026-09-18", "721.45", "USD"]])
        mock_quotes.side_effect = Exception("Network error")

        report = backfill_history(
            [FundSpec("GF", "QQQ", ())], "2026-09-01", self.test_dir
        )

        self.assertEqual(self._rows(), [["QQQ", "2026-09-18", "721.45", "USD"]])
        self.assertEqual(len(report.failures), 1)

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_one_failure_does_not_block_other_instruments(self, mock_quotes):
        """Test instruments are rebuilt independently."""
        self._seed(
            [
                ["QQQ", "2026-09-19", "700.00", ""],
                ["GRAB", "2026-09-19", "2.50", ""],
            ]
        )

        def side_effect(source, fund_id, start, end=None, browser=None):
            if fund_id == "QQQ":
                raise Exception("Network error")
            return [Quote("2026-09-18", "2.795", "USD")]

        mock_quotes.side_effect = side_effect

        backfill_history(
            [FundSpec("GF", "QQQ", ()), FundSpec("GF", "GRAB", ())],
            "2026-09-01",
            self.test_dir,
        )

        rows = self._rows()
        self.assertIn(["QQQ", "2026-09-19", "700.00", ""], rows)
        self.assertIn(["GRAB", "2026-09-18", "2.795", "USD"], rows)
        self.assertNotIn(["GRAB", "2026-09-19", "2.50", ""], rows)

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_rows_before_the_start_date_are_preserved(self, mock_quotes):
        """Test the rebuild only touches the requested range."""
        self._seed(
            [
                ["QQQ", "2022-06-01", "300.00", "USD"],
                ["QQQ", "2026-09-19", "700.00", ""],
            ]
        )
        mock_quotes.return_value = [Quote("2026-09-18", "721.45", "USD")]

        backfill_history([FundSpec("GF", "QQQ", ())], "2023-01-01", self.test_dir)

        rows = self._rows()
        self.assertIn(["QQQ", "2022-06-01", "300.00", "USD"], rows)
        self.assertNotIn(["QQQ", "2026-09-19", "700.00", ""], rows)

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_unconfigured_identifiers_are_preserved(self, mock_quotes):
        """Test a fund removed from funds.txt keeps its recorded history."""
        self._seed(
            [
                ["RETIRED", "2026-09-18", "1.23", "GBP"],
                ["QQQ", "2026-09-19", "700.00", ""],
            ]
        )
        mock_quotes.return_value = [Quote("2026-09-18", "721.45", "USD")]

        backfill_history([FundSpec("GF", "QQQ", ())], "2023-01-01", self.test_dir)

        self.assertIn(["RETIRED", "2026-09-18", "1.23", "GBP"], self._rows())

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_aliases_are_rebuilt_from_a_single_fetch(self, mock_quotes):
        """Test both identifiers get the same rebuilt series."""
        mock_quotes.return_value = [Quote("2026-09-17", "192.43", "USD")]

        backfill_history(
            [FundSpec("GF", "0P00000YAN", ("JFM0003373",))],
            "2023-01-01",
            self.test_dir,
        )

        self.assertEqual(mock_quotes.call_count, 1)
        rows = self._rows()
        self.assertIn(["0P00000YAN", "2026-09-17", "192.43", "USD"], rows)
        self.assertIn(["JFM0003373", "2026-09-17", "192.43", "USD"], rows)

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_rebuild_is_idempotent(self, mock_quotes):
        """Test re-running the rebuild produces no diff."""
        mock_quotes.return_value = [
            Quote("2026-09-17", "192.43", "USD"),
            Quote("2026-09-18", "193.00", "USD"),
        ]
        specs = [FundSpec("GF", "0P00000YAN", ("JFM0003373",))]

        backfill_history(specs, "2023-01-01", self.test_dir)
        first = open(self.history, "rb").read()
        backfill_history(specs, "2023-01-01", self.test_dir)

        self.assertEqual(open(self.history, "rb").read(), first)

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_derived_files_are_regenerated(self, mock_quotes):
        """Test latest prices, the rolling window and price files follow."""
        mock_quotes.return_value = [
            Quote("2026-09-17", "192.00", "USD"),
            Quote("2026-09-18", "192.43", "USD"),
        ]

        backfill_history([FundSpec("GF", "AAA", ())], "2023-01-01", self.test_dir)

        with open(os.path.join(self.test_dir, "latest_prices.csv"), newline="") as f:
            latest = [r for r in csv.reader(f)][1:]
        self.assertEqual(latest, [["AAA", "2026-09-18", "192.43", "USD"]])

        with open(os.path.join(self.test_dir, "latest_AAA.price")) as f:
            self.assertEqual(f.read().strip(), "192.43")

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_legacy_three_column_history_is_rebuilt(self, mock_quotes):
        """Test a pre-SPEC-003 file is readable and comes out with currencies."""
        self._seed([["QQQ", "2026-09-19", "700.00"]], header=("Fund", "Date", "Price"))
        mock_quotes.return_value = [Quote("2026-09-18", "721.45", "USD")]

        backfill_history([FundSpec("GF", "QQQ", ())], "2023-01-01", self.test_dir)

        self.assertEqual(self._rows(), [["QQQ", "2026-09-18", "721.45", "USD"]])

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_unusable_prices_are_dropped_everywhere(self, mock_quotes):
        """Test stored error strings do not survive a rebuild."""
        self._seed(
            [
                ["RETIRED", "2026-09-18", "Error: Timeout", ""],
                ["QQQ", "2026-09-19", "N/A", ""],
            ]
        )
        mock_quotes.return_value = [Quote("2026-09-18", "721.45", "USD")]

        backfill_history([FundSpec("GF", "QQQ", ())], "2023-01-01", self.test_dir)

        prices = [r[2] for r in self._rows()]
        self.assertNotIn("Error: Timeout", prices)
        self.assertNotIn("N/A", prices)


class TestBackfillReporting(unittest.TestCase):
    """Test the reconciliation report and sanity warnings."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_report_counts_rows_changed(self, mock_quotes):
        """Test the report says what it replaced, for review before committing."""
        history = os.path.join(self.test_dir, "prices_history.csv")
        with open(history, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Fund", "Date", "Price", "Currency"])
            writer.writerows(
                [
                    ["QQQ", "2026-09-19", "700.00", ""],
                    ["QQQ", "2026-09-20", "700.00", ""],
                ]
            )
        mock_quotes.return_value = [Quote("2026-09-18", "721.45", "USD")]

        report = backfill_history(
            [FundSpec("GF", "QQQ", ())], "2023-01-01", self.test_dir
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
            [FundSpec("GF", "QQQ", ())], "2023-01-01", self.test_dir
        )
        text = report.to_markdown()
        self.assertIn("QQQ", text)
        self.assertIn("|", text)

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_quoting_unit_change_is_flagged(self, mock_quotes):
        """Test a pence/pounds switch is surfaced rather than stored silently."""
        mock_quotes.return_value = [
            Quote("2026-09-17", "5.06", "GBP"),
            Quote("2026-09-18", "506.00", "GBp"),
        ]
        report = backfill_history(
            [FundSpec("GF", "DPYG.L", ())], "2023-01-01", self.test_dir
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
            [FundSpec("GF", "AAA", ())], "2023-01-01", self.test_dir
        )
        self.assertEqual(report.warnings, [])


class TestBackfillMainMode(unittest.TestCase):
    """Test the --backfill entry point."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch("builtins.print")
    @patch("scrape_fund_price.parse_arguments")
    def test_invalid_invocation_exits_two_without_fetching(self, mock_args, mock_print):
        """Test a bad invocation is rejected before any network call."""
        mock_args.return_value = MagicMock(backfill=True, start=None, history=None)

        with self.assertRaises(SystemExit) as error:
            main()

        self.assertEqual(error.exception.code, 2)

    @patch("builtins.print")
    @patch("scrape_fund_price.backfill_history")
    @patch("scrape_fund_price.read_fund_specs")
    @patch("scrape_fund_price.parse_arguments")
    def test_successful_backfill_prints_the_report(
        self, mock_args, mock_specs, mock_backfill, mock_print
    ):
        """Test the reconciliation report reaches stdout."""
        mock_args.return_value = MagicMock(
            backfill=True, start="2023-01-01", history=None
        )
        mock_specs.return_value = [FundSpec("GF", "QQQ", ())]
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
        mock_backfill.return_value = report

        main()

        self.assertTrue(any("QQQ" in str(c) for c in mock_print.call_args_list))

    @patch("builtins.print")
    @patch("scrape_fund_price.backfill_history")
    @patch("scrape_fund_price.read_fund_specs")
    @patch("scrape_fund_price.parse_arguments")
    def test_failures_exit_non_zero_after_writing(
        self, mock_args, mock_specs, mock_backfill, mock_print
    ):
        """Test the job fails loudly, but only after the report is produced."""
        mock_args.return_value = MagicMock(
            backfill=True, start="2023-01-01", history=None
        )
        mock_specs.return_value = [FundSpec("GF", "QQQ", ())]
        report = BackfillReport()
        report.failures.append("QQQ: Error: Timeout")
        mock_backfill.return_value = report

        with self.assertRaises(SystemExit) as error:
            main()

        self.assertEqual(error.exception.code, 1)
        self.assertTrue(mock_print.called)

    @patch("builtins.print")
    @patch("scrape_fund_price.backfill_history")
    @patch("scrape_fund_price.read_fund_specs")
    @patch("scrape_fund_price.parse_arguments")
    def test_report_is_added_to_the_actions_job_summary(
        self, mock_args, mock_specs, mock_backfill, mock_print
    ):
        """Test the report appears on the workflow run page when in Actions."""
        mock_args.return_value = MagicMock(
            backfill=True, start="2023-01-01", history=None
        )
        mock_specs.return_value = [FundSpec("GF", "QQQ", ())]
        report = BackfillReport()
        report.entries.append(
            {
                "identifier": "QQQ",
                "before": 0,
                "deleted": 0,
                "retained": 0,
                "inserted": 1,
                "first": "2026-09-18",
                "last": "2026-09-18",
                "currency": "USD",
                "status": "rebuilt",
            }
        )
        mock_backfill.return_value = report

        summary_path = os.path.join(self.test_dir, "summary.md")
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": summary_path}):
            main()

        with open(summary_path, encoding="utf-8") as f:
            written = f.read()
        self.assertIn("Backfill from 2023-01-01", written)
        self.assertIn("QQQ", written)

    @patch("builtins.print")
    @patch("scrape_fund_price.backfill_history")
    @patch("scrape_fund_price.read_fund_specs")
    @patch("scrape_fund_price.parse_arguments")
    def test_no_summary_written_outside_actions(
        self, mock_args, mock_specs, mock_backfill, mock_print
    ):
        """Test a local run does not require the Actions environment."""
        mock_args.return_value = MagicMock(
            backfill=True, start="2023-01-01", history=None
        )
        mock_specs.return_value = [FundSpec("GF", "QQQ", ())]
        mock_backfill.return_value = BackfillReport()

        env = {k: v for k, v in os.environ.items() if k != "GITHUB_STEP_SUMMARY"}
        with patch.dict(os.environ, env, clear=True):
            main()

        self.assertTrue(mock_print.called)


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


class TestBackfillPacing(unittest.TestCase):
    """Test the rebuild is polite to the unofficial FT endpoint."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch("scrape_fund_price.time.sleep")
    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_pauses_between_ft_funds(self, mock_quotes, mock_sleep):
        """Test consecutive FT fetches are spaced out."""
        mock_quotes.return_value = [Quote("2026-09-18", "7.15", "GBP")]
        backfill_history(
            [FundSpec("FT", "ISIN1", ()), FundSpec("FT", "ISIN2", ())],
            "2023-01-01",
            self.test_dir,
        )
        self.assertTrue(mock_sleep.called)

    @patch("scrape_fund_price.time.sleep")
    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_does_not_pause_for_api_funds(self, mock_quotes, mock_sleep):
        """Test the API route is not slowed down unnecessarily."""
        mock_quotes.return_value = [Quote("2026-09-18", "721.45", "USD")]
        backfill_history(
            [FundSpec("GF", "QQQ", ()), FundSpec("GF", "GRAB", ())],
            "2023-01-01",
            self.test_dir,
        )
        mock_sleep.assert_not_called()

    @patch("scrape_fund_price.time.sleep")
    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_failed_instrument_appears_in_the_report(self, mock_quotes, mock_sleep):
        """Test a failure is reported per identifier with its kept row count."""
        history = os.path.join(self.test_dir, "prices_history.csv")
        with open(history, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Fund", "Date", "Price", "Currency"])
            writer.writerow(["QQQ", "2026-09-18", "721.45", "USD"])

        mock_quotes.side_effect = Exception("Network error")
        report = backfill_history(
            [FundSpec("GF", "QQQ", ())], "2023-01-01", self.test_dir
        )

        entry = next(e for e in report.entries if e["identifier"] == "QQQ")
        self.assertEqual(entry["status"], "failed, kept existing")
        self.assertEqual(entry["before"], 1)
        self.assertEqual(entry["deleted"], 0)


class TestBackfillProtectsSourceDerivedRows(unittest.TestCase):
    """Test a flaky source cannot silently delete real trading days.

    FT's historical endpoint intermittently omits a row or two from the same
    request (893 vs 895 rows for identical queries, verified against the live
    endpoint). Delete-then-insert would drop those days on the next rebuild.
    Rows that already carry a currency were themselves source-derived, so they
    are kept when the source omits them; legacy rows, which predate the
    currency column, are still removed.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.history = os.path.join(self.test_dir, "prices_history.csv")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _seed(self, rows):
        with open(self.history, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Fund", "Date", "Price", "Currency"])
            writer.writerows(rows)

    def _rows(self):
        with open(self.history, newline="") as f:
            return [r for r in csv.reader(f)][1:]

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_previously_sourced_row_survives_an_omission(self, mock_quotes):
        """Test a day the source skipped this run is not lost."""
        self._seed(
            [
                ["ISIN1", "2025-08-14", "8.29", "GBP"],
                ["ISIN1", "2025-08-18", "8.48", "GBP"],
            ]
        )
        mock_quotes.return_value = [Quote("2025-08-18", "8.48", "GBP")]

        report = backfill_history(
            [FundSpec("FT", "ISIN1", ())], "2023-01-01", self.test_dir
        )

        self.assertIn(["ISIN1", "2025-08-14", "8.29", "GBP"], self._rows())
        entry = next(e for e in report.entries if e["identifier"] == "ISIN1")
        self.assertEqual(entry["retained"], 1)

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_legacy_rows_without_currency_are_still_removed(self, mock_quotes):
        """Test pre-SPEC-003 rows are not protected by the retention rule."""
        self._seed([["ISIN1", "2025-08-14", "8.29", ""]])
        mock_quotes.return_value = [Quote("2025-08-18", "8.48", "GBP")]

        backfill_history([FundSpec("FT", "ISIN1", ())], "2023-01-01", self.test_dir)

        self.assertEqual(self._rows(), [["ISIN1", "2025-08-18", "8.48", "GBP"]])

    @patch("scrape_fund_price.scrape_fund_quotes")
    def test_weekend_rows_are_never_retained(self, mock_quotes):
        """Test a carry-forward is removed even if it carries a currency."""
        self._seed(
            [
                ["QQQ", "2026-09-18", "721.45", "USD"],
                ["QQQ", "2026-09-19", "721.45", "USD"],  # Saturday
                ["QQQ", "2026-09-20", "721.45", "USD"],  # Sunday
            ]
        )
        mock_quotes.return_value = [Quote("2026-09-18", "721.45", "USD")]

        backfill_history([FundSpec("GF", "QQQ", ())], "2023-01-01", self.test_dir)

        self.assertEqual(self._rows(), [["QQQ", "2026-09-18", "721.45", "USD"]])


class TestFxPairConfiguration(unittest.TestCase):
    """Test fx_pairs.txt parsing and validation."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _write(self, text):
        path = os.path.join(self.test_dir, "fx_pairs.txt")
        with open(path, "w") as f:
            f.write(text)
        return path

    def test_reads_one_pair_per_line(self):
        """Test the configured pairs are read in order."""
        pairs = read_fx_pairs(self._write("NZDGBP\nSGDGBP\nUSDGBP\nHKDGBP\n"))
        self.assertEqual(pairs, ["NZDGBP", "SGDGBP", "USDGBP", "HKDGBP"])

    def test_ignores_comments_and_blank_lines(self):
        """Test the file can be annotated."""
        pairs = read_fx_pairs(self._write("# GBP per 1 unit\n\nUSDGBP   # dollar\n\n"))
        self.assertEqual(pairs, ["USDGBP"])

    def test_rejects_a_slash_separated_pair(self):
        """Test the market-convention spelling is rejected, not misread.

        'GBP/NZD' conventionally means NZD per GBP, the inverse of what is
        wanted, so accepting it would store plausible but wrong values.
        """
        with self.assertRaises(ValueError) as error:
            read_fx_pairs(self._write("GBP/NZD\n"))
        self.assertIn("line 1", str(error.exception))

    def test_rejects_lowercase_and_wrong_length(self):
        """Test only six uppercase letters are accepted."""
        for bad in ("usdgbp", "USDGB", "USDGBPX"):
            with self.assertRaises(ValueError):
                read_fx_pairs(self._write(bad + "\n"))

    def test_rejects_duplicate_pairs(self):
        """Test a repeated pair cannot produce duplicate rows."""
        with self.assertRaises(ValueError) as error:
            read_fx_pairs(self._write("USDGBP\nSGDGBP\nUSDGBP\n"))
        self.assertIn("line 3", str(error.exception))

    def test_missing_file_means_no_fx(self):
        """Test FX is optional, so an absent file is not an error."""
        self.assertEqual(read_fx_pairs(os.path.join(self.test_dir, "absent.txt")), [])


class TestFxQuoteFetching(unittest.TestCase):
    """Test FX rate retrieval."""

    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_requests_the_yahoo_fx_ticker(self, mock_quotes):
        """Test the pair is turned into Yahoo's FX ticker."""
        mock_quotes.return_value = [Quote("2026-09-18", "0.7467", "GBP")]
        fetch_fx_quotes("USDGBP", "2026-09-10")
        self.assertEqual(mock_quotes.call_args.args[0], "USDGBP=X")

    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_drops_weekend_bars(self, mock_quotes):
        """Test the transient weekend bar Yahoo shows is not stored."""
        mock_quotes.return_value = [
            Quote("2026-09-18", "0.7467", "GBP"),  # Friday
            Quote("2026-09-19", "0.7467", "GBP"),  # Saturday
            Quote("2026-09-20", "0.7470", "GBP"),  # Sunday
        ]
        quotes = fetch_fx_quotes("USDGBP", "2026-09-10")
        self.assertEqual([q.date for q in quotes], ["2026-09-18"])

    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_rates_are_stored_at_six_decimal_places(self, mock_quotes):
        """Test precision is enough for small rates such as HKDGBP."""
        mock_quotes.return_value = [Quote("2026-09-18", "0.0951234567", "GBP")]
        self.assertEqual(fetch_fx_quotes("HKDGBP", "2026-09-10")[0].price, "0.095123")

    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_rate_carries_the_pair_name(self, mock_quotes):
        """Test the quote is self-describing."""
        mock_quotes.return_value = [Quote("2026-09-18", "0.4267", "GBP")]
        self.assertEqual(fetch_fx_quotes("NZDGBP", "2026-09-10")[0].currency, "NZDGBP")

    @patch("scrape_fund_price.fetch_yahoo_quotes")
    def test_whole_number_rate_keeps_six_places(self, mock_quotes):
        """Test formatting is fixed width, not shortest representation."""
        mock_quotes.return_value = [Quote("2026-09-18", "1", "GBP")]
        self.assertEqual(fetch_fx_quotes("GBPGBP", "2026-09-10")[0].price, "1.000000")


class TestFxStorage(unittest.TestCase):
    """Test FX output files."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.history = os.path.join(self.test_dir, "fx_history.csv")
        self.latest = os.path.join(self.test_dir, "latest_fx.csv")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _rows(self, path):
        with open(path, newline="") as f:
            return list(csv.reader(f))

    def test_history_header_names_the_rate(self):
        """Test the header does not use an ambiguous GBP/xxx label."""
        write_fx_results([["USDGBP", "2026-09-18", "0.746700"]], self.test_dir)
        self.assertEqual(self._rows(self.history)[0], ["Pair", "Date", "Rate"])

    def test_same_pair_and_date_is_replaced(self):
        """Test a provisional rate is overwritten once the day completes."""
        write_fx_results([["USDGBP", "2026-09-18", "0.746000"]], self.test_dir)
        write_fx_results([["USDGBP", "2026-09-18", "0.746700"]], self.test_dir)
        self.assertEqual(
            self._rows(self.history)[1:], [["USDGBP", "2026-09-18", "0.746700"]]
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
            [(r[0], r[1]) for r in self._rows(self.history)[1:]],
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
        first = open(self.history, "rb").read()
        write_fx_results(rows, self.test_dir)
        self.assertEqual(open(self.history, "rb").read(), first)

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
            self._rows(self.latest)[1:], [["USDGBP", "2026-09-18", "0.746700"]]
        )


class TestFxFailureIsolation(unittest.TestCase):
    """Test FX and price failures do not block each other."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

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


class TestFxBackfill(unittest.TestCase):
    """Test FX history is rebuilt by the same rule as prices."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.history = os.path.join(self.test_dir, "fx_history.csv")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _rows(self):
        with open(self.history, newline="") as f:
            return [r for r in csv.reader(f)][1:]

    @patch("scrape_fund_price.fetch_fx_quotes")
    def test_rebuilds_rates_from_the_start_date(self, mock_quotes):
        """Test rates are rebuilt from source data."""
        mock_quotes.return_value = [
            Quote("2023-01-03", "0.830000", "USDGBP"),
            Quote("2026-09-18", "0.746700", "USDGBP"),
        ]
        report = backfill_fx(["USDGBP"], "2023-01-01", self.test_dir)
        self.assertEqual(len(self._rows()), 2)
        entry = next(e for e in report.entries if e["identifier"] == "USDGBP")
        self.assertEqual(entry["inserted"], 2)

    @patch("scrape_fund_price.fetch_fx_quotes")
    def test_stale_rows_in_range_are_removed(self, mock_quotes):
        """Test a rate the source no longer reports does not linger."""
        with open(self.history, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Pair", "Date", "Rate"])
            writer.writerow(["USDGBP", "2026-09-19", "0.999999"])  # Saturday
        mock_quotes.return_value = [Quote("2026-09-18", "0.746700", "USDGBP")]

        backfill_fx(["USDGBP"], "2023-01-01", self.test_dir)

        self.assertEqual(self._rows(), [["USDGBP", "2026-09-18", "0.746700"]])

    @patch("scrape_fund_price.fetch_fx_quotes")
    def test_failed_pair_keeps_its_rows(self, mock_quotes):
        """Test a failed fetch never destroys stored rates."""
        with open(self.history, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Pair", "Date", "Rate"])
            writer.writerow(["USDGBP", "2026-09-18", "0.746700"])
        mock_quotes.side_effect = Exception("Network error")

        report = backfill_fx(["USDGBP"], "2023-01-01", self.test_dir)

        self.assertEqual(self._rows(), [["USDGBP", "2026-09-18", "0.746700"]])
        self.assertEqual(len(report.failures), 1)


class TestPriceSummary(unittest.TestCase):
    """Test day-on-day change calculation."""

    def _rows(self, triples):
        return [[f, d, p, c] for f, d, p, c in triples]

    def test_compares_against_the_previous_distinct_price_date(self):
        """Test a Friday-to-Monday gap is a real comparison, not 0%."""
        rows = self._rows(
            [
                ("QQQ", "2026-09-18", "700.00", "USD"),  # Friday
                ("QQQ", "2026-09-21", "714.00", "USD"),  # Monday
            ]
        )
        summary = build_price_summary(
            rows, [FundSpec("GF", "QQQ", ())], [], "2026-09-21"
        )
        row = summary[0]
        self.assertEqual(row.new_date, "2026-09-21")
        self.assertEqual(row.old_date, "2026-09-18")
        self.assertEqual(row.delta, "14")
        self.assertEqual(row.pct_delta, "+2.00")

    def test_delta_uses_exact_decimal_arithmetic(self):
        """Test 7.15 - 7.09 is 0.06, not a binary-float artefact."""
        rows = self._rows(
            [
                ("ISIN1", "2026-09-17", "7.09", "GBP"),
                ("ISIN1", "2026-09-18", "7.15", "GBP"),
            ]
        )
        row = build_price_summary(
            rows, [FundSpec("FT", "ISIN1", ())], [], "2026-09-18"
        )[0]
        self.assertEqual(row.delta, "0.06")

    def test_negative_move_is_signed(self):
        """Test a fall is reported with its sign."""
        rows = self._rows(
            [
                ("AAA", "2026-09-17", "100.00", "USD"),
                ("AAA", "2026-09-18", "98.00", "USD"),
            ]
        )
        row = build_price_summary(rows, [FundSpec("GF", "AAA", ())], [], "2026-09-18")[
            0
        ]
        self.assertEqual(row.delta, "-2")
        self.assertEqual(row.pct_delta, "-2.00")

    def test_instruments_with_different_latest_dates(self):
        """Test a fund lagging an exchange instrument is handled per instrument."""
        rows = self._rows(
            [
                ("FUND", "2026-09-16", "100.00", "USD"),
                ("FUND", "2026-09-17", "101.00", "USD"),
                ("ETF", "2026-09-17", "50.00", "USD"),
                ("ETF", "2026-09-18", "52.00", "USD"),
            ]
        )
        summary = build_price_summary(
            rows,
            [FundSpec("GF", "FUND", ()), FundSpec("GF", "ETF", ())],
            [],
            "2026-09-18",
        )
        by_name = {r.name: r for r in summary}
        self.assertEqual(by_name["FUND"].new_date, "2026-09-17")
        self.assertEqual(by_name["ETF"].new_date, "2026-09-18")

    def test_single_price_has_no_comparison(self):
        """Test a newly added instrument does not invent a delta."""
        rows = self._rows([("NEW", "2026-09-18", "10.00", "GBP")])
        row = build_price_summary(rows, [FundSpec("GF", "NEW", ())], [], "2026-09-18")[
            0
        ]
        self.assertEqual(row.old, "")
        self.assertEqual(row.delta, "")
        self.assertEqual(row.pct_delta, "")

    def test_zero_previous_price_gives_no_percentage(self):
        """Test a zero prior price does not divide by zero."""
        rows = self._rows(
            [
                ("AAA", "2026-09-17", "0", "USD"),
                ("AAA", "2026-09-18", "5.00", "USD"),
            ]
        )
        row = build_price_summary(rows, [FundSpec("GF", "AAA", ())], [], "2026-09-18")[
            0
        ]
        self.assertEqual(row.delta, "5")
        self.assertEqual(row.pct_delta, "")

    def test_instrument_with_no_history_is_reported_as_failed(self):
        """Test a configured instrument with nothing stored is visible."""
        summary = build_price_summary([], [FundSpec("GF", "AAA", ())], [], "2026-09-18")
        self.assertEqual(summary[0].new, "")
        self.assertTrue(summary[0].failed)

    def test_stale_boundary(self):
        """Test the stale threshold covers a long weekend but not longer."""
        rows = self._rows([("AAA", "2026-09-14", "10.00", "USD")])
        spec = [FundSpec("GF", "AAA", ())]
        self.assertFalse(build_price_summary(rows, spec, [], "2026-09-18")[0].stale)
        self.assertTrue(build_price_summary(rows, spec, [], "2026-09-19")[0].stale)

    def test_failed_instrument_is_flagged(self):
        """Test a fund that fell back to its last price is marked."""
        rows = self._rows([("AAA", "2026-09-18", "10.00", "USD")])
        summary = build_price_summary(
            rows, [FundSpec("GF", "AAA", ())], ["AAA: Error: Timeout"], "2026-09-18"
        )
        self.assertTrue(summary[0].failed)

    def test_aliased_instrument_appears_once_with_its_aliases(self):
        """Test an alias is not reported as a second, identical instrument."""
        rows = self._rows(
            [
                ("0P00000YAN", "2026-09-16", "192.23", "USD"),
                ("0P00000YAN", "2026-09-17", "192.43", "USD"),
                ("JFM0003373", "2026-09-16", "192.23", "USD"),
                ("JFM0003373", "2026-09-17", "192.43", "USD"),
            ]
        )
        summary = build_price_summary(
            rows, [FundSpec("GF", "0P00000YAN", ("JFM0003373",))], [], "2026-09-17"
        )
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0].name, "0P00000YAN")
        self.assertEqual(summary[0].aliases, ("JFM0003373",))

    def test_pence_instrument_keeps_its_unit(self):
        """Test GBp is shown, and the percentage is unit-independent."""
        rows = self._rows(
            [
                ("IGWD.L", "2026-09-17", "13000", "GBp"),
                ("IGWD.L", "2026-09-18", "13339", "GBp"),
            ]
        )
        row = build_price_summary(
            rows, [FundSpec("GF", "IGWD.L", ())], [], "2026-09-18"
        )[0]
        self.assertEqual(row.currency, "GBp")
        self.assertEqual(row.delta, "339")
        self.assertEqual(row.pct_delta, "+2.61")

    def test_rows_follow_funds_file_order(self):
        """Test the summary reads in the order the config lists instruments."""
        rows = self._rows(
            [
                ("BBB", "2026-09-18", "2.00", "USD"),
                ("AAA", "2026-09-18", "1.00", "USD"),
            ]
        )
        summary = build_price_summary(
            rows,
            [FundSpec("GF", "BBB", ()), FundSpec("GF", "AAA", ())],
            [],
            "2026-09-18",
        )
        self.assertEqual([r.name for r in summary], ["BBB", "AAA"])

    def test_spot_check_from_the_issue(self):
        """Test the documented ASEAN fund example."""
        rows = self._rows(
            [
                ("0P00000YAN", "2026-09-16", "192.23", "USD"),
                ("0P00000YAN", "2026-09-17", "192.43", "USD"),
            ]
        )
        row = build_price_summary(
            rows, [FundSpec("GF", "0P00000YAN", ())], [], "2026-09-17"
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


class TestSummaryRendering(unittest.TestCase):
    """Test the Markdown and CSV output."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.price_rows = build_price_summary(
            [
                ["QQQ", "2026-09-17", "700.00", "USD"],
                ["QQQ", "2026-09-18", "714.00", "USD"],
                ["IGWD.L", "2026-09-17", "13000", "GBp"],
                ["IGWD.L", "2026-09-18", "13339", "GBp"],
            ],
            [FundSpec("GF", "QQQ", ()), FundSpec("GF", "IGWD.L", ())],
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

    def tearDown(self):
        shutil.rmtree(self.test_dir)

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
            [FundSpec("GF", "OLD", ())],
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
        with open(os.path.join(self.test_dir, "daily_summary.csv"), newline="") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0][0], "Name")
        self.assertTrue(any(r[0] == "QQQ" for r in rows))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "daily_summary.md")))

    def test_summary_is_added_to_the_actions_job_summary(self):
        """Test the table appears on the workflow run page."""
        path = os.path.join(self.test_dir, "step_summary.md")
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": path}):
            write_summary(self.price_rows, self.fx_rows, "2026-09-18", self.test_dir)
        with open(path, encoding="utf-8") as f:
            self.assertIn("QQQ", f.read())

    def test_no_job_summary_outside_actions(self):
        """Test a local run does not need the Actions environment."""
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_STEP_SUMMARY"}
        with patch.dict(os.environ, env, clear=True):
            write_summary(self.price_rows, self.fx_rows, "2026-09-18", self.test_dir)
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "daily_summary.md")))


class TestSourceCodeCanonicalisation(unittest.TestCase):
    """Test the GF -> YA rename and its deprecation alias."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _write(self, text):
        path = os.path.join(self.test_dir, "funds.txt")
        with open(path, "w") as f:
            f.write(text)
        return path

    def test_current_codes_pass_through_unchanged(self):
        """Test canonical codes are left alone."""
        for code in ("YA", "FT", "YH", "MS"):
            self.assertEqual(canonical_source(code), code)

    def test_deprecated_gf_maps_to_ya(self):
        """Test GF still resolves, to the Yahoo API."""
        self.assertEqual(canonical_source("GF"), "YA")

    def test_yh_is_not_swept_into_the_alias(self):
        """Test the Yahoo scraping code keeps its own meaning.

        Reusing YH for the API would silently change which handler a stale
        funds.txt line selects, which is why the rename chose YA.
        """
        self.assertEqual(canonical_source("YH"), "YH")
        url, selector = get_source_config("YH", "IDTG.L")
        self.assertTrue(url and selector)

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

    def test_committed_funds_file_uses_only_current_codes(self):
        """Test the repository's own configuration has been migrated."""
        specs = read_fund_specs("funds.txt")
        self.assertEqual({s.source for s in specs}, {"YA", "FT"})
        self.assertEqual(len(specs), 26)


class TestLineEndings(unittest.TestCase):
    """Test every written file uses LF, independent of platform.

    csv.writer defaults to CRLF on every platform. Combined with git's
    autocrlf on Windows normalising to LF while a Linux runner stores CRLF,
    that made the data files flip on every handover between a local commit and
    a scheduled run: one overnight commit showed 3,906 insertions for 4 rows
    of real data.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def assertNoCarriageReturns(self, *names):
        for name in names:
            path = os.path.join(self.test_dir, name)
            self.assertTrue(os.path.exists(path), f"{name} was not written")
            raw = open(path, "rb").read()
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
        import pandas as pd

        frame = pd.DataFrame(
            {"Open": [1.0], "Close": [1.5]},
            index=pd.to_datetime(["2026-09-18"]),
        )
        frame.empty  # touch, so the mock returns a real frame
        mock_ticker.return_value.history.return_value = frame

        result = fetch_historical_data(
            "AAPL", "2026-09-01", "2026-09-18", self.test_dir
        )
        self.assertFalse(result.startswith("Error:"), result)
        raw = open(result, "rb").read()
        self.assertNotIn(b"\r", raw)

    def test_price_file_per_fund_uses_lf(self):
        """Test the single-value .price files are LF."""
        write_latest_price_file("AAA", "1.50", self.test_dir)
        self.assertNoCarriageReturns("latest_AAA.price")



class TestClosedHoldingConfiguration(unittest.TestCase):
    """Test the closed-holdings config, which is deliberately not funds.txt.

    These instruments are no longer held. Keeping them out of funds.txt is
    what stops the daily run fetching prices for a fund that stopped trading
    years ago, so the two files must stay separate.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _write(self, text):
        path = os.path.join(self.test_dir, "closed_holdings.txt")
        with open(path, "w") as f:
            f.write(text)
        return path

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

    def test_deprecated_source_code_is_canonicalised(self):
        """Test the config shares funds.txt's source vocabulary."""
        holding = read_closed_holdings(
            self._write("BKCH,GF,BKCH.L,USD,2023-01-03,2024-02-16\n")
        )[0]
        self.assertEqual(holding.source, "YA")

    def test_committed_file_holds_the_three_closed_holdings(self):
        """Test the repository's own configuration matches what was researched."""
        holdings = read_closed_holdings(scrape_fund_price.CLOSED_HOLDINGS_FILE)
        self.assertEqual(
            {h.identifier: h.source for h in holdings},
            {"BKCH": "YA", "BMV7ZZ3": "FT", "BN4MYX3": "IV"},
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


class TestClosedHoldingImport(unittest.TestCase):
    """Test the one-off import writes history and nothing else."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.holding = ClosedHolding(
            "BKCH", "YA", "BKCH.L", "USD", "2023-01-03", "2023-01-05"
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _history(self):
        path = os.path.join(self.test_dir, "prices_history.csv")
        with open(path, newline="") as f:
            return [row for row in csv.reader(f)][1:]

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
        whole life would otherwise import years of irrelevant prices.
        """
        mock_quotes.return_value = [
            Quote("2022-12-30", "2.40", "USD"),
            Quote("2023-01-03", "2.4705", "USD"),
            Quote("2023-01-06", "2.60", "USD"),
        ]
        import_closed_holdings([self.holding], self.test_dir)
        self.assertEqual([row[1] for row in self._history()], ["2023-01-03"])

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
        os.makedirs(self.test_dir, exist_ok=True)
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
                os.path.exists(os.path.join(self.test_dir, name)),
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


class TestRebuildLeavesClosedHoldingsAlone(unittest.TestCase):
    """Test a rebuild preserves imported history without promoting it."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _rows(self, name):
        path = os.path.join(self.test_dir, name)
        with open(path, newline="") as f:
            return [row for row in csv.reader(f)][1:]

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
        self.assertFalse(
            os.path.exists(os.path.join(self.test_dir, "latest_BN4MYX3.price"))
        )


class TestClosedImportMainMode(unittest.TestCase):
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
    @patch("scrape_fund_price.parse_arguments")
    def test_import_mode_skips_the_daily_run(
        self, mock_args, mock_scrape, mock_read, mock_import
    ):
        """Test importing never triggers a scrape or an FX snap."""
        mock_args.return_value = MagicMock(
            backfill=False, history=None, import_closed=True
        )
        mock_read.return_value = [
            ClosedHolding("BKCH", "YA", "BKCH.L", "USD", "2023-01-03", "2024-02-16")
        ]
        mock_import.return_value = BackfillReport()
        main()
        mock_import.assert_called_once()
        mock_scrape.assert_not_called()

    @patch("scrape_fund_price.import_closed_holdings")
    @patch("scrape_fund_price.read_closed_holdings")
    @patch("scrape_fund_price.parse_arguments")
    def test_failures_exit_non_zero(self, mock_args, mock_read, mock_import):
        """Test a partial import is visible to CI."""
        mock_args.return_value = MagicMock(
            backfill=False, history=None, import_closed=True
        )
        mock_read.return_value = []
        report = BackfillReport()
        report.failures.append("BN4MYX3: no rows")
        mock_import.return_value = report
        with self.assertRaises(SystemExit):
            main()

if __name__ == "__main__":
    unittest.main()
