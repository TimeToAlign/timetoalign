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
| `test_looks_ready.py` | The private ``_looks_ready()`` trust gate.  Pins the current contract: a sentinel match alone is insufficient (we additionally require at least one non-marker child); developer checkouts (sentinel missing, but data present) are trusted with a single ``logging.WARNING``; an empty or missing directory always returns ``False``; passing ``trust_unmarked=False`` disables only the developer-checkout fallback, not the sentinel-match case. |
| `test_extraction_lock.py` | Cross-process extraction locking (``_corpus_file_lock``). Drives several real OS processes at once against the same corpus and asserts every one of them observes a complete extraction, never a partial one. |

## The cross-process extraction race

`_ensure_one()`'s critical section — check sentinel, fetch the archive,
`rmtree` any stale ``target_dir``, extract, write the sentinel — used to be
guarded only by a `threading.Lock` (`_EXTRACT_LOCK`). That excludes other
*threads* in the same interpreter but is invisible to sibling *processes*.

Under `pytest-xdist`, each worker is a separate process, and several
workers commonly import a conftest that calls `ensure_data(...)` for the
same corpus at import time — i.e. at (nearly) the same instant, before any
of them has extracted anything. With only a threading lock, multiple
workers pass the initial `_looks_ready()` check together, then race each
other's `rmtree` + extract of the same `DATA_DIR/<name>` directory. The
observed failure in production: one worker's `rmtree` fires while another
worker is mid-extraction, leaving `target_dir` with a subdirectory missing
— yet the extracting worker still reaches its `marker.write_text(...)` and
writes a sentinel that *matches* the expected digest. Every worker after
that point (including ones that never raced) sees a matching sentinel, so
`_looks_ready()` reports `True` for a directory that is quietly missing
files. That surfaces far from the cause, as a `FileNotFoundError` (or a
loader silently treating a missing subtree as "no data") deep inside
whichever test happens to touch the missing files first.

The fix (`_corpus_file_lock` in `timetoalign/testdata/__init__.py`) adds an
`fcntl.flock`-based file lock, scoped per corpus name
(`DATA_DIR/.<name>.lock`), around the *entire* critical section:

1. **Whole-section coverage** — the lock is acquired before the fetch and
   held through the sentinel write, so no process can observe (or trigger)
   a torn `rmtree`/extract performed by another process.
2. **Double-checked sentinel** — after acquiring the lock, `_ensure_one()`
   re-runs `_looks_ready()` before doing any work. A process that lost the
   race to acquire the lock, but whose peer already finished the
   extraction while it waited, returns immediately instead of redundantly
   re-extracting.
3. **Sentinel written only after a complete extraction** — the marker is
   written to a temp file (`.tta_testdata_hash.tmp<pid>`) and atomically
   renamed into place only once the extraction has fully succeeded and
   `target_dir.is_dir()` has been verified. A process killed mid-extraction
   can never leave behind a sentinel that claims completeness it didn't
   reach.

The lock is scoped **per corpus**, not one lock for all of `DATA_DIR`, so
that `pytest-xdist` workers requesting *different* corpora at the same time
still extract in parallel; only workers racing on the *same* corpus
serialize — which is exactly the scenario that produced the bug.

`fcntl.flock` is POSIX-only. That matches this project's CI, which runs on
Ubuntu only (see `.github/workflows/`); Windows support is not part of the
current platform assumptions for this module.

### The pre-lock fast path and `_looks_ready(..., trust_unmarked=False)`

`_ensure_one()` calls `_looks_ready()` once *before* attempting to acquire
`_corpus_file_lock`, purely so that the (overwhelmingly common) warm-cache
call — the corpus is already extracted, nothing needs to change — never
pays for a lock acquisition. That fast-path call is inherently
unsynchronized: a sibling process elsewhere may be mid-extraction of this
exact corpus, holding the lock, with `target_dir` already containing *some*
freshly written files but not yet the sentinel (written last, and only
after extraction fully succeeds). By content alone, that in-progress state
is indistinguishable from `_looks_ready()`'s own "developer checkout"
fallback (sentinel missing, non-marker files present, trust it). Without
a guard, the fast path could hand back a directory another process was
still populating.

`_looks_ready()` therefore takes a keyword-only `trust_unmarked` flag,
`True` by default. The pre-lock call in `_ensure_one()` passes
`trust_unmarked=False`, disabling only the developer-checkout fallback;
the sentinel-match branch — safe even unsynchronized, since the sentinel
is only ever written after a verified-complete extraction — is unaffected.
The recheck *inside* the lock omits the flag (defaulting back to `True`):
once the lock is held, no peer can be concurrently extracting, so a
sentinel-less directory found there is unambiguously a genuine developer
checkout, and the fallback is safe to use again.

Relatedly, `_looks_ready()` wraps its filesystem reads in a
`try/except FileNotFoundError`, treating a directory or sentinel that
vanishes mid-check (because a peer's `rmtree` fired between this
function's `is_dir()`/`iterdir()`/`read_text()` calls) as "not ready"
rather than letting the exception propagate out of `ensure_data()`.

## Why the `_looks_ready` tests exist

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
``test_extraction_lock.py`` additionally spawns its own worker *processes*
(via ``multiprocessing`` with the ``spawn`` start method) to reproduce the
cross-process race directly — a ``pytest-xdist`` worker is itself only one
process, so exercising the lock's cross-process behavior requires spawning
more. Each round uses a fresh ``tmp_path`` subdirectory, so nothing is
shared across test functions or across ``pytest-xdist`` workers.
