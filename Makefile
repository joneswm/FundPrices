.PHONY: help install setup dev-setup validate test test-coverage format lint clean \
	tdd-red tdd-green tdd-refactor all-checks ci format-check

# The interpreter the non-test targets use: the active virtual environment if one is
# active, else venv/ if it exists, else the system python3. No target needs venv/.
ifdef VIRTUAL_ENV
PYTHON ?= python
else ifneq ($(wildcard venv/bin/python),)
PYTHON ?= venv/bin/python
else
PYTHON ?= python3
endif

help: ## Show this help message
	@echo "FundPrices Development Commands"
	@echo "=============================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m pip install black flake8 isort coverage pre-commit
	$(PYTHON) -m playwright install chromium

setup: ## Complete development environment setup
	@echo "Setting up development environment..."
	$(PYTHON) -m venv venv
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
	$(PYTHON) validate_dev_env.py

test: ## Run the mocked test suite (no network)
	./run_tests.sh unit

test-coverage: ## Run the mocked suite under coverage; both gates from .coveragerc
	./run_tests.sh coverage

format: ## Format code with Black and isort
	$(PYTHON) -m black --line-length=88 .
	$(PYTHON) -m isort --profile=black --line-length=88 .

format-check: ## Check formatting without changing files (what CI does)
	$(PYTHON) -m black --check --line-length=88 .
	$(PYTHON) -m isort --check-only --profile=black --line-length=88 .

lint: ## Lint code with flake8
	$(PYTHON) -m flake8 --max-line-length=88 --ignore=E203,W503 .

clean: ## Clean up temporary files
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name ".pytest_cache" -delete
	rm -rf htmlcov/
	rm -rf .coverage

tdd-red: ## TDD RED Phase - Run tests to verify they fail
	@echo "🔴 TDD RED Phase: Run tests to verify they fail"
	./run_tests.sh unit

tdd-green: ## TDD GREEN Phase - Run tests to verify they pass
	@echo "🟢 TDD GREEN Phase: Run tests to verify they pass"
	./run_tests.sh unit

tdd-refactor: ## TDD REFACTOR Phase - Run tests to verify refactoring
	@echo "🔵 TDD REFACTOR Phase: Run tests to verify refactoring"
	./run_tests.sh unit

all-checks: format lint test ## Run all code quality checks
	@echo "All checks completed successfully!"

ci: format-check lint test-coverage ## Run the CI checks locally (checks formatting; never reformats)
	@echo "CI pipeline completed successfully!"
