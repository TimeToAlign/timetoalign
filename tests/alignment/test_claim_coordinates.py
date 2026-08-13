"""Regression tests for coordinates recorded by TimeSkeleton claims."""

from fractions import Fraction

import pytest

from timetoalign import Coordinate, Measure, SectionHierarchy, TimeSkeleton
from timetoalign.core import IdCoordinate, MeasureId, NumberType, TimeUnit
from timetoalign.timelines import (
    ContinuousLogicalTimeline,
    DiscretePhysicalTimeline,
)


def test_coordinate_keeps_its_value_unit_and_number_type() -> None:
    measures = [
        Measure(
            id=f"coordinate-m{i}",
            time_signature="3/4",
            actual_length=Fraction(3),
            nominal_length=Fraction(3),
        )
        for i in range(1, 4)
    ]
    skeleton = TimeSkeleton(SectionHierarchy.from_measures(measures))
    participant = DiscretePhysicalTimeline(length=1_000_000, uid="coordinate-samples")
    skeleton.attach(participant)

    claim = skeleton.create_match_claim(
        participant.id,
        at=MeasureId(1),
        coordinate=Coordinate(0.35, TimeUnit.seconds),
    )
    coordinate = claim.start_anchor.coordinate_a

    assert type(coordinate) is Coordinate
    assert coordinate.value == 0.35
    assert type(coordinate.value) is float
    assert coordinate.unit is TimeUnit.seconds
    assert coordinate.number_type is NumberType.float


def test_raw_int_uses_participant_unit_and_number_type() -> None:
    measures = [
        Measure(
            id=f"raw-int-m{i}",
            time_signature="3/4",
            actual_length=Fraction(3),
            nominal_length=Fraction(3),
        )
        for i in range(1, 4)
    ]
    skeleton = TimeSkeleton(SectionHierarchy.from_measures(measures))
    participant = DiscretePhysicalTimeline(length=1_000_000, uid="raw-int-samples")
    skeleton.attach(participant)

    claim = skeleton.create_match_claim(
        participant.id, at=MeasureId(1), coordinate=52_000
    )
    coordinate = claim.start_anchor.coordinate_a

    assert coordinate.value == 52_000
    assert type(coordinate.value) is int
    assert coordinate.unit is TimeUnit.samples
    assert coordinate.number_type is NumberType.int


def test_raw_fraction_uses_participant_unit_and_number_type() -> None:
    measures = [
        Measure(
            id=f"raw-fraction-m{i}",
            time_signature="3/4",
            actual_length=Fraction(3),
            nominal_length=Fraction(3),
        )
        for i in range(1, 4)
    ]
    skeleton = TimeSkeleton(SectionHierarchy.from_measures(measures))
    participant = ContinuousLogicalTimeline(
        length=Fraction(9), uid="raw-fraction-quarters"
    )
    skeleton.attach(participant)

    claim = skeleton.create_match_claim(
        participant.id, at=MeasureId(1), coordinate=Fraction(7, 3)
    )
    coordinate = claim.start_anchor.coordinate_a

    assert coordinate.value == Fraction(7, 3)
    assert type(coordinate.value) is Fraction
    assert coordinate.unit is TimeUnit.quarters
    assert coordinate.number_type is NumberType.fraction


def test_matching_id_coordinate_keeps_its_own_coordinate_data() -> None:
    measures = [
        Measure(
            id=f"matching-id-m{i}",
            time_signature="3/4",
            actual_length=Fraction(3),
            nominal_length=Fraction(3),
        )
        for i in range(1, 4)
    ]
    skeleton = TimeSkeleton(SectionHierarchy.from_measures(measures))
    participant = DiscretePhysicalTimeline(length=1_000_000, uid="matching-id-samples")
    skeleton.attach(participant)

    claim = skeleton.create_match_claim(
        participant.id,
        at=MeasureId(1),
        coordinate=IdCoordinate(
            0.35,
            TimeUnit.seconds,
            participant.id,
            number_type=NumberType.float,
        ),
    )
    coordinate = claim.start_anchor.coordinate_a

    assert type(coordinate) is Coordinate
    assert coordinate.value == 0.35
    assert type(coordinate.value) is float
    assert coordinate.unit is TimeUnit.seconds
    assert coordinate.number_type is NumberType.float


def test_mismatched_id_coordinate_names_both_timeline_ids() -> None:
    measures = [
        Measure(
            id=f"mismatched-id-m{i}",
            time_signature="3/4",
            actual_length=Fraction(3),
            nominal_length=Fraction(3),
        )
        for i in range(1, 4)
    ]
    skeleton = TimeSkeleton(SectionHierarchy.from_measures(measures))
    participant = DiscretePhysicalTimeline(
        length=1_000_000, uid="mismatched-id-samples"
    )
    skeleton.attach(participant)

    with pytest.raises(ValueError) as exc_info:
        skeleton.create_match_claim(
            participant.id,
            at=MeasureId(1),
            coordinate=IdCoordinate(0.35, TimeUnit.seconds, "different-timeline"),
        )

    message = str(exc_info.value)
    assert "different-timeline" in message
    assert participant.id in message


def test_attach_returns_skeleton_and_supports_chaining() -> None:
    measures = [
        Measure(
            id=f"attach-m{i}",
            time_signature="3/4",
            actual_length=Fraction(3),
            nominal_length=Fraction(3),
        )
        for i in range(1, 4)
    ]
    skeleton = TimeSkeleton(SectionHierarchy.from_measures(measures))
    samples = DiscretePhysicalTimeline(length=1_000_000, uid="attach-samples")
    quarters = ContinuousLogicalTimeline(length=Fraction(9), uid="attach-quarters")

    assert skeleton.attach(samples).attach(quarters) is skeleton
    assert skeleton.attach(samples) is skeleton
    assert skeleton.n_participants == 2
