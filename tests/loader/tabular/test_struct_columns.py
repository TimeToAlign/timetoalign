"""Tests for struct column support in TabularLoader.

Tests the Field, ComputedField, and ConvertedField struct features that enable:
- JSON string to struct column parsing
- Struct field access for start/end columns
- Computed fields from expressions
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pytest

from timetoalign.core import NumberType, TimeUnit
from timetoalign.loader import (
    ComputedField,
    ConvertedField,
    Field,
    parse_json_to_struct,
)
from timetoalign.loader.tabular import TsvLoader

# region Test Fixtures


@pytest.fixture
def sample_tsv_with_json(tmp_path: Path) -> Path:
    """Create a sample TSV file with JSON column."""
    content = """id\tstart_time_sec\tduration_sec\trect_coords_json\tlabel
e001\t0.0\t1.5\t{"x": 10, "y": 90, "width": 148, "height": 55}\tregion_1
e002\t1.5\t2.0\t{"x": 158, "y": 90, "width": 200, "height": 55}\tregion_2
e003\t3.5\t1.0\t{"x": 358, "y": 90, "width": 100, "height": 55}\tregion_3
"""
    tsv_path = tmp_path / "events_with_json.tsv"
    tsv_path.write_text(content)
    return tsv_path


# endregion


# region Field Tests


class TestField:
    """Tests for the Field class."""

    def test_field_creation(self):
        """Test basic Field construction."""
        f = Field("rect_coords", "x")
        assert f.column == "rect_coords"
        assert f.fields == ("x",)

    def test_field_nested(self):
        """Test nested field access."""
        f = Field("metadata", "timing", "offset")
        assert f.column == "metadata"
        assert f.fields == ("timing", "offset")

    def test_field_requires_field_names(self):
        """Test that Field requires at least one field name."""
        with pytest.raises(ValueError, match="at least one field name"):
            Field("column")

    def test_field_resolve(self):
        """Test Field resolution against a PyArrow table."""
        # Create a table with a struct column
        struct_type = pa.struct([("x", pa.int64()), ("y", pa.int64())])
        struct_arr = pa.array(
            [{"x": 10, "y": 20}, {"x": 30, "y": 40}], type=struct_type
        )
        table = pa.table({"rect": struct_arr})

        # Resolve field
        f = Field("rect", "x")
        result = f.resolve(table)

        assert result.to_pylist() == [10, 30]

    def test_field_repr(self):
        """Test Field string representation."""
        f = Field("rect", "x")
        assert repr(f) == "Field('rect', 'x')"

    def test_field_equality(self):
        """Test Field equality comparison."""
        f1 = Field("rect", "x")
        f2 = Field("rect", "x")
        f3 = Field("rect", "y")

        assert f1 == f2
        assert f1 != f3


# endregion


# region ComputedField Tests


class TestComputedField:
    """Tests for the ComputedField class."""

    def test_computed_field_formula(self):
        """Test ComputedField with formula."""
        cf = ComputedField("end", formula="rect.x + rect.width")
        assert cf.name == "end"
        assert cf.formula == "rect.x + rect.width"
        assert cf.expr is None

    def test_computed_field_expr(self):
        """Test ComputedField with callable expression."""
        import pyarrow.compute as pc

        def compute_end(table):
            x = pc.struct_field(table["rect"], "x")
            w = pc.struct_field(table["rect"], "width")
            return pc.add(x, w)

        cf = ComputedField("end", expr=compute_end)
        assert cf.name == "end"
        assert cf.formula is None
        assert cf.expr is compute_end

    def test_computed_field_requires_formula_or_expr(self):
        """Test that ComputedField requires either formula or expr."""
        with pytest.raises(ValueError, match="either 'formula' or 'expr'"):
            ComputedField("end")

    def test_computed_field_cannot_have_both(self):
        """Test that ComputedField cannot have both formula and expr."""
        with pytest.raises(ValueError, match="cannot have both"):
            ComputedField("end", formula="a + b", expr=lambda t: t["a"])

    def test_computed_field_compute_formula(self):
        """Test formula evaluation."""
        struct_type = pa.struct([("x", pa.int64()), ("width", pa.int64())])
        struct_arr = pa.array(
            [{"x": 10, "width": 100}, {"x": 200, "width": 50}], type=struct_type
        )
        table = pa.table({"rect": struct_arr})

        cf = ComputedField("end", formula="rect.x + rect.width")
        result = cf.compute(table)

        assert result.to_pylist() == [110, 250]

    def test_computed_field_compute_expr(self):
        """Test callable expression evaluation."""
        import pyarrow.compute as pc

        struct_type = pa.struct([("x", pa.int64()), ("width", pa.int64())])
        struct_arr = pa.array(
            [{"x": 10, "width": 100}, {"x": 200, "width": 50}], type=struct_type
        )
        table = pa.table({"rect": struct_arr})

        def compute_end(t):
            x = pc.struct_field(t["rect"], "x")
            w = pc.struct_field(t["rect"], "width")
            return pc.add(x, w)

        cf = ComputedField("end", expr=compute_end)
        result = cf.compute(table)

        assert result.to_pylist() == [110, 250]

    def test_computed_field_repr(self):
        """Test ComputedField string representation."""
        cf1 = ComputedField("end", formula="a + b")
        cf2 = ComputedField("end", expr=lambda t: t["a"])

        assert "formula='a + b'" in repr(cf1)
        assert "expr=..." in repr(cf2)


# endregion


# region ConvertedField Struct Tests


class TestConvertedFieldStruct:
    """Tests for ConvertedField with struct types."""

    def test_convertedfield_dict_type(self):
        """Test ConvertedField with dtype=dict."""
        ef = ConvertedField("rect_coords", dict, source="rect_coords_json")
        assert ef.is_struct is True
        assert ef.dtype is None  # Will be inferred
        assert ef.source == "rect_coords_json"

    def test_convertedfield_struct_string(self):
        """Test ConvertedField with dtype='struct'."""
        ef = ConvertedField("rect_coords", "struct", source="rect_coords_json")
        assert ef.is_struct is True
        assert ef.dtype is None

    def test_convertedfield_explicit_schema(self):
        """Test ConvertedField with explicit struct schema."""
        ef = ConvertedField(
            "rect_coords", {"x": int, "y": int, "width": int, "height": int}
        )
        assert ef.is_struct is True
        assert ef.struct_schema == {"x": int, "y": int, "width": int, "height": int}
        assert pa.types.is_struct(ef.dtype)

    def test_convertedfield_pyarrow_struct(self):
        """Test ConvertedField with PyArrow struct type."""
        struct_type = pa.struct([("x", pa.int64()), ("y", pa.int64())])
        ef = ConvertedField("rect", struct_type, source="rect_json")
        assert ef.is_struct is True
        assert ef.dtype == struct_type


# endregion


# region parse_json_to_struct Tests


class TestParseJsonToStruct:
    """Tests for the parse_json_to_struct function."""

    def test_parse_basic_json(self):
        """Test parsing basic JSON strings."""
        json_strings = [
            '{"x": 10, "y": 20}',
            '{"x": 30, "y": 40}',
            '{"x": 50, "y": 60}',
        ]
        result = parse_json_to_struct(json_strings)

        assert pa.types.is_struct(result.type)
        assert result.type.num_fields == 2

        # Check values
        x_values = result.field("x").to_pylist()
        y_values = result.field("y").to_pylist()
        assert x_values == [10, 30, 50]
        assert y_values == [20, 40, 60]

    def test_parse_with_explicit_schema(self):
        """Test parsing with explicit schema."""
        json_strings = ['{"a": 1, "b": 2.5}', '{"a": 3, "b": 4.5}']
        result = parse_json_to_struct(
            json_strings, struct_schema={"a": int, "b": float}
        )

        assert result.type.num_fields == 2
        assert result.field("a").to_pylist() == [1, 3]
        assert result.field("b").to_pylist() == [2.5, 4.5]

    def test_parse_with_nulls(self):
        """Test parsing JSON with null values."""
        json_strings = ['{"x": 10}', None, '{"x": 30}']
        result = parse_json_to_struct(json_strings)

        # Check null mask
        assert result.is_null().to_pylist() == [False, True, False]

    def test_parse_invalid_json(self):
        """Test that invalid JSON produces null."""
        json_strings = ['{"x": 10}', "not valid json", '{"x": 30}']
        result = parse_json_to_struct(json_strings)

        assert result.is_null().to_pylist() == [False, True, False]


# endregion


# region TabularLoader Integration Tests


class TestTabularLoaderStructIntegration:
    """Integration tests for TabularLoader with struct columns."""

    def test_physical_loader_direct_columns(self, sample_tsv_with_json: Path):
        """Test loader using direct column names (traditional approach)."""
        import pyarrow.compute as pc

        class ThoresenPhysicalLoader(TsvLoader):
            """Loader for Thoresen TSV using physical time coordinates."""

            start_column = "start_time_sec"
            duration_column = "duration_sec"
            _default_unit = TimeUnit.seconds
            coordinate_type = NumberType.float
            default_event_type = "ThoresenSegment"

        loader = ThoresenPhysicalLoader()
        loader.load(sample_tsv_with_json)

        events = loader.events
        assert events is not None
        assert events.count == 3

        # Check coordinates are in seconds
        # Access start column and extract value field
        table = events.table
        start_col = table.column("start")
        starts = pc.struct_field(start_col, "value").to_pylist()
        assert starts[0] == pytest.approx(0.0)
        assert starts[1] == pytest.approx(1.5)
        assert starts[2] == pytest.approx(3.5)

    def test_graphical_loader_with_struct_field(self, sample_tsv_with_json: Path):
        """Test loader using struct field for start coordinate."""
        import pyarrow.compute as pc

        class ThoresenGraphicalLoader(TsvLoader):
            """Loader for Thoresen TSV using pixel coordinates from struct."""

            extra_columns = [
                ConvertedField("rect_coords", dict, source="rect_coords_json"),
            ]
            start_column = Field("rect_coords", "x")
            end_column = ComputedField(
                "end", formula="rect_coords.x + rect_coords.width"
            )
            _default_unit = TimeUnit.pixels
            coordinate_type = NumberType.float
            default_event_type = "ThoresenRect"

        loader = ThoresenGraphicalLoader()
        loader.load(sample_tsv_with_json)

        events = loader.events
        assert events is not None
        assert events.count == 3

        # Check coordinates are in pixels
        table = events.table
        starts = pc.struct_field(table.column("start"), "value").to_pylist()
        ends = pc.struct_field(table.column("end"), "value").to_pylist()

        # First row: x=10, width=148 -> start=10, end=158
        assert starts[0] == pytest.approx(10.0)
        assert ends[0] == pytest.approx(158.0)

        # Second row: x=158, width=200 -> start=158, end=358
        assert starts[1] == pytest.approx(158.0)
        assert ends[1] == pytest.approx(358.0)

        # Third row: x=358, width=100 -> start=358, end=458
        assert starts[2] == pytest.approx(358.0)
        assert ends[2] == pytest.approx(458.0)

    def test_tuple_syntax_for_field(self, sample_tsv_with_json: Path):
        """Test that tuple syntax works as shorthand for Field."""
        import pyarrow.compute as pc

        class TupleFieldLoader(TsvLoader):
            """Loader using tuple syntax for struct field."""

            extra_columns = [
                ConvertedField("rect_coords", dict, source="rect_coords_json"),
            ]
            # Tuple is shorthand for Field("rect_coords", "x")
            start_column = ("rect_coords", "x")
            _default_unit = TimeUnit.pixels
            coordinate_type = NumberType.float

        loader = TupleFieldLoader()
        loader.load(sample_tsv_with_json)

        events = loader.events
        assert events is not None

        table = events.table
        starts = pc.struct_field(table.column("start"), "value").to_pylist()
        assert starts[0] == pytest.approx(10.0)
        assert starts[1] == pytest.approx(158.0)

    def test_struct_column_included_in_output(self, sample_tsv_with_json: Path):
        """Test that struct columns are included in output table."""

        class StructOutputLoader(TsvLoader):
            """Loader that outputs struct column."""

            extra_columns = [
                ConvertedField("rect_coords", dict, source="rect_coords_json"),
            ]
            start_column = "start_time_sec"
            _default_unit = TimeUnit.seconds
            coordinate_type = NumberType.float

        loader = StructOutputLoader()
        loader.load(sample_tsv_with_json)

        events = loader.events
        assert events is not None

        # Check that rect_coords column exists
        table = events._table
        assert "rect_coords" in table.column_names

        # Check struct fields are accessible
        rect_col = table.column("rect_coords")
        assert pa.types.is_struct(rect_col.type)

    def test_explicit_struct_schema(self, sample_tsv_with_json: Path):
        """Test ConvertedField with explicit struct schema."""

        class ExplicitSchemaLoader(TsvLoader):
            """Loader with explicit struct schema."""

            extra_columns = [
                ConvertedField(
                    "rect_coords",
                    {"x": int, "y": int, "width": int, "height": int},
                    source="rect_coords_json",
                ),
            ]
            start_column = Field("rect_coords", "x")
            _default_unit = TimeUnit.pixels
            coordinate_type = NumberType.float

        loader = ExplicitSchemaLoader()
        loader.load(sample_tsv_with_json)

        events = loader.events
        assert events is not None
        assert events.count == 3

        # Verify struct schema
        table = events._table
        rect_col = table.column("rect_coords")
        assert rect_col.type.num_fields == 4


# endregion
