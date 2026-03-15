"""Semantic field access mixins for EventData subclasses.

Provides type-dispatched access to ``SemanticField`` columns stored in
PyArrow tables.  The base ``SemanticFieldAccessMixin`` scans column
metadata for ``b"timetoalign"`` JSON blobs containing ``field_type``
entries and reconstructs the matching ``SemanticField`` subclass.

Domain mixins add convenience accessors with priority-based defaults:

- ``PitchAccessMixin`` -- ``get_pitch_field()``
- ``HarmonyAccessMixin`` -- ``get_harmony_field()``
- ``MeasureAccessMixin`` -- ``get_measure_field()`` (placeholder)
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pyarrow as pa

from timetoalign.fields.base import SemanticField

if TYPE_CHECKING:
    from timetoalign.fields.harmony import HarmonyField
    from timetoalign.fields.pitch import PitchField

_TIMETOALIGN_KEY = b"timetoalign"

# ---------------------------------------------------------------------------
# Field-type string -> class mapping (lazy-loaded to avoid circular imports)
# ---------------------------------------------------------------------------

_FIELD_TYPE_MAP: dict[str, type[SemanticField[Any]]] | None = None


def _get_field_type_map() -> dict[str, type[SemanticField[Any]]]:
    """Return the field_type string -> class mapping, building it on first call."""
    global _FIELD_TYPE_MAP
    if _FIELD_TYPE_MAP is not None:
        return _FIELD_TYPE_MAP

    from timetoalign.fields.harmony import (
        DcmlLabelField,
        RomanNumeralHarmonyField,
        WesternTertianHarmonyField,
    )
    from timetoalign.fields.pitch import (
        EnharmonicPitchField,
        GenericPitchField,
        SpecificPitchField,
        SpelledPitchClassField,
    )

    _FIELD_TYPE_MAP = {
        # Pitch hierarchy
        "GenericPitchField": GenericPitchField,
        "SpelledPitchClassField": SpelledPitchClassField,
        "SpecificPitchField": SpecificPitchField,
        "EnharmonicPitchField": EnharmonicPitchField,
        # Harmony hierarchy
        "WesternTertianHarmonyField": WesternTertianHarmonyField,
        "RomanNumeralHarmonyField": RomanNumeralHarmonyField,
        # DcmlLabelField stores its field_type as "HarmonyField" for backward compat
        "HarmonyField": DcmlLabelField,
        "DcmlLabelField": DcmlLabelField,
    }
    return _FIELD_TYPE_MAP


def _parse_field_type_metadata(pa_field: pa.Field) -> str | None:
    """Extract the ``field_type`` string from a PyArrow field's metadata.

    Looks for a ``b"timetoalign"`` key in the field's metadata dict,
    parses it as JSON, and returns the ``field_type`` value.

    Args:
        pa_field: A PyArrow field descriptor.

    Returns:
        The ``field_type`` string, or ``None`` if not present.
    """
    meta = pa_field.metadata
    if not meta:
        return None
    blob = meta.get(_TIMETOALIGN_KEY)
    if blob is None:
        return None
    try:
        parsed = json.loads(blob)
        return parsed.get("field_type")
    except (json.JSONDecodeError, TypeError):
        return None


def _reconstruct_field(
    pa_field: pa.Field,
    col: pa.ChunkedArray | pa.Array | None,
    field_type_str: str,
) -> SemanticField[Any]:
    """Reconstruct a ``SemanticField`` subclass from column data and metadata.

    Args:
        pa_field: The PyArrow field descriptor.
        col: The column data (may be ``None`` for schema-only).
        field_type_str: The ``field_type`` string from metadata.

    Returns:
        A ``SemanticField`` subclass instance.

    Raises:
        KeyError: If ``field_type_str`` is not in the registry.
    """
    registry = _get_field_type_map()
    cls = registry.get(field_type_str)
    if cls is None:
        raise KeyError(
            f"Unknown field_type {field_type_str!r} in metadata. Known types: {sorted(registry)}"
        )
    return cls.from_field((col, pa_field))


# ---------------------------------------------------------------------------
# SemanticFieldAccessMixin
# ---------------------------------------------------------------------------


class SemanticFieldAccessMixin:
    """Base mixin for type-dispatched field access on EventData.

    Expects the host class to provide a ``_table`` attribute of type
    ``pa.Table``.  Scans column metadata for ``b"timetoalign"`` JSON
    blobs and dispatches on the ``field_type`` value to reconstruct
    the appropriate ``SemanticField`` subclass.
    """

    _table: pa.Table  # provided by EventData

    def get_field(self, field_type: type[SemanticField[Any]]) -> SemanticField[Any]:
        """Return the first column matching *field_type*'s class hierarchy.

        Dispatches on ``metadata[b"timetoalign"]["field_type"]`` and uses
        ``issubclass`` to support requesting a parent type (e.g.,
        ``get_field(PitchField)`` matches any pitch field subclass).

        Args:
            field_type: The ``SemanticField`` subclass to search for.

        Returns:
            A ``SemanticField`` subclass instance.

        Raises:
            KeyError: If no matching column is found.
        """
        fields = self.get_fields(field_type)
        if not fields:
            raise KeyError(f"No column matching {field_type.__name__!r} found in table")
        return fields[0]

    def get_fields(
        self, field_type: type[SemanticField[Any]]
    ) -> list[SemanticField[Any]]:
        """Return ALL columns matching *field_type*'s class hierarchy.

        Args:
            field_type: The ``SemanticField`` subclass to search for.

        Returns:
            A list of matching ``SemanticField`` subclass instances (may be empty).
        """
        registry = _get_field_type_map()
        result: list[SemanticField[Any]] = []

        schema = self._table.schema
        for i in range(len(schema)):
            pa_field = schema.field(i)
            ft_str = _parse_field_type_metadata(pa_field)
            if ft_str is None:
                continue
            cls = registry.get(ft_str)
            if cls is None:
                continue
            if issubclass(cls, field_type):
                col = self._table.column(i)
                result.append(_reconstruct_field(pa_field, col, ft_str))

        return result

    def has_field(self, field_type: type[SemanticField[Any]]) -> bool:
        """Check whether any column matches *field_type*.

        Args:
            field_type: The ``SemanticField`` subclass to search for.

        Returns:
            ``True`` if at least one matching column exists.
        """
        registry = _get_field_type_map()

        schema = self._table.schema
        for i in range(len(schema)):
            pa_field = schema.field(i)
            ft_str = _parse_field_type_metadata(pa_field)
            if ft_str is None:
                continue
            cls = registry.get(ft_str)
            if cls is None:
                continue
            if issubclass(cls, field_type):
                return True

        return False


# ---------------------------------------------------------------------------
# PitchAccessMixin
# ---------------------------------------------------------------------------


class PitchAccessMixin(SemanticFieldAccessMixin):
    """Mixin providing pitch field access with priority-based defaults.

    Priority order (most specific first):
    ``EnharmonicPitchField`` > ``SpecificPitchField`` > ``SpelledPitchClassField`` > ``GenericPitchField``
    """

    def get_pitch_field(
        self,
        pitch_type: type[PitchField] | None = None,
        *,
        format: str | None = None,
    ) -> PitchField:
        """Return a pitch field, optionally filtered by type.

        If *pitch_type* is ``None``, returns the most specific available
        pitch field according to the priority order.

        Args:
            pitch_type: Specific ``PitchField`` subclass to request.
                If ``None``, returns the most specific available.
            format: Reserved for future conversion support.

        Returns:
            A ``PitchField`` subclass instance.

        Raises:
            KeyError: If no matching pitch column is found.
        """
        from timetoalign.fields.pitch import (
            EnharmonicPitchField,
            GenericPitchField,
        )
        from timetoalign.fields.pitch import PitchField as PitchFieldCls
        from timetoalign.fields.pitch import (
            SpecificPitchField,
            SpelledPitchClassField,
        )

        if pitch_type is not None:
            return self.get_field(pitch_type)  # type: ignore[return-value]

        # Priority order: most specific first
        priority: list[type[PitchFieldCls]] = [
            EnharmonicPitchField,
            SpecificPitchField,
            SpelledPitchClassField,
            GenericPitchField,
        ]
        for pt in priority:
            if self.has_field(pt):
                return self.get_field(pt)  # type: ignore[return-value]

        raise KeyError("No pitch field found in table")


# ---------------------------------------------------------------------------
# HarmonyAccessMixin
# ---------------------------------------------------------------------------


class HarmonyAccessMixin(SemanticFieldAccessMixin):
    """Mixin providing harmony field access with priority-based defaults.

    Priority order (most specific first):
    ``DcmlLabelField`` > ``RomanNumeralHarmonyField`` > ``WesternTertianHarmonyField``
    """

    def get_harmony_field(
        self,
        harmony_type: type[HarmonyField] | None = None,
    ) -> HarmonyField:
        """Return a harmony field, optionally filtered by type.

        If *harmony_type* is ``None``, returns the most specific available
        harmony field according to the priority order.

        Args:
            harmony_type: Specific ``HarmonyField`` subclass to request.
                If ``None``, returns the most specific available.

        Returns:
            A ``HarmonyField`` subclass instance.

        Raises:
            KeyError: If no matching harmony column is found.
        """
        from timetoalign.fields.harmony import (
            DcmlLabelField,
        )
        from timetoalign.fields.harmony import HarmonyField as HarmonyFieldCls
        from timetoalign.fields.harmony import (
            RomanNumeralHarmonyField,
            WesternTertianHarmonyField,
        )

        if harmony_type is not None:
            return self.get_field(harmony_type)  # type: ignore[return-value]

        # Priority order: most specific first
        priority: list[type[HarmonyFieldCls]] = [
            DcmlLabelField,
            RomanNumeralHarmonyField,
            WesternTertianHarmonyField,
        ]
        for ht in priority:
            if self.has_field(ht):
                return self.get_field(ht)  # type: ignore[return-value]

        raise KeyError("No harmony field found in table")


# ---------------------------------------------------------------------------
# MeasureAccessMixin
# ---------------------------------------------------------------------------


class MeasureAccessMixin(SemanticFieldAccessMixin):
    """Mixin providing measure field access (placeholder).

    ``MeasureField`` is not yet defined; this mixin is a forward-looking
    placeholder that will be filled in when the measure field hierarchy
    is implemented.
    """

    def get_measure_field(self) -> Any:
        """Return the measure field.

        Raises:
            NotImplementedError: Always, until MeasureField is defined.
        """
        raise NotImplementedError(
            "MeasureField is not yet defined in the type hierarchy"
        )
