"""Factory functions for creating Timelines from various sources.

This module provides the `create_timeline` function and its helpers,
enabling timeline creation from EventStores, EventData, and Loaders.

Design principles:
- Multiple entry points (EventData.to_timeline, EventStore.to_timeline, create_timeline)
- Children maintain their own 0-based coordinate systems
- Parent length equals max of all child lengths
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from timetoalign.core import Domain, NumberType, TimeUnit

if TYPE_CHECKING:
    from timetoalign.loader import EventData, EventStore, Loader
    from timetoalign.timelines.base import Timeline

module_logger = logging.getLogger(__name__)


def _infer_timeline_class_and_number_type(
    unit: TimeUnit,
    number_type: NumberType,
) -> tuple[type[Timeline], NumberType]:
    """Infer the appropriate Timeline subclass and number_type.

    Considers both the number_type and the unit's inherent discreteness.
    For example, ticks are inherently discrete even if stored with float,
    so the number_type is overridden to int for the Timeline.

    Args:
        unit: The time unit.
        number_type: The number type from the EventData.

    Returns:
        Tuple of (Timeline subclass, effective number_type).
    """
    from timetoalign.timelines.base import Timeline
    from timetoalign.timelines.types import (
        DISCRETE_GRAPHICAL_UNITS,
        DISCRETE_LOGICAL_UNITS,
        DISCRETE_PHYSICAL_UNITS,
        ContinuousGraphicalTimeline,
        ContinuousLogicalTimeline,
        ContinuousPhysicalTimeline,
        DiscreteGraphicalTimeline,
        DiscreteLogicalTimeline,
        DiscretePhysicalTimeline,
    )

    domain = unit.domain

    # Determine if discrete by number_type OR inherently discrete unit
    inherently_discrete_units = (
        DISCRETE_LOGICAL_UNITS | DISCRETE_PHYSICAL_UNITS | DISCRETE_GRAPHICAL_UNITS
    )
    is_discrete = number_type == NumberType.int or unit in inherently_discrete_units

    # If using a discrete timeline, force int number_type
    effective_number_type = NumberType.int if is_discrete else number_type

    mapping: dict[tuple[Domain, bool], type[Timeline]] = {
        (Domain.logical, True): DiscreteLogicalTimeline,
        (Domain.logical, False): ContinuousLogicalTimeline,
        (Domain.physical, True): DiscretePhysicalTimeline,
        (Domain.physical, False): ContinuousPhysicalTimeline,
        (Domain.graphical, True): DiscreteGraphicalTimeline,
        (Domain.graphical, False): ContinuousGraphicalTimeline,
    }

    return mapping.get((domain, is_discrete), Timeline), effective_number_type


def _infer_timeline_class(
    unit: TimeUnit,
    number_type: NumberType,
) -> type[Timeline]:
    """Infer the appropriate Timeline subclass from unit and number_type.

    Args:
        unit: The time unit.
        number_type: The number type.

    Returns:
        The most appropriate Timeline subclass.
    """
    timeline_class, _ = _infer_timeline_class_and_number_type(unit, number_type)
    return timeline_class


def create_timeline_from_bundle(
    store: "EventStore",
    uid: str | None = None,
    store_filters: dict[str, dict[str, Any]] | None = None,
    include_stores: list[str] | None = None,
    exclude_stores: list[str] | None = None,
    flatten: bool = False,
) -> "Timeline":
    """Create a Timeline from an EventStore.

    This is the core implementation called by EventStore.to_timeline().

    Args:
        store: The source EventStore (container for EventData).
        uid: Unique ID for the parent timeline. Auto-generated if None.
        store_filters: Per-data filter kwargs to apply before adding.
            Example: {"notes": {"event_type": "Note"}}
        include_stores: Only include these data (default: all non-empty).
        exclude_stores: Exclude these data.
        flatten: If True, merge all events into parent timeline.
            If False (default), each data becomes a child at offset 0.

    Returns:
        A Timeline with the requested structure.

    Raises:
        ValueError: If no data remain after filtering, or all are empty.
    """
    from timetoalign.loader.store import EventData

    store_filters = store_filters or {}
    exclude_set = set(exclude_stores or [])

    # Determine which data to include
    data_names = list(store.keys())
    if include_stores is not None:
        data_names = [n for n in data_names if n in include_stores]
    data_names = [n for n in data_names if n not in exclude_set]

    if not data_names:
        raise ValueError("No data to include after filtering")

    # Collect data (with filters applied), skip empty
    data_to_use: list[tuple[str, EventData]] = []
    for name in data_names:
        data = store[name]
        if name in store_filters:
            data = data.filter(**store_filters[name])
        if len(data) > 0:
            data_to_use.append((name, data))

    if not data_to_use:
        raise ValueError("All data are empty after filtering")

    # Infer timeline class and effective number_type from first data
    first_name, first_data = data_to_use[0]
    timeline_class, effective_number_type = _infer_timeline_class_and_number_type(
        first_data.unit, first_data.number_type
    )

    if flatten:
        # Merge all events into single timeline
        merged_data = first_data
        for _, data in data_to_use[1:]:
            merged_data = merged_data.concat(data)
        # Create timeline with corrected number_type
        coord_range = merged_data.coordinate_range()
        length = coord_range[1] if coord_range else 0
        timeline = timeline_class(
            length=length,
            unit=merged_data.unit,
            number_type=effective_number_type,
            uid=uid,
        )
        timeline._events = merged_data
        return timeline

    else:
        # Create parent with children at offset 0
        # Parent length = max of all child lengths
        max_length: float = 0.0
        for _, data in data_to_use:
            coord_range = data.coordinate_range()
            if coord_range:
                max_length = max(max_length, coord_range[1])

        parent = timeline_class(
            length=max_length,
            unit=first_data.unit,
            number_type=effective_number_type,
            uid=uid,
        )

        # Add each data as a child at offset 0
        for name, data in data_to_use:
            # Create child with corrected number_type
            child_coord_range = data.coordinate_range()
            child_length = child_coord_range[1] if child_coord_range else 0
            child = timeline_class(
                length=child_length,
                unit=data.unit,
                number_type=effective_number_type,
                uid=name,
            )
            child._events = data
            parent.add_child(child, offset=0, allow_expansion=True)

        module_logger.debug(
            f"Created timeline '{parent.id}' with {parent.n_children} children"
        )

        return parent


def create_timeline(
    source: "EventStore | EventData | Loader",
    uid: str | None = None,
    store_filters: dict[str, dict[str, Any]] | None = None,
    include_stores: list[str] | None = None,
    exclude_stores: list[str] | None = None,
    flatten: bool = False,
) -> "Timeline":
    """Create a Timeline from various source types.

    This is the most flexible timeline creation API, supporting:
    - EventStore (ScoreStore, MidiStore, SingleEventStore)
    - EventData (creates single child timeline)
    - Loader (uses loader.store)

    By default, each data in the source becomes a child timeline at offset 0,
    maintaining its own 0-based coordinate system.

    Args:
        source: The data source (EventStore, EventData, or Loader).
        uid: Unique ID for the parent timeline. Auto-generated if None.
        store_filters: Per-data filter kwargs to apply before adding.
            Example: {"notes": {"event_type": "Note"}} to exclude rests.
        include_stores: Only include these data (default: all non-empty).
        exclude_stores: Exclude these data from the timeline.
        flatten: If True, merge all events into a single parent timeline.
            If False (default), each data becomes a child at offset 0.

    Returns:
        A Timeline with the requested structure.

    Raises:
        TypeError: If source is not a supported type.
        ValueError: If no data remain after filtering.

    Examples:
        >>> # From a loader (most common)
        >>> loader = PartituraLoader()
        >>> loader.load("score.musicxml")
        >>> timeline = create_timeline(loader, uid="my_score")

        >>> # Access children
        >>> notes_tl = timeline.get_child("notes")
        >>> measures_tl = timeline.get_child("measures")

        >>> # With filters (only Notes, exclude annotations)
        >>> timeline = create_timeline(
        ...     loader,
        ...     store_filters={"notes": {"event_type": "Note"}},
        ...     exclude_stores=["annotations"],
        ... )

        >>> # Flattened (all events in one timeline)
        >>> timeline = create_timeline(loader, flatten=True)

        >>> # From a single EventData
        >>> timeline = create_timeline(data, uid="my_events")
    """
    from timetoalign.loader.base import Loader
    from timetoalign.loader.bundle import EventStore, SingleEventStore
    from timetoalign.loader.store import EventData

    # Normalize to EventStore
    if isinstance(source, EventStore):
        store = source
    elif isinstance(source, EventData):
        store = SingleEventStore(source, name="events")
    elif isinstance(source, Loader):
        store = source.store
    else:
        raise TypeError(
            f"source must be EventStore, EventData, or Loader, "
            f"got {type(source).__name__}"
        )

    return create_timeline_from_bundle(
        store,
        uid=uid,
        store_filters=store_filters,
        include_stores=include_stores,
        exclude_stores=exclude_stores,
        flatten=flatten,
    )
