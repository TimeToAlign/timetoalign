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
# # How to Use Advanced Conversion Maps
#
# Complex `ConversionMap` chaining, piecewise maps, and vectorised
# operations for transforming coordinates.

# %%
import numpy as np
import pandas as pd

from timetoalign.maps import (
    LinearMap,
    PiecewiseMap,
    ScalarMap,
    SecondsToSamples,
    ShiftMap,
    TableMap,
    TicksToQuarters,
)

# %% [markdown]
# ## LinearMap: Scale and Offset
#
# Affine transformation: `y = scalar * x + offset`

# %%
recording_to_score = LinearMap(
    scalar=2.0,
    offset=0.5,
    source_unit="seconds",
    target_unit="seconds",
)

recording_times = [0.0, 0.5, 1.0, 1.5, 2.0]
score_times = [recording_to_score(t) for t in recording_times]

pd.DataFrame({"recording_time": recording_times, "score_time": score_times})

# %%
score_to_recording = recording_to_score.inverse()
{
    "forward": f"y = {recording_to_score.scalar}x + {recording_to_score.offset}",
    "inverse": f"y = {score_to_recording.scalar}x + {score_to_recording.offset}",
}

# %% [markdown]
# ## ShiftMap: Pure Offset
#
# `y = x + offset` --- useful for anacrusis adjustment.

# %%
anacrusis = ShiftMap(offset=-0.5, source_unit="quarters", target_unit="quarters")

notation_beats = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
pd.DataFrame(
    {
        "notation_beat": notation_beats,
        "adjusted_beat": [anacrusis(b) for b in notation_beats],
    }
)

# %% [markdown]
# ## TableMap: Non-Linear Mapping
#
# Explicit anchor points with interpolation. Ideal for tempo-varying
# conversions.

# %%
tempo_map = TableMap(
    x_values=[0, 480, 960, 1440],
    y_values=[0.0, 0.5, 1.5, 2.0],
    source_unit="ticks",
    target_unit="seconds",
)

tick_samples = [0, 240, 480, 720, 960, 1200, 1440]
pd.DataFrame(
    {
        "ticks": tick_samples,
        "seconds": [tempo_map(t) for t in tick_samples],
    }
)

# %%
# From MIDI-style tempo events
tempo_map = TableMap.from_tempo_changes(
    tick_positions=[0, 960],
    tempos_bpm=[120.0, 60.0],
    ticks_per_quarter=480,
)

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
# | Kind | Behaviour |
# |------|-----------|
# | `linear` | Straight line between anchors (default) |
# | `previous` | Hold the left anchor's value |
# | `next` | Jump to the right anchor's value |
# | `nearest` | Use whichever anchor is closer |

# %%
x = [0, 10, 20, 30]
y = [0, 3, 7, 10]

linear = TableMap(x_values=x, y_values=y, kind="linear")
previous = TableMap(x_values=x, y_values=y, kind="previous")
next_ = TableMap(x_values=x, y_values=y, kind="next")
nearest = TableMap(x_values=x, y_values=y, kind="nearest")

test_x = [5, 15, 25]
pd.DataFrame(
    {
        "x": test_x,
        "linear": [linear(v) for v in test_x],
        "previous": [previous(v) for v in test_x],
        "next": [next_(v) for v in test_x],
        "nearest": [nearest(v) for v in test_x],
    }
)

# %% [markdown]
# ## ChainMap: Composing Maps
#
# Chain maps with `>>` or `.then()`: `f(g(x))`

# %%
ticks_to_quarters = TicksToQuarters(ppq=480)
quarters_to_seconds = ScalarMap(
    scalar=0.5, source_unit="quarters", target_unit="seconds"
)

ticks_to_seconds = ticks_to_quarters >> quarters_to_seconds

ticks = [0, 480, 960, 1440, 1920]
pd.DataFrame(
    {
        "ticks": ticks,
        "quarters": [ticks_to_quarters(t) for t in ticks],
        "seconds": [ticks_to_seconds(t) for t in ticks],
    }
)

# %%
# Inverse of a chain reverses order and inverts each map
seconds_to_ticks = ticks_to_seconds.inverse()

seconds = [0.0, 0.5, 1.0, 1.5, 2.0]
pd.DataFrame(
    {
        "seconds": seconds,
        "ticks": [seconds_to_ticks(s) for s in seconds],
    }
)

# %% [markdown]
# ## PiecewiseMap: Region-Based Mapping

# %%
slow = ScalarMap(scalar=2.0)
normal = LinearMap(scalar=1.0, offset=10.0)
fast = LinearMap(scalar=0.5, offset=25.0)

piecewise = PiecewiseMap(
    breaks=[0.0, 10.0, 20.0, 30.0],
    maps=[slow, normal, fast],
)

x_values = [0, 5, 10, 15, 20, 25, 29.9]
pd.DataFrame(
    {
        "input": x_values,
        "output": [piecewise(x) for x in x_values],
        "region": ["slow", "slow", "normal", "normal", "fast", "fast", "fast"],
    }
)

# %% [markdown]
# ## Vectorised Array Operations

# %%
sample_rate = 44100
seconds = np.linspace(0, 60, 61)
s2samples = SecondsToSamples(sample_rate=sample_rate)

samples = s2samples(seconds)
{
    "converted": len(samples),
    "first_5": samples[:5].tolist(),
    "last_5": samples[-5:].tolist(),
}
