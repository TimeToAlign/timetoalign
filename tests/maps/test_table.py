"""Tests for table-based maps."""

import numpy as np
import pytest

from timetoalign.maps.table import ExtrapolationPolicy, InterpolationKind, TableMap


class TestTableMap:
    def test_initialization(self):
        m = TableMap(x_values=[0, 10], y_values=[0, 20])
        assert m.x_min == 0
        assert m.x_max == 10
        assert m.kind == InterpolationKind.linear

        with pytest.raises(ValueError, match="same length"):
            TableMap(x_values=[0, 10], y_values=[0])

        with pytest.raises(ValueError, match="monotonically increasing"):
            TableMap(x_values=[10, 0], y_values=[0, 20])

        with pytest.raises(ValueError, match="at least 2"):
            TableMap(x_values=[0], y_values=[0])

    def test_linear_interpolation(self):
        m = TableMap(x_values=[0, 10, 20], y_values=[0, 100, 150])

        assert m(0) == 0.0
        assert m(10) == 100.0
        assert m(20) == 150.0

        # Midpoints
        assert m(5) == 50.0  # (0,0) to (10,100) -> slope 10
        assert m(15) == 125.0  # (10,100) to (20,150) -> slope 5

    def test_extrapolation_policies(self):
        # Default: extrapolate
        m = TableMap(x_values=[0, 10], y_values=[0, 20])
        assert m(20) == 40.0
        assert m(-10) == -20.0

        # Constant (clamp)
        m_const = TableMap(
            x_values=[0, 10], y_values=[0, 20], extrapolate=ExtrapolationPolicy.constant
        )
        assert m_const(20) == 20.0
        assert m_const(-10) == 0.0

        # Error
        m_err = TableMap(
            x_values=[0, 10], y_values=[0, 20], extrapolate=ExtrapolationPolicy.error
        )
        with pytest.raises(ValueError, match="outside table bounds"):
            m_err(20)

    def test_other_interpolations(self):
        x = [0, 10]
        y = [0, 20]

        # Nearest
        m_near = TableMap(x_values=x, y_values=y, kind=InterpolationKind.nearest)
        assert m_near(4) == 0.0  # Closer to 0
        assert m_near(6) == 20.0  # Closer to 10

        # Previous (Step Left)
        m_prev = TableMap(x_values=x, y_values=y, kind=InterpolationKind.previous)
        assert m_prev(9.9) == 0.0
        assert m_prev(10) == 20.0

        # Next (Step Right)
        m_next = TableMap(x_values=x, y_values=y, kind=InterpolationKind.next)
        assert m_next(0.1) == 20.0
        assert m_next(0) == 0.0

    def test_inverse(self):
        m = TableMap(x_values=[0, 10, 20], y_values=[0, 100, 300])
        assert m.is_invertible

        inv = m.inverse()
        assert np.array_equal(inv.x_values, [0, 100, 300])
        assert np.array_equal(inv.y_values, [0, 10, 20])

        # Round trip
        val = 15.0
        mapped = m(val)  # 10->100, 20->300. Slope 20. 15 -> 100 + 5*20 = 200
        assert mapped == 200.0
        assert inv(mapped) == 15.0

    def test_inverse_decreasing(self):
        # y values decreasing
        m = TableMap(x_values=[0, 10], y_values=[100, 0])
        assert m.is_invertible

        inv = m.inverse()
        # Should reverse so x is increasing
        assert np.array_equal(inv.x_values, [0, 100])
        assert np.array_equal(inv.y_values, [10, 0])

        assert m(5) == 50.0
        assert inv(50) == 5.0

    def test_from_tempo(self):
        # 120 BPM = 0.5 sec/beat = 0.5 sec/480 ticks = 1/960 sec/tick
        # 60 BPM = 1.0 sec/beat = 1.0 sec/480 ticks = 1/480 sec/tick

        m = TableMap.from_tempo_changes(
            tick_positions=[0, 960], tempos_bpm=[120.0, 60.0], ticks_per_quarter=480
        )

        # 0 -> 0 sec
        assert m(0) == 0.0

        # 480 ticks (1 quarter) @ 120 bpm -> 0.5 sec
        assert m(480) == 0.5

        # 960 ticks (2 quarters) @ 120 bpm -> 1.0 sec
        assert m(960) == 1.0

        # 960 + 480 ticks (1 more quarter) @ 60 bpm -> 1.0 + 1.0 = 2.0 sec
        assert m(1440) == 2.0
