"""Tabular loaders for TimeToAlign!

This subpackage provides loaders for tabular data formats (CSV, TSV,
``.solo``, ms3 TSV, …) driven by the universal ``column_specs`` /
``field_specs`` pipeline.

Classes:
    TabularLoader: Base class hosting ``column_specs`` (Step 1) +
        ``field_specs`` (Step 2).
    CsvLoader: CSV file loader.
    TsvLoader: TSV (tab-separated) file loader.
    LabLoader: Audacity / Praat ``.lab`` file loader.
    Ms3Loader: ms3 (MuseScore3) TSV file loader.
    SoloLoader: ``.solo`` performance-analysis file loader.

Modules:
    field_specs: Universal ``FieldSpec`` hierarchy
        (:class:`IntFieldSpec`, :class:`FloatFieldSpec`,
        :class:`StringFieldSpec`, :class:`RationalFieldSpec`,
        :class:`CompositeFieldSpec`, :class:`FractionFieldSpec`) plus
        :func:`resolve_field_spec`.
"""

from __future__ import annotations

from .base import TabularLoader
from .csv import CsvLoader, LabLoader, Ms3Loader, TsvLoader
from .field_specs import (
    CallableFieldSpec,
    CompositeFieldSpec,
    FieldSpec,
    FloatFieldSpec,
    FractionFieldSpec,
    IntFieldSpec,
    RationalFieldSpec,
    StringFieldSpec,
    resolve_field_spec,
)
from .solo import SoloLoader

__all__ = [
    "TabularLoader",
    "CsvLoader",
    "TsvLoader",
    "LabLoader",
    "Ms3Loader",
    "SoloLoader",
    # FieldSpec hierarchy
    "FieldSpec",
    "IntFieldSpec",
    "FloatFieldSpec",
    "StringFieldSpec",
    "RationalFieldSpec",
    "CompositeFieldSpec",
    "FractionFieldSpec",
    "CallableFieldSpec",
    "resolve_field_spec",
]
