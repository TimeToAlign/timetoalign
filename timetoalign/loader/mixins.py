"""Semantic field access mixins for EventData subclasses.

Provides three levels of field access on ``EventData``:

- **``events.table``** -- direct access to the underlying ``pa.Table``
  (specialist use only).
- **``events.get_raw("name")``** -- returns a raw ``DataField``
  (``StructField``, ``NumericField``, etc.) wrapping the field.
- **``events.get_field(...)``** -- returns a ``SemanticField`` wrapping
  the field with semantic identity and typed scalar access.

``get_field()`` accepts three argument forms:

1. ``get_field("start")`` -- string field name; looks up metadata or
   default-field mapping to determine the ``SemanticField`` subclass.
2. ``get_field(EnharmonicPitchField)`` -- a class; scans all fields
   for metadata or shape matching that class.
3. ``get_field(EnharmonicPitchField(source_fields="midi_pitch"))`` --
   a *blueprint* instance; resolves the named source field on the
   table (or a dict-shaped spec for multi-field blueprints) and caches
   the result.

Domain mixins add convenience accessors with priority-based defaults
and ``format=`` parameters for on-the-fly conversion:

- ``PitchAccessMixin`` -- ``get_pitch_field(type, format=)``
- ``HarmonyAccessMixin`` -- ``get_harmony_field(type, format=)``
- ``MeasureAccessMixin`` -- ``get_measure_field(format=)`` (placeholder)
"""

from __future__ import annotations

import enum
import json
from typing import Any

import pyarrow as pa

from timetoalign.core.fields import (
    DataField,
    MapField,
    NumericField,
    SemanticField,
    StringField,
    StructField,
    _GenericField,
)

_TIMETOALIGN_KEY = b"timetoalign"


# ---------------------------------------------------------------------------
# DefaultField -- core temporal fields present on every EventData
# ---------------------------------------------------------------------------


class DefaultField(enum.Enum):
    """Core temporal fields present on every EventData table.

    These map field names to the ``SemanticField`` subclass that
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
    """Return the field_type string -> class mapping, building it on first call.

    Each paired ``XField(SemanticField[X])`` owns exactly one entry here.
    No umbrella classes, no legacy aliases.
    """
    global _FIELD_TYPE_MAP
    if _FIELD_TYPE_MAP is not None:
        return _FIELD_TYPE_MAP

    from timetoalign.core.events import (
        DcmlHarmonyField,
        EnharmonicPitchClassField,
        EnharmonicPitchField,
        GenericPitchClassField,
        GenericPitchField,
        HarmonyLabelField,
        MeasureField,
        MidiPitchField,
        NoteField,
        PitchBasedHarmonyField,
        RomanNumeralHarmonyField,
        SpecificPitchClassField,
        SpecificPitchField,
        WesternTertianHarmonyField,
    )
    from timetoalign.core.time import CoordinateField, DurationField

    _FIELD_TYPE_MAP = {
        # Coordinate / Duration
        "CoordinateField": CoordinateField,
        "DurationField": DurationField,
        # Pitch — paired classes only
        "EnharmonicPitchField": EnharmonicPitchField,
        "EnharmonicPitchClassField": EnharmonicPitchClassField,
        "GenericPitchField": GenericPitchField,
        "GenericPitchClassField": GenericPitchClassField,
        "MidiPitchField": MidiPitchField,
        "SpecificPitchField": SpecificPitchField,
        "SpecificPitchClassField": SpecificPitchClassField,
        # Harmony — paired classes only
        "DcmlHarmonyField": DcmlHarmonyField,
        "HarmonyLabelField": HarmonyLabelField,
        "PitchBasedHarmonyField": PitchBasedHarmonyField,
        "RomanNumeralHarmonyField": RomanNumeralHarmonyField,
        "WesternTertianHarmonyField": WesternTertianHarmonyField,
        # Event scalars
        "MeasureField": MeasureField,
        "NoteField": NoteField,
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
    """Reconstruct a ``SemanticField`` subclass from field data and metadata."""
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
    """Try to match *field_type* against table fields by schema structure.

    Each concrete ``SemanticField`` subclass may declare a
    ``_default_field_name`` attribute (the expected field name) and optionally
    a ``_expected_schema`` (the PyArrow struct type to match).  When the
    table contains a field with a matching name and compatible struct
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
    field_names = set(table.column_names)

    # Collect candidate classes: the field_type itself + any registered
    # subclasses that are subclasses of field_type.
    candidates: list[type[SemanticField[Any]]] = []
    if hasattr(field_type, "_default_field_name"):
        candidates.append(field_type)
    for cls in registry.values():
        if cls is field_type:
            continue
        if issubclass(cls, field_type) and hasattr(cls, "_default_field_name"):
            if cls not in candidates:
                candidates.append(cls)

    for cls in candidates:
        field_name = cls._default_field_name  # type: ignore[attr-defined]
        if field_name not in field_names:
            continue

        cache_key = (field_name, cls.__name__)
        cached = cache.get(cache_key)
        if cached is not None:
            result.append(cached)
            continue

        arr = table.column(field_name)
        pa_field = table.schema.field(field_name)

        # Verify the field is a struct (SemanticFields wrap struct arrays)
        if not pa.types.is_struct(pa_field.type):
            continue

        try:
            field = cls.from_field((arr, pa_field))
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
    """Discover fields by delegating to ``field_type.matches_pa_field()``.

    Iterates the table schema in field order.  For each ``pa.Field`` that
    *field_type* (or one of its subclasses in the registry) claims via
    :py:meth:`SemanticField.matches_pa_field`, constructs the field via
    ``from_field()`` and caches it.

    This is the third-line discovery strategy used by
    :py:meth:`SemanticFieldAccessMixin.get_fields`, after metadata-based
    and ``_default_field_name``-based lookup both yield nothing.  It catches
    fields produced by loaders that have not (yet) injected
    ``b"timetoalign"`` metadata onto raw struct fields
    (e.g. ``midi_pitch`` / ``specific_pitch`` on TSV-loaded score notes).

    Args:
        table: The PyArrow table to search.
        field_type: The ``SemanticField`` subclass to match.
        cache: The field cache dict to populate.

    Returns:
        A list of discovered fields, ordered by their position in
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
        arr = table.column(i)
        try:
            field = field_type.from_field((arr, pa_field))
        except (TypeError, KeyError, ValueError):
            continue
        cache[cache_key] = field
        result.append(field)
    return result


# ---------------------------------------------------------------------------
# Raw field wrapping
# ---------------------------------------------------------------------------


def _wrap_raw(col: pa.ChunkedArray | pa.Array, pa_field: pa.Field) -> DataField:
    """Wrap a field's array in the appropriate raw ``DataField`` subclass."""
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
    """Map default field names to semantic field class names."""
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
    """Try to construct a semantic field for a default (core) field name."""
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
        """Return a raw ``DataField`` for the named field.

        The returned field is a ``StructField``, ``NumericField``,
        ``StringField``, or ``MapField`` -- whichever matches the
        field's PyArrow type.  No semantic metadata is attached.

        Args:
            name: Field name in the underlying table.

        Returns:
            A raw ``DataField`` wrapping the field data.

        Raises:
            KeyError: If *name* is not in the table.
        """
        if name not in self._table.column_names:
            raise KeyError(
                f"Field {name!r} not found. " f"Available: {self._table.column_names}"
            )
        arr = self._table.column(name)
        pa_field = self._table.schema.field(name)
        return _wrap_raw(arr, pa_field)

    # -- get_field() ---------------------------------------------------------

    def get_field(
        self,
        selector: str | type[SemanticField[Any]] | SemanticField[Any],
    ) -> SemanticField[Any]:
        """Return a semantic field, resolved from *selector*.

        Three forms are supported:

        1. **String** -- field name: ``get_field("start")``.  Checks
           field metadata for ``field_type``; falls back to
           ``DefaultField`` mapping for core temporal fields.
        2. **Class** -- ``get_field(PitchField)``.  Scans all
           fields for metadata matching the class.
        3. **Blueprint instance** -- ``get_field(PitchField(ep="col"))``.
           Resolves the named field using the blueprint's pitch type.

        Args:
            selector: Field name, ``SemanticField`` subclass, or
                blueprint instance.

        Returns:
            A ``SemanticField`` subclass instance (cached).

        Raises:
            KeyError: If no matching field is found.
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
        """Return ALL fields matching *field_type*'s class hierarchy.

        Discovery uses three strategies, applied in order:

        1. **Metadata-based**: fields carrying ``b"timetoalign"`` JSON
           metadata with a ``field_type`` entry.
        2. **Default-field-name fallback**: tries to match *field_type*'s
           ``_default_field_name`` against table fields.
        3. **Shape-based fallback**: scans all fields and constructs the
           field via ``cls.matches_pa_field()`` and ``cls.from_field()``.
           This catches loader output that has not (yet) injected
           ``b"timetoalign"`` metadata — e.g. raw ``midi_pitch`` /
           ``specific_pitch`` struct fields from the TSV loader.

        Returns the first non-empty result; never falls through to a
        later strategy once an earlier strategy finds anything.  Order
        matches field order in the table (with structural-match
        fields ordered by the table schema, returning the first
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
                    arr = self._table.column(i)
                    field = _reconstruct_field(pa_field, arr, ft_str)
                    cache[cache_key] = field
                    result.append(field)

        if result:
            return result

        # Strategy 2: schema-based discovery via _default_field_name
        result = _discover_by_schema(self._table, field_type, cache, registry)
        if result:
            return result

        # Strategy 3: structural discovery via cls.matches_pa_field()
        result = _discover_by_shape(self._table, field_type, cache)
        return result

    def has_field(self, field_type: type[SemanticField[Any]]) -> bool:
        """Check whether any field matches *field_type*.

        Args:
            field_type: The ``SemanticField`` subclass to search for.

        Returns:
            ``True`` if at least one matching field exists.
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

        field_names = set(self._table.column_names)
        candidates: list[type[SemanticField[Any]]] = []
        if hasattr(field_type, "_default_field_name"):
            candidates.append(field_type)
        for cls in registry.values():
            if cls is field_type:
                continue
            if issubclass(cls, field_type) and hasattr(cls, "_default_field_name"):
                if cls not in candidates:
                    candidates.append(cls)
        for cls in candidates:
            field_name = cls._default_field_name  # type: ignore[attr-defined]
            if field_name in field_names:
                pa_field = self._table.schema.field(field_name)
                if pa.types.is_struct(pa_field.type):
                    return True

        # Strategy 3: structural match via field_type.matches_pa_field()
        for i in range(len(schema)):
            if field_type.matches_pa_field(schema.field(i)):
                return True

        return False

    # -- convenience accessors for default temporal fields -------------------

    def get_start_field(self) -> SemanticField[Any]:
        """Return the ``CoordinateField`` for the ``start`` field."""
        return self.get_field("start")

    def get_end_field(self) -> SemanticField[Any]:
        """Return the ``CoordinateField`` for the ``end`` field."""
        return self.get_field("end")

    def get_duration_field(self) -> SemanticField[Any]:
        """Return the ``DurationField`` for the ``duration`` field."""
        return self.get_field("duration")

    # -- private dispatch methods --------------------------------------------

    def _get_field_by_name(self, name: str) -> SemanticField[Any]:
        """Resolve a semantic field by field name."""
        if name not in self._table.column_names:
            raise KeyError(
                f"Field {name!r} not found. " f"Available: {self._table.column_names}"
            )
        cache = self._field_cache

        # Check cache first
        for (cached_name, _), cached_field in cache.items():
            if cached_name == name:
                return cached_field

        arr = self._table.column(name)
        pa_field = self._table.schema.field(name)

        # Strategy 1: metadata-based
        ft_str = _parse_field_type_metadata(pa_field)
        if ft_str is not None:
            field = _reconstruct_field(pa_field, arr, ft_str)
            cache[(name, ft_str)] = field
            return field

        # Strategy 2: default field mapping (start/end -> Coordinate, duration -> Duration)
        field = _resolve_default_field(name, arr, pa_field)
        if field is not None:
            cache[(name, type(field).__name__)] = field
            return field

        raise KeyError(
            f"Field {name!r} has no semantic field metadata and is not "
            f"a default field. Use get_raw({name!r}) for raw access."
        )

    def _get_field_by_class(
        self, field_type: type[SemanticField[Any]]
    ) -> SemanticField[Any]:
        """Resolve a semantic field by class (legacy API)."""
        fields = self.get_fields(field_type)
        if not fields:
            raise KeyError(f"No field matching {field_type.__name__!r} found in table")
        return fields[0]

    def _get_field_by_blueprint(
        self, blueprint: SemanticField[Any]
    ) -> SemanticField[Any]:
        """Resolve a semantic field from a blueprint instance.

        A blueprint is a paired ``SemanticField`` constructed with a
        ``source_fields`` specification (see
        :meth:`SemanticField.__init__`).  Two spec shapes are supported
        here:

        * a ``str`` — interpreted as the name of a field exposed by the
          underlying ``pa.Table`` (must carry a struct congruent with
          ``type(blueprint).pa_schema``);
        * a ``dict`` — recursively maps the paired class's
          :attr:`pa_schema` sub-field names to source-field names on
          the table (only single-level dicts are handled today;
          full nested dispatch is reserved for a follow-up as more
          SemanticField shapes need it).
        """
        if not getattr(blueprint, "is_blueprint", False):
            raise TypeError(
                f"Blueprint resolution requires a blueprint-mode SemanticField, "
                f"got {type(blueprint).__name__}"
            )

        spec = blueprint._blueprint_source_fields
        if spec is None:
            raise TypeError(
                f"{type(blueprint).__name__} blueprint has no source_fields attached"
            )

        # Only the string-spec path is wired up at this revision.  Dict
        # specs are validated up front by ``resolve_source_fields`` but
        # the table-side resolver below still expects a single name.
        if not isinstance(spec, str):
            raise NotImplementedError(
                f"{type(blueprint).__name__} blueprint resolution from a dict "
                "source_fields= spec is not implemented yet; pass a single "
                "source-field name as a string."
            )
        field_name = spec

        cache = self._field_cache
        cache_key = (field_name, type(blueprint).__name__)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        if field_name not in self._table.column_names:
            raise KeyError(
                f"Blueprint source field {field_name!r} not found. "
                f"Available: {self._table.column_names}"
            )

        arr = self._table.column(field_name)
        pa_field = self._table.schema.field(field_name)
        field = type(blueprint).from_field((arr, pa_field))
        cache[cache_key] = field
        return field


# ---------------------------------------------------------------------------
# PitchAccessMixin
# ---------------------------------------------------------------------------


class PitchAccessMixin(SemanticFieldAccessMixin):
    """Mixin providing pitch field access with priority-based defaults.

    Priority order (most informative first):
    ``SpecificPitchField`` > ``EnharmonicPitchField`` >
    ``SpecificPitchClassField`` > ``GenericPitchClassField``.
    """

    def get_pitch_field(
        self,
        pitch_field_type: type[SemanticField[Any]] | None = None,
        *,
        format: str | None = None,
    ) -> SemanticField[Any]:
        """Return a pitch field, optionally filtered by class.

        Args:
            pitch_field_type: A specific paired ``XField`` class (e.g.
                ``EnharmonicPitchField``).  If ``None``, returns the most
                informative available pitch field from the priority list.
            format: Format specifier for on-the-fly conversion.
                Reserved for future conversion support.

        Raises:
            KeyError: If no matching pitch field is found.
        """
        from timetoalign.core.events import (
            EnharmonicPitchField,
            GenericPitchClassField,
            SpecificPitchClassField,
            SpecificPitchField,
        )

        if pitch_field_type is not None:
            return self.get_field(pitch_field_type)

        # Priority: SP > EP > SPC > GPC
        priority: list[type[SemanticField[Any]]] = [
            SpecificPitchField,
            EnharmonicPitchField,
            SpecificPitchClassField,
            GenericPitchClassField,
        ]
        for cls in priority:
            try:
                fields = self.get_fields(cls)
            except KeyError:
                fields = []
            if fields:
                return fields[0]

        raise KeyError("No pitch field found in table")


# ---------------------------------------------------------------------------
# HarmonyAccessMixin
# ---------------------------------------------------------------------------


class HarmonyAccessMixin(SemanticFieldAccessMixin):
    """Mixin providing harmony field access with priority-based defaults.

    Priority order (most specific first):
    ``DcmlHarmonyField`` > ``RomanNumeralHarmonyField`` >
    ``WesternTertianHarmonyField`` > ``PitchBasedHarmonyField`` >
    ``HarmonyLabelField``.
    """

    def get_harmony_field(
        self,
        harmony_type: type[SemanticField[Any]] | None = None,
        *,
        format: str | None = None,
    ) -> SemanticField[Any]:
        """Return a harmony field, optionally filtered by class.

        Args:
            harmony_type: A specific paired harmony class to request.
                If ``None``, returns the most specific available.
            format: Format specifier for on-the-fly conversion.
                Reserved for future conversion support.

        Raises:
            KeyError: If no matching harmony field is found.
        """
        from timetoalign.core.events import (
            DcmlHarmonyField,
            HarmonyLabelField,
            PitchBasedHarmonyField,
            RomanNumeralHarmonyField,
            WesternTertianHarmonyField,
        )

        if harmony_type is not None:
            return self.get_field(harmony_type)

        priority: list[type[SemanticField[Any]]] = [
            DcmlHarmonyField,
            RomanNumeralHarmonyField,
            WesternTertianHarmonyField,
            PitchBasedHarmonyField,
            HarmonyLabelField,
        ]
        for ht in priority:
            if self.has_field(ht):
                return self.get_field(ht)

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
