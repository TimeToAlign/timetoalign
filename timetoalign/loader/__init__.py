"""Loader package for TimeToAlign!

This package provides the infrastructure for loading music representations
and storing events in efficient PyArrow tables.

Classes:
    EventStore: PyArrow-based bulk event storage.
    Loader: Abstract base class for file loaders.

The package also exports schema utilities for working with coordinate
structures and table metadata.
"""

from __future__ import annotations

from .base import Loader
from .schema import (
    TEMPORAL_TYPE_INSTANT,
    TEMPORAL_TYPE_INTERVAL,
    coordinate_to_struct,
    extend_schema,
    get_base_column_names,
    get_unit_from_schema,
    make_base_schema,
    make_coordinate_field,
    make_coordinate_type,
    make_table_metadata,
    parse_table_metadata,
    struct_to_coordinate,
)
from .store import EventStore

__all__ = [
    # Main classes
    "EventStore",
    "Loader",
    # Schema utilities
    "make_coordinate_type",
    "make_coordinate_field",
    "coordinate_to_struct",
    "struct_to_coordinate",
    "make_base_schema",
    "get_base_column_names",
    "extend_schema",
    "get_unit_from_schema",
    "make_table_metadata",
    "parse_table_metadata",
    # Constants
    "TEMPORAL_TYPE_INSTANT",
    "TEMPORAL_TYPE_INTERVAL",
]
