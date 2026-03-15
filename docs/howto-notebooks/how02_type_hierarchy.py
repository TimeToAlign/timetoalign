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
# Four levels of pitch specificity, from least to most information:
#
# | Scalar | Information | Protocol |
# |--------|-------------|----------|
# | `GenericPitch` | pitch class only | `GenericPitchLike` |
# | `SpelledPitchClass` | + spelling (step, alter) | `SpelledPitchClassLike` |
# | `MidiPitch` | + octave (MIDI number) | `SpecificPitchClassLike` |
# | `SpelledPitch` | + spelling + octave + cents | `EnharmonicPitchLike` |

# %%
from __future__ import annotations

from timetoalign.core.scalars.pitch import (
    GenericPitch,
    MidiPitch,
    SpelledPitch,
    SpelledPitchClass,
)

# %%
# GenericPitch: pitch class only
gp = GenericPitch(pitch_class=0)
print(gp)
print(f"  pitch_class={gp.pitch_class}, get()={gp.get()!r}")
assert gp.pitch_class == 0

# %%
# SpelledPitchClass: pitch class with enharmonic identity
spc = SpelledPitchClass(step="C", alter=1, fifths=7)
print(spc)
print(f"  step={spc.step!r}, alter={spc.alter}, pitch_class={spc.pitch_class}")
print(f"  get()={spc.get()!r}")
assert spc.pitch_class == 1  # C# = pitch class 1
assert spc.step == "C"

# %%
# MidiPitch: MIDI note number with pitch class
mp = MidiPitch(midi_number=60, pitch_class=0)
print(mp)
print(
    f"  midi_number={mp.midi_number}, pitch_class={mp.pitch_class}, octave={mp.octave}"
)
assert mp.octave == 4  # C4

# %%
# SpelledPitch: full spelling with octave and cents
sp = SpelledPitch(step="C", alter=1, octave=4, fifths=7, cents=0.0)
print(sp)
print(f"  midi_number={sp.midi_number}, pitch_class={sp.pitch_class}")
print(f"  get()={sp.get()!r}, get(format='midi')={sp.get(format='midi')!r}")
assert sp.midi_number == 61  # C#4 = MIDI 61
assert sp.pitch_class == 1

# %% [markdown]
# ### Protocol Satisfaction
#
# Each scalar satisfies its own protocol and all parent protocols.

# %%
from timetoalign.core.protocols import (
    EnharmonicPitchLike,
    GenericPitchLike,
    PitchLike,
    SemanticTypeLike,
    SpecificPitchClassLike,
    SpelledPitchClassLike,
)

# %%
# GenericPitch satisfies PitchLike and GenericPitchLike
assert isinstance(gp, SemanticTypeLike)
assert isinstance(gp, PitchLike)
assert isinstance(gp, GenericPitchLike)
print(f"GenericPitch -> PitchLike: {isinstance(gp, PitchLike)}")
print(f"GenericPitch -> GenericPitchLike: {isinstance(gp, GenericPitchLike)}")

# %%
# SpelledPitch satisfies the full chain up to EnharmonicPitchLike
assert isinstance(sp, PitchLike)
assert isinstance(sp, SpecificPitchClassLike)
assert isinstance(sp, EnharmonicPitchLike)
print(f"SpelledPitch -> EnharmonicPitchLike: {isinstance(sp, EnharmonicPitchLike)}")
print(
    f"SpelledPitch -> SpecificPitchClassLike: {isinstance(sp, SpecificPitchClassLike)}"
)

# %%
# MidiPitch satisfies SpecificPitchClassLike but NOT SpelledPitchClassLike
assert isinstance(mp, SpecificPitchClassLike)
assert not isinstance(mp, SpelledPitchClassLike)
print(f"MidiPitch -> SpecificPitchClassLike: {isinstance(mp, SpecificPitchClassLike)}")
print(f"MidiPitch -> SpelledPitchClassLike: {isinstance(mp, SpelledPitchClassLike)}")

# %% [markdown]
# ### Pitch Conversion with `.to()`
#
# The `TwelveTETPitchMixin` provides a unified `.to()` method for
# converting between pitch types.  Conversions that lose information
# (e.g., SpelledPitch to MidiPitch) are allowed; conversions that require
# missing information (e.g., GenericPitch to MidiPitch) raise `TypeError`.

# %%
# SpelledPitch can convert down to any less-specific type
sp_to_midi = sp.to(MidiPitch)
sp_to_generic = sp.to(GenericPitch)
sp_to_spc = sp.to(SpelledPitchClass)
print(f"SpelledPitch -> MidiPitch: {sp_to_midi}")
print(f"SpelledPitch -> GenericPitch: {sp_to_generic}")
print(f"SpelledPitch -> SpelledPitchClass: {sp_to_spc}")
assert sp_to_midi.midi_number == 61
assert sp_to_generic.pitch_class == 1

# %% [markdown]
# ## Pitch Fields
#
# Each pitch scalar has a corresponding columnar field type that wraps a
# PyArrow struct array and returns scalars on element access.

# %%
import pyarrow as pa

from timetoalign.fields.pitch import (
    EnharmonicPitchField,
    GenericPitchField,
    SpecificPitchField,
    SpelledPitchClassField,
)

# %% [markdown]
# ### GenericPitchField

# %%
gp_arr = pa.array(
    [{"pitch_class": 0}, {"pitch_class": 4}, {"pitch_class": 7}],
    type=pa.struct([pa.field("pitch_class", pa.int64())]),
)
gpf = GenericPitchField.from_field(gp_arr, name="generic_pitch")
print(gpf)
print(f"  [0]={gpf[0]}, [1]={gpf[1]}, [2]={gpf[2]}")
assert gpf[0].pitch_class == 0  # C
assert gpf[1].pitch_class == 4  # E
assert gpf[2].pitch_class == 7  # G

# %% [markdown]
# ### SpelledPitchClassField

# %%
spc_arr = pa.array(
    [
        {"gpc_str": "C", "acc": 0, "spc_int": 0},
        {"gpc_str": "E", "acc": 0, "spc_int": 4},
        {"gpc_str": "B", "acc": -1, "spc_int": -2},
    ],
    type=pa.struct(
        [
            pa.field("gpc_str", pa.string()),
            pa.field("acc", pa.int64()),
            pa.field("spc_int", pa.int64()),
        ]
    ),
)
spcf = SpelledPitchClassField.from_field(spc_arr, name="spelled_pitch_class")
print(spcf)
print(f"  [0]={spcf[0]}, [1]={spcf[1]}, [2]={spcf[2]}")
assert spcf[0].step == "C"
assert spcf[2].step == "B"
assert spcf[2].alter == -1  # Bb

# %% [markdown]
# ### SpecificPitchField (MidiPitchField)

# %%
midi_arr = pa.array(
    [{"ep": 60, "epc": 0}, {"ep": 64, "epc": 4}, {"ep": 67, "epc": 7}],
    type=pa.struct([pa.field("ep", pa.int64()), pa.field("epc", pa.int64())]),
)
mpf = SpecificPitchField.from_field(midi_arr, name="midi_pitch")
print(mpf)
print(f"  [0]={mpf[0]}, [1]={mpf[1]}, [2]={mpf[2]}")
assert mpf[0].midi_number == 60
assert mpf[1].midi_number == 64

# %% [markdown]
# ### EnharmonicPitchField (SpelledPitchField)

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
    type=pa.struct(
        [
            pa.field("gpc_int", pa.int64()),
            pa.field("gpc_str", pa.string()),
            pa.field("acc", pa.int64()),
            pa.field("spc_int", pa.int64()),
            pa.field("spc_str", pa.string()),
            pa.field("sp", pa.string()),
            pa.field("cents", pa.float64()),
        ]
    ),
)
spf = EnharmonicPitchField.from_field(sp_arr, name="spelled_pitch")
print(spf)
print(f"  [0]={spf[0]}, [1]={spf[1]}, [2]={spf[2]}")
assert spf[0].midi_number == 60  # C4
assert spf[1].step == "E"

# %% [markdown]
# ### All Pitch Fields are PitchFields
#
# The abstract `PitchField` parent enables polymorphic handling.

# %%
from timetoalign.fields.pitch import PitchField

for field in [gpf, spcf, mpf, spf]:
    assert isinstance(field, PitchField), f"{type(field).__name__} is not a PitchField"
    print(f"isinstance({type(field).__name__}, PitchField) = True")

# %% [markdown]
# ## Harmony Scalars
#
# Five levels of harmonic specificity:
#
# | Scalar | Adds | Protocol |
# |--------|------|----------|
# | `HarmonyLabel` | label + standard | `HarmonyLabelLike` |
# | `PitchBasedHarmony` | root, bass | `PitchBasedHarmonyLike` |
# | `WesternTertianHarmony` | chord_type, inversion | `WesternTertianHarmonyLike` |
# | `RomanNumeralHarmony` | numeral, key context | `RomanNumeralHarmonyLike` |
# | `DcmlHarmony` | tonicized_key, pedal | `DcmlHarmonyLike` |

# %%
from timetoalign.core.scalars.harmony import (  # noqa: F401
    DcmlHarmony,
    HarmonyLabel,
    RomanNumeralHarmony,
    WesternTertianHarmony,
)

# %%
# HarmonyLabel: the minimal case
hl = HarmonyLabel(label="CM", standard="chord_symbol")
print(hl)
assert hl.semantic_type == "HarmonyLabel"

# %%
# DcmlHarmony: the most specific
dh = DcmlHarmony(
    label="V65/IV",
    globalkey="C",
    localkey="I",
    numeral="V",
    chord_type="Mm7",
    inversion=1,
    root=7,
    bass=11,
)
print(dh)
print(f"  label={dh.label!r}, globalkey={dh.globalkey!r}, localkey={dh.localkey!r}")
print(
    f"  numeral={dh.numeral!r}, chord_type={dh.chord_type!r}, inversion={dh.inversion}"
)
assert dh.semantic_type == "DcmlHarmony"
assert dh.root == 7
assert dh.bass == 11

# %% [markdown]
# ## Harmony Fields
#
# Each harmony scalar has a corresponding field type.

# %%
from timetoalign.fields.harmony import (
    DCML_LABEL_STRUCT_TYPE,
    WESTERN_TERTIAN_STRUCT_TYPE,
    DcmlLabelField,
    HarmonyField,
    WesternTertianHarmonyField,
)

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
    type=WESTERN_TERTIAN_STRUCT_TYPE,
)
wtf = WesternTertianHarmonyField.from_field(wt_arr, name="harmony")
print(wtf)
print(f"  [0]={wtf[0]}")
print(f"  [1]={wtf[1]}")
assert wtf[0].label == "CM"
assert wtf[1].root == 9

# %% [markdown]
# ### DcmlLabelField

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
    type=DCML_LABEL_STRUCT_TYPE,
)
dlf = DcmlLabelField.from_field(dcml_arr, name="harmony")
print(dlf)

h0 = dlf[0]
print(f"  [0]={h0}")
print(
    f"    numeral={h0.numeral!r}, chord_type={h0.chord_type!r}, inversion={h0.inversion}"
)
assert h0.label == "V65"
assert h0.inversion == 1  # figbass "65" -> first inversion
assert h0.root == 7

h1 = dlf[1]
print(f"  [1]={h1}")
assert h1.label == "I"
assert h1.inversion == 0  # root position

# %% [markdown]
# ### All Harmony Fields are HarmonyFields

# %%
for field in [wtf, dlf]:
    assert isinstance(
        field, HarmonyField
    ), f"{type(field).__name__} is not a HarmonyField"
    print(f"isinstance({type(field).__name__}, HarmonyField) = True")

# %% [markdown]
# ## Protocol Dispatch
#
# The `isinstance` checks on protocols enable writing generic functions
# that work across the whole hierarchy.


# %%
def describe_pitch(p: PitchLike) -> str:
    """Describe a pitch at whatever level of detail is available."""
    parts = [f"semantic_type={p.semantic_type}"]

    if isinstance(p, GenericPitchLike):
        parts.append(f"pc={p.pitch_class}")

    if isinstance(p, SpelledPitchClassLike):
        parts.append(f"step={p.step}, alter={p.alter}")

    if isinstance(p, SpecificPitchClassLike):
        parts.append(f"midi={p.midi_number}, oct={p.octave}")

    if isinstance(p, EnharmonicPitchLike):
        parts.append(f"cents={p.cents}")

    return " | ".join(parts)


# %%
# The same function works for every pitch type
for pitch in [gp, spc, mp, sp]:
    print(describe_pitch(pitch))

# %%
# It also works for scalars extracted from fields
for field in [gpf, spcf, mpf, spf]:
    scalar = field[0]
    print(f"  from {type(field).__name__}: {describe_pitch(scalar)}")

# %% [markdown]
# ## Parquet Round-Trip
#
# Pitch and harmony fields store metadata in the PyArrow field's metadata
# dict under the `b"timetoalign"` key.  This survives Parquet serialisation.

# %%
import json
import tempfile

import pyarrow.parquet as pq

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
print(f"Recovered metadata: {meta}")
assert meta["field_type"] == "EnharmonicPitchField"
assert meta["pitch_type"] == "spelled"

# %%
# Reconstruct the field from the loaded table
loaded_arr = loaded.column(col_name).combine_chunks()
loaded_spf = EnharmonicPitchField.from_field(loaded_arr, name=col_name)
print(f"Reconstructed: {loaded_spf}")
print(f"  [0]={loaded_spf[0]}")
assert loaded_spf[0].midi_number == 60  # C4 survives round-trip
assert loaded_spf[0].step == "C"

# %%
# Same for harmony fields
ha_field = dlf.to_field()
ha_table = pa.table({ha_field.name: dlf.to_pyarrow()}, schema=pa.schema([ha_field]))

with tempfile.NamedTemporaryFile(suffix=".parquet") as f:
    pq.write_table(ha_table, f.name)
    ha_loaded = pq.read_table(f.name)

ha_meta = json.loads(ha_loaded.schema.field(ha_field.name).metadata[b"timetoalign"])
print(f"Harmony metadata: {ha_meta}")
assert ha_meta["field_type"] == "HarmonyField"
assert ha_meta["standard"] == "dcml"

# Reconstruct
ha_arr = ha_loaded.column(ha_field.name).combine_chunks()
loaded_dlf = DcmlLabelField.from_field(ha_arr, name=ha_field.name)
print(f"Reconstructed: {loaded_dlf}")
print(f"  [0]={loaded_dlf[0]}")
assert loaded_dlf[0].label == "V65"

# %% [markdown]
# ## What's Next
#
# With the type hierarchy in place, the next steps are:
#
# - **Loader mixins** (`PitchAccessMixin`, `HarmonyAccessMixin`) for
#   accessing typed fields from loaded timelines
# - **Duration and dynamics** field hierarchies following the same
#   three-layer pattern
# - **Cross-field queries** leveraging protocol dispatch for analysis
#   functions that work across field types
