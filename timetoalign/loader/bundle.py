"""EventStore: Base class for collections of EventData.

This module provides the abstract base class for stores (collections of
EventData) and a simple wrapper for single-data stores.

NOTE: This class was renamed from EventBundle to EventStore in the 2026-01 API
refactoring. EventStore holds one or more EventData tables.
- EventData (formerly EventStore): PyArrow-based storage for timeline events
- EventStore (formerly EventBundle): Container for multiple EventData

Design principles:
- Uniform interface for both single-data and multi-data stores
- Consistent timeline creation across all loader types
- Children timelines maintain their own 0-based coordinate systems
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from timetoalign.loader.store import EventData
    from timetoalign.maps import ConversionMap
    from timetoalign.timelines.base import Timeline


class EventStore(ABC):
    """Abstract base class for collections of EventData.

    Provides a uniform interface for both single-data and multi-data
    stores, enabling consistent timeline creation across loader types.

    All stores must implement the collection protocol (iteration, keys,
    items, getitem) to allow uniform access to their constituent data.

    NOTE: This class was renamed from EventBundle to EventStore in the 2026-01 API
    refactoring. EventStore holds one or more EventData tables.

    Subclasses:
        - ScoreStore: notes, measures, controls, annotations
        - MidiStore: notes, controls
        - SingleEventStore: generic wrapper for any single EventData

    Examples:
        >>> # Iterate over stores
        >>> for name, store in bundle.items():
        ...     print(f"{name}: {len(store)} events")

        >>> # Create default timeline with children
        >>> timeline = bundle.to_default_timeline(uid="my_score")

        >>> # Create filtered timeline
        >>> timeline = bundle.to_timeline(
        ...     store_filters={"notes": {"event_type": "Note"}},
        ...     exclude_stores=["annotations"],
        ... )
    """

    # region Abstract Methods

    @abstractmethod
    def __iter__(self) -> Iterator["EventData"]:
        """Iterate over data in canonical order.

        Yields:
            EventData in the store's canonical order.
        """
        ...

    @abstractmethod
    def items(self) -> Iterator[tuple[str, "EventData"]]:
        """Iterate over (name, data) pairs in canonical order.

        Yields:
            Tuples of (data_name, EventData).
        """
        ...

    @abstractmethod
    def keys(self) -> tuple[str, ...]:
        """Return data names in canonical order.

        Returns:
            Tuple of data names.
        """
        ...

    @abstractmethod
    def __getitem__(self, name: str) -> "EventData":
        """Get data by name.

        Args:
            name: The data name.

        Returns:
            The EventData for that name.

        Raises:
            KeyError: If name is not a valid data name.
        """
        ...

    @abstractmethod
    def __len__(self) -> int:
        """Return number of EventData in the store."""
        ...

    # endregion

    # region Collection Protocol

    def __contains__(self, name: object) -> bool:
        """Check if data name exists in the store.

        Args:
            name: Data name to check.

        Returns:
            True if name is a valid data name.
        """
        return name in self.keys()

    def values(self) -> Iterator["EventData"]:
        """Iterate over data.

        Yields:
            EventData in canonical order.
        """
        yield from self

    # endregion

    # region Conversion Maps

    def get_cmaps(self) -> dict[str, "ConversionMap"]:
        """Get ConversionMaps derivable from store metadata.

        Returns a dictionary mapping target unit names to ConversionMaps
        that can convert from this bundle's native unit. Subclasses should
        override to provide maps based on available metadata (PPQ, tempo
        events, sample rate, etc.).

        Returns:
            Dict mapping target unit name (e.g., "quarters", "seconds") to
            ConversionMap instances. Empty dict if no C-Maps can be derived.

        Examples:
            >>> bundle = midi_loader.load("performance.mid")
            >>> cmaps = bundle.get_cmaps()
            >>> if "quarters" in cmaps:
            ...     quarters = cmaps["quarters"](960)  # Convert 960 ticks
        """
        return {}

    # endregion

    # region Timeline Creation

    def to_timeline(
        self,
        uid: str | None = None,
        store_filters: dict[str, dict[str, Any]] | None = None,
        include_stores: list[str] | None = None,
        exclude_stores: list[str] | None = None,
        flatten: bool = False,
    ) -> "Timeline":
        """Create a Timeline from this store.

        By default, each data becomes a child timeline embedded at offset 0,
        maintaining its own 0-based coordinate system. The parent timeline's
        length equals the maximum length across all children.

        Args:
            uid: Unique ID for the parent timeline. Auto-generated if None.
            store_filters: Per-data filter kwargs to apply before timeline
                creation. Example: {"notes": {"event_type": "Note"}} excludes
                rests from the notes data.
            include_stores: Only include these data (default: all non-empty).
            exclude_stores: Exclude these data from the timeline.
            flatten: If True, merge all events into a single parent timeline
                without children. If False (default), each data becomes a
                child timeline at offset 0.

        Returns:
            A Timeline with the requested structure.

        Raises:
            ValueError: If no data remain after filtering, or all data
                are empty.

        Examples:
            >>> # Default: each data as a child
            >>> timeline = store.to_timeline(uid="my_score")
            >>> notes = timeline.get_child("notes")

            >>> # Filtered: only Note events, exclude annotations
            >>> timeline = store.to_timeline(
            ...     store_filters={"notes": {"event_type": "Note"}},
            ...     exclude_stores=["annotations"],
            ... )
        """
        from timetoalign.timelines.factory import create_timeline_from_bundle

        return create_timeline_from_bundle(
            self,
            uid=uid,
            store_filters=store_filters,
            include_stores=include_stores,
            exclude_stores=exclude_stores,
            flatten=flatten,
        )

    def to_default_timeline(self, uid: str | None = None) -> "Timeline":
        """Create a canonical timeline with all data as children.

        Each non-empty data becomes a child timeline at offset 0, preserving
        its own 0-based coordinate system. This is the recommended way to
        create timelines from loaded data.

        Args:
            uid: Unique ID for the parent timeline.

        Returns:
            A parent Timeline with child timelines for each non-empty data.

        Examples:
            >>> timeline = store.to_default_timeline(uid="chopin_score")
            >>> for offset, child in timeline.iter_children():
            ...     print(f"{child.id}: {child.n_events} events at offset {offset}")
        """
        return self.to_timeline(uid=uid, flatten=False)

    # endregion


class SingleEventStore(EventStore):
    """Store wrapper for a single EventData.

    Provides EventStore interface compatibility for loaders that naturally
    produce a single EventData rather than multiple categorized data.

    This is used as the default store type for loaders that don't have
    specialized store implementations (e.g., simple audio loaders).

    NOTE: This class was renamed from SingleStoreBundle to SingleEventStore in
    the 2026-01 API refactoring.

    Attributes:
        data: The wrapped EventData.
        name: The data name.

    Examples:
        >>> data = EventData.from_dicts([...], unit=TimeUnit.seconds)
        >>> store = SingleEventStore(data, name="beats")
        >>> timeline = store.to_default_timeline()
    """

    def __init__(self, data: "EventData", name: str = "events") -> None:
        """Initialize SingleEventStore.

        Args:
            data: The EventData to wrap.
            name: The name for this data. Used as the child timeline ID.
        """
        self._data = data
        self._name = name

    # region EventStore Protocol

    def __iter__(self) -> Iterator["EventData"]:
        """Yield the single data."""
        yield self._data

    def items(self) -> Iterator[tuple[str, "EventData"]]:
        """Yield (name, data) pair."""
        yield (self._name, self._data)

    def keys(self) -> tuple[str, ...]:
        """Return tuple with single data name."""
        return (self._name,)

    def __getitem__(self, name: str) -> "EventData":
        """Get data by name.

        Args:
            name: Must match the data name.

        Returns:
            The wrapped EventData.

        Raises:
            KeyError: If name doesn't match.
        """
        if name == self._name:
            return self._data
        raise KeyError(f"Unknown data: {name!r}. Valid: {self.keys()}")

    def __len__(self) -> int:
        """Return 1 (single data)."""
        return 1

    # endregion

    # region Properties

    @property
    def data(self) -> "EventData":
        """The wrapped EventData."""
        return self._data

    @property
    def name(self) -> str:
        """The data name."""
        return self._name

    # endregion

    def __repr__(self) -> str:
        """Return string representation."""
        return f"SingleEventStore({self._name}={len(self._data)} events)"
