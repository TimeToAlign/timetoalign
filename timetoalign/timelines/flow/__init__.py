"""Compute, represent, map, and unfold musical flow paths."""

from __future__ import annotations

from .controller import FlowControllerBase, ScoreFlowController
from .flowmap import FlowMap, FlowMapSection
from .measures import (
    CompleteMeasure,
    CompleteMeasureGroup,
    IncompleteGroup,
    IncompleteMeasure,
    MeasureGroup,
    MeasureUnit,
    OverlengthGroup,
    OverlengthMeasure,
    SplitMeasure,
)
from .measures import TypedMeasure as TypedMeasure
from .measures import (
    VoltaGroup,
)
from .naming import SegmentNameGenerator
from .sections import (
    AtomicSection,
    Flow,
    FlowDiagnostic,
    PlaythroughSection,
    _as_interval,
    _coerce_intervals,
    load_valid_flows,
)
from .unfolding import compute_qb_sections, create_unfolded_timeline

__all__ = [
    "SegmentNameGenerator",
    "MeasureUnit",
    "IncompleteMeasure",
    "CompleteMeasure",
    "OverlengthMeasure",
    "MeasureGroup",
    "SplitMeasure",
    "IncompleteGroup",
    "VoltaGroup",
    "CompleteMeasureGroup",
    "OverlengthGroup",
    "AtomicSection",
    "FlowDiagnostic",
    "PlaythroughSection",
    "Flow",
    "load_valid_flows",
    "FlowMapSection",
    "FlowMap",
    "FlowControllerBase",
    "ScoreFlowController",
    "compute_qb_sections",
    "create_unfolded_timeline",
]
