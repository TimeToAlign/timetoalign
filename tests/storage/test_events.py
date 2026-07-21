"""Exact-value tests for ``EventData.column_values()``.

See ``README.md`` for the documented contract.
"""

from __future__ import annotations

from fractions import Fraction

import pyarrow as pa

from timetoalign.core import TimeUnit
from timetoalign.storage.events import EventData


class TestColumnValues:
    """Decoded, plain-Python column reads via ``column_values()``."""

    def _data(self) -> EventData:
        return EventData.from_dicts(
            [
                {
                    "event_type": "Note",
                    "start": 0,
                    "duration": Fraction(1, 3),
                    "flag": True,
                },
                {
                    "event_type": "Note",
                    "start": 0,
                    "duration": 0.1,
                    "flag": None,
                },
                {
                    "event_type": "Beat",
                    "instant": 0,
                    "flag": False,
                },
            ],
            unit=TimeUnit.quarters,
        )

    def test_rational_column_decodes_exact_fraction(self) -> None:
        data = self._data()
        values = data.column_values("duration", default=Fraction(0))
        assert values[0] == Fraction(1, 3)

    def test_rational_column_falls_back_to_float_value(self) -> None:
        data = self._data()
        values = data.column_values("duration", default=Fraction(0))
        # duration=0.1 carries no exact numerator/denominator, so the
        # float `value` is used, wrapped in a Fraction.
        assert values[1] == Fraction(0.1)

    def test_null_coordinate_cell_yields_default(self) -> None:
        data = self._data()
        values = data.column_values("duration", default=Fraction(4))
        # The instant event has no duration at all.
        assert values[2] == Fraction(4)

    def test_null_plain_cell_passes_through_as_none(self) -> None:
        # `default` only substitutes for a missing *column* or a null
        # coordinate struct; a null plain-column cell is not a coordinate
        # struct, so it passes through as `None` from `to_pylist()`.
        data = self._data()
        values = data.column_values("flag", default="missing")
        assert values == [True, None, False]

    def test_missing_column_yields_default_list(self) -> None:
        data = self._data()
        values = data.column_values("no_such_column", default="fallback")
        assert values == ["fallback"] * len(data)

    def test_non_coordinate_column_passes_through(self) -> None:
        data = self._data()
        assert data.column_values("event_type") == ["Note", "Note", "Beat"]


class TestIntervalFractionFidelity:
    """Validate exact pairs produced while completing interval coordinates."""

    @staticmethod
    def _pairs(data: EventData, name: str) -> list[tuple[int | None, int | None]]:
        """Return numerator/denominator pairs from a coordinate column."""
        column = data._table.column(name).combine_chunks()
        return list(
            zip(
                column.field("numerator").to_pylist(),
                column.field("denominator").to_pylist(),
                strict=True,
            )
        )

    @staticmethod
    def _coord_type() -> pa.StructType:
        """Return the canonical coordinate struct type used by the test arrays."""
        return pa.struct(
            [
                pa.field("value", pa.float64()),
                pa.field("numerator", pa.int64()),
                pa.field("denominator", pa.int64()),
            ]
        )

    def test_from_dicts_computes_exact_end(self) -> None:
        """Compute an exact end from exact start and duration structs."""
        data = EventData.from_dicts(
            [
                {
                    "event_type": "Note",
                    "start": {
                        "value": 3.5,
                        "numerator": 7,
                        "denominator": 2,
                    },
                    "duration": {
                        "value": 0.75,
                        "numerator": 3,
                        "denominator": 4,
                    },
                }
            ],
            unit=TimeUnit.quarters,
        )

        assert data.column_values("end") == [Fraction(17, 4)]
        assert self._pairs(data, "end") == [(17, 4)]

    def test_from_arrays_computes_exact_end(self) -> None:
        """Compute an exact end in the vectorized construction path."""
        coord_type = self._coord_type()
        data = EventData.from_arrays(
            {
                "id": ["exact"],
                "event_type": ["Note"],
                "start": pa.array(
                    [{"value": 3.5, "numerator": 7, "denominator": 2}],
                    type=coord_type,
                ),
                "duration": pa.array(
                    [{"value": 0.75, "numerator": 3, "denominator": 4}],
                    type=coord_type,
                ),
            },
            unit=TimeUnit.quarters,
        )

        assert data.column_values("end") == [Fraction(17, 4)]
        assert self._pairs(data, "end") == [(17, 4)]

    def test_float_only_computed_fields_have_null_pairs(self) -> None:
        """Keep computed coordinates float-only when inputs have no pair."""
        data = EventData.from_dicts(
            [{"event_type": "Note", "start": 3.5, "duration": 0.75}],
            unit=TimeUnit.quarters,
        )

        assert data.column_values("end") == [Fraction(4.25)]
        assert self._pairs(data, "end") == [(None, None)]

    def test_mixed_rows_preserve_exactness_per_row(self) -> None:
        """Preserve exact output only for rows with complete exact operands."""
        data = EventData.from_dicts(
            [
                {
                    "event_type": "Note",
                    "start": {"value": 3.5, "numerator": 7, "denominator": 2},
                    "duration": {
                        "value": 0.75,
                        "numerator": 3,
                        "denominator": 4,
                    },
                },
                {"event_type": "Note", "start": 3.5, "duration": 0.75},
            ],
            unit=TimeUnit.quarters,
        )

        assert data.column_values("end") == [Fraction(17, 4), Fraction(4.25)]
        assert self._pairs(data, "end") == [(17, 4), (None, None)]
