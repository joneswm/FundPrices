#!/bin/bash
# Code formatting script

set -e

echo "🎨 Code Formatting"
echo "=================="

# Use the active interpreter. Activate venv/ only when none is active and it exists;
# a clone without venv/ (CI, a dev container, a shared interpreter) runs as it is.
if [[ -z "$VIRTUAL_ENV" && -f "venv/bin/activate" ]]; then
    echo "ℹ️  Activating venv/..."
    # shellcheck disable=SC1091
    source venv/bin/activate
fi

echo "📝 Formatting with Black..."
black --line-length=88 .

echo "📦 Sorting imports with isort..."
isort --profile=black --line-length=88 .

echo "🔍 Linting with flake8..."
flake8 --max-line-length=88 --ignore=E203,W503 .

echo "✅ Code formatting completed"
