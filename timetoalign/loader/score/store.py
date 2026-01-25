"""ScoreEventStore: Storage for symbolic score events.

This module defines the ScoreEventStore, which extends EventStore with
score-specific fields like pitch, measure numbers, and voices.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Literal

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


def make_spelled_pitch_type() -> pa.StructType:
    """Create a spelled pitch struct type.

    Returns:
        A PyArrow struct type with step, alter, octave.
    """
    return pa.struct([
        pa.field("step", pa.string(), nullable=True),
        pa.field("alter", pa.int64(), nullable=True),
        pa.field("octave", pa.int64(), nullable=True),
    ])


class ScoreEventStore(EventStore):
    """EventStore for symbolic music scores.

    Adds fields for pitch, measures, and score structure.
    
    Schema Extras:
    - tpc (int64): Tonal Pitch Class
    - ep (int64): Enharmonic Pitch (MIDI number)
    - sp (struct): Spelled Pitch {step, alter, octave}
    - mn (string): Measure Number label ("1", "1a")
    - mc (int64): Measure Count (monotonic index)
    - event_category (string): "measure", "note", "control", "annotation"
    - voice (int64): Voice number
    - staff (int64): Staff number
    - velocity (int64): MIDI velocity (default 64)
    - part_id (string): Part identifier
    """

    _extra_fields: ClassVar[list[pa.Field]] = [
        pa.field("tpc", pa.int64(), nullable=True),
        pa.field("ep", pa.int64(), nullable=True),
        pa.field("sp", make_spelled_pitch_type(), nullable=True),
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
            for field in ["mn", "part_id", "event_category", "id", "name", "event_type"]:
                if row.get(field) is not None:
                    row[field] = str(row[field])
            
            # Ensure int fields are ints (handle 1.0 -> 1)
            for field in ["mc", "voice", "staff", "tpc", "ep", "velocity"]:
                val = row.get(field)
                if val is not None:
                    try:
                        row[field] = int(val)
                    except (ValueError, TypeError):
                        row[field] = None
            
            # Sanitize sp struct
            sp = row.get("sp")
            if isinstance(sp, dict):
                # Ensure step is string
                if sp.get("step") is not None:
                    sp["step"] = str(sp["step"])
                # Ensure alter/octave are ints
                for field in ["alter", "octave"]:
                    val = sp.get(field)
                    if val is not None:
                        try:
                            sp[field] = int(val)
                        except (ValueError, TypeError):
                            sp[field] = None

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
