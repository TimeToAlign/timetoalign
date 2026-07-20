"""MatchGraph and MatchStamp classes.

This module implements the mid-level graph structure for alignment:

- MatchStamp: Cross-group timestamp at a single coordinate
- MatchGraph: Graph of MatchClaims yielding MatchStamps

The hierarchy is:
    AlignmentAnchor -> MatchClaim -> MatchGraph -> MatchStamp -> MatchLine

MatchGraph uses networkx to:
1. Build a graph where nodes are (timeline_id, coordinate) tuples
2. Edges represent synchronous AlignmentAnchors (explicit or inferred)
3. Extend edges via Group membership (implicit claims)
4. Extract MatchStamps from connected components

Design:
    Only synchronous claims produce graph edges. Non-synchronous claims
    (conceptual matches, NOMATCH) are stored as metadata but do not create
    edges. ``extend_to_groups()`` creates implicit ``MatchClaim`` objects
    (case d) and adds their anchors as edges. Each Hendrix M-box
    (M1-M15) is a MatchGraph -- the system is NOT a global graph.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal

import networkx as nx

from timetoalign.alignment.claims import AlignmentAnchor, MatchClaim
from timetoalign.core.enums import Domain, TimeUnit
from timetoalign.core.timestamp import ConversionMapsSpec, Stamp

if TYPE_CHECKING:
    from timetoalign.alignment.bundle import AlignmentBundle
    from timetoalign.alignment.groups import TimelineGroup
    from timetoalign.timelines import Timeline

module_logger = logging.getLogger(__name__)


# Type alias for graph nodes: (timeline_id, coordinate)
GraphNode = tuple[str, float]


# region MatchStamp


@dataclass(frozen=True)
class MatchStamp(Stamp):
    """A synchronized timestamp across multiple timelines.

    A MatchStamp represents a single coordinate (or instant) that has been
    synchronized across multiple timelines via explicit anchors and/or
    inferred group membership.

    Contains one coordinate per participating timeline, where coordinates
    are linked via explicit anchors or inferred group membership.

    Attributes:
        coordinates: Dict of timeline_id -> coordinate.
        anchor_edges: List of (tl_a, tl_b) pairs that are explicitly anchored.
        inferred_edges: List of (tl_a, tl_b) pairs inferred via groups.
        units: Coordinate unit name for each timeline.
        axis: Coordinate used to query the stamp.
        source: Bundle that produced the stamp.
        source_id: Timeline ID used for the query.
        is_interpolated: Whether the stamp used interpolated transfer.
        conversion_maps: Conversion maps available to unit lookup.

    Examples:
        >>> stamp = MatchStamp(
        ...     coordinates={"score": 100.0, "audio": 45.5, "video": 1365.0},
        ...     anchor_edges=[("score", "audio")],
        ...     inferred_edges=[("audio", "video")],
        ... )
        >>> stamp.get("audio")
        45.5
    """

    coordinates: dict[str, float] = field(default_factory=dict)
    anchor_edges: list[tuple[str, str]] = field(default_factory=list)
    inferred_edges: list[tuple[str, str]] = field(default_factory=list)
    units: dict[str, str] = field(default_factory=dict)
    axis: float | None = None
    source: "AlignmentBundle | None" = None
    source_id: str | None = None
    is_interpolated: bool = False
    conversion_maps: ConversionMapsSpec = True

    @property
    def present_timelines(self) -> list[str]:
        """List of timeline IDs in this stamp."""
        return list(self.coordinates.keys())

    @property
    def n_timelines(self) -> int:
        """Number of timelines in this stamp."""
        return len(self.coordinates)

    @property
    def n_explicit_edges(self) -> int:
        """Number of explicitly anchored pairs."""
        return len(self.anchor_edges)

    @property
    def n_inferred_edges(self) -> int:
        """Number of inferred (via group) pairs."""
        return len(self.inferred_edges)

    def get(self, timeline_id: str, default: float | None = None) -> float | None:
        """Get coordinate for a specific timeline.

        Args:
            timeline_id: The timeline to get coordinate for.
            default: Value returned when the timeline is absent.

        Returns:
            The coordinate, or the default if the timeline is absent.
        """
        return self.coordinates.get(timeline_id, default)

    def get_unit(self, unit: TimeUnit) -> float | None:
        """Get the query coordinate converted to a unit.

        Unit conversion is delegated to the source timeline's owning group so
        the same conversion-map selection rules as ``TimeStamp`` apply.

        Args:
            unit: The target unit.

        Returns:
            The converted coordinate, or None when it cannot be resolved.
        """
        timestamp = self._source_timestamp()
        if timestamp is None:
            return None
        return timestamp.get_unit(unit)

    def _unit_for(self, timeline_id: str) -> TimeUnit | None:
        """Get the unit associated with a timeline ID."""
        unit = self.units.get(timeline_id)
        if unit is None:
            return None
        try:
            return TimeUnit(unit)
        except ValueError:
            return None

    def _source_timestamp(self) -> Any | None:
        """Resolve the source group's TimeStamp for unit conversion."""
        if self.source is None or self.source_id is None or self.axis is None:
            return None

        bundle_uid = self.source._timeline_id_to_uid.get(self.source_id, self.source_id)
        group_id = self.source.timeline_to_group.get(bundle_uid)
        if group_id is None:
            return None

        group = self.source.groups.get(group_id)
        if group is None:
            return None
        actual_timeline_id = self.source._uid_to_timeline_id.get(
            bundle_uid, self.source_id
        )
        try:
            timestamp = group.get_timestamp_at(
                self.axis,
                actual_timeline_id,
                conversion_maps=self.conversion_maps,
            )
            return replace(timestamp, conversion_maps=self.conversion_maps)
        except (AttributeError, KeyError, TypeError, ValueError):
            return None

    def _unit_resolution_enabled(self, unit: TimeUnit) -> bool:
        """Return whether the conversion-map specification permits a unit."""
        timestamp = self._source_timestamp()
        if timestamp is None:
            return False
        return timestamp._unit_resolution_enabled(unit)

    def _is_timeline_id(self, key: str) -> bool:
        """Return whether key names a coordinate carried by this stamp."""
        return key in self.coordinates or key == self.source_id

    def has_timeline(self, timeline_id: str) -> bool:
        """Check if timeline is in this stamp."""
        return timeline_id in self.coordinates

    def get_group_coordinates(
        self,
        group: "TimelineGroup",
    ) -> dict[str, float]:
        """Get all coordinates for timelines in a specific group.

        Args:
            group: The TimelineGroup to filter by.

        Returns:
            Dict of timeline_id -> coordinate for timelines in the group.
        """
        group_tl_ids = set(group.timeline_ids)
        return {
            tl_id: coord
            for tl_id, coord in self.coordinates.items()
            if tl_id in group_tl_ids
        }

    def filter_by_timelines(
        self,
        include: set[str] | None = None,
        exclude: set[str] | None = None,
    ) -> "MatchStamp":
        """Create filtered stamp with subset of timelines.

        Args:
            include: Only include these timelines (None = all).
            exclude: Exclude these timelines (None = none).

        Returns:
            New MatchStamp with filtered timelines.
        """
        filtered_coords = {}
        for tl_id, coord in self.coordinates.items():
            if include is not None and tl_id not in include:
                continue
            if exclude is not None and tl_id in exclude:
                continue
            filtered_coords[tl_id] = coord

        # Filter edges to only include those between remaining timelines
        remaining = set(filtered_coords.keys())

        filtered_anchor_edges = [
            (a, b) for a, b in self.anchor_edges if a in remaining and b in remaining
        ]
        filtered_inferred_edges = [
            (a, b) for a, b in self.inferred_edges if a in remaining and b in remaining
        ]

        return MatchStamp(
            coordinates=filtered_coords,
            anchor_edges=filtered_anchor_edges,
            inferred_edges=filtered_inferred_edges,
            units={
                tl_id: self.units[tl_id] for tl_id in remaining if tl_id in self.units
            },
            axis=self.axis,
            source=self.source,
            source_id=self.source_id,
            is_interpolated=self.is_interpolated,
            conversion_maps=self.conversion_maps,
        )

    def to_dict(
        self,
        format: Literal["flat", "prefix", "nested", "graph"] = "flat",
    ) -> dict[str, Any]:
        """Materialize the stamp in a flat, grouped, or graph representation.

        Args:
            format: Output representation. ``"graph"`` preserves the legacy
                MatchGraph storage shape.

        Returns:
            The requested dictionary representation.

        Raises:
            ValueError: If a grouped format is requested without a source
                bundle, or if the format is unknown.
        """
        if format == "graph":
            return {
                "coordinates": self.coordinates,
                "anchor_edges": self.anchor_edges,
                "inferred_edges": self.inferred_edges,
            }

        def _bundle_uid(timeline_id: str) -> str:
            if self.source is None:
                return timeline_id
            return self.source._timeline_id_to_uid.get(timeline_id, timeline_id)

        def _uid_label(timeline_id: str) -> str:
            bundle_uid = _bundle_uid(timeline_id)
            unit = self.units.get(timeline_id) or self.units.get(bundle_uid)
            if unit is None and self.source is not None:
                unit = self.source._get_unit_map().get(bundle_uid)
            return f"{bundle_uid} ({unit})" if unit else bundle_uid

        if format not in ("flat", "prefix", "nested"):
            raise ValueError(
                f"Unknown format: {format!r}. Use 'flat', 'prefix', "
                "'nested', or 'graph'"
            )
        if format in ("prefix", "nested") and self.source is None:
            raise ValueError(
                f"MatchStamp.to_dict(format={format!r}) requires a source bundle "
                "to resolve timeline groups"
            )

        grouped: dict[str, dict[str, float | None]] = {}
        for timeline_id, coordinate in self.coordinates.items():
            bundle_uid = _bundle_uid(timeline_id)
            if self.source is None:
                grouped.setdefault(bundle_uid, {})[timeline_id] = coordinate
                continue

            group_id = self.source.timeline_to_group.get(bundle_uid, bundle_uid)
            if group_id in grouped:
                continue
            group = self.source.groups.get(group_id)
            if group is None:
                grouped[group_id] = {bundle_uid: coordinate}
                continue

            actual_timeline_id = self.source._uid_to_timeline_id.get(
                bundle_uid, timeline_id
            )
            try:
                timestamp = group.get_timestamp_at(
                    coordinate,
                    actual_timeline_id,
                    conversion_maps=self.conversion_maps,
                )
            except (KeyError, TypeError, ValueError):
                grouped[group_id] = {bundle_uid: coordinate}
                continue

            grouped[group_id] = {
                self.source._timeline_id_to_uid.get(
                    group_tl_id, group_tl_id
                ): timestamp.get(group_tl_id)
                for group_tl_id in group.timeline_ids
                if not self.units
                or group_tl_id in self.units
                or self.source._timeline_id_to_uid.get(group_tl_id, group_tl_id)
                in self.units
            }

        if format == "flat":
            return {
                _uid_label(timeline_id): coordinate
                for timeline_coordinates in grouped.values()
                for timeline_id, coordinate in timeline_coordinates.items()
            }

        if format == "nested":
            return {
                group_id: {
                    _uid_label(timeline_id): coordinate
                    for timeline_id, coordinate in timeline_coordinates.items()
                }
                for group_id, timeline_coordinates in grouped.items()
            }

        result: dict[str, float | None] = {}
        for group_id, timeline_coordinates in grouped.items():
            for timeline_id, coordinate in timeline_coordinates.items():
                result[f"{group_id}/{_uid_label(timeline_id)}"] = coordinate
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MatchStamp":
        """Deserialize from dictionary."""
        return cls(
            coordinates=data["coordinates"],
            anchor_edges=[tuple(e) for e in data.get("anchor_edges", [])],
            inferred_edges=[tuple(e) for e in data.get("inferred_edges", [])],
        )

    def __repr__(self) -> str:
        tl_list = ", ".join(f"{k}={v:.2f}" for k, v in self.coordinates.items())
        return f"MatchStamp({tl_list})"

    def __str__(self) -> str:
        """Readable cross-section showing all coordinates.

        Examples:
            >>> print(stamp)
            MatchStamp (3 timelines, 2 edges)
              ID              Coordinate   Type
              score:clt1      0            anchor
              perf:dlt1       0            anchor
              perf:dlt2       128          inferred
        """
        n_edges = self.n_explicit_edges + self.n_inferred_edges
        lines: list[str] = [
            f"MatchStamp ({self.n_timelines} timelines, {n_edges} edges)"
        ]

        if not self.coordinates:
            return lines[0]

        def _fmt(v: float) -> str:
            """Format a coordinate value - never use scientific notation."""
            if v == int(v) and abs(v) < 1e15:
                return str(int(v))
            elif abs(v) >= 1e6:
                return str(int(round(v)))
            elif abs(v) >= 1:
                return f"{v:.6f}".rstrip("0").rstrip(".")
            else:
                return f"{v:.6f}".rstrip("0").rstrip(".")

        # Classify each timeline by edge type
        anchor_tls = set()
        for a, b in self.anchor_edges:
            anchor_tls.add(a)
            anchor_tls.add(b)
        inferred_tls = set()
        for a, b in self.inferred_edges:
            inferred_tls.add(a)
            inferred_tls.add(b)

        entries: list[tuple[str, str, str]] = []
        for tl_id, coord in self.coordinates.items():
            if tl_id in anchor_tls:
                tag = "anchor"
            elif tl_id in inferred_tls:
                tag = "inferred"
            else:
                tag = ""
            entries.append((tl_id, _fmt(coord), tag))

        if entries:
            max_id = max(len(e[0]) for e in entries)
            max_coord = max(len(e[1]) for e in entries)
            for tl_id, coord_str, tag in entries:
                line = f"  {tl_id:<{max_id}}  {coord_str:>{max_coord}}"
                if tag:
                    line += f"  {tag}"
                lines.append(line)

        return "\n".join(lines)

    def _repr_html_(self) -> str:
        """Return HTML representation for Jupyter notebooks.

        Displays the MatchStamp as an HTML table showing all coordinates
        with their edge types, mirroring the TimeStamp HTML display.
        """
        import html as html_mod

        from timetoalign.display.html import affordance_line

        def _fmt_html(v: float) -> str:
            """Format coordinate without scientific notation."""
            if v == int(v) and abs(v) < 1e15:
                return str(int(v))
            elif abs(v) >= 1e6:
                return str(int(round(v)))
            elif abs(v) >= 1:
                return f"{v:.6f}".rstrip("0").rstrip(".")
            else:
                return f"{v:.6f}".rstrip("0").rstrip(".")

        n_edges = self.n_explicit_edges + self.n_inferred_edges

        # Classify timelines
        anchor_tls = set()
        for a, b in self.anchor_edges:
            anchor_tls.add(a)
            anchor_tls.add(b)
        inferred_tls = set()
        for a, b in self.inferred_edges:
            inferred_tls.add(a)
            inferred_tls.add(b)

        rows = []
        for tl_id, coord in self.coordinates.items():
            esc_id = html_mod.escape(tl_id)
            formatted = _fmt_html(coord)
            if tl_id in anchor_tls:
                tag = "<em>anchor</em>"
                rows.append(
                    f"<tr><td><strong>{esc_id}</strong></td>"
                    f"<td style='text-align: right;'>{formatted}</td>"
                    f"<td>{tag}</td></tr>"
                )
            elif tl_id in inferred_tls:
                tag = "<em style='color: #666;'>inferred</em>"
                rows.append(
                    f"<tr><td style='color: #666;'>{esc_id}</td>"
                    f"<td style='text-align: right;'>{formatted}</td>"
                    f"<td>{tag}</td></tr>"
                )
            else:
                rows.append(
                    f"<tr><td>{esc_id}</td>"
                    f"<td style='text-align: right;'>{formatted}</td>"
                    f"<td></td></tr>"
                )

        badge = (
            f" <span style='background: #e3f2fd; padding: 0 4px; "
            f"border-radius: 3px; font-size: 0.8em;'>"
            f"{self.n_timelines} timelines, {n_edges} edges</span>"
        )

        return (
            f"<div style='font-family: monospace;'>"
            f"<strong>MatchStamp</strong>{badge}"
            f"<table style='border-collapse: collapse; margin-top: 4px;'>"
            f"<thead><tr style='border-bottom: 1px solid #ccc;'>"
            f"<th style='text-align: left; padding: 2px 8px;'>ID</th>"
            f"<th style='text-align: right; padding: 2px 8px;'>Coordinate</th>"
            f"<th style='text-align: left; padding: 2px 8px;'>Type</th>"
            f"</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            f"</table>"
            f"{affordance_line(['stamp.get(<tl_id>)', 'stamp.get_coordinate(<tl_id>)'])}"
            f"</div>"
        )


# endregion


# region MatchGraph


class MatchGraph:
    """A graph of MatchClaims connecting events across timelines/groups.

    The MatchGraph builds a networkx graph where:
    - Nodes: (timeline_id, coordinate) tuples
    - Edges: synchronous AlignmentAnchors (explicit or implicit)

    Only synchronous claims produce graph edges. Non-synchronous claims
    (conceptual matches, NOMATCH) are stored in ``_claims`` but do not
    create nodes or edges.

    Each Hendrix M-box (M1–M15) is a separate MatchGraph. The system
    is NOT a global graph; MatchGraphs are created on demand.

    Attributes:
        claims: List of all MatchClaims in this graph (synchronous and non-synchronous).

    Examples:
        >>> # Build graph from claims
        >>> graph = MatchGraph(claims=[claim1, claim2])

        >>> # Extend via group membership
        >>> extended = graph.extend_to_groups(groups, timeline_to_group)

        >>> # Get synchronized timestamps
        >>> stamps = graph.get_stamps()
    """

    def __init__(self, claims: list[MatchClaim] | None = None):
        """Initialize MatchGraph from MatchClaims.

        Args:
            claims: List of MatchClaims to build graph from.
        """
        self._claims: list[MatchClaim] = claims or []
        self._graph: nx.Graph = self._build_graph()
        self._logger = module_logger.getChild("MatchGraph")

    @property
    def claims(self) -> list[MatchClaim]:
        """List of all MatchClaims in this graph (synchronous and non-synchronous)."""
        return self._claims

    @property
    def synchronous_claims(self) -> list[MatchClaim]:
        """List of only synchronous MatchClaims (those with anchors/edges)."""
        return [c for c in self._claims if c.is_synchronous]

    @property
    def non_synchronous_claims(self) -> list[MatchClaim]:
        """List of non-synchronous MatchClaims (NOMATCH, conceptual)."""
        return [c for c in self._claims if not c.is_synchronous]

    @property
    def n_claims(self) -> int:
        """Number of claims in this graph."""
        return len(self._claims)

    @property
    def n_nodes(self) -> int:
        """Number of nodes in the graph."""
        return self._graph.number_of_nodes()

    @property
    def n_edges(self) -> int:
        """Number of edges in the graph."""
        return self._graph.number_of_edges()

    timeline_ids = property(
        lambda self: {node[0] for node in self._graph.nodes()},
        doc="Set of all timeline IDs in the graph.",
    )

    def _build_graph(self) -> nx.Graph:
        """Build the anchor graph from claims.

        Only synchronous claims (those with anchors) produce graph edges.
        Non-synchronous claims are stored in ``_claims`` but do not create
        nodes or edges.

        Nodes: (timeline_id, coordinate) tuples
        Edges: Anchors with attributes (explicit, synchronous, claim_id)

        Returns:
            networkx Graph representing the anchor structure.
        """
        G = nx.Graph()

        for claim in self._claims:
            if not claim.is_synchronous or claim.start_anchor is None:
                continue

            # Add start anchor edge
            self._add_anchor_edge(G, claim.start_anchor, claim)

            # Add end anchor edge if interval
            if claim.end_anchor:
                self._add_anchor_edge(G, claim.end_anchor, claim)

        return G

    def _add_anchor_edge(
        self,
        G: nx.Graph,
        anchor: AlignmentAnchor,
        claim: MatchClaim,
    ) -> None:
        """Add an anchor as an edge to the graph.

        Args:
            G: The networkx graph to add to.
            anchor: The AlignmentAnchor to add.
            claim: The parent MatchClaim for metadata.
        """
        node_a: GraphNode = (anchor.timeline_a_id, anchor.coordinate_a)
        node_b: GraphNode = (anchor.timeline_b_id, anchor.coordinate_b)

        G.add_edge(
            node_a,
            node_b,
            explicit=claim.is_explicit,
            synchronous=claim.is_synchronous,
            claim_id=claim.id,
        )

    def get_nodes_for_timeline(self, timeline_id: str) -> list[GraphNode]:
        """Get all nodes for a specific timeline.

        Args:
            timeline_id: The timeline to get nodes for.

        Returns:
            List of (timeline_id, coordinate) nodes.
        """
        return [node for node in self._graph.nodes() if node[0] == timeline_id]

    def get_coordinates_for_timeline(self, timeline_id: str) -> list[float]:
        """Get all coordinates for a specific timeline.

        Args:
            timeline_id: The timeline to get coordinates for.

        Returns:
            List of coordinates, sorted.
        """
        coords = [node[1] for node in self._graph.nodes() if node[0] == timeline_id]
        return sorted(coords)

    def get_connected_nodes(self, node: GraphNode) -> list[GraphNode]:
        """Get all nodes connected to a given node.

        Args:
            node: The (timeline_id, coordinate) node.

        Returns:
            List of connected nodes.
        """
        if node not in self._graph:
            return []
        return list(self._graph.neighbors(node))

    def get_connected_timelines(self, timeline_id: str) -> set[str]:
        """Get all timelines connected to a given timeline.

        Args:
            timeline_id: The timeline to check.

        Returns:
            Set of connected timeline IDs.
        """
        connected = set()
        for node in self.get_nodes_for_timeline(timeline_id):
            for neighbor in self._graph.neighbors(node):
                connected.add(neighbor[0])
        return connected - {timeline_id}

    def extend_to_groups(
        self,
        groups: dict[str, "TimelineGroup"],
        timeline_to_group: dict[str, str],
        include_inferred: bool = True,
        *,
        timelines: dict[str, "Timeline"] | None = None,
        include_timelines: set[str] | None = None,
        exclude_timelines: set[str] | None = None,
        include_domains: set[Domain] | None = None,
        include_units: set[TimeUnit] | None = None,
    ) -> "MatchGraph":
        """Extend anchors to full group timestamps via implicit claims.

        For each coordinate in the graph, if it belongs to a Group,
        computes the equivalent coordinate for every other member of that
        Group and adds an implicit ``MatchClaim`` (case d) plus the
        corresponding edge. Filters control which timelines receive
        implicit claims.

        Args:
            groups: Dict of group_id -> TimelineGroup.
            timeline_to_group: Dict of timeline_id -> group_id.
            include_inferred: Whether to add inferred edges.
            timelines: Optional dict of timeline_id -> Timeline for
                resolving domain/unit filters. Required if
                ``include_domains`` or ``include_units`` are set.
            include_timelines: Only extend to these timeline IDs.
            exclude_timelines: Do not extend to these timeline IDs.
            include_domains: Only extend to timelines in these domains.
                Requires ``timelines`` parameter.
            include_units: Only extend to timelines with these units.
                Requires ``timelines`` parameter.

        Returns:
            New MatchGraph with extended edges (or self if not extending).
        """
        if not include_inferred:
            return self

        # Create a copy of the graph
        extended = nx.Graph(self._graph)
        implicit_claims: list[MatchClaim] = []

        for node in list(self._graph.nodes()):
            timeline_id, coord = node

            # Check if timeline belongs to a group
            group_id = timeline_to_group.get(timeline_id)
            if not group_id:
                continue

            group = groups.get(group_id)
            if not group:
                continue

            # Find the source claim for traceability
            source_claim = self._find_source_claim_for_node(node)

            # Add inferred edges to all other timelines in group
            for other_tl_id in group.timeline_ids:
                if other_tl_id == timeline_id:
                    continue

                # Apply filters
                if not self._passes_filters(
                    other_tl_id,
                    timelines=timelines,
                    include_timelines=include_timelines,
                    exclude_timelines=exclude_timelines,
                    include_domains=include_domains,
                    include_units=include_units,
                ):
                    continue

                # Convert coordinate to other timeline
                try:
                    other_coord = group.convert(
                        coord, source=timeline_id, target=other_tl_id
                    )
                    if other_coord is None:
                        continue
                except (KeyError, ValueError):
                    continue

                other_node: GraphNode = (other_tl_id, other_coord)

                # Add implicit edge if not already connected
                if not extended.has_edge(node, other_node):
                    # Create an implicit MatchClaim (case d)
                    implicit_claim = MatchClaim.implicit(
                        tl_a_id=timeline_id,
                        coord_a=coord,
                        tl_b_id=other_tl_id,
                        coord_b=other_coord,
                        source_claim=source_claim,
                    )
                    implicit_claims.append(implicit_claim)

                    extended.add_edge(
                        node,
                        other_node,
                        explicit=False,
                        synchronous=True,
                        inferred_via="group",
                        group_id=group_id,
                        claim_id=implicit_claim.id,
                    )

        all_claims = list(self._claims) + implicit_claims
        return MatchGraph._from_graph(extended, all_claims)

    def _find_source_claim_for_node(self, node: GraphNode) -> MatchClaim | None:
        """Find the first explicit synchronous claim that contains this node.

        Args:
            node: The (timeline_id, coordinate) node.

        Returns:
            The source MatchClaim, or None if not found.
        """
        timeline_id, coord = node
        for claim in self._claims:
            if not claim.is_synchronous or not claim.is_explicit:
                continue
            if claim.start_anchor is None:
                continue
            # Check if this claim's anchors touch this node
            for anchor in claim.anchors:
                if anchor.timeline_a_id == timeline_id and anchor.coordinate_a == coord:
                    return claim
                if anchor.timeline_b_id == timeline_id and anchor.coordinate_b == coord:
                    return claim
        return None

    @staticmethod
    def _passes_filters(
        timeline_id: str,
        *,
        timelines: dict[str, "Timeline"] | None = None,
        include_timelines: set[str] | None = None,
        exclude_timelines: set[str] | None = None,
        include_domains: set[Domain] | None = None,
        include_units: set[TimeUnit] | None = None,
    ) -> bool:
        """Check whether a timeline passes the given filters.

        Args:
            timeline_id: The timeline ID to check.
            timelines: Dict of timeline_id -> Timeline for metadata.
            include_timelines: Only these timeline IDs pass.
            exclude_timelines: These timeline IDs are rejected.
            include_domains: Only timelines in these domains pass.
            include_units: Only timelines with these units pass.

        Returns:
            True if the timeline passes all filters.
        """
        if include_timelines is not None and timeline_id not in include_timelines:
            return False
        if exclude_timelines is not None and timeline_id in exclude_timelines:
            return False

        if include_domains is not None or include_units is not None:
            if timelines is None:
                # Cannot resolve domain/unit without timeline objects
                return True
            tl = timelines.get(timeline_id)
            if tl is None:
                return True  # Unknown timeline passes by default

            if include_domains is not None:
                tl_unit = getattr(tl, "unit", None)
                if tl_unit is not None:
                    tl_domain = getattr(tl_unit, "domain", None)
                    if tl_domain is not None and tl_domain not in include_domains:
                        return False

            if include_units is not None:
                tl_unit = getattr(tl, "unit", None)
                if tl_unit is not None and tl_unit not in include_units:
                    return False

        return True

    @classmethod
    def _from_graph(
        cls,
        graph: nx.Graph,
        claims: list[MatchClaim],
    ) -> "MatchGraph":
        """Create MatchGraph from existing networkx graph.

        Internal constructor for creating extended graphs.

        Args:
            graph: The networkx graph.
            claims: All claims (original + implicit).

        Returns:
            New MatchGraph wrapping the graph.
        """
        instance = cls.__new__(cls)
        instance._claims = claims
        instance._graph = graph
        instance._logger = module_logger.getChild("MatchGraph")
        return instance

    def get_stamps(
        self,
    ) -> list["MatchStamp"]:
        """Get all MatchStamps from the graph.

        Returns one MatchStamp per connected component, each containing
        all coordinates reachable from that component.

        Args:
        Returns:
            List of MatchStamps, one per connected component.
        """
        stamps = []
        for component in nx.connected_components(self._graph):
            node = next(iter(component))
            stamp = self._build_stamp_from_node(node)
            stamps.append(stamp)
        return stamps

    def get_matchstamp(self) -> "MatchStamp":
        """Get the single MatchStamp for this graph.

        One MatchGraph = one MatchStamp. The MatchStamp is the union of
        all coordinates reachable through the graph's edges.

        If the graph contains multiple disconnected components, this
        method raises ``ValueError`` -- each component should be its own
        MatchGraph. Use ``split_components()`` to separate them first, or
        use the legacy ``get_stamps()`` method.

        Returns:
            Single MatchStamp spanning all timelines in the graph.

        Raises:
            ValueError: If the graph has multiple disconnected components.
            ValueError: If the graph has no synchronous claims (no nodes).

        See Also:
            `split_components`: Split a multi-component graph into separate
                MatchGraph objects.
            `get_stamps`: Legacy method returning one stamp per component.
        """
        components = list(nx.connected_components(self._graph))
        if not components:
            raise ValueError(
                "MatchGraph has no synchronous claims and therefore no nodes. "
                "Cannot produce a MatchStamp from an empty graph."
            )
        if len(components) > 1:
            raise ValueError(
                f"MatchGraph has {len(components)} disconnected components. "
                f"One graph = one MatchStamp. Use split_components() first, "
                f"or use get_stamps() for the legacy multi-component API."
            )
        node = next(iter(components[0]))
        return self._build_stamp_from_node(node)

    def split_components(self) -> list["MatchGraph"]:
        """Split this graph into one MatchGraph per connected component.

        Each returned MatchGraph represents a single connected component
        and can be queried with ``get_matchstamp()``.

        Returns:
            List of MatchGraph objects, one per connected component.
            Empty list if the graph has no synchronous claims.
        """
        components = list(nx.connected_components(self._graph))
        if not components:
            return []

        result = []
        for component in components:
            subgraph = self._graph.subgraph(component).copy()

            # Find claims whose anchors are entirely within this component
            component_claims = []
            component_tl_ids = {node[0] for node in component}
            for c in self._claims:
                if c.is_synchronous:
                    if (
                        c.timeline_a_id in component_tl_ids
                        and c.timeline_b_id in component_tl_ids
                    ):
                        component_claims.append(c)
                else:
                    # Non-synchronous claims: include if both timelines
                    # are in this component
                    if (
                        c.timeline_a_id in component_tl_ids
                        and c.timeline_b_id in component_tl_ids
                    ):
                        component_claims.append(c)

            result.append(MatchGraph._from_graph(subgraph, component_claims))
        return result

    @property
    def n_components(self) -> int:
        """Number of connected components in the graph."""
        return nx.number_connected_components(self._graph)

    def _build_stamp_from_node(self, start_node: GraphNode) -> "MatchStamp":
        """Build a MatchStamp from a starting node.

        Uses BFS to find all connected nodes and categorize edges.

        Args:
            start_node: The (timeline_id, coordinate) to start from.

        Returns:
            MatchStamp containing all connected coordinates.
        """
        if start_node not in self._graph:
            return MatchStamp(
                coordinates={start_node[0]: start_node[1]},
                anchor_edges=[],
                inferred_edges=[],
            )

        # Find all nodes in the connected component
        component = nx.node_connected_component(self._graph, start_node)

        # Build coordinates dict
        coordinates: dict[str, float] = {}
        for node in component:
            timeline_id, coord = node
            # If timeline already exists, keep the first coordinate
            # (could be multiple nodes for same timeline in complex graphs)
            if timeline_id not in coordinates:
                coordinates[timeline_id] = coord

        # Categorize edges
        anchor_edges: list[tuple[str, str]] = []
        inferred_edges: list[tuple[str, str]] = []

        # Get subgraph for this component
        subgraph = self._graph.subgraph(component)
        for u, v, data in subgraph.edges(data=True):
            edge_pair = (u[0], v[0])
            # Avoid duplicates (edges are undirected)
            reverse_pair = (v[0], u[0])

            if data.get("explicit", True):
                if edge_pair not in anchor_edges and reverse_pair not in anchor_edges:
                    anchor_edges.append(edge_pair)
            else:
                if (
                    edge_pair not in inferred_edges
                    and reverse_pair not in inferred_edges
                ):
                    inferred_edges.append(edge_pair)

        return MatchStamp(
            coordinates=coordinates,
            anchor_edges=anchor_edges,
            inferred_edges=inferred_edges,
        )

    def filter(
        self,
        synchronous_only: bool = False,
        explicit_only: bool = False,
        include_timelines: set[str] | None = None,
        exclude_timelines: set[str] | None = None,
        include_domains: set[Domain] | None = None,
        include_units: set[TimeUnit] | None = None,
        *,
        timelines: dict[str, "Timeline"] | None = None,
    ) -> "MatchGraph":
        """Create filtered view of the graph.

        Args:
            synchronous_only: Include only synchronous edges.
            explicit_only: Include only explicit edges (no inferred).
            include_timelines: Only include these timeline IDs.
            exclude_timelines: Exclude these timeline IDs.
            include_domains: Only include timelines in these domains.
                Requires ``timelines`` parameter.
            include_units: Only include timelines with these units.
                Requires ``timelines`` parameter.
            timelines: Dict of timeline_id -> Timeline for resolving
                domain/unit filters.

        Returns:
            New MatchGraph with filtered edges/nodes.
        """
        # Start with a copy
        filtered = nx.Graph(self._graph)

        # Filter by timeline IDs and domain/unit
        nodes_to_remove = []
        for node in filtered.nodes():
            timeline_id = node[0]
            if not self._passes_filters(
                timeline_id,
                timelines=timelines,
                include_timelines=include_timelines,
                exclude_timelines=exclude_timelines,
                include_domains=include_domains,
                include_units=include_units,
            ):
                nodes_to_remove.append(node)
        filtered.remove_nodes_from(nodes_to_remove)

        # Filter edges by attributes
        if synchronous_only or explicit_only:
            edges_to_remove = []
            for u, v, data in filtered.edges(data=True):
                if synchronous_only and not data.get("synchronous", True):
                    edges_to_remove.append((u, v))
                elif explicit_only and not data.get("explicit", True):
                    edges_to_remove.append((u, v))
            filtered.remove_edges_from(edges_to_remove)

        # Remove isolated nodes (nodes with no edges after filtering)
        isolated = list(nx.isolates(filtered))
        filtered.remove_nodes_from(isolated)

        # Filter claims to match remaining edges
        remaining_claim_ids = set()
        for _, _, data in filtered.edges(data=True):
            if "claim_id" in data:
                remaining_claim_ids.add(data["claim_id"])

        # Keep non-synchronous claims that connect remaining timelines
        remaining_tl_ids = {node[0] for node in filtered.nodes()}
        filtered_claims = []
        for c in self._claims:
            if c.id in remaining_claim_ids:
                filtered_claims.append(c)
            elif (
                not c.is_synchronous
                and c.timeline_a_id in remaining_tl_ids
                and c.timeline_b_id in remaining_tl_ids
            ):
                filtered_claims.append(c)

        return MatchGraph._from_graph(filtered, filtered_claims)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Note: This serializes the claims, not the full graph.
        The graph can be rebuilt from claims.
        """
        return {
            "claims": [c.to_dict() for c in self._claims],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MatchGraph":
        """Deserialize from dictionary."""
        claims = [MatchClaim.from_dict(c) for c in data["claims"]]
        return cls(claims)

    def __repr__(self) -> str:
        return (
            f"MatchGraph(claims={len(self._claims)}, "
            f"nodes={self.n_nodes}, edges={self.n_edges})"
        )


# endregion
