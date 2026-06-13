"""Tests for ``MidiEventData`` and ``ScoreMidiEventData``."""

import pyarrow as pa

from timetoalign.core import TimeUnit
from timetoalign.core.events import EnharmonicPitch, EnharmonicPitchField
from timetoalign.loader.midi import MidiEventData, ScoreMidiEventData

# Canonical extra-column sets used by both EventData classes.  Pin
# membership exactly — the split is a contract, not a suggestion.
PERFORMANCE_EXTRA_COLUMNS = {
    "pitch",
    "velocity",
    "channel",
    "track",
    "control",
    "value",
    "program",
}
SCORE_ONLY_EXTRA_COLUMNS = {"voice", "staff", "part_id"}


class TestMidiEventData:
    """Tests for ``MidiEventData`` schema (narrower performance-MIDI shape)."""

    def test_schema_fields(self) -> None:
        """Schema includes the seven cross-loader MIDI columns, no score-only."""
        schema = MidiEventData.get_schema(TimeUnit.ticks)
        names = set(schema.names)

        # Base columns survive
        assert "id" in names
        assert "start" in names

        # All seven cross-loader columns are present
        assert PERFORMANCE_EXTRA_COLUMNS.issubset(names)

        # The three score-only columns must NOT be present on
        # ``MidiEventData`` — they live on ``ScoreMidiEventData`` only.
        assert SCORE_ONLY_EXTRA_COLUMNS.isdisjoint(names)

    def test_nullable_fields(self) -> None:
        """Extra fields should be nullable."""
        schema = MidiEventData.get_schema(TimeUnit.ticks)

        assert schema.field("pitch").nullable
        assert schema.field("velocity").nullable
        assert schema.field("control").nullable

    def test_creation_from_dicts(self) -> None:
        """Can create data from dicts with MIDI fields."""
        events = [
            {
                "id": "n1",
                "temporal_type": "interval",
                "event_type": "Note",
                "start": 0,
                "end": 480,
                "pitch": 60,
                "velocity": 100,
                "channel": 1,
            }
        ]
        data = MidiEventData.from_dicts(events, TimeUnit.ticks)

        assert len(data) == 1
        table = data.table
        # ``pitch`` is the materialised EnharmonicPitch struct.
        assert table.column("pitch").type == pa.struct(
            [pa.field("midi_number", pa.int64())]
        )
        assert table.column("pitch")[0]["midi_number"].as_py() == 60

    def test_pitch_column_affords_enharmonic_pitch(self) -> None:
        """The pitch struct column affords the ``EnharmonicPitch`` view."""
        events = [
            {
                "id": "n1",
                "event_type": "Note",
                "start": 0,
                "end": 480,
                "pitch": 60,
                "velocity": 100,
            }
        ]
        data = MidiEventData.from_dicts(events, TimeUnit.ticks)

        field = data.get_field(EnharmonicPitch)
        assert isinstance(field, EnharmonicPitchField)
        assert field[0] == EnharmonicPitch(midi_number=60)
        # And via the priority-based pitch accessor.
        assert data.get_pitch_field()[0].midi_number == 60

    def test_control_change_carries_null_pitch(self) -> None:
        """Control Change events have no pitch (null struct slot)."""
        events = [
            {
                "id": "cc1",
                "event_type": "ControlChange",
                "instant": 0,
                "pitch": None,
                "control": 64,
                "value": 127,
            }
        ]
        data = MidiEventData.from_dicts(events, TimeUnit.ticks)
        assert data.table.column("pitch")[0].as_py() is None


class TestScoreMidiEventData:
    """Tests for ``ScoreMidiEventData`` schema (wider score-MIDI shape)."""

    def test_schema_fields(self) -> None:
        """Schema includes the cross-loader seven plus the three score-only columns."""
        schema = ScoreMidiEventData.get_schema(TimeUnit.ticks)
        names = set(schema.names)

        # Base columns survive
        assert "id" in names
        assert "start" in names

        # Both column sets are present on the wider schema
        assert PERFORMANCE_EXTRA_COLUMNS.issubset(names)
        assert SCORE_ONLY_EXTRA_COLUMNS.issubset(names)

    def test_nullable_score_only_fields(self) -> None:
        """The score-only columns are nullable (partitura may not supply them)."""
        schema = ScoreMidiEventData.get_schema(TimeUnit.ticks)

        for name in SCORE_ONLY_EXTRA_COLUMNS:
            assert schema.field(name).nullable, f"{name} must be nullable"

    def test_creation_from_dicts_with_score_fields(self) -> None:
        """Can create data from dicts that include the score-only columns."""
        events = [
            {
                "id": "n1",
                "temporal_type": "interval",
                "event_type": "Note",
                "start": 0,
                "end": 480,
                "pitch": 60,
                "velocity": 64,
                "voice": 1,
                "staff": 1,
                "part_id": "p0",
            }
        ]
        data = ScoreMidiEventData.from_dicts(events, TimeUnit.ticks)

        assert len(data) == 1
        table = data.table
        assert table.column("pitch")[0]["midi_number"].as_py() == 60
        assert table.column("voice")[0].as_py() == 1
        assert table.column("staff")[0].as_py() == 1
        assert table.column("part_id")[0].as_py() == "p0"
        # The wider score store affords the EnharmonicPitch view too.
        assert data.get_field(EnharmonicPitch)[0] == EnharmonicPitch(midi_number=60)

    def test_subclass_relationship(self) -> None:
        """``ScoreMidiEventData`` must remain a subclass of ``MidiEventData``."""
        assert issubclass(ScoreMidiEventData, MidiEventData)
