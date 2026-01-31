"""Tabular loaders for TimeToAlign!

This subpackage provides loaders for tabular data formats (CSV, TSV, Parquet)
with configurable column mapping.

Classes:
    TabularLoader: Abstract base class with column mapping configuration.
    CsvLoader: CSV file loader.
    TsvLoader: TSV (tab-separated) file loader.
    ParquetLoader: Parquet file loader.
"""

from __future__ import annotations

from .base import TabularLoader
from .csv import CsvLoader, TsvLoader

__all__ = [
    "TabularLoader",
    "CsvLoader",
    "TsvLoader",
]
