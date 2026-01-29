"""Tests for InterpolationMap.

InterpolationMap is the core bidirectional coordinate conversion engine
for the unified timestamp architecture.
"""

from __future__ import annotations

import numpy as np
import pytest

from timetoalign.core import TimeUnit
from timetoalign.maps import InterpolationMap


class TestInterpolationMapBasics:
    """Basic functionality tests."""

    def test_create_simple(self):
        """Create a simple interpolation map."""
        imap = InterpolationMap(
            source_coords=np.array([0.0, 100.0]),
            target_coords=np.array([10.0, 110.0]),
            source_id="child:1",
            target_id="parent:1",
        )
        assert imap.source_id == "child:1"
        assert imap.target_id == "parent:1"
        assert imap.n_anchors == 2

    def test_forward_conversion(self):
        """Forward conversion adds offset."""
        imap = InterpolationMap(
            source_coords=np.array([0.0, 100.0]),
            target_coords=np.array([10.0, 110.0]),
            source_id="child",
            target_id="parent",
        )
        # child 0 -> parent 10
        assert imap.forward(0.0) == 10.0
        # child 50 -> parent 60
        assert imap.forward(50.0) == 60.0
        # child 100 -> parent 110
        assert imap.forward(100.0) == 110.0

    def test_inverse_conversion(self):
        """Inverse conversion subtracts offset."""
        imap = InterpolationMap(
            source_coords=np.array([0.0, 100.0]),
            target_coords=np.array([10.0, 110.0]),
            source_id="child",
            target_id="parent",
        )
        # parent 10 -> child 0
        assert imap.inverse(10.0) == 0.0
        # parent 60 -> child 50
        assert imap.inverse(60.0) == 50.0
        # parent 110 -> child 100
        assert imap.inverse(110.0) == 100.0

    def test_forward_array(self):
        """Forward conversion with array input."""
        imap = InterpolationMap(
            source_coords=np.array([0.0, 100.0]),
            target_coords=np.array([0.0, 200.0]),  # 2x scaling
            source_id="source",
            target_id="target",
        )
        values = np.array([0.0, 25.0, 50.0, 100.0])
        result = imap.forward(values)
        expected = np.array([0.0, 50.0, 100.0, 200.0])
        np.testing.assert_array_almost_equal(result, expected)

    def test_inverse_array(self):
        """Inverse conversion with array input."""
        imap = InterpolationMap(
            source_coords=np.array([0.0, 100.0]),
            target_coords=np.array([0.0, 200.0]),
            source_id="source",
            target_id="target",
        )
        values = np.array([0.0, 50.0, 100.0, 200.0])
        result = imap.inverse(values)
        expected = np.array([0.0, 25.0, 50.0, 100.0])
        np.testing.assert_array_almost_equal(result, expected)


class TestInterpolationMapWithUnits:
    """Tests with TimeUnit annotations."""

    def test_units_stored(self):
        """TimeUnits are stored correctly."""
        imap = InterpolationMap(
            source_coords=np.array([0.0, 480.0]),
            target_coords=np.array([0.0, 1.0]),
            source_id="ticks",
            target_id="seconds",
            source_unit=TimeUnit.ticks,
            target_unit=TimeUnit.seconds,
        )
        assert imap.source_unit == TimeUnit.ticks
        assert imap.target_unit == TimeUnit.seconds


class TestInterpolationMapTempoConversion:
    """Tests for tempo-based conversion (non-linear mapping)."""

    def test_tempo_change(self):
        """Conversion with tempo change in the middle."""
        # 0-480 ticks at 120 BPM = 0.5 sec
        # 480-960 ticks at 60 BPM = 1.0 sec (total = 1.5 sec at tick 960)
        imap = InterpolationMap(
            source_coords=np.array([0.0, 480.0, 960.0]),
            target_coords=np.array([0.0, 0.5, 1.5]),
            source_id="ticks",
            target_id="seconds",
        )

        # Check anchor points
        assert imap.forward(0.0) == 0.0
        assert imap.forward(480.0) == 0.5
        assert imap.forward(960.0) == 1.5

        # Check interpolation within first segment (faster tempo)
        assert imap.forward(240.0) == pytest.approx(0.25)

        # Check interpolation within second segment (slower tempo)
        assert imap.forward(720.0) == pytest.approx(1.0)

    def test_tempo_inverse(self):
        """Inverse conversion with tempo changes."""
        imap = InterpolationMap(
            source_coords=np.array([0.0, 480.0, 960.0]),
            target_coords=np.array([0.0, 0.5, 1.5]),
            source_id="ticks",
            target_id="seconds",
        )

        # Check inverse at anchor points
        assert imap.inverse(0.0) == 0.0
        assert imap.inverse(0.5) == 480.0
        assert imap.inverse(1.5) == 960.0

        # Check interpolation
        assert imap.inverse(0.25) == pytest.approx(240.0)
        assert imap.inverse(1.0) == pytest.approx(720.0)


class TestInterpolationMapExtrapolation:
    """Tests for extrapolation beyond anchor points."""

    def test_forward_extrapolation(self):
        """Forward extrapolation extends linearly."""
        imap = InterpolationMap(
            source_coords=np.array([0.0, 100.0]),
            target_coords=np.array([0.0, 200.0]),  # 2x scaling
            source_id="source",
            target_id="target",
        )
        # Beyond max: extrapolate
        assert imap.forward(150.0) == pytest.approx(300.0)
        # Below min: extrapolate
        assert imap.forward(-50.0) == pytest.approx(-100.0)

    def test_inverse_extrapolation(self):
        """Inverse extrapolation extends linearly."""
        imap = InterpolationMap(
            source_coords=np.array([0.0, 100.0]),
            target_coords=np.array([0.0, 200.0]),
            source_id="source",
            target_id="target",
        )
        # Beyond max: extrapolate
        assert imap.inverse(300.0) == pytest.approx(150.0)
        # Below min: extrapolate
        assert imap.inverse(-100.0) == pytest.approx(-50.0)


class TestInterpolationMapValidation:
    """Tests for validation and error handling."""

    def test_requires_two_points(self):
        """Must have at least 2 anchor points."""
        with pytest.raises(ValueError, match="at least 2 anchor"):
            InterpolationMap(
                source_coords=np.array([0.0]),
                target_coords=np.array([0.0]),
                source_id="a",
                target_id="b",
            )

    def test_length_mismatch(self):
        """Source and target must have same length."""
        with pytest.raises(ValueError, match="same length"):
            InterpolationMap(
                source_coords=np.array([0.0, 100.0]),
                target_coords=np.array([0.0, 50.0, 100.0]),
                source_id="a",
                target_id="b",
            )

    def test_source_must_be_increasing(self):
        """Source coords must be strictly monotonically increasing."""
        with pytest.raises(ValueError, match="monotonically increasing"):
            InterpolationMap(
                source_coords=np.array([0.0, 50.0, 30.0]),
                target_coords=np.array([0.0, 100.0, 60.0]),
                source_id="a",
                target_id="b",
            )

    def test_non_invertible_target(self):
        """Non-monotonic target prevents inversion."""
        imap = InterpolationMap(
            source_coords=np.array([0.0, 50.0, 100.0]),
            target_coords=np.array([0.0, 100.0, 50.0]),  # Not monotonic
            source_id="a",
            target_id="b",
        )
        assert not imap.is_invertible
        with pytest.raises(ValueError, match="not strictly monotonic"):
            imap.inverse(50.0)


class TestInterpolationMapDecreasingTarget:
    """Tests for maps with decreasing target values."""

    def test_decreasing_target_forward(self):
        """Forward works with decreasing target."""
        imap = InterpolationMap(
            source_coords=np.array([0.0, 100.0]),
            target_coords=np.array([100.0, 0.0]),  # Decreasing
            source_id="source",
            target_id="target",
        )
        assert imap.is_invertible
        assert imap.forward(0.0) == 100.0
        assert imap.forward(100.0) == 0.0
        assert imap.forward(50.0) == pytest.approx(50.0)

    def test_decreasing_target_inverse(self):
        """Inverse works with decreasing target."""
        imap = InterpolationMap(
            source_coords=np.array([0.0, 100.0]),
            target_coords=np.array([100.0, 0.0]),
            source_id="source",
            target_id="target",
        )
        # Note: inverse reverses the arrays internally
        assert imap.inverse(100.0) == pytest.approx(0.0)
        assert imap.inverse(0.0) == pytest.approx(100.0)
        assert imap.inverse(50.0) == pytest.approx(50.0)


class TestInterpolationMapFactories:
    """Tests for factory methods."""

    def test_identity(self):
        """Identity map: output equals input."""
        imap = InterpolationMap.identity(0.0, 100.0, "test")
        assert imap.forward(50.0) == 50.0
        assert imap.inverse(50.0) == 50.0

    def test_from_table_map(self):
        """Create from TableMap."""
        from timetoalign.maps import TableMap

        tmap = TableMap(
            x_values=[0, 480, 960],
            y_values=[0.0, 0.5, 1.5],
            source_unit=TimeUnit.ticks,
            target_unit=TimeUnit.seconds,
        )
        imap = InterpolationMap.from_table_map(tmap)

        # Should have same anchor points
        assert imap.n_anchors == 3
        assert imap.source_unit == TimeUnit.ticks
        assert imap.target_unit == TimeUnit.seconds

        # Should produce same results
        assert imap.forward(240.0) == pytest.approx(tmap(240))
        assert imap.forward(720.0) == pytest.approx(tmap(720))


class TestInterpolationMapProperties:
    """Tests for property accessors."""

    def test_min_max(self):
        """Min/max properties work correctly."""
        imap = InterpolationMap(
            source_coords=np.array([10.0, 50.0, 100.0]),
            target_coords=np.array([0.0, 25.0, 50.0]),
            source_id="a",
            target_id="b",
        )
        assert imap.source_min == 10.0
        assert imap.source_max == 100.0
        assert imap.target_min == 0.0
        assert imap.target_max == 50.0

    def test_repr(self):
        """Repr shows useful info."""
        imap = InterpolationMap(
            source_coords=np.array([0.0, 100.0]),
            target_coords=np.array([0.0, 200.0]),
            source_id="child:1",
            target_id="parent:1",
        )
        r = repr(imap)
        assert "child:1" in r
        assert "parent:1" in r
        assert "2" in r  # n_anchors
