"""Test fixtures for loader package tests."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import pytest

from timetoalign.core import NumberType, TimeUnit
from timetoalign.loader import EventStore, Loader


@pytest.fixture
def sample_instant_events() -> list[dict[str, Any]]:
    """Sample instant event rows."""
    return [
        {
            "id": "beat_1",
            "name": "Beat 1",
            "temporal_type": "instant",
            "event_type": "Beat",
            "instant": 0,
        },
        {
            "id": "beat_2",
            "name": "Beat 2",
            "temporal_type": "instant",
            "event_type": "Beat",
            "instant": 480,
        },
        {
            "id": "beat_3",
            "name": None,
            "temporal_type": "instant",
            "event_type": "Beat",
            "instant": 960,
        },
    ]


@pytest.fixture
def sample_interval_events() -> list[dict[str, Any]]:
    """Sample interval event rows."""
    return [
        {
            "id": "note_1",
            "name": "C4",
            "temporal_type": "interval",
            "event_type": "Note",
            "start": 0,
            "end": 240,
        },
        {
            "id": "note_2",
            "name": "E4",
            "temporal_type": "interval",
            "event_type": "Note",
            "start": 240,
            "end": 480,
        },
    ]


@pytest.fixture
def sample_mixed_events(
    sample_instant_events: list[dict[str, Any]],
    sample_interval_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sample mixed instant and interval events."""
    return sample_instant_events + sample_interval_events


@pytest.fixture
def sample_fraction_events() -> list[dict[str, Any]]:
    """Sample events with Fraction coordinates."""
    return [
        {
            "id": "beat_1",
            "temporal_type": "instant",
            "event_type": "Beat",
            "instant": Fraction(0),
        },
        {
            "id": "beat_2",
            "temporal_type": "instant",
            "event_type": "Beat",
            "instant": Fraction(1, 4),
        },
        {
            "id": "note_1",
            "temporal_type": "interval",
            "event_type": "Note",
            "start": Fraction(0),
            "end": Fraction(1, 8),
        },
    ]


@pytest.fixture
def empty_store() -> EventStore:
    """An empty EventStore."""
    return EventStore.empty(TimeUnit.ticks)


@pytest.fixture
def store_with_instants(sample_instant_events: list[dict[str, Any]]) -> EventStore:
    """EventStore with instant events."""
    return EventStore.from_dicts(sample_instant_events, TimeUnit.ticks)


@pytest.fixture
def store_with_intervals(sample_interval_events: list[dict[str, Any]]) -> EventStore:
    """EventStore with interval events."""
    return EventStore.from_dicts(sample_interval_events, TimeUnit.ticks)


@pytest.fixture
def store_with_mixed(sample_mixed_events: list[dict[str, Any]]) -> EventStore:
    """EventStore with mixed event types."""
    return EventStore.from_dicts(sample_mixed_events, TimeUnit.ticks)


@pytest.fixture
def temp_parquet_path() -> Path:
    """Temporary path for Parquet file testing."""
    with NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        return Path(f.name)


class DummyLoader(Loader):
    """A concrete Loader implementation for testing."""

    _default_unit = TimeUnit.ticks

    def _load_source(self, source: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Simulate loading a source file."""
        if not source.exists():
            raise FileNotFoundError(f"Source not found: {source}")

        # Simulate parsing a file with some events
        metadata = {
            "format": "dummy",
            "original_path": str(source),
        }
        events = [
            {
                "id": f"{source.stem}_beat_1",
                "temporal_type": "instant",
                "event_type": "Beat",
                "instant": 0,
            },
            {
                "id": f"{source.stem}_note_1",
                "temporal_type": "interval",
                "event_type": "Note",
                "start": 0,
                "end": 480,
            },
        ]
        return metadata, events


@pytest.fixture
def dummy_loader() -> DummyLoader:
    """A DummyLoader instance for testing."""
    return DummyLoader()


@pytest.fixture
def temp_source_file() -> Path:
    """A temporary source file for loader testing."""
    with NamedTemporaryFile(suffix=".dummy", delete=False) as f:
        f.write(b"dummy content")
        return Path(f.name)
