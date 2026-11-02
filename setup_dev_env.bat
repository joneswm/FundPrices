@echo off
REM FundPrices Development Environment Setup Script for Windows
REM This script sets up the complete development environment for the Fund Price Scraping project

echo 🚀 Setting up FundPrices Development Environment
echo ================================================

REM Check if Python is installed
echo ℹ️  Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python is not installed. Please install Python 3.10 or higher.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo ✅ Python %PYTHON_VERSION% found

REM Check if version is 3.10 or higher
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python %PYTHON_VERSION% is too old. Please install Python 3.10 or higher.
    pause
    exit /b 1
)
echo ✅ Python version is compatible (3.10+)

REM Check if pip is installed
echo ℹ️  Checking pip installation...
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ pip is not installed. Please install pip.
    pause
    exit /b 1
)
echo ✅ pip found

REM Create virtual environment
echo ℹ️  Creating virtual environment...
if not exist "venv" (
    python -m venv venv
    echo ✅ Virtual environment created
) else (
    echo ⚠️  Virtual environment already exists
)

REM Activate virtual environment
echo ℹ️  Activating virtual environment...
call venv\Scripts\activate.bat
echo ✅ Virtual environment activated

REM Install dependencies
echo ℹ️  Installing Python dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
echo ✅ Python dependencies installed

REM Install Playwright browsers
echo ℹ️  Installing Playwright browsers...
playwright install chromium
echo ✅ Playwright browsers installed

REM Install development tools
echo ℹ️  Installing development tools...
pip install black flake8 isort coverage
echo ✅ Development tools installed

REM Verify IDE configuration
echo ℹ️  Verifying IDE configuration...
if exist ".vscode" (
    echo ✅ VS Code configuration found
    if exist ".vscode\settings.json" echo ✅ VS Code settings configured
    if exist ".vscode\launch.json" echo ✅ VS Code debug configuration found
    if exist ".vscode\keybindings.json" echo ✅ VS Code keyboard shortcuts configured
    if exist ".vscode\tasks.json" echo ✅ VS Code tasks configured
    if exist ".vscode\extensions.json" echo ✅ VS Code extensions recommendations found
) else (
    echo ⚠️  VS Code configuration not found
)

if exist ".cursor" (
    echo ✅ Cursor configuration found
) else (
    echo ⚠️  Cursor configuration not found
)

REM Check code quality tools
echo ℹ️  Checking code quality tools...
black --version >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ Black formatter available
) else (
    echo ⚠️  Black formatter not found
)

flake8 --version >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ Flake8 linter available
) else (
    echo ⚠️  Flake8 linter not found
)

isort --version >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ isort import sorter available
) else (
    echo ⚠️  isort not found
)

coverage --version >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ Coverage tool available
) else (
    echo ⚠️  Coverage tool not found
)

REM Run tests to verify setup
echo ℹ️  Running tests to verify setup...
python test_scrape_fund_price.py
if %errorlevel% equ 0 (
    echo ✅ All tests passed - setup verified
) else (
    echo ❌ Tests failed - please check the setup
    pause
    exit /b 1
)

echo.
echo ✅ Development environment setup complete!
echo.
echo ℹ️  Development Workflow Information
echo ==================================
echo.
echo 🚨 MANDATORY: Test-Driven Development (TDD)
echo    RED-GREEN-REFACTOR cycle is required for all development
echo.
echo 📝 Keyboard Shortcuts (VS Code/Cursor):
echo    Ctrl+Shift+T  - Run all tests
echo    Ctrl+Shift+R  - Run current test
echo    Ctrl+Shift+D  - Debug tests
echo    Ctrl+Alt+R    - TDD RED Phase
echo    Ctrl+Alt+G    - TDD GREEN Phase
echo    Ctrl+Alt+F    - TDD REFACTOR Phase
echo.
echo 🔧 Development Commands:
echo    python test_scrape_fund_price.py     - Run tests
echo    coverage run -m unittest test_scrape_fund_price.py - Run with coverage
echo    black .                               - Format code
echo    flake8 .                              - Lint code
echo    isort .                               - Sort imports
echo.
echo 📚 Documentation:
echo    docs\technical_documentation\tdd_workflow.md - TDD workflow
echo    docs\technical_documentation\ide_setup.md - IDE setup guide
echo    docs\technical_documentation\development_guide.md - Development guide
echo.
echo ℹ️  Next steps:
echo 1. Open the project in VS Code or Cursor
echo 2. Install recommended extensions
echo 3. Start developing using TDD workflow
echo 4. Run tests frequently with Ctrl+Shift+T
echo.
pause
