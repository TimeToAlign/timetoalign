"""Coordinate numeric types follow the target unit's continuity."""

from __future__ import annotations

from fractions import Fraction

from timetoalign.core import Coordinate, TimeStamp, TimeUnit
from timetoalign.maps import (
    QuartersToTicks,
    SamplesToSeconds,
    ScalarMap,
    SecondsToSamples,
)
from timetoalign.timelines import (
    ContinuousLogicalTimeline,
    ContinuousPhysicalTimeline,
    DiscreteLogicalTimeline,
    DiscretePhysicalTimeline,
)


def test_seconds_to_samples_produces_integer_coordinates() -> None:
    """Integral and half-even sample conversions produce Python integers."""
    timeline = ContinuousPhysicalTimeline(length=30.0, uid="audio")
    timeline.add_conversion_map(SecondsToSamples(sample_rate=44100))

    integral = timeline.convert_to(2.5, TimeUnit.samples)
    lower_tie = timeline.convert_to(Fraction(1, 88200), TimeUnit.samples)
    upper_tie = timeline.convert_to(Fraction(3, 88200), TimeUnit.samples)

    assert integral.value == 110250
    assert isinstance(integral.value, int)
    assert lower_tie.value == 0
    assert isinstance(lower_tie.value, int)
    assert upper_tie.value == 2
    assert isinstance(upper_tie.value, int)

    stamp_value = timeline.get_timestamp(2.5).get_unit(TimeUnit.samples)
    assert stamp_value == 110250
    assert isinstance(stamp_value, int)

    sample_axis = DiscretePhysicalTimeline(length=110250, uid="sample-axis")
    sample_axis.add_conversion_map(SamplesToSeconds(sample_rate=44100))
    resolved = sample_axis.get_coordinate(
        Coordinate(Fraction(3, 88200), TimeUnit.seconds)
    )
    assert resolved.value == 2
    assert isinstance(resolved.value, int)


def test_quarters_to_ticks_produces_integer_coordinates() -> None:
    """Tick conversion applies half-to-even rounding to exact fractions."""
    timeline = ContinuousLogicalTimeline(length=Fraction(4), uid="score")
    timeline.add_conversion_map(QuartersToTicks(ppq=480))

    integral = timeline.convert_to(Fraction(5, 4), TimeUnit.ticks)
    lower_tie = timeline.convert_to(Fraction(1, 960), TimeUnit.ticks)
    upper_tie = timeline.convert_to(Fraction(3, 960), TimeUnit.ticks)

    assert integral.value == 600
    assert isinstance(integral.value, int)
    assert lower_tie.value == 0
    assert isinstance(lower_tie.value, int)
    assert upper_tie.value == 2
    assert isinstance(upper_tie.value, int)


def test_continuous_targets_express_in_the_target_units_type() -> None:
    """Each continuous target writes the result the way that unit writes.

    seconds are float-canonical and quarters fraction-canonical, so the same
    exact ratio arriving at each is expressed differently — by the axis it
    lands on, not by how the conversion computed it.
    """
    audio = DiscretePhysicalTimeline(length=44100, uid="audio-samples")
    audio.add_conversion_map(SamplesToSeconds(sample_rate=44100))
    score = DiscreteLogicalTimeline(length=960, uid="score-ticks")
    score.add_conversion_map(
        ScalarMap(
            scalar=Fraction(1, 480),
            source_unit=TimeUnit.ticks,
            target_unit=TimeUnit.quarters,
        )
    )

    seconds = audio.convert_to(22050, TimeUnit.seconds)
    quarters = score.convert_to(160, TimeUnit.quarters)
    exact_stamp = TimeStamp(axis=Fraction(160), source=score, source_id=score.id)
    stamped_quarters = exact_stamp.get_unit(TimeUnit.quarters)

    assert seconds.value == 0.5
    assert isinstance(seconds.value, float)
    assert quarters.value == Fraction(1, 3)
    assert isinstance(quarters.value, Fraction)
    assert stamped_quarters == Fraction(1, 3)
    assert isinstance(stamped_quarters, Fraction)
    assert "quarters=Fraction(1, 3)" in repr(exact_stamp)
    assert "1/3 quarters" in exact_stamp._repr_html_()
