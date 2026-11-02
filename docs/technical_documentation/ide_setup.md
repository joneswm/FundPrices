# VS Code/Cursor IDE Setup Guide

How to set up VS Code or Cursor for the Fund Price Scraping project.

## Prerequisites

1. **VS Code** or **Cursor** installed
2. **Python extension** installed
3. **Python 3.10+** installed
4. **Virtual environment** set up (recommended; see the
   [development guide](development_guide.md#development-environment-setup))

## Quick Setup

> **Note**: `.vscode/` is listed in `.gitignore` and is **not** tracked in this repository,
> so none of these files arrive with a fresh clone. Create the ones you want locally using
> the contents below. The Dev Container, which is tracked, sets the equivalent options for
> you.

### 1. Install Recommended Extensions

The Dev Container installs these, from
[`.devcontainer/devcontainer.json`](../../.devcontainer/devcontainer.json); install the same
locally:

- **Python** (`ms-python.python`): core Python support
- **Pylance** (`ms-python.vscode-pylance`): language server
- **Debugpy** (`ms-python.debugpy`): debugging
- **Ruff** (`charliermarsh.ruff`): editor diagnostics

The project's formatters are Black and isort, and its linter is flake8, run through
`./format_code.sh` and the pre-commit hooks ([dev_tools_config.md](dev_tools_config.md)).
If you want the editor to format on save, add the **Black Formatter**
(`ms-python.black-formatter`) and **isort** (`ms-python.isort`) extensions and point them
at the same 88-character settings.

To have VS Code recommend them, create `.vscode/extensions.json`:

```json
{
  "recommendations": [
    "ms-python.python",
    "ms-python.vscode-pylance",
    "ms-python.debugpy",
    "charliermarsh.ruff"
  ]
}
```

### 2. Configure the Python Interpreter

1. Open the Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`)
2. Type "Python: Select Interpreter"
3. Choose your virtual environment interpreter (for example `./venv/bin/python`)

### 3. Verify Test Discovery

The tests are `unittest` tests in `test_scrape_fund_price.py`.

1. Open the Test Explorer (the Test icon in the Activity Bar)
2. The tests should be discovered and listed
3. If not, run "Python: Refresh Tests" from the Command Palette

The Dev Container is configured for `unittest` discovery with `-s . -p "test_*.py"`; for a
local setup create `.vscode/settings.json` with the same options:

```json
{
    "python.testing.unittestEnabled": true,
    "python.testing.unittestArgs": ["-v", "-s", ".", "-p", "test_*.py"]
}
```

## Features

### Test Integration

- Run, debug and inspect tests from the Test Explorer
- Failures show their messages inline
- The live-source tests skip unless `FUNDPRICES_LIVE` is set, so the Test Explorer runs the
  unit tests by default

### Debugging

Create `.vscode/launch.json` locally for the configurations you want, such as the current
file, the test suite, or `scrape_fund_price.py` itself. Set breakpoints by clicking in the
gutter and start with the Run and Debug view.

### Code Quality

If you add the Black Formatter and isort extensions, formatting on save uses the project's
88-character line length. Lint with flake8 through `./format_code.sh` or the pre-commit
hooks.

## Troubleshooting

### Tests Not Discovered
1. Check the Python interpreter is set correctly
2. Run "Python: Refresh Tests" from the Command Palette
3. Verify `test_scrape_fund_price.py` is in the workspace root
4. Check the `unittestArgs` above

### Debugging Issues
1. Ensure the Python and Debugpy extensions are installed
2. Check `.vscode/launch.json` exists (create it if you have not already)
3. Verify the breakpoints are set correctly

### Formatting Not Working
1. Install the Black Formatter extension
2. Check the Python interpreter is set
3. Verify `editor.formatOnSave` is enabled
4. Run "Format Document" manually (`Shift+Alt+F`)

## Best Practices

1. **Use a virtual environment**
2. **Install the extensions** above
3. **Run the tests frequently**
4. **Keep code formatted**: run `./format_code.sh` before committing
