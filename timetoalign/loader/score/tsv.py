"""TSVLoader: Load scores from TSV using ms3."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from timetoalign.core import NumberType, TimeUnit
from .base import ScoreLoader
from .store import ScoreEventStore, ScoreEventType

logger = logging.getLogger(__name__)


class TSVLoader(ScoreLoader):
    """Load symbolic scores from DCML-style TSV files.
    
    Wraps ms3.load_tsv to load standard tabular data.
    Requires 'ms3' package.
    """

    def _load_source(self, source: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        try:
            import ms3
            import pandas as pd
        except ImportError:
            raise ImportError("TSVLoader requires 'ms3'. Install with pip install ms3")

        # source can be iteration of files or a directory?
        # Standard approach: The source path points to one file (e.g. notes.tsv) 
        # but ms3 expects a folder or a set of parallel files?
        # User prompt said: "load them either based on ms3's code (function load_tsv())"
        
        # ms3.load_tsv loads a dataframe.
        # If user passes single TSV file, we load it.
        # If user passes directory, we iterate? 
        # ScoreLoader loads "source". If source is a file, we treat it as such.
        
        df = ms3.load_tsv(str(source))
        
        # Determine category based on filename or content?
        # Filename usually has .notes.tsv, .measures.tsv, etc.
        fname = source.name.lower()
        
        category = None
        if "measures" in fname:
            category = ScoreEventType.CAT_MEASURE
        elif "notes" in fname:
            category = ScoreEventType.CAT_NOTE
        elif "chords" in fname or "control" in fname:
            category = ScoreEventType.CAT_CONTROL
        else:
            # Fallback based on columns?
            if "mc" in df.columns and "mn" in df.columns and len(df.columns) < 10:
                category = ScoreEventType.CAT_MEASURE
            elif "midi" in df.columns or "tpc" in df.columns:
                category = ScoreEventType.CAT_NOTE
            else:
                category = ScoreEventType.CAT_ANNOTATION
        
        # Determine has_rests
        # DCML TSV often omits rests or uses special encoding.
        has_rests = False
        # If 'midi' column has NaNs or special val? 
        # Usually rests are not in notes.tsv.
        
        events = []
        
        # Map DataFrame columns to ScoreEventStore schema
        # Expected TSV cols: mc, mn, onset, duration, midi, tpc, staff, voice, ...
        
        for _, row in df.iterrows():
            etype = ScoreEventType.NOTE
            if category == ScoreEventType.CAT_MEASURE:
                etype = ScoreEventType.MEASURE
            elif category == ScoreEventType.CAT_CONTROL:
                etype = str(row.get("label", ScoreEventType.DIRECTION))
            
            # Extract pitch info
            ep = row.get("midi") # ms3 calls it 'midi'
            if pd.isna(ep): ep = None
            else: ep = int(ep)
            
            tpc = row.get("tpc")
            if pd.isna(tpc): tpc = None
            else: tpc = int(tpc)
            
            # Spelled pitch
            sp = None
            # ms3 uses 'name', 'octave' or just 'pitch'?
            # Usually step/alter/octave columns exist if not strictly just tpc.
            if "step" in row and "octave" in row:
                sp = {
                    "step": str(row["step"]),
                    "alter": int(row.get("alter", 0)),
                    "octave": int(row["octave"])
                }
            
            # Timing
            # ms3 usually outputs 'onset', 'duration' in quarter lengths (musical time) which fits 'divs' or 'beats'?
            # Actually ms3 aims for musical unity.
            
            start = float(row.get("onset", row.get("start", 0)))
            dur = float(row.get("duration", 0))
            
            events.append({
                "id": str(row.get("id", f"{category}_{start}_{row.name}")),
                "temporal_type": "interval" if dur > 0 else "instant",
                "event_type": str(etype),
                "event_category": str(category),
                "start": start,
                "end": start + dur,
                "duration": dur,
                "ep": ep,
                "tpc": tpc,
                "sp": sp,
                "mn": str(row.get("mn", "")),
                "mc": int(row.get("mc", 0)) if not pd.isna(row.get("mc")) else None,
                "voice": int(row.get("voice")) if "voice" in row and not pd.isna(row["voice"]) else None,
                "staff": int(row.get("staff")) if "staff" in row and not pd.isna(row["staff"]) else None,
                "part_id": str(row.get("part", "P1")),
                "name": str(row.get("label", ""))
            })

        metadata = {
            "format": "tsv",
            "parser": "ms3",
            "has_rests": has_rests
        }
        
        return metadata, events
