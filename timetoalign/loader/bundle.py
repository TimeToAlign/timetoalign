"""EventBundle: Base class for collections of EventStores.

This module provides the abstract base class for bundles (collections of
EventStores) and a simple wrapper for single-store loaders.

Design principles:
- Uniform interface for both single-store and multi-store bundles
- Consistent timeline creation across all loader types
- Children timelines maintain their own 0-based coordinate systems
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from timetoalign.loader.store import EventStore
    from timetoalign.timelines.base import Timeline


class EventBundle(ABC):
    """Abstract base class for collections of EventStores.

    Provides a uniform interface for both single-store and multi-store
    bundles, enabling consistent timeline creation across loader types.

    All bundles must implement the collection protocol (iteration, keys,
    items, getitem) to allow uniform access to their constituent stores.

    Subclasses:
        - ScoreBundle: notes, measures, controls, annotations
        - MidiBundle: notes, controls
        - SingleStoreBundle: generic wrapper for any single store

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
    def __iter__(self) -> Iterator[EventStore]:
        """Iterate over stores in canonical order.

        Yields:
            EventStores in the bundle's canonical order.
        """
        ...

    @abstractmethod
    def items(self) -> Iterator[tuple[str, EventStore]]:
        """Iterate over (name, store) pairs in canonical order.

        Yields:
            Tuples of (store_name, EventStore).
        """
        ...

    @abstractmethod
    def keys(self) -> tuple[str, ...]:
        """Return store names in canonical order.

        Returns:
            Tuple of store names.
        """
        ...

    @abstractmethod
    def __getitem__(self, name: str) -> EventStore:
        """Get store by name.

        Args:
            name: The store name.

        Returns:
            The EventStore for that name.

        Raises:
            KeyError: If name is not a valid store name.
        """
        ...

    @abstractmethod
    def __len__(self) -> int:
        """Return number of stores in the bundle."""
        ...

    # endregion

    # region Collection Protocol

    def __contains__(self, name: object) -> bool:
        """Check if store name exists in the bundle.

        Args:
            name: Store name to check.

        Returns:
            True if name is a valid store name.
        """
        return name in self.keys()

    def values(self) -> Iterator[EventStore]:
        """Iterate over stores.

        Yields:
            EventStores in canonical order.
        """
        yield from self

    # endregion

    # region Timeline Creation

    def to_timeline(
        self,
        uid: str | None = None,
        store_filters: dict[str, dict[str, Any]] | None = None,
        include_stores: list[str] | None = None,
        exclude_stores: list[str] | None = None,
        flatten: bool = False,
    ) -> Timeline:
        """Create a Timeline from this bundle.

        By default, each store becomes a child timeline embedded at offset 0,
        maintaining its own 0-based coordinate system. The parent timeline's
        length equals the maximum length across all children.

        Args:
            uid: Unique ID for the parent timeline. Auto-generated if None.
            store_filters: Per-store filter kwargs to apply before timeline
                creation. Example: {"notes": {"event_type": "Note"}} excludes
                rests from the notes store.
            include_stores: Only include these stores (default: all non-empty).
            exclude_stores: Exclude these stores from the timeline.
            flatten: If True, merge all events into a single parent timeline
                without children. If False (default), each store becomes a
                child timeline at offset 0.

        Returns:
            A Timeline with the requested structure.

        Raises:
            ValueError: If no stores remain after filtering, or all stores
                are empty.

        Examples:
            >>> # Default: each store as a child
            >>> timeline = bundle.to_timeline(uid="my_score")
            >>> notes = timeline.get_child("notes")

            >>> # Filtered: only Note events, exclude annotations
            >>> timeline = bundle.to_timeline(
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

    def to_default_timeline(self, uid: str | None = None) -> Timeline:
        """Create a canonical timeline with all stores as children.

        Each non-empty store becomes a child timeline at offset 0, preserving
        its own 0-based coordinate system. This is the recommended way to
        create timelines from loaded data.

        Args:
            uid: Unique ID for the parent timeline.

        Returns:
            A parent Timeline with child timelines for each non-empty store.

        Examples:
            >>> timeline = bundle.to_default_timeline(uid="chopin_score")
            >>> for offset, child in timeline.iter_children():
            ...     print(f"{child.id}: {child.n_events} events at offset {offset}")
        """
        return self.to_timeline(uid=uid, flatten=False)

    # endregion


class SingleStoreBundle(EventBundle):
    """Bundle wrapper for a single EventStore.

    Provides EventBundle interface compatibility for loaders that naturally
    produce a single EventStore rather than multiple categorized stores.

    This is used as the default bundle type for loaders that don't have
    specialized bundle implementations (e.g., simple audio loaders).

    Attributes:
        store: The wrapped EventStore.
        name: The store name.

    Examples:
        >>> store = EventStore.from_dicts([...], unit=TimeUnit.seconds)
        >>> bundle = SingleStoreBundle(store, name="beats")
        >>> timeline = bundle.to_default_timeline()
    """

    def __init__(self, store: EventStore, name: str = "events") -> None:
        """Initialize SingleStoreBundle.

        Args:
            store: The EventStore to wrap.
            name: The name for this store. Used as the child timeline ID.
        """
        self._store = store
        self._name = name

    # region EventBundle Protocol

    def __iter__(self) -> Iterator[EventStore]:
        """Yield the single store."""
        yield self._store

    def items(self) -> Iterator[tuple[str, EventStore]]:
        """Yield (name, store) pair."""
        yield (self._name, self._store)

    def keys(self) -> tuple[str, ...]:
        """Return tuple with single store name."""
        return (self._name,)

    def __getitem__(self, name: str) -> EventStore:
        """Get store by name.

        Args:
            name: Must match the store name.

        Returns:
            The wrapped EventStore.

        Raises:
            KeyError: If name doesn't match.
        """
        if name == self._name:
            return self._store
        raise KeyError(f"Unknown store: {name!r}. Valid: {self.keys()}")

    def __len__(self) -> int:
        """Return 1 (single store)."""
        return 1

    # endregion

    # region Properties

    @property
    def store(self) -> EventStore:
        """The wrapped EventStore."""
        return self._store

    @property
    def name(self) -> str:
        """The store name."""
        return self._name

    # endregion

    def __repr__(self) -> str:
        """Return string representation."""
        return f"SingleStoreBundle({self._name}={len(self._store)} events)"
