# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.0
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Why TimeToAlign! Matters
#
# This introductory tutorial explains the problem that TimeToAlign! solves
# and previews its core capabilities.
#
# **Learning Objectives:**
# - Understand the challenge of heterogeneous music representations
# - Recognize the three temporal domains (Physical, Logical, Graphical)
# - Appreciate the value of a unified alignment framework
#
# **Prerequisites:**
# - Basic familiarity with music (notation, audio, sheet music)
# - No programming required for conceptual sections

# %% [markdown]
# ---
#
# ## The Problem: Fragmented Music Data
#
# Consider a simple question: **"Where does the melody begin?"**
#
# The answer depends entirely on *which representation* you're asking about:
#
# | Representation | Answer |
# |----------------|--------|
# | **Sheet music PDF** | "At pixel (245, 380) on page 1" |
# | **Audio recording** | "At 2.3 seconds" |
# | **MIDI file** | "At tick 960" |
# | **MusicXML score** | "At beat 1 of measure 2" |
#
# All four answers refer to the *same musical moment*, yet they use completely
# different coordinate systems.

# %% [markdown]
# ### The Same Music, Four Different Worlds
#
# ```
#                     ┌─────────────────┐
#                     │  Musical Event  │
#                     │  ("The melody") │
#                     └────────┬────────┘
#                              │
#         ┌────────────────────┼────────────────────┐
#         │                    │                    │
#         ▼                    ▼                    ▼
# ┌───────────────┐    ┌───────────────┐    ┌───────────────┐
# │  Sheet Music  │    │    Audio      │    │  MIDI/Score   │
# │   (Pixels)    │    │  (Seconds)    │    │   (Beats)     │
# │               │    │               │    │               │
# │  x=245, y=380 │    │  t=2.3s       │    │  tick=960     │
# │               │    │               │    │  beat=2.0     │
# └───────────────┘    └───────────────┘    └───────────────┘
#    GRAPHICAL            PHYSICAL             LOGICAL
# ```
#
# Without a framework to connect these representations, answering questions like:
#
# - *"What notes are visible in this region of the score image?"*
# - *"Which audio segment corresponds to this measure?"*
# - *"How does the performer's timing differ from the written score?"*
#
# ...requires tedious, error-prone manual alignment.

# %% [markdown]
# ---
#
# ## Current Pain Points
#
# Music researchers and developers face several recurring challenges:
#
# ### 1. Format-Specific Parsing
# Each data source requires specialized code:
# - MusicXML parsers (partitura, music21, etc.)
# - MIDI libraries (mido, pretty_midi, etc.)
# - Audio analysis tools (librosa, essentia, etc.)
# - Custom scripts for proprietary formats
#
# ### 2. Inconsistent Event Representation
# The same note might be represented as:
# - `{pitch: 60, onset: 1.5, duration: 0.5}` (seconds)
# - `{midi: 60, start: 720, end: 960}` (ticks)
# - `{step: C, octave: 4, beat: 1.5, length: 0.5}` (symbolic)
#
# ### 3. Lost Alignment Information
# When alignments *are* computed (e.g., score-to-performance matching), the results are often:
# - Stored in ad-hoc formats
# - Not reusable across tools
# - Lacking provenance metadata (who aligned this? how confident?)
#
# ### 4. Coordinate Conversion Errors
# Converting between systems (e.g., beats to seconds) requires tempo information, but:
# - Tempo changes mid-piece
# - Different sources may have different tempo curves
# - Performers rarely follow written tempo exactly

# %% [markdown]
# ---
#
# ## The TimeToAlign! Solution
#
# TimeToAlign! provides a **unified framework** for working with music across all representations:
#
# ```
#                          TimeToAlign!
#                               │
#          ┌────────────────────┼────────────────────┐
#          │                    │                    │
#          ▼                    ▼                    ▼
#     ┌─────────┐          ┌─────────┐          ┌─────────┐
#     │ Loaders │          │Timelines│          │ Matches │
#     └────┬────┘          └────┬────┘          └────┬────┘
#          │                    │                    │
#          ▼                    ▼                    ▼
#     Normalize            Coordinate           Encode
#     formats into         conversion           alignment
#     EventStores          via C-Maps           decisions
# ```
#
# ### Key Components
#
# 1. **Unified Timeline Model**
#    - Six timeline types covering all three domains
#    - Consistent coordinate system with units
#    - Hierarchical nesting (segments, children)
#
# 2. **Format-Agnostic Loaders**
#    - MusicXML, MIDI, TSV, MEI, and more
#    - All produce consistent `EventStore` objects
#    - Harmonized schema across formats
#
# 3. **ConversionMaps (C-Maps)**
#    - Transform coordinates between units
#    - Chain complex conversions (ticks -> beats -> seconds)
#    - Handle tempo changes and rubato
#
# 4. **Explicit Alignment (Matches)**
#    - Formally encode correspondence between events
#    - Include metadata: author, confidence, method
#    - Reusable and shareable

# %% [markdown]
# ---
#
# ## The Three Domains
#
# TimeToAlign! organizes all musical time into three **Domains**:
#
# ### Physical Domain
# Real-world, wall-clock time.
#
# - **Examples**: Audio files, recordings, performances
# - **Units**: Seconds, milliseconds, samples, frames
# - **Key property**: Absolute, measurable duration
#
# ### Logical Domain
# Symbolic, musical time.
#
# - **Examples**: Scores, MIDI files, notation
# - **Units**: Beats, quarters, measures, ticks
# - **Key property**: Tempo-independent ("beat 1" is always "beat 1")
#
# ### Graphical Domain
# Visual, spatial coordinates.
#
# - **Examples**: Score images, PDFs, spectrograms
# - **Units**: Pixels, centimeters, inches
# - **Key property**: Position on a visual canvas
#
# ```
#            ┌─────────────────────────────────────────────┐
#            │              TEMPORAL DOMAINS               │
#            ├─────────────┬─────────────┬─────────────────┤
#            │  PHYSICAL   │   LOGICAL   │    GRAPHICAL    │
#            ├─────────────┼─────────────┼─────────────────┤
#            │ Seconds     │ Beats       │ Pixels          │
#            │ Samples     │ Quarters    │ Centimeters     │
#            │ Frames      │ Ticks       │ Inches          │
#            ├─────────────┼─────────────┼─────────────────┤
#            │ Audio       │ Scores      │ Sheet images    │
#            │ Recordings  │ MIDI files  │ Spectrograms    │
#            │ Performances│ Notation    │ Visualizations  │
#            └─────────────┴─────────────┴─────────────────┘
# ```

# %% [markdown]
# ---
#
# ## Quick Demo: Consistent Data from Different Sources
#
# Here's a preview of TimeToAlign! in action. We'll load the same piece
# (Chopin Etude Op.10 No.3) from two different formats and verify they
# produce consistent results.

# %%
from pathlib import Path

from timetoalign.loader.score.partitura import PartituraLoader
from timetoalign.loader.score.tsv import TSVLoader

# Locate test data - relative to notebook location
_notebook_dir = Path(__file__).resolve().parent
DATA_DIR = _notebook_dir.parent.parent / "tests" / "data" / "midi" / "score"

# Same piece, two different formats
MUSICXML_PATH = DATA_DIR / "chopin_op10_no3.musicxml"
TSV_PATH = DATA_DIR / "ms3" / "chopin_op10_no3.notes.tsv"

# %%
# Load from MusicXML using Partitura
pt_loader = PartituraLoader()
pt_loader.load(MUSICXML_PATH)

# Load from TSV (MuseScore 3 export)
tsv_loader = TSVLoader()
tsv_loader.load(TSV_PATH)

# Both produce ScoreStores with consistent note counts!
pt_notes = pt_loader.store.notes.to_dataframe()
tsv_notes = tsv_loader.store.notes.to_dataframe()

pt_count = len(pt_notes[pt_notes["event_type"] == "Note"])
tsv_count = len(tsv_notes[tsv_notes["event_type"] == "Note"])

{
    "Partitura (MusicXML)": f"{pt_count} notes",
    "TSV (MS3 export)": f"{tsv_count} notes",
    "Match": pt_count == tsv_count,
}

# %% [markdown]
# Both loaders found **exactly 498 notes** in Chopin's Etude. This consistency
# is not accidental - it's a core design principle of TimeToAlign!:
#
# > **Different formats, same musical content, identical event counts.**
#
# This enables reliable cross-format analysis without worrying about parser discrepancies.

# %% [markdown]
# ---
#
# ## What TimeToAlign! Enables
#
# With a unified framework, you can:
#
# ### Research Applications
# - **Performance analysis**: Compare multiple performances of the same score
# - **OMR validation**: Verify optical music recognition against ground truth
# - **Corpus studies**: Analyze large collections with consistent data structures
#
# ### Practical Applications
# - **Score following**: Track playback position on sheet music
# - **Audio-to-score alignment**: Sync recordings with notation
# - **Annotation transfer**: Propagate labels across representations
#
# ### Development Benefits
# - **Write once, use everywhere**: Analysis code works on any format
# - **Reliable testing**: Gold-standard data for validation
# - **Reproducibility**: Alignments include full provenance

# %% [markdown]
# ---
#
# ## Tutorial Roadmap
#
# This tutorial series will guide you through TimeToAlign! from fundamentals
# to advanced applications:
#
# | Notebook | Topic | Key Concepts |
# |----------|-------|-------------|
# | **01_core_concepts** | Domains, Units, Coordinates | Building blocks |
# | **02_loading_data** | Loaders and EventStores | Bringing music data into TimeToAlign! |
# | **03_conversion_maps** | ConversionMaps (C-Maps) | Transforming coordinates between units |
# | **04_building_timelines** | Timelines and Hierarchies | Structured events |
# | **05_timestamps** | Cross-Section Views | Querying coordinates across the hierarchy |
# | **06_alignment_basics** | Matches and Alignment | Connecting events across timelines |
#
# Each tutorial builds on the previous ones, introducing new concepts with practical examples.

# %% [markdown]
# ---
#
# ## Summary
#
# **The Problem:**
# Music data exists in many formats (audio, scores, images) with incompatible
# coordinate systems. Connecting these representations requires tedious,
# error-prone manual work.
#
# **The Solution:**
# TimeToAlign! provides:
#
# 1. **Three Domains**: Physical (audio), Logical (scores), Graphical (images)
# 2. **Unified Timelines**: Consistent representation across all formats
# 3. **Format-Agnostic Loaders**: Normalize heterogeneous data
# 4. **ConversionMaps**: Transform coordinates between systems
# 5. **Explicit Alignment**: Formal encoding of correspondence
#
# **Key Takeaway:**
# > TimeToAlign! provides a common language for representing musical time,
# > regardless of the original format.

# %% [markdown]
# ## Next Steps
#
# Ready to dive in?
#
# - **01_core_concepts.ipynb**: Learn the fundamental building blocks
# - **02_loading_data.ipynb**: Start working with real music data
