"""Regression tests for exact arithmetic on time scalar fields."""

from __future__ import annotations

from fractions import Fraction

import pyarrow as pa

from timetoalign.core.enums import NumberType, TimeUnit
from timetoalign.core.time import Coordinate, CoordinateField, Duration, DurationField

_COORDINATE_TYPE = pa.struct(
    [
        pa.field("value", pa.float64()),
        pa.field("numerator", pa.int64()),
        pa.field("denominator", pa.int64()),
    ]
)


def _field(values: list[dict[str, object] | None]) -> CoordinateField:
    """Build a coordinate field with explicit rational storage rows."""
    return CoordinateField.from_field(
        pa.array(values, type=_COORDINATE_TYPE),
        unit=TimeUnit.quarters,
        number_type=NumberType.fraction,
    )


def test_exact_field_subtraction_populates_reduced_pairs() -> None:
    """Exact coordinate subtraction stores both the result and its pair."""
    left = _field([{"value": 1 / 3, "numerator": 1, "denominator": 3}])
    right = _field([{"value": 1 / 6, "numerator": 1, "denominator": 6}])

    result = left - right
    row = result.to_pyarrow()[0].as_py()

    assert row == {"value": 1 / 6, "numerator": 1, "denominator": 6}
    assert result[0].value == Fraction(1, 6)


def test_exact_field_addition_populates_reduced_pairs() -> None:
    """Exact duration addition stores the reduced rational result."""
    left = DurationField.from_field(
        pa.array(
            [{"value": 1 / 3, "numerator": 1, "denominator": 3}],
            type=_COORDINATE_TYPE,
        ),
        unit=TimeUnit.quarters,
        number_type=NumberType.fraction,
    )
    right = DurationField.from_field(
        pa.array(
            [{"value": 1 / 6, "numerator": 1, "denominator": 6}],
            type=_COORDINATE_TYPE,
        ),
        unit=TimeUnit.quarters,
        number_type=NumberType.fraction,
    )

    row = (left + right).to_pyarrow()[0].as_py()

    assert row == {"value": 0.5, "numerator": 1, "denominator": 2}


def test_mixed_field_rows_keep_exact_pairs_only_where_possible() -> None:
    """Rows with a float operand remain value-only while exact rows persist."""
    left = _field(
        [
            {"value": 1 / 3, "numerator": 1, "denominator": 3},
            {"value": 1.5, "numerator": None, "denominator": None},
        ]
    )
    right = _field(
        [
            {"value": 1 / 6, "numerator": 1, "denominator": 6},
            {"value": 0.25, "numerator": None, "denominator": None},
        ]
    )

    rows = (left - right).to_pyarrow().to_pylist()

    assert rows[0] == {"value": 1 / 6, "numerator": 1, "denominator": 6}
    assert rows[1] == {"value": 1.25, "numerator": None, "denominator": None}


def test_scalar_fraction_arithmetic_is_exact() -> None:
    """Coordinate and Duration scalar operations retain Fraction values."""
    coordinate = Coordinate(Fraction(1, 3), TimeUnit.quarters)
    duration = Duration(Fraction(1, 6), TimeUnit.quarters)

    assert (coordinate + duration).value == Fraction(1, 2)
    assert (coordinate - duration).value == Fraction(1, 6)
    assert (duration + Fraction(1, 3)).value == Fraction(1, 2)


def test_float_operands_do_not_get_fabricated_pairs() -> None:
    """Float field arithmetic produces a convenience value without a pair."""
    field = _field([{"value": 1 / 3, "numerator": 1, "denominator": 3}])

    row = (field + 0.25).to_pyarrow()[0].as_py()

    assert row["value"] == 1 / 3 + 0.25
    assert row["numerator"] is None
    assert row["denominator"] is None
