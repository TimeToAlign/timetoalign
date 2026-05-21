"""Scalar types for score/symbolic data in Time To Align!

This package provides pydantic v2 ``BaseModel`` scalars (all frozen) that
satisfy the corresponding protocols defined in ``core.protocols``.  Each
scalar carries ``semantic_type`` and ``metadata_dict()`` for Parquet
storage contract compliance.

Type Hierarchy:

Pitch scalars (satisfy PitchLike hierarchy):
    - ``EnharmonicPitchClass`` -- chromatic pitch class 0-11 (GenericPitchLike)
    - ``GenericPitchClass`` -- diatonic step 0-6
    - ``GenericPitch`` -- diatonic step + octave
    - ``SpecificPitchClass`` -- pitch class with spelling (SpecificPitchClassLike)
    - ``EnharmonicPitch`` -- pitch in semitone space with note-name display
    - ``MidiPitch`` -- display subclass of ``EnharmonicPitch`` (raw-MIDI repr)
    - ``SpecificPitch`` -- full spelling (SpecificPitchLike)

Harmony scalars (satisfy HarmonyLabelLike hierarchy):
    - ``HarmonyLabel`` -- label + standard (HarmonyLabelLike)
    - ``PitchBasedHarmony`` -- + root/bass (PitchBasedHarmonyLike)
    - ``WesternTertianHarmony`` -- + chord_type/inversion
    - ``RomanNumeralHarmony`` -- + numeral/localkey/globalkey
    - ``DcmlHarmony`` -- DCML codec specifics (DcmlHarmonyLike)

Event scalars (satisfy IntervalEventLike):
    - ``Note`` -- note/rest event (NoteLike)
    - ``Measure`` -- measure boundary event (MeasureLike)

Duration:
    - ``Duration`` -- non-negative elapsed extent (WP2 new scalar; same
      physical storage as Coordinate)
"""

from __future__ import annotations

from .duration import Duration
from .harmony import (
    DcmlHarmony,
    HarmonyLabel,
    PitchBasedHarmony,
    RomanNumeralHarmony,
    WesternTertianHarmony,
)
from .measure import Measure
from .note import Note
from .pitch import (
    EnharmonicPitch,
    EnharmonicPitchClass,
    GenericPitch,
    GenericPitchClass,
    MidiPitch,
    SpecificPitch,
    SpecificPitchClass,
)

__all__ = [
    # Pitch hierarchy
    "EnharmonicPitchClass",
    "GenericPitch",
    "GenericPitchClass",
    "SpecificPitchClass",
    "MidiPitch",
    "SpecificPitch",
    "EnharmonicPitch",
    # Harmony hierarchy
    "HarmonyLabel",
    "PitchBasedHarmony",
    "WesternTertianHarmony",
    "RomanNumeralHarmony",
    "DcmlHarmony",
    # Event scalars
    "Note",
    "Measure",
    # Duration
    "Duration",
]
