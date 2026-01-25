"""Tests for Timeline conversion map integration."""

import numpy as np
import pytest

from timetoalign.core import Coordinate, TimeUnit
from timetoalign.maps.linear import ScalarMap
from timetoalign.timelines import Timeline


class TestMapIntegration:
    def test_add_conversion_map(self):
        tl = Timeline(unit=TimeUnit.seconds)
        cmap = ScalarMap(scalar=1000, source_unit="seconds", target_unit="milliseconds")

        tl.add_conversion_map(cmap)

        # Verify it's stored (private access for testing)
        assert cmap.id in tl._conversion_maps
        assert tl._conversion_maps[cmap.id] is cmap

    def test_add_conversion_map_validation(self):
        tl = Timeline(unit=TimeUnit.seconds)
        cmap = ScalarMap(scalar=1.0, source_unit="ticks")  # Mismatch

        with pytest.raises(ValueError, match="does not match"):
            tl.add_conversion_map(cmap)

    def test_get_conversion_map(self):
        tl = Timeline(unit=TimeUnit.seconds)
        cmap1 = ScalarMap(
            scalar=1000, source_unit="seconds", target_unit="milliseconds"
        )
        cmap2 = ScalarMap(scalar=1 / 60, source_unit="seconds", target_unit="minutes")

        tl.add_conversion_map(cmap1)
        tl.add_conversion_map(cmap2)

        assert tl.get_conversion_map("milliseconds") is cmap1
        assert tl.get_conversion_map("minutes") is cmap2
        assert tl.get_conversion_map("ticks") is None

    def test_convert_to(self):
        tl = Timeline(unit=TimeUnit.seconds)
        cmap = ScalarMap(scalar=1000, source_unit="seconds", target_unit="milliseconds")
        tl.add_conversion_map(cmap)

        # Scalar
        val = tl.convert_to(1.5, "milliseconds")
        assert val == 1500.0

        # Array
        arr = np.array([1.0, 2.0])
        conv = tl.convert_to(arr, "milliseconds")
        np.testing.assert_array_equal(conv, np.array([1000.0, 2000.0]))

        # Error if no map
        with pytest.raises(ValueError, match="No conversion map found"):
            tl.convert_to(1.0, "ticks")

    def test_convert_coordinate_object(self):
        tl = Timeline(unit=TimeUnit.seconds)
        cmap = ScalarMap(scalar=1000, source_unit="seconds", target_unit="milliseconds")
        tl.add_conversion_map(cmap)

        c = Coordinate(1.5, TimeUnit.seconds)
        val = tl.convert_to(c, "milliseconds")
        assert val == 1500.0

    def test_serialization_with_maps(self):
        tl = Timeline(unit=TimeUnit.seconds, uid="tl1")
        cmap = ScalarMap(
            scalar=1000, source_unit="seconds", target_unit="milliseconds", uid="cmap1"
        )
        tl.add_conversion_map(cmap)

        data = tl.to_dict()
        assert "conversion_maps" in data
        assert len(data["conversion_maps"]) == 1
        assert data["conversion_maps"][0]["id"] == "cmap1"

        # Round trip
        restored = Timeline.from_dict(data)
        assert restored.id == "tl1"
        restored_cmap = restored.get_conversion_map("milliseconds")
        assert restored_cmap is not None
        assert restored_cmap.id == "cmap1"
        assert restored_cmap(1.0) == 1000.0
