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
# # How to Use DataField Typing
#
# Typed columnar wrappers, semantic protocols, and the composition pattern.

# %% [markdown]
# ## The Problem
#
# PyArrow arrays are powerful but semantically opaque -- a `pa.array([1.5, 2.0])`
# could represent seconds, beats, or pixel positions. **DataFields** wrap PyArrow
# arrays with typed metadata so that the meaning travels with the data, through
# Parquet round-trips and across API boundaries.

# %% [markdown]
# ## Raw Fields
#
# The base `DataField` hierarchy provides four concrete raw-field types:
# `NumericField`, `StringField`, `StructField`, and `MapField`. Each validates
# the PyArrow type at construction time.

# %%
import pyarrow as pa

from timetoalign.fields import NumericField, StringField, StructField

# %% [markdown]
# ### NumericField

# %%
nf = NumericField(pa.array([60, 64, 67]), pa.field("midi_pitch", pa.int64()))
nf[0], nf[1], nf[2]

# %%
len(nf), nf.name, nf.pa_type

# %%
nf

# %% [markdown]
# ### StringField

# %%
sf_str = StringField(pa.array(["C4", "E4", "G4"]), pa.field("pitch_name", pa.utf8()))
sf_str[0], sf_str[1], sf_str[2]

# %%
sf_str

# %% [markdown]
# ### StructField
#
# Struct arrays group multiple sub-fields into a single column. `StructField`
# gives access to sub-field names and lets you extract individual sub-fields
# as typed `DataField` objects.

# %%
struct_arr = pa.array(
    [{"x": 1.0, "y": 2.0}, {"x": 3.0, "y": 4.0}],
    type=pa.struct([pa.field("x", pa.float64()), pa.field("y", pa.float64())]),
)
sf = StructField(struct_arr, pa.field("pos", struct_arr.type))
sf.field_names

# %%
sub_x = sf.get_sub_field("x")
sub_x, type(sub_x).__name__

# %%
sub_x[0], sub_x[1]

# %% [markdown]
# ## SemanticField: Adding Meaning
#
# Raw fields know their PyArrow type but not what the data *means*.
# `SemanticField[R]` solves this through **composition**: it wraps a raw field
# `R`, exposes it via `value`, and delegates attribute access through
# `__getattr__`. Subclasses add domain-specific properties (`unit`, `domain`,
# etc.) and override `__getitem__` to return semantic scalars.
#
# | Layer | Class | Provides |
# |-------|-------|----------|
# | Raw | `StructField` | PyArrow type, sub-fields, indexing |
# | Semantic | `CoordinateField` | unit, domain, `Coordinate` scalars |
#
# This pattern means you never lose access to the underlying PyArrow machinery.

# %% [markdown]
# ## CoordinateField
#
# The first concrete `SemanticField[StructField]`. It wraps the canonical
# coordinate struct `{value: float64, numerator: int64, denominator: int64}`
# and returns `Coordinate` scalars on element access.

# %%
from fractions import Fraction

from timetoalign.core import NumberType, TimeUnit
from timetoalign.fields import CoordinateField
from timetoalign.loader.schema import coordinate_to_struct, make_coordinate_type

# %%
# Build coordinate data from mixed numeric types
coord_type = make_coordinate_type(TimeUnit.quarters)
data = [
    coordinate_to_struct(Fraction(3, 4)),
    coordinate_to_struct(1.5),
    coordinate_to_struct(2),
    coordinate_to_struct(Fraction(7, 2)),
]
arr = pa.array(data, type=coord_type)

cf = CoordinateField.from_field(
    arr, unit=TimeUnit.quarters, number_type=NumberType.fraction
)
cf

# %% [markdown]
# ### Element Access Returns Coordinate Scalars

# %%
c0 = cf[0]
c0

# %%
c0.value, type(c0.value).__name__

# %%
cf[1], cf[2], cf[3]

# %% [markdown]
# ### Semantic Properties

# %%
{
    "unit": cf.unit,
    "domain": cf.domain,
    "number_type": cf.number_type,
    "semantic_type": cf.semantic_type,
}

# %%
cf.metadata_dict()

# %% [markdown]
# ### Composition: Accessing the Raw Field

# %%
raw = cf.value
type(raw).__name__

# %%
# Delegated attribute: field_names comes from the inner StructField
cf.field_names

# %%
# Direct sub-field access on the raw StructField
raw.get_sub_field("numerator")

# %% [markdown]
# ## Protocol Conformance
#
# The `CoordinateLike` protocol unifies scalar `Coordinate` objects and
# columnar `CoordinateField` objects under a single structural interface.
# Both carry `unit`, `domain`, `number_type`, and `value`.

# %%
from timetoalign import Coordinate
from timetoalign.core.protocols import CoordinateLike, SemanticTypeLike

# %%
coord_scalar = Coordinate(1.5, TimeUnit.seconds)
isinstance(coord_scalar, SemanticTypeLike)

# %%
isinstance(coord_scalar, CoordinateLike)

# %%
isinstance(cf, CoordinateLike)

# %%
# Same interface, different levels: scalar vs columnar
coord_scalar.unit, cf.unit

# %%
coord_scalar.semantic_type, cf.semantic_type

# %% [markdown]
# ## Parquet Round-Trip
#
# `CoordinateField` stores its semantic metadata in the PyArrow field's metadata
# dict under the `b"timetoalign"` key. This survives Parquet serialisation.

# %%
import json
import tempfile

import pyarrow.parquet as pq

# %%
# Build a table with a CoordinateField column
pa_field = cf.to_field()
table = pa.table({pa_field.name: cf.to_pyarrow()}, schema=pa.schema([pa_field]))

# Write and read Parquet
with tempfile.NamedTemporaryFile(suffix=".parquet") as f:
    pq.write_table(table, f.name)
    loaded = pq.read_table(f.name)

# %%
# Metadata survives the round-trip
col_name = pa_field.name
meta = json.loads(loaded.schema.field(col_name).metadata[b"timetoalign"])
meta

# %%
# Reconstruct the CoordinateField from the loaded table
loaded_cf = CoordinateField.from_table(loaded)
loaded_cf

# %%
loaded_cf[0]

# %% [markdown]
# ## Copy-on-Write
#
# `with_unit()` returns a new `CoordinateField` with updated metadata but the
# same underlying data. Actual value conversion requires a C-Map.

# %%
cf_seconds = cf.with_unit(TimeUnit.seconds)
cf_seconds.unit

# %%
# Data unchanged -- only the metadata label changed
cf_seconds[0]

# %% [markdown]
# ## What's Next
#
# More `SemanticField` subclasses are coming -- `PitchField`, `HarmonyField`,
# `DurationField`, and others -- each following the same composition pattern:
# wrap a raw field, add semantic identity, return domain scalars on access.
