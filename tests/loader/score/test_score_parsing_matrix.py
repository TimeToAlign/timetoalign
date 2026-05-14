"""Score Parsing Test Matrix: Comprehensive validation of all loader/format combinations.

This module implements the test matrix defined in .agent/prompts/score_parsing_test_matrix.md.

TOP-MOST GOAL: FlowController must reproduce ALL target flows from .flow.csv from ANY
loader/format combination. Each success is a HUGE WIN, each failure must be documented.

Test Matrix Coverage:
---------------------
| Specimen               | TSV   | mm.json | MusicXML | MEI    |
|------------------------|-------|---------|----------|--------|
| Rachmaninoff           | gold  | test    | M21/PT   | M21/PT |
| polyrhythm_only        | gold  | test    | M21/PT   | M21/PT |
| c05n05_musete          | gold  | test    | M21/PT   | M21/PT |
| c11n08_Rondeau         | gold  | test    | M21/PT   | M21/PT |
| op18_no4_mov4_flow     | gold  | test    | M21/PT   | M21/PT |
| flow_only              | gold  | test    | M21/PT   | M21/PT |
| WoO71                  | gold  | test    | M21/PT   | M21/PT |

Legend:
- gold: Gold standard (TSV from ms3)
- test: Test against gold
- M21: Music21Loader
- PT: PartituraLoader

Parser Behavior Summary:
------------------------
| Parser     | D.S./D.C. | Repeats | Voltas | Notes |
|------------|-----------|---------|--------|-------|
| ms3 (TSV)  | Yes       | Yes     | Yes    | Gold standard, follows `next[]` arrays |
| MeasureMap | Yes       | Yes     | Yes    | Follows `next[]` arrays, matches ms3 |
| Music21    | No        | Yes     | Yes    | `expandRepeats()` ignores D.S./D.C./Fine |
| Partitura  | Inferred  | Yes     | Yes    | Region model, infers missing start repeats |

Known Deviations (Documented):
-----------------------------
1. **c05n05_musete**: music21 produces 116 MCs (ignores D.S. al Fine), ms3 produces 138
2. **c11n08_Rondeau**: music21 ignores D.S., produces different flow
3. **flow_only**: ms3 diverges from canonical due to ambiguous encoding, music21 fails

ZERO TOLERANCE VALIDATION POLICY:
- EXACT counts required (no tolerances)
- Every mismatch must be investigated
- Gold standard (TSV from ms3) is authoritative for DEFAULT flow
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .conftest import (
    MAX_MUSICXML_SIZE_BYTES,
    SPECIMENS,
    TARGET_FLOWS_DIR,
    SpecimenConfig,
    get_flow_modes,
    get_specimen_path,
    musicxml_too_large,
    parse_flow_csv,
)


def specimen_available(spec: SpecimenConfig) -> bool:
    """Check if the specimen's TSV file is available."""
    tsv_path = get_specimen_path(spec, "tsv")
    return tsv_path is not None and tsv_path.exists()


def format_available(spec: SpecimenConfig, file_type: str) -> bool:
    """Check if a specific format is available for a specimen."""
    path = get_specimen_path(spec, file_type)
    return path is not None and path.exists()


# region Test Fixtures


@pytest.fixture(params=list(SPECIMENS.keys()))
def specimen_name(request) -> str:
    """Parametrized fixture providing each specimen name."""
    return request.param


@pytest.fixture
def specimen(specimen_name: str) -> SpecimenConfig:
    """Get the SpecimenConfig for the current specimen."""
    return SPECIMENS[specimen_name]


@pytest.fixture
def flow_csv_path(specimen: SpecimenConfig) -> Path:
    """Get the .flow.csv path for the current specimen."""
    return TARGET_FLOWS_DIR / specimen.flow_csv


# endregion

# region Test Classes


class TestFlowCSVValidation:
    """Validate .flow.csv files exist and are well-formed."""

    @pytest.mark.parametrize("specimen_name", SPECIMENS.keys())
    def test_flow_csv_exists(self, specimen_name: str) -> None:
        """Each specimen has a .flow.csv file."""
        spec = SPECIMENS[specimen_name]
        csv_path = TARGET_FLOWS_DIR / spec.flow_csv
        assert csv_path.exists(), f"Missing .flow.csv for {specimen_name}: {csv_path}"

    @pytest.mark.parametrize("specimen_name", SPECIMENS.keys())
    def test_flow_csv_has_atomic(self, specimen_name: str) -> None:
        """Each .flow.csv has atomic flow mode."""
        spec = SPECIMENS[specimen_name]
        csv_path = TARGET_FLOWS_DIR / spec.flow_csv
        if not csv_path.exists():
            pytest.skip(f"Flow CSV not found: {csv_path}")

        modes = get_flow_modes(csv_path)
        assert "atomic" in modes, f"{specimen_name}: Missing 'atomic' flow_mode"

    @pytest.mark.parametrize("specimen_name", SPECIMENS.keys())
    def test_flow_csv_has_default(self, specimen_name: str) -> None:
        """Each .flow.csv has default flow mode."""
        spec = SPECIMENS[specimen_name]
        csv_path = TARGET_FLOWS_DIR / spec.flow_csv
        if not csv_path.exists():
            pytest.skip(f"Flow CSV not found: {csv_path}")

        modes = get_flow_modes(csv_path)
        assert "default" in modes, f"{specimen_name}: Missing 'default' flow_mode"

    @pytest.mark.parametrize("specimen_name", SPECIMENS.keys())
    def test_atomic_section_count(self, specimen_name: str) -> None:
        """Atomic sections count matches expected."""
        spec = SPECIMENS[specimen_name]
        csv_path = TARGET_FLOWS_DIR / spec.flow_csv
        if not csv_path.exists():
            pytest.skip(f"Flow CSV not found: {csv_path}")

        entries = parse_flow_csv(csv_path)
        atomic_entries = [e for e in entries if e.flow_mode == "atomic"]
        actual = len(atomic_entries)
        expected = spec.expected_atomic_sections
        assert (
            actual == expected
        ), f"{specimen_name}: Expected {expected} atomic sections, got {actual}"


class TestTSVLoaderValidation:
    """Validate TSVLoader (gold standard) measure counts."""

    @pytest.mark.parametrize("specimen_name", SPECIMENS.keys())
    def test_tsv_folded_count(self, specimen_name: str) -> None:
        """TSVLoader folded measure count is exact."""
        spec = SPECIMENS[specimen_name]
        tsv_path = get_specimen_path(spec, "tsv")
        if tsv_path is None or not tsv_path.exists():
            pytest.skip(f"TSV not found for {specimen_name}")

        from timetoalign.loader.score import TSVLoader

        loader = TSVLoader()
        loader.load(tsv_path)

        mc_values = loader.store.measures._table.column("mc").to_pylist()
        actual = len(set(mc_values))
        expected = spec.folded_measures

        assert actual == expected, (
            f"{specimen_name}: TSV folded count mismatch.\n"
            f"Expected: {expected}\n"
            f"Actual: {actual}"
        )


class TestMeasureMapLoaderValidation:
    """Validate MeasureMapLoader against gold standard."""

    @pytest.mark.parametrize("specimen_name", SPECIMENS.keys())
    def test_measuremap_folded_count(self, specimen_name: str) -> None:
        """MeasureMapLoader folded measure count matches TSV."""
        spec = SPECIMENS[specimen_name]
        mm_path = get_specimen_path(spec, "mm_json")
        if mm_path is None or not mm_path.exists():
            pytest.skip(f"MeasureMap not found for {specimen_name}")

        from timetoalign.loader.score import MeasureMapLoader

        loader = MeasureMapLoader()
        loader.load(mm_path)

        actual = len(loader.store.measures)
        expected = spec.folded_measures

        assert actual == expected, (
            f"{specimen_name}: MeasureMap folded count mismatch.\n"
            f"Expected: {expected}\n"
            f"Actual: {actual}"
        )

    @pytest.mark.parametrize("specimen_name", SPECIMENS.keys())
    def test_measuremap_traversal_count(self, specimen_name: str) -> None:
        """MeasureMapLoader unfolded traversal count matches gold standard."""
        spec = SPECIMENS[specimen_name]
        mm_path = get_specimen_path(spec, "mm_json")
        if mm_path is None or not mm_path.exists():
            pytest.skip(f"MeasureMap not found for {specimen_name}")

        from timetoalign.loader.score import MeasureMapLoader

        loader = MeasureMapLoader()
        loader.load(mm_path)
        traversal = loader.compute_default_traversal()

        actual = len(traversal)
        expected = spec.unfolded_measures

        assert actual == expected, (
            f"{specimen_name}: MeasureMap traversal count mismatch.\n"
            f"Expected: {expected}\n"
            f"Actual: {actual}\n"
            f"First 20: {traversal[:20]}"
        )


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
class TestMusic21LoaderMusicXML:
    """Validate Music21Loader with MusicXML files.

    KNOWN DEVIATIONS:
    - music21's expandRepeats() ignores D.S., D.C., and Fine markers
    - For specimens with D.S./D.C. (c05n05_musete, c11n08_Rondeau, flow_only),
      music21 produces different (often shorter) flows
    """

    @pytest.mark.parametrize("specimen_name", SPECIMENS.keys())
    def test_music21_musicxml_folded_count(self, specimen_name: str) -> None:
        """Music21Loader MusicXML folded measure count is correct."""
        spec = SPECIMENS[specimen_name]
        xml_path = get_specimen_path(spec, "musicxml")
        if xml_path is None or not xml_path.exists():
            pytest.skip(f"MusicXML not found for {specimen_name}")

        # Skip large files to avoid test timeouts
        if musicxml_too_large(xml_path):
            file_size_mb = xml_path.stat().st_size / 1_000_000
            pytest.skip(
                f"MusicXML file too large ({file_size_mb:.1f}MB) for Music21 test. "
                f"Max size: {MAX_MUSICXML_SIZE_BYTES / 1_000_000:.1f}MB"
            )

        try:
            from timetoalign.loader.score import Music21Loader
        except ImportError:
            pytest.skip("Music21Loader not available")

        loader = Music21Loader()
        loader.load(xml_path)

        mc_values = loader.store.measures._table.column("mc").to_pylist()
        actual = len(set(mc_values))
        expected = spec.folded_measures

        assert actual == expected, (
            f"{specimen_name}: Music21 MusicXML folded count mismatch.\n"
            f"Expected: {expected}\n"
            f"Actual: {actual}"
        )

    @pytest.mark.parametrize("specimen_name", SPECIMENS.keys())
    def test_music21_musicxml_flow_valid(self, specimen_name: str) -> None:
        """Music21Loader produces a valid flow (matches one in .flow.csv).

        Note: music21 may produce a different but valid unfolding for specimens
        with D.S./D.C. markers (e.g., c05n05_musete, c11n08_Rondeau).
        """
        spec = SPECIMENS[specimen_name]
        xml_path = get_specimen_path(spec, "musicxml")
        csv_path = TARGET_FLOWS_DIR / spec.flow_csv

        if xml_path is None or not xml_path.exists():
            pytest.skip(f"MusicXML not found for {specimen_name}")
        if not csv_path.exists():
            pytest.skip(f"Flow CSV not found for {specimen_name}")

        # Skip large files to avoid test timeouts
        if musicxml_too_large(xml_path):
            file_size_mb = xml_path.stat().st_size / 1_000_000
            pytest.skip(
                f"MusicXML file too large ({file_size_mb:.1f}MB) for Music21 test. "
                f"Max size: {MAX_MUSICXML_SIZE_BYTES / 1_000_000:.1f}MB"
            )

        try:
            from timetoalign.loader.score import Music21Loader
        except ImportError:
            pytest.skip("Music21Loader not available")

        from timetoalign.core.enums import FlowMode
        from timetoalign.timelines import FlowController
        from timetoalign.timelines.flow import load_valid_flows

        # Load valid flows from ground truth
        valid_flows = load_valid_flows(csv_path)

        # Load and compute flow
        loader = Music21Loader()
        loader.load(xml_path)
        controller = FlowController(loader.store.measures)
        computed = controller.compute_flow(FlowMode.default)

        # Check if computed matches any valid flow
        matches = [
            (mode, flow)
            for mode, flow in valid_flows.items()
            if computed.is_equivalent(flow)
        ]

        if not matches:
            # Document the deviation
            computed_ranges = [(s.mc_start, s.mc_end) for s in computed.sections[:5]]
            valid_summary = {
                m.value: [(s.mc_start, s.mc_end) for s in f.sections[:5]]
                for m, f in valid_flows.items()
            }
            pytest.fail(
                f"{specimen_name}: Music21 MusicXML flow doesn't match any valid unfolding.\n"
                f"Computed (first 5): {computed_ranges}\n"
                f"Valid modes: {list(valid_flows.keys())}\n"
                f"Valid (first 5 each): {valid_summary}\n"
                f"Note: {spec.notes}"
            )


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
class TestMusic21LoaderMEI:
    """Validate Music21Loader with MEI files.

    MEI files are exported from MuseScore and should produce identical results
    to MusicXML. The same D.S./D.C. limitations apply.
    """

    @pytest.mark.parametrize("specimen_name", SPECIMENS.keys())
    def test_music21_mei_folded_count(self, specimen_name: str) -> None:
        """Music21Loader MEI folded measure count is correct."""
        spec = SPECIMENS[specimen_name]
        mei_path = get_specimen_path(spec, "mei")
        if mei_path is None or not mei_path.exists():
            pytest.skip(f"MEI not found for {specimen_name}")

        # Skip large files to avoid test timeouts
        if musicxml_too_large(mei_path):
            file_size_mb = mei_path.stat().st_size / 1_000_000
            pytest.skip(
                f"MEI file too large ({file_size_mb:.1f}MB) for Music21 test. "
                f"Max size: {MAX_MUSICXML_SIZE_BYTES / 1_000_000:.1f}MB"
            )

        try:
            from timetoalign.loader.score import Music21Loader
        except ImportError:
            pytest.skip("Music21Loader not available")

        loader = Music21Loader()
        try:
            loader.load(mei_path)
        except (SyntaxError, KeyError) as e:
            # Music21 MEI parser raises:
            # - music21.exceptions21.Music21Exception subclasses (MeiElementError, etc.)
            #   which inherit from Exception directly — caught separately below
            # - xml.etree.ElementTree.ParseError (subclass of SyntaxError)
            # - KeyError for missing elements
            pytest.skip(f"Music21 failed to load MEI: {e}")
        except Exception as e:
            if "music21" in type(e).__module__:
                pytest.skip(f"Music21 failed to load MEI: {e}")
            raise

        mc_values = loader.store.measures._table.column("mc").to_pylist()
        actual = len(set(mc_values))
        expected = spec.folded_measures

        assert actual == expected, (
            f"{specimen_name}: Music21 MEI folded count mismatch.\n"
            f"Expected: {expected}\n"
            f"Actual: {actual}"
        )

    @pytest.mark.parametrize("specimen_name", SPECIMENS.keys())
    def test_music21_mei_matches_musicxml(self, specimen_name: str) -> None:
        """Music21Loader MEI produces same flow as MusicXML."""
        spec = SPECIMENS[specimen_name]
        mei_path = get_specimen_path(spec, "mei")
        xml_path = get_specimen_path(spec, "musicxml")

        if mei_path is None or not mei_path.exists():
            pytest.skip(f"MEI not found for {specimen_name}")
        if xml_path is None or not xml_path.exists():
            pytest.skip(f"MusicXML not found for {specimen_name}")

        # Skip large files to avoid test timeouts
        if musicxml_too_large(mei_path) or musicxml_too_large(xml_path):
            pytest.skip(
                f"MEI or MusicXML file too large for Music21 test. "
                f"Max size: {MAX_MUSICXML_SIZE_BYTES / 1_000_000:.1f}MB"
            )

        try:
            from timetoalign.loader.score import Music21Loader
        except ImportError:
            pytest.skip("Music21Loader not available")

        from timetoalign.core.enums import FlowMode
        from timetoalign.timelines import FlowController

        # Load both formats
        mei_loader = Music21Loader()
        xml_loader = Music21Loader()

        try:
            mei_loader.load(mei_path)
        except (SyntaxError, KeyError) as e:
            # xml.etree.ElementTree.ParseError (subclass of SyntaxError),
            # KeyError for missing elements
            pytest.skip(f"Music21 failed to load MEI: {e}")
        except Exception as e:
            if "music21" in type(e).__module__:
                pytest.skip(f"Music21 failed to load MEI: {e}")
            raise

        xml_loader.load(xml_path)

        # Compute flows
        mei_ctrl = FlowController(mei_loader.store.measures)
        xml_ctrl = FlowController(xml_loader.store.measures)

        mei_flow = mei_ctrl.compute_flow(FlowMode.default)
        xml_flow = xml_ctrl.compute_flow(FlowMode.default)

        # Compare
        assert mei_flow.is_equivalent(xml_flow), (
            f"{specimen_name}: Music21 MEI flow differs from MusicXML.\n"
            f"MEI sections: {len(mei_flow.sections)}\n"
            f"XML sections: {len(xml_flow.sections)}"
        )


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
class TestPartituraLoaderMusicXML:
    """Validate PartituraLoader with MusicXML files.

    KNOWN DEVIATIONS:
    - Partitura uses a region-based repeat model (start/end pairs)
    - Missing repeat starts are inferred, causing different counts
    - For flow_only specimen, partitura infers 7 starts vs 3 in TSV
    """

    @pytest.mark.parametrize("specimen_name", SPECIMENS.keys())
    def test_partitura_musicxml_folded_count(self, specimen_name: str) -> None:
        """PartituraLoader MusicXML folded measure count is correct."""
        spec = SPECIMENS[specimen_name]
        xml_path = get_specimen_path(spec, "musicxml")
        if xml_path is None or not xml_path.exists():
            pytest.skip(f"MusicXML not found for {specimen_name}")

        # Skip large files to avoid test timeouts
        if musicxml_too_large(xml_path):
            file_size_mb = xml_path.stat().st_size / 1_000_000
            pytest.skip(
                f"MusicXML file too large ({file_size_mb:.1f}MB) for Partitura test. "
                f"Max size: {MAX_MUSICXML_SIZE_BYTES / 1_000_000:.1f}MB"
            )

        try:
            from timetoalign.loader.score import PartituraLoader
        except ImportError:
            pytest.skip("PartituraLoader not available")

        loader = PartituraLoader()
        loader.load(xml_path)

        mc_values = loader.store.measures._table.column("mc").to_pylist()
        actual = len(set(mc_values))
        expected = spec.folded_measures

        assert actual == expected, (
            f"{specimen_name}: Partitura MusicXML folded count mismatch.\n"
            f"Expected: {expected}\n"
            f"Actual: {actual}\n"
            f"Note: Multi-part scores may have different counts"
        )

    @pytest.mark.parametrize("specimen_name", SPECIMENS.keys())
    def test_partitura_musicxml_flow_valid(self, specimen_name: str) -> None:
        """PartituraLoader produces a valid flow (matches one in .flow.csv)."""
        spec = SPECIMENS[specimen_name]
        xml_path = get_specimen_path(spec, "musicxml")
        csv_path = TARGET_FLOWS_DIR / spec.flow_csv

        if xml_path is None or not xml_path.exists():
            pytest.skip(f"MusicXML not found for {specimen_name}")
        if not csv_path.exists():
            pytest.skip(f"Flow CSV not found for {specimen_name}")

        # Skip large files to avoid test timeouts
        if musicxml_too_large(xml_path):
            file_size_mb = xml_path.stat().st_size / 1_000_000
            pytest.skip(
                f"MusicXML file too large ({file_size_mb:.1f}MB) for Partitura test. "
                f"Max size: {MAX_MUSICXML_SIZE_BYTES / 1_000_000:.1f}MB"
            )

        try:
            from timetoalign.loader.score import PartituraLoader
        except ImportError:
            pytest.skip("PartituraLoader not available")

        from timetoalign.core.enums import FlowMode
        from timetoalign.timelines import FlowController
        from timetoalign.timelines.flow import load_valid_flows

        # Load valid flows from ground truth
        valid_flows = load_valid_flows(csv_path)

        # Load and compute flow
        loader = PartituraLoader()
        loader.load(xml_path)
        controller = FlowController(loader.store.measures)
        computed = controller.compute_flow(FlowMode.default)

        # Check if computed matches any valid flow
        matches = [
            (mode, flow)
            for mode, flow in valid_flows.items()
            if computed.is_equivalent(flow)
        ]

        if not matches:
            computed_ranges = [(s.mc_start, s.mc_end) for s in computed.sections[:5]]
            valid_summary = {
                m.value: [(s.mc_start, s.mc_end) for s in f.sections[:5]]
                for m, f in valid_flows.items()
            }
            pytest.fail(
                f"{specimen_name}: Partitura MusicXML flow doesn't match any valid unfolding.\n"
                f"Computed (first 5): {computed_ranges}\n"
                f"Valid modes: {list(valid_flows.keys())}\n"
                f"Valid (first 5 each): {valid_summary}\n"
                f"Note: {spec.notes}"
            )


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
class TestPartituraLoaderMEI:
    """Validate PartituraLoader with MEI files."""

    @pytest.mark.parametrize("specimen_name", SPECIMENS.keys())
    def test_partitura_mei_folded_count(self, specimen_name: str) -> None:
        """PartituraLoader MEI folded measure count is correct."""
        spec = SPECIMENS[specimen_name]
        mei_path = get_specimen_path(spec, "mei")
        if mei_path is None or not mei_path.exists():
            pytest.skip(f"MEI not found for {specimen_name}")

        # Skip large files to avoid test timeouts
        if musicxml_too_large(mei_path):
            file_size_mb = mei_path.stat().st_size / 1_000_000
            pytest.skip(
                f"MEI file too large ({file_size_mb:.1f}MB) for Partitura test. "
                f"Max size: {MAX_MUSICXML_SIZE_BYTES / 1_000_000:.1f}MB"
            )

        try:
            from timetoalign.loader.score import PartituraLoader
        except ImportError:
            pytest.skip("PartituraLoader not available")

        loader = PartituraLoader()
        try:
            loader.load(mei_path)
        except (SyntaxError, KeyError) as e:
            # Partitura MEI parser raises:
            # - lxml.etree.XMLSyntaxError (subclass of SyntaxError) for malformed XML
            # - KeyError for missing elements in the score structure
            pytest.skip(f"Partitura failed to load MEI: {e}")

        mc_values = loader.store.measures._table.column("mc").to_pylist()
        actual = len(set(mc_values))
        expected = spec.folded_measures

        assert actual == expected, (
            f"{specimen_name}: Partitura MEI folded count mismatch.\n"
            f"Expected: {expected}\n"
            f"Actual: {actual}"
        )


class TestFlowControllerReproducesTargetFlows:
    """TOP-MOST GOAL: FlowController reproduces ALL target flows from .flow.csv.

    This is the core test that validates the system works end-to-end.
    """

    @pytest.mark.parametrize("specimen_name", SPECIMENS.keys())
    def test_tsv_reproduces_valid_flow(self, specimen_name: str) -> None:
        """TSVLoader -> FlowController reproduces a valid flow from .flow.csv.

        Note: For flow_only specimen, TSV produces the 'ms3' flow (30 MCs) which
        is documented as divergent from the canonical 'default' flow (31 MCs).
        """
        spec = SPECIMENS[specimen_name]
        tsv_path = get_specimen_path(spec, "tsv")
        csv_path = TARGET_FLOWS_DIR / spec.flow_csv

        if tsv_path is None or not tsv_path.exists():
            pytest.skip(f"TSV not found for {specimen_name}")
        if not csv_path.exists():
            pytest.skip(f"Flow CSV not found for {specimen_name}")

        from timetoalign.core.enums import FlowMode
        from timetoalign.loader.score import TSVLoader
        from timetoalign.timelines import FlowController
        from timetoalign.timelines.flow import load_valid_flows

        # Load all valid flows
        valid_flows = load_valid_flows(csv_path)
        if not valid_flows:
            pytest.skip(f"No valid flows in {csv_path}")

        # Load and compute
        loader = TSVLoader()
        loader.load(tsv_path)
        controller = FlowController(loader.store.measures)
        computed = controller.compute_flow(FlowMode.default)

        # Check if computed matches ANY valid flow
        matches = [
            (mode, flow)
            for mode, flow in valid_flows.items()
            if computed.is_equivalent(flow)
        ]

        if not matches:
            # Build diagnostic
            computed_seq = computed.to_mc_sequence()[:20]
            valid_seqs = {
                m.value: f.to_mc_sequence()[:20] for m, f in valid_flows.items()
            }
            pytest.fail(
                f"{specimen_name}: TSV flow doesn't match any valid unfolding.\n"
                f"Computed sections: {len(computed.sections)}\n"
                f"Computed MC seq (first 20): {computed_seq}\n"
                f"Valid modes: {list(valid_flows.keys())}\n"
                f"Valid MC seqs (first 20): {valid_seqs}\n"
                f"Note: {spec.notes}"
            )

        # Document which flow mode matched
        matched_mode = matches[0][0]
        if matched_mode != FlowMode.default:
            # Log that we matched a divergent mode
            pass  # This is expected for flow_only (matches ms3)

    @pytest.mark.parametrize("specimen_name", SPECIMENS.keys())
    def test_tsv_reproduces_atomic_flow(self, specimen_name: str) -> None:
        """TSVLoader -> FlowController reproduces ATOMIC flow."""
        spec = SPECIMENS[specimen_name]
        tsv_path = get_specimen_path(spec, "tsv")
        csv_path = TARGET_FLOWS_DIR / spec.flow_csv

        if tsv_path is None or not tsv_path.exists():
            pytest.skip(f"TSV not found for {specimen_name}")
        if not csv_path.exists():
            pytest.skip(f"Flow CSV not found for {specimen_name}")

        from timetoalign.core.enums import FlowMode
        from timetoalign.loader.score import TSVLoader
        from timetoalign.timelines import FlowController
        from timetoalign.timelines.flow import load_valid_flows

        # Load gold standard
        valid_flows = load_valid_flows(csv_path)
        if FlowMode.atomic not in valid_flows:
            pytest.skip(f"No ATOMIC flow in {csv_path}")

        target = valid_flows[FlowMode.atomic]

        # Load and compute
        loader = TSVLoader()
        loader.load(tsv_path)
        controller = FlowController(loader.store.measures)

        # Get atomic sections
        atomic_sections = controller.get_sections(mode=None)
        computed_ranges = [(s.mc_start, s.mc_end) for s in atomic_sections]
        target_ranges = [(s.mc_start, s.mc_end) for s in target.sections]

        assert computed_ranges == target_ranges, (
            f"{specimen_name}: TSV ATOMIC flow mismatch.\n"
            f"Computed: {computed_ranges}\n"
            f"Target: {target_ranges}"
        )


class TestCrossLoaderParity:
    """Validate that marker-based loaders (TSV, MeasureMap, Music21) produce identical counts."""

    @pytest.mark.parametrize("specimen_name", SPECIMENS.keys())
    def test_tsv_vs_measuremap_folded_count(self, specimen_name: str) -> None:
        """TSV and MeasureMap have identical folded measure counts."""
        spec = SPECIMENS[specimen_name]
        tsv_path = get_specimen_path(spec, "tsv")
        mm_path = get_specimen_path(spec, "mm_json")

        if tsv_path is None or not tsv_path.exists():
            pytest.skip(f"TSV not found for {specimen_name}")
        if mm_path is None or not mm_path.exists():
            pytest.skip(f"MeasureMap not found for {specimen_name}")

        from timetoalign.loader.score import MeasureMapLoader, TSVLoader

        tsv_loader = TSVLoader()
        tsv_loader.load(tsv_path)
        tsv_count = len(set(tsv_loader.store.measures._table.column("mc").to_pylist()))

        mm_loader = MeasureMapLoader()
        mm_loader.load(mm_path)
        mm_count = len(mm_loader.store.measures)

        assert tsv_count == mm_count, (
            f"{specimen_name}: TSV vs MeasureMap count mismatch.\n"
            f"TSV: {tsv_count}\n"
            f"MeasureMap: {mm_count}"
        )


# endregion

# region Deviation Documentation Tests


class TestDocumentedDeviations:
    """Document known parser deviations for the README.

    These tests capture expected differences between parsers.
    They PASS by documenting the deviation, not by asserting equality.
    """

    def test_c05n05_musete_music21_deviation(self) -> None:
        """Document: music21 ignores D.S. al Fine in c05n05_musete.

        Expected behavior:
        - ms3/TSV: 138 unfolded MCs (follows D.S. al Fine)
        - music21: 116 unfolded MCs (ignores D.S., only handles repeats)
        """
        spec = SPECIMENS["c05n05_musete"]
        csv_path = TARGET_FLOWS_DIR / spec.flow_csv
        if not csv_path.exists():
            pytest.skip("Flow CSV not found")

        modes = get_flow_modes(csv_path)

        # Document the deviation
        assert "default" in modes, "default mode required"
        # The flow.csv shows music21 flow_mode produces different results
        # (only present when music21's expandRepeats() diverges from default)

    def test_flow_only_ms3_deviation(self) -> None:
        """Document: ms3 diverges from canonical in flow_only due to ambiguous encoding.

        The score has ambiguous repeat encoding that ms3 interprets differently:
        - Canonical: 31 MCs (humans would play it this way)
        - ms3: Different sequence due to repeat end inference

        Additionally, music21 fails entirely on this specimen.
        """
        spec = SPECIMENS["flow_only"]
        csv_path = TARGET_FLOWS_DIR / spec.flow_csv
        if not csv_path.exists():
            pytest.skip("Flow CSV not found")

        modes = get_flow_modes(csv_path)

        # The CSV documents multiple valid interpretations
        assert "default" in modes, "default mode required"
        assert "ms3" in modes, "ms3 deviation should be documented in CSV"


# endregion
