"""Immutable measure maps and the structural hierarchies built over them."""

from __future__ import annotations

import warnings
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING, Any

from timetoalign.core import (
    BeatPolicy,
    CadenzaMeasure,
    IrregularMeasure,
    Measure,
    MeasureConstituent,
    RegularMeasure,
)
from timetoalign.core.time import wire_to_rational
from timetoalign.timelines.flow import AtomicSection

if TYPE_CHECKING:
    from timetoalign.loader.score.stores.measures import MeasureData


def _exact_quarters(value: Any) -> Fraction:
    """Read one exact quarter-note value without ratio guessing."""
    if value is None:
        raise ValueError("Measure row states no actual length")
    if isinstance(value, dict):
        return Fraction(wire_to_rational(value))
    if hasattr(value, "value"):
        return Fraction(value.value)
    return value if isinstance(value, Fraction) else Fraction(value)


def _parse_next(value: Any) -> tuple[int, ...] | None:
    """Read successor counts from a sequence or comma-separated spelling."""
    if value is None or value == "":
        return None
    if isinstance(value, (list, tuple)):
        return tuple(int(entry) for entry in value)
    text = str(value).strip().strip("()[]")
    parts = [part.strip() for part in text.split(",") if part.strip()]
    return tuple(int(part) for part in parts) or None


class MeasureMap:
    """An immutable sequence of measures in printed order."""

    @classmethod
    def from_measure_data(cls, data: MeasureData) -> MeasureMap:
        """Build the canonical measure structure described by loaded rows."""
        return cls._from_measure_rows(data)

    @classmethod
    def _from_measure_rows(cls, source: Iterable[Mapping[str, Any]]) -> MeasureMap:
        """Build a measure map from normalized loader facts."""
        rows = list(source)
        if not rows:
            raise ValueError("Cannot build a MeasureMap from empty measure data")

        measures: list[Measure] = []
        current_signature: str | None = None
        for index, row in enumerate(rows, start=1):
            signature = row.get("timesig")
            if signature:
                current_signature = str(signature)
            actual_length = _exact_quarters(row.get("duration"))
            nominal_length = (
                BeatPolicy.from_time_signature(current_signature).span
                if current_signature
                else actual_length
            )
            count = int(row.get("mc") or index)
            label = str(row.get("mn") if row.get("mn") is not None else count)
            raw_number = row.get("mn_int")
            number = int(raw_number) if raw_number is not None else count
            offset_raw = row.get("mc_offset")
            offset = (
                Fraction(0) if offset_raw in (None, "") else Fraction(offset_raw) * 4
            )
            successors = _parse_next(row.get("next"))
            next_ids = (
                tuple(f"m{successor}" for successor in successors if successor != -1)
                if successors
                else None
            )
            common = dict(
                id=f"m{count}",
                count=count,
                qstamp=_exact_quarters(row.get("start")),
                number=number,
                name=label,
                time_signature=current_signature,
                nominal_length=nominal_length,
                actual_length=actual_length,
                start_repeat=bool(row.get("start_repeat", False)),
                end_repeat=bool(row.get("end_repeat", False)),
                next=next_ids or None,
                volta=row.get("volta"),
            )
            if offset:
                measure = MeasureConstituent(
                    **common,
                    offset_within_measure=offset,
                )
            elif current_signature and current_signature.lower() == "cadenza":
                measure = CadenzaMeasure(**common)
            elif actual_length == nominal_length:
                measure = RegularMeasure(**common)
            else:
                measure = IrregularMeasure(**common)
            measures.append(measure)
        return cls(measures)

    @classmethod
    def _from_normalized(cls, measures: Iterable[Measure]) -> MeasureMap:
        """Build a view over measures already normalized by a parent map."""
        instance = cls.__new__(cls)
        instance._measures = tuple(measures)
        return instance

    def __init__(self, measures: Iterable[Measure]) -> None:
        source = tuple(measures)
        normalized: list[Measure] = []
        running: Fraction | None = Fraction(0)
        for count, measure in enumerate(source, start=1):
            computed_qstamp = running
            if measure.count is not None and measure.count != count:
                warnings.warn(
                    f"Measure {measure.id or count!r} supplies count {measure.count}, "
                    f"but printed order computes {count}",
                    stacklevel=2,
                )
            if (
                computed_qstamp is not None
                and measure.qstamp is not None
                and measure.qstamp != computed_qstamp
            ):
                warnings.warn(
                    f"Measure {measure.id or count!r} supplies qstamp {measure.qstamp}, "
                    f"but prefix-summing actual lengths computes {computed_qstamp}",
                    stacklevel=2,
                )
            updates: dict[str, Any] = {
                "id": measure.id or f"m{count}",
                "count": count,
            }
            if computed_qstamp is not None:
                updates["qstamp"] = computed_qstamp
            normalized.append(measure.model_copy(update=updates))
            if running is not None:
                running = (
                    running + measure.actual_length
                    if measure.actual_length is not None
                    else None
                )
        ids = [measure.id for measure in normalized]
        if len(ids) != len(set(ids)):
            raise ValueError("Measure IDs must be unique within a MeasureMap")
        self._measures = tuple(normalized)

    def __iter__(self) -> Iterator[Measure]:
        return iter(self._measures)

    def __len__(self) -> int:
        return len(self._measures)

    def __getitem__(self, index: int | slice) -> Measure | tuple[Measure, ...]:
        return self._measures[index]

    @property
    def measures(self) -> tuple[Measure, ...]:
        """Measures in printed order."""
        return self._measures

    @property
    def total_actual_length(self) -> Fraction | None:
        """Sum of actual lengths, or ``None`` when any length is abstract."""
        if any(measure.actual_length is None for measure in self._measures):
            return None
        return sum(
            (
                measure.actual_length
                for measure in self._measures
                if measure.actual_length is not None
            ),
            Fraction(0),
        )

    def by_id(self, measure_id: str) -> Measure:
        """Return the uniquely identified measure."""
        for measure in self._measures:
            if measure.id == measure_id:
                return measure
        raise KeyError(measure_id)


class SectionHierarchy:
    """A section partition whose leaves carry immutable measure-map segments."""

    @classmethod
    def from_measures(
        cls,
        source: (
            Iterable[Measure]
            | Iterable[Iterable[Measure]]
            | Mapping[str, Any]
            | MeasureMap
        ),
    ) -> SectionHierarchy:
        """Build sections from flat, nested, mapped, or already-mapped measures."""
        if isinstance(source, MeasureMap):
            named_groups = [(None, source.measures)]
        elif isinstance(source, Mapping):
            named_groups = [(str(name), tuple(group)) for name, group in source.items()]
        else:
            values = tuple(source)
            if not values or isinstance(values[0], Measure):
                named_groups = [(None, values)]
            else:
                named_groups = [(None, tuple(group)) for group in values]
        return cls._from_groups(named_groups)

    @classmethod
    def from_measure_counts(
        cls,
        source: int | Iterable[int] | Mapping[str, int] | Iterable[tuple[str, int]],
    ) -> SectionHierarchy:
        """Build sections containing the requested counts of abstract measures."""
        if isinstance(source, int):
            entries: list[tuple[str | None, int]] = [(None, source)]
        elif isinstance(source, Mapping):
            entries = [(str(name), int(count)) for name, count in source.items()]
        else:
            consumed = tuple(source)
            entries = []
            for entry in consumed:
                if isinstance(entry, tuple):
                    name, count = entry
                    entries.append((str(name), int(count)))
                else:
                    entries.append((None, int(entry)))
        return cls._from_groups(
            [(name, tuple(Measure() for _ in range(count))) for name, count in entries]
        )

    @classmethod
    def _from_groups(
        cls, groups: Iterable[tuple[str | None, Iterable[Measure]]]
    ) -> SectionHierarchy:
        materialized = [(name, tuple(measures)) for name, measures in groups]
        flat = MeasureMap(
            measure for _, measures in materialized for measure in measures
        )
        leaves: list[AtomicSection] = []
        start = 0
        for index, (name, measures) in enumerate(materialized, start=1):
            end = start + len(measures)
            segment = MeasureMap._from_normalized(flat.measures[start:end])
            leaves.append(
                AtomicSection(
                    id=f"sec{index}",
                    mc_start=start + 1,
                    mc_end=end + 1,
                    measure_map=segment,
                    name=name,
                )
            )
            start = end
        return cls(flat, leaves)

    def __init__(
        self, measure_map: MeasureMap, sections: Iterable[AtomicSection]
    ) -> None:
        self._measure_map = measure_map
        self._sections = tuple(sections)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SectionHierarchy):
            return NotImplemented
        section_shape_matches = [section.n_measures for section in self._sections] == [
            section.n_measures for section in other._sections
        ]
        return (
            section_shape_matches
            and self._measure_map.measures == other._measure_map.measures
        )

    @property
    def measure_map(self) -> MeasureMap:
        """The whole work's measure map."""
        return self._measure_map

    @property
    def n_sections(self) -> int:
        """Number of leaf sections."""
        return len(self._sections)

    @property
    def n_measures(self) -> int:
        """Total number of measures."""
        return len(self._measure_map)

    @property
    def sections(self) -> list[AtomicSection]:
        """Leaf sections in printed order."""
        return list(self._sections)


@dataclass(frozen=True)
class MetricHierarchyComponent:
    """A measure-anchored metrical change point."""

    first: int
    policy: BeatPolicy
    hypermeter: tuple[int, ...] | None = None


class MetricHierarchy:
    """Beat policies grouped by section."""

    @classmethod
    def from_beat_policies(cls, policies: Mapping[str, BeatPolicy]) -> MetricHierarchy:
        """Create a hierarchy with named policies ready for section authoring."""
        return cls((), policies=dict(policies))

    @classmethod
    def from_sections(
        cls, sections: list[BeatPolicy | list[BeatPolicy]]
    ) -> MetricHierarchy:
        """Create a hierarchy directly from section policy groups."""
        normalized = [
            (section,) if isinstance(section, BeatPolicy) else tuple(section)
            for section in sections
        ]
        return cls(normalized)

    def __init__(
        self,
        sections: Iterable[Iterable[BeatPolicy]],
        *,
        policies: Mapping[str, BeatPolicy] | None = None,
    ) -> None:
        self._sections = tuple(tuple(section) for section in sections)
        self._policies = dict(policies or {})

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MetricHierarchy):
            return NotImplemented

        def shape(
            hierarchy: MetricHierarchy,
        ) -> tuple[tuple[tuple[Any, Any], ...], ...]:
            return tuple(
                tuple((policy.beat_size, policy.bpm) for policy in section)
                for section in hierarchy._sections
            )

        return shape(self) == shape(other)

    @property
    def sections(self) -> tuple[tuple[BeatPolicy, ...], ...]:
        """Policies grouped by section."""
        return self._sections

    def create_sections(self, spec: list[str | list[str]]) -> None:
        """Group registered policies according to a section specification."""
        self._sections = tuple(
            tuple(
                self._policies[name]
                for name in (entry if isinstance(entry, list) else [entry])
            )
            for entry in spec
        )
