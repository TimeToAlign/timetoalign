"""TimeToAlign! — A library for representing and aligning musical timelines.

This library provides tools for:

- Representing musical timelines across physical, logical, and graphical domains
- Converting between different coordinate systems using ConversionMaps
- Aligning events across timelines using Match objects
- Loading and saving alignment data in Parquet and JSON formats

Basic usage::

    >>> import timetoalign as tta
    >>> from timetoalign.core import Coordinate, TimeUnit, Domain
    >>>
    >>> # Create a coordinate
    >>> c = Coordinate(120, TimeUnit.ticks)
    >>> print(c)
    120 ticks

Installation & Optional Dependencies
=====================================

The core install (``pip install -e .``) is deliberately lightweight:
only PyArrow, pandas, NetworkX, and typing_extensions are required.  This
gives you the full timeline/map/alignment framework but **no file-format-
specific loaders**.  Loader backends and other features are available through
optional extras.

Atomic extras — one concern each
--------------------------------

Install with ``pip install -e ".[<extra>]"`` from the repository root.

+---------------+--------------------------------------+----------------------------------------------+
| Extra         | Packages                             | Purpose                                      |
+===============+======================================+==============================================+
| ``midi``      | ``mido``                             | MIDI file loading (PerformanceMidiLoader)    |
+---------------+--------------------------------------+----------------------------------------------+
| ``partitura`` | ``partitura``                        | Score parsing via partitura                  |
|               |                                      | (PartituraLoader, ScoreMidiLoader)           |
+---------------+--------------------------------------+----------------------------------------------+
| ``music21``   | ``music21``                          | Score parsing via music21 (Music21Loader)    |
+---------------+--------------------------------------+----------------------------------------------+
| ``ms3``       | ``ms3``                              | DCML TSV score parsing (TSVLoader)           |
+---------------+--------------------------------------+----------------------------------------------+
| ``audio``     | ``soundfile``, ``mutagen``           | Audio file loading + MP3/M4A metadata        |
+---------------+--------------------------------------+----------------------------------------------+
| ``graphical`` | ``pymupdf``, ``pillow``              | PDF/image loading & drawing                  |
+---------------+--------------------------------------+----------------------------------------------+
| ``plot``      | ``matplotlib``                       | Visualisation                                |
+---------------+--------------------------------------+----------------------------------------------+
| ``delta``     | ``deltalake``                        | Delta Lake columnar storage (future)         |
+---------------+--------------------------------------+----------------------------------------------+
| ``rdf``       | ``rdflib``                           | RDF / linked-data export (future)            |
+---------------+--------------------------------------+----------------------------------------------+

Composite extras — convenience bundles
--------------------------------------

+---------------+-----------------------------------------+----------------------------------------------+
| Extra         | Includes                                | Purpose                                      |
+===============+=========================================+==============================================+
| ``scores``    | ``partitura``, ``music21``, ``ms3``     | All score-loader backends                    |
+---------------+-----------------------------------------+----------------------------------------------+
| ``loaders``   | ``midi``, ``scores``, ``audio``,        | Every loader dependency                      |
|               | ``graphical``                           |                                              |
+---------------+-----------------------------------------+----------------------------------------------+
| ``tutorial``  | ``loaders``, ``plot``, plus             | Everything needed for the tutorial notebooks |
|               | ``jupytext``, ``jupyter``               |                                              |
+---------------+-----------------------------------------+----------------------------------------------+
| ``all``       | ``tutorial``, ``delta``, ``rdf``        | All runtime features                         |
+---------------+-----------------------------------------+----------------------------------------------+
| ``dev``       | ``all``, plus ``pre-commit``,           | All features + development / CI tooling      |
|               | ``pytest``, ``pytest-cov``,             |                                              |
|               | ``pytest-benchmark``, ``hypothesis``,   |                                              |
|               | ``ruff``                                |                                              |
+---------------+-----------------------------------------+----------------------------------------------+

The inclusion chain is::

    dev  ⊃  all  ⊃  tutorial  ⊃  loaders  ⊃  { midi, scores, audio, graphical }
                                            +  plot, jupytext, jupyter
                               +  delta, rdf

Examples (from the repository root)::

    pip install -e .                         # Core only
    pip install -e ".[midi]"                 # Core + MIDI loading
    pip install -e ".[scores]"               # Core + all score-loader backends
    pip install -e ".[loaders]"              # Core + every loader
    pip install -e ".[tutorial]"             # Loaders + plotting + Jupyter
    pip install -e ".[all]"                  # All runtime features
    pip install -e ".[dev]"                  # Everything + dev tooling

For more information, see the documentation site.
"""

from __future__ import annotations

import sys
from importlib import import_module
from types import ModuleType

from timetoalign.core import (
    ColumnNaming,
    ColumnRole,
    Coordinate,
    CoordinateSpec,
    CoordinateValue,
    Domain,
    EventType,
    IdCoordinate,
    IdGenerator,
    NumberType,
    OptionalCoordinate,
    ResolvedCoordinate,
    ScopedId,
    TimeIntervalStamp,
    TimelineIdGenerator,
    TimeStamp,
    TimeUnit,
    resolve_coordinate_spec,
)
from timetoalign.maps import (
    ChainMap,
    ConstantMap,
    ConversionMap,
    InterpolationMap,
    IntervalToConstantMap,
    LinearMap,
    PiecewiseMap,
    QuartersToFloatingMeasures,
    QuartersToMeasureNumber,
    ScalarMap,
    SecondsToSamples,
    ShiftMap,
    TableMap,
)
from timetoalign.storage import DictStore, EventData, EventStore, SingleStore

_DEFERRED_EXPORTS = {
    # Loader layer
    "AudioInfo": ("timetoalign.loader", "AudioInfo"),
    "AudioLoader": ("timetoalign.loader", "AudioLoader"),
    "EepNotesLoader": ("timetoalign.loader", "EepNotesLoader"),
    "Loader": ("timetoalign.loader", "Loader"),
    "MatchfileLoader": ("timetoalign.loader", "MatchfileLoader"),
    "RepoVizzInfo": ("timetoalign.loader", "RepoVizzInfo"),
    "RepoVizzLoader": ("timetoalign.loader", "RepoVizzLoader"),
    "TiliaDictStore": ("timetoalign.loader", "TiliaDictStore"),
    "TiliaJsonLoader": ("timetoalign.loader", "TiliaJsonLoader"),
    # Timeline layer
    "BeatGrid": ("timetoalign.timelines", "BeatGrid"),
    "ContinuousGraphicalTimeline": (
        "timetoalign.timelines",
        "ContinuousGraphicalTimeline",
    ),
    "ContinuousLogicalTimeline": ("timetoalign.timelines", "ContinuousLogicalTimeline"),
    "ContinuousPhysicalTimeline": (
        "timetoalign.timelines",
        "ContinuousPhysicalTimeline",
    ),
    "DiscreteGraphicalTimeline": ("timetoalign.timelines", "DiscreteGraphicalTimeline"),
    "DiscreteLogicalTimeline": ("timetoalign.timelines", "DiscreteLogicalTimeline"),
    "DiscretePhysicalTimeline": ("timetoalign.timelines", "DiscretePhysicalTimeline"),
    "GraphicalTimeline": ("timetoalign.timelines", "GraphicalTimeline"),
    "GroupTimestamp": ("timetoalign.timelines", "GroupTimestamp"),
    "LogicalTimeline": ("timetoalign.timelines", "LogicalTimeline"),
    "PhysicalTimeline": ("timetoalign.timelines", "PhysicalTimeline"),
    "SegmentNameGenerator": ("timetoalign.timelines", "SegmentNameGenerator"),
    "Timeline": ("timetoalign.timelines", "Timeline"),
    "TimelineGroup": ("timetoalign.timelines", "TimelineGroup"),
    # Alignment layer
    "Agent": ("timetoalign.alignment", "Agent"),
    "AlignmentAnchor": ("timetoalign.alignment", "AlignmentAnchor"),
    "AlignmentBundle": ("timetoalign.alignment", "AlignmentBundle"),
    "ClaimFilter": ("timetoalign.alignment", "ClaimFilter"),
    "MatchClaim": ("timetoalign.alignment", "MatchClaim"),
    "MatchClaimField": ("timetoalign.alignment", "MatchClaimField"),
    "MatchFileContext": ("timetoalign.alignment", "MatchFileContext"),
    "MatchGraph": ("timetoalign.alignment", "MatchGraph"),
    "MatchLine": ("timetoalign.alignment", "MatchLine"),
    "MatchMetadata": ("timetoalign.alignment", "MatchMetadata"),
    "MatchStamp": ("timetoalign.alignment", "MatchStamp"),
    "NoteRecord": ("timetoalign.alignment", "NoteRecord"),
    "SnoteRecord": ("timetoalign.alignment", "SnoteRecord"),
    "WarpMap": ("timetoalign.alignment", "WarpMap"),
}


class _FacadeModule(ModuleType):
    """Module facade that loads upper layers only when their exports are requested."""

    def __getattribute__(self, name: str) -> object:
        deferred_exports = ModuleType.__getattribute__(self, "_DEFERRED_EXPORTS")
        target = deferred_exports.get(name)
        if target is not None:
            module_name, attribute_name = target
            value = getattr(import_module(module_name), attribute_name)
            ModuleType.__setattr__(self, name, value)
            deferred_exports.pop(name, None)
            return value
        return ModuleType.__getattribute__(self, name)

    def __dir__(self) -> list[str]:
        names = set(ModuleType.__dir__(self))
        names.update(ModuleType.__getattribute__(self, "_DEFERRED_EXPORTS"))
        return sorted(names)


sys.modules[__name__].__class__ = _FacadeModule

# User-friendly alias for Coordinate
Coord = Coordinate

__version__ = "0.2.0"

__all__ = [
    # Version
    "__version__",
    # Enums
    "ColumnNaming",
    "ColumnRole",
    "Domain",
    "TimeUnit",
    "NumberType",
    "EventType",
    # Types
    "Coordinate",
    "Coord",  # Alias for Coordinate
    "IdCoordinate",
    "CoordinateValue",
    "CoordinateSpec",
    "OptionalCoordinate",
    "ResolvedCoordinate",
    "resolve_coordinate_spec",
    # Timestamps (first-class citizens)
    "TimeStamp",
    "TimeIntervalStamp",
    # IDs
    "ScopedId",
    "IdGenerator",
    "TimelineIdGenerator",
    # Loader - Event-based (Type 2)
    "EventData",
    "EventStore",
    "SingleStore",
    "DictStore",
    "Loader",
    # Loader - Manifest-based (Type 1)
    "AudioLoader",
    "AudioInfo",
    "RepoVizzLoader",
    "RepoVizzInfo",
    # Loader - Physical event-based
    "EepNotesLoader",
    # Loader - Alignment
    "MatchfileLoader",
    "TiliaJsonLoader",
    "TiliaDictStore",
    # Timelines
    "Timeline",
    "LogicalTimeline",
    "PhysicalTimeline",
    "GraphicalTimeline",
    "ContinuousLogicalTimeline",
    "DiscreteLogicalTimeline",
    "ContinuousPhysicalTimeline",
    "DiscretePhysicalTimeline",
    "ContinuousGraphicalTimeline",
    "DiscreteGraphicalTimeline",
    "BeatGrid",
    "SegmentNameGenerator",
    # Maps
    "ConstantMap",
    "ConversionMap",
    "IntervalToConstantMap",
    "InterpolationMap",
    "LinearMap",
    "PiecewiseMap",
    "QuartersToFloatingMeasures",
    "QuartersToMeasureNumber",
    "ScalarMap",
    "SecondsToSamples",
    "ShiftMap",
    "TableMap",
    "ChainMap",
    # Alignment
    "Agent",
    "AlignmentBundle",
    "GroupTimestamp",
    "TimelineGroup",
    "AlignmentAnchor",
    "ClaimFilter",
    "MatchClaim",
    "MatchClaimField",
    "MatchFileContext",
    "MatchGraph",
    "MatchLine",
    "MatchMetadata",
    "MatchStamp",
    "NoteRecord",
    "SnoteRecord",
    "WarpMap",
]
