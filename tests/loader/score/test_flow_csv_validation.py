"""Flow CSV Ground Truth Validation Tests.

This module validates score loaders against .flow.csv ground truth files.
Each flow.csv entry specifies:
- flow_mode: which loader/parsing mode to use
- source_file: the file to parse
- software_version: expected software version
- mc_start, mc_end: expected MC range (INCLUSIVE)
- atomic_segments: partitura segment IDs covered

Per ZERO TOLERANCE VALIDATION POLICY (from AGENTS.md):
- EXACT counts required (no tolerances)
- mc_end is INCLUSIVE (standard musical convention)
- Every mismatch must be investigated
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import NamedTuple

import pytest

# Test data directories
TESTS_DATA_DIR = Path(__file__).parents[2] / "data"
TARGET_FLOWS_DIR = TESTS_DATA_DIR / "target_flows"
SCORE_DATA_DIR = TESTS_DATA_DIR / "score"


class FlowEntry(NamedTuple):
    """A single entry from a .flow.csv file."""

    flow_mode: str
    source_file: str
    software_version: str
    mc_start: int | str  # int or "ERROR"
    mc_end: int | str  # int or error code
    atomic_segments: str


def parse_flow_csv(csv_path: Path) -> list[FlowEntry]:
    """Parse a .flow.csv file into FlowEntry objects.

    Args:
        csv_path: Path to the .flow.csv file

    Returns:
        List of FlowEntry objects (skips comment lines and ERROR entries)
    """
    entries = []
    with open(csv_path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)  # Skip header
        assert header == [
            "flow_mode",
            "source_file",
            "software_version",
            "mc_start",
            "mc_end",
            "atomic_segments",
        ], f"Unexpected header: {header}"

        for row in reader:
            # Skip empty rows and comment lines
            if not row or row[0].startswith("#"):
                continue

            flow_mode, source_file, software_version, mc_start, mc_end, segments = row

            # Skip ERROR entries
            if mc_start == "ERROR":
                continue

            entries.append(
                FlowEntry(
                    flow_mode=flow_mode,
                    source_file=source_file,
                    software_version=software_version,
                    mc_start=int(mc_start),
                    mc_end=int(mc_end),
                    atomic_segments=segments,
                )
            )

    return entries


def find_source_file(source_filename: str, specimen_name: str) -> Path | None:
    """Find the source file in the score data directory.

    Args:
        source_filename: The filename from the flow.csv
        specimen_name: The specimen name (derived from flow.csv filename)

    Returns:
        Path to the source file, or None if not found
    """
    # Map specimen names to directories
    specimen_dirs = {
        "c05n05_musete": SCORE_DATA_DIR / "couperin_concerts",
        "out_of_the_flow_experience-polyrhythm_only": SCORE_DATA_DIR / "flow_control",
        "Piano_Concerto_No._2_Opus_18_1st_Movement__Rachmaninoff": SCORE_DATA_DIR
        / "rachmaninoff",
    }

    # Also check subdirectories for unfolded TSV files
    specimen_subdirs = {
        "c05n05_musete": SCORE_DATA_DIR / "couperin_concerts",
        "out_of_the_flow_experience-polyrhythm_only": SCORE_DATA_DIR
        / "flow_control"
        / "polyrythm_only",
        "Piano_Concerto_No._2_Opus_18_1st_Movement__Rachmaninoff": SCORE_DATA_DIR
        / "rachmaninoff",
    }

    # Try main directory first
    if specimen_name in specimen_dirs:
        candidate = specimen_dirs[specimen_name] / source_filename
        if candidate.exists():
            return candidate

    # Try subdirectory
    if specimen_name in specimen_subdirs:
        candidate = specimen_subdirs[specimen_name] / source_filename
        if candidate.exists():
            return candidate

    # Try recursive search as fallback
    for path in SCORE_DATA_DIR.rglob(source_filename):
        return path

    return None


def get_loader_for_flow_mode(flow_mode: str):
    """Get the appropriate loader class for a flow mode.

    Args:
        flow_mode: The flow mode from the flow.csv

    Returns:
        Loader class or None if not available
    """
    if flow_mode == "default":
        try:
            from timetoalign.loader.score import TSVLoader

            return TSVLoader
        except ImportError:
            return None

    if flow_mode == "mm_json":
        from timetoalign.loader.score import MeasureMapLoader

        return MeasureMapLoader

    if flow_mode in ("partitura_minimal", "partitura_musicxml", "partitura_maximal"):
        try:
            from timetoalign.loader.score import PartituraLoader

            return PartituraLoader
        except ImportError:
            return None

    if flow_mode in ("music21_musicxml", "music21_mei", "music21"):
        try:
            from timetoalign.loader.score import Music21Loader

            return Music21Loader
        except ImportError:
            return None

    return None


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def flow_csv_files() -> list[Path]:
    """Get all .flow.csv files in the target_flows directory."""
    return sorted(TARGET_FLOWS_DIR.glob("*.flow.csv"))


# ============================================================================
# Test: Validate flow.csv files exist and are parseable
# ============================================================================


class TestFlowCSVStructure:
    """Validate .flow.csv file structure and format."""

    def test_flow_csv_files_exist(self, flow_csv_files):
        """At least one .flow.csv file exists."""
        assert len(flow_csv_files) > 0, f"No .flow.csv files in {TARGET_FLOWS_DIR}"

    @pytest.mark.parametrize(
        "csv_name",
        [
            "c05n05_musete.flow.csv",
            "out_of_the_flow_experience-polyrhythm_only.flow.csv",
            "Piano_Concerto_No._2_Opus_18_1st_Movement__Rachmaninoff.flow.csv",
        ],
    )
    def test_flow_csv_parseable(self, csv_name):
        """Each flow.csv can be parsed without errors."""
        csv_path = TARGET_FLOWS_DIR / csv_name
        if not csv_path.exists():
            pytest.skip(f"Flow CSV not found: {csv_path}")

        entries = parse_flow_csv(csv_path)
        assert len(entries) > 0, f"No valid entries in {csv_name}"

    @pytest.mark.parametrize(
        "csv_name",
        [
            "c05n05_musete.flow.csv",
            "out_of_the_flow_experience-polyrhythm_only.flow.csv",
            "Piano_Concerto_No._2_Opus_18_1st_Movement__Rachmaninoff.flow.csv",
        ],
    )
    def test_mc_end_is_inclusive(self, csv_name):
        """Verify mc_end values follow INCLUSIVE convention (no overlapping ranges)."""
        csv_path = TARGET_FLOWS_DIR / csv_name
        if not csv_path.exists():
            pytest.skip(f"Flow CSV not found: {csv_path}")

        entries = parse_flow_csv(csv_path)

        # Group entries by flow_mode
        by_mode: dict[str, list[FlowEntry]] = {}
        for entry in entries:
            if entry.flow_mode not in by_mode:
                by_mode[entry.flow_mode] = []
            by_mode[entry.flow_mode].append(entry)

        # For partitura_minimal, check that segments don't overlap
        if "partitura_minimal" in by_mode:
            minimal_entries = sorted(
                by_mode["partitura_minimal"], key=lambda e: e.mc_start
            )
            for i in range(len(minimal_entries) - 1):
                current = minimal_entries[i]
                next_entry = minimal_entries[i + 1]
                # With INCLUSIVE mc_end, next segment should start at mc_end + 1
                assert current.mc_end < next_entry.mc_start, (
                    f"Overlapping segments in {csv_name} partitura_minimal: "
                    f"segment ending at MC {current.mc_end} overlaps with "
                    f"segment starting at MC {next_entry.mc_start}"
                )


# ============================================================================
# Test: Validate partitura_minimal segments
# ============================================================================


class TestPartituraMinimalValidation:
    """Validate partitura_minimal entries against actual partitura output."""

    @pytest.mark.parametrize(
        "csv_name,expected_segments",
        [
            (
                "c05n05_musete.flow.csv",
                {"A": (1, 5), "B": (6, 16), "C": (17, 31), "D": (32, 58)},
            ),
            ("out_of_the_flow_experience-polyrhythm_only.flow.csv", {"A": (1, 14)}),
            (
                "Piano_Concerto_No._2_Opus_18_1st_Movement__Rachmaninoff.flow.csv",
                {"A": (1, 374)},
            ),
        ],
    )
    def test_partitura_minimal_segments(self, csv_name, expected_segments):
        """Verify partitura_minimal entries match expected segment boundaries."""
        csv_path = TARGET_FLOWS_DIR / csv_name
        if not csv_path.exists():
            pytest.skip(f"Flow CSV not found: {csv_path}")

        entries = parse_flow_csv(csv_path)
        minimal_entries = [e for e in entries if e.flow_mode == "partitura_minimal"]

        if not minimal_entries:
            pytest.skip(f"No partitura_minimal entries in {csv_name}")

        # Build actual segments from CSV
        actual_segments = {}
        for entry in minimal_entries:
            seg_id = entry.atomic_segments
            actual_segments[seg_id] = (entry.mc_start, entry.mc_end)

        # Compare
        assert actual_segments == expected_segments, (
            f"Segment mismatch in {csv_name}:\n"
            f"  Expected: {expected_segments}\n"
            f"  Actual: {actual_segments}"
        )


# ============================================================================
# Test: Validate loader measure counts
# ============================================================================


class TestLoaderMeasureCounts:
    """Validate that loaders produce expected measure counts."""

    @pytest.mark.parametrize(
        "csv_name,flow_mode,expected_total_measures",
        [
            ("c05n05_musete.flow.csv", "partitura_minimal", 58),
            ("c05n05_musete.flow.csv", "music21_musicxml", 58),
            (
                "out_of_the_flow_experience-polyrhythm_only.flow.csv",
                "partitura_minimal",
                14,
            ),
            (
                "out_of_the_flow_experience-polyrhythm_only.flow.csv",
                "music21_musicxml",
                14,
            ),
            (
                "Piano_Concerto_No._2_Opus_18_1st_Movement__Rachmaninoff.flow.csv",
                "partitura_minimal",
                374,
            ),
        ],
    )
    def test_loader_measure_count(self, csv_name, flow_mode, expected_total_measures):
        """Verify loader produces expected total measure count."""
        csv_path = TARGET_FLOWS_DIR / csv_name
        if not csv_path.exists():
            pytest.skip(f"Flow CSV not found: {csv_path}")

        entries = parse_flow_csv(csv_path)
        mode_entries = [e for e in entries if e.flow_mode == flow_mode]

        if not mode_entries:
            pytest.skip(f"No {flow_mode} entries in {csv_name}")

        # Get loader
        loader_class = get_loader_for_flow_mode(flow_mode)
        if loader_class is None:
            pytest.skip(f"Loader not available for {flow_mode}")

        # Find source file
        specimen_name = csv_name.replace(".flow.csv", "")
        source_path = find_source_file(mode_entries[0].source_file, specimen_name)
        if source_path is None:
            pytest.skip(f"Source file not found: {mode_entries[0].source_file}")

        # Load and check measure count
        import warnings

        warnings.filterwarnings("ignore")

        loader = loader_class()
        loader.load(source_path)

        actual_count = len(loader.store.measures)
        assert actual_count == expected_total_measures, (
            f"Measure count mismatch for {csv_name} with {flow_mode}:\n"
            f"  Expected: {expected_total_measures}\n"
            f"  Actual: {actual_count}\n"
            f"  Source: {source_path}"
        )


# ============================================================================
# Test: Validate segment MC ranges against actual partitura output
# ============================================================================


@pytest.mark.parametrize(
    "csv_name",
    [
        "c05n05_musete.flow.csv",
        "out_of_the_flow_experience-polyrhythm_only.flow.csv",
        "Piano_Concerto_No._2_Opus_18_1st_Movement__Rachmaninoff.flow.csv",
    ],
)
class TestPartituraSegmentValidation:
    """Validate partitura_minimal segments against live partitura output."""

    def test_partitura_segment_boundaries(self, csv_name):
        """Verify CSV segment boundaries match actual partitura.add_segments() output."""
        try:
            import partitura as pt
        except ImportError:
            pytest.skip("partitura not installed")

        csv_path = TARGET_FLOWS_DIR / csv_name
        if not csv_path.exists():
            pytest.skip(f"Flow CSV not found: {csv_path}")

        entries = parse_flow_csv(csv_path)
        minimal_entries = [e for e in entries if e.flow_mode == "partitura_minimal"]

        if not minimal_entries:
            pytest.skip(f"No partitura_minimal entries in {csv_name}")

        # Find source file
        specimen_name = csv_name.replace(".flow.csv", "")
        source_path = find_source_file(minimal_entries[0].source_file, specimen_name)
        if source_path is None:
            pytest.skip(f"Source file not found: {minimal_entries[0].source_file}")

        # Load with partitura
        import warnings

        warnings.filterwarnings("ignore")

        score = pt.load_musicxml(source_path)
        part = score[0]

        # Get measures
        measures = list(part.iter_all(pt.score.Measure))

        # Get segments
        pt.score.add_segments(part)
        segments = pt.score.get_segments(part)

        # Build expected segments from CSV
        csv_segments = {}
        for entry in minimal_entries:
            csv_segments[entry.atomic_segments] = (entry.mc_start, entry.mc_end)

        # Build actual segments from partitura
        actual_segments = {}
        for seg_id, seg in segments.items():
            start_t = seg.start.t if hasattr(seg.start, "t") else seg.start
            end_t = seg.end.t if hasattr(seg.end, "t") else seg.end

            # Map t values to MC numbers (INCLUSIVE end)
            start_mc = None
            end_mc = None
            for i, m in enumerate(measures, start=1):
                # Start MC: first measure where segment start falls within
                if start_mc is None and m.start.t <= start_t < m.end.t:
                    start_mc = i
                # End MC: last measure where segment end falls at or before measure end
                if m.start.t < end_t <= m.end.t:
                    end_mc = i

            actual_segments[seg_id] = (start_mc, end_mc)

        # Compare
        assert csv_segments == actual_segments, (
            f"Segment boundary mismatch in {csv_name}:\n"
            f"  CSV segments: {csv_segments}\n"
            f"  Partitura segments: {actual_segments}"
        )
