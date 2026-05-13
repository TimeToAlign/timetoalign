"""Core type definitions for the TTA model.

This module defines the Coordinate dataclass and IdCoordinate, the fundamental
building blocks for representing positions on timelines.

Coordinate Specification Hierarchy:
- Least specific: Just a number (int, float, Fraction) - function may guess unit/timeline
- More specific: A Coordinate (has value + unit) - function may guess timeline
- Most specific: An IdCoordinate (has value + unit + timeline_id) - fully specified
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Union

from .enums import Domain, NumberType, TimeUnit

# Type alias for coordinate values
CoordinateValue = Union[int, float, Fraction]

# Discrete units MUST be displayed as integers, never as floats or scientific notation.
# These are units where fractional values are semantically meaningless.
DISCRETE_UNITS = frozenset(
    {"ticks", "pulses", "divs", "samples", "pixels", "px", "frames"}
)

# Type alias for optional coordinates (common pattern)
OptionalCoordinate = Union["Coordinate", None]

# Type aliases for flexible coordinate specification (layered API)
# NOTE: These are defined after IdCoordinate class below, but documented here for clarity.
# - int/float/Fraction: Just a number, function guesses unit and timeline
# - Coordinate: Has value and unit, function guesses timeline
# - IdCoordinate: Fully specified with timeline_id

# NOTE: CoordinateSpec and CoordinateWithTimeline type aliases are defined at end of file
# after IdCoordinate class to avoid forward reference issues.


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

    def to_int(self, rounding: str = "truncate") -> int:
        """Convert value to int.

        Args:
            rounding: Rounding mode. Options:
                - "truncate": Truncate towards zero (default, same as int())
                - "round": Round to nearest integer (half away from zero)
                - "floor": Round towards negative infinity
                - "ceil": Round towards positive infinity

        Returns:
            The integer value.

        Raises:
            ValueError: If rounding mode is unknown.
        """
        if rounding == "truncate":
            return int(self.value)
        elif rounding == "round":
            return round(self.value)
        elif rounding == "floor":
            import math

            return math.floor(self.value)
        elif rounding == "ceil":
            import math

            return math.ceil(self.value)
        else:
            raise ValueError(
                f"Unknown rounding mode: {rounding!r}. "
                f"Use 'truncate', 'round', 'floor', or 'ceil'."
            )

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

    def __float__(self) -> float:
        """Enable implicit float conversion via float(coord).

        This allows Coordinates to be used directly in contexts expecting
        float, such as math operations, plotting functions, and C APIs.

        Examples:
            >>> coord = Coordinate(15343, TimeUnit.pixels)
            >>> float(coord)
            15343.0
            >>> import math
            >>> math.sqrt(coord)  # Works because of __float__
            123.86...
        """
        return float(self.value)

    def __int__(self) -> int:
        """Enable implicit int conversion via int(coord).

        Uses truncation towards zero (same as int() on the value).

        Examples:
            >>> coord = Coordinate(15.7, TimeUnit.seconds)
            >>> int(coord)
            15
        """
        return int(self.value)

    def __index__(self) -> int:
        """Enable use as sequence index (requires integer value).

        Only works when value is an integer type. This allows Coordinates
        to be used in slice notation and as array indices.

        Examples:
            >>> coord = Coordinate(5, TimeUnit.pixels)
            >>> "hello world"[coord]  # Works because of __index__
            ' '

        Raises:
            TypeError: If value is not an integer.
        """
        if isinstance(self.value, int) and not isinstance(self.value, bool):
            return self.value
        raise TypeError(
            f"Cannot use Coordinate with {type(self.value).__name__} value as index. "
            f"Only integer Coordinates can be used as indices."
        )

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
            raise TypeError(
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
        """Format coordinate without scientific notation.

        Discrete units (ticks, samples, pixels, frames) are shown as integers.
        Continuous units use fixed-point notation.
        """
        unit_name = self.unit.value if hasattr(self.unit, "value") else str(self.unit)
        unit_lower = unit_name.lower()
        v = self.value

        # For discrete units OR exact integers, format as plain integer
        if unit_lower in DISCRETE_UNITS or (v == int(v) and abs(v) < 1e15):
            return f"{int(v)} {self.unit}"

        # For continuous units, use fixed-point notation (never scientific)
        if abs(v) >= 1e6:
            return f"{int(round(v))} {self.unit}"
        elif abs(v) >= 1:
            return f"{v:.6f}".rstrip("0").rstrip(".") + f" {self.unit}"
        elif v == 0:
            return f"0 {self.unit}"
        else:
            return f"{v:.6f}".rstrip("0").rstrip(".") + f" {self.unit}"

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

    def with_timeline(self, timeline_id: str) -> "IdCoordinate":
        """Return an IdCoordinate with the same value and unit, plus a timeline ID.

        Args:
            timeline_id: The ID of the timeline this coordinate belongs to.

        Returns:
            An IdCoordinate that carries the timeline reference.
        """
        return IdCoordinate(self.value, self.unit, timeline_id)


@dataclass(frozen=True)
class IdCoordinate(Coordinate):
    """A Coordinate that carries the ID of the timeline it belongs to.

    IdCoordinate extends Coordinate with a timeline_id field, providing
    the most specific form of coordinate specification. This enables
    unambiguous coordinate operations across multiple timelines.

    The layered coordinate specification API:
    - Least specific: Just a number (int, float, Fraction)
    - More specific: A Coordinate (value + unit)
    - Most specific: An IdCoordinate (value + unit + timeline_id)

    Attributes:
        value: The numeric position (int, float, or Fraction)
        unit: The time unit (e.g., seconds, quarters, pixels)
        timeline_id: The unique identifier of the timeline this coordinate belongs to

    Examples:
        >>> c = IdCoordinate(120, TimeUnit.ticks, "midi:1")
        >>> c.timeline_id
        'midi:1'

        >>> # Create from existing Coordinate
        >>> coord = Coordinate(1.5, TimeUnit.seconds)
        >>> id_coord = coord.with_timeline("audio:1")
        >>> id_coord.timeline_id
        'audio:1'

        >>> # Downcast to Coordinate (drops timeline_id)
        >>> base_coord = id_coord.to_coordinate()
        >>> isinstance(base_coord, IdCoordinate)
        False
    """

    timeline_id: str

    def __post_init__(self) -> None:
        # Call parent validation
        super().__post_init__()
        # Validate timeline_id
        if not isinstance(self.timeline_id, str):
            raise TypeError(
                f"timeline_id must be a string, got {type(self.timeline_id).__name__}"
            )
        if not self.timeline_id:
            raise ValueError("timeline_id cannot be empty")

    # --- Factory methods ---

    @classmethod
    def from_coordinate(cls, coord: Coordinate, timeline_id: str) -> "IdCoordinate":
        """Create an IdCoordinate from a Coordinate and timeline ID.

        Args:
            coord: The base Coordinate.
            timeline_id: The timeline ID to attach.

        Returns:
            A new IdCoordinate.
        """
        return cls(coord.value, coord.unit, timeline_id)

    def to_coordinate(self) -> Coordinate:
        """Return a base Coordinate without the timeline_id.

        Useful when you need to pass the coordinate to functions that
        don't support IdCoordinate.

        Returns:
            A Coordinate with the same value and unit.
        """
        return Coordinate(self.value, self.unit)

    # --- Override arithmetic to return IdCoordinate ---

    def __add__(self, other: object) -> "IdCoordinate":
        result = super().__add__(other)
        return IdCoordinate(result.value, result.unit, self.timeline_id)

    def __sub__(self, other: object) -> "IdCoordinate":
        result = super().__sub__(other)
        return IdCoordinate(result.value, result.unit, self.timeline_id)

    def __mul__(self, scalar: object) -> "IdCoordinate":
        result = super().__mul__(scalar)
        return IdCoordinate(result.value, result.unit, self.timeline_id)

    def __rmul__(self, scalar: object) -> "IdCoordinate":
        return self.__mul__(scalar)

    def __truediv__(self, scalar: object) -> "IdCoordinate":
        result = super().__truediv__(scalar)
        return IdCoordinate(result.value, result.unit, self.timeline_id)

    def __floordiv__(self, scalar: object) -> "IdCoordinate":
        result = super().__floordiv__(scalar)
        return IdCoordinate(result.value, result.unit, self.timeline_id)

    # --- Override factory methods ---

    def with_value(self, new_value: CoordinateValue) -> "IdCoordinate":
        """Return a new IdCoordinate with a different value but same unit and timeline."""
        return IdCoordinate(new_value, self.unit, self.timeline_id)

    def with_unit(self, new_unit: TimeUnit) -> "IdCoordinate":
        """Return a new IdCoordinate with a different unit but same value and timeline.

        Warning: This does NOT convert the value - use a ConversionMap for that.
        """
        return IdCoordinate(self.value, new_unit, self.timeline_id)

    def with_timeline(self, timeline_id: str) -> "IdCoordinate":
        """Return a new IdCoordinate with a different timeline_id."""
        return IdCoordinate(self.value, self.unit, timeline_id)

    # --- String representations ---

    def __repr__(self) -> str:
        return f"IdCoordinate({self.value!r}, {self.unit}, {self.timeline_id!r})"

    def __str__(self) -> str:
        """Format coordinate without scientific notation.

        Discrete units (ticks, samples, pixels, frames) are shown as integers.
        Continuous units use fixed-point notation.
        """
        unit_name = self.unit.value if hasattr(self.unit, "value") else str(self.unit)
        unit_lower = unit_name.lower()
        v = self.value

        # For discrete units OR exact integers, format as plain integer
        if unit_lower in DISCRETE_UNITS or (v == int(v) and abs(v) < 1e15):
            return f"{int(v)} {self.unit} @{self.timeline_id}"

        # For continuous units, use fixed-point notation (never scientific)
        if abs(v) >= 1e6:
            return f"{int(round(v))} {self.unit} @{self.timeline_id}"
        elif abs(v) >= 1:
            formatted = f"{v:.6f}".rstrip("0").rstrip(".")
            return f"{formatted} {self.unit} @{self.timeline_id}"
        elif v == 0:
            return f"0 {self.unit} @{self.timeline_id}"
        else:
            formatted = f"{v:.6f}".rstrip("0").rstrip(".")
            return f"{formatted} {self.unit} @{self.timeline_id}"


# Type aliases for flexible coordinate specification (layered API)
# Defined after classes to avoid forward reference issues.

# CoordinateSpec: Any form of coordinate specification
# - int/float/Fraction: Just a number, function guesses unit and timeline
# - Coordinate: Has value and unit, function guesses timeline
# - IdCoordinate: Fully specified with timeline_id
CoordinateSpec = Union[int, float, Fraction, Coordinate, IdCoordinate]

# CoordinateWithTimeline: Coordinate specification with optional explicit timeline
# - (coord, timeline_id): Tuple form for explicit timeline reference
# - CoordinateSpec: Any of the coordinate types above
CoordinateWithTimeline = Union[tuple[CoordinateSpec, str], CoordinateSpec]
