"""Tests for the ``FieldSpec`` hierarchy and ``resolve_field_spec``.

Validation logic is documented in ``tests/loader/README.md`` (the
``test_column_specs.py`` row).  Summary:

* The universal-resolution table is exercised one row at a time —
  every accepted input (Python type, ``pa.DataType``, raw DataField
  subclass, ``SemanticField`` subclass, ``FieldSpec`` instance,
  callable) must resolve to the documented ``FieldSpec`` instance.
* Each leaf spec (``IntFieldSpec``, ``FloatFieldSpec``,
  ``StringFieldSpec``, ``RationalFieldSpec``) is exercised on a
  representative ``pa.Array`` and the emitted ``DataField`` is
  inspected for type + values.
* ``CompositeFieldSpec`` is exercised in both separator and regex
  forms, with both dict-shaped and iterable-shaped ``parts=``.
* ``FractionFieldSpec`` is exercised in both forms — raw
  ``RationalField`` (no unit) and semantic ``DenominateNumberField``
  (with unit).
"""

from __future__ import annotations

import re
from fractions import Fraction

import pyarrow as pa
import pytest

from timetoalign.core import (
    DenominateNumberField,
    EnharmonicPitchField,
    Id,
    IdField,
    MeasureNumber,
    MeasureNumberField,
    NumericField,
    RationalField,
    StringField,
    StructField,
    TimeUnit,
)
from timetoalign.loader.tabular.field_specs import (
    CallableFieldSpec,
    CompositeFieldSpec,
    FieldSpec,
    FloatFieldSpec,
    FractionFieldSpec,
    IntFieldSpec,
    RationalFieldSpec,
    StringFieldSpec,
    resolve_field_spec,
)

# ---------------------------------------------------------------------------
# resolve_field_spec — universal resolution table
# ---------------------------------------------------------------------------


class TestResolveFieldSpec:
    """Each entry in the universal resolution table maps to exactly one spec."""

    def test_python_int_type(self) -> None:
        assert isinstance(resolve_field_spec(int), IntFieldSpec)

    def test_python_float_type(self) -> None:
        assert isinstance(resolve_field_spec(float), FloatFieldSpec)

    def test_python_str_type(self) -> None:
        assert isinstance(resolve_field_spec(str), StringFieldSpec)

    def test_python_fraction_type(self) -> None:
        assert isinstance(resolve_field_spec(Fraction), RationalFieldSpec)

    def test_pa_int64(self) -> None:
        assert isinstance(resolve_field_spec(pa.int64()), IntFieldSpec)

    def test_pa_int32(self) -> None:
        # All integer widths route to IntFieldSpec.
        assert isinstance(resolve_field_spec(pa.int32()), IntFieldSpec)

    def test_pa_float64(self) -> None:
        assert isinstance(resolve_field_spec(pa.float64()), FloatFieldSpec)

    def test_pa_string(self) -> None:
        assert isinstance(resolve_field_spec(pa.string()), StringFieldSpec)

    def test_numeric_field_class(self) -> None:
        spec = resolve_field_spec(NumericField)
        assert isinstance(spec, FloatFieldSpec)

    def test_string_field_class(self) -> None:
        spec = resolve_field_spec(StringField)
        assert isinstance(spec, StringFieldSpec)

    def test_rational_field_class(self) -> None:
        spec = resolve_field_spec(RationalField)
        assert isinstance(spec, RationalFieldSpec)

    def test_field_spec_instance_passes_through(self) -> None:
        spec = IntFieldSpec(name="x")
        assert resolve_field_spec(spec) is spec

    def test_composite_field_spec_passes_through(self) -> None:
        spec = CompositeFieldSpec(separator="+", parts=[int, int])
        assert resolve_field_spec(spec) is spec

    def test_callable_wraps(self) -> None:
        def my_fn(
            arr: pa.Array, *, name: str = "x"
        ) -> NumericField:  # pragma: no cover
            return NumericField(arr, pa.field(name, arr.type))

        spec = resolve_field_spec(my_fn)
        assert isinstance(spec, CallableFieldSpec)

    def test_unsupported_pa_type_raises(self) -> None:
        with pytest.raises(TypeError):
            resolve_field_spec(pa.binary())

    def test_unsupported_value_raises(self) -> None:
        with pytest.raises(TypeError):
            resolve_field_spec(object())

    def test_semantic_field_subclass_resolves(self) -> None:
        # SemanticField subclasses are resolved via the paired-class
        # emission helper.  We don't assert the exact concrete class
        # here — only that the returned object is a FieldSpec.
        assert isinstance(resolve_field_spec(MeasureNumberField), FieldSpec)
        assert isinstance(resolve_field_spec(IdField), FieldSpec)
        assert isinstance(resolve_field_spec(EnharmonicPitchField), FieldSpec)


# ---------------------------------------------------------------------------
# Leaf specs
# ---------------------------------------------------------------------------


class TestIntFieldSpec:

    def test_emits_int64_numeric_field(self) -> None:
        spec = IntFieldSpec(name="channel")
        result = spec.emit(pa.array(["1", "2", "3"]), name="channel")
        assert isinstance(result, NumericField)
        assert result.field.type == pa.int64()
        assert result.data.to_pylist() == [1, 2, 3]

    def test_fallback_name(self) -> None:
        spec = IntFieldSpec()
        result = spec.emit(pa.array([10, 20]), name="velocity")
        assert result.field.name == "velocity"

    def test_override_name(self) -> None:
        spec = IntFieldSpec(name="explicit")
        result = spec.emit(pa.array([10]), name="ignored_fallback")
        assert result.field.name == "explicit"


class TestFloatFieldSpec:

    def test_emits_float64(self) -> None:
        spec = FloatFieldSpec(name="x")
        result = spec.emit(pa.array(["0.5", "1.5", "2.5"]), name="x")
        assert isinstance(result, NumericField)
        assert result.field.type == pa.float64()
        assert result.data.to_pylist() == [0.5, 1.5, 2.5]


class TestStringFieldSpec:

    def test_emits_string(self) -> None:
        spec = StringFieldSpec(name="note_id")
        result = spec.emit(pa.array(["n1", "n2", "n3"]), name="note_id")
        assert isinstance(result, StringField)
        assert result.data.to_pylist() == ["n1", "n2", "n3"]

    def test_casts_non_string_input(self) -> None:
        spec = StringFieldSpec()
        result = spec.emit(pa.array([1, 2, 3]), name="ints_as_strings")
        assert isinstance(result, StringField)
        assert result.data.to_pylist() == ["1", "2", "3"]


class TestRationalFieldSpec:

    def test_emits_rational_field_from_fraction_strings(self) -> None:
        spec = RationalFieldSpec(name="ratio")
        result = spec.emit(pa.array(["3/4", "1/2", "7/8"]), name="ratio")
        assert isinstance(result, RationalField)
        py = result.data.to_pylist()
        assert py[0] == {"value": 0.75, "numerator": 3, "denominator": 4}
        assert py[1] == {"value": 0.5, "numerator": 1, "denominator": 2}
        assert py[2] == {"value": 0.875, "numerator": 7, "denominator": 8}

    def test_handles_int_strings(self) -> None:
        spec = RationalFieldSpec(name="ratio")
        result = spec.emit(pa.array(["2", "5"]), name="ratio")
        py = result.data.to_pylist()
        assert py[0] == {"value": 2.0, "numerator": 2, "denominator": 1}
        assert py[1] == {"value": 5.0, "numerator": 5, "denominator": 1}

    def test_handles_null_input(self) -> None:
        spec = RationalFieldSpec(name="ratio")
        result = spec.emit(pa.array(["3/4", None, "1/2"]), name="ratio")
        # The struct's null mask is True for the middle row.
        assert result.data.is_null().to_pylist() == [False, True, False]

    def test_zero_denominator_becomes_null(self) -> None:
        spec = RationalFieldSpec(name="ratio")
        # A "3/0" string is unparseable — the row becomes null.
        result = spec.emit(pa.array(["3/4", "3/0"]), name="ratio")
        assert result.data.is_null().to_pylist() == [False, True]


# ---------------------------------------------------------------------------
# CompositeFieldSpec
# ---------------------------------------------------------------------------


class TestCompositeFieldSpec:

    def test_separator_with_iterable_parts(self) -> None:
        spec = CompositeFieldSpec(
            separator="+",
            parts=[IntFieldSpec(), FractionFieldSpec()],
            name="position",
        )
        result = spec.emit(pa.array(["1+3/8", "2+1/4", "16+0/1"]), name="position")
        assert isinstance(result, StructField)
        assert result.field.name == "position"
        # Default part names: from FieldSpec.name where set, else 'part_<i>'.
        assert result.field_names == ["part_0", "part_1"]
        part0 = result.get_sub_field("part_0").data.to_pylist()
        assert part0 == [1, 2, 16]

    def test_separator_with_dict_parts(self) -> None:
        spec = CompositeFieldSpec(
            separator="+",
            parts={"measure": int, "onset": FractionFieldSpec()},
            name="position",
        )
        result = spec.emit(pa.array(["1+3/8", "2+1/4"]), name="position")
        assert result.field_names == ["measure", "onset"]
        measures = result.get_sub_field("measure").data.to_pylist()
        assert measures == [1, 2]

    def test_default_part_name_from_semantic_field_class(self) -> None:
        spec = CompositeFieldSpec(
            separator="+",
            parts=[MeasureNumberField, FractionFieldSpec(name="mn_onset")],
            name="position",
        )
        # MeasureNumberField → "measure_number" (snake_case, sans Field suffix).
        # FractionFieldSpec(name="mn_onset") supplies its own name.
        assert spec.part_keys == ["measure_number", "mn_onset"]

    def test_regex_named_groups(self) -> None:
        pattern = re.compile(r"(?P<measure>\d+)\+(?P<onset>\d+/\d+)")
        spec = CompositeFieldSpec(
            pattern=pattern,
            parts={"measure": int, "onset": FractionFieldSpec()},
            name="position",
        )
        result = spec.emit(pa.array(["1+3/8", "2+1/4"]), name="position")
        assert result.get_sub_field("measure").data.to_pylist() == [1, 2]

    def test_regex_positional_groups(self) -> None:
        pattern = r"(\d+)\+(\d+/\d+)"
        spec = CompositeFieldSpec(
            pattern=pattern,
            parts=[IntFieldSpec(name="measure"), FractionFieldSpec(name="onset")],
            name="position",
        )
        result = spec.emit(pa.array(["1+3/8", "2+1/4"]), name="position")
        assert result.get_sub_field("measure").data.to_pylist() == [1, 2]

    def test_separator_mismatch_produces_null_row(self) -> None:
        spec = CompositeFieldSpec(
            separator="+",
            parts=[IntFieldSpec(name="measure"), FractionFieldSpec(name="onset")],
        )
        # Second row has no separator → its parts are null.
        result = spec.emit(pa.array(["1+3/8", "no_separator"]), name="x")
        measures = result.get_sub_field("measure").data.to_pylist()
        assert measures == [1, None]

    def test_separator_and_pattern_mutually_exclusive(self) -> None:
        with pytest.raises(ValueError):
            CompositeFieldSpec(parts=[int, int])  # neither
        with pytest.raises(ValueError):
            CompositeFieldSpec(separator="+", pattern=r"\d+", parts=[int])


# ---------------------------------------------------------------------------
# FractionFieldSpec
# ---------------------------------------------------------------------------


class TestFractionFieldSpec:

    def test_raw_emission_without_unit(self) -> None:
        spec = FractionFieldSpec(name="duration")
        result = spec.emit(pa.array(["3/4", "1/2"]), name="duration")
        assert isinstance(result, RationalField)
        assert not isinstance(result, DenominateNumberField)
        py = result.data.to_pylist()
        assert py[0] == {"value": 0.75, "numerator": 3, "denominator": 4}

    def test_semantic_emission_with_unit(self) -> None:
        spec = FractionFieldSpec(name="duration", unit=TimeUnit.quarters)
        result = spec.emit(pa.array(["3/4", "1/2"]), name="duration")
        assert isinstance(result, DenominateNumberField)
        assert result.unit == TimeUnit.quarters

    def test_string_unit_coerced(self) -> None:
        spec = FractionFieldSpec(name="duration", unit="quarters")
        assert spec.unit == TimeUnit.quarters

    def test_part_keys_empty(self) -> None:
        # FractionFieldSpec doesn't surface sub-fields as top-level
        # columns; its part_keys is the empty list.
        spec = FractionFieldSpec(name="duration", unit=TimeUnit.quarters)
        assert spec.part_keys == []


# ---------------------------------------------------------------------------
# CallableFieldSpec
# ---------------------------------------------------------------------------


class TestCallableFieldSpec:

    def test_forwards_to_callable(self) -> None:
        def my_fn(arr: pa.Array, *, name: str = "x") -> NumericField:
            return NumericField(
                arr.cast(pa.int64()),
                pa.field(name, pa.int64()),
            )

        spec = CallableFieldSpec(my_fn, name="forwarded")
        result = spec.emit(pa.array(["1", "2"]), name="ignored")
        assert isinstance(result, NumericField)
        assert result.field.name == "forwarded"

    def test_callable_without_name_kwarg(self) -> None:
        # If the wrapped callable doesn't accept ``name``, the spec
        # falls back to a positional call.
        def my_fn(arr: pa.Array) -> NumericField:
            return NumericField(
                arr.cast(pa.int64()),
                pa.field("x", pa.int64()),
            )

        spec = CallableFieldSpec(my_fn)
        result = spec.emit(pa.array(["10", "20"]), name="ignored")
        assert isinstance(result, NumericField)


# ---------------------------------------------------------------------------
# SemanticField-class resolution (paired-class emission via resolve_field_spec)
# ---------------------------------------------------------------------------


class TestSemanticFieldClassResolution:

    def test_measure_number_field_packs_atomic_int(self) -> None:
        spec = resolve_field_spec(MeasureNumberField)
        result = spec.emit(pa.array([1, 2, 16]), name="measure_number")
        assert isinstance(result, MeasureNumberField)
        # Each element materialises into a MeasureNumber scalar.
        assert result[0] == MeasureNumber(value=1)
        assert result[2] == MeasureNumber(value=16)

    def test_id_field_packs_atomic_string(self) -> None:
        spec = resolve_field_spec(IdField)
        result = spec.emit(pa.array(["abc", "def"]), name="note_id")
        assert isinstance(result, IdField)
        assert result[0] == Id(value="abc")
        assert result[1] == Id(value="def")
