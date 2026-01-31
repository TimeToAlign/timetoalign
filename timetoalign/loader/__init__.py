"""Loader package for TimeToAlign!

This package provides the infrastructure for loading music representations
and storing events in efficient PyArrow tables.

Loader Taxonomy:
    The package contains three categories of loaders:

    **EventLoader (Loader)** - Returns EventStore (events only):
        - ScoreLoader subclasses: Music21Loader, PartituraLoader, Ms3Loader
        - MidiLoader subclasses: ScoreMidiLoader, PerformanceMidiLoader
        - TabularLoader subclasses: CsvLoader, TsvLoader

    **ManifestLoader** - Returns ManifestData (dimensions + metadata only):
        - AudioLoader: Audio file -> DiscretePhysicalTimeline (samples)
        - IIIFManifestLoader: IIIF manifest -> Graphical dimensions

    **AlignmentLoader** - Returns AlignmentStore (events + C-maps + matches):
        - Ieee1599Loader: IEEE 1599 multimodal alignment
        - TiliaLoader: TiLiA hierarchical annotations
        - MatchfileLoader: Score-to-performance alignment

Classes:
    EventData: PyArrow-based bulk event storage.
    EventStore: Abstract base class for collections of EventData.
    SingleStore: Store wrapper for a single EventData.
    AlignmentStore: Container for aligned multimodal data.
    MatchData: Container for alignment matches.
    ManifestData: Container for manifest/metadata.
    Loader/EventLoader: Abstract base class for event-based loaders.
    ManifestLoader: Abstract base class for manifest loaders.
    AlignmentLoader: Abstract base class for alignment loaders.
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

from .base import AlignmentLoader, EventLoader, Loader, ManifestData, ManifestLoader
from .bundle import AlignmentStore, EventStore, MatchData, SingleStore
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
    "AlignmentStore",
    "MatchData",
    "ManifestData",
    # Loader ABCs
    "Loader",
    "EventLoader",
    "ManifestLoader",
    "AlignmentLoader",
    # Physical domain loaders (Manifest)
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
