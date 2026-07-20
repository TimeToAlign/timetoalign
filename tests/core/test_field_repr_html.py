"""Exact-presence tests for field affordance ``_repr_html_`` cards.

See ``README.md`` for the documented expectations. Every field renders
through the shared ``affordance_html`` helper; here we pin the specific
rows and Try snippets each field family contributes.
"""

from __future__ import annotations

import pyarrow as pa

from timetoalign.core import TimeUnit
from timetoalign.core.fields import StructField
from timetoalign.loader.events import EventData


def _coordinate_field(n: int) -> object:
    """Return a live CoordinateField with *n* elements (start column)."""
    rows = [
        {
            "id": f"e{i}",
            "temporal_type": "interval",
            "event_type": "Note",
            "start": float(i),
            "end": float(i + 1),
        }
        for i in range(n)
    ]
    data = EventData.from_dicts(rows, unit=TimeUnit.seconds)
    return data.get_start_field()


class TestSemanticFieldReprHtml:
    """SemanticField cards add a Scalar-type row and convert affordances."""

    def test_title_and_scalar_type_row(self) -> None:
        html = _coordinate_field(2)._repr_html_()
        assert "<h4>CoordinateField</h4>" in html
        assert "<tr><td><b>Scalar type</b></td><td>Coordinate</td></tr>" in html

    def test_length_and_arrow_rows(self) -> None:
        html = _coordinate_field(2)._repr_html_()
        assert "<tr><td><b>Length</b></td><td>2</td></tr>" in html
        assert "<b>Arrow type</b>" in html
        assert "struct&lt;value: double" in html

    def test_sample_uses_scalar_repr(self) -> None:
        html = _coordinate_field(2)._repr_html_()
        # Sample row renders repr(field[i]) in the scalar repr form.
        assert "<b>Sample</b>" in html
        assert "Coordinate(0.0," in html

    def test_try_row_affordances(self) -> None:
        html = _coordinate_field(2)._repr_html_()
        assert "<code>field[i] -&gt; &lt;Scalar&gt;</code>" in html
        assert "<code>field.convert_to(&lt;TargetScalar&gt;)</code>" in html
        assert "<code>field.get_raw()</code>" in html

    def test_head_tail_truncation(self) -> None:
        html = _coordinate_field(6)._repr_html_()
        # First 3 (0,1,2) and last 2 (4,5) with an ellipsis between.
        assert "Coordinate(0.0," in html
        assert "Coordinate(2.0," in html
        assert "Coordinate(4.0," in html
        assert "Coordinate(5.0," in html
        assert "…" in html
        # The omitted middle element (index 3) is NOT shown.
        assert "Coordinate(3.0," not in html


class TestRawStructFieldReprHtml:
    """The scalar-less base path: Length, Arrow type, Sample; no Scalar row."""

    def _struct_field(self) -> StructField:
        arr = pa.array([{"x": 1}, {"x": 2}], type=pa.struct([("x", pa.int64())]))
        return StructField(arr, pa.field("s", arr.type))

    def test_no_scalar_type_row(self) -> None:
        html = self._struct_field()._repr_html_()
        assert "<h4>StructField</h4>" in html
        assert "Scalar type" not in html

    def test_base_rows_and_affordances(self) -> None:
        html = self._struct_field()._repr_html_()
        assert "<tr><td><b>Length</b></td><td>2</td></tr>" in html
        assert "<b>Arrow type</b>" in html
        assert "<b>Sample</b>" in html
        assert "<code>field[i]</code>" in html
        assert "<code>field.get_raw()</code>" in html
        # The convert affordance belongs only to SemanticField.
        assert "convert_to" not in html


class TestSchemaOnlyFieldReprHtml:
    """A schema-only blueprint field renders without raising."""

    def test_schema_only_sample(self) -> None:
        from timetoalign.core.fields import IntField

        field = IntField(name="x")  # blueprint, no data
        html = field._repr_html_()
        assert "<tr><td><b>Length</b></td><td>0</td></tr>" in html
        assert "<tr><td><b>Sample</b></td><td>(schema-only)</td></tr>" in html
