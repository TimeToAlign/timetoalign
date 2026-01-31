"""Path API for graphical timelines in TimeToAlign!

This subpackage provides Path objects that serve as graphical timeline segments
with built-in coordinate conversion maps (C-maps) to (x, y) pixel coordinates.

Path objects can be appended to graphical timelines like regular segments,
enabling the construction of complex visual representations of time.

Classes:
    Path: Abstract base class for graphical timeline segments.
    LinearPath: Straight-line path between two points.
    PolylinePath: Path following multiple waypoints.

The Path API extends the existing TimeAxisPath system in graphical/paths.py
by adding timeline segment semantics (start_coord, end_coord) that enable
paths to be composed into contiguous graphical timelines.

Examples:
    >>> # Create a graphical timeline with two horizontal line segments
    >>> from timetoalign.loader.paths import LinearPath
    >>>
    >>> path1 = LinearPath(
    ...     start_coord=0.0, end_coord=60.0,
    ...     start_point=(50, 100), end_point=(750, 100)
    ... )
    >>> path2 = LinearPath(
    ...     start_coord=60.0, end_coord=120.0,
    ...     start_point=(50, 200), end_point=(750, 200)
    ... )
    >>>
    >>> # Paths can be used to build a graphical timeline
    >>> timeline.append(path1)
    >>> timeline.append(path2)
"""

from __future__ import annotations

from .base import Path
from .linear import LinearPath
from .polyline import PolylinePath
from .rect import RectPath

__all__ = [
    "Path",
    "LinearPath",
    "PolylinePath",
    "RectPath",
]
