"""Tests for linear conversion maps."""

from fractions import Fraction

import numpy as np
import pytest

from timetoalign.core.enums import TimeUnit
from timetoalign.core.types import Coordinate
from timetoalign.maps.linear import LinearMap, ScalarMap, ShiftMap


class TestLinearMap:
    def test_initialization(self):
        m = LinearMap(scalar=2.0, offset=10.0)
        assert m.scalar == 2.0
        assert m.offset == 10.0
        assert not m.is_identity

        m_ident = LinearMap(scalar=1.0, offset=0.0)
        assert m_ident.is_identity

        with pytest.raises(ValueError, match="not invertible"):
            LinearMap(scalar=0.0)

    def test_conversion_scalar(self):
        m = LinearMap(scalar=2.0, offset=10.0)
        # y = 2x + 10
        assert m(0) == 10.0
        assert m(5) == 20.0
        assert m(-5) == 0.0

        # With coordinate
        c = Coordinate(5, TimeUnit.ticks)
        # Should return raw value
        assert m(c) == 20.0

    def test_conversion_array(self):
        m = LinearMap(scalar=2.0, offset=10.0)
        arr = np.array([0, 5, -5])
        expected = np.array([10.0, 20.0, 0.0])
        np.testing.assert_array_equal(m(arr), expected)

    def test_inverse(self):
        m = LinearMap(scalar=2.0, offset=10.0)
        inv = m.inverse()

        # Original: y = 2x + 10
        # Inverse: x = (y - 10) / 2 = 0.5y - 5
        assert isinstance(inv, LinearMap)
        assert inv.scalar == 0.5
        assert inv.offset == -5.0

        # Round trip
        val = 42.0
        assert inv(m(val)) == val

    def test_composition(self):
        m1 = LinearMap(scalar=2.0, offset=10.0)
        m2 = LinearMap(scalar=0.5, offset=5.0)

        # m1: y = 2x + 10
        # m2: z = 0.5y + 5 = 0.5(2x + 10) + 5 = x + 5 + 5 = x + 10

        comp = m1.compose_with(m2)
        assert isinstance(comp, LinearMap)
        assert comp.scalar == 1.0
        assert comp.offset == 10.0

        assert comp(5) == 15.0  # 5 -> 20 -> 15

    def test_fraction_support(self):
        m = LinearMap(scalar=Fraction(1, 3), offset=Fraction(2, 3))
        res = m(Fraction(1, 1))
        # 1/3 * 1 + 2/3 = 1
        assert res == Fraction(1, 1)


class TestScalarMap:
    def test_basic(self):
        m = ScalarMap(scalar=10.0)
        assert m.scalar == 10.0
        assert m(5) == 50.0

        inv = m.inverse()
        assert inv.scalar == 0.1
        assert inv(50) == 5.0

    def test_units(self):
        m = ScalarMap(scalar=1000, source_unit="seconds", target_unit="milliseconds")
        assert m.source_unit == TimeUnit.seconds
        assert m.target_unit == TimeUnit.milliseconds

        c = Coordinate(1.5, TimeUnit.seconds)
        assert m(c) == 1500.0

        # Wrong unit
        c_wrong = Coordinate(1.5, TimeUnit.ticks)
        with pytest.raises(ValueError, match="does not match"):
            m(c_wrong)


class TestShiftMap:
    def test_basic(self):
        m = ShiftMap(offset=100)
        assert m.offset == 100
        assert m(50) == 150

        inv = m.inverse()
        assert inv.offset == -100
        assert inv(150) == 50

    def test_identity(self):
        m = ShiftMap(offset=0)
        assert m.is_identity


# region Public convert_array() API Tests


class TestConvertArrayPublicAPI:
    """Tests for the public convert_array() method on all linear map types.

    These tests verify the integration pattern used by the timestamp system.
    """

    def test_linear_map_convert_array_returns_ndarray(self):
        """convert_array() returns numpy array."""
        m = LinearMap(scalar=2.0, offset=1.0)
        values = np.array([0.0, 1.0, 2.0, 3.0])

        result = m.convert_array(values)

        assert isinstance(result, np.ndarray)
        assert result.shape == values.shape

    def test_linear_map_convert_array_values(self):
        """convert_array() computes correct values."""
        m = LinearMap(scalar=2.0, offset=1.0)
        values = np.array([0.0, 1.0, 2.0, 3.0])

        result = m.convert_array(values)

        np.testing.assert_array_equal(result, [1.0, 3.0, 5.0, 7.0])

    def test_scalar_map_convert_array(self):
        """ScalarMap.convert_array() works correctly."""
        m = ScalarMap(scalar=10.0)
        values = np.array([1.0, 2.0, 3.0])

        result = m.convert_array(values)

        assert isinstance(result, np.ndarray)
        np.testing.assert_array_equal(result, [10.0, 20.0, 30.0])

    def test_shift_map_convert_array(self):
        """ShiftMap.convert_array() works correctly."""
        m = ShiftMap(offset=5.0)
        values = np.array([0.0, 10.0, 20.0])

        result = m.convert_array(values)

        assert isinstance(result, np.ndarray)
        np.testing.assert_array_equal(result, [5.0, 15.0, 25.0])

    def test_convert_array_empty_input(self):
        """convert_array() handles empty arrays."""
        m = LinearMap(scalar=2.0, offset=1.0)
        values = np.array([])

        result = m.convert_array(values)

        assert isinstance(result, np.ndarray)
        assert len(result) == 0

    def test_convert_array_single_element(self):
        """convert_array() handles single-element arrays."""
        m = LinearMap(scalar=2.0, offset=1.0)
        values = np.array([5.0])

        result = m.convert_array(values)

        assert len(result) == 1
        assert result[0] == 11.0

    def test_convert_array_large_array(self):
        """convert_array() handles large arrays efficiently."""
        m = LinearMap(scalar=2.0, offset=1.0)
        values = np.arange(100000, dtype=np.float64)

        result = m.convert_array(values)

        assert len(result) == 100000
        # Spot check some values
        assert result[0] == 1.0
        assert result[50000] == 100001.0

    def test_convert_array_matches_scalar_conversion(self):
        """convert_array() results match element-wise scalar conversion."""
        m = LinearMap(scalar=1.5, offset=-3.0)
        values = np.array([0.0, 1.0, -1.0, 100.0, -100.0])

        array_result = m.convert_array(values)
        scalar_results = np.array([m(v) for v in values])

        # Exact same linear arithmetic (f(x) = 1.5x - 3.0), no floating-point
        # divergence between array and scalar paths
        np.testing.assert_array_equal(array_result, scalar_results)


# endregion
