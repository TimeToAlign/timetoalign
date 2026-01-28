"""Alignment data structures for TimeToAlign!

This module provides the core alignment infrastructure for cross-timeline
synchronization as described in the TTA manuscript.

Public API:
- PerfectAlignment: Bijective coordinate mapping definition
- TimelineGroup: Collection of perfectly aligned timelines
- AlignmentAnchor: Atomic coordinate pair claim
- MatchClaim: Low-level match between two events
- MatchMetadata: Provenance information for matches
"""

from __future__ import annotations

from .anchors import AlignmentAnchor, MatchClaim, MatchMetadata
from .groups import PerfectAlignment, TimelineGroup

__all__ = [
    # Groups
    "PerfectAlignment",
    "TimelineGroup",
    # Anchors and Claims
    "AlignmentAnchor",
    "MatchClaim",
    "MatchMetadata",
]
