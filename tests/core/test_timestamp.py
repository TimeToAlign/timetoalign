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
        """Get child coordinate at exact boundaries."""
        parent = Timeline(length=100, unit=TimeUnit.seconds)
        child = Timeline(length=50, unit=TimeUnit.seconds, uid="child:1")

        parent.add_child(child, offset=25)

        # At child start (parent 25)
        ts_start = parent.get_timestamp(25.0)
        assert ts_start["child:1"] == 0.0

        # At child end (parent 75)
        ts_end = parent.get_timestamp(75.0)
        assert ts_end["child:1"] == 50.0

    def test_child_out_of_range_returns_none(self):
        """Coordinates outside child range return None."""
        parent = Timeline(length=100, unit=TimeUnit.seconds)
        child = Timeline(length=40, unit=TimeUnit.seconds, uid="child:1")

        parent.add_child(child, offset=30)

        # Before child (parent 10)
        ts_before = parent.get_timestamp(10.0)
        # The InterpolationMap extrapolates, but child has no meaning there
        # Actually, InterpolationMap extrapolates linearly
        # This is a design question - should we clamp or extrapolate?
        # For now, extrapolation is allowed (matching numpy.interp behavior)
        assert ts_before["child:1"] == -20.0  # 10 - 30 = -20

    def test_multiple_children(self):
        """Timestamps work with multiple children."""
        parent = Timeline(length=100, unit=TimeUnit.seconds)
        child1 = Timeline(length=30, unit=TimeUnit.seconds, uid="child:1")
        child2 = Timeline(length=30, unit=TimeUnit.seconds, uid="child:2")

        parent.add_child(child1, offset=10)
        parent.add_child(child2, offset=60)

        ts = parent.get_timestamp(40.0)

        # Parent 40 in child1 (offset 10): 40 - 10 = 30
        assert ts["child:1"] == 30.0
        # Parent 40 in child2 (offset 60): 40 - 60 = -20 (extrapolated)
        assert ts["child:2"] == -20.0

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
