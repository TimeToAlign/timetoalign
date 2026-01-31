"""RectPath: Rectangular path for bounded regions on images.

RectPath represents a rectangular region where the x-axis corresponds to
time progression and the y-axis defines the vertical extent. This is ideal
for annotations on spectrograms, score images, or any visual timeline where
events occupy rectangular bounds.

The key insight: a rectangle has TWO coordinate systems:
1. **Graphical (pixels)**: x, y, width, height on the image
2. **Physical (time)**: start_time, end_time in seconds

RectPath provides:
- Timeline coordinates in pixels (x to x+width)
- A built-in C-map from pixel-x to physical time (seconds)
- Y-range metadata for the vertical extent
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .base import Path

if TYPE_CHECKING:
    pass

module_logger = logging.getLogger(__name__)


# region RectPath


@dataclass
class RectPath(Path):
    """Rectangular path with x-axis as time and y-axis as vertical extent.

    RectPath is designed for rectangular annotations on images where:
    - The x-axis (left-to-right) represents time progression
    - The y-axis (top-to-bottom) represents vertical extent (not time)

    The rectangle's x-coordinate becomes the start_coord in pixels,
    and x+width becomes the end_coord. The physical time range (in seconds)
    is stored separately and used to build a C-map from pixels to time.

    Attributes:
        start_coord: X-coordinate of left edge (pixels) = start of timeline.
        end_coord: X-coordinate of right edge (pixels) = end of timeline.
        y_min: Y-coordinate of top edge (pixels).
        y_max: Y-coordinate of bottom edge (pixels).
        time_start: Physical start time (seconds).
        time_end: Physical end time (seconds).

    The C-map relationship:
        pixel_x -> time_seconds via linear interpolation:
        time = time_start + (pixel_x - start_coord) / width * (time_end - time_start)

    Examples:
        >>> # Rectangle from JSON: {"x": 10, "y": 90, "width": 148, "height": 55}
        >>> # Physical time: 0.0 to 5.0 seconds
        >>> path = RectPath.from_rect(
        ...     x=10, y=90, width=148, height=55,
        ...     time_start=0.0, time_end=5.0
        ... )
        >>> path.start_coord  # Left edge in pixels
        10.0
        >>> path.end_coord  # Right edge in pixels
        158.0
        >>> path.coord_to_time(84.0)  # Center pixel -> center time
        2.5
        >>> path.coord_to_xy(84.0)  # Center pixel -> (x, y_center)
        (84.0, 117.5)
    """

    y_min: float
    y_max: float
    time_start: float
    time_end: float

    @classmethod
    def from_rect(
        cls,
        x: float,
        y: float,
        width: float,
        height: float,
        time_start: float,
        time_end: float,
    ) -> "RectPath":
        """Create RectPath from rectangle coordinates and time range.

        Args:
            x: Left edge x-coordinate (pixels).
            y: Top edge y-coordinate (pixels).
            width: Rectangle width (pixels).
            height: Rectangle height (pixels).
            time_start: Physical start time (seconds).
            time_end: Physical end time (seconds).

        Returns:
            A RectPath with pixel coordinates and time mapping.

        Examples:
            >>> path = RectPath.from_rect(
            ...     x=10, y=90, width=148, height=55,
            ...     time_start=0.0, time_end=5.0
            ... )
        """
        return cls(
            start_coord=float(x),
            end_coord=float(x + width),
            y_min=float(y),
            y_max=float(y + height),
            time_start=float(time_start),
            time_end=float(time_end),
        )

    @classmethod
    def from_json(
        cls,
        rect_json: dict,
        time_start: float,
        time_end: float,
    ) -> "RectPath":
        """Create RectPath from a JSON rect dict.

        Args:
            rect_json: Dict with keys "x", "y", "width", "height".
            time_start: Physical start time (seconds).
            time_end: Physical end time (seconds).

        Returns:
            A RectPath with pixel coordinates and time mapping.

        Examples:
            >>> rect = {"x": 10, "y": 90, "width": 148, "height": 55}
            >>> path = RectPath.from_json(rect, time_start=0.0, time_end=5.0)
        """
        return cls.from_rect(
            x=rect_json["x"],
            y=rect_json["y"],
            width=rect_json["width"],
            height=rect_json["height"],
            time_start=time_start,
            time_end=time_end,
        )

    @property
    def width(self) -> float:
        """Rectangle width in pixels."""
        return self.end_coord - self.start_coord

    @property
    def height(self) -> float:
        """Rectangle height in pixels."""
        return self.y_max - self.y_min

    @property
    def y_center(self) -> float:
        """Y-coordinate of rectangle center."""
        return (self.y_min + self.y_max) / 2

    @property
    def time_duration(self) -> float:
        """Duration in physical time (seconds)."""
        return self.time_end - self.time_start

    def coord_to_xy(self, coord: float) -> tuple[float, float]:
        """Map pixel x-coordinate to (x, y_center) position.

        For a RectPath, the x-coordinate passes through unchanged,
        and y is the center of the rectangle's vertical extent.

        Args:
            coord: Pixel x-coordinate in [start_coord, end_coord].

        Returns:
            (x, y_center) tuple - x unchanged, y at rectangle center.
        """
        return (coord, self.y_center)

    def xy_to_coord(self, x: float, y: float) -> float | None:
        """Map (x, y) pixel position to pixel x-coordinate.

        Returns the x-coordinate if the point is within the rectangle's
        bounds, None otherwise.

        Args:
            x: X coordinate in image pixels.
            y: Y coordinate in image pixels.

        Returns:
            The x-coordinate (unchanged) if within bounds, else None.
        """
        if not (self.start_coord <= x <= self.end_coord):
            return None
        if not (self.y_min <= y <= self.y_max):
            return None
        return x

    def coord_to_time(self, coord: float) -> float:
        """Map pixel x-coordinate to physical time (seconds).

        This is the C-map from graphical to physical domain.
        Uses linear interpolation between pixel range and time range.

        Args:
            coord: Pixel x-coordinate in [start_coord, end_coord].

        Returns:
            Physical time in seconds.

        Examples:
            >>> path = RectPath.from_rect(10, 90, 148, 55, 0.0, 5.0)
            >>> path.coord_to_time(10)  # Left edge
            0.0
            >>> path.coord_to_time(158)  # Right edge
            5.0
            >>> path.coord_to_time(84)  # Center
            2.5
        """
        if self.width == 0:
            return self.time_start

        # Linear interpolation: pixel -> time
        t = (coord - self.start_coord) / self.width
        return self.time_start + t * self.time_duration

    def time_to_coord(self, time: float) -> float:
        """Map physical time (seconds) to pixel x-coordinate.

        This is the inverse C-map from physical to graphical domain.

        Args:
            time: Physical time in seconds.

        Returns:
            Pixel x-coordinate.

        Examples:
            >>> path = RectPath.from_rect(10, 90, 148, 55, 0.0, 5.0)
            >>> path.time_to_coord(0.0)  # Start time
            10.0
            >>> path.time_to_coord(5.0)  # End time
            158.0
            >>> path.time_to_coord(2.5)  # Center time
            84.0
        """
        if self.time_duration == 0:
            return self.start_coord

        # Linear interpolation: time -> pixel
        t = (time - self.time_start) / self.time_duration
        return self.start_coord + t * self.width

    def contains_point(self, x: float, y: float) -> bool:
        """Check if (x, y) point is inside the rectangle.

        Args:
            x: X coordinate in pixels.
            y: Y coordinate in pixels.

        Returns:
            True if point is inside rectangle bounds.
        """
        return self.start_coord <= x <= self.end_coord and self.y_min <= y <= self.y_max

    def __repr__(self) -> str:
        return (
            f"RectPath(px=[{self.start_coord:.0f}, {self.end_coord:.0f}], "
            f"y=[{self.y_min:.0f}, {self.y_max:.0f}], "
            f"time=[{self.time_start:.2f}s, {self.time_end:.2f}s])"
        )


# endregion
