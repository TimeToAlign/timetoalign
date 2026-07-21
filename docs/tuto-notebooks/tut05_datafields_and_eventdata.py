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
# # DataFields and Layered EventData
#
# *Learn how every music concept in Time To Align! is expressed as the
# same Protocol / Scalar / Field triple, and how a loaded `EventData`
# affords typed views over its raw columns.*
#
# This is a foundational tutorial.  By the end you will be able to read a
# table of musical events, ask it for the fields you care about, and trust
# that whatever comes back is strictly typed — a `Coordinate` is never a
# bare float, a pitch is never a bare integer.  The same machinery you meet
# here on a Chopin notes table underlies every loader in the library.

# %% [markdown]
# ## Setup

# %%
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# The headless verifier runs this script from the notebook directory. Prefer
# the repository containing this source over any separately installed copy.
_cwd = Path.cwd().resolve()
_repo_root = next(
    (
        parent
        for parent in (_cwd, *_cwd.parents)
        if (parent / "timetoalign" / "__init__.py").exists()
    ),
    _cwd,
)
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from timetoalign import Ms3Loader  # noqa: E402
from timetoalign.core.events import (  # noqa: E402
    EnharmonicPitch,
    EnharmonicPitchClass,
    EnharmonicPitchField,
    SpecificPitch,
    SpecificPitchField,
)
from timetoalign.core.fields import (  # noqa: E402
    NumericField,
    StringField,
    StructField,
    build_struct_array,
)
from timetoalign.core.protocols import GenericPitchLike, PitchLike  # noqa: E402
from timetoalign.core.time import CoordinateField  # noqa: E402
from timetoalign.loader.score.stores.notes import NoteEventData  # noqa: E402
from timetoalign.storage import MultipleFieldsError  # noqa: E402
from timetoalign.testdata import ensure_data  # noqa: E402

VIENNA = ensure_data("vienna_1x22")
CHOPIN_NOTES = VIENNA / "ms3" / "chopin_op10_no3.notes.tsv"

# %% [markdown]
# ## The Triple — Protocol, Scalar, Field
#
# Every musical concept in the library is modelled three times over, at
# three altitudes.  The pattern is uniform: learn it once here and it
# holds for coordinates, durations, pitches, harmonies, measures —
# everything.
#
# | Role | What it is | Example | Answers the question |
# |------|------------|---------|----------------------|
# | **Protocol** | A `runtime_checkable` shape | `PitchLike` | *"Does this behave like a pitch?"* |
# | **Scalar** | One frozen, validated value | `EnharmonicPitch(60)` | *"What is this one note?"* |
# | **Field** | A columnar wrapper over many | `EnharmonicPitchField` | *"How do I hold a million of them?"* |
#
# A **Scalar** is a single immutable value you hold in your hand at a
# system edge.  A **Field** is the bulk, PyArrow-backed counterpart — it
# stores thousands of them columnar and hands you a Scalar only when you
# index into it.  A **Protocol** is the structural contract that lets you
# ask whether *something* is pitch-shaped without caring which exact class
# it is.

# %% [markdown]
# ### The three side by side
#
# One enharmonic pitch, seen as all three.  The Scalar satisfies the
# Protocol; the Field's paired scalar class is exactly that Scalar.

# %%
note = EnharmonicPitch(60)
note

# %%
(
    ("scalar", note),
    ("satisfies PitchLike", isinstance(note, PitchLike)),
    ("field's scalar class", EnharmonicPitchField.scalar_cls.__name__),
)

# %% [markdown]
# The short typed `repr` (`EP(C4)`) is the standard form across the whole
# scalar inventory: an abbreviation plus the pretty token.

# %% [markdown]
# ## Layer 0 — Raw Fields
#
# Before any semantics, a table is just typed PyArrow columns.  **DataFields**
# wrap those columns so the PyArrow type travels with the data, but they add
# *no* meaning: a raw column knows it is a struct of three numbers, not that
# those numbers are a musical coordinate.
#
# Three concrete raw types cover the cases you will meet — `NumericField`,
# `StringField`, and `StructField` — each validating the PyArrow type at
# construction time.

# %%
nf = NumericField(pa.array([60, 64, 67]), pa.field("midi_pitch", pa.int64()))
nf[0], nf[1], nf[2]

# %%
sf_str = StringField(pa.array(["C4", "E4", "G4"]), pa.field("pitch_name", pa.utf8()))
sf_str[0], sf_str[2]

# %% [markdown]
# A `StructField` is itself a small typed tree.  Sub-fields are reachable by
# name and come back as typed `DataField` objects in their own right — this
# is why "raw Field" means more than "raw column".

# %%
struct_arr = pa.array(
    [{"x": 1.0, "y": 2.0}, {"x": 3.0, "y": 4.0}],
    type=pa.struct([pa.field("x", pa.float64()), pa.field("y", pa.float64())]),
)
sf = StructField(struct_arr, pa.field("pos", struct_arr.type))
sf.field_names

# %% [markdown]
# ### Raw fields from a loaded table
#
# `EventData.get_raw(name)` gives you any column as a raw `DataField`,
# *without* the unit / domain annotations a semantic view would add.  Here is
# the `start` column of a Chopin notes table — onset coordinates stored as
# `{value, numerator, denominator}` (the numerator / denominator preserve
# rational precision through a Parquet round-trip).

# %%
events = Ms3Loader.from_file(CHOPIN_NOTES).get_events()
raw_start = events.get_raw("start")
raw_start

# %%
# A raw coordinate carries no unit semantics: index 3 is the bare onset
# (value=0.5, numerator=1, denominator=2).  Half a quarter into the piece —
# but the raw level does not know it is "quarters", and it is certainly not a
# pitch.  Semantics arrive at Layer 1.
raw_start[3]

# %%
# The nested sub-fields are reachable from the raw level too.
raw_start.field_names

# %% [markdown]
# ## Default Semantic Fields
#
# Every `EventData` carries three core temporal fields — `start`, `end`, and
# `duration` — and `get_field()` with the column name returns the right
# semantic view automatically: a `CoordinateField` for `start` / `end`, a
# `DurationField` for `duration`.  Indexing the field returns the matching
# Scalar, now *with* its unit.

# %%
start = events.get_field("start")
start

# %%
# Index 8 is the note that starts at quarter 1 — now a Coordinate scalar,
# carrying its unit (compare raw_start[3] above, which had none).
s8 = start[8]
s8.value, s8.unit

# %%
events.get_field("end")[8], events.get_field("duration")[8]

# %% [markdown]
# ## Creating Semantic Fields from Raw Columns
#
# `start` came typed because the loader annotated it.  But a source table
# routinely carries columns whose *meaning* the loader did not pin down — a
# bare `midi_pitch` integer column, say.  You promote such a column to a
# typed field yourself.
#
# ### The scalar-class path
#
# Start from the Scalar.  For enharmonic pitch the raw datum is a single MIDI
# number, so a blueprint field can `emit()` a typed field directly from an
# integer array:

# %%
pf_ep_built = EnharmonicPitchField(name="midi_pitch").emit(pa.array([60, 64, 67]))
pf_ep_built[0], pf_ep_built[1], pf_ep_built[2]

# %% [markdown]
# Specific pitch carries spelling, so build the scalars from labels with the
# scalar class's own constructor (`SpecificPitch.from_label`), then assemble
# them into the paired field:

# %%
spelled = [SpecificPitch.from_label(label) for label in ["C♯4", "E4", "G4"]]
sp_arr = build_struct_array(SpecificPitch, spelled)
pf_sp_built = SpecificPitchField.from_field(
    (sp_arr, pa.field("specific_pitch", sp_arr.type))
)
pf_sp_built[0], pf_sp_built[1], pf_sp_built[2]

# %% [markdown]
# ### The blueprint variant — deferred resolution
#
# A **blueprint** is a paired Field instance that names a source column but
# carries no data.  Hand it to `get_field()` and the resolution is deferred
# to the table: the column is looked up, the live field constructed, and the
# result cached.  This is how you reach a typed pitch view on real loader
# output, where the same kind of pitch may live under different column names.

# %%
blueprint = EnharmonicPitchField(source_fields="midi")
pf_ep_live = events.get_field(blueprint)
pf_ep_live[3], pf_ep_live[8]

# %% [markdown]
# ## Scalar ⇄ Field — the payoff of strict typing
#
# This is the whole point.  A Field may hold a million entries columnar, yet
# indexing it gives you back exactly one fully-typed Scalar — no parsing, no
# guessing what the number means.  Index 3 of the Chopin notes is a black
# key: the enharmonic view spells it both ways, the specific view keeps the
# notated spelling.

# %%
pf_ep = events.get_field(EnharmonicPitch)
pf_sp = events.get_field(SpecificPitch)
(pf_ep[3], pf_sp[3])

# %% [markdown]
# `get_field(EnharmonicPitch)` discovered the `midi` column by its
# scalar *type*, not its name.  Ask twice and you get the identical object:

# %%
events.get_field(EnharmonicPitch) is pf_ep

# %% [markdown]
# ## Caching
#
# `get_field()` memoises its result, so repeated requests — by name, by
# class, or by blueprint — return the same cached field.

# %%
events.get_field("start") is start

# %% [markdown]
# ## Field Discovery
#
# When you do not know which fields a table carries, the discovery API finds
# them for you.

# %%
events.has_field(EnharmonicPitchField)

# %% [markdown]
# `get_field(ScalarClass)` resolves a single field by type.  If two columns
# held the *same* scalar type, it would refuse to guess and raise
# `MultipleFieldsError`, whose message tells you exactly how to disambiguate.
# Here we force the ambiguity by giving the table a second MIDI-pitch column:

# %%
mp_field = events.table.schema.field("midi")
table_two = events.table.append_column(
    pa.field("midi_2", mp_field.type, metadata=mp_field.metadata),
    events.table.column("midi"),
)


class _AmbiguousNoteEventData(NoteEventData):
    _afforded_fields = {
        **NoteEventData._afforded_fields,
        "midi_2": EnharmonicPitchField,
    }


events_two = _AmbiguousNoteEventData(
    table_two, unit=events._unit, number_type=events._number_type
)

try:
    events_two.get_field(EnharmonicPitch)
except MultipleFieldsError as exc:
    error_hint = str(exc)
error_hint

# %% [markdown]
# The `name=` keyword resolves it:

# %%
events_two.get_field(EnharmonicPitch, name="midi")[3]

# %% [markdown]
# To discover *every* field whose scalar satisfies a Protocol, use
# `get_fields_satisfying()`.  `PitchLike` is deliberately minimal —
# future-proofed for microtonal pitches — so it is over-inclusive: it matches
# the temporal coordinate fields too, because they satisfy the same minimal
# shape.

# %%
[(f.name, type(f).__name__) for f in events.get_fields_satisfying(PitchLike)]

# %% [markdown]
# When you specifically want 12-TET pitches (anything carrying a
# `pitch_class`), pass the narrower `GenericPitchLike` instead:

# %%
[(f.name, type(f).__name__) for f in events.get_fields_satisfying(GenericPitchLike)]

# %% [markdown]
# ## Parquet-embedded metadata
#
# A semantic field stores its identity — its type, unit, and domain — inside
# the PyArrow field's metadata.  That metadata survives Parquet
# serialisation, so a typed field can be reconstructed straight from a file
# without re-running the loader.  Write `start` to Parquet, read it back, and
# the round-tripped field still hands you `Coordinate` scalars with their
# unit intact.

# %%
cf_start = events.get_field("start")
pa_field = cf_start.to_field()
table = pa.table({pa_field.name: cf_start.to_pyarrow()}, schema=pa.schema([pa_field]))

with tempfile.NamedTemporaryFile(suffix=".parquet") as f:
    pq.write_table(table, f.name)
    loaded = pq.read_table(f.name)

# The metadata blob rides along under the b"timetoalign" key.
json.loads(loaded.schema.field(pa_field.name).metadata[b"timetoalign"])

# %%
loaded_cf = CoordinateField.from_table(loaded)
loaded_cf[8]

# %% [markdown]
# ## Recap
#
# - Every concept is a **Protocol / Scalar / Field** triple.  A Scalar is one
#   validated value; a Field holds many columnar; a Protocol asks *"is this
#   the right shape?"*.
# - An `EventData` exposes its columns at two levels: **Layer 0** raw
#   `DataField`s (`get_raw`, no semantics) and **Layer 1** typed semantic
#   fields (`get_field`, scalars on access).  The `EventData` itself is never
#   mutated — `get_field()` returns cached views.
# - Discover fields by name, by scalar class, by blueprint, or by Protocol;
#   typed metadata survives Parquet so a field rebuilds straight from a file.
#
# The idioms generalise.  A scalar's short form is its abbreviation —
# `EnharmonicPitchClass(2)` reads back as `EPC(D)` — and the same triple
# carries every music concept the library models.  The pitch-and-harmony
# tutorial applies exactly this principle across formats, showing the same
# sounding pitch reached from many sources.

# %%
EnharmonicPitchClass(2)
