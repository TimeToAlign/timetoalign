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
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Iterator,
    Literal,
    Protocol,
    runtime_checkable,
)

if TYPE_CHECKING:
    import pandas as pd
    import pyarrow as pa

    from ..core.enums import ColumnNaming, TimeUnit
    from ..core.types import Coordinate
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

    def _get_unit_map(self, unit: "TimeUnit") -> "Any":
        """Get a map for unit-based conversion (InterpolationMap or ConversionMap)."""
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

    def _contains_coordinate(self, timeline_id: str, axis: float) -> bool:
        """Check whether *axis* falls within the span of a related timeline.

        For a child embedded at *offset* with *length*, the span on the
        parent is ``[offset, offset + length)``.  Returns ``True`` for
        the source timeline itself and for any related timeline whose
        span includes *axis*.

        Args:
            timeline_id: The related timeline to check.
            axis: The coordinate on the source (parent) timeline.

        Returns:
            True if *axis* is inside the related timeline's span.
        """
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

        Returns ``default`` (None) when the queried coordinate falls
        outside the related timeline's span -- for instance, asking a
        child whose parent-side interval is ``[10, 30)`` for the
        coordinate at axis 5.

        Args:
            timeline_id: The timeline to get coordinate for.
            default: Value to return if timeline not reachable or out of span.

        Returns:
            Coordinate on the target timeline, or *default* if not
            reachable or the axis is outside the target's span.
        """
        if timeline_id == self.source_id:
            return self.axis

        # Bounds check: is axis inside the related timeline's span?
        if not self.source._contains_coordinate(timeline_id, self.axis):
            return default

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

        Works with any map registered by ``add_conversion_map``:
        ``InterpolationMap`` (for ``TableMap``), or analytical
        ``ConversionMap`` subclasses (``ScalarMap``, ``LinearMap``, ...).

        Args:
            unit: The target unit for conversion.

        Returns:
            Converted coordinate, or None if no C-Map available.
        """
        umap = self.source._get_unit_map(unit)
        if umap is None:
            return None
        # InterpolationMap exposes .forward(); ConversionMap exposes __call__
        if hasattr(umap, "forward"):
            return float(umap.forward(self.axis))
        return float(umap(self.axis))

    def get_coordinate(self, timeline_id: str) -> "Coordinate | None":
        """Get a proper Coordinate object for a timeline.

        Unlike get() which returns a float, this returns a Coordinate
        with the correct TimeUnit attached.

        Args:
            timeline_id: The timeline to get coordinate for.

        Returns:
            Coordinate with value and unit, or None if not reachable.

        Examples:
            >>> ts = timeline.get_timestamp(50.0)
            >>> coord = ts.get_coordinate("child:1")
            >>> coord.value
            25.0
            >>> coord.unit
            <TimeUnit.seconds: 'seconds'>
        """
        from ..core.types import Coordinate

        value = self.get(timeline_id)
        if value is None:
            return None

        unit = self.source._get_unit_for_timeline(timeline_id)
        if unit is None:
            return None

        return Coordinate(value, unit)

    @property
    def axis_coordinate(self) -> "Coordinate":
        """Get the axis value as a proper Coordinate object.

        This provides the axis coordinate with its correct TimeUnit,
        enabling proper coordinate arithmetic and serialization.

        Returns:
            Coordinate with the axis value and source unit.

        Examples:
            >>> ts = timeline.get_timestamp(50.0)
            >>> ts.axis_coordinate
            Coordinate(50.0, seconds)
        """
        from ..core.types import Coordinate

        unit = self.source._get_unit_for_timeline(self.source_id)
        # source_id should always be valid, so unit should never be None
        # but we fall back to a safe default just in case
        if unit is None:
            from ..core.enums import TimeUnit

            unit = TimeUnit.seconds  # Fallback
        return Coordinate(self.axis, unit)

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
        unit_str = f" {axis_unit.value}" if axis_unit else ""
        lines.append(f"TimeStamp @{self.axis:g}{unit_str}")

        def _fmt(v: float, u: str = "") -> str:
            """Format a coordinate value, using integer repr when exact."""
            suffix = f" {u}" if u else ""
            if v == int(v) and abs(v) < 1e15:
                return f"{int(v)}{suffix}"
            return f"{v:g}{suffix}"

        # Collect all entries: (label, value_str)
        entries: list[tuple[str, str]] = []

        # Source timeline
        entries.append((self.source_id, _fmt(self.axis, unit_str.strip())))

        # Children / related timelines
        for tid in self.source._get_related_timeline_ids():
            val = self.get(tid)
            if val is not None:
                t_unit = self.source._get_unit_for_timeline(tid)
                entries.append((tid, _fmt(val, t_unit.value if t_unit else "")))

        # C-Map conversions
        for unit in self.source._get_available_units():
            val = self.get_unit(unit)
            if val is not None:
                entries.append((unit.value, _fmt(val)))

        # Align columns
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

        rows = []

        # Add axis coordinate
        axis_unit = self.source._get_unit_for_timeline(self.source_id)
        axis_unit_str = f" ({axis_unit.value})" if axis_unit else ""
        rows.append(
            f"<tr><td><strong>{html.escape(self.source_id)}</strong></td>"
            f"<td style='text-align: right;'>{self.axis:.6g}{axis_unit_str}</td>"
            f"<td><em>axis</em></td></tr>"
        )

        # Add related timeline coordinates
        for tid in self.source._get_related_timeline_ids():
            val = self.get(tid)
            if val is not None:
                unit = self.source._get_unit_for_timeline(tid)
                unit_str = f" ({unit.value})" if unit else ""
                rows.append(
                    f"<tr><td>{html.escape(tid)}</td>"
                    f"<td style='text-align: right;'>{val:.6g}{unit_str}</td>"
                    f"<td></td></tr>"
                )

        # Add C-Map conversions
        for unit in self.source._get_available_units():
            val = self.get_unit(unit)
            if val is not None:
                rows.append(
                    f"<tr><td style='color: #666;'>{html.escape(unit.value)}</td>"
                    f"<td style='text-align: right;'>{val:.6g}</td>"
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
            f"</table></div>"
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
        return (
            f"TimeIntervalStamp([{self.start.axis}, {self.end.axis}]@{self.source_id})"
        )


# endregion


# region Timestamp Table Conversion Utilities


def timestamp_table_to_dataframe(
    table: "pa.Table",
    columns: "ColumnNaming | Callable[[str, dict], str] | list[str] | None" = None,
    units: bool = True,
    format: str = "pandas",
) -> "pd.DataFrame":
    """Convert a PyArrow timestamp table to a pandas DataFrame with proper formatting.

    This utility function processes timestamp tables (from Timeline.get_timestamp_table()
    or TimelineGroup.get_timestamp_table()) and applies column naming and type conversions.

    Args:
        table: PyArrow table with field-level metadata including 'unit' and
            'timeline_id' or 'cmap_id'.
        columns: How to name the columns. Options:
            - None or ColumnNaming.name (default): Use timeline/cmap name property,
              falling back to id if name is not available.
            - ColumnNaming.id: Use timeline/cmap id.
            - Callable[[str, dict], str]: Function taking (column_name, metadata_dict)
              and returning the new column name.
            - list[str]: Explicit list of column names (must match table length).
        units: If True (default), append units to column names like "name (unit)".
        format: Output format. Currently only "pandas" is supported.

    Returns:
        pandas DataFrame with:
        - Columns named according to the `columns` parameter
        - Units appended if `units=True`
        - Integer columns using pandas nullable Int64 dtype
        - Float columns as float64

    Examples:
        >>> table = timeline.get_timestamp_table()
        >>> df = timestamp_table_to_dataframe(table, units=True)
        >>> df.columns
        Index(['axis (pixels)', 'dgt1 (pixels)', 'pixels_to_inches (inches)'])

        >>> # Use IDs instead of names
        >>> from timetoalign import ColumnNaming
        >>> df = timestamp_table_to_dataframe(table, columns=ColumnNaming.id)

        >>> # Custom column naming
        >>> df = timestamp_table_to_dataframe(
        ...     table,
        ...     columns=lambda name, meta: meta.get('timeline_id', name)
        ... )
    """
    import pandas as pd
    import pyarrow as pa

    from .enums import ColumnNaming

    if format != "pandas":
        raise ValueError(f"Unsupported format: {format!r}. Only 'pandas' is supported.")

    if table.num_rows == 0:
        return pd.DataFrame()

    # Resolve columns parameter to ColumnNaming enum if needed
    # Use string lookup to avoid conflict with StrEnum's .name property
    # use_name_mode = columns is None or (
    #     isinstance(columns, ColumnNaming) and columns == ColumnNaming("name")
    # )

    # Build column name mapping
    new_column_names: list[str] = []

    for i, data_field in enumerate(table.schema):
        col_name = data_field.name
        metadata = data_field.metadata or {}

        # Decode metadata bytes to strings for easier access
        meta_dict = {
            k.decode("utf-8") if isinstance(k, bytes) else k: (
                v.decode("utf-8") if isinstance(v, bytes) else v
            )
            for k, v in metadata.items()
        }

        # Determine base name
        if isinstance(columns, list):
            if i < len(columns):
                base_name = columns[i]
            else:
                base_name = col_name
        elif callable(columns) and not isinstance(columns, ColumnNaming):
            base_name = columns(col_name, meta_dict)
        elif isinstance(columns, ColumnNaming) and str(columns) == "id":
            # Use timeline_id or cmap_id from metadata
            base_name = (
                meta_dict.get("timeline_id") or meta_dict.get("cmap_id") or col_name
            )
        else:  # ColumnNaming.name, None, or default
            # For now, use column name directly (names are already set by Timeline)
            # In future, could look up timeline.name property
            base_name = col_name

        # Append unit if requested
        if units:
            unit = meta_dict.get("unit")
            if unit:
                final_name = f"{base_name} ({unit})"
            else:
                final_name = base_name
        else:
            final_name = base_name

        new_column_names.append(str(final_name))

    # Convert to pandas with appropriate dtypes
    df = table.to_pandas()
    df.columns = new_column_names

    # Convert integer columns to nullable Int64
    for i, data_field in enumerate(table.schema):
        col_name = new_column_names[i]
        if pa.types.is_integer(data_field.type):
            # Convert to nullable integer
            df[col_name] = df[col_name].astype("Int64")
        elif pa.types.is_int64(data_field.type):
            df[col_name] = df[col_name].astype("Int64")

    return df


# endregion
