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
    main
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
    
    @patch('scrape_fund_price.yf.Ticker')
    def test_fetch_price_api_mock(self, mock_ticker):
        """Test fetching price via API with mocked yfinance."""
        # Mock the yfinance Ticker object
        mock_ticker_instance = MagicMock()
        mock_ticker_instance.info = {'currentPrice': 150.25}
        mock_ticker.return_value = mock_ticker_instance
        
        price = fetch_price_api("AAPL")
        self.assertEqual(price, "150.25")
        mock_ticker.assert_called_once_with("AAPL")
    
    @patch('scrape_fund_price.yf.Ticker')
    def test_fetch_price_api_exception(self, mock_ticker):
        """Test fetching price via API when exception occurs."""
        # Mock the yfinance Ticker to raise an exception
        mock_ticker.side_effect = Exception("Network error")
        
        price = fetch_price_api("AAPL")
        self.assertTrue(price.startswith("Error:"))
        self.assertIn("Network error", price)
    
    @patch('scrape_fund_price.yf.Ticker')
    def test_fetch_price_api_no_price_available(self, mock_ticker):
        """Test fetching price via API when price is not available."""
        # Mock the yfinance Ticker with no price data
        mock_ticker_instance = MagicMock()
        mock_ticker_instance.info = {}
        mock_ticker.return_value = mock_ticker_instance
        
        price = fetch_price_api("AAPL")
        self.assertEqual(price, "Error: Price not available")
    
    @patch('scrape_fund_price.sync_playwright')
    def test_scrape_funds_mock(self, mock_playwright):
        """Test scraping funds with mocked Playwright."""
        # Mock the Playwright context
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        
        mock_playwright.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser
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
        
        self.assertTrue(os.path.exists(latest_csv))
        self.assertTrue(os.path.exists(history_csv))
        
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
        self.assertTrue(results[0][2].startswith("Error:"))
    
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
    
    def test_fetch_historical_data_start_after_end(self):
        """Test fetching historical data with start date after end date."""
        result = fetch_historical_data('AAPL', '2024-12-31', '2024-01-01', self.test_dir)
        
        # Should return error message
        self.assertTrue(result.startswith("Error:"))
        self.assertIn("start", result.lower())


if __name__ == '__main__':
    unittest.main() 