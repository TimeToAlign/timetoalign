# Beethoven WoO71 Test Specimen

## Overview

Piano Trio in B-flat major, WoO 71, by Ludwig van Beethoven.

## Gold Standard Counts

| Metric | Exact Count | Derivation |
|--------|-------------|------------|
| **Notes** | **4753** | `wc -l WoO71.notes.tsv` = 4754 lines - 1 header |
| **Measures** | **397** | `wc -l WoO71.measures.tsv` = 398 lines - 1 header |

## Source

- **Corpus**: DCML (Digital and Cognitive Musicology Lab)
- **Tool**: MS3 (MuseScore 3 annotation tool)
- **Format**: MuseScore `.mscx` with TSV exports

## Verification

```bash
# Verify note count
$ wc -l WoO71.notes.tsv
4754 WoO71.notes.tsv  # 4754 - 1 header = 4753 notes

# Verify measure count
$ wc -l WoO71.measures.tsv
398 WoO71.measures.tsv  # 398 - 1 header = 397 measures
```

## Files

| File | Description |
|------|-------------|
| `WoO71.mscx` | MuseScore 3 source file |
| `WoO71.notes.tsv` | Gold standard note events |
| `WoO71.measures.tsv` | Gold standard measure boundaries |
| `WoO71.*.resource.json` | MS3 resource metadata |

## Usage in Tests

```python
# Gold standard constants
BEETHOVEN_WOO71_GOLD_NOTES = 4753
BEETHOVEN_WOO71_GOLD_MEASURES = 397

# Test exact count
assert notes_timeline.n_events == BEETHOVEN_WOO71_GOLD_NOTES
```

## Notes

- This is a complex piece with 397 measures spanning multiple movements
- Useful for stress-testing loaders with larger scores
- Complements the Chopin Op.10 No.3 specimen (498 notes, 22 measures)
