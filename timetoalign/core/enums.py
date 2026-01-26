"""Enumerations for the TTA model.

This module defines the fundamental categorical types used throughout
the library: temporal domains, time units, number types, and event types.

The FancyStrEnum base class provides:
- Lowercase member names (via auto() from StrEnum)
- Abbreviation aliases (e.g., q = quarters, ms = milliseconds)
- Flexible instantiation from any alias
- get_abbreviations() for documentation
"""

from __future__ import annotations

from collections import defaultdict
from enum import Enum, StrEnum, auto
from fractions import Fraction


class FancyStrEnum(StrEnum):
    """A StrEnum with support for abbreviation aliases and flexible instantiation.

    Features:
        * Can be instantiated from any alias: FancyStrEnum("abbr") == FancyStrEnum.abbreviation
        * list(FancyStrEnum) returns only non-aliases (canonical members)
        * FancyStrEnum.get_abbreviations() returns a mapping from names to abbreviations

    Example:
        class Vocabulary(FancyStrEnum):
            abbreviation = auto()  # assigns the name as value (lowercase per StrEnum)
            abbr = abbreviation    # alias 1
            abb = abbreviation     # alias 2
    """

    @classmethod
    def _missing_(cls, value: object) -> "FancyStrEnum | None":
        """Allow instantiation from values, including aliases.

        Args:
            value: The value or name string to look up.

        Returns:
            The corresponding enum member, or None if not found.

        Raises:
            ValueError: If the value does not match any member or alias.
        """
        if isinstance(value, str):
            lower_value = value.lower()
            if lower_value in cls.__members__:
                name = cls.__members__[lower_value]
                return cls(name)
        abbrv = cls.get_abbreviations(string=True)
        raise ValueError(
            f"'{value}' is not a valid {cls.__name__}. Available values are: {abbrv}"
        )

    @classmethod
    def get_abbreviations(cls, string: bool = False) -> dict[str, list[str]] | str:
        """Returns a mapping from enum names/values to abbreviated alias values.

        Args:
            string: If True, return a formatted string instead of a dict.

        Returns:
            A dict mapping canonical names to lists of aliases, or a formatted string.
        """
        name2values: dict[str, list[str]] = defaultdict(list)
        for value, name in cls.__members__.items():
            name2values[name].append(value)
        abbreviations: dict[str, list[str]] = {}
        for name, values in name2values.items():
            # Sort by length descending, skip the first (canonical name)
            abbreviations[name] = sorted(values, key=lambda x: len(x), reverse=True)[1:]
        if not string:
            return abbreviations
        str_components = []
        for name, values in abbreviations.items():
            if not values:
                str_components.append(name)
                continue
            abbrev_str = ", ".join(values)
            str_components.append(f"{name} ({abbrev_str})")
        return ", ".join(str_components)

    def __repr__(self) -> str:
        return f'"{self.name}"'

    def __str__(self) -> str:
        return self.name


class Domain(FancyStrEnum):
    """The temporal domain of a timeline.

    Based on the TTA manuscript's three-domain model:
    - logical: Logical time domain (conceptualizing, reading)
    - physical: Physical time domain (hearing, seeing dynamic)
    - graphical: Graphical time domain (seeing static, spatial)
    """

    logical = auto()
    """Logical time domain for symbolic/musical data (beats, measures, ticks)."""
    lo = logical

    physical = auto()
    """Physical time domain for audio/time data (seconds, samples)."""
    ph = physical

    graphical = auto()
    """Graphical time domain for visual/spatial data (pixels, coordinates)."""
    gr = graphical


# Domain mappings for TimeUnit (module-level for efficiency)
_LOGICAL_UNITS: frozenset[str] = frozenset(
    {"beats", "measures", "quarters", "ticks", "number"}
)
_PHYSICAL_UNITS: frozenset[str] = frozenset(
    {"milliseconds", "seconds", "minutes", "samples", "frames"}
)
_GRAPHICAL_UNITS: frozenset[str] = frozenset(
    {"pixels", "meters", "centimeters", "millimeters", "inches", "points"}
)


class TimeUnit(FancyStrEnum):
    """Units of measurement for coordinates.

    Organized by domain. Each unit belongs to a specific domain.
    Aliases are provided for common abbreviations.
    """

    # generic
    number = auto()

    # musical domain
    beats = auto()
    """beats"""
    b = beats
    """beats"""

    measures = auto()
    """measures"""
    m = measures
    """measures"""

    quarters = auto()
    """quarter notes"""
    q = quarters
    """quarter notes"""

    ticks = auto()
    """ticks (MIDI's time unit)"""
    pulses = ticks
    """ticks (MIDI's time unit)"""
    divs = ticks
    """ticks (MIDI's time unit)"""

    # physical domain
    milliseconds = auto()
    """milliseconds"""
    ms = milliseconds
    """milliseconds"""

    seconds = auto()
    """seconds"""
    s = seconds
    """seconds"""

    minutes = auto()
    """minutes"""

    samples = auto()
    """samples"""

    frames = auto()
    """frames"""

    # graphical domain
    pixels = auto()
    """pixels"""
    px = pixels
    """pixels"""

    meters = auto()
    """meters"""

    centimeters = auto()
    """centimeters"""
    cm = centimeters
    """centimeters"""

    millimeters = auto()
    """millimeters"""
    mm = millimeters
    """millimeters"""

    inches = auto()
    """inches"""

    points = auto()
    """points"""
    pt = points
    """points"""

    @property
    def domain(self) -> Domain:
        """Return the domain this unit belongs to."""
        if self.name in _LOGICAL_UNITS:
            return Domain.logical
        elif self.name in _PHYSICAL_UNITS:
            return Domain.physical
        elif self.name in _GRAPHICAL_UNITS:
            return Domain.graphical
        raise ValueError(f"Unknown domain for unit {self.name}")  # pragma: no cover

    @property
    def is_discrete(self) -> bool:
        """Whether this unit is inherently discrete (integer-valued)."""
        return self in {
            TimeUnit.samples,
            TimeUnit.frames,
            TimeUnit.ticks,
            TimeUnit.pixels,
        }


class NumberType(Enum):
    """The numeric type used for coordinate values.

    Members can be instantiated both via NumberType("name") and NumberType(value).

    Example:
        NumberType(int) is NumberType("int")
        # True
        NumberType(int).value(1.4)
        # 1
    """

    int = int
    float = float
    fraction = Fraction

    @classmethod
    def _missing_(cls, value: object) -> "NumberType | None":
        if isinstance(value, str):
            for member in cls:
                if member.name == value:
                    return member
        return None

    @classmethod
    def from_number(cls, number: int | float | Fraction) -> "NumberType":
        """Create NumberType from a number instance."""
        return cls(type(number))

    @property
    def python_type(self) -> type:
        """Return the corresponding Python type."""
        return self.value

    def __str__(self) -> str:
        return self.name


class EventType(FancyStrEnum):
    """Whether an event is an instant or interval.

    From the TTA manuscript:
    - instant: Zero duration, associated with a single coordinate
    - interval: Has duration, defined by start and end coordinates
    """

    instant = auto()
    inst = instant

    interval = auto()
    intv = interval
