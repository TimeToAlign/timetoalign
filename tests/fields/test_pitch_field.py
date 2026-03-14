"""Tests for fields/pitch.py -- PitchField construction, access, and serialization."""

from __future__ import annotations

import json

import pyarrow as pa
import pyarrow.parquet as pq

from timetoalign.core.protocols import PitchLike, SemanticTypeLike
from timetoalign.core.scalars.pitch import MidiPitch
from timetoalign.fields.base import StructField
from timetoalign.fields.pitch import PitchField

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MIDI_PITCH_TYPE = pa.struct(
    [
        pa.field("ep", pa.int64(), nullable=True),
        pa.field("epc", pa.int64(), nullable=True),
    ]
)


def _make_pitch_array(
    values: list[dict[str, int | None]] | None = None,
) -> pa.Array:
    """Build a midi_pitch struct array from simple dicts."""
    if values is None:
        values = [
            {"ep": 59, "epc": 11},
            {"ep": 60, "epc": 0},
            {"ep": 64, "epc": 4},
        ]
    return pa.array(values, type=_MIDI_PITCH_TYPE)


# ---------------------------------------------------------------------------
# Protocol Conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """Verify PitchField satisfies PitchLike and SemanticTypeLike."""

    def test_midi_pitch_satisfies_pitchlike(self) -> None:
        """isinstance(MidiPitch(...), PitchLike) is True."""
        p = MidiPitch(midi_number=60, pitch_class=0)
        assert isinstance(p, PitchLike)

    def test_pitch_field_satisfies_semantic_type_like(self) -> None:
        """isinstance(PitchField(...), SemanticTypeLike) is True."""
        arr = _make_pitch_array()
        pf = PitchField.from_field(arr)
        assert isinstance(pf, SemanticTypeLike)

    def test_pitch_field_semantic_type(self) -> None:
        """PitchField.semantic_type == 'MidiPitch'."""
        arr = _make_pitch_array()
        pf = PitchField.from_field(arr)
        assert pf.semantic_type == "MidiPitch"


# ---------------------------------------------------------------------------
# Construction (from_field)
# ---------------------------------------------------------------------------


class TestConstruction:
    """Tests for PitchField.from_field() with various source types."""

    def test_from_pa_array(self) -> None:
        """Construct from pa.Array (struct array)."""
        arr = _make_pitch_array([{"ep": 59, "epc": 11}])
        pf = PitchField.from_field(arr)
        assert len(pf) == 1

    def test_from_struct_field(self) -> None:
        """Construct from an existing StructField."""
        arr = _make_pitch_array()
        pa_field = pa.field("midi_pitch", _MIDI_PITCH_TYPE)
        sf = StructField(arr, pa_field)
        pf = PitchField.from_field(sf)
        assert len(pf) == 3

    def test_from_pa_field_schema_only(self) -> None:
        """Construct from pa.Field (no data), verify is_empty."""
        meta_dict = {"field_type": "PitchField", "pitch_type": "midi"}
        pa_field = pa.field(
            "midi_pitch",
            _MIDI_PITCH_TYPE,
            metadata={b"timetoalign": json.dumps(meta_dict).encode()},
        )
        pf = PitchField.from_field(pa_field)
        assert pf.is_empty is True

    def test_from_tuple(self) -> None:
        """Construct from (pa.Array, pa.Field) tuple."""
        arr = _make_pitch_array([{"ep": 60, "epc": 0}, {"ep": 64, "epc": 4}])
        pa_field = pa.field(
            "midi_pitch",
            _MIDI_PITCH_TYPE,
            metadata={
                b"timetoalign": json.dumps(
                    {"field_type": "PitchField", "pitch_type": "midi"}
                ).encode()
            },
        )
        pf = PitchField.from_field((arr, pa_field))
        assert len(pf) == 2


# ---------------------------------------------------------------------------
# Element Access (__getitem__)
# ---------------------------------------------------------------------------


class TestElementAccess:
    """Tests for PitchField.__getitem__."""

    def test_getitem_returns_midi_pitch(self) -> None:
        """Verify returns MidiPitch instance with correct values."""
        arr = _make_pitch_array([{"ep": 59, "epc": 11}])
        pf = PitchField.from_field(arr)
        pitch = pf[0]
        assert isinstance(pitch, MidiPitch)
        assert pitch.midi_number == 59
        assert pitch.pitch_class == 11

    def test_getitem_multiple_elements(self) -> None:
        """Iterate several elements, verify each."""
        values = [
            {"ep": 59, "epc": 11},
            {"ep": 60, "epc": 0},
            {"ep": 64, "epc": 4},
        ]
        arr = _make_pitch_array(values)
        pf = PitchField.from_field(arr)
        for i, expected in enumerate(values):
            pitch = pf[i]
            assert pitch is not None
            assert pitch.midi_number == expected["ep"]
            assert pitch.pitch_class == expected["epc"]

    def test_getitem_null_returns_none(self) -> None:
        """Verify None for null struct entries."""
        arr = pa.array(
            [{"ep": 60, "epc": 0}, None, {"ep": 64, "epc": 4}],
            type=_MIDI_PITCH_TYPE,
        )
        pf = PitchField.from_field(arr)
        assert pf[0] is not None
        assert pf[1] is None
        assert pf[2] is not None


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    """Tests for PitchField properties."""

    def test_semantic_type_midi_pitch(self) -> None:
        """PitchField.semantic_type == 'MidiPitch'."""
        arr = _make_pitch_array([{"ep": 60, "epc": 0}])
        pf = PitchField.from_field(arr)
        assert pf.semantic_type == "MidiPitch"

    def test_metadata_dict(self) -> None:
        """Verify returns dict with field_type and pitch_type."""
        arr = _make_pitch_array([{"ep": 60, "epc": 0}])
        pf = PitchField.from_field(arr)
        md = pf.metadata_dict()
        assert md["field_type"] == "PitchField"
        assert md["pitch_type"] == "midi"


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    """Tests for PitchField serialization."""

    def test_to_field_injects_metadata(self) -> None:
        """Verify to_field() produces pa.Field with b'timetoalign' JSON blob."""
        arr = _make_pitch_array([{"ep": 60, "epc": 0}])
        pf = PitchField.from_field(arr)
        pa_field = pf.to_field()

        assert isinstance(pa_field, pa.Field)
        raw_meta = pa_field.metadata
        assert b"timetoalign" in raw_meta
        blob = json.loads(raw_meta[b"timetoalign"].decode("utf-8"))
        assert blob["field_type"] == "PitchField"
        assert blob["pitch_type"] == "midi"

    def test_parquet_round_trip(self, tmp_path: object) -> None:
        """Write pa.Table with PitchField column, read back, verify data + metadata."""
        from pathlib import Path

        tmp_dir = Path(str(tmp_path))
        parquet_path = tmp_dir / "pitches.parquet"

        # Build PitchField
        values = [
            {"ep": 59, "epc": 11},
            {"ep": 60, "epc": 0},
            {"ep": 64, "epc": 4},
        ]
        arr = _make_pitch_array(values)
        pf = PitchField.from_field(arr)

        # Build table using the enriched pa.Field
        enriched_field = pf.to_field()
        table = pa.table(
            {"midi_pitch": arr},
            schema=pa.schema([enriched_field.with_name("midi_pitch")]),
        )

        # Write and read back
        pq.write_table(table, str(parquet_path))
        table_back = pq.read_table(str(parquet_path))

        # Reconstruct PitchField from the read-back table
        col = table_back.column("midi_pitch")
        field = table_back.schema.field("midi_pitch")
        pf2 = PitchField.from_field((col, field))

        # Verify metadata survived
        assert pf2.semantic_type == "MidiPitch"

        # Verify data survived
        assert len(pf2) == 3
        for i, expected in enumerate(values):
            pitch = pf2[i]
            assert pitch is not None
            assert pitch.midi_number == expected["ep"]
            assert pitch.pitch_class == expected["epc"]


# ---------------------------------------------------------------------------
# Delegation
# ---------------------------------------------------------------------------


class TestDelegation:
    """Tests for SemanticField delegation to the inner StructField."""

    def test_value_returns_struct_field(self) -> None:
        """Verify .value returns the inner StructField."""
        arr = _make_pitch_array([{"ep": 60, "epc": 0}])
        pf = PitchField.from_field(arr)
        raw = pf.value
        assert isinstance(raw, StructField)

    def test_len_delegation(self) -> None:
        """Verify len() passes through to inner StructField."""
        arr = _make_pitch_array()
        pf = PitchField.from_field(arr)
        assert len(pf) == 3

    def test_is_empty_delegation(self) -> None:
        """Verify is_empty passes through for schema-only field."""
        meta_dict = {"field_type": "PitchField", "pitch_type": "midi"}
        pa_field = pa.field(
            "midi_pitch",
            _MIDI_PITCH_TYPE,
            metadata={b"timetoalign": json.dumps(meta_dict).encode()},
        )
        pf = PitchField.from_field(pa_field)
        assert pf.is_empty is True

    def test_name_delegation(self) -> None:
        """Verify .name passes through to inner StructField."""
        arr = _make_pitch_array([{"ep": 60, "epc": 0}])
        pa_field = pa.field("my_pitch", _MIDI_PITCH_TYPE)
        sf = StructField(arr, pa_field)
        pf = PitchField.from_field(sf)
        assert pf.name == "my_pitch"

    def test_field_names_delegation(self) -> None:
        """Verify .field_names works via __getattr__ delegation."""
        arr = _make_pitch_array([{"ep": 60, "epc": 0}])
        pf = PitchField.from_field(arr)
        assert pf.field_names == ["ep", "epc"]
