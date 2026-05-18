"""Semantic field access mixins for EventData subclasses.

Provides three levels of column access on ``EventData``:

- **``events.table``** -- direct access to the underlying ``pa.Table``
  (specialist use only).
- **``events.get_raw("name")``** -- returns a raw ``DataField``
  (``StructField``, ``NumericField``, etc.) wrapping the column.
- **``events.get_field(...)``** -- returns a ``SemanticField`` wrapping
  the column with semantic identity and typed scalar access.

``get_field()`` accepts three argument forms:

1. ``get_field("start")`` -- string column name; looks up metadata or
   default-field mapping to determine the ``SemanticField`` subclass.
2. ``get_field(PitchField)`` -- a class; scans all columns
   for metadata matching that class.
3. ``get_field(PitchField(ep="midi_pitch"))`` -- a *blueprint*
   instance; resolves the named column against the blueprint's type
   configuration and caches the result.

Domain mixins add convenience accessors with priority-based defaults
and ``format=`` parameters for on-the-fly conversion:

- ``PitchAccessMixin`` -- ``get_pitch_field(type, format=)``
- ``HarmonyAccessMixin`` -- ``get_harmony_field(type, format=)``
- ``MeasureAccessMixin`` -- ``get_measure_field(format=)`` (placeholder)
"""

from __future__ import annotations

import enum
import json
from typing import TYPE_CHECKING, Any

import pyarrow as pa

from timetoalign.fields.base import (
    DataField,
    MapField,
    NumericField,
    SemanticField,
    StringField,
    StructField,
    _GenericField,
)

if TYPE_CHECKING:
    from timetoalign.fields.harmony import HarmonyField
    from timetoalign.fields.pitch import PitchField

_TIMETOALIGN_KEY = b"timetoalign"


# ---------------------------------------------------------------------------
# DefaultField -- core temporal columns present on every EventData
# ---------------------------------------------------------------------------


class DefaultField(enum.Enum):
    """Core temporal columns present on every EventData table.

    These map column names to the ``SemanticField`` subclass that
    should wrap them.  ``start`` and ``end`` are ``CoordinateField``;
    ``duration`` is ``DurationField``.
    """

    start = "start"
    end = "end"
    duration = "duration"


# ---------------------------------------------------------------------------
# Field-type string -> class mapping (lazy-loaded to avoid circular imports)
# ---------------------------------------------------------------------------

_FIELD_TYPE_MAP: dict[str, type[SemanticField[Any]]] | None = None


def _get_field_type_map() -> dict[str, type[SemanticField[Any]]]:
    """Return the field_type string -> class mapping, building it on first call."""
    global _FIELD_TYPE_MAP
    if _FIELD_TYPE_MAP is not None:
        return _FIELD_TYPE_MAP

    from timetoalign.fields.coordinate import CoordinateField, DurationField
    from timetoalign.fields.harmony import (
        DcmlLabelField,
        RomanNumeralHarmonyField,
        WesternTertianHarmonyField,
    )
    from timetoalign.fields.pitch import PitchField

    _FIELD_TYPE_MAP = {
        # Unified PitchField (canonical entry)
        "PitchField": PitchField,
        # Coordinate / Duration
        "CoordinateField": CoordinateField,
        "DurationField": DurationField,
        # Legacy pitch metadata compatibility -- all map to PitchField
        "GenericPitchField": PitchField,
        "SpecificPitchClassField": PitchField,
        "EnharmonicPitchField": PitchField,
        "SpecificPitchField": PitchField,
        "SpecificPitchField": PitchField,
        "MidiPitchField": PitchField,
        # Harmony hierarchy
        "WesternTertianHarmonyField": WesternTertianHarmonyField,
        "RomanNumeralHarmonyField": RomanNumeralHarmonyField,
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

    This function also checks registered entries that are subclasses of
    *field_type*.

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


def _discover_by_shape(
    table: pa.Table,
    field_type: type[SemanticField[Any]],
    cache: dict[tuple[str, str], SemanticField[Any]],
) -> list[SemanticField[Any]]:
    """Discover columns by delegating to ``field_type.matches_pa_field()``.

    Iterates the table schema in column order.  For each ``pa.Field`` that
    *field_type* (or one of its subclasses in the registry) claims via
    :py:meth:`SemanticField.matches_pa_field`, constructs the field via
    ``from_field()`` and caches it.

    This is the third-line discovery strategy used by
    :py:meth:`SemanticFieldAccessMixin.get_fields`, after metadata-based
    and ``_default_column``-based lookup both yield nothing.  It catches
    columns produced by loaders that have not (yet) injected
    ``b"timetoalign"`` metadata onto raw struct columns
    (e.g. ``midi_pitch`` / ``specific_pitch`` on TSV-loaded score notes).

    Args:
        table: The PyArrow table to search.
        field_type: The ``SemanticField`` subclass to match.
        cache: The field cache dict to populate.

    Returns:
        A list of discovered fields, ordered by their column position in
        the table schema.  Empty list if nothing matches.
    """
    result: list[SemanticField[Any]] = []
    schema = table.schema
    for i in range(len(schema)):
        pa_field = schema.field(i)
        if not field_type.matches_pa_field(pa_field):
            continue
        cache_key = (pa_field.name, field_type.__name__)
        cached = cache.get(cache_key)
        if cached is not None:
            result.append(cached)
            continue
        col = table.column(i)
        try:
            field = field_type.from_field((col, pa_field))
        except (TypeError, KeyError, ValueError):
            continue
        cache[cache_key] = field
        result.append(field)
    return result


# ---------------------------------------------------------------------------
# Raw field wrapping
# ---------------------------------------------------------------------------


def _wrap_raw(col: pa.ChunkedArray | pa.Array, pa_field: pa.Field) -> DataField:
    """Wrap a column in the appropriate raw ``DataField`` subclass."""
    dt = pa_field.type
    if pa.types.is_struct(dt):
        return StructField(col, pa_field)
    if pa.types.is_integer(dt) or pa.types.is_floating(dt):
        return NumericField(col, pa_field)
    if pa.types.is_string(dt) or pa.types.is_large_string(dt):
        return StringField(col, pa_field)
    if pa.types.is_map(dt):
        return MapField(col, pa_field)
    return _GenericField(col, pa_field)


# ---------------------------------------------------------------------------
# Default field resolution (start/end -> CoordinateField, duration -> DurationField)
# ---------------------------------------------------------------------------

_DEFAULT_FIELD_MAP: dict[str, str] | None = None


def _get_default_field_map() -> dict[str, str]:
    """Map default column names to semantic field class names."""
    global _DEFAULT_FIELD_MAP
    if _DEFAULT_FIELD_MAP is None:
        _DEFAULT_FIELD_MAP = {
            DefaultField.start.value: "CoordinateField",
            DefaultField.end.value: "CoordinateField",
            DefaultField.duration.value: "DurationField",
        }
    return _DEFAULT_FIELD_MAP


def _resolve_default_field(
    name: str,
    col: pa.ChunkedArray | pa.Array,
    pa_field: pa.Field,
) -> SemanticField[Any] | None:
    """Try to construct a semantic field for a default (core) column."""
    mapping = _get_default_field_map()
    ft_str = mapping.get(name)
    if ft_str is None:
        return None
    try:
        return _reconstruct_field(pa_field, col, ft_str)
    except (KeyError, TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# SemanticFieldAccessMixin
# ---------------------------------------------------------------------------


class SemanticFieldAccessMixin:
    """Base mixin for field access on EventData.

    Provides three access levels:

    - ``get_raw("name")`` -- raw ``DataField`` wrapper (no semantics).
    - ``get_field("name")`` -- ``SemanticField`` wrapper (typed scalars).
    - ``get_field(PitchField(ep="col"))`` -- blueprint resolution.

    Expects the host class to provide a ``_table`` attribute.
    """

    _table: pa.Table  # provided by EventData

    @property
    def _field_cache(self) -> dict[tuple[str, str], SemanticField[Any]]:
        try:
            return self.__field_cache
        except AttributeError:
            self.__field_cache: dict[tuple[str, str], SemanticField[Any]] = {}
            return self.__field_cache

    # -- get_raw() -----------------------------------------------------------

    def get_raw(self, name: str) -> DataField:
        """Return a raw ``DataField`` for the named column.

        The returned field is a ``StructField``, ``NumericField``,
        ``StringField``, or ``MapField`` -- whichever matches the
        column's PyArrow type.  No semantic metadata is attached.

        Args:
            name: Column name in the underlying table.

        Returns:
            A raw ``DataField`` wrapping the column data.

        Raises:
            KeyError: If *name* is not in the table.
        """
        if name not in self._table.column_names:
            raise KeyError(
                f"Column {name!r} not found. " f"Available: {self._table.column_names}"
            )
        col = self._table.column(name)
        pa_field = self._table.schema.field(name)
        return _wrap_raw(col, pa_field)

    # -- get_field() ---------------------------------------------------------

    def get_field(
        self,
        selector: str | type[SemanticField[Any]] | SemanticField[Any],
    ) -> SemanticField[Any]:
        """Return a semantic field, resolved from *selector*.

        Three forms are supported:

        1. **String** -- column name: ``get_field("start")``.  Checks
           column metadata for ``field_type``; falls back to
           ``DefaultField`` mapping for core temporal columns.
        2. **Class** -- ``get_field(PitchField)``.  Scans all
           columns for metadata matching the class.
        3. **Blueprint instance** -- ``get_field(PitchField(ep="col"))``.
           Resolves the named column using the blueprint's pitch type.

        Args:
            selector: Column name, ``SemanticField`` subclass, or
                blueprint instance.

        Returns:
            A ``SemanticField`` subclass instance (cached).

        Raises:
            KeyError: If no matching column is found.
        """
        if isinstance(selector, str):
            return self._get_field_by_name(selector)
        if isinstance(selector, type) and issubclass(selector, SemanticField):
            return self._get_field_by_class(selector)
        if isinstance(selector, SemanticField):
            return self._get_field_by_blueprint(selector)
        raise TypeError(
            f"get_field() expects str, SemanticField class, or blueprint instance, "
            f"got {type(selector).__name__}"
        )

    def get_fields(
        self, field_type: type[SemanticField[Any]]
    ) -> list[SemanticField[Any]]:
        """Return ALL columns matching *field_type*'s class hierarchy.

        Discovery uses three strategies, applied in order:

        1. **Metadata-based**: columns carrying ``b"timetoalign"`` JSON
           metadata with a ``field_type`` entry.
        2. **Default-column fallback**: tries to match *field_type*'s
           ``_default_column`` name against table columns.
        3. **Shape-based fallback**: scans all columns and constructs the
           field via ``cls.matches_pa_field()`` and ``cls.from_field()``.
           This catches loader output that has not (yet) injected
           ``b"timetoalign"`` metadata — e.g. raw ``midi_pitch`` /
           ``specific_pitch`` struct columns from the TSV loader.

        Returns the first non-empty result; never falls through to a
        later strategy once an earlier strategy finds anything.  Order
        matches column order in the table (with structural-match
        columns ordered by the table schema, returning the first
        match for the "first match" convention used by
        ``_get_field_by_class``).

        Args:
            field_type: The ``SemanticField`` subclass to search for.

        Returns:
            A list of matching ``SemanticField`` subclass instances
            (may be empty if nothing matches).
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

        # Strategy 2: schema-based discovery via _default_column
        result = _discover_by_schema(self._table, field_type, cache, registry)
        if result:
            return result

        # Strategy 3: structural discovery via cls.matches_pa_field()
        result = _discover_by_shape(self._table, field_type, cache)
        return result

    def has_field(self, field_type: type[SemanticField[Any]]) -> bool:
        """Check whether any column matches *field_type*.

        Args:
            field_type: The ``SemanticField`` subclass to search for.

        Returns:
            ``True`` if at least one matching column exists.
        """
        registry = _get_field_type_map()
        cache = self._field_cache

        for (_, cached_ft_str), _ in cache.items():
            cls = registry.get(cached_ft_str)
            if cls is not None and issubclass(cls, field_type):
                return True
        for (_, cached_ft_str), _ in cache.items():
            if cached_ft_str == field_type.__name__:
                return True

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

        # Strategy 3: structural match via field_type.matches_pa_field()
        for i in range(len(schema)):
            if field_type.matches_pa_field(schema.field(i)):
                return True

        return False

    # -- convenience accessors for default temporal fields -------------------

    def get_start_field(self) -> SemanticField[Any]:
        """Return the ``CoordinateField`` for the ``start`` column."""
        return self.get_field("start")

    def get_end_field(self) -> SemanticField[Any]:
        """Return the ``CoordinateField`` for the ``end`` column."""
        return self.get_field("end")

    def get_duration_field(self) -> SemanticField[Any]:
        """Return the ``DurationField`` for the ``duration`` column."""
        return self.get_field("duration")

    # -- private dispatch methods --------------------------------------------

    def _get_field_by_name(self, name: str) -> SemanticField[Any]:
        """Resolve a semantic field by column name."""
        if name not in self._table.column_names:
            raise KeyError(
                f"Column {name!r} not found. " f"Available: {self._table.column_names}"
            )
        cache = self._field_cache

        # Check cache first
        for (cached_name, _), cached_field in cache.items():
            if cached_name == name:
                return cached_field

        col = self._table.column(name)
        pa_field = self._table.schema.field(name)

        # Strategy 1: metadata-based
        ft_str = _parse_field_type_metadata(pa_field)
        if ft_str is not None:
            field = _reconstruct_field(pa_field, col, ft_str)
            cache[(name, ft_str)] = field
            return field

        # Strategy 2: default field mapping (start/end -> Coordinate, duration -> Duration)
        field = _resolve_default_field(name, col, pa_field)
        if field is not None:
            cache[(name, type(field).__name__)] = field
            return field

        raise KeyError(
            f"Column {name!r} has no semantic field metadata and is not "
            f"a default field. Use get_raw({name!r}) for raw access."
        )

    def _get_field_by_class(
        self, field_type: type[SemanticField[Any]]
    ) -> SemanticField[Any]:
        """Resolve a semantic field by class (legacy API)."""
        fields = self.get_fields(field_type)
        if not fields:
            raise KeyError(f"No column matching {field_type.__name__!r} found in table")
        return fields[0]

    def _get_field_by_blueprint(
        self, blueprint: SemanticField[Any]
    ) -> SemanticField[Any]:
        """Resolve a semantic field from a blueprint instance.

        A blueprint is a ``SemanticField`` constructed with column names
        instead of data (e.g. ``PitchField(ep="midi_pitch")``).  This
        method extracts the column from the table and constructs the
        live field.
        """
        from timetoalign.fields.pitch import PitchField as PitchFieldCls

        if isinstance(blueprint, PitchFieldCls) and blueprint.is_blueprint:
            col_name = blueprint._blueprint_column
            pitch_type = blueprint.pitch_type
            cache = self._field_cache
            cache_key = (col_name, f"PitchField:{pitch_type}")

            cached = cache.get(cache_key)
            if cached is not None:
                return cached

            if col_name not in self._table.column_names:
                raise KeyError(
                    f"Blueprint column {col_name!r} not found. "
                    f"Available: {self._table.column_names}"
                )

            col = self._table.column(col_name)
            pa_field = self._table.schema.field(col_name)
            field = PitchFieldCls.from_field((col, pa_field), pitch_type=pitch_type)
            cache[cache_key] = field
            return field

        raise TypeError(
            f"Blueprint resolution not supported for {type(blueprint).__name__}. "
            f"Only PitchField blueprints are currently supported."
        )


# ---------------------------------------------------------------------------
# PitchAccessMixin
# ---------------------------------------------------------------------------


class PitchAccessMixin(SemanticFieldAccessMixin):
    """Mixin providing pitch field access with priority-based defaults.

    Priority order (most informative first):
    SP > EP > SPC > GPC (by ``pitch_type`` attribute on ``PitchField``).
    """

    def get_pitch_field(
        self,
        pitch_field_type: type[PitchField] | None = None,
        *,
        format: str | None = None,
    ) -> PitchField:
        """Return a pitch field, optionally filtered by type.

        This is the one-stop-shop accessor for pitch data.  If
        *pitch_field_type* is ``None``, returns the most informative
        available pitch field.

        Args:
            pitch_field_type: Should be ``PitchField``.
                If ``None``, returns the most informative available.
            format: Format specifier for on-the-fly conversion
                (e.g., ``"midi"``, ``"specific"``, ``"generic"``).
                Reserved for future conversion support.

        Returns:
            A ``PitchField`` instance.

        Raises:
            KeyError: If no matching pitch column is found.
        """
        from timetoalign.fields.pitch import PitchField as PitchFieldCls

        if pitch_field_type is not None:
            result = self.get_field(pitch_field_type)  # type: ignore[return-value]
            if result is None:
                raise KeyError(f"No pitch field found for {pitch_field_type}")
            return result

        # Default: return the most informative available pitch field
        # Priority: sp > ep > spc > gpc
        _PRIORITY = ["sp", "ep", "spc", "gpc"]
        all_pitch = self.get_fields(PitchFieldCls)
        if not all_pitch:
            raise KeyError("No pitch field found in table")

        for pt in _PRIORITY:
            for pf in all_pitch:
                if pf.pitch_type == pt:
                    return pf  # type: ignore[return-value]
        return all_pitch[0]  # type: ignore[return-value]  # fallback


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
