"""Bulk SemanticField construction via the column-builder pattern.

The column-builder pattern is the **only** sanctioned path for building
a SemanticField from many already-validated scalar instances.  Row-wise
``model_dump`` is *forbidden* by the WP2 plan (it is the slowest Arrow
construction path; the microbenchmark gates the bulk migration).

Pattern (canonical form)::

    {name: pa.array([getattr(o, name) for o in objects]) for name in T.model_fields}

This builds one ``pa.Array`` per pydantic field, then assembles them into
a ``pa.StructArray`` using the pa.Schema derived from ``T``.  Computed
fields are NOT included; only ``T.model_fields`` (declared fields) drive
the construction, matching the schema derived by
:mod:`timetoalign.core.schemas.from_pydantic`.

Nested ``BaseModel`` fields (e.g. ``Note.start: Coordinate``) recurse via
:func:`build_struct_array` — the column is materialised as a nested
``pa.StructArray`` rather than a list of Python dicts.  The
``Coordinate`` projector hook is honoured during recursion so that the
denormalised ``{value, numerator, denominator}`` storage shape is
produced from the in-memory ``Coordinate`` objects.

Public surface:

* :func:`build_struct_array` for a generic pydantic scalar.
* :func:`build_coordinate_struct_array` for ``Coordinate`` (kept as an
  explicit entry point — also used as the inner recursion target for any
  scalar that nests ``Coordinate`` or ``Duration``).

When the bulk migration encounters new scalars, they call
:func:`build_struct_array` directly; the function reads
``T.model_fields`` so any scalar lands automatically.
"""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING, Any, Iterable, Sequence

import pyarrow as pa
from pydantic import BaseModel

from .from_pydantic import derive_arrow_struct

if TYPE_CHECKING:
    from ..types import Coordinate


# ---------------------------------------------------------------------------
# Generic column-builder
# ---------------------------------------------------------------------------


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
    ``Note.pitch``) are honoured: a field with a registered projector
    skips the attribute and lets the recursive build of the nested
    Coordinate / Duration drive the column build for that slot.

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
    # Validate types and build null mask first so each column-builder gets
    # a clean list of (instance | None) at the parent level.
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
    # Group pa.Schema fields by their producing pydantic field so the
    # builder can call the right sub-routine once per pydantic field and
    # spread its outputs across the pa.Schema slots it owns.
    sub_blocks = _group_pa_fields_by_pydantic_field(model_cls, pa_fields)

    for py_field_name, pa_block in sub_blocks.items():
        if py_field_name is None:
            raise TypeError(
                "pa.Schema field cannot be mapped back to a pydantic field; "
                "extend the column-builder for this projector shape."
            )

        py_field_info = model_cls.model_fields[py_field_name]
        # Pull the attribute column-wise once.
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


# ---------------------------------------------------------------------------
# Per-field builders
# ---------------------------------------------------------------------------


def _group_pa_fields_by_pydantic_field(
    model_cls: type[BaseModel],
    pa_fields: list[pa.Field],
) -> "dict[str | None, list[pa.Field]]":
    """Map each ``pa.Field`` back to the pydantic field that produced it.

    For most fields the mapping is by-name.  For projector-replaced
    fields the projector returns a list of ``pa.Field``s whose names do
    NOT match the original pydantic field; we identify those by exclusion
    (any pa field whose name is not in ``model_fields``) and assign them
    to the first projector-owning pydantic field whose registered
    projector emitted them.
    """
    pyd_names = list(model_cls.model_fields.keys())
    pyd_name_set = set(pyd_names)
    out: dict[str | None, list[pa.Field]] = {n: [] for n in pyd_names}

    # First pass: pa fields whose name matches a pydantic field name
    # (the common case).  Direct match.
    matched_pa: list[pa.Field] = []
    for pf in pa_fields:
        if pf.name in pyd_name_set:
            out[pf.name].append(pf)
            matched_pa.append(pf)

    leftover = [pf for pf in pa_fields if pf not in matched_pa]
    if not leftover:
        return {k: v for k, v in out.items() if v}

    # Remaining pa fields come from projectors.  Re-run each registered
    # projector to find which pydantic field owns which pa.Field block.
    from .from_pydantic import _VALUE_PROJECTORS as projectors

    for pyd_name in pyd_names:
        proj = projectors.get((model_cls, pyd_name))
        if proj is None:
            continue
        emitted = proj(model_cls, pyd_name, model_cls.model_fields[pyd_name])
        emitted_names = [f.name for f in emitted]
        if not emitted_names:
            # Drop-projector → no pa.Field; nothing to assign.
            continue
        # Move every leftover pa.Field whose name appears in *emitted_names*
        # to this pydantic field.
        captured = [pf for pf in leftover if pf.name in emitted_names]
        for pf in captured:
            out[pyd_name].append(pf)
        leftover = [pf for pf in leftover if pf not in captured]

    if leftover:
        # Unmapped pa.Field — should never happen if the projector contract
        # holds.  Surface clearly rather than silently producing a wrong
        # column.
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
    """Produce one or more ``pa.Array`` for a single pydantic field's slot.

    The number of arrays returned MUST equal ``len(pa_subfields)`` and
    each array's type MUST match the corresponding pa.Field.
    """
    if not pa_subfields:
        return []

    # Special case: Coordinate / Duration nested in another scalar.  The
    # projector denormalises ``value`` into three columns; ``unit`` is
    # dropped.  Build via the dedicated Coordinate / Duration builder so
    # rational precision survives.
    from ..types import Coordinate

    annotation = field_info.annotation
    inner_type, _nullable = _unwrap_optional_annotation(annotation)

    if isinstance(inner_type, type) and issubclass(inner_type, BaseModel):
        # Nested BaseModel: build via recursion.
        if issubclass(inner_type, Coordinate) or _is_duration_type(inner_type):
            return [_build_coordinate_like_column(inner_type, values)]
        # Generic nested BaseModel: recursive build_struct_array, which
        # returns a single StructArray for this slot.
        sub_array = build_struct_array(inner_type, values)
        return [sub_array]

    # Atomic / tuple / list — single pa.Array via direct conversion.
    if len(pa_subfields) != 1:
        raise TypeError(
            f"Cannot build {len(pa_subfields)} arrays for atomic pydantic field "
            f"{model_cls.__name__}.{field_name}"
        )
    pa_field = pa_subfields[0]
    # Tuples: convert to list-of-2 for fixed-length struct, list-of-N for
    # variadic list type.
    pa_type = pa_field.type
    if pa.types.is_struct(pa_type) and all(
        pa_type.field(i).name == f"_{i}" for i in range(pa_type.num_fields)
    ):
        # Positional struct from fixed-length tuple.  Convert each value
        # to {_0: ..., _1: ..., ...}.
        n = pa_type.num_fields
        rows: list[Any] = []
        for v in values:
            if v is None:
                rows.append(None)
            else:
                rows.append({f"_{i}": v[i] for i in range(n)})
        return [pa.array(rows, type=pa_type)]
    if pa.types.is_list(pa_type):
        # Variadic tuple → list.
        rows = []
        for v in values:
            rows.append(None if v is None else list(v))
        return [pa.array(rows, type=pa_type)]
    # Plain atomic.
    return [pa.array(values, type=pa_type)]


def _unwrap_optional_annotation(annotation: Any) -> tuple[Any, bool]:
    import sys
    from typing import get_args, get_origin

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


def _is_duration_type(tp: type) -> bool:
    """Detect ``Duration`` without a hard import (avoids circular imports)."""
    return tp.__name__ == "Duration" and tp.__module__.endswith(".scalars.duration")


def _build_coordinate_like_column(cls: type, values: list[Any]) -> pa.StructArray:
    """Build the denormalised storage struct for ``Coordinate`` or ``Duration``.

    Shared code path so both scalars produce identical storage shapes.
    """
    return build_coordinate_struct_array(values)


# ---------------------------------------------------------------------------
# Coordinate-specific column-builder
# ---------------------------------------------------------------------------


def build_coordinate_struct_array(
    objects: "Iterable[Coordinate | None]",
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
        objects: An iterable of ``Coordinate`` instances (or ``None``).

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
    # Build the per-field arrays explicitly so the result matches the
    # ``derive_arrow_struct(Coordinate)`` shape exactly.  All children
    # are nullable=True so that null parent struct entries round-trip
    # cleanly through Parquet.
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
