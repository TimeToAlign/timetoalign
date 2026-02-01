"""Timeline classes for TimeToAlign!

This module provides the 6 timeline types (3 domains x 2 modalities):

Domains:
- Logical: Symbolic/musical time (beats, quarters, ticks)
- Physical: Acoustic/real time (seconds, samples)
- Graphical: Visual/spatial (pixels, coordinates)

Modalities:
- Continuous: Float or Fraction coordinates
- Discrete: Integer coordinates

Specialized timelines:
- BeatGrid: Metrical timeline with measure/beat C-Maps
- SegmentLine: Timeline with contiguous child segments

Structural components:
- Region: Named TimeInterval (not a timeline itself)

Flow API (Phase 3.7):
- FlowMode: Enum for flow computation modes
- FlowStep: A single step in a Flow sequence
- Flow: A computed flow (sequence of measure visitations)
- FlowMap: Attached to timelines for coordinate transformation
- FlowController: Compute Flow paths from MeasureData

Public API:
- Timeline: Base class
- ContinuousLogicalTimeline, DiscreteLogicalTimeline
- ContinuousPhysicalTimeline, DiscretePhysicalTimeline
- ContinuousGraphicalTimeline, DiscreteGraphicalTimeline
- BeatGrid: Metrical timeline for measure/beat information
- SegmentLine: Timeline where all children are contiguous
- Region: Named TimeInterval for partitioning
- create_timeline: Factory function for creating timelines from bundles/stores
- get_timeline_class: Factory for getting timeline class by domain/modality
"""

from __future__ import annotations

from .base import Timeline
from .beatgrid import BeatGrid
from .factory import create_timeline
from .flow import Flow, FlowController, FlowMap, FlowMode, FlowStep
from .regions import Region
from .types import (
    ContinuousGraphicalTimeline,
    ContinuousLogicalTimeline,
    ContinuousPhysicalTimeline,
    DiscreteGraphicalTimeline,
    DiscreteLogicalTimeline,
    DiscretePhysicalTimeline,
    GraphicalTimeline,
    LogicalTimeline,
    PhysicalTimeline,
    SegmentLine,
    get_timeline_class,
)

__all__ = [
    # Base
    "Timeline",
    # Factory
    "create_timeline",
    "get_timeline_class",
    # Domain base classes
    "LogicalTimeline",
    "PhysicalTimeline",
    "GraphicalTimeline",
    # Concrete types (6)
    "ContinuousLogicalTimeline",
    "DiscreteLogicalTimeline",
    "ContinuousPhysicalTimeline",
    "DiscretePhysicalTimeline",
    "ContinuousGraphicalTimeline",
    "DiscreteGraphicalTimeline",
    # Specialized timelines
    "BeatGrid",
    "SegmentLine",
    # Structural components
    "Region",
    # Flow API (Phase 3.7)
    "FlowMode",
    "FlowStep",
    "Flow",
    "FlowMap",
    "FlowController",
]
