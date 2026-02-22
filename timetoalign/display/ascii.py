"""Pure ASCII timeline rendering - zero external dependencies.

This module provides ASCII/Unicode visualization for TimeToAlign! objects:
- Timelines with nested children (one child per row)
- TimelineGroups with boxed layout
- AlignmentBundles with multiple groups
- ScoreFlowControllers with flow control markers
- Flows with playthrough section sequences
- Flow comparisons (side-by-side diffs)

Design principles:
- Six distinct characters for the six timeline types
- One child per row with positioned bar showing extent on parent scale
- Truncation for many children (first N, ellipsis, last N)
- Unified rendering inside/outside groups
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from timetoalign.alignment import AlignmentBundle, TimelineGroup
    from timetoalign.timelines import Timeline
    from timetoalign.timelines.flow import Flow, ScoreFlowController

# region Character Sets

# Timeline type characters (6 types)
# Keys are (NumberType.name, Domain.name) - note lowercase enum names
# NumberType: int (discrete), float (continuous), fraction (rational)
# Domain: graphical, physical, logical
TIMELINE_CHARS: dict[tuple[str, str], str] = {
    ("float", "graphical"): "=",
    ("int", "graphical"): ":",
    ("float", "physical"): "~",
    ("int", "physical"): "\u22c5",  # U+22C5 middle dot
    ("float", "logical"): "_",
    ("int", "logical"): ",",
    # fraction type uses same as float (continuous)
    ("fraction", "graphical"): "=",
    ("fraction", "physical"): "~",
    ("fraction", "logical"): "_",
}

# ASCII fallback for environments without Unicode
TIMELINE_CHARS_ASCII: dict[tuple[str, str], str] = {
    ("float", "graphical"): "=",
    ("int", "graphical"): ":",
    ("float", "physical"): "~",
    ("int", "physical"): ".",  # fallback for middle dot
    ("float", "logical"): "_",
    ("int", "logical"): ",",
    # fraction type uses same as float (continuous)
    ("fraction", "graphical"): "=",
    ("fraction", "physical"): "~",
    ("fraction", "logical"): "_",
}

# Tree drawing characters
TREE_CHARS: dict[str, str] = {
    "branch": "\u251c",  # ├
    "last": "\u2514",  # └
    "vertical": "\u2502",  # │
    "horizontal": "\u2500",  # ─
}

TREE_CHARS_ASCII: dict[str, str] = {
    "branch": "+",
    "last": "+",
    "vertical": "|",
    "horizontal": "-",
}

# Box drawing characters
BOX_CHARS: dict[str, str] = {
    "top_left": "\u250c",  # ┌
    "top_right": "\u2510",  # ┐
    "bottom_left": "\u2514",  # └
    "bottom_right": "\u2518",  # ┘
    "horizontal": "\u2500",  # ─
    "vertical": "\u2502",  # │
}

BOX_CHARS_ASCII: dict[str, str] = {
    "top_left": "+",
    "top_right": "+",
    "bottom_left": "+",
    "bottom_right": "+",
    "horizontal": "-",
    "vertical": "|",
}

# Region display characters
REGION_CHARS: dict[str, str] = {
    "bar": "\u2550",  # ═  Region span fill (double line)
    "prefix": "\u2504",  # ┄  Row prefix (distinguishes from children's ├─)
    "left": "\u2590",  # ▐  Left boundary marker
    "right": "\u258c",  # ▌  Right boundary marker
}

REGION_CHARS_ASCII: dict[str, str] = {
    "bar": "=",
    "prefix": "~",
    "left": "[",
    "right": "]",
}

# Flow control display characters (BMP-safe — avoids SMP musical symbols)
FLOW_CHARS: dict[str, str] = {
    "repeat_start": "\u2551:",  # ║:
    "repeat_end": ":\u2551",  # :║
    "segno": "\u00a7",  # §  U+00A7 SECTION SIGN (widely supported)
    "coda": "\u2295",  # ⊕  U+2295 CIRCLED PLUS (BMP, well-supported)
    "section_break": "\u2551",  # ║  U+2551 BOX DRAWINGS DOUBLE VERTICAL
    "arrow": "\u2192",  # →  U+2192 RIGHTWARDS ARROW
    "match": "=",
    "mismatch": "\u2260",  # ≠  U+2260 NOT EQUAL TO
    "volta_corner": "\u250c",  # ┌  U+250C BOX DRAWINGS LIGHT DOWN AND RIGHT
    "volta_top": "\u2500",  # ─  U+2500 BOX DRAWINGS LIGHT HORIZONTAL
    "volta_end": "\u2510",  # ┐  U+2510 BOX DRAWINGS LIGHT DOWN AND LEFT
}

FLOW_CHARS_ASCII: dict[str, str] = {
    "repeat_start": "|:",
    "repeat_end": ":|",
    "segno": "S",
    "coda": "@",
    "section_break": "||",
    "arrow": "->",
    "match": "=",
    "mismatch": "!=",
    "volta_corner": "+",
    "volta_top": "-",
    "volta_end": "+",
}

# endregion

# region Configuration Defaults

DEFAULT_WIDTH: int = 70
DEFAULT_MAX_CHILDREN: int = 6
DEFAULT_NAME_WIDTH: int = 12

# endregion

# region Helper Functions


def _format_coordinate(value: float) -> str:
    """Format a coordinate value for display.

    Args:
        value: The coordinate value.

    Returns:
        Formatted string (integer if whole number, else 1 decimal).
    """
    if value == int(value):
        return str(int(value))
    return f"{value:.1f}"


def _elide_name(name: str, max_width: int) -> str:
    """Elide a name if it exceeds max width.

    Args:
        name: The name to potentially elide.
        max_width: Maximum allowed width.

    Returns:
        Original name or elided version with '...' suffix.
    """
    if len(name) <= max_width:
        return name
    if max_width <= 3:
        return name[:max_width]
    return name[: max_width - 3] + "..."


def _get_timeline_char(timeline: "Timeline", use_unicode: bool = True) -> str:
    """Get the display character for a timeline type.

    Args:
        timeline: The timeline to get character for.
        use_unicode: Whether to use Unicode characters.

    Returns:
        Single character representing the timeline type.
    """
    chars = TIMELINE_CHARS if use_unicode else TIMELINE_CHARS_ASCII
    key = (timeline.number_type.name, timeline.domain.name)
    return chars.get(key, "?")


def _get_children_to_display(
    children: list[tuple[float, Any]],
    max_children: int,
) -> tuple[list[tuple[float, Any]], int, list[tuple[float, Any]]]:
    """Determine which children to display with truncation.

    Args:
        children: List of (offset, child) tuples, sorted by offset.
        max_children: Maximum to display.

    Returns:
        Tuple of (first_children, omitted_count, last_children).
        If no truncation needed, omitted_count is 0 and last_children is empty.
    """
    if len(children) <= max_children:
        return children, 0, []

    # Show first half, last half (adjusted for odd numbers)
    first_count = (max_children + 1) // 2
    last_count = max_children - first_count

    first = children[:first_count]
    last = children[-last_count:] if last_count > 0 else []
    omitted = len(children) - first_count - last_count

    return first, omitted, last


def _build_child_row(
    child_offset: float,
    child_length: float,
    child_name: str,
    child_char: str,
    parent_length: float,
    bar_width: int,
    name_width: int,
    coord_width: int,
    is_last: bool,
    tree_chars: dict[str, str],
) -> str:
    """Build a single child row with positioned bar.

    Args:
        child_offset: Where child starts on parent scale.
        child_length: Length of the child.
        child_name: Display name for the child.
        child_char: Timeline character for child's type.
        parent_length: Total length of parent timeline.
        bar_width: Width of the bar area in characters.
        name_width: Max width for child name.
        coord_width: Width for coordinate columns.
        is_last: True if this is the last child (use └ instead of ├).
        tree_chars: Tree drawing character set.

    Returns:
        Formatted row string.
    """
    # Elide name if too long
    display_name = _elide_name(child_name, name_width)

    # Calculate bar position and width
    if parent_length > 0:
        start_pos = int((child_offset / parent_length) * bar_width)
        end_pos = int(((child_offset + child_length) / parent_length) * bar_width)
    else:
        start_pos = 0
        end_pos = bar_width

    bar_len = max(1, end_pos - start_pos)

    # Build the bar with proper positioning
    bar_area = [" "] * bar_width
    for i in range(bar_len):
        if start_pos + i < bar_width:
            bar_area[start_pos + i] = child_char

    # Format coordinates
    entry_coord = _format_coordinate(child_offset)
    exit_coord = _format_coordinate(child_offset + child_length)

    # Choose tree character
    prefix = tree_chars["last"] if is_last else tree_chars["branch"]

    return (
        f"  {prefix}{tree_chars['horizontal']} "
        f"{display_name:<{name_width}} "
        f"{entry_coord:>{coord_width}} "
        f"{''.join(bar_area)} "
        f"{exit_coord}"
    )


def _build_region_row(
    region_start: float,
    region_end: float,
    region_name: str,
    parent_length: float,
    bar_width: int,
    name_width: int,
    coord_width: int,
    region_chars: dict[str, str],
) -> str:
    """Build a single region row with positioned span.

    Similar to _build_child_row() but uses region-specific characters
    and does not need is_last (no tree structure for regions).

    Args:
        region_start: Start coordinate of the region.
        region_end: End coordinate of the region.
        region_name: Display name for the region.
        parent_length: Total length of parent timeline.
        bar_width: Width of the bar area in characters.
        name_width: Max width for region name.
        coord_width: Width for coordinate columns.
        region_chars: Region character set (REGION_CHARS or REGION_CHARS_ASCII).

    Returns:
        Formatted row string.
    """
    display_name = _elide_name(region_name, name_width)

    # Calculate bar position and width
    if parent_length > 0:
        start_pos = int((region_start / parent_length) * bar_width)
        end_pos = int((region_end / parent_length) * bar_width)
    else:
        start_pos = 0
        end_pos = bar_width

    bar_len = max(1, end_pos - start_pos)

    # Build the bar with boundary markers and fill
    bar_area = [" "] * bar_width
    for i in range(bar_len):
        pos = start_pos + i
        if pos < bar_width:
            if i == 0:
                bar_area[pos] = region_chars["left"]
            elif i == bar_len - 1:
                bar_area[pos] = region_chars["right"]
            else:
                bar_area[pos] = region_chars["bar"]

    # Format coordinates
    entry_coord = _format_coordinate(region_start)
    exit_coord = _format_coordinate(region_end)

    return (
        f"  {region_chars['prefix']} "
        f"{display_name:<{name_width}} "
        f"{entry_coord:>{coord_width}} "
        f"{''.join(bar_area)} "
        f"{exit_coord}"
    )


# endregion

# region Timeline Diagram


def timeline_diagram(
    timeline: "Timeline",
    width: int = DEFAULT_WIDTH,
    show_children: bool = True,
    max_children: int = DEFAULT_MAX_CHILDREN,
    indent: int = 0,
    unicode: bool = True,
    parent_id: str | None = None,
    show: set[str] | None = None,
) -> str:
    """Generate ASCII diagram for a timeline.

    Args:
        timeline: The Timeline to render.
        width: Total width of the diagram in characters.
        show_children: Whether to show child timelines (one per row).
        max_children: Maximum children to show before truncating.
        indent: Left indentation (for nested rendering).
        unicode: Use Unicode characters (True) or ASCII fallback (False).
        parent_id: If set, indicates this is a child of parent_id (for annotation).
        show: Optional set controlling which elements appear. Supported values:
            ``"children"`` (child timelines) and ``"regions"`` (named regions).
            When ``None``, behaviour is exactly as before (children shown if
            ``show_children=True``, no regions).  The ``show_children`` parameter
            takes precedence for backwards compatibility.

    Returns:
        Multi-line string with ASCII diagram.

    Examples:
        >>> print(timeline_diagram(my_timeline))
        DiscreteGraphicalTimeline[dgt1:1] (11 events, 5 children)
        0 :::::::::::::::::::::::::::::::::::::::::::::: 4835 pixels
          ├─ system_1     0   :::::::                        967
          ├─ system_2   967          ::::::::               1934
          └─ ...
    """
    # chars = TIMELINE_CHARS if unicode else TIMELINE_CHARS_ASCII
    tree = TREE_CHARS if unicode else TREE_CHARS_ASCII

    # Resolve show set: None means legacy behaviour
    _show_children = show_children  # backwards compat takes precedence
    _show_regions = False
    if show is not None:
        if "children" not in show:
            _show_children = False
        if "regions" in show:
            _show_regions = True
    # show_children=False overrides show={"children"}
    if not show_children:
        _show_children = False

    lines: list[str] = []
    prefix = " " * indent

    # 1. Header line
    header = f"{timeline.class_name}[{timeline.id}]"
    if parent_id:
        header += f" (child of {parent_id})"

    details: list[str] = []
    if timeline.n_events > 0:
        details.append(f"{timeline.n_events} events")
    if timeline.n_children > 0:
        details.append(f"{timeline.n_children} children")
    if timeline.n_regions > 0:
        details.append(f"{timeline.n_regions} regions")
    if details:
        header += f" ({', '.join(details)})"
    lines.append(prefix + header)

    # 2. Calculate dimensions
    length_value = float(timeline.length.value)
    end_label = _format_coordinate(length_value)
    unit_label = str(timeline.unit)

    # Coordinate width based on largest coordinate
    coord_width = max(len(end_label), 5)

    # Calculate left margin to align with child bars
    # Child structure: "  {tree}─ {name:<name_width} {coord:>coord_width} {bar}"
    # For parent, we use empty tree prefix space and show unit label after bar
    # Left margin: 2 (indent) + 3 (tree placeholder) + name_width + 1 + coord_width + 1
    name_width = DEFAULT_NAME_WIDTH
    left_margin = 2 + 3 + name_width + 1 + coord_width + 1

    # Bar width: total - indent - left_margin - " end unit" - margins
    right_label_len = len(end_label) + 1 + len(unit_label)
    bar_width = width - indent - left_margin - right_label_len - 1
    bar_width = max(bar_width, 20)

    # 3. Get timeline character and build parent bar
    line_char = _get_timeline_char(timeline, unicode)
    bar = line_char * bar_width

    # 4. Format parent bar line (aligned with child bars)
    # Structure matches child: padding + "0" coord + bar + end coord + unit
    padding = " " * (left_margin - coord_width - 1)  # Space for tree/name area
    bar_line = f"{prefix}{padding}{'0':>{coord_width}} {bar} {end_label} {unit_label}"
    lines.append(bar_line)

    # 5. Render children (one per row)
    if _show_children and timeline.n_children > 0:
        # Collect and sort children by offset
        child_info: list[tuple[float, Any]] = []
        for child_id, child in timeline._children.items():
            offset = timeline._child_offsets[child_id]
            child_info.append((float(offset.value), child))
        child_info.sort(key=lambda x: x[0])

        # Apply truncation
        first, omitted, last = _get_children_to_display(child_info, max_children)

        parent_length = length_value
        total_to_display = len(first) + len(last)
        display_index = 0

        # Render first group
        for i, (offset, child) in enumerate(first):
            is_last_overall = (display_index == total_to_display - 1) and omitted == 0
            child_char = _get_timeline_char(child, unicode)

            row = _build_child_row(
                child_offset=offset,
                child_length=float(child.length.value),
                child_name=child.name,
                child_char=child_char,
                parent_length=parent_length,
                bar_width=bar_width,
                name_width=DEFAULT_NAME_WIDTH,
                coord_width=coord_width,
                is_last=is_last_overall,
                tree_chars=tree,
            )
            lines.append(prefix + row)
            display_index += 1

        # Render ellipsis if truncated
        if omitted > 0:
            ellipsis = f"  {tree['vertical']}  ... ({omitted} more children)"
            lines.append(prefix + ellipsis)

        # Render last group
        for i, (offset, child) in enumerate(last):
            is_last_overall = i == len(last) - 1
            child_char = _get_timeline_char(child, unicode)

            row = _build_child_row(
                child_offset=offset,
                child_length=float(child.length.value),
                child_name=child.name,
                child_char=child_char,
                parent_length=parent_length,
                bar_width=bar_width,
                name_width=DEFAULT_NAME_WIDTH,
                coord_width=coord_width,
                is_last=is_last_overall,
                tree_chars=tree,
            )
            lines.append(prefix + row)

    # 6. Render regions (below children)
    if _show_regions and timeline.n_regions > 0:
        rgn_chars = REGION_CHARS if unicode else REGION_CHARS_ASCII
        # Collect and sort regions by start coordinate
        region_info: list[tuple[float, float, str]] = []
        for region in timeline.iter_regions():
            region_info.append(
                (float(region.start.value), float(region.end.value), region.name)
            )
        region_info.sort(key=lambda x: x[0])

        parent_length = length_value
        for r_start, r_end, r_name in region_info:
            row = _build_region_row(
                region_start=r_start,
                region_end=r_end,
                region_name=r_name,
                parent_length=parent_length,
                bar_width=bar_width,
                name_width=DEFAULT_NAME_WIDTH,
                coord_width=coord_width,
                region_chars=rgn_chars,
            )
            lines.append(prefix + row)

    return "\n".join(lines)


# endregion

# region Group Diagram


def group_diagram(
    group: "TimelineGroup",
    width: int = DEFAULT_WIDTH,
    show_children: bool = True,
    max_children: int = DEFAULT_MAX_CHILDREN,
    unicode: bool = True,
) -> str:
    """Generate ASCII diagram for a TimelineGroup.

    Args:
        group: The TimelineGroup to render.
        width: Total width of the diagram in characters.
        show_children: Whether to expand child timelines.
        max_children: Maximum children per timeline.
        unicode: Use Unicode characters (True) or ASCII fallback (False).

    Returns:
        Multi-line string with ASCII diagram.

    Examples:
        >>> print(group_diagram(my_group))
        TimelineGroup[my_group] (2 timelines, 2 timestamps)
        ┌────────────────────────────────────────────────────────────┐
        │ DiscreteGraphicalTimeline[dgt1:1] (11 events, 5 children)  │
        │ 0 ::::::::::::::::::::::::::::::::::::::::: 4835 pixels    │
        │   ├─ system_1     0   :::::::                    967       │
        │   └─ ...                                                   │
        │                                                            │
        │ ContinuousPhysicalTimeline[audio:1] (0 events)             │
        │ 0 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ 150.0 seconds  │
        └────────────────────────────────────────────────────────────┘
        Timestamps: 2
    """
    box = BOX_CHARS if unicode else BOX_CHARS_ASCII

    lines: list[str] = []

    # Header
    lines.append(
        f"TimelineGroup[{group.id}] "
        f"({group.n_timelines} timelines, {group.n_timestamps} timestamps)"
    )

    # Collect content lines for all timelines
    content_lines: list[str] = []
    timeline_list = list(group)

    for idx, tl in enumerate(timeline_list):
        # Render each timeline normally (with reduced width for box borders)
        tl_diagram = timeline_diagram(
            tl,
            width=width - 4,  # Account for "│ " prefix and " │" suffix
            show_children=show_children,
            max_children=max_children,
            unicode=unicode,
        )
        for line in tl_diagram.split("\n"):
            content_lines.append(line)

        # Add blank line between timelines (except after last)
        if idx < len(timeline_list) - 1:
            content_lines.append("")

    # Calculate box width based on content
    if content_lines:
        max_content_width = max(len(line) for line in content_lines)
    else:
        max_content_width = width - 4

    inner_width = max(max_content_width, 20)
    box_width = inner_width + 4  # "│ " + content + " │"

    # Build box
    lines.append(
        box["top_left"] + box["horizontal"] * (box_width - 2) + box["top_right"]
    )

    for line in content_lines:
        padded = line.ljust(inner_width)
        lines.append(f"{box['vertical']} {padded} {box['vertical']}")

    lines.append(
        box["bottom_left"] + box["horizontal"] * (box_width - 2) + box["bottom_right"]
    )

    # Footer
    lines.append(f"Timestamps: {group.n_timestamps}")

    return "\n".join(lines)


# endregion

# region Bundle Diagram


def bundle_diagram(
    bundle: "AlignmentBundle",
    width: int = 80,
    show_children: bool = True,
    max_children: int = DEFAULT_MAX_CHILDREN,
    unicode: bool = True,
) -> str:
    """Generate ASCII diagram for an AlignmentBundle.

    Args:
        bundle: The AlignmentBundle to render.
        width: Total width of the diagram in characters.
        show_children: Whether to expand child timelines.
        max_children: Maximum children per timeline.
        unicode: Use Unicode characters (True) or ASCII fallback (False).

    Returns:
        Multi-line string with ASCII diagram.

    Examples:
        >>> print(bundle_diagram(my_bundle))
        AlignmentBundle[thoresen_alignment]

          TimelineGroup[dgt1_group] (2 timelines, 2 timestamps)
          ┌──────────────────────────────────────────────────────┐
          │ DiscreteGraphicalTimeline[dgt1:1] (11 events)        │
          │ 0 ::::::::::::::::::::::::::::::::::: 4835 pixels    │
          └──────────────────────────────────────────────────────┘
          Timestamps: 2

          MatchClaims: 5 segment-to-segment
    """
    lines: list[str] = []

    # Header
    lines.append(f"AlignmentBundle[{bundle.id}]")
    lines.append("")

    # Render each group with indentation
    for group in bundle.groups.values():
        group_str = group_diagram(
            group,
            width=width - 2,  # Account for indentation
            show_children=show_children,
            max_children=max_children,
            unicode=unicode,
        )
        for line in group_str.split("\n"):
            lines.append("  " + line)
        lines.append("")

    # Match claims summary
    n_matches = len(bundle.matches) if hasattr(bundle, "matches") else 0
    if n_matches > 0:
        lines.append(f"  MatchClaims: {n_matches}")
    else:
        lines.append("  MatchClaims: 0")

    return "\n".join(lines)


# endregion

# region Flow Control Diagram


def flow_control_diagram(
    controller: "ScoreFlowController",
    width: int = DEFAULT_WIDTH,
    unicode: bool = True,
    show_graph: bool = True,
    show_legend: bool = True,
    mode: str = "auto",
) -> str:
    """Generate ASCII diagram for a ScoreFlowController.

    Shows the folded score map with atomic sections and flow control markers.

    Three rendering modes are available:

    - ``"full"``: One column per MC — detailed but wide. Best for small
      scores (< ~20 MCs). Shows repeat markers and volta brackets
      aligned to individual MC positions.
    - ``"sections"``: One column per AtomicSection — compact overview.
      Each section shows its ID centered over its MC range. Flow control
      markers attach to sections. Works well for any size score.
    - ``"table"``: Vertical table listing each section on its own row
      with ID, MC range, MC count, flow events, and transitions.
      Most compact; no spatial layout.
    - ``"auto"`` (default): Chooses ``"full"`` if all MCs fit within
      *width*; otherwise ``"sections"``.

    Args:
        controller: The ScoreFlowController to render.
        width: Total width of the diagram in characters.
        unicode: Use Unicode characters (True) or ASCII fallback (False).
        show_graph: Whether to show section transition graph.
        show_legend: Whether to show flow control event legend.
        mode: Rendering mode — ``"auto"``, ``"full"``, ``"sections"``,
            or ``"table"``.

    Returns:
        Multi-line string with ASCII diagram.
    """
    fc = FLOW_CHARS if unicode else FLOW_CHARS_ASCII

    units = list(controller.iter_units())
    sections = controller.get_sections()  # AtomicSections

    # Count flow control events
    n_flow_events = sum(
        1 for u in units if u.flow_control_types or u.start_repeat or u.end_repeat
    )

    n_mcs = len(units)

    # Resolve "auto" mode
    if mode == "auto":
        # 4 chars per MC + 3 chars prefix — if it fits in width, use full
        if n_mcs * 4 + 3 <= width:
            mode = "full"
        else:
            mode = "sections"

    # Header (shared)
    lines: list[str] = []
    lines.append(
        f"ScoreFlowController "
        f"({n_mcs} MCs, {len(sections)} atomic sections, "
        f"{n_flow_events} flow events)"
    )

    # Dispatch to rendering mode
    if mode == "full":
        _render_full_ruler(lines, units, sections, width, fc, unicode)
    elif mode == "sections":
        _render_sections_ruler(lines, units, sections, width, fc, unicode)
    elif mode == "table":
        _render_table(lines, units, sections, fc)
    else:
        raise ValueError(f"Unknown mode: {mode!r} (expected auto/full/sections/table)")

    # Legend (shared across modes)
    if show_legend:
        _render_legend(lines, units, sections, fc)

    # Section transition graph (shared across modes)
    if show_graph and sections:
        _render_graph(lines, sections, fc)

    return "\n".join(lines)


def _render_full_ruler(
    lines: list[str],
    units: list[Any],
    sections: list[Any],
    width: int,
    fc: dict[str, str],
    unicode: bool,
) -> None:
    """Render per-MC ruler (original detailed mode for small scores)."""
    n_mcs = len(units)
    if n_mcs == 0:
        return

    mc_numbers = [u.mc for u in units]
    col_width = max(4, (width - 6) // n_mcs)
    total_ruler_width = col_width * n_mcs

    # MC ruler row
    ruler_parts: list[str] = ["MC "]
    for mc in mc_numbers:
        ruler_parts.append(f"{mc:>{col_width}}")
    lines.append("".join(ruler_parts))

    # Build MC -> column position lookup
    mc_to_col: dict[int, int] = {}
    for idx, mc in enumerate(mc_numbers):
        mc_to_col[mc] = 3 + idx * col_width

    # Section spans row
    section_row = [" "] * (3 + total_ruler_width)
    tree = TREE_CHARS if unicode else TREE_CHARS_ASCII
    for sec in sections:
        start_idx = (
            mc_numbers.index(sec.mc_start) if sec.mc_start in mc_numbers else None
        )
        end_mc = sec.mc_end - 1
        end_idx = mc_numbers.index(end_mc) if end_mc in mc_numbers else None

        if start_idx is not None and end_idx is not None:
            col_start = 3 + start_idx * col_width
            col_end = 3 + (end_idx + 1) * col_width - 1

            if start_idx == end_idx:
                mid = col_start + col_width // 2
                if mid < len(section_row):
                    section_row[mid] = sec.id[0]
            else:
                h = tree["horizontal"]
                if col_start < len(section_row):
                    section_row[col_start] = tree["branch"]
                if col_end < len(section_row):
                    section_row[col_end] = "\u2524" if unicode else "|"
                span = col_end - col_start - 1
                if span > 0:
                    id_str = sec.id
                    if len(id_str) > span:
                        id_str = id_str[:span]
                    pad_left = (span - len(id_str)) // 2
                    pad_right = span - len(id_str) - pad_left
                    fill = h * pad_left + id_str + h * pad_right
                    for ci, ch in enumerate(fill):
                        pos = col_start + 1 + ci
                        if pos < len(section_row):
                            section_row[pos] = ch

    lines.append("".join(section_row).rstrip())

    # Flow control markers row (repeats)
    fc_row = [" "] * (3 + total_ruler_width)
    for unit in units:
        col = mc_to_col.get(unit.mc, 0)
        if unit.start_repeat:
            marker = fc["repeat_start"]
            for ci, ch in enumerate(marker):
                if col + ci < len(fc_row):
                    fc_row[col + ci] = ch
        if unit.end_repeat:
            marker = fc["repeat_end"]
            start_pos = col + col_width - len(marker)
            for ci, ch in enumerate(marker):
                if start_pos + ci < len(fc_row) and start_pos + ci >= 0:
                    fc_row[start_pos + ci] = ch

    fc_str = "".join(fc_row).rstrip()
    if fc_str.strip():
        lines.append(fc_str)

    # Volta brackets row
    volta_row = [" "] * (3 + total_ruler_width)
    has_volta = False
    volta_units = [(u, mc_to_col.get(u.mc, 0)) for u in units if u.volta is not None]
    for vi, (unit, col) in enumerate(volta_units):
        has_volta = True
        corner = fc["volta_corner"]
        top = fc["volta_top"]
        num_str = str(unit.volta)
        bracket = corner + num_str
        if vi > 0:
            _prev_unit, prev_col = volta_units[vi - 1]
            end_char = fc["volta_end"]
            close_pos = col - 1
            if close_pos > prev_col and close_pos < len(volta_row):
                volta_row[close_pos] = end_char
        for ci, ch in enumerate(bracket):
            if col + ci < len(volta_row):
                volta_row[col + ci] = ch
        for ci in range(len(bracket), col_width - 1):
            if col + ci < len(volta_row):
                volta_row[col + ci] = top

    if has_volta:
        lines.append("".join(volta_row).rstrip())

    # Jump markers row
    jump_row = [" "] * (3 + total_ruler_width)
    has_jumps = False
    for unit in units:
        col = mc_to_col.get(unit.mc, 0)
        marker = _get_jump_marker(unit, sections, fc)
        if marker:
            has_jumps = True
            for ci, ch in enumerate(marker):
                if col + ci < len(jump_row):
                    jump_row[col + ci] = ch

    if has_jumps:
        lines.append("".join(jump_row).rstrip())


def _render_sections_ruler(
    lines: list[str],
    units: list[Any],
    sections: list[Any],
    width: int,
    fc: dict[str, str],
    unicode: bool,
) -> None:
    """Render per-section ruler (compact mode for large scores).

    Each AtomicSection gets one column. The section ID is centered above
    its MC range label. Flow control markers attach to sections.
    """
    if not sections:
        return

    n_secs = len(sections)
    tree = TREE_CHARS if unicode else TREE_CHARS_ASCII
    h = tree["horizontal"]

    # Compute column width — distribute width across sections
    prefix_w = 4  # "    " indent
    col_width = max(6, (width - prefix_w) // n_secs)

    # Build section -> column position lookup
    sec_to_col: dict[str, int] = {}
    for idx, sec in enumerate(sections):
        sec_to_col[sec.id] = prefix_w + idx * col_width

    total_w = prefix_w + n_secs * col_width

    # Row 1: Section IDs with span bars
    id_row = [" "] * total_w
    for sec in sections:
        col = sec_to_col[sec.id]
        mc_count = sec.mc_end - sec.mc_start
        label = sec.id
        if mc_count == 1:
            # Single-MC section: just the ID centered
            mid = col + col_width // 2
            for ci, ch in enumerate(label):
                pos = mid - len(label) // 2 + ci
                if 0 <= pos < total_w:
                    id_row[pos] = ch
        else:
            # Multi-MC section: ├──ID──┤
            end_col = col + col_width - 1
            if col < total_w:
                id_row[col] = tree["branch"]
            if end_col < total_w:
                id_row[end_col] = "\u2524" if unicode else "|"
            span = end_col - col - 1
            if span > 0:
                if len(label) > span:
                    label = label[:span]
                pad_left = (span - len(label)) // 2
                pad_right = span - len(label) - pad_left
                fill = h * pad_left + label + h * pad_right
                for ci, ch in enumerate(fill):
                    pos = col + 1 + ci
                    if pos < total_w:
                        id_row[pos] = ch

    lines.append("".join(id_row).rstrip())

    # Row 2: MC range labels below each section
    range_row = [" "] * total_w
    for sec in sections:
        col = sec_to_col[sec.id]
        label = f"{sec.mc_start}-{sec.mc_end - 1}"
        if sec.mc_end - sec.mc_start == 1:
            label = str(sec.mc_start)
        # Truncate if too wide
        if len(label) > col_width - 1:
            label = label[: col_width - 1]
        # Center the label
        pad = (col_width - len(label)) // 2
        for ci, ch in enumerate(label):
            pos = col + pad + ci
            if pos < total_w:
                range_row[pos] = ch

    lines.append("".join(range_row).rstrip())

    # Row 3: Flow control markers (repeats, jumps, volta annotations)
    fc_row = [" "] * total_w
    has_fc = False

    # Build mc -> section lookup
    mc_to_sec: dict[int, str] = {}
    for sec in sections:
        for mc in range(sec.mc_start, sec.mc_end):
            mc_to_sec[mc] = sec.id

    for unit in units:
        sec_id = mc_to_sec.get(unit.mc)
        if sec_id is None:
            continue
        col = sec_to_col.get(sec_id, 0)

        if unit.start_repeat:
            marker = fc["repeat_start"]
            has_fc = True
            for ci, ch in enumerate(marker):
                if col + ci < total_w:
                    fc_row[col + ci] = ch

        if unit.end_repeat:
            marker = fc["repeat_end"]
            has_fc = True
            end_pos = col + col_width - len(marker)
            for ci, ch in enumerate(marker):
                if 0 <= end_pos + ci < total_w:
                    fc_row[end_pos + ci] = ch

    if has_fc:
        lines.append("".join(fc_row).rstrip())

    # Row 4: Volta + jump markers (combined)
    marker_row = [" "] * total_w
    has_markers = False

    for unit in units:
        sec_id = mc_to_sec.get(unit.mc)
        if sec_id is None:
            continue
        col = sec_to_col.get(sec_id, 0)

        if unit.volta is not None:
            marker = f"{fc['volta_corner']}{unit.volta}{fc['volta_top']}"
            has_markers = True
            for ci, ch in enumerate(marker):
                if col + ci < total_w:
                    marker_row[col + ci] = ch

        jump = _get_jump_marker(unit, sections, fc)
        if jump:
            has_markers = True
            for ci, ch in enumerate(jump):
                if col + ci < total_w:
                    marker_row[col + ci] = ch

    if has_markers:
        lines.append("".join(marker_row).rstrip())


def _render_table(
    lines: list[str],
    units: list[Any],
    sections: list[Any],
    fc: dict[str, str],
) -> None:
    """Render compact vertical table listing each section."""
    if not sections:
        return

    # Build mc -> unit lookup for flow control annotation
    mc_to_unit: dict[int, Any] = {u.mc: u for u in units}

    # Table header
    lines.append("")
    lines.append(f"  {'ID':<4} {'MCs':<12} {'#':>3}  {'Flow control'}")
    lines.append(f"  {'──':<4} {'───────────':<12} {'──':>3}  {'────────────'}")

    for sec in sections:
        mc_range = f"[{sec.mc_start}, {sec.mc_end})"
        mc_count = sec.mc_end - sec.mc_start

        # Collect flow events in this section
        events: list[str] = []
        for mc in range(sec.mc_start, sec.mc_end):
            u = mc_to_unit.get(mc)
            if u is None:
                continue
            if u.start_repeat:
                events.append(f"{fc['repeat_start']}")
            if u.end_repeat:
                target = u.next[0] if u.next else "?"
                events.append(f"{fc['repeat_end']}{fc['arrow']}{target}")
            if u.volta is not None:
                events.append(f"v{u.volta}")
            if u.fine:
                events.append("fine")
            jump = _get_jump_marker(u, sections, fc)
            if jump:
                events.append(jump)

        fc_str = ", ".join(events) if events else ""
        lines.append(f"  {sec.id:<4} {mc_range:<12} {mc_count:>3}  {fc_str}")

    # Transitions
    lines.append("")
    for sec in sections:
        targets = list(sec.to) if sec.to else []
        if targets:
            lines.append(f"  {sec.id} {fc['arrow']} [{', '.join(targets)}]")


def _get_jump_marker(
    unit: Any,
    sections: list[Any],
    fc: dict[str, str],
) -> str:
    """Return a jump marker string for a unit, or empty string."""
    if unit.fine:
        return "fine"
    if not unit.jump_from:
        return ""
    fct = unit.flow_control_types
    if "da_capo" in fct:
        target = unit.next[0] if unit.next else "?"
        return f"D.C.{fc['arrow']}{target}"
    if "dal_segno" in fct:
        target = unit.next[0] if unit.next else "?"
        target_sec = "?"
        for sec in sections:
            if sec.mc_start <= target < sec.mc_end:
                target_sec = sec.id
                break
        return f"{fc['segno']}{fc['arrow']}{target_sec}"
    if "to_coda" in fct:
        target = unit.next[0] if unit.next else "?"
        target_sec = "?"
        for sec in sections:
            if sec.mc_start <= target < sec.mc_end:
                target_sec = sec.id
                break
        return f"{fc['coda']}{fc['arrow']}{target_sec}"
    return ""


def _render_legend(
    lines: list[str],
    units: list[Any],
    sections: list[Any],
    fc: dict[str, str],
) -> None:
    """Render flow control legend."""
    lines.append("")
    lines.append("Flow control:")
    for unit in units:
        mc_label = f"  MC {unit.mc:>3}"
        if unit.start_repeat:
            sec_id = "?"
            for sec in sections:
                if sec.mc_start <= unit.mc < sec.mc_end:
                    sec_id = sec.id
                    break
            lines.append(f"{mc_label}: repeat_start (section {sec_id})")
        if unit.end_repeat:
            target = unit.next[0] if unit.next else "?"
            lines.append(f"{mc_label}: repeat_end {fc['arrow']} MC {target}")
        if unit.volta is not None:
            sec_id = "?"
            for sec in sections:
                if sec.mc_start <= unit.mc < sec.mc_end:
                    sec_id = sec.id
                    break
            lines.append(f"{mc_label}: volta {unit.volta} (section {sec_id})")
        if unit.fine:
            lines.append(f"{mc_label}: fine")
        if unit.segno:
            lines.append(f"{mc_label}: segno marker '{unit.segno}'")
        if unit.coda:
            lines.append(f"{mc_label}: coda marker '{unit.coda}'")
        if unit.jump_from:
            fct = unit.flow_control_types
            target = unit.next[0] if unit.next else "?"
            if "da_capo" in fct:
                lines.append(f"{mc_label}: da_capo {fc['arrow']} MC {target}")
            elif "dal_segno" in fct:
                target_sec = "?"
                for sec in sections:
                    if sec.mc_start <= target < sec.mc_end:
                        target_sec = sec.id
                        break
                lines.append(
                    f"{mc_label}: dal_segno {fc['arrow']} " f"section {target_sec}"
                )
            elif "to_coda" in fct:
                target_sec = "?"
                for sec in sections:
                    if sec.mc_start <= target < sec.mc_end:
                        target_sec = sec.id
                        break
                lines.append(
                    f"{mc_label}: to_coda {fc['arrow']} "
                    f"section {target_sec} (MC {target})"
                )
        if unit.section_break:
            lines.append(f"{mc_label}: section_break")


def _render_graph(
    lines: list[str],
    sections: list[Any],
    fc: dict[str, str],
) -> None:
    """Render section transition graph."""
    lines.append("")
    lines.append("Section transitions:")
    entries: list[str] = []
    for sec in sections:
        targets = list(sec.to) if sec.to else []
        entries.append(f"{sec.id} {fc['arrow']} [{', '.join(targets)}]")

    per_row = 4
    for i in range(0, len(entries), per_row):
        end = i + per_row
        chunk = entries[i:end]
        lines.append("  " + "    ".join(chunk))


# endregion

# region Flow Diagram


def flow_diagram(
    flow_obj: "Flow",
    width: int = DEFAULT_WIDTH,
    unicode: bool = True,
    show_mcs: bool = False,
    show_reasons: bool = True,
) -> str:
    """Generate ASCII diagram for a Flow object.

    Shows the playthrough section sequence for a computed flow.

    Args:
        flow_obj: The Flow to render.
        width: Total width of the diagram in characters.
        unicode: Use Unicode characters (True) or ASCII fallback (False).
        show_mcs: Whether to expand MC sequences per section.
        show_reasons: Whether to annotate why each section starts.

    Returns:
        Multi-line string with ASCII diagram.
    """
    fc = FLOW_CHARS if unicode else FLOW_CHARS_ASCII

    lines: list[str] = []
    sections = flow_obj.sections
    folded = flow_obj.folded_length
    unfolded = flow_obj.unfolded_length
    ratio = unfolded / folded if folded > 0 else 0.0

    # 1. Header
    lines.append(
        f"Flow({flow_obj.mode.value}): {folded} folded "
        f"{fc['arrow']} {unfolded} unfolded "
        f"(\u00d7{ratio:.2f}), {len(sections)} sections"
    )
    lines.append("")

    # 2. Table
    if show_reasons:
        lines.append(f" {'#':>3}  {'MCs':<12} {'Sections':<12} {'Reason'}")
        lines.append(
            f" {'──':>3}  {'───────────':<12} " f"{'────────':<12} {'──────────────'}"
        )
    else:
        lines.append(f" {'#':>3}  {'MCs':<12} {'Sections':<12}")
        lines.append(f" {'──':>3}  {'───────────':<12} {'────────':<12}")

    # Try to get controller for rich reason annotations
    ctrl = flow_obj.controller

    for idx, sec in enumerate(sections):
        step = idx + 1
        mc_range = f"[{sec.mc_start}, {sec.mc_end})"
        sec_ids = ";".join(sec.atomic_section_ids)

        # Derive reason
        reason = ""
        if show_reasons:
            if idx == 0:
                reason = "start"
            else:
                prev = sections[idx - 1]
                if sec.mc_start == prev.mc_end:
                    reason = fc["arrow"]
                elif sec.mc_start < prev.mc_end:
                    # Jumped backward
                    if ctrl is not None:
                        try:
                            all_units = list(ctrl.iter_units())
                            prev_last_mc = prev.mc_end - 1
                            prev_unit = next(
                                (u for u in all_units if u.mc == prev_last_mc),
                                None,
                            )
                            if prev_unit and prev_unit.jump_from:
                                fct = prev_unit.flow_control_types
                                if "da_capo" in fct:
                                    reason = f"D.C. {fc['arrow']} {sec.mc_start}"
                                elif "dal_segno" in fct:
                                    reason = f"D.S. {fc['arrow']} {sec.mc_start}"
                                else:
                                    reason = f"repeat {fc['arrow']} {sec.mc_start}"
                            elif prev_unit and prev_unit.end_repeat:
                                reason = f"repeat {fc['arrow']} {sec.mc_start}"
                            else:
                                reason = f"jump \u2190 {sec.mc_start}"
                        except (ValueError, StopIteration):
                            reason = f"jump \u2190 {sec.mc_start}"
                    else:
                        reason = f"jump \u2190 {sec.mc_start}"
                else:
                    # Jumped forward
                    if ctrl is not None:
                        try:
                            all_units = list(ctrl.iter_units())
                            prev_last_mc = prev.mc_end - 1
                            prev_unit = next(
                                (u for u in all_units if u.mc == prev_last_mc),
                                None,
                            )
                            if prev_unit and prev_unit.jump_from:
                                fct = prev_unit.flow_control_types
                                if "to_coda" in fct:
                                    reason = "coda"
                                else:
                                    reason = f"skip {fc['arrow']} {sec.mc_start}"
                            else:
                                reason = f"skip {fc['arrow']} {sec.mc_start}"
                        except (ValueError, StopIteration):
                            reason = f"jump {fc['arrow']} {sec.mc_start}"
                    else:
                        reason = f"jump {fc['arrow']} {sec.mc_start}"

        if show_reasons:
            lines.append(f" {step:>3} {mc_range:<12} {sec_ids:<12} {reason}")
        else:
            lines.append(f" {step:>3} {mc_range:<12} {sec_ids:<12}")

        # Optionally expand MC numbers
        if show_mcs:
            mc_seq = list(range(sec.mc_start, sec.mc_end))
            lines.append(f"      MCs: {', '.join(str(m) for m in mc_seq)}")

    # 3. Footer - atomic sequence
    seq = flow_obj.to_atomic_sequence()
    lines.append("")
    lines.append(f"Sequence: {' '.join(seq)}")

    return "\n".join(lines)


# endregion

# region Flow Comparison Diagram


def flow_comparison_diagram(
    flow_a: "Flow",
    flow_b: "Flow",
    width: int = 80,
    unicode: bool = True,
) -> str:
    """Generate side-by-side comparison of two Flows.

    Args:
        flow_a: First Flow to compare.
        flow_b: Second Flow to compare.
        width: Total width of the diagram in characters.
        unicode: Use Unicode characters (True) or ASCII fallback (False).

    Returns:
        Multi-line string with comparison diagram.
    """
    fc = FLOW_CHARS if unicode else FLOW_CHARS_ASCII

    lines: list[str] = []
    name_a = flow_a.mode.value
    name_b = flow_b.mode.value

    # Header
    lines.append(f"Flow comparison: {name_a} vs {name_b}")
    lines.append("")

    # Column layout
    col_w = max(16, (width - 12) // 2)
    lines.append(f" {'#':>3}  {name_a:<{col_w}} {name_b:<{col_w}} {'':>5}")
    lines.append(
        f" {'──':>3}  "
        f"{'─' * min(col_w, 15)}{' ' * max(0, col_w - 15)} "
        f"{'─' * min(col_w, 15)}{' ' * max(0, col_w - 15)} "
        f"{'─────'}"
    )

    secs_a = flow_a.sections
    secs_b = flow_b.sections
    max_rows = max(len(secs_a), len(secs_b))
    n_matching = 0

    for i in range(max_rows):
        step = i + 1

        if i < len(secs_a):
            sa = secs_a[i]
            a_str = (
                f"[{sa.mc_start}, {sa.mc_end})  " f"{';'.join(sa.atomic_section_ids)}"
            )
        else:
            a_str = "---"

        if i < len(secs_b):
            sb = secs_b[i]
            b_str = (
                f"[{sb.mc_start}, {sb.mc_end})  " f"{';'.join(sb.atomic_section_ids)}"
            )
        else:
            b_str = "---"

        # Compare
        if i < len(secs_a) and i < len(secs_b):
            sa = secs_a[i]
            sb = secs_b[i]
            if (
                sa.mc_start == sb.mc_start
                and sa.mc_end == sb.mc_end
                and sa.atomic_section_ids == sb.atomic_section_ids
            ):
                mark = fc["match"]
                n_matching += 1
            else:
                diffs: list[str] = []
                if sa.mc_start != sb.mc_start:
                    diffs.append("mc_start")
                if sa.mc_end != sb.mc_end:
                    diffs.append("mc_end")
                if sa.atomic_section_ids != sb.atomic_section_ids:
                    diffs.append("sections")
                mark = f"{fc['mismatch']} \u2190 {','.join(diffs)}"
        else:
            mark = fc["mismatch"]

        lines.append(f" {step:>3} {a_str:<{col_w}} {b_str:<{col_w}} {mark}")

    # Summary footer
    lines.append("")
    lines.append(
        f" {name_a}: {len(secs_a)} sections, " f"{flow_a.unfolded_length} unfolded"
    )
    lines.append(
        f" {name_b}: {len(secs_b)} sections, " f"{flow_b.unfolded_length} unfolded"
    )
    lines.append(f" Matching: {n_matching}/{max_rows} sections identical")

    return "\n".join(lines)


# endregion
