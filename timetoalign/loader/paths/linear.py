"""LinearPath: Straight-line path between two points.

LinearPath is the most common path type, representing a straight line
through the image where timeline coordinates map linearly to positions
along the line.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from .base import Path

module_logger = logging.getLogger(__name__)


# region LinearPath


@dataclass
class LinearPath(Path):
    """Straight-line path with linear interpolation between endpoints.

    LinearPath is the standard path type for most graphical timelines:
    - Horizontal score lines (time flows left-to-right)
    - Spectrogram time axes
    - Piano roll timelines

    The mapping is linear: a coordinate that is t% of the way from
    start_coord to end_coord maps to a point t% of the way from
    start_point to end_point.

    Attributes:
        start_coord: Start coordinate on the timeline axis.
        end_coord: End coordinate on the timeline axis.
        start_point: (x, y) position at start_coord.
        end_point: (x, y) position at end_coord.
        tolerance: Distance tolerance for xy_to_coord (pixels).

    Examples:
        >>> # Horizontal line: time flows left to right
        >>> path = LinearPath(
        ...     start_coord=0.0, end_coord=60.0,
        ...     start_point=(50, 100), end_point=(750, 100)
        ... )
        >>> path.coord_to_xy(30.0)  # Midpoint
        (400.0, 100.0)

        >>> # Diagonal line
        >>> path = LinearPath(
        ...     start_coord=0.0, end_coord=10.0,
        ...     start_point=(0, 0), end_point=(300, 400)
        ... )
        >>> path.coord_to_xy(5.0)  # Midpoint
        (150.0, 200.0)
    """

    start_point: tuple[float, float]
    end_point: tuple[float, float]
    tolerance: float = 10.0

    def __post_init__(self) -> None:
        """Validate path parameters."""
        super().__post_init__()
        if self.start_point == self.end_point:
            raise ValueError("start_point and end_point must be different")

    @property
    def _dx(self) -> float:
        """X displacement from start to end."""
        return self.end_point[0] - self.start_point[0]

    @property
    def _dy(self) -> float:
        """Y displacement from start to end."""
        return self.end_point[1] - self.start_point[1]

    @property
    def pixel_length(self) -> float:
        """Euclidean length of the path in pixels."""
        return math.sqrt(self._dx**2 + self._dy**2)

    def coord_to_xy(self, coord: float) -> tuple[float, float]:
        """Map timeline coordinate to (x, y) pixel position.

        Uses linear interpolation between start_point and end_point.

        Args:
            coord: Timeline coordinate in [start_coord, end_coord].

        Returns:
            (x, y) tuple in image pixel coordinates.
        """
        if self.length == 0:
            return self.start_point

        # Normalized position [0, 1]
        t = (coord - self.start_coord) / self.length

        # Linear interpolation
        x = self.start_point[0] + t * self._dx
        y = self.start_point[1] + t * self._dy

        return (x, y)

    def xy_to_coord(self, x: float, y: float) -> float | None:
        """Map (x, y) pixel position to timeline coordinate.

        Projects the point onto the line and returns the corresponding
        timeline coordinate if the projection is within the path and
        the point is within tolerance of the line.

        Args:
            x: X coordinate in image pixels.
            y: Y coordinate in image pixels.

        Returns:
            Timeline coordinate, or None if point is not on the path.
        """
        # Vector from start to point
        px = x - self.start_point[0]
        py = y - self.start_point[1]

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
        proj_x = self.start_point[0] + t * self._dx
        proj_y = self.start_point[1] + t * self._dy
        dist = math.sqrt((x - proj_x) ** 2 + (y - proj_y) ** 2)

        if dist > self.tolerance:
            return None

        # Convert t [0,1] to timeline coordinate
        return self.start_coord + t * self.length

    def distance_to_path(self, x: float, y: float) -> float:
        """Compute perpendicular distance from point to path.

        Args:
            x: X coordinate in image.
            y: Y coordinate in image.

        Returns:
            Distance in pixels.
        """
        px = x - self.start_point[0]
        py = y - self.start_point[1]

        line_len_sq = self._dx**2 + self._dy**2
        if line_len_sq == 0:
            return math.sqrt(px**2 + py**2)

        # Clamp t to [0, 1] for distance to segment
        t = max(0, min(1, (px * self._dx + py * self._dy) / line_len_sq))

        proj_x = self.start_point[0] + t * self._dx
        proj_y = self.start_point[1] + t * self._dy

        return math.sqrt((x - proj_x) ** 2 + (y - proj_y) ** 2)

    def is_horizontal(self, angle_tolerance: float = 1.0) -> bool:
        """Check if the path is approximately horizontal.

        Args:
            angle_tolerance: Maximum angle from horizontal in degrees.

        Returns:
            True if path is within angle_tolerance of horizontal.
        """
        if self.pixel_length == 0:
            return True
        angle = math.degrees(math.atan2(abs(self._dy), abs(self._dx)))
        return angle <= angle_tolerance

    def is_vertical(self, angle_tolerance: float = 1.0) -> bool:
        """Check if the path is approximately vertical.

        Args:
            angle_tolerance: Maximum angle from vertical in degrees.

        Returns:
            True if path is within angle_tolerance of vertical.
        """
        if self.pixel_length == 0:
            return True
        angle = math.degrees(math.atan2(abs(self._dx), abs(self._dy)))
        return angle <= angle_tolerance

    def __repr__(self) -> str:
        return (
            f"LinearPath(coord=[{self.start_coord}, {self.end_coord}], "
            f"points={self.start_point} -> {self.end_point})"
        )


# endregion
