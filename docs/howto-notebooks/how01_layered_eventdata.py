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
# EventData provides three layers of data access.  Layer 0 (raw table)
# always works on any EventData instance -- no special setup needed.
# Layers 1 and 2 add typed field views and external library integration.
#
# **Key principle:** EventData is never mutated.  `get_field()` returns
# a cached view over existing columns -- the EventData itself is
# unchanged.

# %% [markdown]
# ## Setup

# %%
from __future__ import annotations

from pathlib import Path

from timetoalign.fields.pitch import (
    EnharmonicPitchField,
    PitchField,
    SpecificPitchField,
)
from timetoalign.loader.score.tsv import TSVLoader

# Path to a DCML-style notes TSV (Chopin Op. 10 No. 3)
NOTES_TSV = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "data"
    / "vienna_1x22"
    / "ms3"
    / "chopin_op10_no3.notes.tsv"
)

# %% [markdown]
# ## Loading Real Data
#
# We load a DCML-style notes TSV via `TSVLoader`.  The loader parses
# pitches, durations, and measure context from the TSV columns and
# stores them in a PyArrow table.

# %%
loader = TSVLoader.from_file(NOTES_TSV)
events = loader.events
events

# %% [markdown]
# ## Layer 0 -- Raw Table Access
#
# Every EventData instance wraps a PyArrow table.  You can always
# access the underlying table and its columns directly, regardless
# of whether any semantic fields are available.

# %%
events.table

# %%
events.table.column_names

# %% [markdown]
# Individual columns are accessible as PyArrow arrays.  For instance,
# the `midi_pitch` column stores pitch data in a struct format:

# %%
midi_col = events.table.column("midi_pitch")
midi_col

# %% [markdown]
# You can extract sub-fields from struct columns using PyArrow compute:

# %%
import pyarrow.compute as pc

ep_values = pc.struct_field(midi_col, "ep")
ep_values

# %% [markdown]
# And convert to a pandas DataFrame for familiar tabular inspection:

# %%
events.to_pandas().head()

# %% [markdown]
# ## Layer 1 -- SemanticField Views
#
# Layer 1 provides **typed field views** over raw columns.  A field
# wraps a raw PyArrow struct column and adds semantic identity: element
# access returns typed scalars (e.g., `MidiPitch`), and the field
# carries metadata about what kind of pitch it represents.
#
# ### Creating a field externally
#
# You can construct a pitch field from a raw column extracted from the
# table.  This demonstrates the `from_field()` convention: you pass
# the raw column data and get back a semantically typed wrapper.

# %%
epf = EnharmonicPitchField.from_field(midi_col)
epf

# %% [markdown]
# Element access returns a typed scalar -- here, a `MidiPitch`:

# %%
epf[0]

# %%
pitch = epf[0]
pitch.midi_number

# %% [markdown]
# The field knows its `source` -- the raw column it wraps.  The
# `source` parameter records which raw column backs this field.

# %%
epf.name

# %% [markdown]
# ### Creating a field from user data
#
# More commonly, you might have a list of MIDI pitch values (e.g.,
# from a CSV file or a MIDI parser).  The `from_midi_numbers()`
# constructor accepts the data type users actually have:

# %%
standalone = EnharmonicPitchField.from_midi_numbers([60, 64, 67])
standalone[0], standalone[1], standalone[2]

# %% [markdown]
# Similarly, for spelled pitches, `from_labels()` accepts pitch
# strings like `"C4"`, `"E4"`, `"G4"`:

# %%
spelled = SpecificPitchField.from_labels(["C4", "E4", "G4"])
spelled[0], spelled[1], spelled[2]

# %% [markdown]
# ### Discovering fields via `get_field()`
#
# Rather than manually extracting columns, you can ask EventData to
# find and construct the appropriate field automatically.  `get_field()`
# inspects the table's columns, matches them against the requested
# field type, constructs the field, and caches it.

# %%
events.has_field(EnharmonicPitchField)

# %%
field = events.get_field(EnharmonicPitchField)
field

# %%
field[0]

# %% [markdown]
# ### Parent-type queries
#
# Requesting an abstract parent type (e.g. `PitchField`) discovers
# the most specific available subclass:

# %%
events.has_field(PitchField)

# %% [markdown]
# ### Caching is transparent
#
# Repeated `get_field()` calls return the **same** object -- the field
# is constructed once, then cached.  No user action is needed.

# %%
a = events.get_field(EnharmonicPitchField)
b = events.get_field(EnharmonicPitchField)
a is b

# %% [markdown]
# ### Both pitch representations
#
# This TSV contains both enharmonic (MIDI) and specific (spelled)
# pitch data.  Both are accessible as fields:

# %%
events.has_field(SpecificPitchField)

# %%
spf = events.get_field(SpecificPitchField)
spf[0]

# %% [markdown]
# ## Layer 2 -- External Libraries
#
# The raw PyArrow columns that back Layer 1 fields are also accessible
# to external libraries such as FlexOHR and pitchtypes.  Because these
# are optional dependencies, no code example is shown here -- but the
# principle is the same: extract a column from the table and pass it
# to the library's own constructors.
#
# **Key takeaway.**  The three layers form a progressive-disclosure
# stack: Layer 0 always works, Layer 1 adds typed field views via
# `get_field()`, and Layer 2 lets external packages operate on the
# same underlying data.  EventData is never mutated at any layer.
