"""Tests for SemanticFieldAccessMixin and domain mixins."""

from __future__ import annotations

import json

import pyarrow as pa
import pytest

from timetoalign.fields.harmony import (
    DCML_LABEL_STRUCT_TYPE,
    WESTERN_TERTIAN_STRUCT_TYPE,
    DcmlLabelField,
    HarmonyField,
    WesternTertianHarmonyField,
)
from timetoalign.fields.pitch import (
    EnharmonicPitchField,
    PitchField,
    SpecificPitchField,
)
from timetoalign.loader.mixins import (
    HarmonyAccessMixin,
    MeasureAccessMixin,
    PitchAccessMixin,
    SemanticFieldAccessMixin,
)

_TIMETOALIGN_KEY = b"timetoalign"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _inject_metadata(pa_field: pa.Field, field_type: str, **extra: str) -> pa.Field:
    """Return a copy of *pa_field* with timetoalign metadata injected."""
    meta = {"field_type": field_type, **extra}
    blob = json.dumps(meta).encode("utf-8")
    existing = pa_field.metadata or {}
    merged = {**existing, _TIMETOALIGN_KEY: blob}
    return pa_field.with_metadata(merged)


def _make_midi_pitch_table() -> pa.Table:
    """Build a table with a midi_pitch column carrying SpecificPitchField metadata."""
    midi_type = pa.struct([pa.field("ep", pa.int64()), pa.field("epc", pa.int64())])
    arr = pa.array([{"ep": 60, "epc": 0}, {"ep": 64, "epc": 4}], type=midi_type)
    col_field = _inject_metadata(
        pa.field("midi_pitch", midi_type), "SpecificPitchField", pitch_type="midi"
    )
    return pa.table({"midi_pitch": arr}, schema=pa.schema([col_field]))


def _make_spelled_pitch_table() -> pa.Table:
    """Build a table with a spelled_pitch column carrying EnharmonicPitchField metadata."""
    spelled_type = pa.struct(
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
            }
        ],
        type=spelled_type,
    )
    col_field = _inject_metadata(
        pa.field("spelled_pitch", spelled_type),
        "EnharmonicPitchField",
        pitch_type="spelled",
    )
    return pa.table({"spelled_pitch": arr}, schema=pa.schema([col_field]))


def _make_both_pitch_table() -> pa.Table:
    """Build a table with both midi_pitch and spelled_pitch columns."""
    midi_type = pa.struct([pa.field("ep", pa.int64()), pa.field("epc", pa.int64())])
    midi_arr = pa.array([{"ep": 60, "epc": 0}], type=midi_type)
    midi_field = _inject_metadata(
        pa.field("midi_pitch", midi_type), "SpecificPitchField", pitch_type="midi"
    )

    spelled_type = pa.struct(
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
    spelled_arr = pa.array(
        [
            {
                "gpc_int": 0,
                "gpc_str": "C",
                "acc": 0,
                "spc_int": 0,
                "spc_str": "C",
                "sp": "C4",
                "cents": 0.0,
            }
        ],
        type=spelled_type,
    )
    spelled_field = _inject_metadata(
        pa.field("spelled_pitch", spelled_type),
        "EnharmonicPitchField",
        pitch_type="spelled",
    )

    schema = pa.schema([midi_field, spelled_field])
    return pa.table(
        {"midi_pitch": midi_arr, "spelled_pitch": spelled_arr}, schema=schema
    )


def _make_dcml_harmony_table() -> pa.Table:
    """Build a table with a harmony column carrying DcmlLabelField metadata."""
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
        type=DCML_LABEL_STRUCT_TYPE,
    )
    # DcmlLabelField stores field_type as "HarmonyField" (backward compat)
    col_field = _inject_metadata(
        pa.field("harmony", DCML_LABEL_STRUCT_TYPE), "HarmonyField", standard="dcml"
    )
    return pa.table({"harmony": arr}, schema=pa.schema([col_field]))


def _make_western_harmony_table() -> pa.Table:
    """Build a table with a Western tertian harmony column."""
    arr = pa.array(
        [
            {
                "label": "CM",
                "standard": "chord_symbol",
                "root": 0,
                "bass": 0,
                "chord_quality": "M",
                "inversion": 0,
            }
        ],
        type=WESTERN_TERTIAN_STRUCT_TYPE,
    )
    col_field = _inject_metadata(
        pa.field("harmony", WESTERN_TERTIAN_STRUCT_TYPE),
        "WesternTertianHarmonyField",
        standard="chord_symbol",
    )
    return pa.table({"harmony": arr}, schema=pa.schema([col_field]))


# Simple host class that provides _table for the mixins
class _MixinHost(SemanticFieldAccessMixin):
    def __init__(self, table: pa.Table) -> None:
        self._table = table


class _PitchHost(PitchAccessMixin):
    def __init__(self, table: pa.Table) -> None:
        self._table = table


class _HarmonyHost(HarmonyAccessMixin):
    def __init__(self, table: pa.Table) -> None:
        self._table = table


# ---------------------------------------------------------------------------
# SemanticFieldAccessMixin tests
# ---------------------------------------------------------------------------


class TestSemanticFieldAccessMixin:
    """Tests for SemanticFieldAccessMixin.get_field / get_fields / has_field."""

    def test_get_field_returns_specific_pitch(self) -> None:
        table = _make_midi_pitch_table()
        host = _MixinHost(table)
        result = host.get_field(SpecificPitchField)
        assert isinstance(result, SpecificPitchField)

    def test_get_field_returns_enharmonic_pitch(self) -> None:
        table = _make_spelled_pitch_table()
        host = _MixinHost(table)
        result = host.get_field(EnharmonicPitchField)
        assert isinstance(result, EnharmonicPitchField)

    def test_get_field_parent_type_matches_subclass(self) -> None:
        """Requesting PitchField (parent) should match SpecificPitchField (child)."""
        table = _make_midi_pitch_table()
        host = _MixinHost(table)
        result = host.get_field(PitchField)
        assert isinstance(result, SpecificPitchField)

    def test_get_field_raises_on_no_match(self) -> None:
        # Table with no pitch metadata
        table = pa.table({"x": pa.array([1, 2, 3])})
        host = _MixinHost(table)
        with pytest.raises(KeyError, match="No column matching"):
            host.get_field(PitchField)

    def test_get_fields_returns_all_matches(self) -> None:
        table = _make_both_pitch_table()
        host = _MixinHost(table)
        results = host.get_fields(PitchField)
        assert len(results) == 2
        types = {type(r) for r in results}
        assert SpecificPitchField in types
        assert EnharmonicPitchField in types

    def test_get_fields_empty_on_no_match(self) -> None:
        table = pa.table({"x": pa.array([1, 2, 3])})
        host = _MixinHost(table)
        results = host.get_fields(PitchField)
        assert results == []

    def test_has_field_true(self) -> None:
        table = _make_midi_pitch_table()
        host = _MixinHost(table)
        assert host.has_field(PitchField) is True
        assert host.has_field(SpecificPitchField) is True

    def test_has_field_false(self) -> None:
        table = pa.table({"x": pa.array([1, 2, 3])})
        host = _MixinHost(table)
        assert host.has_field(PitchField) is False

    def test_has_field_specific_type_false_when_different(self) -> None:
        table = _make_midi_pitch_table()
        host = _MixinHost(table)
        assert host.has_field(EnharmonicPitchField) is False

    def test_get_field_harmony(self) -> None:
        table = _make_dcml_harmony_table()
        host = _MixinHost(table)
        result = host.get_field(DcmlLabelField)
        assert isinstance(result, DcmlLabelField)

    def test_get_field_harmony_parent_type(self) -> None:
        """Requesting HarmonyField (parent) should match DcmlLabelField (child)."""
        table = _make_dcml_harmony_table()
        host = _MixinHost(table)
        result = host.get_field(HarmonyField)
        assert isinstance(result, DcmlLabelField)

    def test_get_field_data_access(self) -> None:
        """Verify the reconstructed field gives access to element data."""
        table = _make_midi_pitch_table()
        host = _MixinHost(table)
        field = host.get_field(SpecificPitchField)
        assert len(field) == 2
        pitch = field[0]
        assert pitch is not None
        assert pitch.midi_number == 60
        assert pitch.pitch_class == 0


# ---------------------------------------------------------------------------
# PitchAccessMixin tests
# ---------------------------------------------------------------------------


class TestPitchAccessMixin:
    """Tests for PitchAccessMixin.get_pitch_field."""

    def test_get_pitch_field_with_type(self) -> None:
        table = _make_midi_pitch_table()
        host = _PitchHost(table)
        result = host.get_pitch_field(SpecificPitchField)
        assert isinstance(result, SpecificPitchField)

    def test_get_pitch_field_default_priority_enharmonic(self) -> None:
        """When both midi and spelled are present, default picks EnharmonicPitchField."""
        table = _make_both_pitch_table()
        host = _PitchHost(table)
        result = host.get_pitch_field()
        assert isinstance(result, EnharmonicPitchField)

    def test_get_pitch_field_default_only_midi(self) -> None:
        """When only midi is present, default picks SpecificPitchField."""
        table = _make_midi_pitch_table()
        host = _PitchHost(table)
        result = host.get_pitch_field()
        assert isinstance(result, SpecificPitchField)

    def test_get_pitch_field_default_only_spelled(self) -> None:
        """When only spelled is present, default picks EnharmonicPitchField."""
        table = _make_spelled_pitch_table()
        host = _PitchHost(table)
        result = host.get_pitch_field()
        assert isinstance(result, EnharmonicPitchField)

    def test_get_pitch_field_raises_no_pitch(self) -> None:
        table = pa.table({"x": pa.array([1])})
        host = _PitchHost(table)
        with pytest.raises(KeyError, match="No pitch field"):
            host.get_pitch_field()


# ---------------------------------------------------------------------------
# HarmonyAccessMixin tests
# ---------------------------------------------------------------------------


class TestHarmonyAccessMixin:
    """Tests for HarmonyAccessMixin.get_harmony_field."""

    def test_get_harmony_field_with_type(self) -> None:
        table = _make_dcml_harmony_table()
        host = _HarmonyHost(table)
        result = host.get_harmony_field(DcmlLabelField)
        assert isinstance(result, DcmlLabelField)

    def test_get_harmony_field_default_dcml(self) -> None:
        table = _make_dcml_harmony_table()
        host = _HarmonyHost(table)
        result = host.get_harmony_field()
        assert isinstance(result, DcmlLabelField)

    def test_get_harmony_field_default_western(self) -> None:
        table = _make_western_harmony_table()
        host = _HarmonyHost(table)
        result = host.get_harmony_field()
        assert isinstance(result, WesternTertianHarmonyField)

    def test_get_harmony_field_raises_no_harmony(self) -> None:
        table = pa.table({"x": pa.array([1])})
        host = _HarmonyHost(table)
        with pytest.raises(KeyError, match="No harmony field"):
            host.get_harmony_field()

    def test_get_harmony_field_data_access(self) -> None:
        """Verify the reconstructed harmony field gives access to element data."""
        table = _make_dcml_harmony_table()
        host = _HarmonyHost(table)
        field = host.get_harmony_field()
        assert len(field) == 1
        harmony = field[0]
        assert harmony is not None
        assert harmony.label == "V65"


# ---------------------------------------------------------------------------
# MeasureAccessMixin tests
# ---------------------------------------------------------------------------


class TestMeasureAccessMixin:
    """Tests for MeasureAccessMixin.get_measure_field (placeholder)."""

    def test_get_measure_field_raises(self) -> None:
        table = pa.table({"x": pa.array([1])})

        class _MeasureHost(MeasureAccessMixin):
            def __init__(self, t: pa.Table) -> None:
                self._table = t

        host = _MeasureHost(table)
        with pytest.raises(
            NotImplementedError, match="MeasureField is not yet defined"
        ):
            host.get_measure_field()


# ---------------------------------------------------------------------------
# Integration with EventData
# ---------------------------------------------------------------------------


class TestEventDataComposition:
    """Tests verifying the mixins compose correctly with EventData subclasses."""

    def test_note_event_data_has_pitch_access(self) -> None:
        """NoteEventData should have get_pitch_field, has_field, get_field."""
        from timetoalign.loader.score.stores.notes import NoteEventData

        assert hasattr(NoteEventData, "get_pitch_field")
        assert hasattr(NoteEventData, "has_field")
        assert hasattr(NoteEventData, "get_field")
        assert hasattr(NoteEventData, "get_fields")

    def test_measure_data_has_measure_access(self) -> None:
        """MeasureData should have get_measure_field."""
        from timetoalign.loader.score.stores.measures import MeasureData

        assert hasattr(MeasureData, "get_measure_field")
        assert hasattr(MeasureData, "has_field")

    def test_annotation_event_data_has_harmony_access(self) -> None:
        """AnnotationEventData should have get_harmony_field."""
        from timetoalign.loader.score.stores.annotations import AnnotationEventData

        assert hasattr(AnnotationEventData, "get_harmony_field")
        assert hasattr(AnnotationEventData, "has_field")

    def test_note_event_data_pitch_field_backward_compat(self) -> None:
        """NoteEventData.pitch_field property should still work via fallback."""
        from timetoalign.loader.score.stores.notes import NoteEventData

        store = NoteEventData.from_dicts(
            [
                {
                    "event_type": "Note",
                    "start": 0.0,
                    "duration": 1.0,
                    "midi_pitch": {"ep": 60, "epc": 0},
                }
            ],
        )
        pf = store.pitch_field
        assert isinstance(pf, SpecificPitchField)
        assert pf[0] is not None
        assert pf[0].midi_number == 60

    def test_note_event_data_spelled_pitch_field_backward_compat(self) -> None:
        """NoteEventData.spelled_pitch_field property should still work via fallback."""
        from timetoalign.loader.score.stores.notes import NoteEventData

        store = NoteEventData.from_dicts(
            [
                {
                    "event_type": "Note",
                    "start": 0.0,
                    "duration": 1.0,
                    "spelled_pitch": {
                        "gpc_int": 0,
                        "gpc_str": "C",
                        "acc": 0,
                        "spc_int": 0,
                        "spc_str": "C",
                        "sp": "C4",
                        "cents": 0.0,
                    },
                }
            ],
        )
        spf = store.spelled_pitch_field
        assert isinstance(spf, EnharmonicPitchField)
        assert spf[0] is not None
