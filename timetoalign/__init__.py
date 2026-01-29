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

from timetoalign.alignment import (
    AlignmentAnchor,
    AlignmentBundle,
    MatchClaim,
    MatchMetadata,
    PerfectAlignment,
    TimelineGroup,
)
from timetoalign.core import (
    Coordinate,
    CoordinateSpec,
    CoordinateValue,
    CoordinateWithTimeline,
    Domain,
    EventType,
    IdCoordinate,
    IdGenerator,
    NumberType,
    OptionalCoordinate,
    ScopedId,
    TimeUnit,
)
from timetoalign.loader import EventData, EventStore, Loader, SingleEventStore
from timetoalign.maps import (
    ChainMap,
    ConversionMap,
    LinearMap,
    PiecewiseMap,
    ScalarMap,
    ShiftMap,
    TableMap,
)
from timetoalign.timelines import (
    ContinuousGraphicalTimeline,
    ContinuousLogicalTimeline,
    ContinuousPhysicalTimeline,
    DiscreteGraphicalTimeline,
    DiscreteLogicalTimeline,
    DiscretePhysicalTimeline,
    GraphicalTimeline,
    LogicalTimeline,
    PhysicalTimeline,
    Timeline,
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
    "IdCoordinate",
    "CoordinateValue",
    "CoordinateSpec",
    "CoordinateWithTimeline",
    "OptionalCoordinate",
    # IDs
    "ScopedId",
    "IdGenerator",
    # Loader
    "EventData",
    "EventStore",
    "SingleEventStore",
    "Loader",
    # Timelines
    "Timeline",
    "LogicalTimeline",
    "PhysicalTimeline",
    "GraphicalTimeline",
    "ContinuousLogicalTimeline",
    "DiscreteLogicalTimeline",
    "ContinuousPhysicalTimeline",
    "DiscretePhysicalTimeline",
    "ContinuousGraphicalTimeline",
    "DiscreteGraphicalTimeline",
    # Maps
    "ConversionMap",
    "LinearMap",
    "ScalarMap",
    "ShiftMap",
    "TableMap",
    "ChainMap",
    "PiecewiseMap",
    # Alignment
    "AlignmentBundle",
    "PerfectAlignment",
    "TimelineGroup",
    "AlignmentAnchor",
    "MatchClaim",
    "MatchMetadata",
]
