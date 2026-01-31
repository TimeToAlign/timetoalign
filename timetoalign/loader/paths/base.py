"""Path: Abstract base class for graphical timeline segments.

A Path is a graphical timeline segment with a built-in C-map to (x, y)
coordinates. Paths are the fundamental building blocks for constructing
graphical timelines from visual representations like scores and spectrograms.

Unlike TimeAxisPath (which operates in "path-local" coordinates starting at 0),
Path operates in "timeline coordinates" with explicit start_coord and end_coord,
making it suitable for composing into contiguous timelines.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

module_logger = logging.getLogger(__name__)


# region Path ABC


@dataclass
class Path(ABC):
    """Abstract base class for graphical timeline segments with built-in C-map.

    A Path represents a portion of a graphical timeline and provides
    bidirectional coordinate conversion between timeline coordinates
    and (x, y) pixel positions.

    Path objects are designed to be appended to parent timelines like
    regular segments, enabling construction of complex visual timelines
    from multiple line segments, curves, or other geometric shapes.

    Key Concepts:
        - **Timeline Coordinates**: The 1D coordinate system of the parent
          timeline (e.g., seconds, beats). A Path covers [start_coord, end_coord].
        - **Image Coordinates**: The 2D (x, y) pixel space of the source image.
        - **C-map**: The conversion map built into the Path that transforms
          between these coordinate systems.

    Attributes:
        start_coord: Start coordinate on the timeline axis.
        end_coord: End coordinate on the timeline axis.

    Abstract Methods:
        coord_to_xy: Map timeline coordinate to (x, y) position.
        xy_to_coord: Map (x, y) position to timeline coordinate.

    Properties:
        length: Duration of this path in timeline units.

    Examples:
        >>> class MyPath(Path):
        ...     def coord_to_xy(self, coord):
        ...         # Linear interpolation
        ...         t = (coord - self.start_coord) / self.length
        ...         x = self.x0 + t * (self.x1 - self.x0)
        ...         y = self.y0 + t * (self.y1 - self.y0)
        ...         return (x, y)
        ...
        ...     def xy_to_coord(self, x, y):
        ...         # Inverse mapping
        ...         ...
    """

    start_coord: float
    end_coord: float

    def __post_init__(self) -> None:
        """Validate path coordinates."""
        if self.end_coord < self.start_coord:
            raise ValueError(
                f"end_coord ({self.end_coord}) must be >= start_coord ({self.start_coord})"
            )

    @property
    def length(self) -> float:
        """Length of this path in timeline units."""
        return self.end_coord - self.start_coord

    @abstractmethod
    def coord_to_xy(self, coord: float) -> tuple[float, float]:
        """Map timeline coordinate to (x, y) pixel position.

        This is the forward C-map from timeline space to image space.

        Args:
            coord: Timeline coordinate in [start_coord, end_coord].

        Returns:
            (x, y) tuple in image pixel coordinates.

        Raises:
            ValueError: If coord is outside the path's range.
        """
        ...

    @abstractmethod
    def xy_to_coord(self, x: float, y: float) -> float | None:
        """Map (x, y) pixel position to timeline coordinate.

        This is the inverse C-map from image space to timeline space.
        Returns None if the point is not on or near the path.

        Args:
            x: X coordinate in image pixels.
            y: Y coordinate in image pixels.

        Returns:
            Timeline coordinate, or None if point is not on the path.
        """
        ...

    def contains_coord(self, coord: float) -> bool:
        """Check if a timeline coordinate is within this path's range.

        Args:
            coord: Timeline coordinate to check.

        Returns:
            True if start_coord <= coord <= end_coord.
        """
        return self.start_coord <= coord <= self.end_coord

    def is_contiguous_with(self, other: "Path") -> bool:
        """Check if this path is contiguous with another path.

        Two paths are contiguous if one's end_coord equals the other's start_coord.

        Args:
            other: Another Path to check.

        Returns:
            True if the paths are contiguous.
        """
        return (
            self.end_coord == other.start_coord or other.end_coord == self.start_coord
        )


# endregion
