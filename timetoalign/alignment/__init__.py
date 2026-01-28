"""Alignment data structures for TimeToAlign!

This module provides the core alignment infrastructure for cross-timeline
synchronization as described in the TTA manuscript.

Public API:
- AlignmentBundle: Primary entry point for alignment workflows (Phase 1+)
- PerfectAlignment: Bijective coordinate mapping definition
- TimelineGroup: Collection of perfectly aligned timelines
- AlignmentAnchor: Atomic coordinate pair claim
- MatchClaim: Low-level match between two events
- MatchMetadata: Provenance information for matches
- MatchGraph: Graph of MatchClaims (networkx integration)
- MatchStamp: Cross-group timestamp at a single coordinate
"""

from __future__ import annotations

from .anchors import AlignmentAnchor, MatchClaim, MatchMetadata
from .bundle import AlignmentBundle
from .graph import MatchGraph, MatchStamp
from .groups import PerfectAlignment, TimelineGroup

__all__ = [
    # Bundle (Primary Entry Point)
    "AlignmentBundle",
    # Groups
    "PerfectAlignment",
    "TimelineGroup",
    # Anchors and Claims
    "AlignmentAnchor",
    "MatchClaim",
    "MatchMetadata",
    # Graph and Stamps
    "MatchGraph",
    "MatchStamp",
]
