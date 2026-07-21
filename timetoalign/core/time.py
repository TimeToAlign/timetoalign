"""Time scalars (``TimeScalar`` / ``Coordinate`` / ``Duration``) and paired fields.

This module is the single home for the four scalar pydantic models that
represent positions and elapsed extents on a timeline, together with
their paired ``SemanticField`` field wrappers.

Class hierarchy (diamond MRO for the Id-variants)::

    TimeScalar(BaseModel)                          # abstract base
    ├── Coordinate(TimeScalar)
    ├── Duration(TimeScalar)
    └── IdTimeScalar(TimeScalar)                   # adds `timeline_id`

    IdCoordinate(Coordinate, IdTimeScalar)         # diamond
    IdDuration(Duration, IdTimeScalar)             # diamond

* ``Coordinate`` denotes a position on a timeline (origin is meaningful).
* ``Duration`` denotes an elapsed extent (signed; may be negative when
  produced by ``Coordinate - Coordinate`` with the right operand later
  than the left).
* ``IdCoordinate`` / ``IdDuration`` carry the additional ``timeline_id``
  identifying the timeline they refer to.

Arithmetic semantics (all operators raise ``TypeError`` on incompatible
types and on cross-timeline-id mixing):

* ``Coordinate + Coordinate`` → ``TypeError`` (subtract to get a Duration)
* ``Coordinate + Duration``   → ``Coordinate``
* ``Coordinate - Coordinate`` → ``Duration`` (the canonical way to get one)
* ``Coordinate - Duration``   → ``Coordinate``
* ``Duration  ± Duration``    → ``Duration``
* ``Duration  ± Coordinate``  → ``TypeError``
* ``{Coord,Dur} * / // <number>`` → same kind back
* ``{Coord,Dur} * / // {Coord,Dur}`` → ``TypeError``

PyArrow storage shape (identical for Coordinate, Duration, IdCoordinate,
IdDuration): the scalar's ``value`` is denormalised into a struct
``{value: float64, numerator: int64, denominator: int64}`` so that
rational precision survives Parquet round-trips.  ``unit`` and
``timeline_id`` live in ``pa.Field.metadata`` (the ``TIMETOALIGN_METADATA_KEY``
JSON blob), NOT in the struct.

Paired-field hierarchy::

    SemanticField (Generic[T])
    └── TimeScalarField  (abstract; _raw_cls = DenominateNumberField;
                          consolidates the from_field / from_table /
                          metadata-resolve / repr plumbing)
        ├── CoordinateField   (scalar_cls = Coordinate)
        │   └── IdCoordinateField (scalar_cls = IdCoordinate, carries timeline_id)
        └── DurationField     (scalar_cls = Duration)
            └── IdDurationField   (scalar_cls = IdDuration, carries timeline_id)

The inner raw field is a ``DenominateNumberField`` (a ``RationalField``
with a single bound ``unit``) carrying the denormalised
``{value, numerator, denominator}`` struct.  ``unit`` lives in the
field's ``TIMETOALIGN_METADATA_KEY`` metadata blob; ``timeline_id`` lives there
too for the Id-variants.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any, ClassVar, NamedTuple, Union

import pyarrow as pa
import pyarrow.compute as pc
from pydantic import BaseModel, ConfigDict, field_validator

from .enums import Domain, NumberType, TimeUnit
from .fields import (
    TIMETOALIGN_METADATA_KEY,
    DenominateNumberField,
    ScalarVocabulary,
    SemanticField,
    StructField,
    data_shaped,
    parse_metadata_blob,
    register_value_projector,
)

# ---------------------------------------------------------------------------
# Type aliases & module constants
# ---------------------------------------------------------------------------

# Canonical numeric value type for all four scalars.  Re-exported as
# CoordinateValue / DurationValue for back-compat with maps/ and loader/.
TimeScalarValue = Union[int, float, Fraction]
CoordinateValue = TimeScalarValue
DurationValue = TimeScalarValue

# Discrete units MUST be displayed as integers, never as floats or
# scientific notation.  These are units where fractional values are
# semantically meaningless.
DISCRETE_UNITS = frozenset(
    {"ticks", "pulses", "divs", "samples", "pixels", "px", "frames"}
)


def struct_to_coordinate(
    struct: dict[str, Any],
    number_type: NumberType,
) -> int | float | Fraction:
    """Convert an Arrow coordinate struct to its requested numeric value.

    Args:
        struct: Mapping with ``value``, ``numerator``, and ``denominator`` keys.
        number_type: Numeric representation to return.

    Returns:
        The coordinate value in the requested numeric representation.
    """
    if number_type == NumberType.fraction:
        if struct["numerator"] is not None and struct["denominator"] is not None:
            return Fraction(struct["numerator"], struct["denominator"])
        return Fraction(struct["value"]).limit_denominator()
    if number_type == NumberType.int:
        if struct["numerator"] is not None:
            return int(struct["numerator"])
        return int(struct["value"])
    return struct["value"]


# ---------------------------------------------------------------------------
# TimeScalar — abstract base for Coordinate / Duration / Id-variants
# ---------------------------------------------------------------------------


class TimeScalar(ScalarVocabulary, BaseModel):
    """Abstract base for ``Coordinate`` / ``Duration`` and their Id-variants.

    Holds the (value, unit) pair plus all shared mechanics: validators,
    conversions, comparison, status predicates, stringification, and the
    operator-compatibility helper :meth:`_binop_other` that subclasses
    use to centralise type/unit/timeline-id checking.

    ``TimeScalar`` is not constructed directly; instantiate ``Coordinate``,
    ``Duration``, ``IdCoordinate``, or ``IdDuration`` instead.
    """

    model_config = ConfigDict(
        frozen=True,
        # pydantic does NOT know about Fraction natively;
        # arbitrary_types is required so the field validator below can
        # accept Fraction.
        arbitrary_types_allowed=True,
    )

    value: TimeScalarValue
    unit: TimeUnit

    # -- validators ---------------------------------------------------------

    @field_validator("value", mode="before")
    @classmethod
    def _validate_value(cls, v: object) -> TimeScalarValue:
        if isinstance(v, bool):
            raise TypeError(
                f"Boolean values are not valid {cls.__name__.lower()} values"
            )
        if isinstance(v, (int, float, Fraction)):
            return v
        raise TypeError(
            f"{cls.__name__} value must be int, float, or Fraction, "
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
            f"{cls.__name__} unit must be a TimeUnit or string, got {type(v).__name__}"
        )

    # -- conversions --------------------------------------------------------

    @data_shaped
    def to_float(self) -> float:
        """Convert value to ``float``."""
        return float(self.value)

    @data_shaped
    def to_int(self, rounding: str = "truncate") -> int:
        """Convert value to ``int`` using the given rounding mode.

        Args:
            rounding: One of ``"truncate"`` (default, towards zero),
                ``"round"`` (nearest), ``"floor"`` (towards −∞), or
                ``"ceil"`` (towards +∞).
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
        """Convert value to ``Fraction`` (lossless for int/Fraction)."""
        if isinstance(self.value, Fraction):
            return self.value
        if isinstance(self.value, int):
            return Fraction(self.value, 1)
        return Fraction(self.value).limit_denominator(10000)

    def __float__(self) -> float:
        return float(self.value)

    def __int__(self) -> int:
        return int(self.value)

    # -- properties ---------------------------------------------------------

    @property
    def number_type(self) -> NumberType:
        v = self.value
        if isinstance(v, bool):
            raise TypeError("Boolean values are not valid time-scalar values")
        if isinstance(v, int):
            return NumberType.int
        if isinstance(v, float):
            return NumberType.float
        if isinstance(v, Fraction):
            return NumberType.fraction
        raise TypeError(f"Unknown number type for {type(v)}")  # pragma: no cover

    @property
    def domain(self) -> Domain:
        return self.unit.domain

    @property
    def semantic_type(self) -> str:
        """Canonical name of this scalar's type (overridden by subclasses)."""
        return type(self).__name__

    def metadata_dict(self) -> dict[str, str]:
        """Return the discriminator plus the (unit, domain, number_type) triple."""
        return {
            **super().metadata_dict(),
            "unit": self.unit.value,
            "domain": self.domain.value,
            "number_type": self.number_type.name,
        }

    # -- internal helper used by all operators -----------------------------

    def _id_or_none(self) -> str | None:
        """Return ``self.timeline_id`` if present, else ``None``."""
        return getattr(self, "timeline_id", None)

    def _binop_other(
        self, other: object, op_name: str
    ) -> tuple[TimeScalarValue, str | None]:
        """Validate ``other`` for a binary op against ``self``.

        Returns ``(numeric_value_of_other, result_timeline_id)``.  Raises
        ``TypeError`` on incompatible types, unit mismatch, or
        cross-timeline-id mixing of two Id-scalars with different ids.
        """
        if isinstance(other, bool):
            raise TypeError(f"Cannot {op_name} {type(self).__name__} with bool")
        if isinstance(other, (int, float, Fraction)):
            return other, self._id_or_none()
        if isinstance(other, TimeScalar):
            if self.unit != other.unit:
                raise TypeError(
                    f"Cannot {op_name} {type(self).__name__} and "
                    f"{type(other).__name__} with different units: "
                    f"{self.unit} vs {other.unit}"
                )
            self_id = self._id_or_none()
            other_id = other._id_or_none()
            if self_id is not None and other_id is not None and self_id != other_id:
                raise TypeError(
                    f"Cannot {op_name} {type(self).__name__} and "
                    f"{type(other).__name__} with mismatched timeline_id: "
                    f"{self_id!r} vs {other_id!r}"
                )
            result_id = self_id if self_id is not None else other_id
            return other.value, result_id
        raise TypeError(
            f"Cannot {op_name} {type(self).__name__} with {type(other).__name__}"
        )

    # -- comparisons --------------------------------------------------------
    #
    # NB: pydantic's default ``__eq__`` / ``__hash__`` already compare ALL
    # fields (including ``timeline_id``), which is what we want — do NOT
    # override them.

    def _cmp_value(self, other: object, op_name: str) -> TimeScalarValue:
        if isinstance(other, bool):
            raise TypeError(f"Cannot {op_name} {type(self).__name__} with bool")
        if isinstance(other, (int, float, Fraction)):
            return other
        if isinstance(other, TimeScalar):
            if self.unit != other.unit:
                raise TypeError(
                    f"Cannot {op_name} {type(self).__name__} and "
                    f"{type(other).__name__} with different units: "
                    f"{self.unit} vs {other.unit}"
                )
            self_id = self._id_or_none()
            other_id = other._id_or_none()
            if self_id is not None and other_id is not None and self_id != other_id:
                raise TypeError(
                    f"Cannot {op_name} {type(self).__name__} and "
                    f"{type(other).__name__} with mismatched timeline_id: "
                    f"{self_id!r} vs {other_id!r}"
                )
            return other.value
        raise TypeError(
            f"Cannot {op_name} {type(self).__name__} with {type(other).__name__}"
        )

    @data_shaped
    def __lt__(self, other: object) -> bool:
        return self.value < self._cmp_value(other, "compare")

    @data_shaped
    def __le__(self, other: object) -> bool:
        return self.value <= self._cmp_value(other, "compare")

    @data_shaped
    def __gt__(self, other: object) -> bool:
        return self.value > self._cmp_value(other, "compare")

    @data_shaped
    def __ge__(self, other: object) -> bool:
        return self.value >= self._cmp_value(other, "compare")

    # -- status predicates --------------------------------------------------

    @data_shaped
    def is_zero(self) -> bool:
        return self.value == 0

    @data_shaped
    def is_positive(self) -> bool:
        return self.value > 0

    @data_shaped
    def is_negative(self) -> bool:
        return self.value < 0

    # -- mutators (copy-on-write) ------------------------------------------

    def _rebuild(self, value: TimeScalarValue, unit: TimeUnit) -> TimeScalar:
        """Construct a same-class instance with possibly new value/unit.

        Preserves ``timeline_id`` for Id-variants.
        """
        tl_id = self._id_or_none()
        if tl_id is not None:
            return type(self)(value, unit, tl_id)
        return type(self)(value, unit)

    def with_value(self, new_value: TimeScalarValue) -> TimeScalar:
        """Return a same-class instance with a different value."""
        return self._rebuild(new_value, self.unit)

    def with_unit(self, new_unit: TimeUnit) -> TimeScalar:
        """Return a same-class instance with a different unit.

        Warning: this does NOT convert the value — use a ConversionMap
        for that.  Reinterpretation only.
        """
        return self._rebuild(self.value, new_unit)

    # -- stringification helpers -------------------------------------------

    def _format_value(self) -> str:
        """Format ``self.value`` for ``__str__`` honouring DISCRETE_UNITS."""
        unit_name = self.unit.value if hasattr(self.unit, "value") else str(self.unit)
        unit_lower = unit_name.lower()
        v = self.value
        v_f = float(v)

        if unit_lower in DISCRETE_UNITS or (v == int(v_f) and abs(v_f) < 1e15):
            return f"{int(v_f)}"
        if abs(v_f) >= 1e6:
            return f"{int(round(v_f))}"
        if v_f == 0:
            return "0"
        return f"{v_f:.6f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
# Coordinate
# ---------------------------------------------------------------------------


class Coordinate(TimeScalar):
    """A position on a timeline, defined by a value and unit.

    Coordinates are immutable and support arithmetic operations when
    units match.  They preserve the native numeric type (int, float, or
    Fraction) for precision.

    Attributes:
        value: The numeric position (int, float, or Fraction).
        unit: The time unit (e.g., seconds, quarters, pixels).

    Examples:
        >>> c1 = Coordinate(120, TimeUnit.ticks)
        >>> c2 = Coordinate(240, TimeUnit.ticks)
        >>> c2 - c1
        Duration(120, ticks)
    """

    def __init__(
        self,
        value: TimeScalarValue | dict[str, Any] | None = None,
        unit: TimeUnit | str | None = None,
        /,
        **data: Any,
    ) -> None:
        if value is not None or unit is not None:
            if "value" in data or "unit" in data:
                raise TypeError(
                    f"{type(self).__name__} received conflicting positional "
                    "and keyword arguments"
                )
            data = {"value": value, "unit": unit, **data}
        super().__init__(**data)

    def __index__(self) -> int:
        if isinstance(self.value, int) and not isinstance(self.value, bool):
            return self.value
        raise TypeError(
            f"Cannot use Coordinate with {type(self.value).__name__} value as index. "
            f"Only integer Coordinates can be used as indices."
        )

    @property
    def semantic_type(self) -> str:
        return "Coordinate"

    # -- arithmetic ---------------------------------------------------------

    @data_shaped
    def __add__(self, other: object) -> Coordinate:
        if isinstance(other, Coordinate):
            raise TypeError(
                "Cannot add two Coordinates; subtract them to obtain a Duration"
            )
        v, tl_id = self._binop_other(other, "add")
        return _make_coordinate(self.value + v, self.unit, tl_id)

    @data_shaped
    def __sub__(self, other: object) -> TimeScalar:
        if isinstance(other, Coordinate):
            # Coordinate - Coordinate -> Duration.  Run _binop_other to
            # enforce unit + cross-id checks, but produce a Duration
            # (possibly an IdDuration).
            v, tl_id = self._binop_other(other, "subtract")
            return _make_duration(self.value - v, self.unit, tl_id)
        if isinstance(other, Duration):
            v, tl_id = self._binop_other(other, "subtract")
            return _make_coordinate(self.value - v, self.unit, tl_id)
        # Bare number → Coordinate
        v, tl_id = self._binop_other(other, "subtract")
        return _make_coordinate(self.value - v, self.unit, tl_id)

    @data_shaped
    def __mul__(self, scalar: object) -> Coordinate:
        """Scales a *position* — see Duration for tempo-style scaling of *extents*."""
        if isinstance(scalar, TimeScalar):
            raise TypeError(
                f"Cannot multiply two TimeScalars: "
                f"{type(self).__name__} * {type(scalar).__name__}"
            )
        if isinstance(scalar, bool) or not isinstance(scalar, (int, float, Fraction)):
            raise TypeError(f"Cannot multiply Coordinate by {type(scalar).__name__}")
        return _make_coordinate(self.value * scalar, self.unit, self._id_or_none())

    @data_shaped
    def __rmul__(self, scalar: object) -> Coordinate:
        """Scales a *position* — see Duration for tempo-style scaling of *extents*."""
        return self.__mul__(scalar)

    @data_shaped
    def __truediv__(self, scalar: object) -> Coordinate:
        """Scales a *position* — see Duration for tempo-style scaling of *extents*."""
        if isinstance(scalar, TimeScalar):
            raise TypeError(
                f"Cannot divide two TimeScalars: "
                f"{type(self).__name__} / {type(scalar).__name__}"
            )
        if isinstance(scalar, bool) or not isinstance(scalar, (int, float, Fraction)):
            raise TypeError(f"Cannot divide Coordinate by {type(scalar).__name__}")
        if scalar == 0:
            raise ZeroDivisionError("Cannot divide Coordinate by zero")
        return _make_coordinate(self.value / scalar, self.unit, self._id_or_none())

    @data_shaped
    def __floordiv__(self, scalar: object) -> Coordinate:
        """Scales a *position* — see Duration for tempo-style scaling of *extents*."""
        if isinstance(scalar, TimeScalar):
            raise TypeError(
                f"Cannot floor-divide two TimeScalars: "
                f"{type(self).__name__} // {type(scalar).__name__}"
            )
        if isinstance(scalar, bool) or not isinstance(scalar, (int, float, Fraction)):
            raise TypeError(
                f"Cannot floor-divide Coordinate by {type(scalar).__name__}"
            )
        if scalar == 0:
            raise ZeroDivisionError("Cannot divide Coordinate by zero")
        return _make_coordinate(self.value // scalar, self.unit, self._id_or_none())

    # -- copy-on-write ------------------------------------------------------

    def with_timeline(self, timeline_id: str) -> IdCoordinate:
        """Return an ``IdCoordinate`` carrying the given timeline id."""
        return IdCoordinate(self.value, self.unit, timeline_id)

    # -- formatting ---------------------------------------------------------

    def __repr__(self) -> str:
        return f"Coordinate({self.value!r}, {self.unit})"

    def __str__(self) -> str:
        return f"{self._format_value()} {self.unit}"


# ---------------------------------------------------------------------------
# Duration
# ---------------------------------------------------------------------------


class Duration(TimeScalar):
    """An elapsed extent on a timeline.

    Same physical storage as :class:`Coordinate` (denormalised
    ``{value, numerator, denominator}``) — the distinction is semantic.
    Durations may be negative when produced by ``Coordinate - Coordinate``
    where the second operand precedes the first; status predicates
    (:meth:`is_negative`, :meth:`is_positive`) make the sign queryable.

    Attributes:
        value: The numeric duration (int, float, or Fraction; any sign).
        unit: The time unit (e.g., seconds, quarters, ticks).
    """

    def __init__(
        self,
        value: TimeScalarValue | dict[str, Any] | None = None,
        unit: TimeUnit | str | None = None,
        /,
        **data: Any,
    ) -> None:
        if value is not None or unit is not None:
            if "value" in data or "unit" in data:
                raise TypeError(
                    f"{type(self).__name__} received conflicting positional "
                    "and keyword arguments"
                )
            data = {"value": value, "unit": unit, **data}
        super().__init__(**data)

    @property
    def semantic_type(self) -> str:
        return "Duration"

    # -- arithmetic ---------------------------------------------------------

    @data_shaped
    def __add__(self, other: object) -> Duration:
        if isinstance(other, Coordinate):
            raise TypeError(
                "Cannot add a Coordinate to a Duration; use 'coord + dur' instead"
            )
        v, tl_id = self._binop_other(other, "add")
        return _make_duration(self.value + v, self.unit, tl_id)

    @data_shaped
    def __sub__(self, other: object) -> Duration:
        if isinstance(other, Coordinate):
            raise TypeError("Cannot subtract a Coordinate from a Duration")
        v, tl_id = self._binop_other(other, "subtract")
        return _make_duration(self.value - v, self.unit, tl_id)

    @data_shaped
    def __mul__(self, scalar: object) -> Duration:
        if isinstance(scalar, TimeScalar):
            raise TypeError(
                f"Cannot multiply two TimeScalars: "
                f"{type(self).__name__} * {type(scalar).__name__}"
            )
        if isinstance(scalar, bool) or not isinstance(scalar, (int, float, Fraction)):
            raise TypeError(f"Cannot multiply Duration by {type(scalar).__name__}")
        return _make_duration(self.value * scalar, self.unit, self._id_or_none())

    @data_shaped
    def __rmul__(self, scalar: object) -> Duration:
        return self.__mul__(scalar)

    @data_shaped
    def __truediv__(self, scalar: object) -> Duration:
        if isinstance(scalar, TimeScalar):
            raise TypeError(
                f"Cannot divide two TimeScalars: "
                f"{type(self).__name__} / {type(scalar).__name__}"
            )
        if isinstance(scalar, bool) or not isinstance(scalar, (int, float, Fraction)):
            raise TypeError(f"Cannot divide Duration by {type(scalar).__name__}")
        if scalar == 0:
            raise ZeroDivisionError("Cannot divide Duration by zero")
        return _make_duration(self.value / scalar, self.unit, self._id_or_none())

    @data_shaped
    def __floordiv__(self, scalar: object) -> Duration:
        if isinstance(scalar, TimeScalar):
            raise TypeError(
                f"Cannot floor-divide two TimeScalars: "
                f"{type(self).__name__} // {type(scalar).__name__}"
            )
        if isinstance(scalar, bool) or not isinstance(scalar, (int, float, Fraction)):
            raise TypeError(f"Cannot floor-divide Duration by {type(scalar).__name__}")
        if scalar == 0:
            raise ZeroDivisionError("Cannot divide Duration by zero")
        return _make_duration(self.value // scalar, self.unit, self._id_or_none())

    # -- copy-on-write ------------------------------------------------------

    def with_timeline(self, timeline_id: str) -> IdDuration:
        """Return an ``IdDuration`` carrying the given timeline id."""
        return IdDuration(self.value, self.unit, timeline_id)

    # -- formatting ---------------------------------------------------------

    def __repr__(self) -> str:
        return f"Duration({self.value!r}, {self.unit})"

    def __str__(self) -> str:
        return f"{self._format_value()} {self.unit}"


# ---------------------------------------------------------------------------
# IdTimeScalar — abstract; contributes only the ``timeline_id`` field
# ---------------------------------------------------------------------------


class IdTimeScalar(TimeScalar):
    """Abstract mixin contributing ``timeline_id`` + its validator.

    Construct ``IdCoordinate`` or ``IdDuration`` instead — instantiating
    ``IdTimeScalar`` directly raises ``TypeError``.
    """

    timeline_id: str

    def __init__(self, *args: Any, **data: Any) -> None:
        if type(self) is IdTimeScalar:
            raise TypeError(
                "IdTimeScalar is abstract; construct IdCoordinate or IdDuration"
            )
        super().__init__(*args, **data)

    @field_validator("timeline_id", mode="before")
    @classmethod
    def _validate_timeline_id(cls, v: object) -> str:
        if not isinstance(v, str):
            raise TypeError(f"timeline_id must be a string, got {type(v).__name__}")
        if not v:
            raise ValueError("timeline_id cannot be empty")
        return v


# ---------------------------------------------------------------------------
# IdCoordinate — diamond MRO: IdCoordinate -> Coordinate -> IdTimeScalar
#                            -> TimeScalar -> BaseModel
# ---------------------------------------------------------------------------


class IdCoordinate(Coordinate, IdTimeScalar):
    """A ``Coordinate`` that carries the ID of the timeline it belongs to.

    Extends ``Coordinate`` with a ``timeline_id`` field, providing the
    most specific form of coordinate specification.  Operator results
    inherit the timeline_id (``IdCoordinate + Duration → IdCoordinate``;
    ``IdCoordinate - IdCoordinate → IdDuration`` when the ids match).
    """

    # An IdCoordinate is stored by CoordinateField (the timeline id lives
    # in field metadata, not in the row), so the discriminator is the
    # plain coordinate one rather than the derived "IdCoordinateField".
    field_type_name: ClassVar[str] = "CoordinateField"

    def __init__(
        self,
        value: TimeScalarValue | None = None,
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
        BaseModel.__init__(self, **data)

    @classmethod
    def from_coordinate(cls, coord: Coordinate, timeline_id: str) -> IdCoordinate:
        return cls(coord.value, coord.unit, timeline_id)

    def to_coordinate(self) -> Coordinate:
        return Coordinate(self.value, self.unit)

    def with_timeline(self, timeline_id: str) -> IdCoordinate:
        return IdCoordinate(self.value, self.unit, timeline_id)

    def __repr__(self) -> str:
        return f"IdCoordinate({self.value!r}, {self.unit}, {self.timeline_id!r})"

    def __str__(self) -> str:
        return f"{self._format_value()} {self.unit} @{self.timeline_id}"


# ---------------------------------------------------------------------------
# IdDuration — diamond MRO: IdDuration -> Duration -> IdTimeScalar
#                          -> TimeScalar -> BaseModel
# ---------------------------------------------------------------------------


class IdDuration(Duration, IdTimeScalar):
    """A ``Duration`` that carries the ID of the timeline it belongs to.

    Produced by ``Coordinate - Coordinate`` (with at least one operand
    being an ``IdCoordinate``) and ``IdDuration ± Duration``.
    """

    # Mirrors IdCoordinate: stored by DurationField, with the timeline id
    # carried in field metadata rather than derived into the name.
    field_type_name: ClassVar[str] = "DurationField"

    def __init__(
        self,
        value: TimeScalarValue | None = None,
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
                "IdDuration received conflicting positional and keyword arguments"
            )
        data = {**positional, **data}
        BaseModel.__init__(self, **data)

    @classmethod
    def from_duration(cls, dur: Duration, timeline_id: str) -> IdDuration:
        return cls(dur.value, dur.unit, timeline_id)

    def to_duration(self) -> Duration:
        return Duration(self.value, self.unit)

    def with_timeline(self, timeline_id: str) -> IdDuration:
        return IdDuration(self.value, self.unit, timeline_id)

    def __repr__(self) -> str:
        return f"IdDuration({self.value!r}, {self.unit}, {self.timeline_id!r})"

    def __str__(self) -> str:
        return f"{self._format_value()} {self.unit} @{self.timeline_id}"


# ---------------------------------------------------------------------------
# Result-class factories
# ---------------------------------------------------------------------------


def _make_coordinate(
    value: TimeScalarValue, unit: TimeUnit, timeline_id: str | None
) -> Coordinate:
    """Return ``IdCoordinate`` if a timeline id is given, else ``Coordinate``."""
    if timeline_id is not None:
        return IdCoordinate(value, unit, timeline_id)
    return Coordinate(value, unit)


def _make_duration(
    value: TimeScalarValue, unit: TimeUnit, timeline_id: str | None
) -> Duration:
    """Return ``IdDuration`` if a timeline id is given, else ``Duration``."""
    if timeline_id is not None:
        return IdDuration(value, unit, timeline_id)
    return Duration(value, unit)


# ---------------------------------------------------------------------------
# Value projectors — denormalise ``value`` into 3 Arrow fields, drop ``unit``
# and ``timeline_id`` (they live in field metadata).
# ---------------------------------------------------------------------------


def _time_value_projector(
    _model_cls: type[BaseModel], _name: str, _info: object
) -> list[pa.Field]:
    """Project ``value`` onto the denormalised storage struct."""
    return [
        pa.field("value", pa.float64(), nullable=True),
        pa.field("numerator", pa.int64(), nullable=True),
        pa.field("denominator", pa.int64(), nullable=True),
    ]


def _drop_field_projector(
    _model_cls: type[BaseModel], _name: str, _info: object
) -> list[pa.Field]:
    """Drop a pydantic field from the Arrow representation — lives in metadata."""
    return []


register_value_projector(TimeScalar, "value", _time_value_projector)
register_value_projector(TimeScalar, "unit", _drop_field_projector)
register_value_projector(IdTimeScalar, "timeline_id", _drop_field_projector)


# ---------------------------------------------------------------------------
# Type aliases used by callers
# ---------------------------------------------------------------------------

# CoordinateSpec: any form of coordinate specification.
CoordinateSpec = Union[int, float, Fraction, Coordinate, IdCoordinate]


class ResolvedCoordinate(NamedTuple):
    """Decomposed form of a CoordinateSpec input."""

    value: int | float | Fraction
    timeline_id: str | None
    unit: TimeUnit | None


def resolve_coordinate_spec(
    spec: CoordinateSpec, *, timeline_id: str | None = None
) -> ResolvedCoordinate:
    """Decompose a coordinate specification without converting its unit.

    Args:
        spec: Coordinate specification to decompose.
        timeline_id: Optional timeline ID for otherwise unqualified input.

    Returns:
        The numeric value and any timeline or unit metadata.

    Raises:
        ValueError: If an explicit timeline ID conflicts with an IdCoordinate.
        TypeError: If spec is not a supported coordinate specification.
    """
    if isinstance(spec, IdCoordinate):
        if timeline_id is not None and timeline_id != spec.timeline_id:
            raise ValueError(
                f"Timeline ID '{timeline_id}' conflicts with coordinate timeline ID "
                f"'{spec.timeline_id}'"
            )
        return ResolvedCoordinate(spec.value, spec.timeline_id, spec.unit)
    if isinstance(spec, Coordinate):
        return ResolvedCoordinate(spec.value, timeline_id, spec.unit)
    if not isinstance(spec, bool) and isinstance(spec, (int, float, Fraction)):
        return ResolvedCoordinate(spec, timeline_id, None)
    raise TypeError(f"Unsupported coordinate specification type: {type(spec).__name__}")


# Optional coordinate (common pattern).
OptionalCoordinate = Union[Coordinate, None]


# ═══════════════════════════════════════════════════════════════════════════
# Paired SemanticField classes (TimeScalarField hierarchy)
# ═══════════════════════════════════════════════════════════════════════════


def _scalar_compare_value(other: Any) -> Any:
    """Extract the numeric payload for ``pa.compute`` comparison helpers.

    Accepts a bare number (``int`` / ``float`` / ``Fraction``) or a
    ``TimeScalar`` and returns the underlying numeric value.  Mirrors
    ``TimeScalar._cmp_value`` but without unit / timeline-id checking —
    callers are responsible for ensuring compatibility (Field-level
    arithmetic does the metadata-level invariant check once, not per row).
    """
    if isinstance(other, TimeScalar):
        return float(other.value)
    if isinstance(other, Fraction):
        return float(other)
    if isinstance(other, (int, float)):
        return other
    raise TypeError(f"Cannot compare TimeScalarField with {type(other).__name__}")


def _build_denominated_struct(value_arr: pa.Array) -> pa.StructArray:
    """Wrap a numeric ``pa.Array`` back into the canonical denormalised struct.

    Output: ``{value: float64, numerator: int64 (null), denominator: int64 (null)}``
    — matches ``RATIONAL_STRUCT_TYPE``.  Used by Field-level arithmetic
    to package a freshly-computed ``value`` column into the storage shape
    expected by ``DenominateNumberField``.
    """
    n = len(value_arr)
    value_arr = pc.cast(value_arr, pa.float64())
    null_int = pa.array([None] * n, type=pa.int64())
    return pa.StructArray.from_arrays(
        [value_arr, null_int, null_int],
        fields=[
            pa.field("value", pa.float64(), nullable=True),
            pa.field("numerator", pa.int64(), nullable=True),
            pa.field("denominator", pa.int64(), nullable=True),
        ],
    )


def _coord_field_from_value(
    value_arr: pa.Array,
    unit: Any,
    number_type: Any,
    timeline_id: str | None,
) -> CoordinateField | IdCoordinateField:
    """Construct a CoordinateField (or IdCoordinateField) from a value column."""
    struct = _build_denominated_struct(value_arr)
    pa_field = pa.field(
        "value" if timeline_id is None else "id_value",
        struct.type,
    )
    raw = StructField(struct, pa_field)
    if timeline_id is not None:
        return IdCoordinateField(raw, unit, number_type, timeline_id)
    return CoordinateField(raw, unit, number_type)


def _dur_field_from_value(
    value_arr: pa.Array,
    unit: Any,
    number_type: Any,
    timeline_id: str | None,
) -> DurationField | IdDurationField:
    """Construct a DurationField (or IdDurationField) from a value column."""
    struct = _build_denominated_struct(value_arr)
    pa_field = pa.field(
        "value" if timeline_id is None else "id_value",
        struct.type,
    )
    raw = StructField(struct, pa_field)
    if timeline_id is not None:
        return IdDurationField(raw, unit, number_type, timeline_id)
    return DurationField(raw, unit, number_type)


def _scalar_binop_value_and_id(
    self: TimeScalarField, other: Any, op: str
) -> tuple[Any, str | None]:
    """Extract the numeric payload and result timeline_id for arithmetic.

    Performs the metadata-level invariant check exactly once (unit match,
    cross-timeline-id mismatch) at the entry point of a Field arithmetic
    operation — NEVER per row.  Returns ``(numeric_other, result_tl_id)``.
    """
    self_tl = getattr(self, "_timeline_id", None)
    if isinstance(other, TimeScalar):
        if self.unit != other.unit:
            raise TypeError(
                f"Cannot {op} {type(self).__name__} and "
                f"{type(other).__name__} with different units: "
                f"{self.unit} vs {other.unit}"
            )
        other_tl = getattr(other, "timeline_id", None)
        if self_tl is not None and other_tl is not None and self_tl != other_tl:
            raise TypeError(
                f"Cannot {op} {type(self).__name__} and "
                f"{type(other).__name__} with mismatched timeline_id: "
                f"{self_tl!r} vs {other_tl!r}"
            )
        return float(other.value), self_tl or other_tl
    if isinstance(other, TimeScalarField):
        if self.unit != other.unit:
            raise TypeError(
                f"Cannot {op} {type(self).__name__} and "
                f"{type(other).__name__} with different units: "
                f"{self.unit} vs {other.unit}"
            )
        other_tl = getattr(other, "_timeline_id", None)
        if self_tl is not None and other_tl is not None and self_tl != other_tl:
            raise TypeError(
                f"Cannot {op} {type(self).__name__} and "
                f"{type(other).__name__} with mismatched timeline_id: "
                f"{self_tl!r} vs {other_tl!r}"
            )
        return other._value_array(), self_tl or other_tl
    if isinstance(other, Fraction):
        return float(other), self_tl
    if isinstance(other, (int, float)) and not isinstance(other, bool):
        return other, self_tl
    raise TypeError(f"Cannot {op} {type(self).__name__} with {type(other).__name__}")


class TimeScalarField(SemanticField):
    """Abstract parent for ``Coordinate`` / ``Duration`` (+ Id) semantic fields.

    Consolidates the shared ``from_field`` / ``from_table`` / ``__repr__``
    machinery that previously lived twice on ``CoordinateField`` and
    ``DurationField``.  Concrete subclasses set ``scalar_cls`` (which
    drives ``pa_schema`` caching through
    ``SemanticField.__init_subclass__``), then optionally override
    ``semantic_type``, ``metadata_dict``, and ``__getitem__``.

    The inner raw field is a :class:`DenominateNumberField` (a
    ``RationalField`` with a single bound unit).  Construction accepts
    either a bare :class:`StructField` (promoted internally to a
    ``DenominateNumberField`` using the supplied ``unit``) or a fully
    formed ``DenominateNumberField``.

    Args:
        raw: A ``StructField`` (will be promoted) or a
            ``DenominateNumberField`` holding the denormalised
            ``{value, numerator, denominator}`` struct.
        unit: The time unit bound to this field.  Required when *raw*
            is a bare ``StructField`` or its unit cannot be inferred
            from metadata.
        number_type: The numeric representation used when materialising
            individual scalars (``NumberType.float`` /
            ``NumberType.fraction`` / ``NumberType.int``).
    """

    # Inner raw field type is fixed for the whole TimeScalarField branch.
    _raw_cls = DenominateNumberField  # type: ignore[assignment]

    # ``scalar_cls`` is intentionally left as ``None`` here — concrete
    # leaves set it.

    def __init__(
        self,
        raw: StructField | DenominateNumberField | None = None,
        unit: TimeUnit | str | None = None,
        number_type: NumberType | str | None = None,
        *,
        source_fields: "str | dict[str, Any] | None" = None,
    ) -> None:
        if raw is None and source_fields is None:
            raise TypeError(
                f"{type(self).__name__} requires either a raw field (live) or "
                "source_fields= (blueprint)"
            )

        if raw is not None:
            # Promote a bare StructField to a DenominateNumberField; if
            # already a DenominateNumberField, optionally override unit.
            if not isinstance(raw, DenominateNumberField):
                if not isinstance(raw, StructField):
                    raise TypeError(
                        f"{type(self).__name__} requires StructField or "
                        f"DenominateNumberField, got {type(raw).__name__}"
                    )
                resolved_unit = self._require_unit(unit, type(self).__name__)
                raw = DenominateNumberField(raw.data, raw.field, unit=resolved_unit)
            elif unit is not None:
                # Override: rebuild with the supplied unit.
                raw = DenominateNumberField(
                    raw.data,
                    raw.field,
                    unit=TimeUnit(unit) if isinstance(unit, str) else unit,
                )

        super().__init__(raw, source_fields=source_fields)

        # Resolve number_type: explicit override > metadata > NumberType.float.
        if number_type is None and raw is not None:
            _, number_type = self._resolve_metadata(raw.field, None, None)
        elif number_type is None:
            number_type = NumberType.float
        self._number_type = (
            NumberType(number_type) if isinstance(number_type, str) else number_type
        )

    # -- forwarded properties from the raw layer ----------------------------

    @property
    def unit(self) -> Any:
        """The time unit bound to this field (via the inner ``DenominateNumberField``)."""
        return None if self._raw is None else self._raw.unit

    @property
    def _unit(self) -> Any:
        """Back-compat alias for :attr:`unit`.

        Older callers (subclass methods, tests, serialisation helpers)
        reach into ``self._unit`` directly; keep the name available so
        we do not have to rewrite every reference at once.
        """
        return self.unit

    @property
    def domain(self) -> Any:
        """The temporal domain implied by the unit."""
        return None if self._raw is None else self._raw.domain

    @property
    def number_type(self) -> Any:
        """The numeric representation used for scalar access."""
        return self._number_type

    # -- abstract semantic contract ----------------------------------------

    @property
    def semantic_type(self) -> str:
        # Concrete subclasses override with their scalar's name.
        return type(self).__name__.removesuffix("Field")

    def metadata_dict(self) -> dict[str, str]:
        """Return the discriminator plus the (unit, domain, number_type) triple."""
        return {
            **super().metadata_dict(),
            "unit": self.unit.value,
            "domain": self.domain.value,
            "number_type": self._number_type.name,
        }

    # -- materialisation ----------------------------------------------------

    def _materialise_value(self, i: int) -> TimeScalarValue | None:
        """Extract the i-th element's numeric value, honouring NumberType."""
        raw_dict = self._raw[i]
        if raw_dict is None:
            return None
        return struct_to_coordinate(raw_dict, self._number_type)

    def __getitem__(self, i: int):
        """Materialise the i-th scalar instance.

        Default implementation builds ``cls.scalar_cls(value, unit)``.
        Id-variants override to thread the field's ``_timeline_id``
        into the result.
        """
        value = self._materialise_value(i)
        if value is None:
            return None
        cls = type(self).scalar_cls
        if cls is None:  # pragma: no cover - guarded by __init_subclass__
            raise TypeError(
                f"{type(self).__name__} has no scalar_cls; cannot materialise scalar"
            )
        return cls(value, self.unit)

    # -- unit / number_type resolution helpers ------------------------------

    @staticmethod
    def _require_unit(unit: Any, cls_name: str = "TimeScalarField") -> Any:
        if unit is None:
            raise ValueError(
                f"'unit' is required when constructing {cls_name} from a bare "
                "array or StructField"
            )
        return TimeUnit(unit) if isinstance(unit, str) else unit

    @staticmethod
    def _require_number_type(
        number_type: Any, cls_name: str = "TimeScalarField"
    ) -> Any:
        if number_type is None:
            raise ValueError(
                f"'number_type' is required when constructing {cls_name} from a "
                "bare array or StructField"
            )
        return NumberType(number_type) if isinstance(number_type, str) else number_type

    @staticmethod
    def _resolve_metadata(
        pa_field: pa.Field,
        unit_override: Any,
        nt_override: Any,
    ) -> tuple[Any, Any]:
        """Extract unit and number_type from a ``pa.Field``'s metadata."""
        meta: dict[str, Any] = {}
        raw_meta = pa_field.metadata
        if raw_meta:
            if TIMETOALIGN_METADATA_KEY in raw_meta:
                meta = parse_metadata_blob(raw_meta[TIMETOALIGN_METADATA_KEY])
            else:
                meta = {
                    (k.decode("utf-8") if isinstance(k, bytes) else k): (
                        v.decode("utf-8") if isinstance(v, bytes) else v
                    )
                    for k, v in raw_meta.items()
                }

        if unit_override is not None:
            resolved_unit = (
                TimeUnit(unit_override)
                if isinstance(unit_override, str)
                else unit_override
            )
        elif "unit" in meta:
            resolved_unit = TimeUnit(meta["unit"])
        else:
            resolved_unit = None  # caller decides if this is fatal

        if nt_override is not None:
            resolved_nt = (
                NumberType(nt_override) if isinstance(nt_override, str) else nt_override
            )
        elif "number_type" in meta:
            resolved_nt = NumberType(meta["number_type"])
        else:
            resolved_nt = NumberType.float

        return resolved_unit, resolved_nt

    # -- factories ----------------------------------------------------------

    @classmethod
    def _from_field_impl(
        cls,
        source: Any,
        *,
        unit: TimeUnit | str | None,
        number_type: NumberType | str | None,
        name: str,
        extra_resolved: dict[str, Any] | None = None,
    ) -> TimeScalarField:
        """Construct ``cls`` from one of the supported source shapes.

        ``extra_resolved`` is a hook for Id-subclasses to inject already-
        resolved kwargs (e.g. ``timeline_id``) into the final constructor.
        """
        extra_resolved = extra_resolved or {}

        if isinstance(source, tuple):
            data, pa_field = source
            resolved_unit, resolved_nt = cls._resolve_metadata(
                pa_field, unit, number_type
            )
            if resolved_unit is None:
                raise ValueError(
                    f"Cannot determine unit for field {pa_field.name!r}: no "
                    "'unit' in metadata and no override supplied"
                )
            struct_field = StructField(data, pa_field)
            return cls(struct_field, resolved_unit, resolved_nt, **extra_resolved)

        if isinstance(source, pa.Field):
            resolved_unit, resolved_nt = cls._resolve_metadata(
                source, unit, number_type
            )
            if resolved_unit is None:
                raise ValueError(
                    f"Cannot determine unit for field {source.name!r}: no "
                    "'unit' in metadata and no override supplied"
                )
            struct_field = StructField(None, source)
            return cls(struct_field, resolved_unit, resolved_nt, **extra_resolved)

        if isinstance(source, StructField):
            resolved_unit = cls._require_unit(unit, cls.__name__)
            resolved_nt = cls._require_number_type(number_type, cls.__name__)
            return cls(source, resolved_unit, resolved_nt, **extra_resolved)

        if isinstance(source, (pa.Array, pa.ChunkedArray)):
            resolved_unit = cls._require_unit(unit, cls.__name__)
            resolved_nt = cls._require_number_type(number_type, cls.__name__)
            pa_field = pa.field(name, source.type)
            struct_field = StructField(source, pa_field)
            return cls(struct_field, resolved_unit, resolved_nt, **extra_resolved)

        raise TypeError(
            f"Unsupported source type for {cls.__name__}.from_field: "
            f"{type(source).__name__}"
        )

    @classmethod
    def from_field(
        cls,
        source: (
            pa.Array
            | pa.ChunkedArray
            | StructField
            | pa.Field
            | tuple[pa.Array | None, pa.Field]
        ),
        *,
        unit: TimeUnit | str | None = None,
        number_type: NumberType | str | None = None,
        name: str | None = None,
    ) -> TimeScalarField:
        if name is None:
            name = cls.__name__.removesuffix("Field").lower() or "value"
        return cls._from_field_impl(
            source, unit=unit, number_type=number_type, name=name
        )

    @classmethod
    def from_table(
        cls,
        table: pa.Table,
        field: str | None = None,
        *,
        unit: TimeUnit | str | None = None,
        number_type: NumberType | str | None = None,
    ) -> TimeScalarField:
        if field is None:
            candidates = [
                f.name
                for f in table.schema
                if pa.types.is_struct(f.type)
                and f.metadata
                and TIMETOALIGN_METADATA_KEY in f.metadata
            ]
            if len(candidates) == 1:
                field = candidates[0]
            elif len(candidates) == 0:
                raise ValueError(
                    "No struct field carrying a timetoalign metadata blob found in "
                    "table; pass field= explicitly"
                )
            else:
                raise ValueError(
                    f"Multiple candidate fields found: {candidates}; "
                    "pass field= explicitly"
                )
        pa_field = table.schema.field(field)
        data = table.column(field)
        return cls.from_field((data, pa_field), unit=unit, number_type=number_type)

    def with_unit(self, unit: TimeUnit) -> TimeScalarField:
        """Return a same-class field with a different unit (no value conversion)."""
        return type(self)(self._raw, unit, self._number_type)

    # -- vectorized data-shaped mirrors -------------------------------------
    #
    # These mirror the @data_shaped methods on ``TimeScalar`` (declared in
    # scalar form earlier in the module).  Each is a ``pa.compute``
    # expression over the underlying ``value`` sub-field of the
    # denormalised rational struct, NEVER a per-row Python loop.

    def _value_array(self) -> pa.Array:
        """Return the underlying ``value`` sub-field with outer-struct nulls propagated.

        The inner ``value`` sub-field by itself ignores the outer
        ``{value, numerator, denominator}`` struct's null mask, so a
        naive ``arr.field("value")`` would yield ``0.0`` (or any inner
        value) at positions where the outer struct is null.  We fold
        the outer null mask in via :func:`pc.if_else`, so every
        data-shaped predicate / arithmetic / conversion mirror that
        consumes this method's output sees ``None`` at null positions
        and agrees element-wise with the scalar dispatch.
        """
        arr = self.to_pyarrow()
        value_arr = arr.field("value")
        outer_valid = arr.is_valid()
        return pc.if_else(outer_valid, value_arr, pa.scalar(None, type=value_arr.type))

    def to_float(self) -> pa.Array:
        """Vectorized cast of the ``value`` sub-field to ``float64``."""
        return pc.cast(self._value_array(), pa.float64())

    def to_int(self, rounding: str = "truncate") -> pa.Array:
        """Vectorized cast to ``int64`` with the given rounding mode."""
        v = self._value_array()
        if rounding == "truncate":
            rounded = pc.trunc(v)
        elif rounding == "round":
            rounded = pc.round(v)
        elif rounding == "floor":
            rounded = pc.floor(v)
        elif rounding == "ceil":
            rounded = pc.ceil(v)
        else:
            raise ValueError(
                f"Unknown rounding mode: {rounding!r}. "
                f"Use 'truncate', 'round', 'floor', or 'ceil'."
            )
        return pc.cast(rounded, pa.int64())

    def is_zero(self) -> pa.Array:
        """Vectorized ``pc.equal(value, 0)`` predicate."""
        return pc.equal(self._value_array(), 0)

    def is_positive(self) -> pa.Array:
        """Vectorized ``pc.greater(value, 0)`` predicate."""
        return pc.greater(self._value_array(), 0)

    def is_negative(self) -> pa.Array:
        """Vectorized ``pc.less(value, 0)`` predicate."""
        return pc.less(self._value_array(), 0)

    # -- comparison mirrors -------------------------------------------------
    #
    # NB: Python ``__lt__`` / ``__le__`` / ``__gt__`` / ``__ge__`` MUST
    # return a bool — pa.Array cannot legally be returned from a dunder
    # without breaking ``sorted()``, ``list.sort()``, etc.  We therefore
    # split the surface: the parity-mirror dunders raise (see __init_subclass__
    # warning below), and the vectorized predicates live under explicit
    # names (``less_than``, ``less_equal``, etc.) plus a single ``compare``
    # entry-point.

    def less_than(self, other: TimeScalar | int | float | Fraction) -> pa.Array:
        """Vectorized ``pc.less(value, other)``."""
        return pc.less(self._value_array(), _scalar_compare_value(other))

    def less_equal(self, other: TimeScalar | int | float | Fraction) -> pa.Array:
        """Vectorized ``pc.less_equal(value, other)``."""
        return pc.less_equal(self._value_array(), _scalar_compare_value(other))

    def greater_than(self, other: TimeScalar | int | float | Fraction) -> pa.Array:
        """Vectorized ``pc.greater(value, other)``."""
        return pc.greater(self._value_array(), _scalar_compare_value(other))

    def greater_equal(self, other: TimeScalar | int | float | Fraction) -> pa.Array:
        """Vectorized ``pc.greater_equal(value, other)``."""
        return pc.greater_equal(self._value_array(), _scalar_compare_value(other))

    # Parity-mirror dunders.  Python protocol requires ``bool`` returns;
    # use the explicit ``less_than`` / ``less_equal`` / ``greater_than``
    # / ``greater_equal`` methods for vectorized comparisons.
    def __lt__(self, other: object) -> pa.Array:
        return self.less_than(other)  # type: ignore[arg-type]

    def __le__(self, other: object) -> pa.Array:
        return self.less_equal(other)  # type: ignore[arg-type]

    def __gt__(self, other: object) -> pa.Array:
        return self.greater_than(other)  # type: ignore[arg-type]

    def __ge__(self, other: object) -> pa.Array:
        return self.greater_equal(other)  # type: ignore[arg-type]

    def __repr__(self) -> str:
        length = len(self) if not self.is_empty else 0
        return (
            f"{type(self).__name__}(name={self.name!r}, unit={self._unit}, "
            f"number_type={self._number_type}, len={length})"
        )


# ---------------------------------------------------------------------------
# CoordinateField
# ---------------------------------------------------------------------------


class CoordinateField(TimeScalarField):
    """Semantic field for coordinate fields.

    Wraps a ``StructField`` containing the coordinate struct
    ``{value: float64, numerator: int64, denominator: int64}`` and adds
    semantic identity: unit, domain, number_type.

    Pairs with :class:`Coordinate`.

    Examples:
        >>> import pyarrow as pa
        >>> from timetoalign.core.enums import TimeUnit, NumberType
        >>> from timetoalign.core.time import CoordinateField
        >>> arr = pa.array(
        ...     [{"value": 1.5, "numerator": 3, "denominator": 2}],
        ...     type=pa.struct([
        ...         pa.field("value", pa.float64()),
        ...         pa.field("numerator", pa.int64()),
        ...         pa.field("denominator", pa.int64()),
        ...     ]),
        ... )
        >>> cf = CoordinateField.from_field(arr, unit=TimeUnit.seconds, number_type=NumberType.float)
        >>> cf[0]
        Coordinate(1.5, seconds)
    """

    scalar_cls = Coordinate

    @property
    def semantic_type(self) -> str:
        return "Coordinate"

    def __getitem__(self, i: int) -> Coordinate | None:
        value = self._materialise_value(i)
        if value is None:
            return None
        return Coordinate(value, self._unit)

    # -- vectorized arithmetic mirrors --------------------------------------
    #
    # Mirrors ``Coordinate.__add__`` etc.  Per-row ``pa.compute`` over the
    # ``value`` sub-field; metadata-level invariants (unit match, timeline
    # id) are checked once per call, never per row.

    def __add__(self, other: object) -> CoordinateField | DurationField:
        if isinstance(other, (Coordinate, CoordinateField)):
            raise TypeError(
                "Cannot add two Coordinate fields; subtract them to obtain a Duration"
            )
        v, tl = _scalar_binop_value_and_id(self, other, "add")
        new_value = pc.add(self._value_array(), v)
        return _coord_field_from_value(new_value, self._unit, self._number_type, tl)

    def __sub__(self, other: object) -> CoordinateField | DurationField:
        if isinstance(other, (Coordinate, CoordinateField)):
            v, tl = _scalar_binop_value_and_id(self, other, "subtract")
            new_value = pc.subtract(self._value_array(), v)
            return _dur_field_from_value(new_value, self._unit, self._number_type, tl)
        if isinstance(other, (Duration, DurationField)):
            v, tl = _scalar_binop_value_and_id(self, other, "subtract")
            new_value = pc.subtract(self._value_array(), v)
            return _coord_field_from_value(new_value, self._unit, self._number_type, tl)
        v, tl = _scalar_binop_value_and_id(self, other, "subtract")
        new_value = pc.subtract(self._value_array(), v)
        return _coord_field_from_value(new_value, self._unit, self._number_type, tl)

    def __mul__(self, scalar: object) -> CoordinateField:
        """Scales a *position* — see Duration for tempo-style scaling of *extents*."""
        if isinstance(scalar, (TimeScalar, TimeScalarField)):
            raise TypeError(
                f"Cannot multiply two TimeScalar fields: "
                f"{type(self).__name__} * {type(scalar).__name__}"
            )
        if isinstance(scalar, bool) or not isinstance(scalar, (int, float, Fraction)):
            raise TypeError(
                f"Cannot multiply CoordinateField by {type(scalar).__name__}"
            )
        new_value = pc.multiply(self._value_array(), float(scalar))
        return _coord_field_from_value(
            new_value,
            self._unit,
            self._number_type,
            getattr(self, "_timeline_id", None),
        )

    def __rmul__(self, scalar: object) -> CoordinateField:
        """Scales a *position* — see Duration for tempo-style scaling of *extents*."""
        return self.__mul__(scalar)

    def __truediv__(self, scalar: object) -> CoordinateField:
        """Scales a *position* — see Duration for tempo-style scaling of *extents*."""
        if isinstance(scalar, (TimeScalar, TimeScalarField)):
            raise TypeError(
                f"Cannot divide two TimeScalar fields: "
                f"{type(self).__name__} / {type(scalar).__name__}"
            )
        if isinstance(scalar, bool) or not isinstance(scalar, (int, float, Fraction)):
            raise TypeError(f"Cannot divide CoordinateField by {type(scalar).__name__}")
        if scalar == 0:
            raise ZeroDivisionError("Cannot divide CoordinateField by zero")
        new_value = pc.divide(self._value_array(), float(scalar))
        return _coord_field_from_value(
            new_value,
            self._unit,
            self._number_type,
            getattr(self, "_timeline_id", None),
        )

    def __floordiv__(self, scalar: object) -> CoordinateField:
        """Scales a *position* — see Duration for tempo-style scaling of *extents*."""
        if isinstance(scalar, (TimeScalar, TimeScalarField)):
            raise TypeError(
                f"Cannot floor-divide two TimeScalar fields: "
                f"{type(self).__name__} // {type(scalar).__name__}"
            )
        if isinstance(scalar, bool) or not isinstance(scalar, (int, float, Fraction)):
            raise TypeError(
                f"Cannot floor-divide CoordinateField by {type(scalar).__name__}"
            )
        if scalar == 0:
            raise ZeroDivisionError("Cannot divide CoordinateField by zero")
        new_value = pc.floor(pc.divide(self._value_array(), float(scalar)))
        return _coord_field_from_value(
            new_value,
            self._unit,
            self._number_type,
            getattr(self, "_timeline_id", None),
        )

    @classmethod
    def matches_pa_field(cls, pa_field: pa.Field) -> bool:
        """Reject ``IdCoordinateField`` shapes — they live in a sibling class.

        The base ``SemanticField.matches_pa_field`` is shape-OR-metadata.
        Since ``IdCoordinateField`` has the same struct shape, this method
        explicitly rejects ``pa.Field`` whose metadata advertises
        ``"IdCoordinateField"``; structural shape matches still resolve to
        ``CoordinateField`` for backward compatibility with non-Id fields.
        """
        # Inspect metadata first.  If the metadata blob explicitly says
        # this is an IdCoordinateField, this class does NOT match (its
        # sibling will).
        if (
            pa_field.metadata is not None
            and TIMETOALIGN_METADATA_KEY in pa_field.metadata
        ):
            try:
                meta = parse_metadata_blob(pa_field.metadata[TIMETOALIGN_METADATA_KEY])
            except (ValueError, UnicodeDecodeError):
                meta = {}
            if meta:
                ft = meta.get("field_type")
                if ft == "IdCoordinateField":
                    return False
                if ft == cls.__name__:
                    return True
        return super().matches_pa_field(pa_field)


# ---------------------------------------------------------------------------
# IdCoordinateField — carries timeline_id, materialises IdCoordinate
# ---------------------------------------------------------------------------


class IdCoordinateField(CoordinateField):
    """Coordinate field annotated with a ``timeline_id``.

    On-disk struct shape is identical to :class:`CoordinateField`; the
    timeline id lives in field metadata (the ``TIMETOALIGN_METADATA_KEY`` blob)
    and on the live instance.  Materialised scalars are
    :class:`IdCoordinate`.
    """

    scalar_cls = IdCoordinate

    def __init__(
        self,
        raw: StructField,
        unit: Any,
        number_type: Any,
        timeline_id: str,
    ) -> None:
        super().__init__(raw, unit, number_type)
        if not isinstance(timeline_id, str) or not timeline_id:
            raise ValueError(
                f"IdCoordinateField requires a non-empty timeline_id string; "
                f"got {timeline_id!r}"
            )
        self._timeline_id = timeline_id

    @property
    def timeline_id(self) -> str:
        return self._timeline_id

    @property
    def semantic_type(self) -> str:
        return "IdCoordinate"

    def metadata_dict(self) -> dict[str, str]:
        """Extend the inherited payload with this field's bound timeline id."""
        return {**super().metadata_dict(), "timeline_id": self._timeline_id}

    def __getitem__(self, i: int) -> IdCoordinate | None:
        value = self._materialise_value(i)
        if value is None:
            return None
        return IdCoordinate(value, self._unit, self._timeline_id)

    @classmethod
    def from_field(
        cls,
        source: (
            pa.Array
            | pa.ChunkedArray
            | StructField
            | pa.Field
            | tuple[pa.Array | None, pa.Field]
        ),
        *,
        unit: TimeUnit | str | None = None,
        number_type: NumberType | str | None = None,
        timeline_id: str | None = None,
        name: str | None = None,
    ) -> IdCoordinateField:
        if name is None:
            name = "id_coordinate"
        resolved_tl_id = _resolve_timeline_id(source, timeline_id)
        return cls._from_field_impl(
            source,
            unit=unit,
            number_type=number_type,
            name=name,
            extra_resolved={"timeline_id": resolved_tl_id},
        )

    def with_unit(self, unit: TimeUnit) -> IdCoordinateField:
        return IdCoordinateField(self._raw, unit, self._number_type, self._timeline_id)

    @classmethod
    def matches_pa_field(cls, pa_field: pa.Field) -> bool:
        """Require ``field_type == "IdCoordinateField"`` in the metadata blob.

        Id-variants share their struct shape with their non-Id parent, so
        pure structural matching cannot distinguish them.  The
        ``TIMETOALIGN_METADATA_KEY`` JSON blob's ``field_type`` key is the
        authoritative discriminator (already injected by ``metadata_dict``
        at the SemanticField boundary).
        """
        if (
            pa_field.metadata is None
            or TIMETOALIGN_METADATA_KEY not in pa_field.metadata
        ):
            return False
        try:
            meta = parse_metadata_blob(pa_field.metadata[TIMETOALIGN_METADATA_KEY])
        except (ValueError, UnicodeDecodeError):
            return False
        return meta.get("field_type") == "IdCoordinateField"


# ---------------------------------------------------------------------------
# DurationField
# ---------------------------------------------------------------------------


class DurationField(TimeScalarField):
    """Semantic field for duration fields.

    Uses the same coordinate struct ``{value, numerator, denominator}``
    as :class:`CoordinateField`; the distinction is semantic.
    Pairs with :class:`Duration`.
    """

    scalar_cls = Duration

    @property
    def semantic_type(self) -> str:
        return "Duration"

    def __getitem__(self, i: int) -> Duration | None:
        value = self._materialise_value(i)
        if value is None:
            return None
        return Duration(value, self._unit)

    # -- vectorized arithmetic mirrors --------------------------------------

    def __add__(self, other: object) -> DurationField:
        if isinstance(other, (Coordinate, CoordinateField)):
            raise TypeError(
                "Cannot add a Coordinate to a Duration field; "
                "use 'coord + dur' instead"
            )
        v, tl = _scalar_binop_value_and_id(self, other, "add")
        new_value = pc.add(self._value_array(), v)
        return _dur_field_from_value(new_value, self._unit, self._number_type, tl)

    def __sub__(self, other: object) -> DurationField:
        if isinstance(other, (Coordinate, CoordinateField)):
            raise TypeError("Cannot subtract a Coordinate from a Duration field")
        v, tl = _scalar_binop_value_and_id(self, other, "subtract")
        new_value = pc.subtract(self._value_array(), v)
        return _dur_field_from_value(new_value, self._unit, self._number_type, tl)

    def __mul__(self, scalar: object) -> DurationField:
        if isinstance(scalar, (TimeScalar, TimeScalarField)):
            raise TypeError(
                f"Cannot multiply two TimeScalar fields: "
                f"{type(self).__name__} * {type(scalar).__name__}"
            )
        if isinstance(scalar, bool) or not isinstance(scalar, (int, float, Fraction)):
            raise TypeError(f"Cannot multiply DurationField by {type(scalar).__name__}")
        new_value = pc.multiply(self._value_array(), float(scalar))
        return _dur_field_from_value(
            new_value,
            self._unit,
            self._number_type,
            getattr(self, "_timeline_id", None),
        )

    def __rmul__(self, scalar: object) -> DurationField:
        return self.__mul__(scalar)

    def __truediv__(self, scalar: object) -> DurationField:
        if isinstance(scalar, (TimeScalar, TimeScalarField)):
            raise TypeError(
                f"Cannot divide two TimeScalar fields: "
                f"{type(self).__name__} / {type(scalar).__name__}"
            )
        if isinstance(scalar, bool) or not isinstance(scalar, (int, float, Fraction)):
            raise TypeError(f"Cannot divide DurationField by {type(scalar).__name__}")
        if scalar == 0:
            raise ZeroDivisionError("Cannot divide DurationField by zero")
        new_value = pc.divide(self._value_array(), float(scalar))
        return _dur_field_from_value(
            new_value,
            self._unit,
            self._number_type,
            getattr(self, "_timeline_id", None),
        )

    def __floordiv__(self, scalar: object) -> DurationField:
        if isinstance(scalar, (TimeScalar, TimeScalarField)):
            raise TypeError(
                f"Cannot floor-divide two TimeScalar fields: "
                f"{type(self).__name__} // {type(scalar).__name__}"
            )
        if isinstance(scalar, bool) or not isinstance(scalar, (int, float, Fraction)):
            raise TypeError(
                f"Cannot floor-divide DurationField by {type(scalar).__name__}"
            )
        if scalar == 0:
            raise ZeroDivisionError("Cannot divide DurationField by zero")
        new_value = pc.floor(pc.divide(self._value_array(), float(scalar)))
        return _dur_field_from_value(
            new_value,
            self._unit,
            self._number_type,
            getattr(self, "_timeline_id", None),
        )

    @classmethod
    def matches_pa_field(cls, pa_field: pa.Field) -> bool:
        """Reject ``IdDurationField`` shapes; otherwise defer to the base."""
        if (
            pa_field.metadata is not None
            and TIMETOALIGN_METADATA_KEY in pa_field.metadata
        ):
            try:
                meta = parse_metadata_blob(pa_field.metadata[TIMETOALIGN_METADATA_KEY])
            except (ValueError, UnicodeDecodeError):
                meta = {}
            if meta:
                ft = meta.get("field_type")
                if ft == "IdDurationField":
                    return False
                if ft == cls.__name__:
                    return True
        return super().matches_pa_field(pa_field)


# ---------------------------------------------------------------------------
# IdDurationField — carries timeline_id, materialises IdDuration
# ---------------------------------------------------------------------------


class IdDurationField(DurationField):
    """Duration field annotated with a ``timeline_id``.

    On-disk struct shape is identical to :class:`DurationField`; the
    timeline id lives in field metadata.  Materialised scalars are
    :class:`IdDuration`.
    """

    scalar_cls = IdDuration

    def __init__(
        self,
        raw: StructField,
        unit: Any,
        number_type: Any,
        timeline_id: str,
    ) -> None:
        super().__init__(raw, unit, number_type)
        if not isinstance(timeline_id, str) or not timeline_id:
            raise ValueError(
                f"IdDurationField requires a non-empty timeline_id string; "
                f"got {timeline_id!r}"
            )
        self._timeline_id = timeline_id

    @property
    def timeline_id(self) -> str:
        return self._timeline_id

    @property
    def semantic_type(self) -> str:
        return "IdDuration"

    def metadata_dict(self) -> dict[str, str]:
        """Extend the inherited payload with this field's bound timeline id."""
        return {**super().metadata_dict(), "timeline_id": self._timeline_id}

    def __getitem__(self, i: int) -> IdDuration | None:
        value = self._materialise_value(i)
        if value is None:
            return None
        return IdDuration(value, self._unit, self._timeline_id)

    @classmethod
    def from_field(
        cls,
        source: (
            pa.Array
            | pa.ChunkedArray
            | StructField
            | pa.Field
            | tuple[pa.Array | None, pa.Field]
        ),
        *,
        unit: TimeUnit | str | None = None,
        number_type: NumberType | str | None = None,
        timeline_id: str | None = None,
        name: str | None = None,
    ) -> IdDurationField:
        if name is None:
            name = "id_duration"
        resolved_tl_id = _resolve_timeline_id(source, timeline_id)
        return cls._from_field_impl(
            source,
            unit=unit,
            number_type=number_type,
            name=name,
            extra_resolved={"timeline_id": resolved_tl_id},
        )

    def with_unit(self, unit: TimeUnit) -> IdDurationField:
        return IdDurationField(self._raw, unit, self._number_type, self._timeline_id)

    @classmethod
    def matches_pa_field(cls, pa_field: pa.Field) -> bool:
        """Require ``field_type == "IdDurationField"`` in the metadata blob."""
        if (
            pa_field.metadata is None
            or TIMETOALIGN_METADATA_KEY not in pa_field.metadata
        ):
            return False
        try:
            meta = parse_metadata_blob(pa_field.metadata[TIMETOALIGN_METADATA_KEY])
        except (ValueError, UnicodeDecodeError):
            return False
        return meta.get("field_type") == "IdDurationField"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_timeline_id(source: Any, override: str | None) -> str:
    """Resolve ``timeline_id`` from a kwarg override or field metadata."""
    if override is not None:
        if not isinstance(override, str) or not override:
            raise ValueError(
                f"timeline_id must be a non-empty string, got {override!r}"
            )
        return override

    pa_field: pa.Field | None = None
    if isinstance(source, tuple) and len(source) == 2:
        pa_field = source[1]
    elif isinstance(source, pa.Field):
        pa_field = source
    elif isinstance(source, StructField):
        pa_field = source.field

    if pa_field is not None and pa_field.metadata:
        if TIMETOALIGN_METADATA_KEY in pa_field.metadata:
            try:
                meta = parse_metadata_blob(pa_field.metadata[TIMETOALIGN_METADATA_KEY])
            except (ValueError, UnicodeDecodeError):
                meta = {}
            tl_id = meta.get("timeline_id")
            if isinstance(tl_id, str) and tl_id:
                return tl_id

    raise ValueError(
        "timeline_id is required for Id-variant fields; pass it explicitly "
        "or store it in the field's timetoalign metadata blob."
    )
