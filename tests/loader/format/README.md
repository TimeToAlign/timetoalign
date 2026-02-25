# Format Loader Tests

Tests for the format-level loaders in `timetoalign.loader.format`.

## Test Files

### `test_json_loader.py` (29 tests)

Tests for `JsonLoader`, the configurable JSON normaliser that produces flat
PyArrow tables from nested JSON structures.

**Test Specimens:**

| Specimen | Principal Keys | Expected Rows | Validation Focus |
|----------|---------------|---------------|------------------|
| `dj_studio_data.json` | `["audio"]` | 3 | Direct top-level array |
| `dj_studio_data.json` | `["hotCuePoints"]` | 24 | Recursive nested search, parent context propagation |
| `Wagner_WWV086B_140.json` | auto-detect | 15 + 30 + 10 (3 tables) | Auto-detection of all top-level arrays |
| `all_annotations.json` | `["annotations"]` | 6345 | Foreign-key resolution (`image_id` -> images, `category_id` -> categories) |

**Specimen Provenance:**

- `dj_studio_data.json`: DJ Studio export (audio metadata with nested cue points).
  Located at `tests/data/audio/hard_techno/dj_studio_data.json`.
- `Wagner_WWV086B_140.json`: Audiolabs OMR bounding boxes for Wagner WWV086B page 140.
  Located at `tests/data/audiolabs_omr/Wagner_WWV086B-3/json/Wagner_WWV086B_140.json`.
- `all_annotations.json`: COCO-style object detection annotations for Audiolabs OMR.
  Located at `tests/data/audiolabs_omr/all_annotations.json`.

**Key Validations:**

- Exact row counts (ZERO TOLERANCE per AGENTS.md Section 3.6)
- Foreign-key resolution: `image_id` resolves via `images` table, `category_id`
  resolves via `categories` table (y->ies pluralisation)
- Parent context propagation in nested search (audio item scalars appear on hotCuePoints rows)
- Auto-detection correctly identifies all top-level keys with list-of-dict values

## Test Results

All 29 tests pass in parallel mode (`pytest-xdist`).
