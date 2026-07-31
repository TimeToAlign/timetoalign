# `tests/testdata/` — pooch wrapper tests

This directory tests the ``timetoalign.testdata`` package — the on-demand
pooch-backed wrapper that fetches per-corpus tarballs from the
``TimeToAlign/tta_test_data`` GitHub release pinned by ``RELEASE_TAG``.
The wrapper is the canonical (and only) way for tests, conftests, and
notebooks to resolve corpus paths.

See ``tests/data/README.md`` for the binding contract and
``timetoalign/testdata/__init__.py`` for the implementation.

## The trust contract

``ensure_data("<name>")`` must never leave a caller with a directory that
*looks* extracted but is not. Two properties make that guarantee:

1. **Atomic extraction.** The archive is unpacked into a temporary sibling
   directory under ``DATA_DIR`` and only then moved into place with a single
   rename. A process killed mid-extraction leaves either the previous state
   or an orphaned temp directory — never a half-populated corpus directory
   under a trusted sentinel.
2. **Completeness-checked sentinel.** The ``.tta_testdata_hash`` sentinel is
   a two-line file authored by ``ensure_data`` *after* the rename succeeds:

   ```
   <archive SHA256 hex digest>
   <integer count of payload files under the corpus dir, excluding the sentinel>
   ```

   ``_looks_ready`` trusts the directory only when the sentinel's digest
   matches the expected release digest **and** at least the recorded number
   of payload files are on disk. A tree with *fewer* files is a partial
   extraction that self-heals on the next ``ensure_data`` call; a tree with
   *more* files (a test wrote an artifact next to the corpus) is still
   complete and stays trusted, so a stray sibling file never races concurrent
   readers into a destructive rebuild.

The sentinel is authored solely by ``ensure_data``. Any ``.tta_testdata_hash``
entry *shipped inside* an archive is stripped during extraction and never
trusted — a sentinel that travels with the payload could otherwise certify a
tree that a raced or killed extraction only partially wrote.

A **legacy single-line sentinel** (digest only, the pre-count format) has no
count line and is therefore treated as not-ready: the next ``ensure_data``
call re-extracts once and rewrites the sentinel in the two-line format.

## Files

| File | What it validates |
|------|-------------------|
| `test_looks_ready.py` | The private ``_looks_ready()`` trust gate at unit level: two-line-sentinel acceptance (exact and with extra files), digest mismatch, fewer-files-than-recorded rejection (partial tree), legacy single-line rejection, sentinel-without-payload rejection, unparseable count rejection, missing/empty directory rejection, and the no-sentinel developer-checkout branch (trusted with one ``WARNING``). |
| `test_ensure_data.py` | End-to-end ``ensure_data()`` behaviour against fabricated tarballs (no network, no real corpora): partial-tree repair, in-archive sentinel stripping, legacy-sentinel upgrade, and the happy-path sentinel/file-set. |

## Test logic

### `test_looks_ready.py` (unit gate)

``_looks_ready(target_dir, marker, expected_digest)`` returns ``True`` in
exactly two shapes and ``False`` for every other shape:

* **New-format match** — the sentinel's first line equals
  ``expected_digest`` and its second line parses as an integer no greater
  than the live payload-file count (all regular files under ``target_dir``
  except the top-level sentinel). Verified both with an exact match and with
  a directory holding an *extra* file beside the recorded set (still ready).
* **Developer checkout** — the sentinel is absent but at least one payload
  file exists; trusted with exactly one ``logging.WARNING`` on channel
  ``timetoalign.testdata``. This preserves the pre-existing hand-placed-data
  affordance.

``False`` cases, each asserted directly:

1. Digest mismatch — first line differs from ``expected_digest``.
2. Fewer files than recorded — digest matches but the tree holds fewer files
   than the sentinel records (the poisoned partial-tree case).
3. Legacy single-line sentinel — one line, digest only, no count; not-ready
   so the caller re-extracts and upgrades it.
4. Sentinel present but no payload — the directory holds only the sentinel.
5. Unparseable count — second line is not an integer.
6. Missing directory — ``target_dir`` does not exist.
7. Empty directory with no sentinel — silent ``False`` (no warning; there is
   nothing to trust).

### `test_ensure_data.py` (fabricated-tarball integration)

Every test builds a self-contained corpus tree, tars it into a temporary
cache, and drives ``ensure_data`` with the module globals redirected at that
fabrication — ``DATA_DIR`` and ``REGISTRY`` monkeypatched, and ``_POOCH``
replaced by a stub whose ``fetch`` returns the fabricated tarball path (and
counts its calls). No network access and no reliance on the real corpora, so
the tests are hermetic and ``pytest-xdist``-safe.

1. **Partial tree with a digest-valid but wrong-count sentinel** — pre-seed
   the corpus directory with a subset of files and a two-line sentinel whose
   digest matches but whose count overstates the tree. ``ensure_data``
   detects the staleness, re-extracts, and the resulting tree contains the
   exact expected file set.
2. **Archive containing a bogus sentinel entry** — the fabricated tarball
   carries its own ``<corpus>/.tta_testdata_hash`` with junk contents. After
   ``ensure_data`` the on-disk sentinel is the one ``ensure_data`` authored
   (digest on line 1, live count on line 2), never the archive's payload.
3. **Legacy single-line sentinel** — a fully extracted tree carrying a
   one-line digest-only sentinel triggers exactly one re-extraction (asserted
   via the stub's fetch-call count) and the sentinel is upgraded to the
   two-line format.
4. **Happy path** — a fresh (absent) corpus directory: after ``ensure_data``
   the sentinel's first line equals the archive SHA256 digest, its second
   line equals the exact integer count of extracted payload files (excluding
   the sentinel), and the extracted file set matches the archive exactly.

## Parallel-safety

Tests use ``tmp_path`` and ``monkeypatch`` only, never share global state,
and touch no network — matching the ``pytest-xdist`` requirement documented
in ``tests/data/README.md``.
