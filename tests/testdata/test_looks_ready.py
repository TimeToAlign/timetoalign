"""Tests for ``timetoalign.testdata._looks_ready`` (private trust gate).

These tests pin the contract documented in
``tests/testdata/README.md``.  ``_looks_ready`` is the gate guarding
``ensure_data()``'s "skip re-extract" path: a false positive surfaces
much later as ``FileNotFoundError`` on the first downstream ``open()``
call, so the gate must reject every shape that does not entail a usable
extraction.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from timetoalign.testdata import _looks_ready

_DIGEST = "a" * 64  # placeholder SHA256-shaped digest


def test_returns_false_when_sentinel_only(tmp_path: Path) -> None:
    """Sentinel matches but no payload — return False, force re-extract."""
    marker = tmp_path / ".tta_testdata_hash"
    marker.write_text(_DIGEST, encoding="utf-8")
    assert _looks_ready(tmp_path, marker, _DIGEST) is False


def test_returns_true_when_sentinel_and_content(tmp_path: Path) -> None:
    """Sentinel matches AND payload present — canonical happy path."""
    marker = tmp_path / ".tta_testdata_hash"
    marker.write_text(_DIGEST, encoding="utf-8")
    (tmp_path / "data.bin").write_bytes(b"payload")
    assert _looks_ready(tmp_path, marker, _DIGEST) is True


def test_returns_true_with_warning_when_dev_checkout(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Sentinel missing but payload present — trust + emit a warning."""
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


def test_returns_false_when_sentinel_digest_mismatch(tmp_path: Path) -> None:
    """Sentinel exists but digest differs from expected — re-extract.

    Auxiliary case (not in the four-test minimum, but cheap to assert):
    a stale sentinel from a prior corpus version must NOT be trusted
    even when the directory holds non-marker files.
    """
    marker = tmp_path / ".tta_testdata_hash"
    marker.write_text("0" * 64, encoding="utf-8")
    (tmp_path / "data.bin").write_bytes(b"payload")
    assert _looks_ready(tmp_path, marker, _DIGEST) is False


def test_returns_false_when_dir_empty(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Empty directory with no sentinel — false, no warning emitted.

    Auxiliary case: emptiness must be a silent ``False``, not a warning,
    because there is nothing to "trust" in the developer-checkout sense.
    """
    marker = tmp_path / ".tta_testdata_hash"
    with caplog.at_level(logging.WARNING, logger="timetoalign.testdata"):
        result = _looks_ready(tmp_path, marker, _DIGEST)

    assert result is False
    assert not any(r.levelno == logging.WARNING for r in caplog.records)
