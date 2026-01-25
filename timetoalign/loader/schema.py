"""Schema definitions for TimeToAlign! EventStore.

This module defines PyArrow schemas for event storage, including:
- Coordinate struct types (with float + optional Fraction representation)
- Base event schema columns
- Schema construction utilities

The coordinate storage strategy preserves original precision (Fraction numerator/denominator)
while providing a float64 representation for fast queries. Unit metadata is stored at
the column level, not per-row.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

import pyarrow as pa

from timetoalign.core import NumberType, TimeUnit

# region Coordinate Schema


def make_coordinate_type(unit: TimeUnit) -> pa.StructType:
    """Create a coordinate struct type.

    The struct contains:
    - value: float64 representation (always present, for queries)
    - numerator: int64 (for Fraction, nullable)
    - denominator: int64 (for Fraction, nullable)

    Note: Unit metadata is stored at the Field level, not the StructType level.
    Use make_coordinate_field() to create a field with unit metadata.

    Args:
        unit: The time unit (unused here, kept for API consistency).

    Returns:
        A PyArrow struct type.
    """
    return pa.struct(
        [
            pa.field("value", pa.float64(), nullable=False),
            pa.field("numerator", pa.int64(), nullable=True),
            pa.field("denominator", pa.int64(), nullable=True),
        ]
    )


# Fraction struct for temporal columns (quarterbeats, duration, etc.)
FRACTION_TYPE = pa.struct(
    [
        pa.field("num", pa.int64(), nullable=False),
        pa.field("den", pa.int64(), nullable=False),
    ]
)


def make_fraction_field(
    name: str,
    nullable: bool = True,
    metadata: dict[str, str] | None = None,
) -> pa.Field:
    """Create a Fraction field with optional metadata.

    Args:
        name: The field name.
        nullable: Whether the field is nullable.
        metadata: Additional metadata (e.g., unit, number_type).

    Returns:
        A PyArrow field with FRACTION_TYPE.
    """
    meta = {"number_type": "fraction"}
    if metadata:
        meta.update(metadata)
    return pa.field(name, FRACTION_TYPE, nullable=nullable, metadata=meta)


def fraction_to_struct(frac: Fraction | int | float) -> dict[str, int]:
    """Convert a Fraction to struct dict for PyArrow.

    Args:
        frac: A Fraction, int, or float.

    Returns:
        Dict with 'num' and 'den' keys.
    """
    if isinstance(frac, Fraction):
        return {"num": frac.numerator, "den": frac.denominator}
    elif isinstance(frac, int):
        return {"num": frac, "den": 1}
    else:
        # Convert float to Fraction with reasonable denominator
        f = Fraction(frac).limit_denominator(10000)
        return {"num": f.numerator, "den": f.denominator}


def struct_to_fraction(struct: dict[str, int]) -> Fraction:
    """Convert a struct dict back to a Fraction.

    Args:
        struct: Dict with 'num' and 'den' keys.

    Returns:
        A Fraction.
    """
    return Fraction(struct["num"], struct["den"])


def make_coordinate_field(name: str, unit: TimeUnit, nullable: bool = True) -> pa.Field:
    """Create a coordinate field with unit in metadata.

    Args:
        name: The field name.
        unit: The time unit to store in metadata.
        nullable: Whether the field is nullable.

    Returns:
        A PyArrow field with struct type and unit metadata.
    """
    coord_type = make_coordinate_type(unit)
    return pa.field(name, coord_type, nullable=nullable, metadata={"unit": str(unit)})


def coordinate_to_struct(
    coord: int | float | Fraction,
) -> dict[str, Any]:
    """Convert a coordinate value to struct dict for PyArrow.

    Args:
        coord: The coordinate value (int, float, or Fraction).

    Returns:
        Dict with 'value', 'numerator', 'denominator' keys.
    """
    if isinstance(coord, Fraction):
        return {
            "value": float(coord),
            "numerator": coord.numerator,
            "denominator": coord.denominator,
        }
    elif isinstance(coord, int):
        return {
            "value": float(coord),
            "numerator": coord,
            "denominator": 1,
        }
    else:
        # float - no exact Fraction representation
        return {
            "value": float(coord),
            "numerator": None,
            "denominator": None,
        }


def struct_to_coordinate(
    struct: dict[str, Any],
    number_type: NumberType,
) -> int | float | Fraction:
    """Convert a struct dict back to a coordinate value.

    Args:
        struct: Dict with 'value', 'numerator', 'denominator' keys.
        number_type: The desired number type for the result.

    Returns:
        The coordinate value in the requested number type.
    """
    if number_type == NumberType.fraction:
        if struct["numerator"] is not None and struct["denominator"] is not None:
            return Fraction(struct["numerator"], struct["denominator"])
        # Fallback to float if no Fraction data
        return Fraction(struct["value"]).limit_denominator()
    elif number_type == NumberType.int:
        return int(struct["value"])
    else:
        return struct["value"]


# endregion


# region Base Event Schema

# Temporal type values (not an enum in PyArrow, just string literals)
TEMPORAL_TYPE_INSTANT = "instant"
TEMPORAL_TYPE_INTERVAL = "interval"


def make_base_schema(unit: TimeUnit) -> pa.Schema:
    """Create the base event schema with coordinate columns.

    The base schema includes columns that are always present:
    - id: unique identifier (required)
    - name: human-readable label (optional)
    - temporal_type: "instant" or "interval"
    - event_type: class name (e.g., "Note", "Beat")
    - instant: coordinate for InstantEvents (nullable)
    - start: start coordinate for IntervalEvents (nullable)
    - end: end coordinate for IntervalEvents (nullable)
    - duration: computed duration for IntervalEvents (nullable)

    Args:
        unit: The time unit for coordinate columns.

    Returns:
        A PyArrow schema with base event columns.
    """
    return pa.schema(
        [
            pa.field("id", pa.string(), nullable=False),
            pa.field("name", pa.string(), nullable=True),
            pa.field("temporal_type", pa.string(), nullable=False),
            pa.field("event_type", pa.string(), nullable=False),
            make_coordinate_field("instant", unit, nullable=True),
            make_coordinate_field("start", unit, nullable=True),
            make_coordinate_field("end", unit, nullable=True),
            make_coordinate_field("duration", unit, nullable=True),
        ]
    )


def get_base_column_names() -> list[str]:
    """Return the list of base column names.

    Returns:
        List of column names in the base schema.
    """
    return [
        "id",
        "name",
        "temporal_type",
        "event_type",
        "instant",
        "start",
        "end",
        "duration",
    ]


def extend_schema(base: pa.Schema, extra_fields: list[pa.Field]) -> pa.Schema:
    """Extend a base schema with additional fields.

    Args:
        base: The base PyArrow schema.
        extra_fields: Additional fields to append.

    Returns:
        A new schema with the extra fields appended.
    """
    fields = list(base)
    fields.extend(extra_fields)
    return pa.schema(fields, metadata=base.metadata)


def get_unit_from_schema(schema: pa.Schema) -> TimeUnit | None:
    """Extract the time unit from a schema's coordinate column metadata.

    Args:
        schema: A PyArrow schema with coordinate columns.

    Returns:
        The TimeUnit if found, None otherwise.
    """
    # Check the 'instant' field first, then 'start'
    for field_name in ("instant", "start"):
        try:
            field = schema.field(field_name)
            if field.metadata and b"unit" in field.metadata:
                return TimeUnit(field.metadata[b"unit"].decode())
        except KeyError:
            continue
    return None


# endregion


# region Schema Metadata


def make_table_metadata(
    unit: TimeUnit,
    number_type: NumberType,
    sources: list[dict[str, Any]] | None = None,
    loader_class: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[bytes, bytes]:
    """Create metadata dict for a PyArrow table schema.

    The metadata is JSON-encoded for deterministic serialization.

    Args:
        unit: The time unit for coordinates.
        number_type: The number type (int64, float64, fraction).
        sources: List of source file metadata dicts.
        loader_class: Name of the Loader subclass.
        extra: Additional metadata to include.

    Returns:
        A dict suitable for PyArrow schema metadata.
    """
    import json

    metadata = {
        "timetoalign_version": "0.1.0",
        "unit": str(unit),
        "number_type": str(number_type),
        "sources": sources or [],
        "loader_class": loader_class,
    }
    if extra:
        metadata.update(extra)

    return {b"timetoalign": json.dumps(metadata, sort_keys=True).encode()}


def parse_table_metadata(schema: pa.Schema) -> dict[str, Any]:
    """Parse TimeToAlign! metadata from a PyArrow schema.

    Args:
        schema: A PyArrow schema with timetoalign metadata.

    Returns:
        The parsed metadata dict, or empty dict if not found.
    """
    import json

    if schema.metadata and b"timetoalign" in schema.metadata:
        return json.loads(schema.metadata[b"timetoalign"].decode())
    return {}


# endregion
