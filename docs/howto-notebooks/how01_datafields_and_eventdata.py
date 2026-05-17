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
# # How to Work with DataFields and Layered EventData
#
# Typed columnar wrappers, the composition pattern, and the three-layer
# data-access API on top of a loaded `EventData`.
#
# This notebook covers the **data-access axis**: how to get hold of data
# inside an EventData at three levels of abstraction.  Its sibling
# (`how01_pitch_and_harmony_types`) covers the orthogonal **type-design
# axis** — how each music concept is expressed as a Protocol, a Scalar,
# and a Field.

# %% [markdown]
# ## Setup

# %%
from __future__ import annotations

import pyarrow as pa

from timetoalign.fields import (
    CoordinateField,
    NumericField,
    PitchField,
    StringField,
    StructField,
)
from timetoalign.loader.score.tsv import TSVLoader
from timetoalign.testdata import ensure_data

VIENNA = ensure_data("vienna_1x22")
CHOPIN_NOTES = VIENNA / "ms3" / "chopin_op10_no3.notes.tsv"

# %% [markdown]
# ## Part A — Raw DataFields
#
# PyArrow arrays are powerful but semantically opaque: a `pa.array([1.5, 2.0])`
# could be seconds, beats, or pixel positions.  **DataFields** wrap PyArrow
# arrays with typed metadata so the meaning travels with the data.
#
# The base hierarchy provides four concrete raw types — `NumericField`,
# `StringField`, `StructField`, and `MapField` — each validating the
# PyArrow type at construction time.

# %% [markdown]
# ### NumericField

# %%
nf = NumericField(pa.array([60, 64, 67]), pa.field("midi_pitch", pa.int64()))
nf[0], nf[1], nf[2]

# %%
len(nf), nf.name, nf.pa_type

# %% [markdown]
# ### StringField

# %%
sf_str = StringField(pa.array(["C4", "E4", "G4"]), pa.field("pitch_name", pa.utf8()))
sf_str[0], sf_str[2]

# %% [markdown]
# ### StructField — the nested case
#
# Struct arrays group multiple sub-fields into a single column.  This is
# the key reason "raw Field" means more than "raw column": a `StructField`
# is itself a small typed tree.  Sub-fields are accessible by name and
# come back as typed `DataField` objects in their own right.

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
# ## Part B — SemanticField[R]: Adding Meaning
#
# Raw fields know their PyArrow type but not what the data *means*.
# `SemanticField[R]` solves this through **composition**: it wraps a raw
# field `R`, exposes it via `value`, and delegates attribute access
# through `__getattr__`.  Subclasses add domain-specific properties
# (`unit`, `domain`, `pitch_type`, …) and override `__getitem__` to
# return semantic scalars.
#
# | Layer | Class | Provides |
# |-------|-------|----------|
# | Raw | `StructField` | PyArrow type, sub-fields, indexing |
# | Semantic | `CoordinateField` | unit, domain, `Coordinate` scalars |
#
# This pattern means you never lose access to the underlying PyArrow
# machinery: `cf.value` returns the raw `StructField` that `cf` composes.

# %% [markdown]
# ## Part C — The Two-Phase Loader Pattern
#
# Loaders follow a strict two-phase contract:
#
# 1. **Load** — `loader.load(file)` reads the source into a faithful table.
# 2. **Access** — `loader.get_events()` assembles an `EventData` with
#    explicit control over which columns appear.
#
# `from_file()` is a convenience that combines both phases.

# %%
loader = TSVLoader.from_file(CHOPIN_NOTES)
loader

# %% [markdown]
# `get_events(properties=)` controls which non-field columns are included:
#
# - `True` (default): every property column from the source
# - `False`: fields only (`start`, `end`, `duration`, plus core identity)
# - tuple: selected property columns

# %%
events = loader.get_events()
events.table.column_names

# %%
events_fields = loader.get_events(properties=False)
events_fields.table.column_names

# %%
events_selected = loader.get_events(properties=("mc", "mn"))
events_selected.table.column_names

# %% [markdown]
# ## The Data-Access Axis
#
# An `EventData` exposes its contents at three layers.  **Layer 0 always
# works**; Layers 1–2 are opt-in:
#
# | Layer | What | API |
# |-------|------|-----|
# | **0** | Raw Fields — every column as a typed `DataField`, nested structs included | `events.get_raw(col)` |
# | **1** | Semantic Fields — typed views with domain methods, returning scalars on access | `events.get_field(...)` |
# | **2** | External libraries — FlexOHR, pitchtypes | (planned) |
#
# **EventData is never mutated.**  `get_field()` returns a cached view
# over existing columns; the EventData itself stays untouched.

# %% [markdown]
# ## Layer 0 — Raw Fields
#
# `get_raw()` wraps a column in the appropriate raw `DataField` subclass
# **without** adding any semantic identity.  "Raw" here is about the
# absence of semantics, not about the absence of nesting: a struct column
# like `start` still surfaces with full sub-field access, just without
# the `unit` / `domain` annotations that the Layer 1 view would add.

# %%
# Struct column -> StructField (nested!).  start stores onset coordinates
# as {value, numerator, denominator}.
raw_start = events.get_raw("start")
raw_start

# %%
# Index 3 is the G♯3 — an accidental-bearing note
raw_start[3]

# %%
# The nested sub-fields are reachable from the raw level too
raw_start.field_names

# %%
# Numeric column -> NumericField
raw_mc = events.get_raw("mc")
raw_mc[3]

# %%
# String column -> StringField
raw_name = events.get_raw("name")
raw_name[3], raw_name[8], raw_name[16]

# %% [markdown]
# ## Layer 1 — Semantic Fields by Column Name
#
# Every `EventData` has three core temporal columns: `start`, `end`, and
# `duration`.  `get_field()` with a column name returns the appropriate
# SemanticField — `CoordinateField` for `start`/`end`, `DurationField`
# for `duration` — and indexing returns the matching scalar.

# %%
start = events.get_field("start")
start

# %%
# Index 8 is the D♯4 — let's see where it starts (a Coordinate scalar
# with .value and .unit)
s8 = start[8]
s8.value, s8.unit

# %%
end = events.get_field("end")
end[8]

# %%
dur = events.get_field("duration")
dur[8]

# %% [markdown]
# A SemanticField always gives access to its underlying raw field via
# `get_raw()` — composition over inheritance, all the way down.

# %%
start.get_raw()

# %% [markdown]
# ## Layer 1 — Semantic Fields via Blueprint
#
# Real-world tables routinely carry several columns that mean the same
# kind of thing in different representations.  Chopin's notes table has
# **two** pitch columns:
#
# - `midi_pitch` — EP, enharmonic pitch via MIDI numbers
# - `spelled_pitch` — SP, fully spelled pitch with accidental identity
#
# A **blueprint** is a `PitchField` (or any SemanticField) that names a
# column but carries no data.  Passing it to `get_field()` resolves the
# column, constructs the live field, and caches it.

# %% [markdown]
# ### EP blueprint (midi_pitch)

# %%
bp_ep = PitchField(ep="midi_pitch")
bp_ep

# %%
pf_ep = events.get_field(bp_ep)
pf_ep

# %%
# Indices with accidentals: 3=G♯3, 8=D♯4, 16=F♯4, 29=G♯4
pf_ep[3], pf_ep[8], pf_ep[16], pf_ep[29]

# %% [markdown]
# ### SP blueprint (spelled_pitch)

# %%
bp_sp = PitchField(sp="spelled_pitch")
pf_sp = events.get_field(bp_sp)
pf_sp[3], pf_sp[8], pf_sp[16], pf_sp[29]

# %% [markdown]
# The two representations of the same note differ where it counts: EP
# equates enharmonic equivalents, SP preserves them.

# %%
{
    "index 3 (EP)": repr(pf_ep[3]),
    "index 3 (SP)": repr(pf_sp[3]),
    "index 83 (EP)": repr(pf_ep[83]),
    "index 83 (SP)": repr(pf_sp[83]),
}

# %% [markdown]
# ### Caching
#
# `get_field()` calls are cached: repeated requests for the same field
# return the identical object.

# %%
events.get_field(PitchField(ep="midi_pitch")) is pf_ep

# %% [markdown]
# ### Field Discovery
#
# When you don't know which columns are there, the discovery API finds
# fields by class.

# %%
events.has_field(PitchField)

# %%
# get_fields -- ALL matching fields (returns both midi_pitch and spelled_pitch)
pitch_fields = events.get_fields(PitchField)
len(pitch_fields), [repr(pf) for pf in pitch_fields]

# %%
# get_pitch_field -- convenience; returns the most informative (SP > EP)
pf_best = events.get_pitch_field()
repr(pf_best), repr(pf_best[3])

# %% [markdown]
# ## Layer 1 — Conversions
#
# `PitchField.to(target)` converts to less-informative representations
# (richer to coarser).  Starting from SP (the most informative), every
# coarser type is reachable.

# %%
pf_spc = pf_sp.to("spc")  # SPC: drop octave, keep spelling
pf_spc[3], pf_spc[8], pf_spc[29]

# %%
pf_epc = pf_sp.to("epc")  # EPC: drop spelling and octave (chromatic 0-11)
pf_epc[3], pf_epc[8], pf_epc[29]

# %%
pf_gpc = pf_sp.to("gpc")  # GPC: drop accidentals and octave (diatonic 0-6)
pf_gpc[3], pf_gpc[8], pf_gpc[29]

# %%
# Same note index walked through every representation
{
    "SP": repr(pf_sp[29]),
    "SPC": repr(pf_spc[29]),
    "EPC": repr(pf_epc[29]),
    "GPC": repr(pf_gpc[29]),
}

# %% [markdown]
# ## Layer 2 — External Libraries (planned)
#
# The raw PyArrow columns backing Layer 1 are accessible to external
# libraries (FlexOHR, pitchtypes); the integration glue is queued.

# %% [markdown]
# ## Parquet Round-Trip
#
# SemanticFields store their metadata in the PyArrow field's `metadata`
# dict under the `b"timetoalign"` key.  This survives Parquet
# serialisation, so a Layer 1 field can be reconstructed from a file
# without re-running the loader.

# %%
import json
import tempfile

import pyarrow.parquet as pq

# %%
cf_start = events.get_field("start")
pa_field = cf_start.to_field()
table = pa.table({pa_field.name: cf_start.to_pyarrow()}, schema=pa.schema([pa_field]))

with tempfile.NamedTemporaryFile(suffix=".parquet") as f:
    pq.write_table(table, f.name)
    loaded = pq.read_table(f.name)

# %%
json.loads(loaded.schema.field(pa_field.name).metadata[b"timetoalign"])

# %%
loaded_cf = CoordinateField.from_table(loaded)
loaded_cf[8]

# %% [markdown]
# > **Key takeaway.**  An `EventData` exposes its contents along the
# > data-access axis: Layer 0 (raw Fields, including nested structs),
# > Layer 1 (semantic Fields with typed scalars), Layer 2 (external
# > integration).  Fields are cached views; EventData is never mutated.
# > For the orthogonal type-design axis — how each music concept is
# > expressed as Protocol / Scalar / Field — see
# > `how01_pitch_and_harmony_types`.
