"""Core primitives for the TimeToAlign library.

This module provides the fundamental building blocks:
- Enumerations (Domain, TimeUnit, NumberType, EventType)
- Coordinate and IdCoordinate dataclasses for timeline positions
- ScopedId and IdGenerator for identity management
- TimeStamp and TimeIntervalStamp for unified coordinate resolution
- Type alias CoordinateSpec for flexible coordinate specification

These types have no dependencies on other TTA modules.
"""

from __future__ import annotations

from .enums import (
    ColumnNaming,
    Domain,
    EventType,
    FlowControlType,
    NumberType,
    TimeUnit,
)
from .ids import IdGenerator, ScopedId
from .timestamp import (
    TimeIntervalStamp,
    TimeStamp,
    TimeStampSource,
    timestamp_table_to_dataframe,
)
from .types import (
    Coordinate,
    CoordinateSpec,
    CoordinateValue,
    IdCoordinate,
    OptionalCoordinate,
)

__all__ = [
    # Enums
    "ColumnNaming",
    "Domain",
    "TimeUnit",
    "NumberType",
    "EventType",
    "FlowControlType",
    # Types
    "Coordinate",
    "IdCoordinate",
    "CoordinateValue",
    "CoordinateSpec",
    "OptionalCoordinate",
    # Timestamps
    "TimeStamp",
    "TimeIntervalStamp",
    "TimeStampSource",
    "timestamp_table_to_dataframe",
    # IDs
    "ScopedId",
    "IdGenerator",
]
