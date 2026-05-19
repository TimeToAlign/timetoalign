"""Tests for core/types.py."""

from fractions import Fraction

import pytest

from timetoalign.core.enums import Domain, NumberType, TimeUnit
from timetoalign.core.types import Coordinate


class TestCoordinateCreation:
    """Tests for Coordinate instantiation."""

    def test_coordinate_creation_int(self) -> None:
        """Can create coordinate with integer value."""
        c = Coordinate(120, TimeUnit.ticks)
        assert c.value == 120
        assert c.unit == TimeUnit.ticks

    def test_coordinate_creation_float(self) -> None:
        """Can create coordinate with float value."""
        c = Coordinate(1.5, TimeUnit.seconds)
        assert c.value == 1.5
        assert c.unit == TimeUnit.seconds

    def test_coordinate_creation_fraction(self) -> None:
        """Can create coordinate with Fraction value."""
        c = Coordinate(Fraction(3, 4), TimeUnit.quarters)
        assert c.value == Fraction(3, 4)
        assert c.unit == TimeUnit.quarters

    def test_coordinate_creation_string_unit(self) -> None:
        """Can create coordinate with string unit (coerces to enum)."""
        c = Coordinate(1, "seconds")  # type: ignore[arg-type]
        assert c.unit == TimeUnit.seconds

    def test_coordinate_creation_enum_unit(self) -> None:
        """Can create coordinate with TimeUnit enum (no coercion needed)."""
        c = Coordinate(1, TimeUnit.seconds)
        assert c.unit == TimeUnit.seconds
        assert isinstance(c.unit, TimeUnit)

    def test_coordinate_invalid_value_type(self) -> None:
        """Invalid value types raise TypeError."""
        with pytest.raises(TypeError, match="must be int, float, or Fraction"):
            Coordinate("bad", TimeUnit.seconds)  # type: ignore[arg-type]

    def test_coordinate_invalid_value_none(self) -> None:
        """None value raises TypeError."""
        with pytest.raises(TypeError, match="must be int, float, or Fraction"):
            Coordinate(None, TimeUnit.seconds)  # type: ignore[arg-type]

    def test_coordinate_is_frozen(self) -> None:
        """Coordinate is immutable."""
        c = Coordinate(120, TimeUnit.ticks)
        # Pydantic v2 BaseModel with ``frozen=True`` raises ValidationError
        # on attribute assignment (not the dataclass AttributeError).
        with pytest.raises(Exception) as exc_info:
            c.value = 240  # type: ignore[misc]
        assert "frozen" in str(exc_info.value).lower() or isinstance(
            exc_info.value, (AttributeError, ValueError)
        )

    def test_coordinate_is_hashable(self) -> None:
        """Coordinate can be used in sets and as dict keys."""
        c1 = Coordinate(120, TimeUnit.ticks)
        c2 = Coordinate(120, TimeUnit.ticks)
        c3 = Coordinate(240, TimeUnit.ticks)

        assert hash(c1) == hash(c2)
        assert c1 in {c2}
        assert len({c1, c2, c3}) == 2


class TestCoordinateConversions:
    """Tests for Coordinate type conversion methods."""

    def test_to_float_from_int(self) -> None:
        """to_float() works with int value."""
        c = Coordinate(120, TimeUnit.ticks)
        assert c.to_float() == 120.0
        assert isinstance(c.to_float(), float)

    def test_to_float_from_float(self) -> None:
        """to_float() works with float value."""
        c = Coordinate(1.5, TimeUnit.seconds)
        assert c.to_float() == 1.5

    def test_to_float_from_fraction(self) -> None:
        """to_float() works with Fraction value."""
        c = Coordinate(Fraction(3, 4), TimeUnit.quarters)
        assert c.to_float() == 0.75

    def test_to_int_from_int(self) -> None:
        """to_int() works with int value."""
        c = Coordinate(120, TimeUnit.ticks)
        assert c.to_int() == 120

    def test_to_int_from_float(self) -> None:
        """to_int() truncates float value."""
        c = Coordinate(1.9, TimeUnit.seconds)
        assert c.to_int() == 1

    def test_to_int_from_fraction(self) -> None:
        """to_int() truncates Fraction value."""
        c = Coordinate(Fraction(7, 4), TimeUnit.quarters)
        assert c.to_int() == 1

    def test_to_fraction_from_int(self) -> None:
        """to_fraction() works with int value."""
        c = Coordinate(120, TimeUnit.ticks)
        assert c.to_fraction() == Fraction(120, 1)

    def test_to_fraction_from_fraction(self) -> None:
        """to_fraction() returns existing Fraction."""
        frac = Fraction(3, 4)
        c = Coordinate(frac, TimeUnit.quarters)
        assert c.to_fraction() == frac
        assert c.to_fraction() is frac

    def test_to_fraction_from_float(self) -> None:
        """to_fraction() approximates float value."""
        c = Coordinate(0.75, TimeUnit.seconds)
        assert c.to_fraction() == Fraction(3, 4)


class TestCoordinateProperties:
    """Tests for Coordinate properties."""

    def test_number_type_int(self) -> None:
        """number_type is INT for integer values."""
        c = Coordinate(120, TimeUnit.ticks)
        assert c.number_type == NumberType.int

    def test_number_type_float(self) -> None:
        """number_type is FLOAT for float values."""
        c = Coordinate(1.5, TimeUnit.seconds)
        assert c.number_type == NumberType.float

    def test_number_type_fraction(self) -> None:
        """number_type is FRACTION for Fraction values."""
        c = Coordinate(Fraction(3, 4), TimeUnit.quarters)
        assert c.number_type == NumberType.fraction

    def test_number_type_bool_raises(self) -> None:
        """Boolean values are rejected at Coordinate construction.

        Post-WP2 pilot migration to pydantic v2 BaseModel: the validator
        rejects bool eagerly at construction (a stricter and earlier
        rejection than the pre-migration ``number_type``-only check).
        """
        with pytest.raises(Exception, match="Boolean values"):
            Coordinate(True, TimeUnit.ticks)  # type: ignore[arg-type]

    def test_domain_physical(self) -> None:
        """domain property returns PHYSICAL for physical units."""
        c = Coordinate(1.5, TimeUnit.seconds)
        assert c.domain == Domain.physical

    def test_domain_logical(self) -> None:
        """domain property returns logical for logical units."""
        c = Coordinate(120, TimeUnit.ticks)
        assert c.domain == Domain.logical

    def test_domain_graphical(self) -> None:
        """domain property returns GRAPHICAL for graphical units."""
        c = Coordinate(100, TimeUnit.pixels)
        assert c.domain == Domain.graphical


class TestCoordinateArithmetic:
    """Tests for Coordinate arithmetic operations."""

    def test_add_same_unit(self) -> None:
        """Addition works with same unit."""
        c1 = Coordinate(100, TimeUnit.ticks)
        c2 = Coordinate(50, TimeUnit.ticks)
        result = c1 + c2
        assert result.value == 150
        assert result.unit == TimeUnit.ticks

    def test_add_different_units_raises(self) -> None:
        """Addition with different units raises TypeError."""
        c1 = Coordinate(100, TimeUnit.ticks)
        c2 = Coordinate(1.5, TimeUnit.seconds)
        with pytest.raises(TypeError, match="different units"):
            c1 + c2

    def test_add_non_coordinate_raises(self) -> None:
        """Addition with non-Coordinate raises TypeError."""
        c = Coordinate(100, TimeUnit.ticks)
        with pytest.raises(TypeError, match="Cannot add"):
            c + 50  # type: ignore[operator]

    def test_sub_same_unit(self) -> None:
        """Subtraction works with same unit."""
        c1 = Coordinate(100, TimeUnit.ticks)
        c2 = Coordinate(30, TimeUnit.ticks)
        result = c1 - c2
        assert result.value == 70
        assert result.unit == TimeUnit.ticks

    def test_sub_different_units_raises(self) -> None:
        """Subtraction with different units raises TypeError."""
        c1 = Coordinate(100, TimeUnit.ticks)
        c2 = Coordinate(1.5, TimeUnit.seconds)
        with pytest.raises(TypeError, match="different units"):
            c1 - c2

    def test_sub_non_coordinate_raises(self) -> None:
        """Subtraction with non-Coordinate raises TypeError."""
        c = Coordinate(100, TimeUnit.ticks)
        with pytest.raises(TypeError, match="Cannot subtract"):
            c - 50  # type: ignore[operator]

    def test_mul_scalar_int(self) -> None:
        """Multiplication with int scalar."""
        c = Coordinate(100, TimeUnit.ticks)
        result = c * 2
        assert result.value == 200
        assert result.unit == TimeUnit.ticks

    def test_mul_scalar_float(self) -> None:
        """Multiplication with float scalar."""
        c = Coordinate(100, TimeUnit.ticks)
        result = c * 0.5
        assert result.value == 50.0

    def test_mul_scalar_fraction(self) -> None:
        """Multiplication with Fraction scalar."""
        c = Coordinate(100, TimeUnit.ticks)
        result = c * Fraction(1, 2)
        assert result.value == 50

    def test_rmul_scalar(self) -> None:
        """Right multiplication works (scalar * coordinate)."""
        c = Coordinate(100, TimeUnit.ticks)
        result = 2 * c
        assert result.value == 200

    def test_mul_invalid_type_raises(self) -> None:
        """Multiplication with invalid type raises TypeError."""
        c = Coordinate(100, TimeUnit.ticks)
        with pytest.raises(TypeError, match="Cannot multiply"):
            c * "bad"  # type: ignore[operator]

    def test_truediv_scalar(self) -> None:
        """True division with scalar."""
        c = Coordinate(100, TimeUnit.ticks)
        result = c / 4
        assert result.value == 25.0

    def test_truediv_zero_raises(self) -> None:
        """Division by zero raises ZeroDivisionError."""
        c = Coordinate(100, TimeUnit.ticks)
        with pytest.raises(ZeroDivisionError):
            c / 0

    def test_truediv_invalid_type_raises(self) -> None:
        """Division with invalid type raises TypeError."""
        c = Coordinate(100, TimeUnit.ticks)
        with pytest.raises(TypeError, match="Cannot divide"):
            c / "bad"  # type: ignore[operator]

    def test_floordiv_scalar(self) -> None:
        """Floor division with scalar."""
        c = Coordinate(100, TimeUnit.ticks)
        result = c // 3
        assert result.value == 33

    def test_floordiv_zero_raises(self) -> None:
        """Floor division by zero raises ZeroDivisionError."""
        c = Coordinate(100, TimeUnit.ticks)
        with pytest.raises(ZeroDivisionError):
            c // 0

    def test_floordiv_invalid_type_raises(self) -> None:
        """Floor division with invalid type raises TypeError."""
        c = Coordinate(100, TimeUnit.ticks)
        with pytest.raises(TypeError, match="Cannot floor-divide"):
            c // "bad"  # type: ignore[operator]


class TestCoordinateComparison:
    """Tests for Coordinate comparison operations."""

    def test_lt(self) -> None:
        """Less than comparison."""
        c1 = Coordinate(100, TimeUnit.ticks)
        c2 = Coordinate(200, TimeUnit.ticks)
        assert c1 < c2
        assert not c2 < c1
        assert not c1 < c1

    def test_le(self) -> None:
        """Less than or equal comparison."""
        c1 = Coordinate(100, TimeUnit.ticks)
        c2 = Coordinate(200, TimeUnit.ticks)
        c3 = Coordinate(100, TimeUnit.ticks)
        assert c1 <= c2
        assert c1 <= c3
        assert not c2 <= c1

    def test_gt(self) -> None:
        """Greater than comparison."""
        c1 = Coordinate(100, TimeUnit.ticks)
        c2 = Coordinate(200, TimeUnit.ticks)
        assert c2 > c1
        assert not c1 > c2
        assert not c1 > c1

    def test_ge(self) -> None:
        """Greater than or equal comparison."""
        c1 = Coordinate(100, TimeUnit.ticks)
        c2 = Coordinate(200, TimeUnit.ticks)
        c3 = Coordinate(100, TimeUnit.ticks)
        assert c2 >= c1
        assert c1 >= c3
        assert not c1 >= c2

    def test_comparison_different_units_raises(self) -> None:
        """Comparison with different units raises TypeError."""
        c1 = Coordinate(100, TimeUnit.ticks)
        c2 = Coordinate(1.5, TimeUnit.seconds)
        with pytest.raises(TypeError, match="different units"):
            c1 < c2

    def test_comparison_non_coordinate_raises(self) -> None:
        """Comparison with non-Coordinate raises TypeError."""
        c = Coordinate(100, TimeUnit.ticks)
        with pytest.raises(TypeError, match="Cannot compare"):
            c < 100  # type: ignore[operator]


class TestCoordinateUtilities:
    """Tests for Coordinate utility methods."""

    def test_repr(self) -> None:
        """__repr__ returns valid representation."""
        c = Coordinate(120, TimeUnit.ticks)
        assert "Coordinate" in repr(c)
        assert "120" in repr(c)
        assert "ticks" in repr(c)

    def test_str(self) -> None:
        """__str__ returns human-readable string."""
        c = Coordinate(120, TimeUnit.ticks)
        assert str(c) == "120 ticks"

    def test_str_float(self) -> None:
        """__str__ works with float."""
        c = Coordinate(1.5, TimeUnit.seconds)
        assert str(c) == "1.5 seconds"

    def test_is_zero_true(self) -> None:
        """is_zero() returns True for zero coordinate."""
        c = Coordinate(0, TimeUnit.ticks)
        assert c.is_zero() is True

    def test_is_zero_false(self) -> None:
        """is_zero() returns False for non-zero coordinate."""
        c = Coordinate(1, TimeUnit.ticks)
        assert c.is_zero() is False

    def test_is_zero_float(self) -> None:
        """is_zero() works with float zero."""
        c = Coordinate(0.0, TimeUnit.seconds)
        assert c.is_zero() is True

    def test_is_positive_true(self) -> None:
        """is_positive() returns True for positive coordinate."""
        c = Coordinate(1, TimeUnit.ticks)
        assert c.is_positive() is True

    def test_is_positive_false(self) -> None:
        """is_positive() returns False for zero or negative."""
        assert Coordinate(0, TimeUnit.ticks).is_positive() is False
        assert Coordinate(-1, TimeUnit.ticks).is_positive() is False

    def test_is_negative_true(self) -> None:
        """is_negative() returns True for negative coordinate."""
        c = Coordinate(-1, TimeUnit.ticks)
        assert c.is_negative() is True

    def test_is_negative_false(self) -> None:
        """is_negative() returns False for zero or positive."""
        assert Coordinate(0, TimeUnit.ticks).is_negative() is False
        assert Coordinate(1, TimeUnit.ticks).is_negative() is False

    def test_with_value(self) -> None:
        """with_value() returns new Coordinate with different value."""
        c1 = Coordinate(100, TimeUnit.ticks)
        c2 = c1.with_value(200)
        assert c2.value == 200
        assert c2.unit == TimeUnit.ticks
        assert c1.value == 100  # Original unchanged

    def test_with_unit(self) -> None:
        """with_unit() returns new Coordinate with different unit."""
        c1 = Coordinate(100, TimeUnit.ticks)
        c2 = c1.with_unit(TimeUnit.pulses)
        assert c2.value == 100
        assert c2.unit == TimeUnit.pulses
        assert c1.unit == TimeUnit.ticks  # Original unchanged


class TestCoordinateNumericProtocols:
    """Tests for Coordinate numeric protocol methods (__float__, __int__, __index__)."""

    # --- __float__ tests ---

    def test_float_from_int(self) -> None:
        """__float__ converts int value to float."""
        c = Coordinate(15343, TimeUnit.pixels)
        result = float(c)
        assert result == 15343.0
        assert isinstance(result, float)

    def test_float_from_float(self) -> None:
        """__float__ returns float value unchanged."""
        c = Coordinate(3.14159, TimeUnit.seconds)
        result = float(c)
        assert result == 3.14159
        assert isinstance(result, float)

    def test_float_from_fraction(self) -> None:
        """__float__ converts Fraction value to float."""
        c = Coordinate(Fraction(3, 4), TimeUnit.quarters)
        result = float(c)
        assert result == 0.75
        assert isinstance(result, float)

    def test_float_enables_math_functions(self) -> None:
        """__float__ allows Coordinate to be used with math module."""
        import math

        c = Coordinate(16, TimeUnit.pixels)
        # math.sqrt uses __float__ implicitly
        assert math.sqrt(c) == 4.0

    # --- __int__ tests ---

    def test_int_from_int(self) -> None:
        """__int__ returns int value unchanged."""
        c = Coordinate(15343, TimeUnit.pixels)
        result = int(c)
        assert result == 15343
        assert isinstance(result, int)

    def test_int_from_float_truncates(self) -> None:
        """__int__ truncates float value towards zero."""
        c = Coordinate(3.9, TimeUnit.seconds)
        assert int(c) == 3

        c_neg = Coordinate(-3.9, TimeUnit.seconds)
        assert int(c_neg) == -3

    def test_int_from_fraction(self) -> None:
        """__int__ truncates Fraction value."""
        c = Coordinate(Fraction(7, 4), TimeUnit.quarters)
        assert int(c) == 1

    # --- __index__ tests ---

    def test_index_from_int(self) -> None:
        """__index__ returns int value for use as index."""
        c = Coordinate(5, TimeUnit.pixels)
        # Test as string index
        assert "hello world"[c] == " "  # 5th character

    def test_index_enables_slice_notation(self) -> None:
        """__index__ allows Coordinate in slice notation."""
        c = Coordinate(3, TimeUnit.pixels)
        assert [0, 1, 2, 3, 4, 5][c] == 3

    def test_index_from_float_raises(self) -> None:
        """__index__ raises TypeError for float values."""
        c = Coordinate(3.5, TimeUnit.seconds)
        with pytest.raises(TypeError, match="Only integer Coordinates"):
            "hello"[c]

    def test_index_from_fraction_raises(self) -> None:
        """__index__ raises TypeError for Fraction values."""
        c = Coordinate(Fraction(3, 4), TimeUnit.quarters)
        with pytest.raises(TypeError, match="Only integer Coordinates"):
            [1, 2, 3][c]

    # --- Integration tests ---

    def test_float_in_tuple_construction(self) -> None:
        """float(coord) can be used in tuple construction."""
        c = Coordinate(15343, TimeUnit.pixels)
        result = (float(c), "dgt1")
        assert result == (15343.0, "dgt1")

    def test_float_in_arithmetic_with_numbers(self) -> None:
        """float(coord) enables arithmetic with plain numbers."""
        c = Coordinate(100, TimeUnit.pixels)
        # This would fail without float() conversion
        result = 10.0 + float(c)
        assert result == 110.0
