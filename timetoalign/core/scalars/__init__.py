"""Scalar types for score/symbolic data in Time To Align!

This package provides frozen dataclass scalars that satisfy the
corresponding protocols defined in ``core.protocols``.  Each scalar
carries ``semantic_type`` and ``metadata_dict()`` for Parquet storage
contract compliance.
"""

from __future__ import annotations

from .harmony import Harmony
from .measure import Measure
from .note import Note
from .pitch import MidiPitch, SpelledPitch

__all__ = [
    "Harmony",
    "Measure",
    "MidiPitch",
    "Note",
    "SpelledPitch",
]
