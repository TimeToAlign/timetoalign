"""Tests for the new TableSchema semantic field specification system.

This module tests the comprehensive TableSchema that supports:
1. Timeline creation defaults
2. Coordinate specifications (start, end, duration, instant)
3. C-Map fields for coordinate conversion
4. Partition fields for multiple timelines
5. Hierarchy fields for parent-child relationships
6. Region fields for named TimeIntervals
7. Match fields for alignment references
"""

from __future__ import annotations

import pandas as pd
import pytest

from timetoalign.core import NumberType, TimeUnit
from timetoalign.core.enums import ColumnRole, PartitionMode
from timetoalign.loader.table_schema import (
    CMapField,
    CoordinateSpec,
    PartitionSpec,
    RegionSpec,
    TableSchema,
    TimelineDefaults,
)

# region Test Data Fixtures


@pytest.fixture
def simple_df() -> pd.DataFrame:
    """Simple DataFrame with onset/offset in seconds."""
    return pd.DataFrame(
        {
            "id": ["e1", "e2", "e3", "e4"],
            "name": ["Note A", "Note B", "Note C", "Note D"],
            "onset_sec": [0.0, 1.0, 2.0, 3.0],
            "offset_sec": [0.5, 1.5, 2.5, 3.5],
            "pitch": [60, 62, 64, 65],
        }
    )


@pytest.fixture
def multiunit_df() -> pd.DataFrame:
    """DataFrame with both seconds and beats (for C-Map testing)."""
    return pd.DataFrame(
        {
            "id": ["e1", "e2", "e3", "e4"],
            "onset_sec": [0.0, 0.5, 1.0, 1.5],
            "onset_beat": [0.0, 1.0, 2.0, 3.0],  # 2 beats per second
            "offset_sec": [0.25, 0.75, 1.25, 1.75],
            "offset_beat": [0.5, 1.5, 2.5, 3.5],
            "pitch": [60, 62, 64, 65],
        }
    )


@pytest.fixture
def partitioned_df() -> pd.DataFrame:
    """DataFrame with voice column for partitioning."""
    return pd.DataFrame(
        {
            "id": ["s1", "s2", "a1", "a2", "t1", "b1"],
            "onset": [0.0, 1.0, 0.0, 1.0, 0.5, 0.5],
            "offset": [0.5, 1.5, 0.5, 1.5, 1.0, 1.0],
            "voice": ["soprano", "soprano", "alto", "alto", "tenor", "bass"],
            "pitch": [72, 74, 60, 62, 64, 48],
        }
    )


@pytest.fixture
def region_df() -> pd.DataFrame:
    """DataFrame with region column."""
    return pd.DataFrame(
        {
            "id": ["e1", "e2", "e3", "e4", "e5", "e6"],
            "onset": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
            "offset": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "section": ["Intro", "Intro", "Verse", "Verse", "Chorus", "Chorus"],
        }
    )


# endregion


# region TimelineDefaults Tests


class TestTimelineDefaults:
    """Tests for TimelineDefaults dataclass."""

    def test_default_values(self) -> None:
        """Test that defaults are sensible."""
        defaults = TimelineDefaults()
        assert defaults.unit == TimeUnit.seconds
        assert defaults.number_type == NumberType.float
        assert defaults.default_event_type == "Event"
        assert defaults.id_prefix == "tl"
        assert defaults.locked is False

    def test_custom_values(self) -> None:
        """Test custom timeline defaults."""
        defaults = TimelineDefaults(
            unit=TimeUnit.quarters,
            number_type=NumberType.fraction,
            default_event_type="Note",
            id_prefix="score",
        )
        assert defaults.unit == TimeUnit.quarters
        assert defaults.number_type == NumberType.fraction
        assert defaults.default_event_type == "Note"
        assert defaults.id_prefix == "score"


# endregion


# region CoordinateSpec Tests


class TestCoordinateSpec:
    """Tests for CoordinateSpec dataclass."""

    def test_basic_interval_spec(self) -> None:
        """Test basic interval coordinate spec."""
        spec = CoordinateSpec(start="onset", end="offset")
        assert spec.start == "onset"
        assert spec.end == "offset"
        assert spec.duration is None
        assert spec.instant is None

    def test_duration_spec(self) -> None:
        """Test duration-based spec (end computed from duration)."""
        spec = CoordinateSpec(start="onset", duration="length")
        assert spec.start == "onset"
        assert spec.end is None
        assert spec.duration == "length"

    def test_instant_spec(self) -> None:
        """Test instant event spec."""
        spec = CoordinateSpec(instant="timestamp")
        assert spec.instant == "timestamp"
        assert spec.start is None

    def test_with_cmap_fields(self) -> None:
        """Test spec with C-Map fields."""
        spec = CoordinateSpec(
            start="onset_sec",
            end="offset_sec",
            cmap_fields={
                "onset_beat": CMapField(target_unit=TimeUnit.quarters),
            },
        )
        assert "onset_beat" in spec.cmap_fields
        assert spec.cmap_fields["onset_beat"].target_unit == TimeUnit.quarters

    def test_validation_requires_coordinate(self) -> None:
        """Test that at least one coordinate field is required."""
        with pytest.raises(ValueError, match="at least one of"):
            CoordinateSpec(start=None, instant=None)


# endregion


# region PartitionSpec Tests


class TestPartitionSpec:
    """Tests for PartitionSpec dataclass."""

    def test_separate_mode(self) -> None:
        """Test separate partition mode (disparate coordinates)."""
        spec = PartitionSpec(
            fields=["voice"],
            mode=PartitionMode.separate,
        )
        assert spec.fields == ["voice"]
        assert spec.mode == PartitionMode.separate

    def test_children_mode(self) -> None:
        """Test children partition mode (shared coordinates)."""
        spec = PartitionSpec(
            fields=["staff"],
            mode=PartitionMode.children,
            parent_timeline="score",
        )
        assert spec.mode == PartitionMode.children
        assert spec.parent_timeline == "score"

    def test_composite_key(self) -> None:
        """Test composite partition key."""
        spec = PartitionSpec(fields=["piece", "movement", "voice"])
        assert len(spec.fields) == 3


# endregion


# region TableSchema Basic Tests


class TestTableSchemaBasics:
    """Basic tests for TableSchema creation and configuration."""

    def test_minimal_schema(self) -> None:
        """Test minimal schema with defaults."""
        schema = TableSchema()
        assert schema.timeline.unit == TimeUnit.seconds
        assert schema.coordinates.start == "start"

    def test_custom_schema(self) -> None:
        """Test custom schema configuration."""
        schema = TableSchema(
            timeline=TimelineDefaults(unit=TimeUnit.quarters),
            coordinates=CoordinateSpec(start="onset", end="offset"),
            id_field="event_id",
        )
        assert schema.timeline.unit == TimeUnit.quarters
        assert schema.coordinates.start == "onset"
        assert schema.id_field == "event_id"

    def test_reserved_columns(self) -> None:
        """Test that reserved columns are correctly identified."""
        schema = TableSchema(
            coordinates=CoordinateSpec(
                start="onset",
                end="offset",
                cmap_fields={"beat": CMapField(TimeUnit.quarters)},
            ),
            partitions=PartitionSpec(fields=["voice"]),
            regions=RegionSpec(fields=["section"]),
        )
        reserved = schema.get_reserved_fields()
        assert "onset" in reserved
        assert "offset" in reserved
        assert "beat" in reserved
        assert "voice" in reserved
        assert "section" in reserved

    def test_field_role_detection(self) -> None:
        """Test semantic role detection for source columns."""
        schema = TableSchema(
            coordinates=CoordinateSpec(
                start="onset",
                cmap_fields={"beat": CMapField(TimeUnit.quarters)},
            ),
            partitions=PartitionSpec(fields=["voice"]),
            regions=RegionSpec(fields=["section"]),
        )
        assert schema.get_field_role("onset") == ColumnRole.start
        assert schema.get_field_role("beat") == ColumnRole.cmap_target
        assert schema.get_field_role("voice") == ColumnRole.partition
        assert schema.get_field_role("section") == ColumnRole.region
        assert schema.get_field_role("other") == ColumnRole.extra


# endregion


# region Timeline Creation Tests


class TestTimelineCreation:
    """Tests for TableSchema.create_timelines() method."""

    def test_simple_timeline_creation(self, simple_df: pd.DataFrame) -> None:
        """Test creating a single timeline from simple data."""
        schema = TableSchema(
            timeline=TimelineDefaults(unit=TimeUnit.seconds),
            coordinates=CoordinateSpec(start="onset_sec", end="offset_sec"),
        )
        result = schema.create_timelines(simple_df)

        assert "timelines" in result
        assert len(result["timelines"]) == 1

        timeline = list(result["timelines"].values())[0]
        assert timeline.unit == TimeUnit.seconds
        assert timeline.n_events == 4

    def test_partitioned_timeline_creation(self, partitioned_df: pd.DataFrame) -> None:
        """Test creating multiple timelines from partitioned data."""
        schema = TableSchema(
            timeline=TimelineDefaults(unit=TimeUnit.seconds),
            coordinates=CoordinateSpec(start="onset", end="offset"),
            partitions=PartitionSpec(fields=["voice"], mode=PartitionMode.separate),
        )
        result = schema.create_timelines(partitioned_df)

        # Should have 4 timelines (soprano, alto, tenor, bass)
        assert len(result["timelines"]) == 4

        # Check event counts per partition
        for timeline_id, timeline in result["timelines"].items():
            if "soprano" in timeline_id or "alto" in timeline_id:
                assert timeline.n_events == 2
            else:
                assert timeline.n_events == 1

    def test_region_extraction(self, region_df: pd.DataFrame) -> None:
        """Test extracting regions from region fields."""
        schema = TableSchema(
            timeline=TimelineDefaults(unit=TimeUnit.seconds),
            coordinates=CoordinateSpec(start="onset", end="offset"),
            regions=RegionSpec(fields=["section"]),
        )
        result = schema.create_timelines(region_df)

        assert "regions" in result
        timeline_id = list(result["timelines"].keys())[0]
        regions = result["regions"].get(timeline_id, [])

        # Should have 3 regions: Intro, Verse, Chorus
        assert len(regions) == 3

        region_names = {r.name for r in regions}
        assert "Intro" in region_names
        assert "Verse" in region_names
        assert "Chorus" in region_names

    def test_cmap_creation(self, multiunit_df: pd.DataFrame) -> None:
        """Test creating C-Maps from multi-unit fields."""
        schema = TableSchema(
            timeline=TimelineDefaults(unit=TimeUnit.seconds),
            coordinates=CoordinateSpec(
                start="onset_sec",
                end="offset_sec",
                cmap_fields={
                    "onset_beat": CMapField(
                        target_unit=TimeUnit.quarters,
                        bidirectional=True,
                    ),
                },
            ),
        )
        result = schema.create_timelines(multiunit_df)

        # bidirectional=True creates forward (sec->quarters) and reverse (quarters->sec)
        assert len(result["cmaps"]) == 2

        # Check that C-Map was attached to timeline
        timeline = list(result["timelines"].values())[0]
        assert timeline.get_conversion_map(TimeUnit.quarters) is not None

    def test_instant_events(self) -> None:
        """Test creating instant events (no end column)."""
        df = pd.DataFrame(
            {
                "id": ["b1", "b2", "b3"],
                "timestamp": [0.0, 1.0, 2.0],
            }
        )
        schema = TableSchema(
            timeline=TimelineDefaults(unit=TimeUnit.seconds, default_event_type="Beat"),
            coordinates=CoordinateSpec(instant="timestamp"),
        )
        result = schema.create_timelines(df)

        timeline = list(result["timelines"].values())[0]
        assert timeline.n_events == 3

        # All events should be instants
        events = list(timeline.events)
        for event in events:
            assert event["temporal_type"] == "instant"


# endregion


# region Serialization Tests


class TestSerialization:
    """Tests for TableSchema serialization/deserialization."""

    def test_to_dict_roundtrip(self) -> None:
        """Test that to_dict/from_dict preserves schema."""
        original = TableSchema(
            timeline=TimelineDefaults(
                unit=TimeUnit.quarters,
                default_event_type="Note",
            ),
            coordinates=CoordinateSpec(
                start="onset",
                end="offset",
                cmap_fields={
                    "beat": CMapField(target_unit=TimeUnit.measures),
                },
            ),
            partitions=PartitionSpec(fields=["voice"]),
            regions=RegionSpec(fields=["section"]),
        )

        # Serialize and deserialize
        data = original.to_dict()
        restored = TableSchema.from_dict(data)

        # Check preservation
        assert restored.timeline.unit == TimeUnit.quarters
        assert restored.coordinates.start == "onset"
        assert restored.coordinates.end == "offset"
        assert "beat" in restored.coordinates.cmap_fields
        assert restored.partitions is not None
        assert restored.partitions.fields == ["voice"]

    def test_repr(self) -> None:
        """Test string representation."""
        schema = TableSchema(
            timeline=TimelineDefaults(unit=TimeUnit.seconds),
            partitions=PartitionSpec(fields=["voice"]),
            regions=RegionSpec(fields=["section"]),
        )
        repr_str = repr(schema)
        assert "seconds" in repr_str
        assert "partitions" in repr_str
        assert "regions" in repr_str


# endregion


# region Edge Cases


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_missing_required_column(self) -> None:
        """Test error when required column is missing."""
        df = pd.DataFrame({"id": ["e1"], "other": [1]})
        schema = TableSchema(
            coordinates=CoordinateSpec(start="onset"),  # Column doesn't exist
        )
        with pytest.raises(ValueError, match="Required columns missing"):
            schema.create_timelines(df)

    def test_empty_dataframe(self) -> None:
        """Test handling of empty DataFrame."""
        df = pd.DataFrame({"id": [], "onset": [], "offset": []})
        schema = TableSchema(
            coordinates=CoordinateSpec(start="onset", end="offset"),
        )
        result = schema.create_timelines(df)

        # Should create an empty timeline
        assert len(result["timelines"]) == 1
        timeline = list(result["timelines"].values())[0]
        assert timeline.n_events == 0

    def test_null_partition_values(self) -> None:
        """Test handling of null values in partition columns."""
        df = pd.DataFrame(
            {
                "id": ["e1", "e2", "e3"],
                "onset": [0.0, 1.0, 2.0],
                "voice": ["soprano", None, "alto"],  # Null in partition
            }
        )
        schema = TableSchema(
            coordinates=CoordinateSpec(start="onset"),
            partitions=PartitionSpec(fields=["voice"], include_null=False),
        )
        result = schema.create_timelines(df)

        # Should only have 2 timelines (soprano, alto), not null
        assert len(result["timelines"]) == 2

    def test_duration_to_end_computation(self) -> None:
        """Test that end is computed from duration when duration_field is set."""
        df = pd.DataFrame(
            {
                "id": ["e1", "e2"],
                "onset": [0.0, 1.0],
                "length": [0.5, 0.75],  # Duration column
            }
        )
        schema = TableSchema(
            coordinates=CoordinateSpec(start="onset", duration="length"),
        )
        result = schema.create_timelines(df)

        timeline = list(result["timelines"].values())[0]
        events = list(timeline.events)

        # Events should be intervals with computed end
        for event in events:
            assert event["temporal_type"] == "interval"
            assert event.get("end") is not None


# endregion
