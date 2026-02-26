"""Identity management for TTA objects.

This module provides scoped IDs that preserve source provenance
and generators for creating unique IDs within a scope.

Includes:
- ScopedId: An identifier with scope:local format.
- IdGenerator: General-purpose unique ID generation within a scope.
- TimelineIdGenerator: Generates systematic timeline IDs based on type
  (e.g., ``clt1``, ``dlt2``, ``score:clt1``, ``perf:dlt3``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    pass


@dataclass(frozen=True, slots=True)
class ScopedId:
    """An identifier with a scope prefix and local part.

    Format: "{scope}:{local}" or just "{local}" if scope is empty.

    The scope typically represents the source (e.g., "midi", "score")
    while the local part is the original ID from that source.

    Attributes:
        scope: The namespace/source prefix (e.g., "midi", "score:track1")
        local: The local identifier within that scope

    Examples:
        >>> ScopedId("midi", "n42")
        ScopedId(scope='midi', local='n42')

        >>> str(ScopedId("midi", "n42"))
        'midi:n42'

        >>> ScopedId.parse("midi:n42")
        ScopedId(scope='midi', local='n42')

        >>> ScopedId.parse("bare_id")
        ScopedId(scope='', local='bare_id')
    """

    scope: str
    local: str

    SEPARATOR: ClassVar[str] = ":"

    # Validation patterns
    _SCOPE_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^[a-zA-Z_][a-zA-Z0-9_.\-]*$"
    )
    _LOCAL_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^[^\s:]+$"
    )  # No whitespace or colons

    def __post_init__(self) -> None:
        # Allow empty scope
        if self.scope and not self._SCOPE_PATTERN.match(self.scope):
            raise ValueError(
                f"Invalid scope '{self.scope}': must start with letter/underscore, "
                f"contain only alphanumeric, underscore, dot, or hyphen"
            )
        if not self.local:
            raise ValueError("Local ID cannot be empty")
        if not self._LOCAL_PATTERN.match(self.local):
            raise ValueError(
                f"Invalid local ID '{self.local}': cannot contain whitespace or colons"
            )

    def __str__(self) -> str:
        if not self.scope:
            return self.local
        return f"{self.scope}{self.SEPARATOR}{self.local}"

    def __repr__(self) -> str:
        return f"ScopedId(scope={self.scope!r}, local={self.local!r})"

    @classmethod
    def parse(cls, id_str: str) -> ScopedId:
        """Parse a scoped ID string.

        Args:
            id_str: A string like "scope:local" or just "local"

        Returns:
            A ScopedId instance

        Examples:
            >>> ScopedId.parse("midi:n42")
            ScopedId(scope='midi', local='n42')

            >>> ScopedId.parse("bare_id")
            ScopedId(scope='', local='bare_id')
        """
        if cls.SEPARATOR in id_str:
            scope, local = id_str.split(cls.SEPARATOR, 1)
            return cls(scope=scope, local=local)
        return cls(scope="", local=id_str)

    def with_scope(self, new_scope: str) -> ScopedId:
        """Return a new ScopedId with a different scope."""
        return ScopedId(scope=new_scope, local=self.local)

    def with_local(self, new_local: str) -> ScopedId:
        """Return a new ScopedId with a different local part."""
        return ScopedId(scope=self.scope, local=new_local)

    def nested(self, child_scope: str) -> ScopedId:
        """Create a nested scope by appending to the current scope.

        Example:
            >>> ScopedId("midi", "note").nested("track1")
            ScopedId(scope='midi.track1', local='note')
        """
        if self.scope:
            new_scope = f"{self.scope}.{child_scope}"
        else:
            new_scope = child_scope
        return ScopedId(scope=new_scope, local=self.local)

    @property
    def is_scoped(self) -> bool:
        """Whether this ID has a non-empty scope."""
        return bool(self.scope)


@dataclass
class IdGenerator:
    """Generates unique IDs within a given scope.

    Supports both:
    1. Wrapping external IDs with the scope
    2. Generating new IDs when none provided

    Tracks seen IDs to detect collisions.

    Attributes:
        scope: The scope to apply to all generated/wrapped IDs

    Examples:
        >>> gen = IdGenerator("midi")

        >>> gen.get_or_create("n42")  # Wrap external ID
        'midi:n42'

        >>> gen.get_or_create(None, type_hint="note")  # Generate
        'midi:note_1'

        >>> gen.get_or_create(None, type_hint="note")  # Generate next
        'midi:note_2'
    """

    scope: str

    # Internal state
    _counters: dict[str, int] = field(default_factory=dict)
    _seen: set[str] = field(default_factory=set)

    def get_or_create(
        self,
        external_id: str | None = None,
        type_hint: str = "event",
    ) -> str:
        """Get a scoped ID string.

        Args:
            external_id: The ID from the source, if any. Will be wrapped
                        with the scope but otherwise preserved.
            type_hint: A prefix for generated IDs if external_id is None.

        Returns:
            A string in "scope:local_id" format (or just "local_id" if
            scope is empty).
        """
        if external_id is not None and str(external_id).strip():
            # Wrap external ID
            local = str(external_id).strip()
        else:
            # Generate new ID
            counter = self._counters.get(type_hint, 0) + 1
            self._counters[type_hint] = counter
            local = f"{type_hint}_{counter}"

        # Create scoped ID
        scoped = ScopedId(self.scope, local)
        full_id = str(scoped)

        # Track for collision detection (we don't raise, just track)
        self._seen.add(full_id)

        return full_id

    def create(self, type_hint: str = "event") -> str:
        """Generate a new unique ID (no external ID)."""
        return self.get_or_create(None, type_hint=type_hint)

    def wrap(self, external_id: str) -> str:
        """Wrap an external ID with the scope."""
        return self.get_or_create(external_id)

    def reset(self) -> None:
        """Reset all counters and seen IDs."""
        self._counters.clear()
        self._seen.clear()

    def reset_counters(self) -> None:
        """Reset counters but keep seen IDs (for continuation)."""
        self._counters.clear()

    @property
    def count(self) -> int:
        """Total number of IDs generated/wrapped."""
        return len(self._seen)

    def has_seen(self, id_str: str) -> bool:
        """Check if an ID has been generated/wrapped by this generator."""
        return id_str in self._seen


# Mapping from timeline class name to type-based prefix.
# See AGENTS.md section 1.10 for the canonical scheme.
_TIMELINE_TYPE_PREFIXES: dict[str, str] = {
    "ContinuousLogicalTimeline": "clt",
    "DiscreteLogicalTimeline": "dlt",
    "ContinuousPhysicalTimeline": "cpt",
    "DiscretePhysicalTimeline": "dpt",
    "ContinuousGraphicalTimeline": "cgt",
    "DiscreteGraphicalTimeline": "dgt",
}


@dataclass
class TimelineIdGenerator:
    """Generates systematic timeline IDs based on type.

    Timeline IDs follow the pattern ``{prefix}{N}`` where prefix
    encodes the timeline type (domain + continuity) and N is a
    1-indexed counter scoped to this generator instance.

    When a role is specified, the ID becomes ``{role}:{prefix}{N}``
    (e.g., ``score:clt1``, ``perf:dlt3``).

    The counter N is scoped per prefix per generator. Each generator
    instance maintains its own counter state, so different loaders
    do not interfere with each other.

    Attributes:
        _counters: Per-prefix counter state.
        _id_to_meta: Maps generated IDs to metadata dicts for lookup.

    Examples:
        >>> gen = TimelineIdGenerator()
        >>> gen.next_id("ContinuousLogicalTimeline")
        'clt1'
        >>> gen.next_id("ContinuousLogicalTimeline")
        'clt2'
        >>> gen.next_id("DiscreteLogicalTimeline")
        'dlt1'
        >>> gen.next_id_with_role("DiscreteLogicalTimeline", "perf")
        'perf:dlt2'
    """

    _counters: dict[str, int] = field(default_factory=dict)
    _id_to_meta: dict[str, dict[str, object]] = field(default_factory=dict)

    def _get_prefix(self, timeline_type: type | str) -> str:
        """Resolve the prefix for a timeline type.

        Args:
            timeline_type: A timeline class or its name as a string.

        Returns:
            The type-based prefix (e.g., 'clt', 'dlt').

        Raises:
            ValueError: If the timeline type is not recognised.
        """
        if isinstance(timeline_type, str):
            type_name = timeline_type
        else:
            type_name = timeline_type.__name__

        prefix = _TIMELINE_TYPE_PREFIXES.get(type_name)
        if prefix is None:
            # Fallback: try to resolve from base Timeline
            if type_name == "Timeline":
                return "tl"
            raise ValueError(
                f"Unknown timeline type '{type_name}'. "
                f"Expected one of: {', '.join(_TIMELINE_TYPE_PREFIXES.keys())}"
            )
        return prefix

    def next_id(
        self,
        timeline_type: type | str,
        *,
        meta: dict[str, object] | None = None,
    ) -> str:
        """Generate the next ID for a given timeline type.

        Args:
            timeline_type: A timeline class or class name string.
            meta: Optional metadata to associate with this ID.

        Returns:
            An ID like ``clt1``, ``dlt2``, etc.
        """
        prefix = self._get_prefix(timeline_type)
        counter = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = counter
        tid = f"{prefix}{counter}"
        if meta:
            self._id_to_meta[tid] = dict(meta)
        return tid

    def next_id_with_role(
        self,
        timeline_type: type | str,
        role: str,
        *,
        meta: dict[str, object] | None = None,
    ) -> str:
        """Generate the next ID with a role prefix.

        The role is prepended as ``{role}:{prefix}{N}``.

        Args:
            timeline_type: A timeline class or class name string.
            role: The role prefix (e.g., 'score', 'perf').
            meta: Optional metadata to associate with this ID.

        Returns:
            An ID like ``score:clt1``, ``perf:dlt3``.
        """
        prefix = self._get_prefix(timeline_type)
        counter = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = counter
        tid = f"{role}:{prefix}{counter}"
        if meta:
            self._id_to_meta[tid] = dict(meta)
        return tid

    def get_meta(self, timeline_id: str) -> dict[str, object] | None:
        """Retrieve metadata associated with a generated ID.

        Args:
            timeline_id: A previously generated timeline ID.

        Returns:
            The metadata dict, or None if no metadata was stored.
        """
        return self._id_to_meta.get(timeline_id)

    def reset(self) -> None:
        """Reset all counters and metadata."""
        self._counters.clear()
        self._id_to_meta.clear()

    @property
    def count(self) -> int:
        """Total number of IDs generated."""
        return sum(self._counters.values())
