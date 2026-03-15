"""Tests for fields/pitch.py -- pitch field hierarchy construction, access, and serialization."""

from __future__ import annotations

import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from timetoalign.core.protocols import PitchLike, SemanticTypeLike
from timetoalign.core.scalars.pitch import (
    GenericPitch,
    MidiPitch,
    SpelledPitch,
    SpelledPitchClass,
)
from timetoalign.fields.base import StructField
from timetoalign.fields.pitch import (
    EnharmonicPitchField,
    GenericPitchField,
    MidiPitchField,
    PitchField,
    SpecificPitchField,
    SpelledPitchClassField,
    SpelledPitchField,
)

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

_SPELLED_PITCH_CLASS_TYPE = pa.struct(
    [
        pa.field("gpc_str", pa.string(), nullable=True),
        pa.field("acc", pa.int64(), nullable=True),
        pa.field("spc_int", pa.int64(), nullable=True),
    ]
)

_SPELLED_PITCH_TYPE = pa.struct(
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


def _make_spelled_pitch_class_array(
    values: list[dict[str, object]] | None = None,
) -> pa.Array:
    """Build a spelled_pitch_class struct array from simple dicts."""
    if values is None:
        values = [
            {"gpc_str": "C", "acc": 0, "spc_int": 0},
            {"gpc_str": "F", "acc": 1, "spc_int": 6},
        ]
    return pa.array(values, type=_SPELLED_PITCH_CLASS_TYPE)


def _make_spelled_pitch_array(
    values: list[dict[str, object]] | None = None,
) -> pa.Array:
    """Build a spelled_pitch struct array from simple dicts."""
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
    return pa.array(values, type=_SPELLED_PITCH_TYPE)


# ---------------------------------------------------------------------------
# Abstract PitchField
# ---------------------------------------------------------------------------


class TestAbstractPitchField:
    """Verify PitchField is abstract and cannot be instantiated directly."""

    def test_pitchfield_is_abstract(self) -> None:
        """PitchField cannot be instantiated directly."""
        arr = _make_midi_pitch_array([{"ep": 60, "epc": 0}])
        pa_field = pa.field("test", _MIDI_PITCH_TYPE)
        sf = StructField(arr, pa_field)
        with pytest.raises(TypeError):
            PitchField(sf)  # type: ignore[abstract]

    def test_pitchfield_has_abstract_methods(self) -> None:
        """PitchField declares abstract methods."""
        abstracts = PitchField.__abstractmethods__
        assert "semantic_type" in abstracts
        assert "metadata_dict" in abstracts
        assert "__getitem__" in abstracts
        assert "from_field" in abstracts


# ---------------------------------------------------------------------------
# isinstance checks (hierarchy)
# ---------------------------------------------------------------------------


class TestHierarchy:
    """Verify all concrete subclasses are isinstance of PitchField."""

    def test_specific_pitch_field_is_pitch_field(self) -> None:
        """EnharmonicPitchField is a PitchField."""
        arr = _make_midi_pitch_array([{"ep": 60, "epc": 0}])
        pf = EnharmonicPitchField.from_field(arr)
        assert isinstance(pf, PitchField)

    def test_enharmonic_pitch_field_is_pitch_field(self) -> None:
        """SpecificPitchField is a PitchField."""
        arr = _make_spelled_pitch_array()
        epf = SpecificPitchField.from_field(arr)
        assert isinstance(epf, PitchField)

    def test_generic_pitch_field_is_pitch_field(self) -> None:
        """GenericPitchField is a PitchField."""
        arr = _make_generic_pitch_array()
        gpf = GenericPitchField.from_field(arr)
        assert isinstance(gpf, PitchField)

    def test_spelled_pitch_class_field_is_pitch_field(self) -> None:
        """SpelledPitchClassField is a PitchField."""
        arr = _make_spelled_pitch_class_array()
        spcf = SpelledPitchClassField.from_field(arr)
        assert isinstance(spcf, PitchField)


# ---------------------------------------------------------------------------
# Aliases
# ---------------------------------------------------------------------------


class TestAliases:
    """Verify backward-compat aliases work correctly."""

    def test_midi_pitch_field_is_specific_pitch_field(self) -> None:
        """MidiPitchField is EnharmonicPitchField."""
        assert MidiPitchField is EnharmonicPitchField

    def test_spelled_pitch_field_is_enharmonic_pitch_field(self) -> None:
        """SpelledPitchField is SpecificPitchField."""
        assert SpelledPitchField is SpecificPitchField

    def test_midi_pitch_field_creates_specific_pitch_field(self) -> None:
        """MidiPitchField.from_field() returns a EnharmonicPitchField."""
        arr = _make_midi_pitch_array([{"ep": 60, "epc": 0}])
        pf = MidiPitchField.from_field(arr)
        assert isinstance(pf, EnharmonicPitchField)
        assert isinstance(pf, PitchField)

    def test_spelled_pitch_field_creates_enharmonic_pitch_field(self) -> None:
        """SpelledPitchField.from_field() returns an SpecificPitchField."""
        arr = _make_spelled_pitch_array()
        spf = SpelledPitchField.from_field(arr)
        assert isinstance(spf, SpecificPitchField)
        assert isinstance(spf, PitchField)


# ---------------------------------------------------------------------------
# Protocol Conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """Verify pitch fields satisfy PitchLike and SemanticTypeLike."""

    def test_midi_pitch_scalar_satisfies_pitchlike(self) -> None:
        """isinstance(MidiPitch(...), PitchLike) is True."""
        p = MidiPitch(midi_number=60, pitch_class=0)
        assert isinstance(p, PitchLike)

    def test_specific_pitch_field_satisfies_semantic_type_like(self) -> None:
        """isinstance(EnharmonicPitchField(...), SemanticTypeLike) is True."""
        arr = _make_midi_pitch_array()
        pf = EnharmonicPitchField.from_field(arr)
        assert isinstance(pf, SemanticTypeLike)

    def test_specific_pitch_field_semantic_type(self) -> None:
        """EnharmonicPitchField.semantic_type == 'MidiPitch'."""
        arr = _make_midi_pitch_array()
        pf = EnharmonicPitchField.from_field(arr)
        assert pf.semantic_type == "EnharmonicPitch"

    def test_generic_pitch_field_satisfies_semantic_type_like(self) -> None:
        """isinstance(GenericPitchField(...), SemanticTypeLike) is True."""
        arr = _make_generic_pitch_array()
        gpf = GenericPitchField.from_field(arr)
        assert isinstance(gpf, SemanticTypeLike)

    def test_spelled_pitch_class_field_satisfies_semantic_type_like(self) -> None:
        """isinstance(SpelledPitchClassField(...), SemanticTypeLike) is True."""
        arr = _make_spelled_pitch_class_array()
        spcf = SpelledPitchClassField.from_field(arr)
        assert isinstance(spcf, SemanticTypeLike)

    def test_enharmonic_pitch_field_satisfies_semantic_type_like(self) -> None:
        """isinstance(SpecificPitchField(...), SemanticTypeLike) is True."""
        arr = _make_spelled_pitch_array()
        epf = SpecificPitchField.from_field(arr)
        assert isinstance(epf, SemanticTypeLike)


# ---------------------------------------------------------------------------
# EnharmonicPitchField Construction (from_field)
# ---------------------------------------------------------------------------


class TestEnharmonicPitchFieldConstruction:
    """Tests for EnharmonicPitchField.from_field() with various source types."""

    def test_from_pa_array(self) -> None:
        """Construct from pa.Array (struct array)."""
        arr = _make_midi_pitch_array([{"ep": 59, "epc": 11}])
        pf = EnharmonicPitchField.from_field(arr)
        assert len(pf) == 1

    def test_from_struct_field(self) -> None:
        """Construct from an existing StructField."""
        arr = _make_midi_pitch_array()
        pa_field = pa.field("midi_pitch", _MIDI_PITCH_TYPE)
        sf = StructField(arr, pa_field)
        pf = EnharmonicPitchField.from_field(sf)
        assert len(pf) == 3

    def test_from_pa_field_schema_only(self) -> None:
        """Construct from pa.Field (no data), verify is_empty."""
        meta_dict = {"field_type": "EnharmonicPitchField", "pitch_type": "enharmonic"}
        pa_field = pa.field(
            "midi_pitch",
            _MIDI_PITCH_TYPE,
            metadata={b"timetoalign": json.dumps(meta_dict).encode()},
        )
        pf = EnharmonicPitchField.from_field(pa_field)
        assert pf.is_empty is True

    def test_from_tuple(self) -> None:
        """Construct from (pa.Array, pa.Field) tuple."""
        arr = _make_midi_pitch_array([{"ep": 60, "epc": 0}, {"ep": 64, "epc": 4}])
        pa_field = pa.field(
            "midi_pitch",
            _MIDI_PITCH_TYPE,
            metadata={
                b"timetoalign": json.dumps(
                    {"field_type": "EnharmonicPitchField", "pitch_type": "enharmonic"}
                ).encode()
            },
        )
        pf = EnharmonicPitchField.from_field((arr, pa_field))
        assert len(pf) == 2


# ---------------------------------------------------------------------------
# GenericPitchField Construction
# ---------------------------------------------------------------------------


class TestGenericPitchFieldConstruction:
    """Tests for GenericPitchField.from_field() with various source types."""

    def test_from_pa_array(self) -> None:
        """Construct from pa.Array (struct array)."""
        arr = _make_generic_pitch_array([{"pitch_class": 7}])
        gpf = GenericPitchField.from_field(arr)
        assert len(gpf) == 1

    def test_from_struct_field(self) -> None:
        """Construct from an existing StructField."""
        arr = _make_generic_pitch_array()
        pa_field = pa.field("generic_pitch", _GENERIC_PITCH_TYPE)
        sf = StructField(arr, pa_field)
        gpf = GenericPitchField.from_field(sf)
        assert len(gpf) == 3

    def test_from_pa_field_schema_only(self) -> None:
        """Construct from pa.Field (no data), verify is_empty."""
        meta_dict = {"field_type": "GenericPitchField", "pitch_type": "generic"}
        pa_field = pa.field(
            "generic_pitch",
            _GENERIC_PITCH_TYPE,
            metadata={b"timetoalign": json.dumps(meta_dict).encode()},
        )
        gpf = GenericPitchField.from_field(pa_field)
        assert gpf.is_empty is True

    def test_from_tuple(self) -> None:
        """Construct from (pa.Array, pa.Field) tuple."""
        arr = _make_generic_pitch_array([{"pitch_class": 0}, {"pitch_class": 7}])
        pa_field = pa.field("generic_pitch", _GENERIC_PITCH_TYPE)
        gpf = GenericPitchField.from_field((arr, pa_field))
        assert len(gpf) == 2


# ---------------------------------------------------------------------------
# SpelledPitchClassField Construction
# ---------------------------------------------------------------------------


class TestSpelledPitchClassFieldConstruction:
    """Tests for SpelledPitchClassField.from_field() with various source types."""

    def test_from_pa_array(self) -> None:
        """Construct from pa.Array (struct array)."""
        arr = _make_spelled_pitch_class_array(
            [{"gpc_str": "D", "acc": 0, "spc_int": 2}]
        )
        spcf = SpelledPitchClassField.from_field(arr)
        assert len(spcf) == 1

    def test_from_struct_field(self) -> None:
        """Construct from an existing StructField."""
        arr = _make_spelled_pitch_class_array()
        pa_field = pa.field("spelled_pitch_class", _SPELLED_PITCH_CLASS_TYPE)
        sf = StructField(arr, pa_field)
        spcf = SpelledPitchClassField.from_field(sf)
        assert len(spcf) == 2

    def test_from_pa_field_schema_only(self) -> None:
        """Construct from pa.Field (no data), verify is_empty."""
        meta_dict = {
            "field_type": "SpelledPitchClassField",
            "pitch_type": "spelled_class",
        }
        pa_field = pa.field(
            "spelled_pitch_class",
            _SPELLED_PITCH_CLASS_TYPE,
            metadata={b"timetoalign": json.dumps(meta_dict).encode()},
        )
        spcf = SpelledPitchClassField.from_field(pa_field)
        assert spcf.is_empty is True


# ---------------------------------------------------------------------------
# EnharmonicPitchField Element Access (__getitem__)
# ---------------------------------------------------------------------------


class TestEnharmonicPitchFieldElementAccess:
    """Tests for EnharmonicPitchField.__getitem__."""

    def test_getitem_returns_midi_pitch(self) -> None:
        """Verify returns MidiPitch instance with correct values."""
        arr = _make_midi_pitch_array([{"ep": 59, "epc": 11}])
        pf = EnharmonicPitchField.from_field(arr)
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
        arr = _make_midi_pitch_array(values)
        pf = EnharmonicPitchField.from_field(arr)
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
        pf = EnharmonicPitchField.from_field(arr)
        assert pf[0] is not None
        assert pf[1] is None
        assert pf[2] is not None


# ---------------------------------------------------------------------------
# GenericPitchField Element Access
# ---------------------------------------------------------------------------


class TestGenericPitchFieldElementAccess:
    """Tests for GenericPitchField.__getitem__."""

    def test_getitem_returns_generic_pitch(self) -> None:
        """Verify returns GenericPitch instance with correct values."""
        arr = _make_generic_pitch_array([{"pitch_class": 7}])
        gpf = GenericPitchField.from_field(arr)
        pitch = gpf[0]
        assert isinstance(pitch, GenericPitch)
        assert pitch.pitch_class == 7

    def test_getitem_multiple_elements(self) -> None:
        """Iterate several elements, verify each."""
        values = [{"pitch_class": 0}, {"pitch_class": 4}, {"pitch_class": 7}]
        arr = _make_generic_pitch_array(values)
        gpf = GenericPitchField.from_field(arr)
        for i, expected in enumerate(values):
            pitch = gpf[i]
            assert pitch is not None
            assert pitch.pitch_class == expected["pitch_class"]

    def test_getitem_null_returns_none(self) -> None:
        """Verify None for null struct entries."""
        arr = pa.array(
            [{"pitch_class": 0}, None, {"pitch_class": 7}],
            type=_GENERIC_PITCH_TYPE,
        )
        gpf = GenericPitchField.from_field(arr)
        assert gpf[0] is not None
        assert gpf[1] is None
        assert gpf[2] is not None


# ---------------------------------------------------------------------------
# SpelledPitchClassField Element Access
# ---------------------------------------------------------------------------


class TestSpelledPitchClassFieldElementAccess:
    """Tests for SpelledPitchClassField.__getitem__."""

    def test_getitem_returns_spelled_pitch_class(self) -> None:
        """Verify returns SpelledPitchClass instance with correct values."""
        arr = _make_spelled_pitch_class_array(
            [{"gpc_str": "C", "acc": 1, "spc_int": 7}]
        )
        spcf = SpelledPitchClassField.from_field(arr)
        pitch = spcf[0]
        assert isinstance(pitch, SpelledPitchClass)
        assert pitch.step == "C"
        assert pitch.alter == 1
        assert pitch.fifths == 7

    def test_getitem_null_returns_none(self) -> None:
        """Verify None for null struct entries."""
        arr = pa.array(
            [{"gpc_str": "C", "acc": 0, "spc_int": 0}, None],
            type=_SPELLED_PITCH_CLASS_TYPE,
        )
        spcf = SpelledPitchClassField.from_field(arr)
        assert spcf[0] is not None
        assert spcf[1] is None


# ---------------------------------------------------------------------------
# SpecificPitchField Element Access
# ---------------------------------------------------------------------------


class TestSpecificPitchFieldElementAccess:
    """Tests for SpecificPitchField.__getitem__."""

    def test_getitem_returns_spelled_pitch(self) -> None:
        """Verify returns SpelledPitch instance with correct values."""
        arr = _make_spelled_pitch_array()
        epf = SpecificPitchField.from_field(arr)
        pitch = epf[0]
        assert isinstance(pitch, SpelledPitch)
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
            type=_SPELLED_PITCH_TYPE,
        )
        epf = SpecificPitchField.from_field(arr)
        assert epf[0] is not None
        assert epf[1] is None


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    """Tests for pitch field properties."""

    def test_specific_semantic_type(self) -> None:
        """EnharmonicPitchField.semantic_type == 'MidiPitch'."""
        arr = _make_midi_pitch_array([{"ep": 60, "epc": 0}])
        pf = EnharmonicPitchField.from_field(arr)
        assert pf.semantic_type == "EnharmonicPitch"

    def test_specific_metadata_dict(self) -> None:
        """Verify EnharmonicPitchField returns correct metadata_dict."""
        arr = _make_midi_pitch_array([{"ep": 60, "epc": 0}])
        pf = EnharmonicPitchField.from_field(arr)
        md = pf.metadata_dict()
        assert md["field_type"] == "EnharmonicPitchField"
        assert md["pitch_type"] == "enharmonic"

    def test_generic_semantic_type(self) -> None:
        """GenericPitchField.semantic_type == 'GenericPitch'."""
        arr = _make_generic_pitch_array([{"pitch_class": 0}])
        gpf = GenericPitchField.from_field(arr)
        assert gpf.semantic_type == "GenericPitch"

    def test_generic_metadata_dict(self) -> None:
        """Verify GenericPitchField returns correct metadata_dict."""
        arr = _make_generic_pitch_array([{"pitch_class": 0}])
        gpf = GenericPitchField.from_field(arr)
        md = gpf.metadata_dict()
        assert md["field_type"] == "GenericPitchField"
        assert md["pitch_type"] == "generic"

    def test_spelled_pitch_class_semantic_type(self) -> None:
        """SpelledPitchClassField.semantic_type == 'SpelledPitchClass'."""
        arr = _make_spelled_pitch_class_array()
        spcf = SpelledPitchClassField.from_field(arr)
        assert spcf.semantic_type == "SpelledPitchClass"

    def test_spelled_pitch_class_metadata_dict(self) -> None:
        """Verify SpelledPitchClassField returns correct metadata_dict."""
        arr = _make_spelled_pitch_class_array()
        spcf = SpelledPitchClassField.from_field(arr)
        md = spcf.metadata_dict()
        assert md["field_type"] == "SpelledPitchClassField"
        assert md["pitch_type"] == "spelled_class"

    def test_enharmonic_semantic_type(self) -> None:
        """SpecificPitchField.semantic_type == 'SpelledPitch'."""
        arr = _make_spelled_pitch_array()
        epf = SpecificPitchField.from_field(arr)
        assert epf.semantic_type == "SpecificPitch"

    def test_enharmonic_metadata_dict(self) -> None:
        """Verify SpecificPitchField returns correct metadata_dict."""
        arr = _make_spelled_pitch_array()
        epf = SpecificPitchField.from_field(arr)
        md = epf.metadata_dict()
        assert md["field_type"] == "SpecificPitchField"
        assert md["pitch_type"] == "specific"


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    """Tests for pitch field serialization."""

    def test_to_field_injects_metadata(self) -> None:
        """Verify to_field() produces pa.Field with b'timetoalign' JSON blob."""
        arr = _make_midi_pitch_array([{"ep": 60, "epc": 0}])
        pf = EnharmonicPitchField.from_field(arr)
        pa_field = pf.to_field()

        assert isinstance(pa_field, pa.Field)
        raw_meta = pa_field.metadata
        assert b"timetoalign" in raw_meta
        blob = json.loads(raw_meta[b"timetoalign"].decode("utf-8"))
        assert blob["field_type"] == "EnharmonicPitchField"
        assert blob["pitch_type"] == "enharmonic"

    def test_parquet_round_trip(self, tmp_path: object) -> None:
        """Write pa.Table with EnharmonicPitchField column, read back, verify data + metadata."""
        from pathlib import Path

        tmp_dir = Path(str(tmp_path))
        parquet_path = tmp_dir / "pitches.parquet"

        # Build EnharmonicPitchField
        values = [
            {"ep": 59, "epc": 11},
            {"ep": 60, "epc": 0},
            {"ep": 64, "epc": 4},
        ]
        arr = _make_midi_pitch_array(values)
        pf = EnharmonicPitchField.from_field(arr)

        # Build table using the enriched pa.Field
        enriched_field = pf.to_field()
        table = pa.table(
            {"midi_pitch": arr},
            schema=pa.schema([enriched_field.with_name("midi_pitch")]),
        )

        # Write and read back
        pq.write_table(table, str(parquet_path))
        table_back = pq.read_table(str(parquet_path))

        # Reconstruct EnharmonicPitchField from the read-back table
        col = table_back.column("midi_pitch")
        field = table_back.schema.field("midi_pitch")
        pf2 = EnharmonicPitchField.from_field((col, field))

        # Verify metadata survived
        assert pf2.semantic_type == "EnharmonicPitch"

        # Verify data survived
        assert len(pf2) == 3
        for i, expected in enumerate(values):
            pitch = pf2[i]
            assert pitch is not None
            assert pitch.midi_number == expected["ep"]
            assert pitch.pitch_class == expected["epc"]

    def test_generic_to_field_injects_metadata(self) -> None:
        """Verify GenericPitchField.to_field() produces correct metadata."""
        arr = _make_generic_pitch_array([{"pitch_class": 0}])
        gpf = GenericPitchField.from_field(arr)
        pa_field = gpf.to_field()

        raw_meta = pa_field.metadata
        assert b"timetoalign" in raw_meta
        blob = json.loads(raw_meta[b"timetoalign"].decode("utf-8"))
        assert blob["field_type"] == "GenericPitchField"
        assert blob["pitch_type"] == "generic"

    def test_enharmonic_to_field_injects_metadata(self) -> None:
        """Verify SpecificPitchField.to_field() produces correct metadata."""
        arr = _make_spelled_pitch_array()
        epf = SpecificPitchField.from_field(arr)
        pa_field = epf.to_field()

        raw_meta = pa_field.metadata
        assert b"timetoalign" in raw_meta
        blob = json.loads(raw_meta[b"timetoalign"].decode("utf-8"))
        assert blob["field_type"] == "SpecificPitchField"
        assert blob["pitch_type"] == "specific"


# ---------------------------------------------------------------------------
# Delegation
# ---------------------------------------------------------------------------


class TestDelegation:
    """Tests for SemanticField delegation to the inner StructField."""

    def test_value_returns_struct_field(self) -> None:
        """Verify .value returns the inner StructField."""
        arr = _make_midi_pitch_array([{"ep": 60, "epc": 0}])
        pf = EnharmonicPitchField.from_field(arr)
        raw = pf.value
        assert isinstance(raw, StructField)

    def test_len_delegation(self) -> None:
        """Verify len() passes through to inner StructField."""
        arr = _make_midi_pitch_array()
        pf = EnharmonicPitchField.from_field(arr)
        assert len(pf) == 3

    def test_is_empty_delegation(self) -> None:
        """Verify is_empty passes through for schema-only field."""
        meta_dict = {"field_type": "EnharmonicPitchField", "pitch_type": "enharmonic"}
        pa_field = pa.field(
            "midi_pitch",
            _MIDI_PITCH_TYPE,
            metadata={b"timetoalign": json.dumps(meta_dict).encode()},
        )
        pf = EnharmonicPitchField.from_field(pa_field)
        assert pf.is_empty is True

    def test_name_delegation(self) -> None:
        """Verify .name passes through to inner StructField."""
        arr = _make_midi_pitch_array([{"ep": 60, "epc": 0}])
        pa_field = pa.field("my_pitch", _MIDI_PITCH_TYPE)
        sf = StructField(arr, pa_field)
        pf = EnharmonicPitchField.from_field(sf)
        assert pf.name == "my_pitch"

    def test_field_names_delegation(self) -> None:
        """Verify .field_names works via __getattr__ delegation."""
        arr = _make_midi_pitch_array([{"ep": 60, "epc": 0}])
        pf = EnharmonicPitchField.from_field(arr)
        assert pf.field_names == ["ep", "epc"]
