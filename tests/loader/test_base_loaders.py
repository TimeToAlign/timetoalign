"""Tests for base loader classes: ManifestLoader, AlignmentLoader, AlignmentStore."""

from __future__ import annotations

import tempfile
from pathlib import Path

from timetoalign.core import TimeUnit
from timetoalign.loader import (
    AlignmentLoader,
    AlignmentStore,
    EventData,
    ManifestData,
    ManifestLoader,
    MatchData,
    SingleStore,
)

# region ManifestData Tests


class TestManifestData:
    """Tests for ManifestData."""

    def test_create_basic(self):
        """Test basic ManifestData creation."""
        manifest = ManifestData(
            dimensions={"width": 1920, "height": 1080},
            metadata={"format": "mp4"},
            source_type="video",
        )

        assert manifest.dimensions["width"] == 1920
        assert manifest.dimensions["height"] == 1080
        assert manifest.source_type == "video"

    def test_repr(self):
        """Test string representation."""
        manifest = ManifestData(
            dimensions={"duration": 60.0},
            source_type="audio",
        )

        repr_str = repr(manifest)
        assert "audio" in repr_str
        assert "duration" in repr_str


# endregion


# region ManifestLoader Tests


class TestManifestLoader:
    """Tests for ManifestLoader ABC."""

    def test_concrete_implementation(self):
        """Test a concrete ManifestLoader implementation."""

        class TestManifestLoader(ManifestLoader):
            def _load_source(self, source: Path) -> ManifestData:
                return ManifestData(
                    dimensions={"lines": 100},
                    metadata={"encoding": "utf-8"},
                    source_type="text",
                )

        # Create a temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test")
            path = Path(f.name)

        loader = TestManifestLoader()
        loader.load(path)

        assert len(loader) == 1
        assert loader.manifest is not None
        assert loader.manifest.dimensions["lines"] == 100

    def test_multiple_sources(self):
        """Test loading multiple sources."""

        class CountingLoader(ManifestLoader):
            def __init__(self):
                super().__init__()
                self._count = 0

            def _load_source(self, source: Path) -> ManifestData:
                self._count += 1
                return ManifestData(
                    dimensions={"index": self._count},
                    source_type="test",
                )

        # Create temp files
        paths = []
        for i in range(3):
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False
            ) as f:
                f.write(f"test {i}")
                paths.append(Path(f.name))

        loader = CountingLoader()
        loader.load(*paths)

        assert len(loader) == 3
        assert len(loader.manifests) == 3
        assert loader.manifests[0].dimensions["index"] == 1
        assert loader.manifests[2].dimensions["index"] == 3

    def test_clear(self):
        """Test clearing loaded data."""

        class SimpleLoader(ManifestLoader):
            def _load_source(self, source: Path) -> ManifestData:
                return ManifestData(source_type="test")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test")
            path = Path(f.name)

        loader = SimpleLoader()
        loader.load(path)
        assert len(loader) == 1

        loader.clear()
        assert len(loader) == 0
        assert loader.manifest is None


# endregion


# region MatchData Tests


class TestMatchData:
    """Tests for MatchData."""

    def test_empty(self):
        """Test creating empty MatchData."""
        matches = MatchData.empty()
        assert len(matches) == 0

    def test_from_dicts(self):
        """Test creating MatchData from dictionaries."""
        matches = MatchData.from_dicts(
            [
                {
                    "match_id": "m1",
                    "source_event_id": "e1",
                    "source_domain": "logical",
                    "source_coordinate": {
                        "value": 0.0,
                        "numerator": 0,
                        "denominator": 1,
                    },
                    "target_event_id": "e2",
                    "target_domain": "physical",
                    "target_coordinate": {
                        "value": 1.5,
                        "numerator": None,
                        "denominator": None,
                    },
                    "confidence": 0.95,
                    "agent": "test",
                    "method": "manual",
                },
            ]
        )

        assert len(matches) == 1

    def test_extend(self):
        """Test extending MatchData."""
        m1 = MatchData.from_dicts(
            [
                {
                    "match_id": "m1",
                    "source_event_id": None,
                    "source_domain": "logical",
                    "source_coordinate": None,
                    "target_event_id": None,
                    "target_domain": "physical",
                    "target_coordinate": None,
                    "confidence": None,
                    "agent": None,
                    "method": None,
                }
            ]
        )
        m2 = MatchData.from_dicts(
            [
                {
                    "match_id": "m2",
                    "source_event_id": None,
                    "source_domain": "graphical",
                    "source_coordinate": None,
                    "target_event_id": None,
                    "target_domain": "physical",
                    "target_coordinate": None,
                    "confidence": None,
                    "agent": None,
                    "method": None,
                }
            ]
        )

        m1.extend(m2)
        assert len(m1) == 2

    def test_iteration(self):
        """Test iterating over matches."""
        matches = MatchData.from_dicts(
            [
                {
                    "match_id": f"m{i}",
                    "source_event_id": None,
                    "source_domain": "logical",
                    "source_coordinate": None,
                    "target_event_id": None,
                    "target_domain": "physical",
                    "target_coordinate": None,
                    "confidence": None,
                    "agent": None,
                    "method": None,
                }
                for i in range(5)
            ]
        )

        ids = [m["match_id"] for m in matches]
        assert ids == ["m0", "m1", "m2", "m3", "m4"]


# endregion


# region AlignmentStore Tests


class TestAlignmentStore:
    """Tests for AlignmentStore."""

    def test_empty(self):
        """Test creating empty AlignmentStore."""
        store = AlignmentStore.empty()

        assert store.event_count == 0
        assert store.match_count == 0
        assert store.cmap_count == 0

    def test_with_events(self):
        """Test AlignmentStore with events."""
        events = EventData.from_dicts(
            [
                {
                    "id": "e1",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "start": 0.0,
                },
                {
                    "id": "e2",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "start": 1.0,
                },
            ],
            unit=TimeUnit.seconds,
        )

        store = AlignmentStore(
            events=SingleStore(events, name="beats"),
            cmaps=[],
            matches=MatchData.empty(),
        )

        assert store.event_count == 2

    def test_get_matches_for_event(self):
        """Test retrieving matches for a specific event."""
        events = EventData.from_dicts(
            [
                {
                    "id": "e1",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "start": 0.0,
                }
            ],
            unit=TimeUnit.seconds,
        )

        matches = MatchData.from_dicts(
            [
                {
                    "match_id": "m1",
                    "source_event_id": "e1",
                    "source_domain": "logical",
                    "source_coordinate": None,
                    "target_event_id": "e2",
                    "target_domain": "physical",
                    "target_coordinate": None,
                    "confidence": None,
                    "agent": None,
                    "method": None,
                },
                {
                    "match_id": "m2",
                    "source_event_id": "e3",
                    "source_domain": "logical",
                    "source_coordinate": None,
                    "target_event_id": "e1",
                    "target_domain": "physical",
                    "target_coordinate": None,
                    "confidence": None,
                    "agent": None,
                    "method": None,
                },
            ]
        )

        store = AlignmentStore(
            events=SingleStore(events, name="events"),
            cmaps=[],
            matches=matches,
        )

        # e1 is involved in both matches (as source in m1, as target in m2)
        e1_matches = store.get_matches_for_event("e1")
        assert len(e1_matches) == 2

        # e3 is only in m2
        e3_matches = store.get_matches_for_event("e3")
        assert len(e3_matches) == 1

    def test_summary(self):
        """Test summary generation."""
        store = AlignmentStore.empty()
        summary = store.summary()

        assert "event_count" in summary
        assert "match_count" in summary
        assert "cmap_count" in summary


# endregion


# region AlignmentLoader Tests


class TestAlignmentLoader:
    """Tests for AlignmentLoader ABC."""

    def test_concrete_implementation(self):
        """Test a concrete AlignmentLoader implementation."""

        class TestAlignmentLoader(AlignmentLoader):
            def _load_source(self, source: Path) -> AlignmentStore:
                events = EventData.from_dicts(
                    [
                        {
                            "id": "e1",
                            "temporal_type": "instant",
                            "event_type": "Beat",
                            "start": 0.0,
                        }
                    ],
                    unit=TimeUnit.seconds,
                )
                return AlignmentStore(
                    events=SingleStore(events, name="events"),
                    cmaps=[],
                    matches=MatchData.empty(),
                )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write("<alignment/>")
            path = Path(f.name)

        loader = TestAlignmentLoader()
        loader.load(path)

        assert len(loader) == 1
        assert loader.store is not None
        assert loader.store.event_count == 1

    def test_clear(self):
        """Test clearing loaded data."""

        class SimpleAlignmentLoader(AlignmentLoader):
            def _load_source(self, source: Path) -> AlignmentStore:
                return AlignmentStore.empty()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write("<alignment/>")
            path = Path(f.name)

        loader = SimpleAlignmentLoader()
        loader.load(path)
        assert loader.store is not None

        loader.clear()
        assert loader.store is None
        assert len(loader.sources) == 0


# endregion
