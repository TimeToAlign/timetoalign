"""TimeToAlign: A library for representing and aligning musical timelines.

This library provides tools for:
- Representing musical timelines across physical, logical, and graphical domains
- Converting between different coordinate systems using ConversionMaps
- Aligning events across timelines using Match objects
- Loading and saving alignment data in Parquet and JSON formats

Basic usage:

    >>> import timetoalign as tta
    >>> from timetoalign.core import Coordinate, TimeUnit, Domain
    >>>
    >>> # Create a coordinate
    >>> c = Coordinate(120, TimeUnit.ticks)
    >>> print(c)
    120 ticks

For more information, see the documentation at https://timetoalign.readthedocs.io
"""

from __future__ import annotations

from timetoalign.core import (
    Coordinate,
    CoordinateValue,
    Domain,
    EventType,
    IdGenerator,
    NumberType,
    OptionalCoordinate,
    ScopedId,
    TimeUnit,
)

__version__ = "0.1.0"

__all__ = [
    # Version
    "__version__",
    # Enums
    "Domain",
    "TimeUnit",
    "NumberType",
    "EventType",
    # Types
    "Coordinate",
    "CoordinateValue",
    "OptionalCoordinate",
    # IDs
    "ScopedId",
    "IdGenerator",
]
