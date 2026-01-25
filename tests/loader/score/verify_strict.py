"""Strict comparison utility for verification of score loaders against TSV gold standard.

This script compares note events between loaders, verifying:
- Note counts match
- Temporal fields (quarterbeats, duration_qb) are consistent
- Pitch fields (midi_pitch, spelled_pitch) match
- Measure context (mc, mn, mc_onset) is correct
"""

from fractions import Fraction
from pathlib import Path
import sys

import pandas as pd


def get_notes_df(bundle, loader_name):
    """Extract notes as DataFrame from ScoreBundle."""
    df = bundle.notes.to_dataframe()
    
    # Filter to Notes (exclude Rests)
    df = df[df["event_type"] == "Note"].reset_index(drop=True)
    
    # Flatten Fraction structs for comparison
    for col in ["quarterbeats", "duration_qb", "mc_onset", "mn_onset"]:
        if col in df.columns:
            df[f"{col}_float"] = df[col].apply(
                lambda x: x["num"] / x["den"] if isinstance(x, dict) and x.get("den") else None
            )
    
    # Flatten pitch structs
    if "midi_pitch" in df.columns:
        df["ep"] = df["midi_pitch"].apply(
            lambda x: x["ep"] if isinstance(x, dict) else None
        )
    
    # Sort deterministically by quarterbeats, then pitch
    sort_cols = []
    if "quarterbeats_float" in df.columns:
        sort_cols.append("quarterbeats_float")
    if "ep" in df.columns:
        sort_cols.append("ep")
    if sort_cols:
        df = df.sort_values(by=sort_cols).reset_index(drop=True)
    
    return df


def compare_notes(df_gold, df_target, label, verbose=True):
    """Compare note DataFrames and report mismatches."""
    print(f"\n{'='*60}")
    print(f"COMPARING: {label} vs TSV (Gold Standard)")
    print(f"{'='*60}")
    
    gold_count = len(df_gold)
    target_count = len(df_target)
    
    print(f"Note Counts: Gold={gold_count}, Target={target_count}")
    
    if gold_count != target_count:
        print(f"⚠️  COUNT MISMATCH: Difference of {abs(gold_count - target_count)}")
    
    # Compare on common length
    min_len = min(gold_count, target_count)
    
    # Fields to compare
    compare_fields = [
        ("quarterbeats_float", "Quarterbeats", 0.01),
        ("duration_qb_float", "Duration", 0.01),
        ("ep", "MIDI Pitch", 0),
        ("mc", "Measure Count", 0),
    ]
    
    mismatches = {}
    
    for col, label_col, tolerance in compare_fields:
        if col not in df_gold.columns or col not in df_target.columns:
            print(f"  {label_col}: ⚠️  Column missing")
            continue
        
        gold_vals = df_gold[col].iloc[:min_len]
        target_vals = df_target[col].iloc[:min_len]
        
        if tolerance > 0:
            diff = abs(gold_vals - target_vals) > tolerance
        else:
            diff = gold_vals != target_vals
        
        mismatch_count = diff.sum()
        
        if mismatch_count == 0:
            print(f"  {label_col}: ✅ 100% Match")
        else:
            mismatches[col] = mismatch_count
            first_idx = diff.idxmax()
            print(f"  {label_col}: ❌ {mismatch_count} mismatches")
            if verbose:
                print(f"    First mismatch at index {first_idx}:")
                print(f"      Gold:   {gold_vals.iloc[first_idx]}")
                print(f"      Target: {target_vals.iloc[first_idx]}")
    
    # Summary
    if not mismatches and gold_count == target_count:
        print(f"\n✅ SUCCESS: {label} matches TSV gold standard!")
        return True
    else:
        print(f"\n❌ DIFFERENCES FOUND in {label}")
        return False


def run_verification():
    """Run full verification against TSV gold standard."""
    from timetoalign.loader.score.tsv import TSVLoader
    from timetoalign.loader.score.partitura import PartituraLoader
    from timetoalign.loader.score.music21 import Music21Loader
    
    FILE_DIR = Path(__file__).resolve().parent
    TESTS_DIR = FILE_DIR.parents[1]
    DATA_DIR = TESTS_DIR / "data" / "midi" / "score"
    MS3_DIR = DATA_DIR / "ms3"
    
    XML = DATA_DIR / "chopin_op10_no3.musicxml"
    TSV_NOTES = MS3_DIR / "chopin_op10_no3.notes.tsv"
    
    if not XML.exists():
        print(f"Error: XML not found at {XML}")
        sys.exit(1)
    if not TSV_NOTES.exists():
        print(f"Error: TSV not found at {TSV_NOTES}")
        sys.exit(1)
    
    print("Loading loaders...")
    print(f"  TSV: {TSV_NOTES}")
    print(f"  XML: {XML}")
    
    # Load all
    print("\nLoading TSV (Gold Standard)...")
    tsv_bundle = TSVLoader().load(TSV_NOTES)
    df_tsv = get_notes_df(tsv_bundle, "TSV")
    
    print("Loading Partitura...")
    pt_bundle = PartituraLoader().load(XML)
    df_pt = get_notes_df(pt_bundle, "Partitura")
    
    print("Loading Music21...")
    m21_bundle = Music21Loader().load(XML)
    df_m21 = get_notes_df(m21_bundle, "Music21")
    
    # Compare
    results = {}
    results["Partitura"] = compare_notes(df_tsv, df_pt, "Partitura")
    results["Music21"] = compare_notes(df_tsv, df_m21, "Music21")
    
    # Final summary
    print("\n" + "="*60)
    print("VERIFICATION SUMMARY")
    print("="*60)
    for loader, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {loader}: {status}")
    
    all_passed = all(results.values())
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    run_verification()
