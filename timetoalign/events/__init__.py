"""Events package for the TimeToAlign library.

This module provides:
- EventStore: A container for events with query capabilities
- Event dataclasses for instant and interval events
- Factory functions for creating events

Events are the fundamental data objects that live on timelines.
"""

from __future__ import annotations

from .store import EventStore
from .types import (
    Event,
    InstantEvent,
    IntervalEvent,
    make_instant_event,
    make_interval_event,
)

__all__ = [
    # Event types
    "Event",
    "InstantEvent",
    "IntervalEvent",
    # Store
    "EventStore",
    # Factory functions
    "make_instant_event",
    "make_interval_event",
]
