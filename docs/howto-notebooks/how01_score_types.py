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
# # How to Work with Score Types
#
# Typed scalars and semantic fields for pitch, notes, measures, and harmonies.

# %% [markdown]
# ## The Problem
#
# PyArrow stores pitch as a raw struct `{ep: 59, epc: 11}`. What does `ep` mean?
# Is `59` a MIDI number, a frequency, or an index? Without semantic typing, every
# consumer must re-derive meaning from column names and conventions.
# {{< glossary SemanticField >}} subclasses solve this: they wrap raw structs with
# typed metadata, and their `__getitem__` returns frozen dataclass scalars that
# carry domain knowledge.

# %% [markdown]
# ## Loading Score Data

# %%
from timetoalign.loader.score import TSVLoader
from timetoalign.testdata import ensure_data

VIENNA = ensure_data("vienna_1x22")
SCORE = ensure_data("score")

CHOPIN_NOTES = VIENNA / "ms3" / "chopin_op10_no3.notes.tsv"
CHOPIN_MEASURES = VIENNA / "ms3" / "chopin_op10_no3.measures.tsv"

loader = TSVLoader.from_file(CHOPIN_NOTES, CHOPIN_MEASURES)
store = loader.store
store

# %% [markdown]
# ## PitchField: Typed Pitch Access
#
# `PitchField` wraps the `midi_pitch` struct column `{ep, epc}` and returns
# `MidiPitch` scalars. No more guessing what `ep` stands for.

# %%
pitch_field = store.notes.pitch_field
pitch_field

# %%
p = pitch_field[0]
p

# %%
p.midi_number, p.pitch_class

# %% [markdown]
# ## PitchField (SP): Rich Pitch Representation
#
# `PitchField` with SP (spelled pitch) wraps the `spelled_pitch` struct and
# returns `SpelledPitch` scalars with step name, accidental, octave,
# fifths-based spelling, and cents.

# %%
spelled = store.notes.spelled_pitch_field
spelled[0]

# %%
sp = spelled[0]
sp.step, sp.alter, sp.octave, sp.fifths, sp.cents

# %% [markdown]
# ## Note Scalars
#
# Each row in the notes table is a `Note` -- a frozen dataclass combining onset,
# duration, pitch, voice, and staff into a single typed object.

# %%
from timetoalign.core.scalars import Note  # noqa: F401

note = store.notes.get_note(0)
note

# %%
note.onset, note.duration, note.pitch, note.voice, note.staff

# %% [markdown]
# ## Measure Scalars
#
# `Measure` captures measure number, onset, duration, time signature, and
# key signature in a single object.

# %%
from timetoalign.core.scalars import Measure  # noqa: F401

measure = store.measures.get_measure(0)
measure

# %%
measure.mc, measure.mn, measure.onset, measure.time_signature, measure.key_signature

# %% [markdown]
# ## Harmony Types
#
# DCML harmony labels encode Roman-numeral analysis with key context.
# `HarmonyField` wraps these columns and returns `Harmony` scalars.

# %%
BEETHOVEN_HARMONIES = (
    SCORE / "beethoven_op18-4iv_multimodal" / "ABC" / "n04op18-4_04.harmonies.tsv"
)
harm_loader = TSVLoader.from_file(BEETHOVEN_HARMONIES)
harm_store = harm_loader.store

# %%
harmony_field = harm_store.annotations.harmony_field
harmony_field

# %%
h = harmony_field[0]
h

# %%
h.label, h.globalkey, h.localkey, h.numeral

# %% [markdown]
# ## Protocol Conformance
#
# Scalars and fields both implement the same protocols, giving you a uniform
# interface whether you hold a single value or an entire column.

# %%
from timetoalign.core.protocols import HarmonyLike, NoteLike, PitchLike

# %%
# Scalars satisfy their protocols
isinstance(pitch_field[0], PitchLike), isinstance(note, NoteLike), isinstance(
    h, HarmonyLike
)

# %%
# Fields also satisfy the same protocols
isinstance(pitch_field, PitchLike)

# %% [markdown]
# ## Parquet Round-Trip
#
# Semantic metadata survives Parquet serialisation. Write a table with typed
# fields, read it back, and the reconstructed fields carry the same types.

# %%
import json
import tempfile

import pyarrow as pa
import pyarrow.parquet as pq

# %%
# Build a table from the PitchField column
pa_field = pitch_field.to_field()
table = pa.table(
    {pa_field.name: pitch_field.to_pyarrow()}, schema=pa.schema([pa_field])
)

with tempfile.NamedTemporaryFile(suffix=".parquet") as f:
    pq.write_table(table, f.name)
    loaded = pq.read_table(f.name)

# %%
# Metadata survives the round-trip
meta = json.loads(loaded.schema.field(pa_field.name).metadata[b"timetoalign"])
meta

# %%
# Reconstruct the PitchField from the loaded table
from timetoalign.fields import PitchField

col_name = pa_field.name
loaded_arr = loaded.column(col_name).combine_chunks()
loaded_pf = PitchField.from_field(loaded_arr, name=col_name)
loaded_pf[0]
