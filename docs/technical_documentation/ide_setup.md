# VS Code/Cursor IDE Setup Guide

This guide explains how to set up VS Code or Cursor for optimal development experience with the Fund Price Scraping project.

## Prerequisites

1. **VS Code** or **Cursor** installed
2. **Python extension** installed
3. **Python 3.7+** installed
4. **Virtual environment** set up (recommended)

## Quick Setup

### 1. Install Recommended Extensions

The project includes recommended extensions in `.vscode/extensions.json`. Install them:

- **Python** (`ms-python.python`) - Core Python support
- **Flake8** (`ms-python.flake8`) - Linting
- **Black Formatter** (`ms-python.black-formatter`) - Code formatting
- **isort** (`ms-python.isort`) - Import sorting
- **Debugpy** (`ms-python.debugpy`) - Debugging support

### 2. Configure Python Interpreter

1. Open Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`)
2. Type "Python: Select Interpreter"
3. Choose your virtual environment interpreter (e.g., `./venv/bin/python`)

### 3. Verify Test Discovery

1. Open the Test Explorer (Test icon in Activity Bar)
2. Tests should automatically discover and appear
3. If not, run "Python: Refresh Tests" from Command Palette

## Features

### Test Integration

#### Running Tests
- **All Tests**: `Ctrl+Shift+T` or use Test Explorer
- **Current Test**: `Ctrl+Shift+R` (when cursor is in a test method)
- **Debug Tests**: `Ctrl+Shift+D`

#### Test Explorer
- View all tests in sidebar
- Run individual tests with play button
- See test results and failures inline
- Debug tests with breakpoints

#### Test Results
- Tests appear in Test Explorer with pass/fail status
- Failed tests show detailed error messages
- Coverage information available

### Debugging

#### Debug Configurations
- **Python: Current File** - Debug the currently open file
- **Python: Run Tests** - Debug all tests
- **Python: Run Specific Test** - Debug a specific test
- **Python: Run Scraper** - Debug the main scraper
- **Python: Debug Tests** - Debug tests with advanced options

#### Setting Breakpoints
1. Click in the gutter next to line numbers
2. Or press `F9` on the current line
3. Start debugging with `F5`

### Code Quality

#### Formatting
- **Auto-format on save** enabled
- **Black formatter** configured (88 character line length)
- **Import sorting** on save

#### Linting
- **Flake8** configured for code quality
- **Real-time error highlighting**
- **Hover for error details**

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift+T` | Run all tests |
| `Ctrl+Shift+R` | Run current test |
| `Ctrl+Shift+D` | Debug tests |
| `Ctrl+Shift+F` | Run current file |
| `Ctrl+Shift+C` | Run scraper |
| `F5` | Start debugging |
| `F9` | Toggle breakpoint |
| `Ctrl+Shift+P` | Command Palette |

### Tasks

Access tasks via Command Palette (`Ctrl+Shift+P` → "Tasks: Run Task"):

- **Run All Tests** - Execute complete test suite
- **Run Tests with Coverage** - Run tests with coverage analysis
- **Generate Coverage Report** - Create coverage report
- **Run Scraper** - Execute the main scraper
- **Format Code** - Format all Python files
- **Lint Code** - Check code quality

## Troubleshooting

### Tests Not Discovered
1. Check Python interpreter is set correctly
2. Run "Python: Refresh Tests" from Command Palette
3. Verify `test_scrape_fund_price.py` is in workspace root
4. Check Python path includes workspace directory

### Debugging Issues
1. Ensure Python extension is installed
2. Check debug configuration in `.vscode/launch.json`
3. Verify breakpoints are set correctly
4. Check console output for error messages

### Formatting Not Working
1. Install Black Formatter extension
2. Check Python interpreter is set
3. Verify `editor.formatOnSave` is enabled
4. Run "Format Document" manually (`Shift+Alt+F`)

### Linting Errors
1. Install Flake8 extension
2. Check Flake8 is installed: `pip install flake8`
3. Verify configuration in settings
4. Check Python path includes workspace

## Advanced Configuration

### Custom Settings
Modify `.vscode/settings.json` for project-specific settings:

```json
{
    "python.testing.unittestArgs": ["-v", "-s", "."],
    "python.formatting.blackArgs": ["--line-length=88"],
    "python.linting.flake8Args": ["--max-line-length=88", "--ignore=E203,W503"]
}
```

### Custom Tasks
Add project-specific tasks to `.vscode/tasks.json`:

```json
{
    "label": "Custom Task",
    "type": "shell",
    "command": "python",
    "args": ["custom_script.py"],
    "group": "build"
}
```

### Custom Debug Configurations
Add debug configurations to `.vscode/launch.json`:

```json
{
    "name": "Custom Debug",
    "type": "python",
    "request": "launch",
    "program": "${workspaceFolder}/custom_script.py",
    "console": "integratedTerminal"
}
```

## Best Practices

1. **Use Virtual Environment**: Always use a virtual environment for Python projects
2. **Install Extensions**: Install all recommended extensions for best experience
3. **Run Tests Frequently**: Use keyboard shortcuts to run tests during development
4. **Debug Issues**: Use debugging features to troubleshoot problems
5. **Format Code**: Keep code formatted with Black formatter
6. **Check Linting**: Address linting issues promptly

## Integration with CI/CD

The IDE configuration works seamlessly with the GitHub Actions workflows:

- **Test configurations** match CI/CD test execution
- **Coverage reporting** consistent with CI/CD
- **Code formatting** matches CI/CD standards
- **Linting rules** align with CI/CD checks

This ensures that code that works in the IDE will also work in the CI/CD pipeline.
