"""Note scalar for score note/rest events.

``Note`` is a frozen dataclass that represents a single note or rest
event.  It satisfies ``NoteLike`` (and thus ``IntervalEventLike``).

Uses canonical TTA model names: ``start`` / ``end`` for temporal fields.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..types import Coordinate
from .pitch import MidiPitch, SpelledPitch


@dataclass(frozen=True, slots=True)
class Note:
    """A single note or rest event.  Satisfies ``NoteLike``.

    Attributes:
        start: Temporal position as a ``Coordinate`` (StartInstant).
        end: End position as a ``Coordinate``, or ``None`` (EndInstant).
        duration: Duration as a ``Coordinate``, or ``None``.
        pitch: ``MidiPitch`` or ``SpelledPitch`` for pitched notes,
            ``None`` for rests.
        voice: Voice number, or ``None``.
        staff: Staff number, or ``None``.
        velocity: MIDI velocity (0-127), or ``None``.
        instrument: Instrument name/identifier, or ``None``.
    """

    start: Coordinate
    end: Coordinate | None
    duration: Coordinate | None
    pitch: MidiPitch | SpelledPitch | None
    voice: int | None
    staff: int | None
    velocity: int | None
    instrument: str | None = None

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
        return f"Note(start={self.start}, duration={self.duration}, pitch={pitch_str})"
