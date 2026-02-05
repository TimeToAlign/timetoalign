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
# # Core Concepts: Domains, Units, and Coordinates
#
# This tutorial introduces the fundamental building blocks of TimeToAlign!:
# Domains, TimeUnits, Coordinates, and Timelines.
#
# **Learning Objectives:**
# - Understand the three temporal domains (Physical, Logical, Graphical)
# - Work with TimeUnits and their domain compatibility
# - Create and manipulate Coordinate objects
# - Know the six Timeline types and when to use each
#
# **Prerequisites:**
# - Basic Python knowledge
# - TimeToAlign! installed (`pip install timetoalign`)

# %% [markdown]
# ## Why These Concepts Matter
#
# Music exists in multiple representations simultaneously:
#
# - **A score** represents music in symbolic notation (beats, measures, quarter notes)
# - **An audio recording** represents music in physical time (seconds, samples)
# - **A score image** represents music in visual space (pixels, coordinates)
#
# TimeToAlign! provides a unified framework for working across these
# representations. The key insight is that all musical time can be described
# using a small set of concepts:
#
# 1. **Domain**: Which representation are we working with?
# 2. **TimeUnit**: What are we measuring in?
# 3. **Coordinate**: A specific position within a domain
# 4. **Timeline**: An ordered axis of coordinates

# %% [markdown]
# ## Setup

# %%
from fractions import Fraction
from pprint import pprint

import pandas as pd

import timetoalign as tta
from timetoalign import Coordinate, Domain, NumberType, TimeUnit

tta.__version__

# %% [markdown]
# ---
#
# ## The Three Domains
#
# TimeToAlign! organizes all temporal data into three **Domains**:
#
# | Domain | Description | Examples |
# |--------|-------------|----------|
# | **Physical** | Real-world time, audio | Seconds, milliseconds, samples |
# | **Logical** | Symbolic, musical | Beats, quarters, ticks, measures |
# | **Graphical** | Visual, spatial | Pixels, centimeters, inches |
#
# Each domain represents a fundamentally different way of conceptualizing "time" in music.

# %%
# The Domain enum
list(Domain)

# %% jupyter={"is_executing": true}
# Domains have convenient aliases and can be constructed from strings
Domain.physical == Domain.ph == Domain("physical") == Domain("ph")

# %% [markdown]
# ### Understanding Each Domain
#
# **Physical Domain** (`Domain.physical` / `Domain.ph`)
# - Represents real-world, wall-clock time
# - Used for audio files, recordings, performances
# - Units: seconds, milliseconds, samples, frames
#
# **Logical Domain** (`Domain.logical` / `Domain.lo`)
# - Represents symbolic, musical time
# - Used for scores, MIDI files, notation
# - Units: beats, quarters, measures, ticks
# - Key feature: tempo-independent ("beat 1" is always "beat 1" regardless of tempo)
#
# **Graphical Domain** (`Domain.graphical` / `Domain.gr`)
# - Represents visual, spatial coordinates
# - Used for score images, sheet music PDFs, spectrograms
# - Units: pixels, centimeters, inches, points

# %% [markdown]
# ---
#
# ## TimeUnits
#
# A **TimeUnit** specifies the measuring unit for coordinates. Each unit
# belongs to exactly one domain and is either **continuous** (any real number)
# or **discrete** (countable integers).

# %%
# Build a summary table of all TimeUnits
unit_data = [
    {"unit": u.name, "domain": u.domain.name, "discrete": u.is_discrete}
    for u in TimeUnit
]
pd.DataFrame(unit_data).sort_values(["domain", "discrete", "unit"])

# %% [markdown]
# ### Discrete vs. Continuous Units
#
# | Continuous | Discrete |
# |------------|----------|
# | seconds (1.5s) | samples (44100) |
# | quarters (2.5q) | ticks (480) |
# | centimeters (3.2cm) | pixels (1920) |
#
# This distinction matters for arithmetic and timeline types.

# %%
# TimeUnits also have convenient aliases
aliases = {
    "TimeUnit.s": TimeUnit.seconds,
    "TimeUnit.ms": TimeUnit.milliseconds,
    "TimeUnit.q": TimeUnit.quarters,
    "TimeUnit.b": TimeUnit.beats,
    "TimeUnit.px": TimeUnit.pixels,
    "TimeUnit.pulses": TimeUnit.ticks,
    "TimeUnit.divs": TimeUnit.ticks,
}
pd.Series({k: v.name for k, v in aliases.items()}, name="resolves_to")

# %% [markdown]
# ---
#
# ## NumberType
#
# TimeToAlign! supports three numeric types for coordinate values:
#
# | Type | Python Type | Use Case |
# |------|-------------|----------|
# | `NumberType.int` | `int` | Discrete units (samples, ticks, pixels) |
# | `NumberType.float` | `float` | Physical time (seconds, milliseconds) |
# | `NumberType.fraction` | `Fraction` | Exact rational values (beats, quarters) |
#
# The `Fraction` type is particularly important for musical time, where
# triplets, dotted notes, and complex subdivisions require exact representation.

# %%
# NumberType can be inferred from values
{
    "from int": NumberType.from_number(42),
    "from float": NumberType.from_number(3.14),
    "from Fraction": NumberType.from_number(Fraction(3, 4)),
}

# %% [markdown]
# ### Why Fractions Matter for Musical Time
#
# Floating-point numbers accumulate small errors when summed repeatedly.
# Consider a septuplet (7 notes spanning 4 beats) - each note is exactly
# 4/7 beats:

# %%
# Float vs Fraction precision - summing reveals accumulated error
septuplet_float = 4 / 7  # 7 notes spanning 4 beats
septuplet_fraction = Fraction(4, 7)

# Sum 7 septuplets: should equal exactly 4 beats
float_sum = sum(septuplet_float for _ in range(7))
fraction_sum = sum(septuplet_fraction for _ in range(7))

{
    "septuplet_float": septuplet_float,
    "septuplet_fraction": septuplet_fraction,
    "7x_float": float_sum,
    "7x_float == 4": float_sum == 4,  # False due to floating-point error!
    "7x_fraction": fraction_sum,
    "7x_fraction == 4": fraction_sum == 4,  # True - exact!
}

# %% [markdown]
# ---
#
# ## Coordinates
#
# A **Coordinate** is the fundamental building block of TimeToAlign!.
# It pairs a numeric value with a TimeUnit.
#
# ```python
# Coordinate(value, unit)
# ```
#
# Coordinates are:
# - **Immutable** (frozen dataclass)
# - **Hashable** (can be used in sets and as dict keys)
# - **Type-safe** (arithmetic respects units)

# %%
# Creating coordinates with different value types
c1 = Coordinate(120, TimeUnit.ticks)
c2 = Coordinate(1.5, TimeUnit.seconds)
c3 = Coordinate(Fraction(3, 4), TimeUnit.quarters)

c1, c2, c3

# %%
# Coordinate properties are derived from value and unit
{
    "value": c3.value,
    "unit": c3.unit,
    "number_type": c3.number_type,
    "domain": c3.domain,
}

# %%
# String representations
{"str": str(c3), "repr": repr(c3)}

# %% [markdown]
# ### Coordinate Arithmetic
#
# Coordinates support arithmetic operations with type safety:
#
# - **Addition/Subtraction**: Between coordinates with the **same unit**
# - **Multiplication/Division**: With **scalars** (int, float, Fraction)

# %%
# Comparison operators
x = Coordinate(10, TimeUnit.seconds)
y = Coordinate(5, TimeUnit.seconds)

{"x > y": x > y, "x == y": x == y, "x <= y": x <= y}

# %%
# Unit mismatch raises TypeError - you cannot add ticks and seconds directly
ticks = Coordinate(480, TimeUnit.ticks)
seconds = Coordinate(1.0, TimeUnit.seconds)

try:
    ticks + seconds
except TypeError as e:
    print(f"TypeError: {e}")

# %% [markdown]
# ### Coordinate Type Conversions and Utilities

# %%
c = Coordinate(Fraction(7, 4), TimeUnit.quarters)  # 1.75 quarters

{
    "original": c,
    "to_float()": c.to_float(),
    "to_int()": c.to_int(),  # default: truncates toward zero
    "to_int('round')": c.to_int("round"),  # round to nearest
    "to_int('floor')": c.to_int("floor"),  # round toward -inf
    "to_int('ceil')": c.to_int("ceil"),  # round toward +inf
    "to_fraction()": c.to_fraction(),
}

# %%
# Creating modified copies (coordinates are immutable)
original = Coordinate(100, TimeUnit.ticks)

{
    "original": original,
    "with_value(200)": original.with_value(200),
    "with_unit(samples)": original.with_unit(
        TimeUnit.samples
    ),  # Note: does NOT convert!
}

# %% [markdown]
# ---
#
# ## The Six Timeline Types
#
# Combining the 3 domains with continuous/discrete variants gives us **6 Timeline types**:
#
# | Domain | Continuous | Discrete |
# |--------|------------|----------|
# | Physical | `ContinuousPhysicalTimeline` | `DiscretePhysicalTimeline` |
# | Logical | `ContinuousLogicalTimeline` | `DiscreteLogicalTimeline` |
# | Graphical | `ContinuousGraphicalTimeline` | `DiscreteGraphicalTimeline` |

# %%
from timetoalign import (  # noqa: E402
    ContinuousGraphicalTimeline,
    ContinuousLogicalTimeline,
    ContinuousPhysicalTimeline,
    DiscreteGraphicalTimeline,
    DiscreteLogicalTimeline,
    DiscretePhysicalTimeline,
)

# %%
# Each timeline type has sensible defaults
timeline_classes = [
    ContinuousPhysicalTimeline,
    DiscretePhysicalTimeline,
    ContinuousLogicalTimeline,
    DiscreteLogicalTimeline,
    ContinuousGraphicalTimeline,
    DiscreteGraphicalTimeline,
]

pd.DataFrame(
    [
        {
            "class": cls.__name__,
            "domain": (tl := cls(length=1)).domain.name,
            "unit": tl.unit.name,
            "number_type": tl.number_type.name,
        }
        for cls in timeline_classes
    ]
)

# %% [markdown]
# ### Creating Timelines
#
# Timelines require a `length` parameter (or can be created empty):

# %%
# Create timelines for different scenarios
score_tl = ContinuousLogicalTimeline(length=Fraction(16, 1))  # 16 quarter notes
midi_tl = DiscreteLogicalTimeline(length=1920)  # 1920 ticks
audio_tl = ContinuousPhysicalTimeline(length=10.0)  # 10 seconds
image_tl = DiscreteGraphicalTimeline(length=1920)  # 1920 pixels

{
    "score": score_tl.length,
    "midi": midi_tl.length,
    "audio": audio_tl.length,
    "image": image_tl.length,
}

# %%
# Timeline properties
{
    "id": score_tl.id,
    "domain": score_tl.domain,
    "unit": score_tl.unit,
    "number_type": score_tl.number_type,
    "origin": score_tl.origin,
    "length": score_tl.length,
    "is_locked": score_tl.is_locked,
    "n_events": score_tl.n_events,
}

# %% [markdown]
# ### When to Use Each Timeline Type
#
# | Use Case | Timeline Type | Why |
# |----------|---------------|-----|
# | MusicXML/MEI scores | `ContinuousLogicalTimeline` | Exact beat fractions |
# | MIDI files | `DiscreteLogicalTimeline` | Integer tick resolution |
# | Audio analysis | `ContinuousPhysicalTimeline` | Floating-point seconds |
# | Sample-accurate audio | `DiscretePhysicalTimeline` | Integer samples/frames |
# | Score images | `DiscreteGraphicalTimeline` | Integer pixel positions |
# | Scalable graphics | `ContinuousGraphicalTimeline` | Real-valued coordinates |

# %%
# Timelines can create coordinates in their native unit
{
    "score_tl.make_coordinate(4)": score_tl.make_coordinate(4),
    "midi_tl.make_coordinate(480)": midi_tl.make_coordinate(480),
    "audio_tl.make_coordinate(2.5)": audio_tl.make_coordinate(2.5),
}

# %%
# Get a summary of timeline state
pprint(score_tl.summary())

# %% [markdown]
# ---
#
# ## Summary
#
# In this tutorial, we covered the foundational concepts of TimeToAlign!:
#
# 1. **Domains**: Physical, Logical, and Graphical - three ways of representing musical time
# 2. **TimeUnits**: Measuring units (seconds, quarters, pixels, etc.) tied to specific domains
# 3. **NumberType**: Integer, float, or fraction - choose based on required precision
# 4. **Coordinates**: Immutable value+unit pairs with type-safe arithmetic
# 5. **Timelines**: Six types combining domain × continuous/discrete
#
# **Key Takeaway:**
# > A Coordinate pairs a numeric value with a unit, ensuring type-safe
# > temporal arithmetic. Timelines organize coordinates into a consistent
# > structure for events.

# %% [markdown]
# ## Next Steps
#
# - **02_loading_data.ipynb**: Load real music data into EventStores
# - **03_conversion_maps.ipynb**: Convert coordinates between units and domains

# %% [markdown]
# ---
#
# ## Exercise 1: Coordinate Arithmetic
#
# **Task:** A MIDI file uses 480 ticks per quarter note (PPQN). Calculate:
#
# 1. How many ticks is 4 quarter notes?
# 2. If an event starts at tick 720, what quarter note position is that?
# 3. What is the duration in ticks of a dotted half note (3 quarter notes)?
#
# **Hints:**
# 1. Use `Coordinate` objects with `TimeUnit.ticks`
# 2. Remember: 1 quarter = 480 ticks
#
# <details>
# <summary>Solution</summary>
#
# ```python
# ppqn = 480  # ticks per quarter note
#
# # 1. Four quarter notes in ticks
# four_quarters = Coordinate(4 * ppqn, TimeUnit.ticks)
#
# # 2. Tick 720 in quarters
# tick_720 = 720
# quarter_position = tick_720 / ppqn
#
# # 3. Dotted half note (3 quarters) in ticks
# dotted_half = Coordinate(3 * ppqn, TimeUnit.ticks)
#
# {"4 quarters": four_quarters, "tick 720 in quarters": quarter_position,
# #  "dotted half": dotted_half}
# ```
#
# </details>

# %%
# Your solution here


# %% [markdown]
# ---
#
# ## Exercise 2: Choosing the Right Timeline
#
# **Task:** For each scenario, identify the most appropriate timeline type:
#
# 1. Analyzing a WAV audio file at 44.1kHz sample rate with sample-level precision
# 2. Representing a MuseScore file with triplets and complex rhythms
# 3. A PNG image of a musical score (1920x1080 pixels)
# 4. Real-time audio playback position in a media player
#
# <details>
# <summary>Solution</summary>
#
# 1. **DiscretePhysicalTimeline** - Sample-level precision requires integer sample indices
# 2. **ContinuousLogicalTimeline** - Triplets need exact fraction representation (Fraction(1,3))
# 3. **DiscreteGraphicalTimeline** - Pixels are integers
# 4. **ContinuousPhysicalTimeline** - Playback position is floating-point seconds
#
# ```python
# # 1. Audio at sample level
# audio_samples = DiscretePhysicalTimeline(length=44100*10)  # 10 seconds
#
# # 2. Score with triplets
# score = ContinuousLogicalTimeline(length=Fraction(32))  # 32 quarters
# triplet = score.make_coordinate(Fraction(1, 3))
#
# # 3. Score image
# image = DiscreteGraphicalTimeline(length=1920)
#
# # 4. Playback
# playback = ContinuousPhysicalTimeline(length=180.0)  # 3 minutes
# current_pos = playback.make_coordinate(45.7)
#
# {"audio": audio_samples.unit, "triplet": triplet, "image": image.unit, "playback": current_pos}
# ```
#
# </details>

# %%
# Your solution here
