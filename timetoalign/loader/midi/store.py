"""MidiEventStore: Specialized EventStore for MIDI data."""

from __future__ import annotations

from typing import ClassVar

import pyarrow as pa

from timetoalign.loader.store import EventStore


class MidiEventStore(EventStore):
    """EventStore for MIDI events (notes, control changes, program changes).
    
    This store harmonizes fields from both performance MIDI (mido) and 
    score MIDI (partitura) into a single schema. Score-specific fields
    like voice, staff, and part_id are nullable.
    """
    
    _extra_fields: ClassVar[list[pa.Field]] = [
        # Note fields (required for Notes)
        pa.field("pitch", pa.int8(), nullable=True),
        pa.field("velocity", pa.int8(), nullable=True),
        
        # MIDI routing
        pa.field("channel", pa.int8(), nullable=True),
        pa.field("track", pa.int16(), nullable=True),
        
        # Control Change fields
        pa.field("control", pa.int8(), nullable=True),    # CC number
        pa.field("value", pa.int8(), nullable=True),      # CC/Program value
        
        # Program Change
        pa.field("program", pa.int8(), nullable=True),
        
        # Score-specific (from partitura)
        pa.field("voice", pa.int8(), nullable=True),
        pa.field("staff", pa.int8(), nullable=True),
        pa.field("part_id", pa.string(), nullable=True),
    ]
