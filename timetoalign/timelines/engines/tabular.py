"""Provide timestamp and tabular export operations for timeline instances."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from fractions import Fraction
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc

from timetoalign.core import (
    Coordinate,
    CoordinateSpec,
    IdCoordinate,
    NumberType,
    TimeUnit,
    resolve_coordinate_spec,
)
from timetoalign.core.timestamp import (
    ConversionMapsSpec,
    TimeIntervalStamp,
    TimeStamp,
)
from timetoalign.maps import ConversionMap

if TYPE_CHECKING:
    from timetoalign.core.enums import ColumnNaming


class TabularExportMixin:
    """Provide timestamp and tabular export operations for timeline instances."""

    def get_timestamp(
        self,
        coord: CoordinateSpec,
        unit: TimeUnit | str | None = None,
        *,
        conversion_maps: ConversionMapsSpec = True,
    ) -> TimeStamp:
        """Get a TimeStamp at a specific coordinate.

        This is the primary coordinate resolution API. The TimeStamp provides
        access to all equivalent coordinates across children and C-Map units.

        Uses InterpolationMaps for O(log n) coordinate conversion.

        Args:
            coord: Coordinate value. Can be:
                - int/float/Fraction: Value in timeline's native unit
                - Coordinate: Must match unit or specify via `unit` param
            unit: If provided, interpret coord as being in this unit.
                The coordinate is first converted via inverse C-Map.
            conversion_maps: C-Maps available through the returned stamp.

        Returns:
            TimeStamp object for the resolved coordinate.

        Raises:
            ValueError: If unit specified but no inverse C-Map available.

        Examples:
            >>> ts = timeline.get_timestamp(5.0)
            >>> ts["child_a"]  # Get coordinate on child_a
            2.5

            >>> # Query with unit conversion
            >>> ts = timeline.get_timestamp(10.5, unit=TimeUnit.seconds)
            >>> ts.axis  # Converted from seconds to timeline's unit
            5.0
        """
        if unit is None:
            native_coord = self.get_coordinate(coord)
        else:
            target_unit = TimeUnit(unit) if isinstance(unit, str) else unit
            decomposed = resolve_coordinate_spec(coord)
            if decomposed.timeline_id is None:
                qualified_coord: CoordinateSpec = Coordinate(
                    decomposed.value, target_unit
                )
            else:
                qualified_coord = IdCoordinate(
                    decomposed.value,
                    target_unit,
                    decomposed.timeline_id,
                )
            native_coord = self.get_coordinate(qualified_coord)

        return TimeStamp(
            axis=float(native_coord.value),
            source=self,
            source_id=self._id,
            conversion_maps=conversion_maps,
        )

    def get_timestamp_at(
        self,
        coord: CoordinateSpec,
        unit: TimeUnit | str | None = None,
        *,
        conversion_maps: ConversionMapsSpec = True,
    ) -> TimeStamp:
        """Alias for `get_timestamp()` for API consistency with TimelineGroup.

        TimelineGroup uses `get_timestamp_at(coord, tl_id)` with an additional
        timeline_id parameter. This alias provides a consistent verb across
        the hierarchy.

        Args:
            coord: Coordinate value (see `get_timestamp()` for details).
            unit: Optional unit for coordinate interpretation.
            conversion_maps: C-Maps available through the returned stamp.

        Returns:
            TimeStamp object for the resolved coordinate.

        See Also:
            get_timestamp: The primary coordinate resolution method.
            timetoalign.TimelineGroup.get_timestamp_at: Group-level version.
        """
        return self.get_timestamp(
            coord,
            unit=unit,
            conversion_maps=conversion_maps,
        )

    def get_interval_stamp(
        self,
        start: CoordinateSpec,
        end: CoordinateSpec,
        unit: TimeUnit | str | None = None,
        *,
        conversion_maps: ConversionMapsSpec = True,
    ) -> TimeIntervalStamp:
        """Get a TimeIntervalStamp for a coordinate range.

        Args:
            start: Start coordinate.
            end: End coordinate.
            unit: If provided, interpret both coords as being in this unit.
            conversion_maps: C-Maps available through the returned stamps.

        Returns:
            TimeIntervalStamp with start and end TimeStamps.

        Examples:
            >>> interval = timeline.get_interval_stamp(0.0, 10.0)
            >>> interval.duration
            10.0
            >>> interval["child:1"]  # Get (start, end) tuple for child
            (0.0, 7.5)
        """
        return TimeIntervalStamp(
            start=self.get_timestamp(start, unit=unit, conversion_maps=conversion_maps),
            end=self.get_timestamp(end, unit=unit, conversion_maps=conversion_maps),
        )

    def get_timestamp_of(
        self,
        event_id: str,
        *,
        conversion_maps: ConversionMapsSpec = True,
    ) -> TimeStamp | TimeIntervalStamp:
        """Get the timestamp for a specific event by its ID.

        Returns a TimeStamp for instant events, or a TimeIntervalStamp for
        interval events. Searches recursively through children if the event
        is not found on this timeline directly.

        Args:
            event_id: The event identifier to look up.
            conversion_maps: C-Maps available through the returned stamp or stamps.

        Returns:
            TimeStamp for instant events, TimeIntervalStamp for interval events.

        Raises:
            KeyError: If no event with the given ID exists.

        Examples:
            >>> ts = timeline.get_timestamp_of("note:000001")
            >>> ts.axis  # For instant events
            5.0

            >>> ts = timeline.get_timestamp_of("clt1:note:000001")
            >>> ts.start.axis  # For interval events
            0.0
            >>> ts.end.axis
            2.5

        See Also:
            get_timestamp: Get timestamp by coordinate.
            get_event: Get the raw event dict by ID.
        """
        events = self.get_events(include_children=True, id=event_id)
        if len(events) == 0:
            raise KeyError(
                f"Event {event_id!r} not found on timeline {self._id!r} "
                f"({self.n_events} events)"
            )

        start_val = events.column_values("start")[0]
        if start_val is None:
            raise ValueError(f"Event {event_id!r} has no 'start' coordinate")
        start_coord = float(start_val)

        # Check if this is an interval event
        end_val = events.column_values("end")[0]
        if end_val is not None:
            end_coord = float(end_val)
            return self.get_interval_stamp(
                start_coord,
                end_coord,
                conversion_maps=conversion_maps,
            )

        return self.get_timestamp(start_coord, conversion_maps=conversion_maps)

    def get_timestamps_of(
        self,
        event_ids: Sequence[str],
    ) -> pd.DataFrame:
        """Get timestamps for multiple events, returned as a DataFrame.

        For each event, includes fields for start coordinate, end coordinate
        (if interval), event type, and temporal type.

        Args:
            event_ids: Sequence of event identifiers to look up.

        Returns:
            DataFrame indexed by event_id with fields:
            - ``start``: Start coordinate value
            - ``end``: End coordinate value (NaN for instant events)
            - ``event_type``: The event type name
            - ``temporal_type``: "instant" or "interval"

        Raises:
            KeyError: If any event ID is not found.

        Examples:
            >>> df = timeline.get_timestamps_of(["note:000001", "note:000002"])
            >>> df.loc["note:000001", "start"]
            0.0

        See Also:
            get_timestamp_of: Get a single event's timestamp.
            get_events: Filter events by type or coordinate range.
        """
        events = self.get_events(include_children=True)
        ids = events.column_values("id")
        indices = {event_id: index for index, event_id in enumerate(ids)}
        starts = events.column_values("start")
        ends = events.column_values("end")
        event_types = events.column_values("event_type")
        rows = []
        for event_id in event_ids:
            if event_id not in indices:
                raise KeyError(
                    f"Event {event_id!r} not found on timeline {self._id!r} "
                    f"({self.n_events} events)"
                )

            index = indices[event_id]
            start_val = starts[index]
            if start_val is None:
                raise ValueError(f"Event {event_id!r} has no 'start' coordinate")
            start = float(start_val)

            end_val = ends[index]
            if end_val is not None:
                end = float(end_val)
                temporal_type = "interval"
            else:
                end = float("nan")
                temporal_type = "instant"

            rows.append(
                {
                    "event_id": event_id,
                    "start": start,
                    "end": end,
                    "event_type": event_types[index] or "",
                    "temporal_type": temporal_type,
                }
            )

        df = pd.DataFrame(rows)
        if len(df) > 0:
            df = df.set_index("event_id")
        return df

    def _extract_event_coordinates(
        self,
        event_filter: dict[str, Any] | pc.Expression | None = None,
    ) -> pa.ChunkedArray:
        """Extract all unique event coordinates as a sorted PyArrow array.

                Uses PyArrow compute to efficiently extract coordinates from the
                EventData table without Python iteration.

                Args:
                    event_filter: Optional filter to apply before extracting coordinates.
        Can be a dict (passed to EventData.filter()) or a pc.Expression
                        (passed to EventData.where()).

                Returns:
                    Sorted PyArrow ChunkedArray of unique coordinate values (float64).
                    Returns empty array if no events.

                Notes:
                    - Extracts start.value from all events
                    - Extracts end.value from interval events (drops nulls)
                    - Deduplicates and sorts the result
        """
        # Apply filter if provided
        if event_filter is not None:
            if isinstance(event_filter, pc.Expression):
                filtered_store = self._events.where(event_filter)
            else:
                filtered_store = self._events.filter(**event_filter)
            table = filtered_store.table
        else:
            table = self._events.table

        if table.num_rows == 0:
            return pa.chunked_array([], type=pa.float64())

        # Extract start coordinates (all events have start)
        # struct_field returns ChunkedArray
        start_arr = table.column("start")
        start_vals = pc.struct_field(start_arr, "value")

        # Extract end coordinates (intervals only, filter nulls)
        end_arr = table.column("end")
        end_vals = pc.struct_field(end_arr, "value")
        end_vals = pc.drop_null(end_vals)

        # Combine chunks from both ChunkedArrays
        all_chunks = start_vals.chunks + end_vals.chunks
        if not all_chunks:
            return pa.chunked_array([], type=pa.float64())

        combined = pa.chunked_array(all_chunks, type=pa.float64())

        # Deduplicate
        unique_coords = pc.unique(combined)

        # Sort ascending
        sort_indices = pc.sort_indices(unique_coords)
        sorted_coords = pc.take(unique_coords, sort_indices)

        return sorted_coords

    def _collect_all_coordinates(
        self,
        recursion_limit: int | None = None,
        offset: float = 0.0,
        event_filter: dict[str, Any] | pc.Expression | None = None,
    ) -> pa.Array:
        """Collect coordinates from this timeline and all children.

        Recursively collects event coordinates, applying cumulative offset
        to convert to root-relative coordinates.

        Args:
            recursion_limit: Maximum depth for child traversal. None = unlimited.
            offset: Cumulative offset from root timeline (internal use).
            event_filter: Optional filter applied to each timeline's events.
                Can be a dict (passed to EventData.filter()) or a pc.Expression
                (passed to EventData.where()). The same filter is applied to
                all timelines in the hierarchy.

        Returns:
            PyArrow array of unique, sorted, root-relative coordinates (float64).
        """
        # Get this timeline's coordinates (with optional filter)
        local_coords = self._extract_event_coordinates(event_filter)

        # Apply offset to make root-relative
        if offset != 0.0 and len(local_coords) > 0:
            local_coords = pc.add(local_coords, offset)

        arrays = [local_coords]

        # Recurse into children
        if recursion_limit is None or recursion_limit > 0:
            next_limit = None if recursion_limit is None else recursion_limit - 1
            for child_id, child in self._children.items():
                child_offset = self._child_offsets[child_id].value
                child_coords = child._collect_all_coordinates(
                    recursion_limit=next_limit,
                    offset=offset + child_offset,
                    event_filter=event_filter,
                )
                if len(child_coords) > 0:
                    arrays.append(child_coords)

        # Combine all and deduplicate
        if len(arrays) == 1:
            return arrays[0]

        # Filter out empty arrays before concatenation
        non_empty = [a for a in arrays if len(a) > 0]
        if not non_empty:
            return pa.array([], type=pa.float64())

        combined = pa.concat_arrays(non_empty)
        unique = pc.unique(combined)

        # Sort ascending
        sort_indices = pc.sort_indices(unique)
        return pc.take(unique, sort_indices)

    def _collect_boundary_coordinates(
        self,
        recursion_limit: int | None = None,
        offset: float = 0.0,
    ) -> pa.Array:
        """Collect timeline boundary coordinates (start=0, end=length).

        Recursively collects boundary coordinates from this timeline
        and all children, applying cumulative offsets.

        Args:
            recursion_limit: Maximum depth for child traversal. None = unlimited.
            offset: Cumulative offset from root timeline (internal use).

        Returns:
            PyArrow array of unique, sorted, root-relative boundary coordinates.
        """
        # This timeline's boundaries
        boundaries = [offset, offset + self._length.value]
        arrays = [pa.array(boundaries, type=pa.float64())]

        # Recurse into children
        if recursion_limit is None or recursion_limit > 0:
            next_limit = None if recursion_limit is None else recursion_limit - 1
            for child_id, child in self._children.items():
                child_offset = self._child_offsets[child_id].value
                child_bounds = child._collect_boundary_coordinates(
                    recursion_limit=next_limit,
                    offset=offset + child_offset,
                )
                if len(child_bounds) > 0:
                    arrays.append(child_bounds)

        # Combine and deduplicate
        if len(arrays) == 1:
            return arrays[0]

        combined = pa.concat_arrays(arrays)
        unique = pc.unique(combined)
        sort_indices = pc.sort_indices(unique)
        return pc.take(unique, sort_indices)

    def _compute_local_coordinates(
        self,
        root_coords: pa.Array,
        offset: float = 0.0,
    ) -> pa.Array:
        """Compute local coordinates from root coordinates.

        Vectorized offset subtraction with bounds checking. Coordinates
        outside [0, length] are replaced with null.

        Args:
            root_coords: Array of root-relative coordinates.
            offset: This timeline's offset from root.

        Returns:
            PyArrow array with local coordinates, null for out-of-bounds.
        """
        if len(root_coords) == 0:
            return pa.array([], type=pa.float64())

        # Subtract offset: local = root - offset
        local = pc.subtract(root_coords, offset)

        # Create mask for out-of-bounds coordinates. The length scalar must
        # reach the kernel as a float: on a quarters/beats axis its value is a
        # Fraction, which the PyArrow compute kernel rejects.
        too_low = pc.less(local, 0.0)
        too_high = pc.greater(local, float(self._length.value))
        out_of_bounds = pc.or_(too_low, too_high)

        # Replace out-of-bounds with null
        null_scalar = pa.scalar(None, type=pa.float64())
        return pc.if_else(out_of_bounds, null_scalar, local)

    def _resolve_conversion_maps(
        self, spec: ConversionMapsSpec
    ) -> list[ConversionMap[Any]]:
        """Resolve a flexible conversion_maps specification to a list of C-Maps.

        Supports multiple input formats for convenience:
        - True: Return all attached conversion maps
        - False/None: Return empty list
        - str: Look up by map ID, or find map by target unit name
        - TimeUnit: Find map by target unit
        - ConversionMap: Return as single-element list
        - Iterable: Resolve each element recursively

        Args:
            spec: Flexible specification for which C-Maps to include.

        Returns:
            List of resolved ConversionMap objects.

        Raises:
            KeyError: If a string ID doesn't match any attached map.
            ValueError: If a TimeUnit doesn't match any attached map's target.

        Examples:
            >>> tl._resolve_conversion_maps(True)  # All maps
            >>> tl._resolve_conversion_maps("inches")  # Single map by ID/unit
            >>> tl._resolve_conversion_maps(["inches", "cm"])  # Multiple
            >>> tl._resolve_conversion_maps(TimeUnit.seconds)  # By unit enum
        """
        if spec is None or spec is False:
            return []

        if spec is True:
            # Return all attached conversion maps
            return list(self._conversion_maps.values())

        # Single string: could be map ID or target unit name
        if isinstance(spec, str):
            # First try exact ID match
            if spec in self._conversion_maps:
                return [self._conversion_maps[spec]]
            # Try as target unit name
            try:
                unit = TimeUnit(spec)
                cmap = self.get_conversion_map(unit)
                if cmap is not None:
                    return [cmap]
            except ValueError:
                pass
            raise KeyError(
                f"No conversion map with ID '{spec}' or target unit '{spec}'. "
                f"Available: {list(self._conversion_maps.keys())}"
            )

        # TimeUnit: find by target unit
        if isinstance(spec, TimeUnit):
            cmap = self.get_conversion_map(spec)
            if cmap is not None:
                return [cmap]
            raise ValueError(
                f"No conversion map with target unit '{spec}'. "
                f"Available: {list(self._conversion_maps.keys())}"
            )

        # Single ConversionMap object
        if isinstance(spec, ConversionMap):
            return [spec]

        # Iterable: resolve each element
        resolved: list[ConversionMap[Any]] = []
        for item in spec:
            resolved.extend(self._resolve_conversion_maps(item))
        return resolved

    def _build_timestamp_table(
        self,
        axis: pa.Array,
        conversion_maps: list[ConversionMap[Any]] | None = None,
        recursion_limit: int | None = None,
    ) -> pa.Table:
        """Build a timestamp table from axis coordinates.

        Constructs a PyArrow table with:
        - axis: Root coordinate values
        - One field per timeline (root + children) with local coordinates
        - One field per C-Map with converted values

        Each field includes metadata:
        - unit: The TimeUnit for this field's coordinates
        - timeline_id: The timeline ID (for timeline fields)
        - cmap_id: The C-Map ID (for C-Map fields)

        Args:
            axis: Array of root-relative coordinates (the timestamp axis).
            conversion_maps: Optional list of C-Maps to include as fields.
            recursion_limit: Maximum depth for child traversal. None = unlimited.

        Returns:
            PyArrow table with timestamp data and field-level unit metadata.
        """
        field_arrs: dict[str, pa.Array] = {}
        fields: list[pa.Field] = []

        # Helper to get PyArrow type from NumberType
        def _get_pa_type(number_type: NumberType) -> pa.DataType:
            """Map NumberType to PyArrow type: int -> int64, else float64."""
            return pa.int64() if number_type == NumberType.int else pa.float64()

        # Add axis field (root timeline coordinate)
        axis_pa_type = _get_pa_type(self._number_type)
        field_arrs["axis"] = axis
        fields.append(
            pa.field(
                "axis",
                axis_pa_type,
                metadata={
                    b"unit": self._unit.value.encode("utf-8"),
                    b"timeline_id": self._id.encode("utf-8"),
                },
            )
        )

        # Add root timeline field (offset=0)
        field_arrs[self._id] = self._compute_local_coordinates(axis, offset=0.0)
        fields.append(
            pa.field(
                self._id,
                axis_pa_type,
                metadata={
                    b"unit": self._unit.value.encode("utf-8"),
                    b"timeline_id": self._id.encode("utf-8"),
                },
            )
        )

        # Add child fields recursively
        for child_offset, child in self.iter_children(
            recursion_limit=recursion_limit,
            include_self=False,
        ):
            child_pa_type = _get_pa_type(child.number_type)
            field_arrs[child.id] = child._compute_local_coordinates(
                axis, offset=float(child_offset.value)
            )
            fields.append(
                pa.field(
                    child.id,
                    child_pa_type,
                    metadata={
                        b"unit": child.unit.value.encode("utf-8"),
                        b"timeline_id": child.id.encode("utf-8"),
                    },
                )
            )

        # Add C-Map fields
        # C-Maps work on NumPy arrays; we convert PyArrow <-> NumPy at the boundary.
        if conversion_maps:
            # Allow copy for arrays with nulls (zero_copy_only=False)
            axis_np = axis.to_numpy(zero_copy_only=False)
            for cmap in conversion_maps:
                converted = cmap.convert_array(axis_np)
                # Use map's name property for human-readable field header
                col_name = cmap.name
                field_arrs[col_name] = pa.array(converted)
                # C-Map fields include target unit from the C-Map
                target_unit = getattr(cmap, "target_unit", None)
                unit_value = target_unit.value if target_unit else "unknown"
                fields.append(
                    pa.field(
                        col_name,
                        pa.float64(),
                        metadata={
                            b"unit": unit_value.encode("utf-8"),
                            b"cmap_id": cmap.id.encode("utf-8"),
                        },
                    )
                )

        # Build table with explicit schema to preserve metadata
        schema = pa.schema(fields)
        return pa.table(field_arrs, schema=schema)

    def _resolve_coordinate_spec(
        self,
        coordinates: CoordinateSpec | Sequence[CoordinateSpec],
    ) -> pa.Array:
        """Resolve CoordinateSpec to axis coordinates.

        Handles IdCoordinate objects by automatically applying child offsets.
        This enables the dead-simple pattern:

            child_coords = [IdCoordinate(v, unit, "child_id") for v in values]
            df = parent.to_dataframe(coordinates=child_coords)

        When an IdCoordinate's timeline_id matches a child of this timeline,
        the coordinate is automatically converted to parent coordinates by
        adding the child's offset.

        Args:
            coordinates: Single CoordinateSpec or sequence of CoordinateSpec.
                - int/float/Fraction: Used directly as axis coordinate
                - Coordinate: Value extracted
                - IdCoordinate: Child offset applied if timeline_id matches a child
                - Sequence of the above: Each element processed individually

        Returns:
            PyArrow array of float64 axis coordinates.

        Examples:
            >>> # IdCoordinate from child timeline - offset auto-applied
            >>> child_coord = IdCoordinate(1000.0, TimeUnit.pixels, "dgt_holes")
            >>> axis = parent._resolve_coordinate_spec([child_coord])
            >>> # axis[0] == 1000.0 + child_offset
        """

        # Fast path: PyArrow array or numpy array of plain floats
        if isinstance(coordinates, pa.Array):
            return coordinates.cast(pa.float64())
        if isinstance(coordinates, np.ndarray):
            return pa.array(coordinates.astype(np.float64))

        # Single coordinate specification
        if isinstance(coordinates, (int, float, Fraction, Coordinate, IdCoordinate)):
            coordinates = [coordinates]

        # Process list of coordinates
        resolved: list[float] = []
        for coord in coordinates:
            resolve_coordinate_spec(coord)
            resolved.append(float(self._resolve_axis_value(coord)))

        return pa.array(resolved, type=pa.float64())

    def get_timestamp_table(
        self,
        coordinates: CoordinateSpec | Sequence[CoordinateSpec] | None = None,
        conversion_maps: ConversionMapsSpec = True,
        recursion_limit: int | None = None,
        include_events: bool = True,
        include_boundaries: bool = False,
    ) -> pa.Table:
        """Generate a timestamp table as a PyArrow Table.

        A Timestamp is a cross-section through the timeline hierarchy showing
        synchronous coordinates. This method computes local coordinates for
        each timeline in the hierarchy at each axis coordinate.

        Supports IdCoordinate for automatic child offset resolution:

            >>> # IdCoordinates from child timeline - offsets auto-applied!
            >>> child_coords = [IdCoordinate(v, unit, "child_id") for v in values]
            >>> df = parent.to_dataframe(coordinates=child_coords)

        Args:
            coordinates: Explicit coordinates to use as the axis. If None,
                coordinates are extracted from events (and optionally boundaries).
                Accepts IdCoordinate objects - if timeline_id matches a child,
                the offset is automatically applied.
            conversion_maps: C-Maps to include as fields. Flexible input:
                - True: Include all attached conversion maps
                - str: Map ID or target unit name (e.g., "inches", "seconds")
                - TimeUnit: Find map by target unit enum
                - ConversionMap: Include the specific map
                - list: Mix of the above
                - None/False: No conversion maps
            recursion_limit: Maximum depth for child traversal. None = unlimited.
            include_events: If True and coordinates is None, extract from events.
            include_boundaries: If True, include timeline boundary coordinates.

        Returns:
            PyArrow Table with schema:
                - axis: float64 (root coordinate)
                - {timeline_id}: float64 (nullable, local coordinate per timeline)
                - {cmap_id}: varies (converted value per C-Map)

            Each field includes metadata:
                - unit: TimeUnit.value string (e.g., "seconds", "pixels")
                - timeline_id: Timeline ID (for timeline fields)
                - cmap_id: C-Map ID (for C-Map fields)

            Access metadata via: ``table.schema.field(col_name).metadata``

        Examples:
            >>> table = timeline.get_timestamp_table()
            >>> table.column_names
            ['axis', 'tl:1', 'notes', 'measures']

            >>> # Include all attached C-Maps
            >>> table = timeline.get_timestamp_table(conversion_maps=True)

            >>> # Include specific C-Maps by target unit
            >>> table = timeline.get_timestamp_table(conversion_maps=["inches", "cm"])

            >>> # Access unit metadata
            >>> table.schema.field('axis').metadata[b'unit']
            b'seconds'
        """
        # Resolve coordinates (handles IdCoordinate with auto child offset)
        if coordinates is not None:
            axis = self._resolve_coordinate_spec(coordinates)
        elif include_events:
            # Extract from events
            event_coords = self._collect_all_coordinates(
                recursion_limit=recursion_limit
            )
            if include_boundaries:
                boundary_coords = self._collect_boundary_coordinates(
                    recursion_limit=recursion_limit
                )
                if len(event_coords) > 0 and len(boundary_coords) > 0:
                    combined = pa.concat_arrays([event_coords, boundary_coords])
                    unique = pc.unique(combined)
                    sort_indices = pc.sort_indices(unique)
                    axis = pc.take(unique, sort_indices)
                elif len(boundary_coords) > 0:
                    axis = boundary_coords
                else:
                    axis = event_coords
            else:
                axis = event_coords
        else:
            # Boundaries only
            axis = self._collect_boundary_coordinates(recursion_limit=recursion_limit)

        # Resolve C-Map references using flexible helper
        resolved_maps = self._resolve_conversion_maps(conversion_maps)

        return self._build_timestamp_table(
            axis=axis,
            conversion_maps=resolved_maps if resolved_maps else None,
            recursion_limit=recursion_limit,
        )

    def to_dataframe(
        self,
        coordinates: CoordinateSpec | Sequence[CoordinateSpec] | None = None,
        conversion_maps: ConversionMapsSpec = True,
        recursion_limit: int | None = None,
        include_events: bool = True,
        include_boundaries: bool = False,
        *,
        fields: "ColumnNaming | Callable[[str, dict], str] | list[str] | None" = None,
        units: bool = True,
        format: str = "pandas",
        include_ids: bool = True,
        as_fractions: bool | None = None,
    ) -> pd.DataFrame:
        """Generate timestamps as a pandas DataFrame with formatted field names.

        This is the recommended high-level method for getting timestamp data.
        It builds on get_timestamp_table() and applies field formatting.

        Args:
            coordinates: Explicit coordinates to use as the axis.
            conversion_maps: C-Maps to include as additional fields. Defaults to True (all).
            recursion_limit: Maximum depth for child traversal.
            include_events: If True and coordinates is None, extract from events.
            include_boundaries: If True, include timeline boundary coordinates.
            fields: How to name the DataFrame fields. Options:
                - None or ColumnNaming.name (default): Use timeline/cmap name
                - ColumnNaming.id: Use timeline/cmap id
                - Callable: Function taking (name, metadata_dict) -> new_name
                - list[str]: Explicit field names
            units: If True (default), append units to field names like "name (unit)".
            format: Output format. Currently only "pandas" is supported.
            include_ids: If True (default), add event IDs as the DataFrame index
                when coordinates are collected from events.
            as_fractions: If True, render float coordinate fields as Fraction
                objects. If None, enable this for fraction-based timelines.

        Returns:
            pandas DataFrame with:
            - Fields named according to the ``fields`` parameter
            - Units appended if ``units=True``
            - Integer fields using pandas nullable Int64 dtype

        Examples:
            >>> df = timeline.to_dataframe()
            >>> df.columns
            Index(['axis (pixels)', 'dgt1 (pixels)', 'pixels_to_inches (inches)'])

            >>> # Without units in field names
            >>> df = timeline.to_dataframe(units=False)
            >>> df.columns
            Index(['axis', 'dgt1', 'pixels_to_inches'])
        """
        from timetoalign.core.timestamp import timestamp_table_to_dataframe

        table = self.get_timestamp_table(
            coordinates=coordinates,
            conversion_maps=conversion_maps,
            recursion_limit=recursion_limit,
            include_events=include_events,
            include_boundaries=include_boundaries,
        )
        df = timestamp_table_to_dataframe(
            table=table,
            fields=fields,
            units=units,
            format=format,
        )

        use_fractions = as_fractions
        if use_fractions is None:
            use_fractions = self._number_type == NumberType.fraction
        if use_fractions:
            for name in df.columns:
                if df[name].dtype not in (float, "float64", "Float64"):
                    continue
                df[name] = df[name].apply(
                    lambda x: (
                        Fraction(x).limit_denominator(10000) if pd.notna(x) else None
                    )
                )

        if include_ids and include_events and coordinates is None:
            all_events = self.get_events(include_children=True)
            coord_to_ids: dict[float, str] = {}
            for event_id, start in zip(
                all_events.column_values("id"),
                all_events.column_values("start"),
                strict=True,
            ):
                if start is None:
                    continue
                coord_val = float(start)
                if coord_val not in coord_to_ids:
                    coord_to_ids[coord_val] = event_id or ""

            axis_name = df.columns[0]
            ids = []
            for value in df[axis_name]:
                float_value = float(value) if value is not None else None
                ids.append(coord_to_ids.get(float_value, ""))
            df.index = ids
            df.index.name = "id"

        return df

    def get_boundary_table(
        self,
        conversion_maps: ConversionMapsSpec = True,
        recursion_limit: int | None = None,
    ) -> pa.Table:
        """Get timestamps for timeline boundaries only.

        Returns a timestamp table containing only start (0) and end (length)
        coordinates for this timeline and all children.

        Args:
            conversion_maps: C-Maps to include as fields (see get_timestamp_table).
            recursion_limit: Maximum depth for child traversal.

        Returns:
            PyArrow Table with boundary timestamps.

        Examples:
            >>> table = timeline.get_boundary_table()
            >>> table.to_pandas()
               axis  tl:1  child:1
            0   0.0   0.0      NaN
            1  10.0  10.0     10.0
            2  50.0   NaN      0.0
            3  60.0   NaN     10.0
        """
        return self.get_timestamp_table(
            coordinates=self._collect_boundary_coordinates(
                recursion_limit=recursion_limit
            ),
            conversion_maps=conversion_maps,
            recursion_limit=recursion_limit,
            include_events=False,
            include_boundaries=False,  # Already included in coordinates
        )

    def export_to_csv(
        self,
        filepath: str,
        coordinates: CoordinateSpec | Sequence[CoordinateSpec] | None = None,
        conversion_maps: ConversionMapsSpec = True,
        recursion_limit: int | None = None,
        include_events: bool = True,
        include_boundaries: bool = False,
        *,
        fields: "ColumnNaming | Callable[[str, dict], str] | list[str] | None" = None,
        units: bool = True,
        sep: str = ",",
        header: bool = True,
        index: bool = False,
    ) -> int:
        """Export timeline data to a CSV file.

        This is a convenience method that generates a timestamp DataFrame and
        writes it to a CSV file. For more control over the output, use
        to_dataframe() and save manually.

        Args:
            filepath: Output CSV file path.
            coordinates: Explicit coordinates to use as the axis.
            conversion_maps: C-Maps to include as additional fields. Defaults to True (all).
            recursion_limit: Maximum depth for child traversal.
            include_events: If True and coordinates is None, extract from events.
            include_boundaries: If True, include timeline boundary coordinates.
            fields: How to name the DataFrame fields (see to_dataframe).
            units: If True (default), append units to field names.
            sep: Field separator. Default "," (comma).
            header: If True (default), write field headers.
            index: If True, write row indices. Default False.

        Returns:
            Number of rows written.

        Examples:
            >>> timeline.export_to_csv("timestamps.csv")
            100

            >>> # Tab-separated, no header
            >>> timeline.export_to_csv("data.tsv", sep="\\t", header=False)
            100
        """
        df = self.to_dataframe(
            coordinates=coordinates,
            conversion_maps=conversion_maps,
            recursion_limit=recursion_limit,
            include_events=include_events,
            include_boundaries=include_boundaries,
            fields=fields,
            units=units,
        )
        df.to_csv(filepath, sep=sep, header=header, index=index)
        return len(df)
