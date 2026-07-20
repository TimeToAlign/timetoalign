"""Tests for shared coordinate decomposition and timeline resolution."""

from __future__ import annotations

from fractions import Fraction

import pytest

from timetoalign import (
    Coordinate,
    IdCoordinate,
    ResolvedCoordinate,
    Timeline,
    TimeUnit,
    resolve_coordinate_spec,
)
from timetoalign.maps import ScalarMap


@pytest.mark.parametrize("value", [7, 2.5, Fraction(3, 4)])
def test_raw_coordinate_spec_passthrough(value: int | float | Fraction) -> None:
    """Raw numeric inputs retain their exact value and optional timeline ID."""
    assert resolve_coordinate_spec(value, timeline_id="axis") == ResolvedCoordinate(
        value, "axis", None
    )


def test_coordinate_decomposition() -> None:
    """A Coordinate contributes its value and unit."""
    coordinate = Coordinate(Fraction(5, 3), TimeUnit.quarters)
    assert resolve_coordinate_spec(coordinate) == ResolvedCoordinate(
        Fraction(5, 3), None, TimeUnit.quarters
    )


def test_id_coordinate_decomposition() -> None:
    """An IdCoordinate contributes its own timeline ID."""
    coordinate = IdCoordinate(11, TimeUnit.ticks, "notes")
    assert resolve_coordinate_spec(coordinate) == ResolvedCoordinate(
        11, "notes", TimeUnit.ticks
    )


def test_id_coordinate_conflict() -> None:
    """Conflicting explicit and embedded timeline IDs are rejected."""
    coordinate = IdCoordinate(11, TimeUnit.ticks, "notes")
    with pytest.raises(ValueError, match="axis.*notes"):
        resolve_coordinate_spec(coordinate, timeline_id="axis")


def test_coordinate_spec_rejects_unsupported_type() -> None:
    """Unsupported input reports its concrete type."""
    with pytest.raises(TypeError, match="object"):
        resolve_coordinate_spec(object())  # type: ignore[arg-type]


def test_timeline_resolves_native_fraction_exactly() -> None:
    """Native-unit Fraction values are preserved without float coercion."""
    timeline = Timeline(length=8, unit=TimeUnit.quarters, uid="score")
    resolved = timeline.resolve_coordinate(
        Coordinate(Fraction(7, 4), TimeUnit.quarters)
    )
    assert resolved == Coordinate(Fraction(7, 4), TimeUnit.quarters)
    assert isinstance(resolved.value, Fraction)


def test_timeline_resolves_foreign_unit_through_cmap() -> None:
    """A foreign-unit coordinate is inverted through the attached C-Map."""
    timeline = Timeline(length=10, unit=TimeUnit.seconds, uid="audio")
    timeline.add_conversion_map(
        ScalarMap(
            scalar=1000,
            source_unit=TimeUnit.seconds,
            target_unit=TimeUnit.milliseconds,
        )
    )
    assert timeline.resolve_coordinate(
        Coordinate(2500, TimeUnit.milliseconds)
    ) == Coordinate(2.5, TimeUnit.seconds)


def test_timeline_rejects_missing_conversion_path() -> None:
    """A missing C-Map reports both units and the timeline ID."""
    timeline = Timeline(length=10, unit=TimeUnit.seconds, uid="audio")
    with pytest.raises(ValueError, match="quarters.*seconds.*audio"):
        timeline.resolve_coordinate(Coordinate(2, TimeUnit.quarters))


def test_timeline_rejects_unknown_timeline_id() -> None:
    """A non-child timeline ID is never treated as a native coordinate."""
    timeline = Timeline(length=10, unit=TimeUnit.seconds, uid="audio")
    with pytest.raises(ValueError, match="missing.*audio"):
        timeline.resolve_coordinate(IdCoordinate(2, TimeUnit.seconds, "missing"))


def test_timeline_resolves_direct_child_offset_exactly() -> None:
    """A direct child's local coordinate receives the exact stored offset."""
    parent = Timeline(length=20, unit=TimeUnit.quarters, uid="score")
    child = Timeline(length=5, unit=TimeUnit.quarters, uid="measure")
    parent.add_child(child, offset=Fraction(9, 2))

    resolved = parent.resolve_coordinate(
        IdCoordinate(Fraction(3, 2), TimeUnit.quarters, "measure")
    )
    assert resolved == Coordinate(Fraction(6), TimeUnit.quarters)
    assert isinstance(resolved.value, Fraction)
