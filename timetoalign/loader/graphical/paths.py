"""TimeAxisPath definitions for graphical timelines.

This module provides the abstraction for mapping 1D timeline coordinates
to 2D image coordinates (and vice versa).

A TimeAxisPath represents the geometric trajectory that the time axis
follows through an image. Implementations range from simple (horizontal
lines) to complex (parametric curves, spirals).

The design is forward-compatible with video (3D paths through frame-time
and 2D pixel space).

Note:
    For timeline segment-oriented path API with explicit start/end coordinates,
    see the `timetoalign.loader.paths` module which provides `Path`, `LinearPath`,
    and `PolylinePath` classes designed for composing into graphical timelines.

    The TimeAxisPath classes in this module operate in "path-local" coordinates
    (starting at 0), while the Path classes in loader.paths operate in
    "timeline coordinates" with explicit start_coord/end_coord.
"""

from __future__ import annotations

import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

module_logger = logging.getLogger(__name__)


# region TimeAxisPath ABC


class TimeAxisPath(ABC):
    """Abstract definition of a time axis path through 2D space.

    A TimeAxisPath maps 1D timeline coordinates to 2D image coordinates.
    The path has a defined length (in timeline units, typically pixels)
    and provides bidirectional coordinate conversion.

    Subclasses implement specific geometric shapes:
    - HorizontalLinePath: x = time, y = constant
    - DiagonalLinePath: arbitrary straight line
    - ParametricPath: x(t), y(t) functions for curves/spirals
    """

    @property
    @abstractmethod
    def length(self) -> float:
        """Total length of this path in timeline units."""
        ...

    @abstractmethod
    def to_2d(self, coord: float) -> tuple[float, float]:
        """Map timeline coordinate to image (x, y).

        Args:
            coord: Timeline coordinate in [0, length].

        Returns:
            (x, y) tuple in image pixel coordinates.
        """
        ...

    @abstractmethod
    def from_2d(self, x: float, y: float) -> float | None:
        """Map image (x, y) to timeline coordinate.

        Args:
            x: X coordinate in image.
            y: Y coordinate in image.

        Returns:
            Timeline coordinate, or None if point is not on the path.
        """
        ...

    def distance_to_path(self, x: float, y: float) -> float:
        """Compute perpendicular distance from point to path.

        Default implementation samples the path and finds minimum distance.
        Subclasses may override with analytical solutions.

        Args:
            x: X coordinate in image.
            y: Y coordinate in image.

        Returns:
            Distance in pixels.
        """
        # Sample path and find closest point
        min_dist = float("inf")
        samples = max(100, int(self.length))
        for i in range(samples + 1):
            t = (i / samples) * self.length
            px, py = self.to_2d(t)
            dist = math.sqrt((x - px) ** 2 + (y - py) ** 2)
            min_dist = min(min_dist, dist)
        return min_dist

    def is_point_on_path(self, x: float, y: float, tolerance: float = 5.0) -> bool:
        """Check if a point is close enough to the path.

        Args:
            x: X coordinate in image.
            y: Y coordinate in image.
            tolerance: Maximum distance in pixels.

        Returns:
            True if point is within tolerance of the path.
        """
        return self.distance_to_path(x, y) <= tolerance


# endregion


# region HorizontalLinePath


@dataclass(frozen=True)
class HorizontalLinePath(TimeAxisPath):
    """Time axis as a horizontal line at fixed y.

    The simplest case: x directly maps to time coordinate.
    This is the typical case for musical scores, spectrograms,
    and most graphical analyses.

    Attributes:
        x0: Starting x coordinate (left edge).
        x1: Ending x coordinate (right edge).
        y: Fixed y coordinate (vertical position of the line).
        tolerance: Distance tolerance for from_2d conversion.

    Examples:
        >>> path = HorizontalLinePath(x0=10, x1=500, y=100)
        >>> path.length
        490.0
        >>> path.to_2d(0)
        (10.0, 100.0)
        >>> path.to_2d(245)
        (255.0, 100.0)
        >>> path.from_2d(255, 100)
        245.0
    """

    x0: float
    x1: float
    y: float
    tolerance: float = 10.0

    def __post_init__(self) -> None:
        """Validate path parameters."""
        if self.x1 <= self.x0:
            raise ValueError(f"x1 ({self.x1}) must be greater than x0 ({self.x0})")

    @property
    def length(self) -> float:
        """Length is simply x1 - x0."""
        return self.x1 - self.x0

    def to_2d(self, coord: float) -> tuple[float, float]:
        """Map timeline coordinate to (x, y)."""
        return (self.x0 + coord, self.y)

    def from_2d(self, x: float, y: float) -> float | None:
        """Map (x, y) to timeline coordinate.

        Returns None if:
        - y is not within tolerance of the line's y
        - x is outside the [x0, x1] range
        """
        if abs(y - self.y) > self.tolerance:
            return None
        if not (self.x0 <= x <= self.x1):
            return None
        return x - self.x0

    def distance_to_path(self, x: float, y: float) -> float:
        """Distance is simply |y - self.y| if x is in range."""
        if x < self.x0:
            # Distance to left endpoint
            return math.sqrt((x - self.x0) ** 2 + (y - self.y) ** 2)
        if x > self.x1:
            # Distance to right endpoint
            return math.sqrt((x - self.x1) ** 2 + (y - self.y) ** 2)
        # x is in range, distance is vertical only
        return abs(y - self.y)


# endregion


# region VerticalLinePath


@dataclass(frozen=True)
class VerticalLinePath(TimeAxisPath):
    """Time axis as a vertical line at fixed x.

    Useful for vertical timelines where y maps to time.

    Attributes:
        x: Fixed x coordinate.
        y0: Starting y coordinate (top).
        y1: Ending y coordinate (bottom).
        tolerance: Distance tolerance for from_2d conversion.
    """

    x: float
    y0: float
    y1: float
    tolerance: float = 10.0

    def __post_init__(self) -> None:
        """Validate path parameters."""
        if self.y1 <= self.y0:
            raise ValueError(f"y1 ({self.y1}) must be greater than y0 ({self.y0})")

    @property
    def length(self) -> float:
        """Length is y1 - y0."""
        return self.y1 - self.y0

    def to_2d(self, coord: float) -> tuple[float, float]:
        """Map timeline coordinate to (x, y)."""
        return (self.x, self.y0 + coord)

    def from_2d(self, x: float, y: float) -> float | None:
        """Map (x, y) to timeline coordinate."""
        if abs(x - self.x) > self.tolerance:
            return None
        if not (self.y0 <= y <= self.y1):
            return None
        return y - self.y0

    def distance_to_path(self, x: float, y: float) -> float:
        """Distance calculation for vertical line."""
        if y < self.y0:
            return math.sqrt((x - self.x) ** 2 + (y - self.y0) ** 2)
        if y > self.y1:
            return math.sqrt((x - self.x) ** 2 + (y - self.y1) ** 2)
        return abs(x - self.x)


# endregion


# region DiagonalLinePath


@dataclass(frozen=True)
class DiagonalLinePath(TimeAxisPath):
    """Time axis as a diagonal (arbitrary straight) line.

    Useful for rotated segments, skewed timelines, or any straight
    line that isn't perfectly horizontal or vertical.

    The timeline coordinate maps to arc length along the line,
    so length equals the Euclidean distance between endpoints.

    Attributes:
        start: (x, y) starting point.
        end: (x, y) ending point.
        tolerance: Distance tolerance for from_2d conversion.

    Examples:
        >>> path = DiagonalLinePath(start=(0, 0), end=(300, 400))
        >>> path.length  # sqrt(300^2 + 400^2) = 500
        500.0
        >>> path.to_2d(250)  # Halfway point
        (150.0, 200.0)
    """

    start: tuple[float, float]
    end: tuple[float, float]
    tolerance: float = 10.0

    def __post_init__(self) -> None:
        """Validate and compute derived values."""
        if self.start == self.end:
            raise ValueError("Start and end points must be different")

    @property
    def _dx(self) -> float:
        return self.end[0] - self.start[0]

    @property
    def _dy(self) -> float:
        return self.end[1] - self.start[1]

    @property
    def length(self) -> float:
        """Euclidean length of the line."""
        return math.sqrt(self._dx**2 + self._dy**2)

    def to_2d(self, coord: float) -> tuple[float, float]:
        """Map timeline coordinate (arc length) to (x, y)."""
        if self.length == 0:
            return self.start
        ratio = coord / self.length
        return (
            self.start[0] + ratio * self._dx,
            self.start[1] + ratio * self._dy,
        )

    def from_2d(self, x: float, y: float) -> float | None:
        """Map (x, y) to timeline coordinate.

        Projects the point onto the line and returns the arc length
        if the projection falls within the segment.
        """
        # Vector from start to point
        px = x - self.start[0]
        py = y - self.start[1]

        # Project onto line direction
        line_len_sq = self._dx**2 + self._dy**2
        if line_len_sq == 0:
            return None

        # Projection parameter t (0 = start, 1 = end)
        t = (px * self._dx + py * self._dy) / line_len_sq

        # Check if projection is within segment
        if not (0 <= t <= 1):
            return None

        # Check distance from line
        proj_x = self.start[0] + t * self._dx
        proj_y = self.start[1] + t * self._dy
        dist = math.sqrt((x - proj_x) ** 2 + (y - proj_y) ** 2)

        if dist > self.tolerance:
            return None

        # Return arc length
        return t * self.length

    def distance_to_path(self, x: float, y: float) -> float:
        """Perpendicular distance to line segment."""
        px = x - self.start[0]
        py = y - self.start[1]

        line_len_sq = self._dx**2 + self._dy**2
        if line_len_sq == 0:
            return math.sqrt(px**2 + py**2)

        t = max(0, min(1, (px * self._dx + py * self._dy) / line_len_sq))

        proj_x = self.start[0] + t * self._dx
        proj_y = self.start[1] + t * self._dy

        return math.sqrt((x - proj_x) ** 2 + (y - proj_y) ** 2)


# endregion


# region ParametricPath


class ParametricPath(TimeAxisPath):
    """Time axis defined by parametric functions x(t), y(t).

    For complex paths like spirals, curves, Bezier paths, etc.
    The parameter t is NOT directly the timeline coordinate - it's
    mapped via arc length parameterization.

    This class pre-computes an arc length table for efficient
    coordinate conversion.

    Attributes:
        x_func: Function t -> x coordinate.
        y_func: Function t -> y coordinate.
        t_start: Starting parameter value.
        t_end: Ending parameter value.
        tolerance: Distance tolerance for from_2d conversion.

    Examples:
        >>> # Archimedean spiral: r = a + b*t
        >>> import math
        >>> a, b = 50, 10
        >>> x_func = lambda t: (a + b*t) * math.cos(t)
        >>> y_func = lambda t: (a + b*t) * math.sin(t)
        >>> path = ParametricPath(x_func, y_func, t_start=0, t_end=4*math.pi)
    """

    def __init__(
        self,
        x_func: Callable[[float], float],
        y_func: Callable[[float], float],
        t_start: float = 0.0,
        t_end: float = 1.0,
        samples: int = 1000,
        tolerance: float = 10.0,
    ):
        """Initialize parametric path.

        Args:
            x_func: Function mapping parameter t to x coordinate.
            y_func: Function mapping parameter t to y coordinate.
            t_start: Starting parameter value.
            t_end: Ending parameter value.
            samples: Number of samples for arc length computation.
            tolerance: Distance tolerance for from_2d.
        """
        self.x_func = x_func
        self.y_func = y_func
        self.t_start = t_start
        self.t_end = t_end
        self.tolerance = tolerance
        self._samples = samples

        # Pre-compute arc length table
        self._arc_lengths: list[float] = []
        self._t_values: list[float] = []
        self._build_arc_length_table()

    def _build_arc_length_table(self) -> None:
        """Build lookup table for arc length parameterization."""
        self._t_values = []
        self._arc_lengths = []

        total_length = 0.0
        prev_x = self.x_func(self.t_start)
        prev_y = self.y_func(self.t_start)

        self._t_values.append(self.t_start)
        self._arc_lengths.append(0.0)

        for i in range(1, self._samples + 1):
            t = self.t_start + (i / self._samples) * (self.t_end - self.t_start)
            x = self.x_func(t)
            y = self.y_func(t)

            segment_length = math.sqrt((x - prev_x) ** 2 + (y - prev_y) ** 2)
            total_length += segment_length

            self._t_values.append(t)
            self._arc_lengths.append(total_length)

            prev_x, prev_y = x, y

        self._total_length = total_length

    @property
    def length(self) -> float:
        """Total arc length of the path."""
        return self._total_length

    def _arc_to_t(self, arc: float) -> float:
        """Convert arc length to parameter t using binary search."""
        if arc <= 0:
            return self.t_start
        if arc >= self._total_length:
            return self.t_end

        # Binary search in arc_lengths
        lo, hi = 0, len(self._arc_lengths) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if self._arc_lengths[mid] < arc:
                lo = mid + 1
            else:
                hi = mid

        # Linear interpolation between samples
        if lo == 0:
            return self._t_values[0]

        arc_lo = self._arc_lengths[lo - 1]
        arc_hi = self._arc_lengths[lo]
        t_lo = self._t_values[lo - 1]
        t_hi = self._t_values[lo]

        if arc_hi == arc_lo:
            return t_lo

        ratio = (arc - arc_lo) / (arc_hi - arc_lo)
        return t_lo + ratio * (t_hi - t_lo)

    def to_2d(self, coord: float) -> tuple[float, float]:
        """Map timeline coordinate (arc length) to (x, y)."""
        t = self._arc_to_t(coord)
        return (self.x_func(t), self.y_func(t))

    def from_2d(self, x: float, y: float) -> float | None:
        """Map (x, y) to timeline coordinate.

        Finds the closest point on the path and returns its arc length.
        """
        min_dist = float("inf")
        best_arc = None

        for i, t in enumerate(self._t_values):
            px = self.x_func(t)
            py = self.y_func(t)
            dist = math.sqrt((x - px) ** 2 + (y - py) ** 2)

            if dist < min_dist:
                min_dist = dist
                best_arc = self._arc_lengths[i]

        if min_dist > self.tolerance:
            return None

        return best_arc


# endregion
