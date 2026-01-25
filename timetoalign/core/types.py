"""Core type definitions for the TTA model.

This module defines the Coordinate dataclass, the fundamental
building block for representing positions on timelines.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Union

from .enums import Domain, NumberType, TimeUnit

# Type alias for coordinate values
CoordinateValue = Union[int, float, Fraction]

# Type alias for optional coordinates (common pattern)
OptionalCoordinate = Union["Coordinate", None]


@dataclass(frozen=True, slots=True)
class Coordinate:
    """A position on a timeline, defined by a value and unit.

    Coordinates are immutable and support arithmetic operations
    when units match. They preserve the native numeric type
    (int, float, or Fraction) for precision.

    Attributes:
        value: The numeric position (int, float, or Fraction)
        unit: The time unit (e.g., seconds, quarters, pixels)

    Examples:
        >>> c1 = Coordinate(120, TimeUnit.ticks)
        >>> c2 = Coordinate(240, TimeUnit.ticks)
        >>> c2 - c1
        Coordinate(120, ticks)

        >>> Coordinate(1.5, TimeUnit.seconds)
        Coordinate(1.5, seconds)

        >>> Coordinate(Fraction(3, 4), TimeUnit.quarters)
        Coordinate(Fraction(3, 4), quarters)
    """

    value: CoordinateValue
    unit: TimeUnit

    def __post_init__(self) -> None:
        # Validate value type
        if not isinstance(self.value, (int, float, Fraction)):
            raise TypeError(
                f"Coordinate value must be int, float, or Fraction, "
                f"got {type(self.value).__name__}"
            )
        # Coerce unit to enum if string
        if isinstance(self.unit, str):  # pragma: no branch
            object.__setattr__(self, "unit", TimeUnit(self.unit))

    # --- Type conversions ---

    def to_float(self) -> float:
        """Convert value to float."""
        return float(self.value)

    def to_int(self) -> int:
        """Convert value to int (truncates towards zero)."""
        return int(self.value)

    def to_fraction(self) -> Fraction:
        """Convert value to Fraction.

        Lossless for int/Fraction; approximates for float.
        """
        if isinstance(self.value, Fraction):
            return self.value
        if isinstance(self.value, int):
            return Fraction(self.value, 1)
        # Float: use limit_denominator for reasonable precision
        return Fraction(self.value).limit_denominator(10000)

    @property
    def number_type(self) -> NumberType:
        """Infer the NumberType from the value."""
        if isinstance(self.value, bool):
            # bool is subclass of int, but we don't want to treat it as int
            raise TypeError("Boolean values are not valid coordinate values")
        if isinstance(self.value, int):
            return NumberType.int
        if isinstance(self.value, float):
            return NumberType.float
        if isinstance(self.value, Fraction):
            return NumberType.fraction
        raise TypeError(
            f"Unknown number type for {type(self.value)}"
        )  # pragma: no cover

    @property
    def domain(self) -> Domain:
        """Return the domain this coordinate belongs to (via its unit)."""
        return self.unit.domain

    # --- Arithmetic operations ---

    def _check_compatible(self, other: object, operation: str) -> Coordinate:
        """Raise ValueError if units don't match. Returns typed other."""
        if not isinstance(other, Coordinate):
            raise TypeError(
                f"Cannot {operation} Coordinate with {type(other).__name__}"
            )
        if self.unit != other.unit:
            raise ValueError(
                f"Cannot {operation} coordinates with different units: "
                f"{self.unit} vs {other.unit}"
            )
        return other

    def __add__(self, other: object) -> Coordinate:
        other_coord = self._check_compatible(other, "add")
        return Coordinate(self.value + other_coord.value, self.unit)

    def __sub__(self, other: object) -> Coordinate:
        other_coord = self._check_compatible(other, "subtract")
        return Coordinate(self.value - other_coord.value, self.unit)

    def __mul__(self, scalar: object) -> Coordinate:
        if not isinstance(scalar, (int, float, Fraction)):
            raise TypeError(f"Cannot multiply Coordinate by {type(scalar).__name__}")
        return Coordinate(self.value * scalar, self.unit)

    def __rmul__(self, scalar: object) -> Coordinate:
        return self.__mul__(scalar)

    def __truediv__(self, scalar: object) -> Coordinate:
        if not isinstance(scalar, (int, float, Fraction)):
            raise TypeError(f"Cannot divide Coordinate by {type(scalar).__name__}")
        if scalar == 0:
            raise ZeroDivisionError("Cannot divide Coordinate by zero")
        return Coordinate(self.value / scalar, self.unit)

    def __floordiv__(self, scalar: object) -> Coordinate:
        if not isinstance(scalar, (int, float, Fraction)):
            raise TypeError(
                f"Cannot floor-divide Coordinate by {type(scalar).__name__}"
            )
        if scalar == 0:
            raise ZeroDivisionError("Cannot divide Coordinate by zero")
        return Coordinate(self.value // scalar, self.unit)

    # --- Comparison operations ---

    def __lt__(self, other: object) -> bool:
        other_coord = self._check_compatible(other, "compare")
        return self.value < other_coord.value

    def __le__(self, other: object) -> bool:
        other_coord = self._check_compatible(other, "compare")
        return self.value <= other_coord.value

    def __gt__(self, other: object) -> bool:
        other_coord = self._check_compatible(other, "compare")
        return self.value > other_coord.value

    def __ge__(self, other: object) -> bool:
        other_coord = self._check_compatible(other, "compare")
        return self.value >= other_coord.value

    # --- Utilities ---

    def __repr__(self) -> str:
        return f"Coordinate({self.value!r}, {self.unit})"

    def __str__(self) -> str:
        return f"{self.value} {self.unit}"

    def is_zero(self) -> bool:
        """Check if this coordinate represents the origin."""
        return self.value == 0

    def is_positive(self) -> bool:
        """Check if this coordinate is positive (after origin)."""
        return self.value > 0

    def is_negative(self) -> bool:
        """Check if this coordinate is negative (before origin)."""
        return self.value < 0

    def with_value(self, new_value: CoordinateValue) -> Coordinate:
        """Return a new Coordinate with a different value but same unit."""
        return Coordinate(new_value, self.unit)

    def with_unit(self, new_unit: TimeUnit) -> Coordinate:
        """Return a new Coordinate with a different unit but same value.

        Warning: This does NOT convert the value - use a ConversionMap for that.
        This is for reinterpretation only (e.g., aliasing units).
        """
        return Coordinate(self.value, new_unit)
