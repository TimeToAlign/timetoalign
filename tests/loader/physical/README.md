# Physical Loader Tests

Tests for the physical-domain loaders in `timetoalign.loader.physical`.

## Test Files

### `test_audio.py` (24 tests)

Tests for `AudioLoader` against minimal in-memory WAV files.

Durations are asserted **exactly**, with zero tolerance: `AudioLoader`
computes `duration_seconds = n_samples / sample_rate` and `SamplesToSeconds`
performs the same division, so every duration in these tests is bit-identical
to the value expression and is checked with `==` (no `pytest.approx`). The
integer-sample fixtures divide out cleanly (44100/44100 = `1.0`, 96000/48000 =
`2.0`, 22050/44100 = `0.5`); the 10-sample edge case is pinned as `10 / 44100`,
the same double the C-map returns. No approx assertions remain in this file.

### `test_repovizz_loader.py` (27 tests)

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
| `TestRepoVizzLoaderIntegration` | 2 | Cross-recording content and group iteration |

**Exact counts (zero tolerance).** Both the `Normal` and `Mechanical`
recordings catalogue exactly **376** entries, of which **232** become
timelines (**144** audio, **4** score entries), and both expose the same
group list `["audio", "descriptors", "mocap", "score"]`. Durations are exact:
a signal entry's `duration_seconds` is `n_samples / sample_rate` (asserted with
`==`, not `approx`) — the 441000-sample / 44100 Hz `CatalogueEntry` gives
exactly `10.0`, and the legacy-CSV `duration_seconds` equals
`n_samples / frame_rate` bit-for-bit. `TestRepoVizzLoaderIntegration.test_multiple_recordings`
no longer merely checks "both load"; it pins the counts above **and** the fact
that the two takes carry distinct audio content: the shared cardioid-ambient
entry (`ROOT0_Audi1_Audi0_Ambi0`, "Cardioid microphone", 44100 Hz) has
**11753638** samples in the Normal recording and **12426696** in the
Mechanical one.

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
| `test_repovizz_loader.py` | 27 | All pass |
| `test_audio.py` | 24 | All pass |
| **Total** | **51** | **All pass** |

All tests pass in parallel mode (`pytest-xdist -n auto`).
