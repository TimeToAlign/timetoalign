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
# - Transfer coordinates across the entire alignment chain using **Timestamps**
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
from timetoalign.maps import ScalarMap

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
#
# **Note:** We use the `from_file()` constructor for one-line instantiation.

# %%
aton_loader = ATONLoader.from_file(ATON_FILE)

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
# The loader's `create_timeline()` method creates a timeline spanning the full
# image with holes at absolute coordinates.

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
# **Important:** We specify `name=` for human-readable column headers in
# timestamp tables. Without it, columns would show as "map:ScalarMap_1".
#
# **Calculation:** 299,400 pixels / 300.25 DPI = 997.17 inches = 25.33 meters

# %%
LENGTH_DPI = 300.25

# Note: name= provides readable column headers (defaults to "source_to_target")
dgt1.add_conversion_map(
    ScalarMap(
        scalar=1 / LENGTH_DPI,
        source_unit="pixels",
        target_unit="inches",
        name="pixels_to_inches",  # Human-readable name for timestamp columns
    )
)

dgt1.add_conversion_map(
    ScalarMap(
        scalar=2.54 / LENGTH_DPI,
        source_unit="pixels",
        target_unit="cm",
        name="pixels_to_cm",  # Human-readable name for timestamp columns
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

# %%
dgt_holes = dgt1.create_child(
    length=aton_loader.musical_length,
    offset=aton_loader.first_hole,
    uid="dgt_holes",
    name="Musical Holes Region",
)

# ASCII diagram display - no print() needed, no redundant dict
dgt1

# %% [markdown]
# ---
#
# ## Part D: Demonstrate Timestamps
#
# With the parent-child hierarchy established, we can generate **timestamps**
# that show coordinates in both the parent (full image) and child (holes region)
# coordinate systems simultaneously.
#
# **Note:** Columns now show human-readable names like "pixels_to_inches"
# instead of "map:ScalarMap_1", and pixel values are correctly displayed as
# integers.

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
#   with human-readable names like "pixels_to_inches" and "pixels_to_cm"

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
# Note the human-readable column names for C-Maps.

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
#
# **All loaders use the `from_file()` constructor for clean one-line loading.**

# %% [markdown]
# ### E.1: DLT1 - Raw MIDI (one event per hole)

# %%
from timetoalign.loader.midi import PerformanceMidiLoader

# One-line loading with from_file()
midi_raw_loader = PerformanceMidiLoader.from_file(MIDI_RAW_PATH)

# Create timeline directly from loader - no need to access store
dlt1_raw = midi_raw_loader.create_timeline(uid="dlt1_raw")
raw_note_count = len(midi_raw_loader.store.notes)

dlt1_raw

# %%
{
    "DLT1 (MIDI Raw)": dlt1_raw.id,
    "Length": f"{dlt1_raw.length.value:,} ticks",
    "Note events": f"{raw_note_count:,}",
}

# %% [markdown]
# ### E.2: DLT2 - Expressive MIDI (merged notes + dynamics)

# %%
midi_exp_loader = PerformanceMidiLoader.from_file(MIDI_EXP_PATH)
dlt2_exp = midi_exp_loader.create_timeline(uid="dlt2_exp")
exp_note_count = len(midi_exp_loader.store.notes)

dlt2_exp

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
from timetoalign.loader.physical import AudioLoader
from timetoalign.timelines import ContinuousPhysicalTimeline

try:
    audio_loader = AudioLoader.from_file(MP3_PATH)
    dpt1_audio = audio_loader.to_timeline(uid="dpt1_audio")
    audio_duration = audio_loader.duration_seconds
    audio_info = {
        "DPT1 (Audio)": dpt1_audio.id,
        "Sample rate": f"{audio_loader.sample_rate:,} Hz",
        "Duration": f"{audio_duration:.2f} seconds",
    }
except ValueError as e:
    print(f"Note: MP3 loading unavailable ({e}). Using mock timeline.")
    audio_duration = 573.0
    dpt1_audio = ContinuousPhysicalTimeline(
        length=audio_duration,
        unit=TimeUnit.seconds,
        uid="dpt1_audio",
    )
    audio_info = {
        "DPT1 (Audio)": dpt1_audio.id,
        "Duration": f"{audio_duration:.2f} seconds (from README)",
    }

dpt1_audio

# %%
audio_info

# %% [markdown]
# ### E.4: CLT1 - Score Annotations (DCML TSV files)
#
# The DCML corpus provides score data in TSV format. We load **all four files**
# (notes, measures, harmonies, chords) at once using `from_file()` with glob.
#
# **Important:** TimeToAlign! properly loads:
# - `.harmonies.tsv` as **annotations** (Roman numeral analysis)
# - `.chords.tsv` as **control events** (chord symbols)

# %%
from timetoalign.loader.score import TSVLoader

SCORE_BASE = "WWV096-Meistersinger_01_Vorspiel-Prelude_SchottKleinmichel"
score_tsv_files = sorted(DCML_DIR.glob(f"{SCORE_BASE}.*.tsv"))

[f.name for f in score_tsv_files]

# %% [markdown]
# Load all TSV files at once using `from_file()` with `*` unpacking - one line.

# %%
score_loader = TSVLoader.from_file(*score_tsv_files)
score_loader.store.summary()

# %% [markdown]
# Verify against gold standard (ZERO TOLERANCE).

# %%
notes_count = len(score_loader.store.notes)
measures_count = len(score_loader.store.measures)
annotations_count = len(score_loader.store.annotations)  # Harmonies
controls_count = len(score_loader.store.controls)  # Chords

assert notes_count == 5577, f"Notes mismatch: {notes_count} != 5577"
assert measures_count == 222, f"Measures mismatch: {measures_count} != 222"

{
    "Notes": notes_count,
    "Measures": measures_count,
    "Annotations (harmonies)": annotations_count,
    "Controls (chords)": controls_count,
    "Verification": "PASSED",
}

# %% [markdown]
# Create the score timeline using `create_timeline()` directly from the loader.

# %%
clt1_score = score_loader.create_timeline(uid="clt1_score")
clt1_score

# %% [markdown]
# ### E.5: Inspect Harmony Annotations and Chord Controls
#
# - **Harmonies** are loaded as **annotations** (Roman numeral analysis)
# - **Chords** are loaded as **control events** (chord symbols)
#
# Let's examine the harmonies - we'll use a specific label for coordinate transfer!

# %%
# Get harmony annotations (from .harmonies.tsv)
harmonies = score_loader.store.annotations.filter(subtype="Harmony")
harmonies_df = harmonies.to_pandas()[["name", "text", "start", "mc", "mn"]].head(20)
harmonies_df

# %%
# Get chord control events (from .chords.tsv)
chords = score_loader.store.controls.filter(subtype="Chord")
if len(chords) > 0:
    chords_df = chords.to_pandas()[["name", "text", "start", "mc", "mn"]].head(10)
    chords_df
else:
    {"Chord controls": "No chords loaded (file may not exist)"}

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

group

# %%
{"Group": group.name, "Timelines": group.timeline_ids, "Count": group.n_timelines}

# %% [markdown]
# ---
#
# ## Part G: Group Timestamps - The Heart of Alignment
#
# **This is the key feature!** The TimelineGroup maintains a timestamp table
# where each row represents a synchronized point across ALL timelines.
# Coordinate transfer uses these timestamps via interpolation.

# %%
# Get the full timestamp table
group_timestamps = group.get_timestamps_df()
group_timestamps

# %% [markdown]
# Each row shows the **same musical moment** in all coordinate systems:
# - `dgt_holes`: Pixels from first hole
# - `dlt1_raw`: MIDI ticks (raw)
# - `dlt2_exp`: MIDI ticks (expressive)
# - `dpt1_audio`: Seconds
# - `clt1_score`: Quarterbeats

# %% [markdown]
# ---
#
# ## Part H: Coordinate Transfer Using Timestamps
#
# **The right way to transfer coordinates is through timestamps!**
# Instead of manually calling `group.convert()`, we use `get_timestamp_at()`
# which returns a full cross-section through all timelines.

# %% [markdown]
# ### H.1: Transfer a Specific Harmony Label Across All Timelines
#
# Let's take the first occurrence of a I chord (C major) and find its position
# in every timeline.

# %%
# Find the first I chord (tonic) harmony
i_chords = score_loader.store.annotations.filter(text="I")
if len(i_chords) > 0:
    first_i = i_chords.to_pandas().iloc[0]
    i_chord_qb = float(first_i["start"])
    i_chord_label = first_i["text"]
    i_chord_mc = first_i["mc"]
else:
    # Fallback if no I chord
    first_harmony = score_loader.store.annotations.to_pandas().iloc[0]
    i_chord_qb = float(first_harmony["start"])
    i_chord_label = first_harmony["text"]
    i_chord_mc = first_harmony["mc"]

{
    "Harmony label": i_chord_label,
    "Position (quarterbeats)": i_chord_qb,
    "Measure": i_chord_mc,
}

# %% [markdown]
# Now get the timestamp at this position - one call gives us ALL coordinates!

# %%
# Get timestamp at the harmony position in the score timeline
harmony_ts = group.get_timestamp_at(i_chord_qb, "clt1_score")

{
    f"Harmony '{i_chord_label}' at measure {i_chord_mc}": {
        "Score (quarterbeats)": f"{harmony_ts['clt1_score']:.2f}",
        "MIDI raw (ticks)": (
            f"{harmony_ts['dlt1_raw']:,.0f}" if harmony_ts["dlt1_raw"] else "N/A"
        ),
        "MIDI exp (ticks)": (
            f"{harmony_ts['dlt2_exp']:,.0f}" if harmony_ts["dlt2_exp"] else "N/A"
        ),
        "Audio (seconds)": (
            f"{harmony_ts['dpt1_audio']:.2f}" if harmony_ts["dpt1_audio"] else "N/A"
        ),
        "Image holes (pixels)": (
            f"{harmony_ts['dgt_holes']:,.0f}" if harmony_ts["dgt_holes"] else "N/A"
        ),
    }
}

# %% [markdown]
# ### H.2: Convert Back to Full Image Coordinates + Physical Units
#
# The timestamp gives us the position in the holes region. To get the absolute
# image position and physical units, we use the parent timeline's C-Maps.

# %%
if harmony_ts["dgt_holes"] is not None:
    holes_pixels = harmony_ts["dgt_holes"]
    image_pixels = holes_pixels + aton_loader.first_hole.value

    # Use the parent timeline's timestamp with C-Maps
    parent_ts = dgt1.get_timestamp(image_pixels)

    {
        f"Harmony '{i_chord_label}' in full image": {
            "Absolute pixels": f"{image_pixels:,.0f}",
            "Physical (inches)": f"{parent_ts['pixels_to_inches']:.2f}",
            "Physical (cm)": f"{parent_ts['pixels_to_cm']:.2f}",
        }
    }

# %% [markdown]
# ### H.3: Multiple Harmony Labels - Batch Transfer
#
# Let's transfer the first 10 harmony labels to show the power of timestamps.

# %%
# Get first 10 harmonies
first_10_harmonies = (
    score_loader.store.annotations.filter(subtype="Harmony").to_pandas().head(10)
)

transfers = []
for _, harm in first_10_harmonies.iterrows():
    qb = float(harm["start"])
    ts = group.get_timestamp_at(qb, "clt1_score")
    transfers.append(
        {
            "label": harm["text"],
            "mc": harm["mc"],
            "quarterbeats": qb,
            "audio_sec": f"{ts['dpt1_audio']:.2f}" if ts["dpt1_audio"] else "N/A",
            "image_px": f"{ts['dgt_holes']:,.0f}" if ts["dgt_holes"] else "N/A",
        }
    )

import pandas as pd

pd.DataFrame(transfers)

# %% [markdown]
# ---
#
# ## Part I: Comprehensive Group Timestamps Demo
#
# Let's demonstrate all the capabilities of group timestamps.

# %% [markdown]
# ### I.1: Query from Different Timelines
#
# We can query the group from ANY member timeline:

# %%
# Query at 100 seconds in the audio
audio_100s = group.get_timestamp_at(100.0, "dpt1_audio")

{
    "Query: 100 seconds in audio": {
        "dpt1_audio": f"{audio_100s['dpt1_audio']:.2f} sec",
        "dgt_holes": (
            f"{audio_100s['dgt_holes']:,.0f} px" if audio_100s["dgt_holes"] else "N/A"
        ),
        "dlt1_raw": (
            f"{audio_100s['dlt1_raw']:,.0f} ticks" if audio_100s["dlt1_raw"] else "N/A"
        ),
        "clt1_score": (
            f"{audio_100s['clt1_score']:.2f} qb" if audio_100s["clt1_score"] else "N/A"
        ),
    }
}

# %%
# Query at 50,000 pixels in the holes region
holes_50k = group.get_timestamp_at(50000.0, "dgt_holes")

{
    "Query: 50,000 pixels in holes region": {
        "dgt_holes": f"{holes_50k['dgt_holes']:,.0f} px",
        "dpt1_audio": (
            f"{holes_50k['dpt1_audio']:.2f} sec" if holes_50k["dpt1_audio"] else "N/A"
        ),
        "dlt1_raw": (
            f"{holes_50k['dlt1_raw']:,.0f} ticks" if holes_50k["dlt1_raw"] else "N/A"
        ),
        "clt1_score": (
            f"{holes_50k['clt1_score']:.2f} qb" if holes_50k["clt1_score"] else "N/A"
        ),
    }
}

# %% [markdown]
# ### I.2: Boundary Points
#
# Check the alignment at the start and end of the musical content:

# %%
# Start of music (coordinate 0 in dgt_holes)
start_ts = group.get_timestamp_at(0.0, "dgt_holes")

# End of music
end_ts = group.get_timestamp_at(float(aton_loader.musical_length.value), "dgt_holes")

{
    "Start of music": {
        "dgt_holes": f"{start_ts['dgt_holes']:,.0f} px",
        "dpt1_audio": (
            f"{start_ts['dpt1_audio']:.2f} sec" if start_ts["dpt1_audio"] else "N/A"
        ),
        "clt1_score": (
            f"{start_ts['clt1_score']:.2f} qb" if start_ts["clt1_score"] else "N/A"
        ),
    },
    "End of music": {
        "dgt_holes": f"{end_ts['dgt_holes']:,.0f} px",
        "dpt1_audio": (
            f"{end_ts['dpt1_audio']:.2f} sec" if end_ts["dpt1_audio"] else "N/A"
        ),
        "clt1_score": (
            f"{end_ts['clt1_score']:.2f} qb" if end_ts["clt1_score"] else "N/A"
        ),
    },
}

# %% [markdown]
# ### I.3: Round-Trip Verification
#
# Verify that coordinate transfer is reversible (within floating-point precision).

# %%
test_coord = 100000.0  # pixels in holes region

# Transfer to audio and back
ts1 = group.get_timestamp_at(test_coord, "dgt_holes")
audio_coord = ts1["dpt1_audio"]

ts2 = group.get_timestamp_at(audio_coord, "dpt1_audio")
back_to_holes = ts2["dgt_holes"]

# Transfer to score and back
score_coord = ts1["clt1_score"]
ts3 = group.get_timestamp_at(score_coord, "clt1_score")
back_from_score = ts3["dgt_holes"]

{
    "Original (dgt_holes)": f"{test_coord:,.0f} px",
    "Round-trip via audio": {
        "audio_sec": f"{audio_coord:.4f}",
        "back_px": f"{back_to_holes:,.4f}",
        "match": abs(back_to_holes - test_coord) < 0.001,
    },
    "Round-trip via score": {
        "score_qb": f"{score_coord:.4f}",
        "back_px": f"{back_from_score:,.4f}",
        "match": abs(back_from_score - test_coord) < 0.001,
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
# 2. **Physical C-Maps**: Attached with human-readable names (`name=`)
# 3. **Child Timeline (dgt_holes)**: Modeled the musical region as a child
# 4. **Timestamps**: Showed cross-section views through the hierarchy
# 5. **External Data**: Loaded MIDI, audio, and score with harmonies + chords
# 6. **TimelineGroup**: Connected all timelines (no root - all peers)
# 7. **Coordinate Transfer via Timestamps**: The RIGHT way to transfer coordinates!
#
# ### Key Patterns
#
# | Pattern | Usage |
# |---------|-------|
# | One-line loading | `ATONLoader.from_file(path)` |
# | Direct timeline creation | `loader.create_timeline(uid=...)` |
# | Named C-Maps | `ScalarMap(..., name="pixels_to_inches")` |
# | Coordinate transfer | `group.get_timestamp_at(coord, timeline_id)` |
# | Timeline display | Just `timeline` (no `print()` needed) |
#
# ### Timeline Diagram
#
# ```
# DGT1 (Full Image: 0 - 299,400 px)
#   |-- pixels_to_inches (C-Map)
#   |-- pixels_to_cm (C-Map)
#   |
#   +-- [15,343 px] -- dgt_holes (Musical Region: 0 - 277,776 px) -- [293,119 px]
#                           |
#                           | TimelineGroup (all peers)
#                           |
#                           +-- dlt1_raw (MIDI raw: ticks)
#                           |
#                           +-- dlt2_exp (MIDI expressive: ticks)
#                           |
#                           +-- dpt1_audio (Audio: seconds)
#                           |
#                           +-- clt1_score (Score: quarterbeats)
#                                 |-- notes (5,577 events)
#                                 |-- measures (222 events)
#                                 |-- annotations (harmonies from .harmonies.tsv)
#                                 +-- controls (chords from .chords.tsv)
# ```

# %% [markdown]
# ## Next Steps
#
# - **09_beat_grids.ipynb**: Work with BeatGrid, FloorMap, and RotationMap
# - **Advanced**: Implement WarpMap for non-linear alignment (expressive timing)
