"""Tests for ``timetoalign.core.events`` — paired Object/ObjectField API.

The paired-Object/ObjectField redesign replaced the earlier umbrella
``PitchField`` / ``HarmonyField`` / ``DcmlLabelField`` etc. with one
paired ``XField(SemanticField[X])`` per scalar.  Each paired class
derives its ``pa_schema`` from ``T``'s pydantic model at
subclass-declaration time and exposes ``from_field`` / ``__getitem__``
via the ``SemanticField`` base.

This module pins the paired-class surface: schema derivation,
materialisation, parquet round-trip, and blueprint construction.

Tests for legacy umbrella APIs (``PitchField(pitch_type=...)``,
``PitchField.from_raw(ep=...)``, ``DcmlLabelField`` alias, bridge-schema
``_scalar_from_legacy_schema`` reconstructions) have been removed —
they exercised code paths that no longer exist.  Shape-recognising
helpers (``get_field(ScalarClass)``, ``get_fields_satisfying(
ProtocolClass)``) on top of the paired classes are tested separately.
"""

from __future__ import annotations

import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from timetoalign.core.events import (
    DcmlHarmony,
    DcmlHarmonyField,
    DcmlStorageSchema,
    EnharmonicPitch,
    EnharmonicPitchClass,
    EnharmonicPitchClassField,
    EnharmonicPitchField,
    GenericPitch,
    GenericPitchClass,
    GenericPitchClassField,
    GenericPitchField,
    HarmonyLabel,
    HarmonyLabelField,
    MidiPitch,
    MidiPitchField,
    PitchBasedHarmony,
    PitchBasedHarmonyField,
    RomanNumeralHarmony,
    RomanNumeralHarmonyField,
    SpecificPitch,
    SpecificPitchClass,
    SpecificPitchClassField,
    SpecificPitchField,
    WesternTertianHarmony,
    WesternTertianHarmonyField,
    figbass_to_inversion,
)
from timetoalign.core.fields import (
    TIMETOALIGN_METADATA_KEY,
    SemanticField,
    derive_arrow_struct,
)

# ---------------------------------------------------------------------------
# pa_schema caching — every paired class has its struct cached at declaration
# ---------------------------------------------------------------------------


class TestPairedClassSchemaCaching:
    @pytest.mark.parametrize(
        "field_cls,scalar_cls",
        [
            (EnharmonicPitchField, EnharmonicPitch),
            (EnharmonicPitchClassField, EnharmonicPitchClass),
            (GenericPitchField, GenericPitch),
            (GenericPitchClassField, GenericPitchClass),
            (MidiPitchField, MidiPitch),
            (SpecificPitchField, SpecificPitch),
            (SpecificPitchClassField, SpecificPitchClass),
            (HarmonyLabelField, HarmonyLabel),
            (PitchBasedHarmonyField, PitchBasedHarmony),
            (WesternTertianHarmonyField, WesternTertianHarmony),
            (RomanNumeralHarmonyField, RomanNumeralHarmony),
            (DcmlHarmonyField, DcmlHarmony),
        ],
    )
    def test_scalar_cls_is_resolved(
        self, field_cls: type[SemanticField], scalar_cls: type
    ) -> None:
        assert field_cls.scalar_cls is scalar_cls

    @pytest.mark.parametrize(
        "field_cls,scalar_cls",
        [
            (EnharmonicPitchField, EnharmonicPitch),
            (SpecificPitchField, SpecificPitch),
            (DcmlHarmonyField, DcmlHarmony),
            (HarmonyLabelField, HarmonyLabel),
        ],
    )
    def test_pa_schema_matches_derived_struct(
        self, field_cls: type[SemanticField], scalar_cls: type
    ) -> None:
        assert field_cls.pa_schema.equals(derive_arrow_struct(scalar_cls))


# ---------------------------------------------------------------------------
# EnharmonicPitchField — canonical {midi_number} struct
# ---------------------------------------------------------------------------


class TestEnharmonicPitchField:
    def test_pa_schema_shape(self) -> None:
        schema = EnharmonicPitchField.pa_schema
        assert pa.types.is_struct(schema)
        assert schema.num_fields == 1
        assert schema.field(0).name == "midi_number"
        assert schema.field(0).type == pa.int64()

    def test_from_field_and_getitem(self) -> None:
        arr = pa.array(
            [{"midi_number": 60}, {"midi_number": 72}, None],
            type=EnharmonicPitchField.pa_schema,
        )
        pa_field = pa.field("midi_pitch", EnharmonicPitchField.pa_schema)
        ef = EnharmonicPitchField.from_field((arr, pa_field))
        assert ef[0] == EnharmonicPitch(60)
        assert ef[1] == EnharmonicPitch(72)
        assert ef[2] is None

    def test_matches_pa_field_by_shape(self) -> None:
        pa_field = pa.field("midi_pitch", EnharmonicPitchField.pa_schema)
        assert EnharmonicPitchField.matches_pa_field(pa_field) is True

    def test_matches_pa_field_rejects_coordinate(self) -> None:
        coord = pa.field(
            "start",
            pa.struct(
                [
                    pa.field("value", pa.float64()),
                    pa.field("numerator", pa.int64()),
                    pa.field("denominator", pa.int64()),
                ]
            ),
        )
        assert EnharmonicPitchField.matches_pa_field(coord) is False


# ---------------------------------------------------------------------------
# SpecificPitchField — canonical {step, alter, octave, cents} struct
# ---------------------------------------------------------------------------


class TestSpecificPitchField:
    def test_pa_schema_shape(self) -> None:
        schema = SpecificPitchField.pa_schema
        names = [schema.field(i).name for i in range(schema.num_fields)]
        assert names == ["step", "alter", "octave", "cents"]
        assert schema.field("step").type == pa.string()
        assert schema.field("alter").type == pa.int64()
        assert schema.field("octave").type == pa.int64()
        assert schema.field("cents").type == pa.float64()

    def test_from_field_and_getitem(self) -> None:
        arr = pa.array(
            [
                {"step": "C", "alter": 1, "octave": 4, "cents": 0.0},
                {"step": "G", "alter": 0, "octave": 3, "cents": 0.0},
                None,
            ],
            type=SpecificPitchField.pa_schema,
        )
        pa_field = pa.field("specific_pitch", SpecificPitchField.pa_schema)
        sf = SpecificPitchField.from_field((arr, pa_field))
        s0 = sf[0]
        assert s0 is not None
        assert s0.step == "C" and s0.alter == 1 and s0.octave == 4
        s1 = sf[1]
        assert s1 is not None
        assert s1.step == "G" and s1.alter == 0 and s1.octave == 3
        assert sf[2] is None

    def test_matches_pa_field_rejects_enharmonic(self) -> None:
        ep_field = pa.field("midi_pitch", EnharmonicPitchField.pa_schema)
        assert SpecificPitchField.matches_pa_field(ep_field) is False


# ---------------------------------------------------------------------------
# Blueprint mode — XField(source_fields="name")
# ---------------------------------------------------------------------------


class TestBlueprintMode:
    def test_blueprint_construction(self) -> None:
        bp = EnharmonicPitchField(source_fields="midi_pitch")
        assert bp.is_blueprint is True
        assert bp._blueprint_source_fields == "midi_pitch"

    def test_live_construction_not_blueprint(self) -> None:
        arr = pa.array([{"midi_number": 60}], type=EnharmonicPitchField.pa_schema)
        pa_field = pa.field("midi_pitch", EnharmonicPitchField.pa_schema)
        ef = EnharmonicPitchField.from_field((arr, pa_field))
        assert ef.is_blueprint is False


# ---------------------------------------------------------------------------
# Harmony field surface — paired-class construction and materialisation
# ---------------------------------------------------------------------------


class TestDcmlHarmonyField:
    """The DCML import shape (DcmlStorageSchema) maps through scalar.from_row."""

    def test_dcml_import_shape_round_trip(self) -> None:
        arr = pa.array(
            [
                {
                    "label": "V65",
                    "globalkey": "C",
                    "localkey": "I",
                    "numeral": "V",
                    "form": "M",
                    "figbass": "65",
                    "chord_type": "M",
                    "root": 7,
                    "bass_note": 11,
                }
            ],
            type=DcmlStorageSchema.schema,
        )
        # Scalar.from_row maps the DCML import shape; this is the only
        # supported way to reconstruct DcmlHarmony from external format.
        h = DcmlHarmony.from_row(arr[0].as_py())
        assert h is not None
        assert h.label == "V65"
        assert h.numeral == "V"
        assert h.inversion == 1


class TestWesternTertianHarmonyField:
    def test_construction_via_paired_field(self) -> None:
        # Use the canonical pydantic-derived shape, not the legacy
        # WesternTertianSchema (which is the *import* edge for external
        # data, accessed through WesternTertianHarmony.from_row).
        arr = pa.array(
            [
                {
                    "label": "CM",
                    "standard": "chord_symbol",
                    "root": 0,
                    "bass": 0,
                    "chord_type": "M",
                    "inversion": 0,
                }
            ],
            type=WesternTertianHarmonyField.pa_schema,
        )
        pa_field = pa.field("harmony", WesternTertianHarmonyField.pa_schema)
        wf = WesternTertianHarmonyField.from_field((arr, pa_field))
        scalar = wf[0]
        assert isinstance(scalar, WesternTertianHarmony)
        assert scalar.label == "CM"


class TestRomanNumeralHarmonyField:
    def test_construction_via_paired_field(self) -> None:
        arr = pa.array(
            [
                {
                    "label": "I",
                    "standard": "roman_numeral",
                    "root": 0,
                    "bass": 0,
                    "chord_type": "M",
                    "inversion": 0,
                    "numeral": "I",
                    "localkey": "I",
                    "globalkey": "C",
                }
            ],
            type=RomanNumeralHarmonyField.pa_schema,
        )
        pa_field = pa.field("harmony", RomanNumeralHarmonyField.pa_schema)
        rf = RomanNumeralHarmonyField.from_field((arr, pa_field))
        scalar = rf[0]
        assert isinstance(scalar, RomanNumeralHarmony)
        assert scalar.numeral == "I"


# ---------------------------------------------------------------------------
# figbass_to_inversion — the harmony import helper
# ---------------------------------------------------------------------------


class TestFigbassToInversion:
    @pytest.mark.parametrize(
        "figbass,expected",
        [
            ("", 0),
            ("6", 1),
            ("64", 2),
            ("65", 1),
            ("43", 2),
            ("2", 3),
            ("42", 3),
            ("7", 0),
        ],
    )
    def test_known_figbass(self, figbass: str, expected: int) -> None:
        result = figbass_to_inversion(figbass)
        assert result is not None
        assert int(result) == expected

    def test_unknown_returns_none(self) -> None:
        assert figbass_to_inversion("unknown_figbass") is None


# ---------------------------------------------------------------------------
# Parquet round-trip — paired fields preserve scalars
# ---------------------------------------------------------------------------


class TestParquetRoundTrip:
    def test_enharmonic_pitch_round_trip(self, tmp_path) -> None:
        arr = pa.array(
            [{"midi_number": 60}, {"midi_number": 72}],
            type=EnharmonicPitchField.pa_schema,
        )
        pa_field = pa.field(
            "midi_pitch",
            EnharmonicPitchField.pa_schema,
            metadata={
                TIMETOALIGN_METADATA_KEY: b'{"field_type":"EnharmonicPitchField"}'
            },
        )
        table = pa.Table.from_arrays([arr], schema=pa.schema([pa_field]))

        path = tmp_path / "epitch.parquet"
        pq.write_table(table, path)
        loaded = pq.read_table(path)

        loaded_field = loaded.schema.field("midi_pitch")
        assert loaded_field.metadata is not None
        meta_bytes = loaded_field.metadata[TIMETOALIGN_METADATA_KEY]
        meta = json.loads(meta_bytes)
        assert meta["field_type"] == "EnharmonicPitchField"

        ef = EnharmonicPitchField.from_field(
            (loaded.column("midi_pitch"), loaded_field)
        )
        assert ef[0] == EnharmonicPitch(60)
        assert ef[1] == EnharmonicPitch(72)
