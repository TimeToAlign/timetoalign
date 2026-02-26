"""Alignment data structures for TimeToAlign!

This module provides the core alignment infrastructure for cross-timeline
synchronization as described in the TTA manuscript.

Public API:
- AlignmentBundle: Primary entry point for alignment workflows (Phase 1+)
- TimelineGroup: Container for commensurable timelines (timestamp-based)
- GroupTimestamp: A synchronized instant across all timelines in a group
- PerfectAlignment: DEPRECATED - Use TimelineGroup.add_timeline() instead
- AlignmentAnchor: Atomic coordinate pair claim
- MatchClaim: Low-level match between two events
- MatchMetadata: Provenance information for matches
- MatchGraph: Graph of MatchClaims (networkx integration)
- MatchStamp: Cross-group timestamp at a single coordinate
- MatchLine: Ordered sequence of MatchStamps for WarpMap generation
- WarpMap: Bidirectional coordinate warping from alignment data
"""

from __future__ import annotations

from .anchors import AlignmentAnchor, MatchClaim, MatchMetadata
from .bundle import AlignmentBundle
from .filters import ClaimFilter
from .graph import MatchGraph, MatchStamp
from .groups import GroupTimestamp, PerfectAlignment, TimelineGroup
from .matching import (
    MatchResult,
    match_notes_by_attributes,
    prepare_abc_notes_for_matching,
    prepare_eep_notes_for_matching,
)
from .matchline import MatchLine
from .warpmap import WarpMap

__all__ = [
    # Bundle (Primary Entry Point)
    "AlignmentBundle",
    # Groups
    "TimelineGroup",
    "GroupTimestamp",
    # DEPRECATED - kept for backward compatibility
    "PerfectAlignment",
    # Anchors and Claims
    "AlignmentAnchor",
    "MatchClaim",
    "MatchMetadata",
    # Filters
    "ClaimFilter",
    # Graph, Stamps, and Lines
    "MatchGraph",
    "MatchStamp",
    "MatchLine",
    "WarpMap",
    # Matching
    "MatchResult",
    "match_notes_by_attributes",
    "prepare_abc_notes_for_matching",
    "prepare_eep_notes_for_matching",
]
