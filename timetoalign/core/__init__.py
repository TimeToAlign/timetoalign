"""Core primitives for the TimeToAlign library.

This module provides the fundamental building blocks:
- Enumerations (Domain, TimeUnit, NumberType, EventType)
- Coordinate and IdCoordinate dataclasses for timeline positions
- ScopedId and IdGenerator for identity management
- Type aliases for flexible coordinate specification (CoordinateSpec, CoordinateWithTimeline)

These types have no dependencies on other TTA modules.
"""

from __future__ import annotations

from .enums import Domain, EventType, NumberType, TimeUnit
from .ids import IdGenerator, ScopedId
from .types import (
    Coordinate,
    CoordinateSpec,
    CoordinateValue,
    CoordinateWithTimeline,
    IdCoordinate,
    OptionalCoordinate,
)

__all__ = [
    # Enums
    "Domain",
    "TimeUnit",
    "NumberType",
    "EventType",
    # Types
    "Coordinate",
    "IdCoordinate",
    "CoordinateValue",
    "CoordinateSpec",
    "CoordinateWithTimeline",
    "OptionalCoordinate",
    # IDs
    "ScopedId",
    "IdGenerator",
]
