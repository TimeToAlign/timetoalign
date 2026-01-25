"""PartituraLoader: Load scores using partitura."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import partitura as pt
import partitura.score as pts
import partitura.score as pts

from timetoalign.core import NumberType, TimeUnit
from .base import ScoreLoader
from .store import ScoreEventStore, ScoreEventType


class PartituraLoader(ScoreLoader):
    """Load symbolic scores using partitura.
    
    Supports MusicXML (fully typed) and MIDI (quantized/structured).
    Extracts explicit categories: Measures, Notes, Controls, Annotations.
    """

    def __init__(
        self,
        *,
        unit: TimeUnit | None = None,
        number_type: NumberType = NumberType.float,
        force_note_ids: bool = True,
    ) -> None:
        super().__init__(unit, number_type)
        self._force_note_ids = force_note_ids

    def _load_source(self, source: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        # Load score
        score = pt.load_score(str(source), force_note_ids=self._force_note_ids)
        
        # Flatten parts
        parts = []
        if isinstance(score, pts.Score):
            parts = score.parts
        elif isinstance(score, (pts.Part, pts.PartGroup)):
            # Helper to flatten PartGroup if needed, but usually load_score returns Score or Part
            parts = [score] if isinstance(score, pts.Part) else score.children # type: ignore
        elif isinstance(score, list):
            parts = score
        
        events = []
        has_rests = False

        for part_idx, part in enumerate(parts):
            part_id = getattr(part, "id", f"P{part_idx+1}")
            
            # 1. Notes (using note_array for efficiency)
            # We use Partitura's note_array to get onset, duration, pitch info efficiently
            na = pt.utils.music.note_array_from_part(
                part,
                include_pitch_spelling=True,
                include_key_signature=True,
                include_time_signature=True,
                include_staff=True,
                # include_divs_per_quarter=True # If needed for unit conversion
            )
            
            for row in na:
                # Partitura note_array rows are numpy structured arrays
                # Fields: onset_div, duration_div, pitch, step, alter, octave, voice, id, staff...
                
                # Check for rest (if Partitura includes them in note_array - usually it does ONLY if requested, 
                # but standard note_array is for notes. We need to iterate objects for rests if not in array)
                # Actually, iterate methods are safer for strict categorization.
                pass 

            # STRATEGY CHANGE: 
            # Partitura's `iter_all` is safer to catch ALL objects including Rests and overlapping controls.
            # `note_array` is great for analysis but might skip non-note events we need.
            # We will use `iter_all` and manual extraction to ensure full coverage of "4 categories".

            # 2. Iterate all objects
            # Pre-calc measure map for performance
            # part.measure_number_map is a function interpolating division time to measure number
            # We need actual measure objects for the "Measure" category
            
            # Map for MC (1-based index)
            # Create a sorted list of measure start times
            measures = list(part.iter_all(pts.Measure))
            # Sort by start just in case
            measures.sort(key=lambda m: m.start.t)
            
            measure_starts = [m.start.t for m in measures]
            
            # Helper to find MC
            def get_mc(t: int) -> int:
                # Find index of measure that starts <= t
                import bisect
                idx = bisect.bisect_right(measure_starts, t) - 1
                return idx + 1 if idx >= 0 else 0

            # Collect raw objects
            # Filter standard classes
            
            c_measure = set()
            c_note = set()
            c_control = set()
            c_annotation = set()

            for obj in part.iter_all(include_subclasses=True):
                # Classify
                if isinstance(obj, pts.Measure):
                    c_measure.add(obj)
                elif isinstance(obj, (pts.Note, pts.Rest, pts.GraceNote)):
                    c_note.add(obj)
                    if isinstance(obj, pts.Rest):
                        has_rests = True
                elif isinstance(obj, (pts.TimeSignature, pts.KeySignature, pts.Tempo, pts.Direction, pts.Slur, pts.DynamicLoudnessDirection)):
                    # Note: Directions can be text (Annotation) or symbol (Control) depending on type
                    # We'll put Directions in Control by default unless subclass suggests otherwise
                    if isinstance(obj, pts.Words):
                        c_annotation.add(obj)
                    else:
                        c_control.add(obj)
                else:
                    # Fallback
                    # If it has start/end, keep it?
                    if hasattr(obj, "start"):
                        c_control.add(obj)

            # Process Measures
            for m in c_measure:
                events.append({
                    "id": getattr(m, "id", None) or f"measure_{m.start.t}",
                    "temporal_type": "interval",
                    "event_type": ScoreEventType.MEASURE,
                    "event_category": ScoreEventType.CAT_MEASURE,
                    "start": m.start.t,
                    "end": m.end.t,
                    "duration": m.end.t - m.start.t,
                    "mn": str(m.number),
                    "mc": get_mc(m.start.t),
                    "part_id": part_id,
                })

            # Prepare Unit Conversion
            to_quarters = lambda x: x
            if self.unit == TimeUnit.quarters:
                to_quarters = part.beat_map
            
            # Process Notes/Rests
            for n in c_note:
                is_rest = isinstance(n, pts.Rest)
                etype = ScoreEventType.REST if is_rest else ScoreEventType.NOTE
                
                # Pitch info
                midi_pitch = None
                spelled_pitch = None
                octave = None
                
                if not is_rest:
                    ep = None
                    epc = None
                    if hasattr(n, "midi_pitch"):
                        ep = n.midi_pitch
                        epc = ep % 12
                        midi_pitch = {"ep": ep, "epc": epc}
                        
                    if hasattr(n, "octave"):
                         octave = getattr(n, "octave", 4)

                    if hasattr(n, "step"): # Spelled
                        step = n.step
                        alter = int(getattr(n, "alter", 0) or 0)
                        octave = int(getattr(n, "octave", 0) or 4) if octave is None else octave
                        
                        # Generic Pitch Class
                        gpc_map = {'C': 0, 'D': 1, 'E': 2, 'F': 3, 'G': 4, 'A': 5, 'B': 6}
                        gpc_int = gpc_map.get(step, 0)
                        gpc_str = step
                        
                        # Accidental Normalization
                        # Symbols: ♯ (U+266F), ♭ (U+266D)
                        acc = alter
                        acc_str = ""
                        if acc > 0:
                            acc_str = "♯" * acc
                        elif acc < 0:
                            acc_str = "♭" * abs(acc)
                        
                        # Spelled Pitch Class (TPC/Fifths)
                        # C=0, G=1, D=2, A=3, E=4, B=5, F#=6, C#=7...
                        # F=-1, Bb=-2, Eb=-3...
                        # Base fifths: F=-1, C=0, G=1, D=2, A=3, E=4, B=5
                        base_fifths = {'F': -1, 'C': 0, 'G': 1, 'D': 2, 'A': 3, 'E': 4, 'B': 5}
                        spc_int = base_fifths.get(step, 0) + (7 * acc)
                        
                        # Names
                        spc_str = f"{step}{acc_str}"
                        sp = f"{spc_str}{octave}"
                        
                        spelled_pitch = {
                            "gpc_int": gpc_int,
                            "gpc_str": gpc_str,
                            "acc": acc,
                            "spc_int": spc_int,
                            "spc_str": spc_str,
                            "sp": sp,
                            "cents": 0.0
                        }

                # Timing
                # Partitura times are in divs (ticks). Convert if needed.
                start_t = to_quarters(n.start.t)
                end_t = to_quarters(n.start.t + n.duration)
                dur = end_t - start_t
                
                events.append({
                    "id": getattr(n, "id", None),
                    "temporal_type": "interval" if dur > 0 else "instant", # Grace notes?
                    "event_type": etype,
                    "event_category": "rest" if is_rest else ScoreEventType.CAT_NOTE,
                    "start": float(start_t),
                    "end": float(end_t),
                    "duration": dur,
                    "midi_pitch": midi_pitch,
                    "spelled_pitch": spelled_pitch,
                    "octave": octave,
                    "voice": getattr(n, "voice", None),
                    "staff": getattr(n, "staff", None),
                    "mn": str(part.measure_number_map(n.start.t)) if hasattr(part, "measure_number_map") else None,
                    "mc": get_mc(n.start.t),
                    "part_id": part_id,
                })

            # Process Controls
            for c in c_control:
                # determine type name
                etype = c.__class__.__name__
                events.append({
                    "id": getattr(c, "id", None) or f"{etype}_{c.start.t}",
                    "temporal_type": "interval" if getattr(c, "end", None) else "instant",
                    "event_type": etype,
                    "event_category": ScoreEventType.CAT_CONTROL,
                    "start": c.start.t,
                    "end": c.end.t if getattr(c, "end", None) else None,
                    "duration": (c.end.t - c.start.t) if getattr(c, "end", None) else 0,
                    "mn": str(part.measure_number_map(c.start.t)) if hasattr(part, "measure_number_map") else None,
                    "mc": get_mc(c.start.t),
                    "part_id": part_id,
                })

            # Process Annotations
            for a in c_annotation:
                events.append({
                    "id": getattr(a, "id", None),
                    "temporal_type": "instant", # Usually words are point events?
                    "event_type": "Annotation",
                    "event_category": ScoreEventType.CAT_ANNOTATION,
                    "start": a.start.t,
                    "name": getattr(a, "text", str(a)),
                    "mn": str(part.measure_number_map(a.start.t)) if hasattr(part, "measure_number_map") else None,
                    "mc": get_mc(a.start.t),
                    "part_id": part_id,
                })
        
        # Enforce non-negative coordinates (TTA requirement)
        if events:
            min_start = min(e["start"] for e in events)
            if min_start < 0:
                offset = abs(min_start)
                for e in events:
                    e["start"] += offset
                    if "end" in e and e["end"] is not None:
                        e["end"] += offset

        metadata = {
            "format": "score", 
            "parser": "partitura", 
            "has_rests": has_rests
        }
        
        return metadata, events
