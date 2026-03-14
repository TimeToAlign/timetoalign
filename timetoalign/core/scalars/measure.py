"""Measure scalar for measure boundary events.

``Measure`` is a frozen dataclass that represents a single measure
extracted from ``MeasureData``.  It satisfies ``MeasureLike``.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..types import Coordinate


@dataclass(frozen=True, slots=True)
class Measure:
    """A single measure boundary event.  Satisfies ``MeasureLike``.

    Attributes:
        mc: Measure Count (monotonically increasing, 1-indexed).
        mn: Measure Number label (e.g. ``"1"``, ``"0"``, ``"19a"``).
        onset: Temporal position as a ``Coordinate``.
        duration: Duration in quarter-beat units.
        time_signature: Tuple of (numerator, denominator).
        key_signature: Key signature string, or ``None``.
    """

    mc: int
    mn: str
    onset: Coordinate
    duration: float
    time_signature: tuple[int, int]
    key_signature: str | None

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
        return f"Measure(mc={self.mc}, mn={self.mn!r}, timesig={ts})"
