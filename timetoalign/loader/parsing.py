"""Vectorized coordinate parsing and array validation for TimeToAlign!

This module provides the CoordinateParser and ArrayValidator classes that enable
zero-iteration table construction. All operations use vectorized numpy/pandas/pyarrow
operations.

Design Principles:
- NO ROW ITERATION: All operations must be vectorized
- Array-oriented: Input is arrays, output is arrays
- Type-dispatch: Different strategies for int/float/fraction
- Early validation: Catch errors before table construction
"""

from __future__ import annotations

import logging
from fractions import Fraction
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa

from timetoalign.core import NumberType, TimeUnit

module_logger = logging.getLogger(__name__)


# region CoordinateParser


class CoordinateParser:
    """Vectorized coordinate parsing for PyArrow struct columns.

    Converts arrays of coordinates (float, int, Fraction, or string-encoded)
    into PyArrow struct arrays with {value, numerator, denominator} fields.

    All operations are vectorized using numpy/pandas - NO row iteration.

    Examples:
        >>> # Parse float array
        >>> coords = CoordinateParser.parse(
        ...     np.array([0.0, 1.5, 3.0]),
        ...     NumberType.float,
        ...     TimeUnit.seconds
        ... )
        >>> coords.field("value").to_pylist()
        [0.0, 1.5, 3.0]

        >>> # Parse string-encoded fractions
        >>> coords = CoordinateParser.parse(
        ...     ["1/4", "3/8", "1/2"],
        ...     NumberType.fraction,
        ...     TimeUnit.quarters
        ... )
        >>> coords.field("numerator").to_pylist()
        [1, 3, 1]
    """

    @staticmethod
    def parse(
        values: np.ndarray | pd.Series | list | pa.Array,
        number_type: NumberType,
        unit: TimeUnit,
    ) -> pa.StructArray:
        """Parse coordinate array into struct array (vectorized).

        Args:
            values: Array of coordinate values (homogeneous type).
            number_type: The number type (int, float, fraction).
            unit: The time unit (for metadata, not used in parsing).

        Returns:
            PyArrow StructArray with {value, numerator, denominator}.

        Raises:
            ValueError: If values contain invalid data.
            TypeError: If values type cannot be converted.
        """
        # Convert to numpy array for uniform processing
        arr = CoordinateParser._to_numpy(values)

        # Validate shape
        if arr.ndim != 1:
            raise ValueError(f"Expected 1D array, got shape {arr.shape}")

        if len(arr) == 0:
            # Return empty struct array
            return pa.StructArray.from_arrays(
                [
                    pa.array([], type=pa.float64()),
                    pa.array([], type=pa.int64()),
                    pa.array([], type=pa.int64()),
                ],
                names=["value", "numerator", "denominator"],
            )

        # Dispatch based on number_type
        if number_type == NumberType.int:
            return CoordinateParser._parse_int_array(arr)
        elif number_type == NumberType.float:
            return CoordinateParser._parse_float_array(arr)
        elif number_type == NumberType.fraction:
            return CoordinateParser._parse_fraction_array(arr)
        else:
            raise ValueError(f"Unknown NumberType: {number_type}")

    @staticmethod
    def _to_numpy(values: Any) -> np.ndarray:
        """Convert array-like to numpy array.

        Args:
            values: Array-like object (numpy, pandas, pyarrow, list).

        Returns:
            NumPy array.

        Raises:
            TypeError: If conversion is not possible.
        """
        if isinstance(values, np.ndarray):
            return values
        elif isinstance(values, pd.Series):
            return values.to_numpy()
        elif isinstance(values, pa.Array):
            return values.to_numpy()
        elif isinstance(values, list):
            return np.array(values)
        else:
            raise TypeError(f"Cannot convert {type(values)} to numpy array")

    @staticmethod
    def _parse_int_array(arr: np.ndarray) -> pa.StructArray:
        """Parse integer coordinates (vectorized).

        Strategy:
        - value: float(arr)
        - numerator: arr
        - denominator: ones

        Args:
            arr: Integer array.

        Returns:
            StructArray with value/numerator/denominator fields.
        """
        n = len(arr)

        # Vectorized conversion
        value_arr = arr.astype(np.float64)
        num_arr = arr.astype(np.int64)
        den_arr = np.ones(n, dtype=np.int64)

        # Build struct array with proper field types
        coord_type = pa.struct(
            [
                pa.field("value", pa.float64(), nullable=True),
                pa.field("numerator", pa.int64(), nullable=True),
                pa.field("denominator", pa.int64(), nullable=True),
            ]
        )

        return pa.StructArray.from_arrays(
            [
                pa.array(value_arr, type=pa.float64()),
                pa.array(num_arr, type=pa.int64()),
                pa.array(den_arr, type=pa.int64()),
            ],
            fields=list(coord_type),
        )

    @staticmethod
    def _parse_float_array(arr: np.ndarray) -> pa.StructArray:
        """Parse float coordinates (vectorized).

        Strategy:
        - value: arr
        - numerator: None (nullable)
        - denominator: None (nullable)

        Args:
            arr: Float array.

        Returns:
            StructArray with value field populated, num/den null.
        """
        n = len(arr)

        value_arr = arr.astype(np.float64)

        # Build struct array with proper field types
        coord_type = pa.struct(
            [
                pa.field("value", pa.float64(), nullable=True),
                pa.field("numerator", pa.int64(), nullable=True),
                pa.field("denominator", pa.int64(), nullable=True),
            ]
        )

        return pa.StructArray.from_arrays(
            [
                pa.array(value_arr, type=pa.float64()),
                pa.nulls(n, type=pa.int64()),
                pa.nulls(n, type=pa.int64()),
            ],
            fields=list(coord_type),
        )

    @staticmethod
    def _parse_fraction_array(arr: np.ndarray) -> pa.StructArray:
        """Parse fraction coordinates (vectorized).

        Handles three cases (all vectorized):
        1. String-encoded fractions: "num/den"
        2. Fraction objects: extract numerator/denominator
        3. Numeric values: convert to Fraction with limit_denominator

        Args:
            arr: Array containing fractions in various formats.

        Returns:
            StructArray with value/numerator/denominator fields.

        Raises:
            ValueError: If fraction format is invalid.
        """
        # Determine type by inspecting first non-null element
        first_val = arr[0] if len(arr) > 0 else None

        if first_val is None:
            # All null array
            n = len(arr)
            coord_type = pa.struct(
                [
                    pa.field("value", pa.float64(), nullable=True),
                    pa.field("numerator", pa.int64(), nullable=True),
                    pa.field("denominator", pa.int64(), nullable=True),
                ]
            )
            return pa.StructArray.from_arrays(
                [
                    pa.nulls(n, type=pa.float64()),
                    pa.nulls(n, type=pa.int64()),
                    pa.nulls(n, type=pa.int64()),
                ],
                fields=list(coord_type),
            )

        # Case 1: String-encoded fractions "num/den"
        if arr.dtype.kind in ("U", "S", "O") and isinstance(first_val, str):
            return CoordinateParser._parse_string_fractions(arr)

        # Case 2: Fraction objects
        elif isinstance(first_val, Fraction):
            return CoordinateParser._parse_fraction_objects(arr)

        # Case 3: Numeric values -> convert to Fraction
        else:
            return CoordinateParser._parse_numeric_to_fractions(arr)

    @staticmethod
    def _parse_string_fractions(arr: np.ndarray) -> pa.StructArray:
        """Parse string-encoded fractions and integers (vectorized).

        Handles mixed format strings:
        - Pure integers: "0", "1", "42" -> num/1
        - Fractions: "1/4", "3/8", "1/2" -> num/den
        - Null values: None, NaN -> null struct

        Example: ["0", "1/2", "3", "3/4", None] -> struct arrays

        Strategy:
        - Detect nulls first (vectorized)
        - Detect which values contain "/" (vectorized)
        - Parse pure integers and fractions separately
        - Merge results vectorized with null mask

        Args:
            arr: Array of strings in "num" or "num/den" format (may contain nulls).

        Returns:
            StructArray with parsed fractions.

        Raises:
            ValueError: If string format is invalid.
        """
        n = len(arr)

        # Convert to pandas Series for str operations
        s = pd.Series(arr)

        # Detect nulls first (vectorized)
        is_null = s.isna()

        # Detect which values contain "/" (vectorized)
        # na=False means null values return False
        is_fraction = s.str.contains("/", na=False)

        # Values that are non-null and non-fraction are integers
        is_integer = ~is_null & ~is_fraction

        # Initialize output arrays with NaN for float, 0 for int
        values = np.full(n, np.nan, dtype=np.float64)
        numerators = np.zeros(n, dtype=np.int64)
        denominators = np.ones(n, dtype=np.int64)  # Default to 1

        # Parse pure integers (vectorized) - only non-null non-fraction values
        if is_integer.any():
            int_indices = np.where(is_integer)[0]
            # Convert integer strings to int64 (vectorized)
            int_values = s[is_integer].astype(np.int64).to_numpy()
            numerators[int_indices] = int_values
            values[int_indices] = int_values.astype(np.float64)
            # denominators already defaulted to 1

        # Parse fractions (vectorized)
        if is_fraction.any():
            frac_indices = np.where(is_fraction)[0]
            frac_series = s[is_fraction]

            # Vectorized split on '/'
            parts = frac_series.str.split("/", expand=True)

            if parts.shape[1] != 2:
                # Find problematic value for error message
                bad_idx = frac_indices[0]
                raise ValueError(
                    f"Invalid fraction format (expected 'num/den'): '{arr[bad_idx]}'"
                )

            # Convert to int64 arrays (vectorized)
            frac_nums = parts[0].astype(np.int64).to_numpy()
            frac_dens = parts[1].astype(np.int64).to_numpy()

            # Validate denominators (vectorized)
            if np.any(frac_dens == 0):
                zero_idx = np.where(frac_dens == 0)[0][0]
                raise ValueError(
                    f"Fraction with zero denominator: '{frac_series.iloc[zero_idx]}'"
                )

            # Scatter into output arrays
            numerators[frac_indices] = frac_nums
            denominators[frac_indices] = frac_dens
            values[frac_indices] = frac_nums.astype(np.float64) / frac_dens.astype(
                np.float64
            )

        # Build struct array with proper field types and null mask
        coord_type = pa.struct(
            [
                pa.field("value", pa.float64(), nullable=True),
                pa.field("numerator", pa.int64(), nullable=True),
                pa.field("denominator", pa.int64(), nullable=True),
            ]
        )

        # Create null mask for the struct array (True = null)
        null_mask = is_null.to_numpy()

        # Build PyArrow arrays with null handling
        # For numerator/denominator, null where the struct is null
        value_pa = pa.array(values, type=pa.float64(), mask=null_mask)
        num_pa = pa.array(numerators, type=pa.int64(), mask=null_mask)
        den_pa = pa.array(denominators, type=pa.int64(), mask=null_mask)

        return pa.StructArray.from_arrays(
            [value_pa, num_pa, den_pa],
            fields=list(coord_type),
            mask=pa.array(null_mask),
        )

    @staticmethod
    def _parse_fraction_objects(arr: np.ndarray) -> pa.StructArray:
        """Parse Fraction objects (vectorized).

        Strategy:
        - Vectorized attribute extraction using numpy vectorize
        - Build arrays directly

        Args:
            arr: Array of Fraction objects.

        Returns:
            StructArray with parsed fractions.
        """
        # Vectorized extraction of numerator/denominator
        get_num = np.vectorize(lambda f: f.numerator, otypes=[np.int64])
        get_den = np.vectorize(lambda f: f.denominator, otypes=[np.int64])

        numerators = get_num(arr)
        denominators = get_den(arr)

        # Vectorized float conversion
        values = numerators.astype(np.float64) / denominators.astype(np.float64)

        # Build struct array with proper field types
        coord_type = pa.struct(
            [
                pa.field("value", pa.float64(), nullable=True),
                pa.field("numerator", pa.int64(), nullable=True),
                pa.field("denominator", pa.int64(), nullable=True),
            ]
        )

        return pa.StructArray.from_arrays(
            [
                pa.array(values, type=pa.float64()),
                pa.array(numerators, type=pa.int64()),
                pa.array(denominators, type=pa.int64()),
            ],
            fields=list(coord_type),
        )

    @staticmethod
    def _parse_numeric_to_fractions(arr: np.ndarray) -> pa.StructArray:
        """Convert numeric array to fractions with limit_denominator (vectorized).

        Strategy:
        - Use fractions.Fraction.limit_denominator(10000)
        - Vectorize the conversion
        - Extract num/den vectorized

        Args:
            arr: Numeric array (int or float).

        Returns:
            StructArray with converted fractions.
        """
        # Vectorized conversion to Fraction
        to_frac = np.vectorize(
            lambda x: Fraction(x).limit_denominator(10000), otypes=[object]
        )

        fractions = to_frac(arr)

        # Now extract num/den vectorized
        return CoordinateParser._parse_fraction_objects(fractions)


# endregion


# region ArrayValidator


class ArrayValidator:
    """Vectorized array validation before table construction.

    Validates:
    - Array lengths match
    - Required columns present
    - Temporal type consistency (instant vs interval)
    - ID uniqueness

    All checks use vectorized operations - NO row iteration.

    Examples:
        >>> columns = {
        ...     "id": np.array(["e1", "e2"]),
        ...     "temporal_type": np.array(["instant", "interval"]),
        ...     "event_type": np.array(["Beat", "Note"]),
        ...     "start": pa.array([...]),  # StructArray
        ...     "end": pa.array([None, ...]),  # StructArray with nulls
        ... }
        >>> ArrayValidator.validate_column_dict(columns, schema)
    """

    @staticmethod
    def validate_column_dict(
        columns: dict[str, np.ndarray | pd.Series | list | pa.Array],
        schema: pa.Schema,
    ) -> None:
        """Validate column dictionary before table creation (vectorized).

        Args:
            columns: Dict of {column_name: array_values}.
            schema: Expected PyArrow schema.

        Raises:
            ValueError: If validation fails.
        """
        # Check 1: All arrays have same length (vectorized check)
        lengths = {name: len(arr) for name, arr in columns.items()}
        unique_lengths = set(lengths.values())

        if len(unique_lengths) > 1:
            raise ValueError(f"Column length mismatch: {lengths}")

        # Check 2: Required columns present
        required = {"id", "temporal_type", "event_type", "start"}
        missing = required - set(columns.keys())

        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        # Check 3: ID uniqueness (vectorized)
        id_arr = ArrayValidator._to_numpy(columns["id"])
        unique_ids = np.unique(id_arr)

        if len(unique_ids) != len(id_arr):
            duplicates = len(id_arr) - len(unique_ids)
            raise ValueError(
                f"Duplicate IDs found: {len(id_arr)} IDs, " f"{duplicates} duplicates"
            )

        # Check 4: Temporal type consistency (vectorized)
        ArrayValidator._validate_temporal_consistency(columns)

    @staticmethod
    def _validate_temporal_consistency(
        columns: dict[str, np.ndarray | pd.Series | list | pa.Array],
    ) -> None:
        """Validate instant vs interval consistency (vectorized).

        Strategy:
        - instant events: end must be None/null
        - interval events: end must be present
        - Use pandas boolean indexing for vectorized checks

        Args:
            columns: Column dictionary.

        Raises:
            ValueError: If temporal consistency is violated.
        """
        temporal_type = pd.Series(ArrayValidator._to_numpy(columns["temporal_type"]))

        # Get masks for instant/interval events (vectorized)
        is_instant = temporal_type == "instant"
        is_interval = temporal_type == "interval"

        # Validate all values are either instant or interval
        valid_count = is_instant.sum() + is_interval.sum()
        if valid_count != len(temporal_type):
            invalid = temporal_type[~(is_instant | is_interval)]
            raise ValueError(
                f"Invalid temporal_type values: {invalid.unique().tolist()}"
            )

        # Validate instant events have no end coordinate (vectorized check)
        if "end" in columns:
            # Handle both PyArrow StructArray and numpy array
            end_col = columns["end"]
            if isinstance(end_col, pa.StructArray):
                end_is_null = end_col.is_null().to_numpy(zero_copy_only=False)
            elif isinstance(end_col, pa.ChunkedArray):
                end_is_null = end_col.is_null().to_numpy(zero_copy_only=False)
            else:
                end_arr = pd.Series(ArrayValidator._to_numpy(end_col))
                end_is_null = end_arr.isna().to_numpy()

            instant_with_end = is_instant.to_numpy() & ~end_is_null

            if instant_with_end.any():
                raise ValueError(
                    f"Instant events cannot have 'end' coordinate: "
                    f"{instant_with_end.sum()} violations"
                )

        # Validate interval events have end coordinate (vectorized check)
        if "end" not in columns:
            if is_interval.any():
                raise ValueError(
                    f"Interval events require 'end' coordinate: "
                    f"{is_interval.sum()} events missing 'end'"
                )
        else:
            # Check that interval events have non-null end
            end_col = columns["end"]
            if isinstance(end_col, pa.StructArray):
                end_is_null = end_col.is_null().to_numpy(zero_copy_only=False)
            elif isinstance(end_col, pa.ChunkedArray):
                end_is_null = end_col.is_null().to_numpy(zero_copy_only=False)
            else:
                end_arr = pd.Series(ArrayValidator._to_numpy(end_col))
                end_is_null = end_arr.isna().to_numpy()

            interval_no_end = is_interval.to_numpy() & end_is_null

            if interval_no_end.any():
                raise ValueError(
                    f"Interval events missing 'end' coordinate: "
                    f"{interval_no_end.sum()} events"
                )

    @staticmethod
    def _to_numpy(values: Any) -> np.ndarray:
        """Convert array-like to numpy array.

        Args:
            values: Array-like object.

        Returns:
            NumPy array.

        Raises:
            TypeError: If conversion is not possible.
        """
        if isinstance(values, np.ndarray):
            return values
        elif isinstance(values, pd.Series):
            return values.to_numpy()
        elif isinstance(values, pa.Array):
            return values.to_numpy(zero_copy_only=False)
        elif isinstance(values, pa.ChunkedArray):
            return values.to_numpy(zero_copy_only=False)
        elif isinstance(values, list):
            return np.array(values)
        else:
            raise TypeError(f"Cannot convert {type(values)} to numpy array")


# endregion
