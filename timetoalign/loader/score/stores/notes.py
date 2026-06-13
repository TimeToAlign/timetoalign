"""NoteEventData: Storage for note/rest/chord events."""

from __future__ import annotations

from typing import Any, ClassVar

import pyarrow as pa
from typing_extensions import Self

from timetoalign.core import IntervalPolicy, NumberType, TimeUnit
from timetoalign.core.events import EnharmonicPitchField, SpecificPitchField
from timetoalign.loader.events import EventData
from timetoalign.loader.schema import make_fraction_field


class NoteEventData(EventData):
    """EventData for note, rest, and chord events.

    Rich temporal schema following TSV gold standard:
    - start: Continuous logical time (Fraction) - from 'quarterbeats'
    - duration: Duration (Fraction) - from 'duration_qb'
    - mc/mn: Measure context
    - mc_onset/mn_onset: Measure-relative offsets (Fraction)

    Pitch fields (canonical pydantic-derived struct shapes):
    - midi_pitch: {midi_number}                  (EnharmonicPitchField)
    - specific_pitch: {step, alter, octave, cents} (SpecificPitchField)
    - tpc: Tonal Pitch Class (fifths)
    - octave: Octave number
    """

    _extra_fields: ClassVar[list[pa.Field]] = [
        # Temporal - Measure context
        pa.field("mc", pa.int64(), nullable=True, metadata={"number_type": "int64"}),
        pa.field("mn", pa.string(), nullable=True),
        make_fraction_field("mc_onset", nullable=True),
        make_fraction_field("mn_onset", nullable=True),
        # Pitch struct fields — schemas derived from the paired Fields'
        # pydantic models (see core/events.py).
        pa.field("midi_pitch", EnharmonicPitchField.pa_schema, nullable=True),
        pa.field("specific_pitch", SpecificPitchField.pa_schema, nullable=True),
        pa.field(
            "tpc",
            pa.int64(),
            nullable=True,
            metadata={"number_type": "int64", "unit": "fifths"},
        ),
        pa.field(
            "octave", pa.int64(), nullable=True, metadata={"number_type": "int64"}
        ),
        # Attributes
        pa.field("tied", pa.int64(), nullable=True),  # -1=end, 0=none, 1=start
        pa.field("gracenote", pa.string(), nullable=True),
        pa.field("chord_id", pa.int64(), nullable=True),
        # Context
        pa.field("voice", pa.int64(), nullable=True, metadata={"number_type": "int64"}),
        pa.field("staff", pa.int64(), nullable=True, metadata={"number_type": "int64"}),
        pa.field("part_id", pa.string(), nullable=True),
    ]

    def __init__(
        self,
        table: pa.Table,
        unit: TimeUnit,
        number_type: NumberType = NumberType.float,
        has_rests: bool = False,
    ) -> None:
        """Initialize NoteEventData.

        Args:
            table: PyArrow table.
            unit: Time unit.
            number_type: Number type.
            has_rests: Whether the source explicitly includes rests.
        """
        super().__init__(table, unit, number_type)
        self._has_rests = has_rests

    @property
    def has_rests(self) -> bool:
        """Return whether the store explicitly contains rests."""
        return self._has_rests

    @property
    def enharmonic_pitch_field(self) -> EnharmonicPitchField:
        """Extract the ``midi_pitch`` field as an ``EnharmonicPitchField``.

        Returns:
            An ``EnharmonicPitchField`` wrapping the ``midi_pitch`` field.

        Raises:
            KeyError: If the table has no ``midi_pitch`` field.
        """
        try:
            result = self.get_pitch_field(EnharmonicPitchField)
            if isinstance(result, EnharmonicPitchField):
                return result
        except KeyError:
            pass

        col = self._table.column("midi_pitch")
        pa_field = self._table.schema.field("midi_pitch")
        return EnharmonicPitchField.from_field((col, pa_field))

    # Backward-compat alias
    pitch_field = enharmonic_pitch_field

    @property
    def specific_pitch_field(self) -> SpecificPitchField:
        """Extract the ``specific_pitch`` field as a ``SpecificPitchField``.

        Returns:
            A ``SpecificPitchField`` wrapping the ``specific_pitch`` field.

        Raises:
            KeyError: If the table has no ``specific_pitch`` field.
        """
        try:
            result = self.get_pitch_field(SpecificPitchField)
            if isinstance(result, SpecificPitchField):
                return result
        except KeyError:
            pass

        col = self._table.column("specific_pitch")
        pa_field = self._table.schema.field("specific_pitch")
        return SpecificPitchField.from_field((col, pa_field))

    @classmethod
    def empty(
        cls,
        unit: TimeUnit = TimeUnit.quarters,
        number_type: NumberType = NumberType.fraction,
        has_rests: bool = False,
    ) -> Self:
        """Create empty NoteEventData."""
        store = super().empty(unit, number_type)
        store._has_rests = has_rests
        return store

    @classmethod
    def from_dicts(
        cls,
        rows: list[dict[str, Any]],
        unit: TimeUnit = TimeUnit.quarters,
        number_type: NumberType = NumberType.fraction,
        has_rests: bool = False,
        *,
        interval_policy: IntervalPolicy = IntervalPolicy.warn,
    ) -> Self:
        """Create from dicts with has_rests metadata.

        Builds PyArrow table directly using NoteEventData schema.
        """
        if not rows:
            return cls.empty(unit, number_type, has_rests)

        from timetoalign.loader.schema import make_table_metadata

        schema = cls.get_schema(unit)
        metadata = make_table_metadata(unit, number_type, loader_class=cls.__name__)
        schema = schema.with_metadata(metadata)

        # Ensure all required fields exist with proper defaults
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

            # Ensure name field exists
            if "name" not in processed:
                processed["name"] = None

            # Map legacy temporal fields to base
            if "quarterbeats" in processed:
                processed["start"] = processed.pop("quarterbeats")
            if "duration_qb" in processed:
                processed["duration"] = processed.pop("duration_qb")
            # Remove unused/redundant fields
            for k in [
                "quarterbeats_float",
                "duration_qb_float",
                "nominal_duration",
                "scalar",
                "timesig",
                "instant",
            ]:
                processed.pop(k, None)

            # Unified interval normalisation: converts coordinate fields
            # to struct format, fills missing end/duration, and infers
            # temporal_type.  Delegates to the base EventData method.
            EventData._normalize_intervals_row(processed, policy=interval_policy)

            processed_rows.append(processed)

        table = pa.Table.from_pylist(processed_rows, schema=schema)
        store = cls(table, unit, number_type, has_rests)
        return store
