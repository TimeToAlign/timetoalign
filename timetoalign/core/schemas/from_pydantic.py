"""Hand-rolled minimal pydantic v2 → PyArrow translator.

Why hand-rolled (not the external ``pydantic-to-pyarrow`` package):

* ``pydantic-to-pyarrow`` (v0.1.6, alpha) maps ``Literal[str, ...]`` to
  ``pa.dictionary(int32, string)``; TTA's existing schemas use plain
  ``pa.string()`` for these columns (``SpecificPitch.step`` is the pilot
  case).  Adopting dict-encoding silently here would break Parquet
  round-trips and downstream DCML interop.
* ``Coordinate.value`` is typed ``int | float | Fraction`` at the scalar
  level but is stored as a 3-field denormalised struct
  (``{value, numerator, denominator}``) in PyArrow to preserve rational
  precision.  The external translator has no hook for this projection;
  this module exposes :func:`register_value_projector` so each pilot
  scalar can register its own field-expansion rule.
* Workshop scalars (``Note``, ``Measure``, ``MidiEvent`` in WP7) need
  nested ``BaseModel`` fields — the projector registry is the
  extension point.

**Supported field shapes:**

* ``str``                       → ``pa.string()`` (not dictionary-encoded)
* ``int``                       → ``pa.int64()``
* ``float``                     → ``pa.float64()``
* ``bool``                      → ``pa.bool_()``
* ``Optional[T]`` /
  ``T | None``                  → nullable variant of ``T``'s mapping
* ``Literal[str, ...]``         → ``pa.string()`` (NOT dictionary)
* ``Literal[int, ...]``         → ``pa.int64()``
* Nested ``BaseModel``          → ``pa.struct(_derive_arrow_fields(inner))``
* ``tuple[T, ...]`` (variadic)  → ``pa.list_(atomic_T)``
* ``tuple[T1, T2, ...]`` (fixed)→ ``pa.struct({_0, _1, …})`` (positional names)
* Registered value projectors   → multi-field struct expansion / drop
* ``computed_field`` properties → omitted (NOT in pa.Schema)

**NOT yet supported — extend this module rather than reaching outside:**

* ``datetime``, ``Decimal``, ``UUID``, ``bytes``.
* Discriminated unions across ``BaseModel`` subclasses — explicitly
  forbidden by the WP2 plan.  Use a value-projector returning ``[]`` to
  drop the field from the pa.Schema (columnar separation at the
  EventData level handles polymorphism).
* Generic ``list[T]`` / ``dict[K, V]`` outside the variadic-tuple
  shortcut.

The per-pilot value-projector hook generalises cleanly when a new
unsupported shape appears.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from typing import Any, Callable, Literal, get_args, get_origin

import pyarrow as pa
from pydantic import BaseModel
from pydantic.fields import FieldInfo

# ---------------------------------------------------------------------------
# Value-projector registry
# ---------------------------------------------------------------------------

# A value projector maps a single pydantic field to a *sequence* of
# ``pa.Field`` entries that will replace the field in the derived struct.
# Used by ``Coordinate``: the scalar's single ``value: int|float|Fraction``
# field expands to three storage fields ``{value, numerator, denominator}``
# inside the Arrow struct.  An empty list drops the field entirely
# (used to keep e.g. ``Note.pitch`` out of the pa.Schema while preserving
# the Python annotation).
#
# Registry key: (scalar_model_cls, field_name)
# Registry value: callable returning a list[pa.Field] (the replacement
# fields, in order).
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
    # Invalidate the cached derivation for this class.
    _derive_arrow_fields.cache_clear()


# ---------------------------------------------------------------------------
# Translator core
# ---------------------------------------------------------------------------


def _is_tuple_type(py_type: Any) -> bool:
    origin = get_origin(py_type)
    return origin is tuple


def _atomic_arrow_type(py_type: Any) -> pa.DataType:
    """Map a pydantic atomic / structural type annotation to a ``pa.DataType``.

    Handles atomic primitives, ``Literal``, nested ``BaseModel``, and
    ``tuple[...]`` shapes.

    Args:
        py_type: The (possibly-Optional-unwrapped) Python type.

    Returns:
        The corresponding PyArrow data type.

    Raises:
        TypeError: If *py_type* is not a supported atomic/structural type.
    """
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
            # WP2 contract: Literal[str, ...] -> pa.string()  (NOT dictionary).
            return pa.string()
        if all(isinstance(a, int) for a in args):
            return pa.int64()
        raise TypeError(
            f"Mixed-type Literal not supported in pa.Schema derivation: {py_type!r}"
        )

    # Nested pydantic model -> pa.struct of its derived fields.
    if isinstance(py_type, type) and issubclass(py_type, BaseModel):
        return pa.struct(_derive_arrow_fields(py_type))

    # tuple[T, ...] (variable length) -> pa.list_(T).
    # tuple[T1, T2, ...] (fixed)       -> pa.struct({_0, _1, ...}).
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
        "encounters them — extend timetoalign.core.schemas.from_pydantic."
    )


def _unwrap_optional(py_type: Any) -> tuple[Any, bool]:
    """Return (inner_type, nullable) for ``T | None`` / ``Optional[T]``.

    For non-optional annotations, returns ``(py_type, False)``.  Unions
    of more than one non-None arm raise: discriminated unions of
    ``BaseModel`` subclasses are explicitly forbidden under the WP2
    plan (resolve via columnar separation + a value-projector
    returning ``[]``).

    Args:
        py_type: A pydantic field's annotation.

    Returns:
        Tuple of (inner type, whether the field is nullable).
    """
    origin = get_origin(py_type)
    # Python 3.10+ ``X | None`` uses types.UnionType, ``Union[X, None]`` uses
    # typing.Union.  Both expose args through ``get_args``.
    union_type = getattr(sys.modules.get("types"), "UnionType", None)
    is_union = origin is union_type or (
        origin is not None and getattr(origin, "__name__", None) == "Union"
    )
    if not is_union:
        return py_type, False
    args = [a for a in get_args(py_type) if a is not type(None)]
    if len(args) != 1:
        # Detect the forbidden case (union of BaseModels) and emit a
        # pointer to the columnar-separation rule.
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
    describes a columnar storage where nulls are first-class (a null
    parent struct entry means there is no scalar at that row, and the
    child arrays must also accept null at the same offset).  Per-row
    completeness is re-enforced at construction time via
    ``Model.model_validate`` (trust-boundary regime) or by trusting the
    pa.Schema contract (internal round-trip via ``model_construct``).
    """
    out: list[pa.Field] = []
    for name, info in model_cls.model_fields.items():
        # Value-projector hook (e.g. Coordinate.value -> 3 storage fields,
        # Note.pitch -> [] to drop the field).
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
        # All fields nullable=True: columnar storage allows null at the
        # row level (driven by the parent struct's null bitmap).  Pydantic
        # ``required`` is re-checked when the scalar is materialised.
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
    :func:`timetoalign.core.schemas.parquet_metadata.parquet_metadata_for_model`
    when constructing the ``pa.Field`` that holds the struct.

    Args:
        model_cls: A pydantic v2 ``BaseModel`` subclass.

    Returns:
        ``pa.Schema`` of the model.
    """
    return pa.schema(_derive_arrow_fields(model_cls))
