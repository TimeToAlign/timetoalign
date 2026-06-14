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
# # Pitch and Harmony across Formats
#
# *The same sounding note, loaded from five different formats, and the
# typed view each one affords — faithful to exactly what that format
# records.*
#
# The DataFields and EventData tutorial established the universal
# Protocol / Scalar / Field triple: every music concept is a structural
# `Protocol`, a frozen `Scalar`, and a columnar `Field`, and an
# `EventData` *affords* a typed field over a raw column on request.  This
# tutorial puts that machinery to work on the messiest real-world test:
# the same pitch reaches the library from a symbolic score, from a MIDI
# performance, and from a note-alignment export, and each source knows a
# different amount about it.
#
# The lesson is that the heterogeneity is not an obstacle to paper over —
# it *is* the information.  A score that notates **C♯4** affords a
# `SpecificPitch`: it knows the spelling, so C♯4 is not D♭4.  A MIDI file
# that stores only note number 61 affords an `EnharmonicPitch` (or its
# display twin `MidiPitch`): it cannot tell C♯ from D♭, and the typed view
# says so.  They meet at the `EnharmonicPitch` level — the common ground
# every format can reach — and no pitch is ever left as a bare integer.

# %% [markdown]
# ## Setup

# %%
from __future__ import annotations

import pandas as pd
import pyarrow as pa

from timetoalign.core.events import (
    DcmlHarmony,
    DcmlHarmonyField,
    EnharmonicPitch,
    HarmonyLabel,
    MidiPitch,
    SpecificPitch,
)
from timetoalign.core.fields import build_struct_array
from timetoalign.core.protocols import (
    DcmlHarmonyLike,
    HarmonyLabelLike,
    RomanNumeralHarmonyLike,
    SpecificPitchLike,
    WesternTertianHarmonyLike,
)
from timetoalign.loader.alignment.parangonada import ParangonadaLoader
from timetoalign.loader.midi.performance import PerformanceMidiLoader
from timetoalign.loader.score.music21 import Music21Loader
from timetoalign.loader.score.partitura import PartituraLoader
from timetoalign.loader.score.tsv import TSVLoader
from timetoalign.testdata import ensure_data

VIENNA = ensure_data("vienna_1x22")
PARANGONAR = ensure_data("parangonar")

CHOPIN_TSV = VIENNA / "ms3" / "chopin_op10_no3.notes.tsv"
CHOPIN_XML = VIENNA / "Chopin_op10_no3.musicxml"
CHOPIN_MIDI = VIENNA / "Chopin_op10_no3_p01.mid"
EROICA = PARANGONAR / "Beethoven_Eroica_op35-cpjku"

# %% [markdown]
# ## One scalar, three views
#
# Before the loaders, recall what the three pitch scalars *are*.  All
# three describe MIDI note 61, but they record different things about it.
# `EnharmonicPitch` knows the semitone but not the spelling, so its short
# form shows both readings of a black key; `MidiPitch` is the same datum
# with a numeric face; `SpecificPitch` carries the notated spelling and so
# commits to one reading.

# %%
(
    ("EnharmonicPitch", EnharmonicPitch(61)),
    ("MidiPitch", MidiPitch(61)),
    ("SpecificPitch", SpecificPitch.from_label("C♯4")),
)

# %% [markdown]
# Only `SpecificPitch` satisfies `SpecificPitchLike` — the protocol that
# guarantees a spelling.  This is the structural distinction the loaders
# below will respect: a format that does not encode spelling cannot
# afford a field whose scalar satisfies this protocol.

# %%
(
    ("EnharmonicPitch", isinstance(EnharmonicPitch(61), SpecificPitchLike)),
    ("SpecificPitch", isinstance(SpecificPitch.from_label("C♯4"), SpecificPitchLike)),
)

# %% [markdown]
# ## The same C♯4, reached from four formats
#
# The Chopin Étude Op. 10 No. 3 ships in this corpus as an ms3 TSV note
# table, a MusicXML score, and as recorded MIDI performances.  Three
# loaders read the symbolic forms — `TSVLoader`, `Music21Loader`,
# `PartituraLoader` — and one reads the performance, `PerformanceMidiLoader`.
# Every one of them produces an `EventData`, and every `EventData` affords
# the `EnharmonicPitch` field by scalar type.
#
# We pull the `EnharmonicPitch` field from each, then pick out the same
# sounding note — MIDI 61, a C♯4.

# %%
ms3_ep = TSVLoader.from_file(CHOPIN_TSV).get_events().get_field(EnharmonicPitch)
m21_ep = Music21Loader.from_file(CHOPIN_XML).get_events().get_field(EnharmonicPitch)
ptt_ep = PartituraLoader.from_file(CHOPIN_XML).get_events().get_field(EnharmonicPitch)
midi_ep = (
    PerformanceMidiLoader.from_file(CHOPIN_MIDI).get_events().get_field(EnharmonicPitch)
)

ms3_i = next(
    i
    for i in range(len(ms3_ep))
    if ms3_ep[i] is not None and ms3_ep[i].midi_number == 61
)
m21_i = next(
    i
    for i in range(len(m21_ep))
    if m21_ep[i] is not None and m21_ep[i].midi_number == 61
)
ptt_i = next(
    i
    for i in range(len(ptt_ep))
    if ptt_ep[i] is not None and ptt_ep[i].midi_number == 61
)
midi_i = next(
    i
    for i in range(len(midi_ep))
    if midi_ep[i] is not None and midi_ep[i].midi_number == 61
)

# %% [markdown]
# Each format affords `get_field(EnharmonicPitch)` — the semitone view —
# and they agree note-for-note: MIDI 61 is `EP(C♯/D♭4)` everywhere.  The
# enharmonic field spells a black key both ways on purpose; it is the view
# that does *not* commit to a reading.

# %%
(
    ("ms3 TSV", ms3_ep[ms3_i]),
    ("music21", m21_ep[m21_i]),
    ("partitura", ptt_ep[ptt_i]),
    ("performance MIDI", midi_ep[midi_i]),
)

# %% [markdown]
# ## Where the formats diverge — the spelling affordance
#
# The agreement above is the floor.  The *ceiling* differs by format,
# because the three symbolic sources notate a spelling and the MIDI file
# does not.  Ask each `EventData` for `get_field(SpecificPitch)` and the
# divergence becomes visible in the types themselves.
#
# The three symbolic formats afford `SpecificPitch` — `SP(C♯4)`, a single
# committed spelling, distinct from D♭4:

# %%
ms3_sp = TSVLoader.from_file(CHOPIN_TSV).get_events().get_field(SpecificPitch)
m21_sp = Music21Loader.from_file(CHOPIN_XML).get_events().get_field(SpecificPitch)
ptt_sp = PartituraLoader.from_file(CHOPIN_XML).get_events().get_field(SpecificPitch)

(
    ("ms3 TSV", ms3_sp[ms3_i]),
    ("music21", m21_sp[m21_i]),
    ("partitura", ptt_sp[ptt_i]),
)

# %% [markdown]
# The MIDI performance cannot.  It stores note number 61 and nothing about
# how it was spelled, so the `SpecificPitch` field simply is not there to
# afford — asking for it raises, rather than inventing a spelling the
# source never recorded.  This refusal is the faithfulness guarantee: the
# typed view never claims to know more than the format does.

# %%
midi_events = PerformanceMidiLoader.from_file(CHOPIN_MIDI).get_events()
try:
    midi_events.get_field(SpecificPitch)
    spelling_result = "afforded (unexpected)"
except KeyError as exc:
    spelling_result = f"not afforded — {exc}"
spelling_result

# %% [markdown]
# What the MIDI file *does* afford, alongside `EnharmonicPitch`, is
# `MidiPitch`: the identical datum with a numeric display.  Use it when the
# note number itself is what you want to read.

# %%
midi_events.get_field(MidiPitch)[midi_i]

# %% [markdown]
# ### The equivalence, side by side
#
# Collecting the four formats into one table makes the pattern plain.  The
# `EnharmonicPitch` column is uniform; the `SpecificPitch` column is
# populated only where the format encodes spelling.  Every cell is the
# typed view the format genuinely affords — nothing is faked, nothing is
# left as a bare integer.

# %%
pd.DataFrame(
    [
        ("ms3 TSV", str(ms3_ep[ms3_i]), str(ms3_sp[ms3_i])),
        ("music21", str(m21_ep[m21_i]), str(m21_sp[m21_i])),
        ("partitura", str(ptt_ep[ptt_i]), str(ptt_sp[ptt_i])),
        ("performance MIDI", str(midi_ep[midi_i]), "—"),
    ],
    columns=["format", "EnharmonicPitch", "SpecificPitch"],
)

# %% [markdown]
# ## A fifth format — a note-alignment export
#
# The same affordance reaches further than score and performance files.  A
# *parangonada* note-alignment export — here the CP-JKU Eroica Variations,
# five performances aligned against one Beethoven score — loads into a
# whole multimodal `AlignmentBundle`.  Its shared logical score timeline
# carries each note's MIDI number, and that timeline's `EventData` affords
# `EnharmonicPitch` exactly like the others.
#
# This score has no C♯4, so we take its first C♯ honestly rather than
# pretend otherwise — a C♯3 at MIDI 49.  The point is the affordance, not
# the octave: the alignment export sits at the `EnharmonicPitch` level
# because it, too, records a note number and no spelling.

# %%
eroica_events = (
    ParangonadaLoader.from_file(EROICA)
    .create_bundle()
    .get_timeline("score:clt1")
    .get_events()
)
eroica_ep = eroica_events.get_field(EnharmonicPitch)

eroica_i = next(
    i
    for i in range(len(eroica_ep))
    if eroica_ep[i] is not None and eroica_ep[i].midi_number == 49
)
eroica_ep[eroica_i]

# %% [markdown]
# As with the MIDI performance, no spelling means no `SpecificPitch`
# field — the alignment export joins the unification at the enharmonic
# level and stops there.

# %%
try:
    eroica_events.get_field(SpecificPitch)
    eroica_result = "afforded (unexpected)"
except KeyError as exc:
    eroica_result = f"not afforded — {exc}"
eroica_result

# %% [markdown]
# ## The same principle for harmony
#
# Pitch is the clearest case, but the Protocol / Scalar / Field triple is
# uniform across every concept the library models — harmony included.
# Harmony has its own specificity ladder: a bare `HarmonyLabel` knows only
# a string, while a `DcmlHarmony` parsed from a functional label derives
# root, bass, chord type, and Roman-numeral function.

# %%
(
    ("HarmonyLabel", HarmonyLabel(label="CM", standard="chord_symbol")),
    ("DcmlHarmony", DcmlHarmony.from_label("V65", globalkey="C")),
)

# %% [markdown]
# The more specific scalar satisfies more protocols.  A `DcmlHarmony`
# satisfies the whole chain at once — it *is* a label, *is* a Western
# tertian chord, *is* a Roman-numeral function, and *is* a DCML harmony —
# so a consumer written against any of those protocols accepts it.

# %%
v65 = DcmlHarmony.from_label("V65", globalkey="C")
(
    ("HarmonyLabelLike", isinstance(v65, HarmonyLabelLike)),
    ("WesternTertianHarmonyLike", isinstance(v65, WesternTertianHarmonyLike)),
    ("RomanNumeralHarmonyLike", isinstance(v65, RomanNumeralHarmonyLike)),
    ("DcmlHarmonyLike", isinstance(v65, DcmlHarmonyLike)),
)

# %% [markdown]
# And harmony scalars assemble into a paired `DcmlHarmonyField` by exactly
# the route the DataFields tutorial used for `SpecificPitch`: build the
# scalars, gather them with `build_struct_array`, and hand the result to
# the field's `from_field`.  Indexing the field returns a fully-typed
# `DcmlHarmony` scalar — the same Scalar ⇄ Field payoff, one concept over.

# %%
progression = [
    DcmlHarmony.from_label(label, globalkey="C") for label in ["I", "viio7", "V65"]
]
harmony_arr = build_struct_array(DcmlHarmony, progression)
harmony_field = DcmlHarmonyField.from_field(
    (harmony_arr, pa.field("harmony", harmony_arr.type))
)

(harmony_field[0], harmony_field[1], harmony_field[2])

# %% [markdown]
# ## Recap
#
# - The **same sounding pitch** reaches the library from many formats, and
#   each one's `EventData` affords the typed view it genuinely supports.
# - Symbolic formats that notate spelling (ms3 TSV, music21, partitura)
#   afford **`SpecificPitch`** — C♯4 is not D♭4.  Formats that store only a
#   note number (performance MIDI, a note-alignment export) afford
#   **`EnharmonicPitch`** / **`MidiPitch`**, where C♯4 ≡ D♭4, and refuse
#   `SpecificPitch` rather than fabricate a spelling.
# - All formats **unify at the `EnharmonicPitch` level**: the common
#   ground every source can reach, with no pitch left as a bare integer.
# - The same **Protocol / Scalar / Field** uniformity carries to harmony —
#   a specificity ladder, structural protocol dispatch, and the identical
#   `build_struct_array` route into a paired field.
