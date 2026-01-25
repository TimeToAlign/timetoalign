"""AnnotationEventStore: Storage for text annotations and directions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pyarrow as pa
from typing_extensions import Self

from timetoalign.core import NumberType, TimeUnit
from timetoalign.loader.schema import make_fraction_field
from timetoalign.loader.store import EventStore

if TYPE_CHECKING:
    pass


class AnnotationEventStore(EventStore):
    """EventStore for text annotations.

    Subtypes include:
    - TextBox: Free text annotations
    - TextExpression: Expression text (Allegro con brio)
    - Rehearsal: Rehearsal marks (A, B, etc.)
    - Direction: Performance directions

    Schema:
    - quarterbeats: Annotation position (Fraction)
    - text: Annotation content
    - subtype: Annotation category
    """

    _extra_fields: ClassVar[list[pa.Field]] = [
        # Temporal - Derived/Float
        pa.field("duration_float", pa.float64(), nullable=True),
        # Measure context
        pa.field("mc", pa.int64(), nullable=True, metadata={"number_type": "int64"}),
        pa.field("mn", pa.string(), nullable=True),
        make_fraction_field("mc_onset", nullable=True),
        make_fraction_field("mn_onset", nullable=True),
        # Annotation specifics
        pa.field("subtype", pa.string(), nullable=True),  # TextBox, Rehearsal, etc.
        pa.field("text", pa.string(), nullable=False),
        # Context
        pa.field("staff", pa.int64(), nullable=True),
        pa.field("part_id", pa.string(), nullable=True),
    ]

    @classmethod
    def empty(
        cls,
        unit: TimeUnit = TimeUnit.quarters,
        number_type: NumberType = NumberType.float,
    ) -> Self:
        """Create empty AnnotationEventStore."""
        return super().empty(unit, number_type)

    @classmethod
    def from_dicts(
        cls,
        rows: list[dict[str, Any]],
        unit: TimeUnit = TimeUnit.quarters,
        number_type: NumberType = NumberType.float,
    ) -> Self:
        """Create from dicts."""
        if not rows:
            return cls.empty(unit, number_type)

        from timetoalign.loader.schema import make_table_metadata

        schema = cls.schema(unit)
        metadata = make_table_metadata(unit, number_type, loader_class=cls.__name__)
        schema = schema.with_metadata(metadata)

        processed_rows = []
        for row in rows:
            processed = dict(row)

            # Map legacy temporal columns to base
            if "quarterbeats" in processed:
                processed["start"] = processed.pop("quarterbeats")
            if "duration_qb" in processed:
                processed["duration"] = processed.pop("duration_qb")
            if "duration_qb_float" in processed:
                processed["duration_float"] = processed.pop("duration_qb_float")

            # Remove unused
            processed.pop("quarterbeats_float", None)

            # Base columns need defaults
            for col in ["start", "end", "duration"]:
                if col not in processed:
                    processed[col] = None
            processed_rows.append(processed)

        table = pa.Table.from_pylist(processed_rows, schema=schema)
        return cls(table, unit, number_type)
