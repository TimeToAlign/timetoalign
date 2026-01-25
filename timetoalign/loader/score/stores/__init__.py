"""Stores package for category-specific EventStores."""

from __future__ import annotations

from .annotation import AnnotationEventStore
from .control import ControlEventStore
from .measure import MeasureEventStore
from .note import NoteEventStore

__all__ = [
    "NoteEventStore",
    "MeasureEventStore",
    "ControlEventStore",
    "AnnotationEventStore",
]
