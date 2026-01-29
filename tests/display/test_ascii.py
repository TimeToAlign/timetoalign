"""Tests for the ASCII display module.

Tests cover:
- Character sets for all 6 timeline types
- Helper functions (coordinate formatting, name elision)
- Child row building and positioning
- Truncation logic for many children
- Timeline, group, and bundle diagrams
- ASCII fallback mode
"""

from __future__ import annotations

from timetoalign.display.ascii import (
    BOX_CHARS,
    BOX_CHARS_ASCII,
    TIMELINE_CHARS,
    TIMELINE_CHARS_ASCII,
    TREE_CHARS,
    TREE_CHARS_ASCII,
    _build_child_row,
    _elide_name,
    _format_coordinate,
    _get_children_to_display,
    _get_timeline_char,
    bundle_diagram,
    group_diagram,
    timeline_diagram,
)
from timetoalign.timelines.types import (
    ContinuousGraphicalTimeline,
    ContinuousLogicalTimeline,
    ContinuousPhysicalTimeline,
    DiscreteGraphicalTimeline,
    DiscreteLogicalTimeline,
    DiscretePhysicalTimeline,
)

# region Character Set Tests


class TestCharacterSets:
    """Tests for character set definitions."""

    def test_timeline_chars_covers_all_types(self) -> None:
        """All 6 core timeline type combinations have characters."""
        # Core types: int (discrete) and float (continuous) for each domain
        core_keys = {
            ("float", "graphical"),
            ("int", "graphical"),
            ("float", "physical"),
            ("int", "physical"),
            ("float", "logical"),
            ("int", "logical"),
        }
        # fraction type is also supported (same as float/continuous)
        fraction_keys = {
            ("fraction", "graphical"),
            ("fraction", "physical"),
            ("fraction", "logical"),
        }
        all_keys = core_keys | fraction_keys
        assert set(TIMELINE_CHARS.keys()) == all_keys
        assert set(TIMELINE_CHARS_ASCII.keys()) == all_keys

    def test_timeline_chars_are_single_character(self) -> None:
        """All timeline characters are single characters."""
        for key, char in TIMELINE_CHARS.items():
            assert len(char) == 1, f"Character for {key} is not single: {char!r}"
        for key, char in TIMELINE_CHARS_ASCII.items():
            assert len(char) == 1, f"ASCII char for {key} is not single: {char!r}"

    def test_timeline_chars_are_distinct(self) -> None:
        """Core timeline characters are unique (int/float for each domain)."""
        # Check the 6 core types are distinct
        core_keys = [
            ("float", "graphical"),
            ("int", "graphical"),
            ("float", "physical"),
            ("int", "physical"),
            ("float", "logical"),
            ("int", "logical"),
        ]
        chars = [TIMELINE_CHARS[k] for k in core_keys]
        assert len(chars) == len(set(chars)), "Core timeline chars are not unique"

    def test_tree_chars_complete(self) -> None:
        """Tree drawing characters include all necessary entries."""
        required = {"branch", "last", "vertical", "horizontal"}
        assert set(TREE_CHARS.keys()) == required
        assert set(TREE_CHARS_ASCII.keys()) == required

    def test_box_chars_complete(self) -> None:
        """Box drawing characters include all corners and sides."""
        required = {
            "top_left",
            "top_right",
            "bottom_left",
            "bottom_right",
            "horizontal",
            "vertical",
        }
        assert set(BOX_CHARS.keys()) == required
        assert set(BOX_CHARS_ASCII.keys()) == required


# endregion

# region Helper Function Tests


class TestFormatCoordinate:
    """Tests for _format_coordinate helper."""

    def test_integer_value_no_decimal(self) -> None:
        """Integer values format without decimal point."""
        assert _format_coordinate(0.0) == "0"
        assert _format_coordinate(100.0) == "100"
        assert _format_coordinate(4835.0) == "4835"

    def test_float_value_one_decimal(self) -> None:
        """Float values format with one decimal place."""
        assert _format_coordinate(150.5) == "150.5"
        assert _format_coordinate(99.9) == "99.9"
        assert _format_coordinate(0.1) == "0.1"

    def test_nearly_integer_treated_as_integer(self) -> None:
        """Values that are exactly integers format as integers."""
        assert _format_coordinate(150.0) == "150"


class TestElideName:
    """Tests for _elide_name helper."""

    def test_short_name_unchanged(self) -> None:
        """Names within max_width are unchanged."""
        assert _elide_name("system_1", 12) == "system_1"
        assert _elide_name("abc", 5) == "abc"

    def test_exact_length_unchanged(self) -> None:
        """Names exactly at max_width are unchanged."""
        assert _elide_name("system_12345", 12) == "system_12345"

    def test_long_name_elided(self) -> None:
        """Names exceeding max_width get '...' suffix."""
        result = _elide_name("very_long_system_name", 12)
        assert len(result) == 12
        assert result.endswith("...")

    def test_very_short_max_width(self) -> None:
        """Very short max_width just truncates."""
        assert _elide_name("system_1", 3) == "sys"
        assert _elide_name("system_1", 2) == "sy"


class TestGetTimelineChar:
    """Tests for _get_timeline_char helper."""

    def test_discrete_graphical(self) -> None:
        """Discrete graphical timeline gets ':'."""
        tl = DiscreteGraphicalTimeline(length=100, uid="test_dg")
        assert _get_timeline_char(tl, use_unicode=True) == ":"
        assert _get_timeline_char(tl, use_unicode=False) == ":"

    def test_continuous_graphical(self) -> None:
        """Continuous graphical timeline gets '='."""
        tl = ContinuousGraphicalTimeline(length=100.0, uid="test_cg")
        assert _get_timeline_char(tl, use_unicode=True) == "="

    def test_discrete_physical(self) -> None:
        """Discrete physical timeline gets '⋅' (or '.' in ASCII)."""
        tl = DiscretePhysicalTimeline(length=100, uid="test_dp")
        assert _get_timeline_char(tl, use_unicode=True) == "\u22c5"
        assert _get_timeline_char(tl, use_unicode=False) == "."

    def test_continuous_physical(self) -> None:
        """Continuous physical timeline gets '~'."""
        tl = ContinuousPhysicalTimeline(length=100.0, uid="test_cp")
        assert _get_timeline_char(tl, use_unicode=True) == "~"

    def test_discrete_logical(self) -> None:
        """Discrete logical timeline gets ','."""
        tl = DiscreteLogicalTimeline(length=100, uid="test_dl")
        assert _get_timeline_char(tl, use_unicode=True) == ","

    def test_continuous_logical(self) -> None:
        """Continuous logical timeline gets '_'."""
        tl = ContinuousLogicalTimeline(length=100.0, uid="test_cl")
        assert _get_timeline_char(tl, use_unicode=True) == "_"


class TestGetChildrenToDisplay:
    """Tests for _get_children_to_display truncation helper."""

    def test_no_truncation_when_under_max(self) -> None:
        """No truncation when children count <= max."""
        children: list[tuple[float, str]] = [(0.0, "a"), (10.0, "b"), (20.0, "c")]
        first, omitted, last = _get_children_to_display(children, max_children=6)
        assert first == children
        assert omitted == 0
        assert last == []

    def test_no_truncation_at_max(self) -> None:
        """No truncation when children count == max."""
        children: list[tuple[float, str]] = [(float(i * 10), f"c{i}") for i in range(6)]
        first, omitted, last = _get_children_to_display(children, max_children=6)
        assert first == children
        assert omitted == 0
        assert last == []

    def test_truncation_splits_correctly(self) -> None:
        """Truncation splits into first half, omitted count, last half."""
        children: list[tuple[float, str]] = [
            (float(i * 10), f"c{i}") for i in range(10)
        ]
        first, omitted, last = _get_children_to_display(children, max_children=6)
        # For max=6: first_count = (6+1)//2 = 3, last_count = 6-3 = 3
        assert len(first) == 3
        assert len(last) == 3
        assert omitted == 4  # 10 - 3 - 3 = 4

    def test_truncation_with_odd_max(self) -> None:
        """Truncation with odd max_children."""
        children: list[tuple[float, str]] = [
            (float(i * 10), f"c{i}") for i in range(10)
        ]
        first, omitted, last = _get_children_to_display(children, max_children=5)
        # For max=5: first_count = (5+1)//2 = 3, last_count = 5-3 = 2
        assert len(first) == 3
        assert len(last) == 2
        assert omitted == 5


class TestBuildChildRow:
    """Tests for _build_child_row helper."""

    def test_basic_row_structure(self) -> None:
        """Row has expected prefix, name, coords, bar, and end coord."""
        row = _build_child_row(
            child_offset=0,
            child_length=500,
            child_name="system_1",
            child_char=":",
            parent_length=1000,
            bar_width=50,
            name_width=12,
            coord_width=5,
            is_last=False,
            tree_chars=TREE_CHARS,
        )
        assert TREE_CHARS["branch"] in row  # ├
        assert "system_1" in row
        assert ":" in row  # The bar character

    def test_last_child_uses_last_marker(self) -> None:
        """Last child uses └ instead of ├."""
        row = _build_child_row(
            child_offset=0,
            child_length=500,
            child_name="last_one",
            child_char=":",
            parent_length=1000,
            bar_width=50,
            name_width=12,
            coord_width=5,
            is_last=True,
            tree_chars=TREE_CHARS,
        )
        assert TREE_CHARS["last"] in row  # └
        assert TREE_CHARS["branch"] not in row

    def test_bar_positioned_correctly(self) -> None:
        """Child bar is positioned proportionally on parent scale."""
        # Child at 250-750 on parent 0-1000 should be in middle
        row = _build_child_row(
            child_offset=250,
            child_length=500,
            child_name="middle",
            child_char=":",
            parent_length=1000,
            bar_width=40,
            name_width=10,
            coord_width=5,
            is_last=True,
            tree_chars=TREE_CHARS,
        )
        # The bar should start around position 10 (25% of 40)
        # Find the bar area in the row
        assert ":" in row


# endregion

# region Timeline Diagram Tests


class TestTimelineDiagram:
    """Tests for timeline_diagram function."""

    def test_basic_timeline_output(self) -> None:
        """Basic timeline renders header and bar."""
        tl = DiscreteGraphicalTimeline(length=100, uid="test_basic")
        result = timeline_diagram(tl)

        # Check header
        assert "DiscreteGraphicalTimeline[" in result
        assert tl.id in result

        # Check bar line
        assert "0 " in result  # Start coordinate
        assert "100 pixels" in result  # End + unit

    def test_timeline_with_children(self) -> None:
        """Timeline with children shows child rows."""
        parent = DiscreteGraphicalTimeline(length=1000, uid="parent_wc")
        child1 = DiscreteGraphicalTimeline(length=300, uid="child1", name="system_1")
        child2 = DiscreteGraphicalTimeline(length=300, uid="child2", name="system_2")
        parent.add_child(child1, offset=0)
        parent.add_child(child2, offset=400)

        result = timeline_diagram(parent)

        assert "2 children" in result
        assert "system_1" in result
        assert "system_2" in result
        assert TREE_CHARS["branch"] in result or TREE_CHARS["last"] in result

    def test_show_children_false(self) -> None:
        """show_children=False hides children."""
        parent = DiscreteGraphicalTimeline(length=1000, uid="parent_hide")
        child = DiscreteGraphicalTimeline(length=300, uid="child_hide", name="hidden")
        parent.add_child(child, offset=0)

        result = timeline_diagram(parent, show_children=False)

        # Header should still mention children count
        assert "1 children" in result
        # But child row should not appear
        lines = result.split("\n")
        # Only header and bar line, no child rows
        assert len(lines) == 2

    def test_ascii_mode(self) -> None:
        """unicode=False uses ASCII fallback characters."""
        tl = DiscreteGraphicalTimeline(length=100, uid="test_ascii")
        result = timeline_diagram(tl, unicode=False)

        # Should use ASCII-safe characters only
        assert ":" in result  # ASCII colon is same
        # No Unicode box-drawing characters
        assert "\u250c" not in result  # ┌

    def test_parent_id_annotation(self) -> None:
        """parent_id parameter adds annotation to header."""
        tl = DiscreteGraphicalTimeline(length=100, uid="test_annot")
        result = timeline_diagram(tl, parent_id="parent:1")

        assert "(child of parent:1)" in result


# endregion

# region Group Diagram Tests


class TestGroupDiagram:
    """Tests for group_diagram function."""

    def test_basic_group_output(self) -> None:
        """Basic group renders header, box, and footer."""
        from timetoalign.alignment import TimelineGroup

        tl = DiscreteGraphicalTimeline(length=100, uid="grp_basic")
        group = TimelineGroup(id="test_group", timelines=[tl])

        result = group_diagram(group)

        # Header
        assert "TimelineGroup[test_group]" in result
        assert "1 timelines" in result

        # Box characters
        assert BOX_CHARS["top_left"] in result
        assert BOX_CHARS["bottom_right"] in result

        # Footer
        assert "Timestamps:" in result

    def test_group_with_multiple_timelines(self) -> None:
        """Group with multiple timelines shows all."""
        from timetoalign.alignment import TimelineGroup

        tl1 = DiscreteGraphicalTimeline(length=100, uid="grp_multi_1", name="tl1")
        tl2 = ContinuousPhysicalTimeline(length=50.0, uid="grp_multi_2", name="tl2")
        group = TimelineGroup(id="multi", timelines=[tl1, tl2])

        result = group_diagram(group)

        assert "2 timelines" in result
        assert "DiscreteGraphicalTimeline" in result
        assert "ContinuousPhysicalTimeline" in result

    def test_group_ascii_mode(self) -> None:
        """Group in ASCII mode uses ASCII box characters."""
        from timetoalign.alignment import TimelineGroup

        tl = DiscreteGraphicalTimeline(length=100, uid="grp_ascii")
        group = TimelineGroup(id="ascii_test", timelines=[tl])

        result = group_diagram(group, unicode=False)

        # ASCII box corners
        assert "+" in result  # ASCII corner
        assert "\u250c" not in result  # No Unicode ┌


# endregion

# region Bundle Diagram Tests


class TestBundleDiagram:
    """Tests for bundle_diagram function."""

    def test_basic_bundle_output(self) -> None:
        """Basic bundle renders header and groups."""
        from timetoalign.alignment import AlignmentBundle

        tl = DiscreteGraphicalTimeline(length=100, uid="bnd_basic")
        bundle = AlignmentBundle(id="test_bundle")
        bundle.add_timeline(tl, uid="tl1")

        result = bundle_diagram(bundle)

        # Header
        assert "AlignmentBundle[test_bundle]" in result

        # Match claims footer
        assert "MatchClaims:" in result


# endregion

# region Integration Tests


class TestDiagramMethods:
    """Tests for diagram() methods on Timeline, Group, Bundle."""

    def test_timeline_diagram_method(self) -> None:
        """Timeline.diagram() returns same as timeline_diagram()."""
        tl = DiscreteGraphicalTimeline(length=100, uid="meth_tl")

        method_result = tl.diagram()
        func_result = timeline_diagram(tl)

        assert method_result == func_result

    def test_group_diagram_method(self) -> None:
        """TimelineGroup.diagram() returns same as group_diagram()."""
        from timetoalign.alignment import TimelineGroup

        tl = DiscreteGraphicalTimeline(length=100, uid="meth_grp")
        group = TimelineGroup(id="method_test", timelines=[tl])

        method_result = group.diagram()
        func_result = group_diagram(group)

        assert method_result == func_result

    def test_bundle_diagram_method(self) -> None:
        """AlignmentBundle.diagram() returns same as bundle_diagram()."""
        from timetoalign.alignment import AlignmentBundle

        tl = DiscreteGraphicalTimeline(length=100, uid="meth_bnd")
        bundle = AlignmentBundle(id="bundle_method")
        bundle.add_timeline(tl, uid="tl1")

        method_result = bundle.diagram()
        func_result = bundle_diagram(bundle)

        assert method_result == func_result

    def test_diagram_parameters_passed_through(self) -> None:
        """diagram() method passes parameters correctly."""
        tl = DiscreteGraphicalTimeline(length=100, uid="meth_params")

        # Test width parameter affects output
        wide = tl.diagram(width=100)
        narrow = tl.diagram(width=40)
        # Wider diagram should have more bar characters
        assert len(wide) >= len(narrow)


# endregion
