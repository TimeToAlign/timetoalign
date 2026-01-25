# Symbolic Score Loaders: Testing & Verification

This directory contains tests and profiling scripts for the `timetoalign.loader.score` module, verifying the implementation of Partitura, Music21, and TSV loaders.

## Testing Strategy

We employ a **Cross-Validation Strategy** to ensure semantic consistency across different parsing libraries. Since all loaders map to a unified `ScoreEventStore` schema, we verify them by loading the same musical work (*Chopin Op. 10 No. 3*) in three different formats and asserting that the resulting event graphs are commensurable.

### Validation Logic
1. **Schema Compliance**: All loaders must populate the strict typed fields (`tpc`, `ep`, `sp`, `mn`, `mc`, `event_category`).
2. **Event Counts**: We assert that the number of `Note` events is consistent across loaders (allowing for minor deviations due to grace-note/ornament handling differences between parsers).
    - **Partitura**: MIDI/MusicXML parser.
    - **Music21**: Recursive structure parser.
    - **TSV**: Tabular data loader (ms3).
3. **Type Safety**: PyArrow schemas are strictly enforced. String fields (`mn`, `id`, `name`) are sanitized to prevent type coercion errors.

### Profiling Results
Benchmarks run on *Chopin Op. 10 No. 3* (n=5 loops).

| Loader | Format | Time (avg) | Notes |
|---|---|---|---|
| **TSVLoader** | TSV (ms3) | ~130 ms | Fast. Direct tabular load. |
| **Music21Loader** | MusicXML | ~500 ms | Medium. Heavy object overhead. |
| **PartituraLoader** | MusicXML | ~900 ms | Slowest. Detailed analysis overhead. |

*Note: TSV is significantly faster as it bypasses complex parsing, loading pre-structured data.*

## Running Tests
```bash
pytest tests/loader/score/test_loaders.py
```

## Running Profiler
```bash
python3 tests/loader/score/profile.py
```
