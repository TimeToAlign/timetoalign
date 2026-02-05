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
# # 08: SUPRA Piano Roll - A Complete Alignment Workflow
#
# This tutorial applies everything we've learned to a real-world case study:
# aligning a **scanned piano roll image** with **MIDI files**, **audio**, and
# **score annotations** from the Stanford University Piano Roll Archive (SUPRA).
#
# **Learning Objectives:**
# - Create a graphical timeline from ATON analysis data
# - Add C-Maps for physical unit conversion (pixels to inches/cm)
# - Use the **child timeline** API for hierarchical relationships
# - Load MIDI, audio, and score data with specialized loaders
# - Build a **TimelineGroup** connecting all representations
# - Transfer coordinates across the entire alignment chain
#
# **Prerequisites:**
# - Notebook 04 (Timelines, hierarchies)
# - Notebook 05 (Timestamps)
# - Notebook 07 (Alignment Basics, TimelineGroup)
#
# **Data Source:**
# - **Roll**: WM 990 (Welte-Mignon red roll, T-100)
# - **Piece**: Richard Wagner - Meistersinger von Nurnberg: Vorspiel (Prelude)
# - **Performer**: Myrtle Elvyn, piano (December 6, 1905)
# - **SUPRA URL**: https://supra.stanford.edu/
# - **DRUID**: fd660zf8362

# %% [markdown]
# ## Gold Standard Reference Values
#
# Per the ZERO TOLERANCE policy, all values use exact counts from the SUPRA
# analysis:
#
# | Parameter | Value | Description |
# |-----------|-------|-------------|
# | `IMAGE_WIDTH` | 4,096 | Image width in pixels |
# | `IMAGE_HEIGHT` | 299,400 | Image height in pixels |
# | `LENGTH_DPI` | 300.25 | Scan resolution (pixels per inch) |
# | `PHYSICAL_LENGTH` | 997.17 | Roll length in inches (25.33 m) |
# | `FIRST_HOLE` | 15,343 | Pixel row of first musical hole |
# | `LAST_HOLE` | 293,119 | Pixel row of last musical hole |
# | `MUSICAL_LENGTH` | 277,776 | Pixels from first to last hole |
# | `MUSICAL_HOLES` | 30,092 | Individual hole punches (raw MIDI events) |
# | `RAW_MIDI_NOTES` | 30,092 | Raw MIDI note count (1 per hole) |
# | `EXP_MIDI_NOTES` | 6,380 | Expressive MIDI note count (merged) |
# | `SCORE_NOTES` | 5,577 | Notes in DCML score |
# | `SCORE_MEASURES` | 222 | Measures in DCML score |
# | `SCORE_LENGTH` | 888 | Total quarterbeats |

# %% [markdown]
# ## Setup

# %%
from pathlib import Path

from timetoalign import TimeUnit
from timetoalign.alignment import TimelineGroup
from timetoalign.loader.graphical.aton import ATONLoader
from timetoalign.loader.midi import PerformanceMidiLoader
from timetoalign.loader.physical import AudioLoader
from timetoalign.loader.score import TSVLoader
from timetoalign.maps import ScalarMap
from timetoalign.timelines import ContinuousPhysicalTimeline

_notebook_dir = Path(".").resolve()
DATA_DIR = _notebook_dir.parent.parent / "tests" / "data" / "supra"
assert DATA_DIR.is_dir(), f"SUPRA data directory not found: {DATA_DIR}"

ATON_FILE = DATA_DIR / "image" / "fd660zf8362_analysis.txt"
MIDI_RAW_PATH = DATA_DIR / "midi" / "fd660zf8362_raw.mid"
MIDI_EXP_PATH = DATA_DIR / "midi" / "fd660zf8362_exp.mid"
MP3_PATH = DATA_DIR / "midi" / "fd660zf8362.mp3"
DCML_DIR = DATA_DIR / "dcml"

{"Data directory": str(DATA_DIR), "ATON file": ATON_FILE.name}

# %% [markdown]
# ---
#
# ## Part A: Create the Image Timeline (DGT1) from ATON Loader
#
# The ATON (Artistic Text-based Object Notation) file contains hole punch data
# from the Stanford SUPRA project's piano roll analysis. The loader creates a
# timeline with **all hole events already populated** at their absolute pixel
# coordinates.

# %%
aton_loader = ATONLoader()
aton_loader.load(ATON_FILE)

assert aton_loader.musical_holes == 30092
assert aton_loader.musical_notes == 8718
assert aton_loader.first_hole.value == 15343
assert aton_loader.last_hole.value == 293119
assert aton_loader.musical_length.value == 277776
assert aton_loader.image_dimensions["height"] == 299400

{
    "Image height": f"{aton_loader.image_dimensions['height']:,} pixels",
    "Musical holes": f"{aton_loader.musical_holes:,}",
    "First hole": aton_loader.first_hole,
    "Last hole": aton_loader.last_hole,
    "Musical length": aton_loader.musical_length,
    "Verification": "PASSED",
}

# %% [markdown]
# The loader creates a timeline spanning the full image with holes at absolute coordinates.

# %%
dgt1 = aton_loader.create_timeline(uid="dgt1", name="Piano Roll Image (WM 990)")
dgt1

# %% [markdown]
# ---
#
# ## Part B: Add Physical Unit C-Maps
#
# The piano roll was scanned at 300.25 DPI (dots per inch). We attach
# ConversionMaps to convert pixel coordinates to physical units.
#
# **Calculation:** 299,400 pixels / 300.25 DPI = 997.17 inches = 25.33 meters

# %%
LENGTH_DPI = 300.25

dgt1.add_conversion_map(
    ScalarMap(
        scalar=1 / LENGTH_DPI,
        source_unit="pixels",
        target_unit="inches",
    )
)

dgt1.add_conversion_map(
    ScalarMap(
        scalar=2.54 / LENGTH_DPI,
        source_unit="pixels",
        target_unit="cm",
    )
)

# %% [markdown]
# The `convert_to` method returns proper Coordinate objects with units.

# %%
image_length_inches = dgt1.convert_to(dgt1.length, "inches")
image_length_cm = dgt1.convert_to(dgt1.length, "cm")

{
    "Image length": dgt1.length,
    "Image length (inches)": image_length_inches,
    "Image length (cm)": image_length_cm,
    "Image length (meters)": f"{image_length_cm.value / 100:.2f} meters",
}

# %% [markdown]
# ---
#
# ## Part C: Create Child Timeline for Relative Coordinates
#
# The musical content doesn't span the entire image - holes start at pixel 15,343.
# We create a **child timeline** to provide a relative coordinate view where the
# first hole = 0 pixels.
#
# **Key insight:** The child has no events of its own. It's purely a coordinate
# transformation. When we get timestamps, we see event coordinates in BOTH
# the parent (absolute) and child (relative) coordinate systems - for free!

# %% [markdown]
# Note that `first_hole` and `musical_length` now return Coordinates, so we can
# pass them directly to `create_child()` without manual conversion.

# %%
dgt_holes = dgt1.create_child(
    length=aton_loader.musical_length,
    offset=aton_loader.first_hole,
    uid="dgt_holes",
    name="Musical Holes Region",
)

print(dgt1)

# %%
{
    "Child timeline": dgt_holes.id,
    "Child length": dgt_holes.length,
    "Offset in parent": aton_loader.first_hole,
    "Child events": dgt_holes.n_events,
    "Parent events": dgt1.n_events,
}

# %% [markdown]
# ---
#
# ## Part D: Demonstrate Timestamps
#
# With the parent-child hierarchy established, we can generate **timestamps**
# that show coordinates in both the parent (full image) and child (holes region)
# coordinate systems simultaneously.

# %%
timestamps_df = dgt1.get_timestamps(conversion_maps=True)

{"Total timestamps": len(timestamps_df), "Columns": list(timestamps_df.columns)}

# %% [markdown]
# **Why ~20,680 timestamps?**
#
# The timestamp table has one row per **unique** event coordinate in the hierarchy:
# - Parent timeline (dgt1) contains 30,092 hole events at absolute pixel coordinates
# - But many holes share the same pixel row (multiple notes at one time position)
# - After de-duplication: ~20,676 unique coordinates plus 4 boundary coordinates
#
# Each row shows the coordinate in **all** coordinate systems simultaneously:
# - `axis`: The root (parent) coordinate in pixels
# - `dgt1`: Same as axis (this IS the root timeline)
# - `dgt_holes`: **Relative** coordinate in child timeline (first hole = 0, NaN if outside)
# - C-Map columns: Physical units (inches, cm) computed via attached ScalarMaps

# %%
timestamps_df.head(10)

# %% [markdown]
# Query a specific coordinate: at pixel 100,000 in the image, what's the local
# coordinate in the holes region?

# %%
ts = dgt1.get_timestamp(100000.0)

{
    "Query (parent coord)": 100000.0,
    "Child coord (dgt_holes)": ts["dgt_holes"],
    "Calculation": f"100000 - {aton_loader.first_hole.value} = {100000 - aton_loader.first_hole.value}",
}

# %% [markdown]
# Boundary table shows where child timelines start and end (with C-Maps).

# %%
boundary_df = dgt1.get_boundary_table(conversion_maps=True).to_pandas()
boundary_df

# %% [markdown]
# ---
#
# ## Part E: Load External Data Files
#
# Now we load the MIDI files, audio, and score annotations. Each becomes a
# separate timeline that we'll connect via the TimelineGroup.

# %% [markdown]
# ### E.1: DLT1 - Raw MIDI (one event per hole)

# %%

midi_raw_loader = PerformanceMidiLoader()
midi_raw_loader.load(MIDI_RAW_PATH)

dlt1_raw = midi_raw_loader.store.notes.create_timeline(uid="dlt1_raw")
raw_note_count = len(midi_raw_loader.store.notes)

print(dlt1_raw)

# %%
{
    "DLT1 (MIDI Raw)": dlt1_raw.id,
    "Length": f"{dlt1_raw.length.value:,} ticks",
    "Note events": f"{raw_note_count:,}",
}

# %% [markdown]
# ### E.2: DLT2 - Expressive MIDI (merged notes + dynamics)

# %%
midi_exp_loader = PerformanceMidiLoader()
midi_exp_loader.load(MIDI_EXP_PATH)

dlt2_exp = midi_exp_loader.store.notes.create_timeline(uid="dlt2_exp")
exp_note_count = len(midi_exp_loader.store.notes)

print(dlt2_exp)

# %%
{
    "DLT2 (MIDI Expressive)": dlt2_exp.id,
    "Length": f"{dlt2_exp.length.value:,} ticks",
    "Note events": f"{exp_note_count:,}",
}

# %% [markdown]
# ### E.3: DPT1 - Audio (MP3)
#
# **Note:** MP3 loading requires `mutagen` or `soundfile`. If not installed,
# we use a mock timeline with the known duration from the README.

# %%

try:
    audio_loader = AudioLoader()
    audio_loader.load(MP3_PATH)
    dpt1_audio = audio_loader.to_timeline(uid="dpt1_audio")
    audio_duration = audio_loader.duration_seconds
    audio_info = {
        "DPT1 (Audio)": dpt1_audio.id,
        "Sample rate": f"{audio_loader.sample_rate:,} Hz",
        "Duration": f"{audio_duration:.2f} seconds",
    }
except ValueError as e:
    print(f"Note: MP3 loading unavailable ({e}). Using mock timeline.")
    audio_duration = 446.03
    dpt1_audio = ContinuousPhysicalTimeline(
        length=audio_duration,
        unit=TimeUnit.seconds,
        uid="dpt1_audio",
    )
    audio_info = {
        "DPT1 (Audio)": dpt1_audio.id,
        "Duration": f"{audio_duration:.2f} seconds (from README)",
    }

print(dpt1_audio)

# %%
audio_info

# %% [markdown]
# ### E.4: CLT1 - Score Annotations (DCML TSV files)
#
# The DCML corpus provides score data in TSV format. We load **all four files**
# (notes, measures, harmonies, chords) at once using glob, then call
# `create_timeline()` which creates a parent timeline with one child per data type.

# %%

SCORE_BASE = "WWV096-Meistersinger_01_Vorspiel-Prelude_SchottKleinmichel"
score_tsv_files = sorted(DCML_DIR.glob(f"{SCORE_BASE}.*.tsv"))

[f.name for f in score_tsv_files]

# %% [markdown]
# Load all TSV files at once using `*` unpacking - elegant and Pythonic.

# %%
score_loader = TSVLoader()
score_loader.load(*score_tsv_files)

score_loader.store.summary()

# %% [markdown]
# Verify against gold standard (ZERO TOLERANCE).

# %%
notes_count = len(score_loader.store.notes)
measures_count = len(score_loader.store.measures)

assert notes_count == 5577, f"Notes mismatch: {notes_count} != 5577"
assert measures_count == 222, f"Measures mismatch: {measures_count} != 222"

{"Notes": notes_count, "Measures": measures_count, "Verification": "PASSED"}

# %% [markdown]
# Create the score timeline using `create_timeline()` which determines length
# from event coordinates. This creates a parent timeline with children for
# each data type (notes, measures, etc.) and correctly computes the full length
# as 888 quarterbeats.

# %%
clt1_score = score_loader.create_timeline(uid="clt1_score")

clt1_score

# %% [markdown]
# ---
#
# ## Part F: Create the TimelineGroup
#
# Now we bring everything together in a **TimelineGroup**. This establishes
# commensurability between all timelines, enabling coordinate transfer.
#
# **Important:** A TimelineGroup does NOT have a root timeline - all timelines
# are peers. We create it from a list of timelines.
#
# **Alignment structure:**
# ```
# dgt_holes (pixels)
#     |
#     +-- dlt1_raw (MIDI ticks)
#     |
#     +-- dlt2_exp (MIDI ticks)
#     |
#     +-- dpt1_audio (seconds)
#     |
#     +-- clt1_score (quarterbeats)
# ```

# %%
group = TimelineGroup(
    id="supra_alignment",
    name="SUPRA Piano Roll Alignment",
    timelines=[dgt_holes, dlt1_raw, dlt2_exp, dpt1_audio, clt1_score],
)

print(group)

# %%
{"Group": group.name, "Timelines": group.timeline_ids, "Count": group.n_timelines}

# %% [markdown]
# View the timestamp table showing alignment boundaries.

# %%
group.get_timestamps_df()

# %% [markdown]
# ---
#
# ## Part G: Coordinate Transfer
#
# With all timelines in the group, we can transfer coordinates between any pair.
# The group handles the conversion chain automatically.

# %%
holes_midpoint = aton_loader.musical_length.value / 2

{
    "Query coordinate": f"{holes_midpoint:,.0f} pixels (holes midpoint)",
    "-> MIDI raw": f"{group.convert(holes_midpoint, 'dgt_holes', 'dlt1_raw'):,.0f} ticks",
    "-> MIDI exp": f"{group.convert(holes_midpoint, 'dgt_holes', 'dlt2_exp'):,.0f} ticks",
    "-> Audio": f"{group.convert(holes_midpoint, 'dgt_holes', 'dpt1_audio'):.2f} seconds",
    "-> Score": f"{group.convert(holes_midpoint, 'dgt_holes', 'clt1_score'):.2f} quarterbeats",
}

# %% [markdown]
# Transfer from score to image: Measure 50 starts at quarterbeat 196.

# %%
score_coord = 196.0

midi_ticks = group.convert(score_coord, "clt1_score", "dlt1_raw")
holes_pixels = group.convert(score_coord, "clt1_score", "dgt_holes")
audio_seconds = group.convert(score_coord, "clt1_score", "dpt1_audio")

image_pixels = holes_pixels + aton_loader.first_hole.value
image_inches = dgt1.convert_to(image_pixels, "inches")
image_cm = dgt1.convert_to(image_pixels, "cm")

{
    "Score coord": f"{score_coord} quarterbeats (measure 50)",
    "-> MIDI ticks": f"{midi_ticks:,.0f}",
    "-> Holes region": f"{holes_pixels:,.0f} pixels",
    "-> Full image": f"{image_pixels:,.0f} pixels",
    "-> Physical": f"{image_inches} ({image_cm})",
    "-> Audio": f"{audio_seconds:.2f} seconds",
}

# %% [markdown]
# ---
#
# ## Part H: Verification
#
# Let's verify some key alignment properties.

# %%
holes_start = 0.0
midi_start = group.convert(holes_start, "dgt_holes", "dlt1_raw")
audio_start = group.convert(holes_start, "dgt_holes", "dpt1_audio")
score_start = group.convert(holes_start, "dgt_holes", "clt1_score")

holes_end = float(aton_loader.musical_length.value)
midi_end = group.convert(holes_end, "dgt_holes", "dlt1_raw")
audio_end = group.convert(holes_end, "dgt_holes", "dpt1_audio")
score_end = group.convert(holes_end, "dgt_holes", "clt1_score")

{
    "Holes start (0 px)": {
        "MIDI": f"{midi_start:.0f} ticks",
        "Audio": f"{audio_start:.2f} sec",
        "Score": f"{score_start:.2f} qb",
    },
    "Holes end (277776 px)": {
        "MIDI": f"{midi_end:.0f} ticks",
        "Audio": f"{audio_end:.2f} sec",
        "Score": f"{score_end:.2f} qb",
    },
}

# %% [markdown]
# Verify round-trip conversion (should return to original value).

# %%
test_coord = 100000.0

to_midi = group.convert(test_coord, "dgt_holes", "dlt1_raw")
back_to_holes = group.convert(to_midi, "dlt1_raw", "dgt_holes")

to_audio = group.convert(test_coord, "dgt_holes", "dpt1_audio")
back_from_audio = group.convert(to_audio, "dpt1_audio", "dgt_holes")

{
    "Original": test_coord,
    "Via MIDI": {
        "forward": to_midi,
        "back": back_to_holes,
        "match": abs(back_to_holes - test_coord) < 0.001,
    },
    "Via Audio": {
        "forward": to_audio,
        "back": back_from_audio,
        "match": abs(back_from_audio - test_coord) < 0.001,
    },
}

# %% [markdown]
# ---
#
# ## Summary
#
# In this tutorial, we demonstrated a complete alignment workflow:
#
# 1. **Image Timeline (DGT1)**: Created from ATON analysis with holes as events
# 2. **Physical C-Maps**: Attached for pixels -> inches/cm conversion
# 3. **Child Timeline (dgt_holes)**: Modeled the musical region as a child
# 4. **Timestamps**: Showed cross-section views through the hierarchy
# 5. **External Data**: Loaded MIDI, audio, and score with specialized loaders
# 6. **TimelineGroup**: Connected all timelines (no root - all peers)
# 7. **Coordinate Transfer**: Demonstrated conversion across the full chain
#
# ### Key Concepts
#
# | Concept | Implementation |
# |---------|----------------|
# | Parent-child hierarchy | `parent.create_child(length, offset)` |
# | Physical unit conversion | `ScalarMap(scalar=1/DPI)` attached to timeline |
# | Timestamps | `timeline.get_timestamps()`, `timeline.get_timestamp(coord)` |
# | TimelineGroup | `TimelineGroup(timelines=[...])` - no root, all peers |
# | Coordinate transfer | `group.convert(coord, source, target)` |
# | ASCII diagrams | `print(timeline)` or `timeline.diagram()` |
#
# ### Timeline Diagram
#
# ```
# DGT1 (Full Image: 0 - 299,400 px)
#   |
#   +-- [15,343 px] -- dgt_holes (Musical Region: 0 - 277,776 px) -- [293,119 px]
#                           |
#                           | TimelineGroup (all peers)
#                           |
#                           +-- dlt1_raw (MIDI raw: ticks)
#                           |
#                           +-- dlt2_exp (MIDI expressive: ticks)
#                           |
#                           +-- dpt1_audio (Audio: 0 to duration-2 seconds)
#                           |
#                           +-- clt1_score (Score: quarterbeats)
#                                 |-- notes (5,577 events)
#                                 |-- measures (222 events)
#                                 |-- harmonies
#                                 +-- chords
# ```

# %% [markdown]
# ## Next Steps
#
# - **09_beat_grids.ipynb**: Work with BeatGrid, FloorMap, and RotationMap
# - **Advanced**: Implement WarpMap for non-linear alignment (expressive timing)
