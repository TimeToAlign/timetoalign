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
# - Create a graphical timeline from IIIF image metadata
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
from timetoalign.loader.graphical.iiif import IIIFManifestLoader
from timetoalign.maps import ScalarMap
from timetoalign.timelines import Timeline

# Data directory - relative to notebook location
_notebook_dir = Path(".").resolve()
DATA_DIR = _notebook_dir.parent.parent / "tests" / "data" / "supra"
assert DATA_DIR.is_dir(), f"SUPRA data directory not found: {DATA_DIR}"

# File paths
IIIF_MANIFEST = DATA_DIR / "image" / "ifff_manifest.json"
ATON_FILE = DATA_DIR / "image" / "fd660zf8362_analysis.txt"
MIDI_RAW_PATH = DATA_DIR / "midi" / "fd660zf8362_raw.mid"
MIDI_EXP_PATH = DATA_DIR / "midi" / "fd660zf8362_exp.mid"
MP3_PATH = DATA_DIR / "midi" / "fd660zf8362.mp3"
DCML_DIR = DATA_DIR / "dcml"

{
    "Data directory": str(DATA_DIR),
    "IIIF manifest": IIIF_MANIFEST.name,
    "ATON file": ATON_FILE.name,
}

# %% [markdown]
# ---
#
# ## Part A: Create the Image Timeline (DGT1)
#
# We start by loading the IIIF manifest to get the image dimensions. The IIIF
# (International Image Interoperability Framework) standard provides structured
# metadata about images without requiring the actual image files.

# %%
# Load the IIIF manifest
iiif_loader = IIIFManifestLoader()
iiif_loader.load(IIIF_MANIFEST)

# Verify against gold standard (ZERO TOLERANCE)
assert iiif_loader.width == 4096, f"Width mismatch: {iiif_loader.width} != 4096"
assert iiif_loader.height == 299400, f"Height mismatch: {iiif_loader.height} != 299400"

{
    "Image width": f"{iiif_loader.width:,} pixels",
    "Image height": f"{iiif_loader.height:,} pixels",
    "Verification": "PASSED",
}

# %%
# Create the image timeline using the loader's convenience method
# The loader knows the dimensions and can extract a name from the manifest
dgt1_image = iiif_loader.create_timeline(
    uid="dgt1_image",
    name="Piano Roll Image (WM 990)",
)

{
    "Timeline": dgt1_image.id,
    "Length": f"{dgt1_image.length.value:,} pixels",
    "Unit": str(dgt1_image.unit),
    "Manifest label": iiif_loader.name,
}

# %% [markdown]
# ---
#
# ## Part B: Add Physical Unit C-Maps
#
# The piano roll was scanned at 300.25 DPI (dots per inch). We can attach
# ConversionMaps to convert pixel coordinates to physical units (inches and
# centimeters).
#
# **Calculation:**
# - 299,400 pixels / 300.25 DPI = 997.17 inches = 25.33 meters

# %%
# Physical conversion constants
LENGTH_DPI = 300.25  # pixels per inch (from ATON analysis)

# Create C-Maps for physical units
pixels_to_inches = ScalarMap(
    scalar=1 / LENGTH_DPI,
    source_unit="pixels",
    target_unit="inches",
)

pixels_to_cm = ScalarMap(
    scalar=2.54 / LENGTH_DPI,  # 2.54 cm per inch
    source_unit="pixels",
    target_unit="cm",
)

# Attach to the image timeline
dgt1_image.add_conversion_map(pixels_to_inches)
dgt1_image.add_conversion_map(pixels_to_cm)

# Demonstrate conversions
image_length_px = dgt1_image.length.value
image_length_inches = dgt1_image.convert_to(image_length_px, "inches")
image_length_cm = dgt1_image.convert_to(image_length_px, "cm")

{
    "Image length (pixels)": f"{image_length_px:,}",
    "Image length (inches)": f"{image_length_inches:.2f}",
    "Image length (cm)": f"{image_length_cm:.2f}",
    "Image length (meters)": f"{image_length_cm / 100:.2f}",
}

# %% [markdown]
# ---
#
# ## Part C: Create Holes Region as Child Timeline
#
# The musical content doesn't span the entire image. The actual hole punches
# start at pixel 15,343 and end at pixel 293,119. We model this as a **child
# timeline** of the image.
#
# **Key insight:** Instead of creating a separate timeline and aligning it
# later, we use the parent-child relationship to establish the offset directly.

# %%
# Load ATON analysis file for hole punch data
aton_loader = ATONLoader()
aton_loader.load(ATON_FILE)

# Verify against gold standard (ZERO TOLERANCE)
assert aton_loader.musical_holes == 30092
assert aton_loader.musical_notes == 8718
assert aton_loader.first_hole == 15343
assert aton_loader.last_hole == 293119
assert aton_loader.musical_length == 277776

{
    "Musical holes": f"{aton_loader.musical_holes:,}",
    "Musical notes (merged)": f"{aton_loader.musical_notes:,}",
    "First hole (pixel)": f"{aton_loader.first_hole:,}",
    "Last hole (pixel)": f"{aton_loader.last_hole:,}",
    "Musical length": f"{aton_loader.musical_length:,} pixels",
    "Verification": "PASSED",
}

# %%
# Create the holes region as a CHILD timeline using the parent's convenience method
# This creates the child AND embeds it in one step - no separate add_child() needed
dgt1_holes = dgt1_image.create_child(
    length=aton_loader.musical_length,  # 277776 pixels
    offset=aton_loader.first_hole,  # Start at pixel 15,343 in parent
    uid="dgt1_holes",
    name="Musical Holes Region",
)

# Now add hole events to the child timeline
# Coordinates are RELATIVE to the child's origin (0 = first hole)
hole_events = [
    {
        "id": f"hole_{hole.id}",
        "temporal_type": "instant",
        "event_type": "Hole",
        "instant": hole.origin_row - aton_loader.first_hole,  # Relative coordinate
    }
    for hole in aton_loader.holes
]
dgt1_holes.add_events(hole_events)

{
    "Child timeline": dgt1_holes.id,
    "Child length": f"{dgt1_holes.length.value:,} pixels",
    "Offset in parent": f"{aton_loader.first_hole:,} pixels",
    "Events (holes)": f"{dgt1_holes.n_events:,}",
    "Parent children": dgt1_image.n_children,
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
# Get timestamp table showing parent and child coordinates, PLUS all attached C-Maps
# Using conversion_maps=True includes the pixels->inches and pixels->cm conversions
timestamps_df = dgt1_image.get_timestamps(conversion_maps=True)

{
    "Total timestamps": len(timestamps_df),
    "Columns": list(timestamps_df.columns),
}

# %% [markdown]
# **Why 20,680 timestamps?**
#
# The timestamp table has one row per **unique** event coordinate in the hierarchy:
# - Child timeline (dgt1_holes) contains 30,092 hole events
# - But many holes share the same pixel row (multiple notes at one time position)
# - After de-duplication: ~20,676 unique coordinates plus 4 boundary coordinates
#
# Each row shows the coordinate in all coordinate systems simultaneously:
# - `axis`: The root (parent) coordinate in pixels
# - `dgt1_image`: Same as axis (this IS the root timeline)
# - `dgt1_holes`: Local coordinate in child timeline (NaN if outside child's bounds)
# - C-Map columns: Physical units (inches, cm) computed via attached ScalarMaps

# %%
# Show first few timestamps - note the C-Map columns show physical positions
# The 'axis' column is the parent coordinate
# The 'dgt1_holes' column is the child's local coordinate (or NaN if outside)
timestamps_df.head(10)

# %%
# Query a specific coordinate
# At pixel 100,000 in the image, what's the local coordinate in the holes region?
ts = dgt1_image.get_timestamp(100000.0)

{
    "Query (parent coord)": 100000.0,
    "Child coord (dgt1_holes)": ts["dgt1_holes"],  # 100000 - 15343 = 84657
    "Calculation": f"100000 - {aton_loader.first_hole} = {100000 - aton_loader.first_hole}",
}

# %%
# Boundary table shows where child timelines start and end (with C-Maps)
boundary_df = dgt1_image.get_boundary_table(conversion_maps=True).to_pandas()
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
from timetoalign.loader.midi import PerformanceMidiLoader  # noqa: E402

# Load raw MIDI
midi_raw_loader = PerformanceMidiLoader()
midi_raw_loader.load(MIDI_RAW_PATH)

# Create timeline from the store's notes
dlt1_raw = midi_raw_loader.store.notes.create_timeline(uid="dlt1_raw")

# Note count: Raw MIDI has one event per hole punch (30,092)
raw_note_count = len(midi_raw_loader.store.notes)

{
    "DLT1 (MIDI Raw)": dlt1_raw.id,
    "Length": f"{dlt1_raw.length.value:,} ticks",
    "Note events": f"{raw_note_count:,}",
    "Note": "One MIDI event per hole punch (matches MUSICAL_HOLES)",
}

# %% [markdown]
# ### E.2: DLT2 - Expressive MIDI (merged notes + dynamics)

# %%
# Load expressive MIDI
midi_exp_loader = PerformanceMidiLoader()
midi_exp_loader.load(MIDI_EXP_PATH)

# Create timeline from the store's notes
dlt2_exp = midi_exp_loader.store.notes.create_timeline(uid="dlt2_exp")

exp_note_count = len(midi_exp_loader.store.notes)

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
from timetoalign.loader.physical import AudioLoader  # noqa: E402
from timetoalign.timelines import ContinuousPhysicalTimeline  # noqa: E402

# Try to load MP3 metadata
try:
    audio_loader = AudioLoader()
    audio_loader.load(MP3_PATH)
    dpt1_audio = audio_loader.to_timeline(uid="dpt1_audio")
    audio_duration = audio_loader.duration_seconds
    audio_info = {
        "DPT1 (Audio)": dpt1_audio.id,
        "Sample rate": f"{audio_loader.sample_rate:,} Hz",
        "Duration": f"{audio_duration:.2f} seconds",
        "Samples": f"{audio_loader.n_samples:,}",
        "Musical duration": f"{audio_duration - 2:.2f} seconds (excluding 2s silence)",
    }
except ValueError as e:
    # MP3 loading not available - use known duration from README
    # The audio is approximately 573 seconds (from expressive MIDI synthesis)
    print(f"Note: MP3 loading unavailable ({e}). Using mock timeline.")
    audio_duration = 573.0  # Known approximate duration
    dpt1_audio = ContinuousPhysicalTimeline(
        length=audio_duration,
        unit=TimeUnit.seconds,
        uid="dpt1_audio",
    )
    audio_info = {
        "DPT1 (Audio)": dpt1_audio.id,
        "Duration": f"{audio_duration:.2f} seconds (from README)",
        "Note": "MP3 loading requires mutagen or soundfile",
    }

audio_info

# %% [markdown]
# ### E.4: CLT1 - Score Annotations (DCML TSV files)
#
# The DCML corpus provides score data in TSV format. We load notes, measures,
# harmonies, and chords.

# %%
from timetoalign.loader.score import TSVLoader  # noqa: E402

# Define file paths
SCORE_BASE = "WWV096-Meistersinger_01_Vorspiel-Prelude_SchottKleinmichel"

# Load notes
notes_path = DCML_DIR / f"{SCORE_BASE}.notes.tsv"
notes_loader = TSVLoader()
notes_loader.load(notes_path)

# Load measures (separate file)
measures_path = DCML_DIR / f"{SCORE_BASE}.measures.tsv"
measures_loader = TSVLoader()
measures_loader.load(measures_path)

# Get counts using len()
notes_count = len(notes_loader.store.notes)
measures_count = len(measures_loader.store.measures)

# Verify against gold standard (ZERO TOLERANCE)
assert notes_count == 5577, f"Notes mismatch: {notes_count} != 5577"
assert measures_count == 222, f"Measures mismatch: {measures_count} != 222"

{
    "Notes": f"{notes_count:,}",
    "Measures": f"{measures_count:,}",
    "Verification": "PASSED",
}

# %%
# Create score timeline from notes
# Note: We use create_timeline() which determines length from event coordinates
clt1_score = notes_loader.store.notes.create_timeline(uid="clt1_score")

{
    "CLT1 (Score)": clt1_score.id,
    "Length": f"{clt1_score.length.value} quarterbeats",
    "Events": f"{clt1_score.n_events:,}",
}

# %% [markdown]
# ---
#
# ## Part F: Create the TimelineGroup
#
# Now we bring everything together in a **TimelineGroup**. This establishes
# commensurability between all timelines, enabling coordinate transfer.
#
# **Alignment structure:**
# ```
# DGT1_holes (pixels)  <-- root of the group
#     |
#     +-- DLT1_raw (MIDI ticks)
#     |       |
#     |       +-- DLT2_exp (MIDI ticks, same tick space)
#     |
#     +-- DPT1_audio (seconds, 0 to duration-2)
#     |
#     +-- CLT1_score (quarterbeats)
# ```

# %%
# Create the TimelineGroup with the holes region as the starting point
group = TimelineGroup(
    id="supra_alignment",
    name="SUPRA Piano Roll Alignment",
    timelines=[dgt1_holes],
)

# Add MIDI-raw (aligned to holes via linear full-extent mapping)
group.add_timeline(dlt1_raw)

# Add MIDI-expressive (same tick space as raw)
group.add_timeline(dlt2_exp)

# Add Audio timeline
# Note: The MP3 has ~2 seconds of trailing silence. In a production workflow,
# you would create the audio timeline with (duration - 2) seconds, or use
# partial alignment anchors. For this tutorial, we use full extent.
group.add_timeline(dpt1_audio)

# Add Score timeline
group.add_timeline(clt1_score)

{
    "Group": group.name,
    "Timelines": group.timeline_ids,
    "Count": group.n_timelines,
}

# %%
# View the timestamp table showing alignment boundaries
group.get_timestamps_df()

# %% [markdown]
# ---
#
# ## Part G: Coordinate Transfer
#
# With all timelines in the group, we can transfer coordinates between any pair.
# The group handles the conversion chain automatically.

# %%
# Example: Transfer from holes region to all other timelines
holes_midpoint = aton_loader.musical_length / 2  # 138888 pixels

{
    "Query coordinate": f"{holes_midpoint:,.0f} pixels (holes midpoint)",
    "-> MIDI raw": f"{group.convert(holes_midpoint, 'dgt1_holes', 'dlt1_raw'):,.0f} ticks",
    "-> MIDI exp": f"{group.convert(holes_midpoint, 'dgt1_holes', 'dlt2_exp'):,.0f} ticks",
    "-> Audio": f"{group.convert(holes_midpoint, 'dgt1_holes', 'dpt1_audio'):.2f} seconds",
    "-> Score": f"{group.convert(holes_midpoint, 'dgt1_holes', 'clt1_score'):.2f} quarterbeats",
}

# %%
# Example: Transfer from score to image
# Measure 50 starts at quarterbeat 196 (measures 1-49 = 49*4 = 196, assuming 4/4)
score_coord = 196.0  # Quarterbeat at start of measure 50

midi_ticks = group.convert(score_coord, "clt1_score", "dlt1_raw")
holes_pixels = group.convert(score_coord, "clt1_score", "dgt1_holes")
audio_seconds = group.convert(score_coord, "clt1_score", "dpt1_audio")

# Convert holes pixels to parent image coordinates
image_pixels = holes_pixels + aton_loader.first_hole

# Convert to physical units using the C-Map we attached earlier
image_inches = dgt1_image.convert_to(image_pixels, "inches")
image_cm = dgt1_image.convert_to(image_pixels, "cm")

{
    "Score coord": f"{score_coord} quarterbeats (measure 50)",
    "-> MIDI ticks": f"{midi_ticks:,.0f}",
    "-> Holes region": f"{holes_pixels:,.0f} pixels",
    "-> Full image": f"{image_pixels:,.0f} pixels",
    "-> Physical": f"{image_inches:.2f} inches ({image_cm:.2f} cm)",
    "-> Audio": f"{audio_seconds:.2f} seconds",
}

# %% [markdown]
# ---
#
# ## Part H: Verification
#
# Let's verify some key alignment properties.

# %%
# Verify boundary transfers (ZERO TOLERANCE for boundary values)

# Start of holes region (0) should map to start of other timelines
holes_start = 0.0
midi_start = group.convert(holes_start, "dgt1_holes", "dlt1_raw")
audio_start = group.convert(holes_start, "dgt1_holes", "dpt1_audio")
score_start = group.convert(holes_start, "dgt1_holes", "clt1_score")

# End of holes region should map to end of other timelines
holes_end = float(aton_loader.musical_length)
midi_end = group.convert(holes_end, "dgt1_holes", "dlt1_raw")
audio_end = group.convert(holes_end, "dgt1_holes", "dpt1_audio")
score_end = group.convert(holes_end, "dgt1_holes", "clt1_score")

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

# %%
# Verify round-trip conversion (should return to original value)
test_coord = 100000.0

# holes -> midi -> holes
to_midi = group.convert(test_coord, "dgt1_holes", "dlt1_raw")
back_to_holes = group.convert(to_midi, "dlt1_raw", "dgt1_holes")

# holes -> audio -> holes
to_audio = group.convert(test_coord, "dgt1_holes", "dpt1_audio")
back_from_audio = group.convert(to_audio, "dpt1_audio", "dgt1_holes")

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
# 1. **Image Timeline (DGT1)**: Created from IIIF manifest dimensions
# 2. **Physical C-Maps**: Attached for pixels -> inches/cm conversion
# 3. **Child Timeline (DGT1_holes)**: Modeled the musical region as a child
# 4. **Timestamps**: Showed cross-section views through the hierarchy
# 5. **External Data**: Loaded MIDI, audio, and score with specialized loaders
# 6. **TimelineGroup**: Connected all timelines for coordinate transfer
# 7. **Coordinate Transfer**: Demonstrated conversion across the full chain
#
# ### Key Concepts
#
# | Concept | Implementation |
# |---------|----------------|
# | Parent-child hierarchy | `parent.add_child(child, offset=N)` |
# | Physical unit conversion | `ScalarMap(scalar=1/DPI)` attached to timeline |
# | Timestamps | `timeline.get_timestamps()`, `timeline.get_timestamp(coord)` |
# | TimelineGroup | `group.add_timeline()` with optional `start`/`end` for partial alignment |
# | Coordinate transfer | `group.convert(coord, source, target)` |
#
# ### Timeline Diagram
#
# ```
# DGT1 (Full Image: 0 - 299,400 px)
#   |
#   +-- [15,343 px] -- DGT1_holes (Musical Region: 0 - 277,776 px) -- [293,119 px]
#                           |
#                           | TimelineGroup
#                           |
#                           +-- DLT1_raw (MIDI raw: ticks)
#                           |
#                           +-- DLT2_exp (MIDI expressive: ticks)
#                           |
#                           +-- DPT1_audio (Audio: 0 to duration-2 seconds)
#                           |
#                           +-- CLT1_score (Score: quarterbeats)
# ```
#
# > "TimelineGroup establishes commensurability between heterogeneous timelines,
# > enabling seamless coordinate transfer across domains: graphical (pixels),
# > logical (ticks, quarterbeats), and physical (seconds)."

# %% [markdown]
# ## Next Steps
#
# - **09_beat_grids.ipynb**: Work with BeatGrid, FloorMap, and RotationMap
# - **Advanced**: Implement WarpMap for non-linear alignment (expressive timing)
