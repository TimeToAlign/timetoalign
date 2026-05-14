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


class IntervalPolicy(FancyStrEnum):
    """Policy for normalising interval events (end/duration consistency).

    When loading events, interval events may carry ``end``, ``duration``,
    or both.  This enum controls how the loader fills in missing values
    and what happens when both are present but inconsistent.

    Members:
        warn: (default) Prefer ``end``; compute ``duration = end - start``.
            If both are present and inconsistent, log a warning and
            recompute ``duration`` from ``end``.
        prefer_end: Silently prefer ``end``; recompute ``duration`` from
            ``end - start``, ignoring any supplied ``duration``.
        prefer_duration: Silently prefer ``duration``; recompute ``end``
            from ``start + duration``, ignoring any supplied ``end``.
        strict: Raise ``ValueError`` if both are present and inconsistent.
            Otherwise behave like ``warn`` (fill whichever is missing).
    """

    warn = auto()
    """Prefer end; warn on inconsistency."""

    prefer_end = auto()
    """Silently prefer end; always recompute duration."""

    prefer_duration = auto()
    """Silently prefer duration; always recompute end."""

    strict = auto()
    """Raise ValueError on inconsistency."""


class ColumnNaming(FancyStrEnum):
    """How to name columns in timestamp DataFrames.

    Controls the column header naming strategy for timestamp tables.

    Members:
        name: Use the human-readable name property (e.g., "Musical Holes Region").
            Falls back to ID if name is not set.
        id: Use the unique identifier (e.g., "dgt_holes").
    """

    name = auto()
    """Use human-readable name (with id fallback)."""

    id = auto()
    """Use unique identifier."""


class FlowControlType(FancyStrEnum):
    """Canonical taxonomy of flow control markers in musical scores.

    This enum provides a unified vocabulary for flow control across all loaders
    (MeasureMapLoader, TSVLoader, PartituraLoader, Music21Loader).

    **Design Principles**:

    1. **Types vs Names**: This enum defines marker TYPES, not instance names.
       Jump target markers (segno, coda, fine) are TYPES. Each marker INSTANCE
       has a NAME attribute (e.g., "coda", "codab", "segno2") that differentiates
       multiple markers of the same type. Jump instructions reference targets
       by NAME, which defaults to the type name but can be customized.

    2. **Structural vs Flow Control**: Some markers are purely structural (barlines),
       while others affect traversal (jumps, breaks). The `is_structural_marker`
       property distinguishes these.

    3. **Volta Model**: Volta (alternative ending) information is a MEASURE ATTRIBUTE,
       not a separate flow control type. Each measure has a `volta` field (1, 2, None)
       indicating which ending it belongs to. The repeat_end jump evaluates which
       volta to take based on pass count.

    **Taxonomy** (from TTA manuscript and MeasureMap paper):

    **Repeat Markers**:
    - repeat_start: Structural marker (||:) - target for repeat_end jumps
    - repeat_end: Jump instruction (:||) - triggers backward jump; MAY also
      constitute a section_break when it coincides with an end-type barline

    **Jump Instructions** (triggers navigation):
    - da_capo: Jump to beginning (D.C.)
    - dal_segno: Jump to marker named "segno" by default (D.S.)
    - dal_segno_al_coda: D.S., play until "coda" marker, then jump to coda section
    - dal_segno_al_fine: D.S., play until "fine" marker
    - da_capo_al_coda: D.C., play until "coda" marker, then jump to coda section
    - da_capo_al_fine: D.C., play until "fine" marker
    - to_coda: Jump to marker named "coda" by default

    **Jump Target Markers** (destinations - TYPE, instances have names):
    - segno: Target for dal_segno (instance name defaults to "segno")
    - coda: Target for to_coda (instance name defaults to "coda")
    - fine: End marker (instance name defaults to "fine")

    **Structural Breaks** (void contiguity - single instant, not start/end pair):
    - section_break: Voids contiguity at this instant (e.g., section boundary)

    **Structural Markers** (do NOT void contiguity, mark boundaries):
    - double_barline: Double bar line (structural boundary, not a break)
    - final_barline: Final bar line (end of piece)

    **Boundary Markers** (reference markers for addressing):
    - first_measure: First measure of piece (ms3 convention)
    - last_measure: Last measure of piece (ms3 convention)

    **Loader Mappings**:

    | FlowControlType | MeasureMap | ms3/TSV | partitura | music21 |
    |-----------------|------------|---------|-----------|---------|
    | repeat_start | start_repeat=true | repeats="start" | Repeat.start | leftBarline.type="heavy-light" |
    | repeat_end | end_repeat=true | repeats="end" | Repeat.end | rightBarline.type="light-heavy" |
    | da_capo | next=[1] pattern | jump_bwd="dacapo" | DaCapo | DaCapo |
    | dal_segno | next=[segno_mc] | jump_bwd="dalsegno" | DalSegno | DalSegno* |
    | to_coda | - | jump_fwd="tocoda" | ToCoda | Coda(type="to") |
    | fine | next=[-1] + marker | play_until="fine" | Fine | Fine |
    | segno | marker in JSON | marker="segno" | Segno | Segno |
    | coda | marker in JSON | marker="coda" | Coda | Coda |
    | section_break | - | breaks="section" | - | - |
    | double_barline | - | breaks="double" | - | barline.type="double" |
    | final_barline | - | - | - | barline.type="final" |
    """

    # Repeat markers
    repeat_start = auto()
    """Structural marker (||:) - target for repeat_end jumps."""
    repeat_end = auto()
    """Jump instruction (:||) - may also be a section_break when coinciding with end barline."""

    # Jump instructions
    da_capo = auto()
    """Jump to beginning (D.C.)"""
    dc = da_capo
    """Alias for da_capo"""

    dal_segno = auto()
    """Jump to segno marker by name (D.S.)"""
    ds = dal_segno
    """Alias for dal_segno"""

    dal_segno_al_coda = auto()
    """Jump to segno, play until coda, then jump to coda section (D.S. al Coda)"""
    dsac = dal_segno_al_coda
    """Alias for dal_segno_al_coda"""

    dal_segno_al_fine = auto()
    """Jump to segno, play until fine (D.S. al Fine)"""
    dsaf = dal_segno_al_fine
    """Alias for dal_segno_al_fine"""

    da_capo_al_coda = auto()
    """Jump to beginning, play until coda, then jump to coda section (D.C. al Coda)"""
    dcac = da_capo_al_coda
    """Alias for da_capo_al_coda"""

    da_capo_al_fine = auto()
    """Jump to beginning, play until fine (D.C. al Fine)"""
    dcaf = da_capo_al_fine
    """Alias for da_capo_al_fine"""

    to_coda = auto()
    """Jump to coda marker by name (typically to "codab", the second coda marker)"""

    # Jump target markers (TYPE - instances have names like "coda", "codab", "segno2")
    segno = auto()
    """Target marker TYPE for dal_segno (instance name defaults to "segno")"""

    coda = auto()
    """Target marker TYPE for coda symbols.

    In "D.S./D.C. al Coda" structures, there are typically TWO coda markers:
    - First coda marker (name="coda"): Where `to_coda` instruction is placed (JumpFrom).
      This marker becomes active after the D.S./D.C. jump.
    - Second coda marker (name="codab"): Where the jump lands (JumpTo).
      This is the beginning of the coda section. MuseScore uses "codab" as default name.

    Both markers have TYPE `coda` but different instance NAMES.
    """

    fine = auto()
    """End marker TYPE (instance name defaults to "fine")"""

    # Structural breaks (void contiguity - single instant)
    section_break = auto()
    """Single instant that voids contiguity (e.g., section boundary)"""

    # Structural markers (do NOT void contiguity)
    double_barline = auto()
    """Double bar line - structural boundary marker, does NOT void contiguity"""

    final_barline = auto()
    """Final bar line - end of piece marker"""

    # Boundary markers (for reference/addressing)
    first_measure = auto()
    """First measure of piece (ms3 convention)"""

    last_measure = auto()
    """Last measure of piece (ms3 convention)"""

    @classmethod
    def from_ms3_repeats(cls, value: str | None) -> "FlowControlType | None":
        """Convert ms3 'repeats' column value to FlowControlType.

        Args:
            value: Value from ms3 repeats column ("start", "end", "firstMeasure", etc.)

        Returns:
            Corresponding FlowControlType or None.
        """
        if not value:
            return None
        mapping = {
            "start": cls.repeat_start,
            "end": cls.repeat_end,
            "firstMeasure": cls.first_measure,
            "lastMeasure": cls.last_measure,
        }
        return mapping.get(value)

    @classmethod
    def from_ms3_breaks(cls, value: str | None) -> "FlowControlType | None":
        """Convert ms3 'breaks' column value to FlowControlType.

        Args:
            value: Value from ms3 breaks column ("section", "double", etc.)

        Returns:
            Corresponding FlowControlType or None.
        """
        if not value:
            return None
        mapping = {
            "section": cls.section_break,
            "double": cls.double_barline,
        }
        return mapping.get(value)

    @classmethod
    def from_measuremap(
        cls, start_repeat: bool = False, end_repeat: bool = False
    ) -> list["FlowControlType"]:
        """Convert MeasureMap flow control fields to FlowControlType list.

        Args:
            start_repeat: Whether start_repeat is true in MeasureMap.
            end_repeat: Whether end_repeat is true in MeasureMap.

        Returns:
            List of corresponding FlowControlTypes.
        """
        result = []
        if start_repeat:
            result.append(cls.repeat_start)
        if end_repeat:
            result.append(cls.repeat_end)
        return result

    @property
    def is_jump(self) -> bool:
        """Whether this marker triggers a jump to another location."""
        return self in {
            FlowControlType.repeat_end,
            FlowControlType.da_capo,
            FlowControlType.dal_segno,
            FlowControlType.dal_segno_al_coda,
            FlowControlType.dal_segno_al_fine,
            FlowControlType.da_capo_al_coda,
            FlowControlType.da_capo_al_fine,
            FlowControlType.to_coda,
        }

    @property
    def is_target(self) -> bool:
        """Whether this marker TYPE is a jump destination.

        Note: Actual target resolution uses instance NAMES, not just types.
        Multiple markers of the same type (e.g., two coda markers named
        "coda" and "codab") are differentiated by name.
        """
        return self in {
            FlowControlType.repeat_start,
            FlowControlType.segno,
            FlowControlType.coda,
        }

    @property
    def is_break(self) -> bool:
        """Whether this marker voids contiguity (from TTA manuscript).

        Note: repeat_end MAY also void contiguity when it coincides with
        an end-type barline, but this is context-dependent and not
        intrinsic to the type.
        """
        return self in {
            FlowControlType.fine,
            FlowControlType.section_break,
        }

    @property
    def is_structural_marker(self) -> bool:
        """Whether this is a structural marker that does NOT void contiguity."""
        return self in {
            FlowControlType.repeat_start,
            FlowControlType.double_barline,
            FlowControlType.final_barline,
            FlowControlType.first_measure,
            FlowControlType.last_measure,
        }


class InterpolationKind(FancyStrEnum):
    """Interpolation methods for TableMap.

    Attributes:
        linear: Linear interpolation between points.
        nearest: Nearest-neighbor interpolation.
        previous: Use the previous point's value (step function, left).
        next: Use the next point's value (step function, right).
    """

    linear = auto()
    nearest = auto()
    previous = auto()
    next = auto()


class ExtrapolationPolicy(FancyStrEnum):
    """How to handle values outside the table bounds.

    Attributes:
        error: Raise an error for out-of-bounds values.
        extrapolate: Extend the interpolation beyond bounds.
        constant: Use the boundary value (clamp).
        nan: Return NaN for out-of-bounds values.
    """

    error = auto()
    extrapolate = auto()
    constant = auto()
    nan = auto()


class ActivationCondition(FancyStrEnum):
    """When a flow control event becomes active.

    This determines on which traversal pass the event takes effect.
    """

    always = auto()
    """Always active (e.g., section end)."""

    first_n = auto()
    """Active on first N passes (e.g., repeat 2x)."""

    after_first = auto()
    """Active after first pass (e.g., second ending)."""

    after_dc_ds = auto()
    """Active after Da Capo or Dal Segno."""


class ColumnRole(FancyStrEnum):
    """Semantic role of a column in the table.

    Used for automatic role inference when columns are not explicitly specified.
    """

    # Core event identity
    id = auto()
    name = auto()
    event_type = auto()

    # Coordinates (primary timeline)
    start = auto()
    end = auto()
    duration = auto()
    instant = auto()

    # Conversion (C-Map target)
    cmap_target = auto()

    # Structure
    partition = auto()
    parent_id = auto()
    child_id = auto()
    segment_name = auto()
    region = auto()

    # Alignment
    match_ref = auto()

    # Generic data
    extra = auto()


class PartitionMode(FancyStrEnum):
    """How partition columns create timelines.

    separate: Each unique value creates an independent timeline with its own
              coordinate system. Coordinates are NOT comparable across partitions.
              Use for: Different recordings, different performers.

    children: Each unique value creates a child timeline that shares the parent's
              coordinate system. Coordinates ARE comparable (offset by parent position).
              Use for: Voices, instruments, staves within a score.
    """

    separate = auto()
    """Disparate coordinate systems."""

    children = auto()
    """Same coordinate system, parent-child relationship."""


class FlowMode(FancyStrEnum):
    """Flow computation modes.

    Different contexts require different unfoldings:

    Deterministic modes (must be identical across all loaders):
    - atomic: True atomic sections from FlowController (= mode=None)
    - printed: All bars as printed (no unfolding)
    - single: Single playthrough (last volta only)

    Contingent modes (may have alternatives if divergent):
    - default: Most complete flow (all repeats taken), equivalent to MS3
    - music21: music21's expandRepeats() - only if diverges from default
    - partitura_maximal: partitura's unfold_part_maximal() - only if diverges from default
    - partitura_minimal: partitura's atomic segments - only if diverges from atomic

    Other modes:
    - ms3: From ms3's *_unfolded.measures.tsv (gold standard for default)
    - custom: User-provided flow sequence
    """

    atomic = auto()
    default = auto()
    ms3 = auto()
    partitura_minimal = auto()
    partitura_maximal = auto()
    music21 = auto()
    printed = auto()
    single = auto()
    custom = auto()


class IncompletePosition(FancyStrEnum):
    """Position of an incomplete measure within the score.

    Used by IncompleteMeasure to classify why a measure is incomplete:
    - anacrusis: Pickup measure at the start of the piece
    - final: Final incomplete measure (often pairs with anacrusis)
    - split_first: First part of a split measure
    - split_second: Second part of a split measure
    - unknown: Position not yet determined
    """

    anacrusis = auto()
    final = auto()
    split_first = auto()
    split_second = auto()
    unknown = auto()
