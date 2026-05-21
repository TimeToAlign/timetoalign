"""Measure scalar for measure boundary events.

``Measure`` is a pydantic v2 ``BaseModel`` representing a single measure
extracted from ``MeasureData``.  It satisfies ``MeasureLike`` (and thus
``IntervalEventLike``).

Aligned with the MeasureMap specification.  Uses canonical TTA model
names: ``start`` / ``end`` for temporal fields.

WP2 storage notes
-----------------
* ``time_signature: tuple[int, int]`` → pa.Schema ``struct{_0: int64, _1:
  int64}``.  Fixed-length tuples translate to a positional struct (the
  shape that round-trips losslessly through Parquet; verified by the
  schema unit tests under ``tests/core/schemas``).
* ``next_ids: tuple[str, ...]`` (stringified ``ScopedId``) →
  ``pa.list_(string)``.  ``ScopedId`` itself is not a pydantic model and
  cannot be stored as a nested struct without inventing a schema for the
  scope/local pair; the canonical interchange shape is the colon-joined
  string (``ScopedId.__str__``), preserved here for faithful storage.
  Construction-time validators accept the legacy ``tuple[ScopedId, ...]``
  shape and coerce via ``ScopedId.parse``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from ..ids import ScopedId
from ..types import Coordinate
from .duration import Duration


class Measure(BaseModel):
    """A single measure boundary event.  Satisfies ``MeasureLike``.

    Pydantic v2 ``BaseModel``, frozen.

    Attributes:
        id: Measure identifier (monotonically increasing, 1-indexed).
            Called ``ID`` in MeasureMap, ``mc`` in DCML.
        mn: Measure Number label (e.g. ``"1"``, ``"0"``, ``"19a"``).
        start: Temporal position as a ``Coordinate`` (StartInstant).
        end: End position as a ``Coordinate``, or ``None``.
        duration: Duration as a ``Duration`` (preferred) or ``Coordinate``
            (legacy), or ``None``.
        time_signature: Tuple of (numerator, denominator).
        key_signature: Key signature string, or ``None``.
        nominal_length: Expected duration from time signature, or ``None``.
        actual_length: Real duration (may differ for anacrusis), or ``None``.
        start_repeat: Whether this bar has a repeat start marker.
        end_repeat: Whether this bar has a repeat end marker.
        next_ids: Possible successor identifiers as stringified
            ``ScopedId`` values, or ``None``.
        volta: Ending number (1, 2, ...), or ``None``.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    # Note: pydantic intercepts the bare ``id`` attribute name without
    # issue; the field name is preserved for MeasureMap parity (per the
    # MeasureLike protocol).
    id: int  # noqa: A003 — MeasureMap field name
    mn: str
    start: Coordinate
    end: Coordinate | None = None
    duration: Duration | None = None
    time_signature: tuple[int, int] = (4, 4)
    key_signature: str | None = None
    nominal_length: float | None = None
    actual_length: float | None = None
    start_repeat: bool = False
    end_repeat: bool = False
    next_ids: tuple[str, ...] | None = None
    volta: int | None = None

    @field_validator("duration", mode="before")
    @classmethod
    def _coerce_duration_from_coordinate(cls, v: object) -> Duration | None:
        """Accept legacy ``Coordinate``-valued durations and coerce to ``Duration``."""
        if v is None or isinstance(v, Duration):
            return v
        if isinstance(v, Coordinate):
            return Duration(v.value, v.unit)
        return v

    @field_validator("next_ids", mode="before")
    @classmethod
    def _coerce_next_ids(cls, v: object) -> tuple[str, ...] | None:
        """Accept legacy ``tuple[ScopedId, ...]`` input and coerce to strings.

        ``ScopedId`` instances are converted via ``str(...)`` which yields
        the canonical ``scope:local`` form (or just ``local`` if scope is
        empty).
        """
        if v is None:
            return None
        if isinstance(v, str):
            # Single-string convenience.
            return (v,)
        if isinstance(v, (list, tuple)):
            out: list[str] = []
            for item in v:
                if isinstance(item, ScopedId):
                    out.append(str(item))
                elif isinstance(item, str):
                    out.append(item)
                else:
                    raise TypeError(
                        f"next_ids item must be ScopedId or string, got "
                        f"{type(item).__name__}"
                    )
            return tuple(out)
        raise TypeError(
            f"next_ids must be a tuple of ScopedId/string, got {type(v).__name__}"
        )

    @property
    def semantic_type(self) -> str:
        return "Measure"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "MeasureField",
            "time_signature": f"{self.time_signature[0]}/{self.time_signature[1]}",
        }

    def to_dict(self) -> dict[str, object]:
        """Return a dict mirroring the storage struct."""
        return {
            "id": self.id,
            "mn": self.mn,
            "start": self.start.to_dict() if hasattr(self.start, "to_dict") else None,
            "end": (
                self.end.to_dict()
                if (self.end is not None and hasattr(self.end, "to_dict"))
                else None
            ),
            "duration": (
                self.duration.to_dict()
                if (self.duration is not None and hasattr(self.duration, "to_dict"))
                else None
            ),
            "time_signature": list(self.time_signature),
            "key_signature": self.key_signature,
            "nominal_length": self.nominal_length,
            "actual_length": self.actual_length,
            "start_repeat": self.start_repeat,
            "end_repeat": self.end_repeat,
            "next_ids": list(self.next_ids) if self.next_ids is not None else None,
            "volta": self.volta,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Measure | None:
        """Construct from a ``MeasureData`` row dict (trust-boundary regime).

        regime: trust boundary — pydantic validators run on construction.
        """
        from ..enums import TimeUnit

        id_raw = row.get("id")
        if id_raw is None:
            return None

        def _coerce_coord(raw: Any) -> Coordinate | None:
            if raw is None:
                return None
            if isinstance(raw, Coordinate):
                return raw
            if isinstance(raw, dict):
                v = raw.get("value")
                if v is None:
                    return None
                unit = raw.get("unit", TimeUnit.quarters)
                return Coordinate(v, unit)
            return None

        def _coerce_duration(raw: Any) -> Duration | None:
            if raw is None:
                return None
            if isinstance(raw, Duration):
                return raw
            if isinstance(raw, Coordinate):
                return Duration(raw.value, raw.unit)
            if isinstance(raw, dict):
                v = raw.get("value")
                if v is None:
                    return None
                unit = raw.get("unit", TimeUnit.quarters)
                return Duration(v, unit)
            return None

        start = _coerce_coord(row.get("start"))
        if start is None:
            return None
        ts_raw = row.get("time_signature", (4, 4))
        if isinstance(ts_raw, dict):
            ts = (int(ts_raw.get("_0", 4)), int(ts_raw.get("_1", 4)))
        elif isinstance(ts_raw, (list, tuple)) and len(ts_raw) == 2:
            ts = (int(ts_raw[0]), int(ts_raw[1]))
        else:
            ts = (4, 4)
        return cls(
            id=int(id_raw),
            mn=str(row.get("mn") or ""),
            start=start,
            end=_coerce_coord(row.get("end")),
            duration=_coerce_duration(row.get("duration")),
            time_signature=ts,
            key_signature=row.get("key_signature"),
            nominal_length=row.get("nominal_length"),
            actual_length=row.get("actual_length"),
            start_repeat=bool(row.get("start_repeat", False)),
            end_repeat=bool(row.get("end_repeat", False)),
            next_ids=row.get("next_ids"),
            volta=row.get("volta"),
        )

    def __repr__(self) -> str:
        ts = f"{self.time_signature[0]}/{self.time_signature[1]}"
        return f"Measure(id={self.id}, mn={self.mn!r}, timesig={ts})"
