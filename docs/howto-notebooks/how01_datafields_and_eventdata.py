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
# - `specific_pitch` — SP, fully specific pitch with accidental identity
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
# ### SP blueprint (specific_pitch)

# %%
bp_sp = PitchField(sp="specific_pitch")
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
# get_fields -- ALL matching fields (returns both midi_pitch and specific_pitch)
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
# ## Schema Mechanism — Pydantic → pa.Schema → pa.StructArray → Scalars
#
# Each scalar's schema is owned by a pydantic v2 model.  That model is the
# single source of truth: the `pa.Schema` that backs an Arrow column, the
# metadata blob that travels with Parquet, and the JSONSchema that external
# tools consume are all derived from it.  The model is also the project's
# **edge validator** at trust boundaries (external Parquet, untrusted CSV,
# `.jsonl` ingest); on internal round-trips the `pa.Schema` is trusted
# instead.
#
# This section walks the full internal round-trip: pydantic → `pa.Schema`,
# bulk materialisation into a `pa.StructArray`, native Arrow compute on the
# columnar layout, predicate filtering, and reconstruction of survivors as
# `Coordinate` scalars.

# %%
import time
from fractions import Fraction

import pyarrow.compute as pc

from timetoalign.core.enums import NumberType, TimeUnit
from timetoalign.core.scalars.pitch import SpecificPitch
from timetoalign.core.schemas import (
    build_coordinate_struct_array,
    derive_arrow_schema,
    derive_arrow_struct,
)
from timetoalign.core.types import Coordinate
from timetoalign.loader.schema import struct_to_coordinate

# %% [markdown]
# ### JSONSchema preamble
#
# `model_json_schema()` is the cross-language interop artifact — nothing
# TTA-specific, just standard JSONSchema.  The same payload is what lives
# inside `b"timetoalign"` on every emitted column.
#
# `Coordinate.model_json_schema()` — value + unit, the minimal pair every
# coordinate needs.  The PyArrow projection denormalises `value` into
# `{value, numerator, denominator}` so rational precision survives a
# round-trip, but the *schema* exposes the user-facing pair.

# %%
print(json.dumps(Coordinate.model_json_schema(), indent=2))

# %% [markdown]
# `SpecificPitch.model_json_schema()` — required `step` + `octave`,
# optional `alter` and `cents`.  Computed fields (`fifths`, `midi_number`,
# `pitch_class`) are derived on access and absent from the schema by
# design.

# %%
print(json.dumps(SpecificPitch.model_json_schema(), indent=2))

# %% [markdown]
# ### Pydantic → pa.Schema
#
# `derive_arrow_schema(Coordinate)` returns the `pa.Schema` whose columns
# mirror the model.  `value` is denormalised into
# `{value: float64, numerator: int64, denominator: int64}` so rational
# precision survives Parquet; `unit` lives in `pa.Field` metadata, NOT in
# the column itself.  This denormalisation is registered via
# `register_value_projector` (see `core/types.py:548-549`); computed
# fields are excluded by design.
#
# The projector registry currently customises the *schema* only — the
# column-wise materialisation of Coordinate's three storage fields lives
# in the dedicated `build_coordinate_struct_array`.

# %%
derive_arrow_schema(Coordinate)

# %%
derive_arrow_struct(Coordinate)

# %% [markdown]
# ### Headline — reverse direction at N = 1 000 000
#
# Realistic workflow: build a large field, transform it natively in Arrow,
# filter, then materialise survivors as scalars.  Every stage is timed.

# %%
N_LARGE = 1_000_000

# Build N_LARGE Coordinates with the int/float/Fraction mix from the
# canonical benchmark (benchmarks/pydantic_pilot.py:57-68).  These are
# trust-boundary validated once, at construction time.
t0 = time.perf_counter()
coords_large = [
    (
        Coordinate(i, TimeUnit.quarters)
        if i % 3 == 0
        else (
            Coordinate(i + 0.5, TimeUnit.quarters)
            if i % 3 == 1
            else Coordinate(Fraction(i, 4), TimeUnit.quarters)
        )
    )
    for i in range(N_LARGE)
]
t_construct_ms = (time.perf_counter() - t0) * 1000

# %%
# Bulk into pa.StructArray via the column-builder.
t0 = time.perf_counter()
arr_large = build_coordinate_struct_array(coords_large)
t_build_ms = (time.perf_counter() - t0) * 1000
arr_large.type, len(arr_large)

# %%
# Native Arrow compute on the float64 .value sub-field: shift every
# coordinate by +8 quarters.  No Python loop, no scalar materialisation.
t0 = time.perf_counter()
shifted_value = pc.add(arr_large.field("value"), 8.0)
t_compute_ms = (time.perf_counter() - t0) * 1000

# Reassemble the StructArray with the shifted value column; numerator /
# denominator stay aligned only for fraction-typed entries (we'll filter
# to floats below so this is fine for the demo).
arr_shifted = pa.StructArray.from_arrays(
    [shifted_value, arr_large.field("numerator"), arr_large.field("denominator")],
    fields=list(arr_large.type),
)

# %%
# Filter: keep coordinates whose shifted value is in [100, 1000).
t0 = time.perf_counter()
mask = pc.and_(pc.greater_equal(shifted_value, 100.0), pc.less(shifted_value, 1000.0))
arr_filtered = arr_shifted.filter(mask)
t_filter_ms = (time.perf_counter() - t0) * 1000
len(arr_filtered)

# %%
# Materialise survivors as Coordinate scalars via the SemanticField path.
t0 = time.perf_counter()
cf_filtered = CoordinateField.from_field(
    arr_filtered, unit=TimeUnit.quarters, number_type=NumberType.float
)
materialised = [cf_filtered[i] for i in range(len(cf_filtered))]
t_materialise_ms = (time.perf_counter() - t0) * 1000

{
    "N_built": N_LARGE,
    "N_survivors": len(materialised),
    "construct_scalars_ms": round(t_construct_ms, 1),
    "column_builder_ms": round(t_build_ms, 1),
    "arrow_compute_add_ms": round(t_compute_ms, 1),
    "arrow_filter_ms": round(t_filter_ms, 1),
    "materialise_survivors_ms": round(t_materialise_ms, 1),
}

# %% [markdown]
# The Arrow-native compute and filter run in milliseconds at 1 M rows
# because they never leave the columnar layout; only the survivor
# materialisation pays per-row cost, and only on the K rows that pass the
# filter.  This is the architecture's headline payoff: bulk operations
# stay `pa`-native; scalars are materialised on demand.

# %% [markdown]
# ### Forward direction — three array-construction paths at N = 100 000
#
# Starting from raw dict input (representing a post-parse / pre-Arrow
# stage), measure three paths to a `pa.StructArray`: row-wise with
# `model_validate`, row-wise with `model_construct`, and column-wise via
# `build_coordinate_struct_array`.

# %%
N_FWD = 100_000
struct_type = derive_arrow_struct(Coordinate)

# Raw dicts in the *storage shape* (the shape pa.array(..., type=struct)
# expects).  Mix of int / float / Fraction-derived entries.
raw_dicts = []
for i in range(N_FWD):
    mod = i % 3
    if mod == 0:
        raw_dicts.append({"value": float(i), "numerator": i, "denominator": 1})
    elif mod == 1:
        raw_dicts.append(
            {"value": float(i) + 0.5, "numerator": None, "denominator": None}
        )
    else:
        raw_dicts.append({"value": i / 4.0, "numerator": i, "denominator": 4})

# Same N_FWD dicts in the *scalar shape* (the shape Coordinate(...)
# expects), for the row-wise+validate and row-wise+construct paths.
scalar_dicts = []
for i in range(N_FWD):
    mod = i % 3
    if mod == 0:
        scalar_dicts.append({"value": i, "unit": "quarters"})
    elif mod == 1:
        scalar_dicts.append({"value": float(i) + 0.5, "unit": "quarters"})
    else:
        scalar_dicts.append({"value": Fraction(i, 4), "unit": "quarters"})


# %%
def _runs(fn, *args, runs=3):
    durations = []
    for _ in range(runs):
        start = time.perf_counter()
        fn(*args)
        durations.append((time.perf_counter() - start) * 1000)
    return sum(durations) / len(durations)


def _path_rowwise_validate(dicts):
    # Trust-boundary regime per row, then row-wise pa.array of storage dicts.
    coords = [Coordinate.model_validate(d) for d in dicts]
    out = []
    for c in coords:
        v = c.value
        if isinstance(v, Fraction):
            out.append(
                {
                    "value": float(v),
                    "numerator": v.numerator,
                    "denominator": v.denominator,
                }
            )
        elif isinstance(v, int) and not isinstance(v, bool):
            out.append({"value": float(v), "numerator": v, "denominator": 1})
        else:
            out.append({"value": float(v), "numerator": None, "denominator": None})
    return pa.array(out, type=struct_type)


def _path_rowwise_construct(dicts):
    # Internal-round-trip regime per row, then row-wise pa.array of storage dicts.
    coords = [Coordinate.model_construct(**d) for d in dicts]
    out = []
    for c in coords:
        v = c.value
        if isinstance(v, Fraction):
            out.append(
                {
                    "value": float(v),
                    "numerator": v.numerator,
                    "denominator": v.denominator,
                }
            )
        elif isinstance(v, int) and not isinstance(v, bool):
            out.append({"value": float(v), "numerator": v, "denominator": 1})
        else:
            out.append({"value": float(v), "numerator": None, "denominator": None})
    return pa.array(out, type=struct_type)


def _path_column_wise(dicts):
    # Canonical path: validate once at the boundary, then column-builder.
    coords = [Coordinate.model_validate(d) for d in dicts]
    return build_coordinate_struct_array(coords)


t_validate_rowwise = _runs(_path_rowwise_validate, scalar_dicts)
t_construct_rowwise = _runs(_path_rowwise_construct, scalar_dicts)
t_column = _runs(_path_column_wise, scalar_dicts)

{
    "N": N_FWD,
    "row-wise + model_validate (ms)": round(t_validate_rowwise, 1),
    "row-wise + model_construct (ms)": round(t_construct_rowwise, 1),
    "column-wise (canonical, ms)": round(t_column, 1),
    "column-wise speedup vs row-wise+validate": round(t_validate_rowwise / t_column, 2),
    "column-wise speedup vs row-wise+construct": round(
        t_construct_rowwise / t_column, 2
    ),
}

# %% [markdown]
# Validation is the dominant cost when present and unavoidable at the
# trust boundary, but choosing the *array-assembly* path is the
# architect's lever — the column-builder lifts the assembly out of
# Python's per-row hot loop, even when validation runs identically in
# front of it.

# %% [markdown]
# The canonical microbenchmark (`benchmarks/pydantic_pilot.py`, 100 000
# Coordinates × 5 runs, pydantic 2.12, Python 3.11) reports column-builder
# at 59.4 ± 3.9 ms vs row-wise `model_dump` at 259.3 ± 3.9 ms — **4.37×
# faster**.  The WP2 gate (≥ 2× required) passes.  See
# `benchmarks/pydantic_pilot_results.md` for the full log, including the
# `model_construct` vs `model_validate` reconstruction measurement.

# %% [markdown]
# ### Three numeric types — int / float / Fraction round-trip
#
# Sanity check: each `NumberType` reconstructs its own subtype losslessly
# through the StructArray.  Mirrors `tests/core/schemas/test_pilot_round_trip.py`.

# %%
sample_coords = [
    Coordinate(120, TimeUnit.quarters),
    Coordinate(1.5, TimeUnit.quarters),
    Coordinate(Fraction(3, 4), TimeUnit.quarters),
]
sample_arr = build_coordinate_struct_array(sample_coords)
rows = sample_arr.to_pylist()

[
    (struct_to_coordinate(rows[0], NumberType.int), int),
    (struct_to_coordinate(rows[1], NumberType.float), float),
    (struct_to_coordinate(rows[2], NumberType.fraction), Fraction),
]

# %%
cf_sample = CoordinateField.from_field(
    sample_arr, unit=TimeUnit.quarters, number_type=NumberType.fraction
)
cf_sample[0], cf_sample[1], cf_sample[2]

# %% [markdown]
# **Three validation regimes — one schema source.**  The same pydantic
# model drives all three:
#
# - **Trust boundary** — `Model.model_validate(...)` on each incoming
#   record (untrusted CSV column, `.jsonl` import, foreign Parquet).
# - **Internal round-trip** — `Model.model_construct(**dict)` on dicts
#   that came back from a TTA-written `pa.Array`, or
#   `struct_to_coordinate` for Coordinate's denormalised projection.
#   The `pa.Schema` is the trusted artifact; validators do not re-run.
# - **Bulk construction** — column-builder pattern over `model_fields`
#   (one `pa.array` per field name) when assembling a SemanticField
#   from many already-validated scalars.  Row-wise `model_dump` is
#   never used in this regime.

# %% [markdown]
# > **Key takeaway.**  An `EventData` exposes its contents along the
# > data-access axis: Layer 0 (raw Fields, including nested structs),
# > Layer 1 (semantic Fields with typed scalars), Layer 2 (external
# > integration).  Fields are cached views; EventData is never mutated.
# > For the orthogonal type-design axis — how each music concept is
# > expressed as Protocol / Scalar / Field — see
# > `how01_pitch_and_harmony_types`.
