"""Region: Named TimeInterval for timeline partitioning.

This module provides the Region class, which represents a named part of a
timeline defined by a TimeInterval. Regions are NOT timelines themselves -
they cannot hold events or C-maps.

From TTA manuscript (Section 3.5):
"A Region is a named part of a timeline that is defined by a TimeInterval.
Regions are useful for referring to parts of a timeline by name."

Use Region.to_child() or Timeline.partition() to create a Child timeline
from a Region.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from timetoalign.core import Coordinate, TimeUnit

# region Region


@dataclass(frozen=True)
class Region:
    """A named part of a timeline defined by a TimeInterval.

    From TTA manuscript (Section 3.5):
    "A Region is a named part of a timeline that is defined by a
    TimeInterval. Regions are useful for referring to parts of a
    timeline by name."

    IMPORTANT: Regions are NOT timelines. They cannot hold events or C-maps.
    Use Timeline.partition(region) to create a Child timeline from a Region.

    Attributes:
        name: The region's name (e.g., "Chorus", "Verse").
        start: Start coordinate of the region.
        end: End coordinate of the region.
        meta: Additional metadata (e.g., traversal order labels).

    Examples:
        >>> from timetoalign import Coordinate, TimeUnit
        >>> start = Coordinate(16.0, TimeUnit.quarters)
        >>> end = Coordinate(32.0, TimeUnit.quarters)
        >>> region = Region("Chorus", start=start, end=end)
        >>> region.duration
        16.0

        >>> # Create a Child from the region via timeline
        >>> tl.add_region("Chorus", start=16, end=32)
        >>> chorus_child = tl.partition("Chorus")
    """

    name: str
    start: Coordinate
    end: Coordinate
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate region bounds and units."""
        if self.end.value < self.start.value:
            raise ValueError(
                f"Region end ({self.end.value}) cannot be before "
                f"start ({self.start.value})"
            )
        if self.start.unit != self.end.unit:
            raise ValueError(
                f"Region start unit ({self.start.unit}) must match "
                f"end unit ({self.end.unit})"
            )

    @property
    def unit(self) -> TimeUnit:
        """The coordinate unit of this region."""
        return self.start.unit

    @property
    def duration(self) -> float:
        """Duration of the region (end - start)."""
        return float(self.end.value - self.start.value)

    @property
    def as_interval(self) -> tuple[float, float]:
        """The region as a (start, end) tuple."""
        return (float(self.start.value), float(self.end.value))

    def contains(self, coord: float) -> bool:
        """Check if a coordinate is within this region (left-inclusive).

        Following TTA convention, intervals are [start, end) - left-inclusive,
        right-exclusive.

        Args:
            coord: The coordinate value to check.

        Returns:
            True if start <= coord < end.
        """
        return self.start.value <= coord < self.end.value

    def overlaps(self, other: Region) -> bool:
        """Check if this region overlaps with another.

        Args:
            other: Another Region to check against.

        Returns:
            True if the regions overlap (share any coordinates).
        """
        return self.start.value < other.end.value and other.start.value < self.end.value

    def __repr__(self) -> str:
        return f"Region({self.name!r}, {self.start.value}-{self.end.value} {self.unit})"

    def __str__(self) -> str:
        return f"{self.name}: [{self.start.value}, {self.end.value}) {self.unit}"


# endregion
