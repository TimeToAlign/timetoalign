"""Helpers for preserving exact coordinate structs during engine operations."""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from timetoalign.core.fields import (
    coordinate_to_struct,
    struct_to_rational,
    wire_to_rational,
)


def exact_coordinate_value(value: Any) -> Fraction | None:
    """Return an exact coordinate value when one is available."""
    if isinstance(value, dict):
        try:
            return struct_to_rational(value)
        except (TypeError, ValueError, ZeroDivisionError):
            return None
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return Fraction(value, 1)
    return None


def coordinate_numeric_value(value: Any) -> Fraction | float:
    """Return the authoritative numeric value represented by a coordinate."""
    exact = exact_coordinate_value(value)
    if exact is not None:
        return exact
    if isinstance(value, dict):
        return wire_to_rational(value)
    if hasattr(value, "value"):
        return value.value
    return float(value)


def shift_coordinate(value: Any, offset: Any, *, subtract: bool) -> dict[str, Any]:
    """Shift a coordinate and rebuild its complete Arrow struct.

    Exact arithmetic is used only when both operands carry exact values. Any
    operation involving an inexact float returns a struct with a null rational
    pair, preserving the distinction between exact and approximate values.
    """
    value_exact = exact_coordinate_value(value)
    offset_exact = exact_coordinate_value(offset)
    if value_exact is not None and offset_exact is not None:
        result = value_exact - offset_exact if subtract else value_exact + offset_exact
        return coordinate_to_struct(result)

    value_float = float(coordinate_numeric_value(value))
    offset_float = float(coordinate_numeric_value(offset))
    result_float = (
        value_float - offset_float if subtract else value_float + offset_float
    )
    return coordinate_to_struct(result_float)


def subtract_coordinates(left: Any, right: Any) -> dict[str, Any]:
    """Return a complete coordinate struct for ``left - right``."""
    return shift_coordinate(left, right, subtract=True)
