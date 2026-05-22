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

- Exact row counts (ZERO TOLERANCE)
- Foreign-key resolution: `image_id` resolves via `images` table, `category_id`
  resolves via `categories` table (y->ies pluralisation)
- Parent context propagation in nested search (audio item scalars appear on hotCuePoints rows)
- Auto-detection correctly identifies all top-level keys with list-of-dict values

---

### `test_xml_loader.py` (45 tests)

Tests for `XmlLoader`, a generic XML-to-flat-table loader using `xml.etree.ElementTree`.

**Test Classes:**

| Class | Tests | Focus |
|-------|-------|-------|
| `TestXmlLoaderBasic` | 15 | Core functionality: loading, element extraction, attribute propagation |
| `TestXmlLoaderPrincipalTags` | 8 | Principal tag filtering and auto-detection |
| `TestXmlLoaderAncestorPropagation` | 6 | Ancestor attribute inheritance |
| `TestXmlLoaderRealSpecimens` | 10 | Real-world XML files (RepoVizz, MusicXML structure) |
| `TestXmlLoaderEdgeCases` | 6 | Error handling, empty files, malformed XML |

**Test Specimens:**

| Specimen | Principal Tags | Validation Focus |
|----------|---------------|------------------|
| RepoVizz XML manifest | Audio, Signal, Annotation | Hierarchical catalogue parsing |
| Inline test XML | Various | Attribute extraction, text content |

**Key Validations:**

- Ancestor attribute propagation (parent attributes appear on child rows)
- Principal tag filtering (extract only specified element types)
- Auto-detection of principal tags from XML structure
- Text content extraction as `_text` field
- Error handling for malformed XML

---

## Test Results

| Test File | Tests | Status |
|-----------|-------|--------|
| `test_json_loader.py` | 29 | All pass |
| `test_xml_loader.py` | 45 | All pass |
| **Total** | **74** | **All pass** |

All tests pass in parallel mode (`pytest-xdist -n auto`).
