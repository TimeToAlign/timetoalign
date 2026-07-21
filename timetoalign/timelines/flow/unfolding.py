"""Create unfolded timelines from computed flows."""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING, Any

from .flowmap import FlowMap

if TYPE_CHECKING:
    from timetoalign.core import TimeUnit

    from ..base import Timeline
    from ..types import SegmentLine
    from .controller import FlowControllerBase, ScoreFlowController
    from .sections import Flow


def compute_qb_sections(
    flow: Flow,
    controller: FlowControllerBase | ScoreFlowController,
) -> list[tuple[Fraction, Fraction]]:
    """Compute quarterbeat boundaries for each PlaythroughSection in a Flow.

    Uses the controller's MeasureUnit data to convert MC-based section
    ranges to QB-based coordinate ranges. This is the critical function that
    translates from MC-number space (integers 1, 2, 3, ...) to quarterbeat
    space (actual coordinate positions on the score timeline).

    Args:
        flow: A computed Flow with PlaythroughSections.
        controller: The ScoreFlowController that computed the flow (must have
            MeasureUnit data with ``duration_qb`` for each MC).

    Returns:
        List of ``(qb_start, qb_end)`` tuples, one per PlaythroughSection.
        Each tuple gives the start and end quarterbeat coordinates in the
        **folded** source timeline. The intervals are right-open: ``[qb_start, qb_end)``.

    Raises:
        ValueError: If controller lacks MeasureUnit data for a required MC.
        ValueError: If flow has no sections.

    Examples:
        >>> controller = ScoreFlowController(measure_data)
        >>> flow = controller.compute_flow(FlowMode.default)
        >>> qb_sections = compute_qb_sections(flow, controller)
        >>> # Each section gives QB boundaries in the folded score
        >>> for qb_start, qb_end in qb_sections:
        ...     print(f"[{qb_start}, {qb_end})")
    """
    if not flow.sections:
        raise ValueError("Flow has no sections")

    # Build MC -> QB start lookup from MeasureUnit data.
    # mc_to_qb_start[mc] = cumulative QB position where measure mc begins.
    mc_to_qb_start: dict[int, Fraction] = {}
    mc_to_duration: dict[int, Fraction] = {}
    max_mc = 0

    for unit in controller.iter_units():
        mc_to_duration[unit.mc] = unit.duration_qb
        max_mc = max(max_mc, unit.mc)

    # Compute cumulative QB positions by summing durations in MC order.
    # MCs are sorted by MC number (1-indexed, monotonically increasing in the folded score).
    sorted_mcs = sorted(mc_to_duration.keys())
    cumulative = Fraction(0)
    for mc in sorted_mcs:
        mc_to_qb_start[mc] = cumulative
        cumulative += mc_to_duration[mc]

    # The QB position just past the last MC (used when mc_end is beyond max_mc)
    total_folded_qb = cumulative

    qb_sections: list[tuple[Fraction, Fraction]] = []

    for sec in flow.sections:
        # QB start: the cumulative QB position where mc_start begins
        if sec.mc_start not in mc_to_qb_start:
            raise ValueError(
                f"No MeasureUnit data for MC {sec.mc_start}. "
                f"Available MCs: {sorted(mc_to_qb_start.keys())}"
            )
        qb_start = mc_to_qb_start[sec.mc_start]

        # QB end: mc_end is right-open (exclusive), so its QB start IS the section's QB end.
        # If mc_end is beyond the last MC, use the total folded QB length.
        if sec.mc_end in mc_to_qb_start:
            qb_end = mc_to_qb_start[sec.mc_end]
        elif sec.mc_end > max_mc:
            # mc_end is one past the last MC -> section extends to the very end
            qb_end = total_folded_qb
        else:
            raise ValueError(
                f"No MeasureUnit data for MC {sec.mc_end}. "
                f"Available MCs: {sorted(mc_to_qb_start.keys())}"
            )

        qb_sections.append((qb_start, qb_end))

    return qb_sections


# endregion

# region Create Unfolded Timeline


def create_unfolded_timeline(
    source_timeline: "Timeline",
    flow: Flow,
    flow_controller: FlowControllerBase | None = None,
    *,
    uid: str | None = None,
    target_unit: "TimeUnit | str | None" = None,
    include_children: bool = True,
    as_segment_line: bool = False,
) -> "Timeline":
    """Create an unfolded timeline from a folded source via structural slicing.

    Computes QB-space boundaries for each `PlaythroughSection` in the Flow,
    extracts slices from the source timeline at those boundaries, and
    concatenates the slices into a new `SegmentLine`.  This is the TTA
    manuscript's conceptual model: unfolding = assembling a new SegmentLine
    by selecting and concatenating contiguous portions of the folded source.

    The returned timeline has:

    - Correct QB-space coordinates (not MC-number space)
    - A reverse FlowMap attached (id="source") for folded ↔ unfolded conversion
    - A forward FlowMap attached (id="forward_{flow.id}")
    - Events structurally copied via `Timeline.get_slice()`, including
      truncation of interval events at section boundaries
    - Children recursively sliced (when *include_children* is True)

    Design decision: replaces the earlier FlowMap-based per-event
    coordinate remapping with structural slicing.  The previous
    approach operated in MC-number space and produced wrong coordinates
    for scores with non-uniform measure durations.

    Args:
        source_timeline: The folded source timeline.
        flow: The computed Flow (sequence of sections).
        flow_controller: The controller that computed the flow. Required for
            QB-space boundary computation. If ``None``, the function raises
            ``ValueError`` because no QB-space boundaries can be computed.
        uid: Optional identifier for the returned timeline.
        target_unit: Optional unit for the unfolded timeline. When given,
            ``Timeline.resolve_subclass(target_unit, number_type)`` selects
            the timeline type; otherwise ``type(source_timeline)`` is used.
        include_children: If True (default), child timelines are
            recursively sliced and included in each segment.
        as_segment_line: If True, return the `SegmentLine` directly
            (one segment per playthrough section).  If False (default),
            flatten into a plain timeline of the source's concrete class.

    Returns:
        New Timeline (or SegmentLine if *as_segment_line* is True) with:

        - Events structurally copied and reordered per flow
        - Reverse FlowMap attached (id="source")
        - Forward FlowMap attached (id="forward_{flow.id}")

    Raises:
        ValueError: If *flow_controller* is None and QB-space boundaries
            cannot be computed.

    Examples:
        >>> controller = ScoreFlowController(measure_data)
        >>> flow = controller.compute_flow(FlowMode.default)
        >>> unfolded = create_unfolded_timeline(source_tl, flow, controller)
        >>> type(unfolded).__name__  # preserves source type
        'ContinuousLogicalTimeline'
        >>> unfolded.get_flow_map("source")  # Reverse map to trace back
        FlowMap(default_inverse: 5 sections)

    See Also:
        `compute_qb_sections`: Computes QB boundaries from Flow + controller.
        `Timeline.get_slice`: Extracts a portion of a timeline.
        `SegmentLine`: Container for contiguous timeline segments.
    """
    from ..base import Timeline
    from ..types import SegmentLine

    # --- 1. Compute QB-space section boundaries ---
    if flow_controller is not None:
        qb_sections = compute_qb_sections(flow, flow_controller)
    else:
        raise ValueError(
            "flow_controller is required for QB-space unfolding. "
            "The legacy MC-number-space path has been removed."
        )

    # --- 2. Build the QB-space FlowMap ---
    forward_map = FlowMap.from_qb_sections(flow, qb_sections, id=flow.id)
    unfolded_length = forward_map.total_target_length

    # --- 3. Resolve the concrete class ---
    number_type = source_timeline.number_type
    unit = source_timeline.unit if target_unit is None else target_unit
    if target_unit is not None:
        timeline_cls = Timeline.resolve_subclass(unit, number_type)
    else:
        timeline_cls = type(source_timeline)

    # --- 4. Slice source at each section boundary and assemble SegmentLine ---
    segment_line = SegmentLine(
        segment_type=timeline_cls,
        length=0,
        unit=unit,
        number_type=number_type,
        uid=uid if as_segment_line else None,
        name=f"{source_timeline.name}_unfolded",
    )

    for i, (qb_start, qb_end) in enumerate(qb_sections):
        slice_tl = source_timeline.get_slice(
            qb_start,
            qb_end,
            truncate_events=True,
            include_children=include_children,
        )
        segment_line.append_segment(slice_tl, name=f"section_{i}")

    # --- 5. Build the result timeline ---
    if as_segment_line:
        result = segment_line
    else:
        # Flatten: create a plain timeline and copy all events from all segments
        result = timeline_cls(
            length=unfolded_length,
            unit=unit,
            number_type=number_type,
            uid=uid,
            name=f"{source_timeline.name}_unfolded",
        )
        _flatten_segment_line_onto(segment_line, result, include_children)

    # --- 6. Add FlowMaps ---
    reverse_map = forward_map.inverse()
    result.add_flow_map(reverse_map, id="source")
    result.add_flow_map(forward_map, id=f"forward_{flow.id}")

    return result


def _flatten_segment_line_onto(
    segment_line: "SegmentLine",
    target: "Timeline",
    include_children: bool = True,
) -> None:
    """Flatten a SegmentLine's events into a single target timeline.

    Iterates over each segment in order, reads its events, shifts coordinates
    by the segment's offset in the SegmentLine, and adds them to the target.

    Args:
        segment_line: The SegmentLine containing sliced segments.
        target: The flat target timeline to receive all events.
        include_children: If True, also flatten children from each segment.
    """
    all_shifted_events: list[dict[str, Any]] = []
    for seg_id in segment_line._segment_order:
        offset = segment_line._child_offsets[seg_id].value
        segment = segment_line._children[seg_id]

        # Copy parent-level events from this segment
        events = list(segment.get_events(include_children=False))
        if events:
            for event in events:
                new_event = dict(event)
                if event.get("temporal_type") == "instant":
                    coord = event["start"]["value"]
                    new_event["instant"] = type(coord)(coord) + offset
                    new_event.pop("start", None)
                    new_event.pop("end", None)
                    new_event.pop("duration", None)
                elif event.get("temporal_type") == "interval":
                    start_val = event["start"]["value"]
                    end_val = event["end"]["value"]
                    new_event["start"] = type(start_val)(start_val) + offset
                    new_event["end"] = type(end_val)(end_val) + offset
                    new_event["duration"] = new_event["end"] - new_event["start"]
                all_shifted_events.append(new_event)

        # Recursively flatten children from this segment
        if include_children:
            for child_id, child in segment._children.items():
                child_offset_in_seg = segment._child_offsets[child_id].value
                child_offset_in_target = float(child_offset_in_seg) + float(offset)
                # Recursively unfold: flatten child's events into a new child timeline
                child_copy = type(child)(
                    length=child.length.value,
                    unit=child.unit,
                    number_type=child.number_type,
                    name=child.name,
                )
                # Copy child's events directly (they're already in local coords)
                child_events = list(child.get_events(include_children=False))
                if child_events:
                    child_copy.add_events(child_events, allow_expansion=True)
                try:
                    target.add_child(
                        child_copy,
                        offset=child_offset_in_target,
                        allow_expansion=True,
                    )
                except (ValueError, TypeError):
                    # Child may already exist or conflict — skip silently
                    pass

    if all_shifted_events:
        target.add_events(all_shifted_events, allow_expansion=True)


# endregion
