"""Music21Loader: Load scores using music21."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import music21 as m21

from timetoalign.core import NumberType, TimeUnit
from .base import ScoreLoader
from .store import ScoreEventStore, ScoreEventType


class Music21Loader(ScoreLoader):
    """Load symbolic scores using music21.
    
    Uses recursive element parsing to extract:
    - Measures (structure)
    - Notes/Rests (with chord expansion)
    - Controls (dynamics, tempo, etc.)
    - Annotations (text)
    """

    def _load_source(self, source: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        # Parse score
        # forceSource=True ensures we don't pick up cached versions if file changed
        score = m21.converter.parse(str(source), forceSource=True)
        
        events = []
        has_rests = False
        
        # Flatten parts? M21 streams can be nested.
        # We start by separating parts.
        parts = score.parts if score.hasPartLikeStreams() else [score]
        
        for part_idx, part in enumerate(parts):
            part_id = part.id or f"P{part_idx+1}"
            
            # Recurse flat stream is often easier for positioning
            # But flattening can lose structural context if not careful.
            # semiFlat is good compromise usually, or just recurse.
            # Using .flat helps with absolute offsets.
            flat_part = part.flat
            
            # Iterate elements
            # We want offset, duration, and type
            
            # Pre-calculate Measure Map?
            # In flat stream, measures are also elements.
            # We can use .makeMeasures() if raw MIDI, but assuming MusicXML or structured source
            
            # Helper for MC/MN
            # In a flat stream, matching an element to its measure is done via context
            # element.measureNumber is available often.
            
            # Optimization: Iterate once and classify
            
            current_mc = 0
            
            for obj in flat_part:
                offset = float(obj.offset)
                duration = float(obj.duration.quarterLength)
                end = offset + duration
                
                # Classify
                category = None
                etype = None
                
                # 1. Measure
                if isinstance(obj, m21.stream.Measure):
                    category = ScoreEventType.CAT_MEASURE
                    etype = ScoreEventType.MEASURE
                    # MC increments on each measure found in order? 
                    # Note: in flat stream, measures overlap in time (end-to-end).
                    # But measure objects in flat stream are actually just containers.
                    # Actually, .flat usually Strips measures unless we do something else.
                    # Wait, part.flat removes Measure containers and puts elements at absolute offsets.
                    # Measure info is stored in `measureNumber` of elements or we find Barline objects?
                    pass
                
                # Special handling: .flat DOES include Barline objects but maybe not Measure containers.
                # If we want Measure EVENTS, we should maybe iterate the original part.recurse().
                
                # Let's try `recurse()` to keep hierarchy or just iterate original part measures for Measure events
                # and flat part for Notes?
            
            # Better strategy: 
            # 1. Get Measure Events from part.getElementsByClass(Measure)
            # 2. Get other events from part.flat
            
            # 1. Measure Events
            # Only valid if the part contains Measure objects (MusicXML does, MIDI import might)
            measure_list = list(part.getElementsByClass(m21.stream.Measure))
            if not measure_list and part.hasPartLikeStreams():
                 # Sometimes parts are in score -> part -> measure
                 pass

            # Map for MC
            # We'll just count them index 1-based
            measure_map = {} # onset -> {"mn": ..., "mc": ...}
            
            for i, m in enumerate(measure_list):
                m_offset = float(m.getOffsetInHierarchy(score))
                m_end = m_offset + float(m.duration.quarterLength)
                
                events.append({
                    "id": m.id,
                    "temporal_type": "interval",
                    "event_type": ScoreEventType.MEASURE,
                    "event_category": ScoreEventType.CAT_MEASURE,
                    "start": m_offset,
                    "end": m_end,
                    "duration": m_end - m_offset,
                    "mn": str(m.number),
                    "mc": i + 1,
                    "part_id": part_id,
                })
                
                # Build context map - simplistic look up by range
                # Or rely on m.measureNumber context on elements
            
            # 2. Other Events via Flattening
            # We use flat to get absolute timing easily
            for obj in flat_part:
                if isinstance(obj, (m21.stream.Measure, m21.stream.Part, m21.stream.Score)):
                    continue
                    
                offset = float(obj.offset) # This is relative to part if used on flat part
                duration = float(obj.duration.quarterLength)
                
                category = None
                etype = None
                
                # Notes/Rests
                if isinstance(obj, m21.note.GeneralNote):
                    category = ScoreEventType.CAT_NOTE
                    if isinstance(obj, m21.note.Rest):
                        etype = ScoreEventType.REST
                        has_rests = True
                    elif isinstance(obj, m21.note.Note):
                        etype = ScoreEventType.NOTE
                    elif isinstance(obj, m21.chord.Chord):
                        etype = ScoreEventType.CHORD
                    
                # Controls
                elif isinstance(obj, (m21.dynamics.Dynamic, m21.tempo.TempoIndication, 
                                      m21.key.KeySignature, m21.meter.TimeSignature, m21.expressions.TextExpression)):
                    # TextExpression could be Annotation
                    if isinstance(obj, m21.expressions.TextExpression):
                        category = ScoreEventType.CAT_ANNOTATION
                        etype = ScoreEventType.TEXT_EXPRESSION
                    else:
                        category = ScoreEventType.CAT_CONTROL
                        etype = obj.classes[0] # e.g. 'MetronomeMark'
                
                elif isinstance(obj, m21.spanner.Spanner):
                    # Slurs, Wedges
                    category = ScoreEventType.CAT_CONTROL
                    etype = obj.classes[0]

                if category:
                    # Common fields
                    processed_objs = [] # List of (obj, extra_data)
                    
                    if etype == ScoreEventType.CHORD:
                         # Expand Chord
                        for note in obj.notes:
                             processed_objs.append((note, {"parent_chord_id": obj.id}))
                    else:
                        processed_objs.append((obj, {}))
                        
                    for p_obj, extra in processed_objs:
                        # Pitch extraction
                        ep = None
                        tpc = None
                        sp = None
                        
                        if isinstance(p_obj, m21.note.Note):
                            ep = p_obj.pitch.midi
                            sp = {
                                "step": p_obj.pitch.step,
                                "alter": int(p_obj.pitch.alter or 0),
                                "octave": p_obj.pitch.octave
                            }
                            # TPC if available? 
                            # m21 pitch has .pitchClass (0-11) but not TPC directly in dimcat sense usually?
                            # Actually m21 doesn't store TPC by default, need calc. Leave None for now.
                        
                        # Context: Measure Number
                        # In flat stream, we might lose measure number unless preserved
                        mn = str(obj.measureNumber) if obj.measureNumber is not None else None
                        
                        # MC mapping?
                        # If we have measure list, we can lookup
                        # Simple lookup:
                        mc = None
                        if measure_list:
                            # find measure containing this offset
                            # Optimization: Could be better but simple iteration for now
                            # (music usually sequential)
                            for i, m in enumerate(measure_list):
                                m_off = float(m.getOffsetInHierarchy(score))
                                # Loose overlap check
                                if m_off <= offset < (m_off + float(m.duration.quarterLength) + 0.001):
                                    mc = i + 1
                                    if not mn: mn = str(m.number)
                                    break

                        events.append({
                        "id": str(p_obj.id),
                        "temporal_type": "interval" if duration > 0 else "instant",
                        "event_type": ScoreEventType.NOTE if isinstance(p_obj, m21.note.Note) else str(etype),
                        "event_category": str(category),
                            "start": offset,
                            "end": offset + duration,
                            "duration": duration,
                            "ep": ep,
                            "tpc": tpc,
                            "sp": sp,
                            "mn": str(mn) if mn else None,
                        "mc": int(mc) if mc is not None else None,
                        "part_id": str(part_id),
                        "voice": int(getattr(p_obj, "voice", 0)) if getattr(p_obj, "voice", None) is not None else None,  # M21 voice might be object?
                        "name": str(extra.get("name") or getattr(p_obj, "content", "") or "") # For annotations
                    })

        metadata = {
            "format": "score",
            "parser": "music21",
            "has_rests": has_rests
        }
        
        return metadata, events
