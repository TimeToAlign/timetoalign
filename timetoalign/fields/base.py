"""Base DataField hierarchy for columnar semantic types.

This module provides the foundational abstractions for wrapping PyArrow
arrays with typed, metadata-aware field objects:

- ``DataField`` -- abstract base class for all field wrappers
- ``NumericField`` -- fields backed by numeric (int/float) arrays
- ``StringField`` -- fields backed by string arrays
- ``StructField`` -- fields backed by struct arrays (with sub-field access)
- ``MapField`` -- fields backed by map arrays
- ``SemanticField[R]`` -- parameterised wrapper that composes a raw field ``R``
  and adds semantic identity (via ``SemanticTypeLike``)

Design:
    SemanticField uses *composition*, not inheritance, over raw fields.
    The ``value`` property exposes the inner raw field for schema access,
    and ``__getattr__`` delegates attribute lookups to the raw field so
    that callers can use raw-field methods transparently.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

import pyarrow as pa

R = TypeVar("R", bound="DataField")


# ---------------------------------------------------------------------------
# DataField ABC
# ---------------------------------------------------------------------------


class DataField(ABC):
    """Abstract base class for typed PyArrow column wrappers.

    A DataField pairs a ``pa.Array`` (or ``pa.ChunkedArray``) with its
    ``pa.Field`` schema descriptor, providing convenient access to data,
    metadata, and type information.

    Args:
        data: The PyArrow array holding column values, or ``None`` for
            schema-only (empty) fields.
        field: The PyArrow field descriptor carrying name, type, and
            metadata.

    Attributes:
        _data: The underlying array (may be ``None``).
        _field: The PyArrow field descriptor.
    """

    def __init__(
        self, data: pa.Array | pa.ChunkedArray | None, field: pa.Field
    ) -> None:
        self._data = data
        self._field = field

    # -- properties ----------------------------------------------------------

    @property
    def data(self) -> pa.Array | pa.ChunkedArray | None:
        """The underlying PyArrow array, or ``None`` if schema-only."""
        return self._data

    @property
    def field(self) -> pa.Field:
        """The PyArrow field descriptor (name, type, metadata)."""
        return self._field

    @property
    def name(self) -> str:
        """Column name taken from the PyArrow field."""
        return self._field.name

    @property
    def is_empty(self) -> bool:
        """``True`` when this field carries no data (schema-only)."""
        return self._data is None

    @property
    def pa_type(self) -> pa.DataType:
        """The PyArrow data type of this field."""
        return self._field.type

    @property
    def metadata(self) -> dict[str, str]:
        """Decoded metadata from the PyArrow field.

        Returns a plain ``dict[str, str]`` with byte keys/values decoded
        to UTF-8 strings.  Returns an empty dict when no metadata is
        present.
        """
        raw = self._field.metadata
        if not raw:
            return {}
        return {
            (k.decode("utf-8") if isinstance(k, bytes) else k): (
                v.decode("utf-8") if isinstance(v, bytes) else v
            )
            for k, v in raw.items()
        }

    # -- dunder methods ------------------------------------------------------

    def __len__(self) -> int:
        """Number of elements in the data array.

        Raises:
            TypeError: If the field is schema-only (no data).
        """
        if self._data is None:
            raise TypeError(f"Cannot compute length of schema-only field {self.name!r}")
        return len(self._data)

    def __getitem__(self, i: int) -> Any:
        """Return the *i*-th element as a Python scalar via ``.as_py()``.

        Handles both ``pa.Array`` and ``pa.ChunkedArray`` transparently.

        Args:
            i: Zero-based index.

        Returns:
            The Python-native scalar at position *i*.

        Raises:
            TypeError: If the field is schema-only (no data).
            IndexError: If *i* is out of range.
        """
        if self._data is None:
            raise TypeError(f"Cannot index schema-only field {self.name!r}")
        if isinstance(self._data, pa.ChunkedArray):
            # Combine to a contiguous array for correct indexing
            return self._data.combine_chunks()[i].as_py()
        return self._data[i].as_py()

    def __repr__(self) -> str:
        length = len(self) if not self.is_empty else 0
        return f"{type(self).__name__}(name={self.name!r}, type={self.pa_type}, len={length})"

    # -- conversion helpers --------------------------------------------------

    def to_pyarrow(self) -> pa.Array:
        """Return data as a contiguous ``pa.Array``.

        If the underlying storage is a ``ChunkedArray``, it is combined
        into a single chunk first.

        Raises:
            TypeError: If the field is schema-only (no data).
        """
        if self._data is None:
            raise TypeError(
                f"Cannot convert schema-only field {self.name!r} to PyArrow array"
            )
        if isinstance(self._data, pa.ChunkedArray):
            return self._data.combine_chunks()
        return self._data

    def to_field(self) -> pa.Field:
        """Return the ``pa.Field`` descriptor (with metadata)."""
        return self._field

    # -- abstract factory ----------------------------------------------------

    @classmethod
    @abstractmethod
    def from_field(cls, source: Any, **kw: Any) -> "DataField":
        """Construct a DataField from a source.

        Subclasses define what *source* means (e.g., a ``pa.Table``
        column, a ``pa.Field`` + ``pa.Array`` pair, etc.).

        Args:
            source: The data source.
            **kw: Additional keyword arguments for subclass-specific
                construction logic.

        Returns:
            A new DataField instance.
        """
        ...


# ---------------------------------------------------------------------------
# NumericField
# ---------------------------------------------------------------------------


class NumericField(DataField):
    """A DataField backed by a numeric (integer or floating-point) array.

    Validates at construction time that the PyArrow type is numeric.

    Args:
        data: Numeric PyArrow array, or ``None``.
        field: PyArrow field descriptor.

    Raises:
        TypeError: If the field type is not numeric.
    """

    def __init__(
        self, data: pa.Array | pa.ChunkedArray | None, field: pa.Field
    ) -> None:
        if not (pa.types.is_integer(field.type) or pa.types.is_floating(field.type)):
            raise TypeError(f"NumericField requires a numeric type, got {field.type}")
        super().__init__(data, field)

    def __getitem__(self, i: int) -> int | float:
        """Return the *i*-th element as ``int`` or ``float``.

        Args:
            i: Zero-based index.

        Returns:
            An ``int`` for integer types, ``float`` for floating-point types.
        """
        value = super().__getitem__(i)
        return value  # type: ignore[return-value]

    @classmethod
    def from_field(
        cls, source: tuple[pa.Array | pa.ChunkedArray | None, pa.Field], **kw: Any
    ) -> "NumericField":
        """Create a NumericField from a ``(data, field)`` tuple.

        Args:
            source: A tuple of ``(pa.Array | None, pa.Field)``.

        Returns:
            A new NumericField.
        """
        data, field = source
        return cls(data, field)


# ---------------------------------------------------------------------------
# StringField
# ---------------------------------------------------------------------------


class StringField(DataField):
    """A DataField backed by a string (utf8 / large_utf8) array.

    Validates at construction time that the PyArrow type is string-like.

    Args:
        data: String PyArrow array, or ``None``.
        field: PyArrow field descriptor.

    Raises:
        TypeError: If the field type is not string-like.
    """

    def __init__(
        self, data: pa.Array | pa.ChunkedArray | None, field: pa.Field
    ) -> None:
        if not (pa.types.is_string(field.type) or pa.types.is_large_string(field.type)):
            raise TypeError(f"StringField requires a string type, got {field.type}")
        super().__init__(data, field)

    def __getitem__(self, i: int) -> str | None:
        """Return the *i*-th element as ``str`` or ``None``.

        Args:
            i: Zero-based index.

        Returns:
            A string value or ``None`` for null entries.
        """
        return super().__getitem__(i)

    @classmethod
    def from_field(
        cls, source: tuple[pa.Array | pa.ChunkedArray | None, pa.Field], **kw: Any
    ) -> "StringField":
        """Create a StringField from a ``(data, field)`` tuple.

        Args:
            source: A tuple of ``(pa.Array | None, pa.Field)``.

        Returns:
            A new StringField.
        """
        data, field = source
        return cls(data, field)


# ---------------------------------------------------------------------------
# StructField
# ---------------------------------------------------------------------------


class StructField(DataField):
    """A DataField backed by a struct array.

    Provides sub-field extraction and field-name introspection on top of
    the base ``DataField`` interface.

    Args:
        data: Struct PyArrow array, or ``None``.
        field: PyArrow field descriptor.

    Raises:
        TypeError: If the field type is not a struct.
    """

    def __init__(
        self, data: pa.Array | pa.ChunkedArray | None, field: pa.Field
    ) -> None:
        if not pa.types.is_struct(field.type):
            raise TypeError(f"StructField requires a struct type, got {field.type}")
        super().__init__(data, field)

    @property
    def field_names(self) -> list[str]:
        """Names of the sub-fields in this struct.

        Returns:
            List of sub-field name strings.
        """
        struct_type: pa.StructType = self._field.type
        return [struct_type.field(i).name for i in range(struct_type.num_fields)]

    def get_sub_field(self, name: str) -> DataField:
        """Extract a sub-field as a new ``DataField``.

        The returned field uses ``NumericField`` or ``StringField`` when
        the sub-field type matches; otherwise a minimal concrete
        ``DataField`` subclass is returned.

        Args:
            name: Name of the sub-field to extract.

        Returns:
            A DataField wrapping the sub-field's array and schema.

        Raises:
            KeyError: If *name* is not a sub-field of this struct.
            TypeError: If this field has no data.
        """
        struct_type: pa.StructType = self._field.type
        # Validate sub-field exists
        sub_idx = struct_type.get_field_index(name)
        if sub_idx < 0:
            raise KeyError(
                f"Struct field {self.name!r} has no sub-field {name!r}. Available: {self.field_names}"
            )

        sub_pa_field = struct_type.field(sub_idx)

        if self._data is None:
            sub_data = None
        else:
            arr = (
                self.to_pyarrow()
                if isinstance(self._data, pa.ChunkedArray)
                else self._data
            )
            sub_data = arr.field(name)

        # Choose the right concrete class for the sub-field
        if pa.types.is_integer(sub_pa_field.type) or pa.types.is_floating(
            sub_pa_field.type
        ):
            return NumericField(sub_data, sub_pa_field)
        if pa.types.is_string(sub_pa_field.type) or pa.types.is_large_string(
            sub_pa_field.type
        ):
            return StringField(sub_data, sub_pa_field)
        if pa.types.is_struct(sub_pa_field.type):
            return StructField(sub_data, sub_pa_field)
        if pa.types.is_map(sub_pa_field.type):
            return MapField(sub_data, sub_pa_field)
        # Fallback: use _GenericField for other types
        return _GenericField(sub_data, sub_pa_field)

    def __getitem__(self, i: int) -> dict[str, Any] | None:
        """Return the *i*-th element as a Python ``dict`` or ``None``.

        Args:
            i: Zero-based index.

        Returns:
            A dict mapping sub-field names to values, or ``None`` for
            null entries.
        """
        return super().__getitem__(i)

    @classmethod
    def from_field(
        cls, source: tuple[pa.Array | pa.ChunkedArray | None, pa.Field], **kw: Any
    ) -> "StructField":
        """Create a StructField from a ``(data, field)`` tuple.

        Args:
            source: A tuple of ``(pa.Array | None, pa.Field)``.

        Returns:
            A new StructField.
        """
        data, field = source
        return cls(data, field)


# ---------------------------------------------------------------------------
# MapField
# ---------------------------------------------------------------------------


class MapField(DataField):
    """A DataField backed by a map array.

    Args:
        data: Map PyArrow array, or ``None``.
        field: PyArrow field descriptor.

    Raises:
        TypeError: If the field type is not a map.
    """

    def __init__(
        self, data: pa.Array | pa.ChunkedArray | None, field: pa.Field
    ) -> None:
        if not pa.types.is_map(field.type):
            raise TypeError(f"MapField requires a map type, got {field.type}")
        super().__init__(data, field)

    def __getitem__(self, i: int) -> dict[Any, Any] | None:
        """Return the *i*-th element as a Python ``dict`` or ``None``.

        Map scalars are returned as ``list[tuple[key, value]]`` by
        PyArrow's ``.as_py()``; this method converts them to a dict.

        Args:
            i: Zero-based index.

        Returns:
            A dict of key-value pairs, or ``None`` for null entries.
        """
        raw = super().__getitem__(i)
        if raw is None:
            return None
        # pa map .as_py() returns list of (key, value) tuples
        if isinstance(raw, list):
            return dict(raw)
        return raw  # type: ignore[return-value]

    @classmethod
    def from_field(
        cls, source: tuple[pa.Array | pa.ChunkedArray | None, pa.Field], **kw: Any
    ) -> "MapField":
        """Create a MapField from a ``(data, field)`` tuple.

        Args:
            source: A tuple of ``(pa.Array | None, pa.Field)``.

        Returns:
            A new MapField.
        """
        data, field = source
        return cls(data, field)


# ---------------------------------------------------------------------------
# _GenericField (internal fallback)
# ---------------------------------------------------------------------------


class _GenericField(DataField):
    """Concrete fallback DataField for types not covered by specialised classes.

    This is an internal helper used by ``StructField.get_sub_field`` when
    the sub-field type does not match any of the specialised field classes.
    """

    @classmethod
    def from_field(
        cls, source: tuple[pa.Array | pa.ChunkedArray | None, pa.Field], **kw: Any
    ) -> "_GenericField":
        """Create a _GenericField from a ``(data, field)`` tuple.

        Args:
            source: A tuple of ``(pa.Array | None, pa.Field)``.

        Returns:
            A new _GenericField.
        """
        data, field = source
        return cls(data, field)


# ---------------------------------------------------------------------------
# SemanticField
# ---------------------------------------------------------------------------


class SemanticField(DataField, Generic[R]):
    """A DataField that wraps a raw field and adds semantic identity.

    ``SemanticField`` implements parameterised composition: it stores a
    raw field (``R``, a ``DataField`` subclass) and delegates attribute
    access to it via ``__getattr__``.  The ``value`` property exposes
    the raw field directly, giving callers full access to the raw
    field's schema and methods.

    Subclasses are expected to:
    - Override ``__getitem__`` to return semantic scalar objects.
    - Implement ``from_field`` for construction from external sources.
    - Implement ``SemanticTypeLike`` properties (``semantic_type``,
      ``metadata_dict``).

    Args:
        raw: The wrapped raw DataField.

    Attributes:
        _raw: The inner raw field instance.

    Examples:
        >>> # Subclass usage (sketch):
        >>> class CoordinateField(SemanticField[StructField]):
        ...     @property
        ...     def semantic_type(self) -> str:
        ...         return "Coordinate"
        ...     def metadata_dict(self) -> dict[str, str]:
        ...         return {"field_type": "CoordinateField", ...}
    """

    def __init__(self, raw: R) -> None:
        # Use the raw field's data and pa.Field as our own
        super().__init__(raw.data, raw.field)
        self._raw: R = raw

    @property
    def value(self) -> R:
        """The inner raw field, providing access to its schema and methods.

        Returns:
            The wrapped ``DataField`` subclass instance.
        """
        return self._raw

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the wrapped raw field.

        Called only for attributes not found on ``self`` via normal
        lookup.  This makes raw-field methods (e.g.,
        ``StructField.get_sub_field``) transparently available on the
        semantic wrapper.

        Args:
            name: Attribute name to look up.

        Returns:
            The attribute from the raw field.

        Raises:
            AttributeError: If the raw field also lacks the attribute.
        """
        return getattr(self._raw, name)

    def __repr__(self) -> str:
        length = len(self) if not self.is_empty else 0
        return (
            f"{type(self).__name__}(name={self.name!r}, "
            f"raw={type(self._raw).__name__}, len={length})"
        )

    def get_raw(self) -> R:
        """Return the underlying raw field (strips the semantic layer).

        Returns:
            The inner raw ``DataField`` subclass (e.g. ``StructField``).
        """
        return self._raw

    @classmethod
    @abstractmethod
    def from_field(cls, source: Any, **kw: Any) -> "SemanticField[R]":
        """Construct a SemanticField from a source.

        Subclasses must implement this to define how to build the inner
        raw field and wrap it.

        Args:
            source: The data source.
            **kw: Additional keyword arguments.

        Returns:
            A new SemanticField instance.
        """
        ...

    @classmethod
    def matches_pa_field(cls, pa_field: pa.Field) -> bool:
        """Return True iff *pa_field* is a column this class can wrap.

        The base implementation returns ``False``: by default, columns are
        discoverable only via explicit ``b"timetoalign"`` JSON metadata (the
        Parquet round-trip contract).  Subclasses that can recognise their
        own columns by structural signature (e.g. ``PitchField`` matching
        any of the documented pitch struct schemas) MAY override this to
        return ``True`` for shape-matching columns.

        This is used by ``SemanticFieldAccessMixin.get_fields()`` as a
        third discovery strategy, after metadata-based and
        ``_default_column``-based lookup both fail.

        Args:
            pa_field: A ``pa.Field`` from the underlying table schema.

        Returns:
            ``True`` if this class can wrap the column described by
            *pa_field*; ``False`` otherwise.
        """
        return False
