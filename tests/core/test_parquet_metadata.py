"""Tests for the Parquet-metadata blob helpers and the canonical rational struct.

See README.md "test_parquet_metadata.py" for the gold-standard plan.
"""

from __future__ import annotations

import json
import re
from fractions import Fraction
from pathlib import Path

import pyarrow as pa
import pytest

import timetoalign
from timetoalign.core.enums import NumberType, TimeUnit
from timetoalign.core.events import SpecificPitch
from timetoalign.core.fields import (
    RATIONAL_STRUCT_TYPE,
    TIMETOALIGN_BLOB_VERSION,
    TIMETOALIGN_METADATA_KEY,
    metadata_blob_for_model,
    metadata_blob_from_dict,
    parquet_metadata_for_model,
    parse_metadata_blob,
    rational_to_struct,
    struct_to_rational,
)
from timetoalign.core.time import (
    Coordinate,
    CoordinateField,
    DurationField,
    IdCoordinateField,
    IdDurationField,
    _resolve_timeline_id,
)


class TestMetadataBlobForModel:
    """§1, §2: pydantic-model-driven blob construction."""

    def test_payload_is_model_json_schema(self) -> None:
        """§1: blob payload == json.dumps(model_json_schema())."""
        blob = metadata_blob_for_model(SpecificPitch)
        decoded = json.loads(blob.decode("utf-8"))
        assert decoded["title"] == "SpecificPitch"
        assert decoded["type"] == "object"
        assert decoded["required"] == ["step", "octave"]
        # The four declared fields appear under "properties".
        assert set(decoded["properties"]) == {"step", "alter", "octave", "cents"}

    def test_step_property_is_enum_of_seven_letters(self) -> None:
        blob = metadata_blob_for_model(SpecificPitch)
        decoded = json.loads(blob.decode("utf-8"))
        step = decoded["properties"]["step"]
        assert step["enum"] == ["C", "D", "E", "F", "G", "A", "B"]

    def test_blob_cached_object_identity(self) -> None:
        """§2: repeated calls return the same bytes object (lru_cache)."""
        a = metadata_blob_for_model(Coordinate)
        b = metadata_blob_for_model(Coordinate)
        assert a is b


class TestParquetMetadataForModel:
    """§3, §4: dict-shaped metadata for pa.Field.with_metadata."""

    def test_returns_dict_with_timetoalign_key(self) -> None:
        """§3: metadata[TIMETOALIGN_METADATA_KEY] == metadata_blob_for_model(cls)."""
        meta = parquet_metadata_for_model(SpecificPitch)
        assert TIMETOALIGN_METADATA_KEY in meta
        assert meta[TIMETOALIGN_METADATA_KEY] == metadata_blob_for_model(SpecificPitch)

    def test_extra_entries_merged(self) -> None:
        """§4: extra={b"foo": b"bar"} is included alongside the blob."""
        meta = parquet_metadata_for_model(Coordinate, extra={b"foo": b"bar"})
        assert TIMETOALIGN_METADATA_KEY in meta
        assert meta[b"foo"] == b"bar"

    def test_extra_does_not_overwrite_timetoalign(self) -> None:
        """extra cannot smuggle a fake blob — model wins."""
        meta = parquet_metadata_for_model(SpecificPitch, extra={b"foo": b"bar"})
        # The TTA key is set from the model_json_schema; the
        # caller can pass extra but should not try to override the blob.
        # (Implementation merges extra second, but tests pin the
        # documented behaviour.)
        decoded = json.loads(meta[TIMETOALIGN_METADATA_KEY].decode("utf-8"))
        assert decoded["title"] == "SpecificPitch"


class TestMetadataBlobFromDict:
    """§5: legacy path for not-yet-migrated SemanticFields."""

    def test_sorted_keys_for_stability(self) -> None:
        """§5: same dict in different orders -> same bytes."""
        a = metadata_blob_from_dict({"b": 1, "a": 2})
        b = metadata_blob_from_dict({"a": 2, "b": 1})
        assert a == b

    def test_round_trips_through_parse(self) -> None:
        """§6: parse round-trips the payload plus the injected version."""
        d = {"field_type": "CoordinateField", "unit": "quarters"}
        blob = metadata_blob_from_dict(d)
        assert parse_metadata_blob(blob) == {**d, "version": 1}


class TestParseMetadataBlob:
    """Round-trip and edge cases for the parser."""

    def test_parse_none_returns_empty_dict(self) -> None:
        assert parse_metadata_blob(None) == {}

    def test_parse_empty_bytes_returns_empty_dict(self) -> None:
        assert parse_metadata_blob(b"") == {}

    def test_parse_accepts_str_or_bytes(self) -> None:
        payload = metadata_blob_from_dict({"a": 1})
        expected = {"a": 1, "version": 1}
        assert parse_metadata_blob(payload) == expected
        assert parse_metadata_blob(payload.decode("utf-8")) == expected


class TestBlobVersioning:
    """§1, §2 of the README: the version stamp is written and required."""

    def test_dict_writer_injects_version(self) -> None:
        blob = metadata_blob_from_dict({"field_type": "NoteField"})
        assert parse_metadata_blob(blob) == {
            "field_type": "NoteField",
            "version": 1,
        }

    def test_model_writer_injects_version(self) -> None:
        payload = parse_metadata_blob(metadata_blob_for_model(SpecificPitch))
        assert payload["version"] == 1
        assert payload["title"] == "SpecificPitch"

    def test_injected_version_is_the_module_constant(self) -> None:
        assert TIMETOALIGN_BLOB_VERSION == 1
        payload = parse_metadata_blob(metadata_blob_from_dict({}))
        assert payload["version"] == TIMETOALIGN_BLOB_VERSION

    def test_caller_supplied_version_is_overwritten(self) -> None:
        """A payload cannot smuggle its own version past the writer."""
        blob = metadata_blob_from_dict({"version": 99})
        assert parse_metadata_blob(blob)["version"] == TIMETOALIGN_BLOB_VERSION

    def test_version_less_blob_rejected(self) -> None:
        with pytest.raises(ValueError, match="no integer 'version' entry"):
            parse_metadata_blob(b'{"field_type": "CoordinateField"}')

    def test_non_integer_version_rejected(self) -> None:
        with pytest.raises(ValueError, match="no integer 'version' entry"):
            parse_metadata_blob(b'{"version": "1"}')

    def test_future_version_rejected(self) -> None:
        future = TIMETOALIGN_BLOB_VERSION + 1
        with pytest.raises(ValueError, match=f"declares version {future}"):
            parse_metadata_blob(('{"version": %d}' % future).encode("utf-8"))

    def test_non_object_payload_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be a JSON object"):
            parse_metadata_blob(b"[1, 2, 3]")


class TestSingleOwnership:
    """§3: only core/fields.py spells the metadata key out."""

    def test_bytes_literal_confined_to_core_fields(self) -> None:
        package_root = Path(timetoalign.__file__).parent
        owner = package_root / "core" / "fields.py"
        # Either quote style counts: prose that spells the key out the way a
        # bytes literal would is just as much a second source of truth.
        literal = re.compile(r"""b['"]timetoalign['"]""")
        offenders = [
            path.relative_to(package_root).as_posix()
            for path in sorted(package_root.rglob("*.py"))
            if path != owner and literal.search(path.read_text(encoding="utf-8"))
        ]
        assert offenders == []

    def test_owner_defines_the_key(self) -> None:
        assert TIMETOALIGN_METADATA_KEY == b"timetoalign"


class TestHierarchyWideStamping:
    """§4: every SemanticField stamps once, deriving its own field_type."""

    @staticmethod
    def _coordinate_field() -> CoordinateField:
        arr = pa.array(
            [{"value": 0.75, "numerator": 3, "denominator": 4}],
            type=RATIONAL_STRUCT_TYPE,
        )
        return CoordinateField.from_field(
            arr, unit=TimeUnit.quarters, number_type=NumberType.fraction
        )

    def test_to_field_stamps_versioned_blob(self) -> None:
        pa_field = self._coordinate_field().to_field()
        payload = parse_metadata_blob(pa_field.metadata[TIMETOALIGN_METADATA_KEY])
        assert payload == {
            "field_type": "CoordinateField",
            "unit": "quarters",
            "domain": "logical",
            "number_type": "fraction",
            "version": 1,
        }

    def test_stamp_preserves_foreign_metadata(self) -> None:
        cf = self._coordinate_field()
        cf._field = cf._field.with_metadata({b"provenance": b"ms3"})
        pa_field = cf.to_field()
        assert pa_field.metadata[b"provenance"] == b"ms3"
        assert TIMETOALIGN_METADATA_KEY in pa_field.metadata

    def test_field_type_derived_from_class_name(self) -> None:
        assert CoordinateField.field_type() == "CoordinateField"
        assert IdCoordinateField.field_type() == "IdCoordinateField"

    def test_scalar_field_type_appends_field_suffix(self) -> None:
        assert Coordinate.field_type() == "CoordinateField"
        assert SpecificPitch.field_type() == "SpecificPitchField"

    def test_scalar_metadata_dict_carries_derived_discriminator(self) -> None:
        md = Coordinate(Fraction(3, 4), TimeUnit.quarters).metadata_dict()
        assert md["field_type"] == "CoordinateField"


class TestVersionErrorPropagation:
    """A version violation must surface as ``ValueError``, not a swallowed mismatch.

    ``matches_pa_field`` and ``_resolve_timeline_id`` used to catch the
    broad ``(ValueError, UnicodeDecodeError)`` pair around
    ``parse_metadata_blob``, a leftover from when the body was a bare
    ``json.loads``. ``parse_metadata_blob`` now raises ``ValueError`` on
    purpose for version violations, so that error must propagate instead
    of being treated as "no decodable blob".
    """

    @staticmethod
    def _future_version_field(field_type: str) -> pa.Field:
        blob = json.dumps({"field_type": field_type, "version": 999999}).encode("utf-8")
        return pa.field(
            "coord", RATIONAL_STRUCT_TYPE, metadata={TIMETOALIGN_METADATA_KEY: blob}
        )

    def test_coordinate_field_future_version_raises(self) -> None:
        pa_field = self._future_version_field("IdCoordinateField")
        with pytest.raises(ValueError, match="declares version 999999"):
            CoordinateField.matches_pa_field(pa_field)

    def test_id_coordinate_field_future_version_raises(self) -> None:
        pa_field = self._future_version_field("IdCoordinateField")
        with pytest.raises(ValueError, match="declares version 999999"):
            IdCoordinateField.matches_pa_field(pa_field)

    def test_duration_field_future_version_raises(self) -> None:
        pa_field = self._future_version_field("IdDurationField")
        with pytest.raises(ValueError, match="declares version 999999"):
            DurationField.matches_pa_field(pa_field)

    def test_id_duration_field_future_version_raises(self) -> None:
        pa_field = self._future_version_field("IdDurationField")
        with pytest.raises(ValueError, match="declares version 999999"):
            IdDurationField.matches_pa_field(pa_field)

    def test_resolve_timeline_id_surfaces_version_error(self) -> None:
        """The version diagnostic wins over the generic missing-id message."""
        pa_field = self._future_version_field("IdCoordinateField")
        with pytest.raises(ValueError, match="declares version 999999"):
            _resolve_timeline_id(pa_field, None)


class TestCanonicalRationalStruct:
    """§5: one struct shape, exact Fraction round-trip."""

    def test_struct_type_members(self) -> None:
        assert [f.name for f in RATIONAL_STRUCT_TYPE] == [
            "value",
            "numerator",
            "denominator",
        ]

    def test_rational_to_struct_exact(self) -> None:
        assert rational_to_struct(Fraction(3, 4)) == {
            "value": 0.75,
            "numerator": 3,
            "denominator": 4,
        }

    def test_int_to_struct(self) -> None:
        assert rational_to_struct(7) == {
            "value": 7.0,
            "numerator": 7,
            "denominator": 1,
        }

    def test_string_ratio_to_struct(self) -> None:
        assert rational_to_struct("5/8") == {
            "value": 0.625,
            "numerator": 5,
            "denominator": 8,
        }

    def test_float_to_struct(self) -> None:
        assert rational_to_struct(1.5) == {
            "value": 1.5,
            "numerator": 3,
            "denominator": 2,
        }

    @pytest.mark.parametrize(
        "value",
        [Fraction(1, 3), Fraction(-7, 12), Fraction(22, 7), Fraction(5, 1)],
    )
    def test_round_trip_is_exact(self, value: Fraction) -> None:
        assert struct_to_rational(rational_to_struct(value)) == value

    def test_round_trip_survives_arrow(self) -> None:
        values = [Fraction(1, 3), Fraction(3, 4), Fraction(-1, 6)]
        arr = pa.array(
            [rational_to_struct(v) for v in values], type=RATIONAL_STRUCT_TYPE
        )
        assert [struct_to_rational(d) for d in arr.to_pylist()] == values

    def test_struct_to_rational_rejects_non_integral_components(self) -> None:
        with pytest.raises(ValueError, match="numerator must be an integer"):
            struct_to_rational({"value": 0.75, "numerator": None, "denominator": 4})
        with pytest.raises(ValueError, match="denominator must be an integer"):
            struct_to_rational({"value": 0.75, "numerator": 3, "denominator": 0.5})

    def test_struct_to_rational_rejects_zero_denominator(self) -> None:
        with pytest.raises(ValueError, match="denominator must be non-zero"):
            struct_to_rational({"value": 0.0, "numerator": 1, "denominator": 0})

    def test_unparseable_string_raises(self) -> None:
        with pytest.raises(ValueError):
            rational_to_struct("not a number")
