"""Pitch field hierarchy -- unified semantic columnar wrappers for pitch data.

``PitchField(SemanticField[StructField])`` is the unified pitch field that
replaces the four separate concrete classes.  It wraps a ``StructField``
backed by ``PitchSpaceSchema`` (``struct<value: int64, octave: int64>``)
and uses metadata to determine the pitch type.

Supported pitch types (via keyword arguments):

- ``sp``  -- Specific Pitch (fifths space, specific level)
- ``spc`` -- Spelled Pitch Class (fifths space, class level)
- ``ep``  -- Enharmonic Pitch (semitones space, specific level)
- ``epc`` -- Enharmonic Pitch Class (semitones space, class level)
- ``gp``  -- Generic Pitch (steps space, specific level)
- ``gpc`` -- Generic Pitch Class (steps space, class level)

Old class names (``GenericPitchField``, ``SpelledPitchClassField``,
``EnharmonicPitchField``, ``SpecificPitchField``) are kept as deprecated
aliases for backward compatibility.
"""

from __future__ import annotations

import json
from typing import Any

import pyarrow as pa

from ..core.scalars.pitch import (
    _STEP_TO_GPC,
    _STEP_TO_SEMITONE,
    EnharmonicPitch,
    GenericPitch,
    GenericPitchClass,
    SpelledPitch,
    SpelledPitchClass,
)
from .base import SemanticField, StructField
from .schemas import PitchSpaceSchema

_TIMETOALIGN_KEY = b"timetoalign"

# Mapping from type keyword to (space, level) metadata
_TYPE_METADATA: dict[str, dict[str, str]] = {
    "sp": {"space": "fifths", "level": "specific"},
    "spc": {"space": "fifths", "level": "class"},
    "ep": {"space": "semitones", "level": "specific"},
    "epc": {"space": "semitones", "level": "class"},
    "gp": {"space": "steps", "level": "specific"},
    "gpc": {"space": "steps", "level": "class"},
}

# All valid pitch type keywords
_PITCH_TYPES = frozenset(_TYPE_METADATA.keys())


# ---------------------------------------------------------------------------
# PitchField (unified)
# ---------------------------------------------------------------------------


class PitchField(SemanticField[StructField]):
    """Unified pitch field wrapping PitchSpaceSchema.

    Supports two modes:

    **Blueprint mode** -- for deferred resolution via ``EventData.get_field()``:

    .. code-block:: python

        pitch = PitchField(spc="column_name")
        events.get_field(pitch)  # resolves & caches

    **Live mode** -- standalone construction with data:

    .. code-block:: python

        pf = PitchField.from_raw(ep=[60, 64, 67])
        pf[0]  # -> MidiPitch(midi=60, pc=0)

    Args:
        raw: The inner ``StructField`` holding pitch struct data.
        pitch_type: The pitch type keyword (``"sp"``, ``"spc"``, ``"ep"``,
            ``"epc"``, ``"gp"``, ``"gpc"``).

    For blueprint mode, pass a single keyword arg with a column name string::

        PitchField(ep="midi_pitch_col")
    """

    def __init__(
        self,
        raw: StructField | None = None,
        pitch_type: str | None = None,
        **kwargs: str | pa.Array | list,
    ) -> None:
        # Blueprint mode: PitchField(ep="column_name")
        if raw is None:
            type_keys = set(kwargs.keys()) & _PITCH_TYPES
            if len(type_keys) != 1:
                raise ValueError(
                    f"PitchField blueprint requires exactly one pitch type keyword "
                    f"(sp/spc/ep/epc/gp/gpc), got: {set(kwargs.keys())}"
                )
            self._pitch_type = type_keys.pop()
            self._blueprint_column = kwargs[self._pitch_type]
            if not isinstance(self._blueprint_column, str):
                raise TypeError(
                    f"Blueprint mode requires a column name (str), got {type(self._blueprint_column).__name__}"
                )
            # Create a dummy empty StructField for the base class
            dummy_field = pa.field(self._blueprint_column, PitchSpaceSchema.schema)
            dummy_raw = StructField(None, dummy_field)
            super().__init__(dummy_raw)
            self._is_blueprint = True
            return

        # Live mode: PitchField(raw_struct_field, pitch_type="ep")
        if pitch_type is None:
            raise ValueError("pitch_type is required for live PitchField construction")
        if pitch_type not in _PITCH_TYPES:
            raise ValueError(
                f"Invalid pitch_type {pitch_type!r}. Must be one of: {sorted(_PITCH_TYPES)}"
            )
        super().__init__(raw)
        self._pitch_type = pitch_type
        self._blueprint_column: str | None = None
        self._is_blueprint = False

    @property
    def pitch_type(self) -> str:
        """The pitch type keyword (sp/spc/ep/epc/gp/gpc)."""
        return self._pitch_type

    @property
    def space(self) -> str:
        """The pitch space: 'fifths', 'semitones', or 'steps'."""
        return _TYPE_METADATA[self._pitch_type]["space"]

    @property
    def level(self) -> str:
        """The pitch level: 'specific' or 'class'."""
        return _TYPE_METADATA[self._pitch_type]["level"]

    @property
    def is_blueprint(self) -> bool:
        """Whether this is a blueprint (deferred) field."""
        return self._is_blueprint

    # -- SemanticTypeLike properties -----------------------------------------

    @property
    def semantic_type(self) -> str:
        return "Pitch"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "PitchField",
            "pitch_type": self._pitch_type,
            "space": self.space,
            "level": self.level,
        }

    # -- element access ------------------------------------------------------

    def __getitem__(self, i: int) -> Any:
        """Return the *i*-th pitch as a scalar appropriate to the pitch type."""
        if self._is_blueprint:
            raise TypeError(
                "Cannot index a blueprint PitchField — resolve via EventData.get_field() first"
            )
        raw_dict = self._raw[i]
        if raw_dict is None:
            return None
        # Detect whether this is PitchSpaceSchema or a legacy schema
        if "value" in raw_dict:
            return _scalar_from_pitch_space(raw_dict, self._pitch_type)
        return _scalar_from_legacy_schema(raw_dict, self._pitch_type)

    # -- construction --------------------------------------------------------

    @classmethod
    def from_raw(cls, **kwargs: list[int] | list[int | None] | pa.Array) -> PitchField:
        """Construct a live PitchField from raw values.

        Pass exactly one keyword argument matching a pitch type:

        - ``ep=[60, 64, 67]`` — MIDI numbers (semitones, specific)
        - ``epc=[0, 4, 7]`` — pitch class 0-11 (semitones, class)
        - ``spc=[0, 4, -1]`` — fifths position (fifths, class)
        - ``sp=[(0, 4), (4, 4)]`` — (fifths, octave) tuples (fifths, specific)
        - ``gp=[(0, 4), (2, 4)]`` — (step, octave) tuples (steps, specific)
        - ``gpc=[0, 2, 4]`` — diatonic step 0-6 (steps, class)

        For specific types (sp, ep, gp), if a plain list of ints is given,
        octave is derived automatically where possible.
        """
        type_keys = set(kwargs.keys()) & _PITCH_TYPES
        if len(type_keys) != 1:
            raise ValueError(
                f"from_raw() requires exactly one pitch type keyword, got: {set(kwargs.keys())}"
            )
        pitch_type = type_keys.pop()
        values = kwargs[pitch_type]

        if isinstance(values, (pa.Array, pa.ChunkedArray)):
            # Already a PyArrow array — wrap directly
            if pa.types.is_struct(values.type):
                pa_field = pa.field("pitch", values.type)
                return cls(StructField(values, pa_field), pitch_type=pitch_type)

        # Build struct arrays from Python values
        rows = _values_to_pitch_space_rows(values, pitch_type)
        arr = pa.array(rows, type=PitchSpaceSchema.schema)
        pa_field = pa.field("pitch", PitchSpaceSchema.schema)
        return cls(StructField(arr, pa_field), pitch_type=pitch_type)

    @classmethod
    def from_labels(cls, labels: list[str], *, name: str = "pitch") -> PitchField:
        """Construct from pitch label strings (e.g. ``["C4", "E4", "G4"]``).

        Parses each label via ``SpelledPitch.from_label()`` and stores
        as SP (fifths space, specific level).
        """
        rows = []
        for lbl in labels:
            sp = SpelledPitch.from_label(lbl)
            rows.append({"value": sp.fifths, "octave": sp.octave})
        arr = pa.array(rows, type=PitchSpaceSchema.schema)
        pa_field = pa.field(name, PitchSpaceSchema.schema)
        return cls(StructField(arr, pa_field), pitch_type="sp")

    @classmethod
    def from_field(
        cls, source: Any, *, name: str = "pitch", pitch_type: str | None = None
    ) -> PitchField:
        """Construct a PitchField from various source types.

        Handles pa.Array, StructField, pa.Field, and (data, pa.Field) tuples.
        For legacy schemas, automatically detects the pitch type from the
        struct layout.
        """
        if isinstance(source, tuple):
            data, pa_field = source
            resolved_type = pitch_type or _detect_pitch_type(pa_field)
            return cls(StructField(data, pa_field), pitch_type=resolved_type)

        if isinstance(source, pa.Field):
            resolved_type = pitch_type or _detect_pitch_type(source)
            return cls(StructField(None, source), pitch_type=resolved_type)

        if isinstance(source, StructField):
            resolved_type = pitch_type or _detect_pitch_type(source.field)
            return cls(source, pitch_type=resolved_type)

        if isinstance(source, (pa.Array, pa.ChunkedArray)):
            resolved_type = pitch_type or _detect_pitch_type_from_struct(source.type)
            pa_field = pa.field(name, source.type)
            return cls(StructField(source, pa_field), pitch_type=resolved_type)

        raise TypeError(
            f"Unsupported source type for PitchField.from_field: {type(source).__name__}"
        )

    # -- conversion ----------------------------------------------------------

    def to(self, target_type: str) -> PitchField:
        """Convert to a different pitch type.

        Only information-losing conversions are permitted:
        - sp -> spc, ep, epc, gp, gpc
        - spc -> epc, gpc
        - ep -> epc
        - gp -> gpc
        """
        if target_type not in _PITCH_TYPES:
            raise ValueError(f"Invalid target type {target_type!r}")
        if target_type == self._pitch_type:
            return self
        if self._is_blueprint or self.is_empty:
            raise TypeError("Cannot convert a blueprint or empty PitchField")
        new_rows = _convert_pitch_space(self, target_type)
        arr = pa.array(new_rows, type=PitchSpaceSchema.schema)
        pa_field = pa.field(self.name, PitchSpaceSchema.schema)
        return PitchField(StructField(arr, pa_field), pitch_type=target_type)

    # -- serialisation -------------------------------------------------------

    def to_field(self) -> pa.Field:
        """Return a ``pa.Field`` with ``b"timetoalign"`` metadata injected."""
        meta_blob = json.dumps(self.metadata_dict()).encode("utf-8")
        existing = self._field.metadata or {}
        merged = {**existing, _TIMETOALIGN_KEY: meta_blob}
        return self._field.with_metadata(merged)

    def __repr__(self) -> str:
        if self._is_blueprint:
            return f"PitchField({self._pitch_type}={self._blueprint_column!r}, blueprint=True)"
        length = len(self) if not self.is_empty else 0
        return f"PitchField(name={self.name!r}, type={self._pitch_type}, len={length})"


# ---------------------------------------------------------------------------
# Deprecated aliases (backward compat)
# ---------------------------------------------------------------------------


class GenericPitchField(PitchField):
    """Deprecated: use ``PitchField(epc=...)`` instead.

    Note: old GenericPitch (0-11) is EPC, not GPC.
    """

    _default_column: str = "generic_pitch"

    @classmethod
    def from_field(
        cls, source: Any, *, name: str = "generic_pitch", pitch_type: str | None = None
    ) -> GenericPitchField:
        pf = PitchField.from_field(source, name=name, pitch_type=pitch_type or "epc")
        pf.__class__ = cls
        return pf  # type: ignore[return-value]


class SpelledPitchClassField(PitchField):
    """Deprecated: use ``PitchField(spc=...)`` instead."""

    _default_column: str = "spelled_pitch_class"

    @classmethod
    def from_field(
        cls,
        source: Any,
        *,
        name: str = "spelled_pitch_class",
        pitch_type: str | None = None,
    ) -> SpelledPitchClassField:
        pf = PitchField.from_field(source, name=name, pitch_type=pitch_type or "spc")
        pf.__class__ = cls
        return pf  # type: ignore[return-value]


class EnharmonicPitchField(PitchField):
    """Deprecated: use ``PitchField(ep=...)`` instead."""

    _default_column: str = "midi_pitch"

    @classmethod
    def from_field(
        cls, source: Any, *, name: str = "midi_pitch", pitch_type: str | None = None
    ) -> EnharmonicPitchField:
        pf = PitchField.from_field(source, name=name, pitch_type=pitch_type or "ep")
        pf.__class__ = cls
        return pf  # type: ignore[return-value]

    @classmethod
    def from_midi_numbers(
        cls, midi_numbers: list[int], *, name: str = "midi_pitch"
    ) -> EnharmonicPitchField:
        """Construct from MIDI note numbers."""
        pf = PitchField.from_raw(ep=midi_numbers)
        pf.__class__ = cls
        return pf  # type: ignore[return-value]


class SpecificPitchField(PitchField):
    """Deprecated: use ``PitchField(sp=...)`` instead."""

    _default_column: str = "spelled_pitch"

    @classmethod
    def from_field(
        cls, source: Any, *, name: str = "spelled_pitch", pitch_type: str | None = None
    ) -> SpecificPitchField:
        pf = PitchField.from_field(source, name=name, pitch_type=pitch_type or "sp")
        pf.__class__ = cls
        return pf  # type: ignore[return-value]

    @classmethod
    def from_labels(
        cls, labels: list[str], *, name: str = "spelled_pitch"
    ) -> SpecificPitchField:
        """Construct from pitch label strings."""
        pf = PitchField.from_labels(labels, name=name)
        pf.__class__ = cls
        return pf  # type: ignore[return-value]


# Traditional aliases
MidiPitchField = EnharmonicPitchField
SpelledPitchField = SpecificPitchField


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


# Fifths position -> (step_letter, alter)
_FIFTHS_TO_STEP_ALTER: dict[int, tuple[str, int]] = {}
for _step, _base in {"F": -1, "C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5}.items():
    _FIFTHS_TO_STEP_ALTER[_base] = (_step, 0)
    for _n in range(1, 8):
        _FIFTHS_TO_STEP_ALTER[_base + 7 * _n] = (_step, _n)
        _FIFTHS_TO_STEP_ALTER[_base - 7 * _n] = (_step, -_n)


def _fifths_to_step_alter(fifths: int) -> tuple[str, int]:
    """Convert a line-of-fifths position to (step, alter)."""
    if fifths in _FIFTHS_TO_STEP_ALTER:
        return _FIFTHS_TO_STEP_ALTER[fifths]
    # Extended range: compute from modular arithmetic
    # The cycle of fifths mod 7 maps to steps: F C G D A E B
    step_order = ["F", "C", "G", "D", "A", "E", "B"]
    base_fifths = {"F": -1, "C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5}
    idx = (fifths + 1) % 7  # +1 because F is at -1
    step = step_order[idx]
    alter = (fifths - base_fifths[step]) // 7
    return step, alter


def _scalar_from_legacy_schema(row: dict[str, Any], pitch_type: str) -> Any:
    """Convert a legacy schema row (ep/epc, gpc_int/..., pitch_class) to scalar."""
    if pitch_type == "ep" and "ep" in row:
        return EnharmonicPitch.from_row(row)
    if pitch_type == "epc" and "pitch_class" in row:
        return GenericPitch.from_row(row)
    if pitch_type == "sp" and "sp" in row:
        return SpelledPitch.from_row(row)
    if pitch_type == "spc" and "gpc_str" in row:
        return SpelledPitchClass.from_row(row)
    # Fallback: try each scalar's from_row
    if "ep" in row:
        return EnharmonicPitch.from_row(row)
    if "pitch_class" in row:
        return GenericPitch.from_row(row)
    if "sp" in row:
        return SpelledPitch.from_row(row)
    if "gpc_str" in row:
        return SpelledPitchClass.from_row(row)
    raise ValueError(f"Cannot determine scalar for legacy row: {row!r}")


def _scalar_from_pitch_space(row: dict[str, Any], pitch_type: str) -> Any:
    """Convert a PitchSpaceSchema row to the appropriate scalar."""
    value = row.get("value")
    octave = row.get("octave")

    if pitch_type == "ep":
        midi = value if value is not None else 0
        return EnharmonicPitch.from_row({"ep": midi, "epc": midi % 12})
    if pitch_type == "epc":
        pc = value if value is not None else 0
        return GenericPitch.from_row({"pitch_class": pc})
    if pitch_type == "sp":
        fifths = value if value is not None else 0
        oct_ = octave if octave is not None else 4
        step, alter = _fifths_to_step_alter(fifths)
        return SpelledPitch(step=step, alter=alter, octave=oct_)
    if pitch_type == "spc":
        fifths = value if value is not None else 0
        step, alter = _fifths_to_step_alter(fifths)
        return SpelledPitchClass(step=step, alter=alter)
    if pitch_type == "gp":
        step = value if value is not None else 0
        oct_ = octave if octave is not None else 4
        return GenericPitch.from_row({"pitch_class": step + oct_ * 7})
    if pitch_type == "gpc":
        step = value if value is not None else 0
        return GenericPitchClass.from_row({"pitch_class": step})

    raise ValueError(f"Unknown pitch type: {pitch_type!r}")


def _values_to_pitch_space_rows(
    values: list | pa.Array, pitch_type: str
) -> list[dict[str, int | None]]:
    """Convert user values to PitchSpaceSchema row dicts."""
    meta = _TYPE_METADATA[pitch_type]
    is_specific = meta["level"] == "specific"
    rows = []

    for v in values:
        if v is None:
            rows.append({"value": None, "octave": None})
            continue

        if isinstance(v, (tuple, list)) and len(v) == 2:
            rows.append({"value": int(v[0]), "octave": int(v[1])})
            continue

        val = int(v)
        if is_specific:
            if pitch_type == "ep":
                # MIDI number encodes octave implicitly
                rows.append({"value": val, "octave": val // 12 - 1})
            else:
                # For sp, gp with bare int: octave defaults to 4
                rows.append({"value": val, "octave": 4})
        else:
            rows.append({"value": val, "octave": None})

    return rows


def _detect_pitch_type(pa_field: pa.Field) -> str:
    """Detect pitch type from pa.Field metadata or struct layout."""
    if pa_field.metadata:
        if _TIMETOALIGN_KEY in pa_field.metadata:
            blob = pa_field.metadata[_TIMETOALIGN_KEY]
            if isinstance(blob, bytes):
                blob = blob.decode("utf-8")
            meta = json.loads(blob)
            if "pitch_type" in meta:
                pt = meta["pitch_type"]
                # Handle legacy metadata values
                if pt in _PITCH_TYPES:
                    return pt
                return _legacy_pitch_type_map.get(pt, "ep")

    return _detect_pitch_type_from_struct(pa_field.type)


def _detect_pitch_type_from_struct(struct_type: pa.DataType) -> str:
    """Detect pitch type from struct field names."""
    if not pa.types.is_struct(struct_type):
        raise TypeError(f"Expected struct type, got {struct_type}")
    field_names = {struct_type.field(i).name for i in range(struct_type.num_fields)}

    # PitchSpaceSchema
    if field_names == {"value", "octave"}:
        return "ep"  # default; metadata should override

    # Legacy schemas
    if "pitch_class" in field_names and len(field_names) == 1:
        return "epc"  # GenericPitchSchema (0-11 = EPC)
    if "ep" in field_names:
        return "ep"  # EnharmonicPitchSchema
    if "sp" in field_names or "gpc_int" in field_names:
        return "sp"  # SpecificPitchSchema
    if "gpc_str" in field_names and "spc_int" in field_names:
        return "spc"  # SpelledPitchClassSchema

    return "ep"  # fallback


_legacy_pitch_type_map: dict[str, str] = {
    "generic": "epc",
    "spelled_class": "spc",
    "enharmonic": "ep",
    "specific": "sp",
}


def _extract_value_octave(
    raw: dict[str, Any], pitch_type: str
) -> tuple[int | None, int | None]:
    """Extract (value, octave) from a struct row, handling both schemas.

    PitchSpaceSchema rows have ``{value, octave}``.  Legacy schema rows
    have type-specific keys (``ep``, ``epc``, ``pitch_class``, ``sp``, etc.).
    """
    # PitchSpaceSchema
    if "value" in raw:
        return raw.get("value"), raw.get("octave")

    # Legacy: EnharmonicPitchSchema {ep, epc}
    if pitch_type == "ep" and "ep" in raw:
        midi = raw["ep"]
        return midi, (midi // 12 - 1 if midi is not None else None)
    if pitch_type == "epc" and "epc" in raw:
        return raw["epc"], None
    if pitch_type == "epc" and "pitch_class" in raw:
        return raw["pitch_class"], None

    # Legacy: SpecificPitchSchema {sp, gpc_int, ...}
    if pitch_type == "sp" and "sp" in raw:
        return raw["sp"], raw.get("octave")

    # Legacy: SpelledPitchClassSchema {spc_int, ...}
    if pitch_type == "spc" and "spc_int" in raw:
        return raw["spc_int"], None

    # Fallback: try common legacy keys
    if "ep" in raw:
        midi = raw["ep"]
        return midi, (midi // 12 - 1 if midi is not None else None)
    if "pitch_class" in raw:
        return raw["pitch_class"], None
    if "sp" in raw:
        return raw["sp"], raw.get("octave")

    return None, None


def _convert_pitch_space(
    source: PitchField, target_type: str
) -> list[dict[str, int | None]]:
    """Convert pitch values from one type to another."""
    rows = []
    src_type = source.pitch_type
    for i in range(len(source)):
        raw = source._raw[i]
        if raw is None:
            rows.append({"value": None, "octave": None})
            continue

        value, octave = _extract_value_octave(raw, src_type)
        converted = _convert_single(value, octave, src_type, target_type)
        rows.append(converted)

    return rows


def _convert_single(
    value: int | None, octave: int | None, src: str, tgt: str
) -> dict[str, int | None]:
    """Convert a single pitch value between types."""
    if value is None:
        return {"value": None, "octave": None}

    src_meta = _TYPE_METADATA[src]
    tgt_meta = _TYPE_METADATA[tgt]

    # Same space, specific -> class: drop octave
    if src_meta["space"] == tgt_meta["space"] and tgt_meta["level"] == "class":
        if src == "ep" and tgt == "epc":
            return {"value": value % 12, "octave": None}
        if src == "gp" and tgt == "gpc":
            return {"value": value % 7 if value is not None else None, "octave": None}
        if src == "sp" and tgt == "spc":
            return {"value": value, "octave": None}
        # class -> class same space
        return {"value": value, "octave": None}

    # Cross-space: fifths -> semitones
    if src_meta["space"] == "fifths" and tgt_meta["space"] == "semitones":
        step_name, alter = _fifths_to_step_alter(value)
        semitones = (_STEP_TO_SEMITONE[step_name] + alter) % 12
        if tgt_meta["level"] == "specific" and octave is not None:
            midi = (octave + 1) * 12 + _STEP_TO_SEMITONE[step_name] + alter
            return {"value": midi, "octave": midi // 12 - 1}
        return {"value": semitones, "octave": None}

    # Cross-space: fifths -> steps
    if src_meta["space"] == "fifths" and tgt_meta["space"] == "steps":
        step_name, _alter = _fifths_to_step_alter(value)
        diatonic_step = _STEP_TO_GPC[step_name]
        if tgt_meta["level"] == "specific" and octave is not None:
            return {"value": diatonic_step, "octave": octave}
        return {"value": diatonic_step, "octave": None}

    # Cross-space: semitones -> steps (lossy)
    if src_meta["space"] == "semitones" and tgt_meta["space"] == "steps":
        # Approximate: chromatic to nearest diatonic step
        step_map = [0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6]
        pc = value % 12
        step = step_map[pc]
        if tgt_meta["level"] == "specific" and octave is not None:
            return {"value": step, "octave": octave}
        return {"value": step, "octave": None}

    # ep -> epc
    if src == "ep" and tgt == "epc":
        return {"value": value % 12, "octave": None}

    # Fallback: just pass value through
    tgt_octave = octave if tgt_meta["level"] == "specific" else None
    return {"value": value, "octave": tgt_octave}
