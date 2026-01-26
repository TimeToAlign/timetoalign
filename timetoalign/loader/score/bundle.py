"""ScoreBundle: Container for category-specific EventStores."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from timetoalign.loader.bundle import EventBundle
from timetoalign.loader.score.stores.annotations import AnnotationEventStore
from timetoalign.loader.score.stores.controls import ControlEventStore
from timetoalign.loader.score.stores.measures import MeasureEventStore
from timetoalign.loader.score.stores.notes import NoteEventStore
from timetoalign.loader.store import EventStore

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
