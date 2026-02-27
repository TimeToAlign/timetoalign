# Lab File Test Fixtures

Synthetic test files for `LabLoader` (Audacity/Praat label format).

## File Format

Tab-separated values with three columns:
1. `start` - start time in seconds (float)
2. `end` - end time in seconds (float)
3. `label` - region/event label (string)

No header row. Files use `.lab` or `.txt` extension.

## Test Files

| File | Purpose | Events | Coordinate Range |
|------|---------|--------|------------------|
| `regions.lab` | Structural regions (Intro, Verse, Chorus, Outro) | 6 intervals | 0.0 - 15.2 |
| `beats.lab` | Regular beat intervals | 6 intervals | 0.0 - 3.0 |
| `instants.lab` | Instant events (start == end) | 4 instants | 0.0 - 3.0 |

## Validation Values

These are the EXACT expected values for the ZERO TOLERANCE validation policy.

### regions.lab
- Event count: 6
- Temporal types: 6 intervals
- Labels: Intro, Verse, Chorus, Verse, Chorus, Outro
- Coordinate range: [0.0, 15.2]

### beats.lab
- Event count: 6
- Temporal types: 6 intervals
- Labels: all "Beat"
- Coordinate range: [0.0, 3.0]

### instants.lab
- Event count: 4
- Temporal types: 4 instants (start == end)
- Labels: all "Downbeat"
- Coordinate range: [0.0, 3.0]
