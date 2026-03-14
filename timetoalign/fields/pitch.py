"""PitchField and SpelledPitchField -- semantic columnar wrappers for pitch data.

``PitchField(SemanticField[StructField])`` wraps the ``midi_pitch``
struct column ``{ep: int64, epc: int64}`` from ``NoteEventData``.

``SpelledPitchField(SemanticField[StructField])`` wraps the
``spelled_pitch`` struct column
``{gpc_int, gpc_str, acc, spc_int, spc_str, sp, cents}``.

Both follow the ``CoordinateField`` composition pattern exactly.
"""

from __future__ import annotations

import json

import pyarrow as pa

from ..core.scalars.pitch import MidiPitch, SpelledPitch
from .base import SemanticField, StructField

_TIMETOALIGN_KEY = b"timetoalign"


class PitchField(SemanticField[StructField]):
    """Semantic field for MIDI pitch columns.

    Wraps a ``StructField`` containing the ``midi_pitch`` struct
    ``{ep: int64, epc: int64}`` and adds semantic identity.

    Satisfies ``PitchLike`` at the columnar level.

    Args:
        raw: The inner ``StructField`` holding MIDI pitch struct data.

    Examples:
        >>> import pyarrow as pa
        >>> from timetoalign.fields.pitch import PitchField
        >>> arr = pa.array(
        ...     [{"ep": 60, "epc": 0}],
        ...     type=pa.struct([
        ...         pa.field("ep", pa.int64()),
        ...         pa.field("epc", pa.int64()),
        ...     ]),
        ... )
        >>> pf = PitchField.from_field(arr, name="midi_pitch")
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
            "field_type": "PitchField",
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
    ) -> PitchField:
        """Construct a ``PitchField`` from various source types.

        Accepted source forms:

        1. ``pa.Array`` (struct array).
        2. ``StructField``.
        3. ``pa.Field`` (schema-only, no data).
        4. ``tuple[pa.Array | None, pa.Field]``.

        Args:
            source: The data source (see above).
            name: Column name used when *source* is a bare ``pa.Array``.

        Returns:
            A new ``PitchField``.

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
            f"Unsupported source type for PitchField.from_field: {type(source).__name__}"
        )

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

    def __repr__(self) -> str:
        length = len(self) if not self.is_empty else 0
        return f"PitchField(name={self.name!r}, type=midi, len={length})"


class SpelledPitchField(SemanticField[StructField]):
    """Semantic field for spelled pitch columns.

    Wraps a ``StructField`` containing the ``spelled_pitch`` struct
    ``{gpc_int, gpc_str, acc, spc_int, spc_str, sp, cents}``.

    Args:
        raw: The inner ``StructField`` holding spelled pitch struct data.

    Examples:
        >>> import pyarrow as pa
        >>> from timetoalign.fields.pitch import SpelledPitchField
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
        >>> spf = SpelledPitchField.from_field(arr, name="spelled_pitch")
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
            "field_type": "SpelledPitchField",
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
    ) -> SpelledPitchField:
        """Construct a ``SpelledPitchField`` from various source types.

        Accepted source forms:

        1. ``pa.Array`` (struct array).
        2. ``StructField``.
        3. ``pa.Field`` (schema-only, no data).
        4. ``tuple[pa.Array | None, pa.Field]``.

        Args:
            source: The data source (see above).
            name: Column name used when *source* is a bare ``pa.Array``.

        Returns:
            A new ``SpelledPitchField``.

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
            f"Unsupported source type for SpelledPitchField.from_field: {type(source).__name__}"
        )

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

    def __repr__(self) -> str:
        length = len(self) if not self.is_empty else 0
        return f"SpelledPitchField(name={self.name!r}, type=spelled, len={length})"


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
