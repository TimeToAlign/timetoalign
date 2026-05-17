"""Harmony field hierarchy -- semantic columnar wrappers for harmony annotations.

Hierarchy::

    SemanticField[StructField]
    └── HarmonyField (ABSTRACT)
        │   Minimum schema: {label, standard}  (from HarmonyBaseSchema.schema)
        │
        ├── WesternTertianHarmonyField
        │   Schema adds: root, bass, chord_type, inversion
        │
        ├── RomanNumeralHarmonyField
        │   Schema adds: numeral, localkey, globalkey, key_context
        │
        └── DcmlHarmonyField (imports DCML TSV data, maps to internal model)
            DCML storage schema -> internal model

All schema dataclasses and the figbass-to-inversion mapping are defined
in ``fields.schemas`` -- the single source of truth for schema definitions.
"""

from __future__ import annotations

import json
from abc import abstractmethod

import pyarrow as pa

from ..core.scalars.harmony import (
    DcmlHarmony,
    HarmonyLabel,
    RomanNumeralHarmony,
    WesternTertianHarmony,
)
from .base import SemanticField, StructField

_TIMETOALIGN_KEY = b"timetoalign"


# ---------------------------------------------------------------------------
# HarmonyField (abstract parent)
# ---------------------------------------------------------------------------


class HarmonyField(SemanticField[StructField]):
    """Abstract parent for all harmony field types.

    Minimum schema: ``{label, standard}``.  Each concrete subclass adds
    domain-specific columns and implements ``__getitem__`` returning the
    appropriate scalar type.

    Args:
        raw: The inner ``StructField`` holding harmony struct data.
    """

    def __init__(self, raw: StructField) -> None:
        super().__init__(raw)

    # -- SemanticTypeLike properties -----------------------------------------

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "Harmony"

    @abstractmethod
    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract.

        Returns:
            Dict with at least ``field_type`` and ``standard`` keys.
        """
        ...

    # -- element access ------------------------------------------------------

    @abstractmethod
    def __getitem__(self, i: int) -> HarmonyLabel | None:
        """Return the *i*-th harmony as a scalar.

        Args:
            i: Zero-based index.

        Returns:
            A harmony scalar instance, or ``None`` for null entries.
        """
        ...

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
        name: str = "harmony",
    ) -> HarmonyField:
        """Construct a ``HarmonyField`` from various source types.

        Accepted source forms:

        1. ``pa.Array`` (struct array).
        2. ``StructField``.
        3. ``pa.Field`` (schema-only, no data).
        4. ``tuple[pa.Array | None, pa.Field]``.

        Args:
            source: The data source (see above).
            name: Column name used when *source* is a bare ``pa.Array``.

        Returns:
            A new ``HarmonyField``.

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
            f"Unsupported source type for {cls.__name__}.from_field: {type(source).__name__}"
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
        return f"{type(self).__name__}(name={self.name!r}, len={length})"


# ---------------------------------------------------------------------------
# WesternTertianHarmonyField
# ---------------------------------------------------------------------------


class WesternTertianHarmonyField(HarmonyField):
    """Semantic field for Western tertian harmony columns.

    Schema adds ``root``, ``bass``, ``chord_quality``, ``inversion``
    to the base ``{label, standard}`` schema.

    Args:
        raw: The inner ``StructField`` holding harmony struct data.

    Examples:
        >>> import pyarrow as pa
        >>> from timetoalign.fields.harmony import WesternTertianHarmonyField
        >>> from timetoalign.fields.schemas import WesternTertianSchema
        >>> arr = pa.array(
        ...     [{"label": "CM", "standard": "chord_symbol",
        ...       "root": 0, "bass": 0, "chord_quality": "M", "inversion": 0}],
        ...     type=WesternTertianSchema.schema,
        ... )
        >>> wf = WesternTertianHarmonyField.from_field(arr, name="harmony")
        >>> wf[0]
        WesternTertianHarmony(label='CM', chord_type='M')
    """

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract.

        Returns:
            Dict with ``field_type`` and ``standard`` keys.
        """
        return {
            "field_type": "WesternTertianHarmonyField",
            "standard": "chord_symbol",
        }

    def __getitem__(self, i: int) -> WesternTertianHarmony | None:
        """Return the *i*-th harmony as a ``WesternTertianHarmony`` scalar.

        Args:
            i: Zero-based index.

        Returns:
            A ``WesternTertianHarmony`` instance, or ``None`` for null entries.

        Raises:
            TypeError: If the field is schema-only (no data).
            IndexError: If *i* is out of range.
        """
        raw_dict = self._raw[i]
        if raw_dict is None:
            return None

        label = raw_dict.get("label")
        if label is None:
            return None

        root = int(raw_dict["root"]) if raw_dict.get("root") is not None else None
        bass_raw = raw_dict.get("bass")
        bass = int(bass_raw) if bass_raw is not None else None
        chord_type = str(raw_dict.get("chord_type") or "")
        inversion_raw = raw_dict.get("inversion")
        inversion = int(inversion_raw) if inversion_raw is not None else None

        return WesternTertianHarmony(
            label=str(label),
            standard=str(raw_dict.get("standard") or "chord_symbol"),
            root=root,
            bass=bass,
            chord_type=chord_type,
            inversion=inversion,
        )


# ---------------------------------------------------------------------------
# RomanNumeralHarmonyField
# ---------------------------------------------------------------------------


class RomanNumeralHarmonyField(WesternTertianHarmonyField):
    """Semantic field for Roman numeral harmony columns.

    Extends ``WesternTertianHarmonyField`` with ``numeral`` and
    ``key_context`` columns.

    Args:
        raw: The inner ``StructField`` holding harmony struct data.

    Examples:
        >>> import pyarrow as pa
        >>> from timetoalign.fields.harmony import RomanNumeralHarmonyField
        >>> from timetoalign.fields.schemas import RomanNumeralSchema
        >>> arr = pa.array(
        ...     [{"label": "I", "standard": "roman_numeral",
        ...       "root": 0, "bass": 0, "chord_quality": "M", "inversion": 0,
        ...       "numeral": "I", "key_context": "C:I"}],
        ...     type=RomanNumeralSchema.schema,
        ... )
        >>> rf = RomanNumeralHarmonyField.from_field(arr, name="harmony")
        >>> rf[0]
        RomanNumeralHarmony(label='I', numeral='I', key=:)
    """

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract.

        Returns:
            Dict with ``field_type`` and ``standard`` keys.
        """
        return {
            "field_type": "RomanNumeralHarmonyField",
            "standard": "roman_numeral",
        }

    def __getitem__(self, i: int) -> RomanNumeralHarmony | None:
        """Return the *i*-th harmony as a ``RomanNumeralHarmony`` scalar.

        Args:
            i: Zero-based index.

        Returns:
            A ``RomanNumeralHarmony`` instance, or ``None`` for null entries.

        Raises:
            TypeError: If the field is schema-only (no data).
            IndexError: If *i* is out of range.
        """
        raw_dict = self._raw[i]
        if raw_dict is None:
            return None

        label = raw_dict.get("label")
        if label is None:
            return None

        root = int(raw_dict["root"]) if raw_dict.get("root") is not None else None
        bass_raw = raw_dict.get("bass")
        bass = int(bass_raw) if bass_raw is not None else None
        chord_type = str(raw_dict.get("chord_type") or "")
        inversion_raw = raw_dict.get("inversion")
        inversion = int(inversion_raw) if inversion_raw is not None else None

        return RomanNumeralHarmony(
            label=str(label),
            standard=str(raw_dict.get("standard") or "roman_numeral"),
            root=root,
            bass=bass,
            chord_type=chord_type,
            inversion=inversion,
            numeral=str(raw_dict.get("numeral") or ""),
            localkey=str(raw_dict.get("localkey") or ""),
            globalkey=str(raw_dict.get("globalkey") or ""),
        )


# ---------------------------------------------------------------------------
# DcmlLabelField
# ---------------------------------------------------------------------------


class DcmlLabelField(HarmonyField):
    """Semantic field for DCML harmony annotation columns.

    Wraps a ``StructField`` containing the DCML harmony struct and adds
    semantic identity.  This was formerly called ``HarmonyField`` (renamed
    in the type hierarchy restructuring).

    Satisfies ``HarmonyLike`` at the columnar level.

    Args:
        raw: The inner ``StructField`` holding harmony struct data.

    Examples:
        >>> import pyarrow as pa
        >>> from timetoalign.fields.harmony import DcmlLabelField
        >>> from timetoalign.fields.schemas import DcmlStorageSchema
        >>> arr = pa.array(
        ...     [{{"label": "V65", "globalkey": "C", "localkey": "I",
        ...       "numeral": "V", "form": "M", "figbass": "65",
        ...       "chord_type": "M", "root": 7, "bass_note": 11}}],
        ...     type=DcmlStorageSchema.schema,
        ... )
        >>> hf = DcmlLabelField.from_field(arr, name="harmony")
        >>> hf[0]
        DcmlHarmony(label='V65', key=C:I)
    """

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract.

        Returns:
            Dict with ``field_type`` and ``standard`` keys.
        """
        return {
            "field_type": "HarmonyField",
            "standard": "dcml",
        }

    # -- element access ------------------------------------------------------

    def __getitem__(self, i: int) -> DcmlHarmony | None:
        """Return the *i*-th harmony as a ``DcmlHarmony`` scalar.

        Delegates to ``DcmlHarmony.from_row()`` which handles the
        DCML storage -> internal model mapping (figbass -> inversion,
        bass_note -> bass, etc.).

        Args:
            i: Zero-based index.

        Returns:
            A ``DcmlHarmony`` instance, or ``None`` for null entries.

        Raises:
            TypeError: If the field is schema-only (no data).
            IndexError: If *i* is out of range.
        """
        raw_dict = self._raw[i]
        if raw_dict is None:
            return None
        return DcmlHarmony.from_row(raw_dict)

    def __repr__(self) -> str:
        length = len(self) if not self.is_empty else 0
        return f"DcmlLabelField(name={self.name!r}, standard=dcml, len={length})"
