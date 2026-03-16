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
# # How-To 02: Pitch & Harmony Type Hierarchy
#
# Protocols, scalars, and semantic fields -- the three-layer architecture
# for pitch and harmony data in Time To Align!

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
    SpecificPitchLike,
    SpelledPitchClassLike,
    WesternTertianHarmonyLike,
)
from timetoalign.core.scalars.harmony import (
    DcmlHarmony,
    HarmonyLabel,
)
from timetoalign.core.scalars.pitch import (
    GenericPitch,
    MidiPitch,
    SpelledPitch,
    SpelledPitchClass,
)
from timetoalign.fields.harmony import (
    DcmlLabelField,
    WesternTertianHarmonyField,
)
from timetoalign.fields.pitch import (
    EnharmonicPitchField,
    SpecificPitchField,
)
from timetoalign.fields.schemas import (
    DcmlStorageSchema,
    WesternTertianSchema,
)

# %% [markdown]
# ## The Three-Layer Architecture
#
# Every pitch or harmony concept is expressed at three layers:
#
# | Layer | Role | Example |
# |-------|------|---------|
# | **Protocol** | Structural contract (`isinstance`-checkable) | `GenericPitchLike` |
# | **Scalar** | Frozen dataclass for single values | `GenericPitch(pitch_class=0)` |
# | **Field** | Columnar wrapper over a PyArrow struct array | `GenericPitchField` |
#
# Scalars satisfy their corresponding protocol.  Fields wrap PyArrow arrays
# and return scalars on element access.  Protocols enable generic dispatch
# across the whole hierarchy.

# %% [markdown]
# ## Pitch Scalars
#
# Three main categories of pitch representation, from least to most
# information:
#
# | Category | Scalar | Key property | Protocol |
# |----------|--------|-------------|----------|
# | **Generic (GP)** | `GenericPitch` | `pitch_class` (0--11) | `GenericPitchLike` |
# | **Enharmonic (EP)** | `EnharmonicPitch` (alias: `MidiPitch`) | `midi_number` + octave | `EnharmonicPitchLike` |
# | **Specific (SP)** | `SpecificPitch` (alias: `SpelledPitch`) | spelling + octave + cents | `SpecificPitchLike` |
#
# Additionally, `SpelledPitchClass` is an octave-free variant of the
# Specific category -- it carries spelling but no octave information.
#
# The ms3/DCML naming convention calls the MIDI level "enharmonic"
# (because it *equates* enharmonic equivalents) and the spelled level
# "specific" (because it preserves the *specific* spelling).  The aliases
# `EnharmonicPitch = MidiPitch` and `SpecificPitch = SpelledPitch`
# reflect this convention.

# %% [markdown]
# ### Generic Pitch (GP): pitch class only

# %%
gp_c = GenericPitch(pitch_class=0)
gp_c

# %%
# GenericPitch compares directly with integers (pitch class 0-11, C=0)
{"GPC(C) == 0": gp_c == 0, "GPC(C) == 2": gp_c == 2}

# %%
gp_d = GenericPitch(pitch_class=2)
gp_d

# %%
gp_c.to_dict()

# %% [markdown]
# ### Spelled Pitch Class (SPC): spelling without octave
#
# `SpelledPitchClass` sits between Generic and Specific -- it
# distinguishes C♯ from D♭ but carries no octave information.
# `fifths` is automatically derived from `step` and `alter`.

# %%
spc = SpelledPitchClass.from_label("C#")
spc

# %%
# All fields are automatically derived from the label
spc.to_dict()

# %% [markdown]
# ### Enharmonic Pitch (EP / MIDI): octave without spelling
#
# `MidiPitch` knows the MIDI note number; `pitch_class` and `octave`
# are automatically derived.  It cannot distinguish C♯ from D♭.

# %%
mp = MidiPitch(midi_number=60)
mp

# %%
mp.to_dict()

# %% [markdown]
# ### Specific Pitch (SP / Spelled): full spelling with octave
#
# `SpelledPitch` is the most informative level -- it preserves the
# enharmonic identity, octave, and optional cents deviation.
# Use `from_label()` to construct from a pitch string.

# %%
sp = SpelledPitch.from_label("C#4")
sp

# %%
# All fields are automatically inferred from the label
sp.to_dict()

# %% [markdown]
# ### Protocol Satisfaction
#
# Each scalar satisfies its own protocol and all parent protocols.
# The two branches of the hierarchy are **Generic** (pitch class) and
# **Specific** (MIDI + octave), joined at the top by `PitchLike`.

# %%
{
    "GenericPitch -> GenericPitchLike": isinstance(gp_c, GenericPitchLike),
    "SpelledPitchClass -> SpelledPitchClassLike": isinstance(
        spc, SpelledPitchClassLike
    ),
    "MidiPitch -> EnharmonicPitchLike": isinstance(mp, EnharmonicPitchLike),
    "SpelledPitch -> SpecificPitchLike": isinstance(sp, SpecificPitchLike),
    "SpelledPitch -> EnharmonicPitchLike": isinstance(sp, EnharmonicPitchLike),
    "all are PitchLike": all(isinstance(p, PitchLike) for p in [gp_c, spc, mp, sp]),
}

# %% [markdown]
# ### Pitch Conversion with `.to()`
#
# `SpelledPitch`, being the most informative, can convert down to
# any less-specific type.  Conversions that would require missing
# information (e.g., `GenericPitch` to `MidiPitch`) raise `TypeError`.

# %%
{
    "SpelledPitch -> MidiPitch": sp.to(MidiPitch),
    "SpelledPitch -> GenericPitch": sp.to(GenericPitch),
    "SpelledPitch -> SpelledPitchClass": sp.to(SpelledPitchClass),
}

# %% [markdown]
# ## Pitch Fields
#
# Each pitch scalar has a corresponding columnar field type that wraps a
# PyArrow struct array and returns scalars on element access.
# Fields are constructed from minimal information via convenience
# classmethods.

# %% [markdown]
# ### EnharmonicPitchField (MIDI)
#
# Wraps the EP schema and returns `MidiPitch` scalars.

# %%
epf = EnharmonicPitchField.from_midi_numbers([60, 64, 67])
epf

# %%
{"C4": epf[0], "E4": epf[1], "G4": epf[2]}

# %%
epf[0].to_dict()

# %% [markdown]
# ### SpecificPitchField (Spelled)
#
# Wraps the SP schema and returns `SpelledPitch` scalars with full
# enharmonic identity.

# %%
spf = SpecificPitchField.from_labels(["C4", "E4", "G4"])
spf

# %%
{"C4": spf[0], "E4": spf[1], "G4": spf[2]}

# %%
spf[0].to_dict()

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
hl = HarmonyLabel(label="CM", standard="chord_symbol")
hl

# %% [markdown]
# ### DcmlHarmony: instantiation from a label string
#
# The `from_label()` classmethod parses a DCML label string using the
# ms3 regex and derives all component properties automatically.  This
# is the same interface that any standard's numeral would use -- only
# the parser behind `from_label()` differs.

# %%
dh = DcmlHarmony.from_label("V65", globalkey="C")
dh

# %%
# to_dict() displays root and bass as GenericPitch objects
dh.to_dict()

# %%
# The same interface works for any DCML label
{
    lbl: DcmlHarmony.from_label(lbl, globalkey="C")
    for lbl in ["I", "viio7", "iv6", "V65"]
}

# %% [markdown]
# ## Harmony Fields
#
# Each harmony scalar has a corresponding field type.

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
wtf

# %%
{"CM": wtf[0], "Am": wtf[1]}

# %% [markdown]
# ### DcmlLabelField
#
# Built from the `DcmlStorageSchema`, element access returns `DcmlHarmony`
# scalars via `from_row()`.

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
dlf

# %%
h0 = dlf[0]
h0

# %%
h0.to_dict()

# %% [markdown]
# ## DcmlLabelField and DcmlHarmony: the Shared Protocol
#
# Both `DcmlLabelField` element access (returning `DcmlHarmony` scalars)
# and directly constructed `DcmlHarmony` objects satisfy the same
# `DcmlHarmonyLike` protocol.  This means any function that accepts
# `DcmlHarmonyLike` works identically whether the harmony was loaded
# from a field column or created via `from_label()`.

# %%
# DcmlHarmony from from_label()
from_label = DcmlHarmony.from_label("V65", globalkey="C")
# DcmlHarmony from DcmlLabelField element access
from_field = dlf[0]

{
    "from_label satisfies DcmlHarmonyLike": isinstance(from_label, DcmlHarmonyLike),
    "from_field satisfies DcmlHarmonyLike": isinstance(from_field, DcmlHarmonyLike),
    "both satisfy RomanNumeralHarmonyLike": all(
        isinstance(h, RomanNumeralHarmonyLike) for h in [from_label, from_field]
    ),
    "both satisfy WesternTertianHarmonyLike": all(
        isinstance(h, WesternTertianHarmonyLike) for h in [from_label, from_field]
    ),
    "both satisfy HarmonyLabelLike": all(
        isinstance(h, HarmonyLabelLike) for h in [from_label, from_field]
    ),
}

# %%
# The same to_dict() output regardless of origin
{"from_label()": from_label.to_dict(), "from_field[0]": from_field.to_dict()}

# %% [markdown]
# This protocol-based uniformity is the foundation for two further
# capabilities:
#
# - **FlexOHR export:** converting `DcmlHarmonyLike` objects to
#   external FlexOHR representations, since the protocol guarantees
#   that `root`, `bass`, `chord_type`, and `inversion` are always
#   available.
# - **Cross-standard conversion:** any harmony standard that implements
#   the same protocol chain (e.g., `RomanNumeralHarmonyLike`) can be
#   converted to any other, because the shared protocol fields define
#   a common intermediate representation.

# %% [markdown]
# ## Protocol Dispatch
#
# The `isinstance` checks on protocols enable writing generic functions
# that work across the whole hierarchy.  This is also how the individual
# paradigm's codecs look: they "plug" the right information from the
# OHR (One Harmony Representation), transforming and assembling it as
# needed.


# %%
def describe_pitch(p: PitchLike) -> dict:
    """Describe a pitch at whatever level of detail is available."""
    info: dict[str, object] = {"type": p.semantic_type}
    if isinstance(p, GenericPitchLike):
        info["pitch_class"] = p.pitch_class
    if isinstance(p, SpelledPitchClassLike):
        info["step"] = p.step
        info["alter"] = p.alter
    if isinstance(p, EnharmonicPitchLike):
        info["midi"] = p.midi_number
        info["octave"] = p.octave
    if isinstance(p, SpecificPitchLike):
        info["cents"] = p.cents
    return info


# %%
# The same function works for every pitch type
{type(p).__name__: describe_pitch(p) for p in [gp_c, spc, mp, sp]}

# %%
# It also works for scalars extracted from fields
{type(f).__name__: describe_pitch(f[0]) for f in [epf, spf]}

# %% [markdown]
# ## Parquet Round-Trip
#
# Pitch and harmony fields store metadata in the PyArrow field's metadata
# dict under the `b"timetoalign"` key.  This survives Parquet serialisation.

# %%
# Build a table with a pitch field column
pa_field = spf.to_field()
table = pa.table({pa_field.name: spf.to_pyarrow()}, schema=pa.schema([pa_field]))

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
# Reconstruct the field from the loaded table
loaded_arr = loaded.column(col_name).combine_chunks()
loaded_spf = SpecificPitchField.from_field(loaded_arr, name=col_name)
loaded_spf[0]

# %%
# Same for harmony fields
ha_field = dlf.to_field()
ha_table = pa.table({ha_field.name: dlf.to_pyarrow()}, schema=pa.schema([ha_field]))

with tempfile.NamedTemporaryFile(suffix=".parquet") as f:
    pq.write_table(ha_table, f.name)
    ha_loaded = pq.read_table(f.name)

ha_meta = json.loads(ha_loaded.schema.field(ha_field.name).metadata[b"timetoalign"])
ha_meta

# %%
# Reconstruct
ha_arr = ha_loaded.column(ha_field.name).combine_chunks()
loaded_dlf = DcmlLabelField.from_field(ha_arr, name=ha_field.name)
loaded_dlf[0]

# %% [markdown]
# > **Key takeaway.** Time To Align! organises pitch data into three
# > categories -- Generic (GP), Enharmonic/MIDI (EP), and
# > Specific/Spelled (SP) -- each expressible as a frozen scalar, a
# > runtime-checkable protocol, and a columnar PyArrow field.  Harmony
# > data follows the same three-layer pattern with five levels of
# > specificity.  The `DcmlHarmony.from_label()` factory and the
# > `DcmlLabelField` element accessor share the `DcmlHarmonyLike`
# > protocol, laying the foundation for FlexOHR export and cross-standard
# > harmony conversion.
