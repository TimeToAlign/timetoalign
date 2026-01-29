# Display Module Tests

This directory contains tests for the `timetoalign.display` module, which provides
ASCII/Unicode terminal visualization for TimeToAlign! objects.

## Test File: `test_ascii.py`

### Overview

The test suite validates the pure-ASCII display functionality with **38 tests** covering:
- Character set definitions and completeness
- Helper function correctness
- Timeline, group, and bundle diagram rendering
- Unicode and ASCII fallback modes

### Validation Logic

#### 1. Character Set Tests (`TestCharacterSets`)

**What we validate:**
- All 6 core timeline type combinations have assigned characters
- Each character is exactly 1 character (for consistent column width)
- Core timeline characters are unique (no ambiguity in visual representation)
- Tree and box drawing character sets are complete

**Why this matters:**
The display module relies on consistent character mappings. If a timeline type lacks
a character, users would see `?` placeholders. The uniqueness test ensures users can
visually distinguish timeline types at a glance.

**Character mapping (NumberType, Domain) → Character:**
| NumberType | Domain    | Unicode | ASCII |
|------------|-----------|---------|-------|
| int        | graphical | `:`     | `:`   |
| float      | graphical | `=`     | `=`   |
| int        | physical  | `⋅`     | `.`   |
| float      | physical  | `~`     | `~`   |
| int        | logical   | `,`     | `,`   |
| float      | logical   | `_`     | `_`   |
| fraction   | (any)     | (same as float) | |

#### 2. Coordinate Formatting Tests (`TestFormatCoordinate`)

**What we validate:**
- Integer values display without decimal points (e.g., `100` not `100.0`)
- Float values display with 1 decimal place (e.g., `150.5`)
- Values that are mathematically integers format as integers

**Why this matters:**
Clean coordinate display improves readability. `0 :::: 4835 pixels` is clearer than
`0.0 :::: 4835.0 pixels`.

#### 3. Name Elision Tests (`TestElideName`)

**What we validate:**
- Names within the max width pass through unchanged
- Names exceeding max width get `...` suffix
- Edge cases (very short max_width) are handled gracefully

**Why this matters:**
Child timeline names must fit in fixed-width columns. Elision ensures long names
like `very_long_system_name_123` become `very_lon...` without breaking layout.

#### 4. Timeline Character Tests (`TestGetTimelineChar`)

**What we validate:**
- Each of the 6 concrete timeline types returns the correct character
- Unicode and ASCII modes return appropriate characters

**Why this matters:**
This is the core mapping that makes the display work. Each test creates an actual
timeline instance and verifies `_get_timeline_char()` returns the expected character.

#### 5. Child Truncation Tests (`TestGetChildrenToDisplay`)

**What we validate:**
- No truncation when children ≤ max_children
- Correct split into first/last groups when truncation is needed
- Accurate omitted count calculation

**Algorithm tested:**
```
Given: 10 children, max_children=6
Split: first_count = (6+1)//2 = 3, last_count = 6-3 = 3
Result: first 3 children, "... (4 more children)", last 3 children
```

**Why this matters:**
Without truncation, a timeline with 50 children would produce unreadable output.
The truncation shows first and last children with a clear count of omitted items.

#### 6. Child Row Building Tests (`TestBuildChildRow`)

**What we validate:**
- Row contains tree prefix (├─ or └─), name, coordinates, bar, and end coordinate
- Last child uses └─, others use ├─
- Bar characters are positioned proportionally on the parent scale

**Why this matters:**
The child row is the core visual element showing how children map to parent coordinates.
A child at offset 250 with length 500 on a parent of length 1000 should have its bar
positioned at 25% of the width, spanning 50% of the total.

#### 7. Timeline Diagram Tests (`TestTimelineDiagram`)

**What we validate:**
- Basic output includes class name, ID, and bar
- Children appear as properly formatted rows
- `show_children=False` hides child rows (but mentions count in header)
- ASCII mode produces output without Unicode characters
- `parent_id` annotation appears in header

**Example validated output:**
```
DiscreteGraphicalTimeline[page] (3 children)
0 :::::::::::::::::::::::::::::::::::: 1000 pixels
  ├─ System 1     0 :::::         300
  ├─ System 2   350       :::::   650
  └─ System 3   700            :::950
```

#### 8. Group Diagram Tests (`TestGroupDiagram`)

**What we validate:**
- Header shows group ID, timeline count, and timestamp count
- Box border is drawn with proper Unicode/ASCII characters
- All member timelines appear inside the box
- Footer shows timestamp count

#### 9. Bundle Diagram Tests (`TestBundleDiagram`)

**What we validate:**
- Header shows bundle ID
- Groups are rendered with indentation
- Match claims footer is present

#### 10. Integration Tests (`TestDiagramMethods`)

**What we validate:**
- `Timeline.diagram()` returns identical output to `timeline_diagram(tl)`
- `TimelineGroup.diagram()` returns identical output to `group_diagram(group)`
- `AlignmentBundle.diagram()` returns identical output to `bundle_diagram(bundle)`
- Parameters (width, unicode, etc.) are passed through correctly

**Why this matters:**
Users interact with the `.diagram()` method, not the module functions. These tests
ensure the convenience methods are correctly wired to the underlying implementation.

## Running Tests

```bash
# Run only display tests
cd timetoalign
python -m pytest tests/display/ -v

# Run with coverage
python -m pytest tests/display/ --cov=timetoalign.display --cov-report=term-missing
```

## Known Limitations

1. **Terminal width:** The `width` parameter controls output width but does not
   auto-detect terminal size. Users should pass an appropriate width.

2. **Very long coordinates:** Coordinate values over 6 digits may cause column
   misalignment. This is acceptable for the intended use case (music alignment).

3. **Deeply nested children:** Only immediate children are shown. Grandchildren
   are not displayed (by design - keeps output manageable).
