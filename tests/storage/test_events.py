"""Exact-value tests for ``EventData.column_values()``.

See ``README.md`` for the documented contract.
"""

from __future__ import annotations

from fractions import Fraction

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
