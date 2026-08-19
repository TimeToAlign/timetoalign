"""Exact position retrieval for interval and standalone instant claims."""

from __future__ import annotations

from fractions import Fraction

import pytest

from timetoalign import MatchIntervalStamp
from timetoalign.alignment import AlignmentAnchor, MatchClaim, MatchClaimField
from timetoalign.alignment.bundle import AlignmentBundle
from timetoalign.alignment.graph import MatchStamp
from timetoalign.core import Coordinate, Interval, NumberType, TimeUnit
from timetoalign.maps import ScalarMap
from timetoalign.timelines import Timeline


def _timeline(
    timeline_id: str,
    *,
    unit: TimeUnit = TimeUnit.floating_measures,
    number_type: NumberType = NumberType.float,
) -> Timeline:
    """Create one standalone synthetic timeline."""
    return Timeline(
        length=200,
        uid=timeline_id,
        unit=unit,
        number_type=number_type,
    )


def _bundle(*timeline_ids: str) -> AlignmentBundle:
    """Create a bundle whose timelines have no group membership."""
    bundle = AlignmentBundle(id="interval-retrieval")
    for timeline_id in timeline_ids:
        bundle.add_timeline(_timeline(timeline_id), uid=timeline_id)
    return bundle


def _coordinate(value: float) -> Coordinate:
    """Create one float-canonical floating-measure coordinate."""
    return Coordinate(value, TimeUnit.floating_measures, number_type=NumberType.float)


def _interval(start: float, end: float) -> Interval:
    """Create one exact expected floating-measure interval."""
    return Interval(start=_coordinate(start), end=_coordinate(end))


def _interval_claim(
    timeline_a: str,
    start_a: float,
    end_a: float,
    timeline_b: str,
    start_b: float,
    end_b: float,
) -> MatchClaim:
    """Create one synchronous interval claim."""
    return MatchClaim(
        timeline_a_id=timeline_a,
        timeline_b_id=timeline_b,
        start_anchor=AlignmentAnchor(
            timeline_a_id=timeline_a,
            coordinate_a=_coordinate(start_a),
            timeline_b_id=timeline_b,
            coordinate_b=_coordinate(start_b),
        ),
        end_anchor=AlignmentAnchor(
            timeline_a_id=timeline_a,
            coordinate_a=_coordinate(end_a),
            timeline_b_id=timeline_b,
            coordinate_b=_coordinate(end_b),
        ),
    )


def _instant_claim(
    timeline_a: str,
    coordinate_a: float,
    timeline_b: str,
    coordinate_b: float,
) -> MatchClaim:
    """Create one synchronous instant claim."""
    return MatchClaim(
        timeline_a_id=timeline_a,
        timeline_b_id=timeline_b,
        start_anchor=AlignmentAnchor(
            timeline_a_id=timeline_a,
            coordinate_a=_coordinate(coordinate_a),
            timeline_b_id=timeline_b,
            coordinate_b=_coordinate(coordinate_b),
        ),
    )


def test_strict_interior_returns_one_claim_with_both_exact_sides() -> None:
    """A strict interior query returns the claim's two asserted intervals."""
    bundle = _bundle("mix", "track")
    bundle.add_match_claims([_interval_claim("mix", 125, 135, "track", 33, 43)])

    stamp = bundle.get_matchstamp_at(_coordinate(130), "mix")

    assert isinstance(stamp, MatchIntervalStamp)
    assert stamp.coordinate == _coordinate(130)
    assert stamp.present_timelines == ["mix", "track"]
    assert len(stamp.claims) == 1
    assert stamp.claims[0].get_interval_for("mix") == _interval(125, 135)
    assert stamp.claims[0].get_interval_for("track") == _interval(33, 43)
    plural = bundle.get_matchstamps_at([130], "mix")
    dispatched = bundle.get_matchstamp(130, "mix")
    assert len(plural) == 1
    assert isinstance(plural[0], MatchIntervalStamp)
    assert isinstance(dispatched, MatchIntervalStamp)
    assert plural[0].coordinate == stamp.coordinate
    assert dispatched.coordinate == stamp.coordinate
    assert plural[0].claims[0].get_interval_for("track") == _interval(33, 43)
    assert dispatched.claims[0].get_interval_for("track") == _interval(33, 43)


def test_match_interval_stamp_is_exported_at_both_public_levels() -> None:
    """The interval result type is available from both public namespaces."""
    import timetoalign
    import timetoalign.alignment

    assert timetoalign.MatchIntervalStamp is MatchIntervalStamp
    assert timetoalign.alignment.MatchIntervalStamp is MatchIntervalStamp
    assert "MatchIntervalStamp" in timetoalign.__all__
    assert "MatchIntervalStamp" in timetoalign.alignment.__all__


@pytest.mark.parametrize("query", [125.0, 135.0])
def test_both_interval_endpoints_are_included(query: float) -> None:
    """Closed containment includes both the start and end anchor."""
    bundle = _bundle("mix", "track")
    bundle.add_match_claims([_interval_claim("mix", 125, 135, "track", 33, 43)])

    stamp = bundle.get_matchstamp_at(query, "mix")

    assert isinstance(stamp, MatchIntervalStamp)
    assert stamp.coordinate == _coordinate(query)
    assert len(stamp.claims) == 1


def test_overlapping_claims_keep_different_timelines_in_claim_order() -> None:
    """A crossfade returns both claims in deterministic insertion order."""
    bundle = _bundle("mix", "track-a", "track-b")
    first = _interval_claim("mix", 125, 135, "track-a", 33, 43)
    second = _interval_claim("mix", 128, 138, "track-b", 1, 11)
    bundle.add_match_claims([first, second])

    stamp = bundle.get_matchstamp_at(130, "mix")

    assert isinstance(stamp, MatchIntervalStamp)
    assert stamp.present_timelines == ["mix", "track-a", "track-b"]
    assert [claim.timeline_b_id for claim in stamp.claims] == [
        "track-a",
        "track-b",
    ]
    assert [claim.get_interval_for("mix") for claim in stamp.claims] == [
        _interval(125, 135),
        _interval(128, 138),
    ]
    assert [claim.get_interval_for(claim.timeline_b_id) for claim in stamp.claims] == [
        _interval(33, 43),
        _interval(1, 11),
    ]


def test_repeated_counterpart_timeline_keeps_both_claim_entries() -> None:
    """Two mappings to one counterpart remain two independent entries."""
    bundle = _bundle("mix", "track")
    first = _interval_claim("mix", 10, 20, "track", 30, 40)
    second = _interval_claim("mix", 15, 25, "track", 50, 60)
    bundle.add_match_claims([first, second])

    stamp = bundle.get_matchstamp_at(18, "mix")

    assert isinstance(stamp, MatchIntervalStamp)
    assert stamp.present_timelines == ["mix", "track"]
    assert len(stamp.claims) == 2
    assert [claim.get_interval_for("track") for claim in stamp.claims] == [
        _interval(30, 40),
        _interval(50, 60),
    ]


def test_adjacent_claims_both_hit_their_shared_boundary() -> None:
    """Closed adjacent intervals both contain their shared endpoint."""
    bundle = _bundle("mix", "left", "right")
    bundle.add_match_claims(
        [
            _interval_claim("mix", 10, 20, "left", 0, 10),
            _interval_claim("mix", 20, 30, "right", 5, 15),
        ]
    )

    stamp = bundle.get_matchstamp_at(20, "mix")

    assert isinstance(stamp, MatchIntervalStamp)
    assert len(stamp.claims) == 2
    assert [claim.timeline_b_id for claim in stamp.claims] == ["left", "right"]


def test_mixed_instant_and_interval_hits_preserve_instant_pair() -> None:
    """An instant hit remains a coordinate pair beside an interval hit."""
    bundle = _bundle("mix", "cue", "track")
    instant = _instant_claim("mix", 15, "cue", 99)
    interval = _interval_claim("mix", 10, 20, "track", 30, 40)
    bundle.add_match_claims([instant, interval])

    stamp = bundle.get_matchstamp_at(15, "mix")

    assert isinstance(stamp, MatchIntervalStamp)
    assert len(stamp.claims) == 2
    assert stamp.claims[0].is_interval is False
    assert stamp.claims[0].start_anchor.coordinate_a == _coordinate(15)
    assert stamp.claims[0].start_anchor.coordinate_b == _coordinate(99)
    assert stamp.claims[1].get_interval_for("track") == _interval(30, 40)
    assert stamp.to_dict()["claims"][0]["timeline_a"] == {
        "value": 15.0,
        "numerator": None,
        "denominator": None,
        "unit": "floating_measures",
        "number_type": "float",
    }


def test_standalone_instant_claim_chain_reaches_third_timeline() -> None:
    """Direct claims provide transitive closure without timeline groups."""
    bundle = _bundle("A", "B", "C")
    bundle.add_match_claims(
        [_instant_claim("A", 10, "B", 20), _instant_claim("B", 20, "C", 30)]
    )

    stamp = bundle.get_matchstamp_at(10, "A")

    assert isinstance(stamp, MatchStamp)
    assert stamp.present_timelines == ["A", "B", "C"]
    assert stamp.coordinates == {
        "A": _coordinate(10),
        "B": _coordinate(20),
        "C": _coordinate(30),
    }
    assert bundle.transfer(10, "A", "C") == 30.0


def test_fraction_axis_unit_conversion_compares_once_in_exact_domain() -> None:
    """A foreign-unit fraction query lands exactly on a fraction boundary."""
    source = _timeline(
        "source", unit=TimeUnit.quarters, number_type=NumberType.fraction
    )
    source.add_conversion_map(
        ScalarMap(
            scalar=Fraction(3, 10),
            source_unit=TimeUnit.quarters,
            target_unit=TimeUnit.seconds,
        )
    )
    target = _timeline(
        "target", unit=TimeUnit.quarters, number_type=NumberType.fraction
    )
    bundle = AlignmentBundle(id="fraction-conversion")
    bundle.add_timeline(source, uid="source")
    bundle.add_timeline(target, uid="target")
    claim = MatchClaim(
        timeline_a_id="source",
        timeline_b_id="target",
        start_anchor=AlignmentAnchor(
            timeline_a_id="source",
            coordinate_a=Coordinate(Fraction(1, 3), TimeUnit.quarters),
            timeline_b_id="target",
            coordinate_b=Coordinate(Fraction(4, 3), TimeUnit.quarters),
        ),
        end_anchor=AlignmentAnchor(
            timeline_a_id="source",
            coordinate_a=Coordinate(Fraction(2, 3), TimeUnit.quarters),
            timeline_b_id="target",
            coordinate_b=Coordinate(Fraction(5, 3), TimeUnit.quarters),
        ),
    )
    bundle.add_match_claims([claim])

    stamp = bundle.get_matchstamp_at(
        Coordinate(
            Fraction(1, 10),
            TimeUnit.seconds,
            number_type=NumberType.fraction,
        ),
        "source",
    )

    assert isinstance(stamp, MatchIntervalStamp)
    assert stamp.coordinate == Coordinate(Fraction(1, 3), TimeUnit.quarters)
    assert stamp.claims[0].get_interval_for("source") == Interval(
        start=Coordinate(Fraction(1, 3), TimeUnit.quarters),
        end=Coordinate(Fraction(2, 3), TimeUnit.quarters),
    )


def test_columnar_interval_lookup_is_closed_and_materializes_matches_only() -> None:
    """The columnar lane selects an interval row at interior and endpoints."""
    claim = _interval_claim("mix", 10, 20, "track", 30, 40)
    field = MatchClaimField.from_claims([claim])

    assert len(field.at("mix", _coordinate(10))) == 1
    assert len(field.at("mix", _coordinate(15))) == 1
    assert len(field.at("mix", _coordinate(20))) == 1
    assert len(field.at("mix", _coordinate(21))) == 0

    bundle = _bundle("mix", "track")
    bundle.add_match_claim_field(field)
    stamp = bundle.get_matchstamp_at(15, "mix")
    assert isinstance(stamp, MatchIntervalStamp)
    assert stamp.claims[0].get_interval_for("track") == _interval(30, 40)


def test_columnar_fraction_interval_distinguishes_same_float_value() -> None:
    """Columnar closed containment distinguishes exact fractions at one point."""
    third = Fraction(1, 3)
    same_float = Fraction(6004799503160661, 18014398509481984)
    claim = MatchClaim(
        timeline_a_id="source",
        timeline_b_id="target",
        start_anchor=AlignmentAnchor(
            timeline_a_id="source",
            coordinate_a=Coordinate(third, TimeUnit.quarters),
            timeline_b_id="target",
            coordinate_b=Coordinate(Fraction(4, 3), TimeUnit.quarters),
        ),
        end_anchor=AlignmentAnchor(
            timeline_a_id="source",
            coordinate_a=Coordinate(third, TimeUnit.quarters),
            timeline_b_id="target",
            coordinate_b=Coordinate(Fraction(4, 3), TimeUnit.quarters),
        ),
    )
    field = MatchClaimField.from_claims([claim])

    exact_matches = field.at(
        "source",
        Coordinate(third, TimeUnit.quarters, number_type=NumberType.fraction),
    )
    rounded_matches = field.at(
        "source",
        Coordinate(same_float, TimeUnit.quarters, number_type=NumberType.fraction),
    )

    assert len(exact_matches) == 1
    assert len(rounded_matches) == 0
    interval = exact_matches[0].get_interval_for("source")
    assert interval == Interval(
        start=Coordinate(third, TimeUnit.quarters),
        end=Coordinate(third, TimeUnit.quarters),
    )
    assert isinstance(interval.start.value, Fraction)
    assert isinstance(interval.end.value, Fraction)


def test_table_rejects_interval_hits_explicitly() -> None:
    """The instant-only table lane names interval positions as unsupported."""
    bundle = _bundle("mix", "track")
    bundle.add_match_claims([_interval_claim("mix", 10, 20, "track", 30, 40)])

    with pytest.raises(NotImplementedError, match="hits include interval claims"):
        bundle.get_matchstamp_table([15], "mix")


def test_no_hit_retains_source_only_instant_stamp() -> None:
    """A position outside every claim keeps the existing no-hit result."""
    bundle = _bundle("mix", "track")
    bundle.add_match_claims([_interval_claim("mix", 10, 20, "track", 30, 40)])

    stamp = bundle.get_matchstamp_at(25, "mix")

    assert isinstance(stamp, MatchStamp)
    assert stamp.present_timelines == ["mix"]
    assert stamp.coordinates == {"mix": _coordinate(25)}
