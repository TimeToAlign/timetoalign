"""Duration scalar for the Time To Align! type hierarchy.

``Duration`` represents a non-negative elapsed extent on a timeline.
Storage struct is identical to :class:`~timetoalign.core.types.Coordinate`
(denormalised ``{value, numerator, denominator}``) — the distinction is
semantic: durations are anchored at zero, have no origin, and can never
be negative.

WP2 bulk-migration scalar: defined as a pydantic v2 ``BaseModel`` with a
``value >= 0`` validator.  Same projector pattern as ``Coordinate`` — the
``value`` field expands to the denormalised three-field struct; ``unit``
lives in ``pa.Field.metadata``.

Full arithmetic (``Duration + Duration``, ``Coordinate - Coordinate →
Duration``, …) lands in WP3; this module provides the minimal scalar
surface needed for round-trips and field aliasing.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any, Union

import pyarrow as pa
from pydantic import BaseModel, ConfigDict, field_validator

from ..enums import Domain, NumberType, TimeUnit
from ..schemas.from_pydantic import register_value_projector

# Type alias matching CoordinateValue (kept local to avoid cyclic imports).
DurationValue = Union[int, float, Fraction]

# Discrete units mirror the Coordinate set — formatting follows the same
# rules: integer display for ticks/samples/pixels/frames, fixed-point for
# continuous units.
DISCRETE_UNITS = frozenset(
    {"ticks", "pulses", "divs", "samples", "pixels", "px", "frames"}
)


class Duration(BaseModel):
    """A non-negative elapsed extent on a timeline.

    Same physical storage as :class:`~timetoalign.core.types.Coordinate`,
    but with the strict semantic constraint ``value >= 0``.  Durations
    cannot carry a sign; signed temporal offsets are coordinates.

    Attributes:
        value: The numeric duration (int, float, or Fraction).  Must be
            non-negative.
        unit: The time unit (e.g., seconds, quarters, ticks).

    Examples:
        >>> Duration(120, TimeUnit.ticks)
        Duration(120, ticks)

        >>> Duration(Fraction(3, 4), TimeUnit.quarters)
        Duration(Fraction(3, 4), quarters)

        >>> Duration(-1, TimeUnit.seconds)
        Traceback (most recent call last):
            ...
        pydantic_core._pydantic_core.ValidationError: 1 validation error for Duration
        value
          Value error, Duration value must be non-negative ...
    """

    model_config = ConfigDict(
        frozen=True,
        # Fraction is not a pydantic-native type.
        arbitrary_types_allowed=True,
    )

    value: DurationValue
    unit: TimeUnit

    # --- Positional-argument compatibility --------------------------------

    def __init__(
        self,
        value: DurationValue | dict[str, Any] | None = None,
        unit: TimeUnit | str | None = None,
        /,
        **data: Any,
    ) -> None:
        if value is not None or unit is not None:
            if "value" in data or "unit" in data:
                raise TypeError(
                    "Duration received conflicting positional and keyword arguments"
                )
            data = {"value": value, "unit": unit, **data}
        super().__init__(**data)

    # --- Validators -------------------------------------------------------

    @field_validator("value", mode="before")
    @classmethod
    def _validate_value(cls, v: object) -> DurationValue:
        if isinstance(v, bool):
            raise TypeError("Boolean values are not valid duration values")
        if not isinstance(v, (int, float, Fraction)):
            raise TypeError(
                f"Duration value must be int, float, or Fraction, "
                f"got {type(v).__name__}"
            )
        if v < 0:
            raise ValueError(f"Duration value must be non-negative, got {v!r}")
        return v

    @field_validator("unit", mode="before")
    @classmethod
    def _validate_unit(cls, v: object) -> TimeUnit:
        if isinstance(v, TimeUnit):
            return v
        if isinstance(v, str):
            return TimeUnit(v)
        raise TypeError(
            f"Duration unit must be a TimeUnit or string, got {type(v).__name__}"
        )

    # --- Type conversions -------------------------------------------------

    def to_float(self) -> float:
        """Convert value to float."""
        return float(self.value)

    def to_int(self, rounding: str = "truncate") -> int:
        """Convert value to int.

        Args:
            rounding: ``"truncate"`` (default), ``"round"``, ``"floor"``,
                or ``"ceil"``.
        """
        import math

        if rounding == "truncate":
            return int(self.value)
        if rounding == "round":
            return round(self.value)
        if rounding == "floor":
            return math.floor(self.value)
        if rounding == "ceil":
            return math.ceil(self.value)
        raise ValueError(
            f"Unknown rounding mode: {rounding!r}. "
            f"Use 'truncate', 'round', 'floor', or 'ceil'."
        )

    def to_fraction(self) -> Fraction:
        """Convert value to Fraction (lossless for int/Fraction)."""
        if isinstance(self.value, Fraction):
            return self.value
        if isinstance(self.value, int):
            return Fraction(self.value, 1)
        return Fraction(self.value).limit_denominator(10000)

    def __float__(self) -> float:
        return float(self.value)

    def __int__(self) -> int:
        return int(self.value)

    # --- Semantic interface (mirrors Coordinate) --------------------------

    @property
    def number_type(self) -> NumberType:
        if isinstance(self.value, bool):
            raise TypeError("Boolean values are not valid duration values")
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
        return self.unit.domain

    @property
    def semantic_type(self) -> str:
        return "Duration"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "DurationField",
            "unit": self.unit.value,
            "domain": self.domain.value,
            "number_type": self.number_type.name,
        }

    # --- Comparison & predicates -----------------------------------------

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Duration) or self.unit != other.unit:
            raise TypeError("Can only compare Durations with matching units")
        return self.value < other.value

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Duration) or self.unit != other.unit:
            raise TypeError("Can only compare Durations with matching units")
        return self.value <= other.value

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Duration) or self.unit != other.unit:
            raise TypeError("Can only compare Durations with matching units")
        return self.value > other.value

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Duration) or self.unit != other.unit:
            raise TypeError("Can only compare Durations with matching units")
        return self.value >= other.value

    def is_zero(self) -> bool:
        """Return True for a zero-length duration."""
        return self.value == 0

    # --- String forms -----------------------------------------------------

    def __repr__(self) -> str:
        return f"Duration({self.value!r}, {self.unit})"

    def __str__(self) -> str:
        unit_name = self.unit.value if hasattr(self.unit, "value") else str(self.unit)
        v_f = float(self.value)
        if unit_name.lower() in DISCRETE_UNITS or (
            self.value == int(v_f) and abs(v_f) < 1e15
        ):
            return f"{int(v_f)} {self.unit}"
        return f"{v_f:.6f}".rstrip("0").rstrip(".") + f" {self.unit}"


# ---------------------------------------------------------------------------
# Value projectors mirroring Coordinate.
# ---------------------------------------------------------------------------


def _duration_value_projector(
    _model_cls: type[BaseModel], _name: str, _info: object
) -> list[pa.Field]:
    """Project ``Duration.value`` onto the same denormalised struct as Coordinate."""
    return [
        pa.field("value", pa.float64(), nullable=True),
        pa.field("numerator", pa.int64(), nullable=True),
        pa.field("denominator", pa.int64(), nullable=True),
    ]


def _duration_unit_projector(
    _model_cls: type[BaseModel], _name: str, _info: object
) -> list[pa.Field]:
    """Drop ``Duration.unit`` from the Arrow column — it lives in metadata."""
    return []


register_value_projector(Duration, "value", _duration_value_projector)
register_value_projector(Duration, "unit", _duration_unit_projector)
