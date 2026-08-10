"""Exact tests for the paired Interval scalar and semantic field."""

from __future__ import annotations

from fractions import Fraction

import pytest

from timetoalign.core import (
    Coordinate,
    CoordinateField,
    Duration,
    DurationField,
    Interval,
    IntervalField,
    NumberType,
    TimeUnit,
)


def _quarter(
    value: Fraction, number_type: NumberType = NumberType.fraction
) -> Coordinate:
    return Coordinate(value, TimeUnit.quarters, number_type=number_type)


def test_interval_preserves_exact_duration_metadata() -> None:
    """Duration uses the endpoints' exact value, unit, and number type."""
    interval = Interval(start=_quarter(Fraction(1, 2)), end=_quarter(Fraction(5, 2)))

    assert interval.unit is TimeUnit.quarters
    assert interval.number_type is NumberType.fraction
    assert interval.duration == Duration(
        Fraction(2), TimeUnit.quarters, number_type=NumberType.fraction
    )


def test_interval_accepts_zero_length() -> None:
    """Equal endpoints form a valid zero-length half-open interval."""
    endpoint = _quarter(Fraction(3, 2))

    assert Interval(start=endpoint, end=endpoint).duration.value == Fraction(0)


def test_interval_rejects_reversed_endpoints() -> None:
    """A reversed interval cannot manufacture a negative duration."""
    with pytest.raises(ValueError, match="start must not exceed"):
        Interval(start=_quarter(Fraction(2)), end=_quarter(Fraction(1)))


def test_interval_rejects_mixed_units() -> None:
    """Both endpoints must describe one coordinate axis."""
    with pytest.raises(ValueError, match="same unit"):
        Interval(
            start=_quarter(Fraction(1)),
            end=Coordinate(2.0, TimeUnit.seconds),
        )


def test_interval_rejects_mixed_number_types() -> None:
    """Both endpoints must share one canonical representation."""
    with pytest.raises(ValueError, match="same number_type"):
        Interval(
            start=_quarter(Fraction(1)),
            end=_quarter(Fraction(2), NumberType.float),
        )


def test_interval_field_materializes_scalar_and_vector_accessors() -> None:
    """Field indexing and vector accessors retain exact endpoint values."""
    interval = Interval(start=_quarter(Fraction(1, 2)), end=_quarter(Fraction(5, 2)))
    field = IntervalField.from_intervals([interval, None])

    assert field[0] == interval
    assert field[1] is None
    assert isinstance(field.start, CoordinateField)
    assert isinstance(field.end, CoordinateField)
    assert isinstance(field.duration, DurationField)
    assert field.start[0] == interval.start
    assert field.end[0] == interval.end
    assert field.duration[0] == interval.duration
    assert field.start[1] is None
    assert field.end[1] is None
    assert field.duration[1] is None


def test_empty_interval_field_requires_explicit_axis_metadata() -> None:
    """Empty storage cannot infer its shared axis declaration."""
    with pytest.raises(ValueError, match="requires unit and number_type"):
        IntervalField.from_intervals([])

    field = IntervalField.from_intervals(
        [], unit=TimeUnit.seconds, number_type=NumberType.float
    )
    assert field.unit is TimeUnit.seconds
    assert field.number_type is NumberType.float
    assert len(field) == 0
