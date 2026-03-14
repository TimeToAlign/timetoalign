"""Protocols for semantic type classification in Time To Align!

This module defines the structural typing contracts (Protocols) that unify
scalar-level types (e.g., Coordinate) and columnar-level types (e.g.,
CoordinateField) under a single interface.

Protocols:
    SemanticTypeLike: Root protocol for any object carrying semantic type
        metadata (a name and a metadata dict for Parquet storage).
    CoordinateLike[V]: Extension for coordinate-bearing objects, adding
        value access, unit, domain, and number_type.

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
