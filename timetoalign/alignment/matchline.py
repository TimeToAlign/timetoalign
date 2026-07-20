"""MatchLine: ordered sequence of MatchStamps for WarpMap generation.

This module implements the MatchLine class, which provides the bridge
between MatchGraph and WarpMap.

A MatchLine is an ordered sequence of MatchStamps for a given source
timeline, sorted by coordinate on that timeline. It is the input for
WarpMap generation.

The hierarchy is:
    AlignmentAnchor -> MatchClaim -> MatchGraph -> MatchStamp -> MatchLine

Design:
    MatchLine collects MatchStamps from one or more MatchGraphs, orders
    them by coordinate on a designated source timeline, and provides
    ``get_coordinate_pairs()`` for WarpMap construction.  The Hendrix
    pattern (M6-M9) is supported via ``from_graphs()``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from timetoalign.alignment.graph import MatchGraph, MatchStamp

if TYPE_CHECKING:
    from timetoalign.alignment.claims import MatchClaim
    from timetoalign.alignment.groups import TimelineGroup
    from timetoalign.alignment.match_format import MatchFileContext
    from timetoalign.core.enums import Domain, TimeUnit
    from timetoalign.timelines import Timeline

module_logger = logging.getLogger(__name__)


class _RawStampExportView:
    """Present raw stamp coordinates to storage writers."""

    def __init__(self, stamp: MatchStamp) -> None:
        self._stamp = stamp

    def get_coordinate(self, timeline_id: str) -> float | None:
        """Return the raw coordinate expected by storage writers."""
        return self._stamp.get(timeline_id)


class _RawMatchLineExportView:
    """Present a MatchLine with raw-coordinate stamp views."""

    def __init__(self, match_line: MatchLine) -> None:
        self.source_timeline_id = match_line.source_timeline_id
        self.stamps = [_RawStampExportView(stamp) for stamp in match_line.stamps]
        self._target_timeline_ids = match_line.target_timeline_ids()

    def target_timeline_ids(self) -> set[str]:
        """Return target timeline IDs from the source MatchLine."""
        return self._target_timeline_ids


@dataclass
class MatchLine:
    """Ordered sequence of MatchStamps for a source timeline.

    A MatchLine collects all synchronised timestamps that mention a
    given *source* timeline, orders them by coordinate on that timeline,
    and exposes ``get_coordinate_pairs()`` to extract the
    ``(source_coord, target_coord)`` table consumed by WarpMap.

    Attributes:
        source_timeline_id: The timeline whose coordinates define the
            ordering of the stamps.
        stamps: MatchStamps sorted by coordinate on ``source_timeline_id``.

    Examples:
        >>> line = MatchLine.from_claims(
        ...     claims=claims,
        ...     source_timeline_id="score",
        ... )
        >>> pairs = line.get_coordinate_pairs("audio")
        >>> pairs
        [(0.0, 0.0), (100.0, 45.5), (200.0, 91.0)]

    See Also:
        `timetoalign.MatchGraph`
        `timetoalign.MatchStamp`
    """

    source_timeline_id: str
    stamps: list[MatchStamp] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate and sort stamps by source coordinate."""
        # Filter out stamps that don't include the source timeline
        valid_stamps = [
            s for s in self.stamps if s.has_timeline(self.source_timeline_id)
        ]
        if len(valid_stamps) != len(self.stamps):
            n_dropped = len(self.stamps) - len(valid_stamps)
            module_logger.warning(
                "MatchLine: dropped %d stamp(s) that do not contain "
                "source timeline '%s'",
                n_dropped,
                self.source_timeline_id,
            )
        # Sort by coordinate on the source timeline
        object.__setattr__(
            self,
            "stamps",
            sorted(
                valid_stamps,
                key=lambda s: s.get(self.source_timeline_id),
            ),
        )

    @property
    def n_stamps(self) -> int:
        """Number of stamps in this MatchLine."""
        return len(self.stamps)

    @property
    def source_coordinates(self) -> list[float]:
        """Sorted list of coordinates on the source timeline."""
        return [s.get(self.source_timeline_id) for s in self.stamps]

    def target_timeline_ids(self) -> set[str]:
        """All target timelines appearing in at least 2 stamps.

        A target timeline must appear in at least two stamps for
        interpolation (i.e., WarpMap construction) to be meaningful.

        Returns:
            Set of timeline IDs (excluding the source) that appear
            in >= 2 stamps.
        """
        counts: dict[str, int] = {}
        for stamp in self.stamps:
            for tl_id in stamp.present_timelines:
                if tl_id == self.source_timeline_id:
                    continue
                counts[tl_id] = counts.get(tl_id, 0) + 1
        return {tl_id for tl_id, count in counts.items() if count >= 2}

    def get_coordinate_pairs(
        self, target_timeline_id: str
    ) -> list[tuple[float, float]]:
        """Extract (source_coord, target_coord) pairs for a target timeline.

        Only stamps that contain both the source and target timelines
        contribute to the result. Pairs are ordered by source coordinate.

        Args:
            target_timeline_id: The timeline to extract target coordinates
                for.

        Returns:
            List of ``(source_coord, target_coord)`` tuples, sorted by
            source coordinate.

        Raises:
            ValueError: If ``target_timeline_id`` equals
                ``source_timeline_id``.
        """
        if target_timeline_id == self.source_timeline_id:
            raise ValueError(
                f"target_timeline_id '{target_timeline_id}' cannot be the "
                f"same as source_timeline_id '{self.source_timeline_id}'"
            )
        pairs: list[tuple[float, float]] = []
        for stamp in self.stamps:
            target_coord = stamp.get(target_timeline_id)
            if target_coord is None:
                continue
            source_coord = stamp.get(self.source_timeline_id)
            pairs.append((source_coord, target_coord))
        return pairs

    @classmethod
    def from_claims(
        cls,
        claims: list[MatchClaim],
        source_timeline_id: str,
        *,
        groups: dict[str, TimelineGroup] | None = None,
        timeline_to_group: dict[str, str] | None = None,
        timelines: dict[str, Timeline] | None = None,
        include_timelines: set[str] | None = None,
        exclude_timelines: set[str] | None = None,
        include_domains: set[Domain] | None = None,
        include_units: set[TimeUnit] | None = None,
    ) -> MatchLine:
        """Build a MatchLine from claims via a MatchGraph.

        Constructs a MatchGraph from the supplied claims, optionally
        extends it to groups, extracts MatchStamps, and orders them by
        coordinate on the source timeline.

        Args:
            claims: List of MatchClaims to resolve.
            source_timeline_id: The timeline whose coordinates define
                the ordering.
            groups: Dict of group_id -> TimelineGroup for group extension.
                If None, no group extension is performed.
            timeline_to_group: Dict of timeline_id -> group_id.  Required
                if ``groups`` is provided.
            timelines: Dict of timeline_id -> Timeline for domain/unit
                filtering.  Required if ``include_domains`` or
                ``include_units`` are set.
            include_timelines: Only extend to these timeline IDs.
            exclude_timelines: Do not extend to these timeline IDs.
            include_domains: Only extend to timelines in these domains.
            include_units: Only extend to timelines with these units.

        Returns:
            A MatchLine with stamps sorted by source coordinate.
        """
        graph = MatchGraph(claims)

        if groups is not None and timeline_to_group is not None:
            graph = graph.extend_to_groups(
                groups=groups,
                timeline_to_group=timeline_to_group,
                timelines=timelines,
                include_timelines=include_timelines,
                exclude_timelines=exclude_timelines,
                include_domains=include_domains,
                include_units=include_units,
            )

        stamps = graph.get_stamps()
        return cls(
            source_timeline_id=source_timeline_id,
            stamps=stamps,
        )

    @classmethod
    def from_graphs(
        cls,
        graphs: list[MatchGraph],
        source_timeline_id: str,
    ) -> MatchLine:
        """Build a MatchLine from multiple MatchGraphs.

        Merges MatchStamps from several MatchGraphs (the Hendrix M6-M9
        pattern) into a single ordered sequence. Duplicate stamps
        (same source coordinate) are deduplicated, keeping the stamp
        with the most timelines.

        Args:
            graphs: List of MatchGraphs to merge.
            source_timeline_id: The timeline whose coordinates define
                the ordering.

        Returns:
            A MatchLine with merged, deduplicated stamps sorted by
            source coordinate.
        """
        all_stamps: list[MatchStamp] = []
        for graph in graphs:
            all_stamps.extend(graph.get_stamps())

        # Deduplicate: if two stamps have the same source coordinate,
        # keep the one with more timelines (richer information).
        seen: dict[float, MatchStamp] = {}
        for stamp in all_stamps:
            coord = stamp.get(source_timeline_id)
            if coord is None:
                continue
            existing = seen.get(coord)
            if existing is None or stamp.n_timelines > existing.n_timelines:
                seen[coord] = stamp

        return cls(
            source_timeline_id=source_timeline_id,
            stamps=list(seen.values()),
        )

    def save_as(
        self,
        filepath: str | Path,
        *,
        format: str = "match",
        context: MatchFileContext | None = None,
    ) -> Path:
        """Export this MatchLine to a file.

        Args:
            filepath: Output file path.  If the extension matches a known
                format, the format is inferred (e.g. ``.match``).
            format: Export format.  Currently supported: ``"match"``.
            context: Supplementary data for format-specific fields.
                Required for full ``.match`` export; if ``None``, a minimal
                file with coordinate-only placeholder data is produced.

        Returns:
            The resolved output path.

        Raises:
            ValueError: If the format is not supported.

        Examples:
            >>> line.save_as("output.match")  # minimal placeholder export
            >>> line.save_as("output.match", context=ctx)  # rich export
        """
        from timetoalign.alignment.match_format import write_match_file

        filepath = Path(filepath)

        # Infer format from extension if it matches a known format
        ext = filepath.suffix.lower()
        if ext == ".match":
            format = "match"

        if format != "match":
            raise ValueError(
                f"Unsupported export format: {format!r}. "
                f"Currently supported: 'match'."
            )

        return write_match_file(filepath, _RawMatchLineExportView(self), context)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for storage.

        Returns:
            Dict with ``source_timeline_id`` and ``stamps``.
        """
        return {
            "source_timeline_id": self.source_timeline_id,
            "stamps": [s.to_dict(format="graph") for s in self.stamps],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MatchLine:
        """Deserialize from dictionary.

        Args:
            data: Dict as produced by ``to_dict()``.

        Returns:
            A new MatchLine.
        """
        return cls(
            source_timeline_id=data["source_timeline_id"],
            stamps=[MatchStamp.from_dict(s) for s in data["stamps"]],
        )

    def __repr__(self) -> str:
        targets = self.target_timeline_ids()
        target_str = ", ".join(sorted(targets)) if targets else "none"
        return (
            f"MatchLine(source='{self.source_timeline_id}', "
            f"stamps={self.n_stamps}, targets=[{target_str}])"
        )
