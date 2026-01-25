"""ScoreEventStore: Storage for symbolic score events.

This module defines the ScoreEventStore, which extends EventStore with
score-specific fields like pitch, measure numbers, and voices.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pyarrow as pa
from typing_extensions import Self

from timetoalign.core import NumberType, TimeUnit
from timetoalign.loader.store import EventStore

if TYPE_CHECKING:
    pass


class ScoreEventType:
    """Constants for score event types."""

    # Categories
    CAT_MEASURE = "measure"
    CAT_NOTE = "note"
    CAT_CONTROL = "control"
    CAT_ANNOTATION = "annotation"

    # Common Event Types
    NOTE = "Note"
    REST = "Rest"
    CHORD = "Chord"
    MEASURE = "Measure"

    # Control/Direction Types
    TIME_SIGNATURE = "TimeSignature"
    KEY_SIGNATURE = "KeySignature"
    TEMPO = "Tempo"
    METRONOME = "Metronome"
    DYNAMIC = "Dynamic"
    DIRECTION = "Direction"
    WEDGE = "Wedge"  # Hairpins
    pedal = "Pedal"
    OCTAVE_SHIFT = "OctaveShift"

    # Annotation
    TEXT_BOX = "TextBox"
    TEXT_EXPRESSION = "TextExpression"


def make_pitch_types() -> tuple[pa.StructType, pa.StructType]:
    """Create MIDI and Spelled pitch struct types.

    Returns:
        Tuple of (midi_pitch_type, spelled_pitch_type).
    """
    midi_pitch = pa.struct(
        [
            pa.field("ep", pa.int64(), nullable=True),
            pa.field("epc", pa.int64(), nullable=True),
        ]
    )

    spelled_pitch = pa.struct(
        [
            pa.field("gpc_int", pa.int64(), nullable=True),
            pa.field("gpc_str", pa.string(), nullable=True),
            pa.field("acc", pa.int64(), nullable=True),
            pa.field("spc_int", pa.int64(), nullable=True),
            pa.field("spc_str", pa.string(), nullable=True),
            pa.field("sp", pa.string(), nullable=True),
            pa.field("cents", pa.float64(), nullable=False),  # Default 0.0
        ]
    )

    return midi_pitch, spelled_pitch


class ScoreEventStore(EventStore):
    """EventStore for symbolic music scores.

    Adds fields for pitch, measures, and score structure.

    Schema Extras:
    - octave (int64): Octave number.
    - midi_pitch (struct): {ep, epc}
    - spelled_pitch (struct): {gpc_int, gpc_str, acc, spc_int, spc_str, sp, cents}
    - mn (string): Measure Number label ("1", "1a")
    - mc (int64): Measure Count (monotonic index)
    - event_category (string): "measure", "note", "control", "annotation"
    - voice (int64): Voice number
    - staff (int64): Staff number
    - velocity (int64): MIDI velocity (default 64)
    - part_id (string): Part identifier
    """

    _midi_type, _spelled_type = make_pitch_types()

    _extra_fields: ClassVar[list[pa.Field]] = [
        pa.field("octave", pa.int64(), nullable=True),
        pa.field("midi_pitch", _midi_type, nullable=True),
        pa.field("spelled_pitch", _spelled_type, nullable=True),
        pa.field("mn", pa.string(), nullable=True),
        pa.field("mc", pa.int64(), nullable=True),
        pa.field("event_category", pa.string(), nullable=False),
        pa.field("voice", pa.int64(), nullable=True),
        pa.field("staff", pa.int64(), nullable=True),
        pa.field("velocity", pa.int64(), nullable=True),
        pa.field("part_id", pa.string(), nullable=True),
    ]

    def __init__(
        self,
        table: pa.Table,
        unit: TimeUnit,
        number_type: NumberType = NumberType.float,
        has_rests: bool | None = None,
    ) -> None:
        """Initialize ScoreEventStore.

        Args:
            table: PyArrow table.
            unit: Time unit.
            number_type: Number type.
            has_rests: Whether the source explicitly includes rests.
        """
        super().__init__(table, unit, number_type)
        self._has_rests = has_rests

    @property
    def has_rests(self) -> bool | None:
        """Return whether the store explicitly contains rests."""
        return self._has_rests

    @classmethod
    def empty(
        cls,
        unit: TimeUnit,
        number_type: NumberType = NumberType.float,
        has_rests: bool | None = None,
    ) -> Self:
        """Create empty ScoreEventStore."""
        store = super().empty(unit, number_type)
        store._has_rests = has_rests
        return store

    @classmethod
    def from_dicts(
        cls,
        rows: list[dict[str, Any]],
        unit: TimeUnit,
        number_type: NumberType = NumberType.float,
        has_rests: bool | None = None,
    ) -> Self:
        """Create from dicts with has_rests metadata and type sanitization."""
        # Sanitize common string fields to prevent PyArrow coercion errors
        for row in rows:
            for field in [
                "mn",
                "part_id",
                "event_category",
                "id",
                "name",
                "event_type",
            ]:
                if row.get(field) is not None:
                    row[field] = str(row[field])

            # Ensure int fields are ints (handle 1.0 -> 1)
            for field in ["mc", "voice", "staff", "octave", "velocity"]:
                val = row.get(field)
                if val is not None:
                    try:
                        row[field] = int(val)
                    except (ValueError, TypeError):
                        row[field] = None

            # Sanitize structs logic would go here if needed, but loaders should produce minimal dicts
            # We trust loaders to produce correct nested dicts for midi_pitch and spelled_pitch
            # Or we can add safety here.

            mp = row.get("midi_pitch")
            if isinstance(mp, dict):
                for f in ["ep", "epc"]:
                    if mp.get(f) is not None:
                        try:
                            mp[f] = int(mp[f])
                        except Exception:
                            mp[f] = None

            sp = row.get("spelled_pitch")
            if isinstance(sp, dict):
                # Strings
                for f in ["gpc_str", "spc_str", "sp"]:
                    if sp.get(f) is not None:
                        sp[f] = str(sp[f])
                # Ints
                for f in ["gpc_int", "acc", "spc_int"]:
                    if sp.get(f) is not None:
                        try:
                            sp[f] = int(sp[f])
                        except Exception:
                            sp[f] = None
                # Floats
                if sp.get("cents") is not None:
                    try:
                        sp["cents"] = float(sp["cents"])
                    except Exception:
                        sp["cents"] = 0.0
                else:
                    sp["cents"] = 0.0

        store = super().from_dicts(rows, unit, number_type)
        store._has_rests = has_rests
        return store

    @classmethod
    def from_arrays(
        cls,
        columns: dict[str, list[Any]],
        unit: TimeUnit,
        number_type: NumberType = NumberType.float,
        has_rests: bool | None = None,
    ) -> Self:
        """Create from arrays with has_rests metadata."""
        store = super().from_arrays(columns, unit, number_type)
        store._has_rests = has_rests
        return store

    def summary(self) -> dict[str, Any]:
        """Get summary including score-specific stats."""
        base = super().summary()
        base["has_rests"] = self.has_rests
        if self.count > 0:
            base["categories"] = self.count_by("event_category")
        return base
