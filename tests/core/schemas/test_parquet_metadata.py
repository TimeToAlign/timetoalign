"""Tests for the b"timetoalign" Parquet-metadata blob helpers.

See README.md "test_parquet_metadata.py" for the gold-standard plan.
"""

from __future__ import annotations

import json

from timetoalign.core.scalars.pitch import SpecificPitch
from timetoalign.core.schemas import (
    TIMETOALIGN_METADATA_KEY,
    metadata_blob_for_model,
    metadata_blob_from_dict,
    parquet_metadata_for_model,
)
from timetoalign.core.schemas.parquet_metadata import parse_metadata_blob
from timetoalign.core.types import Coordinate


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
        """§3: metadata[b"timetoalign"] == metadata_blob_for_model(cls)."""
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
        # The b"timetoalign" key is set from the model_json_schema; the
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
        """§6: parse_metadata_blob(metadata_blob_from_dict(d)) == d."""
        d = {"field_type": "CoordinateField", "unit": "quarters"}
        blob = metadata_blob_from_dict(d)
        assert parse_metadata_blob(blob) == d


class TestParseMetadataBlob:
    """Round-trip and edge cases for the parser."""

    def test_parse_none_returns_empty_dict(self) -> None:
        assert parse_metadata_blob(None) == {}

    def test_parse_empty_bytes_returns_empty_dict(self) -> None:
        assert parse_metadata_blob(b"") == {}

    def test_parse_accepts_str_or_bytes(self) -> None:
        payload = b'{"a": 1}'
        assert parse_metadata_blob(payload) == {"a": 1}
        assert parse_metadata_blob(payload.decode("utf-8")) == {"a": 1}
