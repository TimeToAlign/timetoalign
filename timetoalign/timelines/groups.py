"""TimelineGroup: Container for commensurable timelines.

This module implements the timestamp-based group architecture:
- Groups store timestamps in a PyArrow table (one row per boundary, one field per timeline)
- GroupTimestamp is a lightweight view object, created on retrieval
- Unified add_timeline() logic whether group is empty or has timelines
- Coordinate conversion via linear interpolation between timestamps
- Locking semantics like Timeline (is_locked, allow_extension)

IMPORTANT CONCEPTUAL DISTINCTION:
- Perfect Alignment: Bijective coordinate mapping (linear interpolation).
  Does NOT imply the alignment is musically/temporally correct.
- Correct Alignment: A special case where mapping corresponds to reality.

UNIFIED TIMESTAMP ARCHITECTURE:
TimelineGroup implements the TimeStampSource protocol and uses the same
TimeStamp/TimeIntervalStamp classes as Timeline. This enables:
- Consistent API across Timeline and TimelineGroup
- O(log n) coordinate conversion via InterpolationMaps
- Unified traversal of hierarchies spanning both
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from fractions import Fraction
from typing import TYPE_CHECKING, Any, Iterator, Literal, Sequence

import numpy as np
import pandas as pd
import pyarrow as pa

from timetoalign.core import (
    Coordinate,
    CoordinateSpec,
    CoordinateValue,
    IdCoordinate,
    IdGenerator,
    resolve_coordinate_spec,
    resolve_id,
)
from timetoalign.core.enums import NumberType, TimeUnit
from timetoalign.core.fields import blob_metadata, field_metadata
from timetoalign.core.timestamp import (
    ConversionMapsSpec,
    Stamp,
    TimeStamp,
    _format_coordinate_value,
)
from timetoalign.maps.base import ConversionMap
from timetoalign.maps.interpolation import InterpolationMap
from timetoalign.storage import EventData

if TYPE_CHECKING:
    from collections.abc import Callable

    from timetoalign.core.enums import ColumnNaming
    from timetoalign.display.ascii import Diagram
    from timetoalign.timelines import Timeline
    from timetoalign.timelines.flow import Flow, FlowControllerBase

module_logger = logging.getLogger(__name__)

# Module-level ID generator for groups
_group_id_generator = IdGenerator(scope="group")


def _reset_group_ids() -> None:
    """Reset the module-level ID generator. For testing only."""
    global _group_id_generator
    _group_id_generator = IdGenerator(scope="group")


# region GroupTimestamp


@dataclass(frozen=True)
class GroupTimestamp(Stamp):
    """A synchronized instant across all timelines in a group.

    This is a view object created from a row in the group's timestamp table.
    Not stored directly - the table is the source of truth.

    Attributes:
        coordinates: Dictionary mapping timeline/cmap IDs to coordinates.
            None values indicate the timeline is not present at this instant.
        units: Dictionary mapping timeline/cmap IDs to their unit strings.
            Used for display purposes.
        row_index: Index of this timestamp in the source table.
            -1 indicates an interpolated timestamp (not from a table row).

    Examples:
        >>> ts = group.get_timestamp_at_index(0)
        >>> ts["dgt1:1"]  # Get coordinate for dgt1
        0.0
        >>> ts.present_timelines  # Which timelines have values here
        ['dgt1:1', 'audio:1']

    See Also:
        TimeStamp: The unified timestamp class from ``timetoalign.core``.
    """

    coordinates: dict[str, float | None]
    units: dict[str, str] = field(default_factory=dict)
    row_index: int = -1
    source: TimelineGroup | None = None
    source_id: str | None = None
    axis: float | None = None
    conversion_maps: ConversionMapsSpec = True

    def get(self, timeline_id: str, default: float | None = None) -> float | None:
        """Get coordinate for a timeline.

        Args:
            timeline_id: The timeline to look up.
            default: Value to return if timeline not in coordinates.

        Returns:
            The coordinate value, or default if not found.
        """
        return self.coordinates.get(timeline_id, default)

    def get_unit(self, unit: TimeUnit) -> float | None:
        """Get the row coordinate converted to a specific unit.

        Args:
            unit: The target unit for conversion.

        Returns:
            Converted coordinate, or None if no permitted C-Map is available.
        """
        if self.source is None or not self._unit_resolution_enabled(unit):
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
            return float(umap(value))
        return None

    def to_dict(
        self,
        include_children: bool = True,
        conversion_units: list[TimeUnit] | Literal["all"] | None = None,
    ) -> dict[str, float | None]:
        """Materialize the stored row coordinates as a dictionary.

        Args:
            include_children: Retained for the shared Stamp interface.
            conversion_units: Retained for the shared Stamp interface.

        Returns:
            Dictionary mapping timeline IDs to stored coordinate values.
        """
        return dict(self.coordinates)

    def _unit_for(self, timeline_id: str) -> TimeUnit | None:
        """Get the unit associated with a timeline ID in this row."""
        unit = self.units.get(timeline_id)
        if unit is None:
            return None
        try:
            return TimeUnit(unit)
        except ValueError:
            return None

    def _unit_resolution_enabled(self, unit: TimeUnit) -> bool:
        """Return whether the conversion-map specification permits a unit."""
        if self.source is None:
            return False

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
                    if cmap.matches_selector(allowed):
                        return True
            elif isinstance(allowed, ConversionMap):
                if allowed.target_unit == unit:
                    return True
                if any(cmap.matches_selector(allowed.id) for cmap in maps):
                    return True
        return False

    @property
    def present_timelines(self) -> list[str]:
        """Timeline IDs that have coordinates at this instant."""
        return [k for k, v in self.coordinates.items() if v is not None]

    @property
    def is_interpolated(self) -> bool:
        """True if this timestamp was interpolated (not from a table row)."""
        return self.row_index == -1

    def __repr__(self) -> str:
        present = self.present_timelines
        interp = " (interpolated)" if self.is_interpolated else ""
        return f"GroupTimestamp({len(present)} timelines{interp})"

    def _repr_html_(self) -> str:
        """Return HTML representation for Jupyter notebooks.

        Displays the timestamp as an HTML table showing all coordinates with units.
        """
        import html

        from timetoalign.display.html import affordance_line

        rows = []
        for tid, val in self.coordinates.items():
            unit = self.units.get(tid, "")
            if val is not None:
                # Use proper formatting that avoids scientific notation
                formatted = _format_coordinate_value(val, unit)
                rows.append(
                    f"<tr><td>{html.escape(tid)}</td>"
                    f"<td style='text-align: right;'>{formatted}</td></tr>"
                )
            else:
                unit_display = f" ({unit})" if unit else ""
                rows.append(
                    f"<tr><td style='color: #999;'>{html.escape(tid)}{unit_display}</td>"
                    f"<td style='text-align: right; color: #999;'>-</td></tr>"
                )

        interp_badge = (
            " <span style='background: #ffeb3b; padding: 0 4px; "
            "border-radius: 3px; font-size: 0.8em;'>interpolated</span>"
            if self.is_interpolated
            else ""
        )

        return (
            f"<div style='font-family: monospace;'>"
            f"<strong>GroupTimestamp</strong> ({len(self.present_timelines)} timelines)"
            f"{interp_badge}"
            f"<table style='border-collapse: collapse; margin-top: 4px;'>"
            f"<thead><tr style='border-bottom: 1px solid #ccc;'>"
            f"<th style='text-align: left; padding: 2px 8px;'>ID (unit)</th>"
            f"<th style='text-align: right; padding: 2px 8px;'>Coordinate</th>"
            f"</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            f"</table>"
            f"{affordance_line(['ts[<tl_id>]', 'ts.get(<tl_id>)'])}"
            f"</div>"
        )


# endregion


# region TimelineGroup


@dataclass
class TimelineGroup:
    """Container for commensurable timelines.

    A TimelineGroup holds timelines (or sections thereof) that are
    commensurable - i.e., bijectively mapped to each other via linear
    interpolation. The group is defined by a timestamp table where each
    row is a boundary instant.

    Between any two adjacent timestamps, all present timelines have
    coordinates that can be converted via linear interpolation.

    Like Timeline, a Group can be locked to prevent extension.

    Attributes:
        id: Unique identifier for this group.
        name: Optional human-readable name.
        is_locked: Whether the group can be extended.
        meta: Additional metadata dictionary.

    Examples:
        >>> # Create empty group
        >>> group = TimelineGroup(id="my_group")

        >>> # Or create with initial timelines
        >>> group = TimelineGroup(id="my_group", timelines=[dgt1, audio])

        >>> # Add a timeline
        >>> group.add_timeline(dgt1)

        >>> # Add with explicit boundaries
        >>> from timetoalign import IdCoordinate, TimeUnit
        >>> group.add_timeline(
        ...     score_section,
        ...     start=IdCoordinate(45.0, TimeUnit.seconds, "audio:1"),
        ...     end=IdCoordinate(135.0, TimeUnit.seconds, "audio:1"),
        ... )

        >>> # Convert coordinates via timestamp lookup
        >>> ts = group.get_timestamp_at(75.0, "audio:1")
        >>> ts["dgt1:1"]  # -> 2437.5
    """

    id: str = field(default="")
    name: str | None = field(default=None)
    meta: dict[str, Any] = field(default_factory=dict)

    # Internal state (not part of dataclass signature)
    _timelines: dict[str, "Timeline"] = field(
        default_factory=dict, init=False, repr=False
    )
    _timestamp_table: pa.Table | None = field(default=None, init=False, repr=False)
    _interpolation_maps: dict[str, InterpolationMap] = field(
        default_factory=dict, init=False, repr=False
    )
    _is_locked: bool = field(default=False, init=False, repr=False)
    _logger: logging.Logger = field(
        default_factory=lambda: module_logger, init=False, repr=False
    )

    def __init__(
        self,
        id: str | None = None,
        name: str | None = None,
        timelines: list["Timeline"] | None = None,
        is_locked: bool = False,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Create a TimelineGroup.

        Args:
            id: Unique identifier. If None, auto-generated.
            name: Optional human-readable name.
            timelines: Initial timelines to add (optional).
            is_locked: Whether to lock the group after creation.
            meta: Additional metadata dictionary.
        """
        if id is None:
            self.id = _group_id_generator.create(type_hint="TimelineGroup")
        else:
            self.id = id

        self.name = name
        self.meta = dict(meta) if meta else {}
        self._timelines = {}
        self._timestamp_table = None
        self._interpolation_maps = {}
        self._is_locked = False  # Temporarily unlocked during init
        self._logger = module_logger.getChild(self.id)

        # Add initial timelines
        if timelines:
            for tl in timelines:
                self.add_timeline(tl)

        # Apply lock setting after adding timelines
        self._is_locked = is_locked

    # region Timeline Management

    def add_timeline(
        self,
        timeline: "Timeline",
        *,
        start: CoordinateSpec | GroupTimestamp | None = None,
        end: CoordinateSpec | GroupTimestamp | None = None,
        allow_extension: bool = False,
    ) -> None:
        """Add a timeline (or Child) to the group.

        The timeline's full extent (0 to length) becomes commensurable with
        the group between the specified start and end boundaries.

        This method works the same whether the group is empty or already
        has timelines. For an empty group, start/end default to the
        timeline's own boundaries (0 and length).

        Args:
            timeline: The timeline or Child to add. If a Child, its 0-origin
                extent is used. If a Timeline, its full extent (0 to length).
            start: Where this timeline's section STARTS in the group.
                - CoordinateSpec: Coordinate in the alignment-reference timeline
                - IdCoordinate: Coordinate with explicit timeline_id
                - GroupTimestamp: Use this existing timestamp
                - float: Coordinate (only if single timeline in group)
                - None: Use group's current start, or 0 if empty
            end: Where this timeline's section ENDS in the group.
                - Same options as start
                - None: Use group's current end, or timeline.length if empty
            allow_extension: If True and end extends beyond current group end,
                add a new end timestamp. If False (default) and group is locked,
                raise an error.

        Raises:
            ValueError: If timeline ID already exists in group.
            ValueError: If start/end specification is ambiguous.
            RuntimeError: If group is locked and extension would be required.

        Examples:
            >>> # Add to empty group - defines initial extent
            >>> group.add_timeline(dgt1)

            >>> # Add to existing group - maps to existing extent
            >>> group.add_timeline(audio)

            >>> # Add partial section with explicit boundaries (using IdCoordinate)
            >>> from timetoalign import IdCoordinate, TimeUnit
            >>> group.add_timeline(
            ...     score_section,
            ...     start=IdCoordinate(45.0, TimeUnit.seconds, "audio:1"),
            ...     end=IdCoordinate(135.0, TimeUnit.seconds, "audio:1"),
            ... )

            >>> # Extend group with new timeline
            >>> group.add_timeline(
            ...     extended_audio,
            ...     end=IdCoordinate(200.0, TimeUnit.seconds, "extended_audio:1"),
            ...     allow_extension=True,
            ... )
        """
        if timeline.id in self._timelines:
            raise ValueError(f"Timeline '{timeline.id}' already in group '{self.id}'")

        # Resolve start and end to timestamp specifications
        start_spec = self._resolve_boundary(start, is_start=True, new_timeline=timeline)
        end_spec = self._resolve_boundary(end, is_start=False, new_timeline=timeline)

        # Check extension
        if (
            self._requires_extension(end_spec)
            and self._is_locked
            and not allow_extension
        ):
            raise RuntimeError(
                f"Group '{self.id}' is locked. Use allow_extension=True to extend."
            )

        # Update timestamp table
        self._insert_timeline(timeline, start_spec, end_spec)
        self._timelines[timeline.id] = timeline

        # Rebuild interpolation maps for O(log n) coordinate conversion
        self._build_interpolation_maps()

        self._logger.debug(
            f"Added timeline '{timeline.id}' with {self.n_timestamps} timestamps"
        )

    def remove_timeline(self, timeline_id: str) -> "Timeline":
        """Remove a timeline from the group.

        Updates timestamp table to remove the timeline's field.
        Rows where all remaining timelines have null are removed.

        Args:
            timeline_id: ID of the timeline to remove.

        Returns:
            The removed timeline.

        Raises:
            KeyError: If timeline_id is not in the group.
        """
        if timeline_id not in self._timelines:
            raise KeyError(
                f"Timeline '{timeline_id}' not in group '{self.id}'. "
                f"Available timelines: {self.timeline_ids}"
            )

        timeline = self._timelines.pop(timeline_id)
        self._remove_timeline_field(timeline_id)

        # Rebuild interpolation maps
        self._build_interpolation_maps()

        self._logger.debug(f"Removed timeline '{timeline_id}'")
        return timeline

    def get_timeline(self, timeline_id: str) -> "Timeline":
        """Get a timeline by ID.

        Supports partial string and regex matching:
        1. Exact match: If ``timeline_id`` matches an ID exactly, returns it.
        2. Substring match: If ``timeline_id`` is a substring of exactly one ID,
           returns that timeline. If multiple match, returns the first and warns.
        3. Regex match: If ``timeline_id`` is a valid regex, matches via
           ``re.search()``. Same first-match logic with warning.

        Args:
            timeline_id: The timeline's unique identifier, or a partial/regex pattern.

        Returns:
            The Timeline object.

        Raises:
            KeyError: If no timeline matches the pattern.

        Examples:
            >>> group.get_timeline("clt1")           # Exact match
            >>> group.get_timeline("notes")          # Substring match
            >>> group.get_timeline(r"^score:")       # Regex match
        """
        resolved_id = resolve_id(timeline_id, list(self._timelines.keys()))
        return self._timelines[resolved_id]

    @property
    def n_timelines(self) -> int:
        """Number of timelines in the group."""
        return len(self._timelines)

    @property
    def timeline_ids(self) -> list[str]:
        """IDs of all member timelines."""
        return list(self._timelines.keys())

    def __contains__(self, timeline_id: str) -> bool:
        """Check if a timeline is in the group."""
        return timeline_id in self._timelines

    def __getitem__(self, timeline_id: str) -> "Timeline":
        """Get a timeline by ID.

        Shorthand for ``get_timeline(timeline_id)``. Supports partial
        string and regex matching.

        Args:
            timeline_id: The timeline's unique identifier, or a partial/regex pattern.

        Returns:
            The Timeline object.

        Raises:
            KeyError: If no timeline matches the pattern.

        Examples:
            >>> tl = group["clt1"]           # Exact match
            >>> tl = group["score"]          # Substring match
        """
        return self.get_timeline(timeline_id)

    def get_events(
        self,
        *,
        timeline_id: str | None = None,
        **kwargs: Any,
    ) -> EventData:
        """Get events from all timelines in the group, concatenated.

        Collects events from all member timelines (or a specific one) and
        concatenates their Arrow tables into a single EventData. Each row includes a
        ``timeline_id`` field identifying the source timeline. A member-provided
        ``timeline_id`` column is discarded because group membership is authoritative.

        Args:
            timeline_id: If provided, only return events from this timeline.
                Supports partial string and regex matching.
            **kwargs: Passed through to each timeline's ``get_events()`` method
                (e.g., ``min_coord``, ``max_coord``, ``event_type``).

        Returns:
            EventData with events from all (or specified) timelines. Includes
            a ``timeline_id`` field and standard event fields (``start``,
            ``end``, ``event_type``, etc.).

        Examples:
            >>> # Get all events from all timelines
            >>> df = group.get_events().to_dataframe()

            >>> # Get events from a specific timeline
            >>> df = group.get_events(timeline_id="clt1").to_dataframe()

            >>> # Get events with filters
            >>> df = group.get_events(
            ...     event_type="Note", min_coord=0.0, max_coord=100.0
            ... ).to_dataframe()
        """
        if timeline_id is not None:
            timeline = self.get_timeline(timeline_id)
            timelines = [(timeline.id, timeline)]
        else:
            timelines = list(self._timelines.items())

        tables: list[pa.Table] = []
        result_unit = TimeUnit.seconds
        result_number_type = NumberType.float
        for tl_id, timeline in timelines:
            events = timeline.get_events(**kwargs)
            result_unit = events.unit
            result_number_type = events.number_type
            if len(events) == 0:
                continue
            source_ids = pa.array([tl_id] * len(events), type=pa.string())
            member_table = events.table
            if "timeline_id" in member_table.column_names:
                member_table = member_table.drop_columns(["timeline_id"])
            tables.append(member_table.append_column("timeline_id", source_ids))

        if tables:
            column_types: dict[str, pa.DataType] = {}
            for table in tables:
                for schema_field in table.schema:
                    previous = column_types.get(schema_field.name)
                    if previous is None or pa.types.is_null(previous):
                        column_types[schema_field.name] = schema_field.type
                        continue
                    if pa.types.is_null(schema_field.type):
                        continue
                    if previous != schema_field.type:
                        raise ValueError(
                            f"Conflicting Arrow types for column {schema_field.name!r}: "
                            f"{previous} and {schema_field.type}."
                        )
            table = pa.concat_tables(tables, promote_options="permissive")
            return EventData(table, result_unit, result_number_type)

        empty = EventData.empty(result_unit, result_number_type)
        return EventData(
            empty.table.append_column("timeline_id", pa.array([], type=pa.string())),
            result_unit,
            result_number_type,
        )

    # endregion

    # region Locking

    @property
    def is_locked(self) -> bool:
        """Whether the group is locked."""
        return self._is_locked

    def lock(self) -> None:
        """Lock the group to prevent extension."""
        self._is_locked = True

    def unlock(self) -> None:
        """Unlock the group to allow extension."""
        self._is_locked = False

    # endregion

    # region Timestamps

    @property
    def n_timestamps(self) -> int:
        """Number of boundary timestamps."""
        if self._timestamp_table is None:
            return 0
        return self._timestamp_table.num_rows

    @property
    def timestamps(self) -> list[GroupTimestamp]:
        """All boundary timestamps as view objects."""
        if self._timestamp_table is None:
            return []
        return [self._row_to_timestamp(i) for i in range(self.n_timestamps)]

    def get_timestamp_at_index(self, index: int) -> GroupTimestamp:
        """Get a specific timestamp by index.

        Args:
            index: The row index in the timestamp table.

        Returns:
            The GroupTimestamp at that index.

        Raises:
            IndexError: If index is out of range.
        """
        if self._timestamp_table is None or index >= self.n_timestamps:
            raise IndexError(f"Timestamp index {index} out of range")
        if index < 0:
            index = self.n_timestamps + index
        return self._row_to_timestamp(index)

    def get_timestamp_at(
        self,
        coordinate: CoordinateSpec,
        timeline_id: str | None = None,
        *,
        relative_to: Literal["group", "original"] = "group",
        conversion_maps: ConversionMapsSpec = True,
    ) -> TimeStamp:
        """Get a TimeStamp at a specific coordinate.

        This is the primary coordinate resolution API for TimelineGroup.
        Returns a proper TimeStamp object (same as Timeline.get_timestamp).

        Args:
            coordinate: The query coordinate. Can be:
                - int/float/Fraction: Raw value, timeline_id required
                - Coordinate: Value with unit, timeline_id required
                - IdCoordinate: Value with unit AND timeline_id (timeline_id param optional)
            timeline_id: Which timeline the coordinate refers to.
                Required unless coordinate is an IdCoordinate.
            relative_to:
                "group" - coordinate is relative to timeline's 0-origin IN THIS GROUP
                         (default; e.g., "3 seconds into this group")
                "original" - coordinate is relative to timeline's ORIGINAL origin
                            (e.g., "50 seconds in the original timeline")
                            NOTE: Currently not implemented, reserved for future use.
            conversion_maps: Whether to include C-Map values in timestamp.
                - True (default): C-Maps accessible via ts.get_unit() and ts["unit_name"]
                - False/None: Only timeline coordinates

        Returns:
            TimeStamp with axis set to the input coordinate and source_id set to
            the timeline. Access other timelines via ts["other_id"] or ts.get().
            Access C-Maps via ts.get_unit() or ts["unit_name"].

        Raises:
            KeyError: If timeline_id is not in the group.
            ValueError: If coordinate is outside the timeline's range in the group.
            ValueError: If timeline_id is None and coordinate is not IdCoordinate.

        Examples:
            >>> ts = group.get_timestamp_at(75.0, "audio:1")
            >>> ts.axis
            75.0
            >>> ts["dgt1:1"]
            2437.5
            >>> ts.get_unit(TimeUnit.seconds)  # C-Map conversion
            75.0

            >>> # Using IdCoordinate (timeline_id extracted automatically)
            >>> coord = IdCoordinate(75.0, TimeUnit.seconds, "audio:1")
            >>> ts = group.get_timestamp_at(coord)
            >>> ts.axis
            75.0
        """
        resolved = resolve_coordinate_spec(coordinate, timeline_id=timeline_id)
        timeline_id = resolved.timeline_id

        if timeline_id is None:
            raise ValueError(
                "timeline_id is required unless coordinate is an IdCoordinate"
            )

        if timeline_id not in self._timelines:
            raise KeyError(
                f"Timeline '{timeline_id}' not in group. "
                f"Available timelines: {self.timeline_ids}"
            )

        native_value = (
            self.get_timeline(timeline_id)
            .get_coordinate(Coordinate(resolved.value, resolved.unit))
            .value
            if resolved.unit is not None
            else resolved.value
        )
        coord_value = float(native_value)
        exact_axis = (
            Fraction(native_value, 1)
            if isinstance(native_value, int)
            else native_value if isinstance(native_value, Fraction) else None
        )

        if self._timestamp_table is None:
            raise ValueError(f"Group '{self.id}' has no timestamps")

        # Adjust for original-relative mode (future extension)
        if relative_to == "original":
            # TODO: Implement offset tracking for original coordinates
            # For now, treat as group-relative
            pass

        # Find the row index (exact match) or verify coordinate is in range
        coords = self._timestamp_table.column(timeline_id).to_pylist()

        # Find bounding rows
        low_idx = None
        high_idx = None
        for i, val in enumerate(coords):
            if val is not None:
                if val <= coord_value:
                    low_idx = i
                if val >= coord_value and high_idx is None:
                    high_idx = i
                    break

        if low_idx is None or high_idx is None:
            raise ValueError(
                f"Coordinate {_format_coordinate_value(coord_value)} "
                f"outside range for '{timeline_id}'"
            )

        # Determine row_index: -1 for interpolated, actual index for exact match
        row_index = -1  # Default: interpolated
        if low_idx == high_idx:
            # Exact match at a boundary
            row_index = low_idx

        # Return a proper TimeStamp object
        # The TimeStamp will use InterpolationMaps for coordinate conversion
        # and _get_unit_map_for_timeline for C-Map access
        return TimeStamp(
            axis=exact_axis if exact_axis is not None else coord_value,
            source=self,
            source_id=timeline_id,
            row_index=row_index,
            conversion_maps=conversion_maps,
        )

    def get_timestamps_at(
        self,
        coordinates: Sequence[CoordinateSpec],
        timeline_id: str | None = None,
        *,
        conversion_maps: ConversionMapsSpec = True,
        units: bool = True,
    ) -> pd.DataFrame:
        """Get timestamps at multiple coordinates - the batch version of get_timestamp_at.

        This is the DEAD-SIMPLE API for batch coordinate transfer: pass a sequence of
        coordinates and get back a DataFrame with one field per timeline and per C-Map.

        Args:
            coordinates: Sequence of CoordinateSpec to query.
            timeline_id: Which timeline the coordinates refer to. Required for
                entries without an embedded timeline ID.
            conversion_maps: Whether to include C-Map fields from member timelines.
                - True (default): Include all attached C-Maps
                - False/None: Only timeline coordinates
            units: If True (default), append units to field names.

        Returns:
            DataFrame with one row per coordinate, one field per timeline and C-Map.

        Examples:
            >>> # Get timestamps at multiple score positions
            >>> coords = [0.0, 100.0, 200.0, 400.0]
            >>> df = group.get_timestamps_at(coords, "clt1_score")
            >>> df.columns
            Index(['clt1_score (quarterbeats)', 'dgt_holes (pixels)', ...])
        """
        import pandas as pd

        # Get individual timestamps and convert to dicts
        timestamp_dicts: list[dict[str, float | None]] = []
        for coord in coordinates:
            resolved = resolve_coordinate_spec(coord, timeline_id=timeline_id)
            resolved_timeline_id = resolved.timeline_id
            if resolved_timeline_id is None:
                raise ValueError(
                    "timeline_id is required unless coordinate is an IdCoordinate"
                )
            coord_float = float(
                self.get_timeline(resolved_timeline_id)
                .get_coordinate(Coordinate(resolved.value, resolved.unit))
                .value
                if resolved.unit is not None
                else resolved.value
            )
            try:
                ts = self.get_timestamp_at(
                    coord_float,
                    resolved_timeline_id,
                    conversion_maps=conversion_maps,
                )
                # Use to_dict() to get all coordinates including C-Maps
                ts_dict = ts.to_dict(
                    include_children=True,
                    conversion_units="all" if conversion_maps else None,
                )
                timestamp_dicts.append(ts_dict)
            except (KeyError, ValueError):
                # Coordinate out of range - add row with just the input coordinate
                timestamp_dicts.append({resolved_timeline_id: coord_float})

        if not timestamp_dicts:
            return pd.DataFrame()

        # Build DataFrame
        df = pd.DataFrame(timestamp_dicts)

        # Add units to field names if requested
        if units:
            new_names = {}
            for name in df.columns:
                # Try to get unit for this field (timeline ID or C-map unit)
                unit = self._get_unit_for_timeline(name)
                if unit is not None:
                    new_names[name] = f"{name} ({unit.value})"
                else:
                    new_names[name] = name
            df = df.rename(columns=new_names)

        return df

    def get_timestamp_table(
        self,
        timeline_filter: set[str] | None = None,
        conversion_maps: ConversionMapsSpec = True,
    ) -> pa.Table:
        """Get the timestamp table (or a filtered subset).

        Args:
            timeline_filter: Only include these timeline fields.
            conversion_maps: Whether to include C-Map fields from member timelines.
                - True (default): Include all attached C-Maps from all timelines
                - False/None: No C-Map fields

        Returns:
            pa.Table with one row per timestamp, one field per timeline,
            plus C-Map fields if conversion_maps=True.
            Returns empty table if group has no timestamps.
        """
        if self._timestamp_table is None:
            return pa.table({})

        table = self._timestamp_table

        # Filter timeline fields if requested
        if timeline_filter is not None:
            keep = [c for c in table.column_names if c in timeline_filter]
            table = table.select(keep)

        # Add C-Map fields from member timelines
        if conversion_maps:
            table = self._add_cmap_fields(table)

        return table

    def _add_cmap_fields(self, table: pa.Table) -> pa.Table:
        """Add C-Map fields from member timelines to a timestamp table.

        For each timeline in the group that has attached C-Maps, applies
        those C-Maps to the timeline's coordinate field and adds the
        results as new fields.

        Args:
            table: The timestamp table to augment.

        Returns:
            Table with additional C-Map fields.
        """
        if table.num_rows == 0:
            return table

        # Collect all C-Maps from member timelines
        for timeline_id, timeline in self._timelines.items():
            if timeline_id not in table.column_names:
                continue

            # Get coordinate values for this timeline
            coord_arr = table.column(timeline_id)
            coord_np = coord_arr.to_numpy(zero_copy_only=False)

            # Apply each of the timeline's C-Maps
            for cmap in timeline._conversion_maps.values():
                # Compute converted values (handle NaN from nulls)
                try:
                    converted = cmap.convert_array(coord_np)
                except Exception:
                    # Skip C-Maps that fail (e.g., out of bounds)
                    continue

                # Field name uses C-Map's name property
                field_name = cmap.name

                # Add field with metadata
                target_unit = getattr(cmap, "target_unit", None)
                unit_value = target_unit.value if target_unit else "unknown"

                new_field = pa.field(
                    field_name,
                    pa.float64(),
                    metadata=blob_metadata(
                        unit=unit_value,
                        cmap_id=cmap.id,
                        source_timeline=timeline_id,
                    ),
                )
                table = table.append_column(new_field, pa.array(converted))

        return table

    def to_dataframe(
        self,
        timeline_filter: set[str] | None = None,
        conversion_maps: ConversionMapsSpec = True,
        *,
        fields: "ColumnNaming | Callable[[str, dict], str] | list[str] | None" = None,
        units: bool = True,
        format: str = "pandas",
    ) -> pd.DataFrame:
        """Generate timestamps as a pandas DataFrame with formatted field names.

        This is the recommended high-level method for getting timestamp data.
        It builds on get_timestamp_table() and applies field formatting.

        Args:
            timeline_filter: Only include these timelines as fields.
            conversion_maps: Whether to include C-Map fields from member timelines.
                - True (default): Include all attached C-Maps
                - False/None: No C-Map fields
            fields: How to name the DataFrame fields. Options:
                - None or ColumnNaming.name (default): Use timeline/cmap name
                - ColumnNaming.id: Use timeline/cmap id
                - Callable: Function taking (name, metadata_dict) -> new_name
                - list[str]: Explicit field names
            units: If True (default), append units to field names like "name (unit)".
            format: Output format. Currently only "pandas" is supported.

        Returns:
            pandas DataFrame with:
            - Fields named according to the ``fields`` parameter
            - Units appended if ``units=True``
            - Integer fields using pandas nullable Int64 dtype

        Examples:
            >>> df = group.to_dataframe()
            >>> df.columns
            Index(['audio (seconds)', 'dgt1 (pixels)', 'pixels_to_beats (beats)'])

            >>> # Without units in field names
            >>> df = group.to_dataframe(units=False)
            >>> df.columns
            Index(['audio', 'dgt1', 'pixels_to_beats'])
        """
        from timetoalign.core.timestamp import timestamp_table_to_dataframe

        table = self.get_timestamp_table(
            timeline_filter=timeline_filter,
            conversion_maps=conversion_maps,
        )
        return timestamp_table_to_dataframe(
            table=table,
            fields=fields,
            units=units,
            format=format,
        )

    def _row_to_timestamp(self, index: int) -> GroupTimestamp:
        """Convert a table row to a GroupTimestamp view object.

        Args:
            index: Row index in the timestamp table.

        Returns:
            GroupTimestamp with coordinates and units from that row.
        """
        if self._timestamp_table is None:
            raise ValueError("No timestamp table")

        row = self._timestamp_table.slice(index, 1)
        coords: dict[str, float | None] = {}
        units: dict[str, str] = {}

        for data_field in self._timestamp_table.schema:
            field_name = data_field.name
            val = row.column(field_name)[0].as_py()
            coords[field_name] = val  # None if null

            # Extract unit from field metadata
            unit_value = field_metadata(data_field).get("unit")
            if unit_value:
                units[field_name] = unit_value

        axis_timeline_id = next(iter(self._timelines))
        axis = coords[axis_timeline_id]
        return GroupTimestamp(
            coordinates=coords,
            units=units,
            row_index=index,
            source=self,
            source_id=axis_timeline_id,
            axis=axis,
        )

    # endregion

    # region Coordinate Conversion

    def convert(
        self,
        coordinate: CoordinateSpec,
        source: str,
        target: str,
        *,
        relative_to: Literal["group", "original"] = "group",
    ) -> Coordinate | None:
        """Convert a coordinate from one timeline to another.

        This is a convenience method that gets the timestamp at the source
        coordinate and returns the target timeline's coordinate from it.

        Args:
            coordinate: The coordinate value to convert. Accepts a raw
                int/float/Fraction, a Coordinate, or an IdCoordinate. A
                unit-qualified coordinate is resolved by the source timeline,
                and an IdCoordinate must agree with ``source``.
            source: Source timeline ID.
            target: Target timeline ID.
            relative_to:
                "group" - coordinate is relative to timeline's 0-origin IN THIS GROUP
                "original" - coordinate is relative to timeline's ORIGINAL origin

        Returns:
            A Coordinate in the target timeline's unit, or None if the target
            timeline is not present at this coordinate.

        Raises:
            KeyError: If source or target timeline is not in the group.
            ValueError: If coordinate is outside the source timeline's range.

        Examples:
            >>> group.convert(75.0, source="audio:1", target="dgt1:1")
            Coordinate(2437.5, pixels)
        """
        ts = self.get_timestamp_at(coordinate, source, relative_to=relative_to)
        return ts.get_coordinate(target)

    # endregion

    # region Range Queries

    def get_range(
        self,
        timeline_id: str,
        relative_to: Literal["group", "original"] = "group",
    ) -> tuple[float, float] | None:
        """Get the coordinate range for a timeline in the group.

        Args:
            timeline_id: The timeline to query.
            relative_to: Coordinate system for the result.

        Returns:
            (start, end) tuple, or None if timeline not in group.
        """
        if timeline_id not in self._timelines:
            return None

        if self._timestamp_table is None:
            return None

        coords = self._timestamp_table.column(timeline_id).to_pylist()

        # Find first and last non-null values
        start_val = None
        end_val = None
        for val in coords:
            if val is not None:
                if start_val is None:
                    start_val = val
                end_val = val

        if start_val is None or end_val is None:
            return None

        return (start_val, end_val)

    # endregion

    # region Unified Timestamp API (TimeStampSource Protocol)

    def get_timestamp_of(self, event_id: str) -> TimeStamp:
        """Get the TimeStamp for a specific event by its ID.

        Searches all timelines in the group for the event and returns
        the corresponding TimeStamp (same structure as Timeline.get_timestamp).

        Args:
            event_id: The event's unique identifier.

        Returns:
            TimeStamp at the event's coordinate, with access to all
            timelines via ts["timeline_id"] and C-Maps via ts.get_unit().

        Raises:
            KeyError: If the event is not found in any timeline.

        Examples:
            >>> ts = group.get_timestamp_of("note:000001")
            >>> ts["audio"]  # Get coordinate on audio timeline
            45.5
            >>> ts.get_unit(TimeUnit.seconds)  # C-Map conversion
            45.5
        """
        for tl_id, tl in self._timelines.items():
            event = tl.get_event(event_id)
            if event is not None:
                # Found the event - get its coordinate and return TimeStamp
                coord = event["start"]["value"]
                return self.get_timestamp_at(coord, tl_id)

        raise KeyError(
            f"Event {event_id!r} not found in any timeline in group. "
            f"Searched timelines: {self.timeline_ids}"
        )

    def get_timestamps_of(self, event_ids: Sequence[str]) -> pd.DataFrame:
        """Get timestamps for multiple events.

        Searches all timelines in the group for each event and returns
        a DataFrame with coordinates on all timelines.

        Args:
            event_ids: List of event IDs to look up.

        Returns:
            DataFrame with one row per event, indexed by event_id.
            Fields are timeline IDs with their coordinates.
            Events not found have NaN values.

        Examples:
            >>> df = group.get_timestamps_of(["note:000001", "note:000002"])
            >>> df.columns
            Index(['clt1', 'audio', 'dgt1'])
        """
        rows: list[dict[str, Any]] = []
        for event_id in event_ids:
            try:
                ts = self.get_timestamp_of(event_id)
                # Use to_dict() to materialize coordinates
                row: dict[str, Any] = dict(
                    ts.to_dict(include_children=True, conversion_units=None)
                )
                row["event_id"] = event_id
                rows.append(row)
            except KeyError:
                # Event not found - add row with NaN
                row = {"event_id": event_id}
                rows.append(row)

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df = df.set_index("event_id")
        return df

    def _get_interpolation_map(
        self, target_id: str, source_id: str | None = None
    ) -> InterpolationMap | None:
        """Get InterpolationMap for coordinate conversion to target.

        This method is part of the TimeStampSource protocol.

        For TimelineGroup, the map key is source_id:target_id since
        groups have multiple member timelines.

        Args:
            target_id: Target timeline ID.
            source_id: Source timeline ID (required for TimelineGroup).

        Returns:
            InterpolationMap for conversion, or None if not available.
        """
        if source_id is None:
            return None
        map_key = f"{source_id}:{target_id}"
        return self._interpolation_maps.get(map_key)

    def _get_exact_interpolated_coordinate(
        self,
        target_id: str,
        source_id: str | None,
        source_coordinate: Fraction,
    ) -> CoordinateValue | None:
        """Interpolate exactly when both bounding pairs are known rationals.

        Group timestamp columns remain float arrays for fast lookup. Their
        first and last present values, however, represent the exact zero and
        length of each member timeline. This method uses those authoritative
        values for rational scalar queries and declines exact interpolation
        when an internal boundary has no exact representation.

        Args:
            target_id: Timeline to convert into.
            source_id: Timeline containing ``source_coordinate``.
            source_coordinate: Exact coordinate on the source timeline.

        Returns:
            The exact converted value when it can be proven, otherwise None.
        """
        if source_id is None or target_id not in self._timelines:
            return None
        if target_id == source_id:
            return source_coordinate
        if self._timestamp_table is None:
            return None

        source_values = self._timestamp_table.column(source_id).to_pylist()
        source_float = float(source_coordinate)
        low_idx: int | None = None
        high_idx: int | None = None
        for index, value in enumerate(source_values):
            if value is None:
                continue
            if value <= source_float:
                low_idx = index
            if value >= source_float and high_idx is None:
                high_idx = index
                break
        if low_idx is None or high_idx is None:
            return None

        def exact_boundary(timeline_id: str, index: int) -> Fraction | None:
            values = self._timestamp_table.column(timeline_id).to_pylist()
            present = [i for i, value in enumerate(values) if value is not None]
            if not present:
                return None
            if index == present[0]:
                return Fraction(0, 1)
            if index == present[-1]:
                length = self._timelines[timeline_id].length.value
                if isinstance(length, int):
                    return Fraction(length, 1)
                if isinstance(length, Fraction):
                    return length
            return None

        source_low = exact_boundary(source_id, low_idx)
        source_high = exact_boundary(source_id, high_idx)
        target_low = exact_boundary(target_id, low_idx)
        target_high = exact_boundary(target_id, high_idx)
        if None in (source_low, source_high, target_low, target_high):
            return None
        assert source_low is not None
        assert source_high is not None
        assert target_low is not None
        assert target_high is not None
        if source_low == source_high:
            return target_low

        ratio = (source_coordinate - source_low) / (source_high - source_low)
        result = target_low + ratio * (target_high - target_low)
        if self._timelines[target_id].number_type == NumberType.int:
            return round(result)
        # This is structural re-expression, not empirical interpolation: the
        # relation is proven from the members' own declared origins and
        # lengths, so it is definitional and stays exact. Estimating between
        # matched anchor pairs is the other thing, and that lane is float --
        # a fitted relation that happens to come out a nice ratio is still a
        # fit, and must not be typed as though someone had claimed it.
        return result

    def _get_unit_map(self, unit: "TimeUnit") -> InterpolationMap | None:
        """Get InterpolationMap for unit-based conversion.

        This method is part of the TimeStampSource protocol.
        For TimelineGroup, returns None as groups don't have their own C-Maps.
        Use _get_unit_map_for_timeline() to get C-Maps from member timelines.

        Args:
            unit: Target unit.

        Returns:
            None (use _get_unit_map_for_timeline for member timeline C-Maps).
        """
        return None

    def _get_unit_map_for_timeline(
        self, timeline_id: str, unit: "TimeUnit"
    ) -> "InterpolationMap | Any | None":
        """Get a C-Map for a specific member timeline.

        This method enables TimeStamp.get_unit() to access C-Maps from
        member timelines when the source is a TimelineGroup.

        Args:
            timeline_id: The member timeline to look up C-Map on.
            unit: The target unit.

        Returns:
            The C-Map (InterpolationMap or ConversionMap), or None if not found.
        """
        timeline = self._timelines.get(timeline_id)
        if timeline is not None:
            return timeline._get_unit_map(unit)
        # Member-descendant: locate the owning member and delegate.
        for member in self._timelines.values():
            descendant = member._find_descendant(timeline_id)
            if descendant is not None:
                return descendant._get_unit_map(unit)
        return None

    def _get_related_timeline_ids(self) -> list[str]:
        """Get IDs of the direct member timelines.

        This method is part of the TimeStampSource protocol. It reports only
        the members; their descendants are reached through
        :meth:`_get_descendant_timeline_ids`.

        Returns:
            List of member timeline IDs.
        """
        return list(self._timelines.keys())

    def _get_descendant_timeline_ids(self) -> list[str]:
        """Get IDs of every member and member-descendant timeline.

        This method is part of the TimeStampSource protocol. Timestamps use it
        to surface conversions from the full subtree of each member.
        """
        ids: list[str] = []
        for member_id, member in self._timelines.items():
            ids.append(member_id)
            ids.extend(member._get_descendant_timeline_ids())
        return ids

    def _get_conversion_maps_for_timeline(
        self, timeline_id: str
    ) -> "list[ConversionMap[Any]]":
        """Get every conversion map attached to a member or its descendants.

        This method is part of the TimeStampSource protocol. It returns C-Maps
        of all kinds, including those with no ``target_unit``, so timestamps
        expose label and structured-value maps across the whole subtree.
        """
        timeline = self._timelines.get(timeline_id)
        if timeline is None:
            for member in self._timelines.values():
                timeline = member._find_descendant(timeline_id)
                if timeline is not None:
                    break
        if timeline is None:
            return []
        return list(timeline._conversion_maps.values())

    def _descendant_coordinate(
        self, timeline_id: str, axis: float, source_id: str
    ) -> float | None:
        """Resolve a coordinate on a member-descendant of this group.

        The axis (on *source_id*) is transferred to the owning member via the
        group's InterpolationMap, then into the descendant via the member's
        exact offset arithmetic. Returns None if the owning member is not
        reachable at *axis*, or the coordinate leaves the descendant's span.

        Direct members are resolved by ``TimeStamp.get`` (with its own
        reachability guard), so this method handles member-descendants only.
        """
        if timeline_id in self._timelines:
            return None
        for member_id, member in self._timelines.items():
            if member._find_descendant(timeline_id) is None:
                continue
            if member_id == source_id:
                member_coord: float = axis
            else:
                if not self._contains_coordinate(member_id, axis, source_id):
                    return None
                imap = self._get_interpolation_map(member_id, source_id=source_id)
                if imap is None:
                    return None
                if imap.source_id == source_id:
                    member_coord = float(imap(axis))
                else:
                    member_coord = float(imap.inverse()(axis))
            return member._get_child_coordinate(timeline_id, member_coord)
        return None

    def _get_available_units(self) -> list["TimeUnit"]:
        """Get all units available via C-Maps from member timelines.

        This method is part of the TimeStampSource protocol.
        Aggregates all C-Map target units from all member timelines.

        Returns:
            List of all available units from member timeline C-Maps.
        """
        units: set["TimeUnit"] = set()
        for timeline in self._timelines.values():
            units.update(timeline._get_available_units())
        return list(units)

    def _get_unit_for_timeline(self, timeline_id: str) -> "TimeUnit | None":
        """Get the TimeUnit for a timeline in the group.

        This method is part of the TimeStampSource protocol. It enables
        TimeStamp to construct proper Coordinate objects with correct units.

        Args:
            timeline_id: The timeline ID to look up.

        Returns:
            The TimeUnit for the timeline, or None if not found.
        """
        if timeline_id in self._timelines:
            return self._timelines[timeline_id].unit
        for member in self._timelines.values():
            descendant = member._find_descendant(timeline_id)
            if descendant is not None:
                return descendant._unit
        return None

    def _contains_coordinate(
        self, timeline_id: str, axis: float, source_id: str | None = None
    ) -> bool:
        """Check if a timeline has a valid coordinate at the given axis.

        This method is part of the TimeStampSource protocol. For TimelineGroup,
        we need to check if the target timeline has values at the given axis
        coordinate on the source timeline.

        Args:
            timeline_id: The target timeline to check.
            axis: The coordinate on the source timeline.
            source_id: The source timeline ID (required for accurate checking).

        Returns:
            True if the target timeline is reachable at this axis coordinate.
        """
        if timeline_id not in self._timelines:
            return False

        # If no timestamp table, assume reachable (will fail later anyway)
        if self._timestamp_table is None:
            return True

        # For the source timeline itself, always reachable
        if source_id is not None and timeline_id == source_id:
            return True

        # If we don't know the source_id, we can't check properly
        if source_id is None:
            # Fall back to checking if the timeline has any values
            target_vals = self._timestamp_table.column(timeline_id).to_pylist()
            return any(v is not None for v in target_vals)

        # Get the source field to find bounding rows
        source_vals = self._timestamp_table.column(source_id).to_pylist()
        target_vals = self._timestamp_table.column(timeline_id).to_pylist()

        # Find bounding rows for the axis coordinate on source
        low_idx = None
        high_idx = None
        for i, val in enumerate(source_vals):
            if val is not None:
                if val <= axis:
                    low_idx = i
                if val >= axis and high_idx is None:
                    high_idx = i
                    break

        if low_idx is None or high_idx is None:
            return False

        # Check if target timeline has non-None values in the bounding rows
        low_target = target_vals[low_idx] if low_idx < len(target_vals) else None
        high_target = target_vals[high_idx] if high_idx < len(target_vals) else None

        # Both bounds must have values for interpolation to work
        return low_target is not None and high_target is not None

    def _build_interpolation_maps(self) -> None:
        """Build InterpolationMaps from the timestamp table.

        Called after timeline additions/removals to update the
        interpolation maps for O(log n) coordinate conversion.
        """
        if self._timestamp_table is None or self._timestamp_table.num_rows < 2:
            self._interpolation_maps = {}
            return

        # Build pairwise maps between all timelines
        timeline_ids = list(self._timelines.keys())
        new_maps: dict[str, InterpolationMap] = {}

        for i, source_id in enumerate(timeline_ids):
            source_coords = self._timestamp_table.column(source_id).to_pylist()

            for j, target_id in enumerate(timeline_ids):
                if i == j:
                    continue

                target_coords = self._timestamp_table.column(target_id).to_pylist()

                # Extract pairs where both have values
                source_vals: list[float] = []
                target_vals: list[float] = []

                for s, t in zip(source_coords, target_coords):
                    if s is not None and t is not None:
                        source_vals.append(s)
                        target_vals.append(t)

                if len(source_vals) >= 2:
                    # Create InterpolationMap: source -> target
                    # Key is (source_id, target_id) combined
                    map_key = f"{source_id}:{target_id}"
                    new_maps[map_key] = InterpolationMap(
                        source_coords=np.array(source_vals, dtype=np.float64),
                        target_coords=np.array(target_vals, dtype=np.float64),
                        source_id=source_id,
                        target_id=target_id,
                    )

        self._interpolation_maps = new_maps

    def _get_pairwise_map(
        self, source_id: str, target_id: str
    ) -> InterpolationMap | None:
        """Get the InterpolationMap for converting between two timelines.

        Args:
            source_id: Source timeline ID.
            target_id: Target timeline ID.

        Returns:
            InterpolationMap for the conversion, or None if not available.
        """
        map_key = f"{source_id}:{target_id}"
        return self._interpolation_maps.get(map_key)

    # endregion

    # region Internal Methods - Boundary Resolution

    def _resolve_boundary(
        self,
        spec: CoordinateSpec | GroupTimestamp | None,
        is_start: bool,
        new_timeline: "Timeline",
    ) -> dict[str, Any]:
        """Resolve a boundary specification to internal representation.

        Args:
            spec: The boundary specification (various forms).
            is_start: True for start boundary, False for end.
            new_timeline: The timeline being added.

        Returns:
            Dict with keys:
                - "mode": "existing_timestamp" | "new_timestamp"
                - "row_index": int (if existing)
                - "coordinates": dict (if new timestamp needed)
                - "new_timeline_coord": float (the new timeline's coordinate)
        """
        # Empty group: use timeline's own boundaries
        if self._timestamp_table is None:
            coord = 0.0 if is_start else float(new_timeline.length.value)
            return {
                "mode": "new_timestamp",
                "coordinates": {new_timeline.id: coord},
                "new_timeline_coord": coord,
            }

        # None: use current group start/end
        if spec is None:
            row_index = 0 if is_start else self.n_timestamps - 1
            new_coord = 0.0 if is_start else float(new_timeline.length.value)
            return {
                "mode": "existing_timestamp",
                "row_index": row_index,
                "new_timeline_coord": new_coord,
            }

        # GroupTimestamp: direct reference
        if isinstance(spec, GroupTimestamp):
            new_coord = 0.0 if is_start else float(new_timeline.length.value)
            return {
                "mode": "existing_timestamp",
                "row_index": spec.row_index,
                "new_timeline_coord": new_coord,
            }

        # IdCoordinate: use timeline_id attribute directly
        if isinstance(spec, IdCoordinate):
            if spec.timeline_id not in self._timelines:
                raise KeyError(
                    f"Timeline '{spec.timeline_id}' not in group. "
                    f"Available timelines: {self.timeline_ids}"
                )
            native_coord = self._timelines[spec.timeline_id].get_coordinate(spec)
            return self._find_or_create_at(
                float(native_coord.value), spec.timeline_id, new_timeline, is_start
            )

        # Unqualified CoordinateSpec: need an existing timeline for context
        try:
            resolved = resolve_coordinate_spec(spec)
        except TypeError as error:
            raise ValueError(f"Invalid boundary specification: {spec}") from error

        if resolved.timeline_id is None:
            # If only one timeline exists, use that for context
            if len(self._timelines) == 1:
                tl_id = next(iter(self._timelines.keys()))
                native_coord = self._timelines[tl_id].get_coordinate(spec)
                return self._find_or_create_at(
                    float(native_coord.value), tl_id, new_timeline, is_start
                )
            else:
                raise ValueError(
                    f"Ambiguous boundary specification: {spec}. "
                    f"Multiple timelines exist. Use IdCoordinate."
                )

        raise ValueError(f"Invalid boundary specification: {spec}")

    def _find_or_create_at(
        self,
        coord: float,
        timeline_id: str,
        new_timeline: "Timeline",
        is_start: bool,
    ) -> dict[str, Any]:
        """Find existing timestamp or create spec for new one at coordinate.

        Args:
            coord: The coordinate in the specified timeline.
            timeline_id: Which timeline the coordinate refers to.
            new_timeline: The timeline being added.
            is_start: True for start boundary, False for end.

        Returns:
            Boundary specification dict.
        """
        if timeline_id not in self._timelines:
            raise KeyError(
                f"Timeline '{timeline_id}' not in group. "
                f"Available timelines: {self.timeline_ids}"
            )

        if self._timestamp_table is None:
            raise ValueError("Cannot find timestamp in empty group")

        # Check if coordinate matches an existing timestamp exactly
        coords = self._timestamp_table.column(timeline_id).to_pylist()
        for i, val in enumerate(coords):
            if val is not None and abs(val - coord) < 1e-10:  # Exact match tolerance
                new_coord = 0.0 if is_start else float(new_timeline.length.value)
                return {
                    "mode": "existing_timestamp",
                    "row_index": i,
                    "new_timeline_coord": new_coord,
                }

        # Need to create a new timestamp via interpolation
        # Find bounding rows
        low_idx = None
        high_idx = None
        for i, val in enumerate(coords):
            if val is not None:
                if val <= coord:
                    low_idx = i
                if val >= coord and high_idx is None:
                    high_idx = i
                    break

        if low_idx is None or high_idx is None:
            raise ValueError(
                f"Coordinate {_format_coordinate_value(coord)} is outside range "
                f"for timeline '{timeline_id}'"
            )

        # Interpolate to get coordinates for all existing timelines
        ratio = (coord - coords[low_idx]) / (coords[high_idx] - coords[low_idx])

        new_row_coords: dict[str, float | None] = {}
        for field_name in self._timestamp_table.column_names:
            field_vals = self._timestamp_table.column(field_name).to_pylist()
            low_val = field_vals[low_idx]
            high_val = field_vals[high_idx]

            if low_val is not None and high_val is not None:
                if field_name == timeline_id:
                    # Use the exact specified coordinate for the source timeline
                    # to avoid floating-point errors from interpolation round-trip
                    new_row_coords[field_name] = coord
                else:
                    val = low_val + ratio * (high_val - low_val)
                    # Round to integer for discrete timelines (samples, pixels, …)
                    tl = self._timelines.get(field_name)
                    if tl is not None and tl.number_type == NumberType.int:
                        val = round(val)
                    new_row_coords[field_name] = val
            else:
                new_row_coords[field_name] = None

        new_coord = 0.0 if is_start else float(new_timeline.length.value)

        return {
            "mode": "new_timestamp",
            "coordinates": new_row_coords,
            "new_timeline_coord": new_coord,
            "insert_after_idx": low_idx,  # Where to insert in sorted order
        }

    def _requires_extension(self, end_spec: dict[str, Any]) -> bool:
        """Check if the end spec would require extending the group.

        Args:
            end_spec: The resolved end boundary specification.

        Returns:
            True if extension is required.
        """
        if end_spec["mode"] == "new_timestamp":
            # If creating a new timestamp for the end, check if it's beyond current end
            if self._timestamp_table is not None:
                insert_idx = end_spec.get("insert_after_idx")
                if insert_idx is not None and insert_idx == self.n_timestamps - 1:
                    return True
        return False

    # endregion

    # region Internal Methods - Table Manipulation

    def _insert_timeline(
        self,
        timeline: "Timeline",
        start_spec: dict[str, Any],
        end_spec: dict[str, Any],
    ) -> None:
        """Insert a timeline into the timestamp table.

        Args:
            timeline: The timeline being added.
            start_spec: Resolved start boundary specification.
            end_spec: Resolved end boundary specification.
        """
        # Handle empty group
        if self._timestamp_table is None:
            # Create initial table with schema including unit metadata
            schema = pa.schema(
                [
                    pa.field(
                        timeline.id,
                        pa.float64(),
                        metadata=blob_metadata(
                            unit=timeline.unit.value,
                            timeline_id=timeline.id,
                        ),
                    )
                ]
            )
            self._timestamp_table = pa.table(
                {
                    timeline.id: pa.array(
                        [
                            start_spec["new_timeline_coord"],
                            end_spec["new_timeline_coord"],
                        ],
                        type=pa.float64(),
                    )
                },
                schema=schema,
            )
            return

        # Insert new timestamp rows if needed (in correct sorted order)
        # We need to track row indices as we insert
        rows_inserted = 0

        if start_spec["mode"] == "new_timestamp":
            insert_idx = start_spec.get("insert_after_idx", 0) + rows_inserted + 1
            self._insert_timestamp_row(start_spec["coordinates"], insert_idx)
            rows_inserted += 1
            start_spec["row_index"] = insert_idx
        else:
            start_spec["row_index"] = start_spec.get("row_index", 0)

        if end_spec["mode"] == "new_timestamp":
            insert_idx = end_spec.get("insert_after_idx", self.n_timestamps - 1)
            insert_idx += rows_inserted + 1
            self._insert_timestamp_row(end_spec["coordinates"], insert_idx)
            end_spec["row_index"] = insert_idx
        else:
            # Adjust for any rows inserted before this index
            end_spec["row_index"] = (
                end_spec.get("row_index", self.n_timestamps - 1) + rows_inserted
            )

        # Get final indices
        start_idx = start_spec["row_index"]
        end_idx = end_spec["row_index"]

        # Build new field with interpolated values
        n_rows = self.n_timestamps
        new_values: list[float | None] = []

        for i in range(n_rows):
            if i < start_idx or i > end_idx:
                new_values.append(None)
            elif i == start_idx:
                new_values.append(start_spec["new_timeline_coord"])
            elif i == end_idx:
                new_values.append(end_spec["new_timeline_coord"])
            else:
                # Interpolate
                ratio = (i - start_idx) / (end_idx - start_idx)
                coord = start_spec["new_timeline_coord"] + ratio * (
                    end_spec["new_timeline_coord"] - start_spec["new_timeline_coord"]
                )
                new_values.append(coord)

        # Add field with unit metadata
        new_field = pa.field(
            timeline.id,
            pa.float64(),
            metadata=blob_metadata(
                unit=timeline.unit.value,
                timeline_id=timeline.id,
            ),
        )
        self._timestamp_table = self._timestamp_table.append_column(
            new_field, pa.array(new_values, type=pa.float64())
        )

    def _insert_timestamp_row(
        self,
        coordinates: dict[str, float | None],
        insert_index: int,
    ) -> None:
        """Insert a new row into the timestamp table at the given index.

        Args:
            coordinates: Dict of timeline_id -> coordinate for the new row.
            insert_index: Where to insert (rows at and after shift down).
        """
        if self._timestamp_table is None:
            return

        # Build a single-row table for the new timestamp
        # Preserve the existing schema with metadata
        new_row_data: dict[str, list[float | None]] = {}
        for field_name in self._timestamp_table.column_names:
            new_row_data[field_name] = [coordinates.get(field_name)]

        # Create arrays and use existing schema to preserve metadata
        arrays = [
            pa.array([new_row_data[name][0]], type=pa.float64())
            for name in self._timestamp_table.column_names
        ]
        new_row_table = pa.table(
            dict(zip(self._timestamp_table.column_names, arrays)),
            schema=self._timestamp_table.schema,
        )

        # Split existing table and concatenate
        before = self._timestamp_table.slice(0, insert_index)
        after = self._timestamp_table.slice(insert_index)

        self._timestamp_table = pa.concat_tables([before, new_row_table, after])

    def _remove_timeline_field(self, timeline_id: str) -> None:
        """Remove a timeline's field from the timestamp table.

        Also removes any rows that become all-null after removal.

        Args:
            timeline_id: The timeline ID (field name) to remove.
        """
        if self._timestamp_table is None:
            return

        # Get field names except the one to remove
        remaining = [c for c in self._timestamp_table.column_names if c != timeline_id]

        if not remaining:
            # No fields left
            self._timestamp_table = None
            return

        # Select remaining fields
        self._timestamp_table = self._timestamp_table.select(remaining)

        # Remove rows where all values are null
        self._remove_all_null_rows()

    def _remove_all_null_rows(self) -> None:
        """Remove rows from timestamp table where all values are null."""
        if self._timestamp_table is None or self._timestamp_table.num_rows == 0:
            return

        # Check each row
        rows_to_keep: list[int] = []
        for i in range(self._timestamp_table.num_rows):
            row = self._timestamp_table.slice(i, 1)
            has_value = False
            for field_name in row.column_names:
                val = row.column(field_name)[0].as_py()
                if val is not None:
                    has_value = True
                    break
            if has_value:
                rows_to_keep.append(i)

        if len(rows_to_keep) == self._timestamp_table.num_rows:
            return  # No rows to remove

        if not rows_to_keep:
            self._timestamp_table = None
            return

        # Take only the rows we want to keep
        indices = pa.array(rows_to_keep)
        self._timestamp_table = self._timestamp_table.take(indices)

    # endregion

    # region Timeline-like API

    def __len__(self) -> int:
        """Number of timelines."""
        return self.n_timelines

    def __iter__(self) -> Iterator["Timeline"]:
        """Iterate over member timelines."""
        return iter(self._timelines.values())

    def __repr__(self) -> str:
        return (
            f"TimelineGroup(id={self.id!r}, n_timelines={self.n_timelines}, "
            f"n_timestamps={self.n_timestamps}, locked={self._is_locked})"
        )

    def __str__(self) -> str:
        """Return human-readable ASCII diagram of the group.

        Uses the diagram() method to generate a visual representation
        showing all member timelines in a boxed layout.
        """
        return str(self.diagram())

    def _repr_html_(self) -> str:
        """Return HTML representation for Jupyter notebooks.

        Displays the ASCII diagram in a monospace pre block so it
        renders correctly in notebook output cells.
        """
        return self.diagram()._repr_html_()

    # endregion

    def summary(self) -> dict[str, Any]:
        """Get a summary of the group.

        Returns:
            Dictionary with group information.
        """
        return {
            "id": self.id,
            "name": self.name,
            "n_timelines": self.n_timelines,
            "n_timestamps": self.n_timestamps,
            "timeline_ids": self.timeline_ids,
            "is_locked": self._is_locked,
            "meta": self.meta,
        }

    # endregion

    # region Unfolding

    def apply_flow(
        self,
        flow: "Flow",
        flow_controller: "FlowControllerBase",
        reference_timeline_id: str,
        *,
        include_children: bool = True,
        name: str | None = None,
    ) -> "TimelineGroup":
        """Unfold ALL timelines in this group via a single flow.

        Uses the flow controller's repeat structure to compute section
        boundaries in the reference timeline's coordinate space, then
        resolves those boundaries into every other timeline's coordinates
        via the group's interpolation maps. Each member is unfolded along its
        own resolved played spans: a new timeline of the member's **same
        concrete type** with one appended child (plus a matching named Region)
        per section, in unfolded coordinates.

        This is the group-level equivalent of
        `timetoalign.timelines.flow.create_unfolded_timeline`, but
        applied to every member at once. It shares the append-children
        assembly via `unfold_via_flowmap`, so each member's children and
        Regions carry the same per-section names as the single-timeline path
        (repeats suffixed ``-rend2``, ``-rend3`` …).

        Args:
            flow: The computed ``Flow`` (from ``controller.compute_flow()``).
            flow_controller: The ``FlowControllerBase`` that produced the flow.
                Required to convert flow sections to quarter-beat coordinates.
            reference_timeline_id: ID of the timeline whose coordinate space
                the flow is defined in (typically the score CLT).  Section
                boundaries are resolved here first, then mapped to all other
                timelines.
            include_children: Whether to recursively slice child timelines
                within each section.
            name: Name for the returned group.  Defaults to
                ``f"{self.name} (unfolded)"``.

        Returns:
            A new ``TimelineGroup`` containing the unfolded timelines. Each
            member keeps its original timeline ID, is the same concrete type as
            its source, and carries one appended child and Region per section.
            The reference timeline additionally carries a reverse FlowMap
            (id ``"source"``) and a forward FlowMap (id ``f"forward_{flow.id}"``).

        Raises:
            KeyError: If ``reference_timeline_id`` is not in the group.
            ValueError: If the flow controller cannot compute QB sections.

        Examples:
            >>> loader = Ms3Loader.from_file("notes.tsv", "measures.tsv")
            >>> controller = loader.create_flow_controller()
            >>> flow = controller.compute_flow(FlowMode.default)
            >>> score_group = TimelineGroup(
            ...     id="score", timelines=[clt1, dgt1, openscore]
            ... )
            >>> unfolded = score_group.apply_flow(flow, controller, "clt1")
        """
        from timetoalign.timelines.flow import FlowMap, compute_qb_sections

        from .flow.unfolding import unfold_via_flowmap

        if reference_timeline_id not in self._timelines:
            raise KeyError(
                f"Reference timeline '{reference_timeline_id}' not in group. "
                f"Available timelines: {self.timeline_ids}"
            )

        # 1. Section boundaries in QB space, plus the labelled reference map
        #    (its section labels name the children/Regions every member gets).
        qb_sections = compute_qb_sections(flow, flow_controller)
        reference_map = FlowMap.from_qb_sections(flow, qb_sections, id=flow.id)
        labels = [sec.label for sec in reference_map._sections]

        # 2. Resolve each section's boundaries into every member's coordinate
        #    space via the group's timestamps, collecting per-member played
        #    spans as (start, end, label) triples in target order.
        member_spans: dict[str, list[tuple[Any, Any, str | None]]] = {
            tl_id: [] for tl_id in self._timelines
        }
        for i, (qb_start, qb_end) in enumerate(qb_sections):
            start_ts = self.get_timestamp_at(float(qb_start), reference_timeline_id)
            end_ts = self.get_timestamp_at(float(qb_end), reference_timeline_id)

            for tl_id in self._timelines:
                coord_start = start_ts[tl_id]
                coord_end = end_ts[tl_id]
                if coord_start is None or coord_end is None:
                    start_display = (
                        "None"
                        if coord_start is None
                        else _format_coordinate_value(coord_start)
                    )
                    end_display = (
                        "None"
                        if coord_end is None
                        else _format_coordinate_value(coord_end)
                    )
                    raise ValueError(
                        f"Section {i}: cannot resolve boundaries for "
                        f"timeline '{tl_id}' from reference "
                        f"'{reference_timeline_id}' "
                        f"(start={start_display}, end={end_display})"
                    )
                member_spans[tl_id].append((coord_start, coord_end, labels[i]))

        # 3. Unfold each member along its own played spans, reusing the shared
        #    append-children assembly (same-type result, appended children +
        #    Regions), preserving each member's original timeline id.
        result_timelines = []
        for tl_id, tl in self._timelines.items():
            member_map = FlowMap(id=flow.id)
            member_map._build_from_intervals(member_spans[tl_id])
            result_timelines.append(
                unfold_via_flowmap(
                    tl, member_map, uid=tl_id, include_children=include_children
                )
            )

        # 4. Assemble the new group.
        group_name = name if name is not None else f"{self.name} (unfolded)"
        return TimelineGroup(
            id=f"{self.id}_unfolded" if self.id else None,
            name=group_name,
            timelines=result_timelines,
        )

    # endregion

    # region Display

    def diagram(
        self,
        width: int = 70,
        show_children: bool = True,
        max_children: int = 6,
        unicode: bool = True,
        depth: bool | int = True,
    ) -> "Diagram":
        """Generate ASCII diagram for this group.

        Args:
            width: Total width of the diagram in characters.
            show_children: Whether to expand child timelines.
            max_children: Maximum children per timeline.
            unicode: Use Unicode characters (True) or ASCII fallback (False).
            depth: Child levels to render for each member timeline. ``True``
                renders all levels, ``False`` renders direct children only,
                and a non-negative integer renders at most that many levels.
                In particular, ``0`` renders no child rows.

        Returns:
            Diagram object (displays as ASCII in terminal, rich HTML in Jupyter).

        Raises:
            ValueError: If ``depth`` is a negative integer.

        Examples:
            >>> print(group.diagram())
            TimelineGroup[my_group] (2 timelines, 2 timestamps)
            ┌────────────────────────────────────────────────────────────┐
            │ DiscreteGraphicalTimeline[dgt1:1] (11 events, 5 children)  │
            │ 0 ∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶ 4835 pixels    │
            │   ├─ system_1     0   ∶∶∶∶∶∶∶                    967       │
            │   └─ ...                                                   │
            └────────────────────────────────────────────────────────────┘
            Timestamps: 2
        """
        from timetoalign.display.ascii import group_diagram

        return group_diagram(
            self,
            width=width,
            show_children=show_children,
            max_children=max_children,
            unicode=unicode,
            depth=depth,
        )

    # endregion


# endregion
