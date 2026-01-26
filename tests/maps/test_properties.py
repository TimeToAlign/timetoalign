"""Property-based tests for ConversionMaps using Hypothesis.

These tests verify mathematical invariants that must hold for all valid inputs:
- Invertibility: inverse(forward(x)) == x
- Composition: (f >> g)(x) == g(f(x))
- Identity: identity(x) == x

Per AGENTS.md Section 3.5: Use hypothesis for mathematical conversions.
"""

from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from timetoalign.maps.composite import ChainMap
from timetoalign.maps.convenience import (
    QuartersToTicks,
    SamplesToSeconds,
    SecondsToSamples,
    TicksToQuarters,
)
from timetoalign.maps.linear import LinearMap, ScalarMap, ShiftMap
from timetoalign.maps.table import TableMap

# region Strategies


# Finite floats (no NaN, no infinity)
finite_floats = st.floats(
    min_value=-1e10,
    max_value=1e10,
    allow_nan=False,
    allow_infinity=False,
)

# Positive floats for scalars (must be non-zero for invertibility)
positive_scalars = st.floats(
    min_value=1e-6,
    max_value=1e6,
    allow_nan=False,
    allow_infinity=False,
)

# Non-zero scalars (positive or negative)
nonzero_scalars = st.one_of(
    st.floats(min_value=1e-6, max_value=1e6, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-1e6, max_value=-1e-6, allow_nan=False, allow_infinity=False),
)

# PPQ values (typical MIDI ticks per quarter)
ppq_values = st.sampled_from([96, 120, 240, 480, 960, 1920])

# Sample rates
sample_rates = st.sampled_from([22050, 44100, 48000, 96000])

# endregion


# region LinearMap Properties


class TestLinearMapProperties:
    """Property-based tests for LinearMap."""

    @given(scalar=nonzero_scalars, offset=finite_floats, x=finite_floats)
    @settings(max_examples=200)
    def test_inverse_roundtrip(self, scalar: float, offset: float, x: float):
        """inverse(forward(x)) == x for all valid x.

        This is the fundamental invertibility property.
        """
        m = LinearMap(scalar=scalar, offset=offset)
        inv = m.inverse()

        forward = m(x)
        back = inv(forward)

        # Use relative tolerance for large values
        assert back == pytest.approx(x, rel=1e-9, abs=1e-9)

    @given(scalar=nonzero_scalars, offset=finite_floats, x=finite_floats)
    @settings(max_examples=200)
    def test_forward_inverse_roundtrip(self, scalar: float, offset: float, x: float):
        """forward(inverse(x)) == x for all valid x.

        Tests the other direction of invertibility.
        """
        m = LinearMap(scalar=scalar, offset=offset)
        inv = m.inverse()

        back = inv(x)
        forward = m(back)

        assert forward == pytest.approx(x, rel=1e-9, abs=1e-9)

    @given(
        s1=nonzero_scalars,
        o1=finite_floats,
        s2=nonzero_scalars,
        o2=finite_floats,
        x=finite_floats,
    )
    @settings(max_examples=200)
    def test_composition_associativity(
        self, s1: float, o1: float, s2: float, o2: float, x: float
    ):
        """(f >> g)(x) == g(f(x)).

        Composition via >> operator matches sequential application.
        """
        m1 = LinearMap(scalar=s1, offset=o1)
        m2 = LinearMap(scalar=s2, offset=o2)

        chain = m1 >> m2
        sequential = m2(m1(x))

        assert chain(x) == pytest.approx(sequential, rel=1e-9, abs=1e-9)

    @given(x=finite_floats)
    def test_identity_map(self, x: float):
        """Identity map returns input unchanged."""
        m = LinearMap(scalar=1.0, offset=0.0)
        assert m.is_identity
        assert m(x) == x


# endregion


# region ScalarMap Properties


class TestScalarMapProperties:
    """Property-based tests for ScalarMap."""

    @given(scalar=positive_scalars, x=finite_floats)
    @settings(max_examples=200)
    def test_inverse_roundtrip(self, scalar: float, x: float):
        """inverse(forward(x)) == x."""
        m = ScalarMap(scalar=scalar)
        inv = m.inverse()

        assert inv(m(x)) == pytest.approx(x, rel=1e-9, abs=1e-9)

    @given(scalar=positive_scalars, x=finite_floats)
    def test_scaling_property(self, scalar: float, x: float):
        """ScalarMap(a)(x) == a * x."""
        m = ScalarMap(scalar=scalar)
        assert m(x) == pytest.approx(scalar * x, rel=1e-9, abs=1e-9)


# endregion


# region ShiftMap Properties


class TestShiftMapProperties:
    """Property-based tests for ShiftMap."""

    @given(offset=finite_floats, x=finite_floats)
    @settings(max_examples=200)
    def test_inverse_roundtrip(self, offset: float, x: float):
        """inverse(forward(x)) == x."""
        m = ShiftMap(offset=offset)
        inv = m.inverse()

        assert inv(m(x)) == pytest.approx(x, rel=1e-9, abs=1e-9)

    @given(offset=finite_floats, x=finite_floats)
    def test_shift_property(self, offset: float, x: float):
        """ShiftMap(b)(x) == x + b."""
        m = ShiftMap(offset=offset)
        assert m(x) == pytest.approx(x + offset, rel=1e-9, abs=1e-9)

    @given(x=finite_floats)
    def test_zero_shift_is_identity(self, x: float):
        """ShiftMap(0) is identity."""
        m = ShiftMap(offset=0.0)
        assert m.is_identity
        assert m(x) == x


# endregion


# region Convenience Map Properties


class TestTicksToQuartersProperties:
    """Property-based tests for TicksToQuarters / QuartersToTicks."""

    @given(ppq=ppq_values, ticks=st.integers(min_value=0, max_value=10_000_000))
    def test_inverse_roundtrip_int(self, ppq: int, ticks: int):
        """Round-trip for integer tick values."""
        t2q = TicksToQuarters(ppq)
        q2t = QuartersToTicks(ppq)

        quarters = t2q(ticks)
        back = q2t(quarters)

        # Integer ticks should round-trip exactly
        assert back == pytest.approx(ticks, abs=1e-9)

    @given(ppq=ppq_values, quarters=st.floats(min_value=0, max_value=10000))
    def test_inverse_roundtrip_float(self, ppq: int, quarters: float):
        """Round-trip for float quarter values."""
        assume(not np.isnan(quarters) and not np.isinf(quarters))

        t2q = TicksToQuarters(ppq)
        q2t = QuartersToTicks(ppq)

        ticks = q2t(quarters)
        back = t2q(ticks)

        assert back == pytest.approx(quarters, rel=1e-9, abs=1e-9)

    @given(ppq=ppq_values)
    def test_one_quarter_equals_ppq_ticks(self, ppq: int):
        """1 quarter note == ppq ticks (by definition)."""
        t2q = TicksToQuarters(ppq)
        q2t = QuartersToTicks(ppq)

        assert t2q(ppq) == 1.0
        assert q2t(1.0) == ppq


class TestSamplesToSecondsProperties:
    """Property-based tests for SamplesToSeconds / SecondsToSamples."""

    @given(sr=sample_rates, samples=st.integers(min_value=0, max_value=100_000_000))
    def test_inverse_roundtrip_int(self, sr: int, samples: int):
        """Round-trip for integer sample values."""
        s2s = SamplesToSeconds(sr)
        s2samp = SecondsToSamples(sr)

        seconds = s2s(samples)
        back = s2samp(seconds)

        assert back == pytest.approx(samples, abs=1e-6)

    @given(sr=sample_rates, seconds=st.floats(min_value=0, max_value=3600))
    def test_inverse_roundtrip_float(self, sr: int, seconds: float):
        """Round-trip for float second values."""
        assume(not np.isnan(seconds) and not np.isinf(seconds))

        s2s = SamplesToSeconds(sr)
        s2samp = SecondsToSamples(sr)

        samples = s2samp(seconds)
        back = s2s(samples)

        assert back == pytest.approx(seconds, rel=1e-9, abs=1e-9)

    @given(sr=sample_rates)
    def test_one_second_equals_sample_rate(self, sr: int):
        """1 second == sample_rate samples (by definition)."""
        s2s = SamplesToSeconds(sr)
        s2samp = SecondsToSamples(sr)

        assert s2s(sr) == 1.0
        assert s2samp(1.0) == sr


# endregion


# region TableMap Properties


class TestTableMapProperties:
    """Property-based tests for TableMap."""

    @given(
        x_start=st.floats(min_value=0, max_value=100),
        x_step=st.floats(min_value=0.1, max_value=10),
        y_start=st.floats(min_value=0, max_value=100),
        y_step=st.floats(min_value=0.1, max_value=10),
    )
    @settings(max_examples=100)
    def test_inverse_roundtrip_monotonic(
        self, x_start: float, x_step: float, y_start: float, y_step: float
    ):
        """inverse(forward(x)) == x for monotonically increasing maps."""
        assume(not any(np.isnan([x_start, x_step, y_start, y_step])))
        assume(not any(np.isinf([x_start, x_step, y_start, y_step])))

        # Create strictly monotonic table
        x_values = [x_start, x_start + x_step, x_start + 2 * x_step]
        y_values = [y_start, y_start + y_step, y_start + 2 * y_step]

        m = TableMap(x_values=x_values, y_values=y_values)
        assert m.is_invertible

        inv = m.inverse()

        # Test at table points
        for x in x_values:
            y = m(x)
            back = inv(y)
            assert back == pytest.approx(x, rel=1e-9, abs=1e-9)

        # Test at midpoints
        for i in range(len(x_values) - 1):
            x_mid = (x_values[i] + x_values[i + 1]) / 2
            y = m(x_mid)
            back = inv(y)
            assert back == pytest.approx(x_mid, rel=1e-9, abs=1e-9)


class TestTableMapTempoProperties:
    """Property-based tests for TableMap.from_tempo_changes."""

    @given(
        tempo1=st.floats(min_value=20, max_value=300),
        tempo2=st.floats(min_value=20, max_value=300),
        ppq=ppq_values,
    )
    @settings(max_examples=100)
    def test_tempo_map_inverse_roundtrip(self, tempo1: float, tempo2: float, ppq: int):
        """Tempo maps are invertible for valid tick values."""
        assume(not np.isnan(tempo1) and not np.isnan(tempo2))

        m = TableMap.from_tempo_changes(
            tick_positions=[0, ppq * 4],  # Change at measure 2
            tempos_bpm=[tempo1, tempo2],
            ticks_per_quarter=ppq,
        )

        # Test at key points
        test_ticks = [0, ppq, ppq * 2, ppq * 4, ppq * 8]
        inv = m.inverse()

        for ticks in test_ticks:
            seconds = m(ticks)
            back = inv(seconds)
            assert back == pytest.approx(ticks, rel=1e-9, abs=1e-6)

    @given(tempo=st.floats(min_value=20, max_value=300), ppq=ppq_values)
    def test_constant_tempo_linear_relationship(self, tempo: float, ppq: int):
        """With constant tempo, ticks and seconds have linear relationship."""
        assume(not np.isnan(tempo))

        m = TableMap.from_tempo_changes(
            tick_positions=[0],
            tempos_bpm=[tempo],
            ticks_per_quarter=ppq,
        )

        # Seconds per tick = 60 / (tempo * ppq)
        sec_per_tick = 60.0 / (tempo * ppq)

        # Test linearity
        t1, t2 = 0, ppq * 4
        s1, s2 = m(t1), m(t2)

        expected_duration = (t2 - t1) * sec_per_tick
        assert (s2 - s1) == pytest.approx(expected_duration, rel=1e-9)


# endregion


# region ChainMap Properties


class TestChainMapProperties:
    """Property-based tests for ChainMap."""

    @given(
        s1=nonzero_scalars,
        o1=finite_floats,
        s2=nonzero_scalars,
        o2=finite_floats,
        x=finite_floats,
    )
    @settings(max_examples=200)
    def test_chain_inverse_roundtrip(
        self, s1: float, o1: float, s2: float, o2: float, x: float
    ):
        """ChainMap inverse works correctly."""
        m1 = LinearMap(scalar=s1, offset=o1)
        m2 = LinearMap(scalar=s2, offset=o2)

        chain = ChainMap([m1, m2])
        inv = chain.inverse()

        y = chain(x)
        back = inv(y)

        assert back == pytest.approx(x, rel=1e-9, abs=1e-9)

    @given(
        s1=nonzero_scalars,
        o1=finite_floats,
        s2=nonzero_scalars,
        o2=finite_floats,
        s3=nonzero_scalars,
        o3=finite_floats,
        x=finite_floats,
    )
    @settings(max_examples=100)
    def test_chain_associativity(
        self,
        s1: float,
        o1: float,
        s2: float,
        o2: float,
        s3: float,
        o3: float,
        x: float,
    ):
        """(f >> g) >> h == f >> (g >> h)."""
        m1 = LinearMap(scalar=s1, offset=o1)
        m2 = LinearMap(scalar=s2, offset=o2)
        m3 = LinearMap(scalar=s3, offset=o3)

        left = (m1 >> m2) >> m3
        right = m1 >> (m2 >> m3)

        assert left(x) == pytest.approx(right(x), rel=1e-9, abs=1e-9)


# endregion


# region Fraction Support Properties


class TestFractionProperties:
    """Property-based tests for Fraction support in maps."""

    @given(
        num=st.integers(min_value=1, max_value=100),
        den=st.integers(min_value=1, max_value=100),
        x_num=st.integers(min_value=-1000, max_value=1000),
        x_den=st.integers(min_value=1, max_value=100),
    )
    def test_linear_map_fraction_exact(
        self, num: int, den: int, x_num: int, x_den: int
    ):
        """LinearMap preserves Fraction exactness."""
        scalar = Fraction(num, den)
        offset = Fraction(1, den)
        x = Fraction(x_num, x_den)

        m = LinearMap(scalar=scalar, offset=offset)
        result = m(x)

        # Result should be exact Fraction
        expected = scalar * x + offset
        assert result == expected

    @given(
        ppq=ppq_values,
        beats_num=st.integers(min_value=0, max_value=100),
        beats_den=st.sampled_from([1, 2, 4, 8, 16]),
    )
    def test_ticks_to_quarters_fraction_exact(
        self, ppq: int, beats_num: int, beats_den: int
    ):
        """TicksToQuarters preserves exactness for integer tick inputs."""
        ticks = ppq * beats_num // beats_den * beats_den  # Ensure divisible

        t2q = TicksToQuarters(ppq)
        quarters = t2q(ticks)

        expected = Fraction(ticks, ppq)
        assert quarters == pytest.approx(float(expected), rel=1e-12)


# endregion
