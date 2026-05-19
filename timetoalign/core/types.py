"""Core type definitions for the TTA model.

This module defines the ``Coordinate`` scalar (pydantic v2 ``BaseModel``)
and its subclass ``IdCoordinate``, the fundamental building blocks for
representing positions on timelines.

Coordinate Specification Hierarchy:
    - Least specific: just a number (int, float, Fraction) — function
      may guess unit/timeline.
    - More specific: a ``Coordinate`` (value + unit) — function may
      guess timeline.
    - Most specific: an ``IdCoordinate`` (value + unit + timeline_id) —
      fully specified.

WP2 pilot scalar: ``Coordinate`` is now a pydantic v2 ``BaseModel``.  Its
PyArrow storage shape ``{value, numerator, denominator}`` is produced via
the value-projector registry in
:mod:`timetoalign.core.schemas.from_pydantic`; the unit lives in
``pa.Field.metadata`` (not in the struct).
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any, Union

import pyarrow as pa
from pydantic import BaseModel, ConfigDict, field_validator

from .enums import Domain, NumberType, TimeUnit
from .schemas.from_pydantic import register_value_projector

# Type alias for coordinate values
CoordinateValue = Union[int, float, Fraction]

# Discrete units MUST be displayed as integers, never as floats or scientific notation.
# These are units where fractional values are semantically meaningless.
DISCRETE_UNITS = frozenset(
    {"ticks", "pulses", "divs", "samples", "pixels", "px", "frames"}
)

# Type alias for optional coordinates (common pattern)
OptionalCoordinate = Union["Coordinate", None]


# ---------------------------------------------------------------------------
# Coordinate (pydantic v2 BaseModel — WP2 pilot)
# ---------------------------------------------------------------------------


class Coordinate(BaseModel):
    """A position on a timeline, defined by a value and unit.

    Coordinates are immutable and support arithmetic operations
    when units match.  They preserve the native numeric type
    (int, float, or Fraction) for precision.

    Attributes:
        value: The numeric position (int, float, or Fraction).
        unit: The time unit (e.g., seconds, quarters, pixels).

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

    model_config = ConfigDict(
        frozen=True,
        # pydantic does NOT know about Fraction natively; arbitrary_types
        # is required so the field validator below can accept Fraction.
        arbitrary_types_allowed=True,
    )

    value: CoordinateValue
    unit: TimeUnit

    # --- Positional-argument compatibility ---------------------------------
    # Pydantic v2 ``BaseModel`` accepts kwargs only.  TTA's API is
    # ``Coordinate(value, unit)`` positionally, so we restore that here
    # without losing pydantic-native validation.

    def __init__(
        self,
        value: CoordinateValue | dict[str, Any] | None = None,
        unit: TimeUnit | str | None = None,
        /,
        **data: Any,
    ) -> None:
        if value is not None or unit is not None:
            if "value" in data or "unit" in data:
                raise TypeError(
                    "Coordinate received conflicting positional and keyword arguments"
                )
            data = {"value": value, "unit": unit, **data}
        super().__init__(**data)

    # --- Validators --------------------------------------------------------

    @field_validator("value", mode="before")
    @classmethod
    def _validate_value(cls, v: object) -> CoordinateValue:
        # bool is technically a subclass of int but must be rejected.
        if isinstance(v, bool):
            raise TypeError("Boolean values are not valid coordinate values")
        if isinstance(v, (int, float, Fraction)):
            return v
        raise TypeError(
            f"Coordinate value must be int, float, or Fraction, "
            f"got {type(v).__name__}"
        )

    @field_validator("unit", mode="before")
    @classmethod
    def _validate_unit(cls, v: object) -> TimeUnit:
        if isinstance(v, TimeUnit):
            return v
        if isinstance(v, str):
            return TimeUnit(v)
        raise TypeError(
            f"Coordinate unit must be a TimeUnit or string, got {type(v).__name__}"
        )

    # --- Type conversions --------------------------------------------------

    def to_float(self) -> float:
        """Convert value to float."""
        return float(self.value)

    def to_int(self, rounding: str = "truncate") -> int:
        """Convert value to int.

        Args:
            rounding: Rounding mode.  Options:
                - ``"truncate"``: Truncate towards zero (default, same as int())
                - ``"round"``: Round to nearest integer (half away from zero)
                - ``"floor"``: Round towards negative infinity
                - ``"ceil"``: Round towards positive infinity

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
        """Enable implicit float conversion via ``float(coord)``."""
        return float(self.value)

    def __int__(self) -> int:
        """Enable implicit int conversion via ``int(coord)``.

        Uses truncation towards zero (same as ``int()`` on the value).
        """
        return int(self.value)

    def __index__(self) -> int:
        """Enable use as sequence index (requires integer value)."""
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

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "Coordinate"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract."""
        return {
            "field_type": "CoordinateField",
            "unit": self.unit.value,
            "domain": self.domain.value,
            "number_type": self.number_type.name,
        }

    # --- Arithmetic operations --------------------------------------------

    def _check_compatible(self, other: object, operation: str) -> Coordinate:
        """Raise ValueError if units don't match.  Returns typed other."""
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

    # --- Comparison operations --------------------------------------------

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

    # --- Utilities ---------------------------------------------------------

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
        v_f = float(v)

        if unit_lower in DISCRETE_UNITS or (v == int(v_f) and abs(v_f) < 1e15):
            return f"{int(v_f)} {self.unit}"

        if abs(v_f) >= 1e6:
            return f"{int(round(v_f))} {self.unit}"
        elif abs(v_f) >= 1:
            return f"{v_f:.6f}".rstrip("0").rstrip(".") + f" {self.unit}"
        elif v_f == 0:
            return f"0 {self.unit}"
        else:
            return f"{v_f:.6f}".rstrip("0").rstrip(".") + f" {self.unit}"

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

        Warning: This does NOT convert the value — use a ConversionMap
        for that.  Reinterpretation only.
        """
        return Coordinate(self.value, new_unit)

    def with_timeline(self, timeline_id: str) -> IdCoordinate:
        """Return an ``IdCoordinate`` with the same value/unit + timeline_id."""
        return IdCoordinate(self.value, self.unit, timeline_id)


# ---------------------------------------------------------------------------
# IdCoordinate
# ---------------------------------------------------------------------------


class IdCoordinate(Coordinate):
    """A ``Coordinate`` that carries the ID of the timeline it belongs to.

    Extends ``Coordinate`` with a ``timeline_id`` field, providing the
    most specific form of coordinate specification.  This enables
    unambiguous coordinate operations across multiple timelines.

    Attributes:
        value: The numeric position (int, float, or Fraction).
        unit: The time unit (e.g., seconds, quarters, pixels).
        timeline_id: The unique identifier of the timeline this coordinate
            belongs to.

    Examples:
        >>> c = IdCoordinate(120, TimeUnit.ticks, "midi:1")
        >>> c.timeline_id
        'midi:1'

        >>> coord = Coordinate(1.5, TimeUnit.seconds)
        >>> id_coord = coord.with_timeline("audio:1")
        >>> id_coord.timeline_id
        'audio:1'
    """

    timeline_id: str

    def __init__(
        self,
        value: CoordinateValue | None = None,
        unit: TimeUnit | str | None = None,
        timeline_id: str | None = None,
        /,
        **data: Any,
    ) -> None:
        positional = {
            k: v
            for k, v in (
                ("value", value),
                ("unit", unit),
                ("timeline_id", timeline_id),
            )
            if v is not None
        }
        if positional and any(k in data for k in positional):
            raise TypeError(
                "IdCoordinate received conflicting positional and keyword arguments"
            )
        data = {**positional, **data}
        # Bypass Coordinate.__init__ (which only knows about value/unit) and
        # go straight to BaseModel; pydantic handles all three fields.
        BaseModel.__init__(self, **data)

    @field_validator("timeline_id", mode="before")
    @classmethod
    def _validate_timeline_id(cls, v: object) -> str:
        if not isinstance(v, str):
            raise TypeError(f"timeline_id must be a string, got {type(v).__name__}")
        if not v:
            raise ValueError("timeline_id cannot be empty")
        return v

    # --- Factory methods ---------------------------------------------------

    @classmethod
    def from_coordinate(cls, coord: Coordinate, timeline_id: str) -> IdCoordinate:
        """Create an ``IdCoordinate`` from a Coordinate + timeline ID."""
        return cls(coord.value, coord.unit, timeline_id)

    def to_coordinate(self) -> Coordinate:
        """Return a base ``Coordinate`` without the ``timeline_id``."""
        return Coordinate(self.value, self.unit)

    # --- Override arithmetic to return IdCoordinate -----------------------

    def __add__(self, other: object) -> IdCoordinate:
        result = super().__add__(other)
        return IdCoordinate(result.value, result.unit, self.timeline_id)

    def __sub__(self, other: object) -> IdCoordinate:
        result = super().__sub__(other)
        return IdCoordinate(result.value, result.unit, self.timeline_id)

    def __mul__(self, scalar: object) -> IdCoordinate:
        result = super().__mul__(scalar)
        return IdCoordinate(result.value, result.unit, self.timeline_id)

    def __rmul__(self, scalar: object) -> IdCoordinate:
        return self.__mul__(scalar)

    def __truediv__(self, scalar: object) -> IdCoordinate:
        result = super().__truediv__(scalar)
        return IdCoordinate(result.value, result.unit, self.timeline_id)

    def __floordiv__(self, scalar: object) -> IdCoordinate:
        result = super().__floordiv__(scalar)
        return IdCoordinate(result.value, result.unit, self.timeline_id)

    # --- Override factory methods -----------------------------------------

    def with_value(self, new_value: CoordinateValue) -> IdCoordinate:
        """Return a new ``IdCoordinate`` with a different value."""
        return IdCoordinate(new_value, self.unit, self.timeline_id)

    def with_unit(self, new_unit: TimeUnit) -> IdCoordinate:
        """Return a new ``IdCoordinate`` with a different unit.

        Warning: does NOT convert values — use a ConversionMap for that.
        """
        return IdCoordinate(self.value, new_unit, self.timeline_id)

    def with_timeline(self, timeline_id: str) -> IdCoordinate:
        """Return a new ``IdCoordinate`` with a different ``timeline_id``."""
        return IdCoordinate(self.value, self.unit, timeline_id)

    # --- String representations -------------------------------------------

    def __repr__(self) -> str:
        return f"IdCoordinate({self.value!r}, {self.unit}, {self.timeline_id!r})"

    def __str__(self) -> str:
        """Format coordinate without scientific notation."""
        unit_name = self.unit.value if hasattr(self.unit, "value") else str(self.unit)
        unit_lower = unit_name.lower()
        v = self.value

        if unit_lower in DISCRETE_UNITS or (v == int(v) and abs(v) < 1e15):
            return f"{int(v)} {self.unit} @{self.timeline_id}"

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


# ---------------------------------------------------------------------------
# Value projector for Coordinate.value
# ---------------------------------------------------------------------------
#
# The scalar's ``value`` field is typed ``int | float | Fraction``, but
# the Arrow storage shape denormalises into three fields so that rational
# precision survives a round-trip even when the loader has lost the
# original Fraction object.  Registering the projector here means the
# pa.Schema derived from ``Coordinate`` is the canonical TTA coordinate
# storage struct ``{value, numerator, denominator}``.
#
# WP2 plan §6 / §7: this is the column-builder pattern's target struct.


def _coordinate_value_projector(
    _model_cls: type[BaseModel], _name: str, _info: object
) -> list[pa.Field]:
    """Project ``Coordinate.value`` onto the denormalised storage struct.

    Matches the legacy ``make_coordinate_type`` shape:
    ``{value: float64?, numerator: int64?, denominator: int64?}`` — all
    nullable so that a null parent struct entry round-trips cleanly
    through Parquet (it forbids non-null children under a null parent).
    """
    return [
        pa.field("value", pa.float64(), nullable=True),
        pa.field("numerator", pa.int64(), nullable=True),
        pa.field("denominator", pa.int64(), nullable=True),
    ]


# Coordinate's ``unit`` is **not** part of the Arrow column — it lives in
# ``pa.Field.metadata`` (and on the scalar instance).  The projector for
# the ``unit`` field returns an empty list so it is omitted from the
# derived pa.Schema entirely.


def _coordinate_unit_projector(
    _model_cls: type[BaseModel], _name: str, _info: object
) -> list[pa.Field]:
    """Drop ``Coordinate.unit`` from the Arrow column — it lives in metadata."""
    return []


register_value_projector(Coordinate, "value", _coordinate_value_projector)
register_value_projector(Coordinate, "unit", _coordinate_unit_projector)


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

# CoordinateSpec: any form of coordinate specification.
# - int/float/Fraction: just a number, function guesses unit and timeline.
# - Coordinate: has value and unit, function guesses timeline.
# - IdCoordinate: fully specified with timeline_id.
CoordinateSpec = Union[int, float, Fraction, Coordinate, IdCoordinate]

# CoordinateWithTimeline: coordinate specification with optional explicit
# timeline.
# - (coord, timeline_id): tuple form for explicit timeline reference.
# - CoordinateSpec: any of the coordinate types above.
CoordinateWithTimeline = Union[tuple[CoordinateSpec, str], CoordinateSpec]
