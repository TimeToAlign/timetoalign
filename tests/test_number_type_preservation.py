"""The declared number_type is preserved at every coordinate boundary.

Validation logic is documented in ``tests/core/README.md`` under "Number
type is preserved everywhere". Every value that lands on a timeline axis is
written in that axis's declared representation, however it was obtained —
typed by a caller, converted, offset-computed, interpolated, or read back
off a query. Estimation is recorded by ``is_interpolated``, never by a
number's type.
"""

from __future__ import annotations

import math
from fractions import Fraction

from timetoalign.alignment import AlignmentBundle, MatchStamp
from timetoalign.core import Coordinate, IdCoordinate, TimeUnit
from timetoalign.maps import ScalarMap, TicksToQuarters
from timetoalign.timelines import (
    ContinuousLogicalTimeline,
    ContinuousPhysicalTimeline,
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


def test_float_input_is_expressed_in_the_target_axis_type() -> None:
    """A float query lands on an exact axis as an exact value.

    quarters are fraction-canonical, so the converted coordinate is a
    ``Fraction`` whatever the caller passed. Re-expressing the double as its
    exact dyadic is not fabrication -- the number is identical, digit for
    digit; fabrication would be inventing a tidier ratio than it really is.
    """
    ticks = DiscreteLogicalTimeline(length=1920, uid="ticks")
    ticks.add_conversion_map(TicksToQuarters(ppq=480))

    converted = ticks.convert_to(160.0, "quarters")

    assert isinstance(converted.value, Fraction)
    assert converted.value == Fraction(160.0 / 480)
    assert float(converted.value) == 160.0 / 480


def test_timestamp_coordinate_preserves_exact_child_offset() -> None:
    """Typed timestamp access retains exact parent-to-child subtraction."""
    piece = ContinuousLogicalTimeline(length=Fraction(12), uid="piece")
    movement = ContinuousLogicalTimeline(length=Fraction(4), uid="movement")
    piece.add_child(movement, offset=Fraction(11, 2))

    stamp = piece.get_timestamp(Fraction(11, 2))
    coordinate = stamp.get_coordinate_for("movement", format="coordinate")

    assert coordinate == Coordinate(Fraction(0), TimeUnit.quarters)
    assert isinstance(coordinate.value, Fraction)
    assert stamp.get_coordinate_for("movement", format="float") == 0.0


def test_float_query_is_expressed_in_the_axis_type() -> None:
    """A float query and the constructor give the same thing on one axis.

    This is the property the rule buys: a caller reasoning about a
    fraction-canonical timeline never has to inspect a value's kind to find
    out what they got, because there is one answer per axis rather than one
    per entry point.
    """
    piece = ContinuousLogicalTimeline(length=Fraction(12), uid="piece")
    movement = ContinuousLogicalTimeline(length=Fraction(4), uid="movement")
    piece.add_child(movement, offset=Fraction(11, 2))

    stamp = piece.get_timestamp(6.5)

    assert stamp.axis.value == Fraction(13, 2)
    assert isinstance(stamp.axis.value, Fraction)

    coordinate = stamp.get_coordinate_for("movement", format="coordinate")
    assert coordinate == Coordinate(Fraction(1), TimeUnit.quarters)
    assert isinstance(coordinate.value, Fraction)

    # Same literal through the constructor: one answer per axis.
    assert (
        piece.get_timestamp(9.5).axis.value == Coordinate(9.5, TimeUnit.quarters).value
    )


def test_interval_coordinate_access_preserves_exact_values() -> None:
    """Typed interval endpoints retain exact child coordinates."""
    piece = ContinuousLogicalTimeline(length=Fraction(12), uid="piece")
    movement = ContinuousLogicalTimeline(length=Fraction(4), uid="movement")
    piece.add_child(movement, offset=Fraction(11, 2))

    stamp = piece.get_interval_stamp(Fraction(11, 2), Fraction(13, 2))
    interval = stamp.get_interval("movement")

    assert interval.start == Coordinate(Fraction(0), TimeUnit.quarters)
    assert interval.end == Coordinate(Fraction(1), TimeUnit.quarters)
    assert isinstance(interval.start.value, Fraction)
    assert isinstance(interval.end.value, Fraction)


def test_group_retrieval_returns_exact_target_coordinate_or_raises() -> None:
    """Structural re-expression between group members stays exact.

    The relation between these two timelines is proven from their own
    declared origins and lengths, so converting across it is definitional
    rather than estimated and the exact value survives. Empirical
    interpolation -- reading a position off matched anchor pairs -- carries
    estimate provenance separately and is re-expressed in the target axis's
    canonical number type.
    """
    source = ContinuousLogicalTimeline(length=Fraction(12), uid="a")
    target = ContinuousLogicalTimeline(length=Fraction(24), uid="b")
    group = TimelineGroup(id="g", timelines=[source, target])

    converted = group.get_coordinate_at(
        IdCoordinate(Fraction(1, 3), TimeUnit.quarters, "a"),
        timeline_id="b",
        format="coordinate",
    )

    assert converted == Coordinate(Fraction(2, 3), TimeUnit.quarters)
    assert isinstance(converted.value, Fraction)

    partial = ContinuousLogicalTimeline(length=Fraction(2), uid="partial")
    group.add_timeline(
        partial,
        start=IdCoordinate(Fraction(2), TimeUnit.quarters, "a"),
        end=IdCoordinate(Fraction(4), TimeUnit.quarters, "a"),
    )
    import pytest

    with pytest.raises(KeyError):
        group.get_coordinate_at(
            IdCoordinate(Fraction(1), TimeUnit.quarters, "a"),
            timeline_id="partial",
        )


def test_irrational_map_output_is_expressed_in_the_axis_type() -> None:
    """Even an irrational-scaled result is written the way its axis writes.

    The computation is as inexact as its parameter; the *type* still follows
    the axis, because a type says how a number is written and not where it
    came from.
    """
    timeline = ContinuousLogicalTimeline(length=Fraction(12), uid="source")
    timeline.add_conversion_map(
        ScalarMap(
            scalar=math.sqrt(2),
            source_unit=TimeUnit.quarters,
            target_unit=TimeUnit.beats,
        )
    )

    converted = timeline.convert_to(Fraction(1, 3), TimeUnit.beats)

    # beats are fraction-canonical, so the result is a Fraction -- the exact
    # dyadic of the double the computation produced, numerically identical
    # to it. That the scaling was irrational is a fact about the map, not
    # something the coordinate's type is asked to carry.
    assert isinstance(converted.value, Fraction)
    assert converted.value == Fraction(math.sqrt(2) * Fraction(1, 3))
    assert float(converted.value) == math.sqrt(2) * Fraction(1, 3)


def test_matchstamp_typed_access_preserves_stored_fraction() -> None:
    """MatchStamp keeps raw access numeric and typed access exact."""
    stamp = MatchStamp(
        coordinates={"score": Coordinate(Fraction(1, 3), TimeUnit.quarters)},
        source_id="score",
    )

    assert stamp.get_coordinate_for("score", format="float") == 1 / 3
    coordinate = stamp.get_coordinate_for("score", format="coordinate")
    assert coordinate == Coordinate(Fraction(1, 3), TimeUnit.quarters)
    assert isinstance(coordinate.value, Fraction)


def _mixed_group() -> TimelineGroup:
    """A group whose two members declare different representations."""
    return TimelineGroup(
        id="g",
        timelines=[
            ContinuousLogicalTimeline(length=100, unit=TimeUnit.quarters, uid="clt1"),
            ContinuousPhysicalTimeline(length=60, unit=TimeUnit.seconds, uid="cpt1"),
        ],
    )


def test_group_axis_follows_the_addressed_timeline_not_the_argument() -> None:
    """A group stamp's axis is written the way its timeline writes numbers.

    Asserted in both directions on one group, because the failure this
    catches is reading the *argument's* Python type: that mistake spells a
    float query as a float on an exact axis and an int query as a Fraction on
    a float axis, and a one-directional check would clear half of it.
    """
    group = _mixed_group()

    exact = group.get_timestamp_at(9.5, "clt1")
    assert exact.axis.value == Fraction(19, 2)
    assert isinstance(exact.axis.value, Fraction)

    # Same position typed exactly: one answer per axis, not one per literal.
    assert group.get_timestamp_at(Fraction(19, 2), "clt1").axis == exact.axis
    assert isinstance(group.get_timestamp_at(10, "clt1").axis.value, Fraction)

    # seconds are float-canonical, so an exact argument is written as a float.
    for query in (10, 10.0, Fraction(10, 1)):
        axis = group.get_timestamp_at(query, "cpt1").axis
        assert axis.value == 10.0
        assert isinstance(axis.value, float)


def test_group_and_timeline_agree_on_the_same_position() -> None:
    """The group path and the timeline path give one answer, not two.

    A stamp from any source has identical structure and behaviour, so a
    caller who reaches a position through a group rather than through its
    member must not get a differently-typed axis.
    """
    group = _mixed_group()
    timeline = group.get_timeline("clt1")

    direct = timeline.get_timestamp(9.5).axis
    via_group = group.get_timestamp_at(9.5, "clt1").axis

    assert direct == via_group
    assert type(direct) is type(via_group)


def test_bundle_matchstamp_axis_follows_the_declared_type() -> None:
    """A bundle's matchstamp axis is re-expressed like every other axis.

    The bundle resolves its query against float graph nodes and WarpMap
    feeds, which is the internal lane the rule deliberately leaves alone.
    What it may not do is report that internal float as the axis: an exact
    query on a fraction-canonical timeline came back as ``79.0`` before, so
    the same position answered differently depending on the entry point.
    """
    score = ContinuousLogicalTimeline(length=100, unit=TimeUnit.quarters, uid="clt1")
    bundle = AlignmentBundle(id="b")
    bundle.add_timeline(score, uid="clt1", as_group="g")

    for query in (Fraction(79, 1), 79.0, 79):
        axis = bundle.get_matchstamp_at(query, "clt1").axis
        assert axis.value == Fraction(79, 1)
        assert isinstance(axis.value, Fraction)

    fractional = bundle.get_matchstamp_at(32.5, "clt1")
    assert fractional.axis.value == Fraction(65, 2)
    assert isinstance(fractional.axis.value, Fraction)
    assert fractional.get_coordinate_for("clt1", format="coordinate") == Coordinate(
        Fraction(65, 2), TimeUnit.quarters
    )


def test_bundle_matchstamp_axis_stays_float_on_a_float_axis() -> None:
    """The other direction: an exact query on a float axis is written float."""
    clock = ContinuousPhysicalTimeline(length=100, unit=TimeUnit.seconds, uid="cpt1")
    bundle = AlignmentBundle(id="b-float")
    bundle.add_timeline(clock, uid="cpt1", as_group="g")

    for query in (25, 25.0, Fraction(25, 1)):
        axis = bundle.get_matchstamp_at(query, "cpt1").axis
        assert axis.value == 25.0
        assert isinstance(axis.value, float)
