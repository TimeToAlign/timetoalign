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
# # How to Load CSV/TSV with `column_specs` and `field_specs`
#
# Tabular loaders in Time To Align! turn **columns** into **fields** in two
# explicit steps:
#
# | Term | Meaning |
# |---|---|
# | **column** | A column in the original source (CSV / TSV / DataFrame / pa.Table). |
# | **field** | A raw or semantic `DataField` (TTA-internal). May be nested. |
#
# The loader's job is the column to field mapping:
#
# - **Step 1 — `column_specs`** processes columns one-by-one. Mandatory for
#   header-based sources; trivial for sources that already carry types.
# - **Step 2 — `field_specs`** combines or promotes the resulting fields.
#   Fully optional — many loaders are complete with Step 1 alone.
#
# This guide walks through the universal resolution table that drives Step 1,
# the `CompositeFieldSpec` mechanism for one-column-to-many-fields,
# the `FractionFieldSpec` shortcut, and a worked example on the Chopin
# `.solo` specimen.

# %% [markdown]
# ## Setup

# %%
from __future__ import annotations

import tempfile
from fractions import Fraction
from pathlib import Path

import pyarrow as pa

from timetoalign.core import EnharmonicPitch, TimeUnit
from timetoalign.loader.tabular import (
    CompositeFieldSpec,
    CsvLoader,
    FractionFieldSpec,
    IntFieldSpec,
    SoloLoader,
    resolve_field_spec,
)
from timetoalign.testdata import ensure_data

PERF_PRECISION = ensure_data("performance_precision")
CHOPIN_SOLO = PERF_PRECISION / "Chopin Nocturne Op. 9 No. 2.solo"

# A small temp directory whose lifetime spans the whole notebook.  Synthetic
# CSV / TSV examples in subsequent cells write through here so the standard
# `Loader.load(path)` API can pick them up.
TMP = Path(tempfile.mkdtemp(prefix="how04_"))


def write_csv(name: str, body: bytes) -> Path:
    """Write a synthetic CSV body to ``TMP / name`` and return its path."""
    p = TMP / name
    p.write_bytes(body)
    return p


# A small helper for compact pa.Table previews. The notebook re-uses this
# whenever it needs to peek at the working table; defining it once keeps
# the example cells terse.
def head_table(table: pa.Table, n: int = 5) -> dict[str, list]:
    """Return the first ``n`` rows of ``table`` as a column-keyed dict."""
    return {
        name: table.column(name).slice(0, n).to_pylist() for name in table.column_names
    }


# %% [markdown]
# ## 1. From columns to fields: the two-step pipeline
#
# We start with the simplest case — a CSV with a header line and one
# Python type per column. The keys of `column_specs` are source-column
# names; the values are anything that resolves through the **universal
# resolution table** (Section 2). Here, a bare `float` / `int` / `str` is
# all we need for the columns that aren't already canonical (the loader
# still resolves `start` / `end` from the underlying source on its own):

# %%
mini_csv = (
    b"id,start,end,pitch,label\n"
    b"e0,0.0,0.5,60,intro\n"
    b"e1,0.5,1.0,64,intro\n"
    b"e2,1.0,1.5,67,verse\n"
    b"e3,1.5,2.0,72,verse\n"
)
mini_path = write_csv("mini.csv", mini_csv)


class MiniLoader(CsvLoader):
    column_specs = {"pitch": int, "label": str}


mini = MiniLoader()
mini.load(mini_path)
events = mini.get_events()
head_table(events.table)

# %% [markdown]
# Step 1 has produced one raw field per declared source column. The raw
# fields are reachable through `get_raw()`; `get_field()` is reserved for
# **semantic** fields with paired-class metadata (we'll meet that path in
# Section 4):

# %%
{
    "pitch": events.get_raw("pitch"),
    "label": events.get_raw("label"),
}

# %% [markdown]
# Note the asymmetry: **columns are a source artefact, fields are a TTA
# artefact**. A loader without `column_specs` leaves the non-canonical
# source columns alone as opaque property columns; with `column_specs`,
# each named column is processed into a typed field whose semantics
# travel with it.

# %% [markdown]
# ## 2. The universal resolution table
#
# Every entry in `column_specs` (and every entry in a `CompositeFieldSpec`'s
# `parts`) is resolved by the same table:
#
# | User passes | Resolved as |
# |---|---|
# | `int` / `float` / `str` / `Fraction` (Python type) | matching FieldSpec leaf |
# | `pa.int64()` / `pa.float64()` / `pa.string()` (pa.DataType) | matched by-type |
# | a raw `DataField` subclass (`NumericField`, `StringField`, …) | spec emitting that DataField |
# | any `FieldSpec` instance (including `CompositeFieldSpec` subclasses) | as-is |
# | any callable `(pa.Array) -> DataField` | wrapped automatically |
#
# The dispatcher is `resolve_field_spec`. The following cells run it
# directly so the resolution table stops being abstract:

# %%
# Python-type input -> matching FieldSpec leaf
{
    "int": type(resolve_field_spec(int)).__name__,
    "float": type(resolve_field_spec(float)).__name__,
    "str": type(resolve_field_spec(str)).__name__,
    "Fraction": type(resolve_field_spec(Fraction)).__name__,
}

# %%
# pa.DataType input -> matched by-type to the equivalent FieldSpec
{
    "pa.int64()": type(resolve_field_spec(pa.int64())).__name__,
    "pa.float64()": type(resolve_field_spec(pa.float64())).__name__,
    "pa.string()": type(resolve_field_spec(pa.string())).__name__,
}

# %%
# A FieldSpec instance is returned as-is (identity check).
spec = IntFieldSpec(name="channel")
resolve_field_spec(spec) is spec

# %%
# A pre-built FieldSpec can also be used directly inside column_specs.
# Here, the resolution table is bypassed because the value already IS a
# FieldSpec.
typed_csv = b"id,start,end,x\n" b"e0,0.0,0.5,1\n" b"e1,0.5,1.0,2\n" b"e2,1.0,1.5,3\n"
typed_path = write_csv("typed.csv", typed_csv)


class TypedLoader(CsvLoader):
    column_specs = {"x": IntFieldSpec(name="x_renamed")}


typed = TypedLoader()
typed.load(typed_path)
typed.get_events().table.column_names


# %% [markdown]
# The `name=` kwarg renames the resulting field. The default name is the
# source-column key (dict form) or the spec's class-level default
# (iterable form).
#
# A callable `(pa.Array) -> DataField` is wrapped automatically — useful
# when a column needs a one-off transformation that doesn't justify its
# own `FieldSpec` subclass. The next two sections cover the standard
# multi-part cases that DO have dedicated specs.

# %% [markdown]
# ## 3. `CompositeFieldSpec`: one column, multiple fields
#
# Some columns pack several values into one string. The classic
# musicological example is `1+3/8` — measure number, then a fractional
# offset inside the measure. `CompositeFieldSpec` is the universal
# splitter: a separator (or regex pattern) plus a `parts` declaration
# that mirrors `column_specs`:

# %%
composite_csv = (
    b"id,start,end,position\n"
    b"e0,0.0,0.5,1+0/8\n"
    b"e1,0.5,1.0,1+3/8\n"
    b"e2,1.0,1.5,2+1/4\n"
    b"e3,1.5,2.0,2+5/8\n"
)
composite_path = write_csv("composite.csv", composite_csv)


class CompositeLoader(CsvLoader):
    column_specs = {
        "position": CompositeFieldSpec(
            separator="+",
            parts={
                "measure": int,
                "offset": Fraction,
            },
        ),
    }


comp = CompositeLoader()
comp.load(composite_path)
head_table(comp.get_events().table)

# %% [markdown]
# Each entry of `parts` is resolved through the same universal table — so
# `int` becomes `IntFieldSpec()` and `Fraction` becomes `RationalFieldSpec()`.
# Composites can also nest: a `parts` entry may itself be a
# `CompositeFieldSpec`.
#
# Because the `1/4` pattern is so common — a fraction split on `/` — TTA
# ships a pre-configured subclass that hides the internal split:

# %%
# FractionFieldSpec without a unit emits a raw RationalField.
raw_spec = FractionFieldSpec(name="x")
{"unit": raw_spec.unit}

# %% [markdown]
# Bound to a `TimeUnit`, the same spec emits a semantic `DenominateNumberField`
# instead. Step 1 jumps straight to semantic because the unit is enough to
# anchor the field's meaning:

# %%
sem_spec = FractionFieldSpec(name="x", unit=TimeUnit.quarters)
{"unit": str(sem_spec.unit)}

# %% [markdown]
# A bound `unit` is the trigger: with `unit=None` (the default) the spec
# stays raw and emits a `RationalField`; with a `unit` set, the same spec
# emits a `DenominateNumberField` whose bound unit travels through the
# rest of the pipeline.
#
# This is the model for future TTA-shipped composite specs: each one
# encapsulates a real-world parsing pattern so that loaders read like
# musicology, not like regex tutorials.

# %% [markdown]
# ## 4. The `.solo` worked example
#
# `.solo` is a header-less tab-separated format. Each row carries six
# columns:
#
# 1. Measure-plus-offset (`1+3/8`)
# 2. Duration as a fraction of a quarter note (`1/4`)
# 3. Channel
# 4. MIDI pitch
# 5. Velocity
# 6. Note ID
#
# The Chopin specimen lets us run the full Step 1 + Step 2 pipeline on a
# realistic source:

# %%
{"first lines": CHOPIN_SOLO.read_text().splitlines()[:5]}

# %% [markdown]
# `SoloLoader` declares both steps. `column_specs` is an iterable
# (positional) because the source has no header; `field_specs` then
# promotes raw `pitch` and `note_id` to semantic fields:

# %%
loader = SoloLoader()
loader.load(CHOPIN_SOLO)

# %% [markdown]
# After Step 1, the working table holds typed fields — measure +
# fractional offset broken out, duration bound to quarters, the three
# integer columns, and the string ID:

# %%
events = loader.get_events()
head_table(events.table)

# %% [markdown]
# Step 2 has promoted the raw `pitch` int into a semantic
# `EnharmonicPitchField` and wrapped `note_id` in a shallow `IdField`.
# The blueprint shorthand `source_fields="pitch"` reads as "one raw
# field called `pitch`, fed into the target's canonical `value`":

# %%
events.table.column_names

# %% [markdown]
# `EnharmonicPitchField` is now reachable by type, and indexing it returns
# `EnharmonicPitch` scalars. The faithfulness rule applies: the field
# records the MIDI pitch number that the source data carried, not anything
# inferred about spelling — both `G♯3` and `A♭3` show as MIDI 56 because
# `.solo` does not carry an accidental:

# %%
ep_field = events.get_field(EnharmonicPitch)
{"first 5": [ep_field[i] for i in range(5)]}

# %%
# IdField holds the original note identifiers. The Chopin specimen
# re-uses some IDs across event onsets/offsets, which the shallow form
# preserves verbatim.
from timetoalign.core import Id

id_field = events.get_field(Id)
{"first 5": [id_field[i] for i in range(5)]}

# %% [markdown]
# ## 5. Property columns
#
# By default, source columns that are NOT consumed by any `column_specs`
# entry survive in the EventData as **property columns** — convenient for
# ad-hoc inspection but excluded from the field machinery. The
# `properties=` kwarg on `get_events()` controls which ones make it
# through:
#
# | Value | Meaning |
# |---|---|
# | `True` (default) | all remaining source columns survive |
# | `False` | no property columns; the EventData carries only fields |
# | `("col1", "col2")` | named subset |

# %%
extras_csv = (
    b"id,start,end,pitch,label,scribbled_note,page\n"
    b"e0,0.0,0.5,60,intro,one,1\n"
    b"e1,0.5,1.0,64,intro,two,1\n"
    b"e2,1.0,1.5,67,verse,three,2\n"
)
extras_path = write_csv("extras.csv", extras_csv)


class ExtrasLoader(CsvLoader):
    column_specs = {"pitch": int, "label": str}


ex = ExtrasLoader()
ex.load(extras_path)

# %%
{
    "properties=True  (default)": ex.get_events(properties=True).table.column_names,
    "properties=False": ex.get_events(properties=False).table.column_names,
    "properties=('page',)": ex.get_events(properties=("page",)).table.column_names,
}

# %% [markdown]
# Property columns let users keep source-side metadata alongside the
# fields without forcing every loose annotation through `column_specs`.
# When you want a property column to gain semantic identity — to become
# a `DataField` proper — that's exactly when `field_specs` enters: name
# the column in Step 1 with the appropriate spec, and Step 2 promotes it.
