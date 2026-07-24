"""Tests for interval-built FlowMaps.

Validates constructing a ``FlowMap`` directly from anything describing an
interval — a singleton or a collection — through the single polymorphic
positional argument of ``FlowMap(source)``, the module-private coercion
helpers behind it, and the ``Timeline.create_flow_map(intervals)`` convenience.

Motivating case: a performance that skips score measures 42 and 43. The child
timeline lives in quarterbeat (QB) space with two played spans ``[0, 123)`` and
``[129, length)``; QB ``123``–``129`` fall in the gap and map to nothing, while
the two played spans concatenate in the unfolded (target) axis.

Following the project's ZERO TOLERANCE policy, every assertion is an exact
``Fraction`` (or exact ``float`` for the timeline convenience surface) — no
ranges, no ``pytest.approx``.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from timetoalign.core import Coordinate, TimeUnit, struct_to_rational
from timetoalign.core.enums import FlowMode
from timetoalign.core.events import Note
from timetoalign.timelines.flow import Flow, FlowMap, PlaythroughSection
from timetoalign.timelines.flow.sections import (
    _as_interval,
    _coerce_intervals,
    _interval_value,
)
from timetoalign.timelines.regions import Region
from timetoalign.timelines.types import ContinuousLogicalTimeline, SegmentLine

# region Helpers


def _coord(value: float) -> Coordinate:
    """A quarterbeat coordinate at *value*."""
    return Coordinate(value, TimeUnit.quarters)


def _region(name: str, start: float, end: float) -> Region:
    """A named region spanning ``[start, end)`` in quarters."""
    return Region(name, start=_coord(start), end=_coord(end))


# endregion

# region Coercion primitives


class TestIntervalValue:
    """`_interval_value` coerces a single coordinate-like value to a Fraction."""

    def test_raw_int(self) -> None:
        assert _interval_value(123) == Fraction(123)

    def test_raw_fraction(self) -> None:
        assert _interval_value(Fraction(129, 2)) == Fraction(129, 2)

    def test_coordinate_like(self) -> None:
        assert _interval_value(_coord(123)) == Fraction(123)


class TestAsInterval:
    """`_as_interval` recognises each descriptor shape → exact (start, end)."""

    def test_pair_of_raw_ints(self) -> None:
        assert _as_interval((0, 123)) == (Fraction(0), Fraction(123))

    def test_pair_of_raw_ints_as_list(self) -> None:
        assert _as_interval([0, 123]) == (Fraction(0), Fraction(123))

    def test_pair_of_coordinates(self) -> None:
        assert _as_interval((_coord(0), _coord(129))) == (
            Fraction(0),
            Fraction(129),
        )

    def test_region(self) -> None:
        assert _as_interval(_region("A8_1", 0, 123)) == (
            Fraction(0),
            Fraction(123),
        )

    def test_timeline_is_an_interval(self) -> None:
        tl = ContinuousLogicalTimeline(length=200)
        assert _as_interval(tl) == (Fraction(0), Fraction(200))

    def test_interval_event(self) -> None:
        note = Note(start=_coord(0), end=_coord(123))
        assert _as_interval(note) == (Fraction(0), Fraction(123))

    def test_name_string_with_resolver(self) -> None:
        regions = {"A8_1": _region("A8_1", 0, 123)}
        assert _as_interval("A8_1", resolve=regions.get) == (
            Fraction(0),
            Fraction(123),
        )

    def test_name_string_without_resolver_raises(self) -> None:
        with pytest.raises(ValueError):
            _as_interval("A8_1")

    def test_wrong_length_sequence_raises(self) -> None:
        with pytest.raises(ValueError):
            _as_interval((0, 123, 200))

    def test_unrecognised_shape_raises(self) -> None:
        with pytest.raises(TypeError):
            _as_interval(object())


class TestCoerceIntervals:
    """`_coerce_intervals` handles singleton-or-collection via one argument."""

    def test_single_pair(self) -> None:
        assert _coerce_intervals((0, 123)) == [(Fraction(0), Fraction(123))]

    def test_single_pair_as_list_is_one_interval(self) -> None:
        # [0, 123] is ONE coordinate pair, not a collection of two singletons.
        assert _coerce_intervals([0, 123]) == [(Fraction(0), Fraction(123))]

    def test_single_region(self) -> None:
        assert _coerce_intervals(_region("A8_1", 0, 123)) == [
            (Fraction(0), Fraction(123))
        ]

    def test_list_of_two_regions(self) -> None:
        assert _coerce_intervals(
            [_region("A8_1", 0, 123), _region("A8_2", 129, 200)]
        ) == [(Fraction(0), Fraction(123)), (Fraction(129), Fraction(200))]

    def test_list_of_two_pairs(self) -> None:
        assert _coerce_intervals([(0, 123), (129, 200)]) == [
            (Fraction(0), Fraction(123)),
            (Fraction(129), Fraction(200)),
        ]

    def test_list_of_two_names(self) -> None:
        regions = {
            "A8_1": _region("A8_1", 0, 123),
            "A8_2": _region("A8_2", 129, 200),
        }
        assert _coerce_intervals(["A8_1", "A8_2"], resolve=regions.get) == [
            (Fraction(0), Fraction(123)),
            (Fraction(129), Fraction(200)),
        ]

    def test_single_name_string_is_never_char_iterated(self) -> None:
        # A str is always a singleton: one interval, not one per character.
        regions = {"A8_1": _region("A8_1", 0, 123)}
        assert _coerce_intervals("A8_1", resolve=regions.get) == [
            (Fraction(0), Fraction(123))
        ]

    def test_end_before_start_raises(self) -> None:
        with pytest.raises(ValueError):
            _coerce_intervals((10, 5))

    def test_end_before_start_in_collection_raises(self) -> None:
        with pytest.raises(ValueError):
            _coerce_intervals([(0, 123), (200, 129)])


# endregion

# region Interval-built FlowMap


class TestFlowMapFromIntervals:
    """FlowMap built from two played spans with a skipped gap between them."""

    @pytest.fixture
    def two_span_map(self) -> FlowMap:
        # Performance skipping score measures 42 & 43 (QB 123-129):
        # played spans [0, 123) and [129, 252) on a length-252 child.
        return FlowMap([_region("A8_1", 0, 123), _region("A8_2", 129, 252)], id="A8")

    def test_n_sections(self, two_span_map: FlowMap) -> None:
        assert two_span_map.n_sections == 2

    def test_flow_is_none(self, two_span_map: FlowMap) -> None:
        assert two_span_map.flow is None

    def test_total_target_length(self, two_span_map: FlowMap) -> None:
        # 123 + (252 - 129) = 246
        assert two_span_map.total_target_length == Fraction(246)

    def test_unfold_first_span(self, two_span_map: FlowMap) -> None:
        assert two_span_map.unfold_coordinate(50) == [Fraction(50)]

    def test_unfold_gap_maps_to_nothing(self, two_span_map: FlowMap) -> None:
        assert two_span_map.unfold_coordinate(125) == []

    def test_unfold_second_span_concatenates(self, two_span_map: FlowMap) -> None:
        # 123 + (150 - 129) = 144
        assert two_span_map.unfold_coordinate(150) == [Fraction(144)]

    def test_fold_second_span(self, two_span_map: FlowMap) -> None:
        assert two_span_map.fold(144) == Fraction(150)

    def test_fold_first_span(self, two_span_map: FlowMap) -> None:
        assert two_span_map.fold(50) == Fraction(50)

    def test_repr_shows_id(self, two_span_map: FlowMap) -> None:
        assert repr(two_span_map) == "FlowMap(A8: 2 sections)"

    def test_inverse_round_trips(self, two_span_map: FlowMap) -> None:
        inverse = two_span_map.inverse()
        assert inverse.flow is None
        assert repr(inverse) == "FlowMap(A8_inverse: 2 sections)"
        # Target 144 came from source 150; the inverse recovers it.
        assert inverse.unfold_coordinate(144) == [Fraction(150)]

    def test_id_defaults_to_default(self) -> None:
        fm = FlowMap([(0, 123), (129, 252)])
        assert fm.id == "default"

    def test_singleton_interval(self) -> None:
        fm = FlowMap(_region("A8_1", 0, 123), id="X")
        assert fm.n_sections == 1
        assert fm.total_target_length == Fraction(123)
        assert fm.unfold_coordinate(10) == [Fraction(10)]

    def test_empty_source_is_empty_map(self) -> None:
        fm = FlowMap()
        assert fm.flow is None
        assert fm.n_sections == 0
        assert fm.unfold_coordinate(0) == []


# endregion

# region Regression: Flow and from_qb_sections paths


class TestFlowMapFlowRegression:
    """The MC-space Flow path and from_qb_sections stay exactly as before."""

    @pytest.fixture
    def repeated_flow(self) -> Flow:
        # MC 3 is visited twice (two identical [1, 5) playthrough sections).
        return Flow.from_sections(
            [
                PlaythroughSection(1, 5, ("A",)),
                PlaythroughSection(1, 5, ("A",)),
            ],
            FlowMode.default,
        )

    def test_positional_flow_builds_mc_sections(self, repeated_flow: Flow) -> None:
        fm = FlowMap(repeated_flow)
        assert fm.flow is repeated_flow
        assert fm.id == "default"
        # Source MC 3 appears twice: target 2 (in first span) and 6 (in second).
        assert fm.unfold_coordinate(3) == [Fraction(2), Fraction(6)]
        assert fm.n_sections == 2

    def test_source_keyword_works(self, repeated_flow: Flow) -> None:
        # The polymorphic positional parameter is named `source`, so it may be
        # passed by keyword as `source=`.
        fm = FlowMap(source=repeated_flow, id="custom")
        assert fm.id == "custom"
        assert fm.unfold_coordinate(3) == [Fraction(2), Fraction(6)]

    def test_legacy_flow_keyword_rejected(self, repeated_flow: Flow) -> None:
        # The historical `flow=` keyword no longer exists; every construction
        # site was migrated to the positional `source`. No compatibility alias
        # is retained.
        with pytest.raises(TypeError):
            FlowMap(flow=repeated_flow)  # type: ignore[call-arg]

    def test_from_qb_sections_unchanged(self, repeated_flow: Flow) -> None:
        qb_sections = [
            (Fraction(0), Fraction(4)),
            (Fraction(4), Fraction(8)),
        ]
        fm = FlowMap.from_qb_sections(repeated_flow, qb_sections, id="qb")
        assert fm.id == "qb"
        assert fm.flow is repeated_flow
        assert fm.n_sections == 2
        assert fm.total_target_length == Fraction(8)
        # Source QB 2 lies in the first span (target 2) and second span
        # (target 4 + (2 - 4)?) — no: second span source range is [4, 8),
        # so QB 2 only appears in the first span.
        assert fm.unfold_coordinate(2) == [Fraction(2)]
        assert fm.unfold_coordinate(5) == [Fraction(5)]

    def test_from_qb_sections_length_mismatch_raises(self, repeated_flow: Flow) -> None:
        with pytest.raises(ValueError):
            FlowMap.from_qb_sections(repeated_flow, [(Fraction(0), Fraction(4))])


# endregion

# region Timeline.create_flow_map


class TestTimelineCreateFlowMap:
    """`Timeline.create_flow_map` constructs, attaches, and returns a FlowMap."""

    @pytest.fixture
    def child(self) -> ContinuousLogicalTimeline:
        tl = ContinuousLogicalTimeline(length=252)
        tl.create_region("A8_1", start=0, end=123)
        tl.create_region("A8_2", start=129, end=252)
        return tl

    def test_by_region_names_attaches(self, child: ContinuousLogicalTimeline) -> None:
        fm = child.create_flow_map(["A8_1", "A8_2"], id="A8")
        assert child.has_flow_map("A8")
        assert child.get_flow_map("A8") is fm
        assert fm.n_sections == 2
        assert repr(fm) == "FlowMap(A8: 2 sections)"

    def test_by_region_names_exact_values(
        self, child: ContinuousLogicalTimeline
    ) -> None:
        child.create_flow_map(["A8_1", "A8_2"], id="A8")
        assert child.unfold_coordinate(50, "A8") == [50.0]
        assert child.unfold_coordinate(125, "A8") == []
        assert child.unfold_coordinate(150, "A8") == [144.0]
        assert child.fold(144, "A8") == 150.0
        assert child.fold(50, "A8") == 50.0

    def test_by_region_objects_equivalent(
        self, child: ContinuousLogicalTimeline
    ) -> None:
        r1 = child.get_region("A8_1")
        r2 = child.get_region("A8_2")
        fm = child.create_flow_map([r1, r2], id="A8b")
        assert fm.total_target_length == Fraction(246)
        assert fm.unfold_coordinate(150) == [Fraction(144)]

    def test_by_coordinate_pairs_equivalent(
        self, child: ContinuousLogicalTimeline
    ) -> None:
        fm = child.create_flow_map([(0, 123), (129, child.length)], id="A8c")
        assert fm.total_target_length == Fraction(246)
        assert fm.unfold_coordinate(150) == [Fraction(144)]

    def test_singleton_region_name(self, child: ContinuousLogicalTimeline) -> None:
        fm = child.create_flow_map("A8_1", id="X")
        assert fm.n_sections == 1
        assert child.get_flow_map("X") is fm

    def test_default_id(self, child: ContinuousLogicalTimeline) -> None:
        fm = child.create_flow_map(["A8_1", "A8_2"])
        assert child.get_flow_map("default") is fm


# endregion

# region Timeline.unfold — the unfolded timeline


class TestTimelineUnfold:
    """`Timeline.unfold(id)` yields the unfolded *timeline* along a FlowMap.

    Distinct from `unfold_coordinate`, which maps a single folded coordinate to
    a list of unfolded coordinates, `unfold` slices the timeline at each section
    of the attached FlowMap and concatenates the slices in target (unfolded)
    order into a new timeline — a ``SegmentLine`` by default, or a flattened
    timeline of the source's concrete type when ``as_segment_line=False``.

    Fixture derivation (ZERO TOLERANCE — every expected value is exact). The
    source is a length-252 timeline with two played spans ``A8_1`` ``[0, 123)``
    and ``A8_2`` ``[129, 252)`` (QB 123-129 is the skipped gap). ``unfold``
    slices the source at those two ranges via `Timeline.get_slice`, which
    rebases each slice's coordinates by ``-start``, then appends them onto a
    ``SegmentLine`` whose segment offsets accumulate as ``0`` then ``123``:

    - Instant ``e10`` at absolute 10 is in span 1 ``[0, 123)`` → local
      ``10 - 0 = 10``. Flattened at section offset 0 → ``10``.
    - Instant ``e140`` at absolute 140 is in span 2 ``[129, 252)`` → local
      ``140 - 129 = 11``. Flattened at section offset 123 → ``134``.
    - The nested child at offset 40 (span [40, 60), inside span 1 only) is
      recursively sliced; its slice offset is ``40 - 0 = 40`` and its own
      instant ``c5`` stays at local 5. It survives in section 0 only.
    - ``total_target_length = 123 + (252 - 129) = 246``.
    """

    @pytest.fixture
    def source(self) -> ContinuousLogicalTimeline:
        """A folded timeline with two played spans, events, and a nested child."""
        tl = ContinuousLogicalTimeline(length=252)
        tl.create_region("A8_1", start=0, end=123)
        tl.create_region("A8_2", start=129, end=252)
        tl.add_events(
            [
                {"id": "e10", "event_type": "Note", "instant": 10},
                {"id": "e140", "event_type": "Note", "instant": 140},
            ]
        )
        nested = ContinuousLogicalTimeline(length=20, uid="nested")
        nested.add_events([{"id": "c5", "event_type": "Note", "instant": 5}])
        tl.add_child(nested, offset=40)
        tl.create_flow_map(["A8_1", "A8_2"], id="A8")
        return tl

    def test_returns_segment_line(self, source: ContinuousLogicalTimeline) -> None:
        assert isinstance(source.unfold("A8"), SegmentLine)

    def test_segment_count(self, source: ContinuousLogicalTimeline) -> None:
        assert source.unfold("A8").n_segments == 2

    def test_total_length(self, source: ContinuousLogicalTimeline) -> None:
        # 123 + (252 - 129) = 246
        assert float(source.unfold("A8").length.value) == 246.0

    def test_segment_lengths(self, source: ContinuousLogicalTimeline) -> None:
        sl = source.unfold("A8")
        _, seg0 = sl.get_segment_by_index(0)
        _, seg1 = sl.get_segment_by_index(1)
        assert float(seg0.length.value) == 123.0
        assert float(seg1.length.value) == 123.0

    def test_parent_events_land_at_derived_coords(
        self, source: ContinuousLogicalTimeline
    ) -> None:
        sl = source.unfold("A8")
        _, seg0 = sl.get_segment_by_index(0)
        _, seg1 = sl.get_segment_by_index(1)
        seg0_events = {e["id"]: e for e in seg0.get_events(include_children=False)}
        seg1_events = {e["id"]: e for e in seg1.get_events(include_children=False)}
        # span 1 slice [0, 123): absolute 10 rebases to 10 - 0 = 10
        assert struct_to_rational(seg0_events["e10"]["start"]) == Fraction(10)
        # span 2 slice [129, 252): absolute 140 rebases to 140 - 129 = 11
        assert struct_to_rational(seg1_events["e140"]["start"]) == Fraction(11)
        # each span carries only its own event
        assert "e140" not in seg0_events
        assert "e10" not in seg1_events

    def test_child_survives_in_its_section(
        self, source: ContinuousLogicalTimeline
    ) -> None:
        sl = source.unfold("A8")
        _, seg0 = sl.get_segment_by_index(0)
        _, seg1 = sl.get_segment_by_index(1)
        # the nested child overlaps span 1 only
        assert len(seg0.list_children()) == 1
        assert len(seg1.list_children()) == 0
        child_id = seg0.list_children()[0]
        # child slice offset in the section: 40 - 0 = 40
        assert float(seg0.get_child_offset(child_id).value) == 40.0
        child_events = {
            e["id"]: e
            for e in seg0.get_child(child_id).get_events(include_children=False)
        }
        # child instant stays at its local coordinate 5
        assert struct_to_rational(child_events["c5"]["start"]) == Fraction(5)

    def test_flow_maps_attached(self, source: ContinuousLogicalTimeline) -> None:
        sl = source.unfold("A8")
        assert sl.get_flow_map("source") is not None
        assert sl.has_flow_map("forward_A8")

    def test_flattened_type_and_length(self, source: ContinuousLogicalTimeline) -> None:
        flat = source.unfold("A8", as_segment_line=False)
        assert type(flat) is ContinuousLogicalTimeline
        assert float(flat.length.value) == 246.0

    def test_flattened_events_at_derived_coords(
        self, source: ContinuousLogicalTimeline
    ) -> None:
        flat = source.unfold("A8", as_segment_line=False)
        events = {e["id"]: e for e in flat.get_events(include_children=False)}
        # span 1 (section offset 0): local 10 + 0 = 10
        assert events["e10"]["start"]["value"] == 10.0
        # span 2 (section offset 123): local 11 + 123 = 134
        assert events["e140"]["start"]["value"] == 134.0

    def test_flattened_child_survives(self, source: ContinuousLogicalTimeline) -> None:
        flat = source.unfold("A8", as_segment_line=False)
        assert len(flat.list_children()) == 1
        child_id = flat.list_children()[0]
        # section-0 offset 0 + child offset 40 = 40
        assert float(flat.get_child_offset(child_id).value) == 40.0
        child_events = {
            e["id"]: e
            for e in flat.get_child(child_id).get_events(include_children=False)
        }
        assert child_events["c5"]["start"]["value"] == 5.0

    def test_unknown_flow_map_raises(self, source: ContinuousLogicalTimeline) -> None:
        with pytest.raises(ValueError):
            source.unfold("nope")


# endregion
