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
# # Conversion Maps: Transforming Coordinates
#
# This tutorial introduces **ConversionMaps** (C-Maps) - the bridge between different coordinate systems in TimeToAlign!
#
# **Learning Objectives:**
# - Understand what C-Maps are and when to use them
# - Use built-in maps: ScalarMap, LinearMap, ShiftMap
# - Create tempo-aware maps with TableMap
# - Chain and compose maps for complex conversions
#
# **Prerequisites:**
# - 01_core_concepts.ipynb (Domains, Units, Coordinates)
# - Basic Python knowledge

# %% [markdown]
# ## Why Conversion Maps Matter
#
# In the previous tutorials, we learned that TimeToAlign! organizes data into three domains (Physical, Logical, Graphical), each with its own units. But real-world workflows often require translating coordinates between units:
#
# | Scenario | From | To | Conversion |
# |----------|------|-----|------------|
# | MIDI to quarters | ticks | quarters | ticks / PPQ |
# | Audio analysis | samples | seconds | samples / sample_rate |
# | Score playback | quarters | seconds | tempo-dependent |
# | Timeline offset | seconds | seconds | add/subtract offset |
#
# **ConversionMaps** encapsulate these transformations as reusable, composable objects. They are the "bridges" that connect coordinate systems.
#
# ```
# ticks ──[TicksToQuarters]──> quarters ──[QuartersToSeconds]──> seconds
# ```

# %% [markdown]
# ## Setup

# %%
import numpy as np
import pandas as pd

from timetoalign import TimeUnit
from timetoalign.maps import (  # Convenience classes
    ChainMap,
    LinearMap,
    PiecewiseMap,
    QuartersToTicks,
    SamplesToSeconds,
    ScalarMap,
    SecondsToSamples,
    ShiftMap,
    TableMap,
    TicksToQuarters,
)

# %% [markdown]
# ---
#
# ## What is a ConversionMap?
#
# A **ConversionMap** is a function that transforms a coordinate from one unit to another. In TimeToAlign!, C-Maps:
#
# 1. **Take input** - a coordinate value (scalar or array)
# 2. **Apply transformation** - mathematical operation
# 3. **Return output** - converted value(s)
#
# All C-Maps share a common interface:
#
# ```python
# cmap(value)        # Convert a single value
# cmap(array)        # Convert an array (vectorized)
# cmap.inverse()     # Get the inverse map
# cmap.source_unit   # Input unit (optional)
# cmap.target_unit   # Output unit (optional)
# ```

# %% [markdown]
# ---
#
# ## ScalarMap: Pure Multiplication
#
# The simplest C-Map multiplies input by a constant: `y = scalar * x`
#
# **Use cases:**
# - Converting between related units (ticks → quarters, samples → seconds)
# - Any linear scaling without offset

# %%
# Convert milliseconds to seconds
ms_to_sec = ScalarMap(
    scalar=0.001,
    source_unit="milliseconds",
    target_unit="seconds",
)

# Convert single value
print(f"1500 ms = {ms_to_sec(1500)} seconds")

# Convert array (vectorized)
ms_values = np.array([0, 500, 1000, 1500, 2000])
sec_values = ms_to_sec(ms_values)
print(f"Array: {ms_values} ms -> {sec_values} seconds")

# %%
# Get the inverse map
sec_to_ms = ms_to_sec.inverse()

print(f"Original: {ms_to_sec}")
print(f"Inverse:  {sec_to_ms}")

# Round-trip: should get back original value
original = 1500
converted = ms_to_sec(original)
back = sec_to_ms(converted)
print(f"\nRound-trip: {original} -> {converted} -> {back}")

# %% [markdown]
# ### Convenience Classes
#
# TimeToAlign! provides named classes for common conversions:

# %%
# MIDI ticks to quarters (uses PPQ = pulses per quarter)
t2q = TicksToQuarters(ppq=480)  # Standard MIDI resolution

tick_values = [0, 480, 960, 1440, 1920]
quarter_values = [t2q(t) for t in tick_values]

pd.DataFrame(
    {
        "ticks": tick_values,
        "quarters": quarter_values,
    }
)

# %%
# Audio samples to seconds
s2s = SamplesToSeconds(sample_rate=44100)  # CD quality

sample_values = [0, 44100, 88200, 132300]
second_values = [s2s(s) for s in sample_values]

pd.DataFrame(
    {
        "samples": sample_values,
        "seconds": second_values,
    }
)

# %% [markdown]
# ---
#
# ## LinearMap: Scale and Offset
#
# For affine transformations: `y = scalar * x + offset`
#
# **Use cases:**
# - Unit conversion with offset (e.g., Celsius to Fahrenheit)
# - Timeline alignment with both scaling and shifting

# %%
# Example: Timeline with a 0.5 second offset and 2x speed
# A recording starts 0.5s after the score begins, and is played at 2x speed
# score_time = 2 * recording_time + 0.5

recording_to_score = LinearMap(
    scalar=2.0,
    offset=0.5,
    source_unit="seconds",
    target_unit="seconds",
)

recording_times = [0.0, 0.5, 1.0, 1.5, 2.0]
score_times = [recording_to_score(t) for t in recording_times]

pd.DataFrame(
    {
        "recording_time": recording_times,
        "score_time": score_times,
    }
)

# %%
# The inverse: score_to_recording
# From y = 2x + 0.5, solve for x: x = (y - 0.5) / 2
score_to_recording = recording_to_score.inverse()

print(f"Original: y = {recording_to_score.scalar}x + {recording_to_score.offset}")
print(f"Inverse:  y = {score_to_recording.scalar}x + {score_to_recording.offset}")

# %% [markdown]
# ---
#
# ## ShiftMap: Pure Offset
#
# For adding/subtracting a constant: `y = x + offset`
#
# **Use cases:**
# - Anacrusis (pickup measure) adjustment
# - Aligning timelines with different origins

# %%
# Example: A piece starts with a half-beat pickup
# Notation shows beat 1 at the anacrusis, but musically it's beat 0.5
anacrusis_adjustment = ShiftMap(
    offset=-0.5,
    source_unit="quarters",
    target_unit="quarters",
)

notation_beats = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
adjusted_beats = [anacrusis_adjustment(b) for b in notation_beats]

pd.DataFrame(
    {
        "notation_beat": notation_beats,
        "adjusted_beat": adjusted_beats,
    }
)

# %% [markdown]
# ---
#
# ## TableMap: Non-Linear Mapping
#
# For mappings defined by explicit anchor points with interpolation between them.
#
# **Use cases:**
# - Tempo-based conversions (ticks to seconds with varying tempo)
# - Alignment anchors
# - Any non-linear monotonic mapping

# %%
# Define explicit anchor points
# X: input coordinates (must be strictly increasing)
# Y: output coordinates
tempo_map = TableMap(
    x_values=[0, 480, 960, 1440],
    y_values=[0.0, 0.5, 1.5, 2.0],  # Non-uniform tempo!
    source_unit="ticks",
    target_unit="seconds",
)

# The first 480 ticks = 0.5 seconds (fast tempo)
# The next 480 ticks = 1.0 seconds (slow tempo)
# The last 480 ticks = 0.5 seconds (fast again)

tick_samples = [0, 240, 480, 720, 960, 1200, 1440]
second_samples = [tempo_map(t) for t in tick_samples]

pd.DataFrame(
    {
        "ticks": tick_samples,
        "seconds": second_samples,
    }
)

# %%
# Convenience: Create from MIDI-style tempo events
# More realistic: tempo starts at 120 BPM, changes to 60 BPM at beat 2

tempo_map = TableMap.from_tempo_changes(
    tick_positions=[0, 960],  # Tempo change at tick 960 (beat 2 @ 480 PPQ)
    tempos_bpm=[120.0, 60.0],  # 120 BPM then 60 BPM
    ticks_per_quarter=480,
)

# At 120 BPM: 1 quarter = 0.5 seconds, 1 tick = 0.5/480 seconds
# At 60 BPM:  1 quarter = 1.0 seconds, 1 tick = 1.0/480 seconds

ticks = [0, 240, 480, 720, 960, 1200, 1440, 1680, 1920]
seconds = tempo_map(np.array(ticks))

pd.DataFrame(
    {
        "ticks": ticks,
        "quarters": [t / 480 for t in ticks],
        "seconds": seconds,
    }
)

# %% [markdown]
# ### Interpolation Methods
#
# TableMap supports different interpolation strategies:

# %%
from timetoalign.maps.table import InterpolationKind

# Same anchor points, different interpolation
x = [0, 10, 20, 30]
y = [0, 5, 5, 10]  # Step function pattern

linear = TableMap(x_values=x, y_values=y, kind="linear")
previous = TableMap(x_values=x, y_values=y, kind="previous")  # Step function
nearest = TableMap(x_values=x, y_values=y, kind="nearest")

test_x = [5, 15, 25]
pd.DataFrame(
    {
        "x": test_x,
        "linear": [linear(v) for v in test_x],
        "previous": [previous(v) for v in test_x],
        "nearest": [nearest(v) for v in test_x],
    }
)

# %% [markdown]
# ---
#
# ## ChainMap: Composing Maps
#
# Chain multiple maps together: `f(g(x))`
#
# **Use cases:**
# - Multi-step conversions (ticks → quarters → seconds)
# - Building complex pipelines from simple components

# %%
# Chain: ticks -> quarters -> seconds
# At constant 120 BPM: 1 quarter = 0.5 seconds

ticks_to_quarters = TicksToQuarters(ppq=480)
quarters_to_seconds = ScalarMap(
    scalar=0.5, source_unit="quarters", target_unit="seconds"
)

# Method 1: Using >> operator
ticks_to_seconds = ticks_to_quarters >> quarters_to_seconds

# Method 2: Using .then() method
ticks_to_seconds_alt = ticks_to_quarters.then(quarters_to_seconds)

ticks = [0, 480, 960, 1440, 1920]
pd.DataFrame(
    {
        "ticks": ticks,
        "quarters": [ticks_to_quarters(t) for t in ticks],
        "seconds": [ticks_to_seconds(t) for t in ticks],
    }
)

# %%
# Inverse of a chain reverses the order and inverts each map
seconds_to_ticks = ticks_to_seconds.inverse()

seconds = [0.0, 0.5, 1.0, 1.5, 2.0]
back_to_ticks = [seconds_to_ticks(s) for s in seconds]

pd.DataFrame(
    {
        "seconds": seconds,
        "ticks": back_to_ticks,
    }
)

# %% [markdown]
# ---
#
# ## PiecewiseMap: Region-Based Mapping
#
# Use different maps for different coordinate ranges.
#
# **Use cases:**
# - Tempo changes (different tempos in different sections)
# - Discontinuous alignments
# - Multi-system score layouts

# %%
# Three sections with different tempos:
# [0, 10): slow tempo (2x time dilation)
# [10, 20): normal tempo (1x)
# [20, 30]: fast tempo (0.5x time compression)

slow_map = ScalarMap(scalar=2.0)
normal_map = LinearMap(scalar=1.0, offset=10.0)  # Offset to connect at boundary
fast_map = LinearMap(scalar=0.5, offset=25.0)  # Continue from previous

piecewise = PiecewiseMap(
    boundaries=[0.0, 10.0, 20.0, 30.0],
    maps=[slow_map, normal_map, fast_map],
)

x_values = [0, 5, 10, 15, 20, 25, 30]
y_values = [piecewise(x) for x in x_values]

pd.DataFrame(
    {
        "input": x_values,
        "output": y_values,
        "region": ["slow", "slow", "normal", "normal", "fast", "fast", "fast"],
    }
)

# %% [markdown]
# ---
#
# ## Vectorized Array Operations
#
# All C-Maps support efficient numpy array operations:

# %%
# Convert a large array of samples to seconds
sample_rate = 44100
samples = np.arange(
    0, sample_rate * 60, sample_rate
)  # One sample per second for 60 seconds

s2s = SamplesToSeconds(sample_rate=sample_rate)

# Vectorized conversion (fast!)
seconds = s2s(samples)

print(f"Converted {len(samples)} sample positions")
print(f"First 5: {seconds[:5]}")
print(f"Last 5: {seconds[-5:]}")

# %% [markdown]
# ---
#
# ## Integration with Timelines
#
# C-Maps can be attached to Timelines for coordinate conversion. This is covered in detail in the next tutorial (04_building_timelines), but here's a preview:

# %%
from timetoalign.timelines import Timeline

# Create a timeline in ticks
tl = Timeline(length=1920, unit="ticks", uid="midi_timeline")

# Attach a C-Map for tick -> quarter conversion
t2q = TicksToQuarters(ppq=480)
tl.add_conversion_map(t2q)

# Now we can convert coordinates using the timeline
ticks_value = 960
quarters_value = tl.convert_to(ticks_value, "quarters")
print(f"{ticks_value} ticks = {quarters_value} quarters")

# %% [markdown]
# ---
#
# ## Summary
#
# In this tutorial, we learned:
#
# 1. **ConversionMaps** transform coordinates between units
# 2. **ScalarMap**: Pure multiplication (`y = ax`)
# 3. **LinearMap**: Scale and offset (`y = ax + b`)
# 4. **ShiftMap**: Pure offset (`y = x + b`)
# 5. **TableMap**: Interpolation between anchor points
# 6. **ChainMap**: Compose multiple maps (`f(g(x))`)
# 7. **PiecewiseMap**: Different maps for different regions
# 8. **Convenience classes**: `TicksToQuarters`, `SamplesToSeconds`, etc.
#
# **Key Takeaway:**
# > ConversionMaps are the bridges between coordinate systems, enabling seamless translation across domains and units. They support both scalar and vectorized operations, and can be composed for complex conversions.

# %% [markdown]
# ## Next Steps
#
# - **04_building_timelines.ipynb**: Create timelines and attach C-Maps
# - **05_timestamps.ipynb**: Generate cross-section timestamps through timeline hierarchies

# %% [markdown]
# ---
#
# ## Exercise 1: MIDI Conversion Chain
#
# **Task:** A MIDI file has PPQ=960 and constant tempo of 90 BPM. Create a chain that converts ticks directly to seconds.
#
# **Hints:**
# 1. At 90 BPM, one quarter note = 60/90 = 0.667 seconds
# 2. Chain: ticks -> quarters -> seconds
#
# <details>
# <summary>Solution</summary>
#
# ```python
# # Parameters
# ppq = 960
# bpm = 90
# seconds_per_quarter = 60 / bpm  # 0.667 seconds
#
# # Build chain
# ticks_to_quarters = TicksToQuarters(ppq=ppq)
# quarters_to_seconds = ScalarMap(scalar=seconds_per_quarter)
#
# ticks_to_seconds = ticks_to_quarters >> quarters_to_seconds
#
# # Test
# print(f"960 ticks = {ticks_to_seconds(960):.3f} seconds")  # Should be 0.667
# print(f"1920 ticks = {ticks_to_seconds(1920):.3f} seconds")  # Should be 1.333
# ```
#
# </details>

# %%
# Your solution here


# %% [markdown]
# ---
#
# ## Exercise 2: Tempo Map
#
# **Task:** Create a TableMap for a piece with the following tempo structure:
# - Measures 1-4: 100 BPM
# - Measures 5-8: 80 BPM
# - Measures 9-12: 120 BPM
#
# Assume 4/4 time signature and PPQ=480.
#
# **Hints:**
# 1. Each measure = 4 quarters = 1920 ticks
# 2. Tempo changes occur at ticks 0, 7680 (measure 5), 15360 (measure 9)
#
# <details>
# <summary>Solution</summary>
#
# ```python
# # Tempo changes at measure boundaries
# # Measure 1: tick 0, Measure 5: tick 7680, Measure 9: tick 15360
#
# tempo_map = TableMap.from_tempo_changes(
#     tick_positions=[0, 7680, 15360],
#     tempos_bpm=[100.0, 80.0, 120.0],
#     ticks_per_quarter=480,
# )
#
# # Test: end of each section
# # End of measure 4 (tick 7680):
# # 16 quarters at 100 BPM = 16 * (60/100) = 9.6 seconds
# print(f"End of m.4 (tick 7680): {tempo_map(7680):.2f} seconds")
#
# # End of measure 8 (tick 15360):
# # First 4 measures: 9.6 seconds
# # Next 4 measures: 16 quarters at 80 BPM = 16 * (60/80) = 12 seconds
# # Total: 21.6 seconds
# print(f"End of m.8 (tick 15360): {tempo_map(15360):.2f} seconds")
# ```
#
# </details>

# %%
# Your solution here
