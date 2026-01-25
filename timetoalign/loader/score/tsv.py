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
        
        if not df.empty:
            # Vectorized Pitch Logic
            # 1. MIDI Pitch
            if "midi" in df.columns:
                df["ep"] = pd.to_numeric(df["midi"], errors="coerce").fillna(-1).astype(int)
                df["epc"] = df["ep"] % 12
                # Create struct column
                df["midi_pitch"] = df.apply(lambda r: {"ep": r["ep"], "epc": r["epc"]} if r["ep"] >= 0 else None, axis=1)
            else:
                df["midi_pitch"] = None

            # 2. Spelled Pitch
            if "name" in df.columns and "step" not in df.columns:
                # Derive step/alter from name
                df["step"] = df["name"].astype(str).str[0]
                # Alter is trickier. ms3 names are like "C#", "Bb".
                # Count sharps/flats? Or specific map.
                def get_alter_from_name(n):
                    if pd.isna(n): return 0
                    n = str(n)
                    if len(n) > 1:
                        if "#" in n: return n.count("#")
                        if "b" in n: return -n.count("b")
                        # Handle '-'?
                        if "-" in n: return -n.count("-")
                    return 0
                df["alter"] = df["name"].apply(get_alter_from_name)

            if "step" in df.columns and "octave" in df.columns:
                # Ensure types
                df["step"] = df["step"].astype(str)
                df["octave"] = pd.to_numeric(df["octave"], errors="coerce").fillna(4).astype(int)
                df["alter"] = pd.to_numeric(df.get("alter", 0), errors="coerce").fillna(0).astype(int)
                
                # GPC
                gpc_map = {'C': 0, 'D': 1, 'E': 2, 'F': 3, 'G': 4, 'A': 5, 'B': 6}
                df["gpc_int"] = df["step"].map(gpc_map).fillna(0).astype(int)
                df["gpc_str"] = df["step"]
                
                # Accidental String
                def get_acc_str(x):
                    if x > 0: return "♯" * x
                    if x < 0: return "♭" * abs(x)
                    return ""
                df["acc_str"] = df["alter"].apply(get_acc_str)
                
                # SPC (TPS)
                if "tpc" in df.columns:
                    df["spc_int"] = pd.to_numeric(df["tpc"], errors="coerce").fillna(0).astype(int)
                else:
                     base_fifths = {'F': -1, 'C': 0, 'G': 1, 'D': 2, 'A': 3, 'E': 4, 'B': 5}
                     df["spc_int"] = df["step"].map(base_fifths).fillna(0) + (7 * df["alter"])
                     df["spc_int"] = df["spc_int"].astype(int)
                
                df["spc_str"] = df["step"] + df["acc_str"]
                df["sp"] = df["spc_str"] + df["octave"].astype(str)
                df["cents"] = 0.0
                
                # Create struct column
                def make_sp_struct(r):
                    return {
                        "gpc_int": r["gpc_int"],
                        "gpc_str": r["gpc_str"],
                        "acc": r["alter"],
                        "spc_int": r["spc_int"],
                        "spc_str": r["spc_str"],
                        "sp": r["sp"],
                        "cents": r["cents"]
                    }
                df["spelled_pitch"] = df.apply(make_sp_struct, axis=1)
            else:
                df["spelled_pitch"] = None

        events = []
        
        # Map DataFrame columns to ScoreEventStore schema
        # Expected TSV cols: mc, mn, onset, duration, midi, tpc, staff, voice, ...
        
        for _, row in df.iterrows():
            etype = ScoreEventType.NOTE
            if category == ScoreEventType.CAT_MEASURE:
                etype = ScoreEventType.MEASURE
            elif category == ScoreEventType.CAT_CONTROL:
                etype = str(row.get("label", ScoreEventType.DIRECTION))
            
            # Timing
            # Prioritize 'quarterbeats', 'score_time', 'onset'
            start = float(row.get("quarterbeats", row.get("score_time", row.get("onset", row.get("start", 0)))))
            dur = float(row.get("duration_qb", row.get("duration", 0)))
            
            events.append({
                "id": str(row.get("id", f"{category}_{start}_{row.name}")),
                "temporal_type": "interval" if dur > 0 else "instant",
                "event_type": str(etype),
                "event_category": str(category),
                "start": start,
                "end": start + dur,
                "duration": dur,
                "midi_pitch": row.get("midi_pitch"),
                "spelled_pitch": row.get("spelled_pitch"),
                "octave": int(row["octave"]) if "octave" in row and pd.notna(row["octave"]) else None,
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
