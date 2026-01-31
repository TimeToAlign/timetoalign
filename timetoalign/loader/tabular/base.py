"""TabularLoader: Vectorized base class for loading tabular data.

This module provides the TabularLoader class that supports:
- ZERO ROW ITERATION: All operations are vectorized
- Configurable column mapping (source column -> schema field)
- Multiple coordinate parsing strategies (float, int, fraction)
- Delimiter configuration for different formats
- Event type inference from data

Design:
- Single file read: pd.read_csv() -> DataFrame
- Vectorized column extraction -> numpy/pandas arrays
- Vectorized coordinate parsing -> PyArrow StructArrays via CoordinateParser
- Vectorized validation -> ArrayValidator
- Single table construction: pa.table()

NO FOR LOOPS OVER ROWS. EVER.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np
import pandas as pd
import pyarrow as pa

from timetoalign.core import NumberType, TimeUnit
from timetoalign.loader.base import Loader
from timetoalign.loader.parsing import CoordinateParser

if TYPE_CHECKING:
    pass

module_logger = logging.getLogger(__name__)


# region TabularLoader


class TabularLoader(Loader):
    """Vectorized base class for loading tabular data with configurable column mapping.

    TabularLoader provides a ZERO ROW ITERATION framework for loading CSV, TSV,
    and other delimited formats into EventData. All operations use vectorized
    numpy/pandas/pyarrow operations.

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

    Architecture:
        1. Single file read: pd.read_csv() -> DataFrame
        2. Vectorized column extraction -> numpy arrays
        3. Vectorized coordinate parsing -> PyArrow StructArrays
        4. Vectorized validation -> ArrayValidator
        5. Returns column dict (NOT row dicts)

    NO FOR LOOPS OVER ROWS. EVER.

    Examples:
        >>> class MyLoader(TabularLoader):
        ...     delimiter = "\\t"
        ...     start_column = "onset"
        ...     end_column = "offset"
        ...     coordinate_unit = TimeUnit.seconds
        ...     extra_columns = {"pitch": "midi_note"}

        >>> loader = MyLoader()
        >>> loader.load("annotations.tsv")  # Vectorized loading
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

    # region Vectorized Loading

    def _load_source(
        self, source: Path
    ) -> tuple[dict[str, Any], dict[str, np.ndarray | pa.Array]]:
        """Load a single source file (VECTORIZED).

        Reads the tabular file using vectorized pandas operations and returns
        column arrays ready for EventData.from_arrays(). NO ROW ITERATION.

        Architecture:
            1. Single file read: pd.read_csv()
            2. Validate required columns exist
            3. Extract columns as numpy/pyarrow arrays (vectorized)
            4. Parse coordinates via CoordinateParser (vectorized)
            5. Return column dict (NOT row dicts)

        Args:
            source: Path to the source file.

        Returns:
            A tuple of (metadata_dict, column_dict):
            - metadata_dict: File-specific metadata
            - column_dict: Dict[str, np.ndarray | pa.Array] for EventData.from_arrays()

        Raises:
            FileNotFoundError: If the source file doesn't exist.
            ValueError: If required columns are missing.
        """
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")

        # Step 1: Single file read (vectorized I/O)
        df = self._read_dataframe(source)

        # Step 2: Validate required columns exist
        self._validate_columns(df, source)

        # Step 3: Extract column arrays (vectorized)
        columns = self._extract_column_arrays(df)

        # Step 4: Build metadata
        metadata = {
            "format": self._infer_format(source),
            "delimiter": self.delimiter,
            "row_count": len(df),
            "columns": list(df.columns),
        }

        return metadata, columns

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

    def _extract_column_arrays(
        self, df: pd.DataFrame
    ) -> dict[str, np.ndarray | pa.Array]:
        """Extract column arrays from DataFrame (VECTORIZED).

        NO ROW ITERATION. All operations use vectorized numpy/pandas/pyarrow.

        Args:
            df: The loaded DataFrame.

        Returns:
            Dict of {column_name: array} ready for EventData.from_arrays().
        """
        n = len(df)
        columns: dict[str, Any] = {}

        # ID column (vectorized generation if not present)
        if self.id_column and self.id_column in df.columns:
            columns["id"] = df[self.id_column].astype(str).to_numpy()
        else:
            # Vectorized ID generation
            columns["id"] = np.array([f"e{i:06d}" for i in range(n)])

        # Name column (vectorized extraction)
        if self.name_column and self.name_column in df.columns:
            name_series = df[self.name_column]
            # Convert to string, handling nulls (vectorized)
            columns["name"] = np.where(
                name_series.isna(), None, name_series.astype(str).to_numpy()
            )
        else:
            columns["name"] = np.array([None] * n, dtype=object)

        # Start coordinate (vectorized parsing via CoordinateParser)
        start_values = df[self.start_column].to_numpy()
        columns["start"] = CoordinateParser.parse(
            start_values, self.coordinate_type, self._unit
        )

        # End coordinate (vectorized parsing)
        # has_end = False
        if self.end_column and self.end_column in df.columns:
            end_col = df[self.end_column]
            # Check for non-null values (vectorized)
            has_end_values = end_col.notna()
            if has_end_values.any():
                # has_end = True
                # Parse non-null values (vectorized)
                end_values = end_col.to_numpy()
                # Create mask for valid values
                valid_mask = ~pd.isna(end_values)
                if valid_mask.all():
                    columns["end"] = CoordinateParser.parse(
                        end_values, self.coordinate_type, self._unit
                    )
                else:
                    # Handle mixed null/non-null (vectorized)
                    columns["end"] = self._parse_nullable_coordinates(
                        end_values, valid_mask
                    )
            else:
                columns["end"] = pa.nulls(n, type=columns["start"].type)
        elif self.duration_column and self.duration_column in df.columns:
            # Vectorized: end = start + duration
            dur_col = df[self.duration_column]
            has_dur_values = dur_col.notna()
            if has_dur_values.any():
                # has_end = True
                dur_values = dur_col.to_numpy()

                # Get start values, handling nulls
                start_float = (
                    columns["start"].field("value").to_numpy(zero_copy_only=False)
                )

                # Compute valid mask: need both start and duration to be valid
                start_is_null = (
                    columns["start"].is_null().to_numpy(zero_copy_only=False)
                )
                valid_dur_mask = ~pd.isna(dur_values)
                valid_end_mask = ~start_is_null & valid_dur_mask

                # Parse duration values as float (vectorized)
                dur_float = np.zeros(n, dtype=np.float64)
                if valid_dur_mask.any():
                    # Fill with duration values where valid
                    dur_float[valid_dur_mask] = dur_values[valid_dur_mask].astype(
                        np.float64
                    )

                # Compute end = start + duration (vectorized)
                end_float = start_float + dur_float

                # Parse end values (only where both start and duration are valid)
                columns["end"] = self._parse_nullable_coordinates(
                    end_float, valid_end_mask
                )

                # Store duration as well
                columns["duration"] = self._parse_nullable_coordinates(
                    dur_values, valid_dur_mask
                )
            else:
                columns["end"] = pa.nulls(n, type=columns["start"].type)
        else:
            # No end column: all instant events
            columns["end"] = pa.nulls(n, type=columns["start"].type)

        # Temporal type (vectorized: instant if end is null, interval otherwise)
        if isinstance(columns["end"], pa.StructArray):
            has_end_arr = ~columns["end"].is_null().to_numpy(zero_copy_only=False)
        else:
            has_end_arr = np.zeros(n, dtype=bool)
        columns["temporal_type"] = np.where(has_end_arr, "interval", "instant")

        # Event type (vectorized extraction or default)
        if self.event_type_column and self.event_type_column in df.columns:
            event_type_series = df[self.event_type_column]
            columns["event_type"] = np.where(
                event_type_series.isna(),
                self.default_event_type,
                event_type_series.astype(str).to_numpy(),
            )
        else:
            columns["event_type"] = np.full(n, self.default_event_type, dtype=object)

        # Extra columns (vectorized extraction)
        for schema_field, source_col in self.extra_columns.items():
            if source_col in df.columns:
                columns[schema_field] = df[source_col].to_numpy()

        return columns

    def _parse_nullable_coordinates(
        self, values: np.ndarray, valid_mask: np.ndarray
    ) -> pa.StructArray:
        """Parse coordinate array with null values (VECTORIZED).

        NO ROW ITERATION. Uses numpy advanced indexing and PyArrow
        array construction.

        Args:
            values: Array of coordinate values (may contain nulls).
            valid_mask: Boolean mask indicating valid (non-null) values.

        Returns:
            PyArrow StructArray with nulls where mask is False.
        """
        n = len(values)
        coord_type = pa.struct(
            [
                pa.field("value", pa.float64(), nullable=True),
                pa.field("numerator", pa.int64(), nullable=True),
                pa.field("denominator", pa.int64(), nullable=True),
            ]
        )

        if not valid_mask.any():
            return pa.nulls(n, type=coord_type)

        # Parse valid values (vectorized)
        valid_values = values[valid_mask]
        # Ensure numeric type for parsing
        if valid_values.dtype == object:
            valid_values = valid_values.astype(np.float64)
        parsed = CoordinateParser.parse(valid_values, NumberType.float, self._unit)

        # Build full array with nulls using vectorized approach
        # Create arrays for each struct field
        value_arr = np.full(n, np.nan, dtype=np.float64)
        num_arr = np.full(n, np.nan, dtype=np.float64)
        den_arr = np.full(n, np.nan, dtype=np.float64)

        # Scatter valid values using boolean indexing (vectorized)
        value_arr[valid_mask] = parsed.field("value").to_numpy(zero_copy_only=False)

        # For numerator/denominator, check if they're not all null
        parsed_num = parsed.field("numerator")
        parsed_den = parsed.field("denominator")

        if parsed_num.null_count < len(parsed_num):
            # Has valid numerators
            num_np = parsed_num.to_numpy(zero_copy_only=False)
            num_arr[valid_mask] = np.where(
                pd.isna(num_np), np.nan, num_np.astype(np.float64)
            )

        if parsed_den.null_count < len(parsed_den):
            # Has valid denominators
            den_np = parsed_den.to_numpy(zero_copy_only=False)
            den_arr[valid_mask] = np.where(
                pd.isna(den_np), np.nan, den_np.astype(np.float64)
            )

        # Build struct array using PyArrow (vectorized construction)
        # Create null mask for the struct array
        struct_null_mask = ~valid_mask

        # Build each field array with proper null handling
        value_pa = pa.array(value_arr, mask=struct_null_mask, type=pa.float64())
        num_pa = pa.array(
            np.where(np.isnan(num_arr), None, num_arr.astype(np.int64)),
            type=pa.int64(),
        )
        den_pa = pa.array(
            np.where(np.isnan(den_arr), None, den_arr.astype(np.int64)),
            type=pa.int64(),
        )

        # Combine into struct array with proper field types
        return pa.StructArray.from_arrays(
            [value_pa, num_pa, den_pa],
            fields=list(coord_type),
            mask=pa.array(struct_null_mask),
        )

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
