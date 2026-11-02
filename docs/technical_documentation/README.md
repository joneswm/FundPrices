# Technical Documentation

This directory contains technical documentation for the Fund Price Scraping project.

## Structure

### Reference
- `architecture.md` - System architecture and design decisions
- `api_reference.md` - API documentation for functions and classes
- `deployment.md` - Deployment and infrastructure documentation
- `troubleshooting.md` - Common issues and solutions

### Development
- `development_guide.md` - Development setup and guidelines
- `tdd_workflow.md` - **MANDATORY** RED-GREEN-REFACTOR workflow
- `tdd_templates.md` - Templates and checklists for TDD cycles
- `dev_tools_config.md` - where the Black, isort, flake8, pre-commit and Makefile configuration lives, with links

### Environment Setup
- `ide_setup.md` - VS Code / Cursor setup

## Which file owns which fact

Each fact below is stated in full in exactly one place. Every other document points here
or at the owner rather than repeating it, so a change is made once and cannot drift.

| Fact | Canonical source |
|------|------------------|
| Run schedule (two runs, 21:05 and 09:17 UTC) | [`.github/workflows/scrape.yml`](../../.github/workflows/scrape.yml); the prose in README and AGENTS describes it, the workflow file is canonical |
| Source codes (`YA`, `FT`, `IV`, `GF`) and run modes | [`architecture.md`](architecture.md) |
| Command-line options and the functions behind them | [`api_reference.md`](api_reference.md) |
| Data file formats (`data/*.csv`, `.price`, the summary) | [`README.md`](../../README.md), Output Files |
| Invariants: latest never goes backwards (#78), no intraday price (#84), FX rate is the New York close (#80), history keyed on `(Fund, Date)` | [`AGENTS.md`](../../AGENTS.md), Important Implementation Details, with the design in [`architecture.md`](architecture.md) |
| Process: TDD, coverage gates, commit format, direct-to-`main` | [`constitution.md`](../../constitution.md) |
| Status: what is done, what remains | [GitHub Issues](https://github.com/joneswm/FundPrices/issues) for open work and [`specs/README.md`](../../specs/README.md) for what each spec delivered; `docs/user_stories/implementation_status.md` is frozen |
| Setup: environment, tools, test runner | [`development_guide.md`](development_guide.md) |

## Purpose

Technical documentation provides detailed information for developers, system administrators, and DevOps engineers who need to understand, maintain, or extend the system.

## Maintenance

This documentation should be kept up to date with code changes. Each major feature or change should include corresponding documentation updates.

When adding a document to this directory, add it to the Structure list above - the index
has previously drifted out of date. 