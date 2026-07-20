"""Tests for the shared Stamp contract as implemented by TimeStamp."""

from __future__ import annotations

import pytest

from timetoalign.core import Coordinate, TimeUnit
from timetoalign.core.timestamp import Stamp, TimeStamp
from timetoalign.maps import TableMap
from timetoalign.timelines import Timeline


def _timeline_with_maps() -> Timeline:
    """Build a timeline with exact-value conversion maps."""
    timeline = Timeline(length=100, unit=TimeUnit.seconds, uid="clock")
    timeline.add_conversion_map(
        TableMap(
            x_values=[0.0, 100.0],
            y_values=[0.0, 100000.0],
            source_unit=TimeUnit.seconds,
            target_unit=TimeUnit.milliseconds,
            uid="clock-ms",
        )
    )
    timeline.add_conversion_map(
        TableMap(
            x_values=[0.0, 100.0],
            y_values=[0.0, 5000.0],
            source_unit=TimeUnit.seconds,
            target_unit=TimeUnit.frames,
            uid="clock-frames",
        )
    )
    return timeline


def test_timestamp_implements_stamp_contract() -> None:
    """TimeStamp exposes every Stamp member with the documented types."""
    timeline = _timeline_with_maps()
    stamp = timeline.get_timestamp(25.0)

    assert isinstance(stamp, Stamp)
    assert isinstance(stamp, TimeStamp)
    assert isinstance(stamp.axis, float)
    assert stamp.source is timeline
    assert isinstance(stamp.source_id, str)
    assert isinstance(stamp.present_timelines, list)
    assert isinstance(stamp.is_interpolated, bool)
    assert isinstance(stamp.get(timeline.id), float)
    assert isinstance(stamp.get_unit(TimeUnit.milliseconds), float)
    assert isinstance(stamp.to_dict(), dict)
    assert stamp._unit_for(timeline.id) == TimeUnit.seconds


def test_coordinate_and_subscript_contract() -> None:
    """Coordinate values retain their unit and both subscript paths work."""
    timeline = _timeline_with_maps()
    stamp = timeline.get_timestamp(25.0)

    coordinate = stamp.get_coordinate(timeline.id)
    assert isinstance(coordinate, Coordinate)
    assert coordinate.value == 25.0
    assert coordinate.unit == TimeUnit.seconds
    assert stamp.axis_coordinate.value == 25.0
    assert stamp.axis_coordinate.unit == TimeUnit.seconds

    assert stamp[timeline.id] == 25.0
    assert stamp["milliseconds"] == 25000.0
    with pytest.raises(KeyError):
        _ = stamp["not-a-timeline-or-unit"]


def test_conversion_maps_false_disables_unit_resolution() -> None:
    """False disables both unit conversion and its unit-name subscript path."""
    timeline = _timeline_with_maps()
    stamp = timeline.get_timestamp(25.0, conversion_maps=False)

    assert stamp.get_unit(TimeUnit.milliseconds) is None
    with pytest.raises(KeyError):
        _ = stamp["milliseconds"]


def test_conversion_maps_allowed_set_restricts_units() -> None:
    """An allowed set exposes only the named conversion maps."""
    timeline = _timeline_with_maps()
    stamp = timeline.get_timestamp(25.0, conversion_maps=["clock-ms"])

    assert stamp.get_unit(TimeUnit.milliseconds) == 25000.0
    assert stamp.get_unit(TimeUnit.frames) is None
    with pytest.raises(KeyError):
        _ = stamp["frames"]


def test_to_dict_shape_is_stable() -> None:
    """to_dict returns the source coordinate and explicitly requested unit."""
    timeline = _timeline_with_maps()
    stamp = timeline.get_timestamp(25.0)

    assert stamp.to_dict(conversion_units=[TimeUnit.milliseconds]) == {
        "clock": 25.0,
        "milliseconds": 25000.0,
    }
