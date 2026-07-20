"""Tests for BeatGrid (metrical timeline).

This module comprehensively tests BeatGrid functionality, including validation
against real-world SUPRA data (Wagner Meistersinger Prelude, 222 measures).

The SUPRA test validates that BeatGrid correctly computes measure numbers and
beat positions for a known musical work, proving the mechanism works correctly.
"""

from fractions import Fraction

import numpy as np
import pytest

from timetoalign.core import Coordinate, TimeUnit
from timetoalign.maps import ScalarMap
from timetoalign.timelines import BeatGrid


class TestBeatGridBasic:
    """Basic BeatGrid functionality tests."""

    def test_initialization(self):
        """Test basic initialization."""
        grid = BeatGrid(length=Fraction(32, 1), beats_per_measure=4)

        assert grid.length.value == Fraction(32, 1)
        assert grid.unit == TimeUnit.quarters
        assert grid.beats_per_measure == 4
        assert grid.beat_unit == Fraction(1, 4)
        assert grid.start_measure == 1
        assert grid.quarters_per_measure == Fraction(4, 1)
        assert grid.n_measures == 8  # 32 / 4 = 8 measures

    def test_invalid_beats_per_measure(self):
        """beats_per_measure must be positive."""
        with pytest.raises(ValueError, match="beats_per_measure"):
            BeatGrid(length=32, beats_per_measure=0)
        with pytest.raises(ValueError, match="beats_per_measure"):
            BeatGrid(length=32, beats_per_measure=-1)

    def test_invalid_beat_unit(self):
        """beat_unit must be positive."""
        with pytest.raises(ValueError, match="beat_unit"):
            BeatGrid(length=32, beat_unit=Fraction(0, 1))

    def test_4_4_time(self):
        """Test standard 4/4 time signature."""
        grid = BeatGrid(length=Fraction(16, 1), beats_per_measure=4)

        # 4 quarters per measure (quarter note = 1 beat)
        assert grid.quarters_per_measure == Fraction(4, 1)
        assert grid.quarters_per_beat == Fraction(1, 1)
        assert grid.n_measures == 4

    def test_3_4_time(self):
        """Test 3/4 time signature."""
        grid = BeatGrid(length=Fraction(12, 1), beats_per_measure=3)

        # 3 quarters per measure (quarter note = 1 beat)
        assert grid.quarters_per_measure == Fraction(3, 1)
        assert grid.quarters_per_beat == Fraction(1, 1)
        assert grid.n_measures == 4

    def test_6_8_time(self):
        """Test 6/8 time signature (eighth-note beats)."""
        grid = BeatGrid(
            length=Fraction(12, 1),  # 12 quarters
            beats_per_measure=6,
            beat_unit=Fraction(1, 8),  # Eighth note beats
        )

        # 6 eighth notes per measure = 3 quarters per measure
        # Each beat = 1/8 note = 1/2 quarter
        assert grid.quarters_per_beat == Fraction(1, 2)
        assert grid.quarters_per_measure == Fraction(3, 1)
        assert grid.n_measures == 4  # 12 / 3 = 4 measures


class TestBeatGridMetricalMaps:
    """Test the built-in metrical C-Maps.

    The new MetricMap-based implementation uses:
    - 'mc' (measure count) instead of 'measure'
    - Fraction for beat positions (not float)
    - MetricMap with explicit boundaries
    """

    def test_measure_at_4_4(self):
        """Test measure number lookup in 4/4."""
        grid = BeatGrid(length=Fraction(100, 1), beats_per_measure=4)

        # Measure 1: quarters 0-3.99
        assert grid.measure_at(0) == 1
        assert grid.measure_at(1) == 1
        assert grid.measure_at(3) == 1
        assert grid.measure_at(3.99) == 1

        # Measure 2: quarters 4-7.99
        assert grid.measure_at(4) == 2
        assert grid.measure_at(7.5) == 2

        # 100 quarters / 4 = 25 measures
        # Quarter 96-99 = measure 25
        # Quarter 100 would be measure 26 but grid only has 25 measures
        # So measure_at(96) == 25 (inside the grid)
        assert grid.measure_at(96) == 25
        assert grid.measure_at(99) == 25

    def test_beat_at_4_4(self):
        """Test exact beat position lookup in 4/4."""
        grid = BeatGrid(length=Fraction(100, 1), beats_per_measure=4)

        # Beat 1 at measure starts
        assert grid.beat_at(0) == Fraction(1, 1)
        assert grid.beat_at(4) == Fraction(1, 1)
        assert grid.beat_at(96) == Fraction(1, 1)  # Start of measure 25

        # Other beats
        assert grid.beat_at(1) == Fraction(2, 1)
        assert grid.beat_at(2) == Fraction(3, 1)
        assert grid.beat_at(3) == Fraction(4, 1)

        # Fractional beats
        assert grid.beat_at(Fraction(1, 2)) == Fraction(3, 2)  # 1.5
        assert grid.beat_at(Fraction(17, 4)) == Fraction(5, 4)  # 4.25 -> beat 1.25

        assert float(grid.beat_at(0.5)) == 1.5

    def test_beat_at_respects_beat_unit(self) -> None:
        """Beat lookup scales offsets by the configured musical beat unit."""
        compound = BeatGrid(length=6, beats_per_measure=6, beat_unit=Fraction(1, 8))
        alla_breve = BeatGrid(length=8, beats_per_measure=2, beat_unit=Fraction(1, 2))

        assert compound.beat_at(0) == Fraction(1, 1)
        assert compound.beat_at(Fraction(1, 2)) == Fraction(2, 1)
        assert compound.beat_at(Fraction(5, 2)) == Fraction(6, 1)
        assert alla_breve.beat_at(0) == Fraction(1, 1)
        assert alla_breve.beat_at(2) == Fraction(2, 1)
        assert compound.quarter_at(1, 2) == Fraction(1, 2)
        assert alla_breve.quarter_at(1, 2) == Fraction(2, 1)

    def test_serialization_round_trip(self) -> None:
        """Serialization rebuilds the grid's metrical maps and timeline state."""
        grid = BeatGrid(length=16, beats_per_measure=4)
        grid.add_events(
            [
                {
                    "id": "beat",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "instant": 0,
                }
            ]
        )
        grid._meta = {"source": "test"}

        restored = BeatGrid.from_dict(grid.to_dict())

        assert type(restored) is BeatGrid
        assert float(restored.length.value) == 16.0
        assert restored.measure_at(4.0) == 2
        assert restored.beat_at(Fraction(1, 2)) == Fraction(3, 2)
        assert restored.quarter_at(2) == Fraction(4, 1)
        assert len(restored._conversion_maps) == len(grid._conversion_maps)

        anacrusis_grid = BeatGrid(
            length=16,
            beats_per_measure=4,
            start_mn="0",
            anacrusis_quarters=Fraction(1, 1),
        )
        restored_anacrusis = BeatGrid.from_dict(anacrusis_grid.to_dict())

        assert restored_anacrusis.mn_at(0) == "0"
        assert restored_anacrusis.mn_at(1) == "1"
        assert restored.meta == {"source": "test"}
        assert len(restored.get_events(event_type="Beat")) == 1

    def test_tempo_serialization_round_trip(self) -> None:
        """Serialization preserves tempo-driven seconds queries."""
        grid = BeatGrid.from_tempo(
            tempo_bpm=120.0,
            length_quarters=Fraction(16, 1),
            start_seconds=0.5,
        )

        restored = BeatGrid.from_dict(grid.to_dict())

        assert restored.tempo_bpm == 120.0
        np.testing.assert_array_equal(restored.beat_seconds()[:3], [0.5, 1.0, 1.5])

    def test_to_dict_excludes_metrical_maps(self) -> None:
        """A plain grid's serialized conversion_maps list is empty."""
        grid = BeatGrid(length=16, beats_per_measure=4)
        data = grid.to_dict()
        assert data["conversion_maps"] == []

    def test_to_dict_serializes_only_tempo_map(self) -> None:
        """A from_tempo grid serializes exactly its tempo map."""
        grid = BeatGrid.from_tempo(tempo_bpm=120.0, length_seconds=60.0)
        data = grid.to_dict()
        assert len(data["conversion_maps"]) == 1
        assert data["conversion_maps"][0]["id"] == grid._tempo_map.id

    def test_round_trip_reconstructs_three_maps(self) -> None:
        """A plain grid round-trips to exactly 3 conversion maps."""
        grid = BeatGrid(length=16, beats_per_measure=4)
        restored = BeatGrid.from_dict(grid.to_dict())
        assert len(restored._conversion_maps) == 3
        assert restored.measure_at(4.0) == 2
        assert restored.beat_at(Fraction(1, 2)) == Fraction(3, 2)

    def test_round_trip_with_tempo_reconstructs_four_maps(self) -> None:
        """A from_tempo grid round-trips to exactly 4 conversion maps."""
        grid = BeatGrid.from_tempo(tempo_bpm=120.0, length_seconds=60.0)
        restored = BeatGrid.from_dict(grid.to_dict())
        assert len(restored._conversion_maps) == 4

    def test_user_attached_map_survives_round_trip(self) -> None:
        """A user-attached extra conversion map is preserved by round-tripping."""
        grid = BeatGrid(length=16, beats_per_measure=4)
        extra = ScalarMap(scalar=3.0, source_unit="quarters", target_unit="ticks")
        grid.add_conversion_map(extra)

        data = grid.to_dict()
        assert len(data["conversion_maps"]) == 1
        assert data["conversion_maps"][0]["id"] == extra.id

        restored = BeatGrid.from_dict(data)
        assert len(restored._conversion_maps) == 4
        assert extra.id in restored._conversion_maps

    def test_metrical_position(self):
        """Test combined measure/beat lookup.

        Note: metrical_position now returns 'mc' (measure count) not 'measure',
        and 'beat' is a Fraction, and includes 'mn' (measure number label).
        """
        grid = BeatGrid(length=Fraction(100, 1), beats_per_measure=4)

        result = grid.metrical_position(0)
        assert result["mc"] == 1
        assert result["beat"] == Fraction(1, 1)
        assert result["mn"] == "1"

        result = grid.metrical_position(7.5)
        assert result["mc"] == 2
        assert result["beat"] == Fraction(9, 2)  # 4.5
        assert result["mn"] == "2"

        # Quarter 96 = start of measure 25
        result = grid.metrical_position(96)
        assert result["mc"] == 25
        assert result["beat"] == Fraction(1, 1)

    def test_quarter_at(self):
        """Test reverse lookup: measure/beat -> quarter."""
        grid = BeatGrid(length=Fraction(100, 1), beats_per_measure=4)

        # Measure 1, beat 1 -> quarter 0
        assert grid.quarter_at(1, 1) == Fraction(0, 1)

        # Measure 1, beat 2 -> quarter 1
        assert grid.quarter_at(1, 2) == Fraction(1, 1)

        # Measure 2, beat 1 -> quarter 4
        assert grid.quarter_at(2, 1) == Fraction(4, 1)

        # Measure 25, beat 1 -> quarter 96 (25 measures in this grid)
        assert grid.quarter_at(25, 1) == Fraction(96, 1)

        # Fractional beat
        assert grid.quarter_at(1, Fraction(3, 2)) == Fraction(1, 2)  # beat 1.5

    def test_quarter_at_validation(self):
        """Test validation in quarter_at."""
        grid = BeatGrid(length=Fraction(100, 1), beats_per_measure=4)

        # MC 0 is not in the meter map
        with pytest.raises(ValueError, match="not found"):
            grid.quarter_at(0, 1)

        # MC 26 is beyond the grid (only has 25 measures)
        with pytest.raises(ValueError, match="not found"):
            grid.quarter_at(26, 1)

    def test_coordinate_queries_preserve_native_fraction(self) -> None:
        """Public metrical queries preserve exact native Fraction input."""
        grid = BeatGrid(length=Fraction(16), beats_per_measure=4)
        coordinate = Fraction(5, 2)

        assert grid.measure_at(coordinate) == 1
        assert grid.mn_at(coordinate) == "1"
        assert grid.beat_at(coordinate) == Fraction(7, 2)
        assert grid.metrical_position(coordinate) == {
            "mc": 1,
            "beat": Fraction(7, 2),
            "mn": "1",
        }

    def test_coordinate_queries_convert_foreign_unit(self) -> None:
        """Public metrical queries convert foreign coordinates through a C-Map."""
        grid = BeatGrid(length=Fraction(16), beats_per_measure=4)
        grid.add_conversion_map(
            ScalarMap(
                scalar=480,
                source_unit=TimeUnit.quarters,
                target_unit=TimeUnit.ticks,
            )
        )
        coordinate = Coordinate(1200, TimeUnit.ticks)

        assert grid.measure_at(coordinate) == 1
        assert grid.mn_at(coordinate) == "1"
        assert grid.beat_at(coordinate) == Fraction(7, 2)
        assert grid.metrical_position(coordinate) == {
            "mc": 1,
            "beat": Fraction(7, 2),
            "mn": "1",
        }

    @pytest.mark.parametrize(
        "method_name", ["measure_at", "mn_at", "beat_at", "metrical_position"]
    )
    def test_coordinate_queries_reject_foreign_unit_without_map(
        self, method_name: str
    ) -> None:
        """Public metrical queries reject foreign coordinates without a C-Map."""
        grid = BeatGrid(length=Fraction(16), beats_per_measure=4, uid="grid")
        coordinate = Coordinate(1200, TimeUnit.ticks)

        with pytest.raises(ValueError) as exc_info:
            getattr(grid, method_name)(coordinate)

        assert str(exc_info.value) == (
            "No C-Map available to convert coordinate from unit 'ticks' to "
            "'quarters' on timeline 'grid'"
        )


class TestBeatGridMaterialization:
    """Test event materialization."""

    def test_materialize_beats(self):
        """Test creating Beat events."""
        grid = BeatGrid(length=Fraction(8, 1), beats_per_measure=4)

        n_beats = grid.materialize_beats()

        # 8 quarters = 8 beats in 4/4
        assert n_beats == 8

        events = grid.get_events(event_type="Beat")
        assert len(events) == 8

    def test_materialize_beats_downbeats_only(self):
        """Test creating only downbeat events."""
        grid = BeatGrid(length=Fraction(8, 1), beats_per_measure=4)

        n_downbeats = grid.materialize_beats(include_downbeats_only=True)

        # 8 quarters = 2 measures = 2 downbeats
        assert n_downbeats == 2

    def test_materialize_measures(self):
        """Test creating Measure events."""
        grid = BeatGrid(length=Fraction(8, 1), beats_per_measure=4)

        n_measures = grid.materialize_measures()

        # 8 quarters / 4 = 2 complete measures
        assert n_measures == 2

        events = grid.get_events(event_type="Measure")
        assert len(events) == 2

    def test_partial_measure(self):
        """Test handling of partial final measure.

        With MetricMap.from_uniform, only complete measures are created.
        10 quarters / 4 = 2.5, so only 2 complete measures.
        """
        grid = BeatGrid(length=Fraction(10, 1), beats_per_measure=4)

        n_measures = grid.materialize_measures()

        # 2 complete measures (8 quarters); the 2 extra quarters don't form a measure
        assert n_measures == 2


class TestBeatGridFromTempo:
    """Test factory method from tempo."""

    def test_from_tempo_with_length_quarters(self):
        """Test creation with length in quarters."""
        grid = BeatGrid.from_tempo(
            tempo_bpm=120.0,
            beats_per_measure=4,
            length_quarters=Fraction(100, 1),
        )

        assert grid.length.value == Fraction(100, 1)
        assert grid.tempo_bpm == 120.0
        assert grid.beats_per_measure == 4

    def test_from_tempo_with_length_seconds(self):
        """Test creation with length in seconds."""
        # At 120 BPM with quarter-note beats:
        # 2 beats/second = 2 quarters/second
        # 60 seconds = 120 quarters
        grid = BeatGrid.from_tempo(
            tempo_bpm=120.0,
            beats_per_measure=4,
            length_seconds=60.0,
        )

        assert grid.length.value == Fraction(120, 1)

    def test_from_tempo_tempo_map(self):
        """Test that tempo C-Map is created."""
        grid = BeatGrid.from_tempo(
            tempo_bpm=120.0,
            beats_per_measure=4,
            length_quarters=Fraction(100, 1),
        )

        # Check tempo map exists
        assert hasattr(grid, "_tempo_map")

        # At 120 BPM: 2 beats/second = 2 quarters/second
        # So 1 quarter = 0.5 seconds
        seconds = grid._tempo_map(1.0)
        assert seconds == 0.5

    def test_from_tempo_validation(self):
        """Test validation of arguments."""
        with pytest.raises(ValueError, match="Must provide"):
            BeatGrid.from_tempo(tempo_bpm=120.0)

        with pytest.raises(ValueError, match="Cannot provide both"):
            BeatGrid.from_tempo(
                tempo_bpm=120.0,
                length_quarters=100,
                length_seconds=60.0,
            )


class TestBeatGridAsChild:
    """Test BeatGrid relationships with other timelines.

    Note: According to the TTA model, children must share the same measuring
    unit as the parent. A BeatGrid (in quarters) cannot be a direct child of
    a physical timeline (in seconds). Cross-domain relationships should be
    established via C-Maps (e.g., tempo maps) or alignment anchors.
    """

    def test_relate_to_physical_timeline_via_tempo_map(self):
        """Test relating BeatGrid to a physical timeline via tempo C-Map.

        This demonstrates the correct TTA approach: cross-domain relationships
        use C-Maps, not parent-child embedding.
        """
        # Beat grid for 4/4 at 120 BPM
        # At 120 BPM: 0.5 seconds/quarter (2 quarters/second)
        grid = BeatGrid.from_tempo(
            tempo_bpm=120.0,
            beats_per_measure=4,
            length_seconds=118.0,
        )

        # The _tempo_map is a C-Map that converts quarters -> seconds
        # (created automatically by from_tempo)
        assert hasattr(grid, "_tempo_map")
        tempo_map = grid._tempo_map
        assert tempo_map is not None

        # Verify tempo map converts correctly (maps are callable)
        # At 120 BPM: quarter 0 -> 0.0 seconds
        assert tempo_map(0) == 0.0
        # quarter 1 -> 0.5 seconds
        assert tempo_map(1) == 0.5
        # quarter 4 (one measure) -> 2.0 seconds
        assert tempo_map(4) == 2.0

        # The BeatGrid can convert quarters to seconds using the tempo map
        # This demonstrates that cross-domain conversion is done via C-Maps
        assert grid.get_conversion_map(TimeUnit.seconds) is not None

    def test_start_measure_offset(self):
        """Test custom start measure number."""
        grid = BeatGrid(
            length=Fraction(32, 1),
            beats_per_measure=4,
            start_measure=5,  # Start numbering at measure 5
        )

        # First quarter should be measure 5
        assert grid.measure_at(0) == 5
        assert grid.measure_at(4) == 6
        assert grid.measure_at(8) == 7


class TestBeatGridVectorizedAccessors:
    """Tests for vectorized beat/measure accessors.

    These methods provide O(1) numpy-array access to all beat and measure
    coordinates, avoiding iteration. Critical for audio beatgrid use cases.
    """

    def test_n_beats(self):
        """Test n_beats property."""
        grid = BeatGrid(length=Fraction(32, 1), beats_per_measure=4)
        # 32 quarters / 1 quarter per beat = 32 beats
        assert grid.n_beats == 32

    def test_n_beats_with_eighth_note_beats(self):
        """Test n_beats with non-quarter beat unit (6/8 time)."""
        grid = BeatGrid(
            length=Fraction(12, 1),  # 12 quarters
            beats_per_measure=6,
            beat_unit=Fraction(1, 8),  # Eighth note beats
        )
        # 1 eighth = 0.5 quarters, so 12 quarters / 0.5 = 24 beats
        assert grid.n_beats == 24

    def test_beat_quarters(self):
        """Test beat_quarters returns correct numpy array."""
        grid = BeatGrid(length=Fraction(8, 1), beats_per_measure=4)

        quarters = grid.beat_quarters()

        assert isinstance(quarters, np.ndarray)
        assert quarters.dtype == np.float64
        assert len(quarters) == 8
        np.testing.assert_array_equal(quarters, [0, 1, 2, 3, 4, 5, 6, 7])

    def test_measure_quarters(self):
        """Test measure_quarters returns correct numpy array."""
        grid = BeatGrid(length=Fraction(16, 1), beats_per_measure=4)

        quarters = grid.measure_quarters()

        assert isinstance(quarters, np.ndarray)
        assert quarters.dtype == np.float64
        assert len(quarters) == 4
        np.testing.assert_array_equal(quarters, [0, 4, 8, 12])

    def test_beat_seconds_requires_tempo(self):
        """beat_seconds raises RuntimeError without tempo info."""
        grid = BeatGrid(length=Fraction(16, 1), beats_per_measure=4)

        with pytest.raises(RuntimeError, match="requires tempo"):
            grid.beat_seconds()

    def test_beat_seconds_with_tempo(self):
        """Test beat_seconds with tempo information."""
        # At 120 BPM: 0.5 seconds per quarter
        grid = BeatGrid.from_tempo(
            tempo_bpm=120.0,
            beats_per_measure=4,
            length_quarters=Fraction(8, 1),
            start_seconds=0.0,
        )

        seconds = grid.beat_seconds()

        assert isinstance(seconds, np.ndarray)
        assert len(seconds) == 8
        # Expected: 0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5
        np.testing.assert_array_equal(seconds, [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5])

    def test_beat_seconds_with_offset(self):
        """Test beat_seconds respects start_seconds offset."""
        # At 160 BPM: 0.375 seconds per quarter (60/160 = 0.375)
        grid = BeatGrid.from_tempo(
            tempo_bpm=160.0,
            beats_per_measure=4,
            length_quarters=Fraction(8, 1),
            start_seconds=0.092,  # First beat offset
        )

        seconds = grid.beat_seconds()

        # Expected: 0.092, 0.467, 0.842, 1.217, ...
        np.testing.assert_array_equal(
            np.round(seconds[:4], 3), [0.092, 0.467, 0.842, 1.217]
        )

    def test_measure_seconds_requires_tempo(self):
        """measure_seconds raises RuntimeError without tempo info."""
        grid = BeatGrid(length=Fraction(16, 1), beats_per_measure=4)

        with pytest.raises(RuntimeError, match="requires tempo"):
            grid.measure_seconds()

    def test_measure_seconds_with_tempo(self):
        """Test measure_seconds with tempo information."""
        # At 120 BPM with 4/4: 2.0 seconds per measure
        grid = BeatGrid.from_tempo(
            tempo_bpm=120.0,
            beats_per_measure=4,
            length_quarters=Fraction(16, 1),
            start_seconds=0.0,
        )

        seconds = grid.measure_seconds()

        assert isinstance(seconds, np.ndarray)
        assert len(seconds) == 4
        np.testing.assert_array_equal(seconds, [0.0, 2.0, 4.0, 6.0])

    def test_measure_seconds_with_offset(self):
        """Test measure_seconds respects start_seconds offset."""
        # At 160 BPM with 4/4: 1.5 seconds per measure (60/160 * 4 = 1.5)
        grid = BeatGrid.from_tempo(
            tempo_bpm=160.0,
            beats_per_measure=4,
            length_quarters=Fraction(16, 1),
            start_seconds=0.092,
        )

        seconds = grid.measure_seconds()

        # Expected: 0.092, 1.592, 3.092, 4.592
        np.testing.assert_array_equal(seconds, [0.092, 1.592, 3.092, 4.592])

    def test_downbeat_seconds_alias(self):
        """downbeat_seconds is an alias for measure_seconds."""
        grid = BeatGrid.from_tempo(
            tempo_bpm=120.0,
            beats_per_measure=4,
            length_quarters=Fraction(8, 1),
            start_seconds=0.5,
        )

        np.testing.assert_array_equal(grid.downbeat_seconds(), grid.measure_seconds())

    def test_measure_at_seconds(self):
        """Test point query: measure number at a given time."""
        # At 160 BPM with 4/4: 1.5 seconds per measure
        grid = BeatGrid.from_tempo(
            tempo_bpm=160.0,
            beats_per_measure=4,
            length_seconds=279.336,
            start_seconds=0.092,
        )

        # t=0.092 is start of measure 1
        assert grid.measure_at_seconds(0.092) == 1
        # t=1.0 is within measure 1 (measure 1 ends at 1.592)
        assert grid.measure_at_seconds(1.0) == 1
        # t=1.592 is start of measure 2
        assert grid.measure_at_seconds(1.592) == 2
        # t=60.0: (60.0 - 0.092) / 1.5 = 39.9 -> measure 40
        assert grid.measure_at_seconds(60.0) == 40

    def test_measure_at_seconds_before_start(self):
        """measure_at_seconds raises ValueError if before first beat."""
        grid = BeatGrid.from_tempo(
            tempo_bpm=160.0,
            beats_per_measure=4,
            length_seconds=60.0,
            start_seconds=0.5,
        )

        with pytest.raises(ValueError, match="before first beat"):
            grid.measure_at_seconds(0.1)

    def test_beat_at_seconds(self):
        """Test point query: beat-in-measure at a given time."""
        # At 160 BPM: 0.375 seconds per beat
        grid = BeatGrid.from_tempo(
            tempo_bpm=160.0,
            beats_per_measure=4,
            length_seconds=60.0,
            start_seconds=0.0,
        )

        # t=0.0 is beat 1
        assert grid.beat_at_seconds(0.0) == 1
        # t=0.375 is beat 2
        assert grid.beat_at_seconds(0.375) == 2
        # t=0.75 is beat 3
        assert grid.beat_at_seconds(0.75) == 3
        # t=1.125 is beat 4
        assert grid.beat_at_seconds(1.125) == 4
        # t=1.5 is beat 1 of measure 2
        assert grid.beat_at_seconds(1.5) == 1

    def test_beat_at_seconds_before_start(self):
        """beat_at_seconds raises ValueError if before first beat."""
        grid = BeatGrid.from_tempo(
            tempo_bpm=160.0,
            beats_per_measure=4,
            length_seconds=60.0,
            start_seconds=0.5,
        )

        with pytest.raises(ValueError, match="before first beat"):
            grid.beat_at_seconds(0.1)


class TestBeatGridAudioUseCase:
    """Integration test: Audio beatgrid use case from tutorial.

    Validates the full workflow for adding metrical structure to audio files
    with known tempo and first-beat offset.
    """

    # Test data from tutorial: Hard techno tracks at 160 BPM, 4/4
    TRACKS = {
        "Ao Ceu": {"duration": 279.336, "first_beat": 0.092},
        "Bye Bye": {"duration": 274.5, "first_beat": 0.035},
        "Bass Kick": {"duration": 316.0, "first_beat": 0.061},
    }
    TEMPO_BPM = 160.0
    BEATS_PER_MEASURE = 4

    def test_ao_ceu_grid(self):
        """Full validation for 'Ao Ceu' track."""
        info = self.TRACKS["Ao Ceu"]
        grid = BeatGrid.from_tempo(
            tempo_bpm=self.TEMPO_BPM,
            beats_per_measure=self.BEATS_PER_MEASURE,
            length_seconds=info["duration"],
            start_seconds=info["first_beat"],
        )

        # Exact measure and beat counts
        assert grid.n_measures == 186
        assert grid.n_beats == 744

        # First 4 beats
        beats = grid.beat_seconds()[:4]
        np.testing.assert_array_equal(np.round(beats, 3), [0.092, 0.467, 0.842, 1.217])

        # First 4 measures
        measures = grid.measure_seconds()[:4]
        np.testing.assert_array_equal(
            np.round(measures, 3), [0.092, 1.592, 3.092, 4.592]
        )

    def test_bye_bye_grid(self):
        """Full validation for 'Bye Bye' track."""
        info = self.TRACKS["Bye Bye"]
        grid = BeatGrid.from_tempo(
            tempo_bpm=self.TEMPO_BPM,
            beats_per_measure=self.BEATS_PER_MEASURE,
            length_seconds=info["duration"],
            start_seconds=info["first_beat"],
        )

        assert grid.n_measures == 182
        assert grid.n_beats == 731

        # First 4 beats
        beats = grid.beat_seconds()[:4]
        np.testing.assert_array_equal(np.round(beats, 3), [0.035, 0.410, 0.785, 1.160])

    def test_bass_kick_grid(self):
        """Full validation for 'Bass Kick' track."""
        info = self.TRACKS["Bass Kick"]
        grid = BeatGrid.from_tempo(
            tempo_bpm=self.TEMPO_BPM,
            beats_per_measure=self.BEATS_PER_MEASURE,
            length_seconds=info["duration"],
            start_seconds=info["first_beat"],
        )

        assert grid.n_measures == 210
        assert grid.n_beats == 842

        # First 4 beats
        beats = grid.beat_seconds()[:4]
        np.testing.assert_array_equal(np.round(beats, 3), [0.061, 0.436, 0.811, 1.186])

    def test_beat_spacing_is_constant(self):
        """Verify constant beat spacing (sanity check for linearity)."""
        grid = BeatGrid.from_tempo(
            tempo_bpm=self.TEMPO_BPM,
            beats_per_measure=self.BEATS_PER_MEASURE,
            length_seconds=60.0,
            start_seconds=0.0,
        )

        beats = grid.beat_seconds()
        # All beat intervals should be exactly 0.375 seconds (60/160)
        intervals = np.diff(beats)
        expected_interval = 60.0 / self.TEMPO_BPM
        np.testing.assert_array_equal(
            intervals, np.full_like(intervals, expected_interval)
        )


class TestBeatGridSUPRAValidation:
    """Validate BeatGrid against SUPRA piano roll data.

    This is the critical validation test. The SUPRA data provides known
    reference values for Wagner's Meistersinger Prelude:

    - Total length: 888 quarter notes
    - Time signature: 4/4 throughout
    - Measures: 222 (numbered 1-222)
    - First beat at approximately 1.3 seconds in audio
    - Last measure ends approximately 2 seconds before audio end

    If BeatGrid correctly computes all measure numbers and beat positions
    for these known values, we can be confident it works correctly for
    any musical content.
    """

    # SUPRA reference values (from README.md)
    TOTAL_QUARTERS = 888
    TOTAL_MEASURES = 222
    QUARTERS_PER_MEASURE = 4
    BEATS_PER_MEASURE = 4

    def test_supra_basic_dimensions(self):
        """Verify basic grid dimensions match SUPRA data."""
        grid = BeatGrid(
            length=Fraction(self.TOTAL_QUARTERS, 1),
            beats_per_measure=self.BEATS_PER_MEASURE,
        )

        assert grid.length.value == Fraction(888, 1)
        assert grid.quarters_per_measure == Fraction(4, 1)
        assert grid.n_measures == self.TOTAL_MEASURES

    def test_supra_measure_boundaries(self):
        """Verify measure boundaries at key points.

        Note: With the new MetricMap implementation, out-of-bounds coordinates
        are clamped to the last measure (not extrapolated to a theoretical next measure).
        """
        grid = BeatGrid(
            length=Fraction(self.TOTAL_QUARTERS, 1),
            beats_per_measure=self.BEATS_PER_MEASURE,
        )

        # First measure: quarters 0-3
        assert grid.measure_at(0) == 1
        assert grid.measure_at(3) == 1

        # Second measure: quarters 4-7
        assert grid.measure_at(4) == 2

        # Last measure (222): quarters 884-887
        assert grid.measure_at(884) == 222
        assert grid.measure_at(887) == 222

        # Quarter 888 is beyond the grid; MetricMap clamps to last measure
        # (the old FloorMap would extrapolate to 223, but MetricMap is table-based)
        assert grid.measure_at(888) == 222

    def test_supra_all_measure_starts(self):
        """Verify all 222 measure start positions."""
        grid = BeatGrid(
            length=Fraction(self.TOTAL_QUARTERS, 1),
            beats_per_measure=self.BEATS_PER_MEASURE,
        )

        # Generate all measure start quarters
        measure_starts = np.arange(0, self.TOTAL_QUARTERS, self.QUARTERS_PER_MEASURE)

        # Should have exactly 222 measure starts
        assert len(measure_starts) == self.TOTAL_MEASURES

        # Verify each measure start maps to correct measure number
        for i, quarter in enumerate(measure_starts):
            expected_measure = i + 1  # 1-indexed
            actual_measure = grid.measure_at(quarter)
            assert actual_measure == expected_measure, (
                f"Quarter {quarter} should be measure {expected_measure}, "
                f"got {actual_measure}"
            )

    def test_supra_beat_positions(self):
        """Verify beat positions within measures.

        Note: beat_at now returns Fraction, not float.
        """
        grid = BeatGrid(
            length=Fraction(self.TOTAL_QUARTERS, 1),
            beats_per_measure=self.BEATS_PER_MEASURE,
        )

        # Check beat positions for first few measures
        for measure in range(1, 6):  # Measures 1-5
            base_quarter = (measure - 1) * self.QUARTERS_PER_MEASURE

            for beat in range(1, 5):  # Beats 1-4
                quarter = base_quarter + (beat - 1)
                actual_beat = grid.beat_at(quarter)
                assert actual_beat == Fraction(beat, 1), (
                    f"Quarter {quarter} (measure {measure}) should be beat {beat}, "
                    f"got {actual_beat}"
                )

    def test_supra_reverse_lookup(self):
        """Verify reverse lookup (measure, beat) -> quarter."""
        grid = BeatGrid(
            length=Fraction(self.TOTAL_QUARTERS, 1),
            beats_per_measure=self.BEATS_PER_MEASURE,
        )

        # Check key positions
        assert grid.quarter_at(1, 1) == Fraction(0, 1)
        assert grid.quarter_at(1, 4) == Fraction(3, 1)
        assert grid.quarter_at(2, 1) == Fraction(4, 1)
        assert grid.quarter_at(222, 1) == Fraction(884, 1)
        assert grid.quarter_at(222, 4) == Fraction(887, 1)

    def test_supra_round_trip(self):
        """Verify round-trip: quarter -> (measure, beat) -> quarter."""
        grid = BeatGrid(
            length=Fraction(self.TOTAL_QUARTERS, 1),
            beats_per_measure=self.BEATS_PER_MEASURE,
        )

        # Test all integer quarters
        for quarter in range(self.TOTAL_QUARTERS):
            measure = grid.measure_at(quarter)
            beat = grid.beat_at(quarter)

            # Round trip back to quarter
            recovered_quarter = grid.quarter_at(measure, beat)

            assert recovered_quarter == Fraction(quarter, 1), (
                f"Round trip failed: {quarter} -> ({measure}, {beat}) -> "
                f"{recovered_quarter}"
            )

    def test_supra_tempo_derivation(self):
        """Derive and verify tempo from SUPRA known values.

        Given:
        - 888 quarters total
        - First beat at 1.3 seconds
        - Last measure ends at (audio_length - 2 seconds)
        - If audio is ~X seconds, then musical content is X - 1.3 - 2 seconds

        From the SUPRA README, we don't have the exact audio length, but we
        can test the tempo calculation mechanism.

        For testing purposes, let's assume:
        - First beat: 1.3 seconds
        - Assume audio duration such that 888 quarters fit in known duration
        """
        # This test verifies the mechanism works with known input/output
        ASSUMED_MUSICAL_DURATION = 592.0  # seconds for musical content

        # Calculate tempo
        # quarters_per_second = 888 / 592 = 1.5
        # beats_per_second = 1.5 (since quarter = beat in 4/4)
        # BPM = beats_per_second * 60 = 90
        quarters_per_second = self.TOTAL_QUARTERS / ASSUMED_MUSICAL_DURATION
        assumed_bpm = quarters_per_second * 60.0

        # Create grid from this tempo
        grid = BeatGrid.from_tempo(
            tempo_bpm=assumed_bpm,
            beats_per_measure=self.BEATS_PER_MEASURE,
            length_seconds=ASSUMED_MUSICAL_DURATION,
        )

        # Verify dimensions
        assert grid.length.value == Fraction(self.TOTAL_QUARTERS, 1)
        assert grid.n_measures == self.TOTAL_MEASURES

        # Verify tempo map converts correctly
        # At 90 BPM: 1.5 quarters/second, so 1 quarter = 0.667 seconds
        seconds_per_quarter = 60.0 / assumed_bpm
        computed_seconds = grid._tempo_map(1.0)
        assert computed_seconds == seconds_per_quarter

    def test_supra_array_operations(self):
        """Test vectorized operations on SUPRA-sized data.

        Note: Uses the new _meter_map (MetricMap) instead of _measure_map.
        The MetricMap supports vectorized operations via its internal arrays.
        """
        grid = BeatGrid(
            length=Fraction(self.TOTAL_QUARTERS, 1),
            beats_per_measure=self.BEATS_PER_MEASURE,
        )

        # Create array of all quarters
        all_quarters = np.arange(self.TOTAL_QUARTERS, dtype=np.float64)

        # Vectorized measure lookup using meter_map
        measures = grid._meter_map(all_quarters)
        assert len(measures) == self.TOTAL_QUARTERS
        assert measures[0] == 1
        assert measures[self.TOTAL_QUARTERS - 1] == self.TOTAL_MEASURES

        # Vectorized beat lookup using beat_map
        beats = grid._beat_map(all_quarters)
        assert len(beats) == self.TOTAL_QUARTERS
        assert beats[0] == 1.0

        # Verify pattern: beats should be 1,2,3,4,1,2,3,4,...
        expected_beat_pattern = np.tile([1.0, 2.0, 3.0, 4.0], self.TOTAL_MEASURES)
        np.testing.assert_array_equal(beats, expected_beat_pattern)

    def test_supra_metrical_position_array(self):
        """Test combined metrical position lookup on array.

        Note: The _metrical_map now returns 'mc' instead of 'measure'.
        """
        grid = BeatGrid(
            length=Fraction(self.TOTAL_QUARTERS, 1),
            beats_per_measure=self.BEATS_PER_MEASURE,
        )

        # Sample quarters
        test_quarters = np.array([0, 1, 4, 100, 500, 884, 887], dtype=np.float64)

        result = grid._metrical_map(test_quarters)

        expected_measures = np.array([1, 1, 2, 26, 126, 222, 222])
        expected_beats = np.array([1.0, 2.0, 1.0, 1.0, 1.0, 1.0, 4.0])

        np.testing.assert_array_equal(result["mc"], expected_measures)
        np.testing.assert_array_equal(result["beat"], expected_beats)

    def test_supra_event_materialization(self):
        """Test beat/measure materialization for SUPRA dimensions."""
        grid = BeatGrid(
            length=Fraction(self.TOTAL_QUARTERS, 1),
            beats_per_measure=self.BEATS_PER_MEASURE,
        )

        # Materialize all beats
        n_beats = grid.materialize_beats()

        # 888 quarters in 4/4 = 888 beats
        assert n_beats == self.TOTAL_QUARTERS

        # Materialize measures (on fresh grid to avoid duplication)
        grid2 = BeatGrid(
            length=Fraction(self.TOTAL_QUARTERS, 1),
            beats_per_measure=self.BEATS_PER_MEASURE,
        )
        n_measures = grid2.materialize_measures()

        # Should have exactly 222 measures
        assert n_measures == self.TOTAL_MEASURES

        # Verify measure events
        measure_events = grid2.get_events(event_type="Measure")
        assert len(measure_events) == self.TOTAL_MEASURES
