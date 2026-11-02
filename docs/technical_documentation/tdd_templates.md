# TDD Templates and Examples

Templates and checklists for Test-Driven Development in the Fund Price Scraping project.
The workflow and rules are in [tdd_workflow.md](tdd_workflow.md).

The contract every test asserts, in brief: **fetchers raise**, `fetch_with_retries()`
retries, failures are collected on the result object, **no error text ever reaches a data
file**, and result rows are `[identifier, date, price, currency]`.

## Models to copy

Do not invent examples from scratch. Two test classes in
[`test_scrape_fund_price.py`](../../test_scrape_fund_price.py) are the models.

| Situation | Copy | What to notice |
|-----------|------|----------------|
| A pure function over data | `TestNewYorkFxCloses` | Inputs built with the `utc()` helper, the clock passed as `now=`, exact expected output, one behaviour per test |
| A step that fetches and writes a file | `TestUkCpiUpdate` | `setUp`/`tearDown` with a temporary directory, `_run()` patching the fetch, the written file compared whole |
| A step whose fetch fails | `TestUkCpiUpdate.test_a_failed_fetch_keeps_the_last_published_file` | File byte-identical, one entry in `failures` with its step prefix |
| A transient failure | `TestUkCpiUpdate.test_a_transient_failure_is_retried` | The shared retry gives three calls, no failure listed |
| A rebuild from a fixture | `TestUkCpiUpdate.test_the_real_response_gives_a_file_from_2015_01` | A recorded response from `fixtures/` through the real parser |

## Test templates

### Pure function with an injected clock

Modelled on `TestNewYorkFxCloses`.

```python
def test_[behaviour]_[condition](self):
    """Test [the observable behaviour]."""
    # Arrange: inputs built by hand, with the clock fixed
    bars = [(utc(2026, 10, 16, 20), 0.75023)]

    # Act
    result = function_under_test(bars, now=utc(2026, 10, 19, 12))

    # Assert: the exact value, not just "something came back"
    self.assertEqual(result, [("2026-10-16", 0.75023)])
```

### A step that writes a file, with the fetch patched

Modelled on `TestUkCpiUpdate`.

```python
class TestSomeStep(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _run(self, fetch):
        with patch.object(scrape_fund_price, "fetch_something", fetch):
            return update_something(self.test_dir, TODAY)

    def test_the_first_run_writes_the_file(self):
        results = self._run(lambda: {"2015-01": "99.3"})
        self.assertEqual(results.failures, [])
        with open(os.path.join(self.test_dir, "something.csv")) as file:
            self.assertEqual(file.read(), EXPECTED_TEXT)
```

### The failure contract

A fetcher raises, and the step collects the failure and leaves the data alone.

```python
def test_a_failed_fetch_keeps_the_last_file(self):
    """Test the stored file survives and the failure is listed."""
    stored = write_stored_file(self.test_dir)

    def refuse():
        raise ValueError("source: months missing")

    results = self._run(refuse)

    self.assertEqual(read_file(self.test_dir), stored)
    self.assertEqual(len(results.failures), 1)
    self.assertTrue(results.failures[0].startswith("something: "))
```

When the thing under test is a per-fund fetch rather than a whole step, assert on the
`ScrapeResults` it returns: its rows are `[identifier, date, price, currency]`, its
`failures` hold `<identifier>: <error>`, and `carried` holds the last known row for a fund
that failed every attempt.

## Implementation guidance

- **GREEN**: the smallest change that passes. Do not add the retry, the formatting or the
  error handling the test does not yet ask for.
- **REFACTOR**: with the suite green, extract helpers and rename. Keep the public
  behaviour and row shapes unchanged.
- **Fetchers**: raise on failure, return `list[Quote]` oldest first, and leave retries to
  `fetch_with_retries()`.

## TDD Workflow Checklist

### Before starting

- [ ] Understand the requirement and the issue or spec it belongs to
- [ ] Identify the test cases, and the existing test class to extend
- [ ] Decide which test comes first

### RED

- [ ] Write the test
- [ ] Run it and confirm it fails on the behaviour
- [ ] Commit with the `RED:` prefix

### GREEN

- [ ] Write the minimum code
- [ ] Run the new test, then the whole suite
- [ ] Commit with the `GREEN:` prefix

### REFACTOR

- [ ] Improve the code
- [ ] Run the whole suite
- [ ] Check the coverage gates still hold
- [ ] Commit with the `REFACTOR:` prefix

### Done

- [ ] `./run_tests.sh unit` passes
- [ ] `./run_tests.sh coverage` holds 90% overall and 95% for `scrape_fund_price.py`
- [ ] `./format_code.sh` leaves nothing to change
- [ ] The file that owns each changed fact is updated (see the table in
      [`README.md`](README.md))

## Best Practices

### Test writing

1. **One behaviour per test**
2. **Descriptive names** that state the expected outcome
3. **Arrange-Act-Assert**
4. **Edge cases**: boundaries, failures, weekends, bank holidays, the US clock change
5. **Mock dependencies**: unit tests never touch the network or the real `data/`
6. **Record real responses** in `fixtures/` for parsers

### Implementation

1. **Minimal code**: only what the tests need
2. **Follow PEP 8** and the project formatting
3. **Refactor continuously**
4. **Keep docstrings current**

### Workflow

1. **Small steps**, tests after every change
2. **Commit after each phase**
3. **Stage by filename**: files under `data/` are tracked, so `git add -A` would sweep
   data changes into a code commit

## Troubleshooting

- **The test does not fail initially**: the feature already exists, or the assertion is
  too loose. Make it specific.
- **The test fails after implementation**: review the test and the code for a mismatch.
- **Refactoring breaks tests**: they are coupled to the implementation. Assert rows and
  files, not internals.
- **Tests pass but the feature does not work**: add a test against a recorded fixture, or
  a live test that skips when its source is down.
