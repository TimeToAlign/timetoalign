# `tests/testdata/` — pooch wrapper tests

This directory tests the ``timetoalign.testdata`` package — the on-demand
pooch-backed wrapper that fetches per-corpus tarballs from the
``TimeToAlign/tta_test_data`` GitHub release pinned by ``RELEASE_TAG``.
The wrapper is the canonical (and only) way for tests, conftests, and
notebooks to resolve corpus paths.

See ``tests/data/README.md`` for the binding contract and
``timetoalign/testdata/__init__.py`` for the implementation.

## Files

| File | What it validates |
|------|-------------------|
| `test_looks_ready.py` | The private ``_looks_ready()`` trust gate.  Pins the current contract: a sentinel match alone is insufficient (we additionally require at least one non-marker child); developer checkouts (sentinel missing, but data present) are trusted with a single ``logging.WARNING``; an empty or missing directory always returns ``False``. |

## Why these tests

Two failure modes observed during earlier type-hierarchy work
motivated this contract:

* **Sentinel without content** — ``.tta_testdata_hash`` matched the
  expected digest but the directory had been emptied of data files;
  ``_looks_ready`` returned ``True`` and ``ensure_data()`` returned
  silently, causing downstream ``open()`` calls to fail with
  ``FileNotFoundError`` far from the cause.
* **Partial developer checkout** — non-empty directory, no sentinel,
  trusted unconditionally; same downstream symptom.

The contract verified by these tests:

1. ``_looks_ready(dir, marker, digest)`` returns ``True`` ONLY if the
   sentinel matches AND a non-marker child exists.
2. If the sentinel is missing but data is present, returns ``True`` and
   emits exactly one ``WARNING``-level log record.
3. Missing or empty target dir returns ``False`` with no warning.

## Parallel-safety

Tests use ``tmp_path`` and never share global state, matching the
``pytest-xdist`` requirement documented in ``tests/data/README.md``.
