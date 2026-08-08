# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.3
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# # The Data Model
#
# *What you will build.* You will load a table of Chopin notes, move from its
# faithful Arrow columns to typed musical views, and promote a column yourself.
# By the end, you can take any column and ask what typed musical value it affords,
# while understanding why the table is Arrow-backed.
#
# *Before you start.* Complete [Flow Control and Grids](tut07_flow_and_grids.ipynb).

# %%
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol, runtime_checkable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from IPython.display import display
from pydantic import BaseModel

from timetoalign import EventData, Ms3Loader
from timetoalign.core import (
    Coordinate,
    CoordinateField,
    DataField,
    DurationField,
    NumberType,
    NumericField,
    SemanticField,
    StringField,
    StructField,
    TimeUnit,
    build_struct_array,
)
from timetoalign.storage import MultipleFieldsError
from timetoalign.testdata import ensure_data

data_root = ensure_data("vienna_1x22")
notes_path = data_root / "ms3" / "chopin_op10_no3.notes.tsv"

# %% [markdown]
# ## Why PyArrow
#
# Arrow is columnar and supports zero-copy operations, so a million notes cost
# what a million notes should cost; Parquet also preserves nested columns, letting
# one object's schema describe both that object and a corpus-sized column of them.
# Arrow carries metadata on tables and columns, so units and musical meanings travel
# with the data rather than depending on names, making TimeToAlign! big-data-ready by
# construction; the library does not restrict which {{< glossary Event >}} types a
# loader's `EventStore` may contain, but it does provide an interface for declaring
# event types that live on {{< glossary Timeline >}}s.

# %%
number_array = pa.array([2, 3, 5], type=pa.int64())
label_array = pa.array(["A", "B", "C"], type=pa.string())
point_array = pa.array([{"x": 10, "y": 20}, {"x": 30, "y": 40}, {"x": 50, "y": 60}])
number_schema = pa.field("number", pa.int64(), metadata={b"meaning": b"example count"})
label_schema = pa.field("label", pa.string())
point_schema = pa.field("point", point_array.type)
primer_schema = pa.schema(
    [number_schema, label_schema, point_schema],
    metadata={b"collection": b"data-model primer"},
)
primer_table = pa.Table.from_arrays(
    [number_array, label_array, point_array], schema=primer_schema
)
primer_table.schema

# %% [markdown]
# The schema shows a nested `point` column, column metadata on `number`, and
# table metadata for the collection. Parquet can retain this whole description.

# %% [markdown]
# ## The three layers
#
# Layer 0 is the faithful typed data parsed by the loader; Layer 1 is the musical
# view the table *affords* on request, and indexing that view produces one typed
# {{< glossary Coordinate >}} or other scalar. “Affords” matters: loaders never
# store semantic types, and requested views are computed lazily and cached rather
# than baked into the table.

# %%
loader = Ms3Loader.from_file(notes_path)
events = loader.get_events()
layer_bases = {
    "Layer 0 base": DataField.__name__,
    "Layer 1 base": SemanticField.__name__,
    "indexed scalar example": Coordinate.__name__,
    "stored table": type(events.table).__name__,
}
layer_bases

# %% [markdown]
# `events` stores an Arrow table. `DataField` and `SemanticField` are two views
# over its columns; only indexing the semantic view creates an individual scalar.

# %% [markdown]
# ## Protocol, Scalar, Field
#
# These three roles separate checking a value's capabilities, representing one
# validated value, and processing many values as a column.

# %%
role_table = pd.DataFrame(
    [
        {
            "Role": "Protocol",
            "Example": Protocol.__name__,
            "Plain-English job": "Checks whether a value has the required attributes and methods.",
        },
        {
            "Role": "Scalar",
            "Example": Coordinate.__name__,
            "Plain-English job": "Validates and represents one musical value.",
        },
        {
            "Role": "Field",
            "Example": CoordinateField.__name__,
            "Plain-English job": "Holds many values as a column and yields a scalar when indexed.",
        },
    ]
)
role_table

# %% [markdown]
# A Protocol asks “is this the right shape?”, a Scalar represents one checked
# value, and a Field keeps many such values in efficient columnar storage.

# %% [markdown]
# ## Layer 0 by hand
#
# Raw `NumericField`, `StringField`, and `StructField` wrappers add convenient
# access to Arrow data and schemas, but they attach no musical interpretation.

# %%
number_field = NumericField.from_field((number_array, number_schema))
label_field = StringField.from_field((label_array, label_schema))
point_field = StructField.from_field((point_array, point_schema))
handmade_raw = {
    "numeric value": number_field[1],
    "string value": label_field[1],
    "struct value": point_field[1],
    "struct field_names": point_field.field_names,
    "all are DataField": all(
        isinstance(field, DataField)
        for field in (number_field, label_field, point_field)
    ),
}
handmade_raw

# %% [markdown]
# The Python values differ because the Arrow types differ. `field_names` exposes
# the two children of the struct, but nothing here says that either child is musical.

# %% [markdown]
# ## Layer 0 from a real table
#
# `get_raw("start")` exposes exactly what the Chopin loader parsed: an onset struct
# with a best-effort value plus numerator and denominator, whose exact ratio survives
# a Parquet round trip.

# %%
raw_start = events.get_raw("start")
raw_start_value = raw_start[1]
raw_snapshot = {
    "wrapper type": type(raw_start).__name__,
    "Arrow type": raw_start.pa_type,
    "field_names": raw_start.field_names,
    "indexed value": raw_start_value,
}
raw_snapshot

# %% [markdown]
# The numerator `1` and denominator `2` preserve one half exactly instead of trusting
# a floating-point reconstruction. At Layer 0, however, the struct does not know that
# it denotes an onset measured in quarters.

# %% [markdown]
# ## Layer 1
#
# Asking for `start` promotes the raw struct to a `CoordinateField`; asking for
# `duration` produces a `DurationField`, and indexing either returns a scalar with
# its unit attached.

# %%
start_field = events.get_field("start")
typed_start = start_field[1]
expected_start = Coordinate(Fraction(1, 2), TimeUnit.quarters)
duration_field = events.get_field("duration")
typed_duration = duration_field[1]
layer_comparison = {
    "raw": {"type": type(raw_start_value).__name__, "value": raw_start_value},
    "start": {
        "field type": type(start_field).__name__,
        "is CoordinateField": isinstance(start_field, CoordinateField),
        "scalar type": type(typed_start).__name__,
        "value": typed_start,
        "exactly one half": typed_start == expected_start,
    },
    "duration": {
        "field type": type(duration_field).__name__,
        "is DurationField": isinstance(duration_field, DurationField),
        "scalar type": type(typed_duration).__name__,
        "value": typed_duration,
    },
}
layer_comparison

# %% [markdown]
# The same onset is now a `Coordinate(Fraction(1, 2), quarters)`, not a dictionary.
# Its type distinguishes it from the quarter-note `Duration`, and both objects retain
# exact rational content and their unit.

# %% [markdown]
# ## Promoting a column yourself
#
# When a source column has meaning that its loader did not declare, define the scalar
# shape, materialise its Field with `from_array()`, or build its nested Arrow storage
# explicitly with `build_struct_array()` and `from_field()`.


# %%
class MetricalAddress(BaseModel):
    bar: int
    beat: int


class MetricalAddressField(SemanticField[MetricalAddress]):
    @property
    def semantic_type(self) -> str:
        return "MetricalAddress"

    def __getitem__(self, index: int) -> MetricalAddress:
        record = super().__getitem__(index)
        return MetricalAddress.model_validate(record)


address_source = pa.array([{"bar": 1, "beat": 1}, {"bar": 2, "beat": 3}])
address_template = MetricalAddressField(name="metrical_address")
address_from_array = address_template.from_array(address_source)
address_scalars = [MetricalAddress(bar=3, beat=1), MetricalAddress(bar=3, beat=4)]
address_struct = build_struct_array(MetricalAddress, address_scalars)
address_schema = pa.field("primary_address", address_struct.type)
address_from_field = MetricalAddressField.from_field((address_struct, address_schema))
address_semantic_schema = address_from_field.to_field()
promotion_examples = {
    "from_array": address_from_array[0],
    "from_field": address_from_field[1],
}
promotion_examples

# %% [markdown]
# `from_array()` validates rows against the scalar class and creates the paired
# semantic field. For a scalar made from several values, `build_struct_array()` makes
# the nested column explicitly, while `from_field()` attaches its semantic wrapper.

# %% [markdown]
# ## Blueprints
#
# A blueprint is a Field instance that names its `source_fields` but carries no data,
# deferring resolution until a table receives it. This lets the same analysis request
# a musical concept from loaders that use different source-column names.

# %%
start_blueprint = CoordinateField(source_fields="start")
resolved_start = events.get_field(start_blueprint)
blueprint_result = {
    "is blueprint": start_blueprint.is_blueprint,
    "source_fields": "start",
    "resolved field": resolved_start,
    "first scalar": resolved_start[1],
}
blueprint_result

# %% [markdown]
# The blueprint contains a deferred instruction rather than 498 values. Here it
# resolves `start`; code for another loader can supply a blueprint naming that
# loader's corresponding onset column.

# %% [markdown]
# ## Finding fields
#
# Use `has_field()` and `get_fields()` for discovery, rely on identity caching for
# repeated requests, and pass `name=` when a scalar class matches several columns.

# %%
secondary_address_schema = address_semantic_schema.with_name("secondary_address")
ambiguous_events = EventData.from_arrays(
    {
        "id": ["marker-1", "marker-2"],
        "event_type": ["Marker", "Marker"],
        "start": [0, 1],
        "primary_address": address_struct,
        "secondary_address": address_struct,
    },
    unit=TimeUnit.quarters,
    number_type=NumberType.fraction,
    extra_fields=[address_semantic_schema, secondary_address_schema],
)
has_addresses = ambiguous_events.has_field(MetricalAddressField)
address_fields = ambiguous_events.get_fields(MetricalAddressField)
named_address = ambiguous_events.get_field(MetricalAddress, name="primary_address")
cached_address = ambiguous_events.get_field(MetricalAddress, name="primary_address")
field_lookup_summary = {
    "has MetricalAddressField": has_addresses,
    "matching columns": [field.name for field in address_fields],
    "cached object reused": cached_address is named_address,
    "name= selects a scalar": named_address[0],
}
display(field_lookup_summary)

ambiguity = None
try:
    ambiguous_events.get_field(MetricalAddress)
except MultipleFieldsError as exc:
    ambiguity = exc
ambiguity

# %% [markdown]
# The summary shows discovery, disambiguation, and that repeated access returns the
# identical cached object. The rendered `MultipleFieldsError` explains that a scalar
# class alone is ambiguous and lists the column names accepted by `name=`.

# %% [markdown]
# ## Discovery by protocol
#
# `get_fields_satisfying()` searches by scalar shape rather than by a concrete class;
# this small runtime-checkable Protocol asks for the octave-bearing shape present in
# this score's pitch columns.


# %%
@runtime_checkable
class OctaveBearingPitch(Protocol):
    @property
    def octave(self) -> int: ...


pitch_fields = events.get_fields_satisfying(OctaveBearingPitch)
pitch_discovery = [
    {"column": field.name, "field type": type(field).__name__} for field in pitch_fields
]
pitch_discovery

# %% [markdown]
# Exactly the `midi` and `specific_pitch` views satisfy this pitch shape; the start,
# end, and duration fields do not. The next tutorial introduces the library's
# `GenericPitchLike` root Protocol for this query across several formats.

# %% [markdown]
# ## Metadata survives Parquet
#
# A semantic Field writes its identity and unit into Arrow column metadata, so Parquet
# can preserve the nested values and enough schema information for `from_table()` to
# reconstruct typed scalars without the original loader.

# %%
semantic_array = start_field.to_pyarrow()
semantic_schema = start_field.to_field()
parquet_schema = pa.schema([semantic_schema])
parquet_table = pa.Table.from_arrays([semantic_array], schema=parquet_schema)

with TemporaryDirectory() as directory:
    parquet_path = Path(directory) / "semantic-start.parquet"
    pq.write_table(parquet_table, parquet_path)
    restored_table = pq.read_table(parquet_path)

restored_start = CoordinateField.from_table(restored_table)
restored_scalar = restored_start[1]
restored_metadata = restored_table.schema.field("start").metadata
round_trip = {
    "column metadata": restored_metadata,
    "field type": type(restored_start).__name__,
    "scalar type": type(restored_scalar).__name__,
    "typed value": restored_scalar,
    "same value and unit": restored_scalar == expected_start,
}
round_trip

# %% [markdown]
# `to_pyarrow()` supplied the nested data and `to_field()` supplied its semantic
# metadata. After the Parquet round trip, `from_table()` rebuilds a `CoordinateField`
# whose indexed value is still the exact half-quarter `Coordinate` seen earlier.

# %% [markdown]
# ## What you learned
#
# - Explain how Arrow's columnar storage, nested schemas, and metadata make the
#   library big-data-ready.
# - Distinguish faithful raw columns, afforded semantic views, and indexed scalars.
# - Explain the separate jobs of a Protocol, Scalar, and Field.
# - Construct raw numeric, string, and struct fields by hand.
# - Inspect a real onset's rational Layer 0 representation.
# - Request coordinate and duration views that retain exact values and units.
# - Promote a source column into a semantic Field yourself.
# - Defer column resolution with a blueprint and `source_fields`.
# - Discover, cache, and disambiguate semantic fields.
# - Find fields by the shape of their scalars.
# - Round-trip a semantic field through Parquet without losing its type or unit.
#
# *Next.* [Pitch and Harmony across Formats](tut09_pitch_and_harmony.ipynb)
#
# *Go deeper.* [Loading data](../howto/how01_loading_data.ipynb),
# [tabular loaders](../howto/how01_tabular_loaders.ipynb), and
# [coordinate mathematics](../howto/how01_coordinate_math.ipynb).
