"""Measure scalar for measure boundary events.

``Measure`` is a frozen dataclass that represents a single measure
extracted from ``MeasureData``.  It satisfies ``MeasureLike``
(and thus ``IntervalEventLike``).

Aligned with the MeasureMap specification.  Uses canonical TTA model
names: ``start`` / ``end`` for temporal fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..types import Coordinate

if TYPE_CHECKING:
    from ..ids import ScopedId


@dataclass(frozen=True, slots=True)
class Measure:
    """A single measure boundary event.  Satisfies ``MeasureLike``.

    Attributes:
        id: Measure identifier (monotonically increasing, 1-indexed).
            Called ``ID`` in MeasureMap, ``mc`` in DCML.
        mn: Measure Number label (e.g. ``"1"``, ``"0"``, ``"19a"``).
        start: Temporal position as a ``Coordinate`` (StartInstant).
        end: End position as a ``Coordinate``, or ``None`` (EndInstant).
        duration: Duration as a ``Coordinate``, or ``None``.
        time_signature: Tuple of (numerator, denominator).
        key_signature: Key signature string, or ``None``.
        nominal_length: Expected duration from time signature, or ``None``.
        actual_length: Real duration (may differ for anacrusis), or ``None``.
        start_repeat: Whether this bar has a repeat start marker.
        end_repeat: Whether this bar has a repeat end marker.
        next_ids: Possible successor identifiers (``ScopedId``), or ``None``.
        volta: Ending number (1, 2, ...), or ``None``.
    """

    id: int  # noqa: A003  # shadows builtin 'id', intentional per MeasureMap spec
    mn: str
    start: Coordinate
    end: Coordinate | None = None
    duration: Coordinate | None = None
    time_signature: tuple[int, int] = (4, 4)
    key_signature: str | None = None
    nominal_length: float | None = None
    actual_length: float | None = None
    start_repeat: bool = False
    end_repeat: bool = False
    next_ids: tuple[ScopedId, ...] | None = None
    volta: int | None = None

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "Measure"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract."""
        return {
            "field_type": "MeasureField",
            "time_signature": f"{self.time_signature[0]}/{self.time_signature[1]}",
        }

    def __repr__(self) -> str:
        ts = f"{self.time_signature[0]}/{self.time_signature[1]}"
        return f"Measure(id={self.id}, mn={self.mn!r}, timesig={ts})"
