"""Provide named region operations for timeline instances."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from typing import Any

from timetoalign.core import CoordinateSpec

from ..regions import Region
from .coordinate_ops import coordinate_numeric_value


class RegionsMixin:
    """Provide named region operations for timeline instances."""

    def add_region(
        self,
        region_or_name: Region | str,
        start: CoordinateSpec | None = None,
        end: CoordinateSpec | None = None,
        *,
        meta: dict[str, Any] | None = None,
    ) -> Region:
        """Add or create a named Region on this timeline.

        Overloaded for backward compatibility:
        - ``add_region(Region)`` — attach a pre-existing Region object.
        - ``add_region(name, start, end)`` — delegate to :meth:`create_region`.

        Under the unified verb×noun API, ``add`` means "attach an existing
        object" while ``create`` means "construct + attach + return".

        Args:
            region_or_name: A Region object (new) or a string name (legacy).
            start: Start coordinate (only when region_or_name is a string).
            end: End coordinate (only when region_or_name is a string).
            meta: Optional metadata dictionary.

        Returns:
            The Region object (either the one passed in or the newly created one).

        Raises:
            ValueError: If region name already exists, end < start, or
                arguments are inconsistent.
            RuntimeError: If timeline is locked.

        Examples:
            >>> # New API — attach a pre-existing Region
            >>> r = Region("Chorus", Coordinate(10, TimeUnit.seconds),
            ...            Coordinate(30, TimeUnit.seconds))
            >>> tl.add_region(r)

            >>> # Legacy API (delegates to create_region)
            >>> tl.add_region("Verse", 30, 50, meta={"repeat": 2})
        """
        if isinstance(region_or_name, Region):
            return self._add_existing_region(region_or_name)
        # Legacy path: string name + positional start/end
        if start is None or end is None:
            raise ValueError(
                "add_region(name, start, end) requires both start and end. "
                "Pass a Region object for the single-argument form."
            )
        return self.create_region(region_or_name, start, end, meta=meta)

    def _add_existing_region(self, region: Region) -> Region:
        """Attach a pre-existing Region object to this timeline.

        Args:
            region: The Region to attach.

        Returns:
            The same Region object.

        Raises:
            ValueError: If a region with the same name already exists or
                the region's unit does not match the timeline's unit.
            RuntimeError: If timeline is locked.
        """
        self._check_not_locked("add region")

        if region.unit != self._unit:
            raise ValueError(
                f"Region unit '{region.unit}' does not match "
                f"timeline unit '{self._unit}'"
            )

        if region.name in self._regions:
            raise ValueError(f"Region '{region.name}' already exists")

        self._regions[region.name] = region
        self._logger.debug(
            f"Added region '{region.name}' "
            f"[{region.start.value}, {region.end.value})"
        )
        return region

    def create_region(
        self,
        name: str,
        start: CoordinateSpec,
        end: CoordinateSpec,
        *,
        meta: dict[str, Any] | None = None,
    ) -> Region:
        """Create a new named Region and attach it to this timeline.

        Under the unified verb×noun API, ``create`` constructs a new object,
        attaches it, and returns it.

        Args:
            name: Unique name for this region.
            start: Start coordinate.
            end: End coordinate (must be >= start).
            meta: Optional metadata dictionary.

        Returns:
            The created Region object.

        Raises:
            ValueError: If name already exists or end < start.
            RuntimeError: If timeline is locked.

        Examples:
            >>> tl.create_region("Chorus", 10.0, 30.0)
            >>> tl.create_region("Verse", 30.0, 50.0, meta={"repeat": 2})
        """
        self._check_not_locked("create region")

        if name in self._regions:
            raise ValueError(f"Region '{name}' already exists")

        start_coord = self.resolve_coordinate(start)
        end_coord = self.resolve_coordinate(end)

        region = Region(
            name=name,
            start=start_coord,
            end=end_coord,
            meta=meta or {},
        )

        self._regions[name] = region
        self._logger.debug(
            f"Created region '{name}' [{start_coord.value}, {end_coord.value})"
        )
        return region

    def create_regions_from_boundaries(
        self,
        boundaries: Sequence[CoordinateSpec],
        *,
        names: Sequence[str] | None = None,
        name_format: str = "{prefix}_{n}",
        prefix: str = "section",
    ) -> list[Region]:
        """Create contiguous regions from boundary coordinates.

        Given k+1 sorted boundary coordinates, creates k regions where
        region_i spans [boundaries[i], boundaries[i+1]).

        Args:
            boundaries: k+1 monotonically increasing coordinates.
            names: Explicit names for the k regions. Mutually exclusive
                with name_format/prefix.
            name_format: Format string. Placeholders: {prefix}, {i} (0-based),
                {n} (1-based).
            prefix: Prefix for auto-generated names.

        Returns:
            List of k Region objects in boundary order.

        Raises:
            ValueError: If fewer than 2 boundaries or not monotonically
                increasing.
            RuntimeError: If timeline is locked.

        Examples:
            >>> tl.create_regions_from_boundaries(
            ...     [0, 30, 60, 90],
            ...     prefix="movement",
            ... )
            [Region('movement_1', 0-30), Region('movement_2', 30-60),
             Region('movement_3', 60-90)]
        """
        self._check_not_locked("create regions from boundaries")

        if len(boundaries) < 2:
            raise ValueError(
                f"Need at least 2 boundary coordinates, got {len(boundaries)}"
            )

        coords = [self._resolve_axis_value(boundary) for boundary in boundaries]
        for i in range(1, len(coords)):
            if coords[i] <= coords[i - 1]:
                raise ValueError(
                    f"Boundaries must be monotonically increasing: "
                    f"boundaries[{i - 1}]={coords[i - 1]} >= "
                    f"boundaries[{i}]={coords[i]}"
                )

        n_regions = len(coords) - 1
        if names is not None:
            if len(names) != n_regions:
                raise ValueError(
                    f"Expected {n_regions} names for {n_regions} regions, "
                    f"got {len(names)}"
                )
            region_names = list(names)
        else:
            region_names = [
                name_format.format(prefix=prefix, i=i, n=i + 1)
                for i in range(n_regions)
            ]

        result: list[Region] = []
        for i in range(n_regions):
            region = self.create_region(region_names[i], coords[i], coords[i + 1])
            result.append(region)
        return result

    def create_regions_by_grouping(
        self,
        field: str,
        *,
        name_format: str = "{value}",
    ) -> list[Region]:
        """Create regions by grouping *adjacent* events on a field value.

        For each *run* of consecutive events that share the same value in the
        specified field, creates a region spanning the run's coordinate extent
        ``[min_start, max_end)``. Only adjacent events with the same value are
        grouped — non-adjacent occurrences of the same value produce separate
        regions.

        This "run-length" semantics is essential for musical data where, e.g.,
        the same time signature may recur after a change (4/4 → 3/4 → 4/4)
        and each occurrence should be its own region.

        Args:
            field: Event field name to group by.
            name_format: Format string. Placeholders: {value}, {i} (0-based),
                {n} (1-based), {run} (1-based run index for this value).

        Returns:
            List of Region objects ordered by start coordinate.

        Raises:
            ValueError: If field does not exist in events.
            RuntimeError: If timeline is locked.

        Examples:
            >>> # Time-signature regions (adjacent grouping)
            >>> tl.create_regions_by_grouping("timesig")
            [Region('4/4', 0-64), Region('3/4', 64-88), Region('4/4', 88-120)]
        """
        self._check_not_locked("create regions by grouping")

        # Collect events sorted by start coordinate
        events_sorted = self._sorted_event_dicts()
        if not events_sorted:
            return []

        # Check field exists
        first_event = events_sorted[0]
        if field not in first_event:
            raise ValueError(
                f"Field '{field}' not found in events. "
                f"Available fields: {list(first_event.keys())}"
            )

        # Build runs of adjacent equal values
        runs: list[tuple[Any, Any, Any]] = []  # (value, start, end)
        value_counts: dict[Any, int] = {}

        current_value = None
        run_start = 0.0
        run_end = 0.0

        for event in events_sorted:
            val = event.get(field)
            # Normalize struct values
            if isinstance(val, dict) and "value" in val:
                val = val["value"]

            ev_start_value = event.get("start", event.get("instant"))
            ev_end_value = event.get("end")
            if ev_end_value is None:
                ev_end_value = ev_start_value
            ev_start = (
                coordinate_numeric_value(ev_start_value)
                if ev_start_value is not None
                else None
            )
            ev_end = (
                coordinate_numeric_value(ev_end_value)
                if ev_end_value is not None
                else ev_start
            )

            if val != current_value:
                # Close previous run
                if current_value is not None:
                    runs.append((current_value, run_start, run_end))
                # Start new run
                current_value = val
                run_start = ev_start if ev_start is not None else 0.0
                run_end = ev_end if ev_end is not None else run_start
            else:
                # Extend current run
                if ev_end is not None:
                    run_end = max(run_end, ev_end)

        # Close last run
        if current_value is not None:
            runs.append((current_value, run_start, run_end))

        # Pre-compute total occurrences per value to detect ambiguity
        from collections import Counter

        total_occurrences = Counter(val for val, _, _ in runs)

        # Create regions
        result: list[Region] = []
        for i, (value, start, end) in enumerate(runs):
            value_counts.setdefault(value, 0)
            value_counts[value] += 1
            region_name = name_format.format(
                value=value,
                i=i,
                n=i + 1,
                run=value_counts[value],
            )
            # Auto-disambiguate if the default format would produce duplicates
            if region_name in self._regions and total_occurrences[value] > 1:
                region_name = f"{region_name}_run{value_counts[value]}"
            region = self.create_region(region_name, start, end)
            result.append(region)

        return result

    def create_regions_by_splitting(
        self,
        predicate: str | dict[str, Any] | Callable[[dict], bool],
        *,
        names: Sequence[str] | None = None,
        name_format: str = "{prefix}_{n}",
        prefix: str = "section",
        include_before_first: bool = True,
        include_after_last: bool = True,
    ) -> list[Region]:
        """Create contiguous regions by splitting at events matching a predicate.

        Finds events matching the predicate, uses their coordinates as split
        points, creates contiguous regions between consecutive split points.

        The predicate can be:
        - A string: field name. Events where this field is truthy (non-null,
          non-empty, non-zero) are split points.
        - A dict: keyword filters in the same style as ``EventData.filter()``.
          For example ``{"breaks": "section"}`` selects events whose ``breaks``
          field equals ``"section"``.
        - A callable: receives event dict, returns True for split points.

        For each matching event the split coordinate is the event's ``end``
        (interval events) or ``start``/``instant`` (instant events).

        Args:
            predicate: Field name, filter dict, or callable identifying
                split-point events.
            names: Explicit region names.
            name_format: Format string. Placeholders: {prefix}, {i}, {n}.
            prefix: Prefix for auto-generated names.
            include_before_first: Create a region from timeline origin to
                first split point.
            include_after_last: Create a region from last split point to
                timeline end.

        Returns:
            List of contiguous Region objects in coordinate order.

        Raises:
            RuntimeError: If timeline is locked.

        Examples:
            >>> # Split at section breaks
            >>> tl.create_regions_by_splitting("breaks", prefix="movement")

            >>> # Split at specific break types
            >>> tl.create_regions_by_splitting(
            ...     {"breaks": "section"}, prefix="movement"
            ... )
        """
        self._check_not_locked("create regions by splitting")

        # Resolve predicate to a callable
        match_fn = self._resolve_predicate(predicate)

        # Find split coordinates
        split_coords: list[Any] = []
        events_sorted = self._sorted_event_dicts()

        for event in events_sorted:
            if match_fn(event):
                # Use end coordinate for intervals, start for instants
                coord_value = event.get("end")
                if coord_value is None:
                    coord_value = event.get("start", event.get("instant"))
                if coord_value is not None:
                    split_coords.append(coordinate_numeric_value(coord_value))

        # Deduplicate and sort
        split_coords = sorted(set(split_coords))

        # Build boundary list
        boundaries: list[Any] = []
        if include_before_first:
            boundaries.append(self.origin.value)
        boundaries.extend(split_coords)
        if include_after_last:
            boundaries.append(self.length.value)

        # Deduplicate again (split point might coincide with origin/end)
        boundaries = sorted(set(boundaries))

        if len(boundaries) < 2:
            return []

        # Determine names
        n_regions = len(boundaries) - 1
        if names is not None:
            if len(names) != n_regions:
                raise ValueError(f"Expected {n_regions} names, got {len(names)}")
            region_names = list(names)
        else:
            region_names = [
                name_format.format(prefix=prefix, i=i, n=i + 1)
                for i in range(n_regions)
            ]

        result: list[Region] = []
        for i in range(n_regions):
            region = self.create_region(
                region_names[i], boundaries[i], boundaries[i + 1]
            )
            result.append(region)
        return result

    def _resolve_predicate(
        self,
        predicate: str | dict[str, Any] | Callable[[dict], bool],
    ) -> Callable[[dict], bool]:
        """Convert a predicate specification to a callable.

        Supports three forms:
        - str: field name — truthy test on that field's value.
        - dict: keyword filters (same semantics as ``EventData.filter``).
        - callable: used directly.

        Args:
            predicate: The predicate specification.

        Returns:
            A callable ``(event_dict) -> bool``.
        """
        if callable(predicate) and not isinstance(predicate, (str, dict)):
            return predicate

        if isinstance(predicate, str):
            name = predicate

            def _match_truthy(event: dict) -> bool:
                val = event.get(name)
                if val is None:
                    return False
                if isinstance(val, dict) and "value" in val:
                    val = val["value"]
                if isinstance(val, str):
                    return bool(val.strip())
                return bool(val)

            return _match_truthy

        if isinstance(predicate, dict):
            filters = predicate

            def _match_dict(event: dict) -> bool:
                for key, expected in filters.items():
                    val = event.get(key)
                    if val is None:
                        return False
                    if isinstance(val, dict) and "value" in val:
                        val = val["value"]
                    # Support list of acceptable values
                    if isinstance(expected, (list, tuple, set, frozenset)):
                        if val not in expected:
                            return False
                    else:
                        if val != expected:
                            return False
                return True

            return _match_dict

        raise TypeError(
            f"predicate must be str, dict, or callable, got {type(predicate)}"
        )

    def get_region(self, name: str) -> Region:
        """Get a Region by name.

        Args:
            name: The region name.

        Returns:
            The Region object.

        Raises:
            KeyError: If no region with that name exists.
        """
        if name not in self._regions:
            raise KeyError(f"No region named '{name}'")
        return self._regions[name]

    def get_regions_at(
        self,
        coord: CoordinateSpec,
    ) -> list[Region]:
        """Return all regions containing the given coordinate.

        A region contains coord if region.start <= coord < region.end
        (left-inclusive, right-exclusive).

        Args:
            coord: The coordinate to query.

        Returns:
            List of Region objects containing coord, ordered by start
            coordinate. Empty list if no regions contain coord.

        Examples:
            >>> tl.get_regions_at(75.0)
            [Region('verse_1', 30-90), Region('chorus', 60-120)]
        """
        coord_val = float(self._resolve_axis_value(coord))
        matching = [r for r in self._regions.values() if r.contains(coord_val)]
        matching.sort(key=lambda r: float(r.start.value))
        return matching

    def has_region(self, name: str) -> bool:
        """Check if a region exists.

        Args:
            name: Name of the region.

        Returns:
            True if the region exists.
        """
        return name in self._regions

    def iter_regions(self) -> Iterator[Region]:
        """Iterate over all regions in insertion order.

        Yields:
            Region objects.
        """
        yield from self._regions.values()

    @property
    def n_regions(self) -> int:
        """Number of regions on this timeline."""
        return len(self._regions)

    def list_regions(self) -> list[str]:
        """List all region names.

        Returns:
            List of region names in insertion order.
        """
        return list(self._regions.keys())
