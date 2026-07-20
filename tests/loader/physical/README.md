# Physical Loader Tests

Tests for the physical-domain loaders in `timetoalign.loader.physical`.

## Test Files

### `test_repovizz_loader.py` (26 tests)

Tests for `RepoVizzLoader`, a manifest-style loader for RepoVizz XML manifests
and legacy 2-line CSV sensor files from the EEP (Expressive Ensemble Performance)
dataset.

**Test Classes:**

| Class | Tests | Focus |
|-------|-------|-------|
| `TestCatalogueEntry` | 3 | Frozen dataclass for catalogue entries |
| `TestRepovizzDictStore` | 2 | DictStore subclass with category properties |
| `TestRepoVizzLoaderXmlMode` | 8 | XML manifest parsing and timeline creation |
| `TestRepoVizzLoaderCsvMode` | 7 | Legacy CSV backwards compatibility |
| `TestRepoVizzLoaderErrors` | 4 | Error handling and edge cases |
| `TestRepoVizzLoaderIntegration` | 2 | Cross-recording and group iteration |

**Test Specimens:**

| Specimen | Location | Validation Focus |
|----------|----------|------------------|
| `StringQuartetEEP_I_Normal.xml` | `tests/data/score/beethoven_op18-4iv_multimodal/` | XML manifest with 376 catalogue entries |
| `StringQuartetEEP_I_Mechanical.xml` | `tests/data/score/beethoven_op18-4iv_multimodal/` | Alternative recording XML |
| `vln1_bow_vel.csv` | `tests/data/score/beethoven_op18-4iv_multimodal/` | Legacy 2-line RepoVizz CSV |

**Key Validations:**

- XML manifest creates correct catalogue entries by group (audio, score, descriptors, mocap)
- Timeline creation with `SamplesToSeconds` conversion map attached
- Backwards compatibility: CSV files still load with legacy behaviour
- Group filtering and TimelineGroup creation, including explicit catalogue selection via the `entries` keyword
- Catalogue entry lookup by ID, name, or partial match

**Specimen Provenance:**

The EEP multimodal dataset contains string quartet recordings with:
- Audio recordings (ambient + pickup microphones)
- Essentia audio descriptors (tonal, lowlevel, rhythm)
- Bowing gesture descriptors (9 per instrument)
- MoCap position data (48 markers x 3 axes)
- Score alignment files (.notes)

Each recording directory has an XML manifest cataloguing all 332+ data files.

---

## Test Results

| Test File | Tests | Status |
|-----------|-------|--------|
| `test_repovizz_loader.py` | 26 | All pass |
| `test_audio_loader.py` | (existing) | All pass |
| **Total** | **26+** | **All pass** |

All tests pass in parallel mode (`pytest-xdist -n auto`).
