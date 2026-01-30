"""Tests for BeatGrid (metrical timeline).

This module comprehensively tests BeatGrid functionality, including validation
against real-world SUPRA data (Wagner Meistersinger Prelude, 222 measures).

The SUPRA test validates that BeatGrid correctly computes measure numbers and
beat positions for a known musical work, proving the mechanism works correctly.
"""

from fractions import Fraction

import numpy as np
import pytest

from timetoalign.core import TimeUnit
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
    """Test the built-in metrical C-Maps."""

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

        # Measure 26: quarters 100-103.99
        assert grid.measure_at(100) == 26

    def test_beat_at_4_4(self):
        """Test beat position lookup in 4/4."""
        grid = BeatGrid(length=Fraction(100, 1), beats_per_measure=4)

        # Beat 1 at measure starts
        assert grid.beat_at(0) == 1.0
        assert grid.beat_at(4) == 1.0
        assert grid.beat_at(100) == 1.0

        # Other beats
        assert grid.beat_at(1) == 2.0
        assert grid.beat_at(2) == 3.0
        assert grid.beat_at(3) == 4.0

        # Fractional beats
        assert grid.beat_at(0.5) == 1.5
        assert grid.beat_at(4.25) == 1.25

    def test_metrical_position(self):
        """Test combined measure/beat lookup."""
        grid = BeatGrid(length=Fraction(100, 1), beats_per_measure=4)

        result = grid.metrical_position(0)
        assert result["measure"] == 1
        assert result["beat"] == 1.0

        result = grid.metrical_position(7.5)
        assert result["measure"] == 2
        assert result["beat"] == 4.5

        result = grid.metrical_position(100)
        assert result["measure"] == 26
        assert result["beat"] == 1.0

    def test_quarter_at(self):
        """Test reverse lookup: measure/beat -> quarter."""
        grid = BeatGrid(length=Fraction(100, 1), beats_per_measure=4)

        # Measure 1, beat 1 -> quarter 0
        assert grid.quarter_at(1, 1) == Fraction(0, 1)

        # Measure 1, beat 2 -> quarter 1
        assert grid.quarter_at(1, 2) == Fraction(1, 1)

        # Measure 2, beat 1 -> quarter 4
        assert grid.quarter_at(2, 1) == Fraction(4, 1)

        # Measure 26, beat 1 -> quarter 100
        assert grid.quarter_at(26, 1) == Fraction(100, 1)

        # Fractional beat
        assert grid.quarter_at(1, 1.5) == Fraction(1, 2)

    def test_quarter_at_validation(self):
        """Test validation in quarter_at."""
        grid = BeatGrid(length=Fraction(100, 1), beats_per_measure=4)

        with pytest.raises(ValueError, match="before start_measure"):
            grid.quarter_at(0, 1)

        with pytest.raises(ValueError, match="Beat must be"):
            grid.quarter_at(1, 0)


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
        """Test handling of partial final measure."""
        grid = BeatGrid(length=Fraction(10, 1), beats_per_measure=4)

        n_measures = grid.materialize_measures()

        # 2 complete measures (8 quarters) + 1 partial (2 quarters)
        assert n_measures == 3


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

        # Should be approximately 120 quarters
        assert abs(float(grid.length.value) - 120.0) < 0.1

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
        assert abs(seconds - 0.5) < 0.001

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
        assert tempo_map(0) == pytest.approx(0.0)
        # quarter 1 -> 0.5 seconds
        assert tempo_map(1) == pytest.approx(0.5)
        # quarter 4 (one measure) -> 2.0 seconds
        assert tempo_map(4) == pytest.approx(2.0)

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
        """Verify measure boundaries at key points."""
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

        # Verify quarter 888 would be measure 223 (beyond piece)
        assert grid.measure_at(888) == 223

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
        """Verify beat positions within measures."""
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
                assert abs(actual_beat - beat) < 0.001, (
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
        # FIRST_BEAT_SECONDS = 1.3
        # RESONANCE_TAIL_SECONDS = 2.0

        # Hypothetical audio length (we'd get this from the actual audio file)
        # For testing, let's work backwards from a reasonable tempo
        # At ~60 BPM (quarter = 1 second), 888 quarters = 888 seconds
        # At ~90 BPM, 888 quarters = 592 seconds
        # Let's assume ~592 seconds of musical content

        # This test verifies the mechanism works with known input/output
        ASSUMED_MUSICAL_DURATION = 592.0  # seconds for musical content
        # ASSUMED_TOTAL_DURATION = (
        #     FIRST_BEAT_SECONDS + ASSUMED_MUSICAL_DURATION + RESONANCE_TAIL_SECONDS
        # )

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
        assert abs(float(grid.length.value) - self.TOTAL_QUARTERS) < 1.0
        assert grid.n_measures == self.TOTAL_MEASURES

        # Verify tempo map converts correctly
        # At 90 BPM: 1.5 quarters/second, so 1 quarter = 0.667 seconds
        seconds_per_quarter = 60.0 / assumed_bpm
        computed_seconds = grid._tempo_map(1.0)
        assert abs(computed_seconds - seconds_per_quarter) < 0.001

    def test_supra_array_operations(self):
        """Test vectorized operations on SUPRA-sized data."""
        grid = BeatGrid(
            length=Fraction(self.TOTAL_QUARTERS, 1),
            beats_per_measure=self.BEATS_PER_MEASURE,
        )

        # Create array of all quarters
        all_quarters = np.arange(self.TOTAL_QUARTERS, dtype=np.float64)

        # Vectorized measure lookup
        measures = grid._measure_map(all_quarters)
        assert len(measures) == self.TOTAL_QUARTERS
        assert measures[0] == 1
        assert measures[self.TOTAL_QUARTERS - 1] == self.TOTAL_MEASURES

        # Vectorized beat lookup
        beats = grid._beat_map(all_quarters)
        assert len(beats) == self.TOTAL_QUARTERS
        assert beats[0] == 1.0

        # Verify pattern: beats should be 1,2,3,4,1,2,3,4,...
        expected_beat_pattern = np.tile([1.0, 2.0, 3.0, 4.0], self.TOTAL_MEASURES)
        np.testing.assert_array_almost_equal(beats, expected_beat_pattern)

    def test_supra_metrical_position_array(self):
        """Test combined metrical position lookup on array."""
        grid = BeatGrid(
            length=Fraction(self.TOTAL_QUARTERS, 1),
            beats_per_measure=self.BEATS_PER_MEASURE,
        )

        # Sample quarters
        test_quarters = np.array([0, 1, 4, 100, 500, 884, 887], dtype=np.float64)

        result = grid._metrical_map(test_quarters)

        expected_measures = np.array([1, 1, 2, 26, 126, 222, 222])
        expected_beats = np.array([1.0, 2.0, 1.0, 1.0, 1.0, 1.0, 4.0])

        np.testing.assert_array_equal(result["measure"], expected_measures)
        np.testing.assert_array_almost_equal(result["beat"], expected_beats)

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
