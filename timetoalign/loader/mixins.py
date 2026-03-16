"""Semantic field access mixins for EventData subclasses.

Provides type-dispatched access to ``SemanticField`` columns stored in
PyArrow tables.  The base ``SemanticFieldAccessMixin`` scans column
metadata for ``b"timetoalign"`` JSON blobs containing ``field_type``
entries and reconstructs the matching ``SemanticField`` subclass.

Domain mixins add convenience accessors with priority-based defaults
and ``format=`` parameters for on-the-fly conversion:

- ``PitchAccessMixin`` -- ``get_pitch_field(type, format=)``
- ``HarmonyAccessMixin`` -- ``get_harmony_field(type, format=)``
- ``MeasureAccessMixin`` -- ``get_measure_field(format=)`` (placeholder)
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
        # Pitch hierarchy (EP = Enharmonic = MIDI, SP = Specific = Spelled)
        "GenericPitchField": GenericPitchField,
        "SpelledPitchClassField": SpelledPitchClassField,
        "EnharmonicPitchField": EnharmonicPitchField,
        "SpecificPitchField": SpecificPitchField,
        # Backward-compat: old names from before the GP/EP/SP correction
        # Old "SpecificPitchField" wrapped EP (MIDI) -> now EnharmonicPitchField
        # Old "EnharmonicPitchField" wrapped SP (Spelled) -> now SpecificPitchField
        "PitchField": EnharmonicPitchField,  # original PitchField was MIDI
        "SpelledPitchField": SpecificPitchField,  # original SpelledPitchField was SP
        # Harmony hierarchy
        "WesternTertianHarmonyField": WesternTertianHarmonyField,
        "RomanNumeralHarmonyField": RomanNumeralHarmonyField,
        # DcmlLabelField stores its field_type as "HarmonyField" for backward compat
        "HarmonyField": DcmlLabelField,
        "DcmlLabelField": DcmlLabelField,
        "DcmlHarmonyField": DcmlLabelField,
    }
    return _FIELD_TYPE_MAP


def _parse_field_type_metadata(pa_field: pa.Field) -> str | None:
    """Extract the ``field_type`` string from a PyArrow field's metadata."""
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
    """Reconstruct a ``SemanticField`` subclass from column data and metadata."""
    registry = _get_field_type_map()
    cls = registry.get(field_type_str)
    if cls is None:
        raise KeyError(
            f"Unknown field_type {field_type_str!r} in metadata. "
            f"Known types: {sorted(registry)}"
        )
    return cls.from_field((col, pa_field))


# ---------------------------------------------------------------------------
# Schema-based field discovery (fallback when no metadata is present)
# ---------------------------------------------------------------------------


def _discover_by_schema(
    table: pa.Table,
    field_type: type[SemanticField[Any]],
    cache: dict[tuple[str, str], SemanticField[Any]],
    registry: dict[str, type[SemanticField[Any]]],
) -> list[SemanticField[Any]]:
    """Try to match *field_type* against table columns by schema structure.

    Each concrete ``SemanticField`` subclass may declare a
    ``_default_column`` attribute (the expected column name) and optionally
    a ``_expected_schema`` (the PyArrow struct type to match).  When the
    table contains a column with a matching name and compatible struct
    type, the field is constructed via ``from_field()`` and cached.

    This function also checks concrete subclasses of *field_type* (e.g.,
    requesting ``PitchField`` will try ``SpecificPitchField``,
    ``EnharmonicPitchField``, etc.).

    Args:
        table: The PyArrow table to search.
        field_type: The ``SemanticField`` subclass (or parent) to match.
        cache: The field cache dict to populate.
        registry: The field type string → class mapping.

    Returns:
        A list of discovered fields (may be empty).
    """
    result: list[SemanticField[Any]] = []
    column_names = set(table.column_names)

    # Collect candidate classes: the field_type itself + any registered
    # subclasses that are subclasses of field_type.
    candidates: list[type[SemanticField[Any]]] = []
    if hasattr(field_type, "_default_column"):
        candidates.append(field_type)
    for cls in registry.values():
        if cls is field_type:
            continue
        if issubclass(cls, field_type) and hasattr(cls, "_default_column"):
            if cls not in candidates:
                candidates.append(cls)

    for cls in candidates:
        col_name = cls._default_column  # type: ignore[attr-defined]
        if col_name not in column_names:
            continue

        cache_key = (col_name, cls.__name__)
        cached = cache.get(cache_key)
        if cached is not None:
            result.append(cached)
            continue

        col = table.column(col_name)
        pa_field = table.schema.field(col_name)

        # Verify the column is a struct (SemanticFields wrap struct arrays)
        if not pa.types.is_struct(pa_field.type):
            continue

        try:
            field = cls.from_field((col, pa_field))
        except (TypeError, KeyError, ValueError):
            continue
        cache[cache_key] = field
        result.append(field)

    return result


# ---------------------------------------------------------------------------
# SemanticFieldAccessMixin
# ---------------------------------------------------------------------------


class SemanticFieldAccessMixin:
    """Base mixin for type-dispatched field access on EventData.

    Expects the host class to provide a ``_table`` attribute of type
    ``pa.Table``.
    """

    _table: pa.Table  # provided by EventData

    @property
    def _field_cache(self) -> dict[tuple[str, str], SemanticField[Any]]:
        try:
            return self.__field_cache
        except AttributeError:
            self.__field_cache: dict[tuple[str, str], SemanticField[Any]] = {}
            return self.__field_cache

    def get_field(self, field_type: type[SemanticField[Any]]) -> SemanticField[Any]:
        """Return the first column matching *field_type*'s class hierarchy.

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

        Discovery uses two strategies:

        1. **Metadata-based**: columns carrying ``b"timetoalign"`` JSON
           metadata with a ``field_type`` entry.
        2. **Schema-based fallback**: if no metadata matches are found,
           tries to match the requested *field_type*'s ``_default_column``
           name against table columns with a compatible struct type.

        Args:
            field_type: The ``SemanticField`` subclass to search for.

        Returns:
            A list of matching ``SemanticField`` subclass instances.
        """
        registry = _get_field_type_map()
        cache = self._field_cache
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
                cache_key = (pa_field.name, ft_str)
                cached = cache.get(cache_key)
                if cached is not None:
                    result.append(cached)
                else:
                    col = self._table.column(i)
                    field = _reconstruct_field(pa_field, col, ft_str)
                    cache[cache_key] = field
                    result.append(field)

        if result:
            return result

        # Fallback: schema-based discovery via _default_column
        result = _discover_by_schema(self._table, field_type, cache, registry)
        return result

    def has_field(self, field_type: type[SemanticField[Any]]) -> bool:
        """Check whether any column matches *field_type*.

        Uses the same two-strategy discovery as ``get_fields()``
        (metadata-based, then schema-based fallback) but avoids
        constructing field objects when possible.

        Args:
            field_type: The ``SemanticField`` subclass to search for.

        Returns:
            ``True`` if at least one matching column exists.
        """
        registry = _get_field_type_map()
        cache = self._field_cache

        # Fast path: check if any cached field already matches
        for (_, cached_ft_str), _ in cache.items():
            cls = registry.get(cached_ft_str)
            if cls is not None and issubclass(cls, field_type):
                return True

        # Check cache keys that came from schema-based discovery
        for (_, cached_ft_str), _ in cache.items():
            if cached_ft_str == field_type.__name__:
                return True

        # Metadata scan
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

        # Schema-based fallback: check if _default_column exists in table
        column_names = set(self._table.column_names)
        candidates: list[type[SemanticField[Any]]] = []
        if hasattr(field_type, "_default_column"):
            candidates.append(field_type)
        for cls in registry.values():
            if cls is field_type:
                continue
            if issubclass(cls, field_type) and hasattr(cls, "_default_column"):
                if cls not in candidates:
                    candidates.append(cls)
        for cls in candidates:
            col_name = cls._default_column  # type: ignore[attr-defined]
            if col_name in column_names:
                pa_field = self._table.schema.field(col_name)
                if pa.types.is_struct(pa_field.type):
                    return True

        return False


# ---------------------------------------------------------------------------
# PitchAccessMixin
# ---------------------------------------------------------------------------


class PitchAccessMixin(SemanticFieldAccessMixin):
    """Mixin providing pitch field access with priority-based defaults.

    Priority order (most informative first):
    ``SpecificPitchField`` (SP) > ``EnharmonicPitchField`` (EP)
    > ``SpelledPitchClassField`` (SPC) > ``GenericPitchField`` (GP)
    """

    def get_pitch_field(
        self,
        pitch_type: type[PitchField] | None = None,
        *,
        format: str | None = None,
    ) -> PitchField:
        """Return a pitch field, optionally filtered by type.

        This is the one-stop-shop accessor for pitch data.  If
        *pitch_type* is ``None``, returns the most informative
        available pitch field.

        Args:
            pitch_type: Specific ``PitchField`` subclass to request.
                If ``None``, returns the most informative available.
            format: Format specifier for on-the-fly conversion
                (e.g., ``"midi"``, ``"spelled"``, ``"generic"``).
                Reserved for future conversion support.

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

        # Priority order: most informative first
        # SP (Specific/Spelled) > EP (Enharmonic/MIDI) > SPC > GP
        priority: list[type[PitchFieldCls]] = [
            SpecificPitchField,
            EnharmonicPitchField,
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
        *,
        format: str | None = None,
    ) -> HarmonyField:
        """Return a harmony field, optionally filtered by type.

        This is the one-stop-shop accessor for harmony data.

        Args:
            harmony_type: Specific ``HarmonyField`` subclass to request.
                If ``None``, returns the most specific available.
            format: Format specifier for on-the-fly conversion.
                Reserved for future conversion support.

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
    placeholder.
    """

    def get_measure_field(self, *, format: str | None = None) -> Any:
        """Return the measure field.

        Args:
            format: Format specifier (reserved for future use).

        Raises:
            NotImplementedError: Always, until MeasureField is defined.
        """
        raise NotImplementedError(
            "MeasureField is not yet defined in the type hierarchy"
        )
