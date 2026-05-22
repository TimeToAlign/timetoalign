"""WP3 — parity tests between scalar ``to(*)`` and field ``convert_to(*)``.

Verifies that every data-shaped conversion implemented at the
``SemanticField`` level produces the same scalar values as the per-row
scalar dispatch.  Per CLAUDE.md §6 (Coordinate Object Primacy) and the
workshop_typing_push.md design: the field-level ``convert_to`` MUST be a
``pa.compute`` expression over the underlying ``pa.Array`` and MUST
NEVER iterate over materialised scalars to call ``scalar.to()``.

Each parity test:

1. Builds a paired ``SemanticField`` with ~100 well-typed instances + 10
   nulls + boundary values.
2. Materialises ``scalar.to(target)`` per row.
3. Calls ``field.convert_to(target)``.
4. Asserts element-wise equality against the field-level conversion.
5. Re-runs the assertion on a sliced view of the field to confirm
   slice-friendly behaviour.
"""

from __future__ import annotations

from typing import Any

import pyarrow as pa
import pytest

from timetoalign.core.events import (
    EnharmonicPitch,
    EnharmonicPitchClass,
    EnharmonicPitchField,
    GenericPitch,
    GenericPitchClass,
    GenericPitchField,
    MidiPitch,
    SpecificPitch,
    SpecificPitchClass,
    SpecificPitchClassField,
    SpecificPitchField,
)
from timetoalign.core.fields import build_struct_array

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_ep_field(scalars: list[EnharmonicPitch | None]) -> EnharmonicPitchField:
    arr = build_struct_array(EnharmonicPitch, scalars)
    pa_field = pa.field("midi_pitch", arr.type)
    return EnharmonicPitchField.from_field((arr, pa_field))


def _build_sp_field(scalars: list[SpecificPitch | None]) -> SpecificPitchField:
    arr = build_struct_array(SpecificPitch, scalars)
    pa_field = pa.field("specific_pitch", arr.type)
    return SpecificPitchField.from_field((arr, pa_field))


def _build_spc_field(
    scalars: list[SpecificPitchClass | None],
) -> SpecificPitchClassField:
    arr = build_struct_array(SpecificPitchClass, scalars)
    pa_field = pa.field("spc", arr.type)
    return SpecificPitchClassField.from_field((arr, pa_field))


def _build_gp_field(scalars: list[GenericPitch | None]) -> GenericPitchField:
    arr = build_struct_array(GenericPitch, scalars)
    pa_field = pa.field("gp", arr.type)
    return GenericPitchField.from_field((arr, pa_field))


def _ep_sample() -> list[EnharmonicPitch | None]:
    """100 EP + 10 nulls + boundary cases (midi 0, 1, 127)."""
    scalars: list[EnharmonicPitch | None] = [
        EnharmonicPitch(midi_number=i % 128) for i in range(100)
    ]
    scalars.extend([None] * 10)
    scalars.append(EnharmonicPitch(midi_number=0))
    scalars.append(EnharmonicPitch(midi_number=1))
    scalars.append(EnharmonicPitch(midi_number=127))
    return scalars


def _sp_sample() -> list[SpecificPitch | None]:
    """SP sample covering all step letters, alter -2..+2, octaves 0..7."""
    scalars: list[SpecificPitch | None] = []
    steps = ("C", "D", "E", "F", "G", "A", "B")
    alters = (-2, -1, 0, 1, 2)
    octaves = list(range(8))
    for i in range(100):
        step = steps[i % 7]
        alter = alters[i % 5]
        octave = octaves[i % 8]
        scalars.append(SpecificPitch(step=step, alter=alter, octave=octave))
    scalars.extend([None] * 10)
    # Boundaries
    scalars.append(SpecificPitch(step="C", alter=0, octave=0))
    scalars.append(SpecificPitch(step="B", alter=2, octave=8))
    scalars.append(SpecificPitch(step="C", alter=-2, octave=-1))
    return scalars


def _spc_sample() -> list[SpecificPitchClass | None]:
    scalars: list[SpecificPitchClass | None] = []
    steps = ("C", "D", "E", "F", "G", "A", "B")
    alters = (-2, -1, 0, 1, 2)
    for i in range(100):
        scalars.append(SpecificPitchClass(step=steps[i % 7], alter=alters[i % 5]))
    scalars.extend([None] * 10)
    return scalars


def _gp_sample() -> list[GenericPitch | None]:
    scalars: list[GenericPitch | None] = []
    for i in range(100):
        scalars.append(GenericPitch(step=i % 7, octave=i % 8))
    scalars.extend([None] * 10)
    return scalars


def _materialise_via_scalar(
    scalars: list[Any | None], target: type
) -> list[Any | None]:
    """Apply ``scalar.to(target)`` per row, preserving null positions."""
    return [None if s is None else s.to(target) for s in scalars]


def _materialise_via_field(field: Any) -> list[Any | None]:
    """Read every element of a SemanticField as a list of scalars."""
    return [field[i] for i in range(len(field))]


def _assert_parity(
    scalars: list[Any | None],
    target: type,
    field: Any,
) -> None:
    expected = _materialise_via_scalar(scalars, target)
    converted_field = field.convert_to(target)
    actual = _materialise_via_field(converted_field)
    assert len(actual) == len(
        expected
    ), f"length mismatch: field={len(actual)} vs scalar={len(expected)}"
    for i, (e, a) in enumerate(zip(expected, actual)):
        assert e == a, f"at index {i}: scalar={e!r} field={a!r}"


# ---------------------------------------------------------------------------
# EnharmonicPitch.to(*) parity
# ---------------------------------------------------------------------------


class TestEnharmonicPitchConversions:
    def test_ep_to_midi_pitch(self) -> None:
        scalars = _ep_sample()
        field = _build_ep_field(scalars)
        _assert_parity(scalars, MidiPitch, field)

    def test_ep_to_enharmonic_pitch_class(self) -> None:
        scalars = _ep_sample()
        field = _build_ep_field(scalars)
        _assert_parity(scalars, EnharmonicPitchClass, field)

    def test_ep_to_self(self) -> None:
        scalars = _ep_sample()
        field = _build_ep_field(scalars)
        _assert_parity(scalars, EnharmonicPitch, field)


# ---------------------------------------------------------------------------
# SpecificPitch.to(*) — full matrix
# ---------------------------------------------------------------------------


class TestSpecificPitchConversions:
    @pytest.mark.parametrize(
        "target",
        [SpecificPitch, MidiPitch, EnharmonicPitchClass, SpecificPitchClass],
    )
    def test_sp_to_target(self, target: type) -> None:
        scalars = _sp_sample()
        field = _build_sp_field(scalars)
        _assert_parity(scalars, target, field)


# ---------------------------------------------------------------------------
# SpecificPitchClass.to(*)
# ---------------------------------------------------------------------------


class TestSpecificPitchClassConversions:
    def test_spc_to_enharmonic_pitch_class(self) -> None:
        scalars = _spc_sample()
        field = _build_spc_field(scalars)
        _assert_parity(scalars, EnharmonicPitchClass, field)

    def test_spc_to_self(self) -> None:
        scalars = _spc_sample()
        field = _build_spc_field(scalars)
        _assert_parity(scalars, SpecificPitchClass, field)


# ---------------------------------------------------------------------------
# GenericPitch.to(*)
# ---------------------------------------------------------------------------


class TestGenericPitchConversions:
    def test_gp_to_generic_pitch_class(self) -> None:
        scalars = _gp_sample()
        field = _build_gp_field(scalars)
        _assert_parity(scalars, GenericPitchClass, field)


# ---------------------------------------------------------------------------
# Sliced-field parity — confirms zero-copy slicing semantics
# ---------------------------------------------------------------------------


class TestSlicedFieldParity:
    def test_sp_slice_parity(self) -> None:
        """Slice the SP field, then run parity on the slice."""
        scalars = _sp_sample()
        field = _build_sp_field(scalars)
        # Slice the underlying StructArray, wrap back into a SemanticField.
        sliced_data = field.to_pyarrow().slice(20, 50)
        sliced_field = SpecificPitchField.from_field(
            (sliced_data, pa.field("specific_pitch_slice", sliced_data.type))
        )
        sliced_scalars = scalars[20:70]
        _assert_parity(sliced_scalars, EnharmonicPitchClass, sliced_field)

    def test_ep_slice_parity(self) -> None:
        scalars = _ep_sample()
        field = _build_ep_field(scalars)
        sliced_data = field.to_pyarrow().slice(10, 50)
        sliced_field = EnharmonicPitchField.from_field(
            (sliced_data, pa.field("midi_pitch_slice", sliced_data.type))
        )
        sliced_scalars = scalars[10:60]
        _assert_parity(sliced_scalars, EnharmonicPitchClass, sliced_field)


# ---------------------------------------------------------------------------
# __init_subclass__ parity-check enforcement (failure path)
# ---------------------------------------------------------------------------


class TestParityCheckEnforcement:
    """Exercise ``SemanticField.__init_subclass__``'s @data_shaped enforcement.

    The enforcement at ``core/fields.py:580-603`` raises ``TypeError`` at
    subclass-creation time when a paired Field fails to mirror every
    ``@data_shaped`` method on its scalar's MRO.  This test constructs a
    synthetic scalar carrying one ``@data_shaped`` method, then attempts to
    declare a paired SemanticField that fails to provide the mirror.
    """

    def test_missing_mirror_raises_typeerror(self) -> None:
        from pydantic import BaseModel as _BaseModel
        from pydantic import ConfigDict

        from timetoalign.core.fields import SemanticField, data_shaped

        class _SyntheticBadScalar(_BaseModel):
            model_config = ConfigDict(frozen=True)
            value: int

            @data_shaped
            def required_mirror(self) -> int:  # pragma: no cover — never called
                return self.value

        with pytest.raises(TypeError, match=r"required_mirror"):

            class _SyntheticBadField(  # noqa: F841 — declaration itself must raise
                SemanticField[_SyntheticBadScalar]
            ):
                """Paired field that is missing the ``required_mirror`` mirror."""

    def test_missing_computed_field_mirror_raises_typeerror(self) -> None:
        """Exercise the ``@computed_field @property @data_shaped`` detection path.

        Mirrors the real ``SpecificPitch.fifths`` decorator stack
        (``@computed_field`` outermost, ``@property``, ``@data_shaped``
        innermost — see ``core/events.py``).  ``_is_data_shaped`` walks
        ``member.fget`` / ``member.wrapped_property`` / ``member.fn``
        to detect the marker through pydantic's ``ComputedFieldInfo``
        wrapper; if any of those branches regress, the parity check
        would silently skip the computed field and the missing mirror
        would NOT raise.
        """
        from pydantic import BaseModel as _BaseModel
        from pydantic import ConfigDict, computed_field

        from timetoalign.core.fields import SemanticField, data_shaped

        class _SyntheticComputedScalar(_BaseModel):
            model_config = ConfigDict(frozen=True)
            value: int

            @computed_field  # type: ignore[prop-decorator]
            @property
            @data_shaped
            def derived(self) -> int:  # pragma: no cover — never called
                return self.value + 1

        with pytest.raises(TypeError, match=r"derived"):

            class _SyntheticComputedField(  # noqa: F841 — declaration must raise
                SemanticField[_SyntheticComputedScalar]
            ):
                """Paired field that omits the ``derived`` computed-field mirror."""

    def test_abstract_intermediate_without_scalar_cls_is_allowed(self) -> None:
        """``__init_subclass__`` MUST skip the parity check when ``scalar_cls`` is None.

        ``TimeScalarField`` extends ``SemanticField`` without parametrising
        ``Generic[T]`` and without declaring a ``scalar_cls`` — its concrete
        children (``CoordinateField`` etc.) supply the scalar.  The
        ``scalar_cls is None`` early-return at
        ``core/fields.py:578-579`` is what lets such intermediates be
        declared at all; a regression here would brick library import.
        """
        from timetoalign.core.fields import SemanticField

        # Declaring an unparametrised abstract intermediate must not raise.
        class _SyntheticAbstractField(
            SemanticField
        ):  # noqa: F841 — declaration is the assertion
            """Abstract intermediate, no scalar parametrisation."""

        # The introspectable state: scalar_cls stays None on the class.
        assert getattr(_SyntheticAbstractField, "scalar_cls", "sentinel") is None
        # Real-world check: TimeScalarField itself follows the same pattern
        # and is the canonical anchor for this skip behaviour.
        from timetoalign.core.time import TimeScalarField

        assert TimeScalarField.scalar_cls is None


# ---------------------------------------------------------------------------
# TimeScalarField arithmetic + predicate parity tests
# ---------------------------------------------------------------------------
#
# Mirror the pitch-conversion parity pattern for the four TimeScalar Field
# classes (CoordinateField, DurationField, IdCoordinateField,
# IdDurationField).  Each parity test:
#
# 1. Builds a field of N >= 4 scalars including at least one ``None`` and
#    one boundary value (zero for predicates).
# 2. Runs the field-level data-shaped method (e.g. ``field.is_zero()``,
#    ``field + other_field``).
# 3. Runs the scalar-level dispatch element-wise.
# 4. Asserts exact element-wise equality.
# 5. Re-runs on a slice (``field[1:3]``) to honour the corpus-scale
#    slicing constraint.
#
# Operator semantics (WP2.5):
#   * ``Coordinate - Coordinate -> Duration``
#   * ``Coordinate + Coordinate`` raises
#   * ``Coordinate + Duration -> Coordinate``
#   * ``Coordinate - Duration -> Coordinate``
#   * ``Duration ± Duration -> Duration``
#   * ``*`` / ``/`` / ``//`` only with raw numbers
#   * Durations are signed.

from timetoalign.core.enums import NumberType, TimeUnit  # noqa: E402
from timetoalign.core.time import (  # noqa: E402
    Coordinate,
    CoordinateField,
    Duration,
    DurationField,
    IdCoordinate,
    IdCoordinateField,
    IdDuration,
    IdDurationField,
)


def _coord_struct_type() -> pa.StructType:
    return pa.struct(
        [
            pa.field("value", pa.float64(), nullable=True),
            pa.field("numerator", pa.int64(), nullable=True),
            pa.field("denominator", pa.int64(), nullable=True),
        ]
    )


def _coord_pa_array(values: list[float | None]) -> pa.Array:
    rows: list[dict[str, float | int | None] | None] = []
    for v in values:
        if v is None:
            rows.append(None)
        else:
            rows.append({"value": v, "numerator": None, "denominator": None})
    return pa.array(rows, type=_coord_struct_type())


def _make_field(
    field_cls: type,
    values: "list[float] | list[float | None]",
    *,
    name: str = "tlf",
    timeline_id: str | None = None,
) -> Any:
    arr = _coord_pa_array(values)
    pa_field = pa.field(name, _coord_struct_type())
    if timeline_id is None:
        return field_cls.from_field(
            (arr, pa_field), unit=TimeUnit.seconds, number_type=NumberType.float
        )
    return field_cls.from_field(
        (arr, pa_field),
        unit=TimeUnit.seconds,
        number_type=NumberType.float,
        timeline_id=timeline_id,
    )


def _scalar_list(
    scalar_cls: type,
    values: "list[float] | list[float | None]",
    timeline_id: str | None = None,
) -> list[Any | None]:
    out: list[Any | None] = []
    for v in values:
        if v is None:
            out.append(None)
        else:
            if timeline_id is None:
                out.append(scalar_cls(v, TimeUnit.seconds))
            else:
                out.append(scalar_cls(v, TimeUnit.seconds, timeline_id))
    return out


def _pa_to_list(arr: pa.Array) -> list[Any]:
    return arr.to_pylist()


def _assert_predicate_parity(
    pred_name: str,
    field: Any,
    scalars: list[Any | None],
) -> None:
    actual = _pa_to_list(getattr(field, pred_name)())
    expected = [None if s is None else getattr(s, pred_name)() for s in scalars]
    assert actual == expected, (
        f"{type(field).__name__}.{pred_name}() parity mismatch: "
        f"field={actual} vs scalar={expected}"
    )


def _assert_to_float_parity(field: Any, scalars: list[Any | None]) -> None:
    actual = _pa_to_list(field.to_float())
    expected = [None if s is None else s.to_float() for s in scalars]
    assert actual == expected, (
        f"{type(field).__name__}.to_float() parity mismatch: "
        f"field={actual} vs scalar={expected}"
    )


def _assert_to_int_parity(field: Any, scalars: list[Any | None], rounding: str) -> None:
    actual = _pa_to_list(field.to_int(rounding=rounding))
    expected = [None if s is None else s.to_int(rounding=rounding) for s in scalars]
    assert actual == expected, (
        f"{type(field).__name__}.to_int({rounding!r}) parity mismatch: "
        f"field={actual} vs scalar={expected}"
    )


def _materialise_field_values(field: Any) -> list[Any | None]:
    return [field[i] for i in range(len(field))]


# Common sample including boundary zero plus signed values.  Kept null-free
# so that predicate/arithmetic parity tests focus on numeric semantics;
# null handling is exercised separately by ``TestTimeScalarFieldNullPropagation``.
_BASE_VALUES: list[float] = [0.0, 1.5, -2.25, 3.0, -0.5, 4.75]

# Sample with None included — used by the null-propagation parity tests
# that pin element-wise None semantics across the TimeScalarField mirrors.
_BASE_VALUES_WITH_NULL: list[float | None] = [0.0, 1.5, -2.25, None, 3.0, -0.5, 4.75]


class TestCoordinateFieldPredicateParity:
    """Coordinate is_zero/is_positive/is_negative + to_float/to_int parity."""

    def test_is_zero(self) -> None:
        field = _make_field(CoordinateField, _BASE_VALUES)
        scalars = _scalar_list(Coordinate, _BASE_VALUES)
        _assert_predicate_parity("is_zero", field, scalars)

    def test_is_positive(self) -> None:
        field = _make_field(CoordinateField, _BASE_VALUES)
        scalars = _scalar_list(Coordinate, _BASE_VALUES)
        _assert_predicate_parity("is_positive", field, scalars)

    def test_is_negative(self) -> None:
        field = _make_field(CoordinateField, _BASE_VALUES)
        scalars = _scalar_list(Coordinate, _BASE_VALUES)
        _assert_predicate_parity("is_negative", field, scalars)

    def test_to_float(self) -> None:
        field = _make_field(CoordinateField, _BASE_VALUES)
        scalars = _scalar_list(Coordinate, _BASE_VALUES)
        _assert_to_float_parity(field, scalars)

    @pytest.mark.parametrize("rounding", ["truncate", "round", "floor", "ceil"])
    def test_to_int(self, rounding: str) -> None:
        field = _make_field(CoordinateField, _BASE_VALUES)
        scalars = _scalar_list(Coordinate, _BASE_VALUES)
        _assert_to_int_parity(field, scalars, rounding)

    def test_predicate_parity_on_slice(self) -> None:
        """Slice the field and confirm parity on the slice."""
        field = _make_field(CoordinateField, _BASE_VALUES)
        scalars = _scalar_list(Coordinate, _BASE_VALUES)
        sliced_data = field.to_pyarrow().slice(1, 3)
        sliced_field = CoordinateField.from_field(
            (sliced_data, pa.field("slice", sliced_data.type)),
            unit=TimeUnit.seconds,
            number_type=NumberType.float,
        )
        sliced_scalars = scalars[1:4]
        _assert_predicate_parity("is_zero", sliced_field, sliced_scalars)


class TestCoordinateFieldArithmeticParity:
    """Coordinate field arithmetic parity (vs Duration; ± raw numbers).

    Coordinate - Coordinate -> Duration; Coordinate + Coordinate raises;
    * / // only accept raw numbers (caveat: position-scaling).
    """

    def test_coord_minus_coord_returns_duration(self) -> None:
        lhs_vals = [1.0, 2.0, 3.5, 5.0]
        rhs_vals = [0.5, 1.0, 1.25, 2.0]
        lhs_field = _make_field(CoordinateField, lhs_vals, name="lhs")
        rhs_field = _make_field(CoordinateField, rhs_vals, name="rhs")
        lhs_scalars = _scalar_list(Coordinate, lhs_vals)
        rhs_scalars = _scalar_list(Coordinate, rhs_vals)
        result_field = lhs_field - rhs_field
        assert isinstance(result_field, DurationField)
        scalar_results = [
            (left - right).value for left, right in zip(lhs_scalars, rhs_scalars)
        ]
        field_results = _pa_to_list(result_field._value_array())
        assert field_results == scalar_results

    def test_coord_plus_coord_raises(self) -> None:
        """Mirror the scalar contract: Coordinate + Coordinate raises."""
        a = _make_field(CoordinateField, [1.0, 2.0], name="a")
        b = _make_field(CoordinateField, [1.0, 2.0], name="b")
        with pytest.raises(TypeError):
            a + b

    def test_coord_plus_duration_returns_coordinate(self) -> None:
        coord_vals = [1.0, 2.0, 3.0, 5.0]
        dur_vals = [0.5, 1.0, 1.5, 4.0]
        coord_field = _make_field(CoordinateField, coord_vals, name="coord")
        dur_field = _make_field(DurationField, dur_vals, name="dur")
        coord_scalars = _scalar_list(Coordinate, coord_vals)
        dur_scalars = _scalar_list(Duration, dur_vals)
        result = coord_field + dur_field
        assert isinstance(result, CoordinateField)
        scalar_results = [(c + d).value for c, d in zip(coord_scalars, dur_scalars)]
        assert _pa_to_list(result._value_array()) == scalar_results

    def test_coord_mul_scalar_parity(self) -> None:
        """Coordinate * raw number (musicologically dubious; mirrored for parity)."""
        vals = [1.0, -2.0, 3.5, 0.0]
        field = _make_field(CoordinateField, vals)
        scalars = _scalar_list(Coordinate, vals)
        result = field * 2.0
        assert isinstance(result, CoordinateField)
        scalar_results = [(s * 2.0).value for s in scalars]
        assert _pa_to_list(result._value_array()) == scalar_results

    def test_coord_truediv_scalar_parity(self) -> None:
        vals = [1.0, -2.0, 3.5, 5.0]
        field = _make_field(CoordinateField, vals)
        scalars = _scalar_list(Coordinate, vals)
        result = field / 2.0
        scalar_results = [(s / 2.0).value for s in scalars]
        assert _pa_to_list(result._value_array()) == scalar_results

    def test_coord_floordiv_scalar_parity(self) -> None:
        vals = [1.5, -2.5, 3.0, 7.25]
        field = _make_field(CoordinateField, vals)
        scalars = _scalar_list(Coordinate, vals)
        result = field // 2.0
        scalar_results = [(s // 2.0).value for s in scalars]
        assert _pa_to_list(result._value_array()) == scalar_results


class TestDurationFieldPredicateParity:
    """Duration is_zero / is_positive / is_negative — durations are signed."""

    def test_is_zero(self) -> None:
        field = _make_field(DurationField, _BASE_VALUES)
        scalars = _scalar_list(Duration, _BASE_VALUES)
        _assert_predicate_parity("is_zero", field, scalars)

    def test_is_positive(self) -> None:
        field = _make_field(DurationField, _BASE_VALUES)
        scalars = _scalar_list(Duration, _BASE_VALUES)
        _assert_predicate_parity("is_positive", field, scalars)

    def test_is_negative(self) -> None:
        field = _make_field(DurationField, _BASE_VALUES)
        scalars = _scalar_list(Duration, _BASE_VALUES)
        _assert_predicate_parity("is_negative", field, scalars)

    def test_to_float(self) -> None:
        field = _make_field(DurationField, _BASE_VALUES)
        scalars = _scalar_list(Duration, _BASE_VALUES)
        _assert_to_float_parity(field, scalars)


class TestDurationFieldArithmeticParity:
    """Duration arithmetic: ± Duration -> Duration; * / // raw number."""

    def test_duration_plus_duration(self) -> None:
        a_vals = [1.0, -2.0, 3.5, 4.0]
        b_vals = [0.5, 1.0, 2.0, 4.0]
        a = _make_field(DurationField, a_vals, name="a")
        b = _make_field(DurationField, b_vals, name="b")
        a_s = _scalar_list(Duration, a_vals)
        b_s = _scalar_list(Duration, b_vals)
        result = a + b
        assert isinstance(result, DurationField)
        scalar_results = [(x + y).value for x, y in zip(a_s, b_s)]
        assert _pa_to_list(result._value_array()) == scalar_results

    def test_duration_minus_duration(self) -> None:
        a_vals = [1.0, -2.0, 3.5, 4.0]
        b_vals = [0.5, 1.0, 2.0, 4.0]
        a = _make_field(DurationField, a_vals, name="a")
        b = _make_field(DurationField, b_vals, name="b")
        a_s = _scalar_list(Duration, a_vals)
        b_s = _scalar_list(Duration, b_vals)
        result = a - b
        scalar_results = [(x - y).value for x, y in zip(a_s, b_s)]
        assert _pa_to_list(result._value_array()) == scalar_results

    def test_duration_mul_scalar(self) -> None:
        vals = [1.0, -2.0, 3.5, 0.0]
        field = _make_field(DurationField, vals)
        scalars = _scalar_list(Duration, vals)
        result = field * 0.75
        scalar_results = [(s * 0.75).value for s in scalars]
        assert _pa_to_list(result._value_array()) == scalar_results

    def test_duration_truediv_scalar(self) -> None:
        vals = [1.0, -2.0, 3.5, 5.0]
        field = _make_field(DurationField, vals)
        scalars = _scalar_list(Duration, vals)
        result = field / 2.0
        scalar_results = [(s / 2.0).value for s in scalars]
        assert _pa_to_list(result._value_array()) == scalar_results

    def test_duration_floordiv_scalar(self) -> None:
        vals = [1.5, -2.5, 3.0, 7.25]
        field = _make_field(DurationField, vals)
        scalars = _scalar_list(Duration, vals)
        result = field // 2.0
        scalar_results = [(s // 2.0).value for s in scalars]
        assert _pa_to_list(result._value_array()) == scalar_results


class TestIdCoordinateFieldParity:
    """IdCoordinateField inherits TimeScalarField mirrors and adds id propagation."""

    def test_is_zero_parity(self) -> None:
        tid = "tl-1"
        field = _make_field(IdCoordinateField, _BASE_VALUES, timeline_id=tid)
        scalars = _scalar_list(IdCoordinate, _BASE_VALUES, timeline_id=tid)
        _assert_predicate_parity("is_zero", field, scalars)

    def test_is_positive_parity(self) -> None:
        tid = "tl-1"
        field = _make_field(IdCoordinateField, _BASE_VALUES, timeline_id=tid)
        scalars = _scalar_list(IdCoordinate, _BASE_VALUES, timeline_id=tid)
        _assert_predicate_parity("is_positive", field, scalars)

    def test_is_negative_parity(self) -> None:
        tid = "tl-1"
        field = _make_field(IdCoordinateField, _BASE_VALUES, timeline_id=tid)
        scalars = _scalar_list(IdCoordinate, _BASE_VALUES, timeline_id=tid)
        _assert_predicate_parity("is_negative", field, scalars)

    def test_to_float_parity(self) -> None:
        tid = "tl-1"
        field = _make_field(IdCoordinateField, _BASE_VALUES, timeline_id=tid)
        scalars = _scalar_list(IdCoordinate, _BASE_VALUES, timeline_id=tid)
        _assert_to_float_parity(field, scalars)

    def test_arithmetic_minus_returns_id_duration(self) -> None:
        tid = "tl-9"
        lhs_vals = [1.0, 2.0, 3.5, 4.0]
        rhs_vals = [0.5, 1.0, 1.25, 2.0]
        lhs = _make_field(IdCoordinateField, lhs_vals, name="lhs", timeline_id=tid)
        rhs = _make_field(IdCoordinateField, rhs_vals, name="rhs", timeline_id=tid)
        result = lhs - rhs
        # Sibling sub-of-DurationField; check value parity.
        lhs_s = _scalar_list(IdCoordinate, lhs_vals, timeline_id=tid)
        rhs_s = _scalar_list(IdCoordinate, rhs_vals, timeline_id=tid)
        scalar_results = [(left - right).value for left, right in zip(lhs_s, rhs_s)]
        assert _pa_to_list(result._value_array()) == scalar_results

    def test_slice_parity(self) -> None:
        tid = "tl-1"
        field = _make_field(IdCoordinateField, _BASE_VALUES, timeline_id=tid)
        scalars = _scalar_list(IdCoordinate, _BASE_VALUES, timeline_id=tid)
        sliced_data = field.to_pyarrow().slice(1, 3)
        sliced = IdCoordinateField.from_field(
            (sliced_data, pa.field("slice", sliced_data.type)),
            unit=TimeUnit.seconds,
            number_type=NumberType.float,
            timeline_id=tid,
        )
        _assert_predicate_parity("is_zero", sliced, scalars[1:4])


class TestIdDurationFieldParity:
    """IdDurationField inherits TimeScalarField mirrors via DurationField."""

    def test_is_zero_parity(self) -> None:
        tid = "tl-1"
        field = _make_field(IdDurationField, _BASE_VALUES, timeline_id=tid)
        scalars = _scalar_list(IdDuration, _BASE_VALUES, timeline_id=tid)
        _assert_predicate_parity("is_zero", field, scalars)

    def test_is_positive_parity(self) -> None:
        tid = "tl-1"
        field = _make_field(IdDurationField, _BASE_VALUES, timeline_id=tid)
        scalars = _scalar_list(IdDuration, _BASE_VALUES, timeline_id=tid)
        _assert_predicate_parity("is_positive", field, scalars)

    def test_is_negative_parity(self) -> None:
        tid = "tl-1"
        field = _make_field(IdDurationField, _BASE_VALUES, timeline_id=tid)
        scalars = _scalar_list(IdDuration, _BASE_VALUES, timeline_id=tid)
        _assert_predicate_parity("is_negative", field, scalars)

    def test_to_float_parity(self) -> None:
        tid = "tl-1"
        field = _make_field(IdDurationField, _BASE_VALUES, timeline_id=tid)
        scalars = _scalar_list(IdDuration, _BASE_VALUES, timeline_id=tid)
        _assert_to_float_parity(field, scalars)

    def test_arithmetic_plus_parity(self) -> None:
        tid = "tl-3"
        a_vals = [1.0, -2.0, 3.5, 4.0]
        b_vals = [0.5, 1.0, 2.0, 4.0]
        a = _make_field(IdDurationField, a_vals, name="a", timeline_id=tid)
        b = _make_field(IdDurationField, b_vals, name="b", timeline_id=tid)
        a_s = _scalar_list(IdDuration, a_vals, timeline_id=tid)
        b_s = _scalar_list(IdDuration, b_vals, timeline_id=tid)
        result = a + b
        scalar_results = [(x + y).value for x, y in zip(a_s, b_s)]
        assert _pa_to_list(result._value_array()) == scalar_results

    def test_slice_parity(self) -> None:
        tid = "tl-1"
        field = _make_field(IdDurationField, _BASE_VALUES, timeline_id=tid)
        scalars = _scalar_list(IdDuration, _BASE_VALUES, timeline_id=tid)
        sliced_data = field.to_pyarrow().slice(2, 3)
        sliced = IdDurationField.from_field(
            (sliced_data, pa.field("slice", sliced_data.type)),
            unit=TimeUnit.seconds,
            number_type=NumberType.float,
            timeline_id=tid,
        )
        _assert_predicate_parity("is_positive", sliced, scalars[2:5])


# ---------------------------------------------------------------------------
# Null propagation through TimeScalarField data-shaped mirrors
# ---------------------------------------------------------------------------
#
# ``TimeScalarField._value_array()`` folds the outer struct's null mask
# through ``pc.if_else``, so every data-shaped predicate / arithmetic /
# conversion mirror returns ``None`` (not ``False`` / ``0.0``) for
# positions where the outer ``{value, numerator, denominator}`` struct
# is null.  These tests pin that behaviour against scalar dispatch — any
# future change that drops the outer null mask must turn them red.


class TestTimeScalarFieldNullPropagation:
    """Regression tests pinning element-wise null parity."""

    def test_coordinate_is_zero_propagates_null(self) -> None:
        field = _make_field(CoordinateField, _BASE_VALUES_WITH_NULL)
        scalars = _scalar_list(Coordinate, _BASE_VALUES_WITH_NULL)
        _assert_predicate_parity("is_zero", field, scalars)

    def test_coordinate_to_float_propagates_null(self) -> None:
        field = _make_field(CoordinateField, _BASE_VALUES_WITH_NULL)
        scalars = _scalar_list(Coordinate, _BASE_VALUES_WITH_NULL)
        _assert_to_float_parity(field, scalars)

    def test_coord_minus_coord_propagates_null(self) -> None:
        lhs_vals = [1.0, 2.0, 3.5, None, 5.0]
        rhs_vals = [0.5, None, 1.25, 2.0, 4.0]
        lhs = _make_field(CoordinateField, lhs_vals, name="lhs")
        rhs = _make_field(CoordinateField, rhs_vals, name="rhs")
        lhs_s = _scalar_list(Coordinate, lhs_vals)
        rhs_s = _scalar_list(Coordinate, rhs_vals)
        result = lhs - rhs
        expected = [
            None if left is None or right is None else (left - right).value
            for left, right in zip(lhs_s, rhs_s)
        ]
        assert _pa_to_list(result._value_array()) == expected

    def test_duration_is_positive_propagates_null(self) -> None:
        field = _make_field(DurationField, _BASE_VALUES_WITH_NULL)
        scalars = _scalar_list(Duration, _BASE_VALUES_WITH_NULL)
        _assert_predicate_parity("is_positive", field, scalars)
