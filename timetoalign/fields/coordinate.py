"""CoordinateField -- semantic columnar wrapper for coordinate data.

``CoordinateField(SemanticField[StructField])`` is the first concrete
``SemanticField`` subclass.  It wraps a ``StructField`` whose PyArrow
struct layout is ``{value: float64, numerator: int64, denominator: int64}``
(the canonical coordinate storage defined by ``loader.schema``).

The class satisfies the ``CoordinateLike[StructField]`` protocol,
providing ``unit``, ``domain``, and ``number_type`` properties alongside
element access that returns ``Coordinate`` scalars.

Note:
    This is ``fields.CoordinateField`` (a DataField subclass).  It
    coexists with ``loader.schema.CoordinateField`` (a loader-config
    descriptor) -- the two classes serve different purposes.
"""

from __future__ import annotations

import json

import pyarrow as pa

from ..core.enums import Domain, NumberType, TimeUnit
from ..core.types import Coordinate
from ..loader.schema import struct_to_coordinate
from .base import SemanticField, StructField

_TIMETOALIGN_KEY = b"timetoalign"


class CoordinateField(SemanticField[StructField]):
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

    def __init__(
        self, raw: StructField, unit: TimeUnit, number_type: NumberType
    ) -> None:
        super().__init__(raw)
        self._unit = TimeUnit(unit) if isinstance(unit, str) else unit
        self._number_type = number_type

    # -- CoordinateLike properties -------------------------------------------

    @property
    def unit(self) -> TimeUnit:
        """The time unit of this coordinate column."""
        return self._unit

    @property
    def domain(self) -> Domain:
        """The temporal domain, derived from the unit."""
        return self._unit.domain

    @property
    def number_type(self) -> NumberType:
        """The numeric representation used for scalar access."""
        return self._number_type

    # -- SemanticTypeLike properties -----------------------------------------

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "Coordinate"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract.

        Returns:
            Dict with ``field_type``, ``unit``, ``domain``, and
            ``number_type`` keys.
        """
        return {
            "field_type": "CoordinateField",
            "unit": self._unit.value,
            "domain": self.domain.value,
            "number_type": self._number_type.name,
        }

    # -- element access ------------------------------------------------------

    def __getitem__(self, i: int) -> Coordinate | None:
        """Return the *i*-th coordinate as a ``Coordinate`` scalar.

        Retrieves the raw struct dict from the underlying ``StructField``,
        converts the numeric value via ``struct_to_coordinate()``, and
        wraps it in a ``Coordinate``.

        Args:
            i: Zero-based index.

        Returns:
            A ``Coordinate`` instance, or ``None`` for null entries.

        Raises:
            TypeError: If the field is schema-only (no data).
            IndexError: If *i* is out of range.
        """
        raw_dict = self._raw[i]
        if raw_dict is None:
            return None
        value = struct_to_coordinate(raw_dict, self._number_type)
        return Coordinate(value, self._unit)

    # -- construction --------------------------------------------------------

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
        """Construct a ``CoordinateField`` from various source types.

        Accepted source forms:

        1. ``pa.Array`` (struct array) with keyword ``unit`` and ``number_type``.
        2. ``StructField`` with keyword ``unit`` and ``number_type``.
        3. ``pa.Field`` (schema-only, no data) -- reads ``unit`` and
           ``number_type`` from the field's ``b"timetoalign"`` metadata.
        4. ``tuple[pa.Array | None, pa.Field]`` -- common pattern from
           PyArrow table column extraction.

        Args:
            source: The data source (see above).
            unit: Time unit.  Required for forms 1 and 2; optional for
                forms 3 and 4 (overrides metadata if provided).
            number_type: Numeric type.  Required for forms 1 and 2;
                optional for forms 3 and 4.
            name: Column name used when *source* is a bare ``pa.Array``
                (ignored otherwise).

        Returns:
            A new ``CoordinateField``.

        Raises:
            TypeError: If the source type is not recognised.
            ValueError: If ``unit`` or ``number_type`` cannot be determined.
        """
        # -- form 4: tuple -------------------------------------------------------
        if isinstance(source, tuple):
            data, pa_field = source
            resolved_unit, resolved_nt = cls._resolve_metadata(
                pa_field, unit, number_type
            )
            struct_field = StructField(data, pa_field)
            return cls(struct_field, resolved_unit, resolved_nt)

        # -- form 3: pa.Field (schema-only) --------------------------------------
        if isinstance(source, pa.Field):
            resolved_unit, resolved_nt = cls._resolve_metadata(
                source, unit, number_type
            )
            struct_field = StructField(None, source)
            return cls(struct_field, resolved_unit, resolved_nt)

        # -- form 2: StructField -------------------------------------------------
        if isinstance(source, StructField):
            resolved_unit = cls._require_unit(unit)
            resolved_nt = cls._require_number_type(number_type)
            return cls(source, resolved_unit, resolved_nt)

        # -- form 1: pa.Array / pa.ChunkedArray ----------------------------------
        if isinstance(source, (pa.Array, pa.ChunkedArray)):
            resolved_unit = cls._require_unit(unit)
            resolved_nt = cls._require_number_type(number_type)
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
        """Construct a ``CoordinateField`` from a ``pa.Table`` column.

        This is the recommended way to reconstruct a ``CoordinateField``
        after a Parquet round-trip.  It extracts the column data and
        schema field in one step.

        Args:
            table: The PyArrow table containing the coordinate column.
            column: Column name.  If ``None``, auto-detects the column
                by looking for a struct column whose schema field carries
                ``b"timetoalign"`` metadata.
            unit: Optional unit override (otherwise read from metadata).
            number_type: Optional number_type override.

        Returns:
            A new ``CoordinateField``.

        Raises:
            ValueError: If *column* is ``None`` and the table has zero
                or more than one candidate column.
            KeyError: If the named *column* does not exist.

        Examples:
            >>> loaded_cf = CoordinateField.from_table(loaded_table)
            >>> loaded_cf = CoordinateField.from_table(loaded_table, "onset")
        """
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

    # -- serialisation helpers -----------------------------------------------

    def to_field(self) -> pa.Field:
        """Return a ``pa.Field`` with ``b"timetoalign"`` metadata injected.

        The metadata is a JSON-encoded dict stored under the
        ``b"timetoalign"`` key, containing ``field_type``, ``unit``,
        ``domain``, and ``number_type``.

        Returns:
            A ``pa.Field`` with enriched metadata.
        """
        meta_blob = json.dumps(self.metadata_dict()).encode("utf-8")
        existing = self._field.metadata or {}
        merged = {**existing, _TIMETOALIGN_KEY: meta_blob}
        return self._field.with_metadata(merged)

    # -- copy-on-write -------------------------------------------------------

    def with_unit(self, unit: TimeUnit) -> CoordinateField:
        """Return a new ``CoordinateField`` with a different unit.

        This does **not** convert values -- it only changes the metadata
        label.  Value conversion requires a C-Map.

        Args:
            unit: The new time unit.

        Returns:
            A new ``CoordinateField`` with the updated unit.
        """
        return CoordinateField(self._raw, unit, self._number_type)

    # -- private helpers -----------------------------------------------------

    @staticmethod
    def _require_unit(unit: TimeUnit | str | None) -> TimeUnit:
        """Validate and coerce the *unit* argument.

        Args:
            unit: The unit value or ``None``.

        Returns:
            A ``TimeUnit`` instance.

        Raises:
            ValueError: If *unit* is ``None``.
        """
        if unit is None:
            raise ValueError(
                "'unit' is required when constructing CoordinateField from a bare array or StructField"
            )
        return TimeUnit(unit) if isinstance(unit, str) else unit

    @staticmethod
    def _require_number_type(number_type: NumberType | str | None) -> NumberType:
        """Validate and coerce the *number_type* argument.

        Args:
            number_type: The number-type value or ``None``.

        Returns:
            A ``NumberType`` instance.

        Raises:
            ValueError: If *number_type* is ``None``.
        """
        if number_type is None:
            raise ValueError(
                "'number_type' is required when constructing CoordinateField from a bare array or StructField"
            )
        return NumberType(number_type) if isinstance(number_type, str) else number_type

    @staticmethod
    def _resolve_metadata(
        pa_field: pa.Field,
        unit_override: TimeUnit | str | None,
        nt_override: NumberType | str | None,
    ) -> tuple[TimeUnit, NumberType]:
        """Extract unit and number_type from a ``pa.Field``'s metadata.

        Keyword overrides take precedence over stored metadata.

        Args:
            pa_field: The PyArrow field descriptor.
            unit_override: Explicit unit (takes precedence).
            nt_override: Explicit number_type (takes precedence).

        Returns:
            A ``(TimeUnit, NumberType)`` tuple.

        Raises:
            ValueError: If a value cannot be determined from either the
                override or the field metadata.
        """
        meta: dict[str, str] = {}
        raw_meta = pa_field.metadata
        if raw_meta:
            # Check for the b"timetoalign" JSON blob first
            if _TIMETOALIGN_KEY in raw_meta:
                blob = raw_meta[_TIMETOALIGN_KEY]
                if isinstance(blob, bytes):
                    blob = blob.decode("utf-8")
                meta = json.loads(blob)
            else:
                # Fall back to flat metadata (e.g. from make_coordinate_field)
                meta = {
                    (k.decode("utf-8") if isinstance(k, bytes) else k): (
                        v.decode("utf-8") if isinstance(v, bytes) else v
                    )
                    for k, v in raw_meta.items()
                }

        # Resolve unit
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

        # Resolve number_type
        if nt_override is not None:
            resolved_nt = (
                NumberType(nt_override) if isinstance(nt_override, str) else nt_override
            )
        elif "number_type" in meta:
            resolved_nt = NumberType(meta["number_type"])
        else:
            # Default to float when number_type is absent (common for legacy fields)
            resolved_nt = NumberType.float

        return resolved_unit, resolved_nt

    def __repr__(self) -> str:
        length = len(self) if not self.is_empty else 0
        return (
            f"CoordinateField(name={self.name!r}, unit={self._unit}, "
            f"number_type={self._number_type}, len={length})"
        )
