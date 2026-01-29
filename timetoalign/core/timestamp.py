"""Unified TimeStamp: Cross-section through timeline hierarchies.

This module provides TimeStamp and TimeIntervalStamp, the unified mechanism
for coordinate resolution across both Timeline (with children) and
TimelineGroup (with member timelines).

Design rationale (from unified_timestamp_architecture.md):
- TimeStamp is a lightweight view object that computes coordinates on access
- Uses InterpolationMaps for O(log n) coordinate conversion
- No table lookups - direct interpolation via precomputed maps
- Works identically for Timeline.get_timestamp() and TimelineGroup.get_timestamp()

Key insight: Every relationship (parent<->child, timeline<->group, forward<->inverse
C-Map) is stored as an InterpolationMap, enabling unified coordinate resolution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterator, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..core.enums import TimeUnit
    from ..maps.interpolation import InterpolationMap

module_logger = logging.getLogger(__name__)


# region TimeStampSource Protocol


@runtime_checkable
class TimeStampSource(Protocol):
    """Protocol for objects that can be TimeStamp sources.

    Both Timeline and TimelineGroup implement this protocol,
    allowing TimeStamp to work with either.
    """

    @property
    def id(self) -> str:
        """Unique identifier."""
        ...

    def _get_interpolation_map(
        self, target_id: str, source_id: str | None = None
    ) -> "InterpolationMap | None":
        """Get InterpolationMap for coordinate conversion to target.

        Args:
            target_id: Target timeline/entity ID.
            source_id: Source timeline ID (optional, for multi-source containers).

        Returns:
            InterpolationMap for conversion, or None if not available.
        """
        ...

    def _get_unit_map(self, unit: "TimeUnit") -> "InterpolationMap | None":
        """Get InterpolationMap for unit-based conversion."""
        ...

    def _get_related_timeline_ids(self) -> list[str]:
        """Get IDs of all related timelines (children/members)."""
        ...

    def _get_available_units(self) -> list["TimeUnit"]:
        """Get all units available via C-Maps."""
        ...


# endregion


# region TimeStamp


@dataclass(frozen=True, slots=True)
class TimeStamp:
    """A synchronized instant across a timeline hierarchy.

    Lightweight object that computes coordinates on access via InterpolationMaps.
    Works identically for Timeline (with children) and TimelineGroup (with members).

    The TimeStamp represents a cross-section through the timeline structure at
    a specific axis coordinate. All related timelines' coordinates can be
    retrieved via get() or subscript access.

    Attributes:
        axis: The root/reference coordinate value.
        source: The Timeline or TimelineGroup this timestamp belongs to.
        source_id: ID of the source (for serialization).
        row_index: If from a table row, the index. -1 if interpolated.

    Examples:
        >>> ts = timeline.get_timestamp(5.0)
        >>> ts.axis  # The root coordinate
        5.0
        >>> ts["child:1"]  # Get coordinate on child timeline
        2.5
        >>> ts.get("child:2", default=0.0)  # With default
        0.0

        >>> # Convert to different unit
        >>> ts.get_unit(TimeUnit.seconds)
        10.5
    """

    axis: float
    source: TimeStampSource
    source_id: str
    row_index: int = field(default=-1)

    def get(self, timeline_id: str, default: float | None = None) -> float | None:
        """Get coordinate on another timeline.

        Uses InterpolationMap for O(log n) lookup.

        Args:
            timeline_id: The timeline to get coordinate for.
            default: Value to return if timeline not reachable.

        Returns:
            Coordinate on the target timeline, or default if not reachable.
        """
        if timeline_id == self.source_id:
            return self.axis

        imap = self.source._get_interpolation_map(timeline_id, source_id=self.source_id)
        if imap is None:
            return default

        # Determine direction based on source/target IDs
        if imap.source_id == self.source_id:
            return float(imap.forward(self.axis))
        else:
            return float(imap.inverse(self.axis))

    def get_unit(self, unit: "TimeUnit") -> float | None:
        """Get coordinate converted to a specific unit.

        Uses C-Map's InterpolationMap if available.

        Args:
            unit: The target unit for conversion.

        Returns:
            Converted coordinate, or None if no C-Map available.
        """
        imap = self.source._get_unit_map(unit)
        if imap is None:
            return None
        return float(imap.forward(self.axis))

    def to_dict(
        self,
        include_children: bool = True,
        conversion_units: list["TimeUnit"] | Literal["all"] | None = None,
    ) -> dict[str, float | None]:
        """Materialize all coordinates as a dictionary.

        Args:
            include_children: Include child/member timeline coordinates.
            conversion_units: C-Map target units to include.
                - None: No C-Map conversions
                - "all": All available C-Maps
                - list: Specific units only

        Returns:
            Dict mapping timeline_id/unit_name to coordinate value.
        """
        result: dict[str, float | None] = {self.source_id: self.axis}

        # Add child/member coordinates
        if include_children:
            for tid in self.source._get_related_timeline_ids():
                result[tid] = self.get(tid)

        # Add C-Map conversions
        if conversion_units == "all":
            for unit in self.source._get_available_units():
                result[unit.name] = self.get_unit(unit)
        elif conversion_units:
            for unit in conversion_units:
                result[unit.name] = self.get_unit(unit)

        return result

    def __getitem__(self, key: str) -> float | None:
        """Subscript access: ts["child:1"] or ts["seconds"].

        First tries as timeline ID, then as unit name.

        Args:
            key: Timeline ID or unit name.

        Returns:
            Coordinate value, or None if not found.
        """
        # Try as timeline ID first
        result = self.get(key)
        if result is not None:
            return result

        # Try as unit name
        from ..core.enums import TimeUnit

        try:
            unit = TimeUnit(key)
            return self.get_unit(unit)
        except ValueError:
            return None

    @property
    def is_interpolated(self) -> bool:
        """True if this timestamp was computed via interpolation."""
        return self.row_index == -1

    @property
    def present_timelines(self) -> list[str]:
        """Timeline IDs that have coordinates at this instant."""
        result = [self.source_id]
        for tid in self.source._get_related_timeline_ids():
            if self.get(tid) is not None:
                result.append(tid)
        return result

    def __repr__(self) -> str:
        interp = " (interpolated)" if self.is_interpolated else ""
        return f"TimeStamp(axis={self.axis}, source={self.source_id!r}{interp})"

    def __str__(self) -> str:
        return f"TimeStamp({self.axis}@{self.source_id})"


# endregion


# region TimeIntervalStamp


@dataclass(frozen=True, slots=True)
class TimeIntervalStamp:
    """An interval defined by start and end TimeStamps.

    Provides facilities for zipping corresponding (start, end) pairs
    across all related timelines.

    Attributes:
        start: TimeStamp at interval start.
        end: TimeStamp at interval end.

    Examples:
        >>> interval = timeline.get_interval_stamp(0.0, 10.0)
        >>> interval.duration  # On axis timeline
        10.0
        >>> interval.get_interval("child:1")  # (start, end) tuple
        (0.0, 7.5)
        >>> interval.get_duration("child:1")
        7.5

        >>> # Get all intervals at once
        >>> interval.zip_intervals()
        {'tl:1': (0.0, 10.0), 'child:1': (0.0, 7.5)}
    """

    start: TimeStamp
    end: TimeStamp

    def __post_init__(self) -> None:
        """Validate that start and end are from the same source."""
        if self.start.source_id != self.end.source_id:
            raise ValueError(
                f"Start and end must be from the same source: "
                f"got {self.start.source_id!r} and {self.end.source_id!r}"
            )

    @property
    def duration(self) -> float:
        """Duration on the axis timeline."""
        return self.end.axis - self.start.axis

    @property
    def source(self) -> TimeStampSource:
        """The source Timeline/Group."""
        return self.start.source

    @property
    def source_id(self) -> str:
        """ID of the source."""
        return self.start.source_id

    def get_interval(self, timeline_id: str) -> tuple[float, float] | None:
        """Get (start, end) pair for a specific timeline.

        Args:
            timeline_id: The timeline to get interval for.

        Returns:
            Tuple of (start, end) coordinates, or None if timeline not reachable.
        """
        s = self.start.get(timeline_id)
        e = self.end.get(timeline_id)
        if s is not None and e is not None:
            return (s, e)
        return None

    def get_duration(self, timeline_id: str) -> float | None:
        """Get duration on a specific timeline.

        Args:
            timeline_id: The timeline to get duration for.

        Returns:
            Duration (end - start), or None if timeline not reachable.
        """
        interval = self.get_interval(timeline_id)
        if interval:
            return interval[1] - interval[0]
        return None

    def get_unit_interval(self, unit: "TimeUnit") -> tuple[float, float] | None:
        """Get (start, end) pair for a specific unit.

        Args:
            unit: The target unit.

        Returns:
            Tuple of (start, end) in the target unit, or None if no C-Map.
        """
        s = self.start.get_unit(unit)
        e = self.end.get_unit(unit)
        if s is not None and e is not None:
            return (s, e)
        return None

    def zip_intervals(
        self,
        timeline_ids: list[str] | None = None,
        include_units: list["TimeUnit"] | None = None,
    ) -> dict[str, tuple[float, float]]:
        """Get all (start, end) pairs across timelines.

        Args:
            timeline_ids: Specific timelines to include (None = all).
            include_units: C-Map units to include as well.

        Returns:
            Dict mapping timeline_id/unit to (start, end) tuple.
        """
        result: dict[str, tuple[float, float]] = {}

        # Add source timeline
        result[self.source_id] = (self.start.axis, self.end.axis)

        # Get timeline intervals
        ids = timeline_ids or self.source._get_related_timeline_ids()
        for tid in ids:
            interval = self.get_interval(tid)
            if interval:
                result[tid] = interval

        # Get unit intervals
        if include_units:
            for unit in include_units:
                interval = self.get_unit_interval(unit)
                if interval:
                    result[unit.name] = interval

        return result

    def __iter__(self) -> Iterator[TimeStamp]:
        """Iterate as (start, end) pair."""
        return iter((self.start, self.end))

    def __getitem__(self, key: str) -> tuple[float, float] | None:
        """Subscript access for intervals."""
        return self.get_interval(key)

    def __repr__(self) -> str:
        return (
            f"TimeIntervalStamp(start={self.start.axis}, end={self.end.axis}, "
            f"source={self.source_id!r})"
        )

    def __str__(self) -> str:
        return (
            f"TimeIntervalStamp([{self.start.axis}, {self.end.axis}]@{self.source_id})"
        )


# endregion
