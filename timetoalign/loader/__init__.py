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
from .bundle import AlignmentStore, DictStore, EventStore, MatchData, SingleStore
from .physical import (
    AudioInfo,
    AudioLoader,
    EepNotesLoader,
    RepoVizzInfo,
    RepoVizzLoader,
)
from .schema import (
    TEMPORAL_TYPE_INSTANT,
    TEMPORAL_TYPE_INTERVAL,
    ComputedField,
    ConvertedField,
    CoordinateField,
    Field,
)
from .schema import TableSchema as BasicTableSchema  # Legacy simple schema
from .schema import (
    coordinate_to_struct,
    extend_schema,
    get_base_column_names,
    get_unit_from_schema,
    make_base_schema,
    make_coordinate_field,
    make_coordinate_type,
    make_table_metadata,
    parse_json_to_struct,
    parse_table_metadata,
    struct_to_coordinate,
)
from .store import EventData
from .table_schema import (
    CMapColumn,
    ColumnRole,
    CoordinateSpec,
    ExtraColumn,
    HierarchySpec,
    MatchColumn,
    MatchSpec,
    PartitionMode,
    PartitionSpec,
    RegionSpec,
    TableSchema,
    TimelineDefaults,
)

__all__ = [
    # Main classes
    "EventData",
    "EventStore",
    "SingleStore",
    "DictStore",
    "AlignmentStore",
    "MatchData",
    "ManifestData",
    # Loader ABCs
    "Loader",
    "EventLoader",
    "ManifestLoader",
    "AlignmentLoader",
    # Alignment loaders
    "MatchfileLoader",
    "TiliaDictStore",
    "TiliaJsonLoader",
    # Physical domain loaders
    "AudioLoader",
    "AudioInfo",
    "RepoVizzLoader",
    "RepoVizzInfo",
    "EepNotesLoader",
    # TableSchema - Semantic column specifications (NEW)
    "TableSchema",
    "TimelineDefaults",
    "CoordinateSpec",
    "PartitionSpec",
    "PartitionMode",
    "HierarchySpec",
    "RegionSpec",
    "MatchSpec",
    "CMapColumn",
    "MatchColumn",
    "ExtraColumn",
    "ColumnRole",
    # Legacy basic schema
    "BasicTableSchema",
    "ConvertedField",
    "CoordinateField",
    "Field",
    "ComputedField",
    "parse_json_to_struct",
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


def __getattr__(name: str):
    """Lazy imports to avoid circular dependency at module load time.

    MatchfileLoader imports from timetoalign.timelines, which in turn
    imports from timetoalign.loader.  Deferring the import here breaks
    the cycle.
    """
    if name == "MatchfileLoader":
        from .alignment import MatchfileLoader

        return MatchfileLoader
    if name == "TiliaJsonLoader":
        from .alignment import TiliaJsonLoader

        return TiliaJsonLoader
    if name == "TiliaDictStore":
        from .alignment import TiliaDictStore

        return TiliaDictStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
