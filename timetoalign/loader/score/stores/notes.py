"""NoteEventStore: Storage for note/rest/chord events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pyarrow as pa
from typing_extensions import Self

from timetoalign.core import NumberType, TimeUnit
from timetoalign.loader.schema import make_fraction_field
from timetoalign.loader.store import EventStore

if TYPE_CHECKING:
    pass


def _make_pitch_types() -> tuple[pa.StructType, pa.StructType]:
    """Create MIDI and Spelled pitch struct types."""
    midi_pitch = pa.struct(
        [
            pa.field("ep", pa.int64(), nullable=True),
            pa.field("epc", pa.int64(), nullable=True),
        ]
    )

    spelled_pitch = pa.struct(
        [
            pa.field("gpc_int", pa.int64(), nullable=True, metadata={"unit": "steps"}),
            pa.field("gpc_str", pa.string(), nullable=True),
            pa.field("acc", pa.int64(), nullable=True, metadata={"unit": "alter"}),
            pa.field("spc_int", pa.int64(), nullable=True, metadata={"unit": "fifths"}),
            pa.field("spc_str", pa.string(), nullable=True),
            pa.field("sp", pa.string(), nullable=True),
            pa.field("cents", pa.float64(), nullable=False, metadata={"unit": "cents"}),
        ]
    )

    return midi_pitch, spelled_pitch


class NoteEventStore(EventStore):
    """EventStore for note, rest, and chord events.

    Rich temporal schema following TSV gold standard:
    - start: Continuous logical time (Fraction) - from 'quarterbeats'
    - duration: Duration (Fraction) - from 'duration_qb'
    - duration_float: Float duration
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
        # Temporal - Derived/Float
        pa.field("duration_float", pa.float64(), nullable=True),
        # Temporal - Measure context
        pa.field("mc", pa.int64(), nullable=True, metadata={"number_type": "int64"}),
        pa.field("mn", pa.string(), nullable=True),
        make_fraction_field("mc_onset", nullable=True),
        make_fraction_field("mn_onset", nullable=True),
        # Pitch
        pa.field("midi_pitch", _midi_type, nullable=True),
        pa.field("spelled_pitch", _spelled_type, nullable=True),
        pa.field(
            "tpc",
            pa.int64(),
            nullable=True,
            metadata={"number_type": "int64", "unit": "fifths"},
        ),
        pa.field(
            "octave", pa.int64(), nullable=True, metadata={"number_type": "int64"}
        ),
        # Performance
        pa.field(
            "velocity", pa.int64(), nullable=True, metadata={"number_type": "int64"}
        ),
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

            # Map legacy temporal columns to base
            if "quarterbeats" in processed:
                processed["start"] = processed.pop("quarterbeats")
            if "duration_qb" in processed:
                processed["duration"] = processed.pop("duration_qb")
            if "duration_qb_float" in processed:
                processed["duration_float"] = processed.pop("duration_qb_float")

            # Remove unused/redundant fields
            for k in [
                "quarterbeats_float",
                "nominal_duration",
                "scalar",
                "timesig",
                "instant",
            ]:
                processed.pop(k, None)

            # Base columns need defaults
            for col in ["start", "end", "duration"]:
                if col not in processed:
                    processed[col] = None
            processed_rows.append(processed)

        table = pa.Table.from_pylist(processed_rows, schema=schema)
        store = cls(table, unit, number_type, has_rests)
        return store
