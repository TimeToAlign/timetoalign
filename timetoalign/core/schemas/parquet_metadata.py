"""Single source for the ``b"timetoalign"`` Parquet-metadata blob.

Every ``pa.Field`` produced by a TTA semantic field carries a metadata
entry under the key ``b"timetoalign"`` whose payload is the JSON-encoded
``model_json_schema()`` of the backing pydantic scalar.  Three call sites
previously declared this blob independently (``fields/coordinate.py``,
``fields/pitch.py``, ``fields/harmony.py``); they now route through this
module instead.

The blob is the on-disk surface of WP2's "Pydantic owns the schema"
principle.  Downstream readers (TTA-internal round-trip, Frictionless
consumers, external tools) can parse it as standard JSONSchema without
any TTA-specific decoding.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

TIMETOALIGN_METADATA_KEY: bytes = b"timetoalign"
"""The bytes key used inside ``pa.Field.metadata`` for the TTA blob."""


@lru_cache(maxsize=None)
def _cached_json_schema_bytes(model_cls: type[BaseModel]) -> bytes:
    """Return ``model_json_schema()`` serialised to UTF-8 bytes.

    Cached per scalar class — the schema is immutable for the lifetime of
    the process, so we pay the JSON-encoding cost exactly once per scalar.
    """
    return json.dumps(model_cls.model_json_schema(), sort_keys=True).encode("utf-8")


def metadata_blob_for_model(model_cls: type[BaseModel]) -> bytes:
    """Return the JSON-encoded ``model_json_schema()`` bytes for a model.

    This is the **payload** that lives under
    ``pa.Field.metadata[b"timetoalign"]``.  It is identical for every
    ``pa.Field`` carrying the same scalar type and is cached so repeated
    calls return the same bytes object.

    Args:
        model_cls: A pydantic v2 ``BaseModel`` subclass.

    Returns:
        UTF-8 encoded JSON bytes of ``model_cls.model_json_schema()``.
    """
    return _cached_json_schema_bytes(model_cls)


def metadata_blob_from_dict(payload: dict[str, Any]) -> bytes:
    """Return JSON-encoded UTF-8 bytes from an arbitrary payload dict.

    Used by **not-yet-migrated** SemanticField subclasses (pitch, harmony)
    to keep their existing ``metadata_dict()`` payload shape unchanged
    while still routing through this module — i.e. they get the unified
    blob-construction path without breaking existing Parquet round-trips.

    Migrated scalars (``Coordinate``, ``SpecificPitch``, …) use
    :func:`metadata_blob_for_model` instead.

    Args:
        payload: The dict to encode as the ``b"timetoalign"`` payload.

    Returns:
        UTF-8 encoded JSON bytes of *payload*.
    """
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def parquet_metadata_for_model(
    model_cls: type[BaseModel],
    *,
    extra: dict[bytes, bytes] | None = None,
) -> dict[bytes, bytes]:
    """Return the ``pa.Field.metadata`` dict for a scalar's pydantic model.

    The returned dict is suitable for passing directly into
    ``pa.field(..., metadata=...)`` or ``pa.Field.with_metadata(...)``.
    Always contains the ``b"timetoalign"`` key with the JSONSchema
    payload; *extra* entries are merged in if provided (used by, e.g.,
    ``CoordinateField`` to preserve per-instance unit/domain hints that
    are not stored in the scalar's pydantic schema).

    Args:
        model_cls: A pydantic v2 ``BaseModel`` subclass.
        extra: Optional additional metadata entries (bytes -> bytes).

    Returns:
        A new dict with at least the ``b"timetoalign"`` entry.
    """
    metadata: dict[bytes, bytes] = {
        TIMETOALIGN_METADATA_KEY: metadata_blob_for_model(model_cls)
    }
    if extra:
        metadata.update(extra)
    return metadata


def parse_metadata_blob(blob: bytes | str | None) -> dict[str, Any]:
    """Parse a ``b"timetoalign"`` payload back into a dict.

    Args:
        blob: The bytes (or already-decoded string) stored under
            ``b"timetoalign"`` in ``pa.Field.metadata``.  ``None`` returns
            an empty dict.

    Returns:
        The decoded JSONSchema dictionary, or ``{}`` if *blob* is empty.
    """
    if blob is None:
        return {}
    if isinstance(blob, bytes):
        blob = blob.decode("utf-8")
    if not blob:
        return {}
    return json.loads(blob)
