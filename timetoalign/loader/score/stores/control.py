"""ControlEventStore: Storage for control events (dynamics, tempo, etc.)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pyarrow as pa
from typing_extensions import Self

from timetoalign.core import NumberType, TimeUnit
from timetoalign.loader.store import EventStore
from timetoalign.loader.schema import FRACTION_TYPE, make_fraction_field

if TYPE_CHECKING:
    pass


class ControlEventStore(EventStore):
    """EventStore for control events.
    
    Subtypes include:
    - Dynamic: velocity/dynamics markings (pp, ff, mf)
    - Tempo: tempo changes (MetronomeMark, TempoIndication)
    - Pedal: sustain/soft pedal events
    - OctaveShift: 8va/8vb markings
    - Wedge: crescendo/decrescendo hairpins
    
    Schema:
    - quarterbeats: Event position (Fraction)
    - duration_qb: Event duration if applicable (Fraction)
    - subtype: Control category (Dynamic, Tempo, Pedal, etc.)
    - value: Numeric value (BPM, velocity level)
    - text: Textual representation
    """

    _extra_fields: ClassVar[list[pa.Field]] = [
        # Temporal
        make_fraction_field("quarterbeats", nullable=False, metadata={"unit": "quarters"}),
        pa.field("quarterbeats_float", pa.float64(), nullable=False),
        make_fraction_field("duration_qb", nullable=True, metadata={"unit": "quarters"}),
        pa.field("duration_qb_float", pa.float64(), nullable=True),
        
        # Measure context
        pa.field("mc", pa.int64(), nullable=True, metadata={"number_type": "int64"}),
        pa.field("mn", pa.string(), nullable=True),
        make_fraction_field("mc_onset", nullable=True),
        make_fraction_field("mn_onset", nullable=True),
        
        # Control specifics
        pa.field("subtype", pa.string(), nullable=False),  # Dynamic, Tempo, Pedal, etc.
        pa.field("value", pa.float64(), nullable=True),    # BPM, velocity, etc.
        pa.field("text", pa.string(), nullable=True),      # "ff", "Allegro", etc.
        
        # Context
        pa.field("voice", pa.int64(), nullable=True),
        pa.field("staff", pa.int64(), nullable=True),
        pa.field("part_id", pa.string(), nullable=True),
    ]

    @classmethod
    def empty(
        cls, 
        unit: TimeUnit = TimeUnit.quarters, 
        number_type: NumberType = NumberType.float,
    ) -> Self:
        """Create empty ControlEventStore."""
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
