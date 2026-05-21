"""Note scalar for score note/rest events.

``Note`` is a pydantic v2 ``BaseModel`` representing a single note or rest
event.  It satisfies ``NoteLike`` (and thus ``IntervalEventLike``).

Uses canonical TTA model names: ``start`` / ``end`` for temporal fields.

WP2 bulk-migration note on polymorphic pitch
--------------------------------------------
``Note.pitch`` is annotated ``EnharmonicPitch | SpecificPitch | None`` for
materialised scalars — both are legitimate pitch representations on a note
depending on the source format.  Per the WP2 plan's locked decision, this
union MUST NOT translate to Arrow ``dense_union``; instead, the field is
**dropped from the pa.Schema** entirely (via the registered value
projector) and ``NoteEventData`` stores pitch in separate columns
(``midi_pitch``, ``specific_pitch``).  See ``loader/score/stores/notes.py``.

When constructing a single ``Note`` at the Python edge, you pass whichever
representation the loader produced; the columnar separation only matters
inside a ``NoteEventData`` table.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from ..schemas.from_pydantic import register_value_projector
from ..types import Coordinate
from .duration import Duration
from .pitch import EnharmonicPitch, MidiPitch, SpecificPitch


class Note(BaseModel):
    """A single note or rest event.  Satisfies ``NoteLike``.

    Pydantic v2 ``BaseModel``, frozen.  ``arbitrary_types_allowed`` so
    nested ``Coordinate`` and ``Duration`` ``BaseModel`` instances pass
    through cleanly.

    Attributes:
        start: Temporal position as a ``Coordinate`` (StartInstant).
        end: End position as a ``Coordinate``, or ``None``.
        duration: Duration as a ``Duration`` (preferred) or ``Coordinate``
            (legacy, accepted during the WP3 alias rollout), or ``None``.
        pitch: ``EnharmonicPitch`` (incl. ``MidiPitch`` subclass) or
            ``SpecificPitch`` for pitched notes, ``None`` for rests.
            Stored on the scalar only — see module docstring on columnar
            separation at the EventData level.
        voice: Voice number, or ``None``.
        staff: Staff number, or ``None``.
        velocity: MIDI velocity (0-127), or ``None``.
        instrument: Instrument name/identifier, or ``None``.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    start: Coordinate
    end: Coordinate | None = None
    duration: Duration | None = None
    pitch: EnharmonicPitch | SpecificPitch | None = None
    voice: int | None = None
    staff: int | None = None
    velocity: int | None = None
    instrument: str | None = None

    @field_validator("duration", mode="before")
    @classmethod
    def _coerce_duration_from_coordinate(cls, v: object) -> Duration | None:
        """Accept legacy ``Coordinate``-valued durations and coerce to ``Duration``.

        During the WP3 alias rollout, ``NoteEventData.duration`` still
        stores ``Coordinate``-shaped structs.  This validator preserves
        compatibility by upgrading on the way in; the storage schema
        itself uses ``Duration``.
        """
        if v is None or isinstance(v, Duration):
            return v
        if isinstance(v, Coordinate):
            return Duration(v.value, v.unit)
        return v  # let pydantic continue validating (will raise if not compatible)

    @property
    def is_rest(self) -> bool:
        """Return ``True`` if this event is a rest (no pitch)."""
        return self.pitch is None

    @property
    def semantic_type(self) -> str:
        return "Note"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "NoteField",
            "has_pitch": str(self.pitch is not None).lower(),
        }

    def to_dict(self) -> dict[str, object]:
        """Return a dict mirroring the storage struct.

        Pitch is intentionally absent from the returned dict — it is
        stored in a separate column on ``NoteEventData`` (columnar
        separation; see module docstring).
        """
        d: dict[str, object] = {
            "start": self.start.to_dict() if hasattr(self.start, "to_dict") else None,
            "end": (
                self.end.to_dict()
                if (self.end is not None and hasattr(self.end, "to_dict"))
                else None
            ),
            "voice": self.voice,
            "staff": self.staff,
            "velocity": self.velocity,
            "instrument": self.instrument,
        }
        if self.duration is None:
            d["duration"] = None
        elif hasattr(self.duration, "to_dict"):
            d["duration"] = self.duration.to_dict()
        return d

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Note | None:
        """Construct from a ``NoteEventData`` row dict (trust-boundary regime).

        Accepts the storage row produced by ``NoteEventData``: nested
        ``start``/``end``/``duration`` structs, plus the per-column
        pitch fields (``midi_pitch`` and/or ``specific_pitch``).  The
        pitch column that is present wins; if both are present, the
        specific pitch is preferred (preserves spelling).

        regime: trust boundary — pydantic validators run on construction.
        """
        from ..enums import TimeUnit

        start_raw = row.get("start")
        if start_raw is None:
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

        start = _coerce_coord(start_raw)
        if start is None:
            return None
        end = _coerce_coord(row.get("end"))
        duration = _coerce_duration(row.get("duration"))

        pitch: EnharmonicPitch | SpecificPitch | None = None
        sp_raw = row.get("specific_pitch")
        if isinstance(sp_raw, dict):
            pitch = SpecificPitch.from_row(sp_raw)
        if pitch is None:
            mp_raw = row.get("midi_pitch")
            if isinstance(mp_raw, dict):
                pitch = EnharmonicPitch.from_row(mp_raw)
            elif isinstance(mp_raw, (int, float)) and mp_raw is not None:
                pitch = EnharmonicPitch(midi_number=int(mp_raw))

        return cls(
            start=start,
            end=end,
            duration=duration,
            pitch=pitch,
            voice=row.get("voice"),
            staff=row.get("staff"),
            velocity=row.get("velocity"),
            instrument=row.get("instrument"),
        )

    def __repr__(self) -> str:
        pitch_str = repr(self.pitch) if self.pitch is not None else "rest"
        return f"Note(start={self.start}, duration={self.duration}, pitch={pitch_str})"


# ---------------------------------------------------------------------------
# Drop the polymorphic ``pitch`` field from the derived pa.Schema.
# ---------------------------------------------------------------------------
#
# Columnar-separation rule (WP2 locked): ``Note.pitch`` is a Python-level
# union for the materialised scalar, but the pa.Schema for a NoteField
# stores pitch in two separate columns on the parent EventData table
# (``midi_pitch``, ``specific_pitch``).  The translator MUST NEVER emit
# Arrow ``dense_union`` for this field.
#
# The empty-list projector achieves that: when the translator builds the
# struct for Note it skips ``pitch`` entirely; the schema is left to
# carry only ``start``, ``end``, ``duration``, ``voice``, ``staff``,
# ``velocity``, ``instrument``.


def _drop_field(_model_cls: type[BaseModel], _name: str, _info: object) -> list[Any]:
    """Drop a polymorphic / out-of-band field from the derived pa.Schema."""
    return []


register_value_projector(Note, "pitch", _drop_field)

# Touch MidiPitch so static analysis cannot prune it from the import; the
# class is referenced via from_row only and would otherwise be unused.
_ = MidiPitch
