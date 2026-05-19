"""PyArrow-schema derivation and Parquet-metadata helpers for pydantic scalars.

This package is the bridge between pydantic v2 ``BaseModel`` scalar
definitions and the PyArrow storage layer.  It owns:

* :mod:`timetoalign.core.schemas.from_pydantic` — translator that turns a
  ``BaseModel`` class into a ``pa.Schema`` (and individual ``pa.Field``
  entries).
* :mod:`timetoalign.core.schemas.parquet_metadata` — single source for the
  ``b"timetoalign"`` JSON metadata blob that travels with every ``pa.Field``
  in TTA-written Parquet files.

These modules implement the **schema mechanism** that WP2 of the workshop
typing push locked: pydantic is the type definition; PyArrow is the bulk
storage layer; the translator is a one-time at-class-definition step whose
output is cached per scalar class.
"""

from __future__ import annotations

from .column_builder import (
    build_coordinate_struct_array,
    build_struct_array,
)
from .from_pydantic import (
    derive_arrow_schema,
    derive_arrow_struct,
    register_value_projector,
)
from .parquet_metadata import (
    TIMETOALIGN_METADATA_KEY,
    metadata_blob_for_model,
    metadata_blob_from_dict,
    parquet_metadata_for_model,
)

__all__ = [
    "TIMETOALIGN_METADATA_KEY",
    "build_coordinate_struct_array",
    "build_struct_array",
    "derive_arrow_schema",
    "derive_arrow_struct",
    "metadata_blob_for_model",
    "metadata_blob_from_dict",
    "parquet_metadata_for_model",
    "register_value_projector",
]
