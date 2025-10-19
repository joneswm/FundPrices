# Development Tools Configuration

This document provides configuration files and setup instructions for development tools used in the FundPrices project.

## Pre-commit Hooks

### Installation
```bash
pip install pre-commit
pre-commit install
```

### Configuration (.pre-commit-config.yaml)
```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.3.0
    hooks:
      - id: black
        language_version: python3
        args: [--line-length=88]

  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort
        args: [--profile=black, --line-length=88]

  - repo: https://github.com/pycqa/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
        args: [--max-line-length=88, --ignore=E203,W503]

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-merge-conflict
```

## Makefile for Development

### Makefile
```makefile
.PHONY: help install test test-coverage format lint clean setup dev-setup validate

help: ## Show this help message
	@echo "FundPrices Development Commands"
	@echo "=============================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	pip install -r requirements.txt
	pip install black flake8 isort coverage pre-commit
	playwright install chromium

setup: ## Complete development environment setup
	@echo "Setting up development environment..."
	python -m venv venv
	@echo "Virtual environment created. Please activate it:"
	@echo "  source venv/bin/activate  # Linux/Mac"
	@echo "  venv\\Scripts\\activate     # Windows"
	@echo "Then run: make install"

dev-setup: ## Run development environment setup script
	@echo "Running development environment setup..."
	@if [ -f "setup_dev_env.sh" ]; then \
		chmod +x setup_dev_env.sh && ./setup_dev_env.sh; \
	elif [ -f "setup_dev_env.bat" ]; then \
		setup_dev_env.bat; \
	else \
		echo "Setup script not found"; \
	fi

validate: ## Validate development environment
	python validate_dev_env.py

test: ## Run tests
	python test_scrape_fund_price.py

test-coverage: ## Run tests with coverage
	coverage run -m unittest test_scrape_fund_price.py
	coverage report -m
	coverage html

format: ## Format code with Black and isort
	black --line-length=88 .
	isort --profile=black --line-length=88 .

lint: ## Lint code with flake8
	flake8 --max-line-length=88 --ignore=E203,W503 .

clean: ## Clean up temporary files
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name ".pytest_cache" -delete
	rm -rf htmlcov/
	rm -rf .coverage

tdd-red: ## TDD RED Phase - Run tests to verify they fail
	@echo "🔴 TDD RED Phase: Run tests to verify they fail"
	python test_scrape_fund_price.py

tdd-green: ## TDD GREEN Phase - Run tests to verify they pass
	@echo "🟢 TDD GREEN Phase: Run tests to verify they pass"
	python test_scrape_fund_price.py

tdd-refactor: ## TDD REFACTOR Phase - Run tests to verify refactoring
	@echo "🔵 TDD REFACTOR Phase: Run tests to verify refactoring"
	python test_scrape_fund_price.py

all-checks: format lint test ## Run all code quality checks
	@echo "All checks completed successfully!"

ci: ## Run CI pipeline locally
	make format
	make lint
	make test-coverage
	@echo "CI pipeline completed successfully!"
```

## Docker Development Environment

### Dockerfile.dev
```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install development tools
RUN pip install --no-cache-dir black flake8 isort coverage pre-commit

# Install Playwright browsers
RUN playwright install chromium

# Copy application files
COPY . .

# Create data directory
RUN mkdir -p data

# Set up pre-commit hooks
RUN pre-commit install

# Default command
CMD ["python", "test_scrape_fund_price.py"]
```

### docker-compose.dev.yml
```yaml
version: '3.8'

services:
  fundprices-dev:
    build:
      context: .
      dockerfile: Dockerfile.dev
    volumes:
      - .:/app
      - /app/venv
    environment:
      - PYTHONPATH=/app
    command: tail -f /dev/null  # Keep container running for development
    ports:
      - "8000:8000"  # If you add a web interface later
```

## Development Scripts

### run_tests.sh
```bash
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
```

### format_code.sh
```bash
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
```

## VS Code Tasks Integration

The project includes comprehensive VS Code task configuration in `.vscode/tasks.json` with:

- **Run All Tests**: Execute complete test suite
- **Run Tests with Coverage**: Generate coverage reports
- **Format Code**: Apply Black and isort formatting
- **Lint Code**: Run flake8 linting
- **TDD Phase Tasks**: Specific tasks for RED/GREEN/REFACTOR phases

## Development Workflow

### Daily Development Workflow
1. **Activate Environment**: `source venv/bin/activate`
2. **Run Validation**: `python validate_dev_env.py`
3. **Start TDD Cycle**: Use keyboard shortcuts or tasks
4. **Format Code**: `make format` or `Ctrl+Shift+P` → "Format Document"
5. **Run Tests**: `make test` or `Ctrl+Shift+T`
6. **Commit Changes**: Follow TDD workflow

### Pre-commit Workflow
1. **Install Hooks**: `pre-commit install`
2. **Automatic Checks**: Hooks run on every commit
3. **Manual Run**: `pre-commit run --all-files`

### CI/CD Integration
The development tools integrate seamlessly with GitHub Actions:
- **Test Execution**: Matches local test commands
- **Code Quality**: Same linting and formatting rules
- **Coverage Reporting**: Consistent coverage thresholds
- **TDD Compliance**: Enforced through code review

## Troubleshooting

### Common Issues
1. **Virtual Environment Not Active**: Run `source venv/bin/activate`
2. **Playwright Browsers Missing**: Run `playwright install chromium`
3. **Dependencies Outdated**: Run `pip install -r requirements.txt --upgrade`
4. **IDE Not Recognizing Config**: Restart VS Code/Cursor

### Getting Help
- **Validation Script**: `python validate_dev_env.py`
- **Setup Script**: `./setup_dev_env.sh` or `setup_dev_env.bat`
- **Documentation**: Check `docs/technical_documentation/ide_setup.md`
- **TDD Workflow**: See `docs/technical_documentation/tdd_workflow.md`

This comprehensive development environment ensures consistent, high-quality development practices across all contributors.
