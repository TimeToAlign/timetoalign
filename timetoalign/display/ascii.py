"""Pure ASCII timeline rendering - zero external dependencies.

This module provides ASCII/Unicode visualization for TimeToAlign! objects:
- Timelines with nested children (one child per row)
- TimelineGroups with boxed layout
- AlignmentBundles with multiple groups

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
    if details:
        header += f" ({', '.join(details)})"
    lines.append(prefix + header)

    # 2. Calculate dimensions
    length_value = float(timeline.length.value)
    end_label = _format_coordinate(length_value)
    unit_label = str(timeline.unit)

    # Coordinate width based on largest coordinate
    coord_width = max(len(end_label), 5)

    # Bar width: total - indent - "0 " - " end unit" - margins
    right_label_len = len(end_label) + 1 + len(unit_label)
    bar_width = width - indent - 2 - right_label_len - 2
    bar_width = max(bar_width, 20)

    # 3. Get timeline character and build parent bar
    line_char = _get_timeline_char(timeline, unicode)
    bar = line_char * bar_width

    # 4. Format parent bar line
    bar_line = f"{prefix}0 {bar} {end_label} {unit_label}"
    lines.append(bar_line)

    # 5. Render children (one per row)
    if show_children and timeline.n_children > 0:
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
    for group in bundle.groups:
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
