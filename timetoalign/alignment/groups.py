"""TimelineGroup: Container for commensurable timelines.

This module implements the timestamp-based group architecture from Phase 7.4:
- Groups store timestamps in a PyArrow table (one row per boundary, one column per timeline)
- GroupTimestamp is a lightweight view object, created on retrieval
- Unified add_timeline() logic whether group is empty or has timelines
- Coordinate conversion via linear interpolation between timestamps
- Locking semantics like Timeline (is_locked, allow_extension)

The PerfectAlignment class is DEPRECATED - groups no longer need per-timeline
alignment objects. Boundary information is stored directly in the timestamp table.

IMPORTANT CONCEPTUAL DISTINCTION:
- Perfect Alignment: Bijective coordinate mapping (linear interpolation).
  Does NOT imply the alignment is musically/temporally correct.
- Correct Alignment: A special case where mapping corresponds to reality.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterator, Literal

import pandas as pd
import pyarrow as pa

from timetoalign.core import IdGenerator

if TYPE_CHECKING:
    from timetoalign.timelines import Timeline

module_logger = logging.getLogger(__name__)

# Module-level ID generator for groups
_group_id_generator = IdGenerator(scope="group")


def _reset_group_ids() -> None:
    """Reset the module-level ID generator. For testing only."""
    global _group_id_generator
    _group_id_generator = IdGenerator(scope="group")


# region GroupTimestamp


@dataclass(frozen=True)
class GroupTimestamp:
    """A synchronized instant across all timelines in a group.

    This is a view object created from a row in the group's timestamp table.
    Not stored directly - the table is the source of truth.

    Attributes:
        coordinates: Dictionary mapping timeline IDs to coordinates.
            None values indicate the timeline is not present at this instant.
        row_index: Index of this timestamp in the source table.
            -1 indicates an interpolated timestamp (not from a table row).

    Examples:
        >>> ts = group.get_timestamp_at(75.0, "audio:1")
        >>> ts["dgt1:1"]  # Get coordinate for dgt1
        2437.5
        >>> ts.present_timelines  # Which timelines have values here
        ['dgt1:1', 'audio:1']
    """

    coordinates: dict[str, float | None]
    row_index: int

    def get(self, timeline_id: str, default: float | None = None) -> float | None:
        """Get coordinate for a timeline.

        Args:
            timeline_id: The timeline to look up.
            default: Value to return if timeline not in coordinates.

        Returns:
            The coordinate value, or default if not found.
        """
        return self.coordinates.get(timeline_id, default)

    def __getitem__(self, timeline_id: str) -> float | None:
        """Subscript access: ts["audio:1"].

        Args:
            timeline_id: The timeline to look up.

        Returns:
            The coordinate value, or None if timeline not present at this instant.
        """
        return self.coordinates.get(timeline_id)

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


# endregion


# region PerfectAlignment (DEPRECATED)


@dataclass(frozen=True)
class PerfectAlignment:
    """DEPRECATED: TimelineGroup no longer uses per-timeline alignment objects.

    This class is maintained for backward compatibility only.
    Use TimelineGroup.add_timeline() with start/end parameters instead.

    Attributes:
        source_start: Start coordinate in the source timeline (default: 0).
        source_end: End coordinate in the source timeline.
        ref_start: Start coordinate in reference timeline (default: 0).
        ref_end: End coordinate in reference timeline.
    """

    source_start: float = 0.0
    source_end: float | None = None
    ref_start: float = 0.0
    ref_end: float | None = None

    def __post_init__(self) -> None:
        """Emit deprecation warning on instantiation."""
        warnings.warn(
            "PerfectAlignment is deprecated and will be removed in a future version. "
            "Use TimelineGroup.add_timeline() with start/end parameters instead.",
            DeprecationWarning,
            stacklevel=3,
        )

    def resolve(
        self,
        source_length: float,
        ref_length: float,
    ) -> tuple[float, float, float, float]:
        """Resolve None values to actual coordinates.

        Args:
            source_length: Length of the source timeline.
            ref_length: Length of the reference timeline.

        Returns:
            Tuple of (source_start, source_end, ref_start, ref_end).
        """
        src_end = self.source_end if self.source_end is not None else source_length
        r_end = self.ref_end if self.ref_end is not None else ref_length
        return (self.source_start, src_end, self.ref_start, r_end)

    def to_reference(
        self,
        coord: float,
        source_length: float,
        ref_length: float,
    ) -> float:
        """Convert source coordinate to reference coordinate.

        Args:
            coord: Coordinate in the source timeline.
            source_length: Length of the source timeline.
            ref_length: Length of the reference timeline.

        Returns:
            Corresponding coordinate in the reference timeline.
        """
        src_start, src_end, r_start, r_end = self.resolve(source_length, ref_length)

        if src_end == src_start:
            raise ValueError(
                f"Cannot convert: source range is zero-length "
                f"(start={src_start}, end={src_end})"
            )

        ratio = (coord - src_start) / (src_end - src_start)
        return r_start + ratio * (r_end - r_start)

    def from_reference(
        self,
        coord: float,
        source_length: float,
        ref_length: float,
    ) -> float:
        """Convert reference coordinate to source coordinate.

        Args:
            coord: Coordinate in the reference timeline.
            source_length: Length of the source timeline.
            ref_length: Length of the reference timeline.

        Returns:
            Corresponding coordinate in the source timeline.
        """
        src_start, src_end, r_start, r_end = self.resolve(source_length, ref_length)

        if r_end == r_start:
            raise ValueError(
                f"Cannot convert: reference range is zero-length "
                f"(start={r_start}, end={r_end})"
            )

        ratio = (coord - r_start) / (r_end - r_start)
        return src_start + ratio * (src_end - src_start)


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
        >>> group.add_timeline(
        ...     score_section,
        ...     start=(45.0, "audio:1"),
        ...     end=(135.0, "audio:1"),
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
        start: GroupTimestamp | tuple[float, str] | float | None = None,
        end: GroupTimestamp | tuple[float, str] | float | None = None,
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
                - GroupTimestamp: Use this existing timestamp
                - (coord, timeline_id): Position in an existing timeline
                - float: Coordinate (only if unambiguous unit)
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

            >>> # Add partial section with explicit boundaries
            >>> group.add_timeline(
            ...     score_section,
            ...     start=(45.0, "audio:1"),
            ...     end=(135.0, "audio:1"),
            ... )

            >>> # Extend group with new timeline
            >>> group.add_timeline(
            ...     extended_audio,
            ...     end=(200.0, "extended_audio:1"),
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

        self._logger.debug(
            f"Added timeline '{timeline.id}' with {self.n_timestamps} timestamps"
        )

    def remove_timeline(self, timeline_id: str) -> "Timeline":
        """Remove a timeline from the group.

        Updates timestamp table to remove the timeline's column.
        Rows where all remaining timelines have null are removed.

        Args:
            timeline_id: ID of the timeline to remove.

        Returns:
            The removed timeline.

        Raises:
            KeyError: If timeline_id is not in the group.
        """
        if timeline_id not in self._timelines:
            raise KeyError(f"Timeline '{timeline_id}' not in group '{self.id}'")

        timeline = self._timelines.pop(timeline_id)
        self._remove_timeline_column(timeline_id)

        self._logger.debug(f"Removed timeline '{timeline_id}'")
        return timeline

    def get_timeline(self, timeline_id: str) -> "Timeline":
        """Get a timeline by ID.

        Args:
            timeline_id: The timeline's unique identifier.

        Returns:
            The Timeline object.

        Raises:
            KeyError: If no timeline with that ID exists.
        """
        if timeline_id not in self._timelines:
            raise KeyError(f"No timeline '{timeline_id}' in group '{self.id}'")
        return self._timelines[timeline_id]

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

    def get_timestamp(self, index: int) -> GroupTimestamp:
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
        coordinate: float,
        timeline_id: str,
        *,
        relative_to: Literal["group", "original"] = "group",
    ) -> GroupTimestamp:
        """Get a GroupTimestamp at a specific coordinate.

        Interpolates between boundary timestamps to get all timeline
        coordinates at the specified point.

        Args:
            coordinate: The query coordinate.
            timeline_id: Which timeline the coordinate refers to.
            relative_to:
                "group" - coordinate is relative to timeline's 0-origin IN THIS GROUP
                         (default; e.g., "3 seconds into this group")
                "original" - coordinate is relative to timeline's ORIGINAL origin
                            (e.g., "50 seconds in the original timeline")
                            NOTE: Currently not implemented, reserved for future use.

        Returns:
            GroupTimestamp with interpolated coordinates for all timelines.
            Timelines not commensurable at this point have None.

        Raises:
            KeyError: If timeline_id is not in the group.
            ValueError: If coordinate is outside the timeline's range in the group.

        Examples:
            >>> ts = group.get_timestamp_at(75.0, "audio:1")
            >>> ts["dgt1:1"]
            2437.5
            >>> ts["score:1"]
            33.33...
        """
        if timeline_id not in self._timelines:
            raise KeyError(f"Timeline '{timeline_id}' not in group")

        if self._timestamp_table is None:
            raise ValueError(f"Group '{self.id}' has no timestamps")

        # Adjust for original-relative mode (future extension)
        if relative_to == "original":
            # TODO: Implement offset tracking for original coordinates
            # For now, treat as group-relative
            pass

        # Get column for this timeline
        col = self._timestamp_table.column(timeline_id).to_pylist()

        # Find bounding rows
        low_idx = None
        high_idx = None
        for i, val in enumerate(col):
            if val is not None:
                if val <= coordinate:
                    low_idx = i
                if val >= coordinate and high_idx is None:
                    high_idx = i
                    break

        if low_idx is None or high_idx is None:
            raise ValueError(
                f"Coordinate {coordinate} outside range for '{timeline_id}'"
            )

        # Exact match at a boundary
        if low_idx == high_idx:
            return self._row_to_timestamp(low_idx)

        # Interpolate all columns
        ratio = (coordinate - col[low_idx]) / (col[high_idx] - col[low_idx])

        coords: dict[str, float | None] = {}
        for col_name in self._timestamp_table.column_names:
            col_data = self._timestamp_table.column(col_name).to_pylist()
            low_val = col_data[low_idx]
            high_val = col_data[high_idx]

            if low_val is None or high_val is None:
                coords[col_name] = None
            else:
                coords[col_name] = low_val + ratio * (high_val - low_val)

        return GroupTimestamp(coordinates=coords, row_index=-1)  # -1 = interpolated

    def get_timestamp_table(
        self,
        timeline_filter: set[str] | None = None,
    ) -> pa.Table:
        """Get the timestamp table (or a filtered subset).

        Args:
            timeline_filter: Only include these timeline columns.

        Returns:
            pa.Table with one row per timestamp, one column per timeline.
            Returns empty table if group has no timestamps.
        """
        if self._timestamp_table is None:
            return pa.table({})
        if timeline_filter is None:
            return self._timestamp_table
        cols = [c for c in self._timestamp_table.column_names if c in timeline_filter]
        return self._timestamp_table.select(cols)

    def get_timestamps_df(
        self,
        timeline_filter: set[str] | None = None,
    ) -> pd.DataFrame:
        """Convenience wrapper returning pandas DataFrame.

        Args:
            timeline_filter: Only include these timeline columns.

        Returns:
            pandas DataFrame with timestamp data.
        """
        return self.get_timestamp_table(timeline_filter=timeline_filter).to_pandas()

    def _row_to_timestamp(self, index: int) -> GroupTimestamp:
        """Convert a table row to a GroupTimestamp view object.

        Args:
            index: Row index in the timestamp table.

        Returns:
            GroupTimestamp with coordinates from that row.
        """
        if self._timestamp_table is None:
            raise ValueError("No timestamp table")

        row = self._timestamp_table.slice(index, 1)
        coords: dict[str, float | None] = {}
        for col_name in row.column_names:
            val = row.column(col_name)[0].as_py()
            coords[col_name] = val  # None if null
        return GroupTimestamp(coordinates=coords, row_index=index)

    # endregion

    # region Coordinate Conversion

    def convert(
        self,
        coordinate: float,
        source: str,
        target: str,
        *,
        relative_to: Literal["group", "original"] = "group",
    ) -> float | None:
        """Convert a coordinate from one timeline to another.

        This is a convenience method that gets the timestamp at the source
        coordinate and returns the target timeline's coordinate from it.

        Args:
            coordinate: The coordinate value to convert.
            source: Source timeline ID.
            target: Target timeline ID.
            relative_to:
                "group" - coordinate is relative to timeline's 0-origin IN THIS GROUP
                "original" - coordinate is relative to timeline's ORIGINAL origin

        Returns:
            The converted coordinate, or None if target timeline is not
            present at this coordinate.

        Raises:
            KeyError: If source or target timeline is not in the group.
            ValueError: If coordinate is outside the source timeline's range.

        Examples:
            >>> group.convert(75.0, source="audio:1", target="dgt1:1")
            2437.5
        """
        ts = self.get_timestamp_at(coordinate, source, relative_to=relative_to)
        return ts[target]

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

        col = self._timestamp_table.column(timeline_id).to_pylist()

        # Find first and last non-null values
        start_val = None
        end_val = None
        for val in col:
            if val is not None:
                if start_val is None:
                    start_val = val
                end_val = val

        if start_val is None or end_val is None:
            return None

        return (start_val, end_val)

    # endregion

    # region Internal Methods - Boundary Resolution

    def _resolve_boundary(
        self,
        spec: GroupTimestamp | tuple[float, str] | float | None,
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

        # (coordinate, timeline_id): find or create
        if isinstance(spec, tuple):
            coord, tl_id = spec
            return self._find_or_create_at(float(coord), tl_id, new_timeline, is_start)

        # float: need existing timelines to determine context
        if isinstance(spec, (int, float)):
            # If only one timeline exists, use that for context
            if len(self._timelines) == 1:
                tl_id = next(iter(self._timelines.keys()))
                return self._find_or_create_at(
                    float(spec), tl_id, new_timeline, is_start
                )
            else:
                raise ValueError(
                    f"Ambiguous boundary specification: {spec}. "
                    f"Multiple timelines exist. Use (coordinate, timeline_id) form."
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
            raise KeyError(f"Timeline '{timeline_id}' not in group")

        if self._timestamp_table is None:
            raise ValueError("Cannot find timestamp in empty group")

        # Check if coordinate matches an existing timestamp exactly
        col = self._timestamp_table.column(timeline_id).to_pylist()
        for i, val in enumerate(col):
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
        for i, val in enumerate(col):
            if val is not None:
                if val <= coord:
                    low_idx = i
                if val >= coord and high_idx is None:
                    high_idx = i
                    break

        if low_idx is None or high_idx is None:
            raise ValueError(
                f"Coordinate {coord} is outside range for timeline '{timeline_id}'"
            )

        # Interpolate to get coordinates for all existing timelines
        ratio = (coord - col[low_idx]) / (col[high_idx] - col[low_idx])

        new_row_coords: dict[str, float | None] = {}
        for col_name in self._timestamp_table.column_names:
            col_data = self._timestamp_table.column(col_name).to_pylist()
            low_val = col_data[low_idx]
            high_val = col_data[high_idx]

            if low_val is not None and high_val is not None:
                if col_name == timeline_id:
                    # Use the exact specified coordinate for the source timeline
                    # to avoid floating-point errors from interpolation round-trip
                    new_row_coords[col_name] = coord
                else:
                    new_row_coords[col_name] = low_val + ratio * (high_val - low_val)
            else:
                new_row_coords[col_name] = None

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
            self._timestamp_table = pa.table(
                {
                    timeline.id: pa.array(
                        [
                            start_spec["new_timeline_coord"],
                            end_spec["new_timeline_coord"],
                        ],
                        type=pa.float64(),
                    )
                }
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

        # Build new column with interpolated values
        n_rows = self.n_timestamps
        new_col: list[float | None] = []

        for i in range(n_rows):
            if i < start_idx or i > end_idx:
                new_col.append(None)
            elif i == start_idx:
                new_col.append(start_spec["new_timeline_coord"])
            elif i == end_idx:
                new_col.append(end_spec["new_timeline_coord"])
            else:
                # Interpolate
                ratio = (i - start_idx) / (end_idx - start_idx)
                coord = start_spec["new_timeline_coord"] + ratio * (
                    end_spec["new_timeline_coord"] - start_spec["new_timeline_coord"]
                )
                new_col.append(coord)

        # Add column
        self._timestamp_table = self._timestamp_table.append_column(
            timeline.id, pa.array(new_col, type=pa.float64())
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
        new_row_data: dict[str, list[float | None]] = {}
        for col_name in self._timestamp_table.column_names:
            new_row_data[col_name] = [coordinates.get(col_name)]

        new_row_table = pa.table(
            {k: pa.array(v, type=pa.float64()) for k, v in new_row_data.items()}
        )

        # Split existing table and concatenate
        before = self._timestamp_table.slice(0, insert_index)
        after = self._timestamp_table.slice(insert_index)

        self._timestamp_table = pa.concat_tables([before, new_row_table, after])

    def _remove_timeline_column(self, timeline_id: str) -> None:
        """Remove a timeline's column from the timestamp table.

        Also removes any rows that become all-null after removal.

        Args:
            timeline_id: The timeline ID (column name) to remove.
        """
        if self._timestamp_table is None:
            return

        # Get column names except the one to remove
        remaining_cols = [
            c for c in self._timestamp_table.column_names if c != timeline_id
        ]

        if not remaining_cols:
            # No columns left
            self._timestamp_table = None
            return

        # Select remaining columns
        self._timestamp_table = self._timestamp_table.select(remaining_cols)

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
            for col_name in row.column_names:
                val = row.column(col_name)[0].as_py()
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

    # endregion

    # region Compatibility Methods (Deprecated)

    @classmethod
    def from_reference(
        cls,
        reference: "Timeline",
        uid: str | None = None,
        name: str | None = None,
    ) -> "TimelineGroup":
        """Create a new group with a reference timeline.

        DEPRECATED: Use TimelineGroup(id=..., timelines=[reference]) instead.

        Args:
            reference: The timeline to use as reference.
            uid: Optional explicit ID.
            name: Optional human-readable name.

        Returns:
            A new TimelineGroup containing only the reference timeline.
        """
        warnings.warn(
            "TimelineGroup.from_reference() is deprecated. "
            "Use TimelineGroup(id=..., timelines=[timeline]) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return cls(id=uid, name=name, timelines=[reference])

    @property
    def reference_timeline_id(self) -> str | None:
        """ID of the first timeline added (for compatibility).

        DEPRECATED: The new architecture does not have a reference timeline concept.
        """
        if self._timelines:
            return next(iter(self._timelines.keys()))
        return None

    @property
    def reference(self) -> "Timeline | None":
        """The first timeline added (for compatibility).

        DEPRECATED: The new architecture does not have a reference timeline concept.
        """
        if self._timelines:
            return next(iter(self._timelines.values()))
        return None

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


# endregion
