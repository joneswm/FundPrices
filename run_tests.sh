#!/bin/bash
# Test runner script with TDD workflow support

set -e

echo "🧪 FundPrices Test Runner"
echo "========================"

# Check if virtual environment is active
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "⚠️  Virtual environment not active. Activating..."
    source venv/bin/activate
fi

# Run tests based on argument
case "${1:-all}" in
    "red")
        echo "🔴 TDD RED Phase: Running tests (should fail)"
        python test_scrape_fund_price.py
        ;;
    "green")
        echo "🟢 TDD GREEN Phase: Running tests (should pass)"
        python test_scrape_fund_price.py
        ;;
    "refactor")
        echo "🔵 TDD REFACTOR Phase: Running tests (should pass)"
        python test_scrape_fund_price.py
        ;;
    "coverage")
        echo "📊 Running tests with coverage"
        coverage run -m unittest test_scrape_fund_price.py
        coverage report -m
        coverage html
        echo "Coverage report generated in htmlcov/"
        ;;
    "all"|*)
        echo "🧪 Running all tests"
        python test_scrape_fund_price.py
        ;;
esac

echo "✅ Tests completed"
