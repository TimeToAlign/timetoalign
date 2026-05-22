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
