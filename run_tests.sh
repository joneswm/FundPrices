#!/bin/bash
# FundPrices test runner.
#
#   ./run_tests.sh [unit]    the mocked suite, no network (default)
#   ./run_tests.sh live      only the classes that hit FT, Yahoo, investing.com
#                            and Playwright, with FUNDPRICES_LIVE=1
#   ./run_tests.sh coverage  the mocked suite under coverage; exits non-zero
#                            below either gate in .coveragerc
#   ./run_tests.sh all       the whole suite, live classes included
#
# Runs with whatever `python` is on PATH: an active virtual environment, or
# ./venv when one exists and none is active. Neither is required.

set -e

cd "$(dirname "$0")"

if [[ -z "$VIRTUAL_ENV" && -f venv/bin/activate ]]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
fi

LIVE_CLASSES="test_scrape_fund_price.TestFunctionalScraping
              test_scrape_fund_price.TestFunctionalClosedHoldingSources"

# unit and coverage unset FUNDPRICES_LIVE so a value exported in the shell
# cannot turn either into a network run.
case "${1:-unit}" in
    unit)
        echo "Unit tests: mocked suite, live classes skipped"
        env -u FUNDPRICES_LIVE python test_scrape_fund_price.py
        ;;
    live)
        echo "Live tests: FT, Yahoo, investing.com and Playwright"
        # shellcheck disable=SC2086
        FUNDPRICES_LIVE=1 python -m unittest $LIVE_CLASSES -v
        ;;
    coverage)
        echo "Unit tests under coverage; both gates from .coveragerc"
        # coverage.py has one fail_under, applied by the first report. The
        # second gate is the module's own figure, read from the same file.
        rcfile="${COVERAGE_RCFILE:-.coveragerc}"
        main_fail_under=$(python - "$rcfile" <<'PY'
import configparser, sys
config = configparser.ConfigParser()
config.read(sys.argv[1])
print(config["fundprices"]["main_fail_under"])
PY
)
        env -u FUNDPRICES_LIVE python -m coverage run test_scrape_fund_price.py
        python -m coverage report -m
        python -m coverage report --include=scrape_fund_price.py \
            --fail-under="$main_fail_under"
        python -m coverage html
        echo "HTML report in htmlcov/"
        ;;
    all)
        echo "All tests, live classes included"
        FUNDPRICES_LIVE=1 python test_scrape_fund_price.py
        ;;
    *)
        echo "usage: $0 [unit|live|coverage|all]" >&2
        exit 2
        ;;
esac
