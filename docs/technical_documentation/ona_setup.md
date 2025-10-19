# Ona Setup and Usage Guide

This document provides guidance for using this project with Ona (formerly Gitpod).

## What is Ona?

Ona is a cloud development environment platform that provides:
- Instant, reproducible development environments
- AI-powered coding assistance (Ona Agent)
- Automated environment setup via Dev Containers
- Integrated testing and debugging tools

## Quick Start with Ona

### Opening the Project

Click the button to open this project in Ona:

[![Open in Ona](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/joneswm/FundPrices)

### Automatic Setup

When you open the project, Ona will automatically:

1. **Create Python 3.12 environment** using the Dev Container configuration
2. **Install dependencies** from `requirements.txt`
3. **Install Playwright** with Chromium browser
4. **Configure VS Code** with Python extensions and settings
5. **Load AGENTS.md** into Ona Agent context

This typically takes 1-2 minutes on first launch.

## Project Optimizations for Ona

### 1. AGENTS.md

The `AGENTS.md` file in the repository root provides project-specific instructions to Ona Agent:

- **Common commands** for testing, running, and formatting
- **Project structure** and key files
- **Code style** and TDD requirements
- **Configuration formats** for fund identifiers
- **Implementation details** about data sources and error handling

Ona Agent automatically reads this file at the start of every conversation.

### 2. Dev Container Configuration

`.devcontainer/devcontainer.json` configures the development environment:

```json
{
  "name": "FundPrices - Python",
  "image": "mcr.microsoft.com/devcontainers/python:3.12",
  "postCreateCommand": "pip install -r requirements.txt && playwright install chromium",
  "customizations": {
    "vscode": {
      "extensions": ["ms-python.python", "ms-python.vscode-pylance", ...],
      "settings": { ... }
    }
  }
}
```

**Benefits:**
- Python-specific image for faster startup (vs universal image)
- Automatic dependency installation
- Pre-configured Python testing and linting
- Consistent environment across all developers

### 3. VS Code Tasks

`.vscode/tasks.json` provides quick access to common commands:

- **Run Tests** (Ctrl+Shift+B)
- **Run Tests with Coverage**
- **Run Scraper**
- **Format Code**
- **Validate Environment**

Access via: `Terminal > Run Task...` or keyboard shortcuts

## Using Ona Agent

### Starting a Conversation

Ona Agent has full context of the project through `AGENTS.md`:

```
You: Add a new test for error handling in fetch_price_api
```

Ona Agent will:
1. Understand the TDD workflow requirement
2. Write a failing test first (RED phase)
3. Implement the fix (GREEN phase)
4. Suggest refactoring if needed (REFACTOR phase)
5. Run tests to verify

### Common Requests

**Running Tests:**
```
You: Run the test suite
Ona: [executes] python test_scrape_fund_price.py
```

**Code Changes:**
```
You: Refactor the write_results function to improve readability
Ona: [follows TDD workflow, maintains test coverage]
```

**Documentation:**
```
You: Update the README with the new feature
Ona: [updates documentation, follows project conventions]
```

## Best Practices

### 1. Let Ona Agent Follow TDD

The project enforces TDD workflow. Ona Agent knows this from `AGENTS.md` and will:
- Write tests before implementation
- Commit with RED/GREEN/REFACTOR prefixes
- Maintain >90% code coverage

### 2. Use Project Commands

Ona Agent knows the common commands from `AGENTS.md`:
- `python test_scrape_fund_price.py` - Run tests
- `./format_code.sh` - Format code
- `python scrape_fund_price.py` - Run scraper

### 3. Reference Documentation

Point Ona Agent to existing documentation:
```
You: Check the implementation status document before adding a new feature
```

### 4. Verify Changes

Always run tests after changes:
```
You: Run tests to verify the changes
```

## Environment Variables

No environment variables are required for basic operation. The project uses:
- `PYTHONUNBUFFERED=1` (set automatically in Dev Container)
- Configuration via `funds.txt` file

## Troubleshooting

### Playwright Installation Issues

If Playwright fails to install:
```bash
playwright install chromium --with-deps
```

### Python Version Issues

The Dev Container uses Python 3.12. If you need a different version:
1. Edit `.devcontainer/devcontainer.json`
2. Change the image to desired Python version
3. Rebuild the container

### Test Failures

If tests fail after environment setup:
```bash
# Verify environment
python validate_dev_env.py

# Check dependencies
pip list | grep -E "playwright|coverage|yfinance"

# Run tests with verbose output
python -m unittest test_scrape_fund_price.TestFundPriceScraper -v
```

## Performance Tips

### 1. Use Python-Specific Image

The project uses `mcr.microsoft.com/devcontainers/python:3.12` instead of the universal image for:
- Faster startup time
- Smaller image size
- Python-optimized environment

### 2. Prebuilt Environments

Ona caches Dev Container images for faster subsequent launches.

### 3. Parallel Testing

Tests run quickly (26 tests in ~9 seconds). No need for parallel execution.

## Additional Resources

- [Ona Documentation](https://www.gitpod.io/docs)
- [Dev Containers Specification](https://containers.dev/)
- [AGENTS.md Standard](https://agents.md/)
- [Project TDD Workflow](./tdd_workflow.md)

## Support

For Ona-specific issues:
- Check [Ona Documentation](https://www.gitpod.io/docs)
- Contact Ona support

For project-specific issues:
- Check [Troubleshooting Guide](./troubleshooting.md)
- Open an issue on GitHub
