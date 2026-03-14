"""Scalar types for score/symbolic data in Time To Align!

This package provides frozen dataclass scalars that satisfy the
corresponding protocols defined in ``core.protocols``.  Each scalar
carries ``semantic_type`` and ``metadata_dict()`` for Parquet storage
contract compliance.

Type Hierarchy:

Pitch scalars (satisfy PitchLike hierarchy):
    - ``GenericPitch`` -- pitch class only (GenericPitchLike)
    - ``SpelledPitchClass`` -- pitch class with spelling (SpelledPitchClassLike)
    - ``MidiPitch`` / ``SpecificPitch`` -- MIDI note (SpecificPitchClassLike)
    - ``SpelledPitch`` / ``EnharmonicPitch`` -- full spelling (EnharmonicPitchLike)

Harmony scalars (satisfy HarmonyLabelLike hierarchy):
    - ``HarmonyLabel`` / ``Harmony`` -- label + standard + temporal (HarmonyLabelLike)
    - ``PitchBasedHarmony`` -- + root/bass (PitchBasedHarmonyLike)
    - ``WesternTertianHarmony`` -- + chord_type/inversion (WesternTertianHarmonyLike)
    - ``RomanNumeralHarmony`` -- + numeral/localkey/globalkey (RomanNumeralHarmonyLike)
    - ``DcmlHarmony`` / ``DcmlLabel`` -- DCML codec specifics (DcmlHarmonyLike)

Event scalars (satisfy IntervalEventLike):
    - ``Note`` -- note/rest event (NoteLike)
    - ``Measure`` -- measure boundary event (MeasureLike)
"""

from __future__ import annotations

from .harmony import (
    DcmlHarmony,
    DcmlLabel,
    Harmony,
    HarmonyLabel,
    PitchBasedHarmony,
    RomanNumeralHarmony,
    WesternTertianHarmony,
)
from .measure import Measure
from .note import Note
from .pitch import (
    EnharmonicPitch,
    GenericPitch,
    MidiPitch,
    SpecificPitch,
    SpelledPitch,
    SpelledPitchClass,
)

__all__ = [
    # Pitch hierarchy
    "GenericPitch",
    "SpelledPitchClass",
    "MidiPitch",
    "SpecificPitch",
    "SpelledPitch",
    "EnharmonicPitch",
    # Harmony hierarchy
    "HarmonyLabel",
    "Harmony",
    "PitchBasedHarmony",
    "WesternTertianHarmony",
    "RomanNumeralHarmony",
    "DcmlHarmony",
    "DcmlLabel",
    # Event scalars
    "Note",
    "Measure",
]
