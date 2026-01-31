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
from timetoalign.loader.schema import (
    ComputedField,
    ConvertedField,
    Field,
    parse_json_to_struct,
)

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
        extra_columns: List of extra columns to include. Can be:
            - Column names as strings: ["midi", "velocity"]
            - ConvertedField objects for type/converter control
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
        ...     extra_columns = ["velocity", "channel"]  # Simple column names

        >>> # For advanced cases with type/converter:
        >>> from timetoalign.loader.schema import ConvertedField
        >>> class AdvancedLoader(TabularLoader):
        ...     extra_columns = [
        ...         "velocity",  # Simple
        ...         ConvertedField("pitch", int, source="midi_note"),  # Renamed + typed
        ...     ]

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
    # start_column can be:
    #   - str: Direct column name
    #   - tuple: Struct field access like ("rect_coords", "x")
    #   - Field: Struct field object like Field("rect_coords", "x")
    #   - ComputedField: Computed value (not typical for start)
    start_column: ClassVar[str | tuple | Field | ComputedField] = "start"  # Required
    _fallback_start_column: ClassVar[str | None] = (
        None  # Fallback if start_column missing
    )
    # end_column can be:
    #   - str: Direct column name
    #   - tuple: Struct field access like ("rect_coords", "x")
    #   - Field: Struct field object
    #   - ComputedField: Computed value like "rect_coords.x + rect_coords.width"
    #   - None: Instant events (no end)
    end_column: ClassVar[str | tuple | Field | ComputedField | None] = None
    duration_column: ClassVar[str | None] = None  # Alternative to end_column
    event_type_column: ClassVar[str | None] = None
    default_event_type: ClassVar[str] = "Event"

    # Extra columns to include from source data.
    # Can be:
    #   - List of column names: ["midi", "velocity", "staff"]
    #   - List mixing names and ConvertedField for advanced cases:
    #     ["midi", ConvertedField("pitch", int, source="note_num")]
    #   - ConvertedField with struct type for JSON parsing:
    #     [ConvertedField("rect_coords", dict, source="rect_coords_json")]
    #   - True: Auto-include all remaining columns (inferred types)
    #   - Dict mapping column names to types: {"midi": int, "velocity": float}
    extra_columns: ClassVar[list | bool | dict] = []

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

        Handles string column names, Field references, and ComputedField.
        For Field/ComputedField, validates that required source columns exist.

        Args:
            df: The loaded DataFrame.
            source: Path to source (for error messages).

        Raises:
            ValueError: If required columns are missing.
        """
        start_col = self.start_column

        # For Field, validate the parent column exists
        if isinstance(start_col, Field):
            if start_col.column not in df.columns:
                # Check if it's a struct field from extra_columns
                struct_sources = self._get_struct_source_columns()
                if start_col.column not in struct_sources:
                    raise ValueError(
                        f"Column '{start_col.column}' for Field not found in {source}. "
                        f"Available columns: {list(df.columns)}"
                    )
        elif isinstance(start_col, tuple):
            # Tuple is shorthand for Field
            if start_col[0] not in df.columns:
                struct_sources = self._get_struct_source_columns()
                if start_col[0] not in struct_sources:
                    raise ValueError(
                        f"Column '{start_col[0]}' for tuple field not found in {source}. "
                        f"Available columns: {list(df.columns)}"
                    )
        elif isinstance(start_col, ComputedField):
            # ComputedField is validated during computation
            pass
        elif isinstance(start_col, str) and start_col not in df.columns:
            # Check fallback
            if not (
                self._fallback_start_column
                and self._fallback_start_column in df.columns
            ):
                raise ValueError(
                    f"Required column '{start_col}' not found in {source}. "
                    f"Available columns: {list(df.columns)}"
                )

    def _get_struct_source_columns(self) -> dict[str, ConvertedField]:
        """Get mapping of struct column names to their ConvertedField definitions.

        Returns:
            Dict mapping output column name to ConvertedField for struct columns.
        """
        # Only lists can contain ConvertedField with struct types
        # True and dict forms don't support struct parsing
        if not isinstance(self.extra_columns, list):
            return {}

        result = {}
        for col_spec in self.extra_columns:
            if isinstance(col_spec, ConvertedField) and col_spec.is_struct:
                result[col_spec.name] = col_spec
        return result

    def _normalize_extra_columns(self, df: pd.DataFrame) -> list[str | ConvertedField]:
        """Normalize extra_columns to a list based on DataFrame.

        Handles three formats:
        - list: Return as-is
        - True: Return all non-core columns from DataFrame
        - dict: Convert to list of column names (types used for future validation)

        Args:
            df: The loaded DataFrame.

        Returns:
            Normalized list of column specs.
        """
        if isinstance(self.extra_columns, list):
            return self.extra_columns

        if self.extra_columns is True:
            # Auto-include all columns not already used by core fields
            core_columns = {
                self.id_column,
                self.name_column,
                self.event_type_column,
                self.duration_column,
            }
            # Handle start_column (could be str, tuple, or Field)
            if isinstance(self.start_column, str):
                core_columns.add(self.start_column)
            if self._fallback_start_column:
                core_columns.add(self._fallback_start_column)
            # Handle end_column
            if isinstance(self.end_column, str):
                core_columns.add(self.end_column)

            # Return all columns not in core set
            return [col for col in df.columns if col not in core_columns]

        if isinstance(self.extra_columns, dict):
            # Dict format: {"col_name": type, ...}
            # For now, just return the column names (types are for future validation)
            return list(self.extra_columns.keys())

        # Fallback: empty list
        return []

    def _extract_column_arrays(
        self, df: pd.DataFrame
    ) -> dict[str, np.ndarray | pa.Array]:
        """Extract column arrays from DataFrame (VECTORIZED).

        NO ROW ITERATION. All operations use vectorized numpy/pandas/pyarrow.

        Supports:
        - Direct column names (str)
        - Struct field access via Field or tuple
        - Computed columns via ComputedField
        - JSON to struct parsing for ConvertedField with is_struct=True

        Args:
            df: The loaded DataFrame.

        Returns:
            Dict of {column_name: array} ready for EventData.from_arrays().
        """

        n = len(df)
        columns: dict[str, Any] = {}

        # Normalize extra_columns to a list (handles True, dict, and list forms)
        extra_cols = self._normalize_extra_columns(df)

        # Step 1: Parse struct columns (JSON -> struct) FIRST
        # This builds a temporary table we can use for Field/ComputedField resolution
        struct_columns: dict[str, pa.Array] = {}
        for col_spec in extra_cols:
            if isinstance(col_spec, ConvertedField) and col_spec.is_struct:
                source_col = col_spec.source
                if source_col in df.columns:
                    struct_arr = parse_json_to_struct(
                        df[source_col],
                        struct_schema=col_spec.struct_schema,
                    )
                    struct_columns[col_spec.name] = struct_arr
                    columns[col_spec.name] = struct_arr

        # Step 2: Build a temporary PyArrow table for Field/ComputedField resolution
        # Include DataFrame columns + parsed struct columns
        temp_arrays = {}
        for col_name in df.columns:
            temp_arrays[col_name] = pa.array(df[col_name])
        temp_arrays.update(struct_columns)
        temp_table = pa.table(temp_arrays)

        # Step 3: Extract basic columns
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
            name_arr = name_series.astype(str).to_numpy()
            null_mask = name_series.isna().to_numpy()
            name_arr[null_mask] = None  # type: ignore[assignment]
            columns["name"] = name_arr
        else:
            columns["name"] = np.array([None] * n, dtype=object)

        # Step 4: Extract start coordinate
        start_values = self._resolve_column_reference(
            self.start_column, df, temp_table, "start"
        )
        columns["start"] = CoordinateParser.parse(
            start_values, self.coordinate_type, self._unit
        )

        # Step 5: Extract end coordinate
        columns["end"] = self._extract_end_column(df, temp_table, columns, n)

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

        # Step 6: Extract extra columns (non-struct, already handled struct above)
        for col_spec in extra_cols:
            if isinstance(col_spec, str):
                # Simple case: column name, same in source and output
                if col_spec in df.columns:
                    columns[col_spec] = df[col_spec].to_numpy()
            elif isinstance(col_spec, ConvertedField):
                # Skip struct fields (already processed)
                if col_spec.is_struct:
                    continue
                # ConvertedField case: may have different source name, type, converter
                schema_field = col_spec.name
                source_col = col_spec.source
                if source_col in df.columns:
                    arr = df[source_col].to_numpy()
                    if col_spec.converter:
                        arr = col_spec.converter(arr)
                    columns[schema_field] = arr

        return columns

    def _resolve_column_reference(
        self,
        col_ref: str | tuple | Field | ComputedField,
        df: pd.DataFrame,
        temp_table: pa.Table,
        context: str,
    ) -> np.ndarray:
        """Resolve a column reference to a numpy array of values.

        Handles:
        - str: Direct DataFrame column lookup
        - tuple: Convert to Field and resolve
        - Field: Struct field access via PyArrow
        - ComputedField: Compute from formula/expression

        Args:
            col_ref: The column reference to resolve.
            df: The source DataFrame.
            temp_table: PyArrow table with struct columns.
            context: Context name for error messages (e.g., "start", "end").

        Returns:
            Numpy array of values.
        """
        if isinstance(col_ref, str):
            # Direct column name
            if col_ref in df.columns:
                return df[col_ref].to_numpy()
            elif self._fallback_start_column and context == "start":
                if self._fallback_start_column in df.columns:
                    return df[self._fallback_start_column].to_numpy()
            raise ValueError(
                f"Column '{col_ref}' not found for {context}. "
                f"Available: {list(df.columns)}"
            )

        elif isinstance(col_ref, tuple):
            # Convert tuple to Field
            col_ref = Field(col_ref[0], *col_ref[1:])

        if isinstance(col_ref, Field):
            # Struct field access
            array = col_ref.resolve(temp_table)
            return array.to_numpy(zero_copy_only=False)

        elif isinstance(col_ref, ComputedField):
            # Computed column
            array = col_ref.compute(temp_table)
            return array.to_numpy(zero_copy_only=False)

        else:
            raise TypeError(
                f"Invalid column reference type for {context}: {type(col_ref)}"
            )

    def _extract_end_column(
        self,
        df: pd.DataFrame,
        temp_table: pa.Table,
        columns: dict[str, Any],
        n: int,
    ) -> pa.Array:
        """Extract the end column, handling various source types.

        Handles:
        - Field/tuple/ComputedField references
        - Direct column names
        - Duration column (computes end = start + duration)
        - None (instant events)

        Args:
            df: Source DataFrame.
            temp_table: PyArrow table with struct columns.
            columns: Already extracted columns (includes "start").
            n: Number of rows.

        Returns:
            PyArrow array for the end column.
        """
        end_col_ref = self.end_column

        # Case 1: No end column (instant events)
        if end_col_ref is None and self.duration_column is None:
            return pa.nulls(n, type=columns["start"].type)

        # Case 2: Field, tuple, or ComputedField reference
        if isinstance(end_col_ref, (Field, tuple, ComputedField)):
            end_values = self._resolve_column_reference(
                end_col_ref, df, temp_table, "end"
            )
            return CoordinateParser.parse(end_values, self.coordinate_type, self._unit)

        # Case 3: Direct column name
        if isinstance(end_col_ref, str) and end_col_ref in df.columns:
            end_col = df[end_col_ref]
            has_end_values = end_col.notna()
            if bool(has_end_values.any()):
                end_values = end_col.to_numpy()
                valid_mask = ~pd.isna(end_values)
                if valid_mask.all():
                    return CoordinateParser.parse(
                        end_values, self.coordinate_type, self._unit
                    )
                else:
                    return self._parse_nullable_coordinates(end_values, valid_mask)
            else:
                return pa.nulls(n, type=columns["start"].type)

        # Case 4: Duration column (compute end = start + duration)
        if self.duration_column and self.duration_column in df.columns:
            return self._compute_end_from_duration(df, columns, n)

        # Case 5: end_column specified but not found, and no duration
        if end_col_ref is not None:
            return pa.nulls(n, type=columns["start"].type)

        # Default: instant events
        return pa.nulls(n, type=columns["start"].type)

    def _compute_end_from_duration(
        self,
        df: pd.DataFrame,
        columns: dict[str, Any],
        n: int,
    ) -> pa.Array:
        """Compute end column from start + duration (FULLY VECTORIZED).

        Args:
            df: Source DataFrame.
            columns: Already extracted columns (includes "start").
            n: Number of rows.

        Returns:
            PyArrow array for the end column.
        """
        dur_col = df[self.duration_column]
        has_dur_values = dur_col.notna()

        if not bool(has_dur_values.any()):
            return pa.nulls(n, type=columns["start"].type)

        dur_values = dur_col.to_numpy()

        # Compute valid masks (vectorized)
        start_is_null = columns["start"].is_null().to_numpy(zero_copy_only=False)
        valid_dur_mask = ~pd.isna(dur_values)
        valid_end_mask = ~start_is_null & valid_dur_mask

        # Parse duration using CoordinateParser (vectorized)
        valid_dur_values = dur_values[valid_dur_mask]
        parsed_dur = CoordinateParser.parse(
            valid_dur_values, self.coordinate_type, self._unit
        )

        # Build full duration arrays using scatter (vectorized)
        dur_value_full = np.full(n, np.nan, dtype=np.float64)
        dur_num_full = np.zeros(n, dtype=np.int64)
        dur_den_full = np.ones(n, dtype=np.int64)

        valid_indices = np.where(valid_dur_mask)[0]
        dur_value_full[valid_indices] = parsed_dur.field("value").to_numpy(
            zero_copy_only=False
        )

        # Extract numerator/denominator arrays from parsed (vectorized)
        parsed_num_arr = parsed_dur.field("numerator").to_numpy(zero_copy_only=False)
        parsed_den_arr = parsed_dur.field("denominator").to_numpy(zero_copy_only=False)

        num_valid = ~pd.isna(parsed_num_arr)
        den_valid = ~pd.isna(parsed_den_arr)

        if num_valid.any():
            dur_num_full[valid_indices[num_valid]] = parsed_num_arr[num_valid].astype(
                np.int64
            )
        if den_valid.any():
            dur_den_full[valid_indices[den_valid]] = parsed_den_arr[den_valid].astype(
                np.int64
            )

        # Get start arrays (vectorized)
        start_value = columns["start"].field("value").to_numpy(zero_copy_only=False)
        start_num = columns["start"].field("numerator").to_numpy(zero_copy_only=False)
        start_den = columns["start"].field("denominator").to_numpy(zero_copy_only=False)

        # Compute end = start + duration (vectorized)
        end_value = start_value + dur_value_full

        # Vectorized fraction addition: a/b + c/d = (a*d + c*b) / (b*d)
        start_has_frac = ~pd.isna(start_num) & ~pd.isna(start_den)
        dur_has_frac = valid_dur_mask.copy()
        both_frac_mask = start_has_frac & dur_has_frac & valid_end_mask

        s_num = np.where(pd.isna(start_num), 0, start_num).astype(np.int64)
        s_den = np.where(pd.isna(start_den), 1, start_den).astype(np.int64)
        d_num = dur_num_full
        d_den = dur_den_full

        result_num = s_num * d_den + d_num * s_den
        result_den = s_den * d_den

        end_num = np.zeros(n, dtype=np.int64)
        end_den = np.ones(n, dtype=np.int64)

        if both_frac_mask.any():
            gcd_vals = np.gcd(result_num[both_frac_mask], result_den[both_frac_mask])
            end_num[both_frac_mask] = result_num[both_frac_mask] // gcd_vals
            end_den[both_frac_mask] = result_den[both_frac_mask] // gcd_vals

        # Build coordinate struct arrays (vectorized)
        coord_type = pa.struct(
            [
                pa.field("value", pa.float64(), nullable=True),
                pa.field("numerator", pa.int64(), nullable=True),
                pa.field("denominator", pa.int64(), nullable=True),
            ]
        )

        end_null_mask = ~valid_end_mask
        end_num_null_mask = ~both_frac_mask

        # Also store duration in columns
        dur_null_mask = ~valid_dur_mask
        dur_num_has_value = np.zeros(n, dtype=bool)
        dur_num_has_value[valid_indices] = num_valid
        dur_num_null_full = ~dur_num_has_value

        columns["duration"] = pa.StructArray.from_arrays(
            [
                pa.array(dur_value_full, mask=dur_null_mask, type=pa.float64()),
                pa.array(dur_num_full, mask=dur_num_null_full, type=pa.int64()),
                pa.array(dur_den_full, mask=dur_num_null_full, type=pa.int64()),
            ],
            fields=list(coord_type),
            mask=pa.array(dur_null_mask),
        )

        return pa.StructArray.from_arrays(
            [
                pa.array(end_value, mask=end_null_mask, type=pa.float64()),
                pa.array(end_num, mask=end_num_null_mask, type=pa.int64()),
                pa.array(end_den, mask=end_num_null_mask, type=pa.int64()),
            ],
            fields=list(coord_type),
            mask=pa.array(end_null_mask),
        )

    def _parse_nullable_coordinates(
        self, values: np.ndarray, valid_mask: np.ndarray
    ) -> pa.StructArray:
        """Parse coordinate array with null values (FULLY VECTORIZED).

        NO ROW ITERATION. Uses numpy advanced indexing and PyArrow
        array construction with proper null masks.

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

        # Use the loader's coordinate_type for parsing
        parsed = CoordinateParser.parse(valid_values, self.coordinate_type, self._unit)

        # Extract parsed arrays (vectorized)
        parsed_value = parsed.field("value").to_numpy(zero_copy_only=False)
        parsed_num = parsed.field("numerator").to_numpy(zero_copy_only=False)
        parsed_den = parsed.field("denominator").to_numpy(zero_copy_only=False)

        # Build full arrays with proper defaults (vectorized)
        value_arr = np.full(n, np.nan, dtype=np.float64)
        num_arr = np.zeros(n, dtype=np.int64)
        den_arr = np.ones(n, dtype=np.int64)  # Default denominator = 1

        # Scatter valid values using boolean indexing (vectorized)
        valid_indices = np.where(valid_mask)[0]
        value_arr[valid_indices] = parsed_value

        # Handle numerator/denominator with null awareness (vectorized)
        num_valid_in_parsed = ~pd.isna(parsed_num)
        den_valid_in_parsed = ~pd.isna(parsed_den)

        if num_valid_in_parsed.any():
            target_indices = valid_indices[num_valid_in_parsed]
            num_arr[target_indices] = parsed_num[num_valid_in_parsed].astype(np.int64)
        if den_valid_in_parsed.any():
            target_indices = valid_indices[den_valid_in_parsed]
            den_arr[target_indices] = parsed_den[den_valid_in_parsed].astype(np.int64)

        # Build null masks (vectorized)
        struct_null_mask = ~valid_mask

        # For numerator/denominator, null if struct is null OR no fraction data
        num_has_value = np.zeros(n, dtype=bool)
        num_has_value[valid_indices] = num_valid_in_parsed
        num_null_mask = ~num_has_value

        # Build PyArrow arrays with proper null masks
        value_pa = pa.array(value_arr, mask=struct_null_mask, type=pa.float64())
        num_pa = pa.array(num_arr, mask=num_null_mask, type=pa.int64())
        den_pa = pa.array(den_arr, mask=num_null_mask, type=pa.int64())

        # Combine into struct array
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
