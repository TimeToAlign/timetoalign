"""Tests for SemanticFieldAccessMixin and domain mixins."""

from __future__ import annotations

import json

import pyarrow as pa
import pytest

from timetoalign.fields.harmony import (
    DcmlLabelField,
    HarmonyField,
    WesternTertianHarmonyField,
)
from timetoalign.fields.pitch import PitchField
from timetoalign.fields.schemas import (
    DcmlStorageSchema,
    WesternTertianSchema,
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
    """Build a table with a midi_pitch column carrying PitchField metadata."""
    midi_type = pa.struct([pa.field("ep", pa.int64()), pa.field("epc", pa.int64())])
    arr = pa.array([{"ep": 60, "epc": 0}, {"ep": 64, "epc": 4}], type=midi_type)
    col_field = _inject_metadata(
        pa.field("midi_pitch", midi_type),
        "PitchField",
        pitch_type="ep",
    )
    return pa.table({"midi_pitch": arr}, schema=pa.schema([col_field]))


def _make_specific_pitch_table() -> pa.Table:
    """Build a table with a specific_pitch column carrying PitchField metadata."""
    specific_type = pa.struct(
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
        type=specific_type,
    )
    col_field = _inject_metadata(
        pa.field("specific_pitch", specific_type),
        "PitchField",
        pitch_type="sp",
    )
    return pa.table({"specific_pitch": arr}, schema=pa.schema([col_field]))


def _make_both_pitch_table() -> pa.Table:
    """Build a table with both midi_pitch and specific_pitch columns."""
    midi_type = pa.struct([pa.field("ep", pa.int64()), pa.field("epc", pa.int64())])
    midi_arr = pa.array([{"ep": 60, "epc": 0}], type=midi_type)
    midi_field = _inject_metadata(
        pa.field("midi_pitch", midi_type),
        "PitchField",
        pitch_type="ep",
    )

    specific_type = pa.struct(
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
    specific_arr = pa.array(
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
        type=specific_type,
    )
    specific_field = _inject_metadata(
        pa.field("specific_pitch", specific_type),
        "PitchField",
        pitch_type="sp",
    )

    schema = pa.schema([midi_field, specific_field])
    return pa.table(
        {"midi_pitch": midi_arr, "specific_pitch": specific_arr}, schema=schema
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
        type=DcmlStorageSchema.schema,
    )
    # DcmlLabelField stores field_type as "HarmonyField" (backward compat)
    col_field = _inject_metadata(
        pa.field("harmony", DcmlStorageSchema.schema), "HarmonyField", standard="dcml"
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
        type=WesternTertianSchema.schema,
    )
    col_field = _inject_metadata(
        pa.field("harmony", WesternTertianSchema.schema),
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

    def test_get_field_returns_ep_pitch(self) -> None:
        table = _make_midi_pitch_table()
        host = _MixinHost(table)
        result = host.get_field(PitchField)
        assert isinstance(result, PitchField)
        assert result.pitch_type == "ep"

    def test_get_field_returns_sp_pitch(self) -> None:
        table = _make_specific_pitch_table()
        host = _MixinHost(table)
        result = host.get_field(PitchField)
        assert isinstance(result, PitchField)
        assert result.pitch_type == "sp"

    def test_get_field_parent_type_matches(self) -> None:
        """Requesting PitchField should match PitchField columns."""
        table = _make_midi_pitch_table()
        host = _MixinHost(table)
        result = host.get_field(PitchField)
        assert isinstance(result, PitchField)

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
        pitch_types = {r.pitch_type for r in results}
        assert "ep" in pitch_types
        assert "sp" in pitch_types

    def test_get_fields_empty_on_no_match(self) -> None:
        table = pa.table({"x": pa.array([1, 2, 3])})
        host = _MixinHost(table)
        results = host.get_fields(PitchField)
        assert results == []

    def test_has_field_true(self) -> None:
        table = _make_midi_pitch_table()
        host = _MixinHost(table)
        assert host.has_field(PitchField) is True

    def test_has_field_false(self) -> None:
        table = pa.table({"x": pa.array([1, 2, 3])})
        host = _MixinHost(table)
        assert host.has_field(PitchField) is False

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
        field = host.get_field(PitchField)
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
        result = host.get_pitch_field(PitchField)
        assert isinstance(result, PitchField)

    def test_get_pitch_field_default_priority_sp(self) -> None:
        """When both midi and specific are present, default picks SP (most informative)."""
        table = _make_both_pitch_table()
        host = _PitchHost(table)
        result = host.get_pitch_field()
        assert isinstance(result, PitchField)
        assert result.pitch_type == "sp"

    def test_get_pitch_field_default_only_midi(self) -> None:
        """When only midi is present, default picks EP."""
        table = _make_midi_pitch_table()
        host = _PitchHost(table)
        result = host.get_pitch_field()
        assert isinstance(result, PitchField)
        assert result.pitch_type == "ep"

    def test_get_pitch_field_default_only_specific(self) -> None:
        """When only specific is present, default picks SP."""
        table = _make_specific_pitch_table()
        host = _PitchHost(table)
        result = host.get_pitch_field()
        assert isinstance(result, PitchField)
        assert result.pitch_type == "sp"

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
        assert isinstance(pf, PitchField)
        assert pf[0] is not None
        assert pf[0].midi_number == 60

    def test_note_event_data_specific_pitch_field_backward_compat(self) -> None:
        """NoteEventData.specific_pitch_field property should still work via fallback."""
        from timetoalign.loader.score.stores.notes import NoteEventData

        store = NoteEventData.from_dicts(
            [
                {
                    "event_type": "Note",
                    "start": 0.0,
                    "duration": 1.0,
                    "specific_pitch": {
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
        spf = store.specific_pitch_field
        assert isinstance(spf, PitchField)
        assert spf[0] is not None

    def test_plain_event_data_has_field_access(self) -> None:
        """A plain EventData instance should expose get_field, get_fields, has_field."""
        from timetoalign.loader.events import EventData

        assert hasattr(EventData, "get_field")
        assert hasattr(EventData, "get_fields")
        assert hasattr(EventData, "has_field")

    def test_plain_event_data_get_field_with_metadata(self) -> None:
        """Plain EventData.get_field(PitchField) works when metadata is present."""
        from timetoalign.core import TimeUnit
        from timetoalign.loader.events import EventData

        # Create a minimal EventData with a pitch column carrying field metadata.
        store = EventData.from_dicts(
            [
                {
                    "event_type": "Note",
                    "start": 0.0,
                    "duration": 1.0,
                }
            ],
            unit=TimeUnit.seconds,
        )
        # Inject a pitch column with PitchField metadata onto the table.
        midi_type = pa.struct([pa.field("ep", pa.int64()), pa.field("epc", pa.int64())])
        pitch_arr = pa.array([{"ep": 60, "epc": 0}], type=midi_type)
        col_field = _inject_metadata(
            pa.field("midi_pitch", midi_type),
            "PitchField",
            pitch_type="ep",
        )
        new_table = store._table.append_column(col_field, pitch_arr)
        store._table = new_table

        result = store.get_field(PitchField)
        assert isinstance(result, PitchField)
        assert result[0] is not None
        assert result[0].midi_number == 60

    def test_plain_event_data_has_field_false_without_metadata(self) -> None:
        """Plain EventData.has_field returns False when no field metadata present."""
        from timetoalign.core import TimeUnit
        from timetoalign.loader.events import EventData

        store = EventData.from_dicts(
            [
                {
                    "event_type": "Beat",
                    "start": 0.0,
                }
            ],
            unit=TimeUnit.seconds,
        )
        assert store.has_field(PitchField) is False


# ---------------------------------------------------------------------------
# Field cache tests
# ---------------------------------------------------------------------------


class TestFieldCache:
    """Tests for the _field_cache on SemanticFieldAccessMixin."""

    def test_cache_returns_same_object(self) -> None:
        """Calling get_field twice returns the exact same object (identity)."""
        table = _make_midi_pitch_table()
        host = _MixinHost(table)
        result1 = host.get_field(PitchField)
        result2 = host.get_field(PitchField)
        assert result1 is result2

    def test_cache_independent_per_instance(self) -> None:
        """Two hosts with the same table have independent caches."""
        table = _make_midi_pitch_table()
        host_a = _MixinHost(table)
        host_b = _MixinHost(table)

        field_a = host_a.get_field(PitchField)
        field_b = host_b.get_field(PitchField)

        # Both should be PitchField but NOT the same object.
        assert isinstance(field_a, PitchField)
        assert isinstance(field_b, PitchField)
        assert field_a is not field_b

    def test_get_fields_populates_cache(self) -> None:
        """get_fields populates the cache; a second call returns the same objects."""
        table = _make_both_pitch_table()
        host = _MixinHost(table)

        first_call = host.get_fields(PitchField)
        second_call = host.get_fields(PitchField)

        assert len(first_call) == 2
        assert len(second_call) == 2
        for f1, f2 in zip(first_call, second_call):
            assert f1 is f2

    def test_has_field_after_get_field_uses_cache(self) -> None:
        """has_field still returns True after get_field has populated the cache."""
        table = _make_midi_pitch_table()
        host = _MixinHost(table)
        host.get_field(PitchField)
        assert host.has_field(PitchField) is True
