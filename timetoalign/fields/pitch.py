"""Pitch field hierarchy -- semantic columnar wrappers for pitch data.

``PitchField(SemanticField[StructField])`` is the abstract parent for all
pitch field types.  Concrete subclasses:

- ``GenericPitchField`` -- pitch class only ``{pitch_class: int64}``
- ``SpelledPitchClassField`` -- spelled pitch class ``{gpc_str, acc, spc_int}``
- ``SpecificPitchField`` (alias ``MidiPitchField``) -- MIDI pitch ``{ep, epc}``
- ``EnharmonicPitchField`` (alias ``SpelledPitchField``) -- full spelling
  ``{gpc_int, gpc_str, acc, spc_int, spc_str, sp, cents}``

All follow the ``CoordinateField`` composition pattern exactly.
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
        """Return the *i*-th pitch as a pitch scalar.

        Args:
            i: Zero-based index.

        Returns:
            A pitch scalar instance, or ``None`` for null entries.
        """
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
        """Construct a ``PitchField`` from various source types.

        Args:
            source: The data source.
            name: Column name used when *source* is a bare ``pa.Array``.

        Returns:
            A new ``PitchField`` subclass instance.
        """
        ...

    # -- serialisation helpers -----------------------------------------------

    def to_field(self) -> pa.Field:
        """Return a ``pa.Field`` with ``b"timetoalign"`` metadata injected.

        Returns:
            A ``pa.Field`` with enriched metadata.
        """
        meta_blob = json.dumps(self.metadata_dict()).encode("utf-8")
        existing = self._field.metadata or {}
        merged = {**existing, _TIMETOALIGN_KEY: meta_blob}
        return self._field.with_metadata(merged)


# ---------------------------------------------------------------------------
# GenericPitchField
# ---------------------------------------------------------------------------


class GenericPitchField(PitchField):
    """Semantic field for generic pitch columns (pitch class only).

    Wraps a ``StructField`` containing the ``generic_pitch`` struct
    ``{pitch_class: int64}`` and adds semantic identity.

    Args:
        raw: The inner ``StructField`` holding generic pitch struct data.

    Examples:
        >>> import pyarrow as pa
        >>> from timetoalign.fields.pitch import GenericPitchField
        >>> arr = pa.array(
        ...     [{"pitch_class": 0}],
        ...     type=pa.struct([pa.field("pitch_class", pa.int64())]),
        ... )
        >>> gpf = GenericPitchField.from_field(arr, name="generic_pitch")
        >>> gpf[0]
        GenericPitch(pitch_class=0)
    """

    def __init__(self, raw: StructField) -> None:
        super().__init__(raw)

    # -- SemanticTypeLike properties -----------------------------------------

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "GenericPitch"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract.

        Returns:
            Dict with ``field_type`` and ``pitch_type`` keys.
        """
        return {
            "field_type": "GenericPitchField",
            "pitch_type": "generic",
        }

    # -- element access ------------------------------------------------------

    def __getitem__(self, i: int) -> GenericPitch | None:
        """Return the *i*-th pitch as a ``GenericPitch`` scalar.

        Args:
            i: Zero-based index.

        Returns:
            A ``GenericPitch`` instance, or ``None`` for null entries.

        Raises:
            TypeError: If the field is schema-only (no data).
            IndexError: If *i* is out of range.
        """
        raw_dict = self._raw[i]
        if raw_dict is None:
            return None
        pc = raw_dict.get("pitch_class")
        if pc is None:
            return None
        return GenericPitch(pitch_class=int(pc))

    # -- construction --------------------------------------------------------

    @classmethod
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
        name: str = "generic_pitch",
    ) -> GenericPitchField:
        """Construct a ``GenericPitchField`` from various source types.

        Accepted source forms:

        1. ``pa.Array`` (struct array).
        2. ``StructField``.
        3. ``pa.Field`` (schema-only, no data).
        4. ``tuple[pa.Array | None, pa.Field]``.

        Args:
            source: The data source (see above).
            name: Column name used when *source* is a bare ``pa.Array``.

        Returns:
            A new ``GenericPitchField``.

        Raises:
            TypeError: If the source type is not recognised.
        """
        return _from_field_impl(cls, source, name, "GenericPitchField")

    def __repr__(self) -> str:
        length = len(self) if not self.is_empty else 0
        return f"GenericPitchField(name={self.name!r}, type=generic, len={length})"


# ---------------------------------------------------------------------------
# SpelledPitchClassField
# ---------------------------------------------------------------------------


class SpelledPitchClassField(PitchField):
    """Semantic field for spelled pitch class columns.

    Wraps a ``StructField`` containing the ``spelled_pitch_class`` struct
    ``{gpc_str: string, acc: int64, spc_int: int64}`` and adds semantic identity.

    Args:
        raw: The inner ``StructField`` holding spelled pitch class struct data.

    Examples:
        >>> import pyarrow as pa
        >>> from timetoalign.fields.pitch import SpelledPitchClassField
        >>> arr = pa.array(
        ...     [{"gpc_str": "C", "acc": 0, "spc_int": 0}],
        ...     type=pa.struct([
        ...         pa.field("gpc_str", pa.string()),
        ...         pa.field("acc", pa.int64()),
        ...         pa.field("spc_int", pa.int64()),
        ...     ]),
        ... )
        >>> spcf = SpelledPitchClassField.from_field(arr, name="spelled_pitch_class")
        >>> spcf[0]
        SpelledPitchClass(C)
    """

    def __init__(self, raw: StructField) -> None:
        super().__init__(raw)

    # -- SemanticTypeLike properties -----------------------------------------

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "SpelledPitchClass"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract.

        Returns:
            Dict with ``field_type`` and ``pitch_type`` keys.
        """
        return {
            "field_type": "SpelledPitchClassField",
            "pitch_type": "spelled_class",
        }

    # -- element access ------------------------------------------------------

    def __getitem__(self, i: int) -> SpelledPitchClass | None:
        """Return the *i*-th pitch as a ``SpelledPitchClass`` scalar.

        Args:
            i: Zero-based index.

        Returns:
            A ``SpelledPitchClass`` instance, or ``None`` for null entries.

        Raises:
            TypeError: If the field is schema-only (no data).
            IndexError: If *i* is out of range.
        """
        raw_dict = self._raw[i]
        if raw_dict is None:
            return None
        step = raw_dict.get("gpc_str")
        if step is None:
            return None
        alter = raw_dict.get("acc", 0) or 0
        fifths = raw_dict.get("spc_int", 0) or 0
        return SpelledPitchClass(
            step=str(step),
            alter=int(alter),
            fifths=int(fifths),
        )

    # -- construction --------------------------------------------------------

    @classmethod
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
        name: str = "spelled_pitch_class",
    ) -> SpelledPitchClassField:
        """Construct a ``SpelledPitchClassField`` from various source types.

        Accepted source forms:

        1. ``pa.Array`` (struct array).
        2. ``StructField``.
        3. ``pa.Field`` (schema-only, no data).
        4. ``tuple[pa.Array | None, pa.Field]``.

        Args:
            source: The data source (see above).
            name: Column name used when *source* is a bare ``pa.Array``.

        Returns:
            A new ``SpelledPitchClassField``.

        Raises:
            TypeError: If the source type is not recognised.
        """
        return _from_field_impl(cls, source, name, "SpelledPitchClassField")

    def __repr__(self) -> str:
        length = len(self) if not self.is_empty else 0
        return f"SpelledPitchClassField(name={self.name!r}, type=spelled_class, len={length})"


# ---------------------------------------------------------------------------
# SpecificPitchField (renamed from PitchField)
# ---------------------------------------------------------------------------


class SpecificPitchField(PitchField):
    """Semantic field for MIDI pitch columns.

    Wraps a ``StructField`` containing the ``midi_pitch`` struct
    ``{ep: int64, epc: int64}`` and adds semantic identity.

    Satisfies ``PitchLike`` at the columnar level.

    Args:
        raw: The inner ``StructField`` holding MIDI pitch struct data.

    Examples:
        >>> import pyarrow as pa
        >>> from timetoalign.fields.pitch import SpecificPitchField
        >>> arr = pa.array(
        ...     [{"ep": 60, "epc": 0}],
        ...     type=pa.struct([
        ...         pa.field("ep", pa.int64()),
        ...         pa.field("epc", pa.int64()),
        ...     ]),
        ... )
        >>> pf = SpecificPitchField.from_field(arr, name="midi_pitch")
        >>> pf[0]
        MidiPitch(midi_number=60, pitch_class=0)
    """

    def __init__(self, raw: StructField) -> None:
        super().__init__(raw)

    # -- SemanticTypeLike properties -----------------------------------------

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "MidiPitch"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract.

        Returns:
            Dict with ``field_type`` and ``pitch_type`` keys.
        """
        return {
            "field_type": "SpecificPitchField",
            "pitch_type": "midi",
        }

    # -- element access ------------------------------------------------------

    def __getitem__(self, i: int) -> MidiPitch | None:
        """Return the *i*-th pitch as a ``MidiPitch`` scalar.

        Args:
            i: Zero-based index.

        Returns:
            A ``MidiPitch`` instance, or ``None`` for null entries (rests).

        Raises:
            TypeError: If the field is schema-only (no data).
            IndexError: If *i* is out of range.
        """
        raw_dict = self._raw[i]
        if raw_dict is None:
            return None
        ep = raw_dict.get("ep")
        epc = raw_dict.get("epc")
        if ep is None or epc is None:
            return None
        return MidiPitch(midi_number=int(ep), pitch_class=int(epc))

    # -- construction --------------------------------------------------------

    @classmethod
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
        name: str = "midi_pitch",
    ) -> SpecificPitchField:
        """Construct a ``SpecificPitchField`` from various source types.

        Accepted source forms:

        1. ``pa.Array`` (struct array).
        2. ``StructField``.
        3. ``pa.Field`` (schema-only, no data).
        4. ``tuple[pa.Array | None, pa.Field]``.

        Args:
            source: The data source (see above).
            name: Column name used when *source* is a bare ``pa.Array``.

        Returns:
            A new ``SpecificPitchField``.

        Raises:
            TypeError: If the source type is not recognised.
        """
        return _from_field_impl(cls, source, name, "SpecificPitchField")

    def __repr__(self) -> str:
        length = len(self) if not self.is_empty else 0
        return f"SpecificPitchField(name={self.name!r}, type=midi, len={length})"


# Alias for backward compatibility and convenience
MidiPitchField = SpecificPitchField


# ---------------------------------------------------------------------------
# EnharmonicPitchField (renamed from SpelledPitchField)
# ---------------------------------------------------------------------------


class EnharmonicPitchField(PitchField):
    """Semantic field for spelled pitch columns.

    Wraps a ``StructField`` containing the ``spelled_pitch`` struct
    ``{gpc_int, gpc_str, acc, spc_int, spc_str, sp, cents}``.

    Args:
        raw: The inner ``StructField`` holding spelled pitch struct data.

    Examples:
        >>> import pyarrow as pa
        >>> from timetoalign.fields.pitch import EnharmonicPitchField
        >>> arr = pa.array(
        ...     [{"gpc_int": 0, "gpc_str": "C", "acc": 0, "spc_int": 0,
        ...       "spc_str": "C", "sp": "C4", "cents": 0.0}],
        ...     type=pa.struct([
        ...         pa.field("gpc_int", pa.int64()),
        ...         pa.field("gpc_str", pa.string()),
        ...         pa.field("acc", pa.int64()),
        ...         pa.field("spc_int", pa.int64()),
        ...         pa.field("spc_str", pa.string()),
        ...         pa.field("sp", pa.string()),
        ...         pa.field("cents", pa.float64()),
        ...     ]),
        ... )
        >>> spf = EnharmonicPitchField.from_field(arr, name="spelled_pitch")
        >>> spf[0]
        SpelledPitch(C4)
    """

    def __init__(self, raw: StructField) -> None:
        super().__init__(raw)

    # -- SemanticTypeLike properties -----------------------------------------

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "SpelledPitch"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract.

        Returns:
            Dict with ``field_type`` and ``pitch_type`` keys.
        """
        return {
            "field_type": "EnharmonicPitchField",
            "pitch_type": "spelled",
        }

    # -- element access ------------------------------------------------------

    def __getitem__(self, i: int) -> SpelledPitch | None:
        """Return the *i*-th pitch as a ``SpelledPitch`` scalar.

        Args:
            i: Zero-based index.

        Returns:
            A ``SpelledPitch`` instance, or ``None`` for null entries.

        Raises:
            TypeError: If the field is schema-only (no data).
            IndexError: If *i* is out of range.
        """
        raw_dict = self._raw[i]
        if raw_dict is None:
            return None

        step = raw_dict.get("gpc_str")
        if step is None:
            return None

        alter = raw_dict.get("acc", 0) or 0
        fifths = raw_dict.get("spc_int", 0) or 0
        cents = raw_dict.get("cents", 0.0) or 0.0

        # Extract octave from 'sp' string (e.g. "C4" -> 4)
        sp = raw_dict.get("sp", "")
        octave = _parse_octave(sp, step)

        return SpelledPitch(
            step=str(step),
            alter=int(alter),
            octave=octave,
            fifths=int(fifths),
            cents=float(cents),
        )

    # -- construction --------------------------------------------------------

    @classmethod
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
        name: str = "spelled_pitch",
    ) -> EnharmonicPitchField:
        """Construct an ``EnharmonicPitchField`` from various source types.

        Accepted source forms:

        1. ``pa.Array`` (struct array).
        2. ``StructField``.
        3. ``pa.Field`` (schema-only, no data).
        4. ``tuple[pa.Array | None, pa.Field]``.

        Args:
            source: The data source (see above).
            name: Column name used when *source* is a bare ``pa.Array``.

        Returns:
            A new ``EnharmonicPitchField``.

        Raises:
            TypeError: If the source type is not recognised.
        """
        return _from_field_impl(cls, source, name, "EnharmonicPitchField")

    def __repr__(self) -> str:
        length = len(self) if not self.is_empty else 0
        return f"EnharmonicPitchField(name={self.name!r}, type=spelled, len={length})"


# Backward compatibility alias
SpelledPitchField = EnharmonicPitchField


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _from_field_impl(cls, source, name: str, class_name: str):
    """Shared from_field construction logic for all concrete PitchField subclasses.

    Args:
        cls: The concrete class to construct.
        source: The data source.
        name: Default column name for bare array sources.
        class_name: Class name used in error messages.

    Returns:
        A new instance of *cls*.

    Raises:
        TypeError: If the source type is not recognised.
    """
    # -- form 4: tuple -------------------------------------------------------
    if isinstance(source, tuple):
        data, pa_field = source
        struct_field = StructField(data, pa_field)
        return cls(struct_field)

    # -- form 3: pa.Field (schema-only) --------------------------------------
    if isinstance(source, pa.Field):
        struct_field = StructField(None, source)
        return cls(struct_field)

    # -- form 2: StructField -------------------------------------------------
    if isinstance(source, StructField):
        return cls(source)

    # -- form 1: pa.Array / pa.ChunkedArray ----------------------------------
    if isinstance(source, (pa.Array, pa.ChunkedArray)):
        pa_field = pa.field(name, source.type)
        struct_field = StructField(source, pa_field)
        return cls(struct_field)

    raise TypeError(
        f"Unsupported source type for {class_name}.from_field: {type(source).__name__}"
    )


def _parse_octave(sp: str | None, step: str) -> int:
    """Extract octave number from a spelled pitch string like ``"C4"``.

    Args:
        sp: The spelled pitch string (e.g. ``"C4"``, ``"Bb3"``).
        step: The step letter (e.g. ``"C"``, ``"B"``).

    Returns:
        The octave number, defaulting to 4 if parsing fails.
    """
    if not sp:
        return 4
    # The octave is typically the last character(s) that form an integer
    # e.g. "C4" -> 4, "Bb3" -> 3, "F#5" -> 5
    try:
        # Walk backwards to find the numeric suffix
        idx = len(sp)
        while idx > 0 and (sp[idx - 1].isdigit() or sp[idx - 1] == "-"):
            idx -= 1
        if idx < len(sp):
            return int(sp[idx:])
    except (ValueError, IndexError):
        pass
    return 4
