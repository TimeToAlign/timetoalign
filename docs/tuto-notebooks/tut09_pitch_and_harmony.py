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
# *What you will build*
#
# You will build a typed comparison of pitch information from an ms3 table,
# two MusicXML readers, a MIDI performance, and a note-alignment export. By
# the end, you can state exactly which sources preserve a written spelling and
# which preserve only a sounding pitch, then apply the same distinction to
# harmony labels.
#
# *Before you start*
#
# Complete [The Data Model](tut08_data_model.ipynb) first; this notebook reuses
# its scalar, field, and protocol pattern.

# %% [markdown]
# ## Setup

# %%
import pandas as pd
import pyarrow as pa

from timetoalign import (
    Ms3Loader,
    Music21Loader,
    ParangonadaLoader,
    PartituraLoader,
    PerformanceMidiLoader,
)
from timetoalign.core import (
    DcmlHarmony,
    DcmlHarmonyField,
    EnharmonicPitch,
    EnharmonicPitchClass,
    EnharmonicPitchField,
    HarmonyLabel,
    MidiPitch,
    SpecificPitch,
    SpecificPitchClass,
    SpecificPitchField,
    build_struct_array,
)
from timetoalign.core.protocols import (
    DcmlHarmonyLike,
    EnharmonicPitchLike,
    GenericPitchLike,
    HarmonyLabelLike,
    RomanNumeralHarmonyLike,
    SpecificPitchClassLike,
    SpecificPitchLike,
    WesternTertianHarmonyLike,
)
from timetoalign.testdata import ensure_data

parangonar_data = ensure_data("parangonar")
vienna_data = ensure_data("vienna_1x22")

# %% [markdown]
# ## Faithfulness
#
# A typed view records what a source represented, not what another source
# might let us infer. We begin with the two source facts that the rest of the
# notebook will compare.

# %%
written_pitch = "C♯4"
target_midi_number = 61
source_facts = {
    "score notation": written_pitch,
    "MIDI performance": target_midi_number,
}
source_facts

# %% [markdown]
# The score fact includes a letter name and accidental; the MIDI fact is only
# note number 61. Although both can describe the same key on a piano, the
# second fact does not contain enough information to choose C♯4 over D♭4.

# %% [markdown]
# ## The pitch ladder
#
# Pitch types differ by how much they promise to know. Here are three views of
# the same sounding pitch, followed by the corresponding spelled and
# enharmonic pitch-class views.

# %%
enharmonic_pitch = EnharmonicPitch(source_facts["MIDI performance"])
midi_pitch = MidiPitch(source_facts["MIDI performance"])
specific_pitch = SpecificPitch.from_string(source_facts["score notation"])
specific_pitch_class = SpecificPitchClass.from_string("C♯")
enharmonic_pitch_class = EnharmonicPitchClass(specific_pitch.pitch_class)
pitch_ladder = {
    "enharmonic pitch": enharmonic_pitch,
    "MIDI pitch": midi_pitch,
    "specific pitch": specific_pitch,
    "specific pitch class": specific_pitch_class,
    "enharmonic pitch class": enharmonic_pitch_class,
}
pitch_ladder

# %% [markdown]
# `EP(C♯/D♭4)` deliberately displays both spellings: `EnharmonicPitch`
# knows the octave and semitone but does not commit to an accidental.
# `MidiPitch` presents the same stored `midi_number` numerically, while
# `SpecificPitch` and `SpecificPitchClass` preserve the written spelling.

# %% [markdown]
# ## Protocols encode the ladder
#
# Protocols let an analysis require only the knowledge it needs. Testing the
# scalar values against all four protocols makes their guarantees explicit.

# %%
pitch_protocols = {
    "GenericPitchLike": GenericPitchLike,
    "EnharmonicPitchLike": EnharmonicPitchLike,
    "SpecificPitchClassLike": SpecificPitchClassLike,
    "SpecificPitchLike": SpecificPitchLike,
}
protocol_values = {
    "EnharmonicPitch": pitch_ladder["enharmonic pitch"],
    "SpecificPitchClass": pitch_ladder["specific pitch class"],
    "SpecificPitch": pitch_ladder["specific pitch"],
}
protocol_results = {
    name: [isinstance(value, protocol) for value in protocol_values.values()]
    for name, protocol in pitch_protocols.items()
}
protocol_checks = pd.DataFrame(protocol_results, index=protocol_values)
protocol_checks

# %% [markdown]
# All three values expose a pitch class. The octave-bearing enharmonic value
# satisfies `EnharmonicPitchLike`, and the spelled pitch class satisfies
# `SpecificPitchClassLike`; only the fully spelled, octave-bearing value
# satisfies `SpecificPitchLike`.

# %% [markdown]
# ## The same C♯4 from four formats
#
# Four earlier loaders expose typed pitch fields over their note
# {{< glossary Event >}} data. One helper locates the first occurrence of
# a requested MIDI note number so that the selection rule is identical for
# every format.


# %%
def index_of_midi_number(pitch_field, midi_number):
    """Return the index of the first non-null pitch with this MIDI number."""
    for position, pitch in enumerate(pitch_field):
        if pitch is not None and pitch.midi_number == midi_number:
            return position
    raise ValueError(f"MIDI note number {midi_number} does not occur")


chopin_tsv = vienna_data / "ms3" / "chopin_op10_no3.notes.tsv"
chopin_xml = vienna_data / "Chopin_op10_no3.musicxml"
chopin_midi = vienna_data / "Chopin_op10_no3_p01.mid"
chopin_sources = {
    "ms3 TSV": (Ms3Loader, chopin_tsv),
    "music21": (Music21Loader, chopin_xml),
    "partitura": (PartituraLoader, chopin_xml),
    "performance MIDI": (PerformanceMidiLoader, chopin_midi),
}
chopin_loaders = {
    name: loader_class.from_file(path)
    for name, (loader_class, path) in chopin_sources.items()
}
chopin_events = {name: loader.get_events() for name, loader in chopin_loaders.items()}
enharmonic_fields = {
    name: events.get_field(EnharmonicPitch) for name, events in chopin_events.items()
}
c_sharp_indices = {
    name: index_of_midi_number(field, target_midi_number)
    for name, field in enharmonic_fields.items()
}
c_sharp_by_format = {
    name: enharmonic_fields[name][position]
    for name, position in c_sharp_indices.items()
}
c_sharp_by_format

# %% [markdown]
# Every loader returns `EP(C♯/D♭4)` for note number 61. The occurrence
# indices differ because these sources organise their rows differently, but
# their `EnharmonicPitch` fields agree on the sounding pitch without choosing
# a spelling.

# %% [markdown]
# ## Where they diverge
#
# The symbolic sources also represented spelling, so they afford
# `SpecificPitch`. The MIDI performance did not; we ask for the same field
# deliberately and retain the resulting refusal as the cell value.

# %%
symbolic_sources = ("ms3 TSV", "music21", "partitura")
specific_fields = {
    name: chopin_events[name].get_field(SpecificPitch) for name in symbolic_sources
}
midi_specific_error = None
try:
    chopin_events["performance MIDI"].get_field(SpecificPitch)
except KeyError as exc:
    midi_specific_error = exc
midi_specific_error

# %% [markdown]
# The three assignments in `specific_fields` succeed. The displayed `KeyError`
# says that the MIDI table has no `SpecificPitchField`: refusing the request is
# the feature, because returning C♯4 or D♭4 would invent information.

# %% [markdown]
# ## What MIDI does afford
#
# MIDI does afford a numeric pitch view. Its scalar and the two field classes
# also show the distinction between one value and columnar storage.

# %%
midi_pitch_field = chopin_events["performance MIDI"].get_field(MidiPitch)
numeric_c_sharp = midi_pitch_field[c_sharp_indices["performance MIDI"]]
columnar_pitch_views = {
    "MIDI scalar": numeric_c_sharp,
    "midi_number": numeric_c_sharp.midi_number,
    "enharmonic field": isinstance(
        enharmonic_fields["performance MIDI"], EnharmonicPitchField
    ),
    "specific field": isinstance(specific_fields["ms3 TSV"], SpecificPitchField),
}
columnar_pitch_views

# %% [markdown]
# `MP(61)` is the same datum as `EP(C♯/D♭4)` with a numeric face.
# `EnharmonicPitchField` and `SpecificPitchField` are the PyArrow-backed
# columnar counterparts of their scalar types; indexing either field returns
# a typed scalar.

# %% [markdown]
# ## Side by side
#
# A compact table now separates the common enharmonic view from the extra
# spelling supplied by symbolic notation and the numeric face used for MIDI.

# %%
comparison_rows = [
    {
        "format": name,
        "enharmonic view": c_sharp_by_format[name],
        "specific view": specific_fields[name][c_sharp_indices[name]],
        "numeric view": "—",
    }
    for name in symbolic_sources
]
comparison_rows.append(
    {
        "format": "performance MIDI",
        "enharmonic view": c_sharp_by_format["performance MIDI"],
        "specific view": "not represented",
        "numeric view": numeric_c_sharp,
    }
)
four_format_comparison = pd.DataFrame(comparison_rows)
four_format_comparison

# %% [markdown]
# The enharmonic column visibly retains the two-spelling form `C♯/D♭4` in
# every row. Only the three symbolic rows contain `C♯4`; the performance row
# states that spelling was not represented rather than displaying an
# unexplained missing value.

# %% [markdown]
# ## A fifth source
#
# A parangonada export is a note alignment, rather than a score or a
# recording. `ParangonadaLoader` assembles its earlier
# {{< glossary AlignmentBundle >}}, whose score {{< glossary Timeline >}}
# carries note numbers and therefore joins the comparison at the enharmonic
# level.

# %%
eroica_path = parangonar_data / "Beethoven_Eroica_op35-cpjku"
parangonada_loader = ParangonadaLoader.from_file(eroica_path)
eroica_bundle = parangonada_loader.create_bundle()
eroica_score_timeline = eroica_bundle.get_timeline("score:clt1")
eroica_events = eroica_score_timeline.get_events()
eroica_enharmonic_field = eroica_events.get_field(EnharmonicPitch)
eroica_midi_field = eroica_events.get_field(MidiPitch)
eroica_midi_number = 63
eroica_pitch_index = index_of_midi_number(eroica_enharmonic_field, eroica_midi_number)
eroica_pitch = eroica_enharmonic_field[eroica_pitch_index]
eroica_numeric_pitch = eroica_midi_field[eroica_pitch_index]
eroica_row = pd.DataFrame(
    [
        {
            "format": "parangonada note alignment",
            "enharmonic view": eroica_pitch,
            "specific view": "not represented",
            "numeric view": eroica_numeric_pitch,
        }
    ]
)
five_source_comparison = pd.concat(
    [four_format_comparison, eroica_row], ignore_index=True
)
five_source_comparison

# %% [markdown]
# MIDI 63 genuinely occurs in this Beethoven export and renders as
# `EP(D♯/E♭4)`. The example does not force the Chopin C♯4 into another
# work: it demonstrates that alignment data carrying only note numbers makes
# the same faithful choice as MIDI. The typed `MidiPitch` uses its compact
# numeric rendering, `63`, inside the table.

# %% [markdown]
# ## The same principle for harmony
#
# `HarmonyLabel` preserves a label and its declared standard, while
# `DcmlHarmony.from_label` parses the structure genuinely encoded by a DCML
# label. One parsed scalar then demonstrates the full harmony protocol chain.

# %%
literal_harmony = HarmonyLabel(label="V65", standard="dcml")
parsed_harmony = DcmlHarmony.from_label("V65", globalkey="C")
harmony_protocol_checks = {
    "HarmonyLabelLike": isinstance(parsed_harmony, HarmonyLabelLike),
    "WesternTertianHarmonyLike": isinstance(parsed_harmony, WesternTertianHarmonyLike),
    "RomanNumeralHarmonyLike": isinstance(parsed_harmony, RomanNumeralHarmonyLike),
    "DcmlHarmonyLike": isinstance(parsed_harmony, DcmlHarmonyLike),
}
harmony_views = {
    "literal label": literal_harmony,
    "parsed DCML harmony": parsed_harmony,
    "parsed protocols": harmony_protocol_checks,
}
harmony_views

# %% [markdown]
# The parsed `V65` satisfies all four protocols, from a labelled harmony to
# the DCML-specific structure. Harmony keeps `from_label` because its source
# value genuinely is a label; a pitch name is the pitch written as a string,
# so pitch uses `from_string`.

# %% [markdown]
# ## Building a harmony field
#
# Harmony uses the same bulk-construction route that the data-model tutorial
# used for pitch: build one Arrow struct array, then wrap it as the matching
# semantic field.

# %%
harmony_progression = [
    DcmlHarmony.from_label("I", globalkey="C"),
    DcmlHarmony.from_label("viio7", globalkey="C"),
    parsed_harmony,
]
harmony_array = build_struct_array(DcmlHarmony, harmony_progression)
harmony_arrow_field = pa.field("harmony", harmony_array.type)
harmony_field = DcmlHarmonyField.from_field((harmony_array, harmony_arrow_field))
indexed_harmony = harmony_field[1]
harmony_field_result = {
    "is DcmlHarmonyField": isinstance(harmony_field, DcmlHarmonyField),
    "indexed scalar": indexed_harmony,
    "is DcmlHarmony": isinstance(indexed_harmony, DcmlHarmony),
}
harmony_field_result

# %% [markdown]
# The field retains the semantic type for the whole column, and indexing it
# returns the fully typed scalar `DcmlHarmony(label='viio7', key=C:I)`. No row
# dictionary or manual Arrow struct is needed.

# %% [markdown]
# ## What you learned
#
# - You can distinguish source representation from later musical inference.
# - You can choose among enharmonic, MIDI, and specifically spelled pitch
#   scalars and pitch classes.
# - You can use pitch protocols to state how much pitch information an
#   analysis requires.
# - You can retrieve a common `EnharmonicPitch` view from four score and
#   performance readers with one consistent selection rule.
# - You can interpret the absence of `SpecificPitch` from MIDI as a
#   faithfulness guarantee.
# - You can read MIDI note numbers as `MidiPitch` values and recognise their
#   columnar field counterparts.
# - You can compare typed pitch affordances without replacing absent knowledge
#   with an unexplained missing value.
# - You can place a note-alignment export at the same enharmonic level as MIDI.
# - You can distinguish a literal harmony label from a parsed DCML harmony and
#   test the harmony protocol chain.
# - You can build and index a typed `DcmlHarmonyField` through the standard
#   Arrow route.
# - You can carry this faithfulness principle into format-specific research
#   workflows.
#
# ## Next
#
# This concludes the tutorial series. Continue with the practical
# [How-to guide for loading the Vienna corpus](../howto/how03_loading_vienna_corpus.ipynb),
# then choose a guide that matches the format or alignment task in your own
# research.
#
# *Go deeper* — [Load a parangonada note alignment](../howto/how03_parangonada.ipynb)
# and [load CSV or TSV data](../howto/how04_loading_csv.ipynb).
