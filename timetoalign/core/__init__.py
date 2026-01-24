"""Core primitives for the TimeToAlign library.

This module provides the fundamental building blocks:
- Enumerations (Domain, TimeUnit, NumberType, EventType)
- Coordinate dataclass for timeline positions
- ScopedId and IdGenerator for identity management

These types have no dependencies on other TTA modules.
"""

from __future__ import annotations

from .enums import Domain, EventType, NumberType, TimeUnit
from .ids import IdGenerator, ScopedId
from .types import Coordinate, CoordinateValue, OptionalCoordinate

__all__ = [
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
