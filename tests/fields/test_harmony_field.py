"""Tests for fields/harmony.py -- HarmonyField hierarchy construction, access, and serialization."""

from __future__ import annotations

import json

import pyarrow as pa
import pyarrow.parquet as pq

from timetoalign.core.protocols import DcmlHarmonyLike, SemanticTypeLike
from timetoalign.core.scalars.harmony import (
    DcmlHarmony,
    RomanNumeralHarmony,
    WesternTertianHarmony,
)
from timetoalign.fields.base import StructField
from timetoalign.fields.harmony import (
    DCML_LABEL_STRUCT_TYPE,
    ROMAN_NUMERAL_STRUCT_TYPE,
    WESTERN_TERTIAN_STRUCT_TYPE,
    DcmlLabelField,
    HarmonyField,
    RomanNumeralHarmonyField,
    WesternTertianHarmonyField,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HARMONY_TYPE = DCML_LABEL_STRUCT_TYPE


def _make_harmony_array(
    values: list[dict[str, str | int | None]] | None = None,
) -> pa.Array:
    """Build a DCML harmony struct array from simple dicts."""
    if values is None:
        values = [
            {
                "label": "c.i",
                "globalkey": "c",
                "localkey": "i",
                "numeral": "i",
                "form": "",
                "figbass": "",
                "chord_type": "m",
                "root": 0,
                "bass_note": 0,
            },
            {
                "label": "V65",
                "globalkey": "c",
                "localkey": "i",
                "numeral": "V",
                "form": "",
                "figbass": "65",
                "chord_type": "Mm7",
                "root": 1,
                "bass_note": 5,
            },
            {
                "label": "i",
                "globalkey": "c",
                "localkey": "i",
                "numeral": "i",
                "form": "",
                "figbass": "",
                "chord_type": "m",
                "root": 0,
                "bass_note": 0,
            },
        ]
    return pa.array(values, type=_HARMONY_TYPE)


def _make_western_tertian_array(
    values: list[dict[str, str | int | None]] | None = None,
) -> pa.Array:
    """Build a Western tertian harmony struct array from simple dicts."""
    if values is None:
        values = [
            {
                "label": "CM",
                "standard": "chord_symbol",
                "root": 0,
                "bass": 0,
                "chord_quality": "M",
                "inversion": 0,
            },
            {
                "label": "Fm",
                "standard": "chord_symbol",
                "root": 5,
                "bass": 5,
                "chord_quality": "m",
                "inversion": 0,
            },
        ]
    return pa.array(values, type=WESTERN_TERTIAN_STRUCT_TYPE)


def _make_roman_numeral_array(
    values: list[dict[str, str | int | None]] | None = None,
) -> pa.Array:
    """Build a Roman numeral harmony struct array from simple dicts."""
    if values is None:
        values = [
            {
                "label": "I",
                "standard": "roman_numeral",
                "root": 0,
                "bass": 0,
                "chord_quality": "M",
                "inversion": 0,
                "numeral": "I",
                "key_context": "C:I",
            },
            {
                "label": "V",
                "standard": "roman_numeral",
                "root": 7,
                "bass": 7,
                "chord_quality": "M",
                "inversion": 0,
                "numeral": "V",
                "key_context": "C:V",
            },
        ]
    return pa.array(values, type=ROMAN_NUMERAL_STRUCT_TYPE)


# ---------------------------------------------------------------------------
# Protocol Conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """Verify HarmonyField hierarchy satisfies protocols."""

    def test_harmony_scalar_satisfies_harmonylike(self) -> None:
        """isinstance(DcmlHarmony(...), DcmlHarmonyLike) is True."""
        h = DcmlHarmony(
            label="i",
            globalkey="c",
            localkey="i",
            numeral="i",
            chord_type="m",
            root=0,
            bass=0,
        )
        assert isinstance(h, DcmlHarmonyLike)

    def test_dcml_label_field_satisfies_semantic_type_like(self) -> None:
        """isinstance(DcmlLabelField(...), SemanticTypeLike) is True."""
        arr = _make_harmony_array()
        hf = DcmlLabelField.from_field(arr)
        assert isinstance(hf, SemanticTypeLike)

    def test_dcml_label_field_semantic_type(self) -> None:
        """DcmlLabelField.semantic_type == 'Harmony'."""
        arr = _make_harmony_array()
        hf = DcmlLabelField.from_field(arr)
        assert hf.semantic_type == "Harmony"


# ---------------------------------------------------------------------------
# Hierarchy / isinstance checks
# ---------------------------------------------------------------------------


class TestHierarchy:
    """Verify isinstance relationships across the hierarchy."""

    def test_dcml_label_field_is_harmony_field(self) -> None:
        """DcmlLabelField is a HarmonyField."""
        arr = _make_harmony_array()
        hf = DcmlLabelField.from_field(arr)
        assert isinstance(hf, HarmonyField)

    def test_western_tertian_is_harmony_field(self) -> None:
        """WesternTertianHarmonyField is a HarmonyField."""
        arr = _make_western_tertian_array()
        wf = WesternTertianHarmonyField.from_field(arr)
        assert isinstance(wf, HarmonyField)

    def test_roman_numeral_is_harmony_field(self) -> None:
        """RomanNumeralHarmonyField is a HarmonyField."""
        arr = _make_roman_numeral_array()
        rf = RomanNumeralHarmonyField.from_field(arr)
        assert isinstance(rf, HarmonyField)

    def test_roman_numeral_is_western_tertian(self) -> None:
        """RomanNumeralHarmonyField is a WesternTertianHarmonyField."""
        arr = _make_roman_numeral_array()
        rf = RomanNumeralHarmonyField.from_field(arr)
        assert isinstance(rf, WesternTertianHarmonyField)

    def test_dcml_label_field_is_not_western_tertian(self) -> None:
        """DcmlLabelField is NOT a WesternTertianHarmonyField (sibling, not child)."""
        arr = _make_harmony_array()
        hf = DcmlLabelField.from_field(arr)
        assert not isinstance(hf, WesternTertianHarmonyField)

    def test_harmony_field_is_abstract(self) -> None:
        """HarmonyField cannot be instantiated directly."""
        import pytest

        arr = _make_harmony_array()
        pa_field = pa.field("harmony", _HARMONY_TYPE)
        sf = StructField(arr, pa_field)
        with pytest.raises(TypeError):
            HarmonyField(sf)  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# Construction (from_field) -- DcmlLabelField
# ---------------------------------------------------------------------------


class TestConstruction:
    """Tests for DcmlLabelField.from_field() with various source types."""

    def test_from_pa_array(self) -> None:
        """Construct from pa.Array (struct array)."""
        arr = _make_harmony_array()
        hf = DcmlLabelField.from_field(arr)
        assert len(hf) == 3

    def test_from_struct_field(self) -> None:
        """Construct from an existing StructField."""
        arr = _make_harmony_array()
        pa_field = pa.field("harmony", _HARMONY_TYPE)
        sf = StructField(arr, pa_field)
        hf = DcmlLabelField.from_field(sf)
        assert len(hf) == 3

    def test_from_pa_field_schema_only(self) -> None:
        """Construct from pa.Field (no data), verify is_empty."""
        meta_dict = {"field_type": "HarmonyField", "standard": "dcml"}
        pa_field = pa.field(
            "harmony",
            _HARMONY_TYPE,
            metadata={b"timetoalign": json.dumps(meta_dict).encode()},
        )
        hf = DcmlLabelField.from_field(pa_field)
        assert hf.is_empty is True

    def test_from_tuple(self) -> None:
        """Construct from (pa.Array, pa.Field) tuple."""
        arr = _make_harmony_array()
        pa_field = pa.field(
            "harmony",
            _HARMONY_TYPE,
            metadata={
                b"timetoalign": json.dumps(
                    {"field_type": "HarmonyField", "standard": "dcml"}
                ).encode()
            },
        )
        hf = DcmlLabelField.from_field((arr, pa_field))
        assert len(hf) == 3


# ---------------------------------------------------------------------------
# Construction -- WesternTertianHarmonyField
# ---------------------------------------------------------------------------


class TestWesternTertianConstruction:
    """Tests for WesternTertianHarmonyField.from_field()."""

    def test_from_pa_array(self) -> None:
        """Construct from pa.Array (struct array)."""
        arr = _make_western_tertian_array()
        wf = WesternTertianHarmonyField.from_field(arr)
        assert len(wf) == 2

    def test_from_struct_field(self) -> None:
        """Construct from an existing StructField."""
        arr = _make_western_tertian_array()
        pa_field = pa.field("harmony", WESTERN_TERTIAN_STRUCT_TYPE)
        sf = StructField(arr, pa_field)
        wf = WesternTertianHarmonyField.from_field(sf)
        assert len(wf) == 2


# ---------------------------------------------------------------------------
# Construction -- RomanNumeralHarmonyField
# ---------------------------------------------------------------------------


class TestRomanNumeralConstruction:
    """Tests for RomanNumeralHarmonyField.from_field()."""

    def test_from_pa_array(self) -> None:
        """Construct from pa.Array (struct array)."""
        arr = _make_roman_numeral_array()
        rf = RomanNumeralHarmonyField.from_field(arr)
        assert len(rf) == 2

    def test_from_struct_field(self) -> None:
        """Construct from an existing StructField."""
        arr = _make_roman_numeral_array()
        pa_field = pa.field("harmony", ROMAN_NUMERAL_STRUCT_TYPE)
        sf = StructField(arr, pa_field)
        rf = RomanNumeralHarmonyField.from_field(sf)
        assert len(rf) == 2


# ---------------------------------------------------------------------------
# Element Access (__getitem__) -- DcmlLabelField
# ---------------------------------------------------------------------------


class TestElementAccess:
    """Tests for DcmlLabelField.__getitem__."""

    def test_getitem_returns_dcml_label(self) -> None:
        """Verify returns DcmlHarmony instance with correct values."""
        data = [
            {
                "label": "c.i",
                "globalkey": "c",
                "localkey": "i",
                "numeral": "i",
                "form": "",
                "figbass": "",
                "chord_type": "m",
                "root": 0,
                "bass_note": 0,
            }
        ]
        arr = _make_harmony_array(data)
        hf = DcmlLabelField.from_field(arr)
        h = hf[0]
        assert isinstance(h, DcmlHarmony)
        assert h.label == "c.i"
        assert h.globalkey == "c"
        assert h.numeral == "i"
        assert h.chord_type == "m"

    def test_getitem_multiple_elements(self) -> None:
        """Iterate several elements, verify each."""
        arr = _make_harmony_array()
        hf = DcmlLabelField.from_field(arr)

        h0 = hf[0]
        assert h0 is not None
        assert h0.label == "c.i"
        assert h0.numeral == "i"

        h1 = hf[1]
        assert h1 is not None
        assert h1.label == "V65"
        assert h1.numeral == "V"
        assert h1.inversion == 1  # figbass "65" -> inversion 1

    def test_getitem_null_returns_none(self) -> None:
        """Verify None for null struct entries."""
        arr = pa.array(
            [
                {
                    "label": "i",
                    "globalkey": "c",
                    "localkey": "i",
                    "numeral": "i",
                    "form": "",
                    "figbass": "",
                    "chord_type": "m",
                    "root": 0,
                    "bass_note": 0,
                },
                None,
            ],
            type=_HARMONY_TYPE,
        )
        hf = DcmlLabelField.from_field(arr)
        assert hf[0] is not None
        assert hf[1] is None


# ---------------------------------------------------------------------------
# Element Access (__getitem__) -- WesternTertianHarmonyField
# ---------------------------------------------------------------------------


class TestWesternTertianElementAccess:
    """Tests for WesternTertianHarmonyField.__getitem__."""

    def test_getitem_returns_western_tertian(self) -> None:
        """Verify returns WesternTertianHarmony instance."""
        arr = _make_western_tertian_array()
        wf = WesternTertianHarmonyField.from_field(arr)
        h = wf[0]
        assert isinstance(h, WesternTertianHarmony)
        assert h.label == "CM"
        assert h.root == 0
        assert h.bass == 0
        assert h.chord_type == "M"
        assert h.inversion == 0

    def test_getitem_null_returns_none(self) -> None:
        """Verify None for null struct entries."""
        arr = pa.array(
            [
                {
                    "label": "CM",
                    "standard": "chord_symbol",
                    "root": 0,
                    "bass": 0,
                    "chord_quality": "M",
                    "inversion": 0,
                },
                None,
            ],
            type=WESTERN_TERTIAN_STRUCT_TYPE,
        )
        wf = WesternTertianHarmonyField.from_field(arr)
        assert wf[0] is not None
        assert wf[1] is None


# ---------------------------------------------------------------------------
# Element Access (__getitem__) -- RomanNumeralHarmonyField
# ---------------------------------------------------------------------------


class TestRomanNumeralElementAccess:
    """Tests for RomanNumeralHarmonyField.__getitem__."""

    def test_getitem_returns_roman_numeral(self) -> None:
        """Verify returns RomanNumeralHarmony instance."""
        arr = _make_roman_numeral_array()
        rf = RomanNumeralHarmonyField.from_field(arr)
        h = rf[0]
        assert isinstance(h, RomanNumeralHarmony)
        assert h.label == "I"
        assert h.numeral == "I"
        assert h.root == 0
        assert h.chord_type == "M"

    def test_getitem_null_returns_none(self) -> None:
        """Verify None for null struct entries."""
        arr = pa.array(
            [
                {
                    "label": "I",
                    "standard": "roman_numeral",
                    "root": 0,
                    "bass": 0,
                    "chord_quality": "M",
                    "inversion": 0,
                    "numeral": "I",
                    "key_context": "C:I",
                },
                None,
            ],
            type=ROMAN_NUMERAL_STRUCT_TYPE,
        )
        rf = RomanNumeralHarmonyField.from_field(arr)
        assert rf[0] is not None
        assert rf[1] is None


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    """Tests for HarmonyField hierarchy properties."""

    def test_dcml_semantic_type_harmony(self) -> None:
        """DcmlLabelField.semantic_type == 'Harmony'."""
        arr = _make_harmony_array()
        hf = DcmlLabelField.from_field(arr)
        assert hf.semantic_type == "Harmony"

    def test_dcml_metadata_dict(self) -> None:
        """Verify DcmlLabelField returns dict with field_type and standard."""
        arr = _make_harmony_array()
        hf = DcmlLabelField.from_field(arr)
        md = hf.metadata_dict()
        assert md["field_type"] == "HarmonyField"
        assert md["standard"] == "dcml"

    def test_western_tertian_semantic_type(self) -> None:
        """WesternTertianHarmonyField.semantic_type == 'Harmony'."""
        arr = _make_western_tertian_array()
        wf = WesternTertianHarmonyField.from_field(arr)
        assert wf.semantic_type == "Harmony"

    def test_western_tertian_metadata_dict(self) -> None:
        """Verify WesternTertianHarmonyField metadata."""
        arr = _make_western_tertian_array()
        wf = WesternTertianHarmonyField.from_field(arr)
        md = wf.metadata_dict()
        assert md["field_type"] == "WesternTertianHarmonyField"
        assert md["standard"] == "chord_symbol"

    def test_roman_numeral_metadata_dict(self) -> None:
        """Verify RomanNumeralHarmonyField metadata."""
        arr = _make_roman_numeral_array()
        rf = RomanNumeralHarmonyField.from_field(arr)
        md = rf.metadata_dict()
        assert md["field_type"] == "RomanNumeralHarmonyField"
        assert md["standard"] == "roman_numeral"


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    """Tests for DcmlLabelField serialization."""

    def test_to_field_injects_metadata(self) -> None:
        """Verify to_field() produces pa.Field with b'timetoalign' JSON blob."""
        arr = _make_harmony_array()
        hf = DcmlLabelField.from_field(arr)
        pa_field = hf.to_field()

        assert isinstance(pa_field, pa.Field)
        raw_meta = pa_field.metadata
        assert b"timetoalign" in raw_meta
        blob = json.loads(raw_meta[b"timetoalign"].decode("utf-8"))
        assert blob["field_type"] == "HarmonyField"
        assert blob["standard"] == "dcml"

    def test_parquet_round_trip(self, tmp_path: object) -> None:
        """Write pa.Table with DcmlLabelField column, read back, verify data + metadata."""
        from pathlib import Path

        tmp_dir = Path(str(tmp_path))
        parquet_path = tmp_dir / "harmonies.parquet"

        # Build DcmlLabelField
        arr = _make_harmony_array()
        hf = DcmlLabelField.from_field(arr)

        # Build table using the enriched pa.Field
        enriched_field = hf.to_field()
        table = pa.table(
            {"harmony": arr},
            schema=pa.schema([enriched_field.with_name("harmony")]),
        )

        # Write and read back
        pq.write_table(table, str(parquet_path))
        table_back = pq.read_table(str(parquet_path))

        # Reconstruct DcmlLabelField from the read-back table
        col = table_back.column("harmony")
        field = table_back.schema.field("harmony")
        hf2 = DcmlLabelField.from_field((col, field))

        # Verify metadata survived
        assert hf2.semantic_type == "Harmony"

        # Verify data survived
        assert len(hf2) == 3
        h0 = hf2[0]
        assert h0 is not None
        assert h0.label == "c.i"
        assert h0.globalkey == "c"


# ---------------------------------------------------------------------------
# Delegation
# ---------------------------------------------------------------------------


class TestDelegation:
    """Tests for SemanticField delegation to the inner StructField."""

    def test_value_returns_struct_field(self) -> None:
        """Verify .value returns the inner StructField."""
        arr = _make_harmony_array()
        hf = DcmlLabelField.from_field(arr)
        raw = hf.value
        assert isinstance(raw, StructField)

    def test_len_delegation(self) -> None:
        """Verify len() passes through to inner StructField."""
        arr = _make_harmony_array()
        hf = DcmlLabelField.from_field(arr)
        assert len(hf) == 3

    def test_is_empty_delegation(self) -> None:
        """Verify is_empty passes through for schema-only field."""
        meta_dict = {"field_type": "HarmonyField", "standard": "dcml"}
        pa_field = pa.field(
            "harmony",
            _HARMONY_TYPE,
            metadata={b"timetoalign": json.dumps(meta_dict).encode()},
        )
        hf = DcmlLabelField.from_field(pa_field)
        assert hf.is_empty is True

    def test_name_delegation(self) -> None:
        """Verify .name passes through to inner StructField."""
        arr = _make_harmony_array()
        pa_field = pa.field("my_harmony", _HARMONY_TYPE)
        sf = StructField(arr, pa_field)
        hf = DcmlLabelField.from_field(sf)
        assert hf.name == "my_harmony"

    def test_field_names_delegation(self) -> None:
        """Verify .field_names works via __getattr__ delegation."""
        arr = _make_harmony_array()
        hf = DcmlLabelField.from_field(arr)
        assert "label" in hf.field_names
        assert "numeral" in hf.field_names
        assert "chord_type" in hf.field_names
