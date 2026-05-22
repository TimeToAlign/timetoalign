"""Event-level scalars and their paired SemanticField wrappers.

This is the catch-all module for TTA scalar types that are not the
fundamental Coordinate / Duration pair.  Each scalar is followed
immediately by its ``XField(SemanticField[X])`` class in the same file
— the paired Object + ObjectField is the unit of code organisation
and is never split across files (see Contributing → §2.4
Architectural decision log).

Sections (in file order):

* Pitch scalars + paired Fields (7 pairs)
* Harmony scalars + paired Fields (5 pairs) — plus the DCML import
  schemas (``DcmlStorageSchema`` etc.) and the ``Inversion`` enum.
* Event scalars + paired Fields (Note, Measure)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, ClassVar, Literal

import pyarrow as pa
from pydantic import BaseModel, ConfigDict, computed_field, field_validator

from .fields import (
    SemanticField,
    register_value_projector,
)
from .ids import ScopedId
from .protocols import TwelveTETPitchMixin
from .time import Coordinate, Duration

# ═══════════════════════════════════════════════════════════════════════════
# 1. PITCH — scalars and paired Fields
# ═══════════════════════════════════════════════════════════════════════════

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
    """Compute line-of-fifths position from step and alter."""
    return _BASE_FIFTHS.get(step, 0) + (7 * alter)


def _parse_pitch_label(label: str) -> tuple[str, int, int | None]:
    """Parse a pitch label string into (step, alter, octave_or_None)."""
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


# ---------------------------------------------------------------------------
# EnharmonicPitchClass + EnharmonicPitchClassField
# ---------------------------------------------------------------------------


class EnharmonicPitchClass(BaseModel, TwelveTETPitchMixin):
    """Enharmonic pitch class scalar -- chromatic pitch class (0-11).

    Pydantic v2 ``BaseModel``, frozen.  Storage struct (derived):
    ``{pitch_class: int64}``.
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
            "field_type": "EnharmonicPitchClassField",
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


class EnharmonicPitchClassField(SemanticField[EnharmonicPitchClass]):
    """Columnar wrapper for ``EnharmonicPitchClass`` (paired Field)."""


# ---------------------------------------------------------------------------
# GenericPitchClass + GenericPitchClassField
# ---------------------------------------------------------------------------

_GPC_NAMES: tuple[str, ...] = ("C", "D", "E", "F", "G", "A", "B")


class GenericPitchClass(BaseModel, TwelveTETPitchMixin):
    """Generic pitch class scalar -- diatonic step (0-6).

    Pydantic v2 ``BaseModel``, frozen.  Storage struct (derived):
    ``{step: int64}``.
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
            "field_type": "GenericPitchClassField",
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
            pc = row.get("step")
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


class GenericPitchClassField(SemanticField[GenericPitchClass]):
    """Columnar wrapper for ``GenericPitchClass`` (paired Field)."""


# ---------------------------------------------------------------------------
# GenericPitch + GenericPitchField
# ---------------------------------------------------------------------------


class GenericPitch(BaseModel, TwelveTETPitchMixin):
    """Generic pitch scalar -- diatonic step + octave.

    Pydantic v2 ``BaseModel``, frozen.  Storage struct (derived):
    ``{step: int64, octave: int64}``.
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
            "field_type": "GenericPitchField",
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
            pc = row.get("step")
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


class GenericPitchField(SemanticField[GenericPitch]):
    """Columnar wrapper for ``GenericPitch`` (paired Field)."""


# ---------------------------------------------------------------------------
# SpecificPitchClass + SpecificPitchClassField
# ---------------------------------------------------------------------------


class SpecificPitchClass(BaseModel, TwelveTETPitchMixin):
    """Pitch class with spelling.

    Pydantic v2 ``BaseModel``, frozen.  Storage struct (derived):
    ``{step: string, alter: int64}``.  ``fifths`` and ``pitch_class`` are
    derived (not stored).
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
            "field_type": "SpecificPitchClassField",
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
        return {
            "step": self.step,
            "alter": self.alter,
            "pitch_class": self.pitch_class,
            "fifths": self.fifths,
            "label": self.get(),
        }

    @classmethod
    def from_label(cls, label: str) -> SpecificPitchClass:
        step, alter, _ = _parse_pitch_label(label)
        return cls(step=step, alter=alter)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> SpecificPitchClass | None:
        step = row.get("step") or row.get("gpc_str")
        if step is None:
            return None
        alter = row.get("alter")
        if alter is None:
            alter = row.get("acc", 0)
        return cls(
            step=str(step),
            alter=int(alter or 0),
        )

    def __repr__(self) -> str:
        return f"SpecificPitchClass({self.get()})"


class SpecificPitchClassField(SemanticField[SpecificPitchClass]):
    """Columnar wrapper for ``SpecificPitchClass`` (paired Field)."""


# ---------------------------------------------------------------------------
# EnharmonicPitch + EnharmonicPitchField
# ---------------------------------------------------------------------------

# Note name labels for enharmonic display (sharp spelling for black keys)
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

    Pydantic v2 ``BaseModel``, frozen.  Storage struct (derived):
    ``{midi_number: int64}``.  ``pitch_class`` and ``octave`` are
    properties, not stored.
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
        return (self.midi_number // 12) - 1

    @property
    def semantic_type(self) -> str:
        return "EnharmonicPitch"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "EnharmonicPitchField",
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
        return {"midi_number": self.midi_number}

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> EnharmonicPitch | None:
        if "midi_number" in row and row.get("midi_number") is not None:
            return cls(midi_number=int(row["midi_number"]))
        return None

    def __eq__(self, other: object) -> bool:
        if isinstance(other, EnharmonicPitch):
            return self.midi_number == other.midi_number
        return NotImplemented

    def __hash__(self) -> int:
        return hash((type(self).__name__, self.midi_number))

    def __repr__(self) -> str:
        return f"EnharmonicPitch({_EP_LABELS[self.pitch_class]}{self.octave})"


class EnharmonicPitchField(SemanticField[EnharmonicPitch]):
    """Columnar wrapper for ``EnharmonicPitch`` (paired Field).

    The on-disk struct shape is the pydantic-derived
    ``{midi_number: int64}``; cached on the class as ``pa_schema``.
    """


# ---------------------------------------------------------------------------
# MidiPitch + MidiPitchField
# ---------------------------------------------------------------------------


class MidiPitch(EnharmonicPitch):
    """Display alias of :class:`EnharmonicPitch` reserved for ``MidiPitchField``.

    Identical data, storage struct, conversions, and protocol conformance.
    Differs only in ``__repr__``, ``semantic_type``, and the default
    ``get()`` format.
    """

    @property
    def semantic_type(self) -> str:
        return "MidiPitch"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "MidiPitchField",
            "pitch_type": "ep",
        }

    def get(self, *, format: str | None = None) -> str:
        if format is None or format == "midi":
            return str(self.midi_number)
        return super().get(format=format)

    def __repr__(self) -> str:
        return f"MidiPitch({self.midi_number})"


class MidiPitchField(SemanticField[MidiPitch]):
    """Columnar wrapper for ``MidiPitch`` (paired Field).

    Same struct as ``EnharmonicPitchField`` (``MidiPitch`` is a subclass
    of ``EnharmonicPitch``), but with distinct ``scalar_cls`` so
    ``__getitem__`` yields ``MidiPitch`` instances.
    """


# ---------------------------------------------------------------------------
# SpecificPitch + SpecificPitchField
# ---------------------------------------------------------------------------


class SpecificPitch(BaseModel, TwelveTETPitchMixin):
    """Specific pitch scalar with full enharmonic identity.

    Storage struct (derived): ``{step: string, alter: int64, octave: int64,
    cents: float64?}``.  ``fifths``, ``midi_number``, ``pitch_class`` are
    derived (not stored).
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
            "field_type": "SpecificPitchField",
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
        return {
            "step": self.step,
            "alter": self.alter,
            "octave": self.octave,
            "cents": self.cents,
            "fifths": self.fifths,
            "midi_number": self.midi_number,
            "pitch_class": self.pitch_class,
            "label": self.get(),
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

        Accepts the canonical struct ``{step, alter, octave, cents}``.
        """
        if "step" in row and row.get("step") is not None:
            cents_raw = row.get("cents")
            cents = float(cents_raw) if cents_raw is not None else None
            return cls(
                step=str(row["step"]),
                alter=int(row.get("alter", 0) or 0),
                octave=int(row["octave"]),
                cents=cents,
            )
        return None

    def __repr__(self) -> str:
        return f"SpecificPitch({self.get()})"


class SpecificPitchField(SemanticField[SpecificPitch]):
    """Columnar wrapper for ``SpecificPitch`` (paired Field).

    Pa schema: ``{step: string, alter: int64, octave: int64, cents: float64}``.
    """


# ═══════════════════════════════════════════════════════════════════════════
# 2. HARMONY — scalars, paired Fields, plus DCML import schemas
# ═══════════════════════════════════════════════════════════════════════════


class Inversion(IntEnum):
    """Chord inversion as an enum.

    The DCML ``figbass`` string maps to these values.
    """

    ROOT = 0
    FIRST = 1
    SECOND = 2
    THIRD = 3


# DCML figbass -> Inversion enum mapping
FIGBASS_TO_INVERSION: dict[str, Inversion] = {
    "": Inversion.ROOT,
    "7": Inversion.ROOT,
    "6": Inversion.FIRST,
    "64": Inversion.SECOND,
    "2": Inversion.THIRD,
    "65": Inversion.FIRST,
    "43": Inversion.SECOND,
    "42": Inversion.THIRD,
}


def figbass_to_inversion(figbass: str) -> Inversion | None:
    """Convert a DCML ``figbass`` string to an ``Inversion`` enum member.

    Args:
        figbass: The DCML figured bass string.

    Returns:
        The corresponding ``Inversion`` enum member, or ``None`` if
        the string is not a recognised figured bass.
    """
    if not figbass:
        return Inversion.ROOT
    return FIGBASS_TO_INVERSION.get(figbass)


# ---------------------------------------------------------------------------
# DCML import schemas — distinct from the canonical paired XField.pa_schema.
# These are the *external* DCML TSV column layouts used at the import edge.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HarmonyBaseSchema:
    """Minimal harmony schema: label and codec standard.

    Storage struct::

        {label: string, standard: string}
    """

    label: str = "label"
    standard: str = "standard"

    schema: ClassVar[pa.StructType] = pa.struct(
        [
            pa.field("label", pa.string(), nullable=True),
            pa.field("standard", pa.string(), nullable=True),
        ]
    )


@dataclass(frozen=True)
class WesternTertianSchema:
    """Schema for Western tertian harmony import: root, bass, chord type, inversion."""

    label: str = "label"
    standard: str = "standard"
    root: str = "root"
    bass: str = "bass"
    chord_type: str = "chord_type"
    inversion: str = "inversion"

    schema: ClassVar[pa.StructType] = pa.struct(
        [
            pa.field("label", pa.string(), nullable=True),
            pa.field("standard", pa.string(), nullable=True),
            pa.field("root", pa.int64(), nullable=True),
            pa.field("bass", pa.int64(), nullable=True),
            pa.field("chord_type", pa.string(), nullable=True),
            pa.field("inversion", pa.int64(), nullable=True),
        ]
    )


@dataclass(frozen=True)
class RomanNumeralSchema:
    """Schema for Roman numeral harmony import: adds numeral, localkey, globalkey."""

    label: str = "label"
    standard: str = "standard"
    root: str = "root"
    bass: str = "bass"
    chord_type: str = "chord_type"
    inversion: str = "inversion"
    numeral: str = "numeral"
    localkey: str = "localkey"
    globalkey: str = "globalkey"
    key_context: str = "key_context"

    schema: ClassVar[pa.StructType] = pa.struct(
        [
            pa.field("label", pa.string(), nullable=True),
            pa.field("standard", pa.string(), nullable=True),
            pa.field("root", pa.int64(), nullable=True),
            pa.field("bass", pa.int64(), nullable=True),
            pa.field("chord_type", pa.string(), nullable=True),
            pa.field("inversion", pa.int64(), nullable=True),
            pa.field("numeral", pa.string(), nullable=True),
            pa.field("localkey", pa.string(), nullable=True),
            pa.field("globalkey", pa.string(), nullable=True),
            pa.field("key_context", pa.string(), nullable=True),
        ]
    )


@dataclass(frozen=True)
class DcmlStorageSchema:
    """Storage schema for DCML harmony labels (the raw DCML TSV columns).

    Import-edge schema, NOT the canonical ``DcmlHarmonyField.pa_schema``.
    Used by external DCML reads which then map to internal model via
    ``DcmlHarmony.from_row``.
    """

    label: str = "label"
    globalkey: str = "globalkey"
    localkey: str = "localkey"
    numeral: str = "numeral"
    form: str = "form"
    figbass: str = "figbass"
    chord_type: str = "chord_type"
    root: str = "root"
    bass_note: str = "bass_note"

    schema: ClassVar[pa.StructType] = pa.struct(
        [
            pa.field("label", pa.string(), nullable=True),
            pa.field("globalkey", pa.string(), nullable=True),
            pa.field("localkey", pa.string(), nullable=True),
            pa.field("numeral", pa.string(), nullable=True),
            pa.field("form", pa.string(), nullable=True),
            pa.field("figbass", pa.string(), nullable=True),
            pa.field("chord_type", pa.string(), nullable=True),
            pa.field("root", pa.int64(), nullable=True),
            pa.field("bass_note", pa.int64(), nullable=True),
        ]
    )


# ---------------------------------------------------------------------------
# Harmony scalars + paired Fields
# ---------------------------------------------------------------------------


class HarmonyLabel(BaseModel):
    """Root harmony scalar.

    Pydantic v2 ``BaseModel``, frozen.  Minimal: label + standard.
    """

    model_config = ConfigDict(frozen=True)

    label: str
    standard: str

    @property
    def semantic_type(self) -> str:
        return "HarmonyLabel"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "HarmonyLabelField",
            "standard": self.standard,
        }

    def to_dict(self) -> dict[str, object]:
        return {"label": self.label, "standard": self.standard}

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> HarmonyLabel | None:
        label = row.get("label")
        if label is None:
            return None
        return cls(label=str(label), standard=str(row.get("standard") or ""))

    def __repr__(self) -> str:
        return f"HarmonyLabel(label={self.label!r}, standard={self.standard!r})"


class HarmonyLabelField(SemanticField[HarmonyLabel]):
    """Columnar wrapper for ``HarmonyLabel`` (paired Field)."""


class PitchBasedHarmony(BaseModel):
    """Harmony with root and bass (OHR model)."""

    model_config = ConfigDict(frozen=True)

    label: str
    standard: str
    root: int | None = None
    bass: int | None = None

    @property
    def semantic_type(self) -> str:
        return "PitchBasedHarmony"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "PitchBasedHarmonyField",
            "standard": self.standard,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "standard": self.standard,
            "root": self.root,
            "bass": self.bass,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> PitchBasedHarmony | None:
        label = row.get("label")
        if label is None:
            return None
        root_raw = row.get("root")
        bass_raw = row.get("bass", row.get("bass_note"))
        return cls(
            label=str(label),
            standard=str(row.get("standard") or ""),
            root=int(root_raw) if root_raw is not None else None,
            bass=int(bass_raw) if bass_raw is not None else None,
        )

    def __repr__(self) -> str:
        return f"PitchBasedHarmony(label={self.label!r}, root={self.root})"


class PitchBasedHarmonyField(SemanticField[PitchBasedHarmony]):
    """Columnar wrapper for ``PitchBasedHarmony`` (paired Field)."""


class WesternTertianHarmony(BaseModel):
    """Western tertian chord."""

    model_config = ConfigDict(frozen=True)

    label: str
    standard: str
    root: int | None = None
    bass: int | None = None
    chord_type: str = ""
    inversion: int | None = None

    @property
    def semantic_type(self) -> str:
        return "WesternTertianHarmony"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "WesternTertianHarmonyField",
            "standard": self.standard,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "standard": self.standard,
            "root": self.root,
            "bass": self.bass,
            "chord_type": self.chord_type,
            "inversion": self.inversion,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> WesternTertianHarmony | None:
        label = row.get("label")
        if label is None:
            return None
        root_raw = row.get("root")
        bass_raw = row.get("bass", row.get("bass_note"))
        inversion_raw = row.get("inversion")
        if inversion_raw is None and "figbass" in row:
            inv = figbass_to_inversion(str(row.get("figbass") or ""))
            inversion_raw = int(inv) if inv is not None else None
        return cls(
            label=str(label),
            standard=str(row.get("standard") or ""),
            root=int(root_raw) if root_raw is not None else None,
            bass=int(bass_raw) if bass_raw is not None else None,
            chord_type=str(row.get("chord_type") or ""),
            inversion=int(inversion_raw) if inversion_raw is not None else None,
        )

    def __repr__(self) -> str:
        return (
            f"WesternTertianHarmony(label={self.label!r}, "
            f"chord_type={self.chord_type!r})"
        )


class WesternTertianHarmonyField(SemanticField[WesternTertianHarmony]):
    """Columnar wrapper for ``WesternTertianHarmony`` (paired Field)."""


class RomanNumeralHarmony(BaseModel):
    """Roman-numeral analysis."""

    model_config = ConfigDict(frozen=True)

    label: str
    standard: str
    root: int | None = None
    bass: int | None = None
    chord_type: str = ""
    inversion: int | None = None
    numeral: str = ""
    localkey: str = ""
    globalkey: str = ""

    @property
    def semantic_type(self) -> str:
        return "RomanNumeralHarmony"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "RomanNumeralHarmonyField",
            "standard": self.standard,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "standard": self.standard,
            "root": self.root,
            "bass": self.bass,
            "chord_type": self.chord_type,
            "inversion": self.inversion,
            "numeral": self.numeral,
            "localkey": self.localkey,
            "globalkey": self.globalkey,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> RomanNumeralHarmony | None:
        label = row.get("label")
        if label is None:
            return None
        root_raw = row.get("root")
        bass_raw = row.get("bass", row.get("bass_note"))
        inversion_raw = row.get("inversion")
        if inversion_raw is None and "figbass" in row:
            inv = figbass_to_inversion(str(row.get("figbass") or ""))
            inversion_raw = int(inv) if inv is not None else None
        return cls(
            label=str(label),
            standard=str(row.get("standard") or ""),
            root=int(root_raw) if root_raw is not None else None,
            bass=int(bass_raw) if bass_raw is not None else None,
            chord_type=str(row.get("chord_type") or ""),
            inversion=int(inversion_raw) if inversion_raw is not None else None,
            numeral=str(row.get("numeral") or ""),
            localkey=str(row.get("localkey") or ""),
            globalkey=str(row.get("globalkey") or ""),
        )

    def __repr__(self) -> str:
        return (
            f"RomanNumeralHarmony(label={self.label!r}, "
            f"numeral={self.numeral!r}, key={self.globalkey}:{self.localkey})"
        )


class RomanNumeralHarmonyField(SemanticField[RomanNumeralHarmony]):
    """Columnar wrapper for ``RomanNumeralHarmony`` (paired Field)."""


class DcmlHarmony(BaseModel):
    """DCML harmony annotation.  ``standard`` pinned to ``Literal["dcml"]``."""

    model_config = ConfigDict(frozen=True)

    label: str
    standard: Literal["dcml"] = "dcml"
    root: int | None = None
    bass: int | None = None
    chord_type: str = ""
    inversion: int | None = None
    numeral: str = ""
    localkey: str = ""
    globalkey: str = ""
    tonicized_key: str | None = None
    pedal: str | None = None

    @property
    def semantic_type(self) -> str:
        return "DcmlHarmony"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "DcmlHarmonyField",
            "standard": "dcml",
        }

    def to_dict(self) -> dict[str, object]:
        """Return a summary dict of all harmony properties.

        Root and bass are shown both as pitch class integers and as
        ``EnharmonicPitchClass`` objects for readability.
        """
        root_gpc = (
            EnharmonicPitchClass(pitch_class=self.root)
            if self.root is not None
            else None
        )
        bass_gpc = (
            EnharmonicPitchClass(pitch_class=self.bass)
            if self.bass is not None
            else None
        )
        return {
            "label": self.label,
            "numeral": self.numeral,
            "chord_type": self.chord_type,
            "inversion": self.inversion,
            "root": root_gpc,
            "bass": bass_gpc,
            "globalkey": self.globalkey,
            "localkey": self.localkey,
            "tonicized_key": self.tonicized_key,
        }

    @classmethod
    def from_label(
        cls,
        label: str,
        *,
        globalkey: str = "C",
        localkey: str = "I",
    ) -> DcmlHarmony:
        """Construct a fully populated ``DcmlHarmony`` from a DCML label string."""
        from ms3.expand_dcml import features2type
        from ms3.utils import fifths2pc, roman_numeral2fifths
        from ms3.utils.constants import DCML_REGEX

        m = DCML_REGEX.match(label)
        if m is None:
            raise ValueError(f"Cannot parse DCML label: {label!r}")

        parts = {k: v for k, v in m.groupdict().items() if v is not None}
        numeral = parts.get("numeral", "")
        form = parts.get("form")
        figbass = parts.get("figbass")
        relativeroot = parts.get("relativeroot")
        pedal = parts.get("pedal")

        chord_type = features2type(numeral, form, figbass) if numeral else ""
        inv = figbass_to_inversion(figbass or "")
        inversion = int(inv) if inv is not None else None

        root: int | None = None
        bass: int | None = None
        if numeral:
            root_tpc = roman_numeral2fifths(numeral)
            root = fifths2pc(root_tpc)
            try:
                from ms3 import chord2tpcs

                chord_str = parts.get("chord", label)
                tpcs = chord2tpcs(chord_str)
                if tpcs:
                    bass = fifths2pc(tpcs[0])
            except Exception:
                bass = root

        return cls(
            label=label,
            globalkey=globalkey,
            localkey=localkey,
            numeral=numeral,
            chord_type=chord_type,
            inversion=inversion,
            root=root,
            bass=bass,
            tonicized_key=relativeroot,
            pedal=pedal,
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> DcmlHarmony | None:
        """Construct from a DCML storage row dict.

        Maps DCML storage field names to internal model names:
        - ``bass_note`` -> ``bass``
        - ``figbass`` -> ``inversion``
        - ``relativeroot`` -> ``tonicized_key``
        """
        label = row.get("label")
        if label is None:
            return None

        root_raw = row.get("root")
        root = int(root_raw) if root_raw is not None else None
        bass_raw = row.get("bass_note", row.get("bass"))
        bass = int(bass_raw) if bass_raw is not None else None
        figbass_raw = row.get("figbass", "")
        inversion_raw = row.get("inversion")
        if inversion_raw is not None:
            inversion = int(inversion_raw)
        else:
            inv = figbass_to_inversion(str(figbass_raw or ""))
            inversion = int(inv) if inv is not None else None

        globalkey = str(row.get("globalkey") or "")
        localkey = str(row.get("localkey") or "")

        return cls(
            label=str(label),
            globalkey=globalkey,
            localkey=localkey,
            numeral=str(row.get("numeral") or ""),
            chord_type=str(row.get("chord_type") or ""),
            inversion=inversion,
            root=root,
            bass=bass,
            tonicized_key=row.get("relativeroot") or row.get("tonicized_key"),
            pedal=row.get("pedal"),
        )

    def __repr__(self) -> str:
        return (
            f"DcmlHarmony(label={self.label!r}, key={self.globalkey}:{self.localkey})"
        )


class DcmlHarmonyField(SemanticField[DcmlHarmony]):
    """Columnar wrapper for ``DcmlHarmony`` (paired Field)."""


# ═══════════════════════════════════════════════════════════════════════════
# 3. EVENT SCALARS — Note, Measure
# ═══════════════════════════════════════════════════════════════════════════


class Note(BaseModel):
    """A single note or rest event.

    ``Note.pitch`` is annotated ``EnharmonicPitch | SpecificPitch | None``
    for materialised scalars — both are legitimate pitch representations
    on a note.  This union MUST NOT translate to Arrow ``dense_union``;
    instead, the field is dropped from the pa.Schema and
    ``NoteEventData`` stores pitch in separate fields
    (``midi_pitch``, ``specific_pitch``).  See Contributing → §2.4
    Architectural decision log (union-of-BaseModels rejected; columnar
    separation).
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    start: Coordinate
    end: Coordinate | None = None
    duration: Duration | None = None
    pitch: EnharmonicPitch | SpecificPitch | None = None
    voice: int | None = None
    staff: int | None = None
    velocity: int | None = None
    instrument: str | None = None

    @field_validator("duration", mode="before")
    @classmethod
    def _coerce_duration_from_coordinate(cls, v: object) -> Duration | None:
        if v is None or isinstance(v, Duration):
            return v
        if isinstance(v, Coordinate):
            return Duration(v.value, v.unit)
        return v

    @property
    def is_rest(self) -> bool:
        return self.pitch is None

    @property
    def semantic_type(self) -> str:
        return "Note"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "NoteField",
            "has_pitch": str(self.pitch is not None).lower(),
        }

    def to_dict(self) -> dict[str, object]:
        """Return a dict mirroring the storage struct.

        Pitch is intentionally absent — it is stored in a separate field
        on ``NoteEventData`` (columnar separation).
        """
        d: dict[str, object] = {
            "start": self.start.to_dict() if hasattr(self.start, "to_dict") else None,
            "end": (
                self.end.to_dict()
                if (self.end is not None and hasattr(self.end, "to_dict"))
                else None
            ),
            "voice": self.voice,
            "staff": self.staff,
            "velocity": self.velocity,
            "instrument": self.instrument,
        }
        if self.duration is None:
            d["duration"] = None
        elif hasattr(self.duration, "to_dict"):
            d["duration"] = self.duration.to_dict()
        return d

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Note | None:
        """Construct from a ``NoteEventData`` row dict (trust-boundary regime)."""
        from .enums import TimeUnit

        start_raw = row.get("start")
        if start_raw is None:
            return None

        def _coerce_coord(raw: Any) -> Coordinate | None:
            if raw is None:
                return None
            if isinstance(raw, Coordinate):
                return raw
            if isinstance(raw, dict):
                v = raw.get("value")
                if v is None:
                    return None
                unit = raw.get("unit", TimeUnit.quarters)
                return Coordinate(v, unit)
            return None

        def _coerce_duration(raw: Any) -> Duration | None:
            if raw is None:
                return None
            if isinstance(raw, Duration):
                return raw
            if isinstance(raw, Coordinate):
                return Duration(raw.value, raw.unit)
            if isinstance(raw, dict):
                v = raw.get("value")
                if v is None:
                    return None
                unit = raw.get("unit", TimeUnit.quarters)
                return Duration(v, unit)
            return None

        start = _coerce_coord(start_raw)
        if start is None:
            return None
        end = _coerce_coord(row.get("end"))
        duration = _coerce_duration(row.get("duration"))

        pitch: EnharmonicPitch | SpecificPitch | None = None
        sp_raw = row.get("specific_pitch")
        if isinstance(sp_raw, dict):
            pitch = SpecificPitch.from_row(sp_raw)
        if pitch is None:
            mp_raw = row.get("midi_pitch")
            if isinstance(mp_raw, dict):
                pitch = EnharmonicPitch.from_row(mp_raw)
            elif isinstance(mp_raw, (int, float)) and mp_raw is not None:
                pitch = EnharmonicPitch(midi_number=int(mp_raw))

        return cls(
            start=start,
            end=end,
            duration=duration,
            pitch=pitch,
            voice=row.get("voice"),
            staff=row.get("staff"),
            velocity=row.get("velocity"),
            instrument=row.get("instrument"),
        )

    def __repr__(self) -> str:
        pitch_str = repr(self.pitch) if self.pitch is not None else "rest"
        return f"Note(start={self.start}, duration={self.duration}, pitch={pitch_str})"


def _drop_field(_model_cls: type[BaseModel], _name: str, _info: object) -> list[Any]:
    """Drop a polymorphic / out-of-band field from the derived pa.Schema."""
    return []


# Columnar-separation rule: drop ``Note.pitch`` from pa.Schema so that
# ``midi_pitch`` and ``specific_pitch`` live in their own fields
# (see Contributing → §2.4 Architectural decision log).
register_value_projector(Note, "pitch", _drop_field)


class NoteField(SemanticField[Note]):
    """Field wrapper for ``Note`` (paired Field)."""


# ---------------------------------------------------------------------------
# Measure + MeasureField
# ---------------------------------------------------------------------------


class Measure(BaseModel):
    """A single measure boundary event."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    id: int  # noqa: A003 — MeasureMap field name
    mn: str
    start: Coordinate
    end: Coordinate | None = None
    duration: Duration | None = None
    time_signature: tuple[int, int] = (4, 4)
    key_signature: str | None = None
    nominal_length: float | None = None
    actual_length: float | None = None
    start_repeat: bool = False
    end_repeat: bool = False
    next_ids: tuple[str, ...] | None = None
    volta: int | None = None

    @field_validator("duration", mode="before")
    @classmethod
    def _coerce_duration_from_coordinate(cls, v: object) -> Duration | None:
        if v is None or isinstance(v, Duration):
            return v
        if isinstance(v, Coordinate):
            return Duration(v.value, v.unit)
        return v

    @field_validator("next_ids", mode="before")
    @classmethod
    def _coerce_next_ids(cls, v: object) -> tuple[str, ...] | None:
        if v is None:
            return None
        if isinstance(v, str):
            return (v,)
        if isinstance(v, (list, tuple)):
            out: list[str] = []
            for item in v:
                if isinstance(item, ScopedId):
                    out.append(str(item))
                elif isinstance(item, str):
                    out.append(item)
                else:
                    raise TypeError(
                        f"next_ids item must be ScopedId or string, got "
                        f"{type(item).__name__}"
                    )
            return tuple(out)
        raise TypeError(
            f"next_ids must be a tuple of ScopedId/string, got {type(v).__name__}"
        )

    @property
    def semantic_type(self) -> str:
        return "Measure"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "MeasureField",
            "time_signature": f"{self.time_signature[0]}/{self.time_signature[1]}",
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "mn": self.mn,
            "start": self.start.to_dict() if hasattr(self.start, "to_dict") else None,
            "end": (
                self.end.to_dict()
                if (self.end is not None and hasattr(self.end, "to_dict"))
                else None
            ),
            "duration": (
                self.duration.to_dict()
                if (self.duration is not None and hasattr(self.duration, "to_dict"))
                else None
            ),
            "time_signature": list(self.time_signature),
            "key_signature": self.key_signature,
            "nominal_length": self.nominal_length,
            "actual_length": self.actual_length,
            "start_repeat": self.start_repeat,
            "end_repeat": self.end_repeat,
            "next_ids": list(self.next_ids) if self.next_ids is not None else None,
            "volta": self.volta,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Measure | None:
        from .enums import TimeUnit

        id_raw = row.get("id")
        if id_raw is None:
            return None

        def _coerce_coord(raw: Any) -> Coordinate | None:
            if raw is None:
                return None
            if isinstance(raw, Coordinate):
                return raw
            if isinstance(raw, dict):
                v = raw.get("value")
                if v is None:
                    return None
                unit = raw.get("unit", TimeUnit.quarters)
                return Coordinate(v, unit)
            return None

        def _coerce_duration(raw: Any) -> Duration | None:
            if raw is None:
                return None
            if isinstance(raw, Duration):
                return raw
            if isinstance(raw, Coordinate):
                return Duration(raw.value, raw.unit)
            if isinstance(raw, dict):
                v = raw.get("value")
                if v is None:
                    return None
                unit = raw.get("unit", TimeUnit.quarters)
                return Duration(v, unit)
            return None

        start = _coerce_coord(row.get("start"))
        if start is None:
            return None
        ts_raw = row.get("time_signature", (4, 4))
        if isinstance(ts_raw, dict):
            ts = (int(ts_raw.get("_0", 4)), int(ts_raw.get("_1", 4)))
        elif isinstance(ts_raw, (list, tuple)) and len(ts_raw) == 2:
            ts = (int(ts_raw[0]), int(ts_raw[1]))
        else:
            ts = (4, 4)
        return cls(
            id=int(id_raw),
            mn=str(row.get("mn") or ""),
            start=start,
            end=_coerce_coord(row.get("end")),
            duration=_coerce_duration(row.get("duration")),
            time_signature=ts,
            key_signature=row.get("key_signature"),
            nominal_length=row.get("nominal_length"),
            actual_length=row.get("actual_length"),
            start_repeat=bool(row.get("start_repeat", False)),
            end_repeat=bool(row.get("end_repeat", False)),
            next_ids=row.get("next_ids"),
            volta=row.get("volta"),
        )

    def __repr__(self) -> str:
        ts = f"{self.time_signature[0]}/{self.time_signature[1]}"
        return f"Measure(id={self.id}, mn={self.mn!r}, timesig={ts})"


class MeasureField(SemanticField[Measure]):
    """Columnar wrapper for ``Measure`` (paired Field)."""
