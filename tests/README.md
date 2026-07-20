# Test suite

Run `pytest` for the everyday development loop. The default lane runs in
parallel through pytest-xdist and does not collect coverage.

Long-running corpus-scale integration tests carry the `slow` marker and are
skipped by default. Run `pytest --runslow` to execute the complete suite.
The complete suite is required before any release and before changes to
loaders, unfolding, or alignment internals.

Coverage is opt-in:

```text
pytest --cov=timetoalign --cov-report=term-missing
```

To run one test file, use for example:

```text
pytest tests/path/to/test_file.py
```
