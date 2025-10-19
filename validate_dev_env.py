#!/usr/bin/env python3
"""
Development Environment Validation Script
Validates that the development environment is properly configured for the FundPrices project.
"""

import sys
import subprocess
import os
import json
from pathlib import Path

class DevEnvValidator:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.successes = []
    
    def log_success(self, message):
        self.successes.append(message)
        print(f"✅ {message}")
    
    def log_warning(self, message):
        self.warnings.append(message)
        print(f"⚠️  {message}")
    
    def log_error(self, message):
        self.errors.append(message)
        print(f"❌ {message}")
    
    def check_python_version(self):
        """Check if Python version is compatible."""
        print("\n🐍 Checking Python version...")
        version = sys.version_info
        if version >= (3, 7):
            self.log_success(f"Python {version.major}.{version.minor}.{version.micro} is compatible")
        else:
            self.log_error(f"Python {version.major}.{version.minor}.{version.micro} is not compatible (requires 3.7+)")
    
    def check_virtual_environment(self):
        """Check if virtual environment is active."""
        print("\n🔧 Checking virtual environment...")
        if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
            self.log_success("Virtual environment is active")
        else:
            self.log_warning("Virtual environment is not active")
    
    def check_dependencies(self):
        """Check if required dependencies are installed."""
        print("\n📦 Checking dependencies...")
        required_packages = ['playwright', 'coverage']
        
        for package in required_packages:
            try:
                __import__(package)
                self.log_success(f"{package} is installed")
            except ImportError:
                self.log_error(f"{package} is not installed")
    
    def check_dev_tools(self):
        """Check if development tools are available."""
        print("\n🛠️  Checking development tools...")
        dev_tools = ['black', 'flake8', 'isort', 'coverage']
        
        for tool in dev_tools:
            try:
                result = subprocess.run([tool, '--version'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    version = result.stdout.strip().split('\n')[0]
                    self.log_success(f"{tool} is available ({version})")
                else:
                    self.log_warning(f"{tool} is not available")
            except (subprocess.TimeoutExpired, FileNotFoundError):
                self.log_warning(f"{tool} is not available")
    
    def check_playwright_browsers(self):
        """Check if Playwright browsers are installed."""
        print("\n🌐 Checking Playwright browsers...")
        try:
            result = subprocess.run(['playwright', 'install', '--dry-run'], 
                                  capture_output=True, text=True, timeout=10)
            if 'chromium' in result.stdout.lower():
                self.log_success("Playwright browsers are installed")
            else:
                self.log_warning("Playwright browsers may not be properly installed")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self.log_warning("Could not verify Playwright browser installation")
    
    def check_ide_configuration(self):
        """Check if IDE configuration files exist."""
        print("\n💻 Checking IDE configuration...")
        
        # Check VS Code configuration
        vscode_files = [
            '.vscode/settings.json',
            '.vscode/launch.json',
            '.vscode/keybindings.json',
            '.vscode/tasks.json',
            '.vscode/extensions.json'
        ]
        
        vscode_found = 0
        for file_path in vscode_files:
            if Path(file_path).exists():
                vscode_found += 1
        
        if vscode_found == len(vscode_files):
            self.log_success("VS Code configuration is complete")
        elif vscode_found > 0:
            self.log_warning(f"VS Code configuration is partial ({vscode_found}/{len(vscode_files)} files)")
        else:
            self.log_error("VS Code configuration is missing")
        
        # Check Cursor configuration
        if Path('.cursor/tdd-config.json').exists():
            self.log_success("Cursor configuration is present")
        else:
            self.log_warning("Cursor configuration is missing")
    
    def check_project_structure(self):
        """Check if project structure is correct."""
        print("\n📁 Checking project structure...")
        
        required_files = [
            'scrape_fund_price.py',
            'test_scrape_fund_price.py',
            'requirements.txt',
            'funds.txt',
            'README.md'
        ]
        
        required_dirs = [
            'docs',
            'docs/technical_documentation',
            'docs/user_stories',
            'data'
        ]
        
        for file_path in required_files:
            if Path(file_path).exists():
                self.log_success(f"{file_path} exists")
            else:
                self.log_error(f"{file_path} is missing")
        
        for dir_path in required_dirs:
            if Path(dir_path).exists():
                self.log_success(f"{dir_path}/ directory exists")
            else:
                self.log_error(f"{dir_path}/ directory is missing")
    
    def check_tdd_documentation(self):
        """Check if TDD documentation exists."""
        print("\n📚 Checking TDD documentation...")
        
        tdd_files = [
            'docs/technical_documentation/tdd_workflow.md',
            'docs/technical_documentation/tdd_templates.md',
            'docs/technical_documentation/development_guide.md',
            'docs/technical_documentation/ide_setup.md'
        ]
        
        for file_path in tdd_files:
            if Path(file_path).exists():
                self.log_success(f"{file_path} exists")
            else:
                self.log_error(f"{file_path} is missing")
    
    def run_tests(self):
        """Run tests to verify functionality."""
        print("\n🧪 Running tests...")
        try:
            result = subprocess.run([sys.executable, 'test_scrape_fund_price.py'], 
                                  capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                self.log_success("All tests pass")
            else:
                self.log_error("Tests failed")
                print(f"Test output: {result.stdout}")
                print(f"Test errors: {result.stderr}")
        except subprocess.TimeoutExpired:
            self.log_error("Tests timed out")
        except Exception as e:
            self.log_error(f"Could not run tests: {e}")
    
    def check_git_configuration(self):
        """Check if git is properly configured."""
        print("\n🔀 Checking git configuration...")
        
        try:
            # Check if git is available
            subprocess.run(['git', '--version'], check=True, capture_output=True)
            self.log_success("Git is available")
            
            # Check if .gitignore includes data directory
            if Path('.gitignore').exists():
                with open('.gitignore', 'r') as f:
                    content = f.read()
                    if 'data/' in content:
                        self.log_success("Data directory is properly ignored in git")
                    else:
                        self.log_warning("Data directory is not ignored in git")
            else:
                self.log_warning(".gitignore file is missing")
                
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.log_error("Git is not available")
    
    def generate_report(self):
        """Generate a summary report."""
        print("\n" + "="*50)
        print("📊 DEVELOPMENT ENVIRONMENT VALIDATION REPORT")
        print("="*50)
        
        print(f"\n✅ Successes: {len(self.successes)}")
        print(f"⚠️  Warnings: {len(self.warnings)}")
        print(f"❌ Errors: {len(self.errors)}")
        
        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for error in self.errors:
                print(f"   • {error}")
        
        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"   • {warning}")
        
        if not self.errors:
            print(f"\n🎉 Development environment is properly configured!")
            print("   You can start developing using the TDD workflow.")
        else:
            print(f"\n🔧 Please fix the errors above before starting development.")
        
        return len(self.errors) == 0
    
    def run_validation(self):
        """Run all validation checks."""
        print("🔍 FundPrices Development Environment Validation")
        print("="*50)
        
        self.check_python_version()
        self.check_virtual_environment()
        self.check_dependencies()
        self.check_dev_tools()
        self.check_playwright_browsers()
        self.check_ide_configuration()
        self.check_project_structure()
        self.check_tdd_documentation()
        self.check_git_configuration()
        self.run_tests()
        
        return self.generate_report()

def main():
    """Main function."""
    validator = DevEnvValidator()
    success = validator.run_validation()
    
    if success:
        print("\n🚀 Ready for development!")
        print("   Use 'python test_scrape_fund_price.py' to run tests")
        print("   Follow TDD workflow: RED-GREEN-REFACTOR")
        sys.exit(0)
    else:
        print("\n🔧 Please fix the issues above before continuing.")
        sys.exit(1)

if __name__ == "__main__":
    main()
