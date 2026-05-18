"""Tests for fields/pitch.py -- unified PitchField construction, access, and serialization."""

from __future__ import annotations

import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from timetoalign.core.protocols import PitchLike, SemanticTypeLike
from timetoalign.core.scalars.pitch import (
    EnharmonicPitch,
    EnharmonicPitchClass,
    MidiPitch,
    SpecificPitch,
    SpecificPitchClass,
)
from timetoalign.fields.base import StructField
from timetoalign.fields.pitch import PitchField

# ---------------------------------------------------------------------------
# Struct type constants
# ---------------------------------------------------------------------------

_MIDI_PITCH_TYPE = pa.struct(
    [
        pa.field("ep", pa.int64(), nullable=True),
        pa.field("epc", pa.int64(), nullable=True),
    ]
)

_GENERIC_PITCH_TYPE = pa.struct(
    [
        pa.field("pitch_class", pa.int64(), nullable=True),
    ]
)

_specific_pitch_CLASS_TYPE = pa.struct(
    [
        pa.field("gpc_str", pa.string(), nullable=True),
        pa.field("acc", pa.int64(), nullable=True),
        pa.field("spc_int", pa.int64(), nullable=True),
    ]
)

_specific_pitch_TYPE = pa.struct(
    [
        pa.field("gpc_int", pa.int64()),
        pa.field("gpc_str", pa.string()),
        pa.field("acc", pa.int64()),
        pa.field("spc_int", pa.int64()),
        pa.field("spc_str", pa.string()),
        pa.field("sp", pa.string()),
        pa.field("cents", pa.float64()),
    ]
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_midi_pitch_array(
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


def _make_generic_pitch_array(
    values: list[dict[str, int | None]] | None = None,
) -> pa.Array:
    """Build a generic_pitch struct array from simple dicts."""
    if values is None:
        values = [{"pitch_class": 0}, {"pitch_class": 4}, {"pitch_class": 7}]
    return pa.array(values, type=_GENERIC_PITCH_TYPE)


def _make_specific_pitch_class_array(
    values: list[dict[str, object]] | None = None,
) -> pa.Array:
    """Build a specific_pitch_class struct array from simple dicts."""
    if values is None:
        values = [
            {"gpc_str": "C", "acc": 0, "spc_int": 0},
            {"gpc_str": "F", "acc": 1, "spc_int": 6},
        ]
    return pa.array(values, type=_specific_pitch_CLASS_TYPE)


def _make_specific_pitch_array(
    values: list[dict[str, object]] | None = None,
) -> pa.Array:
    """Build a specific_pitch struct array from simple dicts."""
    if values is None:
        values = [
            {
                "gpc_int": 0,
                "gpc_str": "C",
                "acc": 0,
                "spc_int": 0,
                "spc_str": "C",
                "sp": "C4",
                "cents": 0.0,
            },
        ]
    return pa.array(values, type=_specific_pitch_TYPE)


# ---------------------------------------------------------------------------
# Unified PitchField
# ---------------------------------------------------------------------------


class TestUnifiedPitchField:
    """Verify PitchField is a concrete unified class."""

    def test_pitchfield_is_concrete(self) -> None:
        """PitchField can be instantiated directly with pitch_type."""
        arr = _make_midi_pitch_array([{"ep": 60, "epc": 0}])
        pa_field = pa.field("test", _MIDI_PITCH_TYPE)
        sf = StructField(arr, pa_field)
        pf = PitchField(sf, pitch_type="ep")
        assert isinstance(pf, PitchField)

    def test_pitchfield_requires_pitch_type(self) -> None:
        """PitchField raises ValueError when pitch_type is missing."""
        arr = _make_midi_pitch_array([{"ep": 60, "epc": 0}])
        pa_field = pa.field("test", _MIDI_PITCH_TYPE)
        sf = StructField(arr, pa_field)
        with pytest.raises(ValueError):
            PitchField(sf)

    def test_pitchfield_rejects_invalid_pitch_type(self) -> None:
        """PitchField raises ValueError for invalid pitch_type."""
        arr = _make_midi_pitch_array([{"ep": 60, "epc": 0}])
        pa_field = pa.field("test", _MIDI_PITCH_TYPE)
        sf = StructField(arr, pa_field)
        with pytest.raises(ValueError):
            PitchField(sf, pitch_type="invalid")


# ---------------------------------------------------------------------------
# isinstance checks (hierarchy)
# ---------------------------------------------------------------------------


class TestHierarchy:
    """Verify PitchField from various schemas is still PitchField."""

    def test_ep_pitch_field_is_pitch_field(self) -> None:
        """PitchField from EP struct is a PitchField."""
        arr = _make_midi_pitch_array([{"ep": 60, "epc": 0}])
        pf = PitchField.from_field(arr, pitch_type="ep")
        assert isinstance(pf, PitchField)

    def test_sp_pitch_field_is_pitch_field(self) -> None:
        """PitchField from SP struct is a PitchField."""
        arr = _make_specific_pitch_array()
        pf = PitchField.from_field(arr, pitch_type="sp")
        assert isinstance(pf, PitchField)

    def test_epc_pitch_field_is_pitch_field(self) -> None:
        """PitchField from EPC struct is a PitchField."""
        arr = _make_generic_pitch_array()
        pf = PitchField.from_field(arr, pitch_type="epc")
        assert isinstance(pf, PitchField)

    def test_spc_pitch_field_is_pitch_field(self) -> None:
        """PitchField from SPC struct is a PitchField."""
        arr = _make_specific_pitch_class_array()
        pf = PitchField.from_field(arr, pitch_type="spc")
        assert isinstance(pf, PitchField)


# ---------------------------------------------------------------------------
# Protocol Conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """Verify pitch fields satisfy PitchLike and SemanticTypeLike."""

    def test_midi_pitch_scalar_satisfies_pitchlike(self) -> None:
        """isinstance(MidiPitch(...), PitchLike) is True."""
        p = MidiPitch(midi_number=60)
        assert isinstance(p, PitchLike)

    def test_ep_pitch_field_satisfies_semantic_type_like(self) -> None:
        """isinstance(PitchField(ep=...), SemanticTypeLike) is True."""
        arr = _make_midi_pitch_array()
        pf = PitchField.from_field(arr, pitch_type="ep")
        assert isinstance(pf, SemanticTypeLike)

    def test_ep_pitch_field_semantic_type(self) -> None:
        """PitchField(ep=...).semantic_type == 'Pitch'."""
        arr = _make_midi_pitch_array()
        pf = PitchField.from_field(arr, pitch_type="ep")
        assert pf.semantic_type == "Pitch"

    def test_epc_pitch_field_satisfies_semantic_type_like(self) -> None:
        """isinstance(PitchField(epc=...), SemanticTypeLike) is True."""
        arr = _make_generic_pitch_array()
        pf = PitchField.from_field(arr, pitch_type="epc")
        assert isinstance(pf, SemanticTypeLike)

    def test_spc_pitch_field_satisfies_semantic_type_like(self) -> None:
        """isinstance(PitchField(spc=...), SemanticTypeLike) is True."""
        arr = _make_specific_pitch_class_array()
        pf = PitchField.from_field(arr, pitch_type="spc")
        assert isinstance(pf, SemanticTypeLike)

    def test_sp_pitch_field_satisfies_semantic_type_like(self) -> None:
        """isinstance(PitchField(sp=...), SemanticTypeLike) is True."""
        arr = _make_specific_pitch_array()
        pf = PitchField.from_field(arr, pitch_type="sp")
        assert isinstance(pf, SemanticTypeLike)


# ---------------------------------------------------------------------------
# PitchField EP Construction (from_field)
# ---------------------------------------------------------------------------


class TestEPPitchFieldConstruction:
    """Tests for PitchField.from_field() with EP (enharmonic pitch) sources."""

    def test_from_pa_array(self) -> None:
        """Construct from pa.Array (struct array)."""
        arr = _make_midi_pitch_array([{"ep": 59, "epc": 11}])
        pf = PitchField.from_field(arr, pitch_type="ep")
        assert len(pf) == 1

    def test_from_struct_field(self) -> None:
        """Construct from an existing StructField."""
        arr = _make_midi_pitch_array()
        pa_field = pa.field("midi_pitch", _MIDI_PITCH_TYPE)
        sf = StructField(arr, pa_field)
        pf = PitchField.from_field(sf, pitch_type="ep")
        assert len(pf) == 3

    def test_from_pa_field_schema_only(self) -> None:
        """Construct from pa.Field (no data), verify is_empty."""
        meta_dict = {"field_type": "PitchField", "pitch_type": "ep"}
        pa_field = pa.field(
            "midi_pitch",
            _MIDI_PITCH_TYPE,
            metadata={b"timetoalign": json.dumps(meta_dict).encode()},
        )
        pf = PitchField.from_field(pa_field)
        assert pf.is_empty is True

    def test_from_tuple(self) -> None:
        """Construct from (pa.Array, pa.Field) tuple."""
        arr = _make_midi_pitch_array([{"ep": 60, "epc": 0}, {"ep": 64, "epc": 4}])
        pa_field = pa.field(
            "midi_pitch",
            _MIDI_PITCH_TYPE,
            metadata={
                b"timetoalign": json.dumps(
                    {"field_type": "PitchField", "pitch_type": "ep"}
                ).encode()
            },
        )
        pf = PitchField.from_field((arr, pa_field))
        assert len(pf) == 2


# ---------------------------------------------------------------------------
# PitchField EPC Construction
# ---------------------------------------------------------------------------


class TestEPCPitchFieldConstruction:
    """Tests for PitchField.from_field() with EPC (enharmonic pitch class) sources."""

    def test_from_pa_array(self) -> None:
        """Construct from pa.Array (struct array)."""
        arr = _make_generic_pitch_array([{"pitch_class": 7}])
        pf = PitchField.from_field(arr, pitch_type="epc")
        assert len(pf) == 1

    def test_from_struct_field(self) -> None:
        """Construct from an existing StructField."""
        arr = _make_generic_pitch_array()
        pa_field = pa.field("generic_pitch", _GENERIC_PITCH_TYPE)
        sf = StructField(arr, pa_field)
        pf = PitchField.from_field(sf, pitch_type="epc")
        assert len(pf) == 3

    def test_from_pa_field_schema_only(self) -> None:
        """Construct from pa.Field (no data), verify is_empty."""
        meta_dict = {"field_type": "PitchField", "pitch_type": "epc"}
        pa_field = pa.field(
            "generic_pitch",
            _GENERIC_PITCH_TYPE,
            metadata={b"timetoalign": json.dumps(meta_dict).encode()},
        )
        pf = PitchField.from_field(pa_field)
        assert pf.is_empty is True

    def test_from_tuple(self) -> None:
        """Construct from (pa.Array, pa.Field) tuple."""
        arr = _make_generic_pitch_array([{"pitch_class": 0}, {"pitch_class": 7}])
        pa_field = pa.field("generic_pitch", _GENERIC_PITCH_TYPE)
        pf = PitchField.from_field((arr, pa_field), pitch_type="epc")
        assert len(pf) == 2


# ---------------------------------------------------------------------------
# PitchField SPC Construction
# ---------------------------------------------------------------------------


class TestSPCPitchFieldConstruction:
    """Tests for PitchField.from_field() with SPC (specific pitch class) sources."""

    def test_from_pa_array(self) -> None:
        """Construct from pa.Array (struct array)."""
        arr = _make_specific_pitch_class_array(
            [{"gpc_str": "D", "acc": 0, "spc_int": 2}]
        )
        pf = PitchField.from_field(arr, pitch_type="spc")
        assert len(pf) == 1

    def test_from_struct_field(self) -> None:
        """Construct from an existing StructField."""
        arr = _make_specific_pitch_class_array()
        pa_field = pa.field("specific_pitch_class", _specific_pitch_CLASS_TYPE)
        sf = StructField(arr, pa_field)
        pf = PitchField.from_field(sf, pitch_type="spc")
        assert len(pf) == 2

    def test_from_pa_field_schema_only(self) -> None:
        """Construct from pa.Field (no data), verify is_empty."""
        meta_dict = {
            "field_type": "PitchField",
            "pitch_type": "spc",
        }
        pa_field = pa.field(
            "specific_pitch_class",
            _specific_pitch_CLASS_TYPE,
            metadata={b"timetoalign": json.dumps(meta_dict).encode()},
        )
        pf = PitchField.from_field(pa_field)
        assert pf.is_empty is True


# ---------------------------------------------------------------------------
# PitchField EP Element Access (__getitem__)
# ---------------------------------------------------------------------------


class TestEPPitchFieldElementAccess:
    """Tests for PitchField(ep=...).__getitem__."""

    def test_getitem_returns_enharmonic_pitch(self) -> None:
        """Verify returns EnharmonicPitch instance with correct values."""
        arr = _make_midi_pitch_array([{"ep": 59, "epc": 11}])
        pf = PitchField.from_field(arr, pitch_type="ep")
        pitch = pf[0]
        assert isinstance(pitch, EnharmonicPitch)
        assert pitch.midi_number == 59
        assert pitch.pitch_class == 11

    def test_getitem_multiple_elements(self) -> None:
        """Iterate several elements, verify each."""
        values = [
            {"ep": 59, "epc": 11},
            {"ep": 60, "epc": 0},
            {"ep": 64, "epc": 4},
        ]
        arr = _make_midi_pitch_array(values)
        pf = PitchField.from_field(arr, pitch_type="ep")
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
        pf = PitchField.from_field(arr, pitch_type="ep")
        assert pf[0] is not None
        assert pf[1] is None
        assert pf[2] is not None


# ---------------------------------------------------------------------------
# PitchField EPC Element Access
# ---------------------------------------------------------------------------


class TestEPCPitchFieldElementAccess:
    """Tests for PitchField(epc=...).__getitem__."""

    def test_getitem_returns_enharmonic_pitch_class(self) -> None:
        """Verify returns EnharmonicPitchClass instance with correct values."""
        arr = _make_generic_pitch_array([{"pitch_class": 7}])
        pf = PitchField.from_field(arr, pitch_type="epc")
        pitch = pf[0]
        assert isinstance(pitch, EnharmonicPitchClass)
        assert pitch.pitch_class == 7

    def test_getitem_multiple_elements(self) -> None:
        """Iterate several elements, verify each."""
        values = [{"pitch_class": 0}, {"pitch_class": 4}, {"pitch_class": 7}]
        arr = _make_generic_pitch_array(values)
        pf = PitchField.from_field(arr, pitch_type="epc")
        for i, expected in enumerate(values):
            pitch = pf[i]
            assert pitch is not None
            assert pitch.pitch_class == expected["pitch_class"]

    def test_getitem_null_returns_none(self) -> None:
        """Verify None for null struct entries."""
        arr = pa.array(
            [{"pitch_class": 0}, None, {"pitch_class": 7}],
            type=_GENERIC_PITCH_TYPE,
        )
        pf = PitchField.from_field(arr, pitch_type="epc")
        assert pf[0] is not None
        assert pf[1] is None
        assert pf[2] is not None


# ---------------------------------------------------------------------------
# PitchField SPC Element Access
# ---------------------------------------------------------------------------


class TestSPCPitchFieldElementAccess:
    """Tests for PitchField(spc=...).__getitem__."""

    def test_getitem_returns_specific_pitch_class(self) -> None:
        """Verify returns SpecificPitchClass instance with correct values."""
        arr = _make_specific_pitch_class_array(
            [{"gpc_str": "C", "acc": 1, "spc_int": 7}]
        )
        pf = PitchField.from_field(arr, pitch_type="spc")
        pitch = pf[0]
        assert isinstance(pitch, SpecificPitchClass)
        assert pitch.step == "C"
        assert pitch.alter == 1
        assert pitch.fifths == 7

    def test_getitem_null_returns_none(self) -> None:
        """Verify None for null struct entries."""
        arr = pa.array(
            [{"gpc_str": "C", "acc": 0, "spc_int": 0}, None],
            type=_specific_pitch_CLASS_TYPE,
        )
        pf = PitchField.from_field(arr, pitch_type="spc")
        assert pf[0] is not None
        assert pf[1] is None


# ---------------------------------------------------------------------------
# PitchField SP Element Access
# ---------------------------------------------------------------------------


class TestSPPitchFieldElementAccess:
    """Tests for PitchField(sp=...).__getitem__."""

    def test_getitem_returns_specific_pitch(self) -> None:
        """Verify returns SpecificPitch instance with correct values."""
        arr = _make_specific_pitch_array()
        pf = PitchField.from_field(arr, pitch_type="sp")
        pitch = pf[0]
        assert isinstance(pitch, SpecificPitch)
        assert pitch.step == "C"
        assert pitch.alter == 0
        assert pitch.octave == 4
        assert pitch.fifths == 0
        assert pitch.cents == 0.0

    def test_getitem_null_returns_none(self) -> None:
        """Verify None for null struct entries."""
        arr = pa.array(
            [
                {
                    "gpc_int": 0,
                    "gpc_str": "C",
                    "acc": 0,
                    "spc_int": 0,
                    "spc_str": "C",
                    "sp": "C4",
                    "cents": 0.0,
                },
                None,
            ],
            type=_specific_pitch_TYPE,
        )
        pf = PitchField.from_field(arr, pitch_type="sp")
        assert pf[0] is not None
        assert pf[1] is None


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    """Tests for pitch field properties."""

    def test_ep_semantic_type(self) -> None:
        """PitchField(ep=...).semantic_type == 'Pitch'."""
        arr = _make_midi_pitch_array([{"ep": 60, "epc": 0}])
        pf = PitchField.from_field(arr, pitch_type="ep")
        assert pf.semantic_type == "Pitch"

    def test_ep_metadata_dict(self) -> None:
        """Verify PitchField(ep=...) returns correct metadata_dict."""
        arr = _make_midi_pitch_array([{"ep": 60, "epc": 0}])
        pf = PitchField.from_field(arr, pitch_type="ep")
        md = pf.metadata_dict()
        assert md["field_type"] == "PitchField"
        assert md["pitch_type"] == "ep"
        assert md["space"] == "enharmonic"
        assert md["is_class"] == "False"

    def test_epc_semantic_type(self) -> None:
        """PitchField(epc=...).semantic_type == 'Pitch'."""
        arr = _make_generic_pitch_array([{"pitch_class": 0}])
        pf = PitchField.from_field(arr, pitch_type="epc")
        assert pf.semantic_type == "Pitch"

    def test_epc_metadata_dict(self) -> None:
        """Verify PitchField(epc=...) returns correct metadata_dict."""
        arr = _make_generic_pitch_array([{"pitch_class": 0}])
        pf = PitchField.from_field(arr, pitch_type="epc")
        md = pf.metadata_dict()
        assert md["field_type"] == "PitchField"
        assert md["pitch_type"] == "epc"
        assert md["space"] == "enharmonic"
        assert md["is_class"] == "True"

    def test_spc_semantic_type(self) -> None:
        """PitchField(spc=...).semantic_type == 'Pitch'."""
        arr = _make_specific_pitch_class_array()
        pf = PitchField.from_field(arr, pitch_type="spc")
        assert pf.semantic_type == "Pitch"

    def test_spc_metadata_dict(self) -> None:
        """Verify PitchField(spc=...) returns correct metadata_dict."""
        arr = _make_specific_pitch_class_array()
        pf = PitchField.from_field(arr, pitch_type="spc")
        md = pf.metadata_dict()
        assert md["field_type"] == "PitchField"
        assert md["pitch_type"] == "spc"
        assert md["space"] == "specific"
        assert md["is_class"] == "True"

    def test_sp_semantic_type(self) -> None:
        """PitchField(sp=...).semantic_type == 'Pitch'."""
        arr = _make_specific_pitch_array()
        pf = PitchField.from_field(arr, pitch_type="sp")
        assert pf.semantic_type == "Pitch"

    def test_sp_metadata_dict(self) -> None:
        """Verify PitchField(sp=...) returns correct metadata_dict."""
        arr = _make_specific_pitch_array()
        pf = PitchField.from_field(arr, pitch_type="sp")
        md = pf.metadata_dict()
        assert md["field_type"] == "PitchField"
        assert md["pitch_type"] == "sp"
        assert md["space"] == "specific"
        assert md["is_class"] == "False"


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    """Tests for pitch field serialization."""

    def test_to_field_injects_metadata(self) -> None:
        """Verify to_field() produces pa.Field with b'timetoalign' JSON blob."""
        arr = _make_midi_pitch_array([{"ep": 60, "epc": 0}])
        pf = PitchField.from_field(arr, pitch_type="ep")
        pa_field = pf.to_field()

        assert isinstance(pa_field, pa.Field)
        raw_meta = pa_field.metadata
        assert b"timetoalign" in raw_meta
        blob = json.loads(raw_meta[b"timetoalign"].decode("utf-8"))
        assert blob["field_type"] == "PitchField"
        assert blob["pitch_type"] == "ep"
        assert blob["space"] == "enharmonic"
        assert blob["is_class"] == "False"

    def test_parquet_round_trip(self, tmp_path: object) -> None:
        """Write pa.Table with PitchField(ep) column, read back, verify data + metadata."""
        from pathlib import Path

        tmp_dir = Path(str(tmp_path))
        parquet_path = tmp_dir / "pitches.parquet"

        # Build PitchField(ep)
        values = [
            {"ep": 59, "epc": 11},
            {"ep": 60, "epc": 0},
            {"ep": 64, "epc": 4},
        ]
        arr = _make_midi_pitch_array(values)
        pf = PitchField.from_field(arr, pitch_type="ep")

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
        assert pf2.semantic_type == "Pitch"
        assert pf2.pitch_type == "ep"

        # Verify data survived
        assert len(pf2) == 3
        for i, expected in enumerate(values):
            pitch = pf2[i]
            assert pitch is not None
            assert pitch.midi_number == expected["ep"]
            assert pitch.pitch_class == expected["epc"]

    def test_epc_to_field_injects_metadata(self) -> None:
        """Verify PitchField(epc=...).to_field() produces correct metadata."""
        arr = _make_generic_pitch_array([{"pitch_class": 0}])
        pf = PitchField.from_field(arr, pitch_type="epc")
        pa_field = pf.to_field()

        raw_meta = pa_field.metadata
        assert b"timetoalign" in raw_meta
        blob = json.loads(raw_meta[b"timetoalign"].decode("utf-8"))
        assert blob["field_type"] == "PitchField"
        assert blob["pitch_type"] == "epc"
        assert blob["space"] == "enharmonic"
        assert blob["is_class"] == "True"

    def test_sp_to_field_injects_metadata(self) -> None:
        """Verify PitchField(sp=...).to_field() produces correct metadata."""
        arr = _make_specific_pitch_array()
        pf = PitchField.from_field(arr, pitch_type="sp")
        pa_field = pf.to_field()

        raw_meta = pa_field.metadata
        assert b"timetoalign" in raw_meta
        blob = json.loads(raw_meta[b"timetoalign"].decode("utf-8"))
        assert blob["field_type"] == "PitchField"
        assert blob["pitch_type"] == "sp"
        assert blob["space"] == "specific"
        assert blob["is_class"] == "False"


# ---------------------------------------------------------------------------
# Delegation
# ---------------------------------------------------------------------------


class TestDelegation:
    """Tests for SemanticField delegation to the inner StructField."""

    def test_value_returns_struct_field(self) -> None:
        """Verify .value returns the inner StructField."""
        arr = _make_midi_pitch_array([{"ep": 60, "epc": 0}])
        pf = PitchField.from_field(arr, pitch_type="ep")
        raw = pf.value
        assert isinstance(raw, StructField)

    def test_len_delegation(self) -> None:
        """Verify len() passes through to inner StructField."""
        arr = _make_midi_pitch_array()
        pf = PitchField.from_field(arr, pitch_type="ep")
        assert len(pf) == 3

    def test_is_empty_delegation(self) -> None:
        """Verify is_empty passes through for schema-only field."""
        meta_dict = {"field_type": "PitchField", "pitch_type": "ep"}
        pa_field = pa.field(
            "midi_pitch",
            _MIDI_PITCH_TYPE,
            metadata={b"timetoalign": json.dumps(meta_dict).encode()},
        )
        pf = PitchField.from_field(pa_field)
        assert pf.is_empty is True

    def test_name_delegation(self) -> None:
        """Verify .name passes through to inner StructField."""
        arr = _make_midi_pitch_array([{"ep": 60, "epc": 0}])
        pa_field = pa.field("my_pitch", _MIDI_PITCH_TYPE)
        sf = StructField(arr, pa_field)
        pf = PitchField.from_field(sf, pitch_type="ep")
        assert pf.name == "my_pitch"

    def test_field_names_delegation(self) -> None:
        """Verify .field_names works via __getattr__ delegation."""
        arr = _make_midi_pitch_array([{"ep": 60, "epc": 0}])
        pf = PitchField.from_field(arr, pitch_type="ep")
        assert pf.field_names == ["ep", "epc"]
