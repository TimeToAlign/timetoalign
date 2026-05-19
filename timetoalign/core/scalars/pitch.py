"""Pitch scalars for the Time To Align! type hierarchy.

Provides frozen dataclass scalars at multiple levels of pitch specificity:

- ``EnharmonicPitchClass`` -- chromatic pitch class 0-11 (satisfies ``GenericPitchLike``)
- ``GenericPitchClass`` -- diatonic step 0-6
- ``GenericPitch`` -- diatonic step + octave
- ``SpecificPitchClass`` -- pitch class with spelling (satisfies ``SpecificPitchClassLike``)
- ``EnharmonicPitch`` -- pitch in semitone space displayed as note-name + octave,
  used by ``PitchField`` when ``pitch_type="ep"`` (satisfies ``EnharmonicPitchLike``)
- ``MidiPitch`` -- display alias of ``EnharmonicPitch`` (same data, raw-MIDI
  display) reserved as the default scalar for the planned ``MidiField``
- ``SpecificPitch`` -- full spelling with octave (satisfies ``SpecificPitchLike``).
  ``SpecificPitch`` is a re-export of the same class under its protocol name.

``MidiPitch`` is a thin subclass of ``EnharmonicPitch``: identical data and
storage struct, differing only in ``__repr__`` and the ``semantic_type``
string. ``EnharmonicPitch`` is the canonical scalar for ``ep`` columns on
score-level pitch data; ``MidiPitch`` exists so that ``MidiField`` rows
display as ``MidiPitch(60)`` instead of ``EnharmonicPitch(C4)`` —
keyboard/MIDI context such as velocity/channel/program lives on the field,
not on the scalar.

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
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, computed_field, field_validator

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
        Conversion to ``MidiPitch`` or ``SpecificPitch`` requires
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

# region SpecificPitchClass


@dataclass(frozen=True, slots=True)
class SpecificPitchClass(TwelveTETPitchMixin):
    """Pitch class with spelling.  Satisfies ``SpecificPitchClassLike``.

    ``fifths`` is automatically derived from ``step`` and ``alter``
    via the line-of-fifths formula.  You need only supply ``step``
    and ``alter``; ``fifths`` is computed in ``__post_init__``.

    Attributes:
        step: Generic pitch class as string (``"C"``, ``"D"``, etc.).
            Stored as ``gpc_str`` in the schema.
        alter: Accidental in semitones (-1=flat, 0=natural, +1=sharp).
            Stored as ``acc`` in the schema.
        fifths: Specific pitch class in fifths (auto-derived).
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
        return "SpecificPitchClass"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract."""
        return {
            "field_type": "PitchField",
            "pitch_type": "spc",
        }

    def to(
        self, target_type: type, *, format: str | None = None
    ) -> "SpecificPitchClass":
        """Convert to another pitch type.

        Args:
            target_type: Target pitch type.
            format: Optional format specifier.

        Returns:
            A pitch scalar of the target type.

        Raises:
            TypeError: If conversion is not supported.
        """
        if target_type is SpecificPitchClass or target_type is type(self):
            return self
        if target_type is EnharmonicPitchClass:
            return EnharmonicPitchClass(pitch_class=self.pitch_class)  # type: ignore[return-value]
        raise TypeError(
            f"Cannot convert SpecificPitchClass to {target_type.__name__} "
            f"(octave information required)"
        )

    def get(self, *, format: str | None = None) -> str:
        """Return string representation.

        Args:
            format: Format specifier (ignored for SpecificPitchClass).
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
    def from_label(cls, label: str) -> SpecificPitchClass:
        """Construct from a pitch label string.

        Parses labels like ``"C#"``, ``"Bb"``, ``"D♯"``, ``"F♭"``.
        Any octave portion is ignored.

        Args:
            label: A pitch label string.

        Returns:
            A ``SpecificPitchClass``.

        Raises:
            ValueError: If the label cannot be parsed.

        Examples:
            >>> SpecificPitchClass.from_label("C#")
            SpecificPitchClass(C♯)
            >>> SpecificPitchClass.from_label("Bb")
            SpecificPitchClass(B♭)
        """
        step, alter, _ = _parse_pitch_label(label)
        return cls(step=step, alter=alter)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> SpecificPitchClass | None:
        """Construct from a PyArrow struct row dict.

        Accepts the ``specific_pitch_class`` struct:
        ``{gpc_str: string, acc: int64, spc_int: int64}``.

        Args:
            row: Dict with storage field names.

        Returns:
            A ``SpecificPitchClass``, or ``None`` if ``gpc_str`` is null.
        """
        step = row.get("gpc_str")
        if step is None:
            return None
        return cls(
            step=str(step),
            alter=int(row.get("acc", 0) or 0),
        )

    def __repr__(self) -> str:
        return f"SpecificPitchClass({self.get()})"


# endregion SpecificPitchClass

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

    Represents a pitch in semitone space and displays as a note name +
    octave (e.g. ``EnharmonicPitch(C4)``). Enharmonic equivalents are equal.

    ``EnharmonicPitch`` is the canonical scalar for the ``ep`` storage
    column on score-level pitch data; ``MidiField`` will use the
    :class:`MidiPitch` subclass (same data, raw-MIDI-number display).

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
        if target_type is MidiPitch:
            return MidiPitch(midi_number=self.midi_number)
        if target_type is EnharmonicPitchClass:
            return EnharmonicPitchClass(pitch_class=self.pitch_class)
        raise TypeError(
            f"Cannot convert {type(self).__name__} to {target_type.__name__} "
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

# region MidiPitch


@dataclass(frozen=True, slots=True)
class MidiPitch(EnharmonicPitch):
    """Display alias of :class:`EnharmonicPitch` reserved for ``MidiField``.

    ``MidiPitch`` is a thin subclass of ``EnharmonicPitch`` with identical
    data, storage struct (``{ep, epc}``), conversions, and protocol
    conformance. The only differences are:

    * ``__repr__`` shows the bare MIDI number — ``MidiPitch(60)``
    * ``semantic_type`` advertises the alias name — ``"MidiPitch"``
    * ``get()`` defaults to the MIDI-number format

    ``MidiPitch`` is the default scalar for the planned ``MidiField``
    (``tta-guide`` §2.2b / A5.2). MIDI-keyboard context — velocity,
    channel, program — lives on the *field*, not on this scalar; the
    distinction here is purely presentational, so that a MidiField row
    displays as ``MidiPitch(60)`` rather than ``EnharmonicPitch(C4)``.

    For score-level pitch data (``pitch_type="ep"``), ``PitchField``
    keeps returning ``EnharmonicPitch`` — note-name display is more
    useful in that context.
    """

    @property
    def semantic_type(self) -> str:
        return "MidiPitch"

    def get(self, *, format: str | None = None) -> str:
        if format is None or format == "midi":
            return str(self.midi_number)
        return super().get(format=format)

    def __repr__(self) -> str:
        return f"MidiPitch({self.midi_number})"


# endregion MidiPitch

# region SpecificPitch


_SPECIFIC_PITCH_STEPS = ("C", "D", "E", "F", "G", "A", "B")
_StepLiteral = Literal["C", "D", "E", "F", "G", "A", "B"]


class SpecificPitch(BaseModel, TwelveTETPitchMixin):
    """Specific pitch scalar with full enharmonic identity.

    Satisfies ``SpecificPitchLike``.

    Called "specific" because it preserves the *specific* enharmonic
    spelling (C♯4 ≠ D♭4).

    WP2 pilot scalar: defined as a pydantic v2 ``BaseModel``.  The
    PyArrow storage shape derived from this model is
    ``{step: string, alter: int64, octave: int64, cents: float64 nullable}`` —
    the minimal set of fields that affords every derivative
    representation.  ``fifths``, ``midi_number``, and ``pitch_class``
    are ``@computed_field`` properties; they are NOT in the pa.Schema
    and NOT in the Arrow column, per the WP2 locked decision.

    Attributes:
        step: Generic pitch class as letter (``"C"``, ``"D"``, ``"E"``,
            ``"F"``, ``"G"``, ``"A"``, ``"B"``).
        alter: Accidental in semitones (``-1=flat``, ``0=natural``,
            ``+1=sharp``).  Defaults to 0.
        octave: Octave number (C4 = MIDI 60 → octave 4).
        cents: Cents deviation from 12-TET, or ``None`` if not measured.
    """

    model_config = ConfigDict(frozen=True)

    step: _StepLiteral
    alter: int = 0
    octave: int
    cents: float | None = None

    # --- Validators --------------------------------------------------------

    @field_validator("step", mode="before")
    @classmethod
    def _normalise_step(cls, v: object) -> str:
        if not isinstance(v, str):
            raise TypeError(f"step must be a string, got {type(v).__name__}")
        upper = v.upper()
        if upper not in _SPECIFIC_PITCH_STEPS:
            raise ValueError(f"step must be one of {_SPECIFIC_PITCH_STEPS}, got {v!r}")
        return upper

    # --- Computed fields (NOT stored in pa.Schema) -------------------------

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fifths(self) -> int:
        """Position on the line of fifths.

        Computed field — derived from ``step + alter``.  NOT stored in
        the pa.Schema and NOT in the Arrow column.  Materialises on
        access.
        """
        return _step_alter_to_fifths(self.step, self.alter)

    @property
    def midi_number(self) -> int:
        """MIDI note number computed from step, alter, octave (C4 = 60)."""
        base = _STEP_TO_SEMITONE.get(self.step, 0)
        return (self.octave + 1) * 12 + base + self.alter

    @property
    def pitch_class(self) -> int:  # type: ignore[override]
        """Pitch class (0-11) derived from step and alter."""
        base = _STEP_TO_SEMITONE.get(self.step, 0)
        return (base + self.alter) % 12

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "SpecificPitch"

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
        if target_type is SpecificPitch or target_type is type(self):
            return self
        if target_type is MidiPitch:
            return MidiPitch(midi_number=self.midi_number)
        if target_type is EnharmonicPitchClass:
            return EnharmonicPitchClass(pitch_class=self.pitch_class)
        if target_type is SpecificPitchClass:
            return SpecificPitchClass(
                step=self.step,
                alter=self.alter,
            )
        raise TypeError(f"Cannot convert SpecificPitch to {target_type.__name__}")

    def get(self, *, format: str | None = None) -> str:
        """Return string representation.

        Args:
            format: ``"specific"`` (default) returns e.g. ``"C♯4"``.
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

    # --- Legacy storage struct mapping ------------------------------------
    #
    # The "legacy SP storage struct" referenced below is
    # ``{gpc_int, gpc_str, acc, spc_int, spc_str, sp, cents}`` — the
    # over-specified shape used in NoteEventData _before_ the WP2 pilot.
    # ``to_dict()`` and ``from_row()`` are the two-way mapping between
    # that legacy struct and the new minimal pydantic model; they keep
    # existing PitchField round-trips working during the bulk migration.
    # Tutorials / docs MUST use ``from_*()`` constructors (CLAUDE.md §9);
    # ``from_row`` / ``to_dict`` are internal.

    def to_dict(self) -> dict[str, object]:
        """Return a dict mirroring the legacy SP storage struct.

        Internal use only — preserves backward compatibility with the
        existing ``SpecificPitchSchema`` Parquet round-trip during the
        bulk migration.  Bulk SemanticField construction uses the
        column-builder pattern over ``model_fields``, NOT this method.
        """
        return {
            "gpc_int": _STEP_TO_GPC[self.step],
            "gpc_str": self.step,
            "acc": self.alter,
            "spc_int": self.fifths,
            "spc_str": self.get().rstrip("0123456789-"),
            "sp": self.get(),
            "cents": self.cents if self.cents is not None else 0.0,
            "midi_number": self.midi_number,
            "pitch_class": self.pitch_class,
        }

    @classmethod
    def from_label(cls, label: str) -> SpecificPitch:
        """Construct from a pitch label string.

        Parses labels like ``"C#4"``, ``"Bb3"``, ``"D♯5"``.
        Octave is **required**.

        Args:
            label: A pitch label string with octave (e.g. ``"C#4"``).

        Returns:
            A ``SpecificPitch``.

        Raises:
            ValueError: If the label cannot be parsed or has no octave.

        Examples:
            >>> SpecificPitch.from_label("C#4")
            SpecificPitch(C♯4)
            >>> SpecificPitch.from_label("Bb3")
            SpecificPitch(B♭3)
        """
        step, alter, octave = _parse_pitch_label(label)
        if octave is None:
            raise ValueError(
                f"Octave required for SpecificPitch, got {label!r}. "
                f"Use SpecificPitchClass.from_label() for octave-free pitches."
            )
        return cls(step=step, alter=alter, octave=octave)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "SpecificPitch | None":
        """Construct from a PyArrow struct row dict (trust-boundary regime).

        Accepts the legacy SP storage struct
        ``{gpc_int, gpc_str, acc, spc_int, spc_str, sp, cents}``.

        Regime: **trust boundary** — per-row construction via the
        pydantic model's validators.  Invalid input raises
        ``ValidationError``.  Bulk reads of TTA-written Parquet using
        the new minimal schema should go through
        ``cls.model_construct(...)`` instead.

        Args:
            row: Dict with legacy SP storage field names.

        Returns:
            A ``SpecificPitch``, or ``None`` if ``gpc_str`` is null.
        """
        step = row.get("gpc_str")
        if step is None:
            return None
        alter = int(row.get("acc", 0) or 0)
        cents_raw = row.get("cents")
        cents = float(cents_raw) if cents_raw is not None else None
        sp = row.get("sp", "")
        octave = _parse_octave_from_sp(sp, str(step))
        # regime: trust boundary — full validators run on construction.
        return cls(
            step=str(step),
            alter=alter,
            octave=octave,
            cents=cents,
        )

    def __repr__(self) -> str:
        return f"SpecificPitch({self.get()})"


def _parse_octave_from_sp(sp: str | None, step: str) -> int:
    """Extract octave number from a specific-pitch string like ``"C4"``."""
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


# endregion SpecificPitch
