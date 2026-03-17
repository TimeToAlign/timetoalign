# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.1
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# # How-To: Layered EventData Access
#
# Time To Align! loaders follow a two-phase pattern:
#
# 1. **Load** -- `loader.load(file)` reads the source into a faithful table.
# 2. **Access** -- `loader.get_events()` assembles an EventData with control
#    over which columns are included.
#
# EventData then provides three layers of data access:
#
# - **Layer 0** -- Raw table (`events.table`, `events.get_raw("col")`)
# - **Layer 1** -- Semantic fields (`events.get_field("start")`, blueprints)
# - **Layer 2** -- External library integration (FlexOHR, pitchtypes)
#
# **Key principle:** EventData is never mutated.  `get_field()` returns
# a cached view over existing columns -- the EventData itself is
# unchanged.

# %% [markdown]
# ## Setup

# %%
from __future__ import annotations

from pathlib import Path

from timetoalign.fields.pitch import PitchField
from timetoalign.loader.score.tsv import TSVLoader

# Path to a DCML-style notes TSV (Chopin Op. 10 No. 3)
try:
    TTA_DIR = Path(__file__).resolve().parents[2]
except NameError:
    TTA_DIR = Path(".").resolve().parents[1]
NOTES_TSV = (
    TTA_DIR / "tests" / "data" / "vienna_1x22" / "ms3" / "chopin_op10_no3.notes.tsv"
)

# %% [markdown]
# ## Phase 1: Loading
#
# `TSVLoader.from_file()` reads a DCML-style notes TSV and builds
# an internal table.  After loading, the loader holds the data ready
# for assembly into EventData.

# %%
loader = TSVLoader.from_file(NOTES_TSV)
loader

# %% [markdown]
# ## Phase 2: get_events() -- Controlling Columns
#
# `get_events()` assembles an EventData from the loaded data.
# The `properties` parameter controls which non-field columns appear:
#
# - `True` (default): all columns
# - `False`: only field columns (start, end, duration) + core (id, name, event_type, temporal_type)
# - tuple of names: selected property columns

# %%
# All properties (default)
events = loader.get_events()
events

# %%
events.table.column_names

# %%
# Fields only -- no property columns like mc, mn, staff, voice
events_fields = loader.get_events(properties=False)
events_fields.table.column_names

# %%
# Selected properties
events_selected = loader.get_events(properties=("mc", "mn"))
events_selected.table.column_names

# %% [markdown]
# ## Layer 0 -- Raw Table Access
#
# Every EventData wraps a PyArrow table.  You can always access the
# underlying table directly -- no semantic setup needed.

# %%
events.table

# %%
events.table.column_names

# %% [markdown]
# `get_raw()` wraps a column in a lightweight raw DataField
# (StructField, NumericField, StringField) without adding any
# semantic identity.  This is the same data as `events.table`,
# just wrapped for convenient field-level access.

# %%
raw_start = events.get_raw("start")
raw_start

# %%
raw_start[0]

# %% [markdown]
# ## Layer 1 -- Default Fields (start, end, duration)
#
# Every EventData has three core temporal columns: `start`, `end`,
# and `duration`.  `get_field()` with a column name returns the
# appropriate SemanticField: `CoordinateField` for start/end,
# `DurationField` for duration.  Both inherit from `NumberField`
# and wrap the coordinate struct `{value, numerator, denominator}`.

# %%
start = events.get_field("start")
start

# %%
start[0]

# %%
end = events.get_field("end")
end[0]

# %%
dur = events.get_field("duration")
dur

# %%
dur[0]

# %% [markdown]
# A SemanticField always gives access to its underlying raw field
# via `get_raw()`:

# %%
start.get_raw()

# %% [markdown]
# ## Layer 1 -- PitchField (Standalone)
#
# The unified `PitchField` handles all pitch types via a single
# keyword argument: `ep` (MIDI), `spc` (spelled pitch class),
# `sp` (spelled pitch), `epc` (pitch class 0-11), `gp` (generic
# pitch), `gpc` (diatonic step 0-6).

# %%
pf = PitchField.from_raw(ep=[60, 64, 67])
pf

# %%
pf[0], pf[1], pf[2]

# %%
pf_sp = PitchField.from_labels(["C4", "E4", "G4"])
pf_sp

# %%
pf_sp[0], pf_sp[1], pf_sp[2]

# %% [markdown]
# ## Layer 1 -- PitchField from EventData (Blueprint)
#
# A **blueprint** PitchField is constructed with a column *name*
# instead of data.  Pass it to `get_field()` and EventData resolves
# the column, constructs the live field, and caches it.

# %%
pitch_blueprint = PitchField(ep="midi_pitch")
pitch_blueprint  # blueprint -- no data yet

# %%
pf_live = events.get_field(pitch_blueprint)
pf_live

# %% [markdown]
# The original values are EnharmonicPitch scalars, combining MIDI pitch
# with enharmonic spelling:

# %%
pf_live[0], pf_live[1], pf_live[2]

# %% [markdown]
# Repeated calls return the **same** cached object:

# %%
events.get_field(PitchField(ep="midi_pitch")) is pf_live

# %% [markdown]
# ## PitchField Conversions
#
# `.to()` converts between pitch types.  Only information-losing
# conversions are permitted (specific -> class, richer space ->
# coarser space).

# %% [markdown]
# **EPC** (enharmonic pitch class) gives the chromatic pitch class (0--11):

# %%
epc = pf_live.to("epc")
epc[0], epc[1], epc[2]

# %% [markdown]
# **GPC** (generic pitch class) gives the diatonic step name (C--B, 0--6):

# %%
gpc = pf_live.to("gpc")
gpc[0], gpc[1], gpc[2]

# %% [markdown]
# ## Layer 2 -- External Libraries
#
# The raw PyArrow columns backing Layer 1 fields are also accessible
# to external libraries (FlexOHR, pitchtypes).  Extract a column from
# the table and pass it to the library's constructors.
#
# **Key takeaway.**  The loader-first pipeline gives you:
#
# 1. `loader.get_events()` -- an EventData with column control
# 2. Three layers of access: raw table, semantic fields, external libs
#
# EventData is never mutated.  Fields are cached views.
