"""Tests for the pydantic v2 → PyArrow translator.

See README.md in this directory for the test plan and gold-standard
expectations.  Each test maps to a numbered point under
"test_from_pydantic.py" in the README.
"""

from __future__ import annotations

from typing import Literal

import pyarrow as pa
import pytest
from pydantic import BaseModel, ConfigDict, computed_field

from timetoalign.core.enums import TimeUnit
from timetoalign.core.events import SpecificPitch
from timetoalign.core.fields import (
    derive_arrow_struct,
    register_value_projector,
)
from timetoalign.core.time import Coordinate
from timetoalign.storage.schema import make_coordinate_type


class TestCoordinateSchema:
    """pa.Schema derivation for Coordinate (test plan §1, §2)."""

    def test_matches_legacy_make_coordinate_type(self) -> None:
        """§1: derive_arrow_struct(Coordinate) == make_coordinate_type."""
        derived = derive_arrow_struct(Coordinate)
        legacy = make_coordinate_type(TimeUnit.seconds)
        assert derived.equals(legacy)

    def test_three_field_denormalised_shape(self) -> None:
        """§2: pa struct is {value, numerator, denominator} all nullable."""
        derived = derive_arrow_struct(Coordinate)
        assert derived.num_fields == 3
        assert derived.field("value").type == pa.float64()
        assert derived.field("value").nullable is True
        assert derived.field("numerator").type == pa.int64()
        assert derived.field("numerator").nullable is True
        assert derived.field("denominator").type == pa.int64()
        assert derived.field("denominator").nullable is True

    def test_unit_not_in_struct(self) -> None:
        """§2: Coordinate.unit is NOT in the pa.Schema (metadata-only)."""
        derived = derive_arrow_struct(Coordinate)
        names = [derived.field(i).name for i in range(derived.num_fields)]
        assert "unit" not in names


class TestSpecificPitchSchema:
    """pa.Schema derivation for SpecificPitch (test plan §3, §4, §6)."""

    def test_four_field_minimal_shape(self) -> None:
        """§3: derived struct is {step, alter, octave, cents}."""
        derived = derive_arrow_struct(SpecificPitch)
        assert derived.num_fields == 4
        names = {derived.field(i).name for i in range(derived.num_fields)}
        assert names == {"step", "alter", "octave", "cents"}

    def test_step_is_plain_string_not_dictionary(self) -> None:
        """§6: Literal[str, ...] -> pa.string(), NOT pa.dictionary."""
        derived = derive_arrow_struct(SpecificPitch)
        step_type = derived.field("step").type
        assert step_type == pa.string()
        assert not pa.types.is_dictionary(step_type)

    def test_alter_is_int64(self) -> None:
        derived = derive_arrow_struct(SpecificPitch)
        assert derived.field("alter").type == pa.int64()

    def test_octave_is_int64(self) -> None:
        derived = derive_arrow_struct(SpecificPitch)
        assert derived.field("octave").type == pa.int64()

    def test_cents_is_nullable_float64(self) -> None:
        derived = derive_arrow_struct(SpecificPitch)
        assert derived.field("cents").type == pa.float64()
        assert derived.field("cents").nullable is True

    def test_fifths_computed_field_excluded(self) -> None:
        """§4: @computed_field properties are NOT in the derived struct."""
        derived = derive_arrow_struct(SpecificPitch)
        names = [derived.field(i).name for i in range(derived.num_fields)]
        assert "fifths" not in names
        assert "midi_number" not in names
        assert "pitch_class" not in names


class TestTranslatorCaching:
    """Translator-level invariants (test plan §5)."""

    def test_struct_cached_per_class(self) -> None:
        """§5: repeated calls return the same StructType object."""
        a = derive_arrow_struct(SpecificPitch)
        b = derive_arrow_struct(SpecificPitch)
        # ``pa.struct(...)`` returns the same equal value but object
        # identity is guaranteed by lru_cache on the underlying field tuple.
        assert a.equals(b)
        # Verify the cache is hit (fields tuple identity preserved).
        from timetoalign.core.fields import _derive_arrow_fields

        f1 = _derive_arrow_fields(SpecificPitch)
        f2 = _derive_arrow_fields(SpecificPitch)
        assert f1 is f2


class TestUnsupportedTypes:
    """Pin the supported-scope contract (test plan §7)."""

    def test_bytes_field_rejected(self) -> None:
        """An unsupported atomic type (bytes) raises TypeError."""

        class _M(BaseModel):
            model_config = ConfigDict(frozen=True)
            data: bytes

        with pytest.raises(TypeError, match="Cannot derive PyArrow type"):
            derive_arrow_struct(_M)

    def test_literal_str_int_mixed_rejected(self) -> None:
        """Mixed-type Literal is rejected — pin the scope."""

        class _M(BaseModel):
            model_config = ConfigDict(frozen=True)
            x: Literal["a", 1]  # type: ignore[valid-type]

        with pytest.raises(TypeError, match="Mixed-type Literal"):
            derive_arrow_struct(_M)


class TestRegisterValueProjector:
    """The projector-registry extension hook (used by Coordinate)."""

    def test_projector_replaces_field_with_multi_struct(self) -> None:
        """A projector can expand one pydantic field into multiple pa.Fields."""

        class _M(BaseModel):
            model_config = ConfigDict(frozen=True)
            payload: float

        def _split(_cls, _name, _info):  # type: ignore[no-untyped-def]
            return [
                pa.field("re", pa.float64(), nullable=True),
                pa.field("im", pa.float64(), nullable=True),
            ]

        register_value_projector(_M, "payload", _split)
        derived = derive_arrow_struct(_M)
        assert derived.num_fields == 2
        names = [derived.field(i).name for i in range(derived.num_fields)]
        assert names == ["re", "im"]

    def test_projector_can_drop_field(self) -> None:
        """An empty-list projector removes the field from the pa.Schema."""

        class _M(BaseModel):
            model_config = ConfigDict(frozen=True)
            x: float
            y: float

        register_value_projector(_M, "y", lambda *a: [])  # type: ignore[no-untyped-call]
        derived = derive_arrow_struct(_M)
        names = [derived.field(i).name for i in range(derived.num_fields)]
        assert names == ["x"]


class TestComputedFieldFiltering:
    """A separate proof that @computed_field is filtered."""

    def test_only_model_fields_included(self) -> None:
        """A model with a @computed_field has it excluded from pa.Schema."""

        class _M(BaseModel):
            model_config = ConfigDict(frozen=True)
            x: int
            y: int

            @computed_field  # type: ignore[prop-decorator]
            @property
            def total(self) -> int:
                return self.x + self.y

        derived = derive_arrow_struct(_M)
        names = {derived.field(i).name for i in range(derived.num_fields)}
        assert names == {"x", "y"}
        assert "total" not in names
