"""Protocols for semantic type classification in Time To Align!

This module defines the structural typing contracts (Protocols) that unify
scalar-level types (e.g., Coordinate) and columnar-level types (e.g.,
CoordinateField) under a single interface.

Hierarchy Overview::

    SemanticTypeLike                       Root protocol
    ├── CoordinateLike[V]                  Coordinate-bearing objects
    ├── TimedObjectLike                    Objects with temporal position
    │   ├── InstantEventLike              Single-instant events
    │   └── IntervalEventLike             Interval [start, end) events
    │       ├── NoteLike                  Notes/rests
    │       ├── MeasureLike               Measures
    │       └── HarmonyLabelLike          Harmony annotations (label on timeline)
    │           └── PitchBasedHarmonyLike  (modelled after OHR)
    │               └── WesternTertianHarmonyLike
    │                   └── RomanNumeralHarmonyLike
    │                       └── DcmlHarmonyLike
    └── PitchLike                          Pitch-bearing objects
        ├── GenericPitchLike              Pitch class only
        │   └── SpelledPitchClassLike     + spelling (step, alter, fifths)
        ├── SpecificPitchClassLike        + octave (midi_number)
        │   └── EnharmonicPitchLike       + spelling (step, alter, fifths, cents)
        └── (future: MicrotonalPitchLike)

The ``TwelveTETPitchMixin`` is a concrete mixin (not a Protocol) that adds
12-TET pitch methods (``pitch_class``, ``to()``, ``get()``) to scalar classes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar, runtime_checkable

from .enums import Domain, NumberType, TimeUnit

if TYPE_CHECKING:
    from .ids import ScopedId

V = TypeVar("V", covariant=True)


# region Root Protocol


@runtime_checkable
class SemanticTypeLike(Protocol):
    """Protocol for objects that carry semantic type metadata.

    Any object with a ``semantic_type`` property and a
    ``metadata_dict()`` method satisfies this protocol.  This is the
    root contract shared by both scalar types (``Coordinate``) and
    columnar types (future ``SemanticField`` subclasses).

    Attributes:
        semantic_type: Canonical name of the semantic type
            (e.g., ``"Coordinate"``).

    Examples:
        >>> from timetoalign.core.types import Coordinate
        >>> from timetoalign.core.enums import TimeUnit
        >>> coord = Coordinate(1.5, TimeUnit.seconds)
        >>> isinstance(coord, SemanticTypeLike)
        True
        >>> coord.semantic_type
        'Coordinate'
    """

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        ...

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract."""
        ...


# endregion Root Protocol

# region Coordinate Protocol


@runtime_checkable
class CoordinateLike(SemanticTypeLike, Protocol[V]):
    """Protocol for coordinate-bearing objects.

    Extends ``SemanticTypeLike`` with properties that describe a
    coordinate's value, unit, domain, and numeric representation.
    The type parameter ``V`` is covariant and unbound -- it may be a
    ``CoordinateValue`` (for scalars) or a ``StructField`` (for
    columnar fields).

    The existing ``Coordinate`` frozen dataclass satisfies this
    protocol structurally with no modifications.

    Attributes:
        value: The underlying value (scalar or columnar).
        unit: The time unit of this coordinate.
        domain: The temporal domain (logical, physical, graphical).
        number_type: The numeric representation (int, float, fraction).
    """

    @property
    def value(self) -> V:
        """The underlying value."""
        ...

    @property
    def unit(self) -> TimeUnit:
        """The time unit of this coordinate."""
        ...

    @property
    def domain(self) -> Domain:
        """The temporal domain this coordinate belongs to."""
        ...

    @property
    def number_type(self) -> NumberType:
        """The numeric type used for this coordinate's values."""
        ...


# endregion Coordinate Protocol

# region Temporal Protocols


@runtime_checkable
class TimedObjectLike(SemanticTypeLike, Protocol):
    """Protocol for any object with a temporal position.

    Uses the canonical TTA model names: ``start`` (StartInstant)
    and ``end`` (EndInstant), matching the storage schema in
    ``EventData`` (columns ``start``, ``end``, ``duration``).
    """

    @property
    def start(self) -> CoordinateLike:  # type: ignore[type-arg]
        """The temporal position (StartInstant)."""
        ...


@runtime_checkable
class InstantEventLike(TimedObjectLike, Protocol):
    """A timed object at a single Instant (no duration).

    Only ``start`` is required (inherited from ``TimedObjectLike``).
    """

    pass


@runtime_checkable
class IntervalEventLike(TimedObjectLike, Protocol):
    """A timed object spanning an interval [start, end).

    Uses the canonical TTA model names from AGENTS.md Section 1.3:
    StartInstant -> ``start``, EndInstant -> ``end``.
    Intervals are left-inclusive, right-exclusive ``[start, end)``.
    """

    @property
    def end(self) -> CoordinateLike | None:  # type: ignore[type-arg]
        """The end position (EndInstant), or ``None``."""
        ...

    @property
    def duration(self) -> CoordinateLike | None:  # type: ignore[type-arg]
        """The duration as a ``Coordinate``, or ``None``."""
        ...


# endregion Temporal Protocols

# region Pitch Protocols


@runtime_checkable
class PitchLike(SemanticTypeLike, Protocol):
    """Abstract root for ALL pitch-like objects.

    Deliberately minimal: does not require ``pitch_class`` or
    ``midi_number``.  12-TET capabilities are added via
    ``TwelveTETPitchMixin``.  This allows future microtonal pitch
    systems to satisfy ``PitchLike`` without implementing 12-TET
    concepts.
    """

    pass


@runtime_checkable
class GenericPitchLike(PitchLike, Protocol):
    """Pitch class only (no octave, no spelling).

    The minimal 12-TET pitch representation: just the pitch class
    (chroma, 0-11).
    """

    @property
    def pitch_class(self) -> int:
        """Pitch class (0-11, C=0)."""
        ...


@runtime_checkable
class SpelledPitchClassLike(GenericPitchLike, Protocol):
    """Pitch class with spelling (e.g., C\u266f vs D\u266d).

    Adds enharmonic identity to the generic pitch class.
    """

    @property
    def step(self) -> str:
        """Generic pitch class as letter (``"C"``, ``"D"``, etc.)."""
        ...

    @property
    def alter(self) -> int:
        """Accidental in semitones (-1=flat, 0=natural, +1=sharp)."""
        ...

    @property
    def fifths(self) -> int:
        """Position on the line of fifths."""
        ...


@runtime_checkable
class SpecificPitchClassLike(PitchLike, Protocol):
    """Full pitch with octave (no spelling).

    Canonical name: ``SpecificPitchClassLike``.
    The ``MidiPitch`` scalar (alias ``SpecificPitch``) satisfies this.
    """

    @property
    def midi_number(self) -> int:
        """MIDI note number (0-127)."""
        ...

    @property
    def pitch_class(self) -> int:
        """Pitch class (0-11, C=0)."""
        ...

    @property
    def octave(self) -> int:
        """Octave number (C4 = octave 4)."""
        ...


@runtime_checkable
class EnharmonicPitchLike(SpecificPitchClassLike, Protocol):
    """Full pitch with spelling (C\u266f4 vs D\u266d4).

    The ``SpelledPitch`` scalar (alias ``EnharmonicPitch``) satisfies
    this protocol.
    """

    @property
    def step(self) -> str:
        """Generic pitch class as letter."""
        ...

    @property
    def alter(self) -> int:
        """Accidental in semitones."""
        ...

    @property
    def fifths(self) -> int:
        """Position on the line of fifths."""
        ...

    @property
    def cents(self) -> float:
        """Cents value."""
        ...


# endregion Pitch Protocols

# region Note Protocol


@runtime_checkable
class NoteLike(IntervalEventLike, Protocol):
    """Protocol for note/rest events.

    Ties pitch information to an interval event.  Temporal fields
    (``start``, ``end``, ``duration``) come from ``IntervalEventLike``.

    Attributes:
        pitch: The pitch of the note, or ``None`` for rests.
        voice: Voice number, or ``None``.
        staff: Staff number, or ``None``.
        velocity: MIDI velocity (0-127), or ``None``.
        instrument: Instrument name/identifier, or ``None``.
        is_rest: ``True`` if this event is a rest.
    """

    @property
    def pitch(self) -> PitchLike | None:
        """The pitch of the note, or ``None`` for rests."""
        ...

    @property
    def voice(self) -> int | None:
        """Voice number, or ``None``."""
        ...

    @property
    def staff(self) -> int | None:
        """Staff number, or ``None``."""
        ...

    @property
    def velocity(self) -> int | None:
        """MIDI velocity (0-127), or ``None``."""
        ...

    @property
    def instrument(self) -> str | None:
        """Instrument name/identifier, or ``None``."""
        ...

    @property
    def is_rest(self) -> bool:
        """``True`` if this event is a rest (no pitch)."""
        ...


# endregion Note Protocol

# region Measure Protocol


@runtime_checkable
class MeasureLike(IntervalEventLike, Protocol):
    """Protocol for measure boundary events.

    Aligned with the MeasureMap specification.  Temporal fields
    (``start``, ``end``, ``duration``) come from ``IntervalEventLike``.

    The ``id`` field is the unique measure identifier (called ``ID``
    in MeasureMap, ``mc`` in DCML).  It is monotonically increasing
    and 1-indexed.

    Attributes:
        id: Measure identifier (monotonically increasing, 1-indexed).
            Called ``ID`` in MeasureMap, ``mc`` in DCML.
        mn: Measure Number label (may have suffix, e.g. ``"19a"``).
        time_signature: Tuple of (numerator, denominator).
        key_signature: Key signature string, or ``None``.
        nominal_length: Expected duration from time signature.
        actual_length: Real duration (may differ for anacrusis).
        start_repeat: Whether this bar has a repeat start marker.
        end_repeat: Whether this bar has a repeat end marker.
        next_ids: Possible successor identifiers (``ScopedId``), or ``None``.
        volta: Ending number (1, 2, ...), or ``None``.
    """

    @property
    def id(self) -> int:
        """Measure identifier (monotonically increasing, 1-indexed)."""
        ...

    @property
    def mn(self) -> str:
        """Measure Number label."""
        ...

    @property
    def time_signature(self) -> tuple[int, int]:
        """Time signature as (numerator, denominator)."""
        ...

    @property
    def key_signature(self) -> str | None:
        """Key signature string, or ``None``."""
        ...

    @property
    def nominal_length(self) -> float | None:
        """Expected duration from time signature, or ``None``."""
        ...

    @property
    def actual_length(self) -> float | None:
        """Real duration (may differ for anacrusis), or ``None``."""
        ...

    @property
    def start_repeat(self) -> bool:
        """Whether this bar has a repeat start marker (``||:``)."""
        ...

    @property
    def end_repeat(self) -> bool:
        """Whether this bar has a repeat end marker (``:||``)."""
        ...

    @property
    def next_ids(self) -> tuple[ScopedId, ...] | None:
        """Possible successor identifiers, or ``None``."""
        ...

    @property
    def volta(self) -> int | None:
        """Ending number (1, 2, ...), or ``None``."""
        ...


# endregion Measure Protocol

# region Harmony Protocols


@runtime_checkable
class HarmonyLabelLike(IntervalEventLike, Protocol):
    """Abstract root for all harmony annotations on a timeline.

    A harmony label ties a harmonic analysis to a temporal interval.
    Minimal schema: a label string and a standard identifier.
    Temporal fields (``start``, ``end``, ``duration``) come from
    ``IntervalEventLike``.

    This is called ``HarmonyLabelLike`` (not ``HarmonyLike``) because
    it represents a label placed on a timeline, not the harmonic
    object itself.  The ``.to_ohr()`` method bridges to FlexOHR's
    rich harmonic model.
    """

    @property
    def label(self) -> str:
        """The full harmony label string."""
        ...

    @property
    def standard(self) -> str:
        """Codec identifier (e.g., ``"dcml"``, ``"chord_symbol"``)."""
        ...


# Backward-compat alias
HarmonyLike = HarmonyLabelLike


@runtime_checkable
class PitchBasedHarmonyLike(HarmonyLabelLike, Protocol):
    """Harmony grounded in pitch, modelled after OHR.

    An OHR (Object of Harmonic Reference) has three components:
    - **reference component**: the root pitch
    - **reference OHR**: the bass (which may differ from root in inversions)
    - **body**: the chord quality describing the intervallic structure

    This protocol captures the minimal pitch-based properties.
    """

    @property
    def root(self) -> PitchLike | None:
        """Root pitch (reference component), or ``None``."""
        ...

    @property
    def bass(self) -> PitchLike | None:
        """Bass note (reference OHR), or ``None``."""
        ...


@runtime_checkable
class WesternTertianHarmonyLike(PitchBasedHarmonyLike, Protocol):
    """Western tertian chord model.

    Minimal schema adds: chord type and inversion.  Everything else
    (which notes are in the chord, voicing, etc.) can be inferred from
    root + chord_type + inversion.
    """

    @property
    def chord_type(self) -> str:
        """Chord type (``"M"``, ``"m"``, ``"o"``, ``"+"``, ``"Mm7"``, etc.)."""
        ...

    @property
    def inversion(self) -> int | None:
        """Inversion number, or ``None``."""
        ...


@runtime_checkable
class RomanNumeralHarmonyLike(WesternTertianHarmonyLike, Protocol):
    """Roman-numeral analysis.

    Minimal schema adds: the numeral itself, plus localkey and globalkey.
    """

    @property
    def numeral(self) -> str:
        """Roman numeral (``"I"``, ``"ii"``, ``"V"``, etc.)."""
        ...

    @property
    def localkey(self) -> str:
        """Local key at this position (e.g., ``"IV"``)."""
        ...

    @property
    def globalkey(self) -> str:
        """Global key of the piece (e.g., ``"C"``)."""
        ...


@runtime_checkable
class DcmlHarmonyLike(RomanNumeralHarmonyLike, Protocol):
    """DCML codec specifics.

    Named ``DcmlHarmonyLike`` (not ``DcmlLabelLike``) because this
    represents the DCML-specific harmonic annotation model.

    The ``pedal`` concept is intentionally minimal here; full
    pedal-tone semantics (embedding chord progressions over a pedal
    as a horizontal sequence of OHRs) will co-evolve with FlexOHR.
    """

    @property
    def tonicized_key(self) -> str | None:
        """Tonicized key (DCML ``relativeroot``), or ``None``."""
        ...

    @property
    def pedal(self) -> str | None:
        """Pedal tone, or ``None``."""
        ...


# Backward-compat alias
DcmlLabelLike = DcmlHarmonyLike

# endregion Harmony Protocols

# region Pitch Mixin


class TwelveTETPitchMixin:
    """Concrete mixin adding 12-TET pitch methods.

    Not a Protocol -- a mixin that provides ``pitch_class``, a unified
    ``.to()`` dispatch method, and a ``.get()`` method with ``format``
    support.  Scalar pitch classes (``GenericPitch``, ``MidiPitch``,
    ``SpelledPitch``, etc.) compose this mixin.
    """

    @property
    def pitch_class(self) -> int:
        """Pitch class (0-11, C=0)."""
        raise NotImplementedError

    def to(
        self, target_type: type, *, format: str | None = None
    ) -> "TwelveTETPitchMixin":
        """Convert to a different pitch representation.

        Unified dispatch method for pitch conversion.  Replaces
        individual ``to_midi_number()``, ``to_generic()``,
        ``to_specific()`` methods.

        Args:
            target_type: The target pitch type (e.g., ``GenericPitch``,
                ``MidiPitch``, ``SpelledPitch``).
            format: Optional format specifier controlling output
                representation (e.g., for string formatting).

        Returns:
            A ``TwelveTETPitchMixin`` instance of the target type.

        Raises:
            TypeError: If conversion to *target_type* is not supported.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support conversion "
            f"to {target_type.__name__}"
        )

    def get(self, *, format: str | None = None) -> str:
        """Return a string representation of this pitch.

        Args:
            format: Format specifier (e.g., ``"midi"``, ``"spelled"``,
                ``"lily"``, ``"kern"``, ``"abc"``).  Default uses the
                most natural format for this pitch type.

        Returns:
            Formatted string representation.
        """
        raise NotImplementedError


# endregion Pitch Mixin
