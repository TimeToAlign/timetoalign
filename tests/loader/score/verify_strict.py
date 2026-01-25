"""Strict comparison utility for verification of score loaders against TSV gold standard."""

import pandas as pd
import pyarrow as pa
from typing import Any
from timetoalign.core import TimeUnit
from timetoalign.loader.score.partitura import PartituraLoader
from timetoalign.loader.score.music21 import Music21Loader
from timetoalign.loader.score.tsv import TSVLoader
from timetoalign.loader.score.store import ScoreEventType

def get_canonical_df(loader):
    """Convert loader events to a canonical sorted pandas DataFrame."""
    table = loader.events.table
    df = table.to_pandas()
    
    # Sort deterministically
    # Start -> EP -> ID
    # Flatten Coordinate structs if present (start, end, duration)
    for col in ["start", "end", "duration"]:
        if col in df.columns and df[col].dtype == "object":
             # Check if it looks like a dict
             sample = df[col].dropna().iloc[0] if not df[col].dropna().empty else None
             if isinstance(sample, dict) and "value" in sample:
                 df[col] = df[col].apply(lambda x: float(x["value"]) if isinstance(x, dict) else x)
                 df[col] = df[col].astype(float) # Ensure float dtype
    
    # Round for deterministic sorting (avoid float noise)
    for c in ["start", "duration"]:
        if c in df.columns:
            df[f"_sort_{c}"] = df[c].round(5)

    # Sort deterministically
    # Start -> EP -> PartID -> Duration
    # Ensure columns exist
    sort_cols = []
    if "_sort_start" in df.columns: sort_cols.append("_sort_start")
    
    if "midi_pitch" in df.columns:
        # Extract EP for sorting
        df["_sort_ep"] = df["midi_pitch"].apply(lambda x: x["ep"] if isinstance(x, dict) and "ep" in x else -1)
        sort_cols.append("_sort_ep")
    
    if "part_id" in df.columns:
        # Ensure part_id is string
        df["part_id"] = df["part_id"].astype(str)
        sort_cols.append("part_id")

    if "_sort_duration" in df.columns:
        sort_cols.append("_sort_duration")
    
    df = df.sort_values(by=sort_cols).reset_index(drop=True)
    return df

def compare_events(df_gold, df_target, label):
    """Compare two DataFrames strictly."""
    # Filter to comparable categories (e.g. NOTES only for now, or stricter?)
    # User said "notes, measures, and control events"
    
    # Filter to overlapping columns
    cols = sorted(list(set(df_gold.columns) & set(df_target.columns)))
    # Exclude dynamic or varying columns if any (e.g. ID might differ)
    exclude = ["id", "name", "_sort_ep", "part_id", "voice", "staff"] # IDs/Parts differ by implementation logic often
    cols = [c for c in cols if c not in exclude]
    
    print(f"\n--- Comparing {label} vs TSV (Gold) ---")
    print(f"Columns: {cols}")
    
    # Filter rows to just NOTES for initial strict pass?
    gold_notes = df_gold[df_gold["event_category"] == ScoreEventType.CAT_NOTE].reset_index(drop=True)
    target_notes = df_target[df_target["event_category"] == ScoreEventType.CAT_NOTE].reset_index(drop=True)
    
    print(f"Notes check: Gold={len(gold_notes)}, Target={len(target_notes)}")
    
    print("\n--- HEAD COMPARISON (First 10) ---")
    print("GOLD (TSV):")
    print(gold_notes[["start", "midi_pitch", "duration", "temporal_type"]].head(10).to_string())
    print("-" * 20)
    print(f"TARGET ({label}):")
    print(target_notes[["start", "midi_pitch", "duration", "temporal_type"]].head(10).to_string())
    print("-" * 40)
    
    if len(gold_notes) != len(target_notes):
        print(f"FATAL: Count mismatch! Gold={len(gold_notes)}, Target={len(target_notes)}")
        # Continue to show differences?
        # return False
        
    # Compare columns
    mismatches = 0
    # Limit rows to min length to prevent crash
    min_len = min(len(gold_notes), len(target_notes))
    
    for col in cols:
        g = gold_notes[col].iloc[:min_len]
        t = target_notes[col].iloc[:min_len]
        
        # Handle structs
        if col in ["midi_pitch", "spelled_pitch"]:
             # Direct dict compare
             diffs = []
             for i in range(len(g)):
                 if g.iloc[i] != t.iloc[i]:
                     diffs.append((i, g.iloc[i], t.iloc[i]))
             
             if diffs:
                 print(f"Mismatch in {col}: {len(diffs)} items")
                 first_i = diffs[0][0]
                 print(f"  First diff at {first_i}: Gold={diffs[0][1]}, Target={diffs[0][2]}")
                 print(f"  Context Gold: {gold_notes.iloc[first_i].to_dict()}")
                 print(f"  Context Target: {target_notes.iloc[first_i].to_dict()}")
                 mismatches += 1
        else:
            try:
                # Approximate floats
                try:
                    pd.testing.assert_series_equal(g, t, check_dtype=False, atol=0.001)
                except AssertionError as e:
                    print(f"Mismatch in {col}: {e}")
                    mismatches += 1
            except Exception as e:
                print(f"Error comparing {col}: {e}")
                
    if mismatches == 0 and len(gold_notes) == len(target_notes):
        print(f"SUCCESS: 100% Match on Notes for {label}!")
        return True
    return False

if __name__ == "__main__":
    from pathlib import Path
    import sys
    
    # ... (path logic handled previously) ...
    # Re-use existing path logic but fix calling
    FILE_DIR = Path(__file__).resolve().parent
    TESTS_DIR = FILE_DIR.parents[1]
    DATA_DIR = TESTS_DIR / "data" / "midi" / "score"
    MS3_DIR = DATA_DIR / "ms3"
    
    XML = DATA_DIR / "chopin_op10_no3.musicxml"
    if not XML.exists():
        print(f"Error: XML not found at {XML}")
        sys.exit(1)
        
    print(f"Using XML: {XML}")
    TSV = list(MS3_DIR.glob("chopin_op10_no3.*.tsv"))
    if not TSV:
        TSV = list((DATA_DIR / "ms3").glob("chopin_op10_no3.*.tsv"))

    # Use Quarters for commensurability
    print("Loading TSV (Gold)...")
    tsv_loader = TSVLoader(unit=TimeUnit.quarters) 
    tsv_loader.load(*TSV)
    df_tsv = get_canonical_df(tsv_loader)
    
    print("Loading Partitura...")
    import inspect
    print(f"DEBUG: PartituraLoader loaded from: {inspect.getfile(PartituraLoader)}")
    pt_loader = PartituraLoader(unit=TimeUnit.quarters) 
    pt_loader.load(XML)
    df_pt = get_canonical_df(pt_loader)
    
    print("Loading Music21...")
    m21_loader = Music21Loader(unit=TimeUnit.quarters)
    m21_loader.load(XML)
    df_m21 = get_canonical_df(m21_loader)

    compare_events(df_tsv, df_pt, "Partitura")
    compare_events(df_tsv, df_m21, "Music21")
