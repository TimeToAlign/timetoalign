"""Typed construction helpers shared by alignment tests."""

from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction
from typing import Any

from timetoalign.alignment.graph import MatchStamp
from timetoalign.core import Coordinate, TimeUnit


def make_match_stamp(
    *,
    coordinates: Mapping[str, Coordinate | int | float | Fraction],
    source_id: str | None = None,
    coordinate_units: Mapping[str, TimeUnit | str] | None = None,
    **kwargs: Any,
) -> MatchStamp:
    """Construct a MatchStamp with canonical typed coordinate storage.

    Args:
        coordinates: Timeline coordinates, already typed or numeric fixture values.
        source_id: Source timeline ID, defaulting to the first coordinate key.
        coordinate_units: Units for numeric fixture values; unspecified values use
            the dimensionless number unit.
        **kwargs: Remaining MatchStamp constructor fields.

    Returns:
        A MatchStamp whose coordinate entries are plain Coordinate scalars.
    """
    units = coordinate_units or {}
    typed = {
        timeline_id: (
            value
            if type(value) is Coordinate
            else Coordinate(value, TimeUnit(units.get(timeline_id, TimeUnit.number)))
        )
        for timeline_id, value in coordinates.items()
    }
    resolved_source = source_id or next(iter(typed), None)
    if resolved_source is None:
        raise ValueError("A typed test stamp requires at least one coordinate")
    return MatchStamp(coordinates=typed, source_id=resolved_source, **kwargs)
