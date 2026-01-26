"""MidiBundle: Container for MIDI EventStores split by event category.

This module provides a bundle class that separates MIDI events into
notes and control events, mirroring the ScoreBundle structure.

Design principles:
- Consistent interface with ScoreBundle
- Automatic splitting of MidiEventStore by event_type
- Support for both performance and score MIDI
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from timetoalign.loader.bundle import EventBundle
from timetoalign.loader.midi.store import MidiEventStore

# Event types that belong to "notes" category
NOTE_EVENT_TYPES: frozenset[str] = frozenset({"Note"})

# Event types that belong to "controls" category
CONTROL_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "ControlChange",
        "ProgramChange",
        "PitchBend",
    }
)

# Store names in canonical order
STORE_NAMES: tuple[str, ...] = ("notes", "controls")


@dataclass
class MidiBundle(EventBundle):
    """Container for MIDI data organized by category.

    Splits a single MidiEventStore into notes and control events
    for consistent bundle interface with ScoreBundle. This enables
    uniform timeline creation across all loader types.

    Attributes:
        notes: MidiEventStore containing Note events.
        controls: MidiEventStore containing ControlChange, ProgramChange,
            PitchBend, and other control events.
        metadata: Source metadata (ticks_per_beat, format, etc.).

    Examples:
        >>> # Create from a loaded MidiEventStore
        >>> bundle = MidiBundle.from_store(loader.events)

        >>> # Access stores
        >>> print(f"Notes: {len(bundle.notes)}")
        >>> print(f"Controls: {len(bundle.controls)}")

        >>> # Create timeline
        >>> timeline = bundle.to_default_timeline(uid="midi_score")
    """

    notes: MidiEventStore
    controls: MidiEventStore
    metadata: dict[str, Any] = field(default_factory=dict)

    # region Class Methods

    @classmethod
    def empty(cls) -> MidiBundle:
        """Create an empty MidiBundle with empty stores.

        Returns:
            A MidiBundle with empty notes and controls stores.
        """
        from timetoalign.core import TimeUnit

        return cls(
            notes=MidiEventStore.empty(TimeUnit.ticks),
            controls=MidiEventStore.empty(TimeUnit.ticks),
            metadata={},
        )

    @classmethod
    def from_store(
        cls,
        store: MidiEventStore,
        metadata: dict[str, Any] | None = None,
    ) -> MidiBundle:
        """Create a MidiBundle by splitting a single MidiEventStore.

        Separates Note events from control events (ControlChange,
        ProgramChange, PitchBend) into separate stores.

        Args:
            store: The source MidiEventStore containing all events.
            metadata: Optional metadata to attach to the bundle.

        Returns:
            A MidiBundle with notes and controls separated.

        Examples:
            >>> loader = PerformanceMidiLoader()
            >>> loader.load("piece.mid")
            >>> bundle = MidiBundle.from_store(loader.events)
        """
        # Filter notes
        notes = store.filter(event_type="Note")

        # Filter controls: accumulate all control event types
        controls = MidiEventStore.empty(store.unit, store.number_type)
        for event_type in CONTROL_EVENT_TYPES:
            filtered = store.filter(event_type=event_type)
            if len(filtered) > 0:
                controls.extend(filtered)

        return cls(
            notes=notes,
            controls=controls,
            metadata=metadata or {},
        )

    # endregion

    # region Instance Methods

    def extend(self, other: MidiBundle) -> None:
        """Extend this bundle with another bundle's data.

        Args:
            other: The MidiBundle to merge into this one.
        """
        self.notes.extend(other.notes)
        self.controls.extend(other.controls)
        self.metadata.update(other.metadata)

    def summary(self) -> dict[str, Any]:
        """Get summary of all stores.

        Returns:
            Dict with counts and metadata.
        """
        return {
            "notes_count": len(self.notes),
            "controls_count": len(self.controls),
            **self.metadata,
        }

    # endregion

    # region Magic Methods

    def __repr__(self) -> str:
        """Return string representation."""
        return f"MidiBundle(notes={len(self.notes)}, controls={len(self.controls)})"

    # endregion

    # region EventBundle Protocol

    def __iter__(self) -> Iterator[MidiEventStore]:
        """Iterate over stores in canonical order.

        Yields:
            MidiEventStores: notes, then controls.
        """
        yield self.notes
        yield self.controls

    def __len__(self) -> int:
        """Return number of stores (always 2)."""
        return len(STORE_NAMES)

    def __getitem__(self, name: str) -> MidiEventStore:
        """Get store by name.

        Args:
            name: Store name ("notes" or "controls").

        Returns:
            The MidiEventStore for that category.

        Raises:
            KeyError: If name is not valid.
        """
        if name == "notes":
            return self.notes
        elif name == "controls":
            return self.controls
        raise KeyError(f"Unknown store: {name!r}. Valid: {STORE_NAMES}")

    def keys(self) -> tuple[str, ...]:
        """Return store names in canonical order.

        Returns:
            ("notes", "controls")
        """
        return STORE_NAMES

    def items(self) -> Iterator[tuple[str, MidiEventStore]]:
        """Iterate over (name, store) pairs.

        Yields:
            Tuples of (name, MidiEventStore) in canonical order.
        """
        yield ("notes", self.notes)
        yield ("controls", self.controls)

    def values(self) -> Iterator[MidiEventStore]:
        """Iterate over stores.

        Yields:
            MidiEventStores in canonical order.
        """
        yield self.notes
        yield self.controls

    # endregion
