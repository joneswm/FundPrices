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
    write_results
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
    
    def test_get_source_config_google_finance(self):
        """Test Google Finance source configuration."""
        url, selector = get_source_config("GF", "NASDAQ:AAPL")
        expected_url = "https://www.google.com/finance/quote/NASDAQ:AAPL"
        expected_selector = '.YMlKec'
        self.assertEqual(url, expected_url)
        self.assertEqual(selector, expected_selector)
    
    def test_get_source_config_google_finance_case_insensitive(self):
        """Test that Google Finance source configuration is case insensitive."""
        url1, selector1 = get_source_config("gf", "NASDAQ:AAPL")
        url2, selector2 = get_source_config("GF", "NASDAQ:AAPL")
        self.assertEqual(url1, url2)
        self.assertEqual(selector1, selector2)
    
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
    
    def test_scrape_funds_error_handling(self):
        """Test error handling in scraping."""
        # This test would require more complex mocking to simulate errors
        # For now, we'll test that the function doesn't crash with invalid data
        test_funds = [("INVALID", "TEST123")]
        
        with patch('scrape_fund_price.sync_playwright'):
            results = scrape_funds(test_funds, self.test_dir)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0][2], "N/A")  # Should return N/A for invalid source

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
        """Functional test for Google Finance scraping (requires internet connection)."""
        test_funds = [("GF", "NASDAQ:AAPL")]
        results = scrape_funds(test_funds)
        
        self.assertEqual(len(results), 1)
        self.assertNotEqual(results[0][2], "N/A")
        self.assertNotEqual(results[0][2], "")
        # Price should be a number (may have $ prefix)
        price_str = results[0][2].replace("$", "").replace(",", "")
        try:
            float(price_str)
        except ValueError:
            self.fail(f"Price should be a valid number, got: {results[0][2]}")

if __name__ == '__main__':
    unittest.main() 