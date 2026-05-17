"""Pitch scalars for the Time To Align! type hierarchy.

Provides frozen dataclass scalars at multiple levels of pitch specificity:

- ``EnharmonicPitchClass`` -- chromatic pitch class 0-11 (satisfies ``GenericPitchLike``)
- ``GenericPitchClass`` -- diatonic step 0-6
- ``GenericPitch`` -- diatonic step + octave
- ``SpelledPitchClass`` -- pitch class with spelling (satisfies ``SpelledPitchClassLike``)
- ``EnharmonicPitch`` -- pitch in semitone space displayed as note-name + octave,
  used by ``PitchField`` when ``pitch_type="ep"`` (satisfies ``EnharmonicPitchLike``)
- ``MidiPitch`` -- **distinct** MIDI-keyboard pitch reserved for the planned
  ``MidiField`` (velocity/channel/program context); satisfies ``EnharmonicPitchLike``
- ``SpelledPitch`` -- full spelling with octave (satisfies ``SpecificPitchLike``).
  ``SpecificPitch`` is a re-export of the same class under its protocol name.

``MidiPitch`` and ``EnharmonicPitch`` are **distinct types**, not aliases.
``EnharmonicPitch`` is the canonical scalar for the ``ep`` storage column on
score-level pitch data; ``MidiPitch`` is reserved for MIDI-keyboard data with
velocity/channel/program context (see the planned ``MidiField``).

All 12-TET scalars compose ``TwelveTETPitchMixin`` which provides the
unified ``.to()`` dispatch method and ``.get(format=)`` formatting.

Scalar field names are canonical semantic names; the mapping to storage
struct names (``ep``, ``epc``, ``gpc_int``, ``gpc_str``, ``acc``,
``spc_int``, ``spc_str``, ``sp``, ``cents``) is handled by the Field
classes and loaders.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
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

# Pitch-class to step name (for reverse mapping — natural notes only)
_PC_TO_STEP: dict[int, str] = {v: k for k, v in _STEP_TO_SEMITONE.items()}

# All 12 chromatic pitch class labels (for EPC display)
_PC_TO_LABEL: tuple[str, ...] = (
    "C",
    "C\u266f/D\u266d",
    "D",
    "D\u266f/E\u266d",
    "E",
    "F",
    "F\u266f/G\u266d",
    "G",
    "G\u266f/A\u266d",
    "A",
    "A\u266f/B\u266d",
    "B",
)

# Step-name to diatonic index (C=0, D=1, E=2, F=3, G=4, A=5, B=6)
_STEP_TO_GPC: dict[str, int] = {
    "C": 0,
    "D": 1,
    "E": 2,
    "F": 3,
    "G": 4,
    "A": 5,
    "B": 6,
}

# Base fifths for each step (unaltered)
_BASE_FIFTHS: dict[str, int] = {
    "F": -1,
    "C": 0,
    "G": 1,
    "D": 2,
    "A": 3,
    "E": 4,
    "B": 5,
}

# Regex for parsing pitch labels like "C#4", "Bb3", "D♯5", "F♭-1"
_PITCH_LABEL_RE = re.compile(
    r"^([A-Ga-g])"  # step letter
    r"([#♯]*|[b♭]*)"  # accidentals
    r"(-?\d+)?$"  # optional octave
)


def _step_alter_to_fifths(step: str, alter: int) -> int:
    """Compute line-of-fifths position from step and alter.

    Each sharp adds 7 fifths, each flat subtracts 7.

    Args:
        step: Step letter (``"C"``, ``"D"``, etc.).
        alter: Accidental in semitones.

    Returns:
        Position on the line of fifths.
    """
    return _BASE_FIFTHS.get(step, 0) + (7 * alter)


def _parse_pitch_label(label: str) -> tuple[str, int, int | None]:
    """Parse a pitch label string into (step, alter, octave_or_None).

    Accepts labels like ``"C#4"``, ``"Bb3"``, ``"D♯5"``, ``"F♭-1"``,
    ``"C♯"`` (no octave).

    Args:
        label: A pitch label string.

    Returns:
        A tuple ``(step, alter, octave)`` where ``octave`` is ``None``
        if not present in the label.

    Raises:
        ValueError: If the label cannot be parsed.
    """
    m = _PITCH_LABEL_RE.match(label.strip())
    if m is None:
        raise ValueError(f"Cannot parse pitch label: {label!r}")
    step = m.group(1).upper()
    acc_str = m.group(2)
    octave_str = m.group(3)

    # Count accidentals
    if not acc_str:
        alter = 0
    elif acc_str[0] in ("#", "\u266f"):
        alter = len(acc_str)
    else:
        alter = -len(acc_str)

    octave = int(octave_str) if octave_str is not None else None
    return step, alter, octave


# region EnharmonicPitchClass


@dataclass(frozen=True, slots=True)
class EnharmonicPitchClass(TwelveTETPitchMixin):
    """Enharmonic pitch class scalar -- chromatic pitch class (0-11).

    Satisfies ``GenericPitchLike``.

    Attributes:
        pitch_class: Pitch class (0-11, C=0).
    """

    pitch_class: int  # type: ignore[override]

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "EnharmonicPitchClass"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract."""
        return {
            "field_type": "PitchField",
            "pitch_type": "epc",
        }

    def to(
        self, target_type: type, *, format: str | None = None
    ) -> "EnharmonicPitchClass":
        """Convert to another pitch type.

        ``EnharmonicPitchClass`` can only convert to itself (identity).
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
        if target_type is EnharmonicPitchClass or target_type is type(self):
            return self
        raise TypeError(
            f"Cannot convert EnharmonicPitchClass to {target_type.__name__} "
            f"(octave and/or spelling information required)"
        )

    def get(self, *, format: str | None = None) -> str:
        """Return string representation.

        Args:
            format: Format specifier (ignored for EnharmonicPitchClass).
        """
        return str(self.pitch_class)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> EnharmonicPitchClass | None:
        """Construct from a PyArrow struct row dict.

        Accepts the ``generic_pitch`` struct: ``{pitch_class: int64}``.

        Args:
            row: Dict with storage field names (from PyArrow ``.as_py()``).

        Returns:
            An ``EnharmonicPitchClass``, or ``None`` if ``pitch_class`` is null.
        """
        pc = row.get("pitch_class")
        if pc is None:
            return None
        return cls(pitch_class=int(pc))

    def to_dict(self) -> dict[str, object]:
        """Return a dict mirroring the storage struct.

        Returns:
            A dict with the ``pitch_class`` storage field.
        """
        return {"pitch_class": self.pitch_class}

    def __eq__(self, other: object) -> bool:
        """Compare to another ``EnharmonicPitchClass`` or to a plain ``int``.

        ``EPC(C) == 0`` evaluates to ``True``, enabling concise pitch-class
        arithmetic in interactive contexts.
        """
        if isinstance(other, int):
            return self.pitch_class == other
        if isinstance(other, EnharmonicPitchClass):
            return self.pitch_class == other.pitch_class
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.pitch_class)

    def __repr__(self) -> str:
        if 0 <= self.pitch_class < 12:
            return f"EPC({_PC_TO_LABEL[self.pitch_class]})"
        return f"EPC({self.pitch_class})"


# endregion EnharmonicPitchClass

# region GenericPitchClass

_GPC_NAMES: tuple[str, ...] = ("C", "D", "E", "F", "G", "A", "B")


@dataclass(frozen=True, slots=True)
class GenericPitchClass(TwelveTETPitchMixin):
    """Generic pitch class scalar -- diatonic step (0-6).

    Represents a pitch class in diatonic (steps) space: C=0, D=1, ..., B=6.
    Unlike ``EnharmonicPitchClass`` (which is EPC, 0-11 chromatic), this is a 7-class
    diatonic pitch class.

    Attributes:
        step: Diatonic step (0-6, C=0).
    """

    step: int

    @property
    def pitch_class(self) -> int:  # type: ignore[override]
        """The diatonic step (0-6)."""
        return self.step

    @property
    def semantic_type(self) -> str:
        return "GenericPitchClass"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "PitchField",
            "pitch_type": "gpc",
        }

    def to(
        self, target_type: type, *, format: str | None = None
    ) -> "GenericPitchClass":
        if target_type is GenericPitchClass or target_type is type(self):
            return self
        raise TypeError(
            f"Cannot convert GenericPitchClass to {target_type.__name__} "
            f"(spelling or octave information required)"
        )

    def get(self, *, format: str | None = None) -> str:
        if 0 <= self.step < 7:
            return _GPC_NAMES[self.step]
        return str(self.step)

    def to_dict(self) -> dict[str, object]:
        return {"pitch_class": self.step}

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> GenericPitchClass | None:
        """Construct from a PyArrow struct row dict ({pitch_class})."""
        pc = row.get("pitch_class")
        if pc is None:
            return None
        return cls(step=int(pc))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, int):
            return self.step == other
        if isinstance(other, GenericPitchClass):
            return self.step == other.step
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.step)

    def __repr__(self) -> str:
        if 0 <= self.step < 7:
            return f"GPC({_GPC_NAMES[self.step]})"
        return f"GPC({self.step})"


# endregion GenericPitchClass

# region GenericPitch


@dataclass(frozen=True, slots=True)
class GenericPitch(TwelveTETPitchMixin):
    """Generic pitch scalar -- diatonic step + octave.

    Represents a pitch in generic (diatonic/steps) space with octave.
    Step is 0-6 (C=0, D=1, ..., B=6).

    Attributes:
        step: Diatonic step (0-6, C=0).
        octave: Octave number.
    """

    step: int
    octave: int

    @property
    def pitch_class(self) -> int:  # type: ignore[override]
        """The diatonic step (0-6)."""
        return self.step

    @property
    def semantic_type(self) -> str:
        return "GenericPitch"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "PitchField",
            "pitch_type": "gp",
        }

    def to(
        self, target_type: type, *, format: str | None = None
    ) -> "TwelveTETPitchMixin":
        if target_type is GenericPitch or target_type is type(self):
            return self
        if target_type is GenericPitchClass:
            return GenericPitchClass(step=self.step)
        raise TypeError(
            f"Cannot convert GenericPitch to {target_type.__name__} "
            f"(accidental information required)"
        )

    def get(self, *, format: str | None = None) -> str:
        if 0 <= self.step < 7:
            return f"{_GPC_NAMES[self.step]}{self.octave}"
        return f"step={self.step}, oct={self.octave}"

    def to_dict(self) -> dict[str, object]:
        return {"pitch_class": self.step, "octave": self.octave}

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> GenericPitch | None:
        """Construct from a PyArrow struct row dict ({pitch_class, octave})."""
        pc = row.get("pitch_class")
        if pc is None:
            return None
        octave = row.get("octave", 4)
        return cls(step=int(pc), octave=int(octave))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, GenericPitch):
            return self.step == other.step and self.octave == other.octave
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.step, self.octave))

    def __repr__(self) -> str:
        if 0 <= self.step < 7:
            return f"GP({_GPC_NAMES[self.step]}{self.octave})"
        return f"GP(step={self.step}, oct={self.octave})"


# endregion GenericPitch

# region SpelledPitchClass


@dataclass(frozen=True, slots=True)
class SpelledPitchClass(TwelveTETPitchMixin):
    """Pitch class with spelling.  Satisfies ``SpelledPitchClassLike``.

    ``fifths`` is automatically derived from ``step`` and ``alter``
    via the line-of-fifths formula.  You need only supply ``step``
    and ``alter``; ``fifths`` is computed in ``__post_init__``.

    Attributes:
        step: Generic pitch class as string (``"C"``, ``"D"``, etc.).
            Stored as ``gpc_str`` in the schema.
        alter: Accidental in semitones (-1=flat, 0=natural, +1=sharp).
            Stored as ``acc`` in the schema.
        fifths: Spelled pitch class in fifths (auto-derived).
            Stored as ``spc_int`` in the schema.
    """

    step: str
    alter: int = 0
    fifths: int = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fifths", _step_alter_to_fifths(self.step, self.alter))

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
            "field_type": "PitchField",
            "pitch_type": "spc",
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
        if target_type is EnharmonicPitchClass:
            return EnharmonicPitchClass(pitch_class=self.pitch_class)  # type: ignore[return-value]
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

    def to_dict(self) -> dict[str, object]:
        """Return a dict mirroring the SPC storage struct.

        Returns:
            A dict with ``gpc_str``, ``acc``, ``spc_int`` storage fields,
            plus derived ``pitch_class`` and ``label``.
        """
        return {
            "gpc_str": self.step,
            "acc": self.alter,
            "spc_int": self.fifths,
            "pitch_class": self.pitch_class,
            "label": self.get(),
        }

    @classmethod
    def from_label(cls, label: str) -> SpelledPitchClass:
        """Construct from a pitch label string.

        Parses labels like ``"C#"``, ``"Bb"``, ``"D♯"``, ``"F♭"``.
        Any octave portion is ignored.

        Args:
            label: A pitch label string.

        Returns:
            A ``SpelledPitchClass``.

        Raises:
            ValueError: If the label cannot be parsed.

        Examples:
            >>> SpelledPitchClass.from_label("C#")
            SpelledPitchClass(C♯)
            >>> SpelledPitchClass.from_label("Bb")
            SpelledPitchClass(B♭)
        """
        step, alter, _ = _parse_pitch_label(label)
        return cls(step=step, alter=alter)

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
        )

    def __repr__(self) -> str:
        return f"SpelledPitchClass({self.get()})"


# endregion SpelledPitchClass

# region MidiPitch


@dataclass(frozen=True, slots=True)
class MidiPitch(TwelveTETPitchMixin):
    """MIDI-keyboard pitch scalar.  Satisfies ``EnharmonicPitchLike``.

    ``MidiPitch`` is **distinct** from ``EnharmonicPitch`` (they are not
    aliases).  This scalar is reserved for the planned ``MidiField``, which
    represents a MIDI-keyboard pitch carrying velocity / channel / program
    context.  For score-level pitch data with ``pitch_type="ep"``, use
    ``EnharmonicPitch`` instead — that is what ``PitchField`` constructs.

    The "MIDI" qualifier here denotes the keyboard / device sense
    (note-on/note-off events with velocity), not merely a MIDI note number.

    Attributes:
        midi_number: MIDI note number (0-127).
        pitch_class: Pitch class (0-11, C=0), auto-derived from ``midi_number``.
    """

    midi_number: int
    pitch_class: int = field(init=False)  # type: ignore[override]

    def __post_init__(self) -> None:
        object.__setattr__(self, "pitch_class", self.midi_number % 12)

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
            "field_type": "PitchField",
            "pitch_type": "ep",
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
        if target_type is EnharmonicPitchClass:
            return EnharmonicPitchClass(pitch_class=self.pitch_class)
        raise TypeError(
            f"Cannot convert MidiPitch to {target_type.__name__} "
            f"(spelling information required for specific pitch types)"
        )

    def get(self, *, format: str | None = None) -> str:
        """Return string representation.

        Args:
            format: ``"midi"`` (default) returns MIDI number as string.
        """
        return str(self.midi_number)

    def to_dict(self) -> dict[str, object]:
        """Return a dict mirroring the EP storage struct.

        Returns:
            A dict with ``ep`` (MIDI number) and ``epc`` (pitch class)
            storage fields, plus derived ``octave``.
        """
        return {
            "ep": self.midi_number,
            "epc": self.pitch_class,
            "octave": self.octave,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> MidiPitch | None:
        """Construct from a PyArrow struct row dict.

        Accepts the ``midi_pitch`` (EP) struct: ``{ep: int64, epc: int64}``.
        Only ``ep`` is required; ``epc`` is ignored (derived from ``ep``).

        Args:
            row: Dict with storage field names.

        Returns:
            A ``MidiPitch``, or ``None`` if ``ep`` is null.
        """
        ep = row.get("ep")
        if ep is None:
            return None
        return cls(midi_number=int(ep))

    def __repr__(self) -> str:
        return f"MidiPitch(midi={self.midi_number}, pc={self.pitch_class})"


# endregion MidiPitch

# region EnharmonicPitch

# Note name labels for enharmonic display (pick the sharp spelling for black keys)
_EP_LABELS: tuple[str, ...] = (
    "C",
    "C\u266f",
    "D",
    "E\u266d",
    "E",
    "F",
    "F\u266f",
    "G",
    "A\u266d",
    "A",
    "B\u266d",
    "B",
)


@dataclass(frozen=True, slots=True)
class EnharmonicPitch(TwelveTETPitchMixin):
    """Enharmonic pitch scalar -- MIDI number with pitch-name display.

    Unlike ``MidiPitch`` (reserved for the future ``MidiField``), this scalar
    represents a pitch in semitone space and displays as a note name + octave
    (e.g. ``EnharmonicPitch(C4)``).  Enharmonic equivalents are equal.

    Attributes:
        midi_number: MIDI note number (0-127).
        pitch_class: Pitch class (0-11, C=0), auto-derived.
    """

    midi_number: int
    pitch_class: int = field(init=False)  # type: ignore[override]

    def __post_init__(self) -> None:
        object.__setattr__(self, "pitch_class", self.midi_number % 12)

    @property
    def octave(self) -> int:
        """Octave number (C4 = 60 -> octave 4)."""
        return (self.midi_number // 12) - 1

    @property
    def semantic_type(self) -> str:
        return "EnharmonicPitch"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "PitchField",
            "pitch_type": "ep",
        }

    def to(
        self, target_type: type, *, format: str | None = None
    ) -> "TwelveTETPitchMixin":
        if target_type is EnharmonicPitch or target_type is type(self):
            return self
        if target_type is EnharmonicPitchClass:
            return EnharmonicPitchClass(pitch_class=self.pitch_class)
        raise TypeError(
            f"Cannot convert EnharmonicPitch to {target_type.__name__} "
            f"(spelling information required for specific pitch types)"
        )

    def get(self, *, format: str | None = None) -> str:
        if format == "midi":
            return str(self.midi_number)
        return f"{_EP_LABELS[self.pitch_class]}{self.octave}"

    def to_dict(self) -> dict[str, object]:
        return {
            "ep": self.midi_number,
            "epc": self.pitch_class,
            "octave": self.octave,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> EnharmonicPitch | None:
        """Construct from a PyArrow struct row dict ({ep, epc})."""
        ep = row.get("ep")
        if ep is None:
            return None
        return cls(midi_number=int(ep))

    def __repr__(self) -> str:
        return f"EnharmonicPitch({_EP_LABELS[self.pitch_class]}{self.octave})"


# endregion EnharmonicPitch

# region SpelledPitch


@dataclass(frozen=True, slots=True)
class SpelledPitch(TwelveTETPitchMixin):
    """Spelled pitch scalar with full enharmonic identity.

    Satisfies ``SpecificPitchLike``.  Re-exported as ``SpecificPitch`` (the
    protocol-name form); both names refer to this same class.

    Called "specific" at the schema/field level because it preserves the
    *specific* enharmonic spelling (C♯4 ≠ D♭4).

    Wraps the ``spelled_pitch`` struct from ``NoteEventData``:
    ``{gpc_int, gpc_str, acc, spc_int, spc_str, sp, cents}``.

    ``fifths`` is automatically derived from ``step`` and ``alter``.

    Attributes:
        step: Generic pitch class as string (from ``gpc_str``).
        alter: Accidental in semitones (from ``acc``).
        octave: Octave number (derived from ``sp``).
        fifths: Spelled pitch class in fifths (auto-derived).
        cents: Cents deviation from 12-TET.
    """

    step: str
    alter: int
    octave: int
    fifths: int = field(init=False)
    cents: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "fifths", _step_alter_to_fifths(self.step, self.alter))

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
            "field_type": "PitchField",
            "pitch_type": "sp",
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
            return MidiPitch(midi_number=self.midi_number)
        if target_type is EnharmonicPitchClass:
            return EnharmonicPitchClass(pitch_class=self.pitch_class)
        if target_type is SpelledPitchClass:
            return SpelledPitchClass(
                step=self.step,
                alter=self.alter,
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

    def to_dict(self) -> dict[str, object]:
        """Return a dict mirroring the SP storage struct.

        Returns:
            A dict with ``gpc_int``, ``gpc_str``, ``acc``, ``spc_int``,
            ``spc_str``, ``sp``, ``cents`` storage fields, plus derived
            ``midi_number`` and ``pitch_class``.
        """
        return {
            "gpc_int": _STEP_TO_GPC[self.step],
            "gpc_str": self.step,
            "acc": self.alter,
            "spc_int": self.fifths,
            "spc_str": self.get().rstrip("0123456789-"),
            "sp": self.get(),
            "cents": self.cents,
            "midi_number": self.midi_number,
            "pitch_class": self.pitch_class,
        }

    @classmethod
    def from_label(cls, label: str) -> SpelledPitch:
        """Construct from a pitch label string.

        Parses labels like ``"C#4"``, ``"Bb3"``, ``"D♯5"``.
        Octave is **required**.

        Args:
            label: A pitch label string with octave (e.g. ``"C#4"``).

        Returns:
            A ``SpelledPitch``.

        Raises:
            ValueError: If the label cannot be parsed or has no octave.

        Examples:
            >>> SpelledPitch.from_label("C#4")
            SpelledPitch(C♯4)
            >>> SpelledPitch.from_label("Bb3")
            SpelledPitch(B♭3)
        """
        step, alter, octave = _parse_pitch_label(label)
        if octave is None:
            raise ValueError(
                f"Octave required for SpelledPitch, got {label!r}. "
                f"Use SpelledPitchClass.from_label() for octave-free pitches."
            )
        return cls(step=step, alter=alter, octave=octave)

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
        cents = float(row.get("cents", 0.0) or 0.0)
        # Extract octave from 'sp' string (e.g. "C4" -> 4)
        sp = row.get("sp", "")
        octave = _parse_octave_from_sp(sp, str(step))
        return cls(
            step=str(step),
            alter=alter,
            octave=octave,
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


# Protocol-name re-export: ``SpecificPitch`` is the same class as ``SpelledPitch``.
# "Specific" because it preserves the specific enharmonic spelling (C♯4 ≠ D♭4).
SpecificPitch = SpelledPitch

# endregion SpelledPitch
