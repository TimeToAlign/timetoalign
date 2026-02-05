# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.17.3
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Beat Grids: Metrical Structure for Timelines
#
# This tutorial introduces **BeatGrid** - a specialized timeline that provides
# metrical structure (measures, beats) for any parent timeline.
#
# **Learning Objectives:**
# - Understand that a BeatGrid is a **ContinuousLogicalTimeline** measured in quarters
# - Create BeatGrids from tempo information
# - Query measure numbers and beat positions via built-in C-Maps
# - Understand the underlying C-Maps (MetricMap, BeatInMeasureMap, MetricalPositionMap)
# - Relate BeatGrids to physical timelines via tempo maps
# - Validate against real-world SUPRA data (Wagner Meistersinger Prelude)
#
# **Prerequisites:**
# - 03_conversion_maps.ipynb (C-Maps)
# - 04_building_timelines.ipynb (Timelines, events, hierarchies)
# - 05_timestamps.ipynb (Cross-section views)

# %% [markdown]
# ## Why BeatGrid?
#
# When working with music data, a common question arises:
#
# > "What measure and beat is this event on?"
#
# For example:
# - An audio track at 60 seconds - what's the measure number?
# - A MIDI tick at position 1920 - what beat is that?
# - A pixel on a sheet music image - what's the metrical position?
#
# **BeatGrid** solves this by providing:
# 1. A **coordinate system** in quarter notes (Fractions for exact representation)
# 2. Built-in **C-Maps** that convert quarters to measure numbers and beat positions
# 3. **Domain-agnostic** design - works with audio, MIDI, scores, and images
#
# ### Key Insight: BeatGrid IS a Timeline
#
# A BeatGrid is NOT just a utility class or a wrapper around C-Maps.
# It is a **proper ContinuousLogicalTimeline**:
#
# ```
# BeatGrid (ContinuousLogicalTimeline)
# ├── Coordinate system: quarters (Fractions)
# ├── C-Map: quarters -> mc (MetricMap) - integer measure count
# ├── C-Map: quarters -> beat (BeatInMeasureMap) - Fraction beat position
# ├── C-Map: quarters -> {mc, beat, mn} (MetricalPositionMap)
# └── Events: Beat instants, Measure intervals (optional)
# ```
#
# This design means:
# - It can hold its own events (beats, downbeats, measures)
# - It integrates with the timestamp system automatically
# - It works for ANY parent domain (physical, logical, graphical)

# %% [markdown]
# ## Setup

# %%
from fractions import Fraction

import numpy as np

from timetoalign import TimeUnit
from timetoalign.maps import (
    FloorMap,
    MetricMap,
    RotationMap,
)
from timetoalign.timelines import (
    BeatGrid,
    ContinuousPhysicalTimeline,
)

# %% [markdown]
# ---
#
# ## Part 1: Basic BeatGrid Usage
#
# Let's start with the simplest case: creating a BeatGrid for a 3-minute audio
# track at 120 BPM in 4/4 time.

# %%
# Create a BeatGrid from tempo information
# At 120 BPM with quarter-note beats: 2 quarters per second
# 180 seconds = 360 quarters = 90 measures

grid = BeatGrid.from_tempo(
    tempo_bpm=120.0,
    beats_per_measure=4,
    length_seconds=180.0,  # 3 minutes
)

# grid._length is a Coordinate object, access .value to get the Fraction
{
    "Length (quarters)": float(grid._length.value),
    "Measures": grid.n_measures,
    "Quarters per measure": float(grid.quarters_per_measure),
    "Quarters per beat": float(grid.quarters_per_beat),
    "Tempo (BPM)": grid.tempo_bpm,
}

# %% [markdown]
# ### Querying Metrical Positions
#
# BeatGrid provides convenient methods to query measure and beat at any quarter-note position.
#
# **Return types:**
# - `measure_at()` returns an **int** (the measure count, MC)
# - `beat_at()` returns a **Fraction** (exact beat position, 1-indexed)
# - `metrical_position()` returns a **dict** with `mc`, `beat`, and `mn` (measure number label)

# %%
# Query metrical position at various quarter-note coordinates
# measure_at() returns int, beat_at() returns Fraction
test_quarters = [0, 1, 4, 7.5, 100]

results = []
for q in test_quarters:
    mc = grid.measure_at(q)  # int
    beat = grid.beat_at(q)  # Fraction
    pos = grid.metrical_position(q)  # {mc: int, beat: Fraction, mn: str}
    results.append(
        {
            "Quarter": q,
            "MC (measure count)": mc,
            "Beat (Fraction)": str(beat),  # Show as string to preserve Fraction
            "Beat (float)": float(beat),
            "MN (label)": pos["mn"],
        }
    )

results

# %% [markdown]
# ### Reverse Lookup: From MC/Beat to Quarters
#
# You can also go the other direction - find the quarter position for a given
# measure count (MC) and beat:

# %%
# Find quarter position for specific MC/beat combinations
# quarter_at(mc, beat) returns a Fraction
positions = [
    (1, Fraction(1, 1)),  # MC 1, beat 1 (downbeat)
    (1, Fraction(3, 1)),  # MC 1, beat 3
    (5, Fraction(1, 1)),  # MC 5, beat 1 (downbeat)
    (10, Fraction(5, 2)),  # MC 10, beat 2.5 (between beats)
]

{f"MC{m}B{float(b)}": float(grid.quarter_at(m, b)) for m, b in positions}

# %% [markdown]
# ### Converting to Seconds via Tempo Map
#
# When created with `from_tempo()`, the BeatGrid includes a tempo C-Map that
# converts quarters to seconds:

# %%
# The tempo map converts quarters -> seconds
# At 120 BPM: 2 quarters per second, so 1 quarter = 0.5 seconds

tempo_map = grid._tempo_map  # Internal tempo map

test_quarters = [0, 1, 4, 100, 360]
{f"{q} quarters": f"{tempo_map(q):.2f} seconds" for q in test_quarters}

# %%
grid

# %% [markdown]
# ---
#
# ## Part 2: Understanding the Underlying C-Maps
#
# BeatGrid uses three specialized C-Map types internally:
#
# 1. **MetricMap**: Converts quarters to measure count (MC) using table-based lookup
# 2. **BeatInMeasureMap**: Converts quarters to beat position (Fraction, 1-indexed)
# 3. **MetricalPositionMap**: Combines both into a {mc, beat, mn} dict
#
# **Why MetricMap instead of FloorMap?**
#
# While `FloorMap` (simple integer division) works for uniform meters,
# `MetricMap` handles real-world complexity:
# - Anacrusis (pickup measures with MN=0)
# - Varying time signatures (4/4 -> 3/4 -> 6/8)
# - Repeat endings (MN=1a, MN=1b)
# - Cadenzas with irregular measure lengths
#
# The simpler `FloorMap` and `RotationMap` are still useful as standalone building blocks.

# %% [markdown]
# ### FloorMap: Integer Division (Building Block)
#
# A `FloorMap` computes integers via floor division. While BeatGrid uses `MetricMap` internally,
# `FloorMap` is a useful standalone building block:
#
# ```
# output = floor((input - offset) / divisor) + base
# ```

# %%
# FloorMap for 4/4 time (4 quarters per measure), 1-indexed
# Formula: floor((input - offset) / divisor) + base
measure_map = FloorMap(
    divisor=4.0,  # quarters per measure
    base=1,  # 1-indexed measures
    offset=0.0,  # no input offset
)

# Test at various positions
test_values = [0, 1, 3.99, 4.0, 7.5, 100]
{f"q={v}": measure_map(v) for v in test_values}

# %% [markdown]
# ### RotationMap: Cyclic Patterns (Building Block)
#
# A `RotationMap` produces cyclic/periodic output using modular arithmetic:
#
# ```
# output = ((input - offset) % period) * scale + base
# ```
#
# This creates the pattern 1, 2, 3, 4, 1, 2, 3, 4... for beats in 4/4 time.
#
# **Important**: RotationMap is NOT invertible (many-to-one).

# %%
# RotationMap for 4/4 time (4 quarters per measure)
# Formula: ((input - offset) % period) * scale + base
beat_rotation_map = RotationMap(
    period=4.0,  # quarters per measure
    scale=1.0,  # 1 quarter = 1 beat (for quarter-note beats)
    base=1.0,  # 1-indexed beats
    offset=0.0,  # no input offset
)

# Test the cyclic pattern
test_values = [0, 1, 2, 3, 4, 5, 6, 7, 7.5]
{f"q={v}": beat_rotation_map(v) for v in test_values}

# %%
# RotationMap is NOT invertible
# Quarters 0, 4, 8, 12... all map to beat 1
{
    "Is invertible?": beat_rotation_map.is_invertible,
    "Why?": "Many quarters map to the same beat (many-to-one)",
}

# %% [markdown]
# ### MetricMap: What BeatGrid Actually Uses
#
# While `FloorMap` works for simple uniform meters, `BeatGrid` uses `MetricMap` internally.
# `MetricMap` is table-based and can handle anacrusis, varying meters, and repeat endings:
#
# ```python
# # MetricMap stores explicit measure boundaries:
# # (start_quarters, mc, mn, length_quarters)
# # This enables handling of irregular structures
# ```

# %% jupyter={"is_executing": true}
# Create a MetricMap with uniform measures (like BeatGrid does internally)
meter_map = MetricMap.from_uniform(
    n_measures=10,
    quarters_per_measure=Fraction(4, 1),  # 4/4 time
    start_mc=1,  # First measure is MC 1
    start_mn="1",  # First measure label is "1"
)

# Test: quarters -> MC (int)
test_values = [0, 3.99, 4.0, 7.5, 36]
{
    f"q={v}": {
        "MC": meter_map(v),
        "MN": meter_map.get_mn(meter_map(v)),
        "beat": str(meter_map.beat_in_measure(v)),
    }
    for v in test_values
}

# %% [markdown]
# ---
#
# ## Part 3: Different Time Signatures
#
# BeatGrid supports various time signatures through the `beats_per_measure`
# and `beat_unit` parameters.

# %%
# 3/4 time: 3 quarter-note beats per measure
# 48 quarters / 3 quarters per measure = 16 measures
grid_3_4 = BeatGrid(
    length=Fraction(48, 1),  # 48 quarters = 16 measures
    beats_per_measure=3,
    beat_unit=Fraction(1, 4),  # quarter note beat
)

# 6/8 time: 6 eighth-note beats per measure
# 6 eighth notes = 3 quarter notes per measure
# 48 quarters / 3 quarters per measure = 16 measures
grid_6_8 = BeatGrid(
    length=Fraction(48, 1),
    beats_per_measure=6,
    beat_unit=Fraction(1, 8),  # eighth note beat
)

# beat_at() returns Fraction - convert to str for display
{
    "3/4": {
        "quarters_per_measure": float(grid_3_4.quarters_per_measure),
        "n_measures": grid_3_4.n_measures,
        "beat_at_q6": str(grid_3_4.beat_at(6)),  # Should be Fraction(1,1) - new measure
    },
    "6/8": {
        "quarters_per_measure": float(grid_6_8.quarters_per_measure),
        "n_measures": grid_6_8.n_measures,
        # 1.5 quarters = 3 eighth notes = beat 4 (1-indexed)
        "beat_at_q1.5": str(grid_6_8.beat_at(1.5)),
    },
}

# %% [markdown]
# ---
#
# ## Part 4: Cross-Domain Relationships
#
# A key principle in TimeToAlign!: timelines with different units relate via
# **C-Maps**, not parent-child embedding.
#
# A BeatGrid (in quarters) cannot be a direct *child* of a physical timeline
# (in seconds). Instead, they are related via a **tempo C-Map**.

# %%
# Create an audio timeline and a BeatGrid
audio = ContinuousPhysicalTimeline(length=180.0, unit=TimeUnit.seconds)

# from_tempo() creates a BeatGrid with an attached tempo C-Map
grid = BeatGrid.from_tempo(
    tempo_bpm=120.0,
    beats_per_measure=4,
    length_seconds=180.0,
)

# The BeatGrid has a tempo map (LinearMap) that converts quarters -> seconds
# This is only available when created via from_tempo()
tempo_map = grid._tempo_map

# Query: "What second corresponds to MC 10, beat 1?"
# quarter_at(mc, beat) returns Fraction
mc_10_beat_1 = grid.quarter_at(10, Fraction(1, 1))
second = tempo_map(float(mc_10_beat_1))

{
    "Query": "MC 10, Beat 1",
    "Quarter position": float(mc_10_beat_1),
    "Second": second,
    "Verification": f"At 120 BPM: {9 * 4} q * 0.5 sec/q = {9 * 4 * 0.5} s",
}

# %%
# Reverse: "What MC/beat is second 60.0?"
# First convert seconds -> quarters using inverse of tempo map

# At 120 BPM: quarters = seconds * 2
quarters_at_60s = 60.0 * 2  # 120 quarters

# measure_at returns int, beat_at returns Fraction
{
    "Second": 60.0,
    "Quarters": quarters_at_60s,
    "MC": grid.measure_at(quarters_at_60s),
    "Beat (Fraction)": str(grid.beat_at(quarters_at_60s)),
    "Full position": grid.metrical_position(quarters_at_60s),
}

# %% [markdown]
# ---
#
# ## Part 5: Materializing Beat and Measure Events
#
# BeatGrid can optionally create actual **events** for beats and measures. This is useful for:
# - Visualization (plotting beat markers)
# - Alignment (matching beats across timelines)
# - Analysis (counting beats, measure statistics)

# %%
# Create a small grid for demonstration
demo_grid = BeatGrid(
    length=Fraction(16, 1),  # 16 quarters = 4 measures
    beats_per_measure=4,
)

# Materialize all beats (creates Beat events)
n_beats = demo_grid.materialize_beats()

# Get the beat events (returns EventData which is iterable)
beat_events = demo_grid.get_events(event_type="Beat")

# Convert to list of dicts for display
beat_list = list(beat_events)

{
    "Total beats created": n_beats,
    "Event count": len(beat_events),
    "First 4 events": beat_list[:4],
}

# %%
# Create another grid for measure events
demo_grid2 = BeatGrid(
    length=Fraction(16, 1),  # 16 quarters = 4 measures
    beats_per_measure=4,
)

# Materialize measures (creates IntervalEvents with start/end)
n_measures = demo_grid2.materialize_measures()

# Get the measure events (returns EventData which is iterable)
measure_events = demo_grid2.get_events(event_type="Measure")

{
    "Total measures created": n_measures,
    "Measure events": list(measure_events),
}

# %% [markdown]
# ---
#
# ## Part 6: SUPRA Validation
#
# Let's validate the BeatGrid implementation against real-world data from the
# **SUPRA Piano Roll Archive**.
#
# ### The Reference Data: Wagner Meistersinger Prelude
#
# The SUPRA archive contains piano roll data for Wagner's Meistersinger Prelude
# with known metrical structure:
#
# | Parameter | Value | Source |
# |-----------|-------|--------|
# | Total Length | 888 quarter notes | DCML score annotation |
# | Time Signature | 4/4 throughout | Score metadata |
# | Total Measures | 222 | 888 / 4 = 222 |
# | First Measure | 1 | Standard numbering |

# %%
# Create the Wagner Meistersinger BeatGrid
# Known: 888 quarters, 4/4 time, 222 measures

SUPRA_LENGTH_QUARTERS = 888
SUPRA_BEATS_PER_MEASURE = 4
SUPRA_N_MEASURES = 222  # 888 / 4

wagner_grid = BeatGrid(
    length=Fraction(SUPRA_LENGTH_QUARTERS, 1),
    beats_per_measure=SUPRA_BEATS_PER_MEASURE,
)

# wagner_grid._length is a Coordinate, access .value for the Fraction
{
    "Expected length": SUPRA_LENGTH_QUARTERS,
    "Actual length": float(wagner_grid._length.value),
    "Expected measures": SUPRA_N_MEASURES,
    "Actual measures": wagner_grid.n_measures,
    "Validation": "PASS" if wagner_grid.n_measures == SUPRA_N_MEASURES else "FAIL",
}

# %%
# Validate measure boundaries
# MC 1 starts at quarter 0
# MC 222 starts at quarter 884 (= (222-1) * 4)
# Last beat of MC 222 is at quarter 887

# expected_beat is a Fraction (beat_at returns Fraction)
test_positions = [
    (0, 1, Fraction(1, 1)),  # Quarter 0 = MC 1, Beat 1
    (4, 2, Fraction(1, 1)),  # Quarter 4 = MC 2, Beat 1
    (884, 222, Fraction(1, 1)),  # Quarter 884 = MC 222, Beat 1
    (887, 222, Fraction(4, 1)),  # Quarter 887 = MC 222, Beat 4 (last beat)
]

results = []
for quarter, expected_mc, expected_beat in test_positions:
    actual_mc = wagner_grid.measure_at(quarter)  # int
    actual_beat = wagner_grid.beat_at(quarter)  # Fraction
    results.append(
        {
            "Quarter": quarter,
            "Expected": f"MC{expected_mc}B{expected_beat}",
            "Actual": f"MC{actual_mc}B{actual_beat}",
            "Pass": actual_mc == expected_mc and actual_beat == expected_beat,
        }
    )

results

# %%
# Validate round-trip: quarter_at(measure_at(q), beat_at(q)) == q
# This should hold for all integer quarter positions on beat boundaries

test_quarters = [0, 4, 100, 500, 884]

round_trip_results = []
for q in test_quarters:
    mc = wagner_grid.measure_at(q)  # int
    beat = wagner_grid.beat_at(q)  # Fraction
    reconstructed = wagner_grid.quarter_at(mc, beat)  # Fraction
    round_trip_results.append(
        {
            "Original quarter": q,
            "MC/Beat": f"MC{mc}B{beat}",
            "Reconstructed": float(reconstructed),
            "Match": float(reconstructed) == q,
        }
    )

round_trip_results

# %% [markdown]
# ### Equivalence with Score TSV Measures
#
# The DCML score annotation files (TSV format) contain explicit measure
# boundaries. Let's verify that our BeatGrid produces equivalent measure
# numbers.
#
# **Key insight**: When loading a score from TSV files that already contain
# measure information, the BeatGrid's measure numbers should **match exactly**
# with the source data. This demonstrates that:
#
# 1. A manually created BeatGrid produces correct metrical positions
# 2. The BeatGrid is equivalent to the measure structure in annotated scores
# 3. We can use BeatGrid for audio/MIDI where no measure annotations exist

# %%
# Array operations: compute measure/beat for ALL quarter positions
all_quarters = np.arange(0, SUPRA_LENGTH_QUARTERS)

# Vectorized MC computation using the underlying MetricMap
# wagner_grid._meter_map is the MetricMap, which supports array input
all_mcs = wagner_grid._meter_map(all_quarters)

# For beat positions, use the BeatInMeasureMap
# Note: array output is float, not Fraction
all_beats = wagner_grid._beat_map(all_quarters)

# Verify expected patterns
unique_mcs = np.unique(all_mcs)
unique_beats = np.unique(all_beats)

{
    "Total quarter positions": len(all_quarters),
    "Unique MCs": len(unique_mcs),
    "MC range": f"{int(unique_mcs.min())} - {int(unique_mcs.max())}",
    "Unique beats (float)": sorted([float(b) for b in unique_beats]),
    "Expected beats (integer positions)": [1.0, 2.0, 3.0, 4.0],
}

# %%
# Final validation: materialize events and verify counts
wagner_full = BeatGrid(
    length=Fraction(SUPRA_LENGTH_QUARTERS, 1),
    beats_per_measure=SUPRA_BEATS_PER_MEASURE,
)

n_beats = wagner_full.materialize_beats()
n_downbeats = len(
    [
        e
        for e in wagner_full.get_events(event_type="Beat")
        if e.get("is_downbeat", False)
    ]
)

# Create new grid for measures (to avoid event ID conflicts)
wagner_measures = BeatGrid(
    length=Fraction(SUPRA_LENGTH_QUARTERS, 1),
    beats_per_measure=SUPRA_BEATS_PER_MEASURE,
)
n_measures = wagner_measures.materialize_measures()

{
    "Total beats": n_beats,
    "Expected beats": SUPRA_LENGTH_QUARTERS,  # One beat per quarter
    "Downbeats": n_downbeats,
    "Expected downbeats": SUPRA_N_MEASURES,  # One per measure
    "Total measures": n_measures,
    "Expected measures": SUPRA_N_MEASURES,
    "All validations pass": (
        n_beats == SUPRA_LENGTH_QUARTERS
        and n_downbeats == SUPRA_N_MEASURES
        and n_measures == SUPRA_N_MEASURES
    ),
}

# %% [markdown]
# ---
#
# ## Summary
#
# **Key Takeaways:**
#
# > "A BeatGrid is a ContinuousLogicalTimeline measured in quarters. It
# > provides metrical structure (measures, beats) via built-in C-Maps,
# > and works for any musical content."
#
# **What you learned:**
#
# 1. **BeatGrid is a timeline**, not just a utility wrapper
#    - It has its own coordinate system (quarters as Fractions)
#    - It can hold events (beats, measures via materialization)
#
# 2. **Built-in C-Maps** handle metrical conversion:
#    - `MetricMap`: quarters -> MC (int) - handles real-world complexity
#    - `BeatInMeasureMap`: quarters -> beat (Fraction, 1-indexed)
#    - `MetricalPositionMap`: quarters -> {mc, beat, mn} dict
#
# 3. **Return types matter:**
#    - `measure_at()` returns `int` (measure count)
#    - `beat_at()` returns `Fraction` (exact beat position)
#    - `metrical_position()` returns dict with `mc`, `beat`, `mn` keys
#
# 4. **Cross-domain relationships** use C-Maps:
#    - A BeatGrid relates to audio via a tempo map (quarters -> seconds)
#    - Not via parent-child embedding (different units)
#
# 5. **SUPRA validation** proves correctness:
#    - 888 quarters = 222 measures in 4/4 time
#    - Round-trip: `quarter_at(measure_at(q), beat_at(q)) == q`
#    - Array operations are vectorized for performance
#
# **The Component Hierarchy:**
#
# ```
# Building Block C-Maps:
# ├── FloorMap       # Integer division (measures, pages)
# ├── RotationMap    # Periodic patterns (beats, angles)
# └── CombinationMap # Tuple outputs ((measure, beat), (x, y))
#
# BeatGrid Internal C-Maps (handles real-world complexity):
# ├── MetricMap            # quarters -> MC (int), handles anacrusis/irregular
# ├── BeatInMeasureMap    # quarters -> beat (Fraction)
# └── MetricalPositionMap # quarters -> {mc, beat, mn}
#
# BeatGrid (ContinuousLogicalTimeline):
# ├── Unit: quarters (Fraction)
# ├── C-Maps: MetricMap + BeatInMeasureMap + MetricalPositionMap
# ├── Events: Beat/Measure (optional via materialize)
# └── Factory: from_tempo() creates with tempo C-Map
# ```

# %% [markdown]
# ---
#
# ## Exercises
#
# ### Exercise 1: Waltz Time
#
# Create a BeatGrid for a 5-minute waltz at 90 BPM in 3/4 time. Query the
# measure and beat at exactly 2.5 minutes.

# %%
# Your solution here:
# waltz = BeatGrid.from_tempo(...)
# ...

# %% [markdown]
# ### Exercise 2: Understanding RotationMap
#
# What does `RotationMap(period=6.0, scale=2.0, base=1.0)` output for inputs 0, 3, 6, 7.5?
#
# Hint: The formula is `((input - offset) % period) * scale + base` (offset defaults to 0)

# %%
# Your solution here:
# rot = RotationMap(...)
# ...

# %% [markdown]
# ### Exercise 3: Custom Measure Numbering
#
# Create a BeatGrid where measures start at MC 0 (for a pickup measure).
# Verify that quarter 0 is MC 0, and quarter 4 is MC 1.
#
# Hint: Use the `start_measure` parameter in the BeatGrid constructor.

# %%
# Your solution here:
# pickup_grid = BeatGrid(
#     length=Fraction(20, 1),
#     beats_per_measure=4,
#     start_measure=0,  # MC starts at 0
# )
# ...

# %% [markdown]
# ---
#
# ## Next Steps
#
# - **Tutorial 07**: Alignment Basics - Learn how to transfer coordinates between timelines
# - **Application A3**: SUPRA Piano Roll - Complete alignment workflow with real data
