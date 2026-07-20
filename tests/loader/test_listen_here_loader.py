"""Tests for ListenHereLoader — Listen Here! alignment JSON → AlignmentBundle.

This module tests ``ListenHereLoader`` against an inline **synthetic**
Listen Here! alignment JSON written to ``tmp_path`` (no pooch corpus,
parallel-safe).  A Listen Here! export describes many recordings of one
work warped onto a shared equidistant reference grid: per recording, a
``times`` array whose ``i``-th entry is that recording's clock-time
(seconds) at reference-grid column ``i``.

It verifies:

- the dense complete-topology pairwise claim field (C(R, 2) × columns
  synchronous instant claims) held columnar in a ``MatchClaimField``,
  reached through the uniform ``loader.get_field(MatchClaim)`` API (the
  ``loader.claim_field`` property is gone);
- the loader repr names the reference recording (``header.ref``);
- one empty seconds timeline per recording, each in its own group, with
  ``length`` taken from the recording's stored ``duration``;
- faithful preservation of negative pre-onset warp coordinates (never
  clamped or dropped);
- a columnar ``create_bundle`` that never explodes the field — the
  bundle's Python claim list stays empty while the field is the store;
- a ``get_matchstamp_at`` headline read returning all recordings'
  coordinates at one reference instant via the columnar query path;
- the bare-array ``body.audio`` value form (``length == max(times)``);
- field-level ``MatchMetadata`` (agent from ``header.createdBy``,
  identifier ``dtw_chroma_alignment``); and
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

from timetoalign.alignment.claims import MatchClaim, MatchClaimField
from timetoalign.core import TimeUnit
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
    assert len(loader.get_field(MatchClaim)) == 15


def test_recording_keys(loader: ListenHereLoader) -> None:
    assert loader.recording_keys == ["rec-a", "rec-b", "rec-ref"]


def test_reference(loader: ListenHereLoader) -> None:
    assert loader.reference == "rec-ref.mp3"


def test_get_field_returns_match_claim_field(loader: ListenHereLoader) -> None:
    assert isinstance(loader.get_field(MatchClaim), MatchClaimField)


def test_get_field_by_field_class_is_same(loader: ListenHereLoader) -> None:
    # The paired Field class resolves to the same field as the scalar class.
    assert loader.get_field(MatchClaimField) is loader.get_field(MatchClaim)


def test_get_field_rejects_other_selectors(loader: ListenHereLoader) -> None:
    with pytest.raises(TypeError, match="MatchClaim"):
        loader.get_field(str)


def test_claim_field_property_is_gone(loader: ListenHereLoader) -> None:
    # The old hard-coded property was deleted in favour of get_field().
    assert not hasattr(loader, "claim_field")


def test_timeline_ids(loader: ListenHereLoader) -> None:
    assert loader.get_field(MatchClaim).timeline_ids == {
        "rec-a:cpt1",
        "rec-b:cpt1",
        "rec-ref:cpt1",
    }


def test_repr(loader: ListenHereLoader) -> None:
    assert repr(loader) == (
        "ListenHereLoader(recordings=3, reference='rec-ref.mp3', claims=15)"
    )


def test_repr_html_names_reference(loader: ListenHereLoader) -> None:
    html = loader._repr_html_()
    assert "rec-ref.mp3" in html
    assert "Reference" in html


def test_repr_html_shows_claims_not_zero_events(loader: ListenHereLoader) -> None:
    html = loader._repr_html_()
    # The payload count is named "Claims" (15), never the base "Events: 0".
    assert "<tr><td><b>Claims</b></td><td>15</td></tr>" in html
    assert "Events" not in html
    # Listen Here!-specific rows are present.
    assert "<tr><td><b>Recordings</b></td><td>3</td></tr>" in html
    assert "<b>File</b>" in html
    assert "in 3 group(s)" in html


# endregion


# region Faithfulness — negative coordinates kept


def test_negative_coordinate_kept(loader: ListenHereLoader) -> None:
    field = loader.get_field(MatchClaim)
    struct = field.table.column("match_claim").combine_chunks()
    anchor = struct.field("start_anchor")
    minimum = min(
        pc.min(anchor.field("coordinate_a").field("value")).as_py(),
        pc.min(anchor.field("coordinate_b").field("value")).as_py(),
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


def test_create_timelines_id_pattern_filters(loader: ListenHereLoader) -> None:
    """The pinned three-recording shape filters to the rec-b timeline."""
    timelines = loader.create_timelines(id_pattern=r"^rec-b:")
    assert len(timelines) == 1
    assert timelines[0].id == "rec-b:cpt1"


def test_bundle_uses_columnar_claim_store(loader: ListenHereLoader) -> None:
    # create_bundle hands the MatchClaimField to the columnar store, NOT the
    # per-claim Python list, so the field is never exploded into objects.
    bundle = loader.create_bundle()
    assert len(bundle.cross_group_claims) == 0
    assert len(bundle.cross_group_claim_fields) == 1
    # The columnar field carries all 15 claims.
    assert len(bundle.cross_group_claim_fields[0]) == 15


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
    for timeline_id, expected in {
        "rec-a:cpt1": 0.04,
        "rec-b:cpt1": 0.03,
        "rec-ref:cpt1": 0.045,
    }.items():
        coordinate = stamp.get_coordinate(timeline_id)
        assert coordinate.value == expected
        assert coordinate.unit is TimeUnit.seconds


def test_matchstamp_does_not_explode_field(loader: ListenHereLoader) -> None:
    # The columnar query path must answer get_matchstamp_at WITHOUT ever
    # filling the bundle's Python claim list: it stays empty before AND after
    # the query (the few matched rows are materialised transiently inside the
    # MatchGraph, never appended to cross_group_claims).
    bundle = loader.create_bundle()
    assert len(bundle.cross_group_claims) == 0
    stamp = bundle.get_matchstamp_at(0.045, "rec-ref:cpt1")
    assert stamp.n_timelines == 3
    assert len(bundle.cross_group_claims) == 0


def test_matchstamp_at_first_grid_coordinate(loader: ListenHereLoader) -> None:
    # Query an exact grid coordinate read off one recording: rec-a column 0
    # is 0.0, where rec-b is -0.01 and rec-ref is 0.0. Same instant in all 3.
    bundle = loader.create_bundle()
    stamp = bundle.get_matchstamp_at(0.0, "rec-a:cpt1")
    assert stamp.n_timelines == 3
    for timeline_id, expected in {
        "rec-a:cpt1": 0.0,
        "rec-b:cpt1": -0.01,
        "rec-ref:cpt1": 0.0,
    }.items():
        coordinate = stamp.get_coordinate(timeline_id)
        assert coordinate.value == expected
        assert coordinate.unit is TimeUnit.seconds


# endregion


# region Metadata


def test_claim_metadata(loader: ListenHereLoader) -> None:
    # Metadata is field-level, injected on read; pull a materialised claim
    # from the columnar field (the bundle's Python claim list is empty).
    claim = loader.get_field(MatchClaim)[0]
    assert claim.metadata is not None
    assert claim.metadata.agent.name == "Listen Here! v0.20.0"
    assert claim.metadata.agent.identifier == "dtw_chroma_alignment"


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
