"""Display module for TimeToAlign! ASCII visualization.

This module provides pure ASCII/Unicode terminal display for timelines,
timeline groups, alignment bundles, and flow control structures.
Zero external dependencies.

Public API:
    - timeline_diagram(): Generate ASCII diagram for a Timeline
    - group_diagram(): Generate ASCII diagram for a TimelineGroup
    - bundle_diagram(): Generate ASCII diagram for an AlignmentBundle
    - flow_control_diagram(): Generate ASCII diagram for a ScoreFlowController
    - flow_diagram(): Generate ASCII diagram for a Flow
    - flow_comparison_diagram(): Generate side-by-side diff of two Flows
    - TIMELINE_CHARS: Character mapping for the 6 timeline types
    - REGION_CHARS: Character mapping for region display
    - FLOW_CHARS: Character mapping for flow control display
"""

from __future__ import annotations

from timetoalign.display.ascii import (
    FLOW_CHARS,
    FLOW_CHARS_ASCII,
    REGION_CHARS,
    REGION_CHARS_ASCII,
    TIMELINE_CHARS,
    TIMELINE_CHARS_ASCII,
    Diagram,
    bundle_diagram,
    flow_comparison_diagram,
    flow_control_diagram,
    flow_diagram,
    group_diagram,
    timeline_diagram,
)
from timetoalign.display.html import affordance_html, affordance_line, code

__all__ = [
    "Diagram",
    "timeline_diagram",
    "group_diagram",
    "bundle_diagram",
    "flow_control_diagram",
    "flow_diagram",
    "flow_comparison_diagram",
    "TIMELINE_CHARS",
    "TIMELINE_CHARS_ASCII",
    "REGION_CHARS",
    "REGION_CHARS_ASCII",
    "FLOW_CHARS",
    "FLOW_CHARS_ASCII",
    "affordance_html",
    "affordance_line",
    "code",
]
