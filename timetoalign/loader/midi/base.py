"""MidiLoader: Abstract base class for MIDI loaders."""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, ClassVar, cast

from timetoalign.core import TimeUnit
from timetoalign.loader import Loader

from .store import MidiEventStore

if TYPE_CHECKING:
    from timetoalign.loader.midi.bundle import MidiBundle


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

    @property
    def events(self) -> MidiEventStore:
        """The MidiEventStore containing all loaded events."""
        return cast(MidiEventStore, self._events)

    @property
    def bundle(self) -> "MidiBundle":
        """Return a MidiBundle wrapping the loader's events.

        The single MidiEventStore is split into notes and controls
        for consistent interface with ScoreBundle.

        Returns:
            A MidiBundle with notes and controls separated.
        """
        from timetoalign.loader.midi.bundle import MidiBundle

        return MidiBundle.from_store(self.events, metadata=self.metadata)
