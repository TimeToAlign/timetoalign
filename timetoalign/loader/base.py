"""Loader: Base classes for loading music representations into TimeToAlign!

This module provides the loader hierarchy for TimeToAlign!:

- **Loader (ABC)**: Base class for all loaders
- **EventLoader (ABC)**: Returns EventStore (events only)
- **ManifestLoader (ABC)**: Returns ManifestData (dimensions/metadata only)
- **AlignmentLoader (ABC)**: Returns AlignmentStore (events + C-maps + Matches)

Design principles:
- Multi-source: One Loader can aggregate multiple files
- Metadata in table: Deterministic, stored in PyArrow schema metadata
- Polymorphic returns: Different loader categories return different types
- Subclassable: Domain-specific loaders extend these ABCs
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar, Union

import numpy as np
import pyarrow as pa
from typing_extensions import Self

from timetoalign.core import NumberType, TimeUnit

from .store import EventData

# Type alias for _load_source return: supports both vectorized and legacy modes
LoadSourceResult = Union[
    tuple[dict[str, Any], dict[str, np.ndarray | pa.Array]],  # Vectorized: column dict
    tuple[dict[str, Any], list[dict[str, Any]]],  # Legacy: row dicts
]

if TYPE_CHECKING:
    from timetoalign.loader.bundle import AlignmentStore, EventStore

module_logger = logging.getLogger(__name__)

# Type variable for polymorphic loader returns
T = TypeVar("T")


class Loader(ABC):
    """Abstract base class for loading music representations.

    Loader provides a unified interface for loading one or more source files
    and aggregating their events into an EventData. Metadata about the sources
    is stored in the PyArrow table's schema metadata for determinism.

    Subclasses must implement:
    - _load_source(): Parse a single source file into event rows
    - _default_unit: The default time unit for this loader type

    Attributes:
        events: The EventData containing all loaded events.
        sources: List of loaded source file paths.
        unit: The time unit for coordinates.
        number_type: The number type for coordinates.

    Examples:
        >>> # Subclass implementation
        >>> class MidiLoader(Loader):
        ...     _default_unit = TimeUnit.ticks
        ...     _event_data_class = EventData
        ...
        ...     def _load_source(self, path):
        ...         # Parse MIDI file, return (metadata_dict, event_rows)
        ...         return {"format": "midi"}, [{"id": "n1", ...}]
        >>>
        >>> loader = MidiLoader()
        >>> loader.load("piece.mid")
        >>> print(loader.event_summary())
    """

    # Class-level configuration (subclasses override)
    _default_unit: ClassVar[TimeUnit] = TimeUnit.seconds
    _event_data_class: ClassVar[type[EventData]] = EventData

    def __init__(
        self,
        unit: TimeUnit | None = None,
        number_type: NumberType = NumberType.float,
    ) -> None:
        """Initialize the Loader.

        Args:
            unit: The time unit for coordinates. Defaults to class's _default_unit.
            number_type: The number type for coordinates.
        """
        self._unit = unit or self._default_unit
        self._number_type = number_type
        self._sources: list[Path] = []
        self._source_metadata: list[dict[str, Any]] = []
        self._events: EventData = self._event_data_class.empty(
            self._unit, self._number_type
        )

    # region Abstract Methods

    @abstractmethod
    def _load_source(self, source: Path) -> LoadSourceResult:
        """Load a single source file.

        Subclasses implement this to parse their specific format.

        VECTORIZED API (preferred):
            Return (metadata_dict, column_dict) where column_dict contains
            numpy/pyarrow arrays for each column. This enables zero-iteration
            table construction.

        LEGACY API (deprecated):
            Return (metadata_dict, row_dicts) where row_dicts is a list of
            event dictionaries. This requires row iteration and should be
            migrated to the vectorized API.

        Args:
            source: Path to the source file.

        Returns:
            A tuple of (metadata_dict, event_data):
            - metadata_dict: File-specific metadata (format, duration, etc.)
            - event_data: Either:
                - dict[str, np.ndarray | pa.Array]: Column arrays (vectorized)
                - list[dict[str, Any]]: Row dicts (legacy, deprecated)

        Raises:
            FileNotFoundError: If the source file doesn't exist.
            ValueError: If the source file is invalid.
        """
        ...

    # endregion

    # region Properties

    @property
    def events(self) -> EventData:
        """The EventData containing all loaded events."""
        return self._events

    @property
    def sources(self) -> list[Path]:
        """List of loaded source file paths."""
        return list(self._sources)

    @property
    def unit(self) -> TimeUnit:
        """The time unit for coordinates."""
        return self._unit

    @property
    def number_type(self) -> NumberType:
        """The number type for coordinates."""
        return self._number_type

    @property
    def metadata(self) -> dict[str, Any]:
        """Aggregated metadata from all sources.

        Returns:
            Dict with loader info and per-source metadata.
        """
        return {
            "loader_class": self.__class__.__name__,
            "unit": str(self._unit),
            "number_type": str(self._number_type),
            "source_count": len(self._sources),
            "sources": self._source_metadata,
        }

    @property
    def store(self) -> "EventStore":
        """Return an EventStore wrapping the loader's events.

        Subclasses may override to return specialized stores
        (e.g., ScoreStore, MidiStore). Default implementation
        wraps self.events in a SingleStore.

        Returns:
            An EventStore providing uniform access to loaded data.
        """
        from timetoalign.loader.bundle import SingleStore

        return SingleStore(self._events, name="events")

    # endregion

    # region Loading

    def load(self, *sources: Path | str) -> Self:
        """Load one or more source files.

        Events from all sources are aggregated into the EventData.
        Metadata for each source is recorded separately.

        Supports both vectorized (column dict) and legacy (row dicts) modes:
        - Vectorized: _load_source returns dict[str, np.ndarray | pa.Array]
        - Legacy: _load_source returns list[dict[str, Any]]

        Args:
            *sources: Paths to source files.

        Returns:
            Self, for method chaining.

        Raises:
            FileNotFoundError: If any source doesn't exist.
            ValueError: If any source is invalid.
        """
        for source in sources:
            path = Path(source)

            # Get source metadata and event data
            source_meta, event_data = self._load_source(path)

            # Add loading metadata
            source_meta["path"] = str(path)
            source_meta["loaded_at"] = datetime.now(timezone.utc).isoformat()

            # Track source
            self._sources.append(path)
            self._source_metadata.append(source_meta)

            # Add events - detect vectorized vs legacy mode
            if event_data:
                if isinstance(event_data, dict):
                    # VECTORIZED MODE: event_data is column dict
                    # Use from_arrays for zero-iteration construction
                    column_dict: dict[str, Any] = event_data
                    new_data = self._event_data_class.from_arrays(
                        column_dict, self._unit, self._number_type
                    )
                else:
                    # LEGACY MODE: event_data is list of row dicts
                    # Use from_dicts (triggers row iteration - deprecated)
                    module_logger.debug(
                        f"Using legacy row-based loading for {path.name}. "
                        "Consider migrating to vectorized API."
                    )
                    row_dicts: list[dict[str, Any]] = event_data
                    new_data = self._event_data_class.from_dicts(
                        row_dicts, self._unit, self._number_type
                    )
                self._events.extend(new_data)

        return self

    def clear(self) -> None:
        """Clear all loaded sources and events."""
        self._sources.clear()
        self._source_metadata.clear()
        self._events = self._event_data_class.empty(self._unit, self._number_type)

    # endregion

    # region Stats (delegated to EventData)

    def event_summary(self) -> dict[str, Any]:
        """Get a summary of loaded events.

        Returns:
            Dict with event counts, types, coordinate range, etc.
        """
        summary = self._events.summary()
        summary["sources"] = [str(s) for s in self._sources]
        return summary

    def count_events_by_type(self) -> dict[str, int]:
        """Count events grouped by event_type.

        Returns:
            Dict mapping event type names to counts.
        """
        return self._events.count_by("event_type")

    def count_events_by_temporal_type(self) -> dict[str, int]:
        """Count events grouped by temporal_type (instant/interval).

        Returns:
            Dict mapping "instant"/"interval" to counts.
        """
        return self._events.count_by("temporal_type")

    # endregion

    # region Magic Methods

    def __len__(self) -> int:
        """Return the number of events."""
        return len(self._events)

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"{self.__class__.__name__}("
            f"sources={len(self._sources)}, "
            f"events={len(self._events)}, "
            f"unit={self._unit})"
        )

    # endregion

    # region Serialization

    def to_parquet(self, path: Path | str) -> None:
        """Save the loaded events to a Parquet file.

        The metadata (including source info) is preserved in the file.

        Args:
            path: Path to write the Parquet file.
        """
        self._events.to_parquet(path)

    @classmethod
    def from_parquet(cls, path: Path | str) -> Self:
        """Load a Loader from a Parquet file.

        Note: This creates a new Loader with the EventData loaded,
        but source paths may not be accessible for re-loading.

        Args:
            path: Path to the Parquet file.

        Returns:
            A new Loader with events loaded from the file.
        """
        events = cls._event_data_class.from_parquet(path)
        loader = cls.__new__(cls)
        loader._unit = events.unit
        loader._number_type = events.number_type
        loader._events = events
        loader._sources = []
        loader._source_metadata = []
        return loader

    # endregion


# Alias for backwards compatibility and clarity
EventLoader = Loader
"""EventLoader is an alias for Loader - the base class for loaders that return EventStore."""


# region ManifestData


@dataclass
class ManifestData:
    """Container for manifest/metadata from ManifestLoader.

    ManifestData holds structural information about a source without events.
    This includes dimensions, sample rates, page counts, etc.

    Attributes:
        dimensions: Dict of named dimensions (e.g., {"width": 1920, "height": 1080}).
        metadata: Additional metadata about the source.
        source_path: Path to the source file.
        source_type: Type of source (e.g., "audio", "image", "pdf").

    Examples:
        >>> # Audio manifest
        >>> manifest = ManifestData(
        ...     dimensions={"duration_samples": 44100 * 60, "duration_seconds": 60.0},
        ...     metadata={"sample_rate": 44100, "channels": 2},
        ...     source_type="audio",
        ... )

        >>> # PDF manifest
        >>> manifest = ManifestData(
        ...     dimensions={"pages": 10, "width": 612, "height": 792},
        ...     metadata={"title": "Score", "dpi": 72},
        ...     source_type="pdf",
        ... )
    """

    dimensions: dict[str, int | float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    source_path: Path | None = None
    source_type: str = "unknown"

    def __repr__(self) -> str:
        dims_str = ", ".join(f"{k}={v}" for k, v in self.dimensions.items())
        return f"ManifestData({self.source_type}, {dims_str})"


# endregion


# region ManifestLoader


class ManifestLoader(ABC):
    """Abstract base class for loaders that return ManifestData.

    ManifestLoader is for sources that provide dimensional/structural
    information without timeline events:
    - Audio files -> duration, sample rate, channels
    - PDF files -> pages, dimensions
    - Images -> width, height, DPI

    Subclasses must implement:
    - _load_source(): Parse a single source into ManifestData

    The loaded ManifestData can be used to create empty timelines with
    correct dimensions, or to configure subsequent event loading.

    Examples:
        >>> class AudioManifestLoader(ManifestLoader):
        ...     def _load_source(self, source: Path) -> ManifestData:
        ...         # Read audio header
        ...         return ManifestData(
        ...             dimensions={"duration_samples": n_samples},
        ...             metadata={"sample_rate": sr},
        ...             source_type="audio",
        ...         )
    """

    def __init__(self) -> None:
        """Initialize the ManifestLoader."""
        self._sources: list[Path] = []
        self._manifests: list[ManifestData] = []
        self._logger = module_logger.getChild(self.__class__.__name__)

    # region Abstract Methods

    @abstractmethod
    def _load_source(self, source: Path) -> ManifestData:
        """Load a single source file into ManifestData.

        Subclasses implement this to parse their specific format.

        Args:
            source: Path to the source file.

        Returns:
            ManifestData containing dimensions and metadata.

        Raises:
            FileNotFoundError: If the source file doesn't exist.
            ValueError: If the source file is invalid.
        """
        ...

    # endregion

    # region Properties

    @property
    def sources(self) -> list[Path]:
        """List of loaded source file paths."""
        return list(self._sources)

    @property
    def manifests(self) -> list[ManifestData]:
        """List of loaded ManifestData objects."""
        return list(self._manifests)

    @property
    def manifest(self) -> ManifestData | None:
        """The first (or only) manifest, for convenience."""
        return self._manifests[0] if self._manifests else None

    # endregion

    # region Loading

    def load(self, *sources: Path | str) -> Self:
        """Load one or more source files.

        Args:
            *sources: Paths to source files.

        Returns:
            Self, for method chaining.

        Raises:
            FileNotFoundError: If any source doesn't exist.
            ValueError: If any source is invalid.
        """
        for source in sources:
            path = Path(source)
            manifest = self._load_source(path)
            manifest.source_path = path

            self._sources.append(path)
            self._manifests.append(manifest)
            self._logger.debug(f"Loaded manifest from {path}")

        return self

    def clear(self) -> None:
        """Clear all loaded sources and manifests."""
        self._sources.clear()
        self._manifests.clear()

    # endregion

    # region Magic Methods

    def __len__(self) -> int:
        """Return the number of loaded manifests."""
        return len(self._manifests)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"{self.__class__.__name__}(sources={len(self._sources)})"

    # endregion


# endregion


# region AlignmentLoader


class AlignmentLoader(ABC):
    """Abstract base class for loaders that return AlignmentStore.

    AlignmentLoader is for formats that encode aligned multimodal data:
    - IEEE 1599 -> score + audio + graphical alignments
    - TiLiA JSON -> hierarchical annotations with alignments
    - Match files -> score-to-performance alignment

    Subclasses must implement:
    - _load_source(): Parse a single source into AlignmentStore

    AlignmentStore contains:
    - EventData tables for each domain/layer
    - ConversionMaps between coordinate systems
    - Match objects representing alignment claims

    Examples:
        >>> class Ieee1599Loader(AlignmentLoader):
        ...     def _load_source(self, source: Path) -> AlignmentStore:
        ...         # Parse IEEE 1599 XML
        ...         return AlignmentStore(
        ...             events=event_store,
        ...             cmaps=[tick_to_seconds_map],
        ...             matches=match_data,
        ...         )
    """

    def __init__(self) -> None:
        """Initialize the AlignmentLoader."""
        self._sources: list[Path] = []
        self._source_metadata: list[dict[str, Any]] = []
        self._store: AlignmentStore | None = None
        self._logger = module_logger.getChild(self.__class__.__name__)

    # region Abstract Methods

    @abstractmethod
    def _load_source(self, source: Path) -> "AlignmentStore":
        """Load a single source file into AlignmentStore.

        Subclasses implement this to parse their specific format.

        Args:
            source: Path to the source file.

        Returns:
            AlignmentStore containing events, C-maps, and matches.

        Raises:
            FileNotFoundError: If the source file doesn't exist.
            ValueError: If the source file is invalid.
        """
        ...

    # endregion

    # region Properties

    @property
    def sources(self) -> list[Path]:
        """List of loaded source file paths."""
        return list(self._sources)

    @property
    def store(self) -> "AlignmentStore | None":
        """The AlignmentStore containing all loaded data."""
        return self._store

    @property
    def metadata(self) -> dict[str, Any]:
        """Aggregated metadata from all sources."""
        return {
            "loader_class": self.__class__.__name__,
            "source_count": len(self._sources),
            "sources": self._source_metadata,
        }

    # endregion

    # region Loading

    def load(self, *sources: Path | str) -> Self:
        """Load one or more source files.

        For multiple sources, stores are merged (events concatenated,
        C-maps and matches aggregated).

        Args:
            *sources: Paths to source files.

        Returns:
            Self, for method chaining.

        Raises:
            FileNotFoundError: If any source doesn't exist.
            ValueError: If any source is invalid.
        """
        for source in sources:
            path = Path(source)

            # Load store from source
            loaded_store = self._load_source(path)

            # Track metadata
            source_meta = {
                "path": str(path),
                "loaded_at": datetime.now(timezone.utc).isoformat(),
            }
            self._sources.append(path)
            self._source_metadata.append(source_meta)

            # Merge or set store
            if self._store is None:
                self._store = loaded_store
            else:
                self._store.extend(loaded_store)

            self._logger.debug(f"Loaded alignment from {path}")

        return self

    def clear(self) -> None:
        """Clear all loaded sources and store."""
        self._sources.clear()
        self._source_metadata.clear()
        self._store = None

    # endregion

    # region Magic Methods

    def __len__(self) -> int:
        """Return total event count across all stores."""
        if self._store is None:
            return 0
        return self._store.event_count

    def __repr__(self) -> str:
        """Return string representation."""
        n_events = len(self) if self._store else 0
        return (
            f"{self.__class__.__name__}("
            f"sources={len(self._sources)}, "
            f"events={n_events})"
        )

    # endregion


# endregion
