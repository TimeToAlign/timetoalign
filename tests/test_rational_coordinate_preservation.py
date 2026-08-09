"""Regression tests for exact scalar coordinate boundaries."""

from __future__ import annotations

import math
from fractions import Fraction

from timetoalign.alignment import MatchStamp
from timetoalign.core import Coordinate, IdCoordinate, TimeUnit
from timetoalign.maps import ScalarMap, TicksToQuarters
from timetoalign.timelines import (
    ContinuousLogicalTimeline,
    DiscreteLogicalTimeline,
    TimelineGroup,
)


def test_ticks_to_quarters_preserves_exact_scalar_value() -> None:
    """An exact tick coordinate remains rational through scalar conversion."""
    ticks = DiscreteLogicalTimeline(length=1920, uid="ticks")
    ticks.add_conversion_map(TicksToQuarters(ppq=480))

    converted = ticks.convert_to(160, "quarters")

    assert converted.value == Fraction(1, 3)
    assert isinstance(converted.value, Fraction)


def test_ticks_to_quarters_keeps_float_input_inexact() -> None:
    """A float input does not acquire fabricated rational exactness."""
    ticks = DiscreteLogicalTimeline(length=1920, uid="ticks")
    ticks.add_conversion_map(TicksToQuarters(ppq=480))

    converted = ticks.convert_to(160.0, "quarters")

    assert converted.value == 160.0 / 480
    assert isinstance(converted.value, float)


def test_timestamp_coordinate_preserves_exact_child_offset() -> None:
    """Typed timestamp access retains exact parent-to-child subtraction."""
    piece = ContinuousLogicalTimeline(length=Fraction(12), uid="piece")
    movement = ContinuousLogicalTimeline(length=Fraction(4), uid="movement")
    piece.add_child(movement, offset=Fraction(11, 2))

    stamp = piece.get_timestamp(Fraction(11, 2))
    coordinate = stamp.get_coordinate("movement")

    assert coordinate == Coordinate(Fraction(0), TimeUnit.quarters)
    assert isinstance(coordinate.value, Fraction)
    assert stamp.get("movement") == 0.0
    assert isinstance(stamp.get("movement"), float)


def test_timestamp_coordinate_does_not_rationalize_float_query() -> None:
    """Typed timestamp access does not infer exactness from a float input."""
    piece = ContinuousLogicalTimeline(length=Fraction(12), uid="piece")
    movement = ContinuousLogicalTimeline(length=Fraction(4), uid="movement")
    piece.add_child(movement, offset=Fraction(11, 2))

    stamp = piece.get_timestamp(6.5)
    coordinate = stamp.get_coordinate("movement")

    assert coordinate == Coordinate(1.0, TimeUnit.quarters)
    assert isinstance(coordinate.value, float)


def test_interval_coordinate_access_preserves_exact_values() -> None:
    """Typed interval endpoints retain exact child coordinates."""
    piece = ContinuousLogicalTimeline(length=Fraction(12), uid="piece")
    movement = ContinuousLogicalTimeline(length=Fraction(4), uid="movement")
    piece.add_child(movement, offset=Fraction(11, 2))

    stamp = piece.get_interval_stamp(Fraction(11, 2), Fraction(13, 2))
    interval = stamp.get_coordinate_interval("movement")

    assert interval == (
        Coordinate(Fraction(0), TimeUnit.quarters),
        Coordinate(Fraction(1), TimeUnit.quarters),
    )
    assert isinstance(interval[0].value, Fraction)
    assert isinstance(interval[1].value, Fraction)
    assert stamp["movement"] == (0.0, 1.0)


def test_group_convert_returns_exact_target_coordinate_or_none() -> None:
    """Group conversion exposes exact values only at its typed boundary."""
    source = ContinuousLogicalTimeline(length=Fraction(12), uid="a")
    target = ContinuousLogicalTimeline(length=Fraction(24), uid="b")
    group = TimelineGroup(id="g", timelines=[source, target])

    converted = group.convert(Fraction(1, 3), "a", "b")

    assert converted == Coordinate(Fraction(2, 3), TimeUnit.quarters)
    assert isinstance(converted.value, Fraction)

    partial = ContinuousLogicalTimeline(length=Fraction(2), uid="partial")
    group.add_timeline(
        partial,
        start=IdCoordinate(Fraction(2), TimeUnit.quarters, "a"),
        end=IdCoordinate(Fraction(4), TimeUnit.quarters, "a"),
    )
    assert group.convert(Fraction(1), "a", "partial") is None


def test_irrational_map_output_remains_float() -> None:
    """An irrational conversion parameter does not fabricate a Fraction."""
    timeline = ContinuousLogicalTimeline(length=Fraction(12), uid="source")
    timeline.add_conversion_map(
        ScalarMap(
            scalar=math.sqrt(2),
            source_unit=TimeUnit.quarters,
            target_unit=TimeUnit.beats,
        )
    )

    converted = timeline.convert_to(Fraction(1, 3), TimeUnit.beats)

    assert converted.value == math.sqrt(2) * Fraction(1, 3)
    assert isinstance(converted.value, float)


def test_matchstamp_typed_access_preserves_stored_fraction() -> None:
    """MatchStamp keeps raw access numeric and typed access exact."""
    stamp = MatchStamp(
        coordinates={"score": Fraction(1, 3)},
        units={"score": TimeUnit.quarters.value},
    )

    assert stamp.get("score") == 1 / 3
    assert isinstance(stamp.get("score"), float)
    coordinate = stamp.get_coordinate("score")
    assert coordinate == Coordinate(Fraction(1, 3), TimeUnit.quarters)
    assert isinstance(coordinate.value, Fraction)
