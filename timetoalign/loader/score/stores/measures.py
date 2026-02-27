"""MeasureData: Storage for measure boundary events.

This module provides the MeasureData class which stores measure information
from both MeasureMap JSON files and measures.tsv files. The schema is designed
to support:

1. **MeasureMap JSON format** (from measure_map paper):
   - ID, count, qstamp, number, name, time_signature, nominal_length, actual_length
   - start_repeat, end_repeat, next (flow control)

2. **measures.tsv format** (ms3/DCML):
   - mc, mn, quarterbeats, duration_qb, timesig, keysig
   - mc_offset, volta, repeats, breaks, next (flow control)

The unified schema allows cross-validation between loaders and enables
derivation of flow-aware maps (MetricMap, MeasureNumberMap, etc.).

Key concepts (from MeasureMap paper):
- **MC (Measure Count)**: Monotonically increasing integer (1-indexed), unique
- **MN (Measure Number)**: Conventional label musicians see (may repeat, have suffixes)
- **Split bars**: Same MN for multiple MCs (e.g., bar split by repeat sign)
- **Anacrusis**: Incomplete first measure, typically MN=0
- **Volta**: Alternative endings (prima/seconda volta)
"""

from __future__ import annotations

import logging
from fractions import Fraction
from typing import TYPE_CHECKING, Any, ClassVar

import pyarrow as pa
from typing_extensions import Self

from timetoalign.core import NumberType, TimeUnit
from timetoalign.loader.store import EventData

if TYPE_CHECKING:
    pass

module_logger = logging.getLogger(__name__)


class MeasureData(EventData):
    """EventData for measure boundary events.

    This schema supports both MeasureMap JSON and measures.tsv formats,
    enabling cross-validation and unified measure handling.

    Core Fields (Identity):
        mc: Measure Count - monotonically increasing integer (1-indexed)
        mn: Measure Number label - string like "1", "0", "19a", "19b"
        mn_int: Measure Number as integer (for sorting/grouping)

    Temporal Fields:
        quarterbeats / start: Measure start in continuous logical time
        duration / duration_qb: Measure length in quarter beats
        nominal_length: Expected duration from time signature
        actual_length: Real duration (may differ for anacrusis, irregular bars)
        mc_offset: Offset within split bar (e.g., Fraction(1/4) for second half)

    Signature Fields:
        timesig: Time signature string ("2/4", "4/4", "6/8")
        timesig_num, timesig_den: Numerator and denominator
        keysig: Key signature string
        keysig_fifths: Circle of fifths position (-7 to 7)

    Flow Control Fields:
        start_repeat: True if this bar has a repeat start marker (||:)
        end_repeat: True if this bar has a repeat end marker (:||)
        next: Comma-separated list of MCs that can follow this bar
        volta: Ending number (1, 2, ...) or null
        repeats: Legacy field ("start", "end", "firstMeasure")
        breaks: Section boundary marker ("section", etc.)
        dont_count: If true, skip in MN counting

    Context Fields:
        barline: Barline type ("double", etc.)
        part_id: Part identifier for multi-part scores
    """

    _extra_fields: ClassVar[list[pa.Field]] = [
        # ===== Core Identity =====
        pa.field(
            "mc",
            pa.int64(),
            nullable=False,
            metadata={"description": "Measure Count (monotonic, 1-indexed)"},
        ),
        pa.field(
            "mn",
            pa.string(),
            nullable=True,
            metadata={"description": "Measure Number label (may have suffix)"},
        ),
        pa.field(
            "mn_int",
            pa.int64(),
            nullable=True,
            metadata={"description": "Measure Number as integer"},
        ),
        pa.field(
            "mm_id",
            pa.string(),
            nullable=True,
            metadata={"description": "MeasureMap ID (string of count)"},
        ),
        # ===== Temporal - Derived/Explicit =====
        pa.field("duration_float", pa.float64(), nullable=True),
        pa.field(
            "nominal_length",
            pa.float64(),
            nullable=True,
            metadata={"description": "Expected duration from timesig"},
        ),
        pa.field(
            "actual_length",
            pa.float64(),
            nullable=True,
            metadata={"description": "Real duration (may differ)"},
        ),
        pa.field(
            "mc_offset",
            pa.string(),
            nullable=True,
            metadata={"description": "Offset in split bar as fraction string"},
        ),
        pa.field(
            "quarterbeats_all_endings",
            pa.string(),
            nullable=True,
            metadata={"description": "Alt qstamp including all endings"},
        ),
        # ===== Signatures =====
        pa.field("timesig", pa.string(), nullable=True),
        pa.field("timesig_num", pa.int64(), nullable=True),
        pa.field("timesig_den", pa.int64(), nullable=True),
        pa.field("keysig", pa.string(), nullable=True),
        pa.field("keysig_fifths", pa.int64(), nullable=True),
        pa.field("keysig_mode", pa.string(), nullable=True),  # "major", "minor"
        # ===== Flow Control =====
        pa.field(
            "start_repeat",
            pa.bool_(),
            nullable=True,
            metadata={"description": "Repeat start marker (||:)"},
        ),
        pa.field(
            "end_repeat",
            pa.bool_(),
            nullable=True,
            metadata={"description": "Repeat end marker (:||)"},
        ),
        pa.field(
            "next",
            pa.string(),
            nullable=True,
            metadata={"description": "Comma-separated list of possible next MCs"},
        ),
        pa.field(
            "volta",
            pa.int64(),
            nullable=True,
            metadata={"description": "Ending number (1, 2, ...)"},
        ),
        pa.field(
            "repeats",
            pa.string(),
            nullable=True,
            metadata={"description": "Legacy: start/end/firstMeasure"},
        ),
        pa.field(
            "breaks",
            pa.string(),
            nullable=True,
            metadata={"description": "Section boundary marker"},
        ),
        pa.field(
            "dont_count",
            pa.bool_(),
            nullable=True,
            metadata={"description": "Skip in MN counting"},
        ),
        pa.field("numbering_offset", pa.int64(), nullable=True),
        # ===== Context =====
        pa.field("barline", pa.string(), nullable=True),
        pa.field("part_id", pa.string(), nullable=True),
    ]

    @classmethod
    def empty(
        cls,
        unit: TimeUnit = TimeUnit.quarters,
        number_type: NumberType = NumberType.fraction,
    ) -> Self:
        """Create empty MeasureData."""
        return super().empty(unit, number_type)

    @classmethod
    def from_dicts(
        cls,
        rows: list[dict[str, Any]],
        unit: TimeUnit = TimeUnit.quarters,
        number_type: NumberType = NumberType.fraction,
    ) -> Self:
        """Create from dicts.

        Handles field mapping from both MeasureMap JSON and measures.tsv formats.

        Args:
            rows: List of measure dictionaries.
            unit: Time unit (default: quarters).
            number_type: Number type for coordinates.

        Returns:
            MeasureData instance.
        """
        if not rows:
            return cls.empty(unit, number_type)

        from timetoalign.loader.schema import coordinate_to_struct, make_table_metadata

        schema = cls.get_schema(unit)
        metadata = make_table_metadata(unit, number_type, loader_class=cls.__name__)
        schema = schema.with_metadata(metadata)

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
                    or processed.get("qstamp") is not None
                )
                if has_start and (has_end or has_duration):
                    processed["temporal_type"] = "interval"
                else:
                    processed["temporal_type"] = "instant"

            # ===== Map MeasureMap JSON fields to schema =====
            # MeasureMap uses "count" for MC, "number" for MN as int
            if "count" in processed and "mc" not in processed:
                processed["mc"] = processed.pop("count")
            if "number" in processed:
                processed["mn_int"] = processed.pop("number")
            if "name" in processed and "mn" not in processed:
                processed["mn"] = processed.get("name")  # Keep name, also set mn
            if "ID" in processed:
                processed["mm_id"] = processed.pop("ID")
            if "qstamp" in processed and "start" not in processed:
                processed["start"] = processed.pop("qstamp")
            if "time_signature" in processed and "timesig" not in processed:
                processed["timesig"] = processed.pop("time_signature")

            # ===== Map measures.tsv fields to schema =====
            if "quarterbeats" in processed and "start" not in processed:
                processed["start"] = processed.pop("quarterbeats")
            if "duration_qb" in processed and "duration" not in processed:
                processed["duration"] = processed.pop("duration_qb")
            if "duration_qb_float" in processed:
                processed["duration_float"] = processed.pop("duration_qb_float")
            if "act_dur" in processed and "actual_length" not in processed:
                # act_dur is typically a fraction string like "1/2"
                processed["actual_length"] = processed.pop("act_dur")

            # ===== Handle 'next' field (array in JSON, string in TSV) =====
            if "next" in processed:
                next_val = processed["next"]
                if isinstance(next_val, list):
                    # Convert array to comma-separated string
                    processed["next"] = ", ".join(str(x) for x in next_val)
                # else: already a string from TSV

            # ===== Parse timesig into components =====
            if "timesig" in processed and processed["timesig"]:
                ts = str(processed["timesig"])
                if "/" in ts:
                    parts = ts.split("/")
                    try:
                        processed.setdefault("timesig_num", int(parts[0]))
                        processed.setdefault("timesig_den", int(parts[1]))
                    except (ValueError, IndexError):
                        pass

            # ===== Compute nominal_length from timesig if not provided =====
            if processed.get("timesig_num") and processed.get("timesig_den"):
                if (
                    "nominal_length" not in processed
                    or processed["nominal_length"] is None
                ):
                    # quarters_per_measure = (timesig_num / timesig_den) * 4
                    # e.g., 2/4 = 2 quarters, 6/8 = 3 quarters
                    processed["nominal_length"] = (
                        processed["timesig_num"] / processed["timesig_den"] * 4
                    )

            # Remove unused legacy fields
            processed.pop("quarterbeats_float", None)
            # Keep 'name' field - it's part of the base schema and should be preserved
            # (e.g., "M1", "M2" for measure labels)

            # ===== Convert temporal columns to struct format =====
            # The schema expects coordinate structs ({value, numerator,
            # denominator}).  Loaders may pass fraction-format dicts
            # ({num, den}) via fraction_to_struct(), raw Fraction/float
            # values, or coordinate-format dicts (already correct).
            for coord_col in ["start", "end", "duration"]:
                if coord_col in processed and processed[coord_col] is not None:
                    val = processed[coord_col]
                    if isinstance(val, dict):
                        if "num" in val and "value" not in val:
                            # fraction_to_struct format -> coordinate format
                            frac = Fraction(val["num"], val["den"])
                            processed[coord_col] = coordinate_to_struct(frac)
                        # else: already coordinate struct format
                    else:
                        processed[coord_col] = coordinate_to_struct(val)
                else:
                    processed[coord_col] = None

            # Compute 'end' from start + duration when not explicitly set.
            if processed.get("end") is None:
                s = processed.get("start")
                d = processed.get("duration")
                if (
                    s is not None
                    and d is not None
                    and isinstance(s, dict)
                    and isinstance(d, dict)
                    and s.get("value") is not None
                    and d.get("value") is not None
                ):
                    end_val = s["value"] + d["value"]
                    end_num = None
                    end_den = None
                    if (
                        s.get("numerator") is not None
                        and d.get("numerator") is not None
                    ):
                        s_frac = Fraction(s["numerator"], s["denominator"])
                        d_frac = Fraction(d["numerator"], d["denominator"])
                        e_frac = s_frac + d_frac
                        end_num = e_frac.numerator
                        end_den = e_frac.denominator
                    processed["end"] = {
                        "value": end_val,
                        "numerator": end_num,
                        "denominator": end_den,
                    }

            processed_rows.append(processed)

        table = pa.Table.from_pylist(processed_rows, schema=schema)
        return cls(table, unit, number_type)

    # ===== Flow Control Helpers =====

    def get_flow_control_summary(self) -> dict[str, Any]:
        """Get summary of flow control elements in this measure data.

        Returns:
            Dict with counts of repeats, voltas, breaks, etc.
        """
        summary: dict[str, Any] = {
            "total_measures": len(self),
            "has_repeats": False,
            "has_voltas": False,
            "has_breaks": False,
            "repeat_starts": 0,
            "repeat_ends": 0,
            "voltas": set(),
            "breaks": set(),
        }

        if len(self) == 0:
            return summary

        # Count repeat starts
        if "start_repeat" in self._table.column_names:
            start_col = self._table.column("start_repeat")
            true_count = sum(1 for v in start_col.to_pylist() if v is True)
            summary["repeat_starts"] = true_count
            summary["has_repeats"] = true_count > 0

        # Count repeat ends
        if "end_repeat" in self._table.column_names:
            end_col = self._table.column("end_repeat")
            true_count = sum(1 for v in end_col.to_pylist() if v is True)
            summary["repeat_ends"] = true_count
            summary["has_repeats"] = summary["has_repeats"] or true_count > 0

        # Count voltas
        if "volta" in self._table.column_names:
            volta_col = self._table.column("volta")
            unique_voltas = set(volta_col.to_pylist())
            summary["voltas"] = {v for v in unique_voltas if v is not None}
            summary["has_voltas"] = len(summary["voltas"]) > 0

        # Count breaks
        if "breaks" in self._table.column_names:
            breaks_col = self._table.column("breaks")
            unique_breaks = set(breaks_col.to_pylist())
            summary["breaks"] = {b for b in unique_breaks if b is not None}
            summary["has_breaks"] = len(summary["breaks"]) > 0

        return summary

    def has_flow_control(self) -> bool:
        """Check if this measure data contains any flow control elements."""
        summary = self.get_flow_control_summary()
        return summary["has_repeats"] or summary["has_voltas"] or summary["has_breaks"]
