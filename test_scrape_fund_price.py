import unittest
import tempfile
import os
import shutil
from unittest.mock import patch, MagicMock
import csv
from datetime import date

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
    fetch_ft_quotes
)

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
            ("FT", "GB00B1FXTF86")
        ]
        self.assertEqual(result, expected)
    
    def test_get_source_config_ft(self):
        """Test FT source configuration."""
        url, selector = get_source_config("FT", "IE0008368742")
        expected_url = "https://markets.ft.com/data/funds/tearsheet/summary?s=IE0008368742"
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
        expected_url = "https://asialt.morningstar.com/DSB/QuickTake/overview.aspx?code=JFM0003373"
        expected_selector = '#mainContent_quicktakeContent_fvOverview_lblNAV'
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
    
    @patch('scrape_fund_price.fetch_yahoo_quotes')
    def test_fetch_price_api_mock(self, mock_quotes):
        """Test fetching price via API with mocked quote retrieval."""
        mock_quotes.return_value = [Quote("2026-09-18", "150.25", "USD")]

        price = fetch_price_api("AAPL")
        self.assertEqual(price, "150.25")
        self.assertEqual(mock_quotes.call_args.args[0], "AAPL")
    
    @patch('scrape_fund_price.yf.Ticker')
    def test_fetch_price_api_exception(self, mock_ticker):
        """Test fetching price via API when exception occurs."""
        # Mock the yfinance Ticker to raise an exception
        mock_ticker.side_effect = Exception("Network error")
        
        price = fetch_price_api("AAPL")
        self.assertTrue(price.startswith("Error:"))
        self.assertIn("Network error", price)
    
    @patch('scrape_fund_price.fetch_yahoo_quotes')
    def test_fetch_price_api_no_price_available(self, mock_quotes):
        """Test fetching price via API when no quotes are returned."""
        mock_quotes.return_value = []

        price = fetch_price_api("AAPL")
        self.assertEqual(price, "Error: Price not available")
    
    @patch('scrape_fund_price.sync_playwright')
    def test_scrape_funds_mock(self, mock_playwright):
        """Test scraping funds with mocked Playwright."""
        # Mock the Playwright context
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        
        mock_playwright.return_value.__enter__.return_value.chromium.launch.return_value = (
            mock_browser
        )
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        
        # Mock the page methods
        mock_page.locator.return_value.first.text_content.return_value = "123.45"
        
        # Test data
        test_funds = [("FT", "IE0008368742"), ("YH", "IDTG.L")]
        
        # Run the function
        results = scrape_funds(test_funds, self.test_dir)
        
        # Verify results
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0][0], "IE0008368742")  # fund_id
        self.assertEqual(results[0][2], "123.45")  # price
        self.assertEqual(results[1][0], "IDTG.L")
        self.assertEqual(results[1][2], "123.45")
        
        # Verify that price files were created
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "latest_IE0008368742.price")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "latest_IDTG.L.price")))

    @patch('scrape_fund_price.sync_playwright')
    def test_scrape_funds_removes_commas_from_all_price_sources(
        self, mock_playwright
    ):
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

        with patch(
            'scrape_fund_price.fetch_price_api', return_value="1,234.56"
        ):
            results = scrape_funds(test_funds, self.test_dir)

        self.assertEqual([row[2] for row in results], ["1234.56"] * 4)
        for _, fund_id in test_funds:
            latest_price_file = os.path.join(
                self.test_dir, f"latest_{fund_id}.price"
            )
            with open(latest_price_file, "r") as f:
                self.assertEqual(f.read().strip(), "1234.56")
    
    def test_write_results(self):
        """Test writing results to CSV files."""
        test_results = [
            ["IE0008368742", "2025-01-20", "123.45"],
            ["IDTG.L", "2025-01-20", "2.92"]
        ]
        
        # Write results
        write_results(test_results, self.test_dir)
        
        # Check that files were created
        latest_csv = os.path.join(self.test_dir, "latest_prices.csv")
        history_csv = os.path.join(self.test_dir, "prices_history.csv")
        rolling_history_csv = os.path.join(
            self.test_dir, "prices_history_90_days.csv"
        )
        
        self.assertTrue(os.path.exists(latest_csv))
        self.assertTrue(os.path.exists(history_csv))
        self.assertTrue(os.path.exists(rolling_history_csv))
        
        # Check latest prices content
        with open(latest_csv, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
        
        expected_latest = [
            ["Fund", "Date", "Price"],
            ["IE0008368742", "2025-01-20", "123.45"],
            ["IDTG.L", "2025-01-20", "2.92"]
        ]
        self.assertEqual(rows, expected_latest)
        
        # Check history content
        with open(history_csv, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
        
        expected_history = [
            ["Fund", "Date", "Price"],
            ["IE0008368742", "2025-01-20", "123.45"],
            ["IDTG.L", "2025-01-20", "2.92"]
        ]
        self.assertEqual(rows, expected_history)

        with open(rolling_history_csv, "r") as f:
            reader = csv.reader(f)
            rows = list(reader)

        self.assertEqual(rows, expected_history)

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

        write_results([["TODAY", "2025-04-01", "5.00"]], self.test_dir)

        with open(history_csv, "r") as file:
            full_history_rows = list(csv.reader(file))

        self.assertEqual(
            full_history_rows,
            [
                ["Fund", "Date", "Price"],
                ["TOO_OLD", "2025-01-01", "1.00"],
                ["AT_CUTOFF", "2025-01-02", "2.00"],
                ["FUTURE", "2025-04-02", "3.00"],
                ["INVALID", "not-a-date", "4.00"],
                ["TODAY", "2025-04-01", "5.00"],
            ],
        )

        rolling_history_csv = os.path.join(
            self.test_dir, "prices_history_90_days.csv"
        )
        with open(rolling_history_csv, "r") as file:
            rolling_history_rows = list(csv.reader(file))

        self.assertEqual(
            rolling_history_rows,
            [
                ["Fund", "Date", "Price"],
                ["AT_CUTOFF", "2025-01-02", "2.00"],
                ["TODAY", "2025-04-01", "5.00"],
            ],
        )

    def test_write_results_empty_results_creates_empty_rolling_history(self):
        """Test an empty run still writes a valid rolling-history CSV."""
        write_results([], self.test_dir)

        rolling_history_csv = os.path.join(
            self.test_dir, "prices_history_90_days.csv"
        )
        with open(rolling_history_csv, "r") as file:
            rows = list(csv.reader(file))

        self.assertEqual(rows, [["Fund", "Date", "Price"]])
    
    def test_write_results_append_history(self):
        """Test that history file appends new data."""
        # Write initial results
        initial_results = [["IE0008368742", "2025-01-20", "123.45"]]
        write_results(initial_results, self.test_dir)
        
        # Write additional results
        additional_results = [["IDTG.L", "2025-01-21", "2.92"]]
        write_results(additional_results, self.test_dir)
        
        # Check history content
        history_csv = os.path.join(self.test_dir, "prices_history.csv")
        with open(history_csv, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
        
        expected_history = [
            ["Fund", "Date", "Price"],
            ["IE0008368742", "2025-01-20", "123.45"],
            ["IDTG.L", "2025-01-21", "2.92"]
        ]
        self.assertEqual(rows, expected_history)
    
    def test_write_results_no_duplicates_same_day(self):
        """Test that running twice on same day updates price instead of duplicating."""
        # Write initial results
        initial_results = [["IE0008368742", "2025-01-20", "123.45"]]
        write_results(initial_results, self.test_dir)
        
        # Write same fund, same date, different price (simulating second run)
        updated_results = [["IE0008368742", "2025-01-20", "125.67"]]
        write_results(updated_results, self.test_dir)
        
        # Check history content - should have only one entry with updated price
        history_csv = os.path.join(self.test_dir, "prices_history.csv")
        with open(history_csv, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
        
        expected_history = [
            ["Fund", "Date", "Price"],
            ["IE0008368742", "2025-01-20", "125.67"]  # Updated price, not duplicate
        ]
        self.assertEqual(rows, expected_history)

        rolling_history_csv = os.path.join(
            self.test_dir, "prices_history_90_days.csv"
        )
        with open(rolling_history_csv, "r") as f:
            rows = list(csv.reader(f))

        self.assertEqual(rows, expected_history)
    
    def test_write_results_mixed_updates_and_new_entries(self):
        """Test that system handles both updates and new entries correctly."""
        # Write initial results for two funds
        initial_results = [
            ["IE0008368742", "2025-01-20", "123.45"],
            ["IDTG.L", "2025-01-20", "2.92"]
        ]
        write_results(initial_results, self.test_dir)
        
        # Second run: update one fund, add new fund, keep one unchanged
        updated_results = [
            ["IE0008368742", "2025-01-20", "125.67"],  # Updated
            ["IDTG.L", "2025-01-20", "2.92"],          # Same (should not duplicate)
            ["AAPL", "2025-01-20", "150.25"]           # New
        ]
        write_results(updated_results, self.test_dir)
        
        # Check history content
        history_csv = os.path.join(self.test_dir, "prices_history.csv")
        with open(history_csv, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
        
        expected_history = [
            ["Fund", "Date", "Price"],
            ["IE0008368742", "2025-01-20", "125.67"],  # Updated
            ["IDTG.L", "2025-01-20", "2.92"],          # Not duplicated
            ["AAPL", "2025-01-20", "150.25"]           # New entry
        ]
        self.assertEqual(rows, expected_history)
    
    def test_scrape_funds_error_handling(self):
        """Test error handling in scraping."""
        # This test would require more complex mocking to simulate errors
        # For now, we'll test that the function doesn't crash with invalid data
        test_funds = [("INVALID", "TEST123")]
        
        with patch('scrape_fund_price.sync_playwright'):
            results = scrape_funds(test_funds, self.test_dir)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0][2], "N/A")  # Should return N/A for invalid source
    
    @patch('scrape_fund_price.sync_playwright')
    def test_scrape_funds_with_gf_source(self, mock_playwright):
        """Test scraping with GF source (uses API instead of scraping)."""
        # Mock the Playwright context
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        
        mock_playwright.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        
        # Test with GF source
        test_funds = [("GF", "AAPL")]
        
        with patch('scrape_fund_price.fetch_price_api', return_value="150.25"):
            results = scrape_funds(test_funds, self.test_dir)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0][2], "150.25")
    
    @patch('scrape_fund_price.sync_playwright')
    def test_scrape_funds_scraping_exception(self, mock_playwright):
        """Test error handling when scraping raises exception."""
        # Mock the Playwright context
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        
        mock_playwright.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        
        # Make scraping raise an exception
        mock_page.goto.side_effect = Exception("Timeout")
        
        test_funds = [("FT", "TEST123")]
        results = scrape_funds(test_funds, self.test_dir)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][2], "N/A")
        self.assertEqual(len(results.failures), 1)
        self.assertEqual(mock_page.goto.call_count, 3)

    @patch('scrape_fund_price.sync_playwright')
    def test_scrape_funds_retries_timeout_and_succeeds(self, mock_playwright):
        """Test transient timeout errors are retried before writing a price."""
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_playwright.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        timeout_error = (
            "Failed to perform, curl: (28) Operation timed out after "
            "30002 milliseconds with 0 bytes received."
        )
        mock_page.goto.side_effect = [Exception(timeout_error), None]
        mock_page.locator.return_value.first.text_content.return_value = "123.45"

        results = scrape_funds([("FT", "TEST123")], self.test_dir)

        self.assertEqual(results, [["TEST123", date.today().isoformat(), "123.45"]])
        self.assertEqual(results.failures, [])
        self.assertEqual(mock_page.goto.call_count, 2)

        latest_price_file = os.path.join(self.test_dir, "latest_TEST123.price")
        with open(latest_price_file, "r") as f:
            self.assertEqual(f.read().strip(), "123.45")

    @patch('scrape_fund_price.sync_playwright')
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

        results = scrape_funds([("FT", "TEST123")], self.test_dir)

        self.assertEqual(results, [["TEST123", date.today().isoformat(), "111.11"]])
        self.assertEqual(len(results.failures), 1)
        self.assertIn("TEST123", results.failures[0])
        self.assertEqual(mock_page.goto.call_count, 3)

        with open(latest_price_file, "r") as f:
            self.assertEqual(f.read().strip(), "111.11")

    @patch('scrape_fund_price.sync_playwright')
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

        timeout_error = (
            "Error: Failed to perform, curl: (28) Operation timed out after "
            "30002 milliseconds with 0 bytes received."
        )

        with patch(
            'scrape_fund_price.fetch_price_api',
            side_effect=[timeout_error, "220.50"],
        ) as mock_api:
            results = scrape_funds([("GF", "IWDG.L")], self.test_dir)

        self.assertEqual(results, [["IWDG.L", date.today().isoformat(), "220.50"]])
        self.assertEqual(results.failures, [])
        self.assertEqual(mock_api.call_count, 2)

    @patch('scrape_fund_price.sync_playwright')
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

        timeout_error = (
            "Error: Failed to perform, curl: (28) Operation timed out after "
            "30002 milliseconds with 0 bytes received."
        )

        history_csv = os.path.join(self.test_dir, "prices_history.csv")
        with open(history_csv, mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["Fund", "Date", "Price"])
            writer.writerow(["IWDG.L", "2025-01-19", "210.75"])

        with patch(
            'scrape_fund_price.fetch_price_api',
            return_value=timeout_error,
        ) as mock_api:
            results = scrape_funds([("GF", "IWDG.L")], self.test_dir)

        self.assertEqual(results, [["IWDG.L", date.today().isoformat(), "210.75"]])
        self.assertEqual(len(results.failures), 1)
        self.assertIn("IWDG.L", results.failures[0])
        self.assertEqual(mock_api.call_count, 3)
    
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
    
    @patch('scrape_fund_price.parse_arguments')
    @patch('scrape_fund_price.read_fund_ids')
    @patch('scrape_fund_price.scrape_funds')
    @patch('scrape_fund_price.write_results')
    def test_main_function(self, mock_write, mock_scrape, mock_read, mock_parse):
        """Test main function orchestration."""
        # Mock the arguments to return normal mode (no history)
        mock_args = MagicMock()
        mock_args.history = None
        mock_parse.return_value = mock_args
        
        # Mock the functions
        mock_read.return_value = [("FT", "TEST123")]
        mock_scrape.return_value = [["TEST123", "2025-01-20", "100.00"]]
        
        # Call main
        main()
        
        # Verify all functions were called
        mock_parse.assert_called_once()
        mock_read.assert_called_once()
        mock_scrape.assert_called_once()
        mock_write.assert_called_once()

    @patch('scrape_fund_price.parse_arguments')
    @patch('scrape_fund_price.read_fund_ids')
    @patch('scrape_fund_price.scrape_funds')
    @patch('scrape_fund_price.write_results')
    def test_main_fails_job_when_scrape_failures_remain(
        self, mock_write, mock_scrape, mock_read, mock_parse
    ):
        """Test main exits non-zero when fallback prices were used after failures."""
        mock_args = MagicMock()
        mock_args.history = None
        mock_parse.return_value = mock_args
        mock_read.return_value = [("FT", "TEST123")]

        class FailedResults(list):
            failures = ["TEST123: timeout"]

        mock_scrape.return_value = FailedResults(
            [["TEST123", "2025-01-20", "111.11"]]
        )

        with self.assertRaises(SystemExit) as error:
            main()

        self.assertEqual(error.exception.code, 1)
        mock_write.assert_called_once_with(mock_scrape.return_value)

class TestFunctionalScraping(unittest.TestCase):
    """Functional tests that can run against real websites (optional)."""
    
    def test_functional_ft_scraping(self):
        """Functional test for FT scraping (requires internet connection)."""
        test_funds = [("FT", "IE0008368742")]
        results = scrape_funds(test_funds)
        
        self.assertEqual(len(results), 1)
        self.assertNotEqual(results[0][2], "N/A")
        self.assertNotEqual(results[0][2], "")
        # Price should be a number
        try:
            float(results[0][2])
        except ValueError:
            self.fail("Price should be a valid number")
    
    def test_functional_yahoo_scraping(self):
        """Functional test for Yahoo scraping (requires internet connection)."""
        test_funds = [("YH", "IDTG.L")]
        results = scrape_funds(test_funds)
        
        self.assertEqual(len(results), 1)
        self.assertNotEqual(results[0][2], "N/A")
        self.assertNotEqual(results[0][2], "")
        # Price should be a number
        try:
            float(results[0][2])
        except ValueError:
            self.fail("Price should be a valid number")
    
    def test_functional_morningstar_scraping(self):
        """Functional test for Morningstar scraping (requires internet connection)."""
        test_funds = [("MS", "JFM0003373")]
        results = scrape_funds(test_funds)
        
        self.assertEqual(len(results), 1)
        self.assertNotEqual(results[0][2], "N/A")
        self.assertNotEqual(results[0][2], "")
        # Price should be a number
        try:
            float(results[0][2])
        except ValueError:
            self.fail("Price should be a valid number")
    
    def test_functional_google_finance_scraping(self):
        """Functional test for Google Finance API (requires internet connection)."""
        test_funds = [("GF", "AAPL")]
        results = scrape_funds(test_funds)
        
        self.assertEqual(len(results), 1)
        self.assertNotEqual(results[0][2], "N/A")
        self.assertNotEqual(results[0][2], "")
        self.assertFalse(results[0][2].startswith("Error:"))
        # Price should be a number
        try:
            float(results[0][2])
        except ValueError:
            self.fail(f"Price should be a valid number, got: {results[0][2]}")
    
    def test_functional_historical_data(self):
        """Functional test for historical data retrieval (requires internet connection)."""
        # Test with a well-known stock
        test_symbol = "AAPL"
        start_date = "2024-01-02"
        end_date = "2024-01-05"
        
        # Create temporary directory for test
        test_dir = tempfile.mkdtemp()
        
        try:
            result = fetch_historical_data(test_symbol, start_date, end_date, test_dir)
            
            # Should not be an error
            self.assertFalse(result.startswith("Error:"), f"Got error: {result}")
            
            # File should exist
            self.assertTrue(os.path.exists(result), f"File not found: {result}")
            
            # File should contain data
            with open(result, 'r') as f:
                lines = f.readlines()
                self.assertGreater(len(lines), 1, "CSV should have header and data")
                
                # Check header
                header = lines[0].strip()
                self.assertIn('Date', header)
                self.assertIn('Open', header)
                self.assertIn('High', header)
                self.assertIn('Low', header)
                self.assertIn('Close', header)
                
        finally:
            # Clean up
            shutil.rmtree(test_dir)


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
        args = parse_arguments(['--history', 'AAPL', '--start', '2024-01-01', '--end', '2024-12-31'])
        self.assertEqual(args.history, 'AAPL')
        self.assertEqual(args.start, '2024-01-01')
        self.assertEqual(args.end, '2024-12-31')
    
    def test_parse_arguments_history_start_only(self):
        """Test parsing command-line arguments with only start date."""
        args = parse_arguments(['--history', 'MSFT', '--start', '2024-11-01'])
        self.assertEqual(args.history, 'MSFT')
        self.assertEqual(args.start, '2024-11-01')
        self.assertIsNone(args.end)
    
    def test_parse_arguments_no_history(self):
        """Test parsing command-line arguments without history flag."""
        args = parse_arguments([])
        self.assertIsNone(args.history)
        self.assertIsNone(args.start)
        self.assertIsNone(args.end)
    
    @patch('scrape_fund_price.yf.Ticker')
    def test_fetch_historical_data_valid_symbol(self, mock_ticker):
        """Test fetching historical data for a valid symbol."""
        # Mock the yfinance Ticker object
        mock_hist = MagicMock()
        mock_hist.empty = False  # Indicate data was returned
        mock_hist.to_csv = MagicMock()
        mock_ticker.return_value.history.return_value = mock_hist
        
        result = fetch_historical_data('AAPL', '2024-01-01', '2024-12-31', self.test_dir)
        
        # Verify the function was called correctly
        mock_ticker.assert_called_once_with('AAPL')
        mock_ticker.return_value.history.assert_called_once_with(start='2024-01-01', end='2024-12-31')
        
        # Verify result contains expected filename
        self.assertIn('history_AAPL', result)
        self.assertTrue(result.endswith('.csv'))
    
    @patch('scrape_fund_price.yf.Ticker')
    def test_fetch_historical_data_invalid_symbol(self, mock_ticker):
        """Test fetching historical data for an invalid symbol."""
        # Mock the yfinance Ticker to raise an exception
        mock_ticker.return_value.history.side_effect = Exception("Invalid symbol")
        
        result = fetch_historical_data('INVALID_XYZ', '2024-01-01', '2024-12-31', self.test_dir)
        
        # Should return error message
        self.assertTrue(result.startswith("Error:"))
    
    def test_fetch_historical_data_invalid_date_format(self):
        """Test fetching historical data with invalid date format."""
        result = fetch_historical_data('AAPL', '01-01-2024', '2024-12-31', self.test_dir)
        
        # Should return error message about date format
        self.assertTrue(result.startswith("Error:"))
        self.assertIn("date", result.lower())
    
    def test_fetch_historical_data_invalid_end_date_format(self):
        """Test fetching historical data with a malformed end date."""
        result = fetch_historical_data("AAPL", "2024-01-01", "31-12-2024")
        self.assertEqual(result, "Error: Invalid end date format. Use YYYY-MM-DD")

    @patch('scrape_fund_price.yf.Ticker')
    def test_fetch_historical_data_empty_range_returns_error(self, mock_ticker):
        """Test a date range yielding no rows reports no data found."""
        mock_hist = MagicMock()
        mock_hist.empty = True
        mock_ticker.return_value.history.return_value = mock_hist
        result = fetch_historical_data("AAPL", "2024-01-01", "2024-01-02")
        self.assertEqual(result, "Error: No data found for symbol AAPL")

    def test_fetch_historical_data_start_after_end(self):
        """Test fetching historical data with start date after end date."""
        result = fetch_historical_data('AAPL', '2024-12-31', '2024-01-01', self.test_dir)
        
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
        self._write_csv("latest_prices.csv", [
            ["AAPL", "2026-01-01", "Error: timeout"],
            ["MSFT", "2026-01-01", "N/A"],
        ])
        self.assertIsNone(read_latest_csv_price("AAPL", self.test_dir))
        self.assertIsNone(read_latest_csv_price("MSFT", self.test_dir))

    def test_read_latest_csv_price_unknown_fund_returns_none(self):
        """Test a fund absent from latest_prices.csv yields no fallback."""
        self._write_csv("latest_prices.csv", [["AAPL", "2026-01-01", "150.25"]])
        self.assertIsNone(read_latest_csv_price("TSLA", self.test_dir))

    def test_read_history_price_returns_most_recent_usable(self):
        """Test history fallback prefers the last usable row for the fund."""
        self._write_csv("prices_history.csv", [
            ["AAPL", "2026-01-01", "100.00"],
            ["AAPL", "2026-01-02", "110.00"],
            ["MSFT", "2026-01-02", "200.00"],
        ])
        self.assertEqual(read_history_price("AAPL", self.test_dir), "110.00")

    def test_read_history_price_all_unusable_returns_none(self):
        """Test history with only error rows provides no fallback price."""
        self._write_csv("prices_history.csv", [
            ["AAPL", "2026-01-01", "Error: timeout"],
            ["AAPL", "2026-01-02", "N/A"],
        ])
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

    @patch('builtins.print')
    @patch('scrape_fund_price.parse_arguments')
    def test_main_history_without_start_date_errors(self, mock_args, mock_print):
        """Test --history without --start reports an error and stops."""
        mock_args.return_value = MagicMock(history="AAPL", start=None, end=None)
        main()
        mock_print.assert_called_once_with(
            "Error: --start date is required when using --history"
        )

    @patch('builtins.print')
    @patch('scrape_fund_price.fetch_historical_data')
    @patch('scrape_fund_price.parse_arguments')
    def test_main_history_success_prints_path(self, mock_args, mock_fetch, mock_print):
        """Test successful historical retrieval reports the saved file."""
        mock_args.return_value = MagicMock(history="AAPL", start="2024-01-01", end=None)
        mock_fetch.return_value = "data/history_AAPL_2024-01-01_2024-12-31.csv"
        main()
        mock_fetch.assert_called_once_with("AAPL", "2024-01-01", None)
        mock_print.assert_called_once_with(
            "Historical data saved to: data/history_AAPL_2024-01-01_2024-12-31.csv"
        )

    @patch('builtins.print')
    @patch('scrape_fund_price.fetch_historical_data')
    @patch('scrape_fund_price.parse_arguments')
    def test_main_history_error_is_reported(self, mock_args, mock_fetch, mock_print):
        """Test a failed historical retrieval surfaces the error message."""
        mock_args.return_value = MagicMock(history="BADSYM", start="2024-01-01", end=None)
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

    @patch('scrape_fund_price.yf.Ticker')
    def test_returns_dated_quotes(self, mock_ticker):
        """Test each bar becomes a Quote carrying the bar's own date."""
        self._ticker(mock_ticker, [("2026-09-17", 192.42999267578125),
                                   ("2026-09-18", 193.5)])
        quotes = fetch_yahoo_quotes("0P00000YAN", "2026-09-10")
        self.assertEqual(len(quotes), 2)
        self.assertEqual(quotes[0], Quote("2026-09-17", "192.43", "GBP"))
        self.assertEqual(quotes[1].date, "2026-09-18")

    @patch('scrape_fund_price.yf.Ticker')
    def test_requests_unadjusted_close(self, mock_ticker):
        """Test history is requested unadjusted so prices match those snapped."""
        inst = self._ticker(mock_ticker, [("2026-09-18", 7.15)])
        fetch_yahoo_quotes("IDTG.L", "2026-09-10", "2026-09-19")
        kwargs = inst.history.call_args.kwargs
        self.assertFalse(kwargs["auto_adjust"])
        self.assertEqual(kwargs["start"], "2026-09-10")
        self.assertEqual(kwargs["end"], "2026-09-19")

    @patch('scrape_fund_price.yf.Ticker')
    def test_preserves_pence_currency(self, mock_ticker):
        """Test GBp is not silently normalised to GBP."""
        self._ticker(mock_ticker, [("2026-09-18", 6317.0)], currency="GBp")
        self.assertEqual(fetch_yahoo_quotes("SGLN.L", "2026-09-10")[0].currency, "GBp")

    @patch('scrape_fund_price.yf.Ticker')
    def test_drops_rows_without_a_price(self, mock_ticker):
        """Test NaN closes are skipped rather than stored."""
        self._ticker(mock_ticker, [("2026-09-17", float("nan")),
                                   ("2026-09-18", 7.15)])
        quotes = fetch_yahoo_quotes("IDTG.L", "2026-09-10")
        self.assertEqual([q.date for q in quotes], ["2026-09-18"])

    @patch('scrape_fund_price.yf.Ticker')
    def test_empty_history_returns_no_quotes(self, mock_ticker):
        """Test an empty result is not an error."""
        self._ticker(mock_ticker, [])
        self.assertEqual(fetch_yahoo_quotes("IDTG.L", "2026-09-10"), [])

    @patch('scrape_fund_price.yf.Ticker')
    def test_exception_propagates_to_retry_wrapper(self, mock_ticker):
        """Test transport errors are raised so fetch_with_retries can retry."""
        mock_ticker.side_effect = Exception("Network error")
        with self.assertRaises(Exception):
            fetch_yahoo_quotes("IDTG.L", "2026-09-10")

    @patch('scrape_fund_price.fetch_yahoo_quotes')
    def test_fetch_price_api_uses_latest_quote(self, mock_quotes):
        """Test the price API wrapper returns the newest quote, not .info."""
        mock_quotes.return_value = [Quote("2026-09-16", "192.23", "USD"),
                                    Quote("2026-09-17", "192.43", "USD")]
        self.assertEqual(fetch_price_api("0P00000YAN"), "192.43")

    @patch('scrape_fund_price.fetch_yahoo_quotes')
    def test_fetch_price_api_reports_missing_price(self, mock_quotes):
        """Test the error contract is kept when no quotes come back."""
        mock_quotes.return_value = []
        self.assertTrue(fetch_price_api("BADSYM").startswith("Error:"))

    @patch('scrape_fund_price.fetch_yahoo_quotes')
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

    @patch('scrape_fund_price.requests.get')
    def test_returns_dated_quotes_with_currency(self, mock_get):
        """Test rows become Quotes carrying the FT price date and currency."""
        mock_get.side_effect = self._responses()
        quotes = fetch_ft_quotes("GB00B1FXTF86", "2026-09-01")
        self.assertEqual(len(quotes), 2)
        self.assertEqual(quotes[0].date, "2026-09-17")
        self.assertEqual(quotes[1].date, "2026-09-18")
        self.assertEqual(quotes[1].currency, "GBP")

    @patch('scrape_fund_price.requests.get')
    def test_uses_close_not_open(self, mock_get):
        """Test the closing price is taken, not the opening price."""
        mock_get.side_effect = self._responses()
        quotes = fetch_ft_quotes("GB00B1FXTF86", "2026-09-01")
        self.assertEqual(quotes[1].price, "7.15")

    @patch('scrape_fund_price.requests.get')
    def test_strips_thousands_separators_without_float_conversion(self, mock_get):
        """Test FT text prices keep their exact digits, commas removed."""
        mock_get.side_effect = self._responses()
        quotes = fetch_ft_quotes("GB00B1FXTF86", "2026-09-01")
        self.assertEqual(quotes[0].price, "1234.5600")

    @patch('scrape_fund_price.requests.get')
    def test_requests_endpoint_with_slash_dates(self, mock_get):
        """Test the ajax endpoint receives YYYY/MM/DD dates and the xid."""
        mock_get.side_effect = self._responses()
        fetch_ft_quotes("GB00B1FXTF86", "2026-09-01", "2026-09-20")
        ajax_url = mock_get.call_args_list[1].args[0]
        self.assertIn("startDate=2026/09/01", ajax_url)
        self.assertIn("endDate=2026/09/20", ajax_url)
        self.assertIn("symbol=28305998", ajax_url)

    @patch('scrape_fund_price.requests.get')
    def test_missing_internal_id_raises(self, mock_get):
        """Test a page without the internal id is an error, not empty data."""
        mock_get.side_effect = self._responses(page="<html>no config here</html>")
        with self.assertRaises(Exception):
            fetch_ft_quotes("GB00B1FXTF86", "2026-09-01")

    @patch('scrape_fund_price.requests.get')
    def test_no_rows_raises(self, mock_get):
        """Test an empty result set is an error so the fallback can run."""
        mock_get.side_effect = self._responses(rows="")
        with self.assertRaises(Exception):
            fetch_ft_quotes("GB00B1FXTF86", "2026-09-01")

    @patch('scrape_fund_price.requests.get')
    def test_missing_currency_label_is_tolerated(self, mock_get):
        """Test quotes are still returned when no currency label is present."""
        page = FT_PAGE.replace("Price (GBP)", "Price")
        mock_get.side_effect = self._responses(page=page)
        self.assertEqual(fetch_ft_quotes("GB00B1FXTF86", "2026-09-01")[0].currency, "")

if __name__ == '__main__':
    unittest.main() 
