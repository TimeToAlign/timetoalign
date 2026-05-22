"""Tests for unified TimeStamp and TimeIntervalStamp.

These tests verify the unified timestamp architecture where Timeline and
TimelineGroup use the same coordinate resolution mechanism via InterpolationMaps.
"""

from __future__ import annotations

import pytest

from timetoalign.core import TimeIntervalStamp, TimeUnit
from timetoalign.maps import TableMap
from timetoalign.timelines import Timeline


class TestTimeStampBasics:
    """Basic TimeStamp functionality tests."""

    def test_get_timestamp_simple(self):
        """Get a timestamp at a specific coordinate."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)
        ts = tl.get_timestamp(50.0)

        assert ts.axis == 50.0
        assert ts.source_id == tl.id
        # Note: is_interpolated is True by default (row_index=-1)
        # Only False if created from a table with exact row match
        assert ts.is_interpolated

    def test_get_timestamp_from_coordinate(self):
        """Get timestamp from a Coordinate object."""
        from timetoalign.core import Coordinate

        tl = Timeline(length=100, unit=TimeUnit.seconds)
        coord = Coordinate(25.0, TimeUnit.seconds)
        ts = tl.get_timestamp(coord)

        assert ts.axis == 25.0

    def test_timestamp_source(self):
        """TimeStamp references its source timeline."""
        tl = Timeline(length=100, unit=TimeUnit.seconds, uid="my_timeline")
        ts = tl.get_timestamp(50.0)

        assert ts.source is tl
        assert ts.source_id == "my_timeline"


class TestTimeStampWithChildren:
    """TimeStamp coordinate resolution with nested timelines."""

    def test_get_child_coordinate(self):
        """Get coordinate on a child timeline."""
        parent = Timeline(length=100, unit=TimeUnit.seconds)
        child = Timeline(length=40, unit=TimeUnit.seconds, uid="child:1")

        # Child embedded at offset 20 in parent
        parent.add_child(child, offset=20)

        # Get timestamp at parent coordinate 30
        ts = parent.get_timestamp(30.0)

        # Parent 30 = Child 10 (30 - 20)
        assert ts["child:1"] == 10.0
        assert ts.get("child:1") == 10.0

    def test_get_child_coordinate_at_boundary(self):
        """Get child coordinate at exact boundaries.

        Child spans [offset, offset + length) on the parent, i.e. [25, 75).
        The right endpoint is *exclusive* per the TTA interval model.
        """
        parent = Timeline(length=100, unit=TimeUnit.seconds)
        child = Timeline(length=50, unit=TimeUnit.seconds, uid="child:1")

        parent.add_child(child, offset=25)

        # At child start (parent 25) -- left-inclusive
        ts_start = parent.get_timestamp(25.0)
        assert ts_start["child:1"] == 0.0

        # At child end (parent 75) -- right-exclusive, so None
        ts_end = parent.get_timestamp(75.0)
        assert ts_end["child:1"] is None

        # Just before child end (parent 74.999...) -- still inside
        ts_just_before = parent.get_timestamp(74.999)
        assert ts_just_before["child:1"] is not None

    def test_child_out_of_range_returns_none(self):
        """Coordinates outside child range return None.

        Child spans [30, 70) on the parent.  Parent coordinate 10 is
        outside that span, so ``get()`` returns None rather than
        extrapolating a meaningless negative local coordinate.
        """
        parent = Timeline(length=100, unit=TimeUnit.seconds)
        child = Timeline(length=40, unit=TimeUnit.seconds, uid="child:1")

        parent.add_child(child, offset=30)

        # Before child (parent 10) -- outside [30, 70)
        ts_before = parent.get_timestamp(10.0)
        assert ts_before["child:1"] is None

    def test_multiple_children(self):
        """Timestamps work with multiple children.

        child1 spans [10, 40) and child2 spans [60, 90) on the parent.
        At parent coordinate 40, child1 is *excluded* (right-exclusive)
        and child2 has not started yet, so both return None.
        At parent coordinate 35, child1 returns 25.0 and child2 returns
        None.
        """
        parent = Timeline(length=100, unit=TimeUnit.seconds)
        child1 = Timeline(length=30, unit=TimeUnit.seconds, uid="child:1")
        child2 = Timeline(length=30, unit=TimeUnit.seconds, uid="child:2")

        parent.add_child(child1, offset=10)
        parent.add_child(child2, offset=60)

        # Parent 40 is at the right-exclusive boundary of child1 [10, 40)
        ts_boundary = parent.get_timestamp(40.0)
        assert ts_boundary["child:1"] is None
        assert ts_boundary["child:2"] is None

        # Parent 35 is inside child1 [10, 40): local = 35 - 10 = 25
        ts_inside = parent.get_timestamp(35.0)
        assert ts_inside["child:1"] == 25.0
        assert ts_inside["child:2"] is None

        # Parent 70 is inside child2 [60, 90): local = 70 - 60 = 10
        ts_child2 = parent.get_timestamp(70.0)
        assert ts_child2["child:1"] is None
        assert ts_child2["child:2"] == 10.0

    def test_to_dict(self):
        """TimeStamp can be materialized to dict."""
        parent = Timeline(length=100, unit=TimeUnit.seconds, uid="parent:1")
        child = Timeline(length=40, unit=TimeUnit.seconds, uid="child:1")

        parent.add_child(child, offset=20)

        ts = parent.get_timestamp(30.0)
        result = ts.to_dict()

        assert result["parent:1"] == 30.0
        assert result["child:1"] == 10.0

    def test_present_timelines(self):
        """Get list of timelines with coordinates."""
        parent = Timeline(length=100, unit=TimeUnit.seconds, uid="parent:1")
        child = Timeline(length=40, unit=TimeUnit.seconds, uid="child:1")

        parent.add_child(child, offset=20)

        ts = parent.get_timestamp(30.0)
        present = ts.present_timelines

        assert "parent:1" in present
        assert "child:1" in present


class TestTimeStampWithCMaps:
    """TimeStamp with C-Map unit conversion."""

    def test_unit_conversion(self):
        """Get coordinate converted to another unit."""
        tl = Timeline(length=960, unit=TimeUnit.ticks)

        # Add tempo map: ticks -> seconds
        tempo_map = TableMap(
            x_values=[0, 960],
            y_values=[0.0, 2.0],  # 960 ticks = 2 seconds
            source_unit=TimeUnit.ticks,
            target_unit=TimeUnit.seconds,
        )
        tl.add_conversion_map(tempo_map)

        ts = tl.get_timestamp(480)

        # 480 ticks = 1.0 seconds
        assert ts.get_unit(TimeUnit.seconds) == pytest.approx(1.0)

    def test_timestamp_from_unit(self):
        """Create timestamp specifying coordinate in different unit."""
        tl = Timeline(length=960, unit=TimeUnit.ticks)

        # Add tempo map: ticks -> seconds
        tempo_map = TableMap(
            x_values=[0, 960],
            y_values=[0.0, 2.0],
            source_unit=TimeUnit.ticks,
            target_unit=TimeUnit.seconds,
        )
        tl.add_conversion_map(tempo_map)

        # Query at 1.5 seconds
        ts = tl.get_timestamp(1.5, unit=TimeUnit.seconds)

        # 1.5 seconds = 720 ticks
        assert ts.axis == pytest.approx(720.0)

    def test_subscript_unit_access(self):
        """Subscript access works for unit names."""
        tl = Timeline(length=960, unit=TimeUnit.ticks)

        tempo_map = TableMap(
            x_values=[0, 960],
            y_values=[0.0, 2.0],
            source_unit=TimeUnit.ticks,
            target_unit=TimeUnit.seconds,
        )
        tl.add_conversion_map(tempo_map)

        ts = tl.get_timestamp(480)

        # Access by unit name string
        result = ts["seconds"]
        assert result == pytest.approx(1.0)

    def test_no_cmap_returns_none(self):
        """get_unit returns None when no C-Map available."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)
        ts = tl.get_timestamp(50.0)

        result = ts.get_unit(TimeUnit.pixels)
        assert result is None

    def test_timestamp_from_unit_raises_without_cmap(self):
        """get_timestamp raises when unit specified but no C-Map."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)

        with pytest.raises(ValueError, match="No C-Map available"):
            tl.get_timestamp(50.0, unit=TimeUnit.pixels)

    def test_to_dict_with_units(self):
        """to_dict includes C-Map conversions."""
        tl = Timeline(length=960, unit=TimeUnit.ticks, uid="tl:1")

        tempo_map = TableMap(
            x_values=[0, 960],
            y_values=[0.0, 2.0],
            source_unit=TimeUnit.ticks,
            target_unit=TimeUnit.seconds,
        )
        tl.add_conversion_map(tempo_map)

        ts = tl.get_timestamp(480)
        result = ts.to_dict(conversion_units=[TimeUnit.seconds])

        assert result["tl:1"] == 480.0
        assert result["seconds"] == pytest.approx(1.0)


class TestTimeIntervalStamp:
    """TimeIntervalStamp tests."""

    def test_create_interval_stamp(self):
        """Create an interval stamp."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)
        interval = tl.get_interval_stamp(10.0, 50.0)

        assert interval.start.axis == 10.0
        assert interval.end.axis == 50.0
        assert interval.duration == 40.0

    def test_get_interval_for_child(self):
        """Get interval on child timeline."""
        parent = Timeline(length=100, unit=TimeUnit.seconds, uid="parent:1")
        child = Timeline(length=60, unit=TimeUnit.seconds, uid="child:1")

        parent.add_child(child, offset=20)

        # Parent interval [30, 70] should be child interval [10, 50]
        interval = parent.get_interval_stamp(30.0, 70.0)

        child_interval = interval.get_interval("child:1")
        assert child_interval == (10.0, 50.0)

    def test_get_duration_for_child(self):
        """Get duration on child timeline."""
        parent = Timeline(length=100, unit=TimeUnit.seconds, uid="parent:1")
        child = Timeline(length=80, unit=TimeUnit.seconds, uid="child:1")

        parent.add_child(child, offset=10)

        interval = parent.get_interval_stamp(20.0, 60.0)

        # Child duration = 40 (same as parent, linear mapping)
        assert interval.get_duration("child:1") == 40.0

    def test_zip_intervals(self):
        """Zip all intervals across timelines."""
        parent = Timeline(length=100, unit=TimeUnit.seconds, uid="parent:1")
        child1 = Timeline(length=80, unit=TimeUnit.seconds, uid="child:1")
        child2 = Timeline(length=60, unit=TimeUnit.seconds, uid="child:2")

        parent.add_child(child1, offset=10)
        parent.add_child(child2, offset=30)

        interval = parent.get_interval_stamp(40.0, 80.0)
        zipped = interval.zip_intervals()

        assert zipped["parent:1"] == (40.0, 80.0)
        assert zipped["child:1"] == (30.0, 70.0)  # 40-10, 80-10
        assert zipped["child:2"] == (10.0, 50.0)  # 40-30, 80-30

    def test_subscript_access(self):
        """Subscript access returns interval tuple."""
        parent = Timeline(length=100, unit=TimeUnit.seconds, uid="parent:1")
        child = Timeline(length=80, unit=TimeUnit.seconds, uid="child:1")

        parent.add_child(child, offset=10)

        interval = parent.get_interval_stamp(20.0, 60.0)

        assert interval["child:1"] == (10.0, 50.0)

    def test_iteration(self):
        """Can iterate over start and end."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)
        interval = tl.get_interval_stamp(10.0, 50.0)

        start, end = interval
        assert start.axis == 10.0
        assert end.axis == 50.0

    def test_str_basic(self):
        """__str__ shows header and aligned start/end columns."""
        parent = Timeline(length=100, unit=TimeUnit.seconds, uid="tl:1")
        child = Timeline(length=60, unit=TimeUnit.seconds, uid="child:1")
        parent.add_child(child, offset=20)

        # Both endpoints inside child [20, 80)
        interval = parent.get_interval_stamp(30.0, 70.0)
        text = str(interval)

        assert "TimeIntervalStamp [30, 70) seconds" in text
        assert "start" in text
        assert "end" in text
        assert "tl:1" in text
        assert "child:1" in text

    def test_str_straddling_children(self):
        """__str__ shows '-' when an endpoint falls outside a child's span.

        child1 spans [0, 40), child2 spans [50, 90) on the parent.
        An interval [35, 55) has its start in child1 and its end in child2.
        """
        parent = Timeline(length=100, unit=TimeUnit.seconds, uid="parent:1")
        child1 = Timeline(length=40, unit=TimeUnit.seconds, uid="sec:A")
        child2 = Timeline(length=40, unit=TimeUnit.seconds, uid="sec:B")
        parent.add_child(child1, offset=0)
        parent.add_child(child2, offset=50)

        interval = parent.get_interval_stamp(35.0, 55.0)
        text = str(interval)

        # Parent row: both endpoints present
        assert "parent:1" in text
        # sec:A: start=35 is inside [0, 40), end=55 is outside -> dash
        assert "sec:A" in text
        # sec:B: start=35 is outside [50, 90), end=55 is inside -> dash
        assert "sec:B" in text

        # Check the actual values by parsing lines
        lines = text.strip().split("\n")
        sec_a_line = [line for line in lines if "sec:A" in line][0]
        sec_b_line = [line for line in lines if "sec:B" in line][0]

        # sec:A shows start=35, end='-'
        assert "35" in sec_a_line
        assert "-" in sec_a_line

        # sec:B shows start='-', end=5
        assert "5" in sec_b_line
        assert "-" in sec_b_line

    def test_str_omits_fully_out_of_range_children(self):
        """Children where both endpoints are out of range are omitted."""
        parent = Timeline(length=100, unit=TimeUnit.seconds, uid="tl:1")
        child = Timeline(length=10, unit=TimeUnit.seconds, uid="far_child")
        parent.add_child(child, offset=80)

        # Interval [5, 15) - far_child is at [80, 90), both endpoints outside
        interval = parent.get_interval_stamp(5.0, 15.0)
        text = str(interval)

        assert "far_child" not in text


class TestTimeStampValidation:
    """Validation and error handling tests."""

    def test_interval_same_source(self):
        """Start and end must be from same source."""
        tl1 = Timeline(length=100, unit=TimeUnit.seconds, uid="tl1")
        tl2 = Timeline(length=100, unit=TimeUnit.seconds, uid="tl2")

        ts1 = tl1.get_timestamp(10.0)
        ts2 = tl2.get_timestamp(50.0)

        with pytest.raises(ValueError, match="same source"):
            TimeIntervalStamp(start=ts1, end=ts2)


class TestTimelineTimeStampSourceProtocol:
    """Verify Timeline implements TimeStampSource protocol."""

    def test_timeline_has_required_methods(self):
        """Timeline has all TimeStampSource protocol methods."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)

        # These methods are required by the protocol
        assert hasattr(tl, "_get_interpolation_map")
        assert hasattr(tl, "_get_unit_map")
        assert hasattr(tl, "_get_related_timeline_ids")
        assert hasattr(tl, "_get_available_units")

    def test_get_related_timeline_ids(self):
        """_get_related_timeline_ids returns child IDs."""
        parent = Timeline(length=100, unit=TimeUnit.seconds)
        child1 = Timeline(length=40, unit=TimeUnit.seconds, uid="child:1")
        child2 = Timeline(length=40, unit=TimeUnit.seconds, uid="child:2")

        parent.add_child(child1, offset=0)
        parent.add_child(child2, offset=50)

        ids = parent._get_related_timeline_ids()
        assert "child:1" in ids
        assert "child:2" in ids

    def test_get_available_units(self):
        """_get_available_units returns C-Map target units."""
        tl = Timeline(length=960, unit=TimeUnit.ticks)

        tempo_map = TableMap(
            x_values=[0, 960],
            y_values=[0.0, 2.0],
            source_unit=TimeUnit.ticks,
            target_unit=TimeUnit.seconds,
        )
        tl.add_conversion_map(tempo_map)

        units = tl._get_available_units()
        assert TimeUnit.seconds in units


class TestTimeStampWithUnits:
    """Tests for unit metadata and Coordinate access in TimeStamps."""

    def test_axis_coordinate_property(self):
        """axis_coordinate returns proper Coordinate object."""
        from timetoalign.core import Coordinate

        tl = Timeline(length=100, unit=TimeUnit.seconds, uid="test:1")
        ts = tl.get_timestamp(50.0)

        coord = ts.axis_coordinate
        assert isinstance(coord, Coordinate)
        assert coord.value == 50.0
        assert coord.unit == TimeUnit.seconds

    def test_get_coordinate_for_self(self):
        """get_coordinate returns Coordinate for source timeline."""
        from timetoalign.core import Coordinate

        tl = Timeline(length=100, unit=TimeUnit.seconds, uid="test:1")
        ts = tl.get_timestamp(50.0)

        coord = ts.get_coordinate("test:1")
        assert isinstance(coord, Coordinate)
        assert coord.value == 50.0
        assert coord.unit == TimeUnit.seconds

    def test_get_coordinate_for_child(self):
        """get_coordinate returns proper Coordinate for child."""
        from timetoalign.core import Coordinate

        # Children must share parent's unit (TTA model constraint)
        parent = Timeline(length=100, unit=TimeUnit.seconds, uid="parent:1")
        child = Timeline(length=40, unit=TimeUnit.seconds, uid="child:1")

        parent.add_child(child, offset=20)

        ts = parent.get_timestamp(30.0)

        # Child coordinate at parent 30 is 10 (30 - 20)
        child_coord = ts.get_coordinate("child:1")
        assert isinstance(child_coord, Coordinate)
        assert child_coord.value == 10.0
        assert child_coord.unit == TimeUnit.seconds  # Same unit as parent

    def test_get_coordinate_unknown_timeline_returns_none(self):
        """get_coordinate returns None for unknown timeline."""
        tl = Timeline(length=100, unit=TimeUnit.seconds, uid="test:1")
        ts = tl.get_timestamp(50.0)

        result = ts.get_coordinate("unknown:1")
        assert result is None

    def test_get_unit_for_timeline_self(self):
        """_get_unit_for_timeline returns own unit for source."""
        tl = Timeline(length=100, unit=TimeUnit.pixels, uid="test:1")

        unit = tl._get_unit_for_timeline("test:1")
        assert unit == TimeUnit.pixels

    def test_get_unit_for_timeline_child(self):
        """_get_unit_for_timeline returns child's unit (same as parent per TTA model)."""
        # Children must share parent's unit (TTA model constraint)
        parent = Timeline(length=100, unit=TimeUnit.seconds, uid="parent:1")
        child = Timeline(length=40, unit=TimeUnit.seconds, uid="child:1")

        parent.add_child(child, offset=20)

        unit = parent._get_unit_for_timeline("child:1")
        assert unit == TimeUnit.seconds  # Same as parent

    def test_get_unit_for_timeline_unknown(self):
        """_get_unit_for_timeline returns None for unknown."""
        tl = Timeline(length=100, unit=TimeUnit.seconds, uid="test:1")

        unit = tl._get_unit_for_timeline("unknown:1")
        assert unit is None


class TestTimeIntervalStampWithUnits:
    """Tests for unit metadata in TimeIntervalStamp."""

    def test_get_coordinate_interval(self):
        """get_coordinate_interval returns Coordinate tuples."""
        from timetoalign.core import Coordinate

        # Children must share parent's unit (TTA model constraint)
        parent = Timeline(length=100, unit=TimeUnit.seconds, uid="parent:1")
        child = Timeline(length=80, unit=TimeUnit.seconds, uid="child:1")

        parent.add_child(child, offset=10)

        interval = parent.get_interval_stamp(20.0, 60.0)

        # Child interval should be [10, 50] in seconds (same as parent)
        child_interval = interval.get_coordinate_interval("child:1")
        assert child_interval is not None

        start, end = child_interval
        assert isinstance(start, Coordinate)
        assert isinstance(end, Coordinate)
        assert start.value == 10.0
        assert end.value == 50.0
        assert start.unit == TimeUnit.seconds
        assert end.unit == TimeUnit.seconds

    def test_get_coordinate_interval_unknown(self):
        """get_coordinate_interval returns None for unknown timeline."""
        tl = Timeline(length=100, unit=TimeUnit.seconds, uid="test:1")
        interval = tl.get_interval_stamp(10.0, 50.0)

        result = interval.get_coordinate_interval("unknown:1")
        assert result is None


class TestTimestampTableMetadata:
    """Tests for unit metadata in timestamp tables."""

    def test_timestamp_table_has_unit_metadata(self):
        """get_timestamp_table includes unit metadata on fields."""
        tl = Timeline(length=100, unit=TimeUnit.seconds, uid="test:1")
        table = tl.get_timestamp_table(coordinates=[0.0, 50.0, 100.0])

        # Check axis field metadata
        axis_field = table.schema.field("axis")
        assert axis_field.metadata is not None
        assert axis_field.metadata[b"unit"] == b"seconds"
        assert axis_field.metadata[b"timeline_id"] == b"test:1"

        # Check timeline field metadata
        tl_field = table.schema.field("test:1")
        assert tl_field.metadata is not None
        assert tl_field.metadata[b"unit"] == b"seconds"

    def test_timestamp_table_child_metadata(self):
        """Child fields have unit metadata (same as parent per TTA model)."""
        # Children must share parent's unit (TTA model constraint)
        parent = Timeline(length=100, unit=TimeUnit.seconds, uid="parent:1")
        child = Timeline(length=40, unit=TimeUnit.seconds, uid="child:1")

        parent.add_child(child, offset=20)

        table = parent.get_timestamp_table(coordinates=[30.0, 50.0])

        # Check child field has its unit metadata
        child_field = table.schema.field("child:1")
        assert child_field.metadata is not None
        assert child_field.metadata[b"unit"] == b"seconds"  # Same as parent
        assert child_field.metadata[b"timeline_id"] == b"child:1"

    def test_timestamp_table_cmap_metadata(self):
        """C-Map fields have target unit metadata."""
        tl = Timeline(length=960, unit=TimeUnit.ticks, uid="test:1")

        tempo_map = TableMap(
            x_values=[0, 960],
            y_values=[0.0, 2.0],
            source_unit=TimeUnit.ticks,
            target_unit=TimeUnit.seconds,
        )
        tl.add_conversion_map(tempo_map)

        table = tl.get_timestamp_table(
            coordinates=[0.0, 480.0, 960.0], conversion_maps=[tempo_map]
        )

        # Find the C-Map field by name (field names use cmap.name, not cmap.id)
        cmap_field = table.schema.field(tempo_map.name)
        assert cmap_field.metadata is not None
        assert cmap_field.metadata[b"unit"] == b"seconds"  # Target unit
        assert cmap_field.metadata[b"cmap_id"] == tempo_map.id.encode("utf-8")
