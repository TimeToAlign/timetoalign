"""Protocols for semantic type classification in Time To Align!

This module defines the structural typing contracts (Protocols) that unify
scalar-level types (e.g., Coordinate) and columnar-level types (e.g.,
CoordinateField) under a single interface.

Protocols:
    SemanticTypeLike: Root protocol for any object carrying semantic type
        metadata (a name and a metadata dict for Parquet storage).
    CoordinateLike[V]: Extension for coordinate-bearing objects, adding
        value access, unit, domain, and number_type.
    PitchLike: Extension for pitch-bearing objects (midi_number, pitch_class).
    NoteLike: Extension for note objects (onset, pitch, duration).
    MeasureLike: Extension for measure objects (mc, mn, time_signature).
    HarmonyLike: Extension for harmony annotations (label, numeral, chord_type).

The existing ``Coordinate`` dataclass already satisfies ``CoordinateLike``
structurally with zero changes.
"""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from .enums import Domain, NumberType, TimeUnit

V = TypeVar("V", covariant=True)


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

    Examples:
        >>> from timetoalign.core.types import Coordinate
        >>> from timetoalign.core.enums import TimeUnit
        >>> coord = Coordinate(120, TimeUnit.ticks)
        >>> isinstance(coord, CoordinateLike)
        True
        >>> coord.domain
        "logical"
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


@runtime_checkable
class PitchLike(SemanticTypeLike, Protocol):
    """Protocol for pitch-bearing objects.

    Any object that exposes a MIDI note number and pitch class satisfies
    this protocol.  Both scalar types (``MidiPitch``, ``SpelledPitch``)
    and columnar types (``PitchField``) are expected to conform.

    Attributes:
        midi_number: MIDI note number (0-127).
        pitch_class: Pitch class (0-11, C=0).
    """

    @property
    def midi_number(self) -> int:
        """MIDI note number (0-127)."""
        ...

    @property
    def pitch_class(self) -> int:
        """Pitch class (0-11, C=0)."""
        ...


@runtime_checkable
class NoteLike(SemanticTypeLike, Protocol):
    """Protocol for note objects with onset, pitch, and duration.

    Attributes:
        onset: The temporal position of the note.
        pitch: The pitch of the note, or ``None`` for rests.
        duration: The duration of the note in quarter-beat units.
    """

    @property
    def onset(self) -> CoordinateLike:  # type: ignore[type-arg]
        """The temporal position of the note."""
        ...

    @property
    def pitch(self) -> PitchLike | None:
        """The pitch of the note, or ``None`` for rests."""
        ...

    @property
    def duration(self) -> float:
        """The duration of the note in quarter-beat units."""
        ...


@runtime_checkable
class MeasureLike(SemanticTypeLike, Protocol):
    """Protocol for measure objects.

    Attributes:
        mc: Measure Count (monotonically increasing, 1-indexed).
        mn: Measure Number label (may have suffix, e.g. ``"19a"``).
        time_signature: Tuple of (numerator, denominator).
    """

    @property
    def mc(self) -> int:
        """Measure Count (monotonically increasing, 1-indexed)."""
        ...

    @property
    def mn(self) -> str:
        """Measure Number label."""
        ...

    @property
    def time_signature(self) -> tuple[int, int]:
        """Time signature as (numerator, denominator)."""
        ...


@runtime_checkable
class HarmonyLike(SemanticTypeLike, Protocol):
    """Protocol for harmony annotation objects.

    Follows the DCML harmony annotation standard.

    Attributes:
        label: The full harmony label string.
        numeral: The Roman numeral component.
        chord_type: The chord type (e.g. ``"M"``, ``"m"``, ``"o"``).
    """

    @property
    def label(self) -> str:
        """The full harmony label string."""
        ...

    @property
    def numeral(self) -> str:
        """The Roman numeral component."""
        ...

    @property
    def chord_type(self) -> str:
        """The chord type."""
        ...
