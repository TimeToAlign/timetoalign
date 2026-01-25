"""Loader: Base class for loading music representations into TimeToAlign!

A Loader orchestrates:
- Loading one or more source files
- Aggregating events into an EventStore
- Storing file/source metadata
- Future: C-maps, Matches

Design principles:
- Multi-source: One Loader can aggregate multiple files
- Metadata in table: Deterministic, stored in PyArrow schema metadata
- Delegation: Stats/queries delegate to EventStore
- Subclassable: Domain-specific loaders (MidiLoader, etc.) extend this
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from typing_extensions import Self

from timetoalign.core import NumberType, TimeUnit

from .store import EventStore

if TYPE_CHECKING:
    pass


class Loader(ABC):
    """Abstract base class for loading music representations.

    Loader provides a unified interface for loading one or more source files
    and aggregating their events into an EventStore. Metadata about the sources
    is stored in the PyArrow table's schema metadata for determinism.

    Subclasses must implement:
    - _load_source(): Parse a single source file into event rows
    - _default_unit: The default time unit for this loader type

    Attributes:
        events: The EventStore containing all loaded events.
        sources: List of loaded source file paths.
        unit: The time unit for coordinates.
        number_type: The number type for coordinates.

    Examples:
        >>> # Subclass implementation
        >>> class MidiLoader(Loader):
        ...     _default_unit = TimeUnit.ticks
        ...     _event_store_class = EventStore
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
    _event_store_class: ClassVar[type[EventStore]] = EventStore

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
        self._events: EventStore = self._event_store_class.empty(
            self._unit, self._number_type
        )

    # region Abstract Methods

    @abstractmethod
    def _load_source(self, source: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Load a single source file.

        Subclasses implement this to parse their specific format.

        Args:
            source: Path to the source file.

        Returns:
            A tuple of (metadata_dict, event_rows):
            - metadata_dict: File-specific metadata (format, duration, etc.)
            - event_rows: List of event dictionaries ready for EventStore

        Raises:
            FileNotFoundError: If the source file doesn't exist.
            ValueError: If the source file is invalid.
        """
        ...

    # endregion

    # region Properties

    @property
    def events(self) -> EventStore:
        """The EventStore containing all loaded events."""
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

    # endregion

    # region Loading

    def load(self, *sources: Path | str) -> Self:
        """Load one or more source files.

        Events from all sources are aggregated into the EventStore.
        Metadata for each source is recorded separately.

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

            # Get source metadata and event rows
            source_meta, event_rows = self._load_source(path)

            # Add loading metadata
            source_meta["path"] = str(path)
            source_meta["loaded_at"] = datetime.now(timezone.utc).isoformat()

            # Track source
            self._sources.append(path)
            self._source_metadata.append(source_meta)

            # Add events
            if event_rows:
                new_store = self._event_store_class.from_dicts(
                    event_rows, self._unit, self._number_type
                )
                self._events.extend(new_store)

        return self

    def clear(self) -> None:
        """Clear all loaded sources and events."""
        self._sources.clear()
        self._source_metadata.clear()
        self._events = self._event_store_class.empty(self._unit, self._number_type)

    # endregion

    # region Stats (delegated to EventStore)

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

        Note: This creates a new Loader with the EventStore loaded,
        but source paths may not be accessible for re-loading.

        Args:
            path: Path to the Parquet file.

        Returns:
            A new Loader with events loaded from the file.
        """
        events = cls._event_store_class.from_parquet(path)
        loader = cls.__new__(cls)
        loader._unit = events.unit
        loader._number_type = events.number_type
        loader._events = events
        loader._sources = []
        loader._source_metadata = []
        return loader

    # endregion
