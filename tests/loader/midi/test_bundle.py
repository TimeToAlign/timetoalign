"""Tests for MidiBundle.

This module tests the MidiBundle class which splits a MidiEventStore
into separate notes and controls stores.
"""

from __future__ import annotations

import pytest

from timetoalign.core import TimeUnit
from timetoalign.loader.midi import MidiBundle, MidiEventStore


class TestMidiBundleFromStore:
    """Tests for MidiBundle.from_store() splitting behavior."""

    @pytest.fixture
    def mixed_midi_store(self) -> MidiEventStore:
        """MidiEventStore with notes and control events."""
        return MidiEventStore.from_dicts(
            [
                {
                    "id": "n1",
                    "temporal_type": "interval",
                    "event_type": "Note",
                    "start": 0,
                    "end": 480,
                    "pitch": 60,
                    "velocity": 64,
                    "channel": 0,
                },
                {
                    "id": "n2",
                    "temporal_type": "interval",
                    "event_type": "Note",
                    "start": 480,
                    "end": 960,
                    "pitch": 62,
                    "velocity": 80,
                    "channel": 0,
                },
                {
                    "id": "cc1",
                    "temporal_type": "instant",
                    "event_type": "ControlChange",
                    "instant": 0,
                    "control": 64,
                    "value": 127,
                    "channel": 0,
                },
                {
                    "id": "pc1",
                    "temporal_type": "instant",
                    "event_type": "ProgramChange",
                    "instant": 0,
                    "program": 1,
                    "channel": 0,
                },
            ],
            unit=TimeUnit.ticks,
        )

    def test_from_store_splits_notes(self, mixed_midi_store: MidiEventStore):
        """from_store separates Note events into notes store."""
        bundle = MidiBundle.from_store(mixed_midi_store)

        # Exact count: 2 notes
        assert len(bundle.notes) == 2

    def test_from_store_splits_controls(self, mixed_midi_store: MidiEventStore):
        """from_store separates control events into controls store."""
        bundle = MidiBundle.from_store(mixed_midi_store)

        # Exact count: 1 ControlChange + 1 ProgramChange = 2
        assert len(bundle.controls) == 2

    def test_notes_have_correct_event_type(self, mixed_midi_store: MidiEventStore):
        """All events in notes store have event_type='Note'."""
        bundle = MidiBundle.from_store(mixed_midi_store)

        for event in bundle.notes:
            assert event["event_type"] == "Note"

    def test_controls_have_control_event_types(self, mixed_midi_store: MidiEventStore):
        """All events in controls store have control event types."""
        bundle = MidiBundle.from_store(mixed_midi_store)

        valid_types = {"ControlChange", "ProgramChange", "PitchBend"}
        for event in bundle.controls:
            assert event["event_type"] in valid_types

    def test_metadata_preserved(self, mixed_midi_store: MidiEventStore):
        """Metadata is attached to bundle."""
        metadata = {"ticks_per_beat": 480, "format": 1}
        bundle = MidiBundle.from_store(mixed_midi_store, metadata=metadata)

        assert bundle.metadata["ticks_per_beat"] == 480
        assert bundle.metadata["format"] == 1


class TestMidiBundleEmpty:
    """Tests for MidiBundle.empty()."""

    def test_empty_bundle_has_empty_stores(self):
        """Empty bundle has zero events in both stores."""
        bundle = MidiBundle.empty()

        assert len(bundle.notes) == 0
        assert len(bundle.controls) == 0

    def test_empty_bundle_metadata(self):
        """Empty bundle has empty metadata."""
        bundle = MidiBundle.empty()

        assert bundle.metadata == {}


class TestMidiBundleExtend:
    """Tests for MidiBundle.extend()."""

    @pytest.fixture
    def bundle_a(self) -> MidiBundle:
        """First MidiBundle with 2 notes."""
        store = MidiEventStore.from_dicts(
            [
                {
                    "id": "a_n1",
                    "temporal_type": "interval",
                    "event_type": "Note",
                    "start": 0,
                    "end": 480,
                    "pitch": 60,
                },
                {
                    "id": "a_n2",
                    "temporal_type": "interval",
                    "event_type": "Note",
                    "start": 480,
                    "end": 960,
                    "pitch": 62,
                },
            ],
            unit=TimeUnit.ticks,
        )
        return MidiBundle.from_store(store, metadata={"source": "a"})

    @pytest.fixture
    def bundle_b(self) -> MidiBundle:
        """Second MidiBundle with 1 note and 1 control."""
        store = MidiEventStore.from_dicts(
            [
                {
                    "id": "b_n1",
                    "temporal_type": "interval",
                    "event_type": "Note",
                    "start": 0,
                    "end": 480,
                    "pitch": 64,
                },
                {
                    "id": "b_cc1",
                    "temporal_type": "instant",
                    "event_type": "ControlChange",
                    "instant": 0,
                    "control": 64,
                },
            ],
            unit=TimeUnit.ticks,
        )
        return MidiBundle.from_store(store, metadata={"source": "b"})

    def test_extend_merges_notes(self, bundle_a: MidiBundle, bundle_b: MidiBundle):
        """extend() merges notes from both bundles."""
        bundle_a.extend(bundle_b)

        # Exact count: 2 from a + 1 from b = 3
        assert len(bundle_a.notes) == 3

    def test_extend_merges_controls(self, bundle_a: MidiBundle, bundle_b: MidiBundle):
        """extend() merges controls from both bundles."""
        bundle_a.extend(bundle_b)

        # Exact count: 0 from a + 1 from b = 1
        assert len(bundle_a.controls) == 1

    def test_extend_updates_metadata(self, bundle_a: MidiBundle, bundle_b: MidiBundle):
        """extend() updates metadata (last wins)."""
        bundle_a.extend(bundle_b)

        assert bundle_a.metadata["source"] == "b"


class TestMidiBundleProtocol:
    """Tests for MidiBundle EventBundle protocol compliance."""

    @pytest.fixture
    def sample_bundle(self) -> MidiBundle:
        """MidiBundle for protocol testing."""
        store = MidiEventStore.from_dicts(
            [
                {
                    "id": "n1",
                    "temporal_type": "interval",
                    "event_type": "Note",
                    "start": 0,
                    "end": 480,
                    "pitch": 60,
                },
                {
                    "id": "cc1",
                    "temporal_type": "instant",
                    "event_type": "ControlChange",
                    "instant": 0,
                },
            ],
            unit=TimeUnit.ticks,
        )
        return MidiBundle.from_store(store)

    def test_keys_canonical_order(self, sample_bundle: MidiBundle):
        """keys() returns canonical order."""
        assert sample_bundle.keys() == ("notes", "controls")

    def test_iteration_order(self, sample_bundle: MidiBundle):
        """Iteration yields stores in canonical order."""
        stores = list(sample_bundle)

        assert stores[0] is sample_bundle.notes
        assert stores[1] is sample_bundle.controls

    def test_items_order(self, sample_bundle: MidiBundle):
        """items() yields in canonical order."""
        items = list(sample_bundle.items())

        assert items[0] == ("notes", sample_bundle.notes)
        assert items[1] == ("controls", sample_bundle.controls)

    def test_getitem_notes(self, sample_bundle: MidiBundle):
        """Can access notes by name."""
        assert sample_bundle["notes"] is sample_bundle.notes

    def test_getitem_controls(self, sample_bundle: MidiBundle):
        """Can access controls by name."""
        assert sample_bundle["controls"] is sample_bundle.controls

    def test_getitem_invalid_raises(self, sample_bundle: MidiBundle):
        """Invalid name raises KeyError."""
        with pytest.raises(KeyError, match="invalid"):
            _ = sample_bundle["invalid"]

    def test_len(self, sample_bundle: MidiBundle):
        """Length is always 2."""
        assert len(sample_bundle) == 2

    def test_contains(self, sample_bundle: MidiBundle):
        """Membership check works."""
        assert "notes" in sample_bundle
        assert "controls" in sample_bundle
        assert "invalid" not in sample_bundle


class TestMidiBundleSummary:
    """Tests for MidiBundle.summary()."""

    def test_summary_counts(self):
        """summary() includes correct counts."""
        store = MidiEventStore.from_dicts(
            [
                {
                    "id": "n1",
                    "temporal_type": "interval",
                    "event_type": "Note",
                    "start": 0,
                    "end": 480,
                },
                {
                    "id": "n2",
                    "temporal_type": "interval",
                    "event_type": "Note",
                    "start": 480,
                    "end": 960,
                },
                {
                    "id": "cc1",
                    "temporal_type": "instant",
                    "event_type": "ControlChange",
                    "instant": 0,
                },
            ],
            unit=TimeUnit.ticks,
        )
        bundle = MidiBundle.from_store(store)

        summary = bundle.summary()

        # Exact counts
        assert summary["notes_count"] == 2
        assert summary["controls_count"] == 1


class TestMidiBundleToTimeline:
    """Tests for MidiBundle timeline creation."""

    @pytest.fixture
    def sample_bundle(self) -> MidiBundle:
        """MidiBundle with notes and controls."""
        store = MidiEventStore.from_dicts(
            [
                {
                    "id": "n1",
                    "temporal_type": "interval",
                    "event_type": "Note",
                    "start": 0,
                    "end": 480,
                    "pitch": 60,
                },
                {
                    "id": "n2",
                    "temporal_type": "interval",
                    "event_type": "Note",
                    "start": 480,
                    "end": 960,
                    "pitch": 62,
                },
                {
                    "id": "cc1",
                    "temporal_type": "instant",
                    "event_type": "ControlChange",
                    "instant": 0,
                    "control": 64,
                },
            ],
            unit=TimeUnit.ticks,
        )
        return MidiBundle.from_store(store)

    def test_to_default_timeline_creates_children(self, sample_bundle: MidiBundle):
        """to_default_timeline creates parent with children."""
        timeline = sample_bundle.to_default_timeline(uid="test")

        assert timeline.id == "test"
        # 2 children: notes and controls
        assert timeline.n_children == 2

    def test_children_at_offset_zero(self, sample_bundle: MidiBundle):
        """Children are embedded at offset 0."""
        timeline = sample_bundle.to_default_timeline()

        assert timeline.get_child_offset("notes").value == 0
        assert timeline.get_child_offset("controls").value == 0

    def test_notes_child_has_correct_count(self, sample_bundle: MidiBundle):
        """Notes child has exact event count."""
        timeline = sample_bundle.to_default_timeline()

        notes_tl = timeline.get_child("notes")
        # Exact count: 2 notes
        assert notes_tl.n_events == 2

    def test_controls_child_has_correct_count(self, sample_bundle: MidiBundle):
        """Controls child has exact event count."""
        timeline = sample_bundle.to_default_timeline()

        controls_tl = timeline.get_child("controls")
        # Exact count: 1 control change
        assert controls_tl.n_events == 1
