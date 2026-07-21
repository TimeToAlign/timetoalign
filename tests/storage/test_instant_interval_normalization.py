"""Temporal-type-aware interval normalisation tests."""

from __future__ import annotations

from fractions import Fraction

import pyarrow as pa

from timetoalign.core import TimeUnit
from timetoalign.storage.events import EventData


def test_vectorized_normalization_keeps_explicit_instants_null() -> None:
    """An instant start does not synthesize an end or duration."""
    coord_type = pa.struct(
        [
            pa.field("value", pa.float64()),
            pa.field("numerator", pa.int64()),
            pa.field("denominator", pa.int64()),
        ]
    )
    data = EventData.from_arrays(
        {
            "id": ["instant", "interval"],
            "temporal_type": ["instant", "interval"],
            "event_type": ["Marker", "Note"],
            "start": pa.array(
                [
                    {"value": 3.5, "numerator": 7, "denominator": 2},
                    {"value": 3.5, "numerator": 7, "denominator": 2},
                ],
                type=coord_type,
            ),
            "duration": pa.array(
                [
                    None,
                    {"value": 0.75, "numerator": 3, "denominator": 4},
                ],
                type=coord_type,
            ),
        },
        unit=TimeUnit.quarters,
    )

    rows = data.table.to_pylist()
    assert rows[0]["end"] is None
    assert rows[0]["duration"] is None
    assert rows[1]["end"]["numerator"] == 17
    assert rows[1]["end"]["denominator"] == 4
    assert Fraction(
        rows[1]["duration"]["numerator"], rows[1]["duration"]["denominator"]
    ) == Fraction(3, 4)
