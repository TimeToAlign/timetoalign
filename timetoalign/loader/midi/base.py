"""MidiLoader: Abstract base class for MIDI loaders."""

from __future__ import annotations

from abc import abstractmethod
from typing import ClassVar

from timetoalign.core import TimeUnit
from timetoalign.loader import Loader

from .store import MidiEventStore


class MidiLoader(Loader):
    """Abstract base class for MIDI loaders.
    
    Subclasses must implement:
    - _load_source(): Parse MIDI file into event rows
    - ticks_per_beat: Property returning PPQ
    """
    
    _default_unit: ClassVar[TimeUnit] = TimeUnit.ticks
    _event_store_class: ClassVar[type[MidiEventStore]] = MidiEventStore
    
    @property
    @abstractmethod
    def ticks_per_beat(self) -> int | None:
        """Return the ticks per beat (PPQ) if available."""
        ...
