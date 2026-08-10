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
# # Timelines and Coordinates
#
# ## What you will build
#
# You will build two {{< glossary Timeline >}} objects for the same 30 seconds
# of audio. One is a continuous axis measured in seconds; the other is a
# {{< glossary Discrete >}} axis that counts whole samples. You will then
# attach a {{< glossary ConversionMap >}} that supplies a sample reading for
# the seconds axis without linking the two timeline objects.

# %% [markdown]
# ## Before you start
#
# Complete [Quickstart](tut00_quickstart.ipynb) first.

# %%
from fractions import Fraction

from timetoalign import (
    ContinuousGraphicalTimeline,
    ContinuousLogicalTimeline,
    ContinuousPhysicalTimeline,
    ConversionMap,
    Coordinate,
    DiscreteGraphicalTimeline,
    DiscreteLogicalTimeline,
    DiscretePhysicalTimeline,
    Domain,
    IdCoordinate,
    LinearMap,
    NumberType,
    ScalarMap,
    SecondsToSamples,
    TimeUnit,
)
from timetoalign.core import Duration
from timetoalign.maps import TicksToQuarters

# %% [markdown]
# ## Why a number is not a position
#
# A colleague sends you `2.5` and says, “the theme starts here.” Seconds,
# beats, or pixels? A number without a {{< glossary Coordinate >}} system is
# not information.

# %%
reported_position = 2.5
reported_position

# %% [markdown]
# The output gives only a magnitude. It cannot tell you where to listen, what
# point in the score to inspect, or where on an image to look.

# %% [markdown]
# ## Coordinate
#
# A coordinate combines a value with a unit. A `Duration` is the
# {{< glossary Length >}} between two positions: it describes an extent, not a
# place.

# %%
theme_start = Coordinate(reported_position, TimeUnit.seconds)
intro_duration = Duration(0.75, TimeUnit.seconds)
{
    "coordinate": theme_start,
    "value": theme_start.value,
    "unit": theme_start.unit,
    "duration": intro_duration,
}

# %% [markdown]
# `theme_start` now carries enough information to locate the onset on a
# seconds axis. Its value and unit remain separately available, while
# `intro_duration` represents a span of three quarters of a second.

# %% [markdown]
# ## Coordinate arithmetic
#
# Position arithmetic preserves that distinction. `Coordinate` is imported
# from `timetoalign`, whereas `Duration` currently comes from `timetoalign.core`.

# %%
theme_end = theme_start + intro_duration
elapsed = theme_end - theme_start
{
    "coordinate plus duration": theme_end,
    "returned type": type(theme_end),
    "coordinate minus coordinate": elapsed,
    "difference type": type(elapsed),
}

# %% [markdown]
# Adding a duration moves to another position, so the result is a
# `Coordinate`. Subtracting two positions asks how far apart they are, so the
# result is a `Duration`.

# %% [markdown]
# ## Three domains, two modalities
#
# {{< glossary Domain >}} and `TimeUnit` encode what an axis measures;
# `NumberType` records the Python numeric representation used for its values.
#
# | Domain | Typical units |
# |---|---|
# | Physical | seconds, samples |
# | Logical | quarters, ticks |
# | Graphical | pixels, points |

# %%
timeline_families = {
    Domain.physical: (ContinuousPhysicalTimeline, DiscretePhysicalTimeline),
    Domain.logical: (ContinuousLogicalTimeline, DiscreteLogicalTimeline),
    Domain.graphical: (ContinuousGraphicalTimeline, DiscreteGraphicalTimeline),
}
{
    "timeline classes": timeline_families,
    "number types": tuple(NumberType),
    "seconds are discrete": TimeUnit.seconds.is_discrete,
    "samples are discrete": TimeUnit.samples.is_discrete,
}

# %% [markdown]
# The six classes combine three domains with two modalities. A continuous unit
# admits any value between two positions; a discrete unit counts indivisible
# steps. Thus seconds normally use floating-point values, while samples,
# ticks, and pixels use integers.

# %% [markdown]
# ## Your first timeline
#
# A continuous physical timeline is a suitable model of an audio axis on which
# onsets may occur between any two measured positions.

# %%
audio = ContinuousPhysicalTimeline(length=30.0, uid="audio")
{
    "id": audio.id,
    "unit": audio.unit,
    "domain": audio.domain,
    "is continuous": audio.is_continuous,
    "start": audio.start,
    "end": audio.end,
    "length": audio.length,
    "physical timeline": isinstance(audio, timeline_families[Domain.physical]),
}

# %% [markdown]
# The timeline knows that it is the continuous physical axis called `audio`.
# Notice especially that `start`, `end`, and `length` render as `Coordinate`
# objects in seconds, rather than as unlabelled numbers.

# %% [markdown]
# ## The timeline makes coordinates for you
#
# Because `audio` knows its own unit, `make_coordinate()` can add that unit for
# you.

# %%
theme_on_audio = audio.make_coordinate(2.5)
theme_on_audio

# %% [markdown]
# The output displays `Coordinate(2.5, seconds)`. The unit is visible because
# the timeline returned a `Coordinate`, not a bare number.

# %% [markdown]
# ## Resolving a coordinate
#
# `get_coordinate()` resolves a compatible coordinate into a timeline's unit.
# Without a suitable conversion map, it refuses instead of guessing.

# %%
unresolved_sample = Coordinate(110250, TimeUnit.samples)
coordinate_error = None
try:
    audio.get_coordinate(unresolved_sample)
except ValueError as exc:
    coordinate_error = exc
coordinate_error

# %% [markdown]
# The rendered `ValueError` is deliberate. C-Map is the library's shorthand
# for a conversion map; without one from samples to seconds, the library cannot
# say what sample 110250 means on this timeline.

# %% [markdown]
# ## The discrete twin
#
# The same recording also needs a sample axis: researchers edit and annotate
# in seconds, but index an audio buffer in whole samples.

# %%
samples = DiscretePhysicalTimeline(length=1323000, uid="samples")
{
    "id": samples.id,
    "unit": samples.unit,
    "domain": samples.domain,
    "is discrete": samples.is_discrete,
    "start": samples.start,
    "end": samples.end,
    "length": samples.length,
}

# %% [markdown]
# At 44,100 samples per second, 30 seconds contains 1,323,000 samples. Every
# extent on this timeline is integer-valued because there is no position at a
# fractional sample index.

# %% [markdown]
# ## Conversion maps
#
# A conversion map supplies the rule for reading one axis in another unit. For
# this recording, the rule is 44,100 samples for every second.

# %%
seconds_to_samples = SecondsToSamples(sample_rate=44100)
audio.add_conversion_map(seconds_to_samples)
sample_theme_start = audio.convert_to(2.5, "samples")
sample_audio_end = audio.convert_to(audio.end, samples.unit)
registered_sample_map = audio.get_conversion_map("samples")
resolved_sample = audio.get_coordinate(unresolved_sample)
{
    "converted position": sample_theme_start,
    "integer value": isinstance(sample_theme_start.value, int),
    "converted endpoint": sample_audio_end,
    "same endpoint": sample_audio_end == samples.end,
    "registered map": registered_sample_map,
    "resolves earlier request": resolved_sample,
    "is a ConversionMap": isinstance(registered_sample_map, ConversionMap),
}

# %% [markdown]
# `convert_to()` returns `Coordinate(110250, samples)`: an integer-valued
# coordinate because samples are discrete. The converted endpoint agrees with
# the sample timeline's endpoint at 1,323,000. The library will not hand you a
# position such as sample 110250.5. `get_conversion_map()` retrieves the same
# registered rule, and that rule can now resolve the request refused above.

# %% [markdown]
# ## A C-Map belongs to one timeline
#
# A C-Map is a property of one timeline: it supplies a second reading of that
# timeline's axis. It is not, by itself, a link between two timeline objects.

# %%
{
    "attached to audio": audio.get_conversion_map(samples.unit)
    is registered_sample_map,
    "attached to samples": samples.get_conversion_map(audio.unit),
}

# %% [markdown]
# The map is present on `audio`; the `None` beside `samples` shows that the
# discrete timeline has no attached map of its own. Relating separate
# timelines is the job of a {{< glossary TimelineGroup >}}, introduced in the
# Timeline Groups tutorial.

# %% [markdown]
# ## Exact logical coordinates
#
# Musical subdivisions are ratios. A triplet quaver at one third of a quarter
# should remain exactly `Fraction(1, 3)`, rather than become a nearby float.

# %%
score = ContinuousLogicalTimeline(length=Fraction(4, 1), uid="score")
triplet_quaver = score.make_coordinate(Fraction(1, 3))
{
    "triplet coordinate": triplet_quaver,
    "stored value type": type(triplet_quaver.value),
    "logical timeline": isinstance(score, timeline_families[Domain.logical]),
}

# %% [markdown]
# The coordinate displays the exact fraction `1/3`, and its stored value is a
# `Fraction`. A continuous logical timeline can therefore represent the
# triplet without a floating-point approximation.

# %% [markdown]
# ## Quarters and ticks
#
# A ticks timeline counts discrete score positions. `TicksToQuarters` supplies
# the conversion between those integer ticks and exact quarter-note values.

# %%
ticks = DiscreteLogicalTimeline(length=1920, uid="ticks")
ticks_to_quarters = TicksToQuarters(ppq=480)
ticks.add_conversion_map(ticks_to_quarters)
triplet_tick = ticks.get_coordinate(triplet_quaver)
triplet_round_trip = ticks.convert_to(triplet_tick, TimeUnit.quarters)
{
    "triplet in ticks": triplet_tick,
    "back in quarters": triplet_round_trip,
    "returned value is exact": isinstance(triplet_round_trip.value, Fraction),
}

# %% [markdown]
# The triplet becomes integer tick 160 and converts directly back to
# `Coordinate(Fraction(1, 3), quarters)`. The `True` value confirms that the
# library itself preserved the fraction through the round trip.

# %% [markdown]
# ## Conversion-map shapes
#
# `ConversionMap` is the common interface for conversion rules. `ScalarMap`
# multiplies by a scale factor, while `LinearMap` can also apply an offset.

# %%
map_family = {
    "named map": ticks_to_quarters,
    "named map is a ScalarMap": isinstance(ticks_to_quarters, ScalarMap),
    "ScalarMap is a ConversionMap": issubclass(ScalarMap, ConversionMap),
    "LinearMap is a ConversionMap": issubclass(LinearMap, ConversionMap),
}
map_family

# %% [markdown]
# The named ticks-to-quarters rule is a `ScalarMap`. The two `True` hierarchy
# checks show that `ScalarMap` and `LinearMap` are both specialised forms of
# the general `ConversionMap` interface.

# %% [markdown]
# ## Naming a coordinate's home
#
# With more than one axis, even “2.5 seconds” may be ambiguous about which
# timeline owns the position. `IdCoordinate` adds the timeline identifier.

# %%
explicit_home = IdCoordinate(theme_on_audio.value, theme_on_audio.unit, audio.id)
named_home = theme_on_audio.with_timeline("audio")
{
    "constructor": explicit_home,
    "with_timeline": named_home,
    "same coordinate": explicit_home == named_home,
}

# %% [markdown]
# Both forms produce the same timeline-qualified coordinate. The current
# constructor order is `IdCoordinate(value, unit, timeline_id)`;
# `with_timeline()` is convenient when you already hold a plain coordinate.
#
# You will rarely need either, because an `IdCoordinate` is what the library's
# getters hand back by default — `get_coordinate()` above already returned one.
# Carrying the identity is what lets a retrieved coordinate be passed straight
# back as the next query without restating which axis it came from. Note that
# an `IdCoordinate` never compares equal to a plain `Coordinate`, in either
# direction: ask for `format="coordinate"` when you deliberately want the value
# and unit without the timeline.

# %% [markdown]
# ## What you learned
#
# - You can explain why a bare number cannot identify a position.
# - You can build a coordinate from a value and unit, and distinguish a duration from
#   a position.
# - You can use coordinate arithmetic and recognise its returned types.
# - You can distinguish physical, logical, and graphical domains in continuous and
#   discrete forms.
# - You can construct a continuous seconds timeline and inspect its coordinate-valued extents.
# - You can ask a timeline to make a coordinate in its own unit.
# - You can resolve compatible coordinates and understand why unsupported units are
#   refused.
# - You can construct the integer sample timeline for the same audio.
# - You can attach, retrieve, and use a seconds-to-samples conversion map.
# - You can distinguish a C-Map on one timeline from a relationship between separate timelines.
# - You can represent a rational logical position exactly.
# - You can convert between exact quarters and integer ticks.
# - You can recognise `ScalarMap`, `LinearMap`, and `ConversionMap` roles.
# - You can add a timeline identifier to a coordinate.

# %% [markdown]
# ## Next
#
# [Nesting and Timestamps](tut02_nesting_and_timestamps.ipynb)
#
# ## Go deeper
#
# - [Coordinate Math](../howto/how01_coordinate_math.ipynb)
# - [Manual Timeline Construction](../howto/how01_manual_timeline_construction.ipynb)
# - [Advanced C-Maps](../howto/how01_advanced_cmaps.ipynb)
