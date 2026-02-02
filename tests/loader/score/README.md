# Symbolic Score Loaders: Testing & Verification

This directory contains tests and profiling scripts for the `timetoalign.loader.score` module.

## Architecture Overview

```
                    +---------------------------------------------+
                    |              FlowController                  |
                    |                                              |
   Input Sources:   |   +-------------------------------------+   |
                    |   |      Atomic Segment Builder          |   |
   next[] arrays ---+-->|  - derives segments from next logic  |   |
   (TSV, mm.json)   |   |  - identifies segment boundaries     |   |
                    |   |    from flow control markers         |   |
   partitura -------+-->|  - tracks jump/break coordinates     |   |
   segments         |   +-------------------+-----------------+   |
                    |                       |                      |
                    |                       v                      |
                    |   +-------------------------------------+   |
                    |   |    Playthrough Segment Grouper       |   |
                    |   |  - uses markers + volta attributes   |   |
                    |   |    to execute flow logic             |   |
                    |   |  - groups atomics per FlowMode       |   |
                    |   +-------------------+-----------------+   |
                    |                       |                      |
                    +---------------------------------------------+
                                            |
                                            v
                              +-------------------------+
                              |         Flow            |
                              |                         |
                              |  PlaythroughSegment[]   |
                              |  mode: FlowMode         |
                              |                         |
                              |  Comparison:            |
                              |  - is_equivalent()      |
                              +-------------------------+
```

All score loaders return a `ScoreStore` containing category-specific data:
- `NoteEventData`: Notes, rests, chords
- `MeasureData`: Measure boundaries with flow control
- `ControlEventData`: Dynamics, tempo, signatures
- `AnnotationEventData`: Text annotations

## Loader/Format Test Matrix

| Format | Loader | Input | Test Against |
|--------|--------|-------|--------------|
| MEI | Music21Loader | `.mei` | Valid flow_modes in .flow.csv |
| MusicXML | Music21Loader | `.musicxml` | Valid flow_modes in .flow.csv |
| MusicXML | PartituraLoader | `.musicxml` | Valid flow_modes in .flow.csv |
| TSV | partitura.load_dcml() | `.tsv` | Valid flow_modes in .flow.csv |
| TSV | TSVLoader | `.tsv` | Gold standard |
| mm.json | MeasureMapLoader | `.mm.json` | Valid flow_modes in .flow.csv |

**Note**: TSVLoader output from `*_unfolded.measures.tsv` serves as the gold standard (`default` flow_mode).

## Test File Organization

| File | Purpose | Concern |
|------|---------|---------|
| `test_loaders.py` | Basic unit tests for each loader | Loader functionality |
| `test_cross_validation.py` | Cross-validates loaders on Chopin (notes, pitch) | Data consistency |
| `test_measuremap_loader.py` | MeasureMapLoader-specific tests | MeasureMap parsing |
| `test_flow_control_parity.py` | Flow control extraction (repeat markers, voltas) | Flow control parsing |
| `test_flow_csv_validation.py` | Validates against .flow.csv ground truth | Flow validation |
| `test_flow_parity.py` | MC sequence parity tests | Flow computation |

## Flow Validation Strategy

### Test Logic

Each `.flow.csv` contains **1-5 valid unfoldings** (flow_mode entries). Tests compare loader output against ALL valid flows:

```python
def test_loader_produces_valid_flow(loader, specimen):
    # Get loader output as Flow
    flow = loader.compute_flow()  # Returns Flow with PlaythroughSegments

    # Load valid flows from ground truth
    valid_flows = load_valid_flows_from_csv(specimen)  # 1-5 Flow objects

    # Test passes if output matches ANY valid unfolding
    assert any(flow.is_equivalent(valid) for valid in valid_flows.values()), \
        f"Loader output doesn't match any valid unfolding"
```

### Test Outcomes

| Outcome | Meaning |
|---------|---------|
| **Match default** | Loader output equals the `default` flow_mode |
| **Match alternative** | Loader output equals another valid flow_mode |
| **No match (FAIL)** | Loader output doesn't match any valid unfolding |

### FlowMode Values

| Value | Description | Typical Source |
|-------|-------------|----------------|
| `default` | Most complete flow (all repeats) | `*_unfolded.measures.tsv` |
| `partitura_minimal` | partitura's atomic segments | MusicXML/MEI |
| `partitura_maximal` | partitura's full unfolding | MusicXML/MEI |
| `music21` | music21's expandRepeats() | MusicXML/MEI |
| `printed` | As printed (no unfolding) | Any |

## Cross-Validation Tests

We load *Chopin Op. 10 No. 3* using three loaders and verify consistency:

| Loader | Source | Notes | Measures | Controls |
|--------|--------|-------|----------|----------|
| TSVLoader | TSV (ms3) | 498 | - | - |
| PartituraLoader | MusicXML | 498 | 22 | 27 |
| Music21Loader | MusicXML | 498+12 rests | 22 | 11 |

### Validation Checks

1. **Note Count Consistency**: All loaders return 498 Notes (rests tracked separately)
2. **Temporal Schema**: `quarterbeats` stored as Fraction structs `{num, den}`
3. **Pitch Schema**: `midi_pitch` and `spelled_pitch` fully populated
4. **Measure Context**: `mc`, `mn`, `mc_onset` correctly computed

## MeasureMapLoader Tests

### Test Categories

| Class | Description | Tests |
|-------|-------------|-------|
| `TestMeasureMapLoaderBasic` | Basic loader functionality | Import, init, load specimen |
| `TestMeasureMapExpansion` | Compression/expansion logic | Minimal, anacrusis, repeats |
| `TestMeasureMapValidation` | Validation rules | MC unique, qstamp monotonic, next valid |
| `TestMeasureMapTraversal` | Traversal computation | Simple, repeat, unfolded count |
| `TestMeasureMapCrossValidation` | Cross-loader validation | Count match, MC match, flow control |
| `TestMeasureDataSchema` | Schema validation | Flow control fields, identity fields |
| `TestFlowControlSpecimen` | Complex flow control | Load flow_control specimen |

### Gold Standard Specimens

| File | Location | Description | Count |
|------|----------|-------------|-------|
| `WoO71.measures.mm.json` | `beethoven_woo71/` | Folded MeasureMap | 397 MCs |
| `WoO71.measures.tsv` | `beethoven_woo71/` | Folded TSV (ms3) | 397 rows |
| `WoO71_unfolded.measures.tsv` | `beethoven_woo71/` | Unfolded traversal | 505 rows |
| `*.mm.json` | `flow_control/flow_only/` | Complex flow control | Variable |

## Flow Control Parity Tests

Cross-validation tests ensuring all score loaders extract flow control information consistently.

### Loader Model Classification

| Model | Loaders | Behavior |
|-------|---------|----------|
| **Marker** | TSV, MeasureMap, Music21 | Reports barline markers as individual events |
| **Region** | Partitura | Infers missing start/end to create complete regions |

**Marker-based loaders** produce identical counts and are validated together.
**Partitura** is tested separately with adjusted expectations.

### Known Discrepancy: Partitura Region Model

Partitura models repeats as **regions** (start/end boundary pairs) rather than **markers**.
When encountering an orphan repeat end without a start, Partitura infers a start point.

This is **expected behavior** and documented in test docstrings.

## Running Tests

```bash
# Run all score loader tests
pytest tests/loader/score/ -v

# Run specific test file
pytest tests/loader/score/test_flow_csv_validation.py -v

# Run with coverage
pytest tests/loader/score/ --cov=timetoalign.loader.score

# Run diagnostic output
pytest tests/loader/score/test_flow_parity.py::TestDiagnosticOutput -v -s
```

## Profiling

Benchmarks on *Chopin Op. 10 No. 3*:

| Loader | Format | Time (avg) | Notes |
|--------|--------|------------|-------|
| TSVLoader | TSV (ms3) | ~150 ms | Fastest. Direct load. |
| Music21Loader | MusicXML | ~400 ms | Medium. Object overhead. |
| PartituraLoader | MusicXML | ~700 ms | Slowest. Detailed analysis. |

```bash
python tests/loader/score/profile.py
```

## Validation Policy

Per the **ZERO TOLERANCE VALIDATION POLICY** (AGENTS.md):

1. **EXACT COUNTS REQUIRED**: All assertions use exact expected values
2. **NO TOLERANCE WITHOUT ROOT CAUSE**: Any tolerance must be documented
3. **MISMATCHES MUST BE INVESTIGATED**: "Close enough" is never acceptable
4. **GOLD STANDARD IS AUTHORITATIVE**: TSV from ms3 defines correct values
5. **LOADER PARITY IS REQUIRED**: Same input must produce equivalent outputs

## Test Data

Located in `tests/data/`:

- `midi/score/`: Chopin Op. 10 No. 3 (MusicXML + TSV)
- `score/`: All specimens (see `.agent/skills/co-create-groundtruth/references/specimens.md`)
- `target_flows/`: Ground truth `.flow.csv` files
