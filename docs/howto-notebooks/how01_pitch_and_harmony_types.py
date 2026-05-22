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
# # How to Work with Pitch and Harmony Types
#
# Pitch and harmony concepts as protocols, scalars, and fields — the
# **type-design axis** of the library.
#
# This notebook covers the orthogonal counterpart to
# `how01_datafields_and_eventdata`: where that one is about *getting
# data out of* a loaded EventData (Layer 0 / 1 / 2), this one is about
# *how each music concept is modelled* — at the level of a structural
# Protocol, a frozen Scalar value, and a fielded paired Field.

# %% [markdown]
# ## Setup

# %%
from __future__ import annotations

import json
import tempfile

import pyarrow as pa
import pyarrow.parquet as pq

from timetoalign.core.protocols import (
    DcmlHarmonyLike,
    EnharmonicPitchLike,
    GenericPitchLike,
    HarmonyLabelLike,
    PitchLike,
    RomanNumeralHarmonyLike,
    SpecificPitchClassLike,
    SpecificPitchLike,
    WesternTertianHarmonyLike,
)
from timetoalign.core.scalars.harmony import DcmlHarmony, HarmonyLabel
from timetoalign.core.scalars.pitch import (
    EnharmonicPitchClass,
    GenericPitch,
    MidiPitch,
    SpecificPitch,
    SpecificPitchClass,
)
from timetoalign.fields.harmony import DcmlLabelField, WesternTertianHarmonyField
from timetoalign.fields.pitch import PitchField
from timetoalign.fields.schemas import DcmlStorageSchema, WesternTertianSchema
from timetoalign.loader.score.tsv import TSVLoader
from timetoalign.testdata import ensure_data

VIENNA = ensure_data("vienna_1x22")
CHOPIN_NOTES = VIENNA / "ms3" / "chopin_op10_no3.notes.tsv"

# %% [markdown]
# ## The Type-Design Axis
#
# Every pitch or harmony concept is expressed at three levels:
#
# | Level | Role | Example |
# |-------|------|---------|
# | **Protocol** | Structural contract (`isinstance`-checkable) | `GenericPitchLike` |
# | **Scalar** | Frozen dataclass for a single value | `EnharmonicPitchClass(pitch_class=0)` |
# | **Field** | Columnar wrapper over a PyArrow struct | `PitchField(epc=...)` |
#
# Scalars satisfy their corresponding protocol; fields wrap arrays and
# return scalars on element access; protocols enable generic dispatch
# across the whole hierarchy.
#
# This is **distinct from the data-access axis** (Layer 0 / 1 / 2) shown
# in `how01_datafields_and_eventdata`: that axis is about how a loaded
# EventData exposes its contents.  The type-design axis here is about
# how a single concept is *modelled* in the first place.

# %% [markdown]
# ## Pitch Scalars
#
# Pitch representations are organised across three **spaces** and two
# **levels**:
#
# | Space | Pitch (with octave) | Pitch Class (octave-free) |
# |-------|---------------------|---------------------------|
# | **Specific (fifths)** | `SpecificPitch` | `SpecificPitchClass` |
# | **Enharmonic (semitones)** | `EnharmonicPitch` (alias `MidiPitch`) | `EnharmonicPitchClass` |
# | **Generic (steps)** | `GenericPitch` | `GenericPitchClass` |
#
# `EnharmonicPitch` is canonical for the `ep` storage field on
# score-level data; `MidiPitch` is a thin display-alias reserved as the
# default scalar for the planned `MidiField` (so MidiField rows display
# as `MidiPitch(60)` rather than `EnharmonicPitch(C4)`).

# %% [markdown]
# ### EnharmonicPitchClass (EPC): chromatic pitch class only

# %%
epc_c = EnharmonicPitchClass(pitch_class=0)
epc_c

# %%
# Compares directly with integers (0-11, C=0)
{"EPC(C) == 0": epc_c == 0, "EPC(C) == 2": epc_c == 2}

# %%
EnharmonicPitchClass(pitch_class=2).to_dict()

# %% [markdown]
# ### GenericPitch (GP): diatonic step + octave
#
# Diatonic 0-6 (C=0, D=1, …, B=6) — distinct from EPC's chromatic 0-11.

# %%
gp_c4 = GenericPitch(step=0, octave=4)
gp_c4

# %%
GenericPitch(step=2, octave=4)

# %%
gp_c4.to_dict()

# %% [markdown]
# ### SpecificPitchClass (SPC): spelling without octave
#
# Distinguishes C♯ from D♭ but carries no octave.  `fifths` is derived
# from `step` and `alter`.

# %%
spc = SpecificPitchClass.from_label("C#")
spc

# %%
spc.to_dict()

# %% [markdown]
# ### MidiPitch (display alias of EnharmonicPitch)
#
# Same data as `EnharmonicPitch` (a 12-TET pitch with octave); differs
# only in how it renders.  `MidiPitch(60)` vs `EnharmonicPitch(C4)`.

# %%
mp = MidiPitch(midi_number=60)
mp

# %%
mp.to_dict()

# %% [markdown]
# ### SpecificPitch (SP): full spelling with octave
#
# The most informative level — preserves enharmonic identity, octave,
# and optional cents deviation.  `from_label()` parses a pitch string.

# %%
sp = SpecificPitch.from_label("C#4")
sp

# %%
sp.to_dict()

# %% [markdown]
# ### Protocol Satisfaction
#
# Each scalar satisfies its own protocol and all of its ancestors.

# %%
{
    "EnharmonicPitchClass → GenericPitchLike": isinstance(epc_c, GenericPitchLike),
    "GenericPitch → GenericPitchLike": isinstance(gp_c4, GenericPitchLike),
    "SpecificPitchClass → SpecificPitchClassLike": isinstance(
        spc, SpecificPitchClassLike
    ),
    "MidiPitch → EnharmonicPitchLike": isinstance(mp, EnharmonicPitchLike),
    "SpecificPitch → SpecificPitchLike": isinstance(sp, SpecificPitchLike),
    "SpecificPitch → EnharmonicPitchLike": isinstance(sp, EnharmonicPitchLike),
    "all are PitchLike": all(
        isinstance(p, PitchLike) for p in [epc_c, gp_c4, spc, mp, sp]
    ),
}

# %% [markdown]
# ### Conversion with `.to()`
#
# `SpecificPitch`, being the most informative, converts down to every
# coarser type.  Conversions that would require missing information
# (e.g. EPC → MidiPitch) raise `TypeError`.

# %%
{
    "SpecificPitch → MidiPitch": sp.to(MidiPitch),
    "SpecificPitch → SpecificPitchClass": sp.to(SpecificPitchClass),
    "SpecificPitch → EnharmonicPitchClass": sp.to(EnharmonicPitchClass),
}

# %% [markdown]
# ## Pitch Fields
#
# Each scalar level has a paired field counterpart that wraps a PyArrow
# struct array and returns scalars on element access.  Fields are
# constructed via `from_*()` factories — never by hand-building structs.

# %% [markdown]
# ### From raw values — `PitchField.from_raw(ep=...)`
#
# Returns `EnharmonicPitch` scalars from the EP storage struct.

# %%
epf = PitchField.from_raw(ep=[60, 64, 67])
epf

# %%
{"C4": epf[0], "E4": epf[1], "G4": epf[2]}

# %% [markdown]
# ### From labels — `PitchField.from_labels(...)`
#
# Parses pitch strings into the SP storage struct; returns
# `SpecificPitch` scalars.

# %%
spf = PitchField.from_labels(["C4", "E4", "G4"])
spf

# %%
{"C4": spf[0], "E4": spf[1], "G4": spf[2]}

# %% [markdown]
# ### From a loader — real Chopin data
#
# The Chopin Op. 10 No. 3 notes table carries both `midi_pitch` (EP) and
# `specific_pitch` (SP) fields.  The loader produces typed `PitchField`
# views over each one.

# %%
loader = TSVLoader.from_file(CHOPIN_NOTES)
chopin_ep = loader.store.notes.enharmonic_pitch_field
chopin_sp = loader.store.notes.specific_pitch_field

# %%
{
    "EP[3]": chopin_ep[3],
    "SP[3]": chopin_sp[3],
    "EP[8]": chopin_ep[8],
    "SP[8]": chopin_sp[8],
}

# %% [markdown]
# ## Harmony Scalars
#
# Five levels of harmonic specificity, each adding more information:
#
# | Scalar | Adds | Protocol |
# |--------|------|----------|
# | `HarmonyLabel` | label + standard | `HarmonyLabelLike` |
# | `PitchBasedHarmony` | root, bass | `PitchBasedHarmonyLike` |
# | `WesternTertianHarmony` | chord_type, inversion | `WesternTertianHarmonyLike` |
# | `RomanNumeralHarmony` | numeral, key context | `RomanNumeralHarmonyLike` |
# | `DcmlHarmony` | tonicized_key, pedal | `DcmlHarmonyLike` |

# %% [markdown]
# ### HarmonyLabel: the minimal case

# %%
HarmonyLabel(label="CM", standard="chord_symbol")

# %% [markdown]
# ### DcmlHarmony: instantiation from a label string
#
# `from_label()` parses a DCML label using the ms3 regex and derives all
# component properties automatically.  Other standards' parsers plug in
# the same way — only the implementation behind `from_label()` differs.

# %%
dh = DcmlHarmony.from_label("V65", globalkey="C")
dh

# %%
# to_dict() displays root and bass as pitch class integers
dh.to_dict()

# %%
{
    lbl: DcmlHarmony.from_label(lbl, globalkey="C")
    for lbl in ["I", "viio7", "iv6", "V65"]
}

# %% [markdown]
# ## Harmony Fields
#
# Each harmony scalar has a corresponding paired field type.  The
# TSVLoader pipeline does not yet produce typed harmony fields
# automatically, so the examples below build the storage arrays
# directly via the schema dataclasses.

# %% [markdown]
# ### WesternTertianHarmonyField

# %%
wt_arr = pa.array(
    [
        {
            "label": "CM",
            "standard": "chord_symbol",
            "root": 0,
            "bass": 0,
            "chord_quality": "M",
            "inversion": 0,
        },
        {
            "label": "Am",
            "standard": "chord_symbol",
            "root": 9,
            "bass": 9,
            "chord_quality": "m",
            "inversion": 0,
        },
    ],
    type=WesternTertianSchema.schema,
)
wtf = WesternTertianHarmonyField.from_field(wt_arr, name="harmony")
{"CM": wtf[0], "Am": wtf[1]}

# %% [markdown]
# ### DcmlLabelField
#
# Built on `DcmlStorageSchema`; element access returns `DcmlHarmony`
# scalars.

# %%
dcml_arr = pa.array(
    [
        {
            "label": "V65",
            "globalkey": "C",
            "localkey": "I",
            "numeral": "V",
            "form": "M",
            "figbass": "65",
            "chord_type": "Mm7",
            "root": 7,
            "bass_note": 11,
        },
        {
            "label": "I",
            "globalkey": "C",
            "localkey": "I",
            "numeral": "I",
            "form": "M",
            "figbass": "",
            "chord_type": "M",
            "root": 0,
            "bass_note": 0,
        },
    ],
    type=DcmlStorageSchema.schema,
)
dlf = DcmlLabelField.from_field(dcml_arr, name="harmony")
dlf[0]

# %%
dlf[0].to_dict()

# %% [markdown]
# ### The Shared Protocol — `DcmlHarmonyLike`
#
# Both `DcmlLabelField` element access and direct `DcmlHarmony` objects
# satisfy the same `DcmlHarmonyLike` protocol.  Any function that
# accepts `DcmlHarmonyLike` works identically whether the harmony was
# loaded from a field or built via `from_label()`.

# %%
from_label = DcmlHarmony.from_label("V65", globalkey="C")
from_field = dlf[0]

{
    "from_label → DcmlHarmonyLike": isinstance(from_label, DcmlHarmonyLike),
    "from_field → DcmlHarmonyLike": isinstance(from_field, DcmlHarmonyLike),
    "both → RomanNumeralHarmonyLike": all(
        isinstance(h, RomanNumeralHarmonyLike) for h in [from_label, from_field]
    ),
    "both → WesternTertianHarmonyLike": all(
        isinstance(h, WesternTertianHarmonyLike) for h in [from_label, from_field]
    ),
    "both → HarmonyLabelLike": all(
        isinstance(h, HarmonyLabelLike) for h in [from_label, from_field]
    ),
}

# %%
{"from_label()": from_label.to_dict(), "from_field[0]": from_field.to_dict()}

# %% [markdown]
# This protocol-based uniformity is the foundation for two further
# capabilities:
#
# - **FlexOHR export:** converting `DcmlHarmonyLike` objects to external
#   FlexOHR representations, since the protocol guarantees that `root`,
#   `bass`, `chord_type`, and `inversion` are always available.
# - **Cross-standard conversion:** any harmony standard that implements
#   the same protocol chain (e.g. `RomanNumeralHarmonyLike`) can be
#   converted to any other, because the shared protocol fields define a
#   common intermediate representation.

# %% [markdown]
# ## Protocol Dispatch
#
# `isinstance` checks against protocols let you write a single function
# that adapts to whatever level of detail is available.


# %%
def describe_pitch(p: PitchLike) -> dict:
    """Describe a pitch at whatever level of detail is available."""
    info: dict[str, object] = {"type": p.semantic_type}
    if isinstance(p, GenericPitchLike):
        info["pitch_class"] = p.pitch_class
    if isinstance(p, SpecificPitchClassLike):
        info["step"] = p.step
        info["alter"] = p.alter
    if isinstance(p, EnharmonicPitchLike):
        info["midi"] = p.midi_number
        info["octave"] = p.octave
    if isinstance(p, SpecificPitchLike):
        info["cents"] = p.cents
    return info


# %%
# The same function works for every scalar level
{type(p).__name__: describe_pitch(p) for p in [epc_c, gp_c4, spc, mp, sp]}

# %%
# It also works for scalars extracted from fields — including loader output
{type(f[3]).__name__: describe_pitch(f[3]) for f in [chopin_ep, chopin_sp]}

# %% [markdown]
# ## Parquet Round-Trip
#
# Pitch and harmony fields store their metadata in the PyArrow field's
# `metadata` dict under `b"timetoalign"`.  This survives Parquet
# serialisation; the reconstructed field carries the same scalar type.

# %%
pa_field = spf.to_field()
table = pa.table({pa_field.name: spf.to_pyarrow()}, schema=pa.schema([pa_field]))

with tempfile.NamedTemporaryFile(suffix=".parquet") as f:
    pq.write_table(table, f.name)
    loaded = pq.read_table(f.name)

# %%
json.loads(loaded.schema.field(pa_field.name).metadata[b"timetoalign"])

# %%
loaded_arr = loaded.column(pa_field.name).combine_chunks()
PitchField.from_field(loaded_arr, name=pa_field.name)[0]

# %% [markdown]
# > **Key takeaway.**  Time To Align! models pitch across three spaces
# > (Specific, Enharmonic/MIDI, Generic) at two levels (pitch and
# > pitch class).  Each is expressed as a Protocol (structural
# > contract), a Scalar (frozen value), and a Field (paired wrapper).
# > Harmony follows the same three-level pattern, with five degrees of
# > specificity culminating in `DcmlHarmony`.  Shared protocols make
# > `from_label()` and `Field[i]` interchangeable consumers downstream.
# > For the orthogonal data-access axis — how a loaded `EventData`
# > exposes its contents at Layer 0 / 1 / 2 — see
# > `how01_datafields_and_eventdata`.
