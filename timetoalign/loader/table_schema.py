"""TableSchema: Semantic field specifications for TimeToAlign! data loading.

This module provides a comprehensive schema system for interpreting tabular data
as TimeToAlign! objects (Timelines, Events, Regions, C-Maps, MatchClaims).

The key insight is that tabular data encodes multiple semantic relationships:
1. **Coordinates** - Where events live on a timeline (start, end, duration)
2. **Conversions** - Coordinates in different units (C-Maps)
3. **Partitions** - Multiple independent timelines in one table
4. **Hierarchy** - Parent-child relationships within one timeline
5. **Regions** - Named TimeIntervals
6. **Matches** - References to events on other timelines

Example - A typical annotation table:

    | id  | onset_sec | onset_beat | measure | voice | region  | matched_score_id |
    |-----|-----------|------------|---------|-------|---------|------------------|
    | e1  | 0.0       | 0.0        | 1       | sop   | Intro   | s1               |
    | e2  | 2.5       | 4.0        | 2       | sop   | Intro   | s2               |

This single table encodes:
- Events with TWO coordinate systems (seconds, beats) -> C-Map implied
- Multiple timelines (partitioned by voice)
- A named region ("Intro")
- Match claims (e1 matches s1 on another timeline)

Usage:

    >>> schema = TableSchema(
    ...     timeline=TimelineDefaults(unit=TimeUnit.seconds),
    ...     coordinates=CoordinateSpec(
    ...         start="onset_sec",
    ...         cmap_fields={"onset_beat": CMapField(target_unit=TimeUnit.quarters)},
    ...     ),
    ...     partitions=PartitionSpec(fields=["voice"]),
    ...     regions=RegionSpec(fields=["region"]),
    ...     matches=MatchSpec(fields={"matched_score_id": MatchField(
    ...         target_timeline="score", target_event_field="id"
    ...     )}),
    ... )
    >>> results = schema.create_timelines(df)  # Returns dict[str, Timeline]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Literal

import numpy as np
import pandas as pd
import pyarrow as pa

from timetoalign.core import NumberType, TimeUnit
from timetoalign.core.enums import ColumnRole, PartitionMode

# Import from specific submodules to avoid circular imports
# (timetoalign/__init__.py imports loader, which imports table_schema)
from timetoalign.timelines.base import Timeline

if TYPE_CHECKING:
    from timetoalign.alignment import (  # noqa: F401
        AlignmentAnchor,
        MatchClaim,
        MatchMetadata,
    )

module_logger = logging.getLogger(__name__)


# region Enums


# endregion


# region Field Specifications


@dataclass(frozen=True)
class CMapField:
    """Specification for a field that defines a ConversionMap target.

    A C-Map field contains coordinates in a different unit than the primary
    timeline. Loading this field creates a C-Map (or TableMap) converting
    from the primary unit to the target unit.

    Attributes:
        target_unit: The TimeUnit of coordinates in this field.
        source_field: The primary coordinate field this maps from.
            Defaults to the start field if not specified.
        map_type: Type of C-Map to create:
            - "table": TableMap from explicit coordinate pairs (default).
            - "linear": LinearMap fit from coordinate pairs.
            - "interpolation": InterpolationMap for O(log n) lookup.
        bidirectional: If True, also create the inverse map.

    Examples:
        >>> # Field with beat positions -> creates TableMap(seconds -> beats)
        >>> CMapField(target_unit=TimeUnit.quarters)

        >>> # Field with measure numbers
        >>> CMapField(target_unit=TimeUnit.measures)
    """

    target_unit: TimeUnit
    source_field: str | None = None
    map_type: Literal["table", "linear", "interpolation"] = "table"
    bidirectional: bool = True


@dataclass(frozen=True)
class MatchField:
    """Specification for a field that references events on another timeline.

    A Match field contains identifiers of events on a different timeline,
    creating MatchClaims when the data is loaded.

    Attributes:
        target_timeline: ID or role of the timeline containing matched events.
            Can be:
            - Explicit ID: "score:1"
            - Partition value: References another partition's timeline
            - External: Name of an externally-provided timeline
        target_event_field: Field in target timeline's data containing event IDs.
            If not specified, assumes the target uses the same ID scheme.
        is_synchronous: Whether matches represent temporal synchrony (True)
            or conceptual correspondence (False, e.g., structural alignment).
        match_metadata: Default metadata for generated MatchClaims.

    Examples:
        >>> # Field referencing score events by ID
        >>> MatchField(target_timeline="score", target_event_field="note_id")

        >>> # Conceptual match (same structural position, not same time)
        >>> MatchField(
        ...     target_timeline="analysis_v2",
        ...     is_synchronous=False,
        ... )
    """

    target_timeline: str
    target_event_field: str | None = None
    is_synchronous: bool = True
    match_metadata: dict[str, Any] | None = None


@dataclass
class ExtraField:
    """Specification for an extra data field.

    This is a simplified version of the existing ConvertedField for the new schema.

    Attributes:
        name: Output field name in the EventData.
        dtype: PyArrow data type (or type hint for inference).
        source: Source field name if different from name.
        converter: Optional transformation function.
        nullable: Whether nulls are allowed.
    """

    name: str
    dtype: type | pa.DataType | str | None = None
    source: str | None = None
    converter: Callable[[Any], Any] | None = None
    nullable: bool = True


# endregion


# region Structural Specifications


@dataclass
class TimelineDefaults:
    """Default parameters for timeline creation.

    These values are used when creating Timeline objects from the table data.

    Attributes:
        unit: The TimeUnit for the primary coordinate system.
        number_type: Number type for coordinates (float, int, fraction).
        domain: Override the domain (normally inferred from unit).
        id_prefix: Prefix for auto-generated timeline IDs.
        default_event_type: Event type when not specified in data.
        locked: Whether created timelines should be locked.
        meta: Additional metadata for created timelines.

    Examples:
        >>> TimelineDefaults(
        ...     unit=TimeUnit.quarters,
        ...     number_type=NumberType.fraction,
        ...     default_event_type="Note",
        ... )
    """

    unit: TimeUnit = TimeUnit.seconds
    number_type: NumberType = NumberType.float
    domain: str | None = None  # Infer from unit if None
    id_prefix: str = "tl"
    default_event_type: str = "Event"
    locked: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


# Sentinel for "not specified" vs "explicitly set to None"
_UNSET = object()


@dataclass
class CoordinateSpec:
    """Specification for coordinate fields.

    Defines which fields hold temporal coordinates and how to interpret them.

    Attributes:
        start: Field for start coordinates (required for interval events).
        end: Field for end coordinates (optional, None for instant events).
        duration: Alternative to end - compute end as start + duration.
        instant: Field for instant event coordinates (alternative to start).
        cmap_fields: Fields containing coordinates in other units.
            Each creates a ConversionMap.

    Invariants:
        - Must have at least one of: start, instant
        - If end is None and duration is None, events are instants
        - cmap_fields are in ADDITION to the primary coordinate field

    Examples:
        >>> # Interval events with explicit end
        >>> CoordinateSpec(start="onset", end="offset")

        >>> # Interval events with duration
        >>> CoordinateSpec(start="onset_sec", duration="length")

        >>> # Instant events
        >>> CoordinateSpec(instant="timestamp")

        >>> # With beat coordinates for C-Map
        >>> CoordinateSpec(
        ...     start="onset_sec",
        ...     end="offset_sec",
        ...     cmap_fields={"onset_beat": CMapField(TimeUnit.quarters)},
        ... )

    Raises:
        ValueError: If both start and instant are explicitly set to None.
    """

    start: str | None | object = field(default=_UNSET)
    end: str | None = None
    duration: str | None = None
    instant: str | None | object = field(default=_UNSET)
    cmap_fields: dict[str, CMapField] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate coordinate specification.

        Raises:
            ValueError: If both start and instant are explicitly set to None.
        """
        # Check for explicit None assignment (vs unset)
        start_is_explicit_none = self.start is None
        instant_is_explicit_none = self.instant is None
        start_is_unset = self.start is _UNSET
        instant_is_unset = self.instant is _UNSET

        # If both are explicitly None, that's an error
        if start_is_explicit_none and instant_is_explicit_none:
            raise ValueError(
                "CoordinateSpec requires at least one of 'start' or 'instant' fields. "
                "Both cannot be explicitly set to None."
            )

        # If start is unset but instant is provided, leave start as None
        if start_is_unset and not instant_is_unset:
            object.__setattr__(self, "start", None)
        # If instant is unset but start is provided, leave instant as None
        elif instant_is_unset and not start_is_unset:
            object.__setattr__(self, "instant", None)
        # If both are unset, default start to "start"
        elif start_is_unset and instant_is_unset:
            object.__setattr__(self, "start", "start")
            object.__setattr__(self, "instant", None)


@dataclass
class PartitionSpec:
    """Specification for partitioning a table into multiple timelines.

    A partition field groups rows such that each unique value (or combination
    of values) creates a separate timeline. The mode determines whether these
    timelines have independent coordinate systems (SEPARATE) or share a parent
    coordinate system (CHILDREN).

    Attributes:
        fields: Field names that define the partition key.
            Multiple fields create a composite key.
        mode: How to handle partitioned timelines:
            - SEPARATE: Independent timelines with disparate coordinates.
            - CHILDREN: Child timelines sharing parent's coordinates.
        parent_timeline: For CHILDREN mode, the ID of the parent timeline.
            If None, creates a new parent timeline.
        include_null: Whether to create a timeline for rows with null partition values.
        timeline_name_template: Template for naming partitioned timelines.
            Use {field_name} for substitution.

    Examples:
        >>> # Separate timeline per voice (independent coordinate systems)
        >>> PartitionSpec(fields=["voice"], mode=PartitionMode.separate)

        >>> # Child timelines per staff (shared coordinates)
        >>> PartitionSpec(
        ...     fields=["staff"],
        ...     mode=PartitionMode.children,
        ...     parent_timeline="score",
        ... )

        >>> # Composite partition key
        >>> PartitionSpec(fields=["piece_id", "movement"])
    """

    fields: list[str] = field(default_factory=list)
    mode: PartitionMode = PartitionMode.separate
    parent_timeline: str | None = None
    include_null: bool = False
    timeline_name_template: str = "{value}"


@dataclass
class HierarchySpec:
    """Specification for hierarchical timeline structure.

    Defines parent-child relationships within the loaded data. Unlike partitions
    (which create sibling timelines), hierarchy creates nested timelines.

    Attributes:
        parent_id_field: Field containing parent event/timeline IDs.
        child_id_field: Field containing child event/timeline IDs.
        segment_name_field: Field containing segment names.
        offset_field: Field containing child offsets relative to parent.
            If None, children start at their first event's coordinate.

    Note: This is for explicit hierarchy in the DATA. Partition-based hierarchy
    (PartitionSpec with mode=CHILDREN) is an alternative approach.

    Examples:
        >>> # Measure -> beat hierarchy
        >>> HierarchySpec(
        ...     parent_id_field="measure_id",
        ...     child_id_field="beat_id",
        ... )

        >>> # Named segments
        >>> HierarchySpec(segment_name_field="section_name")
    """

    parent_id_field: str | None = None
    child_id_field: str | None = None
    segment_name_field: str | None = None
    offset_field: str | None = None


@dataclass
class RegionSpec:
    """Specification for region (named TimeInterval) fields.

    Region fields contain identifiers that group events into named TimeIntervals.
    Unlike partitions (which create separate timelines) or hierarchy (which creates
    nested timelines), regions are just named spans on the SAME timeline.

    Attributes:
        fields: Field names containing region identifiers.
        start_field: Field for region start (default: derive from first event).
        end_field: Field for region end (default: derive from last event).
        allow_overlap: Whether regions can overlap.

    From TTA manuscript: "A Region is a named part of a timeline defined by a
    TimeInterval. Regions are NOT timelines - they cannot hold events or C-maps."

    Examples:
        >>> # Simple region field
        >>> RegionSpec(fields=["section"])

        >>> # Explicit region boundaries
        >>> RegionSpec(
        ...     fields=["section"],
        ...     start_field="section_start",
        ...     end_field="section_end",
        ... )
    """

    fields: list[str] = field(default_factory=list)
    start_field: str | None = None
    end_field: str | None = None
    allow_overlap: bool = True


@dataclass
class MatchSpec:
    """Specification for match (alignment) fields.

    Match fields reference events on other timelines, creating MatchClaims
    when the data is loaded.

    Attributes:
        fields: Mapping of field names to MatchField specifications.
        default_metadata: Default metadata for all matches from this table.
        allow_nomatch: Whether null values in match fields are allowed
            (representing NOMATCH sentinel per TTA manuscript).

    Examples:
        >>> MatchSpec(fields={
        ...     "aligned_score_id": MatchField(
        ...         target_timeline="score",
        ...         target_event_field="id",
        ...     ),
        ... })
    """

    fields: dict[str, MatchField] = field(default_factory=dict)
    default_metadata: dict[str, Any] | None = None
    allow_nomatch: bool = True


# endregion


# region TableSchema


@dataclass
class TableSchema:
    """Comprehensive schema for interpreting tabular data as TTA objects.

    TableSchema provides a declarative specification for how to interpret
    tabular data (CSV, TSV, DataFrame) as TimeToAlign! objects:
    - Timelines with events
    - ConversionMaps (from C-Map fields)
    - Regions (named TimeIntervals)
    - MatchClaims (alignment references)

    The schema specifies WHAT the data means, not HOW to process it. The actual
    processing is performed by `create_timelines()` and related methods.

    Attributes:
        timeline: Default parameters for timeline creation.
        coordinates: Coordinate field specifications.
        partitions: Partition specifications (multiple timelines).
        hierarchy: Hierarchy specifications (nested timelines).
        regions: Region specifications (named TimeIntervals).
        matches: Match specifications (alignment references).
        id_field: Field for event IDs.
        name_field: Field for event names.
        event_type_field: Field for event types.
        extra_fields: Additional data fields to include.
        infer_remaining: Whether to auto-include unspecified fields.

    Examples:
        >>> # Simple schema for second-based events
        >>> schema = TableSchema(
        ...     timeline=TimelineDefaults(unit=TimeUnit.seconds),
        ...     coordinates=CoordinateSpec(start="onset", end="offset"),
        ... )

        >>> # Complex schema with partitions, C-maps, and matches
        >>> schema = TableSchema(
        ...     timeline=TimelineDefaults(unit=TimeUnit.seconds),
        ...     coordinates=CoordinateSpec(
        ...         start="onset_sec",
        ...         end="offset_sec",
        ...         cmap_fields={"beat": CMapField(TimeUnit.quarters)},
        ...     ),
        ...     partitions=PartitionSpec(fields=["voice"]),
        ...     regions=RegionSpec(fields=["section"]),
        ...     matches=MatchSpec(fields={
        ...         "score_id": MatchField(target_timeline="score"),
        ...     }),
        ... )

        >>> # Create timelines from data
        >>> timelines = schema.create_timelines(df)
    """

    # Core specifications
    timeline: TimelineDefaults = field(default_factory=TimelineDefaults)
    coordinates: CoordinateSpec = field(default_factory=CoordinateSpec)

    # Structural specifications
    partitions: PartitionSpec | None = None
    hierarchy: HierarchySpec | None = None
    regions: RegionSpec | None = None
    matches: MatchSpec | None = None

    # Identity fields
    id_field: str | None = "id"
    name_field: str | None = "name"
    event_type_field: str | None = None

    # Extra fields
    extra_fields: list[ExtraField | str] = field(default_factory=list)
    infer_remaining: bool = False
    exclude_fields: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        """Validate schema configuration."""
        self._logger = module_logger.getChild("TableSchema")

    # region Field Analysis

    def get_reserved_fields(self) -> set[str]:
        """Get all field names that have special semantic roles.

        Returns:
            Set of field names used for coordinates, partitions, etc.
        """
        reserved = set()

        # Identity fields
        if self.id_field:
            reserved.add(self.id_field)
        if self.name_field:
            reserved.add(self.name_field)
        if self.event_type_field:
            reserved.add(self.event_type_field)

        # Coordinate fields
        if self.coordinates.start:
            reserved.add(self.coordinates.start)
        if self.coordinates.end:
            reserved.add(self.coordinates.end)
        if self.coordinates.duration:
            reserved.add(self.coordinates.duration)
        if self.coordinates.instant:
            reserved.add(self.coordinates.instant)

        # C-Map fields
        reserved.update(self.coordinates.cmap_fields.keys())

        # Partition fields
        if self.partitions:
            reserved.update(self.partitions.fields)

        # Hierarchy fields
        if self.hierarchy:
            if self.hierarchy.parent_id_field:
                reserved.add(self.hierarchy.parent_id_field)
            if self.hierarchy.child_id_field:
                reserved.add(self.hierarchy.child_id_field)
            if self.hierarchy.segment_name_field:
                reserved.add(self.hierarchy.segment_name_field)
            if self.hierarchy.offset_field:
                reserved.add(self.hierarchy.offset_field)

        # Region fields
        if self.regions:
            reserved.update(self.regions.fields)
            if self.regions.start_field:
                reserved.add(self.regions.start_field)
            if self.regions.end_field:
                reserved.add(self.regions.end_field)

        # Match fields
        if self.matches:
            reserved.update(self.matches.fields.keys())

        return reserved

    def get_field_role(self, field_name: str) -> ColumnRole:
        """Determine the semantic role of a field.

        Args:
            field_name: Field name to analyze.

        Returns:
            The ColumnRole for this field.
        """
        # Identity
        if field_name == self.id_field:
            return ColumnRole.id
        if field_name == self.name_field:
            return ColumnRole.name
        if field_name == self.event_type_field:
            return ColumnRole.event_type

        # Coordinates
        if field_name == self.coordinates.start:
            return ColumnRole.start
        if field_name == self.coordinates.end:
            return ColumnRole.end
        if field_name == self.coordinates.duration:
            return ColumnRole.duration
        if field_name == self.coordinates.instant:
            return ColumnRole.instant

        # C-Maps
        if field_name in self.coordinates.cmap_fields:
            return ColumnRole.cmap_target

        # Partitions
        if self.partitions and field_name in self.partitions.fields:
            return ColumnRole.partition

        # Hierarchy
        if self.hierarchy:
            if field_name == self.hierarchy.parent_id_field:
                return ColumnRole.parent_id
            if field_name == self.hierarchy.child_id_field:
                return ColumnRole.child_id
            if field_name == self.hierarchy.segment_name_field:
                return ColumnRole.segment_name

        # Regions
        if self.regions and field_name in self.regions.fields:
            return ColumnRole.region

        # Matches
        if self.matches and field_name in self.matches.fields:
            return ColumnRole.match_ref

        return ColumnRole.extra

    # endregion

    # region Timeline Creation

    def create_timelines(
        self,
        data: pd.DataFrame | pa.Table,
        external_timelines: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create Timeline objects from tabular data.

        This is the main entry point for interpreting tabular data according
        to this schema.

        Args:
            data: The source data (DataFrame or PyArrow Table).
            external_timelines: Externally-provided timelines referenced by
                MatchSpec fields. Keys are timeline IDs.

        Returns:
            Dictionary with:
            - "timelines": dict[str, Timeline] - Created timelines by ID
            - "cmaps": list[ConversionMap] - Created conversion maps
            - "regions": dict[str, list[Region]] - Regions by timeline ID
            - "matches": list[MatchClaim] - Created match claims

        Raises:
            ValueError: If required fields are missing.
            TypeError: If data types are incompatible.

        Examples:
            >>> schema = TableSchema(...)
            >>> result = schema.create_timelines(df)
            >>> result["timelines"]["voice:soprano"]  # Timeline for soprano
            >>> result["cmaps"][0]  # TableMap from seconds to beats
        """

        if isinstance(data, pa.Table):
            df = data.to_pandas()
        else:
            df = data

        self._validate_fields(df)

        result: dict[str, Any] = {
            "timelines": {},
            "cmaps": [],
            "regions": {},
            "matches": [],
        }

        # Step 1: Determine partitions
        if self.partitions and self.partitions.fields:
            partition_groups = self._compute_partitions(df)
        else:
            partition_groups = {None: df}  # Single timeline

        # Step 2: Create timeline for each partition
        for partition_key, partition_df in partition_groups.items():
            timeline_id = self._make_timeline_id(partition_key)

            # Create timeline
            timeline = self._create_single_timeline(partition_df, timeline_id)
            result["timelines"][timeline_id] = timeline

            # Extract regions for this timeline
            if self.regions and self.regions.fields:
                regions = self._extract_regions(partition_df, timeline)
                if regions:
                    result["regions"][timeline_id] = regions

        # Step 3: Build C-Maps from cmap_fields
        if self.coordinates.cmap_fields:
            cmaps = self._build_cmaps(df, result["timelines"])
            result["cmaps"].extend(cmaps)

        # Step 4: Build MatchClaims
        if self.matches and self.matches.fields:
            matches = self._build_matches(
                df, result["timelines"], external_timelines or {}
            )
            result["matches"].extend(matches)

        # Step 5: Handle hierarchy (CHILDREN mode partitions or explicit hierarchy)
        if self.partitions and self.partitions.mode == PartitionMode.children:
            self._apply_partition_hierarchy(result["timelines"], self.partitions)

        if self.hierarchy:
            self._apply_explicit_hierarchy(df, result["timelines"])

        return result

    def _validate_fields(self, df: pd.DataFrame) -> None:
        """Validate that required source columns exist in the data.

        Args:
            df: The source DataFrame.

        Raises:
            ValueError: If required source columns are missing.
        """
        required = []

        # At least one coordinate source field
        if self.coordinates.start:
            required.append(self.coordinates.start)
        elif self.coordinates.instant:
            required.append(self.coordinates.instant)

        # Partition source fields
        if self.partitions:
            required.extend(self.partitions.fields)

        # Check all required source columns exist in the DataFrame
        missing = [name for name in required if name not in df.columns]
        if missing:
            raise ValueError(
                f"Required columns missing from data: {missing}. "
                f"Available columns: {list(df.columns)}"
            )

    def _compute_partitions(
        self, df: pd.DataFrame
    ) -> dict[tuple[Any, ...] | None, pd.DataFrame]:
        """Group data by partition fields.

        Args:
            df: The source DataFrame.

        Returns:
            Dictionary mapping partition key tuples to DataFrames.
        """
        if not self.partitions or not self.partitions.fields:
            return {None: df}

        result = {}
        for key, group in df.groupby(
            self.partitions.fields, dropna=not self.partitions.include_null
        ):
            # Normalize key to tuple
            if not isinstance(key, tuple):
                key = (key,)
            result[key] = group

        return result

    def _make_timeline_id(self, partition_key: tuple[Any, ...] | None) -> str:
        """Generate timeline ID from partition key.

        Args:
            partition_key: Tuple of partition values, or None for single timeline.

        Returns:
            Timeline ID string.
        """
        if partition_key is None:
            return f"{self.timeline.id_prefix}:1"

        # Use template if provided
        if self.partitions and self.partitions.timeline_name_template:
            # Simple substitution
            value_str = "_".join(str(v) for v in partition_key)
            return self.partitions.timeline_name_template.format(value=value_str)

        return f"{self.timeline.id_prefix}:{'_'.join(str(v) for v in partition_key)}"

    def _create_single_timeline(
        self, df: pd.DataFrame, timeline_id: str
    ) -> Any:  # Returns Timeline
        """Create a single Timeline from a DataFrame partition.

        Args:
            df: DataFrame containing events for this timeline.
            timeline_id: ID for the created timeline.

        Returns:
            A Timeline object populated with events.
        """

        # Build event data
        events = self._extract_events(df)

        # Calculate length from max coordinate
        max_coord = 0.0
        for event in events:
            for key in ("end", "instant", "start"):
                val = event.get(key)
                if val is not None:
                    max_coord = max(max_coord, float(val))

        # Create timeline
        timeline = Timeline(
            length=max_coord,
            unit=self.timeline.unit,
            number_type=self.timeline.number_type,
            id_prefix=timeline_id.split(":")[0] if ":" in timeline_id else "tl",
            uid=timeline_id,
            locked=self.timeline.locked,
            meta=dict(self.timeline.meta),
        )

        # Add events
        if events:
            timeline.add_events(events, allow_expansion=True)

        return timeline

    def _extract_events(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Extract event dictionaries from DataFrame.

        Args:
            df: Source DataFrame.

        Returns:
            List of event dictionaries.
        """
        events = []
        n = len(df)

        # Generate IDs if needed
        if self.id_field and self.id_field in df.columns:
            ids = df[self.id_field].astype(str).tolist()
        else:
            ids = [f"e{i:06d}" for i in range(n)]

        # Get names
        names = [None] * n
        if self.name_field and self.name_field in df.columns:
            names = df[self.name_field].tolist()

        # Get event types
        event_types = [self.timeline.default_event_type] * n
        if self.event_type_field and self.event_type_field in df.columns:
            event_types = (
                df[self.event_type_field]
                .fillna(self.timeline.default_event_type)
                .tolist()
            )

        # Get coordinates
        starts = [None] * n
        ends = [None] * n
        instants = [None] * n

        if self.coordinates.start and self.coordinates.start in df.columns:
            starts = df[self.coordinates.start].tolist()
        if self.coordinates.end and self.coordinates.end in df.columns:
            ends = df[self.coordinates.end].tolist()
        elif self.coordinates.duration and self.coordinates.duration in df.columns:
            # Compute end from duration
            durations = df[self.coordinates.duration].tolist()
            ends = [
                (
                    s + d
                    if s is not None
                    and d is not None
                    and not pd.isna(s)
                    and not pd.isna(d)
                    else None
                )
                for s, d in zip(starts, durations)
            ]
        if self.coordinates.instant and self.coordinates.instant in df.columns:
            instants = df[self.coordinates.instant].tolist()

        # Determine temporal type
        for i in range(n):
            event: dict[str, Any] = {
                "id": ids[i],
                "event_type": event_types[i],
            }

            if names[i] is not None and not pd.isna(names[i]):
                event["name"] = names[i]

            # Determine if instant or interval
            has_end = ends[i] is not None and not pd.isna(ends[i])
            has_instant = instants[i] is not None and not pd.isna(instants[i])
            has_start = starts[i] is not None and not pd.isna(starts[i])

            if has_instant and not has_start:
                event["temporal_type"] = "instant"
                event["instant"] = float(instants[i])
            elif has_start and has_end:
                event["temporal_type"] = "interval"
                event["start"] = float(starts[i])
                event["end"] = float(ends[i])
            elif has_start:
                event["temporal_type"] = "instant"
                event["instant"] = float(starts[i])
            else:
                continue  # Skip rows without coordinates

            # Add extra fields
            for extra in self.extra_fields:
                if isinstance(extra, str):
                    if extra in df.columns:
                        val = df[extra].iloc[i]
                        if val is not None and not pd.isna(val):
                            event[extra] = val
                elif isinstance(extra, ExtraField):
                    source = extra.source or extra.name
                    if source in df.columns:
                        val = df[source].iloc[i]
                        if val is not None and not pd.isna(val):
                            if extra.converter:
                                val = extra.converter(val)
                            event[extra.name] = val

            events.append(event)

        return events

    def _extract_regions(
        self, df: pd.DataFrame, timeline: Any
    ) -> list[Any]:  # Returns list[Region]
        """Extract Region objects from region fields.

        Args:
            df: Source DataFrame.
            timeline: The timeline these regions belong to.

        Returns:
            List of Region objects.
        """
        from timetoalign.core import Coordinate
        from timetoalign.timelines.regions import Region

        if not self.regions or not self.regions.fields:
            return []

        regions = []
        start_field = self.coordinates.start or self.coordinates.instant

        for region_field in self.regions.fields:
            if region_field not in df.columns:
                continue

            # Group by region value
            for region_name, group in df.groupby(region_field, dropna=True):
                if pd.isna(region_name):
                    continue

                # Determine region bounds
                if self.regions.start_field and self.regions.start_field in df.columns:
                    start = group[self.regions.start_field].min()
                elif start_field and start_field in df.columns:
                    start = group[start_field].min()
                else:
                    continue

                if self.regions.end_field and self.regions.end_field in df.columns:
                    end = group[self.regions.end_field].max()
                elif self.coordinates.end and self.coordinates.end in df.columns:
                    end = group[self.coordinates.end].max()
                elif start_field and start_field in df.columns:
                    end = group[start_field].max()
                else:
                    end = start

                if pd.isna(start) or pd.isna(end):
                    continue

                region = Region(
                    name=str(region_name),
                    start=Coordinate(float(start), timeline.unit),
                    end=Coordinate(float(end), timeline.unit),
                )
                regions.append(region)

        return regions

    def _build_cmaps(
        self, df: pd.DataFrame, timelines: dict[str, Any]
    ) -> list[Any]:  # Returns list[ConversionMap]
        """Build ConversionMaps from cmap_fields.

        Args:
            df: Source DataFrame.
            timelines: Created timelines.

        Returns:
            List of ConversionMap objects.
        """
        from timetoalign.maps import TableMap

        cmaps = []
        start_field = self.coordinates.start or self.coordinates.instant

        for field_name, cmap_spec in self.coordinates.cmap_fields.items():
            if field_name not in df.columns:
                self._logger.warning(f"C-Map field '{field_name}' not found in data")
                continue

            source_field = cmap_spec.source_field or start_field
            if source_field not in df.columns:
                self._logger.warning(
                    f"Source field '{source_field}' not found for C-Map"
                )
                continue

            # Extract coordinate pairs
            mask = df[source_field].notna() & df[field_name].notna()
            source_coords = df.loc[mask, source_field].astype(float).values
            target_coords = df.loc[mask, field_name].astype(float).values

            if len(source_coords) < 2:
                self._logger.warning(
                    f"Not enough valid pairs for C-Map from '{source_field}' to '{field_name}'"
                )
                continue

            # Sort by source coordinate
            sort_idx = np.argsort(source_coords)
            source_coords = source_coords[sort_idx]
            target_coords = target_coords[sort_idx]

            # Create map
            cmap = TableMap(
                x_values=source_coords.tolist(),
                y_values=target_coords.tolist(),
                source_unit=self.timeline.unit,
                target_unit=cmap_spec.target_unit,
            )
            cmaps.append(cmap)

            # Attach to timeline(s)
            for timeline in timelines.values():
                timeline.add_conversion_map(cmap)

            # Create inverse if bidirectional
            if cmap_spec.bidirectional and cmap.is_invertible:
                inverse = cmap.inverse()
                cmaps.append(inverse)

        return cmaps

    def _build_matches(
        self,
        df: pd.DataFrame,
        timelines: dict[str, Any],
        external_timelines: dict[str, Any],
    ) -> list[Any]:  # Returns list[MatchClaim]
        """Build MatchClaims from match fields.

        Args:
            df: Source DataFrame.
            timelines: Created timelines.
            external_timelines: Externally-provided timelines.

        Returns:
            List of MatchClaim objects.
        """

        if not self.matches:
            return []

        from timetoalign.alignment import (  # noqa: F811
            AlignmentAnchor,
            MatchClaim,
            MatchMetadata,
        )

        matches = []
        start_field = self.coordinates.start or self.coordinates.instant

        # Get source timeline (first one if multiple)
        source_timeline_id = next(iter(timelines.keys()))

        for field_name, match_spec in self.matches.fields.items():
            if field_name not in df.columns:
                self._logger.warning(f"Match field '{field_name}' not found in data")
                continue

            # Find target timeline
            target_id = match_spec.target_timeline
            target_timeline = external_timelines.get(target_id)
            if target_timeline is None:
                target_timeline = timelines.get(target_id)

            # Build metadata
            metadata = None
            if self.matches.default_metadata or match_spec.match_metadata:
                meta_dict = dict(self.matches.default_metadata or {})
                if match_spec.match_metadata:
                    meta_dict.update(match_spec.match_metadata)
                metadata = MatchMetadata(
                    agent=meta_dict.get("agent", "table_schema"),
                    decision_criteria=meta_dict.get(
                        "decision_criteria", "field_reference"
                    ),
                    certainty=meta_dict.get("certainty", 1.0),
                )

            # Create matches for each row with a valid reference
            for idx, row in df.iterrows():
                target_event_id = row.get(field_name)
                if pd.isna(target_event_id):
                    if self.matches.allow_nomatch:
                        continue  # NOMATCH sentinel
                    else:
                        raise ValueError(
                            f"Null value in match field '{field_name}' at row {idx}"
                        )

                # Get source coordinate
                source_coord = row.get(start_field)
                if pd.isna(source_coord):
                    continue

                # source_event_id = (
                #     row.get(self.id_field) if self.id_field else f"e{idx}"
                # )

                # For now, create instant matches (coordinate-based)
                # Full event-based matches would require looking up target events
                if match_spec.is_synchronous:
                    claim = MatchClaim(
                        timeline_a_id=source_timeline_id,
                        timeline_b_id=target_id,
                        start_anchor=AlignmentAnchor(
                            timeline_a_id=source_timeline_id,
                            coordinate_a=float(source_coord),
                            timeline_b_id=target_id,
                            coordinate_b=float(source_coord),  # Placeholder
                        ),
                        metadata=metadata,
                        is_synchronous=True,
                    )
                else:
                    claim = MatchClaim(
                        timeline_a_id=source_timeline_id,
                        timeline_b_id=target_id,
                        start_anchor=None,
                        end_anchor=None,
                        is_synchronous=False,
                        metadata=metadata,
                    )
                matches.append(claim)

        return matches

    def _apply_partition_hierarchy(
        self, timelines: dict[str, Any], partition_spec: PartitionSpec
    ) -> None:
        """Apply CHILDREN mode hierarchy to partitioned timelines.

        Args:
            timelines: Created timelines (modified in-place).
            partition_spec: The partition specification.
        """
        if partition_spec.mode != PartitionMode.children:
            return

        # Create or get parent timeline
        if partition_spec.parent_timeline:
            parent_id = partition_spec.parent_timeline
            if parent_id not in timelines:
                # Create parent
                from timetoalign.timelines import Timeline

                max_length = max(tl.length.value for tl in timelines.values())
                parent = Timeline(
                    length=max_length,
                    unit=self.timeline.unit,
                    number_type=self.timeline.number_type,
                    uid=parent_id,
                )
                timelines[parent_id] = parent
        else:
            # First timeline becomes parent
            parent_id = next(iter(timelines.keys()))

        parent = timelines[parent_id]

        # Add other timelines as children
        for child_id, child in list(timelines.items()):
            if child_id != parent_id:
                parent.add_child(child, offset=0)

    def _apply_explicit_hierarchy(
        self, df: pd.DataFrame, timelines: dict[str, Any]
    ) -> None:
        """Apply explicit hierarchy from HierarchySpec.

        Args:
            df: Source DataFrame.
            timelines: Created timelines (modified in-place).
        """
        if not self.hierarchy:
            return

        # Implementation would handle parent_id_field, child_id_field, etc.
        # This is a placeholder for the full implementation
        pass

    # endregion

    # region Export

    def to_dict(self) -> dict[str, Any]:
        """Serialize schema to dictionary.

        Returns:
            Dictionary representation for JSON serialization.
        """
        result: dict[str, Any] = {
            "timeline": {
                "unit": self.timeline.unit.name,
                "number_type": self.timeline.number_type.name,
                "id_prefix": self.timeline.id_prefix,
                "default_event_type": self.timeline.default_event_type,
            },
            "coordinates": {
                "start": self.coordinates.start,
                "end": self.coordinates.end,
                "duration": self.coordinates.duration,
                "instant": self.coordinates.instant,
            },
        }

        if self.coordinates.cmap_fields:
            result["coordinates"]["cmap_fields"] = {
                name: {
                    "target_unit": spec.target_unit.name,
                    "map_type": spec.map_type,
                    "bidirectional": spec.bidirectional,
                }
                for name, spec in self.coordinates.cmap_fields.items()
            }

        if self.partitions:
            result["partitions"] = {
                "fields": self.partitions.fields,
                "mode": self.partitions.mode.name,
            }

        if self.regions:
            result["regions"] = {"fields": self.regions.fields}

        if self.matches:
            result["matches"] = {
                "fields": {
                    name: {
                        "target_timeline": spec.target_timeline,
                        "is_synchronous": spec.is_synchronous,
                    }
                    for name, spec in self.matches.fields.items()
                }
            }

        result["id_field"] = self.id_field
        result["name_field"] = self.name_field
        result["event_type_field"] = self.event_type_field

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TableSchema":
        """Deserialize schema from dictionary.

        Args:
            data: Dictionary from to_dict().

        Returns:
            New TableSchema instance.
        """
        # Parse timeline defaults
        tl_data = data.get("timeline", {})
        timeline = TimelineDefaults(
            unit=TimeUnit(tl_data.get("unit", "seconds")),
            number_type=NumberType(tl_data.get("number_type", "float")),
            id_prefix=tl_data.get("id_prefix", "tl"),
            default_event_type=tl_data.get("default_event_type", "Event"),
        )

        # Parse coordinates
        coord_data = data.get("coordinates", {})
        cmap_fields = {}
        if "cmap_fields" in coord_data:
            for name, spec in coord_data["cmap_fields"].items():
                cmap_fields[name] = CMapField(
                    target_unit=TimeUnit(spec["target_unit"]),
                    map_type=spec.get("map_type", "table"),
                    bidirectional=spec.get("bidirectional", True),
                )

        coordinates = CoordinateSpec(
            start=coord_data.get("start"),
            end=coord_data.get("end"),
            duration=coord_data.get("duration"),
            instant=coord_data.get("instant"),
            cmap_fields=cmap_fields,
        )

        # Parse partitions
        partitions = None
        if "partitions" in data:
            part_data = data["partitions"]
            partitions = PartitionSpec(
                fields=part_data.get("fields", []),
                mode=PartitionMode[part_data.get("mode", "SEPARATE")],
            )

        # Parse regions
        regions = None
        if "regions" in data:
            reg_data = data["regions"]
            regions = RegionSpec(fields=reg_data.get("fields", []))

        # Parse matches
        matches = None
        if "matches" in data:
            match_data = data["matches"]
            match_fields = {}
            for name, spec in match_data.get("fields", {}).items():
                match_fields[name] = MatchField(
                    target_timeline=spec["target_timeline"],
                    is_synchronous=spec.get("is_synchronous", True),
                )
            matches = MatchSpec(fields=match_fields)

        return cls(
            timeline=timeline,
            coordinates=coordinates,
            partitions=partitions,
            regions=regions,
            matches=matches,
            id_field=data.get("id_field"),
            name_field=data.get("name_field"),
            event_type_field=data.get("event_type_field"),
        )

    # endregion

    def __repr__(self) -> str:
        parts = [f"unit={self.timeline.unit.value}"]
        if self.partitions and self.partitions.fields:
            parts.append(f"partitions={self.partitions.fields}")
        if self.coordinates.cmap_fields:
            parts.append(f"cmaps={list(self.coordinates.cmap_fields.keys())}")
        if self.regions and self.regions.fields:
            parts.append(f"regions={self.regions.fields}")
        if self.matches and self.matches.fields:
            parts.append(f"matches={list(self.matches.fields.keys())}")
        return f"TableSchema({', '.join(parts)})"


# endregion
