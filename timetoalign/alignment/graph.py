"""MatchGraph and MatchStamp classes.

This module implements the mid-level graph structure for alignment:

- MatchStamp: Cross-group timestamp at a single coordinate
- MatchGraph: Graph of MatchClaims yielding MatchStamps

The hierarchy is:
    AlignmentAnchor -> MatchClaim -> MatchGraph -> MatchStamp -> MatchLine

MatchGraph uses networkx to:
1. Build a graph where nodes are (timeline_id, coordinate) tuples
2. Edges are AlignmentAnchors with explicit/synchronous attributes
3. Extend edges via Group membership (inferred edges)
4. Extract MatchStamps from connected components
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import networkx as nx

from timetoalign.alignment.anchors import AlignmentAnchor, MatchClaim
from timetoalign.core.enums import TimeUnit

if TYPE_CHECKING:
    from timetoalign.alignment.groups import TimelineGroup

module_logger = logging.getLogger(__name__)


# Type alias for graph nodes: (timeline_id, coordinate)
GraphNode = tuple[str, float]


# region MatchStamp


@dataclass
class MatchStamp:
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

    Examples:
        >>> stamp = MatchStamp(
        ...     coordinates={"score": 100.0, "audio": 45.5, "video": 1365.0},
        ...     anchor_edges=[("score", "audio")],
        ...     inferred_edges=[("audio", "video")],
        ... )
        >>> stamp.get_coordinate("audio")
        45.5
    """

    coordinates: dict[str, float] = field(default_factory=dict)
    anchor_edges: list[tuple[str, str]] = field(default_factory=list)
    inferred_edges: list[tuple[str, str]] = field(default_factory=list)

    @property
    def timeline_ids(self) -> list[str]:
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

    def get_coordinate(self, timeline_id: str) -> float | None:
        """Get coordinate for a specific timeline.

        Args:
            timeline_id: The timeline to get coordinate for.

        Returns:
            The coordinate, or None if timeline not in this stamp.
        """
        return self.coordinates.get(timeline_id)

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
        return {
            tl_id: coord
            for tl_id, coord in self.coordinates.items()
            if tl_id in group.timelines
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
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "coordinates": self.coordinates,
            "anchor_edges": self.anchor_edges,
            "inferred_edges": self.inferred_edges,
        }

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


# endregion


# region MatchGraph


class MatchGraph:
    """A graph of MatchClaims connecting events across timelines/groups.

    The MatchGraph is the core data structure for alignment. It builds a
    networkx graph where:
    - Nodes: (timeline_id, coordinate) tuples
    - Edges: AlignmentAnchors with attributes (explicit, synchronous)

    A MatchGraph produces 1-2 MatchStamps:
    - 1 MatchStamp for instant matches
    - 2 MatchStamps for interval matches (start and end)

    The graph differentiates between:
    - Explicit anchors: Directly claimed by user/algorithm
    - Inferred edges: Extended via C-Maps or Group membership

    Attributes:
        claims: List of MatchClaims that built this graph.

    Examples:
        >>> # Build graph from claims
        >>> graph = MatchGraph(claims=[claim1, claim2])

        >>> # Extend via group membership
        >>> extended = graph.extend_to_groups(bundle)

        >>> # Get synchronized timestamps
        >>> start_stamp, end_stamp = graph.get_match_stamps()
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
        """List of MatchClaims in this graph."""
        return self._claims

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

    @property
    def timeline_ids(self) -> set[str]:
        """Set of all timeline IDs in the graph."""
        return {node[0] for node in self._graph.nodes()}

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
    ) -> "MatchGraph":
        """Extend anchors to full group timestamps.

        For each coordinate in the graph, if it belongs to a Group,
        add inferred edges to all other timelines in that Group.

        Args:
            groups: Dict of group_id -> TimelineGroup.
            timeline_to_group: Dict of timeline_id -> group_id.
            include_inferred: Whether to add inferred edges.

        Returns:
            New MatchGraph with extended edges (or self if not extending).
        """
        if not include_inferred:
            return self

        # Create a copy of the graph
        extended = nx.Graph(self._graph)

        for node in list(self._graph.nodes()):
            timeline_id, coord = node

            # Check if timeline belongs to a group
            group_id = timeline_to_group.get(timeline_id)
            if not group_id:
                continue

            group = groups.get(group_id)
            if not group:
                continue

            # Add inferred edges to all other timelines in group
            for other_tl_id in group.timeline_ids:
                if other_tl_id == timeline_id:
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

                # Add inferred edge if not already connected
                if not extended.has_edge(node, other_node):
                    extended.add_edge(
                        node,
                        other_node,
                        explicit=False,
                        synchronous=True,  # Within-group is always synchronous
                        inferred_via="group",
                        group_id=group_id,
                    )

        return MatchGraph._from_graph(extended, self._claims)

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
            claims: Original claims (for reference).

        Returns:
            New MatchGraph wrapping the graph.
        """
        instance = cls.__new__(cls)
        instance._claims = claims
        instance._graph = graph
        instance._logger = module_logger.getChild("MatchGraph")
        return instance

    def get_match_stamps(self) -> tuple["MatchStamp", "MatchStamp | None"]:
        """Extract MatchStamps from the graph.

        Returns:
            (start_stamp, end_stamp) - end_stamp is None for instant matches.

        Note:
            For a graph built from multiple interval claims, this returns
            stamps for the first synchronous claim's coordinates. Use
            get_all_stamps() for all unique timestamps.
        """
        if not self._claims:
            return MatchStamp(), None

        # Find the first synchronous claim with anchors
        claim = None
        for c in self._claims:
            if c.is_synchronous and c.start_anchor is not None:
                claim = c
                break

        if claim is None:
            return MatchStamp(), None

        # Build start stamp
        start_node: GraphNode = (
            claim.start_anchor.timeline_a_id,
            claim.start_anchor.coordinate_a,
        )
        start_stamp = self._build_stamp_from_node(start_node)

        # Build end stamp if interval
        end_stamp = None
        if claim.end_anchor:
            end_node: GraphNode = (
                claim.end_anchor.timeline_a_id,
                claim.end_anchor.coordinate_a,
            )
            end_stamp = self._build_stamp_from_node(end_node)

        return start_stamp, end_stamp

    def get_all_stamps(self) -> list["MatchStamp"]:
        """Get all unique MatchStamps from the graph.

        For each connected component in the graph, creates a MatchStamp.

        Returns:
            List of MatchStamps, one per connected component.
        """
        stamps = []
        for component in nx.connected_components(self._graph):
            # Use any node in the component to build stamp
            node = next(iter(component))
            stamp = self._build_stamp_from_node(node)
            stamps.append(stamp)
        return stamps

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
        include_units: set[TimeUnit] | None = None,
        exclude_units: set[TimeUnit] | None = None,
        include_timelines: set[str] | None = None,
        exclude_timelines: set[str] | None = None,
    ) -> "MatchGraph":
        """Create filtered view of the graph.

        Args:
            synchronous_only: Include only synchronous edges.
            explicit_only: Include only explicit edges (no inferred).
            include_units: Only include timelines with these units.
                (Requires timeline lookup - not implemented yet)
            exclude_units: Exclude timelines with these units.
                (Requires timeline lookup - not implemented yet)
            include_timelines: Only include these timeline IDs.
            exclude_timelines: Exclude these timeline IDs.

        Returns:
            New MatchGraph with filtered edges/nodes.
        """
        # Start with a copy
        filtered = nx.Graph(self._graph)

        # Filter by timeline IDs
        if include_timelines is not None or exclude_timelines is not None:
            nodes_to_remove = []
            for node in filtered.nodes():
                timeline_id = node[0]
                if (
                    include_timelines is not None
                    and timeline_id not in include_timelines
                ):
                    nodes_to_remove.append(node)
                elif exclude_timelines is not None and timeline_id in exclude_timelines:
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

        filtered_claims = [c for c in self._claims if c.id in remaining_claim_ids]

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
