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
    field_parsers: :class:`FieldParser` hierarchy
        (:class:`CompositeFieldParser`, :class:`CallableFieldParser`)
        plus :func:`resolve_field_parser`, the universal-resolution
        dispatcher that turns user-supplied ``column_specs`` entries
        into producers (DataField blueprints or FieldParser instances).
"""

from __future__ import annotations

from .base import TabularLoader
from .csv import CsvLoader, LabLoader, Ms3Loader, TsvLoader
from .field_parsers import (
    CallableFieldParser,
    CompositeFieldParser,
    FieldParser,
    resolve_field_parser,
)
from .solo import SoloLoader

__all__ = [
    "TabularLoader",
    "CsvLoader",
    "TsvLoader",
    "LabLoader",
    "Ms3Loader",
    "SoloLoader",
    # FieldParser hierarchy + dispatcher
    "FieldParser",
    "CompositeFieldParser",
    "CallableFieldParser",
    "resolve_field_parser",
]
