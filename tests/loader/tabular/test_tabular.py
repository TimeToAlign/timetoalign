"""Tests for TabularLoader, CsvLoader, and TsvLoader."""

from __future__ import annotations

from pathlib import Path

import pytest

from timetoalign.core import NumberType, TimeUnit
from timetoalign.loader.tabular import CsvLoader, TabularLoader, TsvLoader

# region Test Fixtures


@pytest.fixture
def csv_file(tmp_path: Path) -> Path:
    """Create a temporary CSV file for testing."""
    content = """id,start,end,event_type,name
e1,0.0,1.0,Note,first
e2,1.0,2.5,Note,second
e3,2.5,,Beat,downbeat
"""
    path = tmp_path / "test.csv"
    path.write_text(content)
    return path


@pytest.fixture
def tsv_file(tmp_path: Path) -> Path:
    """Create a temporary TSV file for testing."""
    content = """id\tstart\tend\tevent_type\tname
e1\t0.0\t1.0\tNote\tfirst
e2\t1.0\t2.5\tNote\tsecond
e3\t2.5\t\tBeat\tdownbeat
"""
    path = tmp_path / "test.tsv"
    path.write_text(content)
    return path


@pytest.fixture
def minimal_csv(tmp_path: Path) -> Path:
    """Create a minimal CSV with only start column."""
    content = """start
0.0
1.0
2.0
"""
    path = tmp_path / "minimal.csv"
    path.write_text(content)
    return path


# endregion


# region CsvLoader Tests


class TestCsvLoader:
    """Tests for CsvLoader."""

    def test_load_basic_csv(self, csv_file: Path):
        """Test loading a basic CSV file."""
        loader = CsvLoader()
        loader.load(csv_file)

        assert len(loader) == 3
        assert len(loader.sources) == 1

    def test_event_types(self, csv_file: Path):
        """Test that event types are correctly parsed."""
        loader = CsvLoader()
        loader.load(csv_file)

        types = loader.count_events_by_type()
        assert types.get("Note", 0) == 2
        assert types.get("Beat", 0) == 1

    def test_temporal_types(self, csv_file: Path):
        """Test that temporal types are correctly inferred."""
        loader = CsvLoader()
        loader.load(csv_file)

        types = loader.count_events_by_temporal_type()
        assert types.get("interval", 0) == 2  # Notes with start/end
        assert types.get("instant", 0) == 1  # Beat without end

    def test_coordinate_range(self, csv_file: Path):
        """Test coordinate range calculation."""
        loader = CsvLoader()
        loader.load(csv_file)

        coord_range = loader.events.coordinate_range()
        assert coord_range is not None
        assert coord_range[0] == 0.0
        assert coord_range[1] == 2.5

    def test_minimal_csv(self, minimal_csv: Path):
        """Test loading CSV with only required columns."""
        loader = CsvLoader()
        loader.load(minimal_csv)

        assert len(loader) == 3
        # All events should be instants (no end column)
        types = loader.count_events_by_temporal_type()
        assert types.get("instant", 0) == 3

    def test_missing_start_column_raises(self, tmp_path: Path):
        """Test that missing start column raises ValueError."""
        content = """id,end,name
e1,1.0,test
"""
        path = tmp_path / "no_start.csv"
        path.write_text(content)

        loader = CsvLoader()
        with pytest.raises(ValueError, match="Required column.*start.*not found"):
            loader.load(path)


# endregion


# region TsvLoader Tests


class TestTsvLoader:
    """Tests for TsvLoader."""

    def test_load_basic_tsv(self, tsv_file: Path):
        """Test loading a basic TSV file."""
        loader = TsvLoader()
        loader.load(tsv_file)

        assert len(loader) == 3
        assert loader.metadata["source_count"] == 1

    def test_delimiter_is_tab(self):
        """Test that TsvLoader uses tab as delimiter."""
        assert TsvLoader.delimiter == "\t"

    def test_event_summary(self, tsv_file: Path):
        """Test event summary generation."""
        loader = TsvLoader()
        loader.load(tsv_file)

        summary = loader.event_summary()
        assert summary["sources"] == [str(tsv_file)]
        assert "event_types" in summary


# endregion


# region Custom TabularLoader Tests


class TestCustomTabularLoader:
    """Tests for custom TabularLoader subclasses."""

    def test_custom_column_mapping(self, tmp_path: Path):
        """Test custom column mapping via subclass."""

        class CustomLoader(TabularLoader):
            delimiter = ","
            start_column = "onset"
            end_column = "offset"
            id_column = "note_id"
            extra_columns = {"pitch": "midi_note"}

        content = """note_id,onset,offset,midi_note
n1,0.0,1.0,60
n2,1.0,2.0,62
"""
        path = tmp_path / "custom.csv"
        path.write_text(content)

        loader = CustomLoader()
        loader.load(path)

        assert len(loader) == 2
        # Check that custom ID was used
        events = list(loader.events)
        assert events[0]["id"] == "n1"
        assert events[1]["id"] == "n2"

    def test_custom_coordinate_unit(self, tmp_path: Path):
        """Test custom coordinate unit."""

        class TickLoader(TabularLoader):
            start_column = "tick"
            _default_unit = TimeUnit.ticks
            coordinate_type = NumberType.int

        content = """tick
0
480
960
"""
        path = tmp_path / "ticks.csv"
        path.write_text(content)

        loader = TickLoader()
        loader.load(path)

        assert loader.unit == TimeUnit.ticks
        assert loader.number_type == NumberType.int


# endregion
