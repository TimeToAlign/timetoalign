"""Scalar types for score/symbolic data in Time To Align!

This package provides frozen dataclass scalars that satisfy the
corresponding protocols defined in ``core.protocols``.  Each scalar
carries ``semantic_type`` and ``metadata_dict()`` for Parquet storage
contract compliance.

Type Hierarchy:

Pitch scalars (satisfy PitchLike hierarchy):
    - ``EnharmonicPitchClass`` -- chromatic pitch class 0-11 (GenericPitchLike)
    - ``GenericPitchClass`` -- diatonic step 0-6
    - ``GenericPitch`` -- diatonic step + octave
    - ``SpecificPitchClass`` -- pitch class with spelling (SpecificPitchClassLike)
    - ``EnharmonicPitch`` -- pitch in semitone space with note-name display;
      used by ``PitchField`` for ``pitch_type="ep"`` (EnharmonicPitchLike)
    - ``MidiPitch`` -- display alias of ``EnharmonicPitch`` (same data,
      raw-MIDI-number ``__repr__``); reserved as the default scalar for
      the planned ``MidiField`` (EnharmonicPitchLike)
    - ``SpecificPitch`` / ``SpecificPitch`` -- full spelling (SpecificPitchLike).
      ``SpecificPitch`` is a protocol-name re-export of the same class.

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
    "SpecificPitch",
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
