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
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # 07: Alignment Basics
#
# This tutorial introduces alignment - the core capability that connects
# timelines and enables coordinate transfer between them.
#
# **Learning Objectives:**
# - Understand alignment as establishing commensurability between timelines
# - Use `TimelineGroup` to manage commensurable timelines
# - Define alignments with `start`/`end` parameters (partial alignment)
# - Transfer coordinates between timelines in a group
#
# **Prerequisites:**
# - Notebooks 01-06 (Core Concepts, Loaders, C-Maps, Timelines, Timestamps, Graphical Timelines)
# - Understanding of Timeline objects and Coordinate types
#
# **Note (Phase 7.4):** The `PerfectAlignment` class is deprecated. This
# tutorial uses the new timestamp-based TimelineGroup API with `start`/`end`
# parameters for partial alignment.

# %% [markdown]
# ## Part 1: What is Alignment?
#
# In previous tutorials, we learned:
# - **Timestamps** (Notebook 05): Cross-section views through timeline
#   hierarchies - they tell us WHERE events are
# - **Graphical Timelines** (Notebook 06): Mapping images to timelines
#
# But timestamps are **read-only**. They don't let us convert coordinates from
# one timeline to another.
#
# **Alignment** establishes **commensurability** between timelines - the
# ability to convert coordinates from one to another:
# > "If I'm at coordinate X in Timeline A, what's the corresponding coordinate in Timeline B?"
#
# ### Use Cases
# - **Score-Audio Sync**: "At measure 5 in the score, what's the timestamp in the audio?"
# - **Cross-Version Comparison**: "This pixel in Analysis A corresponds to
#   which pixel in Analysis B?"
# - **OMR Linking**: "This note in the scanned image maps to which MIDI event?"

# %% [markdown]
# ## Part 2: Commensurability
#
# Two timelines are **commensurable** if there exists a way to convert coordinates between them.
#
# In TimeToAlign!, commensurability is established by placing timelines in a
# **TimelineGroup**. Any timeline in the group can be converted to any other
# via linear interpolation.
#
# ```
# Timeline A  <-->  Timeline B  <-->  Timeline C
#    (MIDI)          (pixels)          (audio)
# ```
#
# ### Timestamp Table Architecture
#
# A `TimelineGroup` stores alignment as a **timestamp table** where each row is a boundary instant:
#
# ```
# | image    | holes    | midi     |
# |----------|----------|----------|
# | 0.0      | null     | null     |  <- group start (image only)
# | 15343.0  | 0.0      | 0.0      |  <- musical region starts
# | 293119.0 | 277776.0 | 871800.0 |  <- musical region ends
# | 299400.0 | null     | null     |  <- group end (image only)
# ```
#
# Between any two adjacent rows, ALL non-null timelines have a bijective linear mapping.

# %% [markdown]
# ## Setup
#
# import importlib.util

# %%
import importlib.util
from pathlib import Path

from timetoalign.alignment import AlignmentBundle, TimelineGroup
from timetoalign.timelines import (
    ContinuousPhysicalTimeline,
    Timeline,
)

# Check for optional graphical loader dependency (pymupdf)
_HAS_PYMUPDF = importlib.util.find_spec("pymupdf") is not None
if _HAS_PYMUPDF:
    from timetoalign.loader.graphical import GraphicalLoader
else:
    print("Note: pymupdf not installed. Graphical loader examples will use mock data.")
    print("Install with: pip install pymupdf")

# %% [markdown]
# ## Part 3: TimelineGroup
#
# A `TimelineGroup` is a collection of **commensurable timelines** - timelines
# that can be converted to each other through linear interpolation.
#
# ### Creating a Group with Timelines

# %%
# Create an image timeline (e.g., a piano roll image)
image_timeline = Timeline(
    length=10000,  # 10,000 pixels tall
    uid="image",
    name="Piano Roll Image",
)

# Create a group with this timeline
group = TimelineGroup(
    id="piano_roll_group", name="Piano Roll Group", timelines=[image_timeline]
)

{
    "group_id": group.id,
    "name": group.name,
    "n_timelines": group.n_timelines,
    "timeline_ids": group.timeline_ids,
}

# %% [markdown]
# ### Adding Timelines to the Group
#
# When you add a timeline to the group, it's aligned to the group's existing
# extent by default (linear full-extent).

# %%
# Create an audio timeline
audio_timeline = ContinuousPhysicalTimeline(
    length=300.0,  # 5 minutes = 300 seconds
    unit="seconds",
    uid="audio",
    name="Audio Recording",
)

# Add to group - by default, maps [0, 300] seconds to [0, 10000] pixels
group.add_timeline(audio_timeline)

{
    "n_timelines": group.n_timelines,
    "timeline_ids": group.timeline_ids,
}

# %% [markdown]
# ### Partial Alignment with start/end Parameters
#
# Timelines don't have to cover the full extent. Use `start` and `end`
# parameters to specify the exact mapping:

# %%
# Create a MIDI timeline
midi_timeline = Timeline(
    length=87180,  # MIDI ticks
    uid="midi",
    name="MIDI File",
)

# The MIDI only covers the middle portion of the image
# MIDI ticks [0, 87180] map to image pixels [1000, 9000]
group.add_timeline(
    midi_timeline,
    start=(1000.0, "image"),  # MIDI starts at image pixel 1000
    end=(9000.0, "image"),  # MIDI ends at image pixel 9000
)

group.n_timelines

# %% [markdown]
# ### Viewing the Timestamp Table
#
# The group's internal timestamp table shows the alignment boundaries:

# %%
# View the timestamp table as a DataFrame
group.get_timestamps_df()

# %% [markdown]
# ### Coordinate Transfer
#
# Now that all three timelines are commensurable (in the same group), we can
# convert between any pair:

# %%
# Transfer from audio seconds to image pixels
audio_coord = 150.0  # 2.5 minutes
pixel_coord = group.convert(audio_coord, source="audio", target="image")

print(f"Audio: {audio_coord} seconds -> Image: {pixel_coord:.1f} pixels")

# Transfer from MIDI ticks to audio seconds
midi_coord = 43590  # Halfway through the MIDI
audio_from_midi = group.convert(midi_coord, source="midi", target="audio")

print(f"MIDI: {midi_coord} ticks -> Audio: {audio_from_midi:.2f} seconds")

# %% [markdown]
# ### How Conversion Works
#
# All conversions use linear interpolation within the timestamp table:
#
# 1. Find the bounding rows for the source coordinate
# 2. Compute the interpolation ratio
# 3. Apply the same ratio to get the target coordinate
#
# ```
# MIDI 43590 (source)  -->  Interpolate  -->  Audio 150.0 (target)
#      (ratio: 0.5 through MIDI range)        (ratio: 0.5 through Audio range within MIDI extent)
# ```

# %% [markdown]
# ---
#
# ## Part 4: Real-World Example - Thoresen Cross-Version Analysis
#
# Let's apply these concepts to real data: two different graphical analyses of the same music.
#
# ### The Data
# - **DGT1 (2009)**: Single image with 5 horizontal systems (4835 pixels total)
# - **DGT2 (2010)**: 5 separate images (4328 pixels total)
# - Both represent the same **150-second audio excerpt**
#
# We want to make coordinates transferable between DGT1 and DGT2. Since both
# analyses represent the same audio, we can establish commensurability through
# a shared audio timeline.

# %%
# Path to test data - relative to notebook location
_notebook_dir = Path(__file__).resolve().parent
data_dir = _notebook_dir.parent.parent / "tests" / "alignment" / "data" / "thoresen"

# Constants for the Thoresen example
DGT1_X0, DGT1_X1 = 2, 969
DGT1_Y_POSITIONS = [18, 205, 396, 588, 785]
DGT2_SEGMENT_BOUNDS = [
    (8, 874, 15),
    (7, 874, 18),
    (7, 874, 19),
    (8, 872, 15),
    (9, 873, 20),
]
AUDIO_DURATION = 150.0

# This example requires pymupdf for image loading
if _HAS_PYMUPDF:
    # DGT1: Single image with 5 systems
    dgt1_image = data_dir / "thoresen_2009_sound-objects_p312_page1_1.jpeg"

    # Load DGT1
    loader1 = GraphicalLoader(metadata={"source": "Thoresen 2009"})
    idx1 = loader1.add_image(dgt1_image)

    for i, y in enumerate(DGT1_Y_POSITIONS):
        loader1.add_horizontal_segment(
            source_index=idx1,
            x0=DGT1_X0,
            x1=DGT1_X1,
            y=y,
            name=f"system_{i+1}",
        )

    dgt1_bundle = loader1.bundle
    print(
        f"DGT1: {dgt1_bundle.n_segments} segments, {dgt1_bundle.total_length:.0f} pixels"
    )

    # DGT2: 5 separate images
    dgt2_images = [
        data_dir / "thoresen_2010_form-building-patterns_p90-91_page1_1.jpeg",
        data_dir / "thoresen_2010_form-building-patterns_p90-91_page1_2.jpeg",
        data_dir / "thoresen_2010_form-building-patterns_p90-91_page1_3.jpeg",
        data_dir / "thoresen_2010_form-building-patterns_p90-91_page1_4.jpeg",
        data_dir / "thoresen_2010_form-building-patterns_p90-91_page2_1.jpeg",
    ]

    loader2 = GraphicalLoader(metadata={"source": "Thoresen 2010"})

    for i, (img_path, (x0, x1, y)) in enumerate(zip(dgt2_images, DGT2_SEGMENT_BOUNDS)):
        idx2 = loader2.add_image(img_path)
        loader2.add_horizontal_segment(
            source_index=idx2,
            x0=x0,
            x1=x1,
            y=y,
            name=f"page_{i+1}",
        )

    dgt2_bundle = loader2.bundle
    print(
        f"DGT2: {dgt2_bundle.n_segments} segments, {dgt2_bundle.total_length:.0f} pixels"
    )

    # Convert bundles to timelines
    dgt1_timeline = dgt1_bundle.to_timeline(uid="dgt1", name="Thoresen 2009")
    dgt2_timeline = dgt2_bundle.to_timeline(uid="dgt2", name="Thoresen 2010")

else:
    # Create mock timelines with the same pixel lengths as the real data
    # DGT1: 5 systems × 967 pixels each = 4835 pixels total
    # DGT2: 5 pages with varying widths ≈ 4328 pixels total
    dgt1_timeline = Timeline(length=4835, uid="dgt1", name="Thoresen 2009 (mock)")
    dgt2_timeline = Timeline(length=4328, uid="dgt2", name="Thoresen 2010 (mock)")
    print("Using mock timelines (pymupdf not installed)")
    print(f"DGT1: 5 segments, {dgt1_timeline.length.value:.0f} pixels (mock)")
    print(f"DGT2: 5 segments, {dgt2_timeline.length.value:.0f} pixels (mock)")

# Create audio timeline (150 seconds)
audio_timeline = ContinuousPhysicalTimeline(
    length=AUDIO_DURATION,
    unit="seconds",
    uid="audio",
    name="Audio",
)

# %% [markdown]
# ### Create Timelines

# %%
{
    "DGT1": f"{dgt1_timeline.length.value:.0f} pixels",
    "DGT2": f"{dgt2_timeline.length.value:.0f} pixels",
    "Audio": f"{audio_timeline.length.value:.1f} seconds",
}

# %% [markdown]
# ### Create TimelineGroups
#
# We create two groups, each establishing commensurability between a graphical
# timeline and the audio:
# - **Group 1**: DGT1 + Audio (full extent linear)
# - **Group 2**: DGT2 + Audio (full extent linear)
#
# Since both groups include the same audio, we can transfer coordinates from
# DGT1 to DGT2 by going through audio.

# %%
# Group 1: DGT1 and Audio (linear full-extent alignment)
dgt1_group = TimelineGroup(
    id="dgt1_group", name="DGT1_Group", timelines=[dgt1_timeline]
)
dgt1_group.add_timeline(audio_timeline)  # Default: full extent maps to full extent

# Group 2: DGT2 and Audio (linear full-extent alignment)
dgt2_group = TimelineGroup(
    id="dgt2_group", name="DGT2_Group", timelines=[dgt2_timeline]
)
dgt2_group.add_timeline(audio_timeline)

{
    "DGT1 Group": dgt1_group.n_timelines,
    "DGT2 Group": dgt2_group.n_timelines,
}

# %% [markdown]
# ### Coordinate Transfer: DGT2 -> DGT1
#
# To transfer a coordinate from DGT2 to DGT1, we go through the shared audio timeline:
#
# ```
# DGT2 pixels  -->  Audio seconds  -->  DGT1 pixels
#   (Group 2)                           (Group 1)
# ```

# %%
# Test pixel in DGT2 (halfway through)
dgt2_pixel = 2164.0

# Step 1: DGT2 -> Audio (via DGT2 group)
audio_seconds = dgt2_group.convert(dgt2_pixel, source="dgt2", target="audio")
print(f"DGT2 pixel {dgt2_pixel:.0f} -> Audio {audio_seconds:.2f} seconds")

# Step 2: Audio -> DGT1 (via DGT1 group)
dgt1_pixel = dgt1_group.convert(audio_seconds, source="audio", target="dgt1")
print(f"Audio {audio_seconds:.2f} seconds -> DGT1 pixel {dgt1_pixel:.1f}")

# Verify: Both should be at 50% (75 seconds)
print(f"\nVerification: {audio_seconds / AUDIO_DURATION * 100:.1f}% through the piece")

# %% [markdown]
# ---
#
# ## Part 5: AlignmentBundle
#
# For projects with many timelines, `AlignmentBundle` provides a convenience
# wrapper that manages groups and provides a unified interface.
#
# AlignmentBundle supports both **linear** (full-extent) and **partial**
# alignment via the `start`/`end` parameters.

# %%
# Create a bundle
bundle = AlignmentBundle(name="Thoresen Project")

# Add DGT1 as the first timeline
bundle.add_timeline(dgt1_timeline, uid="dgt1")

# Add audio aligned to DGT1 (linear full-extent)
bundle.add_timeline(
    audio_timeline,
    uid="audio_1",
    aligned_to="dgt1",
)

# Transfer works the same way
result = bundle.transfer(2437.5, from_timeline="dgt1", to_timeline="audio_1")
print(f"DGT1 2437.5 pixels -> Audio {result:.1f} seconds")

# %% [markdown]
# ### Partial Alignment via AlignmentBundle
#
# You can also specify partial alignment using `start` and `end` parameters:

# %%
# Create a new bundle for partial alignment example
partial_bundle = AlignmentBundle(name="Partial Alignment Example")

# Add image timeline (full extent: 0 - 10000 pixels)
image = Timeline(length=10000, uid="img")
partial_bundle.add_timeline(image, uid="image")

# Add musical region that only covers pixels 1000-9000
music = Timeline(length=8000, uid="music")
partial_bundle.add_timeline(
    music,
    uid="music",
    aligned_to="image",
    start=(1000.0, "image"),  # Music starts at image pixel 1000
    end=(9000.0, "image"),  # Music ends at image pixel 9000
)

# Transfer: music coord 0 -> image pixel 1000
result_start = partial_bundle.transfer(0.0, "music", "image")
print(f"Music coord 0 -> Image pixel {result_start}")

# Transfer: music coord 8000 -> image pixel 9000
result_end = partial_bundle.transfer(8000.0, "music", "image")
print(f"Music coord 8000 -> Image pixel {result_end}")

# %% [markdown]
# ---
#
# ## Part 6: Roadmap
#
# ### What's Implemented (Phase 7.4)
# - `TimelineGroup` with timestamp table architecture
# - `start`/`end` parameters for partial alignment
# - `AlignmentBundle` for multi-timeline management
# - Linear interpolation for coordinate conversion
#
# ### Coming Soon (Phase 2+)
# - **MatchClaim**: Event-to-event correspondence
# - **MatchGraph**: Network of match claims
# - **WarpMap**: Non-linear alignment derived from match data
# - **Cross-group transfer** via shared timelines (automated)
#
# ### Next Tutorial
# See **08_supra_piano_roll.ipynb** for a complete alignment workflow
# with IIIF image metadata, ATON hole punch data, MIDI files, audio, and score
# annotations.

# %% [markdown]
# ---
#
# ## Summary
#
# **Key Takeaways:**
#
# 1. **Commensurability** is the ability to convert coordinates between timelines
# 2. **TimelineGroup** establishes commensurability via a timestamp table
# 3. **start/end parameters** define partial alignment (not all timelines cover the full extent)
# 4. **convert()** transfers coordinates between any commensurable timelines in the group
#
# > "A TimelineGroup stores alignment as a timestamp table where each row is
# > a boundary instant, enabling coordinate transfer between any pair of
# > timelines via linear interpolation."

# %% [markdown]
# ---
#
# ## Exercises
#
# ### Exercise 1: Basic Group
# Create a TimelineGroup with:
# - A score timeline (1000 quarters)
# - A performance timeline (240 seconds) aligned to it
#
# Transfer the coordinate for measure 50 (assuming 4 quarters per measure) to performance seconds.
#
# <details>
# <summary>Solution</summary>
#
# ```python
# score = Timeline(length=1000, uid="score")
# perf = ContinuousPhysicalTimeline(length=240.0, unit="seconds", uid="perf")
#
# group = TimelineGroup(id="score_perf", name="Score-Perf", timelines=[score])
# group.add_timeline(perf)  # Linear full-extent
#
# measure_50 = 50 * 4  # 200 quarters
# perf_seconds = group.convert(measure_50, source="score", target="perf")
# print(f"Measure 50 -> {perf_seconds:.1f} seconds")
# # Expected: 48.0 seconds (200/1000 * 240)
# ```
# </details>
#
# ### Exercise 2: Partial Alignment
# Create a group where a MIDI file (0-48000 ticks) only covers measures 10-50
# of a score (1000 quarters).
#
# <details>
# <summary>Solution</summary>
#
# ```python
# score = Timeline(length=1000, uid="score")
# midi = Timeline(length=48000, uid="midi")
#
# group = TimelineGroup(id="score_midi", name="Score-MIDI", timelines=[score])
# group.add_timeline(
#     midi,
#     start=(40.0, "score"),   # Measure 10 = 40 quarters
#     end=(200.0, "score"),    # Measure 50 = 200 quarters
# )
#
# # MIDI tick 24000 (halfway) should map to measure 30
# score_quarters = group.convert(24000, source="midi", target="score")
# print(f"MIDI 24000 -> {score_quarters:.0f} quarters (measure {score_quarters/4:.0f})")
# # Expected: 120 quarters (measure 30)
# ```
# </details>
