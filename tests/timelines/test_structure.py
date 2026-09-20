"""Structure-level validation for the TimeSkeleton building blocks.

These tests pin the ground truths documented in ``tests/timelines/README.md``
under *Native Timeline Structure and Flow-Control Validation*, subsection
*Measure and hierarchy structure*, for the ``SectionHierarchy``, ``MetricHierarchy`` and
``Measure`` scalars: construction equivalences, forest-only hierarchy equality,
name-aware policy equality, and the derived ``count``/``qstamp`` arithmetic of
a ``MeasureMap``. Every expected value is exact, never a range.
"""

from __future__ import annotations

import json
import warnings
from fractions import Fraction
from numbers import Real

import pydantic
import pytest

from timetoalign.core import (
    BeatPolicy,
    CadenzaMeasure,
    Coordinate,
    Duration,
    Interval,
    IrregularMeasure,
    Measure,
    MeasureConstituent,
    RegularMeasure,
    SplitIrregularMeasure,
    SplitRegularMeasure,
    Tempo,
    TimeUnit,
)
from timetoalign.core.time import rational_to_wire
from timetoalign.timelines import (
    Expansion,
    MeasureMap,
    MetricHierarchy,
    MetricNode,
    Reading,
    SectionHierarchy,
    TempoEntry,
    TempoMap,
    Timeline,
)

# The canonical three-section shape used throughout: 78 + 65 + 60 == 203.
SECTION_COUNTS = (78, 65, 60)
TOTAL_MEASURES = 203


def _abstract(count: int) -> list[Measure]:
    """A run of ``count`` length-less measures, as ``from_measure_counts`` mints."""
    return [Measure() for _ in range(count)]


# region (a) Construction equivalences


class TestSectionHierarchyConstructionEquivalence:
    """The same partition spelled every accepted way compares equal."""

    def test_nested_measures_equal_measure_counts(self) -> None:
        nested = SectionHierarchy.from_measures([_abstract(n) for n in SECTION_COUNTS])
        counts = SectionHierarchy.from_measure_counts(list(SECTION_COUNTS))
        assert nested == counts
        assert counts.n_sections == 3
        assert [section.n_measures for section in counts.sections] == list(
            SECTION_COUNTS
        )
        assert counts.n_measures == TOTAL_MEASURES

    def test_int_form_equals_every_single_section_spelling(self) -> None:
        as_int = SectionHierarchy.from_measure_counts(TOTAL_MEASURES)
        as_list = SectionHierarchy.from_measure_counts([TOTAL_MEASURES])
        as_map = SectionHierarchy.from_measure_counts({"whole": TOTAL_MEASURES})
        as_pairs = SectionHierarchy.from_measure_counts([("whole", TOTAL_MEASURES)])
        as_zip = SectionHierarchy.from_measure_counts(
            zip(["whole"], [TOTAL_MEASURES], strict=True)
        )
        as_nested = SectionHierarchy.from_measures([_abstract(TOTAL_MEASURES)])
        assert as_int.n_sections == 1
        for other in (as_list, as_map, as_pairs, as_zip, as_nested):
            assert as_int == other

    def test_three_section_spellings_all_equal(self) -> None:
        as_list = SectionHierarchy.from_measure_counts(list(SECTION_COUNTS))
        as_map = SectionHierarchy.from_measure_counts({"I": 78, "II": 65, "III": 60})
        as_pairs = SectionHierarchy.from_measure_counts(
            [("I", 78), ("II", 65), ("III", 60)]
        )
        as_zip = SectionHierarchy.from_measure_counts(
            zip(["I", "II", "III"], SECTION_COUNTS, strict=True)
        )
        for other in (as_map, as_pairs, as_zip):
            assert as_list == other

    def test_consumed_once_zip_is_materialized(self) -> None:
        # A zip is a single-use iterator; the constructor must read it once and
        # still compare equal to the eager list-of-pairs spelling.
        consumed = zip(["I", "II", "III"], SECTION_COUNTS, strict=True)
        from_zip = SectionHierarchy.from_measure_counts(consumed)
        assert list(consumed) == []  # the iterator is now exhausted
        assert from_zip == SectionHierarchy.from_measure_counts(
            [("I", 78), ("II", 65), ("III", 60)]
        )

    def test_measure_map_accepted_where_measures_expected(self) -> None:
        measure_map = MeasureMap(_abstract(TOTAL_MEASURES))
        from_map = SectionHierarchy.from_measures(measure_map)
        assert from_map.n_sections == 1
        assert from_map.measure_map is measure_map
        assert from_map == SectionHierarchy.from_measure_counts(TOTAL_MEASURES)

    def test_existing_map_is_partitioned_without_rebuilding(self) -> None:
        measure_map = MeasureMap(
            Measure(actual_length=Fraction(1, 3)) for _ in range(6)
        )
        hierarchy = SectionHierarchy.from_measure_map(measure_map, counts=[1, 2, 3])
        assert hierarchy.measure_map is measure_map
        assert [section.n_measures for section in hierarchy.sections] == [1, 2, 3]
        assert [
            tuple(measure.id for measure in section.measure_map)
            for section in hierarchy.sections
        ] == [("m1",), ("m2", "m3"), ("m4", "m5", "m6")]

    def test_existing_map_partition_must_cover_the_map_exactly(self) -> None:
        measure_map = MeasureMap(_abstract(6))
        with pytest.raises(
            ValueError,
            match=r"Section counts must sum to MeasureMap length 6, got \(2, 3\)",
        ):
            SectionHierarchy.from_measure_map(measure_map, counts=[2, 3])

    def test_display_names_excluded_from_equality(self) -> None:
        named = SectionHierarchy.from_measure_counts({"I": 78, "II": 65, "III": 60})
        differently_named = SectionHierarchy.from_measure_counts(
            [("intro", 78), ("middle", 65), ("finale", 60)]
        )
        anonymous = SectionHierarchy.from_measure_counts(list(SECTION_COUNTS))
        assert named == differently_named
        assert named == anonymous
        assert [section.name for section in named.sections] == ["I", "II", "III"]
        assert [section.name for section in anonymous.sections] == [None, None, None]

    def test_different_section_shape_is_unequal(self) -> None:
        assert SectionHierarchy.from_measure_counts(
            list(SECTION_COUNTS)
        ) != SectionHierarchy.from_measure_counts([78, 60, 65])
        assert SectionHierarchy.from_measure_counts(
            [3, 2, 2]
        ) != SectionHierarchy.from_measure_counts([3, 3, 1])

    def test_concrete_leaf_quarter_spans(self) -> None:
        # A concrete three-section structure (3/2/2 bars of 3/4) carries exact
        # leaf spans of 9, 6, 6 quarters and 21 total.
        def bars(count: int) -> list[Measure]:
            return [
                Measure(actual_length=Fraction(3), time_signature="3/4")
                for _ in range(count)
            ]

        hierarchy = SectionHierarchy.from_measures([bars(3), bars(2), bars(2)])
        spans = [
            section.measure_map.total_actual_length for section in hierarchy.sections
        ]
        assert spans == [Fraction(9), Fraction(6), Fraction(6)]
        assert hierarchy.measure_map.total_actual_length == Fraction(21)


# endregion


# region MeasureMap immutability


class TestMeasureMapImmutability:
    """A ``MeasureMap`` exposes no mutators and a read-only measures tuple."""

    @pytest.mark.parametrize("mutator", ["append", "insert", "replace", "set"])
    def test_no_mutator_attributes(self, mutator: str) -> None:
        measure_map = MeasureMap(_abstract(3))
        assert not hasattr(measure_map, mutator)

    def test_measures_tuple_is_not_writable(self) -> None:
        measure_map = MeasureMap(_abstract(3))
        assert isinstance(measure_map.measures, tuple)
        with pytest.raises(TypeError):
            measure_map.measures[0] = Measure()  # type: ignore[index]


class TestMeasureMapEqualityAndWire:
    """Map equality preserves concrete measure semantics and exact wire values."""

    def test_maps_built_twice_compare_equal(self) -> None:
        first = MeasureMap([RegularMeasure(actual_length=Fraction(1, 3))])
        second = MeasureMap([RegularMeasure(actual_length=Fraction(1, 3))])
        assert first == second

    def test_equal_fields_on_different_measure_classes_compare_unequal(self) -> None:
        regular = MeasureMap([RegularMeasure(actual_length=Fraction(1, 3))])
        irregular = MeasureMap([IrregularMeasure(actual_length=Fraction(1, 3))])
        assert regular != irregular

    def test_foreign_equality_operand_is_not_equal(self) -> None:
        assert MeasureMap([]) != ()

    def test_json_round_trip_is_exact_and_emits_no_warning(self) -> None:
        measure_map = MeasureMap(
            [
                RegularMeasure(actual_length=Fraction(1, 3)),
                IrregularMeasure(actual_length=Fraction(2, 3)),
            ]
        )
        payload = json.loads(json.dumps(measure_map.to_dict()))
        with warnings.catch_warnings(record=True) as emitted:
            warnings.simplefilter("always")
            restored = MeasureMap.from_dict(payload)
        assert emitted == []
        assert restored == measure_map
        assert restored.to_dict() == payload


# endregion


# region (b) Metric-hierarchy equivalence


class TestMetricHierarchyEquivalence:
    """Metric equality is exactly the attributed forest."""

    def test_authored_sections_retain_shape_and_every_tempo(self) -> None:
        beat_sizes = [
            Duration(value, "w")
            for value in (
                Fraction(1, 2),
                Fraction(3, 4),
                Fraction(1, 8),
                Fraction(1, 16),
                Fraction(1, 4),
            )
        ]
        rates = [138, 80, 92, 76, 144]
        tempi = [Tempo(beat=beat, bpm=rate) for beat, rate in zip(beat_sizes, rates)]
        hierarchy = MetricHierarchy.from_sections(tempi[:3] + [tempi[3:]])

        assert len(hierarchy.root.expansions) == 1
        assert len(hierarchy.root.expansions[0].children) == 4
        assert [entry.tempo for entry in hierarchy.tempo_maps[0].entries] == tempi
        assert hierarchy.root.level is None
        assert all(
            child.level is None for child in hierarchy.root.expansions[0].children
        )
        assert all(entry.at is None for entry in hierarchy.tempo_maps[0].entries)
        assert hierarchy.tempo_maps[0].kind == "indication"
        assert hierarchy.readings[0].source == "notation"

        pulse_claim = hierarchy.root.model_copy(
            update={
                "expansions": (
                    hierarchy.root.expansions[0].model_copy(
                        update={
                            "children": tuple(
                                child.model_copy(update={"level": 0})
                                for child in hierarchy.root.expansions[0].children
                            )
                        }
                    ),
                )
            }
        )
        assert hierarchy != MetricHierarchy(
            root=pulse_claim,
            readings=hierarchy.readings,
            tempo_maps=hierarchy.tempo_maps,
        )

    def test_tempo_text_is_outside_structural_equality(self) -> None:
        plain = MetricHierarchy.from_sections([Tempo(bpm=120)])
        named = MetricHierarchy.from_sections([Tempo(bpm=120, text="Allegro")])
        assert plain == named

    def test_nested_and_flat_partitions_are_not_equal(self) -> None:
        nested_children = tuple(
            MetricNode(
                proportion=Fraction(1, 2),
                expansions=(
                    Expansion(
                        children=tuple(
                            MetricNode(proportion=Fraction(1, 3)) for _ in range(3)
                        ),
                        readings=frozenset({"r"}),
                    ),
                ),
            )
            for _ in range(2)
        )
        nested = MetricHierarchy(
            root=MetricNode(
                expansions=(
                    Expansion(children=nested_children, readings=frozenset({"r"})),
                )
            ),
            readings=(Reading(id="r", source="notation"),),
        )
        flat = MetricHierarchy(
            root=MetricNode(
                expansions=(
                    Expansion(
                        children=tuple(
                            MetricNode(proportion=Fraction(1, 6)) for _ in range(6)
                        ),
                        readings=frozenset({"r"}),
                    ),
                )
            ),
            readings=nested.readings,
        )

        assert nested != flat

    def test_reading_membership_participates_in_forest_equality(self) -> None:
        children = (MetricNode(proportion=Fraction(1)),)
        first = MetricHierarchy(
            root=MetricNode(
                expansions=(
                    Expansion(children=children, readings=frozenset({"first"})),
                )
            ),
            readings=(
                Reading(id="first", source="analysis"),
                Reading(id="second", source="analysis"),
            ),
        )
        second = MetricHierarchy(
            root=MetricNode(
                expansions=(
                    Expansion(children=children, readings=frozenset({"second"})),
                )
            ),
            readings=first.readings,
        )

        assert first != second

    def test_realization_and_reading_provenance_are_outside_equality(self) -> None:
        base = MetricHierarchy.from_sections([Tempo(bpm=120)])
        changed_reading = MetricHierarchy(
            root=base.root,
            readings=(
                Reading(
                    id=base.readings[0].id,
                    source=base.readings[0].source,
                    by="editor",
                    reinterprets="engraved",
                    level_names={1: "bar"},
                ),
            ),
            tempo_maps=base.tempo_maps,
        )
        extra = TempoMap(
            kind="observed",
            entries=(
                TempoEntry(at=Coordinate(Fraction(0), "quarters"), tempo=Tempo(bpm=90)),
            ),
            provenance={"by": "probe"},
        )

        assert base.readings[0].reinterprets is None
        assert changed_reading.readings[0].reinterprets == "engraved"
        assert changed_reading == base
        assert base.with_tempo_map(extra) == base
        assert len(base.with_tempo_map(extra).tempo_maps) == 2
        assert len(base.tempo_maps) == 1


class TestMetricHierarchyReadings:
    """Readings share matching partitions and retain divergent alternatives."""

    def test_with_reading_coalesces_an_agreeing_partition(self) -> None:
        children = (
            MetricNode(proportion=Fraction(1, 2)),
            MetricNode(proportion=Fraction(1, 2)),
        )
        hierarchy = MetricHierarchy(
            root=MetricNode(
                expansions=(
                    Expansion(children=children, readings=frozenset({"first"})),
                )
            ),
            readings=(Reading(id="first", source="analysis"),),
        )

        merged = hierarchy.with_reading(
            Reading(id="second", source="performance"),
            (Expansion(children=children, readings=frozenset()),),
        )

        assert len(merged.root.expansions) == 1
        assert merged.root.expansions[0].readings == frozenset({"first", "second"})
        assert merged.root.expansions[0].children[0] is children[0]
        assert hierarchy.root.expansions[0].readings == frozenset({"first"})

    def test_with_reading_retains_a_divergent_partition(self) -> None:
        halves = (
            MetricNode(proportion=Fraction(1, 2)),
            MetricNode(proportion=Fraction(1, 2)),
        )
        thirds = tuple(MetricNode(proportion=Fraction(1, 3)) for _ in range(3))
        hierarchy = MetricHierarchy(
            root=MetricNode(
                expansions=(Expansion(children=halves, readings=frozenset({"first"})),)
            ),
            readings=(Reading(id="first", source="analysis"),),
        )

        merged = hierarchy.with_reading(
            Reading(id="second", source="performance"),
            (Expansion(children=thirds, readings=frozenset()),),
        )

        assert len(merged.root.expansions) == 2
        assert merged.root.expansions[0].readings == frozenset({"first"})
        assert merged.root.expansions[1].readings == frozenset({"second"})
        assert merged.root.expansions[0].children == halves
        assert merged.root.expansions[1].children == thirds

    def test_policy_at_uses_only_the_named_reading(self) -> None:
        halves = Expansion(
            children=(
                MetricNode(proportion=Fraction(1, 2)),
                MetricNode(proportion=Fraction(1, 2)),
            ),
            readings=frozenset({"halves"}),
        )
        thirds = Expansion(
            children=tuple(MetricNode(proportion=Fraction(1, 3)) for _ in range(3)),
            readings=frozenset({"thirds"}),
        )
        hierarchy = MetricHierarchy(
            root=MetricNode(level=1, expansions=(halves, thirds)),
            readings=(
                Reading(id="halves", source="analysis"),
                Reading(id="thirds", source="analysis"),
            ),
        )

        assert hierarchy.root.expansions == (halves, thirds)
        assert hierarchy.policy_at("halves", Fraction(0)) == BeatPolicy(
            grouping=(1, 1), division=Fraction(1, 2)
        )
        assert hierarchy.policy_at("thirds", Fraction(0)) == BeatPolicy(
            grouping=(1, 1, 1), division=Fraction(1, 3)
        )

    def test_policy_at_rejects_unasserted_reading_and_physical_position(self) -> None:
        hierarchy = MetricHierarchy(
            root=MetricNode(
                expansions=(
                    Expansion(
                        children=(MetricNode(proportion=Fraction(1)),),
                        readings=frozenset({"asserted"}),
                    ),
                )
            ),
            readings=(
                Reading(id="asserted", source="analysis"),
                Reading(id="silent", source="analysis"),
            ),
        )

        with pytest.raises(ValueError, match="silent.*asserts no expansion"):
            hierarchy.policy_at("silent", Fraction(0))
        with pytest.raises(ValueError, match="seconds.*allowed units"):
            hierarchy.policy_at("asserted", Coordinate(Fraction(1, 2), "seconds"))

    def test_unknown_expansion_reading_is_rejected(self) -> None:
        root = MetricNode(
            expansions=(
                Expansion(
                    children=(MetricNode(proportion=Fraction(1)),),
                    readings=frozenset({"missing"}),
                ),
            )
        )
        with pytest.raises(ValueError, match="unknown reading id 'missing'"):
            MetricHierarchy(root=root, readings=())


class TestTempoRealizationValues:
    """Tempo-map values preserve exact, distinct, immutable source evidence."""

    def test_observation_states_are_distinct_and_round_trip(self) -> None:
        point = TempoEntry(observed=Coordinate(Fraction(1, 3), "seconds"))
        interval = TempoEntry(
            observed=Interval(
                Coordinate(Fraction(1, 3), "seconds"),
                Coordinate(Fraction(2, 3), "seconds"),
            )
        )
        undefined = TempoEntry(observation_undefined=True)
        unstated = TempoEntry()

        assert point.to_dict()["observed"]["type"] == "coordinate"
        assert interval.to_dict()["observed"]["type"] == "interval"
        assert undefined.to_dict()["observed"] is None
        assert undefined.to_dict()["observation_undefined"] is True
        assert unstated.to_dict()["observed"] is None
        assert unstated.to_dict()["observation_undefined"] is False
        assert len({point, interval, undefined, unstated}) == 4

        for entry in (point, interval, undefined, unstated):
            payload = json.loads(json.dumps(entry.to_dict()))
            restored = TempoEntry.from_dict(payload)
            assert restored == entry
            assert restored.to_dict() == payload

    def test_observation_cannot_be_present_and_explicitly_undefined(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="cannot be true"):
            TempoEntry(
                observed=Coordinate(Fraction(1), "seconds"),
                observation_undefined=True,
            )

    def test_symbolic_position_rejects_physical_unit(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="seconds.*allowed units"):
            TempoEntry(at=Coordinate(Fraction(3), "seconds"))

    def test_alternative_weights_are_exact_and_bounded(self) -> None:
        entry = TempoEntry(
            alternatives=((Coordinate(Fraction(1), "seconds"), Fraction(1, 3)),)
        )
        payload = json.loads(json.dumps(entry.to_dict()))

        assert entry.alternatives[0][1] == Fraction(1, 3)
        assert type(entry.alternatives[0][1]) is Fraction
        assert payload["alternatives"][0]["weight"] == rational_to_wire(Fraction(1, 3))
        assert TempoEntry.from_dict(payload) == entry

    @pytest.mark.parametrize(
        "weight",
        [float("nan"), float("inf"), Fraction(0), Fraction(-1), Fraction(2)],
    )
    def test_invalid_alternative_weight_is_rejected(self, weight: Real) -> None:
        with pytest.raises(
            pydantic.ValidationError,
            match="finite real number greater than zero and at most one",
        ):
            TempoEntry(alternatives=((Coordinate(Fraction(1), "seconds"), weight),))

    def test_provenance_and_level_names_are_immutable(self) -> None:
        tempo_map = TempoMap(
            kind="steady",
            entries=(),
            provenance={"nested": {"x": 1}},
        )
        reading = Reading(
            id="analysis",
            source="analysis",
            level_names={-1: "groove"},
        )

        with pytest.raises(TypeError):
            tempo_map.provenance["new"] = 2  # type: ignore[index]
        with pytest.raises(TypeError):
            tempo_map.provenance["nested"]["x"] = 2  # type: ignore[index]
        with pytest.raises(TypeError):
            reading.level_names[-1] = "changed"  # type: ignore[index]
        assert tempo_map.to_dict()["provenance"] == {"nested": {"x": 1}}
        assert reading.level_names[-1] == "groove"

    def test_non_json_provenance_is_rejected_at_construction(self) -> None:
        with pytest.raises(
            pydantic.ValidationError,
            match="key 'ratio'.*type Fraction",
        ):
            TempoMap(
                kind="indication",
                entries=(),
                provenance={"ratio": Fraction(1, 3)},
            )

    def test_non_default_members_appear_in_representations(self) -> None:
        observed = Coordinate(Fraction(2), "seconds")
        entry = TempoEntry(
            at=Coordinate(Fraction(1), "quarters"),
            tempo=Tempo(bpm=90),
            observed=observed,
            alternatives=((Coordinate(Fraction(3), "seconds"), Fraction(1)),),
            is_interpolated=True,
        )
        tempo_map = TempoMap(
            kind="steady", entries=(entry,), provenance={"by": "probe"}
        )
        reading = Reading(
            id="performed",
            source="performance",
            by="A. Player",
            reinterprets="notation",
            level_names={-1: "groove"},
        )
        node = MetricNode(
            level=0,
            proportion=Fraction(3, 8),
            expansions=(Expansion(children=(), readings=frozenset({"performed"})),),
        )

        assert "proportion=Fraction(3, 8)" in repr(node)
        assert f"observed={observed!r}" in repr(entry)
        assert "alternatives=" in repr(entry)
        assert "is_interpolated=True" in repr(entry)
        assert "provenance={'by': 'probe'}" in repr(tempo_map)
        assert "by='A. Player'" in repr(reading)
        assert "reinterprets='notation'" in repr(reading)
        assert "level_names={-1: 'groove'}" in repr(reading)


class TestBeatPolicyScalarEquality:
    """The ``BeatPolicy`` scalar itself keeps its pydantic name-aware equality."""

    def test_name_participates_in_scalar_equality(self) -> None:
        first = BeatPolicy(grouping=(1, 1, 1), division=Fraction(1), name="a")
        second = BeatPolicy(grouping=(1, 1, 1), division=Fraction(1), name="b")
        assert first != second

    def test_identical_policies_including_name_are_equal(self) -> None:
        first = BeatPolicy(grouping=(1, 1, 1), division=Fraction(1), name="a")
        second = BeatPolicy(grouping=(1, 1, 1), division=Fraction(1), name="a")
        assert first == second


class TestBeatPolicyAndMetricHierarchyWire:
    """Metric wire forms preserve authored units and complete forest values."""

    @pytest.mark.parametrize(
        "policy",
        [
            BeatPolicy(
                grouping=(1, 2),
                beat_size=Duration(Fraction(1, 3), TimeUnit.whole_note),
                name="whole-note spelling",
            ),
            BeatPolicy(
                grouping=(2, 1),
                beat_size=Duration(Fraction(1, 3), TimeUnit.quarters),
                name="quarters spelling",
            ),
            BeatPolicy(
                grouping=(3, 2),
                division=Fraction(1, 3),
                name="division spelling",
            ),
        ],
        ids=("whole-note", "quarters", "division"),
    )
    def test_policy_json_round_trip_preserves_full_scalar(
        self, policy: BeatPolicy
    ) -> None:
        payload = json.loads(json.dumps(policy.to_dict()))
        restored = BeatPolicy.from_dict(payload)
        assert restored == policy
        assert restored.to_dict() == payload
        assert payload["beat_size"]["number_type"] == "fraction"

    def test_metric_hierarchy_round_trip_preserves_forest_and_maps(self) -> None:
        hierarchy = MetricHierarchy(
            root=MetricNode(
                level=1,
                proportion=Fraction(1),
                expansions=(
                    Expansion(
                        children=(
                            MetricNode(level=0, proportion=Fraction(1, 3)),
                            MetricNode(level=0, proportion=Fraction(2, 3)),
                        ),
                        readings=frozenset({"performed"}),
                    ),
                ),
            ),
            readings=(
                Reading(id="notation", source="notation"),
                Reading(
                    id="performed",
                    source="performance",
                    reinterprets="notation",
                ),
            ),
            tempo_maps=(
                TempoMap(
                    kind="indication",
                    entries=(
                        TempoEntry(
                            at=Coordinate(Fraction(1, 3), "quarters"),
                            tempo=Tempo(bpm=Fraction(90)),
                        ),
                    ),
                    provenance={"source": "score"},
                ),
            ),
        )
        payload = json.loads(json.dumps(hierarchy.to_dict()))
        restored = MetricHierarchy.from_dict(payload)
        assert restored == hierarchy
        assert restored.to_dict() == payload
        assert restored.tempo_maps == hierarchy.tempo_maps
        assert restored.root.proportion == Fraction(1)
        assert restored.root.expansions[0].children[0].proportion == Fraction(1, 3)
        assert restored.readings[1].reinterprets == "notation"

    def test_timeline_payload_carries_the_same_hierarchy_wire(self) -> None:
        hierarchy = MetricHierarchy(
            root=MetricNode(
                level=1,
                proportion=Fraction(1),
                expansions=(
                    Expansion(
                        children=(
                            MetricNode(level=0, proportion=Fraction(1, 3)),
                            MetricNode(level=0, proportion=Fraction(2, 3)),
                        ),
                        readings=frozenset({"notation"}),
                    ),
                ),
            ),
            readings=(Reading(id="notation", source="notation"),),
            tempo_maps=(
                TempoMap(
                    kind="indication",
                    entries=(
                        TempoEntry(
                            at=Coordinate(Fraction(1, 3), "quarters"),
                            tempo=Tempo(bpm=Fraction(90)),
                        ),
                    ),
                    provenance={"source": "score"},
                ),
            ),
        )
        timeline = Timeline(
            length=Fraction(3),
            unit=TimeUnit.quarters,
            uid="metric_wire",
        )
        timeline.add_metric_hierarchy(hierarchy)

        payload = json.loads(json.dumps(timeline.to_dict(events=False)))
        restored = Timeline.from_dict(payload)

        assert restored.metric_hierarchy == hierarchy
        assert restored.metric_hierarchy.to_dict() == hierarchy.to_dict()
        assert restored.metric_hierarchy.root.expansions[0].children[0].proportion == (
            Fraction(1, 3)
        )
        assert restored.metric_hierarchy.tempo_maps == hierarchy.tempo_maps
        assert restored.to_dict(events=False) == payload
        assert "events" not in payload


# endregion


# region (c) Measure scalar


class TestMeasureScalar:
    """The ``Measure`` scalar's field set and map-derived arithmetic."""

    def test_constructs_with_no_arguments(self) -> None:
        measure = Measure()
        assert measure.id is None
        assert measure.count is None
        assert measure.qstamp is None
        assert measure.actual_length is None

    def test_field_set_is_exactly_the_standard_plus_volta(self) -> None:
        assert set(Measure.model_fields) == {
            "id",
            "count",
            "qstamp",
            "number",
            "name",
            "time_signature",
            "nominal_length",
            "actual_length",
            "start_repeat",
            "end_repeat",
            "next",
            "volta",
        }

    def test_is_frozen(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            Measure().count = 5  # type: ignore[misc]

    def test_count_and_qstamp_are_prefix_sums_when_omitted(self) -> None:
        measure_map = MeasureMap(
            [
                Measure(actual_length=Fraction(3)),
                Measure(actual_length=Fraction(3)),
                Measure(actual_length=Fraction(2)),
            ]
        )
        assert [measure.count for measure in measure_map] == [1, 2, 3]
        assert [measure.qstamp for measure in measure_map] == [
            Fraction(0),
            Fraction(3),
            Fraction(6),
        ]
        assert [measure.id for measure in measure_map] == ["m1", "m2", "m3"]

    def test_disagreeing_count_warns_and_is_corrected(self) -> None:
        with pytest.warns(UserWarning, match="supplies count 5"):
            measure_map = MeasureMap(
                [
                    Measure(count=5, actual_length=Fraction(3)),
                    Measure(actual_length=Fraction(3)),
                ]
            )
        # The deviation is announced, not swallowed: the printed-order value wins.
        assert [measure.count for measure in measure_map] == [1, 2]

    def test_disagreeing_qstamp_warns_and_is_corrected(self) -> None:
        with pytest.warns(UserWarning, match="supplies qstamp 99"):
            measure_map = MeasureMap(
                [
                    Measure(actual_length=Fraction(3)),
                    Measure(qstamp=Fraction(99), actual_length=Fraction(3)),
                ]
            )
        assert [measure.qstamp for measure in measure_map] == [
            Fraction(0),
            Fraction(3),
        ]


class TestMeasureWire:
    """Every concrete measure class survives JSON with exact fractions."""

    @pytest.mark.parametrize(
        "measure_class",
        [
            RegularMeasure,
            IrregularMeasure,
            SplitRegularMeasure,
            SplitIrregularMeasure,
            MeasureConstituent,
            CadenzaMeasure,
        ],
    )
    def test_concrete_class_and_all_fields_round_trip(
        self, measure_class: type[Measure]
    ) -> None:
        kwargs = {
            "id": "m7",
            "count": 7,
            "qstamp": Fraction(2, 3),
            "number": 5,
            "name": "5a",
            "time_signature": "7/9",
            "nominal_length": Fraction(7, 3),
            "actual_length": Fraction(5, 3),
            "start_repeat": True,
            "end_repeat": True,
            "next": ("m8", "m11"),
            "volta": 2,
        }
        if measure_class is MeasureConstituent:
            kwargs["offset_within_measure"] = Fraction(1, 3)
        measure = measure_class(**kwargs)
        payload = json.loads(json.dumps(measure.to_dict()))
        restored = Measure.from_dict(payload)
        assert type(restored) is measure_class
        assert restored == measure
        assert restored.qstamp == Fraction(2, 3)
        assert restored.nominal_length == Fraction(7, 3)
        assert restored.actual_length == Fraction(5, 3)
        if isinstance(restored, MeasureConstituent):
            assert restored.offset_within_measure == Fraction(1, 3)
        assert restored.to_dict() == payload

    def test_unknown_class_tag_names_known_classes(self) -> None:
        with pytest.raises(
            ValueError,
            match=r"Unknown or missing Measure class 'UnknownMeasure'.*RegularMeasure",
        ):
            Measure.from_dict({"class": "UnknownMeasure"})

    def test_missing_class_tag_names_known_classes(self) -> None:
        payload = RegularMeasure(id="m1").to_dict()
        del payload["class"]
        with pytest.raises(
            ValueError,
            match=r"Unknown or missing Measure class None.*RegularMeasure",
        ):
            Measure.from_dict(payload)

    def test_undeclared_payload_key_is_rejected_by_name(self) -> None:
        payload = RegularMeasure(id="m1").to_dict()
        payload["offset_within_measure"] = rational_to_wire(Fraction(1, 3))
        with pytest.raises(
            ValueError,
            match=(
                "Measure class 'RegularMeasure' does not declare the keys: "
                "offset_within_measure"
            ),
        ):
            Measure.from_dict(payload)

    def test_subclass_rejects_a_different_tag(self) -> None:
        with pytest.raises(
            ValueError,
            match="does not match receiving subclass 'RegularMeasure'",
        ):
            RegularMeasure.from_dict(IrregularMeasure().to_dict())


# endregion
