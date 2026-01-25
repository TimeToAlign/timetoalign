"""Stores package for category-specific EventStores."""

from __future__ import annotations

from .annotations import AnnotationEventStore
from .controls import ControlEventStore
from .measures import MeasureEventStore
from .notes import NoteEventStore

__all__ = [
    "NoteEventStore",
    "MeasureEventStore",
    "ControlEventStore",
    "AnnotationEventStore",
]
