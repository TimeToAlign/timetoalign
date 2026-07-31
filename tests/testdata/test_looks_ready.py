"""Tests for ``timetoalign.testdata._looks_ready`` (private trust gate).

These tests pin the contract documented in ``tests/testdata/README.md``.
``_looks_ready`` guards ``ensure_data()``'s "skip re-extract" fast path: a
false positive surfaces much later as ``FileNotFoundError`` on the first
downstream ``open()`` call, so the gate must reject every shape that does
not entail a complete, usable extraction.

The sentinel is a two-line file — ``<digest>`` then ``<payload file
count>`` — so the gate can catch a partial tree whose digest still matches.
A single-line (legacy) sentinel carries no count and is rejected on sight.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from timetoalign.testdata import _looks_ready

_DIGEST = "a" * 64  # placeholder SHA256-shaped digest


def _write_sentinel(marker: Path, digest: str, count: int) -> None:
    """Write a two-line (new-format) sentinel: digest then payload count."""
    marker.write_text(f"{digest}\n{count}\n", encoding="utf-8")


def test_returns_true_when_sentinel_and_matching_count(tmp_path: Path) -> None:
    """New-format sentinel, digest matches, count matches payload — True."""
    marker = tmp_path / ".tta_testdata_hash"
    (tmp_path / "a.bin").write_bytes(b"payload")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.bin").write_bytes(b"payload")
    _write_sentinel(marker, _DIGEST, 2)  # two payload files, sentinel excluded
    assert _looks_ready(tmp_path, marker, _DIGEST) is True


def test_returns_false_when_fewer_files_than_recorded(tmp_path: Path) -> None:
    """Digest matches but the tree holds fewer files than recorded — partial, False."""
    marker = tmp_path / ".tta_testdata_hash"
    (tmp_path / "a.bin").write_bytes(b"payload")  # one payload file on disk
    _write_sentinel(marker, _DIGEST, 5)  # sentinel records five
    assert _looks_ready(tmp_path, marker, _DIGEST) is False


def test_returns_true_when_more_files_than_recorded(tmp_path: Path) -> None:
    """Extra files beside a complete corpus keep it ready (no spurious rebuild).

    A test that writes an artifact next to the corpus raises the live count
    above the recorded count. The corpus is still complete, so ``_looks_ready``
    must stay ``True`` — treating the extra file as staleness would race
    concurrent readers into a destructive re-extraction.
    """
    marker = tmp_path / ".tta_testdata_hash"
    (tmp_path / "a.bin").write_bytes(b"payload")
    (tmp_path / "b.bin").write_bytes(b"payload")
    (tmp_path / "stray.bin").write_bytes(b"written by a test")
    _write_sentinel(marker, _DIGEST, 2)  # recorded two, three now on disk
    assert _looks_ready(tmp_path, marker, _DIGEST) is True


def test_returns_false_when_legacy_single_line_sentinel(tmp_path: Path) -> None:
    """Legacy digest-only sentinel has no count line — not ready, re-extract."""
    marker = tmp_path / ".tta_testdata_hash"
    marker.write_text(_DIGEST, encoding="utf-8")  # one line, old format
    (tmp_path / "a.bin").write_bytes(b"payload")
    assert _looks_ready(tmp_path, marker, _DIGEST) is False


def test_returns_false_when_sentinel_digest_mismatch(tmp_path: Path) -> None:
    """Two-line sentinel whose digest differs from expected — re-extract."""
    marker = tmp_path / ".tta_testdata_hash"
    (tmp_path / "a.bin").write_bytes(b"payload")
    _write_sentinel(marker, "0" * 64, 1)
    assert _looks_ready(tmp_path, marker, _DIGEST) is False


def test_returns_false_when_sentinel_only_no_payload(tmp_path: Path) -> None:
    """Sentinel present (count 0) but no payload files — False, force re-extract."""
    marker = tmp_path / ".tta_testdata_hash"
    _write_sentinel(marker, _DIGEST, 0)
    assert _looks_ready(tmp_path, marker, _DIGEST) is False


def test_returns_false_when_count_unparseable(tmp_path: Path) -> None:
    """Second line is not an integer — treat as corrupt, not ready."""
    marker = tmp_path / ".tta_testdata_hash"
    (tmp_path / "a.bin").write_bytes(b"payload")
    marker.write_text(f"{_DIGEST}\nnot-a-number\n", encoding="utf-8")
    assert _looks_ready(tmp_path, marker, _DIGEST) is False


def test_returns_true_with_warning_when_dev_checkout(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Sentinel missing but payload present — trust + emit a single warning."""
    marker = tmp_path / ".tta_testdata_hash"
    assert not marker.exists()
    (tmp_path / "data.bin").write_bytes(b"payload")

    with caplog.at_level(logging.WARNING, logger="timetoalign.testdata"):
        result = _looks_ready(tmp_path, marker, _DIGEST)

    assert result is True
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "no .tta_testdata_hash sentinel" in warnings[0].getMessage()


def test_returns_false_when_dir_missing(tmp_path: Path) -> None:
    """Target dir does not exist — never trust, always re-extract."""
    missing = tmp_path / "does_not_exist"
    marker = missing / ".tta_testdata_hash"
    assert _looks_ready(missing, marker, _DIGEST) is False


def test_returns_false_when_dir_empty(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Empty directory with no sentinel — silent False, no warning emitted."""
    marker = tmp_path / ".tta_testdata_hash"
    with caplog.at_level(logging.WARNING, logger="timetoalign.testdata"):
        result = _looks_ready(tmp_path, marker, _DIGEST)

    assert result is False
    assert not any(r.levelno == logging.WARNING for r in caplog.records)
