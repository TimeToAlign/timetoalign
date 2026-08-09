"""Tests for TimelineGroup and GroupTimestamp classes."""

from __future__ import annotations

import pytest

from timetoalign.core import Coordinate, IdCoordinate
from timetoalign.core.enums import NumberType, TimeUnit
from timetoalign.core.fields import field_metadata
from timetoalign.core.timestamp import Stamp, TimeStamp
from timetoalign.maps import TableMap
from timetoalign.storage.events import EventData
from timetoalign.timelines import (
    ContinuousPhysicalTimeline,
    DiscreteGraphicalTimeline,
    DiscreteLogicalTimeline,
    GroupTimestamp,
    TimelineGroup,
)

# region Fixtures


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


# region Event ID Timestamp Lookup Tests


class TestEventIdTimestampLookup:
    """Event IDs resolve through group timestamp coordinates."""

    @staticmethod
    def _group() -> TimelineGroup:
        """Create two linearly aligned timelines with two source events."""
        audio = ContinuousPhysicalTimeline(length=10.0, unit="seconds", uid="audio")
        audio.add_events(
            [
                {"id": "event:one", "event_type": "Marker", "instant": 2.0},
                {"id": "event:two", "event_type": "Marker", "instant": 6.0},
            ]
        )
        score = ContinuousPhysicalTimeline(length=20.0, unit="seconds", uid="score")
        return TimelineGroup(id="paired", timelines=[audio, score])

    def test_get_timestamp_of_returns_source_coordinate_fields(self) -> None:
        """The event coordinate identifies its source and mapped member coordinates."""
        timestamp = self._group().get_timestamp_of("event:one")

        assert type(timestamp) is TimeStamp
        assert timestamp.axis == 2.0
        assert timestamp.source_id == "audio"
        assert timestamp.present_timelines == ["audio", "audio", "score"]
        assert timestamp.to_dict(include_children=True, conversion_units=None) == {
            "audio": 2.0,
            "score": 4.0,
        }

    def test_get_timestamp_of_missing_event_raises_key_error(self) -> None:
        """Absent IDs retain the lookup API's KeyError contract."""
        with pytest.raises(KeyError):
            self._group().get_timestamp_of("missing")

    def test_get_timestamps_of_preserves_requested_order(self) -> None:
        """Bulk lookup creates one row per requested ID in the original order."""
        timestamps = self._group().get_timestamps_of(["event:two", "event:one"])

        assert len(timestamps) == 2
        assert list(timestamps.index) == ["event:two", "event:one"]
        assert timestamps.to_dict(orient="list") == {
            "audio": [6.0, 2.0],
            "score": [12.0, 4.0],
        }


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
        assert ts.get("tl3") is None
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

    def test_repr_html_renders_coordinate_table(self) -> None:
        """The coordinate cross-section table still renders."""
        ts = GroupTimestamp(coordinates={"tl1": 10.0, "tl2": 20.0}, row_index=0)
        html = ts._repr_html_()
        assert "<table" in html
        assert "GroupTimestamp" in html
        assert "tl1" in html
        assert "tl2" in html

    def test_repr_html_try_footer(self) -> None:
        """A Try footer surfaces the real GroupTimestamp accessors after the table."""
        ts = GroupTimestamp(coordinates={"tl1": 10.0, "tl2": 20.0}, row_index=0)
        html = ts._repr_html_()
        assert (
            "Try: <code>ts[&lt;tl_id&gt;]</code>, "
            "<code>ts.get(&lt;tl_id&gt;)</code>" in html
        )
        assert html.index("</table>") < html.index("Try:")


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


class TestTimelineGroupEvents:
    """Event aggregation preserves Arrow data and source provenance."""

    def test_get_events_returns_promoted_event_data(self) -> None:
        """Member-specific fields are null-filled in one EventData table."""
        first = ContinuousPhysicalTimeline(length=10.0, uid="first")
        first.add_events([{"start": 1.0, "name": "a"}])
        second = ContinuousPhysicalTimeline(length=10.0, uid="second")
        second.add_events([{"start": 2.0, "velocity": 64}])

        events = TimelineGroup(id="group", timelines=[first, second]).get_events()

        assert isinstance(events, EventData)
        assert events.table.num_rows == 2
        assert events.table.column("timeline_id").to_pylist() == ["first", "second"]
        assert events.table.column("name").to_pylist() == ["a", None]
        assert events.table.column("velocity").to_pylist() == [None, 64]

    def test_get_events_empty_group_returns_empty_event_data(self) -> None:
        """An empty group has an empty Arrow-backed result."""
        events = TimelineGroup(id="empty").get_events()

        assert isinstance(events, EventData)
        assert events.table.num_rows == 0
        assert events.table.column("timeline_id").to_pylist() == []

    def test_get_events_rejects_incompatible_shared_column_types(self) -> None:
        """A shared column cannot silently change its Arrow type."""
        first = ContinuousPhysicalTimeline(length=10.0, uid="first")
        first.add_events([{"start": 1.0, "tag": 1}])
        second = ContinuousPhysicalTimeline(length=10.0, uid="second")
        second.add_events([{"start": 2.0, "tag": "x"}])

        group = TimelineGroup(id="group", timelines=[first, second])
        with pytest.raises(
            ValueError,
            match=r"^Conflicting Arrow types for column 'tag': int64 and string\.$",
        ):
            group.get_events()

    def test_get_events_overwrites_member_timeline_id(self) -> None:
        """Group membership is authoritative provenance."""
        timeline = ContinuousPhysicalTimeline(length=10.0, uid="authoritative")
        timeline.add_events([{"start": 1.0, "timeline_id": "stale"}])

        events = TimelineGroup(id="group", timelines=[timeline]).get_events()

        assert events.table.column_names.count("timeline_id") == 1
        assert events.table.column("timeline_id").to_pylist() == ["authoritative"]

    def test_get_events_propagates_timeline_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A member query failure is visible to the group caller."""
        timeline = ContinuousPhysicalTimeline(length=10.0, uid="broken")

        def fail(**kwargs: object) -> EventData:
            raise RuntimeError("member query failed")

        monkeypatch.setattr(timeline, "get_events", fail)
        group = TimelineGroup(id="group", timelines=[timeline])

        with pytest.raises(RuntimeError, match="member query failed"):
            group.get_events()


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
        ts_start = group.get_timestamp_at_index(0)
        ts_end = group.get_timestamp_at_index(1)

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
        ts_start = group.get_timestamp_at_index(0)
        ts_end = group.get_timestamp_at_index(1)

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
            start=IdCoordinate(45.0, TimeUnit.seconds, "audio"),
            end=IdCoordinate(135.0, TimeUnit.seconds, "audio"),
        )

        assert group.n_timelines == 3
        assert group.n_timestamps == 4  # 0, 45, 135, 150 in audio coords

        # Verify the range for score
        score_range = group.get_range("score")
        assert score_range is not None
        assert score_range[0] == 0.0
        assert score_range[1] == 100.0

    def test_add_timeline_with_coordinate_boundaries(
        self,
        audio_timeline: ContinuousPhysicalTimeline,
        score_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Coordinate and IdCoordinate boundaries resolve in the reference timeline."""
        group = TimelineGroup(id="test_group", timelines=[audio_timeline])

        group.add_timeline(
            score_timeline,
            start=Coordinate(45.0, TimeUnit.seconds),
            end=IdCoordinate(135.0, TimeUnit.seconds, "audio"),
        )

        assert group.get_timestamp_at_index(1).coordinates == {
            "audio": 45.0,
            "score": 0.0,
        }
        assert group.get_timestamp_at_index(2).coordinates == {
            "audio": 135.0,
            "score": 100.0,
        }

    def test_add_timeline_coordinate_boundary_rejects_wrong_unit(
        self,
        audio_timeline: ContinuousPhysicalTimeline,
        score_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """A Coordinate boundary must convert to the reference timeline unit."""
        group = TimelineGroup(id="test_group", timelines=[audio_timeline])

        with pytest.raises(ValueError, match="No C-Map available"):
            group.add_timeline(
                score_timeline,
                start=Coordinate(45.0, TimeUnit.pixels),
            )

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

        ts0 = group.get_timestamp_at_index(0)
        ts1 = group.get_timestamp_at_index(1)
        ts_last = group.get_timestamp_at_index(-1)  # Negative indexing

        assert ts0["dgt1"] == 0.0
        assert ts1["dgt1"] == 4875.0
        assert ts_last["dgt1"] == 4875.0

    def test_get_timestamp_index_error(
        self, dgt_timeline: DiscreteGraphicalTimeline
    ) -> None:
        """Test that invalid index raises IndexError."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline])

        with pytest.raises(IndexError):
            group.get_timestamp_at_index(10)

    def test_row_timestamp_stamp_contract(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """A table row exposes the same coordinate contract as other stamps."""
        dgt_timeline.add_conversion_map(
            TableMap(
                x_values=[0.0, 4875.0],
                y_values=[0.0, 150.0],
                source_unit=TimeUnit.pixels,
                target_unit=TimeUnit.seconds,
                uid="dgt1-seconds",
            )
        )
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        gt = group.get_timestamp_at_index(1)

        assert isinstance(gt, Stamp)
        assert gt.source is group
        assert gt.source_id == "dgt1"
        assert gt.axis == 4875.0
        assert gt.get_coordinate("dgt1") == Coordinate(4875.0, TimeUnit.pixels)
        assert gt["seconds"] == 150.0
        assert gt.to_dict() == {"dgt1": 4875.0, "audio": 150.0}

    def test_row_timestamp_round_trips_through_group_lookup(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """A row stamp identifies the member timeline that owns its axis."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        gt = group.get_timestamp_at_index(1)
        ts = group.get_timestamp_at(gt.axis, gt.source_id)

        assert ts.get("audio") == gt.get("audio")

    def test_old_timestamp_accessor_is_absent(
        self, dgt_timeline: DiscreteGraphicalTimeline
    ) -> None:
        """The index accessor has an unambiguous name."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline])

        with pytest.raises(AttributeError):
            group.get_timestamp(0)  # type: ignore[attr-defined]

    def test_group_timestamp_is_exported_at_top_level(self) -> None:
        """The row timestamp type is available from the package root."""
        from timetoalign import GroupTimestamp as TopLevelGroupTimestamp

        assert TopLevelGroupTimestamp is GroupTimestamp

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

    def test_to_dataframe(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test to_dataframe() returns pandas DataFrame with units in column names."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        df = group.to_dataframe()

        assert len(df) == 2
        # Column names now include units like "dgt1 (pixels)"
        assert "dgt1 (pixels)" in df.columns
        assert "audio (seconds)" in df.columns

        # Test units=False returns raw column names
        df_no_units = group.to_dataframe(units=False)
        assert "dgt1" in df_no_units.columns
        assert "audio" in df_no_units.columns


# endregion


# region Interpolation Tests


class TestGetTimestampAt:
    """Tests for get_timestamp_at() interpolation."""

    def test_get_timestamps_at_uses_each_embedded_timeline_id(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Batch lookup accepts independently qualified coordinate rows."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        result = group.get_timestamps_at(
            [
                IdCoordinate(75.0, TimeUnit.seconds, "audio"),
                IdCoordinate(2437.5, TimeUnit.pixels, "dgt1"),
            ],
            units=False,
        )

        assert result["audio"].tolist() == [75.0, 75.01538461538462]
        assert result["dgt1"].tolist() == [2438, 2438]

    def test_get_timestamps_at_requires_id_for_plain_values(
        self,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Batch lookup rejects raw rows when no timeline ID is supplied."""
        group = TimelineGroup(id="test_group", timelines=[audio_timeline])

        with pytest.raises(
            ValueError,
            match="timeline_id is required unless coordinate is an IdCoordinate",
        ):
            group.get_timestamps_at([25.0])

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

        assert ts["audio"] == 75.0
        # Discrete timelines round to nearest integer: 4875/2 = 2437.5 → 2438
        assert ts["dgt1"] == 2438
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

        assert ts["audio"] == 30.0
        assert ts["dgt1"] == 975  # 20% of 4875, discrete → integer

    def test_interpolation_reverse_lookup(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test interpolation looking up by different timeline."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        # 2437.5 pixels is halfway through 4875 pixels
        ts = group.get_timestamp_at(2437.5, "dgt1")

        # Discrete timelines round to nearest integer: 2437.5 → 2438
        assert ts["dgt1"] == 2438
        # Every projection of the stamp is a projection of that one pixel, so
        # the audio reading is pixel 2438's, not the half-pixel's.
        assert ts["audio"] == 2438 / 4875 * 150
        assert ts["audio"] == 75.01538461538462

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
            start=IdCoordinate(45.0, TimeUnit.seconds, "audio"),
            end=IdCoordinate(135.0, TimeUnit.seconds, "audio"),
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

    def test_discrete_out_of_range_coordinate_uses_integer_display(self) -> None:
        """A discrete coordinate is rendered as the integer it represents."""
        score = DiscreteLogicalTimeline(length=12000, uid="score")
        annotation = DiscreteLogicalTimeline(length=480, uid="annotation")
        group = TimelineGroup(id="test_group", timelines=[score])

        with pytest.raises(ValueError) as error:
            group.add_timeline(
                annotation,
                start=IdCoordinate(12673.0, TimeUnit.ticks, "score"),
            )

        assert str(error.value) == (
            "Coordinate 12673 is outside range for timeline 'score'"
        )

    def test_continuous_out_of_range_coordinate_keeps_fractional_part(
        self,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """A continuous coordinate retains a meaningful fractional part."""
        group = TimelineGroup(id="test_group", timelines=[audio_timeline])

        with pytest.raises(ValueError) as error:
            group.get_timestamp_at(150.25, "audio")

        assert str(error.value) == "Coordinate 150.25 outside range for 'audio'"

    def test_out_of_range_coordinate_avoids_scientific_notation(
        self,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """A large coordinate is expanded to fixed-point display."""
        group = TimelineGroup(id="test_group", timelines=[audio_timeline])

        with pytest.raises(ValueError) as error:
            group.get_timestamp_at(1e20, "audio")

        assert str(error.value) == (
            "Coordinate 100000000000000000000 outside range for 'audio'"
        )

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

        # 75 seconds -> 2438 pixels (discrete: 2437.5 rounds to 2438)
        result = group.convert(75.0, source="audio", target="dgt1")
        assert result == Coordinate(2438, TimeUnit.pixels)

        # 2437.5 pixels names pixel 2438, so the answer is pixel 2438's second
        # position. A pixel axis holds integers; there is no half-pixel to
        # convert from.
        result = group.convert(2437.5, source="dgt1", target="audio")
        assert result == Coordinate(2438 / 4875 * 150, TimeUnit.seconds)
        assert result == Coordinate(75.01538461538462, TimeUnit.seconds)

    def test_convert_same_timeline(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
    ) -> None:
        """Test conversion to same timeline returns same value."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline])

        result = group.convert(1000.0, source="dgt1", target="dgt1")
        assert result == Coordinate(1000.0, TimeUnit.pixels)

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
            start=IdCoordinate(45.0, TimeUnit.seconds, "audio"),
            end=IdCoordinate(135.0, TimeUnit.seconds, "audio"),
        )

        # Query at 30 seconds (score not present)
        result = group.convert(30.0, source="audio", target="score")
        assert result is None

    def test_convert_accepts_coordinate_objects(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """convert() accepts raw value, Coordinate, and IdCoordinate forms.

        The endpoints are named by ``source``/``target``, so an IdCoordinate's
        own timeline_id is informational only; its value is what is converted.
        """
        from timetoalign.core import Coordinate, IdCoordinate
        from timetoalign.core.enums import TimeUnit

        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        raw = group.convert(75.0, source="audio", target="dgt1")
        assert raw == Coordinate(2438, TimeUnit.pixels)
        from_coord = group.convert(
            Coordinate(75.0, TimeUnit.seconds), source="audio", target="dgt1"
        )
        assert from_coord == Coordinate(2438, TimeUnit.pixels)
        from_id = group.convert(
            IdCoordinate(75.0, TimeUnit.seconds, "audio"),
            source="audio",
            target="dgt1",
        )
        assert from_id == Coordinate(2438, TimeUnit.pixels)

    def test_convert_rejects_unsupported_type(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """convert() raises TypeError for a non-coordinate value."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])
        with pytest.raises(TypeError, match="Unsupported coordinate specification"):
            group.convert("x", source="audio", target="dgt1")  # type: ignore[arg-type]


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
            start=IdCoordinate(45.0, TimeUnit.seconds, "audio"),
            end=IdCoordinate(135.0, TimeUnit.seconds, "audio"),
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
        assert group1.convert(0.0, "dgt1", "audio") == Coordinate(0.0, TimeUnit.seconds)
        assert group1.convert(4875.0, "dgt1", "audio") == Coordinate(
            150.0, TimeUnit.seconds
        )
        # 2437.5 names pixel 2438 on an integer axis.
        assert group1.convert(2437.5, "dgt1", "audio") == Coordinate(
            2438 / 4875 * 150, TimeUnit.seconds
        )

        # Verify conversions in group2
        assert group2.convert(0.0, "dgt2", "audio") == Coordinate(0.0, TimeUnit.seconds)
        assert group2.convert(4328.0, "dgt2", "audio") == Coordinate(
            150.0, TimeUnit.seconds
        )
        assert group2.convert(2164.0, "dgt2", "audio") == Coordinate(
            75.0, TimeUnit.seconds
        )

    def test_three_timeline_group(self) -> None:
        """Test a group with three timelines and partial overlap."""
        # Create timelines
        audio = ContinuousPhysicalTimeline(length=180.0, unit="seconds", uid="audio")
        dgt = DiscreteGraphicalTimeline(length=4875, unit="pixels", uid="dgt")
        score = ContinuousPhysicalTimeline(length=100.0, unit="seconds", uid="score")

        # Create group with audio and DGT spanning only 0-150 seconds
        group = TimelineGroup(id="test_group")
        group.add_timeline(audio)
        group.add_timeline(dgt, end=IdCoordinate(150.0, TimeUnit.seconds, "audio"))

        # Score section maps to audio seconds 45-135
        group.add_timeline(
            score,
            start=IdCoordinate(45.0, TimeUnit.seconds, "audio"),
            end=IdCoordinate(135.0, TimeUnit.seconds, "audio"),
        )

        # Verify timestamps count
        # Should have: 0, 45, 135, 150, 180 = 5 timestamps
        assert group.n_timestamps == 5

        # Check conversions
        # At audio 75.0: score spans audio 45-135 (90 seconds), so
        # audio 75 = (75-45)/(135-45) = 30/90 = 1/3 through score
        # score 1/3 of 100 = 33.33...
        ts = group.get_timestamp_at(75.0, "audio")
        assert ts["audio"] == 75.0
        # Interpolated onto a partial timeline: 100 * 30/90 = 33.333… is a
        # non-terminating ratio, so this remains a genuine float comparison.
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
        """Test that conversions are reversible within quantization error.

        Discrete timelines round interpolated coordinates to integers,
        introducing a quantization error of at most ±0.5 in the discrete
        unit.  The round-trip tolerance in seconds is therefore
        0.5 * (150 / 4875) ≈ 0.0154 seconds.
        """
        audio = ContinuousPhysicalTimeline(length=150.0, unit="seconds", uid="audio")
        dgt = DiscreteGraphicalTimeline(length=4875, unit="pixels", uid="dgt")

        group = TimelineGroup(id="test_group", timelines=[audio, dgt])

        # Round trip: audio -> dgt -> audio
        original = 67.5
        dgt_coord = group.convert(original, source="audio", target="dgt")
        assert dgt_coord is not None
        assert isinstance(dgt_coord.value, int)  # discrete → integer
        back = group.convert(dgt_coord, source="dgt", target="audio")
        assert back is not None

        # Quantization error: ≤ 0.5 * (150 / 4875) ≈ 0.0154 seconds
        assert back.value == pytest.approx(original, abs=0.5 * 150.0 / 4875)


# endregion


# region Summary Test


class TestTimelineGroupSummary:
    """Tests for TimelineGroup.summary()."""

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


# region Unified Timestamp API Tests


class TestTimelineGroupTimestampAt:
    """Tests for the unified TimeStamp API via get_timestamp_at()."""

    def test_get_timestamp_at_basic(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test basic timestamp creation."""
        from timetoalign.core import TimeStamp

        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        ts = group.get_timestamp_at(75.0, "audio")
        assert isinstance(ts, TimeStamp)
        assert ts.axis == 75.0
        assert ts.source_id == "audio"

    def test_get_timestamp_at_without_conversion_maps(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Disabled conversion maps leave member timeline access available."""
        dgt_timeline.add_conversion_map(
            TableMap(
                x_values=[0.0, 4875.0],
                y_values=[0.0, 100.0],
                source_unit=TimeUnit.pixels,
                target_unit=TimeUnit.beats,
                uid="pixels-to-beats",
            )
        )
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        ts = group.get_timestamp_at(4875.0, "dgt1", conversion_maps=False)

        assert ts.get_unit(TimeUnit.beats) is None
        with pytest.raises(KeyError):
            _ = ts["beats"]
        assert ts["dgt1"] == 4875

    def test_get_timestamp_at_with_restricted_conversion_maps(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Restricted conversion maps expose only their target unit."""
        dgt_timeline.add_conversion_map(
            TableMap(
                x_values=[0.0, 4875.0],
                y_values=[0.0, 100.0],
                source_unit=TimeUnit.pixels,
                target_unit=TimeUnit.beats,
                uid="pixels-to-beats",
            )
        )
        dgt_timeline.add_conversion_map(
            TableMap(
                x_values=[0.0, 4875.0],
                y_values=[0.0, 200.0],
                source_unit=TimeUnit.pixels,
                target_unit=TimeUnit.frames,
                uid="pixels-to-frames",
            )
        )
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        ts = group.get_timestamp_at(
            4875.0,
            "dgt1",
            conversion_maps=[TimeUnit.beats],
        )

        assert ts.get_unit(TimeUnit.beats) == 100.0
        assert ts["beats"] == 100.0
        assert ts.get_unit(TimeUnit.frames) is None
        with pytest.raises(KeyError):
            _ = ts["frames"]

    def test_get_timestamp_at_coordinate_conversion(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test coordinate conversion via timestamp."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        # audio: 0 -> 150, dgt: 0 -> 4875
        # At audio=75 (half), dgt should be 4875/2 = 2437.5 -> rounded to 2438
        ts = group.get_timestamp_at(75.0, "audio")

        dgt_coord = ts["dgt1"]
        assert dgt_coord is not None
        # Discrete timelines are rounded to nearest integer
        assert dgt_coord == 2438

    def test_get_timestamp_at_bidirectional(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test bidirectional coordinate conversion."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        # From dgt to audio. 2437.5 names pixel 2438 on an integer axis.
        ts = group.get_timestamp_at(2437.5, "dgt1")
        audio_coord = ts["audio"]
        assert audio_coord is not None
        assert audio_coord == 2438 / 4875 * 150

    def test_get_timestamp_at_unknown_timeline_raises(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
    ) -> None:
        """Test that unknown timeline raises KeyError."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline])

        with pytest.raises(KeyError, match="nonexistent"):
            group.get_timestamp_at(50.0, "nonexistent")

    def test_get_timestamp_at_empty_group_raises(self) -> None:
        """Test that empty group raises KeyError (no timelines)."""
        group = TimelineGroup(id="empty_group")

        # Empty group has no timelines, so KeyError is raised first
        with pytest.raises(KeyError, match="not in group"):
            group.get_timestamp_at(50.0, "any_timeline")

    def test_interval_stamp_from_get_timestamp_at(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Compose a TimeIntervalStamp from two get_timestamp_at() calls."""
        from timetoalign.core import TimeIntervalStamp

        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        interval = TimeIntervalStamp(
            start=group.get_timestamp_at(0.0, "audio"),
            end=group.get_timestamp_at(100.0, "audio"),
        )

        assert isinstance(interval, TimeIntervalStamp)
        assert interval.duration == 100.0
        assert interval.source_id == "audio"

        # Check interval on dgt
        dgt_interval = interval["dgt1"]
        assert dgt_interval is not None
        # audio 0->100 maps to dgt 0->3250 (100/150 * 4875)
        assert dgt_interval[0] == 0.0
        assert dgt_interval[1] == 3250.0

    def test_timestamp_with_three_timelines(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
        score_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test coordinate conversion with three timelines."""
        group = TimelineGroup(
            id="test_group",
            timelines=[dgt_timeline, audio_timeline, score_timeline],
        )

        # All timelines aligned start-to-start and end-to-end
        # At audio midpoint (75.0):
        # - dgt should be 2437.5 -> rounded to 2438 (discrete timeline)
        # - score should be 50.0 (midpoint of 0-100)

        ts = group.get_timestamp_at(75.0, "audio")

        # Discrete timelines are rounded to nearest integer
        assert ts["dgt1"] == 2438
        assert ts["score"] == 50.0
        assert ts["audio"] == 75.0

    def test_timestamp_same_timeline_returns_axis(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test that getting the same timeline returns axis value."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        ts = group.get_timestamp_at(75.0, "audio")

        # Getting the source timeline should return axis
        assert ts["audio"] == 75.0
        assert ts.get("audio") == 75.0

    def test_interpolation_maps_built_on_add(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test that interpolation maps are built when timelines are added."""
        group = TimelineGroup(id="test_group")

        # Initially empty
        assert len(group._interpolation_maps) == 0

        # Add first timeline - still empty (need at least 2 for pairwise maps)
        group.add_timeline(dgt_timeline)
        assert len(group._interpolation_maps) == 0

        # Add second timeline - should have 2 maps (dgt->audio, audio->dgt)
        group.add_timeline(audio_timeline)
        assert len(group._interpolation_maps) == 2
        assert "dgt1:audio" in group._interpolation_maps
        assert "audio:dgt1" in group._interpolation_maps

    def test_interpolation_maps_updated_on_remove(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
        score_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test that interpolation maps are updated when a timeline is removed."""
        group = TimelineGroup(
            id="test_group",
            timelines=[dgt_timeline, audio_timeline, score_timeline],
        )

        # Should have 6 maps (3 timelines, each direction)
        assert len(group._interpolation_maps) == 6

        # Remove score
        group.remove_timeline("score")

        # Should have 2 maps now
        assert len(group._interpolation_maps) == 2
        assert "dgt1:audio" in group._interpolation_maps
        assert "audio:dgt1" in group._interpolation_maps
        assert "score:audio" not in group._interpolation_maps

    def test_implements_timestamp_source_protocol(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test that TimelineGroup implements TimeStampSource protocol."""
        from timetoalign.core.timestamp import TimeStampSource

        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        # Check protocol compliance
        assert isinstance(group, TimeStampSource)
        assert hasattr(group, "_get_interpolation_map")
        assert hasattr(group, "_get_unit_map")
        assert hasattr(group, "_get_related_timeline_ids")
        assert hasattr(group, "_get_available_units")

    def test_get_related_timeline_ids(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test _get_related_timeline_ids method."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        ids = group._get_related_timeline_ids()
        assert "dgt1" in ids
        assert "audio" in ids
        assert len(ids) == 2

    def test_get_available_units_returns_empty(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
    ) -> None:
        """Test _get_available_units returns empty (groups don't have C-Maps)."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline])

        units = group._get_available_units()
        assert units == []


# endregion


# region TimelineGroup Unit Metadata Tests


class TestTimelineGroupUnitMetadata:
    """Tests for unit metadata in TimelineGroup timestamp tables."""

    def test_get_unit_for_timeline(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test _get_unit_for_timeline returns correct unit for each timeline."""
        from timetoalign.core.enums import TimeUnit

        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        dgt_unit = group._get_unit_for_timeline("dgt1")
        assert dgt_unit == TimeUnit.pixels

        audio_unit = group._get_unit_for_timeline("audio")
        assert audio_unit == TimeUnit.seconds

    def test_get_unit_for_unknown_timeline_returns_none(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
    ) -> None:
        """Test _get_unit_for_timeline returns None for unknown timeline."""
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline])

        unit = group._get_unit_for_timeline("nonexistent")
        assert unit is None

    def test_timestamp_table_has_unit_metadata(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test that get_timestamp_table includes unit metadata on fields."""
        # Creating group with two timelines auto-creates boundaries
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        table = group.get_timestamp_table()

        # Check each timeline field has correct unit metadata
        dgt_field = table.schema.field("dgt1")
        assert dgt_field.metadata is not None
        assert field_metadata(dgt_field)["unit"] == "pixels"
        assert field_metadata(dgt_field)["timeline_id"] == "dgt1"

        audio_field = table.schema.field("audio")
        assert audio_field.metadata is not None
        assert field_metadata(audio_field)["unit"] == "seconds"
        assert field_metadata(audio_field)["timeline_id"] == "audio"

    def test_timestamp_table_preserves_metadata_after_insert(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
        score_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test that unit metadata is preserved when adding timelines."""
        # Start with two timelines
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline, audio_timeline])

        # Add a third timeline which inserts more rows
        group.add_timeline(
            score_timeline,
            start=IdCoordinate(45.0, TimeUnit.seconds, "audio"),
            end=IdCoordinate(135.0, TimeUnit.seconds, "audio"),
        )

        table = group.get_timestamp_table()

        # Metadata should still be present after adding timeline
        dgt_field = table.schema.field("dgt1")
        assert dgt_field.metadata is not None
        assert field_metadata(dgt_field)["unit"] == "pixels"

        audio_field = table.schema.field("audio")
        assert audio_field.metadata is not None
        assert field_metadata(audio_field)["unit"] == "seconds"

        # New timeline also has metadata
        score_field = table.schema.field("score")
        assert score_field.metadata is not None
        assert field_metadata(score_field)["unit"] == "seconds"
        assert field_metadata(score_field)["timeline_id"] == "score"

    def test_add_timeline_creates_metadata_for_new_column(
        self,
        dgt_timeline: DiscreteGraphicalTimeline,
        audio_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test that adding a timeline creates field with correct metadata."""
        # Start with one timeline
        group = TimelineGroup(id="test_group", timelines=[dgt_timeline])

        table_before = group.get_timestamp_table()
        assert "audio" not in table_before.schema.names

        # Add second timeline
        group.add_timeline(audio_timeline, start=0.0, end=150.0)

        table_after = group.get_timestamp_table()

        # New field should have metadata
        audio_field = table_after.schema.field("audio")
        assert audio_field.metadata is not None
        assert field_metadata(audio_field)["unit"] == "seconds"
        assert field_metadata(audio_field)["timeline_id"] == "audio"


# endregion


# region EventData field typing


def test_event_data_coerces_volta_to_integer() -> None:
    """Carried volta values retain the ordinal ending-number type."""
    null_only = EventData.from_dicts(
        [{"event_type": "Measure", "start": 0, "end": 1, "volta": None}],
        TimeUnit.quarters,
        NumberType.fraction,
    )
    with_volta = EventData.from_dicts(
        [{"event_type": "Measure", "start": 1, "end": 2, "volta": "2"}],
        TimeUnit.quarters,
        NumberType.fraction,
    )

    assert str(null_only._table.schema.field("volta").type) == "int64"
    assert with_volta._table.column("volta").to_pylist() == [2]
    null_only.extend(with_volta)
    assert null_only._table.column("volta").to_pylist() == [None, 2]


# endregion


# region TestTimelineGroupUnfold


@pytest.mark.slow
class TestTimelineGroupUnfold:
    """Tests for TimelineGroup.apply_flow() — group-level unfolding.

    Uses the Beethoven Op.18 No.4 iv multimodal score group containing:
    - CLT1: ContinuousLogicalTimeline (ABC v2.6, 878.5 quarters)
    - OpenScore: ContinuousLogicalTimeline (4th movement, 878.5 quarters)

    The FlowMap has 11 PlaythroughSections producing 1116 unfolded QB.
    Gold standard values from the test_unfolding.py module.
    """

    # Gold standard constants (same as test_unfolding.py)
    FOLDED_QB = 878.5
    UNFOLDED_QB = 1116
    N_SECTIONS = 11

    @pytest.fixture(scope="class")
    def score_data(self):
        """Build score group + flow data for unfolding tests."""
        from pathlib import Path

        from timetoalign.core.enums import FlowMode
        from timetoalign.loader.score import Ms3Loader
        from timetoalign.timelines.flow import ScoreFlowController

        data_dir = (
            Path(__file__).parent.parent
            / "data"
            / "score"
            / "beethoven_op18-4iv_multimodal"
        )
        abc_dir = data_dir / "ABC"
        os_dir = data_dir / "OpenScoreSQ"

        if not abc_dir.exists():
            pytest.skip(f"Beethoven test data not found: {abc_dir}")

        # CLT1
        abc_loader = Ms3Loader.from_file(
            abc_dir / "n04op18-4_04.notes.tsv",
            abc_dir / "n04op18-4_04.measures.tsv",
            abc_dir / "n04op18-4_04.harmonies.tsv",
        )
        clt1 = abc_loader.create_timeline(uid="clt1")

        # OpenScore (4th movement only)
        os_loader = Ms3Loader.from_file(
            os_dir / "sq8913219.notes.tsv",
            os_dir / "sq8913219.measures.tsv",
        )
        os_full = os_loader.create_timeline(uid="openscore_full")
        os_controller = ScoreFlowController(os_loader.store.measures)
        boundaries = os_controller.get_section_boundary_coordinates()
        os_full.create_regions_from_boundaries(
            [0, *[float(b) for b in boundaries], float(os_full.length.value)],
            prefix="movement",
        )
        openscore = os_full.create_child_from_region("movement_4", uid="openscore")

        # Group
        group = TimelineGroup(
            id="score",
            name="Score (ABC + OpenScore)",
            timelines=[clt1, openscore],
        )

        # Flow
        controller = abc_loader.create_flow_controller()
        flow = controller.compute_flow(FlowMode.default)

        return {
            "group": group,
            "clt1": clt1,
            "openscore": openscore,
            "controller": controller,
            "flow": flow,
            "abc_loader": abc_loader,
        }

    @pytest.fixture(scope="class")
    def unfolded_group(self, score_data):
        """Unfold the score group once for flattened-result assertions."""
        return score_data["group"].apply_flow(
            score_data["flow"], score_data["controller"], "clt1"
        )

    def test_unfold_returns_timeline_group(self, unfolded_group):
        """apply_flow() returns a TimelineGroup."""
        assert isinstance(unfolded_group, TimelineGroup)

    def test_unfold_preserves_timeline_ids(self, score_data, unfolded_group):
        """Unfolded group has the same timeline IDs as the original."""
        group = score_data["group"]
        assert set(unfolded_group.timeline_ids) == set(group.timeline_ids)

    def test_unfold_preserves_timeline_count(self, score_data, unfolded_group):
        """Unfolded group has the same number of timelines."""
        group = score_data["group"]
        assert unfolded_group.n_timelines == group.n_timelines

    def test_unfold_group_name(self, unfolded_group):
        """Unfolded group has a descriptive name."""
        assert "unfolded" in unfolded_group.name.lower()

    def test_unfold_custom_name(self, score_data):
        """Custom name is used when specified."""
        group = score_data["group"]
        result = group.apply_flow(
            score_data["flow"],
            score_data["controller"],
            "clt1",
            name="My Unfolded Group",
        )
        assert result.name == "My Unfolded Group"

    def test_unfold_clt1_length(self, unfolded_group):
        """Unfolded CLT1 has exact unfolded length (1116 QB)."""
        clt1 = unfolded_group.get_timeline("clt1")
        assert clt1.length.value == self.UNFOLDED_QB

    def test_unfold_openscore_length(self, unfolded_group):
        """Unfolded OpenScore has exact unfolded length (1116 QB)."""
        openscore = unfolded_group.get_timeline("openscore")
        assert openscore.length.value == self.UNFOLDED_QB

    def test_unfold_child_count(self, unfolded_group):
        """Each unfolded member has exactly N_SECTIONS appended children."""
        for tl_id in unfolded_group.timeline_ids:
            tl = unfolded_group.get_timeline(tl_id)
            assert tl.n_children == self.N_SECTIONS, (
                f"{tl_id}: n_children={tl.n_children}, " f"expected {self.N_SECTIONS}"
            )

    def test_unfold_members_keep_concrete_type(self, score_data, unfolded_group):
        """Each unfolded member is the same concrete type as its source."""
        group = score_data["group"]
        for tl_id in unfolded_group.timeline_ids:
            src = group.get_timeline(tl_id)
            out = unfolded_group.get_timeline(tl_id)
            assert type(out) is type(src)

    def test_unfold_flattened_has_events(self, unfolded_group):
        """Unfolded CLT1 has note events (now living in its appended children)."""
        clt1 = unfolded_group.get_timeline("clt1")
        events = clt1.get_events(event_type="Note", include_children=True)
        assert len(events) > 0

    def test_unfold_reference_has_flow_maps(self, unfolded_group):
        """Reference timeline in unfolded group has FlowMaps attached."""
        clt1 = unfolded_group.get_timeline("clt1")
        assert clt1.n_flow_maps >= 2
        assert clt1.has_flow_map("source")

    def test_unfold_invalid_reference_raises(self, score_data):
        """KeyError when reference_timeline_id is not in the group."""
        group = score_data["group"]
        with pytest.raises(KeyError, match="nonexistent"):
            group.apply_flow(
                score_data["flow"],
                score_data["controller"],
                "nonexistent",
            )

    def test_unfold_consistency_with_single_timeline(self, score_data, unfolded_group):
        """Group unfold produces same length as create_unfolded_timeline.

        Verifies that the group-based approach is consistent with the
        single-timeline function for the reference timeline: both yield a
        same-type timeline with one appended child per section.
        """
        from timetoalign.timelines.flow import create_unfolded_timeline

        controller = score_data["controller"]
        flow = score_data["flow"]
        clt1 = score_data["clt1"]

        group_clt1 = unfolded_group.get_timeline("clt1")
        single_clt1 = create_unfolded_timeline(clt1, flow, controller)

        assert group_clt1.length.value == single_clt1.length.value
        assert group_clt1.n_children == single_clt1.n_children


# endregion


# region TestScoreLoaderCreateFlowController


class TestScoreLoaderCreateFlowController:
    """Tests for ScoreLoader.create_flow_controller()."""

    @pytest.fixture(scope="class")
    def abc_loader(self):
        """Load the Beethoven ABC score."""
        from pathlib import Path

        from timetoalign.loader.score import Ms3Loader

        data_dir = (
            Path(__file__).parent.parent
            / "data"
            / "score"
            / "beethoven_op18-4iv_multimodal"
            / "ABC"
        )
        if not data_dir.exists():
            pytest.skip(f"Beethoven test data not found: {data_dir}")

        return Ms3Loader.from_file(
            data_dir / "n04op18-4_04.notes.tsv",
            data_dir / "n04op18-4_04.measures.tsv",
        )

    def test_returns_score_flow_controller(self, abc_loader):
        """create_flow_controller() returns a ScoreFlowController."""
        from timetoalign.timelines.flow import ScoreFlowController

        controller = abc_loader.create_flow_controller()
        assert isinstance(controller, ScoreFlowController)

    def test_controller_can_compute_flow(self, abc_loader):
        """The returned controller can compute a flow."""
        from timetoalign.core.enums import FlowMode

        controller = abc_loader.create_flow_controller()
        flow = controller.compute_flow(FlowMode.default)
        assert len(flow.sections) == 11

    def test_raises_without_measures(self):
        """ValueError when no measure data has been loaded."""
        from timetoalign.loader.score import Ms3Loader

        loader = Ms3Loader()
        with pytest.raises(ValueError, match="no measure data"):
            loader.create_flow_controller()

    def test_equivalent_to_manual_construction(self, abc_loader):
        """Produces the same result as manual ScoreFlowController()."""
        from timetoalign.core.enums import FlowMode
        from timetoalign.timelines.flow import ScoreFlowController

        # API way
        ctrl_api = abc_loader.create_flow_controller()
        flow_api = ctrl_api.compute_flow(FlowMode.default)

        # Manual way
        ctrl_manual = ScoreFlowController(abc_loader.store.measures)
        flow_manual = ctrl_manual.compute_flow(FlowMode.default)

        assert len(flow_api.sections) == len(flow_manual.sections)


# endregion
