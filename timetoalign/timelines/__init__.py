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

Flow API (Phase 3.7 + Phase 10 MeasureUnit Architecture):
- FlowMode: Enum for flow computation modes
- MeasureUnit: Fundamental building block (one per MeasureData row)
- Typed MeasureUnit subclasses (Phase 10.2a):
  - IncompleteMeasure: Measure shorter than expected (anacrusis, final, split)
  - CompleteMeasure: Measure matching expected duration
  - OverlengthMeasure: Measure exceeding expected duration (fermata, cadenza)
  - IncompletePosition: Enum for IncompleteMeasure position classification
  - TypedMeasure: Type alias for any typed measure
- AtomicSection: Smallest indivisible traversal unit (with typed_measures)
- PlaythroughSection: Contiguous group of atomic sections (with typed_measures)
- Flow: A computed flow (sequence of measure visitations)
- FlowMap: Attached to timelines for coordinate transformation
- FlowController: Compute Flow paths from MeasureData
- load_valid_flows: Load all valid flows from a .flow.csv file

Note:
    MC ranges in AtomicSection and PlaythroughSection use the right-open
    interval convention [mc_start, mc_end), consistent with partitura and
    the TTA manuscript.

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
from .flow import (
    AtomicSection,
    CompleteMeasure,
    Flow,
    FlowController,
    FlowMap,
    FlowMode,
    IncompleteMeasure,
    IncompletePosition,
    MeasureUnit,
    OverlengthMeasure,
    PlaythroughSection,
    TypedMeasure,
    load_valid_flows,
)
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
    # Flow API (Phase 3.7 + Phase 10)
    "FlowMode",
    "MeasureUnit",
    # Typed MeasureUnit subclasses (Phase 10.2a)
    "IncompleteMeasure",
    "CompleteMeasure",
    "OverlengthMeasure",
    "IncompletePosition",
    "TypedMeasure",
    # Sections and Flow
    "Flow",
    "FlowMap",
    "FlowController",
    "AtomicSection",
    "PlaythroughSection",
    "load_valid_flows",
]
