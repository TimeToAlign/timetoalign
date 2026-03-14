"""Pitch scalars for MIDI and spelled pitch representations.

``MidiPitch`` wraps the ``midi_pitch`` struct ``{ep, epc}`` from
``NoteEventData``.  ``SpelledPitch`` wraps the ``spelled_pitch``
struct ``{gpc_int, gpc_str, acc, spc_int, spc_str, sp, cents}``.

Both satisfy the ``PitchLike`` protocol.
"""

from __future__ import annotations

from dataclasses import dataclass

# Step-name to semitone offset from C (C=0, D=2, E=4, F=5, G=7, A=9, B=11)
_STEP_TO_SEMITONE: dict[str, int] = {
    "C": 0,
    "D": 2,
    "E": 4,
    "F": 5,
    "G": 7,
    "A": 9,
    "B": 11,
}

# Step-name to pitch-class base (no accidental)
_STEP_TO_PC: dict[str, int] = _STEP_TO_SEMITONE


@dataclass(frozen=True, slots=True)
class MidiPitch:
    """MIDI pitch scalar.  Satisfies ``PitchLike``.

    Wraps the ``midi_pitch`` struct ``{ep, epc}`` from ``NoteEventData``
    where ``ep`` is the MIDI note number and ``epc`` is the pitch class.

    Attributes:
        midi_number: MIDI note number (0-127), stored as ``ep`` in schema.
        pitch_class: Pitch class (0-11, C=0), stored as ``epc`` in schema.
    """

    midi_number: int
    pitch_class: int

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "MidiPitch"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract."""
        return {
            "field_type": "PitchField",
            "pitch_type": "midi",
        }

    def __repr__(self) -> str:
        return (
            f"MidiPitch(midi_number={self.midi_number}, pitch_class={self.pitch_class})"
        )


@dataclass(frozen=True, slots=True)
class SpelledPitch:
    """Spelled pitch scalar with enharmonic information.

    Wraps the ``spelled_pitch`` struct from ``NoteEventData``:
    ``{gpc_int, gpc_str, acc, spc_int, spc_str, sp, cents}``.

    Attributes:
        step: Generic pitch class as string (from ``gpc_str``: ``"C"``, ``"D"``, etc.).
        alter: Accidental in semitones (from ``acc``: -1=flat, 0=natural, 1=sharp).
        octave: Octave number (derived from ``sp`` or computed).
        fifths: Spelled pitch class in fifths (from ``spc_int``).
        cents: Cents value.
    """

    step: str
    alter: int
    octave: int
    fifths: int
    cents: float

    @property
    def midi_number(self) -> int:
        """Compute MIDI note number from step, alter, and octave.

        Uses the standard MIDI mapping: C4 = 60.
        """
        base = _STEP_TO_SEMITONE.get(self.step, 0)
        return (self.octave + 1) * 12 + base + self.alter

    @property
    def pitch_class(self) -> int:
        """Compute pitch class (0-11) from step and alter."""
        base = _STEP_TO_PC.get(self.step, 0)
        return (base + self.alter) % 12

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "SpelledPitch"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract."""
        return {
            "field_type": "SpelledPitchField",
            "pitch_type": "spelled",
        }

    def __repr__(self) -> str:
        alter_str = ""
        if self.alter > 0:
            alter_str = "#" * self.alter
        elif self.alter < 0:
            alter_str = "b" * abs(self.alter)
        return f"SpelledPitch({self.step}{alter_str}{self.octave})"
