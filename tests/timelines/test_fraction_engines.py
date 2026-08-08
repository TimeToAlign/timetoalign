"""Regression tests for exact coordinate propagation through timeline engines."""

from __future__ import annotations

from fractions import Fraction

from timetoalign.core import NumberType, TimeUnit, struct_to_rational
from timetoalign.timelines import Timeline


def _fraction_timeline(uid: str, length: Fraction) -> Timeline:
    """Create a fraction-valued timeline in quarter-note units."""
    return Timeline(
        length=length,
        unit=TimeUnit.quarters,
        number_type=NumberType.fraction,
        uid=uid,
    )


def _assert_coordinate_struct_is_consistent(value: object) -> None:
    """Require every exact coordinate struct to agree with its float value."""
    if not isinstance(value, dict) or value.get("numerator") is None:
        return
    rational = struct_to_rational(value)
    assert value["value"] == float(rational)


def test_child_event_offsets_preserve_exact_coordinate_pairs() -> None:
    """Child event coordinates keep exact pairs after parent-space shifting."""
    parent = _fraction_timeline("parent", Fraction(4))
    child = _fraction_timeline("child", Fraction(2))
    child.add_events(
        [
            {
                "id": "child:instant",
                "event_type": "Beat",
                "instant": Fraction(1, 3),
            },
            {
                "id": "child:note",
                "event_type": "Note",
                "start": Fraction(1, 3),
                "end": Fraction(5, 6),
            },
        ]
    )
    parent.add_child(child, offset=Fraction(1, 6))

    single = parent.get_event("child:note")
    bulk = {event["id"]: event for event in parent.get_events()}

    assert single is not None
    assert single["start"]["value"] == float(Fraction(1, 2))
    assert single["start"]["numerator"] == 1
    assert single["start"]["denominator"] == 2
    assert struct_to_rational(single["start"]) == Fraction(1, 2)
    assert single["end"]["value"] == 1.0
    assert single["end"]["numerator"] == 1
    assert single["end"]["denominator"] == 1
    assert struct_to_rational(single["end"]) == Fraction(1)
    shifted_instant = parent.get_event("child:instant")
    assert shifted_instant is not None
    assert struct_to_rational(shifted_instant["start"]) == Fraction(1, 2)
    assert bulk["child:note"]["start"] == single["start"]
    assert bulk["child:note"]["end"] == single["end"]

    for event in [single, *bulk.values()]:
        for field in ("start", "end", "duration"):
            _assert_coordinate_struct_is_consistent(event.get(field))


def test_segment_extraction_preserves_exact_pairs_after_shift() -> None:
    """Copied segment events retain exact values relative to the segment start."""
    source = _fraction_timeline("source", Fraction(3))
    source.add_events(
        [
            {
                "id": "source:note",
                "event_type": "Note",
                "start": Fraction(1, 2),
                "end": Fraction(3, 2),
            }
        ]
    )

    segments = source.create_segment_line(
        [Fraction(1, 3), Fraction(2)],
        copy_events=True,
    )
    copied = list(
        segments._children[segments._segment_order[0]].get_events(
            include_children=False
        )
    )[0]

    assert copied["start"]["numerator"] == 1
    assert copied["start"]["denominator"] == 6
    assert struct_to_rational(copied["start"]) == Fraction(1, 6)
    assert copied["end"]["numerator"] == 7
    assert copied["end"]["denominator"] == 6
    assert struct_to_rational(copied["end"]) == Fraction(7, 6)
    assert copied["duration"]["numerator"] == 1
    assert copied["duration"]["denominator"] == 1
    assert struct_to_rational(copied["duration"]) == Fraction(1)
    for field in ("start", "end", "duration"):
        _assert_coordinate_struct_is_consistent(copied[field])


def test_region_and_grouped_segment_boundaries_preserve_exact_values() -> None:
    """Region-derived boundaries retain exact event and input coordinates."""
    timeline = _fraction_timeline("regions", Fraction(2))
    timeline.add_events(
        [
            {
                "id": "regions:break",
                "event_type": "Break",
                "instant": Fraction(1, 3),
                "breaks": True,
            },
            {
                "id": "regions:one",
                "event_type": "Marker",
                "start": Fraction(1, 3),
                "end": Fraction(2, 3),
                "group": "one",
            },
            {
                "id": "regions:two",
                "event_type": "Marker",
                "start": Fraction(2, 3),
                "end": Fraction(1),
                "group": "two",
            },
        ]
    )

    regions = timeline.create_regions_from_boundaries([Fraction(1, 3), Fraction(1)])
    assert regions[0].start.value == Fraction(1, 3)
    assert regions[0].end.value == Fraction(1)

    split_regions = timeline.create_regions_by_splitting("breaks", prefix="split")
    assert split_regions[1].start.value == Fraction(1, 3)
    assert split_regions[1].end.value == Fraction(2)

    grouped_regions = timeline.create_regions_by_grouping("group")
    assert grouped_regions[0].start.value == Fraction(1, 3)
    assert grouped_regions[0].end.value == Fraction(2, 3)

    grouped_segments = timeline.create_segment_line_by_grouping("group")
    grouped_child = grouped_segments._children[grouped_segments._segment_order[0]]
    assert grouped_child.length.value == Fraction(1, 3)


def test_fraction_timestamp_coordinate_uses_stored_pair() -> None:
    """Exact event coordinates materialize as Fractions without changing get()."""
    timeline = _fraction_timeline("fraction", Fraction(2))
    timeline.add_events(
        [{"id": "fraction:beat", "event_type": "Beat", "instant": Fraction(2, 3)}]
    )
    stored = timeline.events.table.column("start").combine_chunks()[0].as_py()

    stamp = timeline.get_timestamp(stored["value"])
    coordinate = stamp.get_coordinate(timeline.id)

    assert stamp.get(timeline.id) == stored["value"]
    assert isinstance(stamp.get(timeline.id), float)
    assert coordinate is not None
    assert coordinate.value == Fraction(2, 3)
    assert isinstance(coordinate.value, Fraction)

    direct_query = timeline.get_timestamp(0.5)
    assert direct_query.is_interpolated is False
