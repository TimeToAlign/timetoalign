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
from typing import Any, Callable

import pyarrow as pa
import pyarrow.compute as pc

from timetoalign.core import NumberType, TimeUnit

# region Coordinate Schema


def make_coordinate_type(unit: TimeUnit) -> pa.StructType:
    """Create a coordinate struct type.

    The struct contains:
    - value: float64 representation (nullable when struct is null)
    - numerator: int64 (for Fraction, nullable)
    - denominator: int64 (for Fraction, nullable)

    Note: Unit metadata is stored at the Field level, not the StructType level.
    Use make_coordinate_field() to create a field with unit metadata.

    Note: All fields are nullable to allow for null struct values (e.g., missing
    end coordinates for instant events).

    Args:
        unit: The time unit (unused here, kept for API consistency).

    Returns:
        A PyArrow struct type.
    """
    return pa.struct(
        [
            pa.field("value", pa.float64(), nullable=True),
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
    coord: int | float | Fraction | dict[str, Any],
) -> dict[str, Any]:
    """Convert a coordinate value to struct dict for PyArrow.

    Args:
        coord: The coordinate value (int, float, Fraction, or already-converted dict).

    Returns:
        Dict with 'value', 'numerator', 'denominator' keys.
    """
    # If already a struct dict, return as-is (idempotent)
    if isinstance(coord, dict):
        if "value" in coord:
            return coord
        raise ValueError(f"Invalid coordinate dict structure: {coord}")
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
    # Check the 'start' field
    try:
        field = schema.field("start")
        if field.metadata and b"unit" in field.metadata:
            return TimeUnit(field.metadata[b"unit"].decode())
    except KeyError:
        pass
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


# region LoaderSchema


# Type mappings for simple type specifications
_TYPE_MAP: dict[str | type, pa.DataType] = {
    "int": pa.int64(),
    "int64": pa.int64(),
    "int32": pa.int32(),
    "float": pa.float64(),
    "float64": pa.float64(),
    "float32": pa.float32(),
    "str": pa.string(),
    "string": pa.string(),
    "bool": pa.bool_(),
    "boolean": pa.bool_(),
    int: pa.int64(),
    float: pa.float64(),
    str: pa.string(),
    bool: pa.bool_(),
}


# region Field and ComputedField


class Field:
    """Reference to a struct field for coordinate access.

    Field provides a way to specify nested struct column access in TabularLoader
    configurations. It supports multiple input formats:

    - Tuple: ("rect_coords", "x")
    - Field object: Field("rect_coords", "x")
    - PyArrow expression (for advanced use)

    The Field is resolved during column extraction using PyArrow's struct_field
    compute function for vectorized access.

    Attributes:
        column: The parent column name containing the struct.
        fields: Nested field path within the struct.

    Examples:
        >>> # Access x field from rect_coords struct
        >>> start = Field("rect_coords", "x")

        >>> # Deeply nested access
        >>> value = Field("metadata", "timing", "offset")

        >>> # In loader configuration
        >>> class MyLoader(TsvLoader):
        ...     extra_columns = [
        ...         ConvertedField("rect_coords", dict, source="rect_coords_json"),
        ...     ]
        ...     start_column = Field("rect_coords", "x")
    """

    def __init__(self, column: str, *fields: str) -> None:
        """Initialize Field.

        Args:
            column: The parent column name.
            *fields: One or more nested field names to access.

        Raises:
            ValueError: If no field names are provided.
        """
        if not fields:
            raise ValueError("Field requires at least one field name after the column")
        self.column = column
        self.fields = fields

    def resolve(self, table: pa.Table) -> pa.Array:
        """Resolve the field reference to a PyArrow array.

        Uses PyArrow compute functions for vectorized struct field access.
        If the source column is a string (not already a struct), automatically
        parses it as JSON to extract nested fields.

        Args:
            table: The PyArrow table containing the struct column.

        Returns:
            The extracted field as a PyArrow array.

        Raises:
            KeyError: If the column doesn't exist.
            ValueError: If the field path is invalid or JSON parsing fails.
        """
        if self.column not in table.column_names:
            raise KeyError(f"Column '{self.column}' not found in table")

        array = table.column(self.column).combine_chunks()

        # Auto-detect JSON string columns and parse them
        if pa.types.is_string(array.type) or pa.types.is_large_string(array.type):
            # Column is a string - assume it's JSON and parse it
            array = parse_json_to_struct(array.to_pylist())

        # Navigate through nested fields
        for field_name in self.fields:
            if not pa.types.is_struct(array.type):
                raise ValueError(
                    f"Cannot access field '{field_name}' on non-struct type {array.type}. "
                    f"Column '{self.column}' may not contain valid JSON."
                )
            array = pc.struct_field(array, field_name)

        return array

    def __repr__(self) -> str:
        fields_str = ", ".join(repr(f) for f in self.fields)
        return f"Field({self.column!r}, {fields_str})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Field):
            return NotImplemented
        return self.column == other.column and self.fields == other.fields

    def __hash__(self) -> int:
        return hash((self.column, self.fields))


class ComputedField:
    """Computed column derived from an expression or function.

    ComputedField allows defining derived columns using either:
    - A formula string (e.g., "rect_coords.x + rect_coords.width")
    - A callable that operates on PyArrow arrays

    The computation is fully vectorized using PyArrow compute functions.

    Attributes:
        name: The output column name.
        formula: Optional formula string for simple expressions.
        expr: Optional callable for complex computations.

    Formula Syntax:
        - Struct field access: "column.field" or "column.nested.field"
        - Arithmetic: +, -, *, /
        - Column references: plain column names

    Examples:
        >>> # Simple addition using formula
        >>> end = ComputedField("end", formula="rect_coords.x + rect_coords.width")

        >>> # Using a callable for complex logic
        >>> def compute_end(table):
        ...     x = pc.struct_field(table["rect_coords"], "x")
        ...     w = pc.struct_field(table["rect_coords"], "width")
        ...     return pc.add(x, w)
        >>> end = ComputedField("end", expr=compute_end)

        >>> # In loader configuration
        >>> class MyLoader(TsvLoader):
        ...     end_column = ComputedField("end", formula="rect_coords.x + rect_coords.width")
    """

    def __init__(
        self,
        name: str,
        formula: str | None = None,
        expr: Callable[[pa.Table], pa.Array] | None = None,
    ) -> None:
        """Initialize ComputedField.

        Args:
            name: The output column name.
            formula: A formula string (e.g., "a.x + a.width").
            expr: A callable that takes a PyArrow Table and returns an Array.

        Raises:
            ValueError: If neither formula nor expr is provided.
        """
        if formula is None and expr is None:
            raise ValueError("ComputedField requires either 'formula' or 'expr'")
        if formula is not None and expr is not None:
            raise ValueError("ComputedField cannot have both 'formula' and 'expr'")

        self.name = name
        self.formula = formula
        self.expr = expr

    def compute(self, table: pa.Table) -> pa.Array:
        """Compute the field value from the table.

        Args:
            table: The PyArrow table with source columns.

        Returns:
            The computed PyArrow array.
        """
        if self.expr is not None:
            return self.expr(table)
        else:
            return self._evaluate_formula(table)

    def _evaluate_formula(self, table: pa.Table) -> pa.Array:
        """Evaluate the formula string against the table.

        Supports simple arithmetic expressions with struct field access.
        Uses a basic expression parser for safety.

        Args:
            table: The PyArrow table.

        Returns:
            The computed array.
        """
        import re

        formula = self.formula
        assert formula is not None

        # Tokenize the formula
        # Matches: column.field.subfield, column_name, numbers, operators
        token_pattern = r"(\w+(?:\.\w+)*)|([+\-*/])|(\d+(?:\.\d+)?)"
        tokens = re.findall(token_pattern, formula)

        # Parse into operands and operators
        operands: list[pa.Array | float] = []
        operators: list[str] = []

        for ref, op, num in tokens:
            if ref:
                # Column or struct field reference
                operands.append(self._resolve_reference(table, ref))
            elif op:
                operators.append(op)
            elif num:
                operands.append(float(num))

        if not operands:
            raise ValueError(f"Invalid formula: {formula}")

        # Evaluate left-to-right (no precedence for simplicity)
        # For proper math precedence, would need a full expression parser
        result = operands[0]
        if isinstance(result, (int, float)):
            result = pa.scalar(result)

        for i, op in enumerate(operators):
            right = operands[i + 1]
            if isinstance(right, (int, float)):
                right = pa.scalar(right)

            if op == "+":
                result = pc.add(result, right)
            elif op == "-":
                result = pc.subtract(result, right)
            elif op == "*":
                result = pc.multiply(result, right)
            elif op == "/":
                result = pc.divide(result, right)
            else:
                raise ValueError(f"Unknown operator: {op}")

        return result

    def _resolve_reference(self, table: pa.Table, ref: str) -> pa.Array:
        """Resolve a column or struct field reference.

        Args:
            table: The PyArrow table.
            ref: Reference string like "column" or "column.field.subfield".

        Returns:
            The resolved PyArrow array.
        """
        parts = ref.split(".")

        if parts[0] not in table.column_names:
            raise KeyError(f"Column '{parts[0]}' not found in table")

        array = table.column(parts[0]).combine_chunks()

        # Auto-detect JSON string columns and parse them (same as Field.resolve)
        if len(parts) > 1 and (
            pa.types.is_string(array.type) or pa.types.is_large_string(array.type)
        ):
            # Column is a string but we need struct access - assume it's JSON
            array = parse_json_to_struct(array.to_pylist())

        # Navigate struct fields
        for field_name in parts[1:]:
            if not pa.types.is_struct(array.type):
                raise ValueError(
                    f"Cannot access field '{field_name}' on non-struct type {array.type}. "
                    f"Column '{parts[0]}' may not contain valid JSON."
                )
            array = pc.struct_field(array, field_name)

        return array

    def __repr__(self) -> str:
        if self.formula:
            return f"ComputedField({self.name!r}, formula={self.formula!r})"
        else:
            return f"ComputedField({self.name!r}, expr=...)"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ComputedField):
            return NotImplemented
        return self.name == other.name and self.formula == other.formula

    def __hash__(self) -> int:
        return hash((self.name, self.formula))


# endregion


class ConvertedField:
    """Specification for a column requiring type conversion or transformation.

    ConvertedField defines how a source column maps to an output column with
    explicit type conversion, renaming, or custom transformation. Use this when
    you need to:
    - Convert JSON strings to struct types for nested field access
    - Apply custom converter functions
    - Rename columns during loading
    - Specify explicit PyArrow types

    For simple extra columns without conversion, use a plain string or dict
    in the loader's extra_columns attribute instead.

    Attributes:
        name: The column name in the output schema.
        dtype: PyArrow data type for the column.
        source: Source column name (defaults to name if not specified).
        converter: Optional function to transform values during loading.
        nullable: Whether the column allows nulls.
        is_struct: Whether this field is a struct type (JSON parsing).
        struct_schema: The struct schema dict if is_struct is True.

    Examples:
        >>> # Parse JSON column into struct for nested access
        >>> ConvertedField("rect_coords", dict, source="rect_coords_json")

        >>> # Struct field with explicit schema
        >>> ConvertedField("coords", {"x": int, "y": int, "width": int, "height": int})

        >>> # Field with converter function
        >>> ConvertedField("name", str, converter=lambda x: x.strip().upper())

        >>> # Field with different source column name and type
        >>> ConvertedField("pitch", int, source="midi_note")
    """

    def __init__(
        self,
        name: str,
        dtype: str | type | pa.DataType | dict[str, type] | None = None,
        *,
        source: str | None = None,
        converter: Any | None = None,
        nullable: bool = True,
    ) -> None:
        """Initialize ConvertedField.

        Args:
            name: Column name in output schema.
            dtype: Data type. Can be:
                - None: Type inferred from source data.
                - str like "int", "float", "str", "struct": Mapped to PyArrow type.
                - type like int, float, str, dict: Python type.
                - pa.DataType: PyArrow type directly.
                - dict[str, type]: Struct schema like {"x": int, "y": float}.
            source: Source column name. Defaults to name.
            converter: Function to transform values: converter(array) -> array.
            nullable: Whether to allow null values.
        """
        self.name = name
        self.source = source or name
        self.converter = converter
        self.nullable = nullable
        self.is_struct = False
        self.struct_schema: dict[str, type] | None = None

        # Resolve dtype
        if dtype is None:
            self._dtype: pa.DataType | None = None  # Infer from data
        elif isinstance(dtype, pa.DataType):
            self._dtype = dtype
            self.is_struct = pa.types.is_struct(dtype)
        elif isinstance(dtype, dict):
            # Struct schema definition: {"x": int, "y": float}
            self.is_struct = True
            self.struct_schema = dtype
            self._dtype = self._build_struct_type(dtype)
        elif dtype is dict or dtype == "struct":
            # Generic struct - schema will be inferred from JSON data
            self.is_struct = True
            self._dtype = None  # Will be inferred
        elif dtype in _TYPE_MAP:
            self._dtype = _TYPE_MAP[dtype]
        else:
            raise ValueError(
                f"Unknown dtype '{dtype}'. Use str like 'int', type like int, "
                f"pa.DataType, or dict for struct schema. "
                f"Known types: {list(_TYPE_MAP.keys())}"
            )

    def _build_struct_type(self, schema: dict[str, type]) -> pa.StructType:
        """Build a PyArrow struct type from a dict schema.

        Args:
            schema: Dict mapping field names to Python types.

        Returns:
            PyArrow StructType.
        """
        fields = []
        for field_name, field_type in schema.items():
            if field_type in _TYPE_MAP:
                pa_type = _TYPE_MAP[field_type]
            elif isinstance(field_type, pa.DataType):
                pa_type = field_type
            else:
                raise ValueError(
                    f"Unknown type '{field_type}' for struct field '{field_name}'"
                )
            fields.append(pa.field(field_name, pa_type, nullable=True))
        return pa.struct(fields)

    @property
    def dtype(self) -> pa.DataType | None:
        """The PyArrow data type, or None if to be inferred."""
        return self._dtype

    def to_field(self, inferred_type: pa.DataType | None = None) -> pa.Field:
        """Create a PyArrow Field from this specification.

        Args:
            inferred_type: Type inferred from data, used if dtype is None.

        Returns:
            PyArrow Field.

        Raises:
            ValueError: If dtype is None and no inferred_type provided.
        """
        dtype = self._dtype or inferred_type
        if dtype is None:
            raise ValueError(
                f"Cannot create field '{self.name}': no dtype specified and "
                f"no type could be inferred from data."
            )
        return pa.field(self.name, dtype, nullable=self.nullable)

    def __repr__(self) -> str:
        dtype_str = self._dtype if self._dtype else "infer"
        parts = [f"name={self.name!r}", f"dtype={dtype_str}"]
        if self.source != self.name:
            parts.append(f"source={self.source!r}")
        if self.converter:
            parts.append("converter=...")
        if self.is_struct:
            parts.append("is_struct=True")
        return f"ConvertedField({', '.join(parts)})"


def parse_json_to_struct(
    json_strings: Any,
    struct_schema: dict[str, type] | None = None,
) -> pa.StructArray:
    """Parse JSON strings into a PyArrow StructArray (VECTORIZED).

    Uses vectorized JSON parsing for efficiency. No row iteration.

    Args:
        json_strings: Array-like of JSON strings.
        struct_schema: Optional dict of {field: type} for explicit schema.
            If None, schema is inferred from first valid JSON object.

    Returns:
        PyArrow StructArray with parsed JSON data.

    Raises:
        ValueError: If JSON parsing fails or schema cannot be inferred.
    """
    import json

    import numpy as np

    # Convert to numpy array if needed
    if hasattr(json_strings, "to_numpy"):
        json_arr = json_strings.to_numpy()
    else:
        json_arr = np.asarray(json_strings)

    # n = len(json_arr)

    # Parse all JSON strings (vectorized via list comprehension)
    parsed = []
    for s in json_arr:
        if s is None or (isinstance(s, float) and np.isnan(s)):
            parsed.append(None)
        elif isinstance(s, str):
            try:
                parsed.append(json.loads(s))
            except json.JSONDecodeError:
                parsed.append(None)
        elif isinstance(s, dict):
            # Already parsed
            parsed.append(s)
        else:
            parsed.append(None)

    # Infer schema from first valid object if not provided
    if struct_schema is None:
        for obj in parsed:
            if obj is not None:
                # Infer types from first object
                struct_schema = {}
                for k, v in obj.items():
                    if isinstance(v, bool):
                        struct_schema[k] = bool
                    elif isinstance(v, int):
                        struct_schema[k] = int
                    elif isinstance(v, float):
                        struct_schema[k] = float
                    else:
                        struct_schema[k] = str
                break

    if struct_schema is None:
        raise ValueError("Cannot infer struct schema: no valid JSON objects found")

    # Build field arrays (vectorized extraction)
    field_arrays = {}
    null_mask = np.array([obj is None for obj in parsed], dtype=bool)

    for field_name, field_type in struct_schema.items():
        # Extract field values (vectorized list comprehension)
        values = [obj.get(field_name) if obj is not None else None for obj in parsed]

        # Convert to appropriate type
        if field_type in (int, "int", "int64"):
            # Handle potential None values
            arr = np.array([v if v is not None else 0 for v in values], dtype=np.int64)
            field_null = np.array([v is None for v in values], dtype=bool)
            field_arrays[field_name] = pa.array(arr, mask=field_null, type=pa.int64())
        elif field_type in (float, "float", "float64"):
            arr = np.array(
                [v if v is not None else np.nan for v in values], dtype=np.float64
            )
            field_null = np.array([v is None for v in values], dtype=bool)
            field_arrays[field_name] = pa.array(arr, mask=field_null, type=pa.float64())
        elif field_type in (bool, "bool", "boolean"):
            arr = np.array([v if v is not None else False for v in values], dtype=bool)
            field_null = np.array([v is None for v in values], dtype=bool)
            field_arrays[field_name] = pa.array(arr, mask=field_null, type=pa.bool_())
        else:
            # String type
            arr = [str(v) if v is not None else None for v in values]
            field_arrays[field_name] = pa.array(arr, type=pa.string())

    # Build struct type and array
    struct_fields = []
    arrays = []
    for field_name, field_type in struct_schema.items():
        if field_type in _TYPE_MAP:
            pa_type = _TYPE_MAP[field_type]
        elif isinstance(field_type, pa.DataType):
            pa_type = field_type
        else:
            pa_type = pa.string()
        struct_fields.append(pa.field(field_name, pa_type, nullable=True))
        arrays.append(field_arrays[field_name])

    return pa.StructArray.from_arrays(
        arrays,
        fields=struct_fields,
        mask=pa.array(null_mask),
    )


class TableSchema:
    """Flexible schema configuration for event tables.

    TableSchema wraps PyArrow schema creation with a user-friendly API that
    supports multiple ways of defining extra columns:

    1. **Existing schema**: Pass a pa.Schema to use as-is or extend
    2. **Column names**: Pass strings to auto-infer types from source data
    3. **Type specifications**: Pass {name: type} dict or name=type kwargs
    4. **Field objects**: Pass ConvertedField for full control over conversion

    The schema always includes the base event columns (id, name, temporal_type,
    event_type, start, end, duration). Extra columns are appended.

    Attributes:
        unit: The time unit for coordinate columns.
        base_schema: The base schema with event columns.
        extra_fields: List of ConvertedField specifications.
        infer_remaining: Whether to infer types for columns not explicitly specified.

    Examples:
        >>> # Auto-infer all extra columns from source data
        >>> schema = TableSchema(unit=TimeUnit.quarters, infer_remaining=True)

        >>> # Specify some columns, infer rest
        >>> schema = TableSchema(
        ...     TimeUnit.quarters,
        ...     midi=int, velocity=int,  # kwargs
        ...     infer_remaining=True
        ... )

        >>> # Explicit columns only (no inference)
        >>> schema = TableSchema(
        ...     TimeUnit.quarters,
        ...     "midi", "velocity", "channel",  # Simple column names
        ...     ConvertedField("pitch", int, source="midi_note"),  # Rename + type
        ... )

        >>> # Use existing schema as base
        >>> schema = TableSchema(
        ...     TimeUnit.quarters,
        ...     base=existing_schema,
        ...     extra_column="infer_this_one"
        ... )

        >>> # Specify which columns to include from remaining
        >>> schema = TableSchema(
        ...     TimeUnit.quarters,
        ...     include_columns=["midi", "velocity", "name"],
        ... )
    """

    def __init__(
        self,
        unit: TimeUnit,
        *args: str | ConvertedField | dict[str, Any] | pa.Schema,
        base: pa.Schema | None = None,
        infer_remaining: bool = False,
        include_columns: list[str] | None = None,
        exclude_columns: list[str] | None = None,
        **kwargs: str | type | pa.DataType,
    ) -> None:
        """Initialize LoaderSchema.

        Args:
            unit: Time unit for coordinate columns.
            *args: Extra field specifications. Can be:
                - str: Column name (type inferred from data)
                - ConvertedField: Full field specification
                - dict: Mapping of {name: type} pairs
                - pa.Schema: Use as base schema
            base: Base schema to use instead of default event schema.
            infer_remaining: If True, auto-add columns from source data
                that aren't explicitly specified.
            include_columns: When infer_remaining=True, only include these
                columns from the remaining unspecified ones.
            exclude_columns: When infer_remaining=True, exclude these
                columns from the remaining unspecified ones.
            **kwargs: Extra fields as name=type pairs.
        """
        self.unit = unit
        self.infer_remaining = infer_remaining
        self.include_columns = set(include_columns) if include_columns else None
        self.exclude_columns = set(exclude_columns) if exclude_columns else set()

        # Build base schema
        self._base_schema = base or make_base_schema(unit)

        # Collect extra field specifications
        self._extra_fields: list[ConvertedField] = []
        self._explicit_names: set[str] = set()

        # Process args
        for arg in args:
            if isinstance(arg, str):
                # Column name - infer type
                self._add_field(ConvertedField(arg))
            elif isinstance(arg, ConvertedField):
                self._add_field(arg)
            elif isinstance(arg, dict):
                for name, dtype in arg.items():
                    self._add_field(ConvertedField(name, dtype))
            elif isinstance(arg, pa.Schema):
                # Use as base schema
                self._base_schema = arg
            else:
                raise TypeError(
                    f"Invalid arg type {type(arg)}. Expected str, ConvertedField, "
                    f"dict, or pa.Schema."
                )

        # Process kwargs
        for name, dtype in kwargs.items():
            self._add_field(ConvertedField(name, dtype))

    def _add_field(self, field: ConvertedField) -> None:
        """Add an extra field specification."""
        if field.name in self._explicit_names:
            raise ValueError(f"Duplicate field name: {field.name}")
        self._extra_fields.append(field)
        self._explicit_names.add(field.name)

    @property
    def base_schema(self) -> pa.Schema:
        """The base schema with event columns."""
        return self._base_schema

    @property
    def extra_fields(self) -> list[ConvertedField]:
        """List of extra field specifications."""
        return list(self._extra_fields)

    @property
    def explicit_column_names(self) -> set[str]:
        """Set of explicitly specified column names."""
        return set(self._explicit_names)

    def build_schema(
        self,
        source_columns: dict[str, pa.DataType] | None = None,
    ) -> pa.Schema:
        """Build the final PyArrow schema.

        Args:
            source_columns: Dict of {column_name: inferred_type} from source data.
                Used for type inference when dtype is None.

        Returns:
            Complete PyArrow schema with base and extra fields.
        """
        source_columns = source_columns or {}
        extra_pa_fields = []

        # Add explicitly specified fields
        for field in self._extra_fields:
            inferred = source_columns.get(field.source)
            pa_field = field.to_field(inferred_type=inferred)
            extra_pa_fields.append(pa_field)

        # Add inferred remaining fields
        if self.infer_remaining:
            base_names = set(self._base_schema.names)
            for col_name, col_type in source_columns.items():
                # Skip if already in base schema or explicitly specified
                if col_name in base_names:
                    continue
                if col_name in self._explicit_names:
                    continue
                # Skip if source column for an explicit field
                if any(f.source == col_name for f in self._extra_fields):
                    continue
                # Apply include/exclude filters
                if self.include_columns and col_name not in self.include_columns:
                    continue
                if col_name in self.exclude_columns:
                    continue

                extra_pa_fields.append(pa.field(col_name, col_type, nullable=True))

        # Extend base schema
        if extra_pa_fields:
            return extend_schema(self._base_schema, extra_pa_fields)
        return self._base_schema

    def get_field_converter(self, name: str) -> Any | None:
        """Get the converter function for a field, if any.

        Args:
            name: Field name.

        Returns:
            Converter function or None.
        """
        for field in self._extra_fields:
            if field.name == name:
                return field.converter
        return None

    def get_source_column(self, name: str) -> str:
        """Get the source column name for a field.

        Args:
            name: Field name.

        Returns:
            Source column name (may be same as field name).
        """
        for field in self._extra_fields:
            if field.name == name:
                return field.source
        return name

    def __repr__(self) -> str:
        parts = [f"unit={self.unit}"]
        if self._extra_fields:
            parts.append(f"extra_fields={len(self._extra_fields)}")
        if self.infer_remaining:
            parts.append("infer_remaining=True")
        return f"TableSchema({', '.join(parts)})"


# endregion
