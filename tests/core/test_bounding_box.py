"""Tests for the canonical graphical bounding-box scalar and field."""

from __future__ import annotations

import pyarrow as pa
import pytest
from pydantic import ValidationError

from timetoalign.core.enums import TimeUnit
from timetoalign.core.events import BoundingBox, BoundingBoxField
from timetoalign.storage.events import EventData


class TestBoundingBox:
    """Tests for ``BoundingBox`` scalar construction and validation."""

    def test_from_corners_preserves_coordinates(self) -> None:
        """Corner construction exposes the canonical nested point shape."""
        box = BoundingBox.from_corners(1, 2.5, 30, 40.5)

        assert box.model_dump() == {
            "ul": {"x": 1.0, "y": 2.5},
            "lr": {"x": 30.0, "y": 40.5},
        }

    @pytest.mark.parametrize("invalid", [float("nan"), float("inf")])
    def test_rejects_non_finite_coordinates(self, invalid: float) -> None:
        """All bounding-box coordinates must be finite."""
        with pytest.raises(ValueError, match="finite"):
            BoundingBox.from_corners(0, 0, invalid, 1)

    def test_from_corners_accepts_finite_floats(self) -> None:
        """Finite float coordinates remain valid."""
        assert BoundingBox.from_corners(0.25, 0.5, 1.75, 2.0).lr.x == 1.75

    @pytest.mark.parametrize(
        ("corners", "coordinate"),
        [((5, 2, 4, 3), "lr.x"), ((2, 5, 3, 4), "lr.y")],
    )
    def test_rejects_inverted_corners(
        self, corners: tuple[int, int, int, int], coordinate: str
    ) -> None:
        """Lower-right corners must not precede upper-left corners."""
        with pytest.raises(ValueError, match=coordinate):
            BoundingBox.from_corners(*corners)

    def test_is_frozen(self) -> None:
        """The scalar and its nested points are immutable."""
        box = BoundingBox.from_corners(1, 2, 3, 4)

        with pytest.raises(ValidationError, match="frozen"):
            box.ul.x = 10


class TestBoundingBoxField:
    """Tests for ``BoundingBoxField`` ingestion and Arrow materialization."""

    def test_list_ingestion_uses_nested_struct_shape(self) -> None:
        """Bounding-box scalars ingest into the canonical nested Arrow struct."""
        first = BoundingBox.from_corners(1, 2, 3, 4)
        second = BoundingBox.from_corners(10.5, 20.5, 30.5, 40.5)

        field = BoundingBoxField.from_field([first, second])
        array = field.to_pyarrow()

        assert array.type == pa.struct(
            [
                pa.field(
                    "ul",
                    pa.struct(
                        [pa.field("x", pa.float64()), pa.field("y", pa.float64())]
                    ),
                ),
                pa.field(
                    "lr",
                    pa.struct(
                        [pa.field("x", pa.float64()), pa.field("y", pa.float64())]
                    ),
                ),
            ]
        )
        assert array.to_pylist() == [
            {"ul": {"x": 1.0, "y": 2.0}, "lr": {"x": 3.0, "y": 4.0}},
            {"ul": {"x": 10.5, "y": 20.5}, "lr": {"x": 30.5, "y": 40.5}},
        ]

    def test_arrow_round_trip_materializes_scalars(self) -> None:
        """Canonical Arrow rows materialize back to validated bounding boxes."""
        expected = BoundingBox.from_corners(1, 2, 3, 4)
        array = pa.array([expected.model_dump()], type=BoundingBoxField.pa_schema)
        field = BoundingBoxField.from_field(
            (array, pa.field("bounding_box", BoundingBoxField.pa_schema))
        )

        assert field[0] == expected

    def test_event_data_resolves_raw_bbox_struct_by_scalar(self) -> None:
        """Raw bounding-box structs afford their paired semantic field."""
        data = EventData.from_dicts(
            [
                {
                    "bbox": {
                        "ul": {"x": 0, "y": 0},
                        "lr": {"x": 1, "y": 1},
                    }
                }
            ],
            unit=TimeUnit.seconds,
        )

        field = data.get_field(BoundingBox)

        assert isinstance(field, BoundingBoxField)
        assert field[0] == BoundingBox.from_corners(0, 0, 1, 1)
