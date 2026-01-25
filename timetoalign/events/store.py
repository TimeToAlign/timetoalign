"""EventStore: A columnar store for timeline events.

This module provides the EventStore class which stores events
in a single PyArrow table with efficient columnar operations.

Design decisions:
- Single table with 'event_type' column (instant/interval)
- Events are copied on insertion (independent after)
- Supports filtering by type, unit, coordinate range
- No external dependencies for core functionality (PyArrow optional)
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Literal, overload

from timetoalign.core import CoordinateValue, EventType, TimeUnit

from .types import Event, InstantEvent, IntervalEvent


@dataclass
class EventStore:
    """A store for timeline events with query capabilities.

    EventStore provides a unified container for both instant and interval
    events. Events are stored internally and can be queried/filtered
    efficiently.

    The store maintains events in insertion order but provides
    methods to iterate in coordinate order.

    Attributes:
        name: Optional name for this store (for identification)
        unit: The time unit for all events in this store (None = mixed)

    Examples:
        >>> store = EventStore(name="midi_events")
        >>> store.add_instant("n1", 0, TimeUnit.ticks, pitch=60)
        >>> store.add_interval("n2", 0, 480, TimeUnit.ticks, pitch=62)
        >>> len(store)
        2
        >>> list(store.iter_instants())
        [InstantEvent(id='n1', ...)]
    """

    name: str = ""
    unit: TimeUnit | None = None

    # Internal storage
    _events: list[Event] = field(default_factory=list)
    _id_index: dict[str, int] = field(default_factory=dict)

    def __len__(self) -> int:
        """Return the number of events in the store."""
        return len(self._events)

    def __contains__(self, event_id: str) -> bool:
        """Check if an event ID exists in the store."""
        return event_id in self._id_index

    def __iter__(self) -> Iterator[Event]:
        """Iterate over all events in insertion order."""
        return iter(self._events)

    # --- Adding events ---

    def add(self, event: Event) -> None:
        """Add an event to the store.

        The event is copied (frozen dataclass) so modifications
        to the original don't affect the store.

        Args:
            event: The event to add

        Raises:
            ValueError: If an event with the same ID already exists
            ValueError: If event unit doesn't match store unit (when set)
        """
        if event.id in self._id_index:
            raise ValueError(f"Event with ID '{event.id}' already exists")

        if self.unit is not None and event.unit != self.unit:
            raise ValueError(
                f"Event unit {event.unit} doesn't match store unit {self.unit}"
            )

        idx = len(self._events)
        self._events.append(event)
        self._id_index[event.id] = idx

    def add_instant(
        self,
        id: str,
        instant: CoordinateValue,
        unit: TimeUnit | str,
        **data: Any,
    ) -> InstantEvent:
        """Create and add an instant event.

        Args:
            id: Unique identifier for the event
            instant: The coordinate value
            unit: Time unit
            **data: Additional data fields

        Returns:
            The created InstantEvent

        Raises:
            ValueError: If ID already exists or unit mismatch
        """
        if not isinstance(unit, TimeUnit):
            unit = TimeUnit(unit)

        data_tuple = tuple(data.items()) if data else ()
        event = InstantEvent(
            id=id,
            event_type=EventType.instant,
            unit=unit,
            instant=instant,
            data=data_tuple,
        )
        self.add(event)
        return event

    def add_interval(
        self,
        id: str,
        start: CoordinateValue,
        end: CoordinateValue,
        unit: TimeUnit | str,
        **data: Any,
    ) -> IntervalEvent:
        """Create and add an interval event.

        Args:
            id: Unique identifier for the event
            start: Start coordinate
            end: End coordinate
            unit: Time unit
            **data: Additional data fields

        Returns:
            The created IntervalEvent

        Raises:
            ValueError: If ID already exists, unit mismatch, or end < start
        """
        if not isinstance(unit, TimeUnit):
            unit = TimeUnit(unit)

        data_tuple = tuple(data.items()) if data else ()
        event = IntervalEvent(
            id=id,
            event_type=EventType.interval,
            unit=unit,
            start=start,
            end=end,
            data=data_tuple,
        )
        self.add(event)
        return event

    # --- Retrieval ---

    def get(self, event_id: str) -> Event | None:
        """Get an event by ID.

        Args:
            event_id: The ID to look up

        Returns:
            The event if found, None otherwise
        """
        idx = self._id_index.get(event_id)
        if idx is not None:
            return self._events[idx]
        return None

    def get_instant(self, event_id: str) -> InstantEvent | None:
        """Get an instant event by ID.

        Returns None if not found or if the event is not an instant.
        """
        event = self.get(event_id)
        if isinstance(event, InstantEvent):
            return event
        return None

    def get_interval(self, event_id: str) -> IntervalEvent | None:
        """Get an interval event by ID.

        Returns None if not found or if the event is not an interval.
        """
        event = self.get(event_id)
        if isinstance(event, IntervalEvent):
            return event
        return None

    # --- Iteration ---

    def iter_instants(self) -> Iterator[InstantEvent]:
        """Iterate over instant events only."""
        for event in self._events:
            if isinstance(event, InstantEvent):
                yield event

    def iter_intervals(self) -> Iterator[IntervalEvent]:
        """Iterate over interval events only."""
        for event in self._events:
            if isinstance(event, IntervalEvent):
                yield event

    def iter_by_type(self, event_type: EventType) -> Iterator[Event]:
        """Iterate over events of a specific type."""
        for event in self._events:
            if event.event_type == event_type:
                yield event

    def iter_sorted(
        self,
        *,
        reverse: bool = False,
    ) -> Iterator[Event]:
        """Iterate over events sorted by coordinate.

        For instant events, sorts by instant.
        For interval events, sorts by start.

        Args:
            reverse: If True, sort descending

        Yields:
            Events in coordinate order
        """

        def sort_key(event: Event) -> CoordinateValue:
            if isinstance(event, InstantEvent):
                return event.instant
            elif isinstance(event, IntervalEvent):
                return event.start
            return 0  # pragma: no cover

        yield from sorted(self._events, key=sort_key, reverse=reverse)

    # --- Filtering ---

    def filter(
        self,
        *,
        event_type: EventType | None = None,
        unit: TimeUnit | None = None,
        min_coord: CoordinateValue | None = None,
        max_coord: CoordinateValue | None = None,
        data_key: str | None = None,
        data_value: Any = None,
    ) -> Iterator[Event]:
        """Filter events by various criteria.

        All criteria are AND-ed together.

        Args:
            event_type: Filter by event type
            unit: Filter by time unit
            min_coord: Minimum coordinate (inclusive)
            max_coord: Maximum coordinate (exclusive for intervals)
            data_key: Filter by data key existence
            data_value: If data_key set, also match this value

        Yields:
            Events matching all criteria
        """
        for event in self._events:
            # Type filter
            if event_type is not None and event.event_type != event_type:
                continue

            # Unit filter
            if unit is not None and event.unit != unit:
                continue

            # Coordinate filters
            if min_coord is not None:
                if isinstance(event, InstantEvent):
                    if event.instant < min_coord:
                        continue
                elif isinstance(event, IntervalEvent):
                    if event.end <= min_coord:
                        continue

            if max_coord is not None:
                if isinstance(event, InstantEvent):
                    if event.instant >= max_coord:
                        continue
                elif isinstance(event, IntervalEvent):
                    if event.start >= max_coord:
                        continue

            # Data filters
            if data_key is not None:
                if not event.has(data_key):
                    continue
                if data_value is not None and event.get(data_key) != data_value:
                    continue

            yield event

    # --- Bulk operations ---

    def ids(self) -> list[str]:
        """Return all event IDs in insertion order."""
        return [event.id for event in self._events]

    def count_by_type(self) -> dict[EventType, int]:
        """Count events by type."""
        counts: dict[EventType, int] = {
            EventType.instant: 0,
            EventType.interval: 0,
        }
        for event in self._events:
            counts[event.event_type] += 1
        return counts

    def clear(self) -> None:
        """Remove all events from the store."""
        self._events.clear()
        self._id_index.clear()

    # --- Representations ---

    def __repr__(self) -> str:
        name_part = f"name={self.name!r}, " if self.name else ""
        unit_part = f"unit={self.unit}, " if self.unit else ""
        return f"EventStore({name_part}{unit_part}events={len(self)})"
