"""ScoreBundle: Container for category-specific EventStores."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from timetoalign.loader.bundle import EventBundle
from timetoalign.loader.score.stores.annotations import AnnotationEventStore
from timetoalign.loader.score.stores.controls import ControlEventStore
from timetoalign.loader.score.stores.measures import MeasureEventStore
from timetoalign.loader.score.stores.notes import NoteEventStore
from timetoalign.loader.store import EventStore

if TYPE_CHECKING:
    from timetoalign.maps import ConversionMap

# Store names in canonical order
STORE_NAMES: tuple[str, ...] = ("notes", "measures", "controls", "annotations")


@dataclass
class ScoreBundle(EventBundle):
    """Container for score data organized by category.

    A ScoreLoader returns a ScoreBundle containing separate EventStores
    for each category (notes, measures, controls, annotations).

    Attributes:
        notes: NoteEventStore with note/rest/chord events.
        measures: MeasureEventStore with measure boundaries.
        controls: ControlEventStore with dynamics, tempo, etc.
        annotations: AnnotationEventStore with text annotations.
        metadata: Source metadata (format, parser, has_rests, divs_per_quarter).
    """

    notes: NoteEventStore
    measures: MeasureEventStore
    controls: ControlEventStore
    annotations: AnnotationEventStore
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> ScoreBundle:
        """Create an empty ScoreBundle with empty stores."""

        return cls(
            notes=NoteEventStore.empty(),
            measures=MeasureEventStore.empty(),
            controls=ControlEventStore.empty(),
            annotations=AnnotationEventStore.empty(),
            metadata={},
        )

    def extend(self, other: ScoreBundle) -> None:
        """Extend this bundle with another bundle's data.

        Args:
            other: The ScoreBundle to add.
        """
        self.notes.extend(other.notes)
        self.measures.extend(other.measures)
        self.controls.extend(other.controls)
        self.annotations.extend(other.annotations)
        # Metadata aggregation strategy: keep last or list?
        # Loader handles source metadata separately.
        # We can merge non-source metadata if needed.
        self.metadata.update(other.metadata)

    def summary(self) -> dict[str, Any]:
        """Get summary of all stores."""
        return {
            "notes_count": len(self.notes),
            "measures_count": len(self.measures),
            "controls_count": len(self.controls),
            "annotations_count": len(self.annotations),
            "has_rests": (
                self.notes.has_rests if hasattr(self.notes, "has_rests") else None
            ),
            **self.metadata,
        }

    def get_cmaps(self, ppq: int = 480) -> dict[str, ConversionMap]:
        """Get ConversionMaps derivable from score bundle metadata.

        Returns C-Maps based on available metadata:
        - "ticks": quarters -> ticks (using provided PPQ)
        - "seconds": quarters -> seconds (if tempo markings available)

        Args:
            ppq: Pulses per quarter note for ticks conversion. Defaults to 480.

        Returns:
            Dict mapping target unit name to ConversionMap.

        Examples:
            >>> bundle = score_loader.load("score.musicxml")
            >>> cmaps = bundle.get_cmaps(ppq=480)
            >>> ticks_map = cmaps["ticks"]
            >>> ticks = ticks_map(2.0)  # 960 ticks at 480 PPQ
        """
        from timetoalign.maps import ScalarMap

        cmaps: dict[str, ConversionMap] = {}

        # Always available: quarters -> ticks
        cmaps["ticks"] = ScalarMap(
            scalar=ppq,
            source_unit="quarters",
            target_unit="ticks",
        )

        # Check for tempo markings to build quarters -> seconds map
        tempo_events = self._extract_tempo_markings()
        if tempo_events:
            cmaps["seconds"] = self._create_tempo_map(tempo_events)

        return cmaps

    def _extract_tempo_markings(self) -> list[tuple[float, float]]:
        """Extract tempo markings from controls store.

        Returns:
            List of (quarter_position, bpm) tuples, sorted by position.
            Empty list if no tempo markings available.
        """
        # Check metadata first for pre-extracted tempo events
        if "tempo_events" in self.metadata:
            return self.metadata["tempo_events"]

        # Extract from controls store - look for Tempo subtypes
        tempo_events: list[tuple[float, float]] = []

        for event in self.controls:
            subtype = event.get("subtype")
            if subtype == "Tempo":
                # Get position (start coordinate) and BPM value
                start = event.get("start")
                bpm = event.get("value")
                if start is not None and bpm is not None:
                    # Handle Fraction or dict representation of start
                    if isinstance(start, dict) and "value" in start:
                        start = start["value"]
                    tempo_events.append((float(start), float(bpm)))

        # Sort by position
        tempo_events.sort(key=lambda x: x[0])

        return tempo_events

    def _create_tempo_map(
        self, tempo_events: list[tuple[float, float]]
    ) -> ConversionMap:
        """Create a quarters -> seconds ConversionMap from tempo markings.

        Args:
            tempo_events: List of (quarter_position, bpm) tuples.

        Returns:
            A TableMap for quarters -> seconds conversion.
        """
        from timetoalign.maps import TableMap

        if not tempo_events:
            raise ValueError("No tempo events provided")

        # Build cumulative time map
        quarter_positions: list[float] = []
        second_positions: list[float] = []

        current_seconds = 0.0

        for i, (quarter, bpm) in enumerate(tempo_events):
            quarter_positions.append(quarter)
            second_positions.append(current_seconds)

            # Calculate time to next tempo change
            if i < len(tempo_events) - 1:
                next_quarter = tempo_events[i + 1][0]
                duration_quarters = next_quarter - quarter
                seconds_per_quarter = 60.0 / bpm
                current_seconds += duration_quarters * seconds_per_quarter

        # Add a final point to allow extrapolation
        # Extend 4 quarters beyond the last tempo change
        final_quarter = quarter_positions[-1] + 4.0
        seconds_per_quarter = 60.0 / tempo_events[-1][1]
        final_seconds = current_seconds + 4.0 * seconds_per_quarter

        quarter_positions.append(final_quarter)
        second_positions.append(final_seconds)

        return TableMap(
            x_values=quarter_positions,
            y_values=second_positions,
            source_unit="quarters",
            target_unit="seconds",
        )

    def __repr__(self) -> str:
        return (
            f"ScoreBundle(notes={len(self.notes)}, measures={len(self.measures)}, "
            f"controls={len(self.controls)}, annotations={len(self.annotations)})"
        )

    # region Iterator Protocol

    def __iter__(self) -> Iterator[EventStore]:
        """Iterate over stores.

        Yields:
            EventStores in canonical order: notes, measures, controls, annotations.

        Examples:
            >>> for store in bundle:
            ...     timeline = Timeline.from_event_store(store)
        """
        yield self.notes
        yield self.measures
        yield self.controls
        yield self.annotations

    def __len__(self) -> int:
        """Return the number of stores (always 4)."""
        return len(STORE_NAMES)

    def __getitem__(self, name: str) -> EventStore:
        """Get a store by name.

        Args:
            name: Store name (notes, measures, controls, annotations).

        Returns:
            The EventStore for that category.

        Raises:
            KeyError: If name is not a valid store name.

        Examples:
            >>> notes_store = bundle["notes"]
        """
        if name == "notes":
            return self.notes
        elif name == "measures":
            return self.measures
        elif name == "controls":
            return self.controls
        elif name == "annotations":
            return self.annotations
        else:
            raise KeyError(f"Unknown store name: {name!r}. Valid: {STORE_NAMES}")

    def __contains__(self, name: object) -> bool:
        """Check if a store name is valid.

        Args:
            name: Store name to check.

        Returns:
            True if name is a valid store name.
        """
        return name in STORE_NAMES

    def keys(self) -> tuple[str, ...]:
        """Return store names.

        Returns:
            Tuple of store names in canonical order.
        """
        return STORE_NAMES

    def values(self) -> Iterator[EventStore]:
        """Iterate over stores.

        Yields:
            EventStores in canonical order.

        Examples:
            >>> for store in bundle.values():
            ...     print(len(store))
        """
        yield self.notes
        yield self.measures
        yield self.controls
        yield self.annotations

    def items(self) -> Iterator[tuple[str, EventStore]]:
        """Iterate over (name, store) pairs.

        Yields:
            Tuples of (name, EventStore) in canonical order.

        Examples:
            >>> for name, store in bundle.items():
            ...     timeline = Timeline.from_event_store(store, uid=name)
        """
        yield ("notes", self.notes)
        yield ("measures", self.measures)
        yield ("controls", self.controls)
        yield ("annotations", self.annotations)

    # endregion
