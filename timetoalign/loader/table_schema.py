"""TableSchema: Semantic column specifications for TimeToAlign! data loading.

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
    ...         cmap_columns={"onset_beat": CMapColumn(target_unit=TimeUnit.quarters)},
    ...     ),
    ...     partitions=PartitionSpec(columns=["voice"]),
    ...     regions=RegionSpec(columns=["region"]),
    ...     matches=MatchSpec(columns={"matched_score_id": MatchColumn(
    ...         target_timeline="score", target_event_column="id"
    ...     )}),
    ... )
    >>> results = schema.create_timelines(df)  # Returns dict[str, Timeline]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Callable, Literal

import numpy as np
import pandas as pd
import pyarrow as pa

from timetoalign.core import NumberType, TimeUnit

# Import from specific submodules to avoid circular imports
# (timetoalign/__init__.py imports loader, which imports table_schema)
from timetoalign.timelines.base import Timeline

if TYPE_CHECKING:
    from timetoalign.alignment import MatchClaim, MatchMetadata

module_logger = logging.getLogger(__name__)


# region Enums


class ColumnRole(Enum):
    """Semantic role of a column in the table.

    Used for automatic role inference when columns are not explicitly specified.
    """

    # Core event identity
    ID = auto()
    NAME = auto()
    EVENT_TYPE = auto()

    # Coordinates (primary timeline)
    START = auto()
    END = auto()
    DURATION = auto()
    INSTANT = auto()

    # Conversion (C-Map target)
    CMAP_TARGET = auto()

    # Structure
    PARTITION = auto()
    PARENT_ID = auto()
    CHILD_ID = auto()
    SEGMENT_NAME = auto()
    REGION = auto()

    # Alignment
    MATCH_REF = auto()

    # Generic data
    EXTRA = auto()


class PartitionMode(Enum):
    """How partition columns create timelines.

    SEPARATE: Each unique value creates an independent timeline with its own
              coordinate system. Coordinates are NOT comparable across partitions.
              Use for: Different recordings, different performers.

    CHILDREN: Each unique value creates a child timeline that shares the parent's
              coordinate system. Coordinates ARE comparable (offset by parent position).
              Use for: Voices, instruments, staves within a score.
    """

    SEPARATE = auto()  # Disparate coordinate systems
    CHILDREN = auto()  # Same coordinate system, parent-child relationship


# endregion


# region Column Specifications


@dataclass(frozen=True)
class CMapColumn:
    """Specification for a column that defines a ConversionMap target.

    A C-Map column contains coordinates in a different unit than the primary
    timeline. Loading this column creates a C-Map (or TableMap) converting
    from the primary unit to the target unit.

    Attributes:
        target_unit: The TimeUnit of coordinates in this column.
        source_column: The primary coordinate column this maps from.
            Defaults to the start_column if not specified.
        map_type: Type of C-Map to create:
            - "table": TableMap from explicit coordinate pairs (default).
            - "linear": LinearMap fit from coordinate pairs.
            - "interpolation": InterpolationMap for O(log n) lookup.
        bidirectional: If True, also create the inverse map.

    Examples:
        >>> # Column with beat positions -> creates TableMap(seconds -> beats)
        >>> CMapColumn(target_unit=TimeUnit.quarters)

        >>> # Column with measure numbers
        >>> CMapColumn(target_unit=TimeUnit.measures)
    """

    target_unit: TimeUnit
    source_column: str | None = None
    map_type: Literal["table", "linear", "interpolation"] = "table"
    bidirectional: bool = True


@dataclass(frozen=True)
class MatchColumn:
    """Specification for a column that references events on another timeline.

    A Match column contains identifiers of events on a different timeline,
    creating MatchClaims when the data is loaded.

    Attributes:
        target_timeline: ID or role of the timeline containing matched events.
            Can be:
            - Explicit ID: "score:1"
            - Partition value: References another partition's timeline
            - External: Name of an externally-provided timeline
        target_event_column: Column in target timeline's data containing event IDs.
            If not specified, assumes the target uses the same ID scheme.
        is_synchronous: Whether matches represent temporal synchrony (True)
            or conceptual correspondence (False, e.g., structural alignment).
        match_metadata: Default metadata for generated MatchClaims.

    Examples:
        >>> # Column referencing score events by ID
        >>> MatchColumn(target_timeline="score", target_event_column="note_id")

        >>> # Conceptual match (same structural position, not same time)
        >>> MatchColumn(
        ...     target_timeline="analysis_v2",
        ...     is_synchronous=False,
        ... )
    """

    target_timeline: str
    target_event_column: str | None = None
    is_synchronous: bool = True
    match_metadata: dict[str, Any] | None = None


@dataclass
class ExtraColumn:
    """Specification for an extra data column.

    This is a simplified version of the existing ExtraField for the new schema.

    Attributes:
        name: Output column name in the EventData.
        dtype: PyArrow data type (or type hint for inference).
        source: Source column name if different from name.
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
    """Specification for coordinate columns.

    Defines which columns hold temporal coordinates and how to interpret them.

    Attributes:
        start: Column for start coordinates (required for interval events).
        end: Column for end coordinates (optional, None for instant events).
        duration: Alternative to end - compute end as start + duration.
        instant: Column for instant event coordinates (alternative to start).
        cmap_columns: Columns containing coordinates in other units.
            Each creates a ConversionMap.

    Invariants:
        - Must have at least one of: start, instant
        - If end is None and duration is None, events are instants
        - cmap_columns are in ADDITION to the primary coordinate column

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
        ...     cmap_columns={"onset_beat": CMapColumn(TimeUnit.quarters)},
        ... )

    Raises:
        ValueError: If both start and instant are explicitly set to None.
    """

    start: str | None | object = field(default=_UNSET)
    end: str | None = None
    duration: str | None = None
    instant: str | None | object = field(default=_UNSET)
    cmap_columns: dict[str, CMapColumn] = field(default_factory=dict)

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
                "CoordinateSpec requires at least one of 'start' or 'instant' columns. "
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

    A partition column groups rows such that each unique value (or combination
    of values) creates a separate timeline. The mode determines whether these
    timelines have independent coordinate systems (SEPARATE) or share a parent
    coordinate system (CHILDREN).

    Attributes:
        columns: Column names that define the partition key.
            Multiple columns create a composite key.
        mode: How to handle partitioned timelines:
            - SEPARATE: Independent timelines with disparate coordinates.
            - CHILDREN: Child timelines sharing parent's coordinates.
        parent_timeline: For CHILDREN mode, the ID of the parent timeline.
            If None, creates a new parent timeline.
        include_null: Whether to create a timeline for rows with null partition values.
        timeline_name_template: Template for naming partitioned timelines.
            Use {column_name} for substitution.

    Examples:
        >>> # Separate timeline per voice (independent coordinate systems)
        >>> PartitionSpec(columns=["voice"], mode=PartitionMode.SEPARATE)

        >>> # Child timelines per staff (shared coordinates)
        >>> PartitionSpec(
        ...     columns=["staff"],
        ...     mode=PartitionMode.CHILDREN,
        ...     parent_timeline="score",
        ... )

        >>> # Composite partition key
        >>> PartitionSpec(columns=["piece_id", "movement"])
    """

    columns: list[str] = field(default_factory=list)
    mode: PartitionMode = PartitionMode.SEPARATE
    parent_timeline: str | None = None
    include_null: bool = False
    timeline_name_template: str = "{value}"


@dataclass
class HierarchySpec:
    """Specification for hierarchical timeline structure.

    Defines parent-child relationships within the loaded data. Unlike partitions
    (which create sibling timelines), hierarchy creates nested timelines.

    Attributes:
        parent_id_column: Column containing parent event/timeline IDs.
        child_id_column: Column containing child event/timeline IDs.
        segment_name_column: Column containing segment names.
        offset_column: Column containing child offsets relative to parent.
            If None, children start at their first event's coordinate.

    Note: This is for explicit hierarchy in the DATA. Partition-based hierarchy
    (PartitionSpec with mode=CHILDREN) is an alternative approach.

    Examples:
        >>> # Measure -> beat hierarchy
        >>> HierarchySpec(
        ...     parent_id_column="measure_id",
        ...     child_id_column="beat_id",
        ... )

        >>> # Named segments
        >>> HierarchySpec(segment_name_column="section_name")
    """

    parent_id_column: str | None = None
    child_id_column: str | None = None
    segment_name_column: str | None = None
    offset_column: str | None = None


@dataclass
class RegionSpec:
    """Specification for region (named TimeInterval) columns.

    Region columns contain identifiers that group events into named TimeIntervals.
    Unlike partitions (which create separate timelines) or hierarchy (which creates
    nested timelines), regions are just named spans on the SAME timeline.

    Attributes:
        columns: Column names containing region identifiers.
        start_column: Column for region start (default: derive from first event).
        end_column: Column for region end (default: derive from last event).
        allow_overlap: Whether regions can overlap.

    From TTA manuscript: "A Region is a named part of a timeline defined by a
    TimeInterval. Regions are NOT timelines - they cannot hold events or C-maps."

    Examples:
        >>> # Simple region column
        >>> RegionSpec(columns=["section"])

        >>> # Explicit region boundaries
        >>> RegionSpec(
        ...     columns=["section"],
        ...     start_column="section_start",
        ...     end_column="section_end",
        ... )
    """

    columns: list[str] = field(default_factory=list)
    start_column: str | None = None
    end_column: str | None = None
    allow_overlap: bool = True


@dataclass
class MatchSpec:
    """Specification for match (alignment) columns.

    Match columns reference events on other timelines, creating MatchClaims
    when the data is loaded.

    Attributes:
        columns: Mapping of column names to MatchColumn specifications.
        default_metadata: Default metadata for all matches from this table.
        allow_nomatch: Whether null values in match columns are allowed
            (representing NOMATCH sentinel per TTA manuscript).

    Examples:
        >>> MatchSpec(columns={
        ...     "aligned_score_id": MatchColumn(
        ...         target_timeline="score",
        ...         target_event_column="id",
        ...     ),
        ... })
    """

    columns: dict[str, MatchColumn] = field(default_factory=dict)
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
    - ConversionMaps (from C-Map columns)
    - Regions (named TimeIntervals)
    - MatchClaims (alignment references)

    The schema specifies WHAT the data means, not HOW to process it. The actual
    processing is performed by `create_timelines()` and related methods.

    Attributes:
        timeline: Default parameters for timeline creation.
        coordinates: Coordinate column specifications.
        partitions: Partition specifications (multiple timelines).
        hierarchy: Hierarchy specifications (nested timelines).
        regions: Region specifications (named TimeIntervals).
        matches: Match specifications (alignment references).
        id_column: Column for event IDs.
        name_column: Column for event names.
        event_type_column: Column for event types.
        extra_columns: Additional data columns to include.
        infer_remaining: Whether to auto-include unspecified columns.

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
        ...         cmap_columns={"beat": CMapColumn(TimeUnit.quarters)},
        ...     ),
        ...     partitions=PartitionSpec(columns=["voice"]),
        ...     regions=RegionSpec(columns=["section"]),
        ...     matches=MatchSpec(columns={
        ...         "score_id": MatchColumn(target_timeline="score"),
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

    # Identity columns
    id_column: str | None = "id"
    name_column: str | None = "name"
    event_type_column: str | None = None

    # Extra columns
    extra_columns: list[ExtraColumn | str] = field(default_factory=list)
    infer_remaining: bool = False
    exclude_columns: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        """Validate schema configuration."""
        self._logger = module_logger.getChild("TableSchema")

    # region Column Analysis

    def get_reserved_columns(self) -> set[str]:
        """Get all column names that have special semantic roles.

        Returns:
            Set of column names used for coordinates, partitions, etc.
        """
        reserved = set()

        # Identity columns
        if self.id_column:
            reserved.add(self.id_column)
        if self.name_column:
            reserved.add(self.name_column)
        if self.event_type_column:
            reserved.add(self.event_type_column)

        # Coordinate columns
        if self.coordinates.start:
            reserved.add(self.coordinates.start)
        if self.coordinates.end:
            reserved.add(self.coordinates.end)
        if self.coordinates.duration:
            reserved.add(self.coordinates.duration)
        if self.coordinates.instant:
            reserved.add(self.coordinates.instant)

        # C-Map columns
        reserved.update(self.coordinates.cmap_columns.keys())

        # Partition columns
        if self.partitions:
            reserved.update(self.partitions.columns)

        # Hierarchy columns
        if self.hierarchy:
            if self.hierarchy.parent_id_column:
                reserved.add(self.hierarchy.parent_id_column)
            if self.hierarchy.child_id_column:
                reserved.add(self.hierarchy.child_id_column)
            if self.hierarchy.segment_name_column:
                reserved.add(self.hierarchy.segment_name_column)
            if self.hierarchy.offset_column:
                reserved.add(self.hierarchy.offset_column)

        # Region columns
        if self.regions:
            reserved.update(self.regions.columns)
            if self.regions.start_column:
                reserved.add(self.regions.start_column)
            if self.regions.end_column:
                reserved.add(self.regions.end_column)

        # Match columns
        if self.matches:
            reserved.update(self.matches.columns.keys())

        return reserved

    def get_column_role(self, column: str) -> ColumnRole:
        """Determine the semantic role of a column.

        Args:
            column: Column name to analyze.

        Returns:
            The ColumnRole for this column.
        """
        # Identity
        if column == self.id_column:
            return ColumnRole.ID
        if column == self.name_column:
            return ColumnRole.NAME
        if column == self.event_type_column:
            return ColumnRole.EVENT_TYPE

        # Coordinates
        if column == self.coordinates.start:
            return ColumnRole.START
        if column == self.coordinates.end:
            return ColumnRole.END
        if column == self.coordinates.duration:
            return ColumnRole.DURATION
        if column == self.coordinates.instant:
            return ColumnRole.INSTANT

        # C-Maps
        if column in self.coordinates.cmap_columns:
            return ColumnRole.CMAP_TARGET

        # Partitions
        if self.partitions and column in self.partitions.columns:
            return ColumnRole.PARTITION

        # Hierarchy
        if self.hierarchy:
            if column == self.hierarchy.parent_id_column:
                return ColumnRole.PARENT_ID
            if column == self.hierarchy.child_id_column:
                return ColumnRole.CHILD_ID
            if column == self.hierarchy.segment_name_column:
                return ColumnRole.SEGMENT_NAME

        # Regions
        if self.regions and column in self.regions.columns:
            return ColumnRole.REGION

        # Matches
        if self.matches and column in self.matches.columns:
            return ColumnRole.MATCH_REF

        return ColumnRole.EXTRA

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
                MatchSpec columns. Keys are timeline IDs.

        Returns:
            Dictionary with:
            - "timelines": dict[str, Timeline] - Created timelines by ID
            - "cmaps": list[ConversionMap] - Created conversion maps
            - "regions": dict[str, list[Region]] - Regions by timeline ID
            - "matches": list[MatchClaim] - Created match claims

        Raises:
            ValueError: If required columns are missing.
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

        self._validate_columns(df)

        result: dict[str, Any] = {
            "timelines": {},
            "cmaps": [],
            "regions": {},
            "matches": [],
        }

        # Step 1: Determine partitions
        if self.partitions and self.partitions.columns:
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
            if self.regions and self.regions.columns:
                regions = self._extract_regions(partition_df, timeline)
                if regions:
                    result["regions"][timeline_id] = regions

        # Step 3: Build C-Maps from cmap_columns
        if self.coordinates.cmap_columns:
            cmaps = self._build_cmaps(df, result["timelines"])
            result["cmaps"].extend(cmaps)

        # Step 4: Build MatchClaims
        if self.matches and self.matches.columns:
            matches = self._build_matches(
                df, result["timelines"], external_timelines or {}
            )
            result["matches"].extend(matches)

        # Step 5: Handle hierarchy (CHILDREN mode partitions or explicit hierarchy)
        if self.partitions and self.partitions.mode == PartitionMode.CHILDREN:
            self._apply_partition_hierarchy(result["timelines"], self.partitions)

        if self.hierarchy:
            self._apply_explicit_hierarchy(df, result["timelines"])

        return result

    def _validate_columns(self, df: pd.DataFrame) -> None:
        """Validate that required columns exist in the data.

        Args:
            df: The source DataFrame.

        Raises:
            ValueError: If required columns are missing.
        """
        required = []

        # At least one coordinate column
        if self.coordinates.start:
            required.append(self.coordinates.start)
        elif self.coordinates.instant:
            required.append(self.coordinates.instant)

        # Partition columns
        if self.partitions:
            required.extend(self.partitions.columns)

        # Check all required columns exist
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(
                f"Required columns missing from data: {missing}. "
                f"Available columns: {list(df.columns)}"
            )

    def _compute_partitions(
        self, df: pd.DataFrame
    ) -> dict[tuple[Any, ...] | None, pd.DataFrame]:
        """Group data by partition columns.

        Args:
            df: The source DataFrame.

        Returns:
            Dictionary mapping partition key tuples to DataFrames.
        """
        if not self.partitions or not self.partitions.columns:
            return {None: df}

        result = {}
        for key, group in df.groupby(
            self.partitions.columns, dropna=not self.partitions.include_null
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
        if self.id_column and self.id_column in df.columns:
            ids = df[self.id_column].astype(str).tolist()
        else:
            ids = [f"e{i:06d}" for i in range(n)]

        # Get names
        names = [None] * n
        if self.name_column and self.name_column in df.columns:
            names = df[self.name_column].tolist()

        # Get event types
        event_types = [self.timeline.default_event_type] * n
        if self.event_type_column and self.event_type_column in df.columns:
            event_types = (
                df[self.event_type_column]
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

            # Add extra columns
            for extra in self.extra_columns:
                if isinstance(extra, str):
                    if extra in df.columns:
                        val = df[extra].iloc[i]
                        if val is not None and not pd.isna(val):
                            event[extra] = val
                elif isinstance(extra, ExtraColumn):
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
        """Extract Region objects from region columns.

        Args:
            df: Source DataFrame.
            timeline: The timeline these regions belong to.

        Returns:
            List of Region objects.
        """
        from timetoalign.core import Coordinate
        from timetoalign.timelines.regions import Region

        if not self.regions or not self.regions.columns:
            return []

        regions = []
        start_col = self.coordinates.start or self.coordinates.instant

        for region_col in self.regions.columns:
            if region_col not in df.columns:
                continue

            # Group by region value
            for region_name, group in df.groupby(region_col, dropna=True):
                if pd.isna(region_name):
                    continue

                # Determine region bounds
                if (
                    self.regions.start_column
                    and self.regions.start_column in df.columns
                ):
                    start = group[self.regions.start_column].min()
                elif start_col and start_col in df.columns:
                    start = group[start_col].min()
                else:
                    continue

                if self.regions.end_column and self.regions.end_column in df.columns:
                    end = group[self.regions.end_column].max()
                elif self.coordinates.end and self.coordinates.end in df.columns:
                    end = group[self.coordinates.end].max()
                elif start_col and start_col in df.columns:
                    end = group[start_col].max()
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
        """Build ConversionMaps from cmap_columns.

        Args:
            df: Source DataFrame.
            timelines: Created timelines.

        Returns:
            List of ConversionMap objects.
        """
        from timetoalign.maps import TableMap

        cmaps = []
        start_col = self.coordinates.start or self.coordinates.instant

        for col_name, cmap_spec in self.coordinates.cmap_columns.items():
            if col_name not in df.columns:
                self._logger.warning(f"C-Map column '{col_name}' not found in data")
                continue

            source_col = cmap_spec.source_column or start_col
            if source_col not in df.columns:
                self._logger.warning(
                    f"Source column '{source_col}' not found for C-Map"
                )
                continue

            # Extract coordinate pairs
            mask = df[source_col].notna() & df[col_name].notna()
            source_coords = df.loc[mask, source_col].astype(float).values
            target_coords = df.loc[mask, col_name].astype(float).values

            if len(source_coords) < 2:
                self._logger.warning(
                    f"Not enough valid pairs for C-Map from '{source_col}' to '{col_name}'"
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
        """Build MatchClaims from match columns.

        Args:
            df: Source DataFrame.
            timelines: Created timelines.
            external_timelines: Externally-provided timelines.

        Returns:
            List of MatchClaim objects.
        """

        if not self.matches:
            return []

        matches = []
        start_col = self.coordinates.start or self.coordinates.instant

        # Get source timeline (first one if multiple)
        source_timeline_id = next(iter(timelines.keys()))

        for col_name, match_spec in self.matches.columns.items():
            if col_name not in df.columns:
                self._logger.warning(f"Match column '{col_name}' not found in data")
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
                        "decision_criteria", "column_reference"
                    ),
                    certainty=meta_dict.get("certainty", 1.0),
                )

            # Create matches for each row with a valid reference
            for idx, row in df.iterrows():
                target_event_id = row.get(col_name)
                if pd.isna(target_event_id):
                    if self.matches.allow_nomatch:
                        continue  # NOMATCH sentinel
                    else:
                        raise ValueError(
                            f"Null value in match column '{col_name}' at row {idx}"
                        )

                # Get source coordinate
                source_coord = row.get(start_col)
                if pd.isna(source_coord):
                    continue

                # source_event_id = (
                #     row.get(self.id_column) if self.id_column else f"e{idx}"
                # )

                # For now, create instant matches (coordinate-based)
                # Full event-based matches would require looking up target events
                claim = MatchClaim.instant(
                    timeline_a_id=source_timeline_id,
                    coordinate_a=float(source_coord),
                    timeline_b_id=target_id,
                    coordinate_b=float(source_coord),  # Placeholder
                    metadata=metadata,
                    is_synchronous=match_spec.is_synchronous,
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
        if partition_spec.mode != PartitionMode.CHILDREN:
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

        # Implementation would handle parent_id_column, child_id_column, etc.
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

        if self.coordinates.cmap_columns:
            result["coordinates"]["cmap_columns"] = {
                col: {
                    "target_unit": spec.target_unit.name,
                    "map_type": spec.map_type,
                    "bidirectional": spec.bidirectional,
                }
                for col, spec in self.coordinates.cmap_columns.items()
            }

        if self.partitions:
            result["partitions"] = {
                "columns": self.partitions.columns,
                "mode": self.partitions.mode.name,
            }

        if self.regions:
            result["regions"] = {"columns": self.regions.columns}

        if self.matches:
            result["matches"] = {
                "columns": {
                    col: {
                        "target_timeline": spec.target_timeline,
                        "is_synchronous": spec.is_synchronous,
                    }
                    for col, spec in self.matches.columns.items()
                }
            }

        result["id_column"] = self.id_column
        result["name_column"] = self.name_column
        result["event_type_column"] = self.event_type_column

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
        cmap_columns = {}
        if "cmap_columns" in coord_data:
            for col, spec in coord_data["cmap_columns"].items():
                cmap_columns[col] = CMapColumn(
                    target_unit=TimeUnit(spec["target_unit"]),
                    map_type=spec.get("map_type", "table"),
                    bidirectional=spec.get("bidirectional", True),
                )

        coordinates = CoordinateSpec(
            start=coord_data.get("start"),
            end=coord_data.get("end"),
            duration=coord_data.get("duration"),
            instant=coord_data.get("instant"),
            cmap_columns=cmap_columns,
        )

        # Parse partitions
        partitions = None
        if "partitions" in data:
            part_data = data["partitions"]
            partitions = PartitionSpec(
                columns=part_data.get("columns", []),
                mode=PartitionMode[part_data.get("mode", "SEPARATE")],
            )

        # Parse regions
        regions = None
        if "regions" in data:
            reg_data = data["regions"]
            regions = RegionSpec(columns=reg_data.get("columns", []))

        # Parse matches
        matches = None
        if "matches" in data:
            match_data = data["matches"]
            match_columns = {}
            for col, spec in match_data.get("columns", {}).items():
                match_columns[col] = MatchColumn(
                    target_timeline=spec["target_timeline"],
                    is_synchronous=spec.get("is_synchronous", True),
                )
            matches = MatchSpec(columns=match_columns)

        return cls(
            timeline=timeline,
            coordinates=coordinates,
            partitions=partitions,
            regions=regions,
            matches=matches,
            id_column=data.get("id_column"),
            name_column=data.get("name_column"),
            event_type_column=data.get("event_type_column"),
        )

    # endregion

    def __repr__(self) -> str:
        parts = [f"unit={self.timeline.unit.value}"]
        if self.partitions and self.partitions.columns:
            parts.append(f"partitions={self.partitions.columns}")
        if self.coordinates.cmap_columns:
            parts.append(f"cmaps={list(self.coordinates.cmap_columns.keys())}")
        if self.regions and self.regions.columns:
            parts.append(f"regions={self.regions.columns}")
        if self.matches and self.matches.columns:
            parts.append(f"matches={list(self.matches.columns.keys())}")
        return f"TableSchema({', '.join(parts)})"


# endregion
