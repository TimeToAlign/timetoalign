"""Tests for canonical graphical segment bounding boxes."""

from __future__ import annotations

from timetoalign.core.events import BoundingBox
from timetoalign.loader.graphical.paths import HorizontalLinePath
from timetoalign.loader.graphical.segment import GraphicalSegment


def test_get_image_bounds_returns_bounding_box() -> None:
    """Path bounds use the canonical nested image-coordinate box scalar."""
    segment = GraphicalSegment(
        source_index=0,
        path=HorizontalLinePath(x0=10, x1=30, y=5),
        region=(100, 200, 500, 300),
    )

    assert segment.get_image_bounds() == BoundingBox.from_corners(110, 205, 130, 205)
