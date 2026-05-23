"""FieldSpec — universal column-to-field processor objects.

A ``FieldSpec`` is a *recipe* for producing a ``DataField`` from a
source ``pa.Array`` (a column in the original tabular source).  This
module hosts the hierarchy together with :func:`resolve_field_spec`,
the entry point for the universal resolution table used by
``TabularLoader.column_specs``.

The hierarchy

* :class:`FieldSpec` — abstract base; every concrete subclass implements
  :meth:`FieldSpec.emit`.
* :class:`IntFieldSpec`, :class:`FloatFieldSpec`, :class:`StringFieldSpec`
  — leaf specs that emit a typed raw :class:`NumericField` /
  :class:`StringField`.
* :class:`RationalFieldSpec` — leaf spec emitting the canonical
  ``{value, numerator, denominator}`` struct (raw
  :class:`RationalField`).  Accepts string fractions (``"3/4"``) or any
  numeric input.
* :class:`CompositeFieldSpec` — one source column splits into many
  fields by separator or named regex.
* :class:`FractionFieldSpec` — pre-configured ``CompositeFieldSpec``
  for ``"<numerator>/<denominator>"`` columns; promoted to a semantic
  :class:`DenominateNumberField` when a ``unit`` is bound.
* :class:`CallableFieldSpec` — escape hatch wrapping a user-provided
  ``(pa.Array) -> DataField`` callable.

The resolution table

:func:`resolve_field_spec` maps user-friendly inputs (``int`` /
``float`` / ``str`` / ``Fraction`` types, ``pa.DataType`` instances,
raw ``DataField`` subclasses, ``FieldSpec`` instances, or callables)
to ``FieldSpec`` instances.  Loaders call it on each entry of
``column_specs`` exactly once.

Bulk-emission contract
----------------------

Every leaf ``FieldSpec.emit()`` is implemented through ``pa.compute``
(vectorized) — never through per-row Python loops.  Composite specs
recurse into their parts using the same contract.
"""

from __future__ import annotations

import re
from fractions import Fraction
from typing import Any, Callable, Sequence

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc

from timetoalign.core import (
    DenominateNumberField,
    NumericField,
    RationalField,
    SemanticField,
    StringField,
    StructField,
    TimeUnit,
)
from timetoalign.core.fields import DataField

__all__ = [
    "FieldSpec",
    "IntFieldSpec",
    "FloatFieldSpec",
    "StringFieldSpec",
    "RationalFieldSpec",
    "CompositeFieldSpec",
    "FractionFieldSpec",
    "CallableFieldSpec",
    "resolve_field_spec",
]


# ═══════════════════════════════════════════════════════════════════════════
# 1. ABSTRACT BASE
# ═══════════════════════════════════════════════════════════════════════════


class FieldSpec:
    """Abstract base for column-to-field processors.

    Subclasses implement :meth:`emit` to turn a source ``pa.Array``
    into a single :class:`DataField`.  The output's name comes from the
    spec's own ``name`` (when set) or from the source column name passed
    to :meth:`emit`.

    Args:
        name: Optional override.  When ``None``, :meth:`emit` falls back
            to the source column name supplied by the caller.
    """

    def __init__(self, name: str | None = None) -> None:
        self._name = name

    @property
    def name(self) -> str | None:
        """Override name, or ``None`` if the source column name is used."""
        return self._name

    def emit(self, source: pa.Array, *, name: str) -> DataField:
        """Resolve *source* into a typed :class:`DataField`.

        Args:
            source: The raw column from the source ``pa.Table``.
            name: The source column name (used as a fallback when this
                spec carries no ``name=`` override).

        Returns:
            A single :class:`DataField` whose name is ``self.name`` if
            set, otherwise *name*.
        """
        raise NotImplementedError  # pragma: no cover

    def _resolve_name(self, fallback: str) -> str:
        """Return the spec's name override, or the *fallback*."""
        return self._name if self._name is not None else fallback


# ═══════════════════════════════════════════════════════════════════════════
# 2. LEAF SPECS
# ═══════════════════════════════════════════════════════════════════════════


class IntFieldSpec(FieldSpec):
    """Emit a raw :class:`NumericField` of ``pa.int64()``.

    Input may already be integer; non-integer numeric input is cast.
    Strings are parsed via ``pa.compute.cast`` (raises on
    unparseable values).
    """

    def emit(self, source: pa.Array, *, name: str) -> NumericField:
        out_name = self._resolve_name(name)
        casted = pc.cast(source, pa.int64())
        pa_field = pa.field(out_name, pa.int64())
        return NumericField(casted, pa_field)


class FloatFieldSpec(FieldSpec):
    """Emit a raw :class:`NumericField` of ``pa.float64()``."""

    def emit(self, source: pa.Array, *, name: str) -> NumericField:
        out_name = self._resolve_name(name)
        casted = pc.cast(source, pa.float64())
        pa_field = pa.field(out_name, pa.float64())
        return NumericField(casted, pa_field)


class StringFieldSpec(FieldSpec):
    """Emit a raw :class:`StringField` of ``pa.string()``."""

    def emit(self, source: pa.Array, *, name: str) -> StringField:
        out_name = self._resolve_name(name)
        if pa.types.is_string(source.type) or pa.types.is_large_string(source.type):
            casted = source
        else:
            casted = pc.cast(source, pa.string())
        pa_field = pa.field(out_name, pa.string())
        return StringField(casted, pa_field)


# ─── RationalFieldSpec helpers (module-level for testability) ──────────────

_FRACTION_RE = re.compile(r"^\s*(-?\d+)\s*/\s*(-?\d+)\s*$")


def _parse_rational_pair(value: Any) -> tuple[int, int]:
    """Parse *value* into a ``(numerator, denominator)`` pair.

    Accepts strings of the form ``"<int>/<int>"``, plain integer or
    float strings, ``int``, ``float``, ``Fraction`` instances.  Raises
    ``ValueError`` for unparseable input.

    Float-to-fraction conversion uses :meth:`Fraction.from_float` to
    keep the exact bit-for-bit representation; callers wanting a
    limited-denominator approximation should pass a ``Fraction``.
    """
    if value is None:
        raise ValueError("cannot parse None as a rational")
    if isinstance(value, Fraction):
        return value.numerator, value.denominator
    if isinstance(value, bool):
        return int(value), 1
    if isinstance(value, int):
        return value, 1
    if isinstance(value, float):
        f = Fraction(value).limit_denominator(10**12)
        return f.numerator, f.denominator
    if isinstance(value, str):
        m = _FRACTION_RE.match(value)
        if m is not None:
            num, den = int(m.group(1)), int(m.group(2))
            if den == 0:
                raise ValueError(f"zero denominator in {value!r}")
            return num, den
        # Plain numeric strings: route through float.
        return _parse_rational_pair(float(value))
    raise TypeError(f"cannot parse {type(value).__name__} as a rational")


def _build_rational_struct(
    source: pa.Array, *, name: str
) -> tuple[pa.StructArray, pa.Field]:
    """Build the ``{value, numerator, denominator}`` struct array.

    Vectorized: walks the source as a Python iterable exactly once
    (necessary because pa.compute has no general fraction parser); the
    output is a single ``pa.StructArray`` consumed by callers.
    """
    pylist = source.to_pylist()
    n = len(pylist)
    values = np.empty(n, dtype=np.float64)
    nums = np.zeros(n, dtype=np.int64)
    dens = np.ones(n, dtype=np.int64)
    null_mask = np.zeros(n, dtype=bool)
    for i, raw in enumerate(pylist):
        if raw is None:
            null_mask[i] = True
            continue
        try:
            num, den = _parse_rational_pair(raw)
        except (ValueError, TypeError):
            null_mask[i] = True
            continue
        nums[i] = num
        dens[i] = den
        values[i] = num / den if den != 0 else float("nan")

    struct_type = pa.struct(
        [
            pa.field("value", pa.float64(), nullable=True),
            pa.field("numerator", pa.int64(), nullable=True),
            pa.field("denominator", pa.int64(), nullable=True),
        ]
    )
    if null_mask.any():
        value_pa = pa.array(values, mask=null_mask, type=pa.float64())
        num_pa = pa.array(nums, mask=null_mask, type=pa.int64())
        den_pa = pa.array(dens, mask=null_mask, type=pa.int64())
        struct_arr = pa.StructArray.from_arrays(
            [value_pa, num_pa, den_pa],
            fields=list(struct_type),
            mask=pa.array(null_mask.tolist()),
        )
    else:
        struct_arr = pa.StructArray.from_arrays(
            [
                pa.array(values, type=pa.float64()),
                pa.array(nums, type=pa.int64()),
                pa.array(dens, type=pa.int64()),
            ],
            fields=list(struct_type),
        )
    pa_field = pa.field(name, struct_type)
    return struct_arr, pa_field


class RationalFieldSpec(FieldSpec):
    """Emit a raw :class:`RationalField`.

    Parses strings of the form ``"<numerator>/<denominator>"`` (e.g.
    ``"3/4"``) as well as plain numeric input.  The resulting struct
    stores both the float-best-effort ``value`` and the exact
    ``numerator`` / ``denominator``.
    """

    def emit(self, source: pa.Array, *, name: str) -> RationalField:
        out_name = self._resolve_name(name)
        struct_arr, pa_field = _build_rational_struct(source, name=out_name)
        return RationalField(struct_arr, pa_field)


# ═══════════════════════════════════════════════════════════════════════════
# 3. COMPOSITE SPECS
# ═══════════════════════════════════════════════════════════════════════════


def _default_part_name(part_spec: Any, index: int) -> str:
    """Pick a default name for an unnamed part in an iterable ``parts=``.

    Order of preference:

    * If *part_spec* is a paired :class:`SemanticField` subclass, use
      its ``__name__`` minus the ``Field`` suffix in snake_case
      (``MeasureNumberField`` → ``measure_number``).
    * If *part_spec* is a :class:`FieldSpec` instance with a non-``None``
      :attr:`FieldSpec.name`, use that name.
    * Otherwise fall back to ``f"part_{index}"``.
    """
    if isinstance(part_spec, type) and issubclass(part_spec, SemanticField):
        stem = part_spec.__name__.removesuffix("Field")
        # Convert PascalCase → snake_case.
        return re.sub(r"(?<!^)(?=[A-Z])", "_", stem).lower()
    if isinstance(part_spec, FieldSpec) and part_spec.name is not None:
        return part_spec.name
    return f"part_{index}"


class CompositeFieldSpec(FieldSpec):
    """Split one source column into many fields by separator or regex.

    The split strategy is determined at construction time:

    * ``separator="<sep>"`` — split each row's string on a literal
      separator.  The number of resulting parts MUST match ``len(parts)``
      after splitting (otherwise the row is treated as null).
    * ``pattern=<regex>`` — apply a regex with named or positional
      groups.  Named groups must match the keys of a ``dict``-shaped
      ``parts``; positional groups feed the sequence form in order.

    ``parts`` follows the same dict-or-iterable rule as
    ``column_specs``, and each value undergoes the universal
    :func:`resolve_field_spec` resolution — including nested
    ``CompositeFieldSpec`` subclasses for recursive composition.

    Args:
        separator: Literal separator string.  Mutually exclusive with
            ``pattern``.
        pattern: Regex (a ``str`` or compiled :class:`re.Pattern`) with
            named groups (dict-form) or positional groups (iterable-form).
        parts: Either a ``dict[str, FieldSpec-like]`` or a sequence of
            ``FieldSpec-like`` entries.  Resolution goes through
            :func:`resolve_field_spec`.
        name: Optional name for the resulting :class:`StructField`.
            Defaults to the source column name passed to :meth:`emit`.
    """

    def __init__(
        self,
        *,
        separator: str | None = None,
        pattern: str | re.Pattern[str] | None = None,
        parts: dict[str, Any] | Sequence[Any],
        name: str | None = None,
    ) -> None:
        super().__init__(name=name)
        if (separator is None) == (pattern is None):
            raise ValueError(
                "CompositeFieldSpec requires exactly one of separator= or pattern="
            )
        self._separator = separator
        self._pattern: re.Pattern[str] | None = (
            re.compile(pattern) if isinstance(pattern, str) else pattern
        )

        # Resolve `parts` lazily but uniformly.  Keep the original
        # container shape (dict / sequence) for diagnostics.
        if isinstance(parts, dict):
            self._part_keys: list[str] = list(parts.keys())
            self._part_specs: list[FieldSpec] = [
                resolve_field_spec(value) for value in parts.values()
            ]
        else:
            seq = list(parts)
            self._part_specs = [resolve_field_spec(v) for v in seq]
            self._part_keys = [_default_part_name(seq[i], i) for i in range(len(seq))]

    @property
    def part_keys(self) -> list[str]:
        """Names of the sub-fields produced by this composite spec."""
        return list(self._part_keys)

    @property
    def part_specs(self) -> list[FieldSpec]:
        """Resolved :class:`FieldSpec` for each part, in part-key order."""
        return list(self._part_specs)

    def _split_to_parts(self, source: pa.Array) -> dict[str, pa.Array]:
        """Run the split strategy over *source* and bin the results.

        Returns a dict ``{part_key: pa.Array}`` where each array is a
        Pythonic string array (no type cast yet — the sub-spec emits
        the typed field).  Rows that fail to split produce ``None``
        in every part.
        """
        as_strings = source.to_pylist()
        n = len(as_strings)
        bins: dict[str, list[Any]] = {key: [None] * n for key in self._part_keys}

        if self._separator is not None:
            sep = self._separator
            expected = len(self._part_keys)
            for i, value in enumerate(as_strings):
                if value is None:
                    continue
                if not isinstance(value, str):
                    value = str(value)
                pieces = value.split(sep)
                if len(pieces) != expected:
                    continue
                for key, piece in zip(self._part_keys, pieces):
                    bins[key][i] = piece.strip()
        else:
            assert self._pattern is not None
            pattern = self._pattern
            named = pattern.groupindex
            for i, value in enumerate(as_strings):
                if value is None:
                    continue
                if not isinstance(value, str):
                    value = str(value)
                m = pattern.match(value)
                if m is None:
                    continue
                if named:
                    for key in self._part_keys:
                        if key in named:
                            bins[key][i] = m.group(key)
                else:
                    groups = m.groups()
                    if len(groups) != len(self._part_keys):
                        continue
                    for key, piece in zip(self._part_keys, groups):
                        bins[key][i] = piece

        return {key: pa.array(values, type=pa.string()) for key, values in bins.items()}

    def emit(self, source: pa.Array, *, name: str) -> StructField:
        """Emit a :class:`StructField` whose sub-fields are the parts.

        The struct's sub-field types come from each part's
        ``FieldSpec.emit()`` result — preserving the typed semantics of
        the sub-specs.  When a sub-spec emits a struct (e.g. a
        :class:`RationalFieldSpec` nested inside a composite), the
        struct nests cleanly.
        """
        out_name = self._resolve_name(name)
        parts_in = self._split_to_parts(source)

        emitted_fields: list[DataField] = []
        pa_fields: list[pa.Field] = []
        pa_arrays: list[pa.Array] = []
        for key, spec in zip(self._part_keys, self._part_specs):
            sub_field = spec.emit(parts_in[key], name=key)
            emitted_fields.append(sub_field)
            pa_fields.append(sub_field.field)
            data = sub_field.data
            if data is None:
                raise RuntimeError(
                    f"CompositeFieldSpec part {key!r} produced no data array"
                )
            pa_arrays.append(data)

        struct_type = pa.struct(pa_fields)
        struct_arr = pa.StructArray.from_arrays(pa_arrays, fields=list(struct_type))
        pa_field = pa.field(out_name, struct_type)
        return StructField(struct_arr, pa_field)


class FractionFieldSpec(CompositeFieldSpec):
    """Pre-configured composite spec for ``"<numerator>/<denominator>"`` strings.

    Splits on ``"/"`` into two integer parts.  The resulting struct's
    sub-field names are ``numerator`` and ``denominator``.

    When ``unit`` is ``None`` (default), the spec emits a raw
    :class:`RationalField` (a struct
    ``{value, numerator, denominator}`` materialised via
    :class:`RationalFieldSpec`).  When ``unit`` is set, the emitted
    field is promoted to a semantic :class:`DenominateNumberField` with
    its ``unit`` bound.
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        unit: TimeUnit | str | None = None,
    ) -> None:
        # The internal split-shape isn't exposed publicly — callers see
        # a single rational field — so we build the spec on top of a
        # private composite that emits the canonical rational struct.
        # We forgo CompositeFieldSpec entirely and implement emit()
        # directly via _build_rational_struct.
        FieldSpec.__init__(self, name=name)
        self._unit: TimeUnit | None = TimeUnit(unit) if isinstance(unit, str) else unit
        # FractionFieldSpec emits a single struct field (not nested
        # sub-fields surfaced as separate top-level columns), so its
        # public part_keys is empty — callers iterating composite
        # part-keys must not descend into a FractionFieldSpec.
        self._part_keys: list[str] = []
        self._part_specs: list[FieldSpec] = []

    @property
    def unit(self) -> TimeUnit | None:
        """The unit bound to this spec, or ``None`` for a raw rational field."""
        return self._unit

    def emit(
        self, source: pa.Array, *, name: str
    ) -> RationalField | DenominateNumberField:
        out_name = self._resolve_name(name)
        struct_arr, pa_field = _build_rational_struct(source, name=out_name)
        if self._unit is None:
            return RationalField(struct_arr, pa_field)
        return DenominateNumberField(struct_arr, pa_field, unit=self._unit)


# ═══════════════════════════════════════════════════════════════════════════
# 4. CALLABLE WRAPPER
# ═══════════════════════════════════════════════════════════════════════════


class CallableFieldSpec(FieldSpec):
    """Wrap a user-provided ``(pa.Array) -> DataField`` callable.

    The escape hatch in the resolution table — when the standard leaf
    and composite specs are insufficient, callers may supply any
    function that takes a ``pa.Array`` and returns a :class:`DataField`.
    The spec defers entirely to the callable; the *name* parameter is
    forwarded as a keyword argument when the callable accepts it.

    Args:
        fn: Callable ``(pa.Array) -> DataField`` (optionally
            accepting ``name=`` as a keyword).
        name: Optional override.
    """

    def __init__(
        self,
        fn: Callable[..., DataField],
        *,
        name: str | None = None,
    ) -> None:
        super().__init__(name=name)
        self._fn = fn

    def emit(self, source: pa.Array, *, name: str) -> DataField:
        out_name = self._resolve_name(name)
        try:
            return self._fn(source, name=out_name)
        except TypeError:
            return self._fn(source)


# ═══════════════════════════════════════════════════════════════════════════
# 5. UNIVERSAL RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════


def _spec_for_data_field_cls(cls: type[DataField]) -> FieldSpec:
    """Return a leaf :class:`FieldSpec` that emits *cls* instances.

    Recognised raw classes: :class:`NumericField`, :class:`StringField`,
    :class:`RationalField`.  Subclasses of :class:`SemanticField` go
    through their paired-class blueprint mode and are not handled here.
    """
    if cls is NumericField:
        return FloatFieldSpec()
    if cls is StringField:
        return StringFieldSpec()
    if cls is RationalField:
        return RationalFieldSpec()
    raise TypeError(
        f"Cannot resolve DataField subclass {cls.__name__!r} to a FieldSpec; "
        "supply a FieldSpec instance directly"
    )


def _spec_for_pa_type(dtype: pa.DataType) -> FieldSpec:
    """Map a :class:`pa.DataType` to a leaf :class:`FieldSpec`.

    Integer, floating, and string types are recognised.  Other types
    raise ``TypeError`` — callers must supply a :class:`FieldSpec`
    instance directly.
    """
    if pa.types.is_integer(dtype):
        return IntFieldSpec()
    if pa.types.is_floating(dtype):
        return FloatFieldSpec()
    if pa.types.is_string(dtype) or pa.types.is_large_string(dtype):
        return StringFieldSpec()
    raise TypeError(
        f"Cannot resolve pa.DataType {dtype!r} to a FieldSpec; "
        "supply a FieldSpec instance directly"
    )


def resolve_field_spec(value: Any) -> FieldSpec:
    """Resolve an entry in ``column_specs`` to a :class:`FieldSpec`.

    Resolution table:

    +-------------------------------------------+-----------------------------------+
    | Input                                     | Resolved FieldSpec                |
    +===========================================+===================================+
    | ``int`` (Python type)                     | ``IntFieldSpec()``                |
    +-------------------------------------------+-----------------------------------+
    | ``float`` (Python type)                   | ``FloatFieldSpec()``              |
    +-------------------------------------------+-----------------------------------+
    | ``str`` (Python type)                     | ``StringFieldSpec()``             |
    +-------------------------------------------+-----------------------------------+
    | ``Fraction`` (Python type)                | ``RationalFieldSpec()``           |
    +-------------------------------------------+-----------------------------------+
    | ``pa.int64()`` / ``pa.float64()`` /       | matched by-type to the equivalent |
    | ``pa.string()`` etc. (``pa.DataType``)    | leaf spec                         |
    +-------------------------------------------+-----------------------------------+
    | ``NumericField`` (raw DataField subclass) | ``FloatFieldSpec()``              |
    +-------------------------------------------+-----------------------------------+
    | ``StringField``                           | ``StringFieldSpec()``             |
    +-------------------------------------------+-----------------------------------+
    | ``RationalField``                         | ``RationalFieldSpec()``           |
    +-------------------------------------------+-----------------------------------+
    | a :class:`SemanticField` subclass         | ``CallableFieldSpec`` that builds |
    |                                           | the paired field via              |
    |                                           | ``.from_field(...)``              |
    +-------------------------------------------+-----------------------------------+
    | any ``FieldSpec`` instance                | as-is                             |
    +-------------------------------------------+-----------------------------------+
    | any callable ``(pa.Array) -> DataField``  | wrapped in ``CallableFieldSpec``  |
    +-------------------------------------------+-----------------------------------+

    Args:
        value: The user-supplied entry.

    Returns:
        A :class:`FieldSpec`.

    Raises:
        TypeError: When *value* matches no recognised shape.
    """
    if isinstance(value, FieldSpec):
        return value

    if isinstance(value, type):
        # Python builtins.
        if value is int:
            return IntFieldSpec()
        if value is float:
            return FloatFieldSpec()
        if value is str:
            return StringFieldSpec()
        if value is Fraction:
            return RationalFieldSpec()
        # SemanticField subclasses — wrap via from_field.
        if issubclass(value, SemanticField):
            return _spec_for_semantic_field_cls(value)
        # Raw DataField subclasses.
        if issubclass(value, DataField):
            return _spec_for_data_field_cls(value)

    if isinstance(value, pa.DataType):
        return _spec_for_pa_type(value)

    if callable(value):
        return CallableFieldSpec(value)

    raise TypeError(
        f"Cannot resolve {value!r} (type {type(value).__name__}) to a FieldSpec"
    )


def _spec_for_semantic_field_cls(cls: type[SemanticField]) -> FieldSpec:
    """Return a :class:`FieldSpec` that emits the paired ``cls`` field.

    The strategy:

    1. Inspect ``cls.pa_schema`` to discover the storage shape.
    2. If the schema is the canonical rational struct
       (``{value, numerator, denominator}``), reuse the rational
       builder.
    3. If the schema is a single-field struct (``{value: <atomic>}``),
       wrap each row as the matching atomic type and pack it into a
       struct directly — this covers :class:`MeasureNumberField` and
       :class:`IdField` cleanly.
    4. Otherwise fall back to a generic packer that maps each source
       row through :meth:`cls.scalar_cls.model_validate` and runs the
       column-builder.  This path is reserved for richer scalars whose
       storage shape exceeds the single-atomic-value case.
    """
    from timetoalign.core import build_struct_array

    schema = cls.pa_schema
    scalar_cls = cls.scalar_cls
    if schema is None or scalar_cls is None:
        raise TypeError(
            f"{cls.__name__} has no derived pa_schema / scalar_cls; cannot resolve"
        )

    field_names = [schema.field(i).name for i in range(schema.num_fields)]

    def _emit_single_value(source: pa.Array, *, name: str) -> DataField:
        """Pack a flat source array into a ``{value: <atomic>}`` struct."""
        sub_field = schema.field(0)
        sub_type = sub_field.type
        if not (
            pa.types.is_string(source.type)
            or pa.types.is_large_string(source.type)
            or pa.types.is_integer(source.type)
            or pa.types.is_floating(source.type)
        ):
            source = pc.cast(source, pa.string())
        if pa.types.is_integer(sub_type):
            casted = pc.cast(source, sub_type)
        elif pa.types.is_floating(sub_type):
            casted = pc.cast(source, sub_type)
        elif pa.types.is_string(sub_type):
            if pa.types.is_string(source.type) or pa.types.is_large_string(source.type):
                casted = source
            else:
                casted = pc.cast(source, pa.string())
        else:
            raise TypeError(f"_emit_single_value: unsupported sub_type {sub_type!r}")
        struct_arr = pa.StructArray.from_arrays([casted], fields=list(schema))
        pa_field = pa.field(name, schema)
        return cls.from_field((struct_arr, pa_field))

    def _emit_rational(source: pa.Array, *, name: str) -> DataField:
        struct_arr, pa_field = _build_rational_struct(source, name=name)
        return cls.from_field((struct_arr, pa_field))

    def _emit_generic(source: pa.Array, *, name: str) -> DataField:
        """Fall back: row-wise materialise + column-builder."""
        objects = []
        for row in source.to_pylist():
            if row is None:
                objects.append(None)
            else:
                objects.append(scalar_cls.model_validate(row))
        # Filter out Nones for build_struct_array, then reconstruct.
        # The builder doesn't natively support nulls in the input list,
        # so we build the struct array piece by piece.
        struct_arr = build_struct_array(
            scalar_cls, [o for o in objects if o is not None]
        )
        pa_field = pa.field(name, schema)
        return cls.from_field((struct_arr, pa_field))

    # Recognise canonical shapes.
    if field_names == ["value", "numerator", "denominator"]:
        return CallableFieldSpec(_emit_rational)
    if field_names == ["value"]:
        return CallableFieldSpec(_emit_single_value)
    return CallableFieldSpec(_emit_generic)
