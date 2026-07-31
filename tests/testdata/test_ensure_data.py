"""End-to-end tests for ``timetoalign.testdata.ensure_data``.

These exercise the extraction/repair pipeline against *fabricated* tarballs
with the module globals redirected, so they touch no network and do not rely
on the real corpora. The contract they pin is documented in
``tests/testdata/README.md``:

* extraction is atomic and the sentinel is authored last,
* a partial tree (digest matches, count wrong) self-heals,
* an in-archive ``.tta_testdata_hash`` is stripped, never trusted,
* a legacy one-line sentinel forces exactly one re-extraction, and
* the happy-path sentinel records the archive digest and the exact count of
  extracted payload files.
"""

from __future__ import annotations

import hashlib
import io
import tarfile
from pathlib import Path

import pytest

from timetoalign import testdata

_SENTINEL = ".tta_testdata_hash"


class _StubPooch:
    """Stand-in for the module ``pooch`` object.

    ``fetch`` returns a fixed local tarball path (no download, no digest
    verification) and records how many times it was called so a test can
    assert that a re-extraction did or did not happen.
    """

    def __init__(self, archive_path: Path) -> None:
        self.archive_path = archive_path
        self.fetch_calls = 0

    def fetch(self, name: str) -> str:
        self.fetch_calls += 1
        return str(self.archive_path)


def _make_tarball(files: dict[str, bytes], corpus: str, dest: Path) -> tuple[Path, str]:
    """Write ``files`` into ``dest`` as ``<corpus>/<relpath>`` entries.

    Returns the tarball path and its SHA256 hex digest (the value a real
    release ``REGISTRY`` would carry).
    """
    with tarfile.open(dest, "w:gz") as tar:
        for relpath, content in files.items():
            info = tarfile.TarInfo(name=f"{corpus}/{relpath}")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    return dest, digest


def _payload_relpaths(target: Path) -> set[str]:
    """Relative paths of every regular file under ``target`` bar the sentinel."""
    return {
        str(p.relative_to(target))
        for p in target.rglob("*")
        if p.is_file() and p.name != _SENTINEL
    }


def _install(
    monkeypatch: pytest.MonkeyPatch,
    data_dir: Path,
    corpus: str,
    tarball: Path,
    digest: str,
) -> _StubPooch:
    """Redirect the module globals at a fabricated single-corpus setup."""
    stub = _StubPooch(tarball)
    monkeypatch.setattr(testdata, "DATA_DIR", data_dir)
    monkeypatch.setattr(testdata, "REGISTRY", {f"{corpus}.tar.gz": f"sha256:{digest}"})
    monkeypatch.setattr(testdata, "_POOCH", stub)
    return stub


def test_partial_tree_with_wrong_count_is_repaired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Digest-valid sentinel over a partial tree is detected and re-extracted."""
    corpus = "toycorpus"
    files = {"one.txt": b"1", "two.txt": b"2", "nested/three.txt": b"3"}
    cache = tmp_path / "cache"
    cache.mkdir()
    tarball, digest = _make_tarball(files, corpus, cache / f"{corpus}.tar.gz")

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    stub = _install(monkeypatch, data_dir, corpus, tarball, digest)

    # Seed a partial tree: only one of the three files, but a sentinel whose
    # digest matches and whose count overstates the tree.
    target = data_dir / corpus
    target.mkdir()
    (target / "one.txt").write_bytes(b"1")
    (target / _SENTINEL).write_text(f"{digest}\n3\n", encoding="utf-8")

    result = testdata.ensure_data(corpus)

    assert result == target
    assert stub.fetch_calls == 1
    assert _payload_relpaths(target) == set(files)
    lines = (target / _SENTINEL).read_text(encoding="utf-8").splitlines()
    assert lines == [digest, "3"]


def test_in_archive_sentinel_is_stripped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``.tta_testdata_hash`` shipped inside the archive is never trusted."""
    corpus = "toycorpus"
    files = {"one.txt": b"1", _SENTINEL: b"BOGUS-NOT-A-DIGEST"}
    cache = tmp_path / "cache"
    cache.mkdir()
    tarball, digest = _make_tarball(files, corpus, cache / f"{corpus}.tar.gz")

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _install(monkeypatch, data_dir, corpus, tarball, digest)

    result = testdata.ensure_data(corpus)

    marker_text = (result / _SENTINEL).read_text(encoding="utf-8")
    assert "BOGUS" not in marker_text
    lines = marker_text.splitlines()
    assert lines == [digest, "1"]  # only one.txt is payload; archive sentinel stripped
    assert _payload_relpaths(result) == {"one.txt"}


def test_legacy_single_line_sentinel_upgraded_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A legacy one-line sentinel triggers one re-extract and is upgraded."""
    corpus = "toycorpus"
    files = {"one.txt": b"1", "two.txt": b"2"}
    cache = tmp_path / "cache"
    cache.mkdir()
    tarball, digest = _make_tarball(files, corpus, cache / f"{corpus}.tar.gz")

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    stub = _install(monkeypatch, data_dir, corpus, tarball, digest)

    # A fully extracted tree, but carrying the old single-line sentinel.
    target = data_dir / corpus
    target.mkdir()
    (target / "one.txt").write_bytes(b"1")
    (target / "two.txt").write_bytes(b"2")
    (target / _SENTINEL).write_text(digest, encoding="utf-8")

    testdata.ensure_data(corpus)

    assert stub.fetch_calls == 1
    lines = (target / _SENTINEL).read_text(encoding="utf-8").splitlines()
    assert lines == [digest, "2"]

    # The upgraded sentinel is now trusted: a second call is a no-op.
    testdata.ensure_data(corpus)
    assert stub.fetch_calls == 1


def test_happy_path_records_digest_and_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fresh extraction writes digest + exact payload count and matches archive."""
    corpus = "toycorpus"
    files = {"a.txt": b"aa", "b/c.txt": b"cc", "b/d.txt": b"dd"}
    cache = tmp_path / "cache"
    cache.mkdir()
    tarball, digest = _make_tarball(files, corpus, cache / f"{corpus}.tar.gz")

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    stub = _install(monkeypatch, data_dir, corpus, tarball, digest)

    target = data_dir / corpus
    assert not target.exists()

    result = testdata.ensure_data(corpus)

    assert result == target
    lines = (target / _SENTINEL).read_text(encoding="utf-8").splitlines()
    assert lines[0] == digest
    assert lines[1] == str(len(files))
    assert _payload_relpaths(target) == set(files)

    # No orphaned temp directories left under DATA_DIR.
    assert {p.name for p in data_dir.iterdir()} == {corpus}

    # Idempotent: the trusted sentinel short-circuits the second call.
    testdata.ensure_data(corpus)
    assert stub.fetch_calls == 1
