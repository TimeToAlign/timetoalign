"""Domain-specific Timeline subclasses.

This module provides the 6 concrete Timeline types:
- ContinuousLogicalTimeline, DiscreteLogicalTimeline
- ContinuousPhysicalTimeline, DiscretePhysicalTimeline
- ContinuousGraphicalTimeline, DiscreteGraphicalTimeline

Each class restricts valid units to its domain and modality,
and provides sensible defaults.
"""

from __future__ import annotations

from typing import ClassVar

from timetoalign.core import NumberType, TimeUnit

from .base import Timeline
from .mixins import ContinuousMixin, DiscreteMixin

# region Unit Sets by Domain

# Logical domain units (symbolic/musical time)
LOGICAL_UNITS: frozenset[TimeUnit] = frozenset(
    {
        TimeUnit.beats,
        TimeUnit.quarters,
        TimeUnit.measures,
        TimeUnit.ticks,
        TimeUnit.number,
    }
)

# Physical domain units (acoustic/real time)
PHYSICAL_UNITS: frozenset[TimeUnit] = frozenset(
    {
        TimeUnit.seconds,
        TimeUnit.milliseconds,
        TimeUnit.minutes,
        TimeUnit.samples,
        TimeUnit.frames,
    }
)

# Graphical domain units (visual/spatial)
GRAPHICAL_UNITS: frozenset[TimeUnit] = frozenset(
    {
        TimeUnit.pixels,
        TimeUnit.meters,
        TimeUnit.centimeters,
        TimeUnit.millimeters,
        TimeUnit.inches,
        TimeUnit.points,
    }
)

# Continuous vs discrete unit categorization
CONTINUOUS_LOGICAL_UNITS: frozenset[TimeUnit] = frozenset(
    {TimeUnit.beats, TimeUnit.quarters, TimeUnit.measures, TimeUnit.number}
)
DISCRETE_LOGICAL_UNITS: frozenset[TimeUnit] = frozenset({TimeUnit.ticks})

CONTINUOUS_PHYSICAL_UNITS: frozenset[TimeUnit] = frozenset(
    {TimeUnit.seconds, TimeUnit.milliseconds, TimeUnit.minutes}
)
DISCRETE_PHYSICAL_UNITS: frozenset[TimeUnit] = frozenset(
    {TimeUnit.samples, TimeUnit.frames}
)

CONTINUOUS_GRAPHICAL_UNITS: frozenset[TimeUnit] = frozenset(
    {
        TimeUnit.meters,
        TimeUnit.centimeters,
        TimeUnit.millimeters,
        TimeUnit.inches,
        TimeUnit.points,
    }
)
DISCRETE_GRAPHICAL_UNITS: frozenset[TimeUnit] = frozenset({TimeUnit.pixels})

# endregion


# region Domain Base Classes


class LogicalTimeline(Timeline):
    """A timeline representing logical/musical time.

    Logical timelines measure symbolic musical time such as beats,
    quarter notes, measures, or MIDI ticks. They are used for
    score-based representations of music.

    Allowed units: beats, quarters, measures, ticks, number.
    """

    _allowed_units: ClassVar[frozenset[TimeUnit]] = LOGICAL_UNITS
    _default_unit: ClassVar[TimeUnit] = TimeUnit.quarters


class PhysicalTimeline(Timeline):
    """A timeline representing physical/acoustic time.

    Physical timelines measure real-world time in units like
    seconds, milliseconds, or audio samples. They are used for
    performance and audio representations.

    Allowed units: seconds, milliseconds, minutes, samples, frames.
    """

    _allowed_units: ClassVar[frozenset[TimeUnit]] = PHYSICAL_UNITS
    _default_unit: ClassVar[TimeUnit] = TimeUnit.seconds


class GraphicalTimeline(Timeline):
    """A timeline representing graphical/spatial coordinates.

    Graphical timelines measure visual positions for score
    visualization and plotting. They can be in pixels or
    physical measurements.

    Allowed units: pixels, meters, centimeters, millimeters, inches, points.
    """

    _allowed_units: ClassVar[frozenset[TimeUnit]] = GRAPHICAL_UNITS
    _default_unit: ClassVar[TimeUnit] = TimeUnit.pixels


# endregion


# region Continuous Timeline Types


class ContinuousLogicalTimeline(ContinuousMixin, LogicalTimeline):
    """A logical timeline with continuous coordinates.

    Used for score representations where fractional beat positions
    are meaningful (e.g., a note at beat 2.5 or quarter beat 3/4).

    Default unit: quarters (quarter notes).
    Default number type: Fraction (for exact rhythmic representation).
    Allowed units: beats, quarters, measures, number (NOT ticks).
    """

    _allowed_units: ClassVar[frozenset[TimeUnit]] = CONTINUOUS_LOGICAL_UNITS
    _default_unit: ClassVar[TimeUnit] = TimeUnit.quarters
    _default_number_type: ClassVar[NumberType] = NumberType.fraction


class ContinuousPhysicalTimeline(ContinuousMixin, PhysicalTimeline):
    """A physical timeline with continuous coordinates.

    Used for acoustic time measurements where arbitrary precision
    is needed (e.g., note onsets at 1.234 seconds).

    Default unit: seconds.
    Default number type: float.
    Allowed units: seconds, milliseconds, minutes (NOT samples/frames).
    """

    _allowed_units: ClassVar[frozenset[TimeUnit]] = CONTINUOUS_PHYSICAL_UNITS
    _default_unit: ClassVar[TimeUnit] = TimeUnit.seconds
    _default_number_type: ClassVar[NumberType] = NumberType.float


class ContinuousGraphicalTimeline(ContinuousMixin, GraphicalTimeline):
    """A graphical timeline with continuous coordinates.

    Used for visualization where real-valued positions are needed
    (e.g., a note head at x=12.75 centimeters).

    Default unit: centimeters.
    Default number type: float.
    Allowed units: meters, centimeters, millimeters, inches, points.
    """

    _allowed_units: ClassVar[frozenset[TimeUnit]] = CONTINUOUS_GRAPHICAL_UNITS
    _default_unit: ClassVar[TimeUnit] = TimeUnit.centimeters
    _default_number_type: ClassVar[NumberType] = NumberType.float


# endregion


# region Discrete Timeline Types


class DiscreteLogicalTimeline(DiscreteMixin, LogicalTimeline):
    """A logical timeline with discrete (integer) coordinates.

    Used for MIDI-based representations where time is measured in
    quantized ticks. Essential for MIDI file parsing and generation.

    Default unit: ticks.
    Default number type: int.
    Allowed units: ticks only.
    """

    _allowed_units: ClassVar[frozenset[TimeUnit]] = DISCRETE_LOGICAL_UNITS
    _default_unit: ClassVar[TimeUnit] = TimeUnit.ticks
    _default_number_type: ClassVar[NumberType] = NumberType.int


class DiscretePhysicalTimeline(DiscreteMixin, PhysicalTimeline):
    """A physical timeline with discrete (integer) coordinates.

    Used for audio sample-based representations where time is
    measured in discrete sample indices or video frames.

    Default unit: samples.
    Default number type: int.
    Allowed units: samples, frames.
    """

    _allowed_units: ClassVar[frozenset[TimeUnit]] = DISCRETE_PHYSICAL_UNITS
    _default_unit: ClassVar[TimeUnit] = TimeUnit.samples
    _default_number_type: ClassVar[NumberType] = NumberType.int


class DiscreteGraphicalTimeline(DiscreteMixin, GraphicalTimeline):
    """A graphical timeline with discrete (integer) coordinates.

    Used for pixel-based visualization where positions are
    quantized to screen coordinates.

    Default unit: pixels.
    Default number type: int.
    Allowed units: pixels only.
    """

    _allowed_units: ClassVar[frozenset[TimeUnit]] = DISCRETE_GRAPHICAL_UNITS
    _default_unit: ClassVar[TimeUnit] = TimeUnit.pixels
    _default_number_type: ClassVar[NumberType] = NumberType.int


# endregion
