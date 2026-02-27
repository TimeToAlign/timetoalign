"""ControlEventData: Storage for control events (dynamics, tempo, etc.)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pyarrow as pa
from typing_extensions import Self

from timetoalign.core import NumberType, TimeUnit
from timetoalign.loader.schema import make_fraction_field
from timetoalign.loader.store import EventData

if TYPE_CHECKING:
    pass


class ControlEventData(EventData):
    """EventData for control events.

    Subtypes include:
    - Dynamic: velocity/dynamics markings (pp, ff, mf)
    - Tempo: tempo changes (MetronomeMark, TempoIndication)
    - Pedal: sustain/soft pedal events
    - OctaveShift: 8va/8vb markings
    - Wedge: crescendo/decrescendo hairpins

    Schema:
    - quarterbeats: Event position (Fraction)
    - duration_qb: Event duration if applicable (Fraction)
    - subtype: Control category (Dynamic, Tempo, Pedal, etc.)
    - value: Numeric value (BPM, velocity level)
    - text: Textual representation
    """

    _extra_fields: ClassVar[list[pa.Field]] = [
        # Temporal - Derived/Float
        pa.field("duration_float", pa.float64(), nullable=True),
        # Measure context
        pa.field("mc", pa.int64(), nullable=True, metadata={"number_type": "int64"}),
        pa.field("mn", pa.string(), nullable=True),
        make_fraction_field("mc_onset", nullable=True),
        make_fraction_field("mn_onset", nullable=True),
        # Control specifics
        pa.field("subtype", pa.string(), nullable=False),  # Dynamic, Tempo, Pedal, etc.
        pa.field("value", pa.float64(), nullable=True),  # BPM, velocity, etc.
        pa.field("text", pa.string(), nullable=True),  # "ff", "Allegro", etc.
        # Context
        pa.field("voice", pa.int64(), nullable=True),
        pa.field("staff", pa.int64(), nullable=True),
        pa.field("part_id", pa.string(), nullable=True),
    ]

    @classmethod
    def empty(
        cls,
        unit: TimeUnit = TimeUnit.quarters,
        number_type: NumberType = NumberType.fraction,
    ) -> Self:
        """Create empty ControlEventData."""
        return super().empty(unit, number_type)

    @classmethod
    def from_dicts(
        cls,
        rows: list[dict[str, Any]],
        unit: TimeUnit = TimeUnit.quarters,
        number_type: NumberType = NumberType.fraction,
    ) -> Self:
        """Create from dicts."""
        if not rows:
            return cls.empty(unit, number_type)

        from timetoalign.loader.schema import make_table_metadata

        schema = cls.get_schema(unit)
        metadata = make_table_metadata(unit, number_type, loader_class=cls.__name__)
        schema = schema.with_metadata(metadata)

        from fractions import Fraction

        from timetoalign.loader.schema import coordinate_to_struct

        processed_rows = []
        type_counters: dict[str, int] = {}
        for row in rows:
            processed = dict(row)

            # Auto-generate id if missing (mirrors EventData.from_dicts logic)
            if "id" not in processed or processed["id"] is None:
                etype = str(processed.get("event_type", "event")).lower()
                type_counters.setdefault(etype, 0)
                type_counters[etype] += 1
                processed["id"] = f"{etype}:{type_counters[etype]:06d}"

            # Infer temporal_type if missing
            if "temporal_type" not in processed or processed["temporal_type"] is None:
                has_end = processed.get("end") is not None
                has_duration = (
                    processed.get("duration") is not None
                    or processed.get("duration_qb") is not None
                )
                has_start = (
                    processed.get("start") is not None
                    or processed.get("quarterbeats") is not None
                )
                if has_start and (has_end or has_duration):
                    processed["temporal_type"] = "interval"
                else:
                    processed["temporal_type"] = "instant"

            # Ensure name column exists
            if "name" not in processed:
                processed["name"] = None

            # Map legacy temporal columns to base
            if "quarterbeats" in processed:
                processed["start"] = processed.pop("quarterbeats")
            if "duration_qb" in processed:
                processed["duration"] = processed.pop("duration_qb")
            if "duration_qb_float" in processed:
                processed["duration_float"] = processed.pop("duration_qb_float")

            # Remove unused
            processed.pop("quarterbeats_float", None)

            # Convert temporal columns to coordinate struct format.
            for col in ["start", "duration"]:
                val = processed.get(col)
                if val is not None:
                    if isinstance(val, dict):
                        if "num" in val and "value" not in val:
                            frac = Fraction(val["num"], val["den"])
                            processed[col] = coordinate_to_struct(frac)
                    else:
                        processed[col] = coordinate_to_struct(val)

            # Base columns need defaults
            for col in ["start", "end", "duration"]:
                if col not in processed:
                    processed[col] = None
            processed_rows.append(processed)

        table = pa.Table.from_pylist(processed_rows, schema=schema)
        return cls(table, unit, number_type)
