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

from typing import ClassVar

import pyarrow as pa

from timetoalign.loader.events import EventData


class MidiEventData(EventData):
    """EventData for performance MIDI events (mido cross-loader columns).

    Carries the seven columns mido can produce on its own: ``pitch``,
    ``velocity``, ``channel``, ``track``, ``control``, ``value``,
    ``program``.  Stored as nullable atomic columns (NOT a struct) for
    fast columnar access; the paired :class:`MidiEvent` scalar
    advertises the matching shape via its ``midi_number``-nested
    pa.Schema for semantic-field round-tripping.

    For score-side MIDI loaded via partitura, see
    :class:`ScoreMidiEventData`, which adds ``voice``, ``staff`` and
    ``part_id`` on top.
    """

    _extra_fields: ClassVar[list[pa.Field]] = [
        # Note fields (required for Notes)
        pa.field("pitch", pa.int8(), nullable=True),
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


class ScoreMidiEventData(MidiEventData):
    """EventData for score MIDI events (partitura).

    Extends :class:`MidiEventData` with the three partitura-only
    columns: ``voice``, ``staff``, ``part_id``.  ``_extra_fields`` is
    redeclared (not appended) because the base ``EventData.get_schema``
    reads ``cls._extra_fields`` directly as the canonical column list.
    """

    _extra_fields: ClassVar[list[pa.Field]] = [
        # Inherited cross-loader columns
        pa.field("pitch", pa.int8(), nullable=True),
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
