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

The two WP2 pilot scalars use this module via:

* :func:`build_struct_array` for a generic pydantic scalar.
* :func:`build_coordinate_struct_array` for the special-case ``Coordinate``
  whose storage shape denormalises ``value`` into three fields.

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

    ``None`` entries in *objects* are represented as null struct entries.
    The struct type matches :func:`derive_arrow_struct` for *model_cls*,
    so the result is guaranteed to round-trip through the corresponding
    SemanticField.

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
    field_names = list(model_cls.model_fields.keys())
    # One column per pydantic field name.  We pull attributes directly via
    # ``getattr`` so pydantic's frozen storage layout is irrelevant — this
    # is identical to ``model_dump`` field-wise but skips dict-creation
    # cost per row.
    columns: dict[str, list[Any]] = {name: [] for name in field_names}
    null_mask: list[bool] = []
    for obj in objects:
        if obj is None:
            null_mask.append(True)
            for name in field_names:
                columns[name].append(None)
            continue
        if not isinstance(obj, model_cls):
            raise TypeError(
                f"Expected {model_cls.__name__} (or None), got " f"{type(obj).__name__}"
            )
        null_mask.append(False)
        for name in field_names:
            columns[name].append(getattr(obj, name))
    arrow_struct = derive_arrow_struct(model_cls)
    field_arrays = [
        pa.array(columns[child.name], type=child.type) for child in arrow_struct
    ]
    return pa.StructArray.from_arrays(
        field_arrays,
        fields=list(arrow_struct),
        mask=pa.array(null_mask) if any(null_mask) else None,
    )


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
