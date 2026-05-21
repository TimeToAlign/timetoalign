"""Pitch scalars for the Time To Align! type hierarchy.

Provides pydantic v2 frozen ``BaseModel`` scalars at multiple levels of
pitch specificity:

- ``EnharmonicPitchClass`` -- chromatic pitch class 0-11 (satisfies ``GenericPitchLike``)
- ``GenericPitchClass`` -- diatonic step 0-6
- ``GenericPitch`` -- diatonic step + octave
- ``SpecificPitchClass`` -- pitch class with spelling (satisfies ``SpecificPitchClassLike``)
- ``EnharmonicPitch`` -- pitch in semitone space displayed as note-name + octave
  (satisfies ``EnharmonicPitchLike``)
- ``MidiPitch`` -- display subclass of ``EnharmonicPitch`` (same data,
  raw-MIDI display) reserved as the default scalar for ``MidiField``
- ``SpecificPitch`` -- full spelling with octave (satisfies ``SpecificPitchLike``)

``MidiPitch`` is a thin subclass of ``EnharmonicPitch``: identical data and
storage struct, differing only in ``__repr__`` and the ``semantic_type``
string. ``EnharmonicPitch`` is the canonical scalar for ``ep`` columns on
score-level pitch data; ``MidiPitch`` exists so that ``MidiField`` rows
display as ``MidiPitch(60)`` instead of ``EnharmonicPitch(C4)`` —
keyboard/MIDI context such as velocity/channel/program lives on the field
(or on the WP7 ``MidiEvent`` scalar), not on these pitch scalars.

All 12-TET scalars compose ``TwelveTETPitchMixin`` which provides the
unified ``.to()`` dispatch method and ``.get(format=)`` formatting.  The
mixin coexists with ``BaseModel`` via plain multiple inheritance.

Each scalar is a ``BaseModel`` with ``model_config = ConfigDict(frozen=True)``.
WP2 migrates this file in bulk away from the previous ``@dataclass(frozen=True,
slots=True)`` implementation; per-scalar storage shapes collapse to the
minimal field set (per CLAUDE.md §9).  ``from_row()`` / ``to_dict()`` survive
as internal storage shims so existing PitchField round-trips keep working
during WP3.  Bulk SemanticField construction uses the column-builder pattern
over ``T.model_fields`` (per WP2's locked decision); see
:mod:`timetoalign.core.schemas.column_builder`.
"""

from __future__ import annotations

import re
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
    "C♯/D♭",
    "D",
    "D♯/E♭",
    "E",
    "F",
    "F♯/G♭",
    "G",
    "G♯/A♭",
    "A",
    "A♯/B♭",
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

_SPECIFIC_PITCH_STEPS = ("C", "D", "E", "F", "G", "A", "B")
_StepLiteral = Literal["C", "D", "E", "F", "G", "A", "B"]


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
    """
    m = _PITCH_LABEL_RE.match(label.strip())
    if m is None:
        raise ValueError(f"Cannot parse pitch label: {label!r}")
    step = m.group(1).upper()
    acc_str = m.group(2)
    octave_str = m.group(3)

    if not acc_str:
        alter = 0
    elif acc_str[0] in ("#", "♯"):
        alter = len(acc_str)
    else:
        alter = -len(acc_str)

    octave = int(octave_str) if octave_str is not None else None
    return step, alter, octave


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


# region EnharmonicPitchClass


class EnharmonicPitchClass(BaseModel, TwelveTETPitchMixin):
    """Enharmonic pitch class scalar -- chromatic pitch class (0-11).

    Satisfies ``GenericPitchLike``.  Pydantic v2 ``BaseModel``, frozen.
    Storage struct (derived): ``{pitch_class: int64}``.

    Attributes:
        pitch_class: Pitch class (0-11, C=0).
    """

    model_config = ConfigDict(frozen=True)

    pitch_class: int

    def __init__(
        self,
        pitch_class: int | None = None,
        /,
        **data: Any,
    ) -> None:
        if pitch_class is not None:
            if "pitch_class" in data:
                raise TypeError(
                    "EnharmonicPitchClass received conflicting positional and "
                    "keyword arguments"
                )
            data = {"pitch_class": pitch_class, **data}
        super().__init__(**data)

    @property
    def semantic_type(self) -> str:
        return "EnharmonicPitchClass"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "PitchField",
            "pitch_type": "epc",
        }

    def to(
        self, target_type: type, *, format: str | None = None
    ) -> "EnharmonicPitchClass":
        if target_type is EnharmonicPitchClass or target_type is type(self):
            return self
        raise TypeError(
            f"Cannot convert EnharmonicPitchClass to {target_type.__name__} "
            f"(octave and/or spelling information required)"
        )

    def get(self, *, format: str | None = None) -> str:
        return str(self.pitch_class)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> EnharmonicPitchClass | None:
        """Construct from a PyArrow struct row dict ``{pitch_class}``."""
        pc = row.get("pitch_class")
        if pc is None:
            return None
        return cls(pitch_class=int(pc))

    def to_dict(self) -> dict[str, object]:
        return {"pitch_class": self.pitch_class}

    def __eq__(self, other: object) -> bool:
        if isinstance(other, int):
            return self.pitch_class == other
        if isinstance(other, EnharmonicPitchClass):
            return self.pitch_class == other.pitch_class
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("EnharmonicPitchClass", self.pitch_class))

    def __repr__(self) -> str:
        if 0 <= self.pitch_class < 12:
            return f"EPC({_PC_TO_LABEL[self.pitch_class]})"
        return f"EPC({self.pitch_class})"


# endregion EnharmonicPitchClass

# region GenericPitchClass

_GPC_NAMES: tuple[str, ...] = ("C", "D", "E", "F", "G", "A", "B")


class GenericPitchClass(BaseModel, TwelveTETPitchMixin):
    """Generic pitch class scalar -- diatonic step (0-6).

    Pydantic v2 ``BaseModel``, frozen.  Storage struct (derived):
    ``{step: int64}``.

    Attributes:
        step: Diatonic step (0-6, C=0).
    """

    model_config = ConfigDict(frozen=True)

    step: int

    def __init__(
        self,
        step: int | None = None,
        /,
        **data: Any,
    ) -> None:
        if step is not None:
            if "step" in data:
                raise TypeError(
                    "GenericPitchClass received conflicting positional and "
                    "keyword arguments"
                )
            data = {"step": step, **data}
        super().__init__(**data)

    @property
    def pitch_class(self) -> int:  # type: ignore[override]
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
        return hash(("GenericPitchClass", self.step))

    def __repr__(self) -> str:
        if 0 <= self.step < 7:
            return f"GPC({_GPC_NAMES[self.step]})"
        return f"GPC({self.step})"


# endregion GenericPitchClass

# region GenericPitch


class GenericPitch(BaseModel, TwelveTETPitchMixin):
    """Generic pitch scalar -- diatonic step + octave.

    Pydantic v2 ``BaseModel``, frozen.  Storage struct (derived):
    ``{step: int64, octave: int64}``.

    Attributes:
        step: Diatonic step (0-6, C=0).
        octave: Octave number.
    """

    model_config = ConfigDict(frozen=True)

    step: int
    octave: int

    def __init__(
        self,
        step: int | None = None,
        octave: int | None = None,
        /,
        **data: Any,
    ) -> None:
        positional = {
            k: v for k, v in (("step", step), ("octave", octave)) if v is not None
        }
        if positional and any(k in data for k in positional):
            raise TypeError(
                "GenericPitch received conflicting positional and keyword arguments"
            )
        data = {**positional, **data}
        super().__init__(**data)

    @property
    def pitch_class(self) -> int:  # type: ignore[override]
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
        return hash(("GenericPitch", self.step, self.octave))

    def __repr__(self) -> str:
        if 0 <= self.step < 7:
            return f"GP({_GPC_NAMES[self.step]}{self.octave})"
        return f"GP(step={self.step}, oct={self.octave})"


# endregion GenericPitch

# region SpecificPitchClass


class SpecificPitchClass(BaseModel, TwelveTETPitchMixin):
    """Pitch class with spelling.  Satisfies ``SpecificPitchClassLike``.

    Pydantic v2 ``BaseModel``, frozen.  Storage struct (derived):
    ``{step: string, alter: int64}``.  ``fifths`` and ``pitch_class`` are
    ``@computed_field`` properties — derived from ``step`` + ``alter``,
    not stored in the pa.Schema.

    Attributes:
        step: Generic pitch class as letter (``"C"``..``"B"``).
        alter: Accidental in semitones (-1=flat, 0=natural, +1=sharp).
    """

    model_config = ConfigDict(frozen=True)

    step: _StepLiteral
    alter: int = 0

    def __init__(
        self,
        step: str | None = None,
        alter: int | None = None,
        /,
        **data: Any,
    ) -> None:
        positional = {
            k: v for k, v in (("step", step), ("alter", alter)) if v is not None
        }
        if positional and any(k in data for k in positional):
            raise TypeError(
                "SpecificPitchClass received conflicting positional and "
                "keyword arguments"
            )
        data = {**positional, **data}
        super().__init__(**data)

    @field_validator("step", mode="before")
    @classmethod
    def _normalise_step(cls, v: object) -> str:
        if not isinstance(v, str):
            raise TypeError(f"step must be a string, got {type(v).__name__}")
        upper = v.upper()
        if upper not in _SPECIFIC_PITCH_STEPS:
            raise ValueError(f"step must be one of {_SPECIFIC_PITCH_STEPS}, got {v!r}")
        return upper

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fifths(self) -> int:
        """Position on the line of fifths (derived from step + alter)."""
        return _step_alter_to_fifths(self.step, self.alter)

    @property
    def pitch_class(self) -> int:  # type: ignore[override]
        base = _STEP_TO_SEMITONE.get(self.step, 0)
        return (base + self.alter) % 12

    @property
    def semantic_type(self) -> str:
        return "SpecificPitchClass"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "PitchField",
            "pitch_type": "spc",
        }

    def to(
        self, target_type: type, *, format: str | None = None
    ) -> "SpecificPitchClass | EnharmonicPitchClass":
        if target_type is SpecificPitchClass or target_type is type(self):
            return self
        if target_type is EnharmonicPitchClass:
            return EnharmonicPitchClass(pitch_class=self.pitch_class)
        raise TypeError(
            f"Cannot convert SpecificPitchClass to {target_type.__name__} "
            f"(octave information required)"
        )

    def get(self, *, format: str | None = None) -> str:
        alter_str = ""
        if self.alter > 0:
            alter_str = "♯" * self.alter
        elif self.alter < 0:
            alter_str = "♭" * abs(self.alter)
        return f"{self.step}{alter_str}"

    def to_dict(self) -> dict[str, object]:
        """Return a dict mirroring the legacy SPC storage struct.

        Includes derived ``pitch_class`` and ``label`` for backward
        compatibility with the legacy ``SpecificPitchClassSchema`` shape.
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
        """Construct from a pitch label string."""
        step, alter, _ = _parse_pitch_label(label)
        return cls(step=step, alter=alter)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> SpecificPitchClass | None:
        """Construct from the legacy ``specific_pitch_class`` struct."""
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
    "C♯",
    "D",
    "E♭",
    "E",
    "F",
    "F♯",
    "G",
    "A♭",
    "A",
    "B♭",
    "B",
)


class EnharmonicPitch(BaseModel, TwelveTETPitchMixin):
    """Enharmonic pitch scalar -- MIDI number with pitch-name display.

    Pydantic v2 ``BaseModel``, frozen.  Storage collapses to a single
    ``midi_number: int64`` column (per WP1 inventory item #3): the
    previous ``{ep, epc}`` struct stored ``epc`` redundantly with
    ``ep % 12``; the bulk migration removes the redundancy.  ``pitch_class``
    and ``octave`` are ``@property`` (not stored, not in the pa.Schema).

    ``EnharmonicPitch`` is the canonical scalar for the ``ep`` storage
    column on score-level pitch data.

    Attributes:
        midi_number: MIDI note number (0-127).
    """

    model_config = ConfigDict(frozen=True)

    midi_number: int

    def __init__(
        self,
        midi_number: int | None = None,
        /,
        **data: Any,
    ) -> None:
        if midi_number is not None:
            if "midi_number" in data:
                raise TypeError(
                    f"{type(self).__name__} received conflicting positional and "
                    "keyword arguments"
                )
            data = {"midi_number": midi_number, **data}
        super().__init__(**data)

    @property
    def pitch_class(self) -> int:  # type: ignore[override]
        return self.midi_number % 12

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
        """Return a dict mirroring the legacy ``{ep, epc, octave}`` storage.

        Internal use only — preserves backward compatibility with the
        legacy ``EnharmonicPitchSchema`` Parquet round-trip during the
        WP3 alias rollout.  Bulk SemanticField construction uses the
        column-builder pattern over ``model_fields`` instead.
        """
        return {
            "ep": self.midi_number,
            "epc": self.pitch_class,
            "octave": self.octave,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> EnharmonicPitch | None:
        """Construct from a PyArrow struct row dict.

        Accepts either the legacy ``{ep, epc}`` struct or the new
        single-field ``{midi_number}`` struct.
        """
        # Prefer the new minimal field; fall back to the legacy struct.
        if "midi_number" in row and row.get("midi_number") is not None:
            return cls(midi_number=int(row["midi_number"]))
        ep = row.get("ep")
        if ep is None:
            return None
        return cls(midi_number=int(ep))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, EnharmonicPitch):
            return self.midi_number == other.midi_number
        return NotImplemented

    def __hash__(self) -> int:
        # Include the concrete class in the hash so EnharmonicPitch(60) and
        # MidiPitch(60) hash distinctly even though they compare equal under
        # ``__eq__``.
        return hash((type(self).__name__, self.midi_number))

    def __repr__(self) -> str:
        return f"EnharmonicPitch({_EP_LABELS[self.pitch_class]}{self.octave})"


# endregion EnharmonicPitch

# region MidiPitch


class MidiPitch(EnharmonicPitch):
    """Display alias of :class:`EnharmonicPitch` reserved for ``MidiField``.

    Pydantic v2 ``BaseModel`` subclass of ``EnharmonicPitch`` — identical
    data, storage struct, conversions, and protocol conformance.  Differs
    only in ``__repr__``, ``semantic_type``, and the default ``get()``
    format.  MIDI-keyboard context (velocity, channel, program) lives on
    the field / WP7 ``MidiEvent`` scalar, not here; the distinction is
    purely presentational.
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


class SpecificPitch(BaseModel, TwelveTETPitchMixin):
    """Specific pitch scalar with full enharmonic identity.

    Satisfies ``SpecificPitchLike``.

    Called "specific" because it preserves the *specific* enharmonic
    spelling (C♯4 ≠ D♭4).

    WP2 pilot scalar.  The PyArrow storage shape derived from this
    pydantic model is ``{step: string, alter: int64, octave: int64, cents:
    float64?}`` — the minimal set of fields that affords every derivative
    representation.  ``fifths``, ``midi_number``, and ``pitch_class`` are
    derived (``@computed_field`` / ``@property``); they are NOT in the
    pa.Schema and NOT in the Arrow column.

    Attributes:
        step: Generic pitch class as letter.
        alter: Accidental in semitones.
        octave: Octave number (C4 = MIDI 60 → octave 4).
        cents: Cents deviation from 12-TET, or ``None`` if unmeasured.
    """

    model_config = ConfigDict(frozen=True)

    step: _StepLiteral
    alter: int = 0
    octave: int
    cents: float | None = None

    @field_validator("step", mode="before")
    @classmethod
    def _normalise_step(cls, v: object) -> str:
        if not isinstance(v, str):
            raise TypeError(f"step must be a string, got {type(v).__name__}")
        upper = v.upper()
        if upper not in _SPECIFIC_PITCH_STEPS:
            raise ValueError(f"step must be one of {_SPECIFIC_PITCH_STEPS}, got {v!r}")
        return upper

    # --- Computed / derived (NOT in pa.Schema) ----------------------------

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fifths(self) -> int:
        return _step_alter_to_fifths(self.step, self.alter)

    @property
    def midi_number(self) -> int:
        base = _STEP_TO_SEMITONE.get(self.step, 0)
        return (self.octave + 1) * 12 + base + self.alter

    @property
    def pitch_class(self) -> int:  # type: ignore[override]
        base = _STEP_TO_SEMITONE.get(self.step, 0)
        return (base + self.alter) % 12

    @property
    def semantic_type(self) -> str:
        return "SpecificPitch"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "PitchField",
            "pitch_type": "sp",
        }

    def to(
        self, target_type: type, *, format: str | None = None
    ) -> "TwelveTETPitchMixin":
        if target_type is SpecificPitch or target_type is type(self):
            return self
        if target_type is MidiPitch:
            return MidiPitch(midi_number=self.midi_number)
        if target_type is EnharmonicPitchClass:
            return EnharmonicPitchClass(pitch_class=self.pitch_class)
        if target_type is SpecificPitchClass:
            return SpecificPitchClass(step=self.step, alter=self.alter)
        raise TypeError(f"Cannot convert SpecificPitch to {target_type.__name__}")

    def get(self, *, format: str | None = None) -> str:
        if format == "midi":
            return str(self.midi_number)
        alter_str = ""
        if self.alter > 0:
            alter_str = "♯" * self.alter
        elif self.alter < 0:
            alter_str = "♭" * abs(self.alter)
        return f"{self.step}{alter_str}{self.octave}"

    def to_dict(self) -> dict[str, object]:
        """Return a dict mirroring the legacy SP storage struct.

        Internal use only — preserves backward compatibility with the
        existing ``SpecificPitchSchema`` Parquet round-trip during the
        WP3 alias rollout.  Bulk SemanticField construction uses the
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
        ``{gpc_int, gpc_str, acc, spc_int, spc_str, sp, cents}`` OR the
        new minimal struct ``{step, alter, octave, cents}``.

        Regime: **trust boundary** — per-row construction via the
        pydantic model's validators.  Invalid input raises
        ``ValidationError``.  Bulk reads of TTA-written Parquet using
        the new minimal schema go through ``cls.model_construct(...)``.
        """
        # Minimal schema wins if present.
        if "step" in row and row.get("step") is not None:
            cents_raw = row.get("cents")
            cents = float(cents_raw) if cents_raw is not None else None
            # regime: trust boundary — full validators run on construction.
            return cls(
                step=str(row["step"]),
                alter=int(row.get("alter", 0) or 0),
                octave=int(row["octave"]),
                cents=cents,
            )
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


# endregion SpecificPitch
