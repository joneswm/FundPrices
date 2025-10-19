#!/bin/bash
# Code formatting script

set -e

echo "🎨 Code Formatting"
echo "=================="

# Check if virtual environment is active
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "⚠️  Virtual environment not active. Activating..."
    source venv/bin/activate
fi

echo "📝 Formatting with Black..."
black --line-length=88 .

echo "📦 Sorting imports with isort..."
isort --profile=black --line-length=88 .

echo "🔍 Linting with flake8..."
flake8 --max-line-length=88 --ignore=E203,W503 .

echo "✅ Code formatting completed"
