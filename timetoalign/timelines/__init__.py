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

Flow API (MeasureUnit architecture):
- MeasureUnit: Fundamental building block (one per MeasureData row)
- Typed MeasureUnit subclasses (Typing step):
  - IncompleteMeasure: Measure shorter than expected (anacrusis, final, split)
  - CompleteMeasure: Measure matching expected duration
  - OverlengthMeasure: Measure exceeding expected duration (fermata, cadenza)
  - TypedMeasure: Type alias for any typed measure
- MeasureGroup hierarchy (Grouping step):
  - MeasureGroup: Base class for groupings of typed measures
  - SplitMeasure: IncompleteMeasures that together form a complete unit
  - IncompleteGroup: Isolated IncompleteMeasures (will merge in playthrough)
  - VoltaGroup: Measures under same volta bracket
  - CompleteMeasureGroup: Adjacent CompleteMeasures
  - OverlengthGroup: OverlengthMeasures
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
    CompleteMeasureGroup,
    Flow,
    FlowController,
    FlowControllerBase,
    FlowMap,
    FlowMapSection,
    IncompleteGroup,
    IncompleteMeasure,
    MeasureGroup,
    MeasureUnit,
    OverlengthGroup,
    OverlengthMeasure,
    PlaythroughSection,
    ScoreFlowController,
    SegmentNameGenerator,
    SplitMeasure,
    TypedMeasure,
    VoltaGroup,
    create_unfolded_timeline,
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
    # Flow API
    "MeasureUnit",
    # Typed MeasureUnit subclasses (Typing step)
    "IncompleteMeasure",
    "CompleteMeasure",
    "OverlengthMeasure",
    "TypedMeasure",
    # MeasureGroup hierarchy (Grouping step)
    "MeasureGroup",
    "SplitMeasure",
    "IncompleteGroup",
    "VoltaGroup",
    "CompleteMeasureGroup",
    "OverlengthGroup",
    # Sections and Flow
    "Flow",
    "FlowMap",
    "FlowMapSection",
    "FlowController",  # Backwards-compatible alias for ScoreFlowController
    "FlowControllerBase",  # Abstract base class
    "ScoreFlowController",  # Concrete implementation for score data
    "SegmentNameGenerator",  # Customizable atomic-section labelling
    "AtomicSection",
    "PlaythroughSection",
    "load_valid_flows",
    "create_unfolded_timeline",  # Create unfolded timeline from flow
]
