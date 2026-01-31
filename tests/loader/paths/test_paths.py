"""Tests for Path API: LinearPath and PolylinePath."""

from __future__ import annotations

import pytest

from timetoalign.loader.paths import LinearPath, PolylinePath

# region LinearPath Tests


class TestLinearPath:
    """Tests for LinearPath."""

    def test_horizontal_path(self):
        """Test a horizontal line path."""
        path = LinearPath(
            start_coord=0.0,
            end_coord=100.0,
            start_point=(50, 100),
            end_point=(150, 100),
        )

        assert path.length == 100.0
        assert path.pixel_length == 100.0
        assert path.is_horizontal()
        assert not path.is_vertical()

    def test_vertical_path(self):
        """Test a vertical line path."""
        path = LinearPath(
            start_coord=0.0,
            end_coord=100.0,
            start_point=(100, 50),
            end_point=(100, 150),
        )

        assert path.length == 100.0
        assert path.pixel_length == 100.0
        assert not path.is_horizontal()
        assert path.is_vertical()

    def test_diagonal_path(self):
        """Test a diagonal (45 degree) path."""
        path = LinearPath(
            start_coord=0.0,
            end_coord=10.0,
            start_point=(0, 0),
            end_point=(300, 400),
        )

        assert path.length == 10.0
        assert path.pixel_length == 500.0  # 3-4-5 triangle * 100

    def test_coord_to_xy_start(self):
        """Test coordinate conversion at path start."""
        path = LinearPath(
            start_coord=0.0,
            end_coord=100.0,
            start_point=(50, 100),
            end_point=(150, 200),
        )

        x, y = path.coord_to_xy(0.0)
        assert x == 50.0
        assert y == 100.0

    def test_coord_to_xy_end(self):
        """Test coordinate conversion at path end."""
        path = LinearPath(
            start_coord=0.0,
            end_coord=100.0,
            start_point=(50, 100),
            end_point=(150, 200),
        )

        x, y = path.coord_to_xy(100.0)
        assert x == 150.0
        assert y == 200.0

    def test_coord_to_xy_midpoint(self):
        """Test coordinate conversion at midpoint."""
        path = LinearPath(
            start_coord=0.0,
            end_coord=100.0,
            start_point=(0, 0),
            end_point=(100, 100),
        )

        x, y = path.coord_to_xy(50.0)
        assert x == 50.0
        assert y == 50.0

    def test_xy_to_coord_on_path(self):
        """Test reverse mapping for point on path."""
        path = LinearPath(
            start_coord=0.0,
            end_coord=100.0,
            start_point=(0, 0),
            end_point=(100, 0),
        )

        coord = path.xy_to_coord(50.0, 0.0)
        assert coord is not None
        assert coord == pytest.approx(50.0)

    def test_xy_to_coord_off_path(self):
        """Test reverse mapping for point far from path."""
        path = LinearPath(
            start_coord=0.0,
            end_coord=100.0,
            start_point=(0, 0),
            end_point=(100, 0),
            tolerance=5.0,
        )

        coord = path.xy_to_coord(50.0, 100.0)  # Far from path
        assert coord is None

    def test_xy_to_coord_near_path(self):
        """Test reverse mapping for point near path (within tolerance)."""
        path = LinearPath(
            start_coord=0.0,
            end_coord=100.0,
            start_point=(0, 0),
            end_point=(100, 0),
            tolerance=10.0,
        )

        coord = path.xy_to_coord(50.0, 5.0)  # Within tolerance
        assert coord is not None
        assert coord == pytest.approx(50.0)

    def test_contains_coord(self):
        """Test coordinate containment check."""
        path = LinearPath(
            start_coord=10.0,
            end_coord=20.0,
            start_point=(0, 0),
            end_point=(100, 0),
        )

        assert path.contains_coord(10.0)
        assert path.contains_coord(15.0)
        assert path.contains_coord(20.0)
        assert not path.contains_coord(5.0)
        assert not path.contains_coord(25.0)

    def test_distance_to_path(self):
        """Test distance calculation."""
        path = LinearPath(
            start_coord=0.0,
            end_coord=100.0,
            start_point=(0, 0),
            end_point=(100, 0),
        )

        # Point directly above path
        dist = path.distance_to_path(50.0, 10.0)
        assert dist == pytest.approx(10.0)

        # Point on path
        dist = path.distance_to_path(50.0, 0.0)
        assert dist == pytest.approx(0.0)

    def test_invalid_same_points_raises(self):
        """Test that same start/end points raises ValueError."""
        with pytest.raises(ValueError, match="must be different"):
            LinearPath(
                start_coord=0.0,
                end_coord=10.0,
                start_point=(50, 50),
                end_point=(50, 50),
            )

    def test_invalid_coord_order_raises(self):
        """Test that end_coord < start_coord raises ValueError."""
        with pytest.raises(ValueError, match="must be >= start_coord"):
            LinearPath(
                start_coord=100.0,
                end_coord=50.0,
                start_point=(0, 0),
                end_point=(100, 0),
            )


# endregion


# region PolylinePath Tests


class TestPolylinePath:
    """Tests for PolylinePath."""

    def test_simple_polyline(self):
        """Test a simple two-segment polyline."""
        path = PolylinePath(
            start_coord=0.0,
            end_coord=100.0,
            waypoints=[
                (0.0, 0, 0),
                (50.0, 100, 0),
                (100.0, 100, 100),
            ],
        )

        assert path.length == 100.0
        assert path.n_segments == 2

    def test_coord_to_xy_first_segment(self):
        """Test coordinate conversion in first segment."""
        path = PolylinePath(
            start_coord=0.0,
            end_coord=100.0,
            waypoints=[
                (0.0, 0, 0),
                (50.0, 100, 0),
                (100.0, 100, 100),
            ],
        )

        # Midpoint of first segment
        x, y = path.coord_to_xy(25.0)
        assert x == pytest.approx(50.0)
        assert y == pytest.approx(0.0)

    def test_coord_to_xy_second_segment(self):
        """Test coordinate conversion in second segment."""
        path = PolylinePath(
            start_coord=0.0,
            end_coord=100.0,
            waypoints=[
                (0.0, 0, 0),
                (50.0, 100, 0),
                (100.0, 100, 100),
            ],
        )

        # Midpoint of second segment
        x, y = path.coord_to_xy(75.0)
        assert x == pytest.approx(100.0)
        assert y == pytest.approx(50.0)

    def test_xy_to_coord(self):
        """Test reverse mapping."""
        path = PolylinePath(
            start_coord=0.0,
            end_coord=100.0,
            waypoints=[
                (0.0, 0, 0),
                (50.0, 100, 0),
                (100.0, 200, 0),
            ],
            tolerance=10.0,
        )

        # Point on first segment
        coord = path.xy_to_coord(50.0, 0.0)
        assert coord is not None
        assert coord == pytest.approx(25.0)

    def test_pixel_length(self):
        """Test total pixel length calculation."""
        path = PolylinePath(
            start_coord=0.0,
            end_coord=100.0,
            waypoints=[
                (0.0, 0, 0),
                (50.0, 100, 0),  # 100 pixels horizontal
                (100.0, 100, 100),  # 100 pixels vertical
            ],
        )

        assert path.pixel_length == pytest.approx(200.0)

    def test_invalid_too_few_waypoints(self):
        """Test that fewer than 2 waypoints raises ValueError."""
        with pytest.raises(ValueError, match="at least 2 waypoints"):
            PolylinePath(
                start_coord=0.0,
                end_coord=10.0,
                waypoints=[(0.0, 0, 0)],
            )

    def test_invalid_waypoint_coord_mismatch(self):
        """Test that mismatched waypoint coords raise ValueError."""
        with pytest.raises(ValueError, match="must equal start_coord"):
            PolylinePath(
                start_coord=0.0,
                end_coord=100.0,
                waypoints=[
                    (10.0, 0, 0),  # Doesn't match start_coord
                    (100.0, 100, 0),
                ],
            )


# endregion


# region Path Contiguity Tests


class TestPathContiguity:
    """Tests for path contiguity checking."""

    def test_contiguous_paths(self):
        """Test contiguous path detection."""
        path1 = LinearPath(
            start_coord=0.0,
            end_coord=50.0,
            start_point=(0, 0),
            end_point=(100, 0),
        )
        path2 = LinearPath(
            start_coord=50.0,
            end_coord=100.0,
            start_point=(0, 100),
            end_point=(100, 100),
        )

        assert path1.is_contiguous_with(path2)
        assert path2.is_contiguous_with(path1)

    def test_non_contiguous_paths(self):
        """Test non-contiguous path detection."""
        path1 = LinearPath(
            start_coord=0.0,
            end_coord=40.0,
            start_point=(0, 0),
            end_point=(100, 0),
        )
        path2 = LinearPath(
            start_coord=50.0,
            end_coord=100.0,
            start_point=(0, 100),
            end_point=(100, 100),
        )

        assert not path1.is_contiguous_with(path2)


# endregion
