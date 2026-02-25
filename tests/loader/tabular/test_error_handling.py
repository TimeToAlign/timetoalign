"""Error handling tests for vectorized TabularLoader.

This module validates graceful degradation and clear error messages
when loading malformed or invalid data.

Error Handling Philosophy:
1. Validation errors (block): Missing required columns, invalid file format
   - Raise ValueError with clear message including context
2. Data errors (warn + skip): Malformed rows, invalid coordinate values
   - Log warning, skip problematic data, continue processing
3. Type errors (attempt coercion, then error): Wrong type but convertible
   - Attempt automatic conversion, raise TypeError if fails
"""

from __future__ import annotations

from pathlib import Path

import pytest

from timetoalign.loader.tabular import CsvLoader, Ms3Loader, TabularLoader, TsvLoader

# region Missing Column Tests


class TestMissingColumnErrors:
    """Test clear errors when required columns are missing."""

    def test_missing_start_column_error(self, tmp_path: Path) -> None:
        """Validate clear error when 'start' column is missing."""
        # CSV with no 'start' column
        content = """id,name,event_type
e1,Beat1,Beat
e2,Beat2,Beat
"""
        path = tmp_path / "missing_start.csv"
        path.write_text(content)

        loader = CsvLoader()

        with pytest.raises(ValueError) as exc_info:
            loader.load(path)

        # Error message should include:
        # - Which column is missing
        # - Available columns
        error_msg = str(exc_info.value)
        assert "start" in error_msg.lower(), "Error should mention 'start' column"
        assert (
            "id" in error_msg or "Available" in error_msg
        ), "Error should list available columns"

    def test_missing_start_column_custom_loader(self, tmp_path: Path) -> None:
        """Validate error message includes custom column name."""

        class CustomLoader(TabularLoader):
            delimiter = ","
            start_column = "onset_time"

        content = """id,time,event_type
e1,0.0,Beat
"""
        path = tmp_path / "custom_loader.csv"
        path.write_text(content)

        loader = CustomLoader()

        with pytest.raises(ValueError) as exc_info:
            loader.load(path)

        error_msg = str(exc_info.value)
        assert (
            "onset_time" in error_msg
        ), "Error should mention custom column name 'onset_time'"


# endregion


# region File Not Found Tests


class TestFileNotFoundErrors:
    """Test clear errors when file doesn't exist."""

    def test_file_not_found_error(self) -> None:
        """Validate clear error when file doesn't exist."""
        loader = CsvLoader()

        with pytest.raises(FileNotFoundError) as exc_info:
            loader.load(Path("/nonexistent/path/to/file.csv"))

        error_msg = str(exc_info.value)
        assert "file.csv" in error_msg or "not found" in error_msg.lower()

    def test_directory_instead_of_file_error(self, tmp_path: Path) -> None:
        """Validate error when path is a directory, not a file."""
        loader = CsvLoader()

        # tmp_path is a directory - pandas open() raises IsADirectoryError
        with pytest.raises(IsADirectoryError):
            loader.load(tmp_path)


# endregion


# region Empty File Tests


class TestEmptyFileHandling:
    """Test handling of empty or minimal files."""

    def test_empty_file_returns_empty_events(self, tmp_path: Path) -> None:
        """Validate empty file doesn't crash, returns empty EventData."""
        # Header-only file
        content = "start,end,event_type\n"

        path = tmp_path / "empty.csv"
        path.write_text(content)

        loader = CsvLoader()
        loader.load(path)

        # Should succeed with 0 events
        assert len(loader.events) == 0

    def test_single_row_file(self, tmp_path: Path) -> None:
        """Validate file with single data row works correctly."""
        content = """start,end,event_type
0.0,1.0,Note
"""
        path = tmp_path / "single_row.csv"
        path.write_text(content)

        loader = CsvLoader()
        loader.load(path)

        assert len(loader.events) == 1
        assert loader.events.coordinate_range() == (0.0, 1.0)


# endregion


# region Invalid Coordinate Format Tests


class TestInvalidCoordinateErrors:
    """Test handling of invalid coordinate formats."""

    def test_non_numeric_start_value_error(self, tmp_path: Path) -> None:
        """Validate clear error on non-numeric start values."""
        content = """start,event_type
abc,Note
1.0,Note
"""
        path = tmp_path / "non_numeric.csv"
        path.write_text(content)

        loader = CsvLoader()

        # Should raise error on 'abc' which cannot be converted to float
        with pytest.raises((ValueError, TypeError)):
            loader.load(path)

    def test_invalid_fraction_format_error(self, tmp_path: Path) -> None:
        """Validate clear error on invalid fraction format."""
        # TSV content with tab delimiter (Ms3Loader uses tab)
        # Ms3Loader uses quarterbeats_all_endings as primary column
        content = "quarterbeats_all_endings\tduration\n1/2/3\t1/4\n1/4\t1/8\n"

        path = tmp_path / "invalid_fraction.tsv"
        path.write_text(content)

        loader = Ms3Loader()

        with pytest.raises(ValueError) as exc_info:
            loader.load(path)

        error_msg = str(exc_info.value)
        assert "fraction" in error_msg.lower() or "1/2/3" in error_msg

    def test_zero_denominator_error(self, tmp_path: Path) -> None:
        """Validate clear error on zero denominator in fractions."""
        # TSV content with tab delimiter
        # Ms3Loader uses quarterbeats_all_endings as primary column
        content = "quarterbeats_all_endings\tduration\n1/0\t1/4\n"

        path = tmp_path / "zero_denom.tsv"
        path.write_text(content)

        loader = Ms3Loader()

        with pytest.raises(ValueError) as exc_info:
            loader.load(path)

        error_msg = str(exc_info.value)
        assert "zero" in error_msg.lower() or "denominator" in error_msg.lower()


# endregion


# region Null Value Handling Tests


class TestNullValueHandling:
    """Test handling of null/missing values in data."""

    def test_null_start_values_error(self, tmp_path: Path) -> None:
        """Validate that null start values raise an error.

        Null start coordinates are invalid for fraction parsing.
        The loader should raise a clear error rather than silently failing.
        """
        # TSV content with tab delimiter - second row has null start
        content = "quarterbeats\tduration_qb\tname\n0\t1.0\tnote1\n\t0.5\tnull_start\n1\t1.0\tnote2\n"

        path = tmp_path / "null_start.tsv"
        path.write_text(content)

        loader = Ms3Loader()

        # Should raise error on null start coordinate
        with pytest.raises(ValueError):
            loader.load(path)

    def test_null_duration_creates_instant(self, tmp_path: Path) -> None:
        """Validate null duration creates instant event."""
        # TSV content with tab delimiter - uses quarterbeats_all_endings and duration (fraction)
        content = (
            "quarterbeats_all_endings\tduration\tname\n0\t1/4\tinterval_note\n1\t\t"
            "instant_note\n2\t1/4\tanother_interval\n"
        )

        path = tmp_path / "null_duration.tsv"
        path.write_text(content)

        loader = Ms3Loader()
        loader.load(path)

        assert len(loader.events) == 3

        types = loader.count_events_by_temporal_type()
        # One event should be instant (null duration)
        assert types.get("instant", 0) == 1


# endregion


# region Multiple Sources Error Tests


class TestMultipleSourcesErrors:
    """Test error handling when loading multiple files."""

    def test_some_files_missing(self, tmp_path: Path) -> None:
        """Validate clear error when some files in batch are missing."""
        content = "start,event_type\n0.0,Note\n"

        valid_path = tmp_path / "valid.csv"
        valid_path.write_text(content)

        invalid_path = Path("/nonexistent/missing.csv")

        loader = CsvLoader()

        with pytest.raises(FileNotFoundError):
            loader.load(valid_path, invalid_path)

    def test_first_file_valid_second_invalid(self, tmp_path: Path) -> None:
        """Validate processing stops on first invalid file."""
        valid_content = "start,event_type\n0.0,Note\n"
        invalid_content = "invalid,columns\nabc,xyz\n"

        valid_path = tmp_path / "valid.csv"
        valid_path.write_text(valid_content)

        invalid_path = tmp_path / "invalid.csv"
        invalid_path.write_text(invalid_content)

        loader = CsvLoader()

        # Should fail on second file (missing 'start' column)
        with pytest.raises(ValueError):
            loader.load(valid_path, invalid_path)


# endregion


# region Delimiter Mismatch Tests


class TestDelimiterMismatchHandling:
    """Test handling of delimiter mismatches."""

    def test_csv_loader_on_tsv_file(self, tmp_path: Path) -> None:
        """Validate behavior when CSV loader loads TSV file."""
        # Tab-separated content loaded with comma delimiter
        content = "start\tend\tevent_type\n0.0\t1.0\tNote\n"

        path = tmp_path / "mismatch.tsv"
        path.write_text(content)

        loader = CsvLoader()  # Uses comma delimiter

        # Should fail because it can't find 'start' column
        # (the whole line becomes one column)
        with pytest.raises(ValueError) as exc_info:
            loader.load(path)

        error_msg = str(exc_info.value)
        assert "start" in error_msg.lower()

    def test_tsv_loader_on_csv_file(self, tmp_path: Path) -> None:
        """Validate behavior when TSV loader loads CSV file."""
        content = "start,end,event_type\n0.0,1.0,Note\n"

        path = tmp_path / "mismatch.csv"
        path.write_text(content)

        loader = TsvLoader()  # Uses tab delimiter

        # Should fail because 'start' column not found
        with pytest.raises(ValueError) as exc_info:
            loader.load(path)

        error_msg = str(exc_info.value)
        assert "start" in error_msg.lower()


# endregion
