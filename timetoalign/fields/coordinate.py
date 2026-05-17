"""Coordinate and duration fields -- semantic columnar wrappers for temporal data.

``NumberField(SemanticField[StructField])`` is the shared parent for
``CoordinateField`` and ``DurationField``.  Both wrap a ``StructField``
whose PyArrow struct layout is ``{value: float64, numerator: int64,
denominator: int64}`` (the canonical coordinate storage).

Note:
    This is ``fields.CoordinateField`` (a DataField subclass).  It
    coexists with ``loader.schema.CoordinateField`` (a loader-config
    descriptor) -- the two classes serve different purposes.
"""

from __future__ import annotations

import json
from abc import abstractmethod

import pyarrow as pa

from ..core.enums import Domain, NumberType, TimeUnit
from ..core.types import Coordinate
from ..loader.schema import struct_to_coordinate
from .base import SemanticField, StructField

_TIMETOALIGN_KEY = b"timetoalign"


# ---------------------------------------------------------------------------
# NumberField (abstract parent)
# ---------------------------------------------------------------------------


class NumberField(SemanticField[StructField]):
    """Abstract parent for numeric struct fields (coordinates, durations).

    Wraps a ``StructField`` and adds unit/number_type semantics plus
    shared serialisation logic.

    Args:
        raw: The inner ``StructField`` holding numeric struct data.
        unit: The time unit.
        number_type: The numeric representation used for scalar access.
    """

    def __init__(
        self, raw: StructField, unit: TimeUnit, number_type: NumberType
    ) -> None:
        super().__init__(raw)
        self._unit = TimeUnit(unit) if isinstance(unit, str) else unit
        self._number_type = number_type

    @property
    def unit(self) -> TimeUnit:
        """The time unit of this field."""
        return self._unit

    @property
    def domain(self) -> Domain:
        """The temporal domain, derived from the unit."""
        return self._unit.domain

    @property
    def number_type(self) -> NumberType:
        """The numeric representation used for scalar access."""
        return self._number_type

    @property
    @abstractmethod
    def semantic_type(self) -> str: ...

    @abstractmethod
    def metadata_dict(self) -> dict[str, str]: ...

    # -- serialisation helpers -----------------------------------------------

    def to_field(self) -> pa.Field:
        """Return a ``pa.Field`` with ``b"timetoalign"`` metadata injected."""
        meta_blob = json.dumps(self.metadata_dict()).encode("utf-8")
        existing = self._field.metadata or {}
        merged = {**existing, _TIMETOALIGN_KEY: meta_blob}
        return self._field.with_metadata(merged)

    # -- private helpers -----------------------------------------------------

    @staticmethod
    def _require_unit(
        unit: TimeUnit | str | None, cls_name: str = "NumberField"
    ) -> TimeUnit:
        """Validate and coerce the *unit* argument."""
        if unit is None:
            raise ValueError(
                f"'unit' is required when constructing {cls_name} from a bare array or StructField"
            )
        return TimeUnit(unit) if isinstance(unit, str) else unit

    @staticmethod
    def _require_number_type(
        number_type: NumberType | str | None, cls_name: str = "NumberField"
    ) -> NumberType:
        """Validate and coerce the *number_type* argument."""
        if number_type is None:
            raise ValueError(
                f"'number_type' is required when constructing {cls_name} from a bare array or StructField"
            )
        return NumberType(number_type) if isinstance(number_type, str) else number_type

    @staticmethod
    def _resolve_metadata(
        pa_field: pa.Field,
        unit_override: TimeUnit | str | None,
        nt_override: NumberType | str | None,
    ) -> tuple[TimeUnit, NumberType]:
        """Extract unit and number_type from a ``pa.Field``'s metadata."""
        meta: dict[str, str] = {}
        raw_meta = pa_field.metadata
        if raw_meta:
            if _TIMETOALIGN_KEY in raw_meta:
                blob = raw_meta[_TIMETOALIGN_KEY]
                if isinstance(blob, bytes):
                    blob = blob.decode("utf-8")
                meta = json.loads(blob)
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
            raise ValueError(
                f"Cannot determine unit for field {pa_field.name!r}: no 'unit' in metadata and no override"
            )

        if nt_override is not None:
            resolved_nt = (
                NumberType(nt_override) if isinstance(nt_override, str) else nt_override
            )
        elif "number_type" in meta:
            resolved_nt = NumberType(meta["number_type"])
        else:
            resolved_nt = NumberType.float

        return resolved_unit, resolved_nt


# ---------------------------------------------------------------------------
# CoordinateField
# ---------------------------------------------------------------------------


class CoordinateField(NumberField):
    """Semantic field for coordinate columns.

    Wraps a ``StructField`` containing the coordinate struct
    ``{value: float64, numerator: int64, denominator: int64}``
    and adds semantic identity: unit, domain, number_type.

    Satisfies ``CoordinateLike[StructField]``.

    Args:
        raw: The inner ``StructField`` holding coordinate struct data.
        unit: The time unit for this coordinate column.
        number_type: The numeric representation used for scalar access.

    Examples:
        >>> import pyarrow as pa
        >>> from timetoalign.core.enums import TimeUnit, NumberType
        >>> from timetoalign.fields.coordinate import CoordinateField
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

    @property
    def semantic_type(self) -> str:
        return "Coordinate"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "CoordinateField",
            "unit": self._unit.value,
            "domain": self.domain.value,
            "number_type": self._number_type.name,
        }

    def __getitem__(self, i: int) -> Coordinate | None:
        """Return the *i*-th coordinate as a ``Coordinate`` scalar."""
        raw_dict = self._raw[i]
        if raw_dict is None:
            return None
        value = struct_to_coordinate(raw_dict, self._number_type)
        return Coordinate(value, self._unit)

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
        name: str = "coordinate",
    ) -> CoordinateField:
        """Construct a ``CoordinateField`` from various source types."""
        if isinstance(source, tuple):
            data, pa_field = source
            resolved_unit, resolved_nt = cls._resolve_metadata(
                pa_field, unit, number_type
            )
            struct_field = StructField(data, pa_field)
            return cls(struct_field, resolved_unit, resolved_nt)

        if isinstance(source, pa.Field):
            resolved_unit, resolved_nt = cls._resolve_metadata(
                source, unit, number_type
            )
            struct_field = StructField(None, source)
            return cls(struct_field, resolved_unit, resolved_nt)

        if isinstance(source, StructField):
            resolved_unit = cls._require_unit(unit, "CoordinateField")
            resolved_nt = cls._require_number_type(number_type, "CoordinateField")
            return cls(source, resolved_unit, resolved_nt)

        if isinstance(source, (pa.Array, pa.ChunkedArray)):
            resolved_unit = cls._require_unit(unit, "CoordinateField")
            resolved_nt = cls._require_number_type(number_type, "CoordinateField")
            pa_field = pa.field(name, source.type)
            struct_field = StructField(source, pa_field)
            return cls(struct_field, resolved_unit, resolved_nt)

        raise TypeError(
            f"Unsupported source type for CoordinateField.from_field: {type(source).__name__}"
        )

    @classmethod
    def from_table(
        cls,
        table: pa.Table,
        column: str | None = None,
        *,
        unit: TimeUnit | str | None = None,
        number_type: NumberType | str | None = None,
    ) -> CoordinateField:
        """Construct a ``CoordinateField`` from a ``pa.Table`` column."""
        if column is None:
            candidates = [
                f.name
                for f in table.schema
                if pa.types.is_struct(f.type)
                and f.metadata
                and _TIMETOALIGN_KEY in f.metadata
            ]
            if len(candidates) == 1:
                column = candidates[0]
            elif len(candidates) == 0:
                raise ValueError(
                    "No struct column with b'timetoalign' metadata found in table; "
                    "pass column= explicitly"
                )
            else:
                raise ValueError(
                    f"Multiple candidate columns found: {candidates}; "
                    "pass column= explicitly"
                )
        pa_field = table.schema.field(column)
        data = table.column(column)
        return cls.from_field((data, pa_field), unit=unit, number_type=number_type)

    def with_unit(self, unit: TimeUnit) -> CoordinateField:
        """Return a new ``CoordinateField`` with a different unit.

        This does **not** convert values -- it only changes the metadata
        label.  Value conversion requires a C-Map.
        """
        return CoordinateField(self._raw, unit, self._number_type)

    def __repr__(self) -> str:
        length = len(self) if not self.is_empty else 0
        return (
            f"CoordinateField(name={self.name!r}, unit={self._unit}, "
            f"number_type={self._number_type}, len={length})"
        )


# ---------------------------------------------------------------------------
# DurationField
# ---------------------------------------------------------------------------


class DurationField(NumberField):
    """Semantic field for duration columns.

    Uses the same coordinate struct ``{value, numerator, denominator}``
    as ``CoordinateField``, replacing bare ``duration_float`` columns.

    Args:
        raw: The inner ``StructField`` holding duration struct data.
        unit: The time unit for this duration column.
        number_type: The numeric representation used for scalar access.

    Examples:
        >>> import pyarrow as pa
        >>> from timetoalign.core.enums import TimeUnit, NumberType
        >>> from timetoalign.fields.coordinate import DurationField
        >>> arr = pa.array(
        ...     [{"value": 2.0, "numerator": 2, "denominator": 1}],
        ...     type=pa.struct([
        ...         pa.field("value", pa.float64()),
        ...         pa.field("numerator", pa.int64()),
        ...         pa.field("denominator", pa.int64()),
        ...     ]),
        ... )
        >>> df = DurationField.from_field(arr, unit=TimeUnit.quarters, number_type=NumberType.float)
        >>> df[0]
        Coordinate(2.0, quarters)
    """

    @property
    def semantic_type(self) -> str:
        return "Duration"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "DurationField",
            "unit": self._unit.value,
            "domain": self.domain.value,
            "number_type": self._number_type.name,
        }

    def __getitem__(self, i: int) -> Coordinate | None:
        """Return the *i*-th duration as a ``Coordinate`` scalar."""
        raw_dict = self._raw[i]
        if raw_dict is None:
            return None
        value = struct_to_coordinate(raw_dict, self._number_type)
        return Coordinate(value, self._unit)

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
        name: str = "duration",
    ) -> DurationField:
        """Construct a ``DurationField`` from various source types."""
        if isinstance(source, tuple):
            data, pa_field = source
            resolved_unit, resolved_nt = cls._resolve_metadata(
                pa_field, unit, number_type
            )
            struct_field = StructField(data, pa_field)
            return cls(struct_field, resolved_unit, resolved_nt)

        if isinstance(source, pa.Field):
            resolved_unit, resolved_nt = cls._resolve_metadata(
                source, unit, number_type
            )
            struct_field = StructField(None, source)
            return cls(struct_field, resolved_unit, resolved_nt)

        if isinstance(source, StructField):
            resolved_unit = cls._require_unit(unit, "DurationField")
            resolved_nt = cls._require_number_type(number_type, "DurationField")
            return cls(source, resolved_unit, resolved_nt)

        if isinstance(source, (pa.Array, pa.ChunkedArray)):
            resolved_unit = cls._require_unit(unit, "DurationField")
            resolved_nt = cls._require_number_type(number_type, "DurationField")
            pa_field = pa.field(name, source.type)
            struct_field = StructField(source, pa_field)
            return cls(struct_field, resolved_unit, resolved_nt)

        raise TypeError(
            f"Unsupported source type for DurationField.from_field: {type(source).__name__}"
        )

    def __repr__(self) -> str:
        length = len(self) if not self.is_empty else 0
        return (
            f"DurationField(name={self.name!r}, unit={self._unit}, "
            f"number_type={self._number_type}, len={length})"
        )
