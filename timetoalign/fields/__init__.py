"""Field abstractions for columnar semantic types in Time To Align!

This package provides the DataField hierarchy -- typed wrappers around
PyArrow arrays that carry schema metadata and support semantic operations.
"""

from __future__ import annotations

from .base import (
    DataField,
    MapField,
    NumericField,
    SemanticField,
    StringField,
    StructField,
)
from .coordinate import CoordinateField, DurationField, NumberField
from .harmony import (
    DcmlLabelField,
    HarmonyField,
    RomanNumeralHarmonyField,
    WesternTertianHarmonyField,
)
from .pitch import (
    EnharmonicPitchField,
    GenericPitchField,
    MidiPitchField,
    PitchField,
    SpecificPitchField,
    SpelledPitchClassField,
    SpelledPitchField,
)
from .schemas import PitchSpaceSchema

# Alias for consistency with naming convention
DcmlHarmonyField = DcmlLabelField

__all__ = [
    "CoordinateField",
    "DataField",
    "DcmlHarmonyField",
    "DcmlLabelField",
    "DurationField",
    "EnharmonicPitchField",
    "GenericPitchField",
    "HarmonyField",
    "MapField",
    "MidiPitchField",
    "NumberField",
    "NumericField",
    "PitchField",
    "PitchSpaceSchema",
    "RomanNumeralHarmonyField",
    "SemanticField",
    "SpecificPitchField",
    "SpelledPitchClassField",
    "SpelledPitchField",
    "StringField",
    "StructField",
    "WesternTertianHarmonyField",
]
