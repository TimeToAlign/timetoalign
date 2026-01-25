"""Stores package for category-specific EventStores."""

from __future__ import annotations

from .note import NoteEventStore
from .measure import MeasureEventStore
from .control import ControlEventStore
from .annotation import AnnotationEventStore

__all__ = [
    "NoteEventStore",
    "MeasureEventStore",
    "ControlEventStore",
    "AnnotationEventStore",
]
