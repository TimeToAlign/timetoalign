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
from .coordinate import CoordinateField

__all__ = [
    "CoordinateField",
    "DataField",
    "MapField",
    "NumericField",
    "SemanticField",
    "StringField",
    "StructField",
]
