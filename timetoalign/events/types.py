"""Event type definitions for the TTA model.

This module defines the Event dataclasses that represent occurrences
on timelines. Events are either instant (point-in-time) or interval
(duration-based).

Per the TTA manuscript:
- InstantEvent: Associated with a single instant (no duration)
- IntervalEvent: Defined by start and end instants [start, end)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from timetoalign.core import Coordinate, CoordinateValue, EventType, TimeUnit


@dataclass(frozen=True, slots=True, kw_only=True)
class Event:
    """Base class for all events on a timeline.

    Events are immutable value objects that represent occurrences
    associated with coordinates on a timeline.

    Attributes:
        id: Unique identifier for this event (scoped or local)
        event_type: Whether this is an instant or interval event
        unit: The time unit for coordinates
        data: Optional arbitrary data payload (must be hashable for frozen)

    Note:
        This base class should not be instantiated directly.
        Use InstantEvent or IntervalEvent instead.
    """

    id: str
    event_type: EventType
    unit: TimeUnit
    # Note: data has default, so subclass fields must also have defaults
    data: tuple[tuple[str, Any], ...] = field(default_factory=tuple)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the data payload.

        Args:
            key: The key to look up
            default: Value to return if key not found

        Returns:
            The value associated with key, or default if not found
        """
        for k, v in self.data:
            if k == key:
                return v
        return default

    def has(self, key: str) -> bool:
        """Check if a key exists in the data payload."""
        return any(k == key for k, _ in self.data)

    @property
    def data_dict(self) -> dict[str, Any]:
        """Return data as a dictionary (creates new dict each call)."""
        return dict(self.data)


@dataclass(frozen=True, slots=True, kw_only=True)
class InstantEvent(Event):
    """An event defined by a single instant (no duration).

    InstantEvents represent point-in-time occurrences like:
    - Note onsets
    - Marker positions
    - Beat locations

    Attributes:
        instant: The coordinate where this event occurs

    Examples:
        >>> from timetoalign.core import TimeUnit, EventType
        >>> evt = InstantEvent(
        ...     id="note_1",
        ...     event_type=EventType.instant,
        ...     unit=TimeUnit.ticks,
        ...     instant=120,
        ... )
        >>> evt.instant
        120
        >>> evt.coordinate
        Coordinate(120, ticks)
    """

    instant: CoordinateValue

    def __post_init__(self) -> None:
        # Ensure event_type is set correctly
        if self.event_type != EventType.instant:
            object.__setattr__(self, "event_type", EventType.instant)

    @property
    def coordinate(self) -> Coordinate:
        """Return the instant as a Coordinate object."""
        return Coordinate(self.instant, self.unit)

    @property
    def start(self) -> CoordinateValue:
        """Alias for instant (for uniform API with IntervalEvent)."""
        return self.instant

    @property
    def end(self) -> CoordinateValue:
        """Alias for instant (for uniform API with IntervalEvent)."""
        return self.instant


@dataclass(frozen=True, slots=True, kw_only=True)
class IntervalEvent(Event):
    """An event defined by a start and end instant (has duration).

    IntervalEvents represent durational occurrences like:
    - Notes (onset to offset)
    - Regions/sections
    - Segments

    Per TTA manuscript, intervals are left-inclusive, right-exclusive: [start, end)

    Attributes:
        start: The coordinate where this event begins
        end: The coordinate where this event ends (exclusive)

    Examples:
        >>> from timetoalign.core import TimeUnit, EventType
        >>> evt = IntervalEvent(
        ...     id="note_1",
        ...     event_type=EventType.interval,
        ...     unit=TimeUnit.ticks,
        ...     start=0,
        ...     end=480,
        ... )
        >>> evt.duration
        480
        >>> evt.start_coordinate
        Coordinate(0, ticks)
    """

    start: CoordinateValue
    end: CoordinateValue

    def __post_init__(self) -> None:
        # Ensure event_type is set correctly
        if self.event_type != EventType.interval:
            object.__setattr__(self, "event_type", EventType.interval)
        # Validate interval constraint: end >= start
        if self.end < self.start:
            raise ValueError(
                f"IntervalEvent end ({self.end}) must be >= start ({self.start})"
            )

    @property
    def start_coordinate(self) -> Coordinate:
        """Return the start as a Coordinate object."""
        return Coordinate(self.start, self.unit)

    @property
    def end_coordinate(self) -> Coordinate:
        """Return the end as a Coordinate object."""
        return Coordinate(self.end, self.unit)

    @property
    def duration(self) -> CoordinateValue:
        """Return the duration (end - start)."""
        return self.end - self.start

    @property
    def instant(self) -> CoordinateValue:
        """Return start as instant (for uniform API with InstantEvent)."""
        return self.start


# Factory functions for cleaner API


def make_instant_event(
    id: str,
    instant: CoordinateValue,
    unit: TimeUnit | str,
    **data: Any,
) -> InstantEvent:
    """Create an InstantEvent with a cleaner API.

    Args:
        id: Unique identifier
        instant: The coordinate value
        unit: Time unit (can be string, will be coerced)
        **data: Additional data as keyword arguments

    Returns:
        A new InstantEvent
    """
    if not isinstance(unit, TimeUnit):
        unit = TimeUnit(unit)
    data_tuple = tuple(data.items()) if data else ()
    return InstantEvent(
        id=id,
        event_type=EventType.instant,
        unit=unit,
        instant=instant,
        data=data_tuple,
    )


def make_interval_event(
    id: str,
    start: CoordinateValue,
    end: CoordinateValue,
    unit: TimeUnit | str,
    **data: Any,
) -> IntervalEvent:
    """Create an IntervalEvent with a cleaner API.

    Args:
        id: Unique identifier
        start: Start coordinate value
        end: End coordinate value
        unit: Time unit (can be string, will be coerced)
        **data: Additional data as keyword arguments

    Returns:
        A new IntervalEvent
    """
    if not isinstance(unit, TimeUnit):
        unit = TimeUnit(unit)
    data_tuple = tuple(data.items()) if data else ()
    return IntervalEvent(
        id=id,
        event_type=EventType.interval,
        unit=unit,
        start=start,
        end=end,
        data=data_tuple,
    )
