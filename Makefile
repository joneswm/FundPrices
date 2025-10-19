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
