"""Unified TimeStamp: Cross-section through timeline hierarchies.

This module provides Stamp, TimeStamp, and TimeIntervalStamp, the unified mechanism
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
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Iterator,
    Literal,
    Protocol,
    runtime_checkable,
)

from ..maps.base import ConversionMap
from .enums import TimeUnit

if TYPE_CHECKING:
    import pandas as pd
    import pyarrow as pa

    from ..core.enums import ColumnNaming
    from ..core.time import Coordinate
    from ..maps.interpolation import InterpolationMap
else:
    from ..maps.interpolation import InterpolationMap

module_logger = logging.getLogger(__name__)


# Type alias for flexible conversion_maps parameters.
# Accepts: True (all), single cmap/str, or a list of cmaps/strs.
ConversionMapsSpec = (
    bool
    | str
    | TimeUnit
    | ConversionMap[Any]
    | list[ConversionMap[Any] | str | TimeUnit]
    | None
)


# region Coordinate Formatting

# Discrete units MUST be displayed as integers, never as floats or scientific notation.
DISCRETE_UNITS = frozenset(
    {"ticks", "pulses", "divs", "samples", "pixels", "px", "frames"}
)


def _format_coordinate_value(value: float, unit_str: str = "") -> str:
    """Format a coordinate value, avoiding scientific notation.

    Rules:
    - Discrete units (ticks, samples, pixels, frames): Always integer
    - Continuous units: Fixed-point notation, no scientific notation
    - Exact integers: Show as integer (no decimal point)

    Args:
        value: The numeric coordinate value.
        unit_str: The unit name (used to detect discrete vs continuous).

    Returns:
        Formatted string, never in scientific notation.
    """
    suffix = f" {unit_str}" if unit_str else ""
    unit_lower = unit_str.lower().strip()

    # For discrete units OR exact integers, format as plain integer
    if unit_lower in DISCRETE_UNITS or (value == int(value) and abs(value) < 1e15):
        return f"{int(value)}{suffix}"

    # For continuous units, use fixed-point notation (no scientific notation)
    if abs(value) >= 1e6:
        # Large values: show as integer
        return f"{int(round(value))}{suffix}"
    elif abs(value) >= 1:
        # Normal range: up to 6 decimal places, strip trailing zeros
        return f"{value:.6f}".rstrip("0").rstrip(".") + suffix
    elif value == 0:
        return f"0{suffix}"
    else:
        # Small values (< 1): up to 6 decimal places
        return f"{value:.6f}".rstrip("0").rstrip(".") + suffix


# endregion


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

    def _get_unit_map(self, unit: "TimeUnit") -> "Any":
        """Get a map for unit-based conversion (InterpolationMap or ConversionMap)."""
        ...

    def _get_unit_map_for_timeline(self, timeline_id: str, unit: "TimeUnit") -> "Any":
        """Get a unit map associated with a specific timeline."""
        ...

    def _get_related_timeline_ids(self) -> list[str]:
        """Get IDs of all related timelines (children/members)."""
        ...

    def _get_available_units(self) -> list["TimeUnit"]:
        """Get all units available via C-Maps."""
        ...

    def _get_unit_for_timeline(self, timeline_id: str) -> "TimeUnit | None":
        """Get the TimeUnit for a timeline in the hierarchy.

        Args:
            timeline_id: The timeline ID to look up.

        Returns:
            The TimeUnit for the timeline, or None if not found.
        """
        ...

    def _contains_coordinate(
        self, timeline_id: str, axis: float, source_id: str | None = None
    ) -> bool:
        """Check whether *axis* falls within the span of a related timeline.

        For a child embedded at *offset* with *length*, the span on the
        parent is ``[offset, offset + length)``.  Returns ``True`` for
        the source timeline itself and for any related timeline whose
        span includes *axis*.

        Args:
            timeline_id: The related timeline to check.
            axis: The coordinate on the source timeline.
            source_id: The source timeline ID (required for TimelineGroup,
                optional for Timeline where it defaults to the parent).

        Returns:
            True if *axis* is inside the related timeline's span.
        """
        ...


# endregion


# region Stamp


class Stamp(ABC):
    """Common contract for every synchronized stamp.

    Any stamp, from any source, has identical structure and behaviour: an axis
    coordinate, a source identity, timeline and unit accessors, coordinate
    materialization, and dictionary/subscript views.
    """

    @property
    @abstractmethod
    def axis(self) -> float:
        """Reference coordinate value."""
        ...

    @property
    @abstractmethod
    def source(self) -> object | None:
        """Object that provides the stamp's coordinate relationships."""
        ...

    @property
    @abstractmethod
    def source_id(self) -> str | None:
        """Identifier of the source timeline or group."""
        ...

    @property
    @abstractmethod
    def present_timelines(self) -> list[str]:
        """Timeline IDs that have coordinates at this instant."""
        ...

    @property
    @abstractmethod
    def is_interpolated(self) -> bool:
        """Whether this stamp was computed by interpolation."""
        ...

    @abstractmethod
    def get(self, timeline_id: str, default: float | None = None) -> float | None:
        """Get a coordinate on a related timeline."""
        ...

    @abstractmethod
    def get_unit(self, unit: TimeUnit) -> float | None:
        """Get a coordinate converted to a unit."""
        ...

    @abstractmethod
    def to_dict(
        self,
        include_children: bool = True,
        conversion_units: list[TimeUnit] | Literal["all"] | None = None,
    ) -> dict[str, float | None]:
        """Materialize the stamp as a coordinate dictionary."""
        ...

    @abstractmethod
    def _unit_for(self, timeline_id: str) -> TimeUnit | None:
        """Get the unit associated with a timeline ID."""
        ...

    def get_coordinate(self, timeline_id: str) -> "Coordinate | None":
        """Get a coordinate value with its timeline unit attached.

        Args:
            timeline_id: The timeline to get a coordinate for.

        Returns:
            A Coordinate object, or None when the timeline or unit is unavailable.
        """
        from ..core.time import Coordinate

        raw = self.get(timeline_id)
        unit = self._unit_for(timeline_id)
        if raw is None or unit is None:
            return None
        return Coordinate(raw, unit)

    @property
    def axis_coordinate(self) -> "Coordinate":
        """Get the axis value as a Coordinate with its source unit."""
        from ..core.time import Coordinate

        unit = self._unit_for(self.source_id or "")
        if unit is None:
            unit = TimeUnit.seconds
        return Coordinate(self.axis, unit)

    def __getitem__(self, key: str) -> float | None:
        """Get a timeline coordinate or a converted unit by name.

        Timeline IDs are tried first, followed by unit-name resolution.

        Args:
            key: Timeline ID or unit name.

        Returns:
            The resolved coordinate, or None for an existing unit with no map.

        Raises:
            KeyError: If key is neither a timeline ID nor a unit name, or if
                unit resolution is disabled for that unit.
        """
        result = self.get(key)
        if result is not None:
            return result
        if self._is_timeline_id(key):
            return result

        try:
            unit = TimeUnit(key)
        except ValueError:
            raise KeyError(key) from None

        if not self._unit_resolution_enabled(unit):
            raise KeyError(key)
        return self.get_unit(unit)

    def _unit_resolution_enabled(self, unit: TimeUnit) -> bool:
        """Return whether the stamp's conversion-map spec permits a unit."""
        return True

    def _is_timeline_id(self, key: str) -> bool:
        """Return whether key names the source or a related timeline."""
        if key == self.source_id or self.source is None:
            return key == self.source_id
        return key in self.source._get_related_timeline_ids()  # type: ignore[attr-defined]


# endregion


# region TimeStamp


@dataclass(frozen=True, slots=True)
class TimeStamp(Stamp):
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
    conversion_maps: ConversionMapsSpec = field(default=True)

    def get(self, timeline_id: str, default: float | None = None) -> float | None:
        """Get coordinate on another timeline.

        Returns ``default`` (None) when the queried coordinate falls
        outside the related timeline's span -- for instance, asking a
        child whose parent-side interval is ``[10, 30)`` for the
        coordinate at axis 5.

        For `Timeline` sources, child coordinates are resolved via exact
        offset arithmetic (no interpolation). For `TimelineGroup` sources,
        coordinates are resolved via `InterpolationMap`.

        Args:
            timeline_id: The timeline to get coordinate for.
            default: Value to return if timeline not reachable or out of span.

        Returns:
            Coordinate on the target timeline, or *default* if not
            reachable or the axis is outside the target's span.
        """
        if timeline_id == self.source_id:
            # Round for discrete timelines (TimelineGroup members)
            if self._number_type_for(timeline_id) == "int":
                return round(self.axis)
            return self.axis

        # Bounds check: is axis inside the related timeline's span?
        if not self.source._contains_coordinate(timeline_id, self.axis, self.source_id):
            return default

        # Strategy 1: exact offset arithmetic (Timeline with children)
        _get_child = getattr(self.source, "_get_child_coordinate", None)
        if _get_child is not None:
            result = _get_child(timeline_id, self.axis)
            if result is not None:
                return result
            # If child coordinate returned None but _contains_coordinate
            # said True, fall through to interpolation (should not happen
            # for Timeline, but is safe).

        # Strategy 2: InterpolationMap (TimelineGroup or fallback)
        imap = self.source._get_interpolation_map(timeline_id, source_id=self.source_id)
        if imap is None:
            return default

        # Determine direction based on source/target IDs
        if imap.source_id == self.source_id:
            result = float(imap.forward(self.axis))
        else:
            result = float(imap.inverse(self.axis))

        # Round for discrete timelines (TimelineGroup members)
        if self._number_type_for(timeline_id) == "int":
            result = round(result)

        return result

    def get_unit(self, unit: "TimeUnit") -> float | None:
        """Get coordinate converted to a specific unit.

        Works with any map registered by ``add_conversion_map``:
        ``InterpolationMap`` (for ``TableMap``), or analytical
        ``ConversionMap`` subclasses (``ScalarMap``, ``LinearMap``, ...).

        For TimelineGroup sources, searches ALL member timelines for the C-Map,
        first trying the source timeline, then others. This ensures that
        timestamps always show C-Map conversions regardless of which timeline
        is queried.

        Args:
            unit: The target unit for conversion.

        Returns:
            Converted coordinate, or None if no C-Map available.
        """
        if not self._unit_resolution_enabled(unit):
            return None

        for timeline_id in [self.source_id, *self.source._get_related_timeline_ids()]:
            umap = self.source._get_unit_map_for_timeline(timeline_id, unit)
            if umap is None:
                continue
            value = (
                self.axis if timeline_id == self.source_id else self.get(timeline_id)
            )
            if value is None:
                continue
            if isinstance(umap, InterpolationMap):
                return float(umap.forward(value))
            return float(umap(value))
        return None

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

    def _unit_for(self, timeline_id: str) -> "TimeUnit | None":
        """Get the unit associated with a timeline ID."""
        return self.source._get_unit_for_timeline(timeline_id)

    def _unit_resolution_enabled(self, unit: TimeUnit) -> bool:
        """Return whether conversion-map specification permits a unit."""
        spec = self.conversion_maps
        if spec is True:
            return True
        if spec is False or spec is None:
            return False

        requested = spec if isinstance(spec, list) else [spec]
        maps = [
            self.source._get_unit_map_for_timeline(timeline_id, unit)
            for timeline_id in [
                self.source_id,
                *self.source._get_related_timeline_ids(),
            ]
        ]
        maps = [cmap for cmap in maps if cmap is not None]

        for allowed in requested:
            if isinstance(allowed, TimeUnit) and allowed == unit:
                return True
            if isinstance(allowed, str):
                try:
                    if TimeUnit(allowed) == unit:
                        return True
                except ValueError:
                    pass
                for cmap in maps:
                    if isinstance(cmap, InterpolationMap):
                        if allowed == cmap.source_id:
                            return True
                    elif allowed in (cmap.id, cmap.name):
                        return True
            elif isinstance(allowed, ConversionMap):
                if allowed.target_unit == unit:
                    return True
                if any(
                    isinstance(cmap, InterpolationMap)
                    and cmap.source_id == allowed.id
                    or not isinstance(cmap, InterpolationMap)
                    and cmap.id == allowed.id
                    for cmap in maps
                ):
                    return True
        return False

    def _number_type_for(self, timeline_id: str) -> str | None:
        """Get the numeric type name, retaining group compatibility."""
        try:
            number_type = self.source._get_number_type_for_timeline(timeline_id)
        except AttributeError:
            try:
                timelines = self.source._timelines  # type: ignore[attr-defined]
            except AttributeError:
                return None
            timeline = timelines.get(timeline_id)
            number_type = timeline.number_type if timeline is not None else None
        return number_type.name if number_type is not None else None

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
        """Readable cross-section showing all reachable coordinates and units.

        Examples:
            >>> print(timeline.get_timestamp(25.0))
            TimeStamp @25 seconds
              audio      25 seconds
              intro      25 seconds
              verse      15 seconds
              chorus     -5 seconds
              milliseconds   25000
              samples  1200000
        """

        lines: list[str] = []

        # Header: axis value with unit
        axis_unit = self.source._get_unit_for_timeline(self.source_id)
        unit_str = axis_unit.value if axis_unit else ""
        lines.append(f"TimeStamp @{_format_coordinate_value(self.axis, unit_str)}")

        # Collect all entries: (label, value_str)
        entries: list[tuple[str, str]] = []

        # Source timeline
        entries.append((self.source_id, _format_coordinate_value(self.axis, unit_str)))

        # Children / related timelines (skip source_id to avoid duplicate)
        for tid in self.source._get_related_timeline_ids():
            if tid == self.source_id:
                continue  # Already added above
            val = self.get(tid)
            if val is not None:
                t_unit = self.source._get_unit_for_timeline(tid)
                entries.append(
                    (tid, _format_coordinate_value(val, t_unit.value if t_unit else ""))
                )

        # C-Map conversions
        for unit in self.source._get_available_units():
            val = self.get_unit(unit)
            if val is not None:
                entries.append((unit.value, _format_coordinate_value(val, unit.value)))

        # Align fields
        if entries:
            max_label = max(len(e[0]) for e in entries)
            for label, value_str in entries:
                lines.append(f"  {label:<{max_label}}  {value_str}")

        return "\n".join(lines)

    def _repr_html_(self) -> str:
        """Return HTML representation for Jupyter notebooks.

        Displays the timestamp as an HTML table showing all coordinates
        with their units, organized by timeline and C-Map.
        """
        import html

        from timetoalign.display.html import affordance_line

        def _fmt_html(value: float, unit_name: str = "") -> str:
            """Format for HTML display, keeping unit separate."""
            return _format_coordinate_value(value, unit_name)

        rows = []

        # Add axis coordinate
        axis_unit = self.source._get_unit_for_timeline(self.source_id)
        axis_unit_name = axis_unit.value if axis_unit else ""
        rows.append(
            f"<tr><td><strong>{html.escape(self.source_id)}</strong></td>"
            f"<td style='text-align: right;'>{_fmt_html(self.axis, axis_unit_name)}</td>"
            f"<td><em>axis</em></td></tr>"
        )

        # Add related timeline coordinates (children) - skip source_id to avoid duplicate
        for tid in self.source._get_related_timeline_ids():
            if tid == self.source_id:
                continue  # Already added above
            val = self.get(tid)
            if val is not None:
                unit = self.source._get_unit_for_timeline(tid)
                unit_name = unit.value if unit else ""
                rows.append(
                    f"<tr><td>{html.escape(tid)}</td>"
                    f"<td style='text-align: right;'>{_fmt_html(val, unit_name)}</td>"
                    f"<td><em>child</em></td></tr>"
                )

        # Add C-Map conversions
        for unit in self.source._get_available_units():
            val = self.get_unit(unit)
            if val is not None:
                rows.append(
                    f"<tr><td style='color: #666;'>{html.escape(unit.value)}</td>"
                    f"<td style='text-align: right;'>{_fmt_html(val, unit.value)}</td>"
                    f"<td style='color: #666;'><em>cmap</em></td></tr>"
                )

        interp_badge = (
            " <span style='background: #ffeb3b; padding: 0 4px; "
            "border-radius: 3px; font-size: 0.8em;'>interpolated</span>"
            if self.is_interpolated
            else ""
        )

        return (
            f"<div style='font-family: monospace;'>"
            f"<strong>TimeStamp</strong>{interp_badge}"
            f"<table style='border-collapse: collapse; margin-top: 4px;'>"
            f"<thead><tr style='border-bottom: 1px solid #ccc;'>"
            f"<th style='text-align: left; padding: 2px 8px;'>ID</th>"
            f"<th style='text-align: right; padding: 2px 8px;'>Coordinate</th>"
            f"<th style='text-align: left; padding: 2px 8px;'>Type</th>"
            f"</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            f"</table>"
            f"{affordance_line(['ts.get(<tl_id>)', 'ts.get_unit(<unit>)'])}"
            f"</div>"
        )


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

    def get_coordinate_interval(
        self, timeline_id: str
    ) -> "tuple[Coordinate, Coordinate] | None":
        """Get (start, end) as proper Coordinate objects.

        Unlike get_interval() which returns floats, this returns Coordinates
        with the correct TimeUnit attached.

        Args:
            timeline_id: The timeline to get interval for.

        Returns:
            Tuple of (start, end) Coordinates, or None if not reachable.

        Examples:
            >>> interval = timeline.get_interval_stamp(10.0, 50.0)
            >>> start, end = interval.get_coordinate_interval("child:1")
            >>> start.unit
            <TimeUnit.seconds: 'seconds'>
        """
        start_coord = self.start.get_coordinate(timeline_id)
        end_coord = self.end.get_coordinate(timeline_id)
        if start_coord is not None and end_coord is not None:
            return (start_coord, end_coord)
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
        """Readable cross-section showing start/end across all reachable timelines.

        Entries where only one endpoint is in range display ``-`` for the
        missing side, making it easy to see events that straddle children.

        Examples:
            >>> print(timeline.get_interval_stamp(8.0, 12.0))
            TimeIntervalStamp [8, 12) seconds
                          start    end
              audio           8     12 seconds
              intro           8      - seconds
              verse           -      2 seconds
              milliseconds 8000  12000
              samples    384000 576000
        """

        def _fmt(v: float | None, unit_name: str = "") -> str:
            """Format a coordinate value; ``None`` becomes ``-``."""
            if v is None:
                return "-"
            # Use the module-level formatter but strip unit suffix (we add it separately)
            formatted = _format_coordinate_value(v, unit_name)
            # Remove the unit suffix since we display it at the end of the row
            if unit_name and formatted.endswith(f" {unit_name}"):
                formatted = formatted[: -(len(unit_name) + 1)]
            return formatted

        axis_unit = self.source._get_unit_for_timeline(self.source_id)
        unit_str = f" {axis_unit.value}" if axis_unit else ""
        unit_name = axis_unit.value if axis_unit else ""

        # Header - format axis values properly
        start_fmt = _format_coordinate_value(self.start.axis, unit_name)
        end_fmt = _format_coordinate_value(self.end.axis, unit_name)
        # Strip unit from these since we show it at end
        if unit_name:
            if start_fmt.endswith(f" {unit_name}"):
                start_fmt = start_fmt[: -(len(unit_name) + 1)]
            if end_fmt.endswith(f" {unit_name}"):
                end_fmt = end_fmt[: -(len(unit_name) + 1)]

        # Header
        lines: list[str] = [f"TimeIntervalStamp [{start_fmt}, {end_fmt}){unit_str}"]

        # Collect rows: (label, start_str, end_str, suffix)
        rows: list[tuple[str, str, str, str]] = []

        # Axis / source timeline
        rows.append(
            (
                self.source_id,
                _fmt(self.start.axis, unit_name),
                _fmt(self.end.axis, unit_name),
                unit_str.strip(),
            )
        )

        # Children / related timelines
        for tid in self.source._get_related_timeline_ids():
            s = self.start.get(tid)
            e = self.end.get(tid)
            if s is None and e is None:
                continue
            t_unit = self.source._get_unit_for_timeline(tid)
            suffix = t_unit.value if t_unit else ""
            rows.append((tid, _fmt(s, suffix), _fmt(e, suffix), suffix))

        # C-Map units
        for cmap_unit in self.source._get_available_units():
            s = self.start.get_unit(cmap_unit)
            e = self.end.get_unit(cmap_unit)
            if s is None and e is None:
                continue
            rows.append(
                (
                    cmap_unit.value,
                    _fmt(s, cmap_unit.value),
                    _fmt(e, cmap_unit.value),
                    "",
                )
            )

        # Align fields
        if rows:
            max_label = max(len(r[0]) for r in rows)
            max_start = max(len(r[1]) for r in rows)
            max_end = max(len(r[2]) for r in rows)

            # Column headers
            lines.append(
                f"  {'':>{max_label}}  {'start':>{max_start}}  {'end':>{max_end}}"
            )

            for label, s_str, e_str, suffix in rows:
                suffix_part = f" {suffix}" if suffix else ""
                lines.append(
                    f"  {label:<{max_label}}  {s_str:>{max_start}}  "
                    f"{e_str:>{max_end}}{suffix_part}"
                )

        return "\n".join(lines)


# endregion


# region Timestamp Table Conversion Utilities


def timestamp_table_to_dataframe(
    table: "pa.Table",
    fields: "ColumnNaming | Callable[[str, dict], str] | list[str] | None" = None,
    units: bool = True,
    format: str = "pandas",
) -> "pd.DataFrame":
    """Convert a PyArrow timestamp table to a pandas DataFrame with proper formatting.

    This utility function processes timestamp tables (from Timeline.get_timestamp_table()
    or TimelineGroup.get_timestamp_table()) and applies field naming and type conversions.

    Args:
        table: PyArrow table with field-level metadata including 'unit' and
            'timeline_id' or 'cmap_id'.
        fields: How to name the DataFrame fields. Options:
            - None or ColumnNaming.name (default): Use timeline/cmap name property,
              falling back to id if name is not available.
            - ColumnNaming.id: Use timeline/cmap id.
            - Callable[[str, dict], str]: Function taking (field_name, metadata_dict)
              and returning the new field name.
            - list[str]: Explicit list of field names (must match table length).
        units: If True (default), append units to field names like "name (unit)".
        format: Output format. Currently only "pandas" is supported.

    Returns:
        pandas DataFrame with:
        - Fields named according to the ``fields`` parameter
        - Units appended if ``units=True``
        - Integer fields using pandas nullable Int64 dtype
        - Float fields as float64

    Examples:
        >>> table = timeline.get_timestamp_table()
        >>> df = timestamp_table_to_dataframe(table, units=True)
        >>> df.columns
        Index(['axis (pixels)', 'dgt1 (pixels)', 'pixels_to_inches (inches)'])

        >>> # Use IDs instead of names
        >>> from timetoalign import ColumnNaming
        >>> df = timestamp_table_to_dataframe(table, fields=ColumnNaming.id)

        >>> # Custom field naming
        >>> df = timestamp_table_to_dataframe(
        ...     table,
        ...     fields=lambda name, meta: meta.get('timeline_id', name)
        ... )
    """
    import pandas as pd
    import pyarrow as pa

    from .enums import ColumnNaming

    if format != "pandas":
        raise ValueError(f"Unsupported format: {format!r}. Only 'pandas' is supported.")

    if table.num_rows == 0:
        return pd.DataFrame()

    # Build field name mapping
    new_field_names: list[str] = []

    for i, data_field in enumerate(table.schema):
        field_name = data_field.name
        metadata = data_field.metadata or {}

        # Decode metadata bytes to strings for easier access
        meta_dict = {
            k.decode("utf-8") if isinstance(k, bytes) else k: (
                v.decode("utf-8") if isinstance(v, bytes) else v
            )
            for k, v in metadata.items()
        }

        # Determine base name
        if isinstance(fields, list):
            if i < len(fields):
                base_name = fields[i]
            else:
                base_name = field_name
        elif callable(fields) and not isinstance(fields, ColumnNaming):
            base_name = fields(field_name, meta_dict)
        elif isinstance(fields, ColumnNaming) and str(fields) == "id":
            # Use timeline_id or cmap_id from metadata
            base_name = (
                meta_dict.get("timeline_id") or meta_dict.get("cmap_id") or field_name
            )
        else:  # ColumnNaming.name, None, or default
            # For now, use field name directly (names are already set by Timeline)
            # In future, could look up timeline.name property
            base_name = field_name

        # Append unit if requested
        if units:
            unit = meta_dict.get("unit")
            if unit:
                final_name = f"{base_name} ({unit})"
            else:
                final_name = base_name
        else:
            final_name = base_name

        new_field_names.append(str(final_name))

    # Convert to pandas with appropriate dtypes
    df = table.to_pandas()
    df.columns = new_field_names

    # Convert integer fields to nullable Int64
    for i, data_field in enumerate(table.schema):
        field_name = new_field_names[i]
        if pa.types.is_integer(data_field.type):
            # Convert to nullable integer
            df[field_name] = df[field_name].astype("Int64")
        elif pa.types.is_int64(data_field.type):
            df[field_name] = df[field_name].astype("Int64")

    return df


# endregion
