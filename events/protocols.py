from __future__ import annotations

from typing import Protocol, runtime_checkable, Any

from timetoalign.coordinates.coordinate import Coordinate

@runtime_checkable
class Event(Protocol):
    """Base protocol for all events."""
    id: str
    category: str

@runtime_checkable
class InstantEvent(Event, Protocol):
    """An event that happens at a single instant."""
    instant: Coordinate

@runtime_checkable
class IntervalEvent(Event, Protocol):
    """An event that spans a time interval."""
    start: Coordinate
    end: Coordinate
    
    @property
    def duration(self) -> Coordinate:
        ...
