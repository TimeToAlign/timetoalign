"""NoteEventStore: Storage for note/rest/chord events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pyarrow as pa
from typing_extensions import Self

from timetoalign.core import NumberType, TimeUnit
from timetoalign.loader.store import EventStore
from timetoalign.loader.schema import FRACTION_TYPE, make_fraction_field

if TYPE_CHECKING:
    pass


def _make_pitch_types() -> tuple[pa.StructType, pa.StructType]:
    """Create MIDI and Spelled pitch struct types."""
    midi_pitch = pa.struct([
        pa.field("ep", pa.int64(), nullable=True),
        pa.field("epc", pa.int64(), nullable=True),
    ])
    
    spelled_pitch = pa.struct([
        pa.field("gpc_int", pa.int64(), nullable=True),
        pa.field("gpc_str", pa.string(), nullable=True),
        pa.field("acc", pa.int64(), nullable=True),
        pa.field("spc_int", pa.int64(), nullable=True),
        pa.field("spc_str", pa.string(), nullable=True),
        pa.field("sp", pa.string(), nullable=True),
        pa.field("cents", pa.float64(), nullable=False),
    ])
    
    return midi_pitch, spelled_pitch


class NoteEventStore(EventStore):
    """EventStore for note, rest, and chord events.
    
    Rich temporal schema following TSV gold standard:
    - quarterbeats: Continuous logical time (Fraction)
    - quarterbeats_float: Float representation
    - duration_qb: Duration in quarter beats (Fraction)
    - duration_qb_float: Float duration
    - mc/mn: Measure context
    - mc_onset/mn_onset: Measure-relative offsets (Fraction)
    
    Pitch fields:
    - midi_pitch: {ep, epc}
    - spelled_pitch: {gpc_int, gpc_str, acc, spc_int, spc_str, sp, cents}
    - tpc: Tonal Pitch Class (fifths)
    - octave: Octave number
    """

    _midi_type, _spelled_type = _make_pitch_types()

    _extra_fields: ClassVar[list[pa.Field]] = [
        # Temporal - Primary (Fractions)
        make_fraction_field("quarterbeats", nullable=False, metadata={"unit": "quarters"}),
        pa.field("quarterbeats_float", pa.float64(), nullable=False),
        make_fraction_field("duration_qb", nullable=True, metadata={"unit": "quarters"}),
        pa.field("duration_qb_float", pa.float64(), nullable=True),
        
        # Temporal - Measure context
        pa.field("mc", pa.int64(), nullable=True, metadata={"number_type": "int64"}),
        pa.field("mn", pa.string(), nullable=True),
        make_fraction_field("mc_onset", nullable=True),
        make_fraction_field("mn_onset", nullable=True),
        pa.field("timesig", pa.string(), nullable=True),
        
        # Temporal - Symbolic duration
        make_fraction_field("duration", nullable=True),
        make_fraction_field("nominal_duration", nullable=True),
        make_fraction_field("scalar", nullable=True),
        
        # Pitch
        pa.field("midi_pitch", _midi_type, nullable=True),
        pa.field("spelled_pitch", _spelled_type, nullable=True),
        pa.field("tpc", pa.int64(), nullable=True, metadata={"number_type": "int64"}),
        pa.field("octave", pa.int64(), nullable=True, metadata={"number_type": "int64"}),
        
        # Performance
        pa.field("velocity", pa.int64(), nullable=True, metadata={"number_type": "int64"}),
        pa.field("tied", pa.int64(), nullable=True),  # -1=end, 0=none, 1=start
        pa.field("gracenote", pa.string(), nullable=True),
        pa.field("chord_id", pa.int64(), nullable=True),
        
        # Context
        pa.field("voice", pa.int64(), nullable=True, metadata={"number_type": "int64"}),
        pa.field("staff", pa.int64(), nullable=True, metadata={"number_type": "int64"}),
        pa.field("part_id", pa.string(), nullable=True),
    ]

    def __init__(
        self,
        table: pa.Table,
        unit: TimeUnit,
        number_type: NumberType = NumberType.float,
        has_rests: bool = False,
    ) -> None:
        """Initialize NoteEventStore.

        Args:
            table: PyArrow table.
            unit: Time unit.
            number_type: Number type.
            has_rests: Whether the source explicitly includes rests.
        """
        super().__init__(table, unit, number_type)
        self._has_rests = has_rests

    @property
    def has_rests(self) -> bool:
        """Return whether the store explicitly contains rests."""
        return self._has_rests

    @classmethod
    def empty(
        cls, 
        unit: TimeUnit = TimeUnit.quarters, 
        number_type: NumberType = NumberType.float,
        has_rests: bool = False,
    ) -> Self:
        """Create empty NoteEventStore."""
        store = super().empty(unit, number_type)
        store._has_rests = has_rests
        return store

    @classmethod
    def from_dicts(
        cls,
        rows: list[dict[str, Any]],
        unit: TimeUnit = TimeUnit.quarters,
        number_type: NumberType = NumberType.float,
        has_rests: bool = False,
    ) -> Self:
        """Create from dicts with has_rests metadata.
        
        Builds PyArrow table directly using NoteEventStore schema.
        """
        if not rows:
            return cls.empty(unit, number_type, has_rests)
        
        from timetoalign.loader.schema import make_table_metadata
        
        schema = cls.schema(unit)
        metadata = make_table_metadata(unit, number_type, loader_class=cls.__name__)
        schema = schema.with_metadata(metadata)
        
        # Ensure all required columns exist with proper defaults
        processed_rows = []
        for row in rows:
            processed = dict(row)
            # Base columns need defaults
            for col in ["instant", "start", "end", "duration"]:
                if col not in processed:
                    processed[col] = None
            processed_rows.append(processed)
        
        table = pa.Table.from_pylist(processed_rows, schema=schema)
        store = cls(table, unit, number_type, has_rests)
        return store
