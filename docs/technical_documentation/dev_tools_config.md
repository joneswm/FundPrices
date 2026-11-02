# Development Tools Configuration

How the development tools are set up for the FundPrices project. The configuration lives
in the files linked below; this page says what each is for and does not copy them, so it
cannot drift out of date.

## Formatting and Linting

The project uses Black and isort (88-character lines, isort's `black` profile) for
formatting and flake8 (`--max-line-length=88 --ignore=E203,W503`) for linting. There is no
`pyproject.toml`, `setup.cfg` or `.flake8`: the options are on the command lines in the
files below.

| File | Purpose |
|------|---------|
| [`format_code.sh`](../../format_code.sh) | Runs Black, isort and flake8 over the repository |
| [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml) | The same three tools, plus whitespace, end-of-file, YAML, large-file and merge-conflict checks, on every commit |
| [`Makefile`](../../Makefile) | `make format` and `make lint` run the same commands |

Formatting and linting run **locally**, through these files. CI does not check them:
`test.yml` runs the tests and the coverage gates only (see [tdd_workflow.md](tdd_workflow.md)).

## Pre-commit Hooks

```bash
pip install pre-commit
pre-commit install            # run the hooks on every commit
pre-commit run --all-files    # run them by hand
```

The hooks are listed in [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml).

## Makefile

[`Makefile`](../../Makefile) is the entry point for common commands. `make help` lists the
targets with their descriptions. The ones used most:

| Target | Purpose |
|--------|---------|
| `make install` | Install the dependencies, the development tools and the Playwright browser |
| `make test` | Run the tests |
| `make test-coverage` | Run the tests with coverage |
| `make format` | Black and isort |
| `make lint` | flake8 |
| `make validate` | `python validate_dev_env.py` |

## Development Scripts

| File | Purpose |
|------|---------|
| [`run_tests.sh`](../../run_tests.sh) | `./run_tests.sh unit \| live \| coverage \| all`; `unit` is the default and needs no virtual environment. The coverage gates (90% overall, 95% for `scrape_fund_price.py`) are in [`.coveragerc`](../../.coveragerc) |
| [`format_code.sh`](../../format_code.sh) | Format and lint |
| [`setup_dev_env.sh`](../../setup_dev_env.sh), [`setup_dev_env.bat`](../../setup_dev_env.bat) | Create the environment and install the dependencies and tools |
| [`validate_dev_env.py`](../../validate_dev_env.py) | Check the environment is ready |

Live tests are switched on by the `FUNDPRICES_LIVE` environment variable, which
`./run_tests.sh live` sets.

## Dev Container

[`.devcontainer/devcontainer.json`](../../.devcontainer/devcontainer.json) gives the same
environment in VS Code and GitHub Codespaces: Python 3.12, the requirements and the
Playwright browser installed on creation, and the editor extensions listed in
[ide_setup.md](ide_setup.md).

## VS Code Tasks

`.vscode/` is not tracked in git. If you want tasks, create `.vscode/tasks.json` locally
and have them call the commands above (`./run_tests.sh unit`, `./format_code.sh`).

## Development Workflow

### Daily workflow
1. Activate the environment: `source venv/bin/activate`
2. Check it is ready: `python validate_dev_env.py`
3. Follow the TDD cycle ([tdd_workflow.md](tdd_workflow.md))
4. Format: `./format_code.sh`
5. Test: `./run_tests.sh unit`
6. Commit, staging by filename

### Pre-commit workflow
1. Install the hooks once: `pre-commit install`
2. The hooks run on every commit
3. Run them by hand with `pre-commit run --all-files`

## Troubleshooting

1. **Virtual environment not active**: `source venv/bin/activate`
2. **Playwright browser missing**: `playwright install chromium`
3. **Dependencies outdated**: `pip install -r requirements.txt --upgrade`
4. **Editor not picking up the configuration**: restart VS Code or Cursor

Further help: `python validate_dev_env.py`, [ide_setup.md](ide_setup.md) and
[tdd_workflow.md](tdd_workflow.md).
