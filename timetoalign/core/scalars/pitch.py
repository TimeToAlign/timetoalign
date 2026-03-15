"""Pitch scalars for the Time To Align! type hierarchy.

Provides frozen dataclass scalars at four levels of pitch specificity:

- ``GenericPitch`` -- pitch class only (satisfies ``GenericPitchLike``)
- ``SpelledPitchClass`` -- pitch class with spelling (satisfies ``SpelledPitchClassLike``)
- ``MidiPitch`` (alias ``SpecificPitch``) -- MIDI note (satisfies ``SpecificPitchClassLike``)
- ``SpelledPitch`` (alias ``EnharmonicPitch``) -- full spelling (satisfies ``EnharmonicPitchLike``)

All 12-TET scalars compose ``TwelveTETPitchMixin`` which provides the
unified ``.to()`` dispatch method and ``.get(format=)`` formatting.

Scalar field names are canonical semantic names; the mapping to storage
struct names (``ep``, ``epc``, ``gpc_int``, ``gpc_str``, ``acc``,
``spc_int``, ``spc_str``, ``sp``, ``cents``) is handled by the Field
classes and loaders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..protocols import TwelveTETPitchMixin

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

# Pitch-class to step name (for reverse mapping)
_PC_TO_STEP: dict[int, str] = {v: k for k, v in _STEP_TO_SEMITONE.items()}


# region GenericPitch


@dataclass(frozen=True, slots=True)
class GenericPitch(TwelveTETPitchMixin):
    """Pitch class only.  Satisfies ``GenericPitchLike``.

    Attributes:
        pitch_class: Pitch class (0-11, C=0).
    """

    pitch_class: int  # type: ignore[override]

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "GenericPitch"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract."""
        return {
            "field_type": "GenericPitchField",
            "pitch_type": "generic",
        }

    def to(self, target_type: type, *, format: str | None = None) -> "GenericPitch":
        """Convert to another pitch type.

        ``GenericPitch`` can only convert to itself (identity).
        Conversion to ``MidiPitch`` or ``SpelledPitch`` requires
        additional information (octave, spelling).

        Args:
            target_type: Target pitch type.
            format: Optional format specifier.

        Returns:
            A pitch scalar of the target type.

        Raises:
            TypeError: If conversion is not supported.
        """
        if target_type is GenericPitch or target_type is type(self):
            return self
        raise TypeError(
            f"Cannot convert GenericPitch to {target_type.__name__} "
            f"(octave and/or spelling information required)"
        )

    def get(self, *, format: str | None = None) -> str:
        """Return string representation.

        Args:
            format: Format specifier (ignored for GenericPitch).
        """
        return str(self.pitch_class)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> GenericPitch | None:
        """Construct from a PyArrow struct row dict.

        Accepts the ``generic_pitch`` struct: ``{pitch_class: int64}``.

        Args:
            row: Dict with storage field names (from PyArrow ``.as_py()``).

        Returns:
            A ``GenericPitch``, or ``None`` if ``pitch_class`` is null.
        """
        pc = row.get("pitch_class")
        if pc is None:
            return None
        return cls(pitch_class=int(pc))

    def __eq__(self, other: object) -> bool:
        """Compare to another ``GenericPitch`` or to a plain ``int``.

        ``GPC(C) == 0`` evaluates to ``True``, enabling concise pitch-class
        arithmetic in interactive contexts.
        """
        if isinstance(other, int):
            return self.pitch_class == other
        if isinstance(other, GenericPitch):
            return self.pitch_class == other.pitch_class
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.pitch_class)

    def __repr__(self) -> str:
        step = _PC_TO_STEP.get(self.pitch_class)
        if step is not None:
            return f"GPC({step})"
        return f"GPC({self.pitch_class})"


# endregion GenericPitch

# region SpelledPitchClass


@dataclass(frozen=True, slots=True)
class SpelledPitchClass(TwelveTETPitchMixin):
    """Pitch class with spelling.  Satisfies ``SpelledPitchClassLike``.

    Attributes:
        step: Generic pitch class as string (``"C"``, ``"D"``, etc.).
            Stored as ``gpc_str`` in the schema.
        alter: Accidental in semitones (-1=flat, 0=natural, +1=sharp).
            Stored as ``acc`` in the schema.
        fifths: Spelled pitch class in fifths.
            Stored as ``spc_int`` in the schema.
    """

    step: str
    alter: int
    fifths: int

    @property
    def pitch_class(self) -> int:  # type: ignore[override]
        """Compute pitch class (0-11) from step and alter."""
        base = _STEP_TO_SEMITONE.get(self.step, 0)
        return (base + self.alter) % 12

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "SpelledPitchClass"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract."""
        return {
            "field_type": "SpelledPitchClassField",
            "pitch_type": "spelled_class",
        }

    def to(
        self, target_type: type, *, format: str | None = None
    ) -> "SpelledPitchClass":
        """Convert to another pitch type.

        Args:
            target_type: Target pitch type.
            format: Optional format specifier.

        Returns:
            A pitch scalar of the target type.

        Raises:
            TypeError: If conversion is not supported.
        """
        if target_type is SpelledPitchClass or target_type is type(self):
            return self
        if target_type is GenericPitch:
            return GenericPitch(pitch_class=self.pitch_class)  # type: ignore[return-value]
        raise TypeError(
            f"Cannot convert SpelledPitchClass to {target_type.__name__} "
            f"(octave information required)"
        )

    def get(self, *, format: str | None = None) -> str:
        """Return string representation.

        Args:
            format: Format specifier (ignored for SpelledPitchClass).
        """
        alter_str = ""
        if self.alter > 0:
            alter_str = "\u266f" * self.alter
        elif self.alter < 0:
            alter_str = "\u266d" * abs(self.alter)
        return f"{self.step}{alter_str}"

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> SpelledPitchClass | None:
        """Construct from a PyArrow struct row dict.

        Accepts the ``spelled_pitch_class`` struct:
        ``{gpc_str: string, acc: int64, spc_int: int64}``.

        Args:
            row: Dict with storage field names.

        Returns:
            A ``SpelledPitchClass``, or ``None`` if ``gpc_str`` is null.
        """
        step = row.get("gpc_str")
        if step is None:
            return None
        return cls(
            step=str(step),
            alter=int(row.get("acc", 0) or 0),
            fifths=int(row.get("spc_int", 0) or 0),
        )

    def __repr__(self) -> str:
        return f"SpelledPitchClass({self.get()})"


# endregion SpelledPitchClass

# region MidiPitch


@dataclass(frozen=True, slots=True)
class MidiPitch(TwelveTETPitchMixin):
    """MIDI pitch scalar.  Satisfies ``SpecificPitchClassLike``.

    Alias: ``SpecificPitch``.

    Wraps the ``midi_pitch`` struct ``{ep, epc}`` from ``NoteEventData``
    where ``ep`` is the MIDI note number and ``epc`` is the pitch class.

    Attributes:
        midi_number: MIDI note number (0-127), stored as ``ep`` in schema.
        pitch_class: Pitch class (0-11, C=0), stored as ``epc`` in schema.
    """

    midi_number: int
    pitch_class: int  # type: ignore[override]

    @property
    def octave(self) -> int:
        """Octave number (C4 = 60 -> octave 4)."""
        return (self.midi_number // 12) - 1

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "MidiPitch"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract."""
        return {
            "field_type": "SpecificPitchField",
            "pitch_type": "midi",
        }

    def to(
        self, target_type: type, *, format: str | None = None
    ) -> "TwelveTETPitchMixin":
        """Convert to another pitch type.

        Args:
            target_type: Target pitch type.
            format: Optional format specifier.

        Returns:
            A pitch scalar of the target type.

        Raises:
            TypeError: If conversion is not supported.
        """
        if target_type is MidiPitch or target_type is type(self):
            return self
        if target_type is GenericPitch:
            return GenericPitch(pitch_class=self.pitch_class)
        raise TypeError(
            f"Cannot convert MidiPitch to {target_type.__name__} "
            f"(spelling information required for enharmonic types)"
        )

    def get(self, *, format: str | None = None) -> str:
        """Return string representation.

        Args:
            format: ``"midi"`` (default) returns MIDI number as string.
        """
        return str(self.midi_number)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> MidiPitch | None:
        """Construct from a PyArrow struct row dict.

        Accepts the ``midi_pitch`` (EP) struct: ``{ep: int64, epc: int64}``.

        Args:
            row: Dict with storage field names.

        Returns:
            A ``MidiPitch``, or ``None`` if ``ep`` or ``epc`` is null.
        """
        ep = row.get("ep")
        epc = row.get("epc")
        if ep is None or epc is None:
            return None
        return cls(midi_number=int(ep), pitch_class=int(epc))

    def __repr__(self) -> str:
        return (
            f"MidiPitch(midi_number={self.midi_number}, pitch_class={self.pitch_class})"
        )


# Alias for canonical naming
SpecificPitch = MidiPitch

# endregion MidiPitch

# region SpelledPitch


@dataclass(frozen=True, slots=True)
class SpelledPitch(TwelveTETPitchMixin):
    """Spelled pitch scalar with enharmonic information.

    Satisfies ``EnharmonicPitchLike``.  Alias: ``EnharmonicPitch``.

    Wraps the ``spelled_pitch`` struct from ``NoteEventData``:
    ``{gpc_int, gpc_str, acc, spc_int, spc_str, sp, cents}``.

    Attributes:
        step: Generic pitch class as string (from ``gpc_str``).
        alter: Accidental in semitones (from ``acc``).
        octave: Octave number (derived from ``sp``).
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
    def pitch_class(self) -> int:  # type: ignore[override]
        """Compute pitch class (0-11) from step and alter."""
        base = _STEP_TO_SEMITONE.get(self.step, 0)
        return (base + self.alter) % 12

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "SpelledPitch"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract."""
        return {
            "field_type": "EnharmonicPitchField",
            "pitch_type": "spelled",
        }

    def to(
        self, target_type: type, *, format: str | None = None
    ) -> "TwelveTETPitchMixin":
        """Convert to another pitch type.

        Args:
            target_type: Target pitch type.
            format: Optional format specifier.

        Returns:
            A pitch scalar of the target type.

        Raises:
            TypeError: If conversion is not supported.
        """
        if target_type is SpelledPitch or target_type is type(self):
            return self
        if target_type is MidiPitch:
            return MidiPitch(
                midi_number=self.midi_number,
                pitch_class=self.pitch_class,
            )
        if target_type is GenericPitch:
            return GenericPitch(pitch_class=self.pitch_class)
        if target_type is SpelledPitchClass:
            return SpelledPitchClass(
                step=self.step,
                alter=self.alter,
                fifths=self.fifths,
            )
        raise TypeError(f"Cannot convert SpelledPitch to {target_type.__name__}")

    def get(self, *, format: str | None = None) -> str:
        """Return string representation.

        Args:
            format: ``"spelled"`` (default) returns e.g. ``"C♯4"``.
                ``"midi"`` returns the MIDI number.
        """
        if format == "midi":
            return str(self.midi_number)
        alter_str = ""
        if self.alter > 0:
            alter_str = "\u266f" * self.alter
        elif self.alter < 0:
            alter_str = "\u266d" * abs(self.alter)
        return f"{self.step}{alter_str}{self.octave}"

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> SpelledPitch | None:
        """Construct from a PyArrow struct row dict.

        Accepts the ``spelled_pitch`` (SP) struct:
        ``{gpc_int, gpc_str, acc, spc_int, spc_str, sp, cents}``.

        Args:
            row: Dict with storage field names.

        Returns:
            A ``SpelledPitch``, or ``None`` if ``gpc_str`` is null.
        """
        step = row.get("gpc_str")
        if step is None:
            return None
        alter = int(row.get("acc", 0) or 0)
        fifths = int(row.get("spc_int", 0) or 0)
        cents = float(row.get("cents", 0.0) or 0.0)
        # Extract octave from 'sp' string (e.g. "C4" -> 4)
        sp = row.get("sp", "")
        octave = _parse_octave_from_sp(sp, str(step))
        return cls(
            step=str(step),
            alter=alter,
            octave=octave,
            fifths=fifths,
            cents=cents,
        )

    def __repr__(self) -> str:
        return f"SpelledPitch({self.get()})"


def _parse_octave_from_sp(sp: str | None, step: str) -> int:
    """Extract octave number from a spelled pitch string like ``"C4"``."""
    if not sp:
        return 4
    try:
        idx = len(sp)
        while idx > 0 and (sp[idx - 1].isdigit() or sp[idx - 1] == "-"):
            idx -= 1
        if idx < len(sp):
            return int(sp[idx:])
    except (ValueError, IndexError):
        pass
    return 4


# Alias for canonical naming
EnharmonicPitch = SpelledPitch

# endregion SpelledPitch
