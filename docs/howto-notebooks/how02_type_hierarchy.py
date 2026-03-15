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
    SpecificPitchClassLike,
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
    HarmonyField,
    WesternTertianHarmonyField,
)
from timetoalign.fields.pitch import (
    EnharmonicPitchField,
    GenericPitchField,
    PitchField,
    SpecificPitchField,
    SpelledPitchClassField,
)
from timetoalign.fields.schemas import (
    DcmlStorageSchema,
    EnharmonicPitchSchema,
    GenericPitchSchema,
    SpecificPitchSchema,
    SpelledPitchClassSchema,
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
# | **Enharmonic (EP)** | `MidiPitch` | `midi_number` + octave | `SpecificPitchClassLike` |
# | **Specific (SP)** | `SpelledPitch` | spelling + octave + cents | `EnharmonicPitchLike` |
#
# Additionally, `SpelledPitchClass` is an octave-free variant of the
# Specific category -- it carries spelling but no octave information.
#
# The ms3/DCML naming convention calls the MIDI level "enharmonic"
# (because it *equates* enharmonic equivalents) and the spelled level
# "specific" (because it preserves the *specific* spelling).  The class
# aliases `SpecificPitch = MidiPitch` and `EnharmonicPitch = SpelledPitch`
# reflect this convention.

# %% [markdown]
# ### Generic Pitch (GP): pitch class only

# %%
gp_c = GenericPitch(pitch_class=0)
gp_c

# %%
# GenericPitch compares directly with integers
{"GPC(C) == 0": gp_c == 0, "GPC(C) == 7": gp_c == 7}

# %%
gp_g = GenericPitch(pitch_class=7)
gp_g

# %% [markdown]
# ### Spelled Pitch Class (SPC): spelling without octave
#
# `SpelledPitchClass` sits between Generic and Specific -- it
# distinguishes C♯ from D♭ but carries no octave information.

# %%
spc = SpelledPitchClass(step="C", alter=1, fifths=7)
spc

# %%
{"pitch_class": spc.pitch_class, "step": spc.step, "alter": spc.alter}

# %% [markdown]
# ### Enharmonic Pitch (EP / MIDI): octave without spelling
#
# `MidiPitch` knows the MIDI note number and pitch class but cannot
# distinguish C♯ from D♭.

# %%
mp = MidiPitch(midi_number=60, pitch_class=0)
mp

# %%
{"midi_number": mp.midi_number, "octave": mp.octave, "pitch_class": mp.pitch_class}

# %% [markdown]
# ### Specific Pitch (SP / Spelled): full spelling with octave
#
# `SpelledPitch` is the most informative level -- it preserves the
# enharmonic identity, octave, and optional cents deviation.

# %%
sp = SpelledPitch(step="C", alter=1, octave=4, fifths=7, cents=0.0)
sp

# %%
{
    "midi_number": sp.midi_number,
    "pitch_class": sp.pitch_class,
    "octave": sp.octave,
    "step": sp.step,
    "alter": sp.alter,
}

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
    "MidiPitch -> SpecificPitchClassLike": isinstance(mp, SpecificPitchClassLike),
    "MidiPitch -> SpelledPitchClassLike": isinstance(mp, SpelledPitchClassLike),
    "SpelledPitch -> EnharmonicPitchLike": isinstance(sp, EnharmonicPitchLike),
    "SpelledPitch -> SpecificPitchClassLike": isinstance(sp, SpecificPitchClassLike),
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

# %% [markdown]
# ### GenericPitchField

# %%
gp_arr = pa.array(
    [{"pitch_class": 0}, {"pitch_class": 4}, {"pitch_class": 7}],
    type=GenericPitchSchema.schema,
)
gpf = GenericPitchField.from_field(gp_arr, name="generic_pitch")
gpf

# %%
{"C": gpf[0], "E": gpf[1], "G": gpf[2]}

# %% [markdown]
# ### SpelledPitchClassField

# %%
spc_arr = pa.array(
    [
        {"gpc_str": "C", "acc": 0, "spc_int": 0},
        {"gpc_str": "E", "acc": 0, "spc_int": 4},
        {"gpc_str": "B", "acc": -1, "spc_int": -2},
    ],
    type=SpelledPitchClassSchema.schema,
)
spcf = SpelledPitchClassField.from_field(spc_arr, name="spelled_pitch_class")
spcf

# %%
{"C": spcf[0], "E": spcf[1], "Bb": spcf[2]}

# %% [markdown]
# ### EnharmonicPitchField (MIDI)
#
# Wraps the EP schema (`{ep, epc}`) and returns `MidiPitch` scalars.

# %%
midi_arr = pa.array(
    [{"ep": 60, "epc": 0}, {"ep": 64, "epc": 4}, {"ep": 67, "epc": 7}],
    type=EnharmonicPitchSchema.schema,
)
epf = EnharmonicPitchField.from_field(midi_arr, name="midi_pitch")
epf

# %%
{
    "C4": epf[0],
    "E4": epf[1],
    "G4": epf[2],
    "C4 midi": epf[0].midi_number,
    "C4 octave": epf[0].octave,
}

# %% [markdown]
# ### SpecificPitchField (Spelled)
#
# Wraps the SP schema and returns `SpelledPitch` scalars with full
# enharmonic identity.  The storage struct carries seven fields, but
# several are derivable -- we specify all of them here because the
# PyArrow struct requires the full schema.

# %%
sp_arr = pa.array(
    [
        {
            "gpc_int": 0,
            "gpc_str": "C",
            "acc": 0,
            "spc_int": 0,
            "spc_str": "C",
            "sp": "C4",
            "cents": 0.0,
        },
        {
            "gpc_int": 2,
            "gpc_str": "E",
            "acc": 0,
            "spc_int": 4,
            "spc_str": "E",
            "sp": "E4",
            "cents": 0.0,
        },
        {
            "gpc_int": 4,
            "gpc_str": "G",
            "acc": 0,
            "spc_int": 7,
            "spc_str": "G",
            "sp": "G4",
            "cents": 0.0,
        },
    ],
    type=SpecificPitchSchema.schema,
)
spf = SpecificPitchField.from_field(sp_arr, name="spelled_pitch")
spf

# %%
{
    "C4": spf[0],
    "E4": spf[1],
    "G4": spf[2],
    "C4 midi": spf[0].midi_number,
    "C4 step": spf[0].step,
}

# %% [markdown]
# ### All Pitch Fields are PitchFields
#
# The abstract `PitchField` parent enables polymorphic handling.

# %%
{type(f).__name__: isinstance(f, PitchField) for f in [gpf, spcf, epf, spf]}

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
dh = DcmlHarmony.from_label("V65/IV", globalkey="C")
dh

# %%
{
    "label": dh.label,
    "numeral": dh.numeral,
    "chord_type": dh.chord_type,
    "inversion": dh.inversion,
    "root": dh.root,
    "bass": dh.bass,
    "tonicized_key": dh.tonicized_key,
    "globalkey": dh.globalkey,
}

# %%
# The same interface works for any DCML label
{
    lbl: DcmlHarmony.from_label(lbl, globalkey="C")
    for lbl in ["I", "viio7", "iv6", "V65/IV"]
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
{
    "label": h0.label,
    "numeral": h0.numeral,
    "chord_type": h0.chord_type,
    "inversion": h0.inversion,
    "root": h0.root,
    "bass": h0.bass,
}

# %% [markdown]
# ### All Harmony Fields are HarmonyFields

# %%
{type(f).__name__: isinstance(f, HarmonyField) for f in [wtf, dlf]}

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
# The same fields are accessible regardless of origin
{
    "Property": ["label", "numeral", "chord_type", "inversion", "root", "bass"],
    "from_label()": [
        from_label.label,
        from_label.numeral,
        from_label.chord_type,
        from_label.inversion,
        from_label.root,
        from_label.bass,
    ],
    "from_field[0]": [
        from_field.label,
        from_field.numeral,
        from_field.chord_type,
        from_field.inversion,
        from_field.root,
        from_field.bass,
    ],
}

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
# that work across the whole hierarchy.


# %%
def describe_pitch(p: PitchLike) -> dict:
    """Describe a pitch at whatever level of detail is available."""
    info: dict[str, object] = {"type": p.semantic_type}
    if isinstance(p, GenericPitchLike):
        info["pitch_class"] = p.pitch_class
    if isinstance(p, SpelledPitchClassLike):
        info["step"] = p.step
        info["alter"] = p.alter
    if isinstance(p, SpecificPitchClassLike):
        info["midi"] = p.midi_number
        info["octave"] = p.octave
    if isinstance(p, EnharmonicPitchLike):
        info["cents"] = p.cents
    return info


# %%
# The same function works for every pitch type
{type(p).__name__: describe_pitch(p) for p in [gp_c, spc, mp, sp]}

# %%
# It also works for scalars extracted from fields
{type(f).__name__: describe_pitch(f[0]) for f in [gpf, spcf, epf, spf]}

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
