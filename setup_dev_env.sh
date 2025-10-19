#!/bin/bash

# FundPrices Development Environment Setup Script
# This script sets up the complete development environment for the Fund Price Scraping project

set -e  # Exit on any error

echo "🚀 Setting up FundPrices Development Environment"
echo "================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check if Python is installed
check_python() {
    print_info "Checking Python installation..."
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
        print_status "Python $PYTHON_VERSION found"
        
        # Check if version is 3.7 or higher
        if python3 -c "import sys; exit(0 if sys.version_info >= (3, 7) else 1)"; then
            print_status "Python version is compatible (3.7+)"
        else
            print_error "Python version must be 3.7 or higher"
            exit 1
        fi
    else
        print_error "Python 3 is not installed. Please install Python 3.7 or higher."
        exit 1
    fi
}

# Check if pip is installed
check_pip() {
    print_info "Checking pip installation..."
    if command -v pip3 &> /dev/null; then
        print_status "pip3 found"
    else
        print_error "pip3 is not installed. Please install pip."
        exit 1
    fi
}

# Create virtual environment
create_venv() {
    print_info "Creating virtual environment..."
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        print_status "Virtual environment created"
    else
        print_warning "Virtual environment already exists"
    fi
}

# Activate virtual environment
activate_venv() {
    print_info "Activating virtual environment..."
    source venv/bin/activate
    print_status "Virtual environment activated"
}

# Install dependencies
install_dependencies() {
    print_info "Installing Python dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt
    print_status "Python dependencies installed"
}

# Install Playwright browsers
install_playwright() {
    print_info "Installing Playwright browsers..."
    playwright install chromium
    print_status "Playwright browsers installed"
}

# Install development tools
install_dev_tools() {
    print_info "Installing development tools..."
    pip install black flake8 isort coverage
    print_status "Development tools installed"
}

# Verify IDE configuration
verify_ide_config() {
    print_info "Verifying IDE configuration..."
    
    if [ -d ".vscode" ]; then
        print_status "VS Code configuration found"
        
        # Check for key configuration files
        if [ -f ".vscode/settings.json" ]; then
            print_status "VS Code settings configured"
        fi
        
        if [ -f ".vscode/launch.json" ]; then
            print_status "VS Code debug configuration found"
        fi
        
        if [ -f ".vscode/keybindings.json" ]; then
            print_status "VS Code keyboard shortcuts configured"
        fi
        
        if [ -f ".vscode/tasks.json" ]; then
            print_status "VS Code tasks configured"
        fi
        
        if [ -f ".vscode/extensions.json" ]; then
            print_status "VS Code extensions recommendations found"
        fi
    else
        print_warning "VS Code configuration not found"
    fi
    
    if [ -d ".cursor" ]; then
        print_status "Cursor configuration found"
    else
        print_warning "Cursor configuration not found"
    fi
}

# Run tests to verify setup
run_tests() {
    print_info "Running tests to verify setup..."
    if python test_scrape_fund_price.py; then
        print_status "All tests passed - setup verified"
    else
        print_error "Tests failed - please check the setup"
        exit 1
    fi
}

# Check code quality tools
check_code_quality() {
    print_info "Checking code quality tools..."
    
    # Check Black formatter
    if command -v black &> /dev/null; then
        print_status "Black formatter available"
    else
        print_warning "Black formatter not found"
    fi
    
    # Check Flake8 linter
    if command -v flake8 &> /dev/null; then
        print_status "Flake8 linter available"
    else
        print_warning "Flake8 linter not found"
    fi
    
    # Check isort
    if command -v isort &> /dev/null; then
        print_status "isort import sorter available"
    else
        print_warning "isort not found"
    fi
    
    # Check coverage
    if command -v coverage &> /dev/null; then
        print_status "Coverage tool available"
    else
        print_warning "Coverage tool not found"
    fi
}

# Display development workflow information
show_dev_workflow() {
    print_info "Development Workflow Information"
    echo "=================================="
    echo ""
    echo "🚨 MANDATORY: Test-Driven Development (TDD)"
    echo "   RED-GREEN-REFACTOR cycle is required for all development"
    echo ""
    echo "📝 Keyboard Shortcuts (VS Code/Cursor):"
    echo "   Ctrl+Shift+T  - Run all tests"
    echo "   Ctrl+Shift+R  - Run current test"
    echo "   Ctrl+Shift+D  - Debug tests"
    echo "   Ctrl+Alt+R    - TDD RED Phase"
    echo "   Ctrl+Alt+G    - TDD GREEN Phase"
    echo "   Ctrl+Alt+F    - TDD REFACTOR Phase"
    echo ""
    echo "🔧 Development Commands:"
    echo "   python test_scrape_fund_price.py     - Run tests"
    echo "   coverage run -m unittest test_scrape_fund_price.py - Run with coverage"
    echo "   black .                               - Format code"
    echo "   flake8 .                             - Lint code"
    echo "   isort .                              - Sort imports"
    echo ""
    echo "📚 Documentation:"
    echo "   docs/technical_documentation/tdd_workflow.md - TDD workflow"
    echo "   docs/technical_documentation/ide_setup.md - IDE setup guide"
    echo "   docs/technical_documentation/development_guide.md - Development guide"
    echo ""
}

# Main setup process
main() {
    echo ""
    check_python
    check_pip
    create_venv
    activate_venv
    install_dependencies
    install_playwright
    install_dev_tools
    verify_ide_config
    check_code_quality
    run_tests
    
    echo ""
    print_status "Development environment setup complete!"
    echo ""
    show_dev_workflow
    
    echo ""
    print_info "Next steps:"
    echo "1. Open the project in VS Code or Cursor"
    echo "2. Install recommended extensions"
    echo "3. Start developing using TDD workflow"
    echo "4. Run tests frequently with Ctrl+Shift+T"
    echo ""
}

# Run main function
main "$@"
