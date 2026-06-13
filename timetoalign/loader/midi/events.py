"""EventData subclasses for MIDI loaders.

Two concrete subclasses model the cross-loader / loader-specific split:

* :class:`MidiEventData` carries the **seven cross-loader columns**
  produced by both mido (``PerformanceMidiLoader``) and partitura
  (``ScoreMidiLoader``).  Performance MIDI uses this class directly —
  there is no notion of voice, staff or part on a raw MIDI track, so
  storing always-null columns for those names would be a redundant
  schema.
* :class:`ScoreMidiEventData` extends the base with the three
  partitura-only columns (``voice``, ``staff``, ``part_id``).  It is
  the storage class for ``ScoreMidiLoader``.

The two classes pair with the :class:`MidiEvent` and
:class:`ScoreMidiEvent` pydantic scalars in ``core/events.py``: each
``_extra_fields`` list mirrors the additional sub-fields the scalar
exposes.  ``MidiStore`` works against either concrete class
transparently via ``type(data).empty(...)`` so that filter / merge
operations preserve the wider schema when one is in play.
"""

from __future__ import annotations

import json
from typing import ClassVar

import pyarrow as pa

from timetoalign.core.enums import IntervalPolicy, NumberType
from timetoalign.core.events import EnharmonicPitchField
from timetoalign.core.fields import (
    TIMETOALIGN_METADATA_KEY,
    metadata_blob_from_dict,
)
from timetoalign.loader.events import EventData

# The ``pitch`` column is a materialised ``{midi_number: int64}`` struct —
# the exact ``EnharmonicPitch`` storage shape — decorated with
# ``b"timetoalign"`` metadata advertising ``EnharmonicPitchField``.  A MIDI
# pitch *number* carries no enharmonic spelling, so reading it as an
# ``EnharmonicPitch`` (display alias ``MidiPitch``) invents nothing.  The
# materialised struct makes ``events.get_field(EnharmonicPitch)`` /
# ``get_pitch_field()`` succeed without any per-loader wiring.
_PITCH_METADATA: dict[bytes, bytes] = {
    TIMETOALIGN_METADATA_KEY: metadata_blob_from_dict(
        {"field_type": "EnharmonicPitchField", "pitch_type": "ep"}
    )
}
_PITCH_FIELD = pa.field(
    "pitch", EnharmonicPitchField.pa_schema, nullable=True, metadata=_PITCH_METADATA
)


def _pitch_struct(value: object) -> dict[str, int] | None:
    """Coerce a raw MIDI pitch value into the ``{midi_number}`` struct dict.

    Accepts a bare integer (the raw mido/partitura value), an existing
    ``{"midi_number": int}`` dict, a JSON-encoded variant of either (the
    historical string-coerced storage), or ``None`` (Control / Program
    changes carry no pitch).
    """
    if value is None:
        return None
    if isinstance(value, dict):
        mn = value.get("midi_number")
        return None if mn is None else {"midi_number": int(mn)}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return {"midi_number": int(value)}
        return _pitch_struct(parsed)
    return {"midi_number": int(value)}


class MidiEventData(EventData):
    """EventData for performance MIDI events (mido cross-loader columns).

    Carries the seven columns mido can produce on its own: ``pitch``,
    ``velocity``, ``channel``, ``track``, ``control``, ``value``,
    ``program``.  ``pitch`` is a materialised ``{midi_number: int64}``
    struct (the :class:`EnharmonicPitch` storage shape) so the produced
    EventData affords ``get_field(EnharmonicPitch)`` / ``get_pitch_field()``
    over the note number, matching the ``pitch: EnharmonicPitch | None``
    annotation on the paired :class:`MidiEvent` scalar.  The remaining six
    sub-fields stay nullable atomic columns for fast columnar access.

    For score-side MIDI loaded via partitura, see
    :class:`ScoreMidiEventData`, which adds ``voice``, ``staff`` and
    ``part_id`` on top.
    """

    _extra_fields: ClassVar[list[pa.Field]] = [
        # Note pitch as the EnharmonicPitch storage struct (afforded view).
        _PITCH_FIELD,
        pa.field("velocity", pa.int8(), nullable=True),
        # MIDI routing
        pa.field("channel", pa.int8(), nullable=True),
        pa.field("track", pa.int16(), nullable=True),
        # Control Change fields
        pa.field("control", pa.int8(), nullable=True),  # CC number
        pa.field("value", pa.int8(), nullable=True),  # CC/Program value
        # Program Change
        pa.field("program", pa.int8(), nullable=True),
    ]

    @classmethod
    def from_dicts(  # type: ignore[override]
        cls,
        rows,
        unit,
        number_type=NumberType.float,
        *,
        interval_policy=IntervalPolicy.warn,
    ):
        """Coerce raw ``pitch`` integers into ``{midi_number}`` structs.

        The MIDI loaders emit a bare MIDI note number for ``pitch``; here
        it is lifted into the materialised ``EnharmonicPitch`` struct shape
        so the resulting column affords the semantic-field view.  Delegates
        to :meth:`EventData.from_dicts` for everything else.
        """
        for row in rows:
            if "pitch" in row:
                row["pitch"] = _pitch_struct(row["pitch"])
        return super().from_dicts(
            rows, unit, number_type, interval_policy=interval_policy
        )


class ScoreMidiEventData(MidiEventData):
    """EventData for score MIDI events (partitura).

    Extends :class:`MidiEventData` with the three partitura-only
    columns: ``voice``, ``staff``, ``part_id``.  ``_extra_fields`` is
    redeclared (not appended) because the base ``EventData.get_schema``
    reads ``cls._extra_fields`` directly as the canonical column list.
    ``pitch`` is the same materialised ``{midi_number: int64}`` struct as
    the base, affording the ``EnharmonicPitch`` view.
    """

    _extra_fields: ClassVar[list[pa.Field]] = [
        # Inherited cross-loader columns
        _PITCH_FIELD,
        pa.field("velocity", pa.int8(), nullable=True),
        pa.field("channel", pa.int8(), nullable=True),
        pa.field("track", pa.int16(), nullable=True),
        pa.field("control", pa.int8(), nullable=True),
        pa.field("value", pa.int8(), nullable=True),
        pa.field("program", pa.int8(), nullable=True),
        # Score-only columns (partitura)
        pa.field("voice", pa.int8(), nullable=True),
        pa.field("staff", pa.int8(), nullable=True),
        pa.field("part_id", pa.string(), nullable=True),
    ]
