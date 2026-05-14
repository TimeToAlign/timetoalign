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
    ActivationCondition,
    ColumnNaming,
    ColumnRole,
    Domain,
    EventType,
    ExtrapolationPolicy,
    FancyStrEnum,
    FlowControlType,
    FlowMode,
    IncompletePosition,
    InterpolationKind,
    IntervalPolicy,
    NumberType,
    PartitionMode,
    TimeUnit,
)
from .ids import IdGenerator, ScopedId, TimelineIdGenerator, resolve_id, resolve_ids
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
    "FancyStrEnum",
    "ActivationCondition",
    "ColumnNaming",
    "ColumnRole",
    "Domain",
    "EventType",
    "ExtrapolationPolicy",
    "FlowControlType",
    "FlowMode",
    "IncompletePosition",
    "InterpolationKind",
    "IntervalPolicy",
    "NumberType",
    "PartitionMode",
    "TimeUnit",
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
    "TimelineIdGenerator",
    "resolve_id",
    "resolve_ids",
]
