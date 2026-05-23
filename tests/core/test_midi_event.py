"""Round-trip tests for :class:`MidiEvent` and :class:`ScoreMidiEvent`.

Covers the column-builder + pa.Schema contract for the MIDI scalars
and their paired ``SemanticField`` round-trip via ``from_field`` +
``__getitem__``:

* Default-construction of both scalars (all optional, default ``None``).
* Construction with a nested :class:`EnharmonicPitch` and reading
  ``pitch.midi_number`` back.
* ``derive_arrow_schema`` produces exactly the expected sub-fields, in
  declaration order, all nullable; ``pitch`` is itself a one-field
  struct.
* Column-builder + ``from_field`` round-trips three instances exercising
  the three event flavours (note-on, CC, PC) for the base and three
  instances exercising voice / staff / part_id for the subclass.
* The paired Field classes import without raising the
  ``@data_shaped`` parity check (trivially satisfied — neither scalar
  has any ``@data_shaped`` methods).
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from timetoalign.core import (
    EnharmonicPitch,
    MidiEvent,
    MidiEventField,
    ScoreMidiEvent,
    ScoreMidiEventField,
)
from timetoalign.core.fields import (
    TIMETOALIGN_METADATA_KEY,
    build_struct_array,
    derive_arrow_schema,
    parquet_metadata_for_model,
)


class TestMidiEventScalar:
    """Constructor + attribute access on :class:`MidiEvent`."""

    def test_default_constructor_all_none(self) -> None:
        ev = MidiEvent()
        assert ev.pitch is None
        assert ev.velocity is None
        assert ev.channel is None
        assert ev.track is None
        assert ev.control is None
        assert ev.value is None
        assert ev.program is None

    def test_constructor_with_nested_pitch(self) -> None:
        ev = MidiEvent(
            pitch=EnharmonicPitch(midi_number=60),
            velocity=100,
            channel=0,
        )
        assert ev.pitch is not None
        assert ev.pitch.midi_number == 60
        assert ev.velocity == 100
        assert ev.channel == 0
        assert ev.track is None

    def test_repr_lists_non_none_fields_only(self) -> None:
        ev = MidiEvent(control=64, value=127, channel=0, track=0)
        rendered = repr(ev)
        assert rendered == "MidiEvent(channel=0, track=0, control=64, value=127)"

    def test_equality(self) -> None:
        a = MidiEvent(pitch=EnharmonicPitch(midi_number=60), velocity=100)
        b = MidiEvent(pitch=EnharmonicPitch(midi_number=60), velocity=100)
        c = MidiEvent(pitch=EnharmonicPitch(midi_number=61), velocity=100)
        assert a == b
        assert a != c


class TestScoreMidiEventScalar:
    """Constructor + attribute access on :class:`ScoreMidiEvent`."""

    def test_default_constructor_all_none(self) -> None:
        ev = ScoreMidiEvent()
        # Base fields
        assert ev.pitch is None
        assert ev.velocity is None
        # Score-only fields
        assert ev.voice is None
        assert ev.staff is None
        assert ev.part_id is None

    def test_constructor_with_score_metadata(self) -> None:
        ev = ScoreMidiEvent(
            pitch=EnharmonicPitch(midi_number=72),
            velocity=64,
            voice=1,
            staff=2,
            part_id="p0",
        )
        assert ev.pitch is not None
        assert ev.pitch.midi_number == 72
        assert ev.voice == 1
        assert ev.staff == 2
        assert ev.part_id == "p0"

    def test_is_midi_event_subclass(self) -> None:
        assert issubclass(ScoreMidiEvent, MidiEvent)
        assert isinstance(ScoreMidiEvent(), MidiEvent)

    def test_repr_includes_score_fields(self) -> None:
        ev = ScoreMidiEvent(
            pitch=EnharmonicPitch(midi_number=72),
            velocity=64,
            voice=2,
            staff=1,
            part_id="p0",
        )
        rendered = repr(ev)
        assert "voice=2" in rendered
        assert "staff=1" in rendered
        assert "part_id='p0'" in rendered
        assert rendered.startswith("ScoreMidiEvent(")


class TestMidiEventArrowSchema:
    """``derive_arrow_schema`` produces the expected shape."""

    def test_base_has_seven_fields_in_order(self) -> None:
        schema = derive_arrow_schema(MidiEvent)
        assert schema.names == [
            "pitch",
            "velocity",
            "channel",
            "track",
            "control",
            "value",
            "program",
        ]

    def test_base_all_top_level_fields_nullable(self) -> None:
        schema = derive_arrow_schema(MidiEvent)
        for name in schema.names:
            assert schema.field(name).nullable, f"{name} must be nullable"

    def test_base_pitch_is_one_field_struct(self) -> None:
        schema = derive_arrow_schema(MidiEvent)
        pitch_type = schema.field("pitch").type
        assert pa.types.is_struct(pitch_type)
        assert pitch_type.num_fields == 1
        assert pitch_type.field(0).name == "midi_number"
        assert pitch_type.field(0).type == pa.int64()


class TestScoreMidiEventArrowSchema:
    """:class:`ScoreMidiEvent` is a *separate* wider struct, not shared layout."""

    def test_has_ten_fields_in_order(self) -> None:
        schema = derive_arrow_schema(ScoreMidiEvent)
        assert schema.names == [
            "pitch",
            "velocity",
            "channel",
            "track",
            "control",
            "value",
            "program",
            "voice",
            "staff",
            "part_id",
        ]

    def test_first_seven_match_base_shape(self) -> None:
        base = derive_arrow_schema(MidiEvent)
        wide = derive_arrow_schema(ScoreMidiEvent)
        for name in base.names:
            assert wide.field(name).type == base.field(name).type
            assert wide.field(name).nullable == base.field(name).nullable

    def test_score_only_fields_have_correct_types(self) -> None:
        schema = derive_arrow_schema(ScoreMidiEvent)
        assert schema.field("voice").type == pa.int64()
        assert schema.field("voice").nullable
        assert schema.field("staff").type == pa.int64()
        assert schema.field("staff").nullable
        assert schema.field("part_id").type == pa.string()
        assert schema.field("part_id").nullable


class TestMidiEventRoundTrip:
    """Column-builder + ``from_field`` round-trip on the base scalar."""

    def test_three_event_flavours_round_trip(self) -> None:
        originals = [
            MidiEvent(
                pitch=EnharmonicPitch(midi_number=60),
                velocity=100,
                channel=0,
                track=0,
            ),
            MidiEvent(control=64, value=127, channel=0, track=0),
            MidiEvent(program=1, channel=0, track=0),
        ]
        arr = build_struct_array(MidiEvent, originals)
        pa_field = pa.field(
            "midi_event",
            arr.type,
            nullable=True,
            metadata=parquet_metadata_for_model(MidiEvent),
        )
        field = MidiEventField.from_field((arr, pa_field))
        for i, original in enumerate(originals):
            assert field[i] == original

    def test_parquet_round_trip_preserves_metadata(self, tmp_path: Path) -> None:
        originals = [
            MidiEvent(pitch=EnharmonicPitch(midi_number=60), velocity=100),
            MidiEvent(control=7, value=64),
        ]
        arr = build_struct_array(MidiEvent, originals)
        meta = parquet_metadata_for_model(MidiEvent)
        pa_field = pa.field("midi_event", arr.type, nullable=True, metadata=meta)
        table = pa.Table.from_arrays([arr], schema=pa.schema([pa_field]))

        out = tmp_path / "midi_event.parquet"
        pq.write_table(table, out)
        read = pq.read_table(out)
        read_field = read.schema.field("midi_event")
        assert read_field.metadata is not None
        assert TIMETOALIGN_METADATA_KEY in read_field.metadata
        assert (
            read_field.metadata[TIMETOALIGN_METADATA_KEY]
            == meta[TIMETOALIGN_METADATA_KEY]
        )

        # And the data still reconstructs row-by-row.
        rows = read.column(0).to_pylist()
        reconstructed = [MidiEvent.from_row(r) for r in rows]
        assert reconstructed == originals


class TestScoreMidiEventRoundTrip:
    """Column-builder + ``from_field`` round-trip on the score-side scalar."""

    def test_three_score_events_round_trip(self) -> None:
        originals = [
            ScoreMidiEvent(
                pitch=EnharmonicPitch(midi_number=60),
                velocity=64,
                track=0,
                voice=1,
                staff=1,
                part_id="p0",
            ),
            ScoreMidiEvent(
                pitch=EnharmonicPitch(midi_number=72),
                velocity=64,
                track=0,
                voice=2,
                staff=2,
                part_id="p1",
            ),
            ScoreMidiEvent(
                pitch=EnharmonicPitch(midi_number=55),
                velocity=64,
                track=0,
                voice=1,
                staff=1,
                part_id="p0",
            ),
        ]
        arr = build_struct_array(ScoreMidiEvent, originals)
        pa_field = pa.field(
            "score_midi_event",
            arr.type,
            nullable=True,
            metadata=parquet_metadata_for_model(ScoreMidiEvent),
        )
        field = ScoreMidiEventField.from_field((arr, pa_field))
        for i, original in enumerate(originals):
            assert field[i] == original


class TestPairedFieldsImport:
    """Both paired Fields must import without raising the parity check.

    The parity check lives in ``SemanticField.__init_subclass__`` and
    fires at class-construction time on any ``@data_shaped`` scalar
    method lacking a Field mirror.  ``MidiEvent`` / ``ScoreMidiEvent``
    expose none, so the check is trivially satisfied.  These tests
    pin that contract.
    """

    def test_midi_event_field_pa_schema_matches_scalar(self) -> None:
        from timetoalign.core.fields import derive_arrow_struct

        assert MidiEventField.scalar_cls is MidiEvent
        assert MidiEventField.pa_schema == derive_arrow_struct(MidiEvent)

    def test_score_midi_event_field_pa_schema_matches_scalar(self) -> None:
        from timetoalign.core.fields import derive_arrow_struct

        assert ScoreMidiEventField.scalar_cls is ScoreMidiEvent
        assert ScoreMidiEventField.pa_schema == derive_arrow_struct(ScoreMidiEvent)
