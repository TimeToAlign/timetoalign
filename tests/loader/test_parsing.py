"""Comprehensive unit tests for CoordinateParser and ArrayValidator.

Tests the vectorized coordinate parsing and array validation infrastructure
that enables zero-iteration table construction.
"""

from __future__ import annotations

from fractions import Fraction

import numpy as np
import pandas as pd
import pyarrow as pa
import pytest

from timetoalign.core import NumberType, TimeUnit
from timetoalign.storage.parsing import ArrayValidator, CoordinateParser

# region CoordinateParser Tests


class TestCoordinateParserInt:
    """Test vectorized integer coordinate parsing."""

    def test_parse_int_array_small(self):
        """Parse small integer array."""
        arr = np.array([0, 1, 2, 3, 4])
        result = CoordinateParser.parse(arr, NumberType.int, TimeUnit.ticks)

        assert isinstance(result, pa.StructArray)
        assert len(result) == 5

        # Check structure
        values = result.field("value").to_pylist()
        nums = result.field("numerator").to_pylist()
        dens = result.field("denominator").to_pylist()

        assert values == [0.0, 1.0, 2.0, 3.0, 4.0]
        assert nums == [0, 1, 2, 3, 4]
        assert dens == [1, 1, 1, 1, 1]

    def test_parse_int_array_large(self):
        """Parse large integer array (100k elements)."""
        arr = np.arange(100000, dtype=np.int64)
        result = CoordinateParser.parse(arr, NumberType.int, TimeUnit.ticks)

        assert isinstance(result, pa.StructArray)
        assert len(result) == 100000

        # Spot checks
        assert result.field("value")[0].as_py() == 0.0
        assert result.field("numerator")[0].as_py() == 0
        assert result.field("denominator")[0].as_py() == 1

        assert result.field("value")[99999].as_py() == 99999.0
        assert result.field("numerator")[99999].as_py() == 99999
        assert result.field("denominator")[99999].as_py() == 1

    def test_parse_int_array_from_list(self):
        """Parse integer array from Python list."""
        lst = [0, 10, 20, 30]
        result = CoordinateParser.parse(lst, NumberType.int, TimeUnit.ticks)

        assert isinstance(result, pa.StructArray)
        assert len(result) == 4
        assert result.field("numerator").to_pylist() == [0, 10, 20, 30]

    def test_parse_int_array_from_pandas(self):
        """Parse integer array from pandas Series."""
        series = pd.Series([5, 10, 15, 20, 25])
        result = CoordinateParser.parse(series, NumberType.int, TimeUnit.ticks)

        assert isinstance(result, pa.StructArray)
        assert len(result) == 5
        assert result.field("numerator").to_pylist() == [5, 10, 15, 20, 25]


class TestCoordinateParserFloat:
    """Test vectorized float coordinate parsing."""

    def test_parse_float_array_small(self):
        """Parse small float array."""
        arr = np.array([0.0, 1.5, 3.14, 2.718])
        result = CoordinateParser.parse(arr, NumberType.float, TimeUnit.seconds)

        assert isinstance(result, pa.StructArray)
        assert len(result) == 4

        values = result.field("value").to_pylist()
        nums = result.field("numerator").to_pylist()
        dens = result.field("denominator").to_pylist()

        assert values == [0.0, 1.5, 3.14, 2.718]
        assert nums == [None, None, None, None]  # Floats have null num/den
        assert dens == [None, None, None, None]

    def test_parse_float_array_large(self):
        """Parse large float array (100k elements)."""
        arr = np.linspace(0, 100, 100000)
        result = CoordinateParser.parse(arr, NumberType.float, TimeUnit.seconds)

        assert isinstance(result, pa.StructArray)
        assert len(result) == 100000

        # np.linspace(0, 100, 100000) produces exactly 0.0 and 100.0 at boundaries
        assert result.field("value")[0].as_py() == 0.0
        assert result.field("value")[99999].as_py() == 100.0

        # All numerators should be null
        assert result.field("numerator").null_count == 100000

    def test_parse_float_array_with_nan(self):
        """Parse float array containing NaN values."""
        arr = np.array([0.0, np.nan, 2.0, np.nan, 4.0])
        result = CoordinateParser.parse(arr, NumberType.float, TimeUnit.seconds)

        assert isinstance(result, pa.StructArray)
        assert len(result) == 5

        values = result.field("value").to_pylist()
        # NaN is preserved in float values
        assert values[0] == 0.0
        assert np.isnan(values[1])
        assert values[2] == 2.0


class TestCoordinateParserFraction:
    """Test vectorized fraction coordinate parsing."""

    def test_parse_string_fractions_simple(self):
        """Parse string-encoded fractions."""
        arr = np.array(["1/4", "3/8", "1/2", "5/4"])
        result = CoordinateParser.parse(arr, NumberType.fraction, TimeUnit.quarters)

        assert isinstance(result, pa.StructArray)
        assert len(result) == 4

        values = result.field("value").to_pylist()
        nums = result.field("numerator").to_pylist()
        dens = result.field("denominator").to_pylist()

        assert values == [0.25, 0.375, 0.5, 1.25]
        assert nums == [1, 3, 1, 5]
        assert dens == [4, 8, 2, 4]

    def test_parse_string_fractions_large(self):
        """Parse large array of string fractions."""
        # Create 10k string fractions
        fracs = [f"{i}/4" for i in range(10000)]
        result = CoordinateParser.parse(fracs, NumberType.fraction, TimeUnit.quarters)

        assert isinstance(result, pa.StructArray)
        assert len(result) == 10000

        # Spot checks
        assert result.field("numerator")[0].as_py() == 0
        assert result.field("denominator")[0].as_py() == 4
        assert result.field("value")[0].as_py() == 0.0

        assert result.field("numerator")[9999].as_py() == 9999
        assert result.field("denominator")[9999].as_py() == 4
        # 9999/4 = 2499.75, exactly representable in float64
        assert result.field("value")[9999].as_py() == 9999 / 4

    def test_parse_fraction_objects(self):
        """Parse Fraction objects."""
        arr = np.array([Fraction(1, 4), Fraction(3, 8), Fraction(1, 2)], dtype=object)
        result = CoordinateParser.parse(arr, NumberType.fraction, TimeUnit.quarters)

        assert isinstance(result, pa.StructArray)
        assert len(result) == 3

        nums = result.field("numerator").to_pylist()
        dens = result.field("denominator").to_pylist()

        assert nums == [1, 3, 1]
        assert dens == [4, 8, 2]

    def test_parse_numeric_to_fractions(self):
        """Parse numeric values as fractions with limit_denominator."""
        arr = np.array([0.25, 0.5, 0.75, 1.0])
        result = CoordinateParser.parse(arr, NumberType.fraction, TimeUnit.quarters)

        assert isinstance(result, pa.StructArray)
        assert len(result) == 4

        nums = result.field("numerator").to_pylist()
        dens = result.field("denominator").to_pylist()

        # Should produce exact fractions
        assert nums == [1, 1, 3, 1]
        assert dens == [4, 2, 4, 1]

    def test_parse_string_fractions_invalid_format(self):
        """Test error on invalid fraction format."""
        # "1/2/3" contains "/" so it's parsed as fraction but has too many parts
        arr = np.array(["1/2/3", "3/4"])

        with pytest.raises(ValueError, match="Invalid fraction format"):
            CoordinateParser.parse(arr, NumberType.fraction, TimeUnit.quarters)

    def test_parse_string_fractions_invalid_integer(self):
        """Test error on invalid integer format in mixed array."""
        # "invalid" is treated as pure integer (no "/") but cannot be parsed
        arr = np.array(["1/2", "invalid"])

        with pytest.raises(ValueError):
            CoordinateParser.parse(arr, NumberType.fraction, TimeUnit.quarters)

    def test_parse_string_fractions_zero_denominator(self):
        """Test error on zero denominator."""
        arr = np.array(["1/0", "2/3"])

        with pytest.raises(ValueError, match="zero denominator"):
            CoordinateParser.parse(arr, NumberType.fraction, TimeUnit.quarters)


class TestCoordinateParserEdgeCases:
    """Test edge cases in coordinate parsing."""

    def test_parse_empty_array(self):
        """Parse empty array."""
        arr = np.array([])
        result = CoordinateParser.parse(arr, NumberType.int, TimeUnit.ticks)

        assert isinstance(result, pa.StructArray)
        assert len(result) == 0

    def test_parse_single_element(self):
        """Parse single-element array."""
        arr = np.array([42])
        result = CoordinateParser.parse(arr, NumberType.int, TimeUnit.ticks)

        assert isinstance(result, pa.StructArray)
        assert len(result) == 1
        assert result.field("value")[0].as_py() == 42.0

    def test_parse_invalid_number_type(self):
        """Test error on invalid NumberType."""
        arr = np.array([1, 2, 3])

        with pytest.raises(ValueError, match="Unknown NumberType"):
            CoordinateParser.parse(arr, "invalid", TimeUnit.ticks)  # type: ignore

    def test_parse_2d_array_error(self):
        """Test error on 2D array."""
        arr = np.array([[1, 2], [3, 4]])

        with pytest.raises(ValueError, match="Expected 1D array"):
            CoordinateParser.parse(arr, NumberType.int, TimeUnit.ticks)

    def test_to_numpy_with_pyarrow_array(self):
        """Test _to_numpy with PyArrow array input."""
        pa_arr = pa.array([1, 2, 3])
        result = CoordinateParser._to_numpy(pa_arr)

        assert isinstance(result, np.ndarray)
        assert list(result) == [1, 2, 3]

    def test_to_numpy_invalid_type(self):
        """Test _to_numpy with invalid type."""
        with pytest.raises(TypeError, match="Cannot convert"):
            CoordinateParser._to_numpy({"invalid": "type"})


# endregion


# region ArrayValidator Tests


class TestArrayValidatorBasic:
    """Test basic array validation."""

    def test_validate_valid_column_dict(self):
        """Validate a valid field dictionary."""
        coord_type = pa.struct(
            [
                pa.field("value", pa.float64()),
                pa.field("numerator", pa.int64()),
                pa.field("denominator", pa.int64()),
            ]
        )

        schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("temporal_type", pa.string()),
                pa.field("event_type", pa.string()),
                pa.field("start", coord_type),
                pa.field("end", coord_type),
            ]
        )

        columns = {
            "id": np.array(["e1", "e2", "e3"]),
            "temporal_type": np.array(["instant", "instant", "interval"]),
            "event_type": np.array(["Beat", "Beat", "Note"]),
            "start": CoordinateParser.parse([0, 1, 2], NumberType.int, TimeUnit.ticks),
            "end": pa.StructArray.from_arrays(
                [
                    pa.array([None, None, 3.0]),
                    pa.array([None, None, 3], type=pa.int64()),
                    pa.array([None, None, 1], type=pa.int64()),
                ],
                names=["value", "numerator", "denominator"],
                mask=pa.array([True, True, False]),  # First two are null (instants)
            ),
        }

        # Should not raise
        ArrayValidator.validate_field_dict(columns, schema)

    def test_validate_length_mismatch(self):
        """Test error on field length mismatch."""
        schema = pa.schema([pa.field("id", pa.string())])

        columns = {
            "id": np.array(["e1", "e2"]),
            "temporal_type": np.array(
                ["instant", "instant", "interval"]
            ),  # Wrong length
        }

        with pytest.raises(ValueError, match="Field length mismatch"):
            ArrayValidator.validate_field_dict(columns, schema)

    def test_validate_missing_required_columns(self):
        """Test error on missing required fields."""
        schema = pa.schema([pa.field("id", pa.string())])

        columns = {
            "id": np.array(["e1", "e2"]),
            # Missing: temporal_type, event_type, start
        }

        with pytest.raises(ValueError, match="Missing required fields"):
            ArrayValidator.validate_field_dict(columns, schema)

    def test_validate_duplicate_ids(self):
        """Test error on duplicate IDs."""
        schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("temporal_type", pa.string()),
                pa.field("event_type", pa.string()),
                pa.field(
                    "start",
                    pa.struct(
                        [
                            pa.field("value", pa.float64()),
                            pa.field("numerator", pa.int64()),
                            pa.field("denominator", pa.int64()),
                        ]
                    ),
                ),
            ]
        )

        columns = {
            "id": np.array(["e1", "e2", "e1"]),  # Duplicate "e1"
            "temporal_type": np.array(["instant", "instant", "instant"]),
            "event_type": np.array(["Beat", "Beat", "Beat"]),
            "start": CoordinateParser.parse([0, 1, 2], NumberType.int, TimeUnit.ticks),
        }

        with pytest.raises(ValueError, match="Duplicate IDs found"):
            ArrayValidator.validate_field_dict(columns, schema)


class TestArrayValidatorTemporalConsistency:
    """Test temporal type consistency validation."""

    def test_validate_instant_without_end(self):
        """Validate instant events without end coordinate (valid)."""
        schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("temporal_type", pa.string()),
                pa.field("event_type", pa.string()),
                pa.field(
                    "start",
                    pa.struct(
                        [
                            pa.field("value", pa.float64()),
                            pa.field("numerator", pa.int64()),
                            pa.field("denominator", pa.int64()),
                        ]
                    ),
                ),
                pa.field(
                    "end",
                    pa.struct(
                        [
                            pa.field("value", pa.float64()),
                            pa.field("numerator", pa.int64()),
                            pa.field("denominator", pa.int64()),
                        ]
                    ),
                ),
            ]
        )

        # Create struct type for coordinates
        coord_type = pa.struct(
            [
                pa.field("value", pa.float64()),
                pa.field("numerator", pa.int64()),
                pa.field("denominator", pa.int64()),
            ]
        )

        columns = {
            "id": np.array(["e1", "e2"]),
            "temporal_type": np.array(["instant", "instant"]),
            "event_type": np.array(["Beat", "Beat"]),
            "start": CoordinateParser.parse([0, 1], NumberType.int, TimeUnit.ticks),
            "end": pa.nulls(2, type=coord_type),  # Null ends for instants
        }

        # Should not raise
        ArrayValidator.validate_field_dict(columns, schema)

    def test_validate_instant_with_end_error(self):
        """Test error when instant events have end coordinate."""
        schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("temporal_type", pa.string()),
                pa.field("event_type", pa.string()),
                pa.field(
                    "start",
                    pa.struct(
                        [
                            pa.field("value", pa.float64()),
                            pa.field("numerator", pa.int64()),
                            pa.field("denominator", pa.int64()),
                        ]
                    ),
                ),
                pa.field(
                    "end",
                    pa.struct(
                        [
                            pa.field("value", pa.float64()),
                            pa.field("numerator", pa.int64()),
                            pa.field("denominator", pa.int64()),
                        ]
                    ),
                ),
            ]
        )

        columns = {
            "id": np.array(["e1", "e2"]),
            "temporal_type": np.array(["instant", "instant"]),
            "event_type": np.array(["Beat", "Beat"]),
            "start": CoordinateParser.parse([0, 1], NumberType.int, TimeUnit.ticks),
            "end": CoordinateParser.parse(
                [1, 2], NumberType.int, TimeUnit.ticks
            ),  # Invalid!
        }

        with pytest.raises(ValueError, match="Instant events cannot have 'end'"):
            ArrayValidator.validate_field_dict(columns, schema)

    def test_validate_interval_without_end_error(self):
        """Test error when interval events missing end coordinate."""
        schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("temporal_type", pa.string()),
                pa.field("event_type", pa.string()),
                pa.field(
                    "start",
                    pa.struct(
                        [
                            pa.field("value", pa.float64()),
                            pa.field("numerator", pa.int64()),
                            pa.field("denominator", pa.int64()),
                        ]
                    ),
                ),
            ]
        )

        columns = {
            "id": np.array(["e1", "e2"]),
            "temporal_type": np.array(["interval", "interval"]),
            "event_type": np.array(["Note", "Note"]),
            "start": CoordinateParser.parse([0, 1], NumberType.int, TimeUnit.ticks),
            # Missing 'end' field
        }

        with pytest.raises(ValueError, match="Interval events require 'end'"):
            ArrayValidator.validate_field_dict(columns, schema)

    def test_validate_invalid_temporal_type(self):
        """Test error on invalid temporal_type values."""
        schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("temporal_type", pa.string()),
                pa.field("event_type", pa.string()),
                pa.field(
                    "start",
                    pa.struct(
                        [
                            pa.field("value", pa.float64()),
                            pa.field("numerator", pa.int64()),
                            pa.field("denominator", pa.int64()),
                        ]
                    ),
                ),
            ]
        )

        columns = {
            "id": np.array(["e1", "e2"]),
            "temporal_type": np.array(["instant", "invalid"]),  # Invalid value
            "event_type": np.array(["Beat", "Beat"]),
            "start": CoordinateParser.parse([0, 1], NumberType.int, TimeUnit.ticks),
        }

        with pytest.raises(ValueError, match="Invalid temporal_type values"):
            ArrayValidator.validate_field_dict(columns, schema)


class TestArrayValidatorHelpers:
    """Test ArrayValidator helper methods."""

    def test_to_numpy_with_numpy_array(self):
        """Test _to_numpy with numpy array."""
        arr = np.array([1, 2, 3])
        result = ArrayValidator._to_numpy(arr)
        assert isinstance(result, np.ndarray)
        assert list(result) == [1, 2, 3]

    def test_to_numpy_with_pandas_series(self):
        """Test _to_numpy with pandas Series."""
        series = pd.Series([1, 2, 3])
        result = ArrayValidator._to_numpy(series)
        assert isinstance(result, np.ndarray)
        assert list(result) == [1, 2, 3]

    def test_to_numpy_with_pyarrow_array(self):
        """Test _to_numpy with PyArrow array."""
        pa_arr = pa.array([1, 2, 3])
        result = ArrayValidator._to_numpy(pa_arr)
        assert isinstance(result, np.ndarray)
        assert list(result) == [1, 2, 3]

    def test_to_numpy_with_list(self):
        """Test _to_numpy with list."""
        lst = [1, 2, 3]
        result = ArrayValidator._to_numpy(lst)
        assert isinstance(result, np.ndarray)
        assert list(result) == [1, 2, 3]

    def test_to_numpy_invalid_type(self):
        """Test _to_numpy with invalid type."""
        with pytest.raises(TypeError, match="Cannot convert"):
            ArrayValidator._to_numpy({"invalid": "type"})


# endregion
