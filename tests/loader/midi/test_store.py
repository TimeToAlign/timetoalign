"""Tests for MidiEventStore."""

from timetoalign.core import TimeUnit
from timetoalign.loader.midi import MidiEventStore


class TestMidiEventStore:
    """Tests for MidiEventStore schema and functionality."""

    def test_schema_fields(self) -> None:
        """Schema should include MIDI-specific fields."""
        schema = MidiEventStore.schema(TimeUnit.ticks)
        names = schema.names

        # Base fields
        assert "id" in names
        assert "start" in names

        # MIDI fields
        assert "pitch" in names
        assert "velocity" in names
        assert "channel" in names
        assert "track" in names
        assert "control" in names
        assert "program" in names

        # Score fields
        assert "voice" in names
        assert "staff" in names
        assert "part_id" in names

    def test_nullable_fields(self) -> None:
        """Extra fields should be nullable."""
        schema = MidiEventStore.schema(TimeUnit.ticks)

        assert schema.field("voice").nullable
        assert schema.field("control").nullable
        assert schema.field("pitch").nullable

    def test_creation_from_dicts(self) -> None:
        """Can create store from dicts with MIDI fields."""
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
        store = MidiEventStore.from_dicts(events, TimeUnit.ticks)

        assert len(store) == 1
        table = store.table
        assert table.column("pitch")[0].as_py() == 60
        assert table.column("voice")[0].as_py() is None  # Missing field is None
