"""HarmonyField -- semantic columnar wrapper for DCML harmony annotations.

``HarmonyField(SemanticField[StructField])`` wraps a struct column
containing DCML harmony annotation data: ``{label, globalkey, localkey,
numeral, form, figbass, chord_type, root, bass_note}``.

Follows the ``CoordinateField`` composition pattern exactly.
"""

from __future__ import annotations

import json

import pyarrow as pa

from ..core.scalars.harmony import Harmony
from .base import SemanticField, StructField

_TIMETOALIGN_KEY = b"timetoalign"

# The canonical struct type for DCML harmony annotations.
HARMONY_STRUCT_TYPE = pa.struct(
    [
        pa.field("label", pa.string(), nullable=True),
        pa.field("globalkey", pa.string(), nullable=True),
        pa.field("localkey", pa.string(), nullable=True),
        pa.field("numeral", pa.string(), nullable=True),
        pa.field("form", pa.string(), nullable=True),
        pa.field("figbass", pa.string(), nullable=True),
        pa.field("chord_type", pa.string(), nullable=True),
        pa.field("root", pa.int64(), nullable=True),
        pa.field("bass_note", pa.int64(), nullable=True),
    ]
)


class HarmonyField(SemanticField[StructField]):
    """Semantic field for DCML harmony annotation columns.

    Wraps a ``StructField`` containing the harmony struct and adds
    semantic identity.

    Satisfies ``HarmonyLike`` at the columnar level.

    Args:
        raw: The inner ``StructField`` holding harmony struct data.

    Examples:
        >>> import pyarrow as pa
        >>> from timetoalign.fields.harmony import HarmonyField, HARMONY_STRUCT_TYPE
        >>> arr = pa.array(
        ...     [{"label": "V65", "globalkey": "C", "localkey": "I",
        ...       "numeral": "V", "form": "M", "figbass": "65",
        ...       "chord_type": "M", "root": 7, "bass_note": 11}],
        ...     type=HARMONY_STRUCT_TYPE,
        ... )
        >>> hf = HarmonyField.from_field(arr, name="harmony")
        >>> hf[0]
        Harmony(label='V65', key=C:I)
    """

    def __init__(self, raw: StructField) -> None:
        super().__init__(raw)

    # -- SemanticTypeLike properties -----------------------------------------

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "Harmony"

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

    def __getitem__(self, i: int) -> Harmony | None:
        """Return the *i*-th harmony as a ``Harmony`` scalar.

        Args:
            i: Zero-based index.

        Returns:
            A ``Harmony`` instance, or ``None`` for null entries.

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

        return Harmony(
            label=str(label),
            globalkey=str(raw_dict.get("globalkey") or ""),
            localkey=str(raw_dict.get("localkey") or ""),
            numeral=str(raw_dict.get("numeral") or ""),
            form=str(raw_dict.get("form") or ""),
            figbass=str(raw_dict.get("figbass") or ""),
            chord_type=str(raw_dict.get("chord_type") or ""),
            root=int(raw_dict["root"]) if raw_dict.get("root") is not None else None,
            bass_note=(
                int(raw_dict["bass_note"])
                if raw_dict.get("bass_note") is not None
                else None
            ),
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
            f"Unsupported source type for HarmonyField.from_field: {type(source).__name__}"
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
        return f"HarmonyField(name={self.name!r}, standard=dcml, len={length})"
