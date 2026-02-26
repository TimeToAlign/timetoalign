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
# # How to Build Beat Grids
#
# This tutorial shows how to add beat and measure information to audio tracks
# when you know the tempo and first-beat offset.
#
# **The Common Problem:**
#
# > "I have an audio file. I know the tempo and when the first beat occurs.
# > I want to export the beat times for Audacity."
#
# **The TimeToAlign! Solution:**
#
# ```python
# grid = BeatGrid.from_tempo(tempo_bpm=120, length_seconds=180, start_seconds=0.5)
# grid.export_to_csv("beats.txt", format="sonic_visualiser")  # Done!
# ```
#
# **Learning Objectives:**
#
# 1. Create a BeatGrid from tempo + first-beat offset
# 2. Get all beat/measure times as numpy arrays
# 3. Export to Audacity-compatible CSV
# 4. Query individual time positions for measure/beat
# 5. (Advanced) Create BeatGrids from score measure data
#
# **Prerequisites:**
# - how01_coordinate_math.ipynb (Timelines, Coordinates)
# - No prerequisites for Part 1 (the simple case)

# %% [markdown]
# ## Setup

# %%
import os
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd

from timetoalign import AudioLoader, BeatGrid

# Path to test audio files (relative to notebook directory)
_notebook_dir = Path(".").resolve()
AUDIO_DIR = _notebook_dir.parent.parent / "tests" / "data" / "audio" / "hard_techno"
assert AUDIO_DIR.is_dir(), f"Audio directory not found: {AUDIO_DIR}"

# %% [markdown]
# ---
#
# ## TL;DR: Three Lines to Beatgrid Your Audio
#
# If you already know what you're doing, here's the pattern:

# %%

# Create beatgrid: 120 BPM, 4/4, 3-minute track, first beat at 0.5 seconds
grid = BeatGrid.from_tempo(tempo_bpm=120, length_seconds=180, start_seconds=0.5)

# Get all beat times in seconds (numpy array)
beat_times = grid.beat_seconds()

# Quick look at what we have
{
    "Total beats": len(beat_times),
    "Total measures": grid.n_measures,
    "First 4 beats (seconds)": list(beat_times[:4].round(3)),
    "First 4 measures (seconds)": list(grid.measure_seconds()[:4].round(3)),
}

# %% [markdown]
# ---
#
# ## Part 1: Audio Beatgrids - The Simple Case
#
# You have audio files. You know the tempo and when the first beat occurs.
# You want to generate a complete list of beat and measure times.
#
# ### 1.1 The Use Case
#
# Let's work with three techno tracks that all have:
# - **Tempo**: 160 BPM (constant throughout)
# - **Time Signature**: 4/4
# - **Known first-beat offset** (measured by ear or beat detection)

# %%
# Our test tracks - tempo is constant 160 BPM
TEMPO_BPM = 160.0
BEATS_PER_MEASURE = 4

# Load audio files to get accurate durations
# First-beat offsets are measured by ear or beat detection
TRACK_FILES = {
    "Ao Céu": {"file": "Ao Céu.m4a", "first_beat": 0.092},
    "Bye Bye": {"file": "Bye Bye.m4a", "first_beat": 0.035},
    "Bass Kick": {"file": "Bass Kick.mp3", "first_beat": 0.061},
}

# Create loaders and extract durations from actual audio files
TRACKS = {}
for name, info in TRACK_FILES.items():
    loader = AudioLoader.from_file(AUDIO_DIR / info["file"])
    TRACKS[name] = {
        "loader": loader,
        "duration": loader.duration_seconds,
        "first_beat": info["first_beat"],
    }
    print(f"{name}: {loader.duration_seconds:.3f}s ({loader.format})")

# %% [markdown]
# ### 1.2 Creating the BeatGrid
#
# The `BeatGrid.from_tempo()` factory method does all the work:

# %%
# Create a beatgrid for "Ao Céu"
ao_ceu = TRACKS["Ao Céu"]
grid = BeatGrid.from_tempo(
    tempo_bpm=TEMPO_BPM,
    beats_per_measure=BEATS_PER_MEASURE,
    length_seconds=ao_ceu["duration"],
    start_seconds=ao_ceu["first_beat"],  # When the first beat occurs
)

{
    "Track": "Ao Céu",
    "Duration": f'{ao_ceu["duration"]:.3f} seconds',
    "First beat at": f'{ao_ceu["first_beat"]} seconds',
    "Total measures": grid.n_measures,
    "Total beats": grid.n_beats,
}

# %% [markdown]
# ### 1.3 Getting Beat Times
#
# The `beat_seconds()` method returns a numpy array of ALL beat times.

# %%
# Get all beat times
beats = grid.beat_seconds()

{
    "Array shape": beats.shape,
    "First 8 beats (seconds)": list(beats[:8].round(3)),
    "Last 4 beats (seconds)": list(beats[-4:].round(3)),
}

# %% [markdown]
# ### 1.4 Getting Measure (Downbeat) Times
#
# Use `measure_seconds()` for downbeat times only:

# %%
# Get all measure start times (downbeats)
measures = grid.measure_seconds()

{
    "Total measures": len(measures),
    "First 4 measures (seconds)": list(measures[:4].round(3)),
    "Last 4 measures (seconds)": list(measures[-4:].round(3)),
}

# %% [markdown]
# ### 1.5 Verifying the Math
#
# At 160 BPM:
# - One beat = 60/160 = 0.375 seconds
# - One measure (4 beats) = 1.5 seconds
#
# Let's verify the beat spacing is constant:

# %%
# Check beat intervals
intervals = np.diff(beats)
expected_interval = 60.0 / TEMPO_BPM  # 0.375 seconds

{
    "Expected beat interval": f"{expected_interval} seconds",
    "Actual intervals (first 8)": list(intervals[:8].round(4)),
    "All intervals equal?": np.allclose(intervals, expected_interval),
}

# %% [markdown]
# ---
#
# ## Part 2: Exporting Beat Grids
#
# BeatGrid supports multiple export formats for different annotation tools:
#
# | Format | Tool | Columns |
# |--------|------|---------|
# | `sonic_visualiser` | Sonic Visualiser, Audacity | TIME, LABEL |
# | `tilia` | Tilia | time, measure, beat, is_first_in_measure |
#
# ### 2.1 Export Formats

# %%
# Preview: Sonic Visualiser format (TIME, LABEL)
times = grid.beat_seconds()[:8]
measures = np.repeat(np.arange(1, 3), grid.beats_per_measure)
beats = np.tile(np.arange(1, grid.beats_per_measure + 1), 2)

pd.DataFrame(
    {
        "TIME": np.round(times, 6),
        "LABEL": [f"M{m}B{b}" for m, b in zip(measures, beats)],
    }
)

# %%
# Preview: Tilia format (time, measure, beat, is_first_in_measure)
pd.DataFrame(
    {
        "time": np.round(times, 6),
        "measure": measures,
        "beat": beats,
        "is_first_in_measure": beats == 1,
    }
)

# %% [markdown]
# ### 2.2 Batch Export to Multiple Formats

# %%
# Create outputs directory
os.makedirs("outputs", exist_ok=True)

# Process all three tracks and export to both formats
results = []

for name, info in TRACKS.items():
    grid = BeatGrid.from_tempo(
        tempo_bpm=TEMPO_BPM,
        beats_per_measure=BEATS_PER_MEASURE,
        length_seconds=info["duration"],
        start_seconds=info["first_beat"],
    )

    # Export to both formats
    base_name = name.lower().replace(" ", "_")
    sv_file = f"outputs/{base_name}_beats.csv"
    tilia_file = f"outputs/{base_name}_beats_tilia.csv"

    n_sv = grid.export_to_csv(sv_file, format="sonic_visualiser")
    n_tilia = grid.export_to_csv(tilia_file, format="tilia")

    results.append(
        {
            "Track": name,
            "Measures": grid.n_measures,
            "Beats": n_sv,
            "Sonic Visualiser": sv_file,
            "Tilia": tilia_file,
        }
    )

pd.DataFrame(results)

# %% [markdown]
# ---
#
# ## Part 3: Point Queries
#
# Sometimes you need to ask: "What measure/beat is this time position?"
#
# ### 3.1 Query by Time (Seconds)

# %%
# Create grid for "Ao Céu" using loaded audio duration
ao_ceu = TRACKS["Ao Céu"]
grid = BeatGrid.from_tempo(
    tempo_bpm=TEMPO_BPM,
    beats_per_measure=BEATS_PER_MEASURE,
    length_seconds=ao_ceu["duration"],
    start_seconds=ao_ceu["first_beat"],
)

# Query specific time positions
test_times = [0.092, 1.0, 60.0, 120.0, 200.0]

queries = []
for t in test_times:
    queries.append(
        {
            "Time (s)": t,
            "Measure": grid.measure_at_seconds(t),
            "Beat": grid.beat_at_seconds(t),
        }
    )

pd.DataFrame(queries)

# %% [markdown]
# ### 3.2 Query by Quarter-Note Position
#
# If you're working with MIDI or score data, you may have coordinates in
# quarter notes. BeatGrid handles these directly:

# %%
# Query positions in quarters
test_quarters = [0, 4, 100, 400]

queries = []
for q in test_quarters:
    pos = grid.metrical_position(q)
    queries.append(
        {
            "Quarters": q,
            "Measure (MC)": pos["mc"],
            "Beat": str(pos["beat"]),
            "Label (MN)": pos["mn"],
        }
    )

pd.DataFrame(queries)

# %% [markdown]
# ---
#
# ## Part 4: Different Time Signatures
#
# BeatGrid supports any time signature via `beats_per_measure` and `beat_unit`.
#
# ### 4.1 Waltz (3/4 Time)

# %%
# A waltz at 90 BPM, 5 minutes long
waltz = BeatGrid.from_tempo(
    tempo_bpm=90.0,
    beats_per_measure=3,  # 3 beats per measure
    length_seconds=300.0,
    start_seconds=0.0,
)

{
    "Time signature": "3/4",
    "Tempo": "90 BPM",
    "Duration": "5 minutes",
    "Total measures": waltz.n_measures,
    "Total beats": waltz.n_beats,
    "Seconds per measure": f"{60/90 * 3:.2f}",
}

# %% [markdown]
# ### 4.2 Compound Meter (6/8 Time)
#
# For 6/8, you have 6 eighth-note beats per measure.
# Use `beat_unit=Fraction(1, 8)` to indicate eighth-note beats:

# %%
# 6/8 time at 120 BPM (where the beat is an eighth note)
compound = BeatGrid.from_tempo(
    tempo_bpm=120.0,
    beats_per_measure=6,
    beat_unit=Fraction(1, 8),  # Eighth note = 1 beat
    length_seconds=60.0,
    start_seconds=0.0,
)

{
    "Time signature": "6/8",
    "Beat unit": "eighth note",
    "Quarters per measure": float(compound.quarters_per_measure),
    "Quarters per beat": float(compound.quarters_per_beat),
    "Total measures": compound.n_measures,
    "First 6 beats (seconds)": list(compound.beat_seconds()[:6].round(3)),
}

# %% [markdown]
# ---
#
# ## Part 5: Score-Based Beatgrids (Advanced)
#
# When working with classical music that has complex meter changes, repeats,
# and pickup measures, you need to create BeatGrids from score data rather
# than simple tempo information.
#
# ### 5.1 The Use Case: Beethoven String Quartet
#
# Consider Beethoven's String Quartet Op. 18 No. 4, 4th movement:
# - Has **repeat structures** (needs unfolding for audio alignment)
# - **Pickup measure** (anacrusis)
# - **2/2 time signature** throughout
#
# We have a recording: `StringQuartetEEP_I_Normal_mono.mp3`
#
# The score data is available in TSV format with:
# - Measure coordinates in quarterbeats
# - Flow control information (repeats, voltas)
# - Unfolded versions for performance alignment

# %%
# This is the score data structure we're working with
# (From: tests/data/score/beethoven_op18-4iv_multimodal/ABC/)

BEETHOVEN_MEASURES = """
mc	mn	quarterbeats	duration_qb	timesig	repeats
1	0	0	1.0	2/2	start
2	1	1	4.0	2/2
...
9	8	29	3.0	2/2	end
10	8	32	1.0	2/2	start
...
"""

# The unfolded version has ~291 measures (with repeats expanded)
UNFOLDED_TOTAL_QUARTERS = 1116
UNFOLDED_MEASURES = 291

# %% [markdown]
# ### 5.2 Creating BeatGrid from Score (API Draft)
#
# **Note**: This API is a draft for future implementation. The pattern shows
# how TimeToAlign! will support creating BeatGrids from rich score metadata.

# %%
# API DRAFT: Creating BeatGrid from score measures
#
# This functionality is planned for the Score Integration milestone.
# The code below shows the intended API design.

# --- FUTURE API ---
#
# from timetoalign.loader import MeasureMapLoader
#
# # Load measure map from score TSV
# loader = MeasureMapLoader.from_file(
#     "tests/data/score/beethoven_op18-4iv_multimodal/ABC/n04op18-4_04_flow_unfolded.measures.tsv"
# )
#
# # Create BeatGrid with the actual meter structure
# grid = loader.create_beatgrid(
#     tempo_bpm=120.0,  # Performance tempo (from audio analysis or metadata)
#     start_seconds=0.5,  # First beat offset
# )
#
# # The grid now has the exact measure structure from the score
# # Including partial measures, meter changes, etc.
# grid.n_measures  # -> 291 (unfolded)
# grid.n_beats     # -> based on actual time signatures
#
# # Export to Audacity with score measure labels
# beatgrid_to_audacity_csv(grid, "beethoven_op18-4iv_beats.txt")
# --- END FUTURE API ---

# For now, we can approximate with uniform measures
approx_grid = BeatGrid.from_tempo(
    tempo_bpm=120.0,  # Assumed tempo
    beats_per_measure=4,  # 2/2 = 4 quarter beats per measure
    length_seconds=540.0,  # ~9 minutes (estimated)
    start_seconds=0.5,
    name="Beethoven Op.18/4-iv (approximate)",
)

{
    "Track": "StringQuartetEEP_I_Normal_mono.mp3",
    "Approximate measures": approx_grid.n_measures,
    "Approximate beats": approx_grid.n_beats,
    "Note": "Use MeasureMapLoader for exact score structure",
}

# %% [markdown]
# ### 5.3 Why Score-Based BeatGrids Matter
#
# For simple steady-tempo music, `BeatGrid.from_tempo()` works perfectly.
# But classical music often has:
#
# | Feature | Simple BeatGrid | Score-Based BeatGrid |
# |---------|-----------------|----------------------|
# | Constant tempo | Yes | Yes |
# | Tempo changes | No | Yes (via tempo track) |
# | Repeats/Voltas | No | Yes (unfolded) |
# | Anacrusis | Limited | Full support |
# | Measure labels | M1, M2... | 0, 1a, 1b, 2... |
# | Time sig changes | No | Yes |
#
# The Score-Based approach gives you **ground truth** measure structure from
# the score, ensuring your beat markers match what musicians see on the page.

# %% [markdown]
# ---
#
# ## Summary
#
# > "BeatGrid.from_tempo() generates beat and measure times for audio with
# > known tempo and first-beat offset. Export to Audacity with one line."
#
# **Key API:**
#
# | Method | Returns | Use Case |
# |--------|---------|----------|
# | `BeatGrid.from_tempo()` | BeatGrid | Create from tempo + offset |
# | `.beat_seconds()` | numpy array | All beat times |
# | `.measure_seconds()` | numpy array | All measure/downbeat times |
# | `.n_beats` | int | Total beat count |
# | `.n_measures` | int | Total measure count |
# | `.measure_at_seconds(t)` | int | Measure number at time t |
# | `.beat_at_seconds(t)` | int | Beat-in-measure at time t |
# | `.export_to_csv()` | int | Export to Audacity/Sonic Visualiser |
#
# **Common Patterns:**
#
# ```python
# # Pattern 1: Simple audio beatgrid
# grid = BeatGrid.from_tempo(tempo_bpm=120, length_seconds=180, start_seconds=0.5)
# beats = grid.beat_seconds()
#
# # Pattern 2: Export to Audacity (one line!)
# grid.export_to_csv("beats.txt", format="sonic_visualiser")
#
# # Pattern 3: Different time signatures
# grid_3_4 = BeatGrid.from_tempo(tempo_bpm=90, beats_per_measure=3, ...)
# grid_6_8 = BeatGrid.from_tempo(tempo_bpm=120, beats_per_measure=6,
#                                 beat_unit=Fraction(1, 8), ...)
# ```

# %% [markdown]
# ---
#
# ## Exercises
#
# ### Exercise 1: Your Own Track
#
# Pick an audio track you know the tempo of. Create a BeatGrid and export
# the first 32 beats to an Audacity-compatible format.

# %%
# Your solution here:
# my_grid = BeatGrid.from_tempo(
#     tempo_bpm=...,
#     length_seconds=...,
#     start_seconds=...,
# )
# ...

# %% [markdown]
# ### Exercise 2: Tempo Change Workaround
#
# For a track that changes tempo at 60 seconds (from 120 to 140 BPM),
# create two BeatGrids and concatenate their beat arrays.
#
# Hint: Use `np.concatenate()` on the beat_seconds() arrays.

# %%
# Your solution here:
# grid1 = BeatGrid.from_tempo(tempo_bpm=120, length_seconds=60, start_seconds=0)
# grid2 = BeatGrid.from_tempo(tempo_bpm=140, length_seconds=120, start_seconds=60)
# all_beats = np.concatenate([grid1.beat_seconds(), grid2.beat_seconds()])
# ...

# %% [markdown]
# ### Exercise 3: Custom Labels
#
# Use `grid.beat_seconds()` and `grid.measure_at_seconds()` to create a
# custom export with time signature in the labels (e.g., "M1 (4/4)").

# %%
# Your solution here:
# times = grid.measure_seconds()
# labels = [f"M{i} (4/4)" for i in range(1, len(times) + 1)]
# ...

# %% [markdown]
# ---
#
# ## Next Steps
#
# - **Tutorial 07**: TimelineGroups - Connect beatgrids to other timelines
# - **Tutorial 08**: SUPRA Piano Roll - See beatgrids in a complete alignment workflow
# - **Score Integration**: MeasureMapLoader for complex scores
