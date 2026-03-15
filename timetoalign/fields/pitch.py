"""Pitch field hierarchy -- semantic columnar wrappers for pitch data.

``PitchField(SemanticField[StructField])`` is the abstract parent for all
pitch field types.  Concrete subclasses follow the ms3/DCML naming:

- ``GenericPitchField`` -- GP: pitch class only ``{pitch_class: int64}``
- ``SpelledPitchClassField`` -- SPC: spelled pitch class ``{gpc_str, acc, spc_int}``
- ``EnharmonicPitchField`` (alias ``MidiPitchField``) -- EP: MIDI ``{ep, epc}``
  Called "enharmonic" because it equates enharmonic equivalents (C♯ = D♭).
- ``SpecificPitchField`` (alias ``SpelledPitchField``) -- SP: full spelling
  ``{gpc_int, gpc_str, acc, spc_int, spc_str, sp, cents}``
  Called "specific" because it preserves the specific spelling.

All struct type constants are defined in ``fields.schemas`` -- the single
source of truth for schema definitions.
"""

from __future__ import annotations

import json
from abc import abstractmethod

import pyarrow as pa

from ..core.scalars.pitch import (
    GenericPitch,
    MidiPitch,
    SpelledPitch,
    SpelledPitchClass,
)
from .base import SemanticField, StructField

_TIMETOALIGN_KEY = b"timetoalign"


# ---------------------------------------------------------------------------
# PitchField (abstract parent)
# ---------------------------------------------------------------------------


class PitchField(SemanticField[StructField]):
    """Abstract parent for all pitch field types.

    Wraps a ``StructField`` and adds semantic pitch identity.
    Concrete subclasses must implement ``semantic_type``,
    ``metadata_dict``, ``__getitem__``, and ``from_field``.

    Satisfies ``PitchLike`` at the columnar level.

    Args:
        raw: The inner ``StructField`` holding pitch struct data.
    """

    def __init__(self, raw: StructField) -> None:
        super().__init__(raw)

    # -- SemanticTypeLike properties (abstract) ------------------------------

    @property
    @abstractmethod
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        ...

    @abstractmethod
    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract."""
        ...

    # -- element access (abstract) -------------------------------------------

    @abstractmethod
    def __getitem__(self, i: int) -> object:
        """Return the *i*-th pitch as a pitch scalar."""
        ...

    # -- construction (abstract) ---------------------------------------------

    @classmethod
    @abstractmethod
    def from_field(
        cls,
        source: (
            pa.Array
            | pa.ChunkedArray
            | StructField
            | pa.Field
            | tuple[pa.Array | None, pa.Field]
        ),
        *,
        name: str = "pitch",
    ) -> PitchField:
        """Construct a ``PitchField`` from various source types."""
        ...

    # -- serialisation helpers -----------------------------------------------

    def to_field(self) -> pa.Field:
        """Return a ``pa.Field`` with ``b"timetoalign"`` metadata injected."""
        meta_blob = json.dumps(self.metadata_dict()).encode("utf-8")
        existing = self._field.metadata or {}
        merged = {**existing, _TIMETOALIGN_KEY: meta_blob}
        return self._field.with_metadata(merged)


# ---------------------------------------------------------------------------
# GenericPitchField (GP)
# ---------------------------------------------------------------------------


class GenericPitchField(PitchField):
    """Semantic field for generic pitch columns (pitch class only).

    Wraps struct ``{pitch_class: int64}``
    (schema: ``GenericPitchSchema.schema``).

    Examples:
        >>> import pyarrow as pa
        >>> from timetoalign.fields.pitch import GenericPitchField
        >>> from timetoalign.fields.schemas import GenericPitchSchema
        >>> arr = pa.array([{"pitch_class": 0}], type=GenericPitchSchema.schema)
        >>> gpf = GenericPitchField.from_field(arr, name="generic_pitch")
        >>> gpf[0]
        GenericPitch(pitch_class=0)
    """

    @property
    def semantic_type(self) -> str:
        return "GenericPitch"

    def metadata_dict(self) -> dict[str, str]:
        return {"field_type": "GenericPitchField", "pitch_type": "generic"}

    def __getitem__(self, i: int) -> GenericPitch | None:
        raw_dict = self._raw[i]
        if raw_dict is None:
            return None
        return GenericPitch.from_row(raw_dict)

    @classmethod
    def from_field(cls, source, *, name: str = "generic_pitch") -> GenericPitchField:
        return _from_field_impl(cls, source, name)

    def __repr__(self) -> str:
        length = len(self) if not self.is_empty else 0
        return f"GenericPitchField(name={self.name!r}, type=generic, len={length})"


# ---------------------------------------------------------------------------
# SpelledPitchClassField (SPC)
# ---------------------------------------------------------------------------


class SpelledPitchClassField(PitchField):
    """Semantic field for spelled pitch class columns.

    Wraps struct ``{gpc_str: string, acc: int64, spc_int: int64}``
    (schema: ``SpelledPitchClassSchema.schema``).

    Examples:
        >>> import pyarrow as pa
        >>> from timetoalign.fields.pitch import SpelledPitchClassField
        >>> from timetoalign.fields.schemas import SpelledPitchClassSchema
        >>> arr = pa.array(
        ...     [{"gpc_str": "C", "acc": 0, "spc_int": 0}],
        ...     type=SpelledPitchClassSchema.schema,
        ... )
        >>> spcf = SpelledPitchClassField.from_field(arr, name="spelled_pitch_class")
        >>> spcf[0]
        SpelledPitchClass(C)
    """

    @property
    def semantic_type(self) -> str:
        return "SpelledPitchClass"

    def metadata_dict(self) -> dict[str, str]:
        return {"field_type": "SpelledPitchClassField", "pitch_type": "spelled_class"}

    def __getitem__(self, i: int) -> SpelledPitchClass | None:
        raw_dict = self._raw[i]
        if raw_dict is None:
            return None
        return SpelledPitchClass.from_row(raw_dict)

    @classmethod
    def from_field(
        cls, source, *, name: str = "spelled_pitch_class"
    ) -> SpelledPitchClassField:
        return _from_field_impl(cls, source, name)

    def __repr__(self) -> str:
        length = len(self) if not self.is_empty else 0
        return f"SpelledPitchClassField(name={self.name!r}, type=SpelledPitchClass, len={length})"


# ---------------------------------------------------------------------------
# EnharmonicPitchField (EP = MIDI pitch)
# ---------------------------------------------------------------------------


class EnharmonicPitchField(PitchField):
    """Semantic field for enharmonic (MIDI) pitch columns.

    Called "enharmonic" because it **equates** enharmonic equivalents:
    C♯4 and D♭4 both map to MIDI number 61.

    Wraps struct ``{ep: int64, epc: int64}``
    (schema: ``EnharmonicPitchSchema.schema``).

    Examples:
        >>> import pyarrow as pa
        >>> from timetoalign.fields.pitch import EnharmonicPitchField
        >>> from timetoalign.fields.schemas import EnharmonicPitchSchema
        >>> arr = pa.array([{"ep": 60, "epc": 0}], type=EnharmonicPitchSchema.schema)
        >>> pf = EnharmonicPitchField.from_field(arr, name="midi_pitch")
        >>> pf[0]
        MidiPitch(midi=60, pc=0)
    """

    @property
    def semantic_type(self) -> str:
        return "EnharmonicPitch"

    def metadata_dict(self) -> dict[str, str]:
        return {"field_type": "EnharmonicPitchField", "pitch_type": "enharmonic"}

    def __getitem__(self, i: int) -> MidiPitch | None:
        raw_dict = self._raw[i]
        if raw_dict is None:
            return None
        return MidiPitch.from_row(raw_dict)

    @classmethod
    def from_field(cls, source, *, name: str = "midi_pitch") -> EnharmonicPitchField:
        return _from_field_impl(cls, source, name)

    def __repr__(self) -> str:
        length = len(self) if not self.is_empty else 0
        return (
            f"EnharmonicPitchField(name={self.name!r}, type=enharmonic, len={length})"
        )


# Alias: MidiPitchField = EnharmonicPitchField
MidiPitchField = EnharmonicPitchField


# ---------------------------------------------------------------------------
# SpecificPitchField (SP = Spelled pitch)
# ---------------------------------------------------------------------------


class SpecificPitchField(PitchField):
    """Semantic field for specific (spelled) pitch columns.

    Called "specific" because it preserves the **specific** spelling:
    C♯4 ≠ D♭4.

    Wraps struct ``{gpc_int, gpc_str, acc, spc_int, spc_str, sp, cents}``
    (schema: ``SpecificPitchSchema.schema``).

    Examples:
        >>> import pyarrow as pa
        >>> from timetoalign.fields.pitch import SpecificPitchField
        >>> from timetoalign.fields.schemas import SpecificPitchSchema
        >>> arr = pa.array(
        ...     [{"gpc_int": 0, "gpc_str": "C", "acc": 0, "spc_int": 0,
        ...       "spc_str": "C", "sp": "C4", "cents": 0.0}],
        ...     type=SpecificPitchSchema.schema,
        ... )
        >>> spf = SpecificPitchField.from_field(arr, name="spelled_pitch")
        >>> spf[0]
        SpelledPitch(C4)
    """

    @property
    def semantic_type(self) -> str:
        return "SpecificPitch"

    def metadata_dict(self) -> dict[str, str]:
        return {"field_type": "SpecificPitchField", "pitch_type": "specific"}

    def __getitem__(self, i: int) -> SpelledPitch | None:
        raw_dict = self._raw[i]
        if raw_dict is None:
            return None
        return SpelledPitch.from_row(raw_dict)

    @classmethod
    def from_field(cls, source, *, name: str = "spelled_pitch") -> SpecificPitchField:
        return _from_field_impl(cls, source, name)

    def __repr__(self) -> str:
        length = len(self) if not self.is_empty else 0
        return f"SpecificPitchField(name={self.name!r}, type=specific, len={length})"


# Alias: SpelledPitchField = SpecificPitchField
SpelledPitchField = SpecificPitchField


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _from_field_impl(cls, source, name: str):
    """Shared from_field construction logic for all concrete PitchField subclasses."""
    if isinstance(source, tuple):
        data, pa_field = source
        return cls(StructField(data, pa_field))
    if isinstance(source, pa.Field):
        return cls(StructField(None, source))
    if isinstance(source, StructField):
        return cls(source)
    if isinstance(source, (pa.Array, pa.ChunkedArray)):
        pa_field = pa.field(name, source.type)
        return cls(StructField(source, pa_field))
    raise TypeError(
        f"Unsupported source type for {cls.__name__}.from_field: {type(source).__name__}"
    )
