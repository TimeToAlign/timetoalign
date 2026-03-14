"""Tests for fields/harmony.py -- HarmonyField construction, access, and serialization."""

from __future__ import annotations

import json

import pyarrow as pa
import pyarrow.parquet as pq

from timetoalign.core.protocols import HarmonyLike, SemanticTypeLike
from timetoalign.core.scalars.harmony import Harmony
from timetoalign.fields.base import StructField
from timetoalign.fields.harmony import HarmonyField

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HARMONY_TYPE = pa.struct(
    [
        pa.field("label", pa.string(), nullable=True),
        pa.field("globalkey", pa.string(), nullable=True),
        pa.field("localkey", pa.string(), nullable=True),
        pa.field("numeral", pa.string(), nullable=True),
        pa.field("form", pa.string(), nullable=True),
        pa.field("figbass", pa.string(), nullable=True),
        pa.field("chord_type", pa.string(), nullable=True),
        pa.field("root", pa.int64(), nullable=True),
        pa.field("bass_note", pa.int64(), nullable=True),
    ]
)


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


# ---------------------------------------------------------------------------
# Protocol Conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """Verify HarmonyField satisfies HarmonyLike and SemanticTypeLike."""

    def test_harmony_scalar_satisfies_harmonylike(self) -> None:
        """isinstance(Harmony(...), HarmonyLike) is True."""
        h = Harmony(
            label="i",
            globalkey="c",
            localkey="i",
            numeral="i",
            form="",
            figbass="",
            chord_type="m",
            root=0,
            bass_note=0,
        )
        assert isinstance(h, HarmonyLike)

    def test_harmony_field_satisfies_semantic_type_like(self) -> None:
        """isinstance(HarmonyField(...), SemanticTypeLike) is True."""
        arr = _make_harmony_array()
        hf = HarmonyField.from_field(arr)
        assert isinstance(hf, SemanticTypeLike)

    def test_harmony_field_semantic_type(self) -> None:
        """HarmonyField.semantic_type == 'Harmony'."""
        arr = _make_harmony_array()
        hf = HarmonyField.from_field(arr)
        assert hf.semantic_type == "Harmony"


# ---------------------------------------------------------------------------
# Construction (from_field)
# ---------------------------------------------------------------------------


class TestConstruction:
    """Tests for HarmonyField.from_field() with various source types."""

    def test_from_pa_array(self) -> None:
        """Construct from pa.Array (struct array)."""
        arr = _make_harmony_array()
        hf = HarmonyField.from_field(arr)
        assert len(hf) == 3

    def test_from_struct_field(self) -> None:
        """Construct from an existing StructField."""
        arr = _make_harmony_array()
        pa_field = pa.field("harmony", _HARMONY_TYPE)
        sf = StructField(arr, pa_field)
        hf = HarmonyField.from_field(sf)
        assert len(hf) == 3

    def test_from_pa_field_schema_only(self) -> None:
        """Construct from pa.Field (no data), verify is_empty."""
        meta_dict = {"field_type": "HarmonyField", "standard": "dcml"}
        pa_field = pa.field(
            "harmony",
            _HARMONY_TYPE,
            metadata={b"timetoalign": json.dumps(meta_dict).encode()},
        )
        hf = HarmonyField.from_field(pa_field)
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
        hf = HarmonyField.from_field((arr, pa_field))
        assert len(hf) == 3


# ---------------------------------------------------------------------------
# Element Access (__getitem__)
# ---------------------------------------------------------------------------


class TestElementAccess:
    """Tests for HarmonyField.__getitem__."""

    def test_getitem_returns_harmony(self) -> None:
        """Verify returns Harmony instance with correct values."""
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
        hf = HarmonyField.from_field(arr)
        h = hf[0]
        assert isinstance(h, Harmony)
        assert h.label == "c.i"
        assert h.globalkey == "c"
        assert h.numeral == "i"
        assert h.chord_type == "m"

    def test_getitem_multiple_elements(self) -> None:
        """Iterate several elements, verify each."""
        arr = _make_harmony_array()
        hf = HarmonyField.from_field(arr)

        h0 = hf[0]
        assert h0 is not None
        assert h0.label == "c.i"
        assert h0.numeral == "i"

        h1 = hf[1]
        assert h1 is not None
        assert h1.label == "V65"
        assert h1.numeral == "V"
        assert h1.figbass == "65"

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
        hf = HarmonyField.from_field(arr)
        assert hf[0] is not None
        assert hf[1] is None


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    """Tests for HarmonyField properties."""

    def test_semantic_type_harmony(self) -> None:
        """HarmonyField.semantic_type == 'Harmony'."""
        arr = _make_harmony_array()
        hf = HarmonyField.from_field(arr)
        assert hf.semantic_type == "Harmony"

    def test_metadata_dict(self) -> None:
        """Verify returns dict with field_type and standard."""
        arr = _make_harmony_array()
        hf = HarmonyField.from_field(arr)
        md = hf.metadata_dict()
        assert md["field_type"] == "HarmonyField"
        assert md["standard"] == "dcml"


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    """Tests for HarmonyField serialization."""

    def test_to_field_injects_metadata(self) -> None:
        """Verify to_field() produces pa.Field with b'timetoalign' JSON blob."""
        arr = _make_harmony_array()
        hf = HarmonyField.from_field(arr)
        pa_field = hf.to_field()

        assert isinstance(pa_field, pa.Field)
        raw_meta = pa_field.metadata
        assert b"timetoalign" in raw_meta
        blob = json.loads(raw_meta[b"timetoalign"].decode("utf-8"))
        assert blob["field_type"] == "HarmonyField"
        assert blob["standard"] == "dcml"

    def test_parquet_round_trip(self, tmp_path: object) -> None:
        """Write pa.Table with HarmonyField column, read back, verify data + metadata."""
        from pathlib import Path

        tmp_dir = Path(str(tmp_path))
        parquet_path = tmp_dir / "harmonies.parquet"

        # Build HarmonyField
        arr = _make_harmony_array()
        hf = HarmonyField.from_field(arr)

        # Build table using the enriched pa.Field
        enriched_field = hf.to_field()
        table = pa.table(
            {"harmony": arr},
            schema=pa.schema([enriched_field.with_name("harmony")]),
        )

        # Write and read back
        pq.write_table(table, str(parquet_path))
        table_back = pq.read_table(str(parquet_path))

        # Reconstruct HarmonyField from the read-back table
        col = table_back.column("harmony")
        field = table_back.schema.field("harmony")
        hf2 = HarmonyField.from_field((col, field))

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
        hf = HarmonyField.from_field(arr)
        raw = hf.value
        assert isinstance(raw, StructField)

    def test_len_delegation(self) -> None:
        """Verify len() passes through to inner StructField."""
        arr = _make_harmony_array()
        hf = HarmonyField.from_field(arr)
        assert len(hf) == 3

    def test_is_empty_delegation(self) -> None:
        """Verify is_empty passes through for schema-only field."""
        meta_dict = {"field_type": "HarmonyField", "standard": "dcml"}
        pa_field = pa.field(
            "harmony",
            _HARMONY_TYPE,
            metadata={b"timetoalign": json.dumps(meta_dict).encode()},
        )
        hf = HarmonyField.from_field(pa_field)
        assert hf.is_empty is True

    def test_name_delegation(self) -> None:
        """Verify .name passes through to inner StructField."""
        arr = _make_harmony_array()
        pa_field = pa.field("my_harmony", _HARMONY_TYPE)
        sf = StructField(arr, pa_field)
        hf = HarmonyField.from_field(sf)
        assert hf.name == "my_harmony"

    def test_field_names_delegation(self) -> None:
        """Verify .field_names works via __getattr__ delegation."""
        arr = _make_harmony_array()
        hf = HarmonyField.from_field(arr)
        assert "label" in hf.field_names
        assert "numeral" in hf.field_names
        assert "chord_type" in hf.field_names
