"""Tests for ListenHereLoader — Listen Here! alignment JSON → AlignmentBundle.

This module tests ``ListenHereLoader`` against an inline **synthetic**
Listen Here! alignment JSON written to ``tmp_path`` (no pooch corpus,
parallel-safe).  A Listen Here! export describes many recordings of one
work warped onto a shared equidistant reference grid: per recording, a
``times`` array whose ``i``-th entry is that recording's clock-time
(seconds) at reference-grid column ``i``.

It verifies:

- the dense complete-topology pairwise claim field (C(R, 2) × columns
  synchronous instant claims) held columnar in a ``MatchClaimField``;
- one empty seconds timeline per recording, each in its own group, with
  ``length`` taken from the recording's stored ``duration``;
- faithful preservation of negative pre-onset warp coordinates (never
  clamped or dropped);
- a ``get_matchstamp_at`` headline read returning all recordings'
  coordinates at one reference instant;
- the bare-array ``body.audio`` value form (``length == max(times)``);
- field-level ``MatchMetadata`` (agent from ``header.createdBy``,
  criteria ``dtw_chroma_alignment``); and
- the ``ValueError`` paths (unequal ``times`` lengths, ``header.ref``
  absent from ``body.audio``, fewer than two recordings).

All counts and coordinates are exact per the Zero Tolerance Validation
Policy.  Validation logic is documented in ``tests/loader/README.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow.compute as pc
import pytest

from timetoalign.alignment.anchors import MatchClaimField
from timetoalign.loader.alignment import ListenHereLoader

# region Fixtures


#: The canonical synthetic specimen (mirrors tests/loader/README.md).
_CANONICAL_SPEC = {
    "header": {"ref": "rec-ref.mp3", "createdBy": "Listen Here! v0.20.0"},
    "body": {
        "audio": {
            "rec-a.mp3": {
                "times": [0.00, 0.02, 0.04, 0.06, 0.08],
                "peaks": [0.1, 0.2],
                "duration": 0.08,
            },
            "rec-b.mp3": {
                "times": [-0.01, 0.01, 0.03, 0.05, 0.07],
                "peaks": [0.1, 0.2],
                "duration": 0.10,
            },
            "rec-ref.mp3": {
                "times": [0.00, 0.025, 0.045, 0.065, 0.085],
                "peaks": [0.1, 0.2],
                "duration": 0.085,
            },
        }
    },
}


def _write_spec(directory: Path, spec: dict) -> Path:
    """Write ``spec`` as ``alignment.json`` under ``directory``; return path."""
    path = directory / "alignment.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


@pytest.fixture()
def canonical_path(tmp_path: Path) -> Path:
    """Path to the canonical synthetic specimen in ``tmp_path``."""
    return _write_spec(tmp_path, _CANONICAL_SPEC)


@pytest.fixture()
def loader(canonical_path: Path) -> ListenHereLoader:
    """A ``ListenHereLoader`` loaded from the canonical specimen."""
    return ListenHereLoader.from_file(canonical_path)


# endregion


# region After-load counts


def test_claim_count(loader: ListenHereLoader) -> None:
    # C(3, 2) = 3 pairs × 5 grid columns = 15 synchronous claims.
    assert len(loader) == 15
    assert len(loader.claim_field) == 15


def test_recording_keys(loader: ListenHereLoader) -> None:
    assert loader.recording_keys == ["rec-a", "rec-b", "rec-ref"]


def test_claim_field_is_match_claim_field(loader: ListenHereLoader) -> None:
    assert isinstance(loader.claim_field, MatchClaimField)


def test_timeline_ids(loader: ListenHereLoader) -> None:
    assert loader.claim_field.timeline_ids == {
        "rec-a:cpt1",
        "rec-b:cpt1",
        "rec-ref:cpt1",
    }


def test_repr(loader: ListenHereLoader) -> None:
    assert repr(loader) == "ListenHereLoader(recordings=3, claims=15)"


# endregion


# region Faithfulness — negative coordinates kept


def test_negative_coordinate_kept(loader: ListenHereLoader) -> None:
    table = loader.claim_field.table
    minimum = min(
        pc.min(table.column("coordinate_a")).as_py(),
        pc.min(table.column("coordinate_b")).as_py(),
    )
    # rec-b's first grid column is -0.01 (pre-onset extrapolation); the
    # loader stores it as-is, neither clamped nor dropped.
    assert minimum == -0.01


# endregion


# region Bundle structure


def test_bundle_timeline_and_group_counts(loader: ListenHereLoader) -> None:
    bundle = loader.create_bundle()
    assert bundle.n_timelines == 3
    assert len(bundle.groups) == 3


def test_bundle_timeline_uids(loader: ListenHereLoader) -> None:
    bundle = loader.create_bundle()
    assert set(bundle.timelines.keys()) == {
        "rec-a:cpt1",
        "rec-b:cpt1",
        "rec-ref:cpt1",
    }


def test_bundle_timelines_are_empty(loader: ListenHereLoader) -> None:
    bundle = loader.create_bundle()
    for timeline in bundle.timelines.values():
        assert len(timeline.events) == 0


def test_recording_timeline_length(loader: ListenHereLoader) -> None:
    bundle = loader.create_bundle()
    assert float(bundle.timelines["rec-b:cpt1"].length) == 0.10


# endregion


# region Headline read — get_matchstamp_at


def test_matchstamp_spans_all_recordings(loader: ListenHereLoader) -> None:
    bundle = loader.create_bundle()
    stamp = bundle.get_matchstamp_at(0.045, "rec-ref:cpt1")
    assert stamp.n_timelines == 3
    # Reference-grid column index 2: rec-a=0.04, rec-b=0.03, rec-ref=0.045.
    assert stamp.get_coordinate("rec-a:cpt1") == 0.04
    assert stamp.get_coordinate("rec-b:cpt1") == 0.03
    assert stamp.get_coordinate("rec-ref:cpt1") == 0.045


# endregion


# region Metadata


def test_claim_metadata(loader: ListenHereLoader) -> None:
    bundle = loader.create_bundle()
    claim = bundle.cross_group_claims[0]
    assert claim.metadata is not None
    assert claim.metadata.agent == "Listen Here! v0.20.0"
    assert claim.metadata.decision_criteria == "dtw_chroma_alignment"


# endregion


# region Bare-array audio value form


def test_bare_array_value_form(tmp_path: Path) -> None:
    spec = {
        "header": {"ref": "rec-x.mp3", "createdBy": "Listen Here! v0.20.0"},
        "body": {
            "audio": {
                # Object form for one, bare-array form for the other.
                "rec-x.mp3": {"times": [0.0, 0.02, 0.04], "duration": 0.04},
                "rec-y.mp3": [0.0, 0.02, 0.04],
            }
        },
    }
    path = _write_spec(tmp_path, spec)
    bundle = ListenHereLoader.from_file(path).create_bundle()
    # The bare-array recording's length is the max of its times.
    assert float(bundle.timelines["rec-y:cpt1"].length) == 0.04


# endregion


# region Error cases


def test_unequal_times_lengths_raise(tmp_path: Path) -> None:
    spec = {
        "header": {"ref": "rec-a.mp3", "createdBy": "Listen Here!"},
        "body": {
            "audio": {
                "rec-a.mp3": {"times": [0.0, 0.02, 0.04], "duration": 0.04},
                "rec-b.mp3": {"times": [0.0, 0.02], "duration": 0.02},
            }
        },
    }
    path = _write_spec(tmp_path, spec)
    with pytest.raises(ValueError, match="same length"):
        ListenHereLoader.from_file(path)


def test_ref_not_in_audio_raises(tmp_path: Path) -> None:
    spec = {
        "header": {"ref": "missing.mp3", "createdBy": "Listen Here!"},
        "body": {
            "audio": {
                "rec-a.mp3": {"times": [0.0, 0.02], "duration": 0.02},
                "rec-b.mp3": {"times": [0.0, 0.02], "duration": 0.02},
            }
        },
    }
    path = _write_spec(tmp_path, spec)
    with pytest.raises(ValueError, match="header.ref"):
        ListenHereLoader.from_file(path)


def test_fewer_than_two_recordings_raises(tmp_path: Path) -> None:
    spec = {
        "header": {"ref": "rec-a.mp3", "createdBy": "Listen Here!"},
        "body": {
            "audio": {
                "rec-a.mp3": {"times": [0.0, 0.02], "duration": 0.02},
            }
        },
    }
    path = _write_spec(tmp_path, spec)
    with pytest.raises(ValueError, match="at least 2 recordings"):
        ListenHereLoader.from_file(path)


# endregion
