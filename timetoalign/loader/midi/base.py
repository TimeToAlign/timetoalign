"""MidiLoader: Abstract base class for MIDI loaders."""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, ClassVar, cast

from timetoalign.core import TimeUnit
from timetoalign.loader import Loader

from .events import MidiEventData

if TYPE_CHECKING:
    from timetoalign.loader.midi.store import MidiStore


class MidiLoader(Loader):
    """Abstract base class for MIDI loaders.

    Subclasses must implement:
    - _load_source(): Parse MIDI file into event rows
    - ticks_per_beat: Property returning PPQ
    """

    _default_unit: ClassVar[TimeUnit] = TimeUnit.ticks
    _event_data_class: ClassVar[type[MidiEventData]] = MidiEventData

    @property
    @abstractmethod
    def ticks_per_beat(self) -> int | None:
        """Return the ticks per beat (PPQ) if available."""
        ...

    @property
    def events(self) -> MidiEventData:
        """The MidiEventData containing all loaded events."""
        return cast(MidiEventData, self._events)

    @property
    def store(self) -> "MidiStore":
        """Return a MidiStore wrapping the loader's events.

        The single MidiEventData is split into notes and controls
        for consistent interface with ScoreStore.

        Returns:
            A MidiStore with notes and controls separated.
        """
        from timetoalign.loader.midi.store import MidiStore

        return MidiStore.from_data(self.events, metadata=self.metadata)
