"""EventStore: PyArrow-based bulk event storage for TimeToAlign!

This module provides the EventStore class which stores events in a PyArrow table
with efficient columnar operations. Events are NOT wrapped in Python objects -
they are rows in the table.

Design principles:
- Bulk operations are the primary API (from_dicts, from_arrays, from_dataframe)
- Schema is fixed per class, with extension points for subclasses
- Coordinates stored with both original precision and float representation
- Unit metadata at column level (all events share same unit)
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from typing_extensions import Self

from timetoalign.core import NumberType, TimeUnit

from .schema import (
    coordinate_to_struct,
    extend_schema,
    get_base_column_names,
    make_base_schema,
    make_table_metadata,
    parse_table_metadata,
)

if TYPE_CHECKING:
    pass


class EventStore:
    """PyArrow-based storage for timeline events.

    EventStore wraps a PyArrow table containing events. Events are rows in the
    table, not Python wrapper objects. The primary API is bulk operations:

    - from_dicts(): Create from list of row dictionaries
    - from_arrays(): Create from column-oriented arrays
    - from_dataframe(): Create from pandas DataFrame

    The schema is fixed at class definition time but can be extended by
    subclasses to add domain-specific columns (e.g., pitch, velocity for notes).

    Attributes:
        table: The underlying PyArrow table.
        unit: The time unit for all coordinates.
        number_type: The number type used for coordinates.

    Examples:
        >>> store = EventStore.from_dicts([
        ...     {"id": "e1", "temporal_type": "instant", "event_type": "Beat",
        ...      "instant": 0.0},
        ...     {"id": "e2", "temporal_type": "interval", "event_type": "Note",
        ...      "start": 0.0, "end": 1.0},
        ... ], unit=TimeUnit.seconds)
        >>> len(store)
        2
    """

    # Class-level schema configuration (subclasses can extend)
    _extra_fields: ClassVar[list[pa.Field]] = []

    def __init__(
        self,
        table: pa.Table,
        unit: TimeUnit,
        number_type: NumberType = NumberType.float,
    ) -> None:
        """Initialize EventStore with an existing table.

        Use class methods (from_dicts, from_arrays, etc.) to create instances.

        Args:
            table: The PyArrow table containing events.
            unit: The time unit for coordinates.
            number_type: The number type for coordinate interpretation.
        """
        self._table = table
        self._unit = unit
        self._number_type = number_type

    # region Class Methods - Schema

    @classmethod
    def schema(cls, unit: TimeUnit) -> pa.Schema:
        """Get the PyArrow schema for this EventStore class.

        Args:
            unit: The time unit for coordinate columns.

        Returns:
            The complete schema including base and extra fields.
        """
        base = make_base_schema(unit)
        if cls._extra_fields:
            return extend_schema(base, cls._extra_fields)
        return base

    @classmethod
    def column_names(cls) -> list[str]:
        """Get the list of column names for this EventStore class.

        Returns:
            List of all column names (base + extra).
        """
        base_names = get_base_column_names()
        extra_names = [f.name for f in cls._extra_fields]
        return base_names + extra_names

    # endregion

    # region Class Methods - Creation

    @classmethod
    def empty(cls, unit: TimeUnit, number_type: NumberType = NumberType.float) -> Self:
        """Create an empty EventStore.

        Args:
            unit: The time unit for coordinates.
            number_type: The number type for coordinates.

        Returns:
            An empty EventStore with the appropriate schema.
        """
        schema = cls.schema(unit)
        metadata = make_table_metadata(unit, number_type, loader_class=cls.__name__)
        schema = schema.with_metadata(metadata)
        table = pa.table({name: [] for name in cls.column_names()}, schema=schema)
        return cls(table, unit, number_type)

    @classmethod
    def from_dicts(
        cls,
        rows: list[dict[str, Any]],
        unit: TimeUnit,
        number_type: NumberType = NumberType.float,
    ) -> Self:
        """Create EventStore from a list of row dictionaries.

        Coordinate values (instant, start, end, duration) are automatically
        converted to the internal struct format.

        Args:
            rows: List of event dictionaries. Each dict should have at minimum:
                - id: unique identifier
                - temporal_type: "instant" or "interval"
                - event_type: class name (e.g., "Note")
                - instant: coordinate (for instant events)
                - start, end: coordinates (for interval events)
            unit: The time unit for coordinates.
            number_type: The number type for coordinates.

        Returns:
            A new EventStore containing the events.

        Examples:
            >>> store = EventStore.from_dicts([
            ...     {"id": "e1", "temporal_type": "instant",
            ...      "event_type": "Beat", "instant": 0},
            ... ], unit=TimeUnit.ticks)
        """
        if not rows:
            return cls.empty(unit, number_type)

        # Convert coordinate values to struct format
        processed_rows = []
        for row in rows:
            processed = dict(row)
            # Handle coordinate columns
            for coord_col in ("instant", "start", "end", "duration"):
                if coord_col in processed and processed[coord_col] is not None:
                    processed[coord_col] = coordinate_to_struct(processed[coord_col])
                elif coord_col not in processed:
                    processed[coord_col] = None
            # Ensure name column exists
            if "name" not in processed:
                processed["name"] = None
            processed_rows.append(processed)

        schema = cls.schema(unit)
        metadata = make_table_metadata(unit, number_type, loader_class=cls.__name__)
        schema = schema.with_metadata(metadata)

        table = pa.Table.from_pylist(processed_rows, schema=schema)
        return cls(table, unit, number_type)

    @classmethod
    def from_arrays(
        cls,
        columns: dict[str, list[Any]],
        unit: TimeUnit,
        number_type: NumberType = NumberType.float,
    ) -> Self:
        """Create EventStore from column-oriented arrays.

        This is the most efficient creation method as it matches PyArrow's
        native columnar format.

        Args:
            columns: Dict mapping column names to lists of values.
                Coordinate columns should contain coordinate values (not structs).
            unit: The time unit for coordinates.
            number_type: The number type for coordinates.

        Returns:
            A new EventStore containing the events.

        Examples:
            >>> store = EventStore.from_arrays({
            ...     "id": ["e1", "e2"],
            ...     "temporal_type": ["instant", "instant"],
            ...     "event_type": ["Beat", "Beat"],
            ...     "instant": [0, 480],
            ... }, unit=TimeUnit.ticks)
        """
        if not columns or not columns.get("id"):
            return cls.empty(unit, number_type)

        # Convert coordinate columns to struct format
        n_rows = len(columns["id"])
        processed = {}

        for col_name in cls.column_names():
            if col_name in ("instant", "start", "end", "duration"):
                if col_name in columns:
                    processed[col_name] = [
                        coordinate_to_struct(v) if v is not None else None
                        for v in columns[col_name]
                    ]
                else:
                    processed[col_name] = [None] * n_rows
            elif col_name in columns:
                processed[col_name] = columns[col_name]
            elif col_name == "name":
                processed[col_name] = [None] * n_rows
            else:
                processed[col_name] = [None] * n_rows

        schema = cls.schema(unit)
        metadata = make_table_metadata(unit, number_type, loader_class=cls.__name__)
        schema = schema.with_metadata(metadata)

        table = pa.Table.from_pydict(processed, schema=schema)
        return cls(table, unit, number_type)

    @classmethod
    def from_dataframe(
        cls,
        df: pd.DataFrame,
        unit: TimeUnit,
        number_type: NumberType = NumberType.float,
    ) -> Self:
        """Create EventStore from a pandas DataFrame.

        Args:
            df: DataFrame with event data. Column names should match the schema.
            unit: The time unit for coordinates.
            number_type: The number type for coordinates.

        Returns:
            A new EventStore containing the events.
        """
        if df.empty:
            return cls.empty(unit, number_type)

        return cls.from_dicts(df.to_dict("records"), unit, number_type)

    @classmethod
    def from_parquet(cls, path: Path | str) -> Self:
        """Load EventStore from a Parquet file.

        Args:
            path: Path to the Parquet file.

        Returns:
            An EventStore loaded from the file.

        Raises:
            ValueError: If the file lacks required TimeToAlign! metadata.
        """
        table = pq.read_table(path)
        metadata = parse_table_metadata(table.schema)

        if not metadata:
            raise ValueError(f"File {path} lacks TimeToAlign! metadata")

        unit = TimeUnit(metadata["unit"])
        number_type = NumberType(metadata["number_type"])

        return cls(table, unit, number_type)

    # endregion

    # region Properties

    @property
    def table(self) -> pa.Table:
        """The underlying PyArrow table."""
        return self._table

    @property
    def unit(self) -> TimeUnit:
        """The time unit for coordinates."""
        return self._unit

    @property
    def number_type(self) -> NumberType:
        """The number type for coordinate interpretation."""
        return self._number_type

    @property
    def count(self) -> int:
        """The number of events in the store."""
        return self._table.num_rows

    # endregion

    # region Magic Methods

    def __len__(self) -> int:
        """Return the number of events."""
        return self.count

    def __iter__(self) -> Iterator[dict[str, Any]]:
        """Iterate over events as dictionaries."""
        for batch in self._table.to_batches():
            for row in batch.to_pylist():
                yield row

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"{self.__class__.__name__}("
            f"count={self.count}, unit={self.unit}, number_type={self.number_type})"
        )

    # endregion

    # region Extend/Merge

    def extend(self, other: EventStore) -> None:
        """Extend this store with events from another store (in-place).

        Args:
            other: Another EventStore with compatible schema.

        Raises:
            ValueError: If units don't match.
        """
        if other.unit != self.unit:
            raise ValueError(f"Unit mismatch: {self.unit} vs {other.unit}")

        self._table = pa.concat_tables([self._table, other._table])

    def concat(self, *others: EventStore) -> EventStore:
        """Concatenate with other stores, returning a new store.

        Args:
            *others: Other EventStores to concatenate.

        Returns:
            A new EventStore containing all events.

        Raises:
            ValueError: If any units don't match.
        """
        tables = [self._table]
        for other in others:
            if other.unit != self.unit:
                raise ValueError(f"Unit mismatch: {self.unit} vs {other.unit}")
            tables.append(other._table)

        new_table = pa.concat_tables(tables)
        return self.__class__(new_table, self.unit, self.number_type)

    # endregion

    # region Query/Filter

    def filter(
        self,
        *,
        temporal_type: Literal["instant", "interval"] | None = None,
        event_type: str | None = None,
        min_coord: float | None = None,
        max_coord: float | None = None,
        **kwargs: Any,
    ) -> EventStore:
        """Filter events by criteria, returning a new EventStore.

        All criteria are AND-ed together.

        Args:
            temporal_type: Filter by "instant" or "interval".
            event_type: Filter by event type name.
            min_coord: Minimum coordinate (inclusive).
            max_coord: Maximum coordinate (exclusive).
            **kwargs: Exact match filters for other columns (e.g. event_category="note").

        Returns:
            A new EventStore with filtered events.
        """
        mask = None

        if temporal_type is not None:
            expr = pc.equal(pc.field("temporal_type"), temporal_type)
            mask = expr if mask is None else (mask & expr)

        if event_type is not None:
            expr = pc.equal(pc.field("event_type"), event_type)
            mask = expr if mask is None else (mask & expr)

        if min_coord is not None or max_coord is not None:
            # For coordinate filtering, we use the float 'value' field
            # Check both instant.value and start.value
            instant_val = pc.struct_field(pc.field("instant"), "value")
            start_val = pc.struct_field(pc.field("start"), "value")

            # Use coalesce to get whichever is not null
            coord_val = pc.coalesce(instant_val, start_val)

            if min_coord is not None:
                expr = pc.greater_equal(coord_val, min_coord)
                mask = expr if mask is None else (mask & expr)

            if max_coord is not None:
                expr = pc.less(coord_val, max_coord)
                mask = expr if mask is None else (mask & expr)

        # Generic kwargs filtering
        for col, val in kwargs.items():
            # Only if column exists in schema
            if col in self.column_names():
                expr = pc.equal(pc.field(col), val)
                mask = expr if mask is None else (mask & expr)

        if mask is None:
            return self

        filtered = self._table.filter(mask)
        return self.__class__(filtered, self.unit, self.number_type)

    def select(self, columns: list[str]) -> pa.Table:
        """Select specific columns from the table.

        Args:
            columns: List of column names to select.

        Returns:
            A PyArrow table with only the selected columns.
        """
        return self._table.select(columns)

    def where(self, expression: pc.Expression) -> EventStore:
        """Filter with a custom PyArrow compute expression.

        Args:
            expression: A PyArrow compute expression.

        Returns:
            A new EventStore with filtered events.
        """
        filtered = self._table.filter(expression)
        return self.__class__(filtered, self.unit, self.number_type)

    # endregion

    # region Stats/Overview

    def count_by(self, column: str) -> dict[str, int]:
        """Count events grouped by a column's values.

        Args:
            column: The column to group by.

        Returns:
            Dict mapping column values to counts.
        """
        result = self._table.group_by(column).aggregate([(column, "count")])
        return {row[column]: row[f"{column}_count"] for row in result.to_pylist()}

    def coordinate_range(self) -> tuple[float, float] | None:
        """Get the min and max coordinates across all events.

        Returns:
            Tuple of (min, max) coordinates, or None if store is empty.
        """
        if self.count == 0:
            return None

        # Get min/max iteratively to avoid PyArrow chunked_array type issues
        min_val = None
        max_val = None

        for col_name in ["instant", "start", "end"]:
            try:
                col = self._table.column(col_name)
                # Check for null column
                if col.null_count == len(col):
                    continue

                vals = pc.struct_field(col, "value")
                vals = pc.drop_null(vals)

                if len(vals) > 0:
                    curr_min = pc.min(vals).as_py()
                    curr_max = pc.max(vals).as_py()

                    if min_val is None or curr_min < min_val:
                        min_val = curr_min
                    if max_val is None or curr_max > max_val:
                        max_val = curr_max
            except (ValueError, TypeError, KeyError):
                continue

        if min_val is None:
            return None

        return (min_val, max_val)

    def event_types(self) -> list[str]:
        """Get the list of unique event types.

        Returns:
            List of event type names.
        """
        unique = pc.unique(self._table.column("event_type"))
        return [v.as_py() for v in unique if v.as_py() is not None]

    def summary(self) -> dict[str, Any]:
        """Get a comprehensive summary of the store.

        Returns:
            Dict with count, temporal type counts, event type counts,
            coordinate range, unit, and number type.
        """
        return {
            "count": self.count,
            "unit": str(self.unit),
            "number_type": str(self.number_type),
            "temporal_types": self.count_by("temporal_type"),
            "event_types": self.count_by("event_type"),
            "coordinate_range": self.coordinate_range(),
        }

    # endregion

    # region Serialization

    def to_parquet(self, path: Path | str) -> None:
        """Save the EventStore to a Parquet file.

        Args:
            path: Path to write the Parquet file.
        """
        pq.write_table(self._table, path)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert to a pandas DataFrame.

        Returns:
            A DataFrame with the event data.
        """
        return self._table.to_pandas()

    # endregion
