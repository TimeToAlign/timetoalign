"""DataField hierarchy + pydantic → PyArrow translator + Parquet metadata.

This module is the foundation of TTA's columnar storage layer.  It pulls
together three closely-related concerns that previously lived in separate
sub-packages (``fields/base.py``, ``core/schemas/from_pydantic.py``,
``core/schemas/column_builder.py``, ``core/schemas/parquet_metadata.py``):

* The **DataField hierarchy** wraps ``pa.Array`` / ``pa.ChunkedArray`` with
  typed accessors.  ``SemanticField[T]`` is the strictly-typed bridge
  between a pydantic scalar ``T`` and a PyArrow column.
* The **pydantic → PyArrow translator** derives a ``pa.Schema`` (and
  individual ``pa.Field`` entries) from a pydantic ``BaseModel`` once at
  class-definition time.  Value projectors handle denormalised storage
  (``Coordinate.value`` → ``{value, numerator, denominator}``) and
  columnar separation (``Note.pitch`` → dropped from the pa.Schema).
* The **column-builder** assembles a ``pa.StructArray`` from many
  validated scalar instances column-wise (NEVER ``model_dump`` row-wise).
* The **Parquet-metadata** helpers produce the ``b"timetoalign"`` JSON
  blob that travels with every TTA-written ``pa.Field``.

Layout convention: four labelled sections, ordered base hierarchy →
translator → builder → metadata.
"""

from __future__ import annotations

import json
import sys
from abc import ABC, abstractmethod
from fractions import Fraction
from functools import lru_cache
from typing import (
    Any,
    Callable,
    ClassVar,
    Generic,
    Iterable,
    Literal,
    Sequence,
    TypeVar,
    get_args,
    get_origin,
)

import pyarrow as pa
from pydantic import BaseModel
from pydantic.fields import FieldInfo

R = TypeVar("R", bound="DataField")
T = TypeVar("T", bound=BaseModel)


# ═══════════════════════════════════════════════════════════════════════════
# 1. DATAFIELD HIERARCHY
# ═══════════════════════════════════════════════════════════════════════════


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


class StringField(DataField):
    """A DataField backed by a string (utf8 / large_utf8) array.

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
        return super().__getitem__(i)

    @classmethod
    def from_field(
        cls, source: tuple[pa.Array | pa.ChunkedArray | None, pa.Field], **kw: Any
    ) -> "StringField":
        data, field = source
        return cls(data, field)


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
        """Names of the sub-fields in this struct."""
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
        return _GenericField(sub_data, sub_pa_field)

    def __getitem__(self, i: int) -> dict[str, Any] | None:
        return super().__getitem__(i)

    @classmethod
    def from_field(
        cls, source: tuple[pa.Array | pa.ChunkedArray | None, pa.Field], **kw: Any
    ) -> "StructField":
        data, field = source
        return cls(data, field)


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
        raw = super().__getitem__(i)
        if raw is None:
            return None
        if isinstance(raw, list):
            return dict(raw)
        return raw  # type: ignore[return-value]

    @classmethod
    def from_field(
        cls, source: tuple[pa.Array | pa.ChunkedArray | None, pa.Field], **kw: Any
    ) -> "MapField":
        data, field = source
        return cls(data, field)


class _GenericField(DataField):
    """Concrete fallback DataField for types not covered by specialised classes."""

    @classmethod
    def from_field(
        cls, source: tuple[pa.Array | pa.ChunkedArray | None, pa.Field], **kw: Any
    ) -> "_GenericField":
        data, field = source
        return cls(data, field)


class SemanticField(DataField, Generic[R]):
    """A DataField that wraps a raw field and adds semantic identity.

    ``SemanticField`` implements parameterised composition: it stores a
    raw field (``R``, a ``DataField`` subclass) and delegates attribute
    access to it via ``__getattr__``.  The ``value`` property exposes
    the raw field directly, giving callers full access to the raw
    field's schema and methods.

    Paired-class contract (WP2.5).  Every concrete subclass is paired with
    a pydantic scalar ``T`` via ``XField(SemanticField[T])``.  At subclass
    declaration time, ``__init_subclass__`` derives ``cls.pa_schema`` (the
    ``pa.StructType`` for ``T``) and caches it on the subclass.  Callers
    use ``XField.pa_schema`` whenever they need the struct layout for an
    on-disk column without instantiating a live field.

    Subclasses are expected to:
    - Override ``__getitem__`` to return semantic scalar objects.
    - Implement ``from_field`` for construction from external sources.
    - Implement ``SemanticTypeLike`` properties (``semantic_type``,
      ``metadata_dict``).

    Args:
        raw: The wrapped raw DataField.

    Attributes:
        _raw: The inner raw field instance.
    """

    # The pydantic scalar class this SemanticField is paired with.
    # Populated by ``__init_subclass__`` from ``Generic[T]`` on the bases
    # of the concrete subclass.  ``None`` on the abstract base.
    scalar_cls: ClassVar[type[BaseModel] | None] = None

    # Cached pa.StructType derived from ``scalar_cls``'s pydantic model.
    # ``None`` on the abstract base; populated for every concrete subclass.
    pa_schema: ClassVar[pa.StructType | None] = None

    def __init_subclass__(cls, **kw: Any) -> None:
        """Resolve ``cls.scalar_cls`` and cache ``cls.pa_schema``.

        Resolution order:

        1. If the subclass declares ``scalar_cls`` in its own ``__dict__``
           (concrete override), use that directly.  This is the escape
           hatch for ``CoordinateField`` / ``DurationField`` which
           inherit through ``NumberField(SemanticField[StructField])``
           and can't pick up ``Coordinate`` / ``Duration`` from
           ``Generic[T]`` parametrisation.
        2. Otherwise walk ``__orig_bases__`` for a parametrised
           ``SemanticField[T]`` whose ``T`` is a pydantic ``BaseModel``.
           This is the common path used by every paired ``XField``.

        Intermediate abstract classes (e.g. ``NumberField`` parametrised
        on ``StructField``) leave ``scalar_cls`` / ``pa_schema`` as
        ``None``; their concrete children resolve normally.
        """
        super().__init_subclass__(**kw)
        own_scalar = cls.__dict__.get("scalar_cls")
        if isinstance(own_scalar, type) and issubclass(own_scalar, BaseModel):
            cls.pa_schema = derive_arrow_struct(own_scalar)
            return
        scalar = _resolve_scalar_cls(cls)
        if scalar is not None:
            cls.scalar_cls = scalar
            cls.pa_schema = derive_arrow_struct(scalar)

    def __init__(
        self, raw: R | None = None, *, source_fields: str | None = None
    ) -> None:
        """Construct a SemanticField.

        Two construction modes:

        * **Live mode:** pass a non-``None`` ``raw`` ``DataField``.  The
          SemanticField wraps it as usual.
        * **Blueprint mode:** pass only ``column=<name>``.  The
          SemanticField acts as a deferred specification of "find me
          this column on an EventData table".  ``is_blueprint`` is
          ``True``; ``_blueprint_column`` holds the column name.
          Materialise via ``EventData.get_field(blueprint)``.

        Args:
            raw: The wrapped raw DataField (live mode), or ``None`` for
                blueprint mode.
            source_fields: Column name to resolve later (blueprint mode).
        """
        if raw is None:
            if source_fields is None:
                raise TypeError(
                    f"{type(self).__name__} requires either a raw DataField (live) "
                    "or column= (blueprint)"
                )
            schema = type(self).pa_schema
            if schema is None:
                raise TypeError(
                    f"{type(self).__name__} cannot be a blueprint without a derived "
                    "pa_schema; check Generic parametrisation"
                )
            dummy_field = pa.field(source_fields, schema)
            raw = StructField(None, dummy_field)
            self._is_blueprint = True
            self._blueprint_column: str | None = source_fields
        else:
            self._is_blueprint = False
            self._blueprint_column = None

        super().__init__(raw.data, raw.field)
        self._raw: R = raw

    @property
    def is_blueprint(self) -> bool:
        """``True`` if this instance is a deferred-resolution blueprint."""
        return self._is_blueprint

    @property
    def value(self) -> R:
        """The inner raw field, providing access to its schema and methods."""
        return self._raw

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the wrapped raw field."""
        return getattr(self._raw, name)

    def __repr__(self) -> str:
        length = len(self) if not self.is_empty else 0
        return (
            f"{type(self).__name__}(name={self.name!r}, "
            f"raw={type(self._raw).__name__}, len={length})"
        )

    def get_raw(self) -> R:
        """Return the underlying raw field (strips the semantic layer)."""
        return self._raw

    def __getitem__(self, i: int) -> Any:
        """Return the *i*-th element as a typed scalar instance.

        Default implementation:

        * If ``cls.scalar_cls`` exposes a classmethod ``from_row``, the
          inner raw dict (or value) is passed through it — yielding a
          fully-validated pydantic scalar.
        * Otherwise falls back to the underlying ``DataField`` behaviour
          (``.as_py()`` on the element, typically a dict).

        Subclasses that need a richer materialisation override this
        method (e.g. ``CoordinateField`` carries a ``unit`` that is not
        in the column, so its ``__getitem__`` injects the unit).
        """
        raw = self._raw[i]
        cls = type(self)
        if cls.scalar_cls is not None and raw is not None:
            from_row = getattr(cls.scalar_cls, "from_row", None)
            if callable(from_row):
                return from_row(raw)
        return raw

    @classmethod
    def from_field(cls, source: Any, **kw: Any) -> "SemanticField[R]":
        """Construct a SemanticField from a source.

        Default implementation accepts the four common source shapes
        (``pa.Array``, ``pa.ChunkedArray``, ``StructField``, ``pa.Field``,
        or a ``(data, pa.Field)`` tuple) and wraps each in a
        ``StructField`` for storage.  Subclasses that need additional
        semantic state (e.g. ``CoordinateField`` carrying a ``unit``)
        override this method.

        Args:
            source: One of the accepted source shapes.
            **kw: Subclass-specific keyword arguments (e.g. ``name``).

        Returns:
            A new SemanticField instance.

        Raises:
            TypeError: If *source* is not a recognised shape.
        """
        name = kw.pop("name", cls.__name__.removesuffix("Field").lower() or "value")

        if isinstance(source, tuple):
            data, pa_field = source
            struct_field = StructField(data, pa_field)
            return cls(struct_field)

        if isinstance(source, pa.Field):
            struct_field = StructField(None, source)
            return cls(struct_field)

        if isinstance(source, StructField):
            return cls(source)

        if isinstance(source, (pa.Array, pa.ChunkedArray)):
            pa_field = pa.field(name, source.type)
            struct_field = StructField(source, pa_field)
            return cls(struct_field)

        raise TypeError(
            f"Unsupported source type for {cls.__name__}.from_field: {type(source).__name__}"
        )

    @classmethod
    def matches_pa_field(cls, pa_field: pa.Field) -> bool:
        """Return True iff *pa_field* is a column this class can wrap.

        Two checks, applied in order:

        1. **Metadata-based identification (round-trip contract).** If
           ``pa_field`` carries the ``b"timetoalign"`` JSON blob with a
           ``field_type`` matching ``cls.__name__``, the column is
           definitively claimed.
        2. **Structural identification.** If ``cls.pa_schema`` is
           populated (every concrete subclass) and ``pa_field.type``
           matches it exactly (struct with identical sub-field names
           and types), the column is claimed.

        Subclasses MAY override to relax or tighten these checks.

        Args:
            pa_field: A ``pa.Field`` from the underlying table schema.

        Returns:
            ``True`` if this class can wrap the column described by
            *pa_field*; ``False`` otherwise.
        """
        # Metadata-based identification
        if (
            pa_field.metadata is not None
            and TIMETOALIGN_METADATA_KEY in pa_field.metadata
        ):
            blob = pa_field.metadata[TIMETOALIGN_METADATA_KEY]
            try:
                if isinstance(blob, bytes):
                    blob = blob.decode("utf-8")
                meta = json.loads(blob)
            except (json.JSONDecodeError, UnicodeDecodeError):
                meta = {}
            if isinstance(meta, dict) and meta.get("field_type") == cls.__name__:
                return True

        # Structural identification — exact struct-shape match.
        expected = cls.pa_schema
        if expected is None:
            return False
        if not pa.types.is_struct(pa_field.type):
            return False
        return _struct_types_match(pa_field.type, expected)


def _resolve_scalar_cls(cls: type) -> type[BaseModel] | None:
    """Walk ``__orig_bases__`` to find the ``SemanticField[T]`` parametrisation.

    Returns the pydantic ``BaseModel`` subclass ``T`` when found, or
    ``None`` when the class is an intermediate abstract subclass that
    does not pin ``T`` (e.g. ``NumberField`` does not provide a concrete
    ``T``; its children ``CoordinateField`` and ``DurationField`` do).
    """
    for base in getattr(cls, "__orig_bases__", ()) or ():
        origin = get_origin(base)
        if origin is None:
            continue
        if origin is SemanticField or (
            isinstance(origin, type) and issubclass(origin, SemanticField)
        ):
            args = get_args(base)
            if not args:
                continue
            arg = args[0]
            if isinstance(arg, type) and issubclass(arg, BaseModel):
                return arg
    return None


def _struct_types_match(actual: pa.DataType, expected: pa.StructType) -> bool:
    """Strict structural match of two struct types — names and types both."""
    if not pa.types.is_struct(actual):
        return False
    if actual.num_fields != expected.num_fields:
        return False
    for i in range(expected.num_fields):
        a, e = actual.field(i), expected.field(i)
        if a.name != e.name:
            return False
        if not a.type.equals(e.type):
            return False
    return True


# ═══════════════════════════════════════════════════════════════════════════
# 2. PYDANTIC → PYARROW TRANSLATOR
# ═══════════════════════════════════════════════════════════════════════════

# A value projector maps a single pydantic field to a *sequence* of
# ``pa.Field`` entries that will replace the field in the derived struct.
# Used by ``Coordinate``: the scalar's single ``value: int|float|Fraction``
# field expands to three storage fields ``{value, numerator, denominator}``
# inside the Arrow struct.  An empty list drops the field entirely
# (used to keep e.g. ``Note.pitch`` out of the pa.Schema).
_ValueProjector = Callable[[type[BaseModel], str, FieldInfo], list[pa.Field]]

_VALUE_PROJECTORS: dict[tuple[type[BaseModel], str], _ValueProjector] = {}


def register_value_projector(
    model_cls: type[BaseModel],
    field_name: str,
    projector: _ValueProjector,
) -> None:
    """Register a custom field-expansion rule for a scalar field.

    The projector receives ``(model_cls, field_name, field_info)`` and
    returns a list of ``pa.Field`` entries that replace the single
    pydantic field in the derived pa.Schema.  Used for denormalised
    storage projections that the type alone cannot express (e.g.
    ``Coordinate.value`` → ``{value, numerator, denominator}``) and for
    columnar-separation drops (e.g. ``Note.pitch`` → ``[]``).

    Registration is idempotent on the (cls, field_name) pair — later
    registrations override earlier ones.  Calling this also invalidates
    the per-class derivation cache.

    Args:
        model_cls: The pydantic ``BaseModel`` subclass.
        field_name: The pydantic field name to project.
        projector: Callable returning a list of ``pa.Field`` replacements.
    """
    _VALUE_PROJECTORS[(model_cls, field_name)] = projector
    _derive_arrow_fields.cache_clear()


def _is_tuple_type(py_type: Any) -> bool:
    origin = get_origin(py_type)
    return origin is tuple


def _atomic_arrow_type(py_type: Any) -> pa.DataType:
    """Map a pydantic atomic / structural type annotation to a ``pa.DataType``."""
    if py_type is str:
        return pa.string()
    if py_type is int:
        return pa.int64()
    if py_type is float:
        return pa.float64()
    if py_type is bool:
        return pa.bool_()

    origin = get_origin(py_type)

    if origin is Literal:
        args = get_args(py_type)
        if all(isinstance(a, str) for a in args):
            return pa.string()
        if all(isinstance(a, int) for a in args):
            return pa.int64()
        raise TypeError(
            f"Mixed-type Literal not supported in pa.Schema derivation: {py_type!r}"
        )

    if isinstance(py_type, type) and issubclass(py_type, BaseModel):
        return pa.struct(_derive_arrow_fields(py_type))

    if _is_tuple_type(py_type):
        args = get_args(py_type)
        if len(args) == 2 and args[1] is Ellipsis:
            inner_pa = _atomic_arrow_type(args[0])
            return pa.list_(inner_pa)
        if len(args) >= 1 and Ellipsis not in args:
            children = [
                pa.field(f"_{i}", _atomic_arrow_type(a), nullable=True)
                for i, a in enumerate(args)
            ]
            return pa.struct(children)
        raise TypeError(
            f"Unsupported tuple annotation {py_type!r}; use tuple[T, ...] "
            "for variadic or tuple[T1, T2, ...] for fixed-length."
        )

    raise TypeError(
        f"Cannot derive PyArrow type for {py_type!r}: not a supported type. "
        "Supported: str, int, float, bool, Literal[str|int, ...], nested "
        "BaseModel, tuple[T, ...] (variadic), tuple[T1, T2, ...] (fixed). "
        "Nested unsupported shapes need to be added when the bulk migration "
        "encounters them — extend timetoalign.core.fields."
    )


def _unwrap_optional(py_type: Any) -> tuple[Any, bool]:
    """Return (inner_type, nullable) for ``T | None`` / ``Optional[T]``."""
    origin = get_origin(py_type)
    union_type = getattr(sys.modules.get("types"), "UnionType", None)
    is_union = origin is union_type or (
        origin is not None and getattr(origin, "__name__", None) == "Union"
    )
    if not is_union:
        return py_type, False
    args = [a for a in get_args(py_type) if a is not type(None)]
    if len(args) != 1:
        basemodel_arms = [
            a for a in args if isinstance(a, type) and issubclass(a, BaseModel)
        ]
        if len(basemodel_arms) >= 2:
            raise TypeError(
                f"Union of BaseModel subclasses is forbidden by the WP2 plan "
                f"(columnar separation required): {py_type!r}. Drop the field "
                f"from the pa.Schema via register_value_projector(cls, name, "
                f"lambda *_: [])."
            )
        raise TypeError(
            f"Only Optional[T] / T | None unions are supported, got {py_type!r}"
        )
    return args[0], True


@lru_cache(maxsize=None)
def _derive_arrow_fields(model_cls: type[BaseModel]) -> tuple[pa.Field, ...]:
    """Translate a pydantic model class into a tuple of ``pa.Field``.

    Cached per class — derivation runs exactly once per scalar.  Computed
    fields (``@computed_field``) are NOT included: per WP2's locked
    decision, they derive on access and are absent from both pa.Schema
    and the underlying Arrow column.

    All derived fields are marked ``nullable=True``.  Pydantic ``required``
    describes what a single scalar instance must contain; the pa.Schema
    describes a columnar storage where nulls are first-class.
    """
    out: list[pa.Field] = []
    for name, info in model_cls.model_fields.items():
        proj = _VALUE_PROJECTORS.get((model_cls, name))
        if proj is not None:
            out.extend(proj(model_cls, name, info))
            continue

        ann = info.annotation
        if ann is None:
            raise TypeError(
                f"Field {model_cls.__name__}.{name} has no annotation; cannot "
                "derive PyArrow type"
            )
        inner, _optional = _unwrap_optional(ann)
        pa_type = _atomic_arrow_type(inner)
        out.append(pa.field(name, pa_type, nullable=True))
    return tuple(out)


def derive_arrow_struct(model_cls: type[BaseModel]) -> pa.StructType:
    """Return the PyArrow struct type for a pydantic scalar.

    The struct's children are derived once per class and cached.

    Args:
        model_cls: A pydantic v2 ``BaseModel`` subclass.

    Returns:
        ``pa.StructType`` whose children mirror the model's fields
        (with value-projector expansions applied).
    """
    return pa.struct(_derive_arrow_fields(model_cls))


def derive_arrow_schema(model_cls: type[BaseModel]) -> pa.Schema:
    """Return a ``pa.Schema`` whose columns mirror a pydantic scalar's fields.

    Convenience for callers that want a top-level schema (rather than a
    nested struct).  The schema is **not** decorated with the
    ``b"timetoalign"`` metadata blob — use
    :func:`parquet_metadata_for_model` when constructing the ``pa.Field``
    that holds the struct.
    """
    return pa.schema(_derive_arrow_fields(model_cls))


# ═══════════════════════════════════════════════════════════════════════════
# 3. COLUMN-BUILDER
# ═══════════════════════════════════════════════════════════════════════════


def build_struct_array(
    model_cls: type[BaseModel],
    objects: Sequence[BaseModel | None],
) -> pa.StructArray:
    """Construct a ``pa.StructArray`` from a sequence of pydantic instances.

    Implements the column-builder pattern: for each pydantic field name,
    materialise one ``pa.Array`` by pulling that attribute column-wise,
    then assemble the per-field arrays into a single struct array.  This
    is the WP2 canonical bulk-construction path.

    **Nested ``BaseModel`` fields** (e.g. ``Note.start: Coordinate``,
    ``Measure.duration: Duration``) are recursed into — the column is
    built by recursive ``build_struct_array`` (or
    ``build_coordinate_struct_array`` for ``Coordinate`` / ``Duration``)
    so that the result is a nested ``pa.StructArray`` matching the
    derived storage shape.

    **Projector-replaced fields** (Coordinate's ``value``/``unit``;
    ``Note.pitch``) are honoured.

    ``None`` entries in *objects* are represented as null struct entries.

    Args:
        model_cls: The pydantic ``BaseModel`` subclass whose fields drive
            the column build.
        objects: A sequence of *model_cls* instances (or ``None`` for null
            rows).

    Returns:
        A ``pa.StructArray`` matching ``derive_arrow_struct(model_cls)``.

    Raises:
        TypeError: If a non-``None`` entry is not an instance of *model_cls*.
    """
    arrow_struct = derive_arrow_struct(model_cls)
    null_mask: list[bool] = []
    for obj in objects:
        if obj is None:
            null_mask.append(True)
            continue
        if not isinstance(obj, model_cls):
            raise TypeError(
                f"Expected {model_cls.__name__} (or None), got {type(obj).__name__}"
            )
        null_mask.append(False)

    field_arrays: list[pa.Array] = []
    pa_fields: list[pa.Field] = list(arrow_struct)
    sub_blocks = _group_pa_fields_by_pydantic_field(model_cls, pa_fields)

    for py_field_name, pa_block in sub_blocks.items():
        if py_field_name is None:
            raise TypeError(
                "pa.Schema field cannot be mapped back to a pydantic field; "
                "extend the column-builder for this projector shape."
            )

        py_field_info = model_cls.model_fields[py_field_name]
        values: list[Any] = []
        for i, obj in enumerate(objects):
            if obj is None:
                values.append(None)
            else:
                values.append(getattr(obj, py_field_name))

        emitted = _build_field_arrays(
            model_cls=model_cls,
            field_name=py_field_name,
            field_info=py_field_info,
            pa_subfields=pa_block,
            values=values,
        )
        field_arrays.extend(emitted)

    return pa.StructArray.from_arrays(
        field_arrays,
        fields=pa_fields,
        mask=pa.array(null_mask) if any(null_mask) else None,
    )


def _group_pa_fields_by_pydantic_field(
    model_cls: type[BaseModel],
    pa_fields: list[pa.Field],
) -> "dict[str | None, list[pa.Field]]":
    """Map each ``pa.Field`` back to the pydantic field that produced it."""
    pyd_names = list(model_cls.model_fields.keys())
    pyd_name_set = set(pyd_names)
    out: dict[str | None, list[pa.Field]] = {n: [] for n in pyd_names}

    matched_pa: list[pa.Field] = []
    for pf in pa_fields:
        if pf.name in pyd_name_set:
            out[pf.name].append(pf)
            matched_pa.append(pf)

    leftover = [pf for pf in pa_fields if pf not in matched_pa]
    if not leftover:
        return {k: v for k, v in out.items() if v}

    for pyd_name in pyd_names:
        proj = _VALUE_PROJECTORS.get((model_cls, pyd_name))
        if proj is None:
            continue
        emitted = proj(model_cls, pyd_name, model_cls.model_fields[pyd_name])
        emitted_names = [f.name for f in emitted]
        if not emitted_names:
            continue
        captured = [pf for pf in leftover if pf.name in emitted_names]
        for pf in captured:
            out[pyd_name].append(pf)
        leftover = [pf for pf in leftover if pf not in captured]

    if leftover:
        return {**out, None: leftover}

    return {k: v for k, v in out.items() if v}


def _build_field_arrays(
    *,
    model_cls: type[BaseModel],
    field_name: str,
    field_info: Any,
    pa_subfields: list[pa.Field],
    values: list[Any],
) -> list[pa.Array]:
    """Produce one or more ``pa.Array`` for a single pydantic field's slot."""
    if not pa_subfields:
        return []

    annotation = field_info.annotation
    inner_type, _nullable = _unwrap_optional_annotation(annotation)

    if isinstance(inner_type, type) and issubclass(inner_type, BaseModel):
        if _is_coordinate_like(inner_type):
            return [build_coordinate_struct_array(values)]
        sub_array = build_struct_array(inner_type, values)
        return [sub_array]

    if len(pa_subfields) != 1:
        raise TypeError(
            f"Cannot build {len(pa_subfields)} arrays for atomic pydantic field "
            f"{model_cls.__name__}.{field_name}"
        )
    pa_field = pa_subfields[0]
    pa_type = pa_field.type
    if pa.types.is_struct(pa_type) and all(
        pa_type.field(i).name == f"_{i}" for i in range(pa_type.num_fields)
    ):
        n = pa_type.num_fields
        rows: list[Any] = []
        for v in values:
            if v is None:
                rows.append(None)
            else:
                rows.append({f"_{i}": v[i] for i in range(n)})
        return [pa.array(rows, type=pa_type)]
    if pa.types.is_list(pa_type):
        rows = []
        for v in values:
            rows.append(None if v is None else list(v))
        return [pa.array(rows, type=pa_type)]
    return [pa.array(values, type=pa_type)]


def _unwrap_optional_annotation(annotation: Any) -> tuple[Any, bool]:
    origin = get_origin(annotation)
    union_type = getattr(sys.modules.get("types"), "UnionType", None)
    is_union = origin is union_type or (
        origin is not None and getattr(origin, "__name__", None) == "Union"
    )
    if not is_union:
        return annotation, False
    args = [a for a in get_args(annotation) if a is not type(None)]
    if len(args) == 1:
        return args[0], True
    return annotation, False


def _is_coordinate_like(tp: type) -> bool:
    """Detect ``Coordinate`` / ``Duration`` (and Id-variants) without a hard import.

    The TimeScalar value-projector denormalises ``value`` into three
    columns and drops ``unit`` (and ``timeline_id`` for the Id-variants);
    this helper is the signal that the nested-field builder must route
    through :func:`build_coordinate_struct_array` rather than the generic
    recursion.
    """
    if tp.__name__ in (
        "TimeScalar",
        "Coordinate",
        "IdCoordinate",
        "Duration",
        "IdDuration",
    ) and tp.__module__.endswith(".core.time"):
        return True
    return False


def build_coordinate_struct_array(
    objects: Iterable[Any],
) -> pa.StructArray:
    """Build the coordinate storage struct from a sequence of Coordinates.

    Coordinate's pydantic model exposes ``(value, unit)`` to users, but
    the on-disk Arrow column denormalises ``value`` into
    ``{value: float64, numerator: int64, denominator: int64}`` so that
    rational precision survives a Parquet round-trip.  This function is
    the column-builder for that denormalised projection.

    ``unit`` is NOT stored in the column — it lives in ``pa.Field``
    metadata (the SemanticField carries it).

    Args:
        objects: An iterable of ``Coordinate`` (or ``Duration``)
            instances, or ``None``.

    Returns:
        A ``pa.StructArray`` with the canonical coordinate storage type.
    """
    values: list[float] = []
    numerators: list[int | None] = []
    denominators: list[int | None] = []
    null_mask: list[bool] = []
    for obj in objects:
        if obj is None:
            null_mask.append(True)
            values.append(0.0)
            numerators.append(None)
            denominators.append(None)
            continue
        null_mask.append(False)
        v = obj.value
        values.append(float(v))
        if isinstance(v, Fraction):
            numerators.append(v.numerator)
            denominators.append(v.denominator)
        elif isinstance(v, int) and not isinstance(v, bool):
            numerators.append(v)
            denominators.append(1)
        else:
            numerators.append(None)
            denominators.append(None)
    fields = [
        pa.field("value", pa.float64(), nullable=True),
        pa.field("numerator", pa.int64(), nullable=True),
        pa.field("denominator", pa.int64(), nullable=True),
    ]
    arrs = [
        pa.array(values, type=pa.float64()),
        pa.array(numerators, type=pa.int64()),
        pa.array(denominators, type=pa.int64()),
    ]
    return pa.StructArray.from_arrays(
        arrs,
        fields=fields,
        mask=pa.array(null_mask) if any(null_mask) else None,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. PARQUET METADATA
# ═══════════════════════════════════════════════════════════════════════════

TIMETOALIGN_METADATA_KEY: bytes = b"timetoalign"
"""The bytes key used inside ``pa.Field.metadata`` for the TTA blob."""


@lru_cache(maxsize=None)
def _cached_json_schema_bytes(model_cls: type[BaseModel]) -> bytes:
    """Return ``model_json_schema()`` serialised to UTF-8 bytes."""
    return json.dumps(model_cls.model_json_schema(), sort_keys=True).encode("utf-8")


def metadata_blob_for_model(model_cls: type[BaseModel]) -> bytes:
    """Return the JSON-encoded ``model_json_schema()`` bytes for a model.

    This is the **payload** that lives under
    ``pa.Field.metadata[b"timetoalign"]``.  It is identical for every
    ``pa.Field`` carrying the same scalar type and is cached so repeated
    calls return the same bytes object.
    """
    return _cached_json_schema_bytes(model_cls)


def metadata_blob_from_dict(payload: dict[str, Any]) -> bytes:
    """Return JSON-encoded UTF-8 bytes from an arbitrary payload dict.

    Used by SemanticField subclasses (Coordinate, Duration) to keep
    their per-instance payload shape (which records the *runtime*
    ``unit``) while still routing through the unified metadata helper.
    Migrated scalars whose schema is entirely pydantic-derived can use
    :func:`metadata_blob_for_model` directly.
    """
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def parquet_metadata_for_model(
    model_cls: type[BaseModel],
    *,
    extra: dict[bytes, bytes] | None = None,
) -> dict[bytes, bytes]:
    """Return the ``pa.Field.metadata`` dict for a scalar's pydantic model.

    The returned dict is suitable for passing directly into
    ``pa.field(..., metadata=...)`` or ``pa.Field.with_metadata(...)``.
    Always contains the ``b"timetoalign"`` key with the JSONSchema
    payload; *extra* entries are merged in if provided.
    """
    metadata: dict[bytes, bytes] = {
        TIMETOALIGN_METADATA_KEY: metadata_blob_for_model(model_cls)
    }
    if extra:
        metadata.update(extra)
    return metadata


def parse_metadata_blob(blob: bytes | str | None) -> dict[str, Any]:
    """Parse a ``b"timetoalign"`` payload back into a dict.

    Args:
        blob: The bytes (or already-decoded string) stored under
            ``b"timetoalign"`` in ``pa.Field.metadata``.  ``None`` returns
            an empty dict.

    Returns:
        The decoded JSONSchema dictionary, or ``{}`` if *blob* is empty.
    """
    if blob is None:
        return {}
    if isinstance(blob, bytes):
        blob = blob.decode("utf-8")
    if not blob:
        return {}
    return json.loads(blob)


# ═══════════════════════════════════════════════════════════════════════════
# 5. NumberField — shared parent for CoordinateField & DurationField
# ═══════════════════════════════════════════════════════════════════════════
#
# Lives at the bottom because it depends on the SemanticField machinery
# above; the concrete CoordinateField / DurationField subclasses (and
# the shared TimeScalarField parent) live in core/time.py.


class DenominateNumberField(SemanticField[StructField]):
    """Abstract parent for numeric struct fields (coordinates, durations).

    Wraps a ``StructField`` and adds unit/number_type semantics plus
    shared serialisation logic.  Concrete subclasses (CoordinateField,
    DurationField) supply ``semantic_type``, ``metadata_dict``, and
    ``__getitem__``.

    Args:
        raw: The inner ``StructField`` holding numeric struct data.
        unit: The time unit.
        number_type: The numeric representation used for scalar access.
    """

    def __init__(self, raw: StructField, unit: Any, number_type: Any) -> None:
        # NumberField is always live (Coordinate/Duration columns need
        # explicit unit + number_type semantics).  We bypass the
        # SemanticField blueprint plumbing and store directly.
        DataField.__init__(self, raw.data, raw.field)
        self._raw = raw
        self._is_blueprint = False
        self._blueprint_column = None
        # Late imports avoid pulling enums into the base module.
        from .enums import NumberType, TimeUnit

        self._unit = TimeUnit(unit) if isinstance(unit, str) else unit
        self._number_type = (
            NumberType(number_type) if isinstance(number_type, str) else number_type
        )

    @property
    def unit(self) -> Any:
        """The time unit of this field."""
        return self._unit

    @property
    def domain(self) -> Any:
        """The temporal domain, derived from the unit."""
        return self._unit.domain

    @property
    def number_type(self) -> Any:
        """The numeric representation used for scalar access."""
        return self._number_type

    @property
    @abstractmethod
    def semantic_type(self) -> str: ...

    @abstractmethod
    def metadata_dict(self) -> dict[str, str]: ...

    def to_field(self) -> pa.Field:
        """Return a ``pa.Field`` with ``b"timetoalign"`` metadata injected."""
        meta_blob = metadata_blob_from_dict(self.metadata_dict())
        existing = self._field.metadata or {}
        merged = {**existing, TIMETOALIGN_METADATA_KEY: meta_blob}
        return self._field.with_metadata(merged)

    @staticmethod
    def _require_unit(unit: Any, cls_name: str = "NumberField") -> Any:
        from .enums import TimeUnit

        if unit is None:
            raise ValueError(
                f"'unit' is required when constructing {cls_name} from a bare array or StructField"
            )
        return TimeUnit(unit) if isinstance(unit, str) else unit

    @staticmethod
    def _require_number_type(number_type: Any, cls_name: str = "NumberField") -> Any:
        from .enums import NumberType

        if number_type is None:
            raise ValueError(
                f"'number_type' is required when constructing {cls_name} from a bare array or StructField"
            )
        return NumberType(number_type) if isinstance(number_type, str) else number_type

    @staticmethod
    def _resolve_metadata(
        pa_field: pa.Field,
        unit_override: Any,
        nt_override: Any,
    ) -> tuple[Any, Any]:
        """Extract unit and number_type from a ``pa.Field``'s metadata."""
        from .enums import NumberType, TimeUnit

        meta: dict[str, str] = {}
        raw_meta = pa_field.metadata
        if raw_meta:
            if TIMETOALIGN_METADATA_KEY in raw_meta:
                blob = raw_meta[TIMETOALIGN_METADATA_KEY]
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
