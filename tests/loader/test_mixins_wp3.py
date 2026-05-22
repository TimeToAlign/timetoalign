"""WP3 additions to the mixin test suite.

Covers:

* ``get_field(ScalarClass)`` — pydantic-scalar dispatch
* ``IdCoordinate`` vs ``Coordinate`` discrimination via metadata
* ``MultipleFieldsError`` on ambiguity + ``name=`` resolution
* ``get_fields_satisfying(ProtocolClass)`` — Protocol-based grouping

All tests build hand-crafted ``pa.Table`` instances and a thin
``_MixinHost`` wrapper that pins ``_table`` on the mixin, matching the
existing ``test_mixins.py`` test scaffolding.
"""

from __future__ import annotations

import json

import pyarrow as pa
import pytest

from timetoalign.core.events import (
    EnharmonicPitch,
    EnharmonicPitchClass,
    EnharmonicPitchField,
    SpecificPitch,
    SpecificPitchField,
)
from timetoalign.core.protocols import GenericPitchLike, TimeScalarLike
from timetoalign.core.time import (
    Coordinate,
    CoordinateField,
    Duration,
    DurationField,
    IdCoordinate,
    IdCoordinateField,
)
from timetoalign.loader.mixins import (
    MultipleFieldsError,
    SemanticFieldAccessMixin,
)

_TIMETOALIGN_KEY = b"timetoalign"


def _inject_metadata(pa_field: pa.Field, field_type: str, **extra: str) -> pa.Field:
    meta = {"field_type": field_type, **extra}
    blob = json.dumps(meta).encode("utf-8")
    existing = pa_field.metadata or {}
    merged = {**existing, _TIMETOALIGN_KEY: blob}
    return pa_field.with_metadata(merged)


class _MixinHost(SemanticFieldAccessMixin):
    def __init__(self, table: pa.Table) -> None:
        self._table = table


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _rational_struct() -> pa.StructType:
    return pa.struct(
        [
            pa.field("value", pa.float64(), nullable=True),
            pa.field("numerator", pa.int64(), nullable=True),
            pa.field("denominator", pa.int64(), nullable=True),
        ]
    )


def _make_coord_field(values: list[float]) -> pa.Array:
    return pa.array(
        [{"value": v, "numerator": None, "denominator": None} for v in values],
        type=_rational_struct(),
    )


def _make_table_with_coordinate_and_id_coordinate() -> pa.Table:
    """Build a table holding ONE Coordinate column and ONE IdCoordinate column.

    The two columns share the rational-struct shape; the
    ``b"timetoalign"`` ``field_type`` blob distinguishes them.
    """
    coord_arr = _make_coord_field([1.0, 2.0, 3.0])
    id_coord_arr = _make_coord_field([10.0, 20.0, 30.0])

    coord_field = _inject_metadata(
        pa.field("start", _rational_struct()),
        "CoordinateField",
        unit="seconds",
        domain="physical",
        number_type="float",
    )
    id_coord_field = _inject_metadata(
        pa.field("anchor", _rational_struct()),
        "IdCoordinateField",
        unit="seconds",
        domain="physical",
        number_type="float",
        timeline_id="tl-42",
    )

    schema = pa.schema([coord_field, id_coord_field])
    return pa.table({"start": coord_arr, "anchor": id_coord_arr}, schema=schema)


def _make_table_with_two_ep_columns() -> pa.Table:
    """Build a table with two EnharmonicPitch columns under different names."""
    ep_schema = EnharmonicPitchField.pa_schema
    arr_a = pa.array([{"midi_number": 60}], type=ep_schema)
    arr_b = pa.array([{"midi_number": 67}], type=ep_schema)
    field_a = _inject_metadata(pa.field("primary", ep_schema), "EnharmonicPitchField")
    field_b = _inject_metadata(pa.field("secondary", ep_schema), "EnharmonicPitchField")
    schema = pa.schema([field_a, field_b])
    return pa.table({"primary": arr_a, "secondary": arr_b}, schema=schema)


def _make_table_with_pitches_and_coordinates() -> pa.Table:
    """Build a table holding pitch (EP, SP) and time (Coordinate, Duration) columns."""
    coord_arr = _make_coord_field([1.0])
    dur_arr = _make_coord_field([2.5])
    ep_arr = pa.array([{"midi_number": 60}], type=EnharmonicPitchField.pa_schema)
    sp_arr = pa.array(
        [{"step": "C", "alter": 0, "octave": 4, "cents": None}],
        type=SpecificPitchField.pa_schema,
    )

    coord_field = _inject_metadata(
        pa.field("start", _rational_struct()),
        "CoordinateField",
        unit="quarters",
        domain="logical",
        number_type="float",
    )
    dur_field = _inject_metadata(
        pa.field("duration", _rational_struct()),
        "DurationField",
        unit="quarters",
        domain="logical",
        number_type="float",
    )
    ep_field = _inject_metadata(
        pa.field("midi_pitch", EnharmonicPitchField.pa_schema), "EnharmonicPitchField"
    )
    sp_field = _inject_metadata(
        pa.field("specific_pitch", SpecificPitchField.pa_schema), "SpecificPitchField"
    )
    schema = pa.schema([coord_field, dur_field, ep_field, sp_field])
    return pa.table(
        {
            "start": coord_arr,
            "duration": dur_arr,
            "midi_pitch": ep_arr,
            "specific_pitch": sp_arr,
        },
        schema=schema,
    )


# ---------------------------------------------------------------------------
# get_field(ScalarClass) — basic dispatch
# ---------------------------------------------------------------------------


class TestGetFieldByScalarClass:
    def test_lookup_by_pydantic_scalar(self) -> None:
        host = _MixinHost(_make_table_with_pitches_and_coordinates())
        result = host.get_field(EnharmonicPitch)
        assert isinstance(result, EnharmonicPitchField)
        assert result.name == "midi_pitch"

    def test_lookup_by_pydantic_scalar_specific_pitch(self) -> None:
        host = _MixinHost(_make_table_with_pitches_and_coordinates())
        result = host.get_field(SpecificPitch)
        assert isinstance(result, SpecificPitchField)
        assert result.name == "specific_pitch"

    def test_lookup_by_pydantic_scalar_coordinate(self) -> None:
        host = _MixinHost(_make_table_with_pitches_and_coordinates())
        result = host.get_field(Coordinate)
        assert isinstance(result, CoordinateField)
        assert result.name == "start"

    def test_lookup_by_pydantic_scalar_duration(self) -> None:
        host = _MixinHost(_make_table_with_pitches_and_coordinates())
        result = host.get_field(Duration)
        assert isinstance(result, DurationField)
        assert result.name == "duration"

    def test_unknown_scalar_raises(self) -> None:
        host = _MixinHost(_make_table_with_pitches_and_coordinates())
        with pytest.raises(KeyError):
            host.get_field(EnharmonicPitchClass)


# ---------------------------------------------------------------------------
# IdCoordinate vs Coordinate discrimination
# ---------------------------------------------------------------------------


class TestIdCoordinateDiscrimination:
    def test_id_coordinate_lookup_returns_only_id_field(self) -> None:
        host = _MixinHost(_make_table_with_coordinate_and_id_coordinate())
        result = host.get_field(IdCoordinate)
        assert isinstance(result, IdCoordinateField)
        assert result.name == "anchor"

    def test_coordinate_lookup_skips_id_coordinate(self) -> None:
        host = _MixinHost(_make_table_with_coordinate_and_id_coordinate())
        result = host.get_field(Coordinate)
        assert isinstance(result, CoordinateField)
        assert not isinstance(result, IdCoordinateField)
        assert result.name == "start"

    def test_coordinate_field_rejects_id_coordinate_field_metadata(self) -> None:
        """CoordinateField.matches_pa_field must NOT match an IdCoordinateField column."""
        table = _make_table_with_coordinate_and_id_coordinate()
        id_field = table.schema.field("anchor")
        assert not CoordinateField.matches_pa_field(id_field)
        assert IdCoordinateField.matches_pa_field(id_field)

    def test_id_coordinate_field_rejects_plain_coordinate_metadata(self) -> None:
        """IdCoordinateField.matches_pa_field must NOT match a plain Coordinate column."""
        table = _make_table_with_coordinate_and_id_coordinate()
        coord_field = table.schema.field("start")
        assert CoordinateField.matches_pa_field(coord_field)
        assert not IdCoordinateField.matches_pa_field(coord_field)


# ---------------------------------------------------------------------------
# MultipleFieldsError + name= disambiguation
# ---------------------------------------------------------------------------


class TestMultipleFieldsError:
    def test_ambiguity_raises_multiple_fields_error(self) -> None:
        host = _MixinHost(_make_table_with_two_ep_columns())
        with pytest.raises(MultipleFieldsError) as exc_info:
            host.get_field(EnharmonicPitch)
        msg = str(exc_info.value)
        assert "EnharmonicPitch" in msg
        assert "primary" in msg and "secondary" in msg
        assert "name=" in msg

    def test_name_resolves_ambiguity(self) -> None:
        host = _MixinHost(_make_table_with_two_ep_columns())
        result = host.get_field(EnharmonicPitch, name="primary")
        assert isinstance(result, EnharmonicPitchField)
        assert result.name == "primary"

        result2 = host.get_field(EnharmonicPitch, name="secondary")
        assert result2.name == "secondary"

    def test_unknown_name_raises_plain_keyerror(self) -> None:
        host = _MixinHost(_make_table_with_two_ep_columns())
        with pytest.raises(KeyError) as exc_info:
            host.get_field(EnharmonicPitch, name="nonexistent")
        # Must NOT be a MultipleFieldsError
        assert not isinstance(exc_info.value, MultipleFieldsError)

    def test_ambiguous_class_form_also_raises(self) -> None:
        """get_field(FieldClass) ALSO raises MultipleFieldsError on ambiguity."""
        host = _MixinHost(_make_table_with_two_ep_columns())
        with pytest.raises(MultipleFieldsError):
            host.get_field(EnharmonicPitchField)

    def test_name_with_field_class_resolves_ambiguity(self) -> None:
        host = _MixinHost(_make_table_with_two_ep_columns())
        result = host.get_field(EnharmonicPitchField, name="secondary")
        assert result.name == "secondary"

    def test_name_without_scalar_class_rejected(self) -> None:
        host = _MixinHost(_make_table_with_two_ep_columns())
        with pytest.raises(TypeError):
            host.get_field("primary", name="primary")


# ---------------------------------------------------------------------------
# get_fields_satisfying(ProtocolClass)
# ---------------------------------------------------------------------------


class TestGetFieldsSatisfying:
    def test_generic_pitch_like_finds_pitch_fields(self) -> None:
        """``GenericPitchLike`` requires ``pitch_class`` — finds EP + SP."""
        host = _MixinHost(_make_table_with_pitches_and_coordinates())
        fields = host.get_fields_satisfying(GenericPitchLike)
        names = sorted(f.name for f in fields)
        assert "midi_pitch" in names
        assert "specific_pitch" in names

    def test_time_scalar_like_finds_coordinate_and_duration(self) -> None:
        host = _MixinHost(_make_table_with_pitches_and_coordinates())
        fields = host.get_fields_satisfying(TimeScalarLike)
        names = sorted(f.name for f in fields)
        assert "start" in names
        assert "duration" in names
        # Pitch columns do NOT satisfy TimeScalarLike (no ``unit``).
        assert "midi_pitch" not in names

    def test_time_scalar_like_includes_id_variants(self) -> None:
        host = _MixinHost(_make_table_with_coordinate_and_id_coordinate())
        fields = host.get_fields_satisfying(TimeScalarLike)
        names = sorted(f.name for f in fields)
        # Both the plain Coordinate column AND the IdCoordinate column
        # satisfy TimeScalarLike (structural match on ``unit``).
        assert "anchor" in names
        assert "start" in names

    def test_empty_when_no_match(self) -> None:
        # An empty table → no protocol matches.
        table = pa.table({"x": pa.array([1, 2, 3], type=pa.int64())})
        host = _MixinHost(table)
        fields = host.get_fields_satisfying(GenericPitchLike)
        assert fields == []
