"""Tests for ``MidiEventData`` and ``ScoreMidiEventData``."""

from timetoalign.core import TimeUnit
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
        assert table.column("pitch")[0].as_py() == 60


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
        assert table.column("pitch")[0].as_py() == 60
        assert table.column("voice")[0].as_py() == 1
        assert table.column("staff")[0].as_py() == 1
        assert table.column("part_id")[0].as_py() == "p0"

    def test_subclass_relationship(self) -> None:
        """``ScoreMidiEventData`` must remain a subclass of ``MidiEventData``."""
        assert issubclass(ScoreMidiEventData, MidiEventData)
