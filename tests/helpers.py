"""Helpers shared across the whole test suite."""

from __future__ import annotations

from typing import Any

import pyarrow as pa

from timetoalign.core import (
    NumberType,
    build_number_struct_array,
    struct_to_coordinate,
    timestamp_table_to_dataframe,
)


def table_column(table: pa.Table, name: str) -> list[Any]:
    """Return one timestamp-table column as plain scalars.

    Timestamp-table cells are coordinate structs, so ``to_pylist()`` on a
    column yields one dict per row. Tests that care about positions read the
    column through the library's own decoding boundary instead, which is what
    a user reading the table gets.
    """
    frame = timestamp_table_to_dataframe(table, units=False)
    return frame[name].tolist()


def coordinate_values(
    column: pa.Array | pa.ChunkedArray,
    number_type: NumberType = NumberType.float,
) -> list[Any]:
    """Return a coordinate column's positions in one declared representation.

    The axis-collecting helpers carry storage cells, not bare numbers, so a
    test asserting positions has to say which side of the cell it means. That
    is the same thing every reader of a column does, and it is declared, not
    guessed from the digits.
    """
    if isinstance(column, pa.ChunkedArray):
        column = column.combine_chunks()
    return [
        None if cell is None else struct_to_coordinate(cell, number_type)
        for cell in column.to_pylist()
    ]


def coordinate_column(
    values: Any, number_type: NumberType = NumberType.float
) -> pa.StructArray:
    """Encode positions as a coordinate column under one declared type."""
    return build_number_struct_array(values, number_type=number_type)
