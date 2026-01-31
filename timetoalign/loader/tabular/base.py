"""TabularLoader: Base class for loading tabular data with configurable column mapping.

This module provides the abstract TabularLoader class that supports:
- Configurable column mapping (source column -> schema field)
- Multiple coordinate parsing strategies (float, int, fraction)
- Delimiter configuration for different formats
- Event type inference from data
"""

from __future__ import annotations

import logging
from fractions import Fraction
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import pandas as pd

from timetoalign.core import NumberType, TimeUnit
from timetoalign.loader.base import Loader

if TYPE_CHECKING:
    pass

module_logger = logging.getLogger(__name__)


# region TabularLoader


class TabularLoader(Loader):
    """Abstract base class for loading tabular data with configurable column mapping.

    TabularLoader provides a flexible framework for loading CSV, TSV, and other
    delimited formats into EventData. Subclasses configure column mappings and
    parsing behavior via class attributes.

    Configuration Attributes:
        delimiter: Field delimiter character (default: ",").
        header_row: Row index containing column headers (default: 0).
        id_column: Column name for event IDs (auto-generated if None).
        name_column: Column name for event names (optional).
        start_column: Column name for start coordinate (required).
        end_column: Column name for end coordinate (None for instant events).
        duration_column: Column name for duration (alternative to end_column).
        event_type_column: Column name for event type (optional).
        default_event_type: Default event type if column not specified.
        extra_columns: Dict mapping schema fields to source columns.
        coordinate_unit: TimeUnit for coordinate values.
        coordinate_type: NumberType for coordinate parsing.

    The mapping strategy:
    1. Required fields (id, start) are mapped from configured columns
    2. Optional fields (name, end, duration, event_type) are mapped if columns exist
    3. Extra columns are mapped via the extra_columns dict
    4. Unmapped source columns are preserved in the 'extra' field (if supported)

    Examples:
        >>> class MyLoader(TabularLoader):
        ...     delimiter = "\\t"
        ...     start_column = "onset"
        ...     end_column = "offset"
        ...     coordinate_unit = TimeUnit.seconds
        ...     extra_columns = {"pitch": "midi_note"}

        >>> loader = MyLoader()
        >>> loader.load("annotations.tsv")
    """

    # region Class Configuration

    # Parsing configuration
    delimiter: ClassVar[str] = ","
    header_row: ClassVar[int] = 0
    encoding: ClassVar[str] = "utf-8"

    # Column mapping - subclasses should override
    id_column: ClassVar[str | None] = None
    name_column: ClassVar[str | None] = None
    start_column: ClassVar[str] = "start"  # Required
    end_column: ClassVar[str | None] = None  # None = instant events
    duration_column: ClassVar[str | None] = None  # Alternative to end_column
    event_type_column: ClassVar[str | None] = None
    default_event_type: ClassVar[str] = "Event"

    # Extra column mapping: {schema_field: source_column}
    extra_columns: ClassVar[dict[str, str]] = {}

    # Coordinate configuration
    _default_unit: ClassVar[TimeUnit] = TimeUnit.seconds
    coordinate_type: ClassVar[NumberType] = NumberType.float

    # endregion

    def __init__(
        self,
        unit: TimeUnit | None = None,
        number_type: NumberType | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize TabularLoader.

        Args:
            unit: Override the default time unit.
            number_type: Override the default number type.
            **kwargs: Additional arguments passed to parent Loader.
        """
        # Use class-level coordinate_type as default if not overridden
        if number_type is None:
            number_type = self.coordinate_type

        super().__init__(unit=unit, number_type=number_type)
        self._logger = module_logger.getChild(self.__class__.__name__)

    # region Abstract Methods

    def _load_source(self, source: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Load a single source file.

        Reads the tabular file, applies column mapping, and converts
        to event dictionaries.

        Args:
            source: Path to the source file.

        Returns:
            A tuple of (metadata_dict, event_rows).

        Raises:
            FileNotFoundError: If the source file doesn't exist.
            ValueError: If required columns are missing.
        """
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")

        # Read the file
        df = self._read_dataframe(source)

        # Validate required columns
        self._validate_columns(df, source)

        # Convert to event rows
        event_rows = self._dataframe_to_events(df)

        # Build metadata
        metadata = {
            "format": self._infer_format(source),
            "delimiter": self.delimiter,
            "row_count": len(df),
            "columns": list(df.columns),
        }

        return metadata, event_rows

    # endregion

    # region DataFrame Processing

    def _read_dataframe(self, source: Path) -> pd.DataFrame:
        """Read source file into a DataFrame.

        Subclasses can override for custom reading logic.

        Args:
            source: Path to the source file.

        Returns:
            DataFrame containing the tabular data.
        """
        return pd.read_csv(
            source,
            sep=self.delimiter,
            header=self.header_row,
            encoding=self.encoding,
        )

    def _validate_columns(self, df: pd.DataFrame, source: Path) -> None:
        """Validate that required columns exist.

        Args:
            df: The loaded DataFrame.
            source: Path to source (for error messages).

        Raises:
            ValueError: If required columns are missing.
        """
        if self.start_column not in df.columns:
            raise ValueError(
                f"Required column '{self.start_column}' not found in {source}. "
                f"Available columns: {list(df.columns)}"
            )

    def _dataframe_to_events(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Convert DataFrame rows to event dictionaries.

        Args:
            df: The loaded DataFrame.

        Returns:
            List of event dictionaries ready for EventData.
        """
        events = []
        id_counter = 0

        for idx, row in df.iterrows():
            event = self._row_to_event(row, idx, id_counter)
            if event is not None:
                events.append(event)
                id_counter += 1

        return events

    def _row_to_event(
        self,
        row: pd.Series,
        row_idx: int,
        event_idx: int,
    ) -> dict[str, Any] | None:
        """Convert a single row to an event dictionary.

        Args:
            row: The DataFrame row.
            row_idx: Original row index in the DataFrame.
            event_idx: Running event counter for ID generation.

        Returns:
            Event dictionary, or None to skip this row.
        """
        event: dict[str, Any] = {}

        # ID
        if self.id_column and self.id_column in row.index:
            event["id"] = str(row[self.id_column])
        else:
            event["id"] = f"e{event_idx:06d}"

        # Name (optional)
        if self.name_column and self.name_column in row.index:
            val = row[self.name_column]
            event["name"] = str(val) if pd.notna(val) else None
        else:
            event["name"] = None

        # Start coordinate (required)
        start_val = row[self.start_column]
        if pd.isna(start_val):
            self._logger.warning(f"Row {row_idx}: Missing start coordinate, skipping")
            return None

        event["start"] = self._parse_coordinate(start_val)

        # End coordinate (optional)
        end_val = None
        if self.end_column and self.end_column in row.index:
            end_val = row[self.end_column]
            if pd.notna(end_val):
                event["end"] = self._parse_coordinate(end_val)
            else:
                event["end"] = None
        elif self.duration_column and self.duration_column in row.index:
            dur_val = row[self.duration_column]
            if pd.notna(dur_val):
                duration = self._parse_coordinate(dur_val)
                event["end"] = event["start"] + duration
                event["duration"] = duration
            else:
                event["end"] = None
        else:
            event["end"] = None

        # Temporal type
        if event.get("end") is not None:
            event["temporal_type"] = "interval"
        else:
            event["temporal_type"] = "instant"

        # Event type
        if self.event_type_column and self.event_type_column in row.index:
            val = row[self.event_type_column]
            event["event_type"] = str(val) if pd.notna(val) else self.default_event_type
        else:
            event["event_type"] = self.default_event_type

        # Extra columns
        for schema_field, source_col in self.extra_columns.items():
            if source_col in row.index:
                val = row[source_col]
                event[schema_field] = val if pd.notna(val) else None

        return event

    def _parse_coordinate(self, value: Any) -> int | float | Fraction:
        """Parse a coordinate value according to coordinate_type.

        Args:
            value: The raw value from the DataFrame.

        Returns:
            Parsed coordinate in the appropriate type.
        """
        if self.coordinate_type == NumberType.int:
            return int(float(value))
        elif self.coordinate_type == NumberType.fraction:
            if isinstance(value, str) and "/" in value:
                parts = value.split("/")
                return Fraction(int(parts[0]), int(parts[1]))
            else:
                return Fraction(value).limit_denominator(10000)
        else:
            return float(value)

    # endregion

    # region Utilities

    def _infer_format(self, source: Path) -> str:
        """Infer the format name from the file extension.

        Args:
            source: Path to the source file.

        Returns:
            Format name string.
        """
        ext = source.suffix.lower()
        if ext == ".csv":
            return "csv"
        elif ext in (".tsv", ".txt"):
            return "tsv"
        elif ext == ".parquet":
            return "parquet"
        else:
            return ext.lstrip(".")

    # endregion

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"delimiter={self.delimiter!r}, "
            f"start_column={self.start_column!r}, "
            f"unit={self._unit})"
        )


# endregion
