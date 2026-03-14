"""Note scalar for score note/rest events.

``Note`` is a frozen dataclass that represents a single note or rest
event extracted from ``NoteEventData``.  It satisfies ``NoteLike``.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..types import Coordinate
from .pitch import MidiPitch


@dataclass(frozen=True, slots=True)
class Note:
    """A single note or rest event.  Satisfies ``NoteLike``.

    Attributes:
        onset: Temporal position as a ``Coordinate``.
        offset: End position as a ``Coordinate``, or ``None``.
        duration: Duration in quarter-beat units.
        pitch: ``MidiPitch`` for pitched notes, ``None`` for rests.
        voice: Voice number, or ``None``.
        staff: Staff number, or ``None``.
        velocity: MIDI velocity (0-127), or ``None``.
    """

    onset: Coordinate
    offset: Coordinate | None
    duration: float
    pitch: MidiPitch | None
    voice: int | None
    staff: int | None
    velocity: int | None

    @property
    def is_rest(self) -> bool:
        """Return ``True`` if this event is a rest (no pitch)."""
        return self.pitch is None

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "Note"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract."""
        return {
            "field_type": "NoteField",
            "has_pitch": str(self.pitch is not None).lower(),
        }

    def __repr__(self) -> str:
        pitch_str = repr(self.pitch) if self.pitch is not None else "rest"
        return f"Note(onset={self.onset}, duration={self.duration}, pitch={pitch_str})"
