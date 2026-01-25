"""ScoreBundle: Container for category-specific EventStores."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from timetoalign.loader.score.stores.annotation import AnnotationEventStore
from timetoalign.loader.score.stores.control import ControlEventStore
from timetoalign.loader.score.stores.measure import MeasureEventStore
from timetoalign.loader.score.stores.note import NoteEventStore


@dataclass
class ScoreBundle:
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
