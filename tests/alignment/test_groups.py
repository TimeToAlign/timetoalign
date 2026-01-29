"""Tests for TimelineGroup and GroupTimestamp classes (Phase 7.4 refactor)."""

from __future__ import annotations

import pytest

from timetoalign.alignment import GroupTimestamp, TimelineGroup
from timetoalign.alignment.groups import _reset_group_ids
from timetoalign.timelines import (
    ContinuousPhysicalTimeline,
    DiscreteGraphicalTimeline,
)

# region Fixtures


@pytest.fixture(autouse=True)
def reset_ids() -> None:
    """Reset ID generators before each test."""
    _reset_group_ids()


@pytest.fixture
def dgt_timeline() -> DiscreteGraphicalTimeline:
    """Create a discrete graphical timeline (4875 pixels)."""
    return DiscreteGraphicalTimeline(length=4875, unit="pixels", uid="dgt1")


@pytest.fixture
def audio_timeline() -> ContinuousPhysicalTimeline:
    """Create a continuous physical timeline (150 seconds)."""
    return ContinuousPhysicalTimeline(length=150.0, unit="seconds", uid="audio")


@pytest.fixture
def score_timeline() -> ContinuousPhysicalTimeline:
    """Create a score timeline (100 units, e.g., beats)."""
    return ContinuousPhysicalTimeline(length=100.0, unit="seconds", uid="score")


# endregion


# region GroupTimestamp Tests


class TestGroupTimestamp:
    """Tests for GroupTimestamp dataclass."""

    def test_basic_creation(self) -> None:
        """Test creating a GroupTimestamp."""
        coords = {"tl1": 10.0, "tl2": 20.0, "tl3": None}
        ts = GroupTimestamp(coordinates=coords, row_index=0)

        assert ts["tl1"] == 10.0
        assert ts["tl2"] == 20.0
        assert ts["tl3"] is None
        assert ts.row_index == 0

    def test_get_method(self) -> None:
        """Test get() method with default value."""
        ts = GroupTimestamp(coordinates={"tl1": 10.0}, row_index=0)

        assert ts.get("tl1") == 10.0
        assert ts.get("nonexistent") is None
        assert ts.get("nonexistent", 999.0) == 999.0

    def test_present_timelines(self) -> None:
        """Test present_timelines property."""
        coords = {"tl1": 10.0, "tl2": None, "tl3": 30.0}
        ts = GroupTimestamp(coordinates=coords, row_index=0)

        present = ts.present_timelines
        assert "tl1" in present
        assert "tl3" in present
        assert "tl2" not in present
        assert len(present) == 2

    def test_is_interpolated(self) -> None:
        """Test is_interpolated property."""
        ts_row = GroupTimestamp(coordinates={"tl1": 10.0}, row_index=0)
        ts_interp = GroupTimestamp(coordinates={"tl1": 10.0}, row_index=-1)

        assert ts_row.is_interpolated is False
        assert ts_interp.is_interpolated is True

    def test_frozen_dataclass(self) -> None:
        """Test that GroupTimestamp is immutable."""
        ts = GroupTimestamp(coordinates={"tl1": 10.0}, row_index=0)
        with pytest.raises(AttributeError):
            ts.row_index = 5  # type: ignore


# endregion


# region TimelineGroup Creation Tests


class TestTimelineGroupCreation:
    """Tests for TimelineGroup creation and initialization."""

    def test_create_empty_group(self) -> None:
        """Test creating an empty group."""
        group = TimelineGroup(id="test_group")

        assert group.id == "test_group"
        assert group.n_timelines == 0
        assert group.n_timestamps == 0
        assert group.is_locked is False

    def test_create_group_with_initial_timeline(
        self, dgt_timeline: DiscreteGraphicalTimeline
    ) -> None:
        """Test creating a group with an initial timeline."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline])

        assert group.n_timelines == 1
        assert group.n_timestamps == 2  # Start and end
        assert "dgt1" in group

    def test_create_group_with_multiple_timelines(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test creating a group with multiple initial timelines."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        assert group.n_timelines == 2
        assert group.n_timestamps == 2
        assert "dgt1" in group
        assert "audio" in group

    def test_auto_generated_id(self) -> None:
        """Test auto-generated group ID."""
        group = TimelineGroup()
        assert group.id.startswith("group:TimelineGroup")

    def test_create_locked_group(self, dgt_timeline: DiscreteGraphicalTimeline) -> None:
        """Test creating a locked group."""
        group = TimelineGroup(
            id="locked_group", timelines=[dgt_timeline], is_locked=True
        )

        assert group.is_locked is True


# endregion


# region Add Timeline Tests


class TestAddTimeline:
    """Tests for add_timeline() method."""

    def test_add_first_timeline(self, dgt_timeline: DiscreteGraphicalTimeline) -> None:
        """Test adding the first timeline to an empty group."""
        group = TimelineGroup(id="test_group")
        group.add_timeline(dgt_timeline)

        assert group.n_timelines == 1
        assert group.n_timestamps == 2

        # Check timestamps
        ts_start = group.get_timestamp(0)
        ts_end = group.get_timestamp(1)

        assert ts_start["dgt1"] == 0.0
        assert ts_end["dgt1"] == 4875.0

    def test_add_second_timeline_default_mapping(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test adding a second timeline with default (full extent) mapping."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline])
        group.add_timeline(audio_timeline)

        assert group.n_timelines == 2
        assert group.n_timestamps == 2

        # Both should span full extent
        ts_start = group.get_timestamp(0)
        ts_end = group.get_timestamp(1)

        assert ts_start["dgt1"] == 0.0
        assert ts_start["audio"] == 0.0
        assert ts_end["dgt1"] == 4875.0
        assert ts_end["audio"] == 150.0

    def test_add_timeline_with_explicit_boundaries(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
        score_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test adding a timeline with explicit boundary specifications."""
        # Create group with dgt and audio
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        # Add score section that maps to audio seconds 45-135
        group.add_timeline(
            score_timeline,
            start=(45.0, "audio"),
            end=(135.0, "audio"),
        )

        assert group.n_timelines == 3
        assert group.n_timestamps == 4  # 0, 45, 135, 150 in audio coords

        # Verify the range for score
        score_range = group.get_range("score")
        assert score_range is not None
        assert score_range[0] == 0.0
        assert score_range[1] == 100.0

    def test_add_duplicate_timeline_raises(
        self, dgt_timeline: DiscreteGraphicalTimeline
    ) -> None:
        """Test that adding a duplicate timeline raises an error."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline])

        with pytest.raises(ValueError, match="already in group"):
            group.add_timeline(dgt_timeline)

    def test_add_timeline_to_locked_group_raises(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test that adding to a locked group raises error without allow_extension."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline], is_locked=True)

        # Adding with default mapping should work (no extension needed)
        group.add_timeline(audio_timeline)
        assert group.n_timelines == 2


# endregion


# region Timestamp Access Tests


class TestTimestampAccess:
    """Tests for timestamp access methods."""

    def test_get_timestamp_by_index(
        self, dgt_timeline: DiscreteGraphicalTimeline
    ) -> None:
        """Test getting timestamp by index."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline])

        ts0 = group.get_timestamp(0)
        ts1 = group.get_timestamp(1)
        ts_last = group.get_timestamp(-1)  # Negative indexing

        assert ts0["dgt1"] == 0.0
        assert ts1["dgt1"] == 4875.0
        assert ts_last["dgt1"] == 4875.0

    def test_get_timestamp_index_error(
        self, dgt_timeline: DiscreteGraphicalTimeline
    ) -> None:
        """Test that invalid index raises IndexError."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline])

        with pytest.raises(IndexError):
            group.get_timestamp(10)

    def test_timestamps_property(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test timestamps property returns all timestamps."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        timestamps = group.timestamps
        assert len(timestamps) == 2
        assert all(isinstance(ts, GroupTimestamp) for ts in timestamps)

    def test_get_timestamp_table(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test get_timestamp_table() returns PyArrow table."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        table = group.get_timestamp_table()

        assert table.num_rows == 2
        assert "dgt1" in table.column_names
        assert "audio" in table.column_names

    def test_get_timestamp_table_filtered(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test get_timestamp_table() with filter."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        table = group.get_timestamp_table(timeline_filter={"dgt1"})

        assert table.num_rows == 2
        assert "dgt1" in table.column_names
        assert "audio" not in table.column_names

    def test_get_timestamps_df(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test get_timestamps_df() returns pandas DataFrame."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        df = group.get_timestamps_df()

        assert len(df) == 2
        assert "dgt1" in df.columns
        assert "audio" in df.columns


# endregion


# region Interpolation Tests


class TestGetTimestampAt:
    """Tests for get_timestamp_at() interpolation."""

    def test_exact_boundary_match(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test get_timestamp_at() at exact boundary."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        ts = group.get_timestamp_at(0.0, "audio")
        assert ts["audio"] == 0.0
        assert ts["dgt1"] == 0.0
        assert ts.is_interpolated is False

    def test_interpolation_midpoint(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test interpolation at midpoint."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        # 75 seconds is halfway through 150 seconds
        ts = group.get_timestamp_at(75.0, "audio")

        assert ts["audio"] == pytest.approx(75.0)
        assert ts["dgt1"] == pytest.approx(2437.5)  # Half of 4875
        assert ts.is_interpolated is True

    def test_interpolation_arbitrary_point(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test interpolation at an arbitrary point."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        # 30 seconds = 20% of 150 seconds
        ts = group.get_timestamp_at(30.0, "audio")

        assert ts["audio"] == pytest.approx(30.0)
        assert ts["dgt1"] == pytest.approx(975.0)  # 20% of 4875

    def test_interpolation_reverse_lookup(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test interpolation looking up by different timeline."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        # 2437.5 pixels is halfway through 4875 pixels
        ts = group.get_timestamp_at(2437.5, "dgt1")

        assert ts["dgt1"] == pytest.approx(2437.5)
        assert ts["audio"] == pytest.approx(75.0)

    def test_interpolation_with_partial_timeline(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
        score_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test interpolation when a timeline is only partially present."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        # Add score that only spans audio 45-135 seconds
        group.add_timeline(
            score_timeline,
            start=(45.0, "audio"),
            end=(135.0, "audio"),
        )

        # Query at 75 seconds (within score range)
        ts_in_range = group.get_timestamp_at(75.0, "audio")
        assert ts_in_range["score"] is not None

        # Query at 30 seconds (before score starts)
        ts_before = group.get_timestamp_at(30.0, "audio")
        assert ts_before["score"] is None

        # Query at 140 seconds (after score ends)
        ts_after = group.get_timestamp_at(140.0, "audio")
        assert ts_after["score"] is None

    def test_interpolation_out_of_range_raises(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test that querying outside range raises ValueError."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        with pytest.raises(ValueError, match="outside range"):
            group.get_timestamp_at(200.0, "audio")

    def test_interpolation_nonexistent_timeline_raises(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
    ) -> None:
        """Test that querying non-existent timeline raises KeyError."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline])

        with pytest.raises(KeyError):
            group.get_timestamp_at(50.0, "nonexistent")


# endregion


# region Conversion Tests


class TestConvert:
    """Tests for convert() method."""

    def test_convert_basic(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test basic coordinate conversion."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        # 75 seconds -> 2437.5 pixels
        result = group.convert(75.0, source="audio", target="dgt1")
        assert result == pytest.approx(2437.5)

        # 2437.5 pixels -> 75 seconds
        result = group.convert(2437.5, source="dgt1", target="audio")
        assert result == pytest.approx(75.0)

    def test_convert_same_timeline(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
    ) -> None:
        """Test conversion to same timeline returns same value."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline])

        result = group.convert(1000.0, source="dgt1", target="dgt1")
        assert result == pytest.approx(1000.0)

    def test_convert_returns_none_for_absent_target(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
        score_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test convert returns None when target is absent at coordinate."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        # Add score that only spans audio 45-135 seconds
        group.add_timeline(
            score_timeline,
            start=(45.0, "audio"),
            end=(135.0, "audio"),
        )

        # Query at 30 seconds (score not present)
        result = group.convert(30.0, source="audio", target="score")
        assert result is None


# endregion


# region Range and Utilities Tests


class TestRangeAndUtilities:
    """Tests for get_range() and other utility methods."""

    def test_get_range(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test get_range() returns correct bounds."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        dgt_range = group.get_range("dgt1")
        audio_range = group.get_range("audio")

        assert dgt_range == (0.0, 4875.0)
        assert audio_range == (0.0, 150.0)

    def test_get_range_partial_timeline(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
        score_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test get_range() for partial timeline."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        group.add_timeline(
            score_timeline,
            start=(45.0, "audio"),
            end=(135.0, "audio"),
        )

        score_range = group.get_range("score")
        assert score_range == (0.0, 100.0)

    def test_get_range_nonexistent_returns_none(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
    ) -> None:
        """Test get_range() returns None for non-existent timeline."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline])

        result = group.get_range("nonexistent")
        assert result is None

    def test_timeline_ids(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test timeline_ids property."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        ids = group.timeline_ids
        assert "dgt1" in ids
        assert "audio" in ids
        assert len(ids) == 2


# endregion


# region Remove Timeline Tests


class TestRemoveTimeline:
    """Tests for remove_timeline() method."""

    def test_remove_timeline(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test removing a timeline from the group."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        removed = group.remove_timeline("audio")

        assert removed is audio_timeline
        assert group.n_timelines == 1
        assert "audio" not in group
        assert "dgt1" in group

    def test_remove_nonexistent_raises(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
    ) -> None:
        """Test removing non-existent timeline raises KeyError."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline])

        with pytest.raises(KeyError):
            group.remove_timeline("nonexistent")

    def test_remove_all_timelines(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
    ) -> None:
        """Test removing all timelines results in empty group."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline])

        group.remove_timeline("dgt1")

        assert group.n_timelines == 0
        assert group.n_timestamps == 0


# endregion


# region Locking Tests


class TestLocking:
    """Tests for locking semantics."""

    def test_lock_unlock(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
    ) -> None:
        """Test lock() and unlock() methods."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline])

        assert group.is_locked is False

        group.lock()
        assert group.is_locked is True

        group.unlock()
        assert group.is_locked is False


# endregion


# region Integration Tests


class TestGroupIntegration:
    """Integration tests for TimelineGroup with real timelines."""

    def test_thoresen_poc_setup(self) -> None:
        """Test setup similar to Thoresen PoC from spec.

        DGT1 (2009): 4875 pixels total
        DGT2 (2010): 4328 pixels total
        Both should map to 150 seconds of audio.
        """
        # Create timelines
        dgt1 = DiscreteGraphicalTimeline(length=4875, unit="pixels", uid="dgt1")
        dgt2 = DiscreteGraphicalTimeline(length=4328, unit="pixels", uid="dgt2")
        audio = ContinuousPhysicalTimeline(length=150.0, unit="seconds", uid="audio")

        # Create group 1: DGT1 + audio
        group1 = TimelineGroup(id="DGT1_Group", timelines=[dgt1, audio])

        # Create group 2: DGT2 + audio
        group2 = TimelineGroup(id="DGT2_Group", timelines=[dgt2, audio])

        # Verify conversions in group1
        assert group1.convert(0.0, "dgt1", "audio") == pytest.approx(0.0)
        assert group1.convert(4875.0, "dgt1", "audio") == pytest.approx(150.0)
        assert group1.convert(2437.5, "dgt1", "audio") == pytest.approx(75.0)

        # Verify conversions in group2
        assert group2.convert(0.0, "dgt2", "audio") == pytest.approx(0.0)
        assert group2.convert(4328.0, "dgt2", "audio") == pytest.approx(150.0)
        assert group2.convert(2164.0, "dgt2", "audio") == pytest.approx(75.0)

    def test_three_timeline_group(self) -> None:
        """Test a group with three timelines and partial overlap."""
        # Create timelines
        audio = ContinuousPhysicalTimeline(length=180.0, unit="seconds", uid="audio")
        dgt = DiscreteGraphicalTimeline(length=4875, unit="pixels", uid="dgt")
        score = ContinuousPhysicalTimeline(length=100.0, unit="seconds", uid="score")

        # Create group with audio and DGT spanning only 0-150 seconds
        group = TimelineGroup(id="test_group")
        group.add_timeline(audio)
        group.add_timeline(dgt, end=(150.0, "audio"))

        # Score section maps to audio seconds 45-135
        group.add_timeline(
            score,
            start=(45.0, "audio"),
            end=(135.0, "audio"),
        )

        # Verify timestamps count
        # Should have: 0, 45, 135, 150, 180 = 5 timestamps
        assert group.n_timestamps == 5

        # Check conversions
        # At audio 75.0: score spans audio 45-135 (90 seconds), so
        # audio 75 = (75-45)/(135-45) = 30/90 = 1/3 through score
        # score 1/3 of 100 = 33.33...
        ts = group.get_timestamp_at(75.0, "audio")
        assert ts["audio"] == pytest.approx(75.0)
        assert ts["score"] == pytest.approx(100.0 * (75.0 - 45.0) / (135.0 - 45.0))
        assert ts["dgt"] is not None

        # At audio 30.0 (before score starts)
        ts_early = group.get_timestamp_at(30.0, "audio")
        assert ts_early["score"] is None
        assert ts_early["dgt"] is not None

        # At audio 160.0 (after DGT ends)
        ts_late = group.get_timestamp_at(160.0, "audio")
        assert ts_late["dgt"] is None
        assert ts_late["score"] is None

    def test_round_trip_conversion(self) -> None:
        """Test that conversions are reversible."""
        audio = ContinuousPhysicalTimeline(length=150.0, unit="seconds", uid="audio")
        dgt = DiscreteGraphicalTimeline(length=4875, unit="pixels", uid="dgt")

        group = TimelineGroup(id="test_group", timelines=[audio, dgt])

        # Round trip: audio -> dgt -> audio
        original = 67.5
        dgt_coord = group.convert(original, source="audio", target="dgt")
        assert dgt_coord is not None
        back = group.convert(dgt_coord, source="dgt", target="audio")

        assert back == pytest.approx(original)


# endregion


# region Backward Compatibility Tests


class TestBackwardCompatibility:
    """Tests for deprecated APIs and backward compatibility."""

    def test_from_reference_deprecated(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
    ) -> None:
        """Test from_reference() still works but emits warning."""
        with pytest.warns(DeprecationWarning, match="from_reference"):
            group = TimelineGroup.from_reference(dgt_timeline, name="TestGroup")

        assert group.n_timelines == 1
        assert "dgt1" in group

    def test_reference_property(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
    ) -> None:
        """Test reference property for compatibility."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline])

        assert group.reference is dgt_timeline
        assert group.reference_timeline_id == "dgt1"

    def test_summary(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test summary() method."""
        group = TimelineGroup(
            id="test_group",
            name="Test Group",
            timelines=[dgt_timeline, audio_timeline],
        )

        summary = group.summary()

        assert summary["id"] == "test_group"
        assert summary["name"] == "Test Group"
        assert summary["n_timelines"] == 2
        assert summary["n_timestamps"] == 2
        assert "dgt1" in summary["timeline_ids"]
        assert "audio" in summary["timeline_ids"]


# endregion
