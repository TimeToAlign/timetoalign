"""MeasureEventStore: Storage for measure boundary events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pyarrow as pa
from typing_extensions import Self

from timetoalign.core import NumberType, TimeUnit
from timetoalign.loader.schema import make_fraction_field
from timetoalign.loader.store import EventStore

if TYPE_CHECKING:
    pass


class MeasureEventStore(EventStore):
    """EventStore for measure boundary events.

    Schema:
    - quarterbeats: Measure start in continuous logical time (Fraction)
    - duration_qb: Measure length in quarter beats (Fraction)
    - mc: Measure Count (1-indexed monotonic)
    - mn: Measure Number label ("1", "1a", etc.)
    - timesig: Time signature ("2/4", "4/4")
    - keysig: Key signature (e.g., "C", "G#m")
    """

    _extra_fields: ClassVar[list[pa.Field]] = [
        # Temporal
        make_fraction_field(
            "quarterbeats", nullable=False, metadata={"unit": "quarters"}
        ),
        pa.field("quarterbeats_float", pa.float64(), nullable=False),
        make_fraction_field(
            "duration_qb", nullable=True, metadata={"unit": "quarters"}
        ),
        pa.field("duration_qb_float", pa.float64(), nullable=True),
        # Measure identity
        pa.field("mc", pa.int64(), nullable=False, metadata={"number_type": "int64"}),
        pa.field("mn", pa.string(), nullable=True),
        # Signatures
        pa.field("timesig", pa.string(), nullable=True),
        pa.field("timesig_num", pa.int64(), nullable=True),
        pa.field("timesig_den", pa.int64(), nullable=True),
        pa.field("keysig", pa.string(), nullable=True),
        pa.field("keysig_fifths", pa.int64(), nullable=True),
        pa.field("keysig_mode", pa.string(), nullable=True),  # "major", "minor"
        # Context
        pa.field("part_id", pa.string(), nullable=True),
    ]

    @classmethod
    def empty(
        cls,
        unit: TimeUnit = TimeUnit.quarters,
        number_type: NumberType = NumberType.float,
    ) -> Self:
        """Create empty MeasureEventStore."""
        return super().empty(unit, number_type)

    @classmethod
    def from_dicts(
        cls,
        rows: list[dict[str, Any]],
        unit: TimeUnit = TimeUnit.quarters,
        number_type: NumberType = NumberType.float,
    ) -> Self:
        """Create from dicts."""
        if not rows:
            return cls.empty(unit, number_type)

        from timetoalign.loader.schema import make_table_metadata

        schema = cls.schema(unit)
        metadata = make_table_metadata(unit, number_type, loader_class=cls.__name__)
        schema = schema.with_metadata(metadata)

        processed_rows = []
        for row in rows:
            processed = dict(row)
            for col in ["instant", "start", "end", "duration"]:
                if col not in processed:
                    processed[col] = None
            processed_rows.append(processed)

        table = pa.Table.from_pylist(processed_rows, schema=schema)
        return cls(table, unit, number_type)
