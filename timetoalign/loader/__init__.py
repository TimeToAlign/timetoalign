"""Loader package for TimeToAlign!

This package provides the infrastructure for loading music representations
and storing events in efficient PyArrow tables.

Loader Taxonomy:
    The package contains three types of loaders:

    **Type 1 - Manifest/Metadata Loaders** (dimensions + metadata only):
        - AudioLoader: Audio file -> DiscretePhysicalTimeline (samples)
        - IIIFManifestLoader: IIIF manifest -> Graphical dimensions

    **Type 2 - Event Loaders** (events only, dimensions derived):
        - ScoreLoader subclasses: Music21Loader, PartituraLoader, TSVLoader
        - MidiLoader subclasses: ScoreMidiLoader, PerformanceMidiLoader

    **Type 3 - Hybrid Loaders** (both fixed dimensions + events):
        - GraphicalLoader: Image sources + segments
        - ATONLoader: Piano roll image dimensions + hole punch events

Classes:
    EventData: PyArrow-based bulk event storage.
    EventStore: Abstract base class for collections of EventData.
    SingleStore: Store wrapper for a single EventData.
    Loader: Abstract base class for event-based file loaders.
    AudioLoader: Manifest loader for audio files.
    AudioInfo: Metadata container for audio files.

NOTE: Class naming was updated in the 2026-01 API refactoring:
- EventStore -> EventData (PyArrow table storage)
- EventBundle -> EventStore (container for EventData)
- SingleStoreBundle -> SingleStore

The package also exports schema utilities for working with coordinate
structures and table metadata.
"""

from __future__ import annotations

from .base import Loader
from .bundle import EventStore, SingleStore
from .physical import AudioInfo, AudioLoader
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
from .store import EventData

__all__ = [
    # Main classes
    "EventData",
    "EventStore",
    "SingleStore",
    "Loader",
    # Physical domain loaders (Type 1 - Manifest)
    "AudioLoader",
    "AudioInfo",
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
