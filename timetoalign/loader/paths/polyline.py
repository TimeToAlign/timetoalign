"""PolylinePath: Path following multiple waypoints with linear interpolation.

PolylinePath represents a piecewise-linear path through multiple waypoints,
useful for representing paths that change direction (e.g., multi-line scores).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from .base import Path

module_logger = logging.getLogger(__name__)


# region PolylinePath


@dataclass
class PolylinePath(Path):
    """Path following multiple waypoints with linear interpolation.

    PolylinePath is used for paths that bend or change direction, such as:
    - Multi-line music scores (each system is a segment)
    - Paths that follow curves approximated by line segments
    - Complex graphical analyses with non-linear time layouts

    Each waypoint specifies a (coord, x, y) tuple mapping a timeline
    coordinate to an (x, y) position. Between waypoints, linear
    interpolation is used.

    Attributes:
        start_coord: Start coordinate on the timeline axis.
        end_coord: End coordinate on the timeline axis.
        waypoints: List of (coord, x, y) tuples defining the path.
        tolerance: Distance tolerance for xy_to_coord (pixels).

    Note:
        The first waypoint's coord should equal start_coord and the
        last waypoint's coord should equal end_coord. Waypoints must
        be sorted by coordinate.

    Examples:
        >>> # Two-line score: first line at y=100, second at y=200
        >>> path = PolylinePath(
        ...     start_coord=0.0, end_coord=120.0,
        ...     waypoints=[
        ...         (0.0, 50, 100),     # Start of line 1
        ...         (60.0, 750, 100),   # End of line 1
        ...         (60.0, 50, 200),    # Start of line 2 (jump in y)
        ...         (120.0, 750, 200),  # End of line 2
        ...     ]
        ... )
    """

    waypoints: list[tuple[float, float, float]] = field(default_factory=list)
    tolerance: float = 10.0

    def __post_init__(self) -> None:
        """Validate path parameters."""
        super().__post_init__()

        if len(self.waypoints) < 2:
            raise ValueError("PolylinePath requires at least 2 waypoints")

        # Sort waypoints by coordinate
        self.waypoints = sorted(self.waypoints, key=lambda w: w[0])

        # Validate coordinate range
        first_coord = self.waypoints[0][0]
        last_coord = self.waypoints[-1][0]

        if first_coord != self.start_coord:
            raise ValueError(
                f"First waypoint coord ({first_coord}) must equal start_coord ({self.start_coord})"
            )
        if last_coord != self.end_coord:
            raise ValueError(
                f"Last waypoint coord ({last_coord}) must equal end_coord ({self.end_coord})"
            )

    def _find_segment(self, coord: float) -> tuple[int, float]:
        """Find the segment containing a coordinate.

        Args:
            coord: Timeline coordinate.

        Returns:
            Tuple of (segment_index, local_t) where local_t is [0, 1]
            within the segment.
        """
        # Binary search for the segment
        for i in range(len(self.waypoints) - 1):
            c0 = self.waypoints[i][0]
            c1 = self.waypoints[i + 1][0]

            if c0 <= coord <= c1:
                if c1 == c0:
                    return i, 0.0
                t = (coord - c0) / (c1 - c0)
                return i, t

        # Clamp to last segment
        return len(self.waypoints) - 2, 1.0

    def coord_to_xy(self, coord: float) -> tuple[float, float]:
        """Map timeline coordinate to (x, y) pixel position.

        Uses linear interpolation between waypoints.

        Args:
            coord: Timeline coordinate in [start_coord, end_coord].

        Returns:
            (x, y) tuple in image pixel coordinates.
        """
        seg_idx, t = self._find_segment(coord)

        w0 = self.waypoints[seg_idx]
        w1 = self.waypoints[seg_idx + 1]

        # Linear interpolation
        x = w0[1] + t * (w1[1] - w0[1])
        y = w0[2] + t * (w1[2] - w0[2])

        return (x, y)

    def xy_to_coord(self, x: float, y: float) -> float | None:
        """Map (x, y) pixel position to timeline coordinate.

        Finds the closest point on any segment and returns the
        corresponding timeline coordinate if within tolerance.

        Args:
            x: X coordinate in image pixels.
            y: Y coordinate in image pixels.

        Returns:
            Timeline coordinate, or None if point is not on the path.
        """
        best_coord = None
        best_dist = float("inf")

        for i in range(len(self.waypoints) - 1):
            w0 = self.waypoints[i]
            w1 = self.waypoints[i + 1]

            # Segment endpoints
            x0, y0 = w0[1], w0[2]
            x1, y1 = w1[1], w1[2]
            c0, c1 = w0[0], w1[0]

            # Vector from start to point
            dx = x1 - x0
            dy = y1 - y0
            px = x - x0
            py = y - y0

            # Project onto segment
            seg_len_sq = dx * dx + dy * dy
            if seg_len_sq == 0:
                t = 0.0
            else:
                t = max(0, min(1, (px * dx + py * dy) / seg_len_sq))

            # Projected point
            proj_x = x0 + t * dx
            proj_y = y0 + t * dy

            # Distance to projected point
            dist = math.sqrt((x - proj_x) ** 2 + (y - proj_y) ** 2)

            if dist < best_dist:
                best_dist = dist
                # Convert t to timeline coordinate
                best_coord = c0 + t * (c1 - c0)

        if best_dist > self.tolerance:
            return None

        return best_coord

    def distance_to_path(self, x: float, y: float) -> float:
        """Compute minimum distance from point to path.

        Args:
            x: X coordinate in image.
            y: Y coordinate in image.

        Returns:
            Distance in pixels.
        """
        min_dist = float("inf")

        for i in range(len(self.waypoints) - 1):
            w0 = self.waypoints[i]
            w1 = self.waypoints[i + 1]

            # Segment endpoints
            x0, y0 = w0[1], w0[2]
            x1, y1 = w1[1], w1[2]

            # Vector from start to point
            dx = x1 - x0
            dy = y1 - y0
            px = x - x0
            py = y - y0

            # Project onto segment
            seg_len_sq = dx * dx + dy * dy
            if seg_len_sq == 0:
                t = 0.0
            else:
                t = max(0, min(1, (px * dx + py * dy) / seg_len_sq))

            # Projected point
            proj_x = x0 + t * dx
            proj_y = y0 + t * dy

            # Distance
            dist = math.sqrt((x - proj_x) ** 2 + (y - proj_y) ** 2)
            min_dist = min(min_dist, dist)

        return min_dist

    @property
    def pixel_length(self) -> float:
        """Total Euclidean length of the path in pixels."""
        total = 0.0
        for i in range(len(self.waypoints) - 1):
            w0 = self.waypoints[i]
            w1 = self.waypoints[i + 1]
            dx = w1[1] - w0[1]
            dy = w1[2] - w0[2]
            total += math.sqrt(dx * dx + dy * dy)
        return total

    @property
    def n_segments(self) -> int:
        """Number of line segments in the path."""
        return len(self.waypoints) - 1

    def __repr__(self) -> str:
        return (
            f"PolylinePath(coord=[{self.start_coord}, {self.end_coord}], "
            f"waypoints={len(self.waypoints)}, segments={self.n_segments})"
        )


# endregion
