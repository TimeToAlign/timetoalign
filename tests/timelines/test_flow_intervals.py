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

from timetoalign.core import Coordinate, TimeUnit
from timetoalign.core.enums import FlowMode
from timetoalign.core.events import Note
from timetoalign.timelines.flow import Flow, FlowMap, PlaythroughSection
from timetoalign.timelines.flow.sections import (
    _as_interval,
    _coerce_intervals,
    _interval_value,
)
from timetoalign.timelines.regions import Region
from timetoalign.timelines.types import ContinuousLogicalTimeline

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
        assert two_span_map.unfold(50) == [Fraction(50)]

    def test_unfold_gap_maps_to_nothing(self, two_span_map: FlowMap) -> None:
        assert two_span_map.unfold(125) == []

    def test_unfold_second_span_concatenates(self, two_span_map: FlowMap) -> None:
        # 123 + (150 - 129) = 144
        assert two_span_map.unfold(150) == [Fraction(144)]

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
        assert inverse.unfold(144) == [Fraction(150)]

    def test_id_defaults_to_default(self) -> None:
        fm = FlowMap([(0, 123), (129, 252)])
        assert fm.id == "default"

    def test_singleton_interval(self) -> None:
        fm = FlowMap(_region("A8_1", 0, 123), id="X")
        assert fm.n_sections == 1
        assert fm.total_target_length == Fraction(123)
        assert fm.unfold(10) == [Fraction(10)]

    def test_empty_source_is_empty_map(self) -> None:
        fm = FlowMap()
        assert fm.flow is None
        assert fm.n_sections == 0
        assert fm.unfold(0) == []


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
        assert fm.unfold(3) == [Fraction(2), Fraction(6)]
        assert fm.n_sections == 2

    def test_source_keyword_works(self, repeated_flow: Flow) -> None:
        # The polymorphic positional parameter is named `source`, so it may be
        # passed by keyword as `source=`.
        fm = FlowMap(source=repeated_flow, id="custom")
        assert fm.id == "custom"
        assert fm.unfold(3) == [Fraction(2), Fraction(6)]

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
        assert fm.unfold(2) == [Fraction(2)]
        assert fm.unfold(5) == [Fraction(5)]

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
        assert child.unfold(50, "A8") == [50.0]
        assert child.unfold(125, "A8") == []
        assert child.unfold(150, "A8") == [144.0]
        assert child.fold(144, "A8") == 150.0
        assert child.fold(50, "A8") == 50.0

    def test_by_region_objects_equivalent(
        self, child: ContinuousLogicalTimeline
    ) -> None:
        r1 = child.get_region("A8_1")
        r2 = child.get_region("A8_2")
        fm = child.create_flow_map([r1, r2], id="A8b")
        assert fm.total_target_length == Fraction(246)
        assert fm.unfold(150) == [Fraction(144)]

    def test_by_coordinate_pairs_equivalent(
        self, child: ContinuousLogicalTimeline
    ) -> None:
        fm = child.create_flow_map([(0, 123), (129, child.length)], id="A8c")
        assert fm.total_target_length == Fraction(246)
        assert fm.unfold(150) == [Fraction(144)]

    def test_singleton_region_name(self, child: ContinuousLogicalTimeline) -> None:
        fm = child.create_flow_map("A8_1", id="X")
        assert fm.n_sections == 1
        assert child.get_flow_map("X") is fm

    def test_default_id(self, child: ContinuousLogicalTimeline) -> None:
        fm = child.create_flow_map(["A8_1", "A8_2"])
        assert child.get_flow_map("default") is fm


# endregion
