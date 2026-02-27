# ATON File Test Fixtures

Synthetic test files for `ATONLoader` (ATON format used by Stanford SUPRA project).

## File Format

ATON (Artistic Text-based Object Notation) is a structured text format with:
- Lines starting with `@@` for comments and block markers
- Lines starting with `@KEY:` for key-value metadata
- `@@BEGIN: SECTION` / `@@END: SECTION` for block structures

See: http://aton.sapp.org

## Test Files

| File | Purpose | Holes | Size |
|------|---------|-------|------|
| `minimal.aton` | Fast unit testing | 5 | ~2KB |

For comprehensive testing with real data, see:
`tests/data/supra/image/fd660zf8362_analysis.txt` (10MB, 30092 holes)

## Validation Values (EXACT - ZERO TOLERANCE)

### minimal.aton

**ROLLINFO metadata:**
- IMAGE_WIDTH: 1024
- IMAGE_LENGTH: 2000
- LENGTH_DPI: 300.00
- TRACKER_HOLES: 100
- FIRST_HOLE: 100
- LAST_HOLE: 1900
- MUSICAL_LENGTH: 1800
- MUSICAL_HOLES: 5
- MUSICAL_NOTES: 5

**HOLE blocks:**
- Total holes: 5
- Hole IDs: H1_N1, H2_N2, H3_N3, H4_N4, H5_N5
- MIDI keys: 60, 62, 64, 65, 67 (C4, D4, E4, F4, G4)
- Origin rows: 100, 300, 500, 800, 1900
- All holes have NOTE_ATTACK set (musical holes)

**First hole (H1_N1) exact values:**
- origin_row: 100
- origin_col: 200
- width_row: 20
- width_col: 15
- centroid_row: 110.5
- centroid_col: 207.5
- area: 280
- perimeter: 70.0
- circularity: 0.72
- tracker_hole: 60
- midi_key: 60
- note_attack: 100
- off_time: 120
