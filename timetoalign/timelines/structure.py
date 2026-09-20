"""Immutable measure maps and the structural hierarchies built over them."""

from __future__ import annotations

import json
import warnings
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from fractions import Fraction
from math import gcd, isfinite, lcm
from numbers import Real
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from timetoalign.core import (
    BeatPolicy,
    CadenzaMeasure,
    Coordinate,
    Domain,
    Interval,
    IrregularMeasure,
    Measure,
    MeasureConstituent,
    RegularMeasure,
    Tempo,
    TimeUnit,
)
from timetoalign.core.retrieval import coordinate_from_wire_entry, coordinate_wire_entry
from timetoalign.core.time import rational_to_wire, wire_to_rational
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
    def from_dict(cls, data: dict[str, Any]) -> MeasureMap:
        """Restore a map through its validating public constructor."""
        return cls(Measure.from_dict(measure) for measure in data["measures"])

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
        ids = [
            measure.id or f"m{count}" for count, measure in enumerate(source, start=1)
        ]
        if len(ids) != len(set(ids)):
            raise ValueError("Measure IDs must be unique within a MeasureMap")
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
        self._measures = tuple(normalized)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MeasureMap):
            return NotImplemented
        return self.measures == other.measures

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

    def to_dict(self) -> dict[str, Any]:
        """Return this map as a JSON-safe sequence of measure payloads."""
        return {"measures": [measure.to_dict() for measure in self._measures]}


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
            return cls.from_measure_map(source)
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
    def from_measure_map(
        cls,
        measure_map: MeasureMap,
        *,
        counts: Iterable[int] | None = None,
    ) -> SectionHierarchy:
        """Partition an existing map without rebuilding its measures.

        Args:
            measure_map: The map retained as the hierarchy's whole-work map.
            counts: Consecutive leaf sizes. ``None`` creates one leaf.

        Returns:
            A hierarchy whose ``measure_map`` is the supplied object.

        Raises:
            ValueError: If the counts do not sum to the map length.
        """
        section_counts = (len(measure_map),) if counts is None else tuple(counts)
        if any(count < 0 for count in section_counts) or sum(section_counts) != len(
            measure_map
        ):
            raise ValueError(
                f"Section counts must sum to MeasureMap length {len(measure_map)}, "
                f"got {section_counts}"
            )
        leaves: list[AtomicSection] = []
        start = 0
        for index, count in enumerate(section_counts, start=1):
            end = start + count
            leaves.append(
                AtomicSection(
                    id=f"sec{index}",
                    mc_start=start + 1,
                    mc_end=end + 1,
                    measure_map=MeasureMap._from_normalized(
                        measure_map.measures[start:end]
                    ),
                )
            )
            start = end
        return cls(measure_map, leaves)

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


def _coordinate_to_wire(value: Coordinate) -> dict[str, Any]:
    """Encode a coordinate through the shared typed wire contract."""
    return dict(coordinate_wire_entry(value))


def _coordinate_from_wire(value: Mapping[str, Any]) -> Coordinate:
    """Restore a coordinate through the shared typed wire contract."""
    return coordinate_from_wire_entry(value)


def _unsupported_json_type(value: Any, seen: set[int] | None = None) -> type | None:
    """Return the first type that the standard JSON encoder cannot carry."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return None
    if seen is None:
        seen = set()
    identity = id(value)
    if identity in seen:
        return type(value)
    seen.add(identity)
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                return type(key)
            unsupported = _unsupported_json_type(child, seen)
            if unsupported is not None:
                return unsupported
        return None
    if isinstance(value, (list, tuple)):
        for child in value:
            unsupported = _unsupported_json_type(child, seen)
            if unsupported is not None:
                return unsupported
        return None
    return type(value)


def _require_physical_unit(unit: TimeUnit, member: str) -> None:
    """Refuse an observation coordinate that is not on the physical axis.

    Args:
        unit: Unit of the coordinate given for that member.
        member: Name of the ``TempoEntry`` member being validated.

    Raises:
        ValueError: If *unit* does not belong to the physical domain.
    """
    if unit.domain is Domain.physical:
        return
    allowed = ", ".join(
        sorted(
            candidate.value
            for candidate in TimeUnit
            if candidate.domain is Domain.physical
        )
    )
    raise ValueError(
        f"TempoEntry {member} unit {unit.value!r} is not physical; "
        f"allowed units: {allowed}"
    )


def _freeze_json(value: Any) -> Any:
    """Return an immutable copy of a JSON-compatible value."""
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze_json(child) for key, child in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(child) for child in value)
    return value


def _thaw_json(value: Any) -> Any:
    """Return a JSON-encodable copy of an immutable provenance value."""
    if isinstance(value, Mapping):
        return {key: _thaw_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(child) for child in value]
    return value


class TempoEntry(BaseModel):
    """One optionally positioned symbolic-axis row in a tempo map.

    Attributes:
        at: Exact symbolic position, when stated by the source.
        tempo: Optional rate law stated at that position.
        observed: Optional physical point or support interval.
        observation_undefined: Whether the source explicitly states no onset.
        alternatives: Weighted alternative physical positions.
        is_interpolated: Whether the symbolic position was derived.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    at: Coordinate | None = None
    tempo: Tempo | None = None
    observed: Coordinate | Interval | None = None
    observation_undefined: bool = False
    alternatives: tuple[tuple[Coordinate, Fraction], ...] = ()
    is_interpolated: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TempoEntry:
        """Restore a tempo entry from its JSON wire representation.

        Args:
            data: JSON-safe tempo-entry dictionary.

        Returns:
            The restored tempo entry.
        """
        observed_data = data.get("observed")
        observed: Coordinate | Interval | None
        if observed_data is None:
            observed = None
        elif observed_data["type"] == "coordinate":
            observed = _coordinate_from_wire(observed_data["value"])
        elif observed_data["type"] == "interval":
            observed = Interval(
                start=_coordinate_from_wire(observed_data["start"]),
                end=_coordinate_from_wire(observed_data["end"]),
            )
        else:
            raise ValueError(
                f"Unknown tempo observation type {observed_data['type']!r}"
            )
        return cls(
            at=(None if data.get("at") is None else _coordinate_from_wire(data["at"])),
            tempo=(
                None if data.get("tempo") is None else Tempo.from_dict(data["tempo"])
            ),
            observed=observed,
            observation_undefined=bool(data.get("observation_undefined", False)),
            alternatives=tuple(
                (
                    _coordinate_from_wire(item["at"]),
                    Fraction(wire_to_rational(item["weight"])),
                )
                for item in data.get("alternatives", [])
            ),
            is_interpolated=bool(data.get("is_interpolated", False)),
        )

    @field_validator("at")
    @classmethod
    def _validate_symbolic_position(cls, value: Coordinate | None) -> Coordinate | None:
        if value is None or value.unit.domain is Domain.logical:
            return value
        allowed = ", ".join(
            sorted(unit.value for unit in TimeUnit if unit.domain is Domain.logical)
        )
        raise ValueError(
            f"TempoEntry at unit {value.unit.value!r} is not symbolic; "
            f"allowed units: {allowed}"
        )

    @field_validator("observed")
    @classmethod
    def _validate_physical_observation(
        cls, value: Coordinate | Interval | None
    ) -> Coordinate | Interval | None:
        if isinstance(value, Interval):
            _require_physical_unit(value.start.unit, "observed")
            _require_physical_unit(value.end.unit, "observed")
        elif value is not None:
            _require_physical_unit(value.unit, "observed")
        return value

    @field_validator("alternatives", mode="after")
    @classmethod
    def _validate_physical_alternatives(
        cls, value: tuple[tuple[Coordinate, Fraction], ...]
    ) -> tuple[tuple[Coordinate, Fraction], ...]:
        for at, _weight in value:
            _require_physical_unit(at.unit, "alternative")
        return value

    @field_validator("alternatives", mode="before")
    @classmethod
    def _coerce_and_validate_weights(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        normalized: list[tuple[object, Fraction]] = []
        for item in value:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                return value
            at, weight = item
            if (
                isinstance(weight, bool)
                or not isinstance(weight, Real)
                or weight <= 0
                or weight > 1
                or not isfinite(float(weight))
            ):
                raise ValueError(
                    "TempoEntry alternative weight must be a finite real number "
                    "greater than zero and at most one"
                )
            normalized.append((at, Fraction(weight)))
        return tuple(normalized)

    @model_validator(mode="after")
    def _validate_observation_state(self) -> TempoEntry:
        if self.observation_undefined and self.observed is not None:
            raise ValueError(
                "TempoEntry observation_undefined cannot be true when observed is set"
            )
        return self

    def __repr__(self) -> str:
        parts: list[str] = []
        if self.at is not None:
            parts.append(f"at={self.at!r}")
        if self.tempo is not None:
            parts.append(f"tempo={self.tempo!r}")
        if self.observed is not None:
            parts.append(f"observed={self.observed!r}")
        if self.observation_undefined:
            parts.append("observation_undefined=True")
        if self.alternatives:
            parts.append(f"alternatives={self.alternatives!r}")
        if self.is_interpolated:
            parts.append("is_interpolated=True")
        return f"TempoEntry({', '.join(parts)})"

    def to_dict(self) -> dict[str, Any]:
        """Return this entry as a JSON-safe wire dictionary.

        Returns:
            A dictionary retaining typed coordinates and exact tempo values.
        """
        observed: dict[str, Any] | None
        if self.observed is None:
            observed = None
        elif isinstance(self.observed, Interval):
            observed = {
                "type": "interval",
                "start": _coordinate_to_wire(self.observed.start),
                "end": _coordinate_to_wire(self.observed.end),
            }
        else:
            observed = {
                "type": "coordinate",
                "value": _coordinate_to_wire(self.observed),
            }
        return {
            "at": None if self.at is None else _coordinate_to_wire(self.at),
            "tempo": None if self.tempo is None else self.tempo.to_dict(),
            "observed": observed,
            "observation_undefined": self.observation_undefined,
            "alternatives": [
                {"at": _coordinate_to_wire(at), "weight": rational_to_wire(weight)}
                for at, weight in self.alternatives
            ],
            "is_interpolated": self.is_interpolated,
        }


class TempoMap(BaseModel):
    """An independent sequence of tempo facts from one source.

    The ``steady`` kind declares that entries are anchor-and-rate generators
    which abut; consumers use the kind rather than the producing format's
    name to select that rule.

    Attributes:
        kind: Behaviour of the map's entries.
        entries: Tempo facts in source order.
        provenance: Immutable JSON-compatible source metadata.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    kind: Literal["indication", "steady", "observed", "modelled"]
    entries: tuple[TempoEntry, ...]
    provenance: Mapping[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TempoMap:
        """Restore a tempo map from its JSON wire representation.

        Args:
            data: JSON-safe tempo-map dictionary.

        Returns:
            The restored tempo map.
        """
        return cls(
            kind=data["kind"],
            entries=tuple(TempoEntry.from_dict(entry) for entry in data["entries"]),
            provenance=dict(data["provenance"]),
        )

    @field_validator("provenance", mode="after")
    @classmethod
    def _validate_and_freeze_provenance(
        cls, value: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        for key, item in value.items():
            unsupported = _unsupported_json_type(item)
            try:
                json.dumps(item, allow_nan=False)
            except (TypeError, ValueError):
                value_type = unsupported or type(item)
                raise ValueError(
                    f"TempoMap provenance key {key!r} has a non-JSON-serializable "
                    f"value of type {value_type.__name__}"
                ) from None
        return MappingProxyType(
            {key: _freeze_json(item) for key, item in value.items()}
        )

    def __repr__(self) -> str:
        parts = [f"kind={self.kind!r}", f"entries={len(self.entries)}"]
        if self.provenance:
            parts.append(f"provenance={_thaw_json(self.provenance)!r}")
        return f"TempoMap({', '.join(parts)})"

    def to_dict(self) -> dict[str, Any]:
        """Return this map as a JSON-safe wire dictionary.

        Returns:
            A dictionary retaining entries and provenance unchanged.
        """
        return {
            "kind": self.kind,
            "entries": [entry.to_dict() for entry in self.entries],
            "provenance": _thaw_json(self.provenance),
        }


class MetricNode(BaseModel):
    """A metrical timespan with alternative attributed partitions.

    Attributes:
        level: Stated metrical level, with pulse at zero and groove below zero.
        proportion: Exact share of the parent span, when stated.
        expansions: Alternative partitions of this span.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    level: int | None = None
    proportion: Fraction | None = None
    expansions: tuple[Expansion, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetricNode:
        """Restore a metric node from its JSON wire representation.

        Args:
            data: JSON-safe metric-node dictionary.

        Returns:
            The restored node and all descendant expansions.
        """
        return cls(
            level=data.get("level"),
            proportion=(
                None
                if data.get("proportion") is None
                else Fraction(wire_to_rational(data["proportion"]))
            ),
            expansions=tuple(
                Expansion.from_dict(expansion) for expansion in data["expansions"]
            ),
        )

    def __repr__(self) -> str:
        parts: list[str] = []
        if self.level is not None:
            parts.append(f"level={self.level}")
        if self.proportion is not None:
            parts.append(f"proportion={self.proportion!r}")
        if self.expansions:
            parts.append(f"expansions={len(self.expansions)}")
        return f"MetricNode({', '.join(parts)})"

    def to_dict(self) -> dict[str, Any]:
        """Return this node as a JSON-safe recursive wire dictionary.

        Returns:
            A dictionary retaining exact proportions and all alternatives.
        """
        return {
            "level": self.level,
            "proportion": (
                None if self.proportion is None else rational_to_wire(self.proportion)
            ),
            "expansions": [expansion.to_dict() for expansion in self.expansions],
        }


class Expansion(BaseModel):
    """One partition of a metric node, attributed to readings.

    Attributes:
        children: Ordered child timespans forming the partition.
        readings: Reading identifiers which assert the partition.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    children: tuple[MetricNode, ...]
    readings: frozenset[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Expansion:
        """Restore an expansion from its JSON wire representation.

        Args:
            data: JSON-safe expansion dictionary.

        Returns:
            The restored attributed partition.
        """
        return cls(
            children=tuple(MetricNode.from_dict(child) for child in data["children"]),
            readings=frozenset(data["readings"]),
        )

    def __repr__(self) -> str:
        return (
            f"Expansion(children={len(self.children)}, "
            f"readings={sorted(self.readings)!r})"
        )

    def to_dict(self) -> dict[str, Any]:
        """Return this expansion as a JSON-safe wire dictionary.

        Returns:
            A dictionary retaining children and sorted reading identifiers.
        """
        return {
            "children": [child.to_dict() for child in self.children],
            "readings": sorted(self.readings),
        }


class Reading(BaseModel):
    """Provenance and vocabulary for one consistent forest reading.

    Attributes:
        id: Identifier used by attributed expansions.
        source: Epistemic source of the reading.
        by: Optional author or system name.
        reinterprets: Optional identifier of a prior reading.
        level_names: Reading-local names for metrical levels.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    id: str
    source: Literal["notation", "performance", "analysis", "algorithm"]
    by: str | None = None
    reinterprets: str | None = None
    level_names: Mapping[int, str] = Field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Reading:
        """Restore reading provenance from its JSON wire representation.

        Args:
            data: JSON-safe reading dictionary.

        Returns:
            The restored reading.
        """
        return cls(
            id=data["id"],
            source=data["source"],
            by=data.get("by"),
            reinterprets=data.get("reinterprets"),
            level_names={
                int(level): name for level, name in data["level_names"].items()
            },
        )

    @field_validator("level_names", mode="after")
    @classmethod
    def _freeze_level_names(cls, value: Mapping[int, str]) -> Mapping[int, str]:
        return MappingProxyType(dict(value))

    def __repr__(self) -> str:
        parts = [f"id={self.id!r}", f"source={self.source!r}"]
        if self.by is not None:
            parts.append(f"by={self.by!r}")
        if self.reinterprets is not None:
            parts.append(f"reinterprets={self.reinterprets!r}")
        if self.level_names:
            parts.append(f"level_names={dict(self.level_names)!r}")
        return f"Reading({', '.join(parts)})"

    def to_dict(self) -> dict[str, Any]:
        """Return this reading as a JSON-safe wire dictionary.

        Returns:
            A dictionary retaining provenance and level vocabulary.
        """
        return {
            "id": self.id,
            "source": self.source,
            "by": self.by,
            "reinterprets": self.reinterprets,
            "level_names": {
                str(level): name for level, name in self.level_names.items()
            },
        }


MetricNode.model_rebuild()


@dataclass(frozen=True, eq=False, kw_only=True)
class MetricHierarchy:
    """One packed metrical forest with independent tempo realizations.

    Attributes:
        root: Node spanning the complete symbolic extent.
        readings: Provenance records for attributed structural readings.
        tempo_maps: Independent collections of tempo and observation facts.
    """

    root: MetricNode
    readings: tuple[Reading, ...] = ()
    tempo_maps: tuple[TempoMap, ...] = ()

    __hash__ = None

    @classmethod
    def from_sections(
        cls, sections: Iterable[Tempo | Iterable[Tempo]]
    ) -> MetricHierarchy:
        """Build the authored abstract hierarchy from tempo-bearing sections.

        Args:
            sections: Each authored section as one tempo statement or an
                iterable of tempo statements.

        Returns:
            A hierarchy with one notation reading, one root partition, and
            one indication tempo map containing every statement in order.
        """
        normalized = tuple(
            (section,) if isinstance(section, Tempo) else tuple(section)
            for section in sections
        )
        if any(
            not isinstance(tempo, Tempo) for section in normalized for tempo in section
        ):
            raise TypeError("MetricHierarchy sections must contain Tempo values")
        reading = Reading(id="notation", source="notation")
        children = tuple(MetricNode() for _ in normalized)
        root = MetricNode(
            expansions=(
                Expansion(children=children, readings=frozenset({reading.id})),
            ),
        )
        entries = tuple(
            TempoEntry(tempo=tempo) for section in normalized for tempo in section
        )
        tempo_map = TempoMap(kind="indication", entries=entries, provenance={})
        return cls(root=root, readings=(reading,), tempo_maps=(tempo_map,))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetricHierarchy:
        """Restore a packed forest and its independent metadata.

        Args:
            data: JSON-safe hierarchy dictionary.

        Returns:
            The restored immutable hierarchy.
        """
        return cls(
            root=MetricNode.from_dict(data["root"]),
            readings=tuple(Reading.from_dict(item) for item in data["readings"]),
            tempo_maps=tuple(TempoMap.from_dict(item) for item in data["tempo_maps"]),
        )

    def __post_init__(self) -> None:
        known = {reading.id for reading in self.readings}

        def validate(node: MetricNode) -> None:
            for expansion in node.expansions:
                for reading_id in expansion.readings:
                    if reading_id not in known:
                        raise ValueError(
                            f"Metric expansion names unknown reading id {reading_id!r}"
                        )
                for child in expansion.children:
                    validate(child)

        validate(self.root)

    def __eq__(self, other: object) -> bool:
        """Compare only the attributed metrical forest."""
        if not isinstance(other, MetricHierarchy):
            return NotImplemented
        return self.root == other.root

    def with_reading(
        self,
        reading: Reading,
        expansions: Mapping[tuple[int, ...], Expansion] | Iterable[Expansion],
    ) -> MetricHierarchy:
        """Return a hierarchy with one reading's partitions merged in.

        A mapping addresses nodes by child-index paths through the first
        expansion at each ancestor; an iterable contributes alternatives at
        the root. Structurally identical alternatives are coalesced and their
        reading-id sets united.

        Args:
            reading: Provenance for the added reading.
            expansions: Node paths mapped to asserted partitions, or root
                partitions as a plain iterable.

        Returns:
            A new hierarchy sharing every unchanged node.

        Raises:
            ValueError: If the reading id is already registered or a path is
                not present in the forest.
        """
        if any(existing.id == reading.id for existing in self.readings):
            raise ValueError(f"Reading id {reading.id!r} is already registered")

        def attributed(expansion: Expansion) -> Expansion:
            return expansion.model_copy(
                update={"readings": expansion.readings | {reading.id}}
            )

        def merge(node: MetricNode, expansion: Expansion) -> MetricNode:
            for index, existing in enumerate(node.expansions):
                if existing.children == expansion.children:
                    united = existing.model_copy(
                        update={"readings": existing.readings | expansion.readings}
                    )
                    alternatives = list(node.expansions)
                    alternatives[index] = united
                    return node.model_copy(update={"expansions": tuple(alternatives)})
            return node.model_copy(update={"expansions": (*node.expansions, expansion)})

        def merge_at(
            node: MetricNode, path: tuple[int, ...], expansion: Expansion
        ) -> MetricNode:
            if not path:
                return merge(node, attributed(expansion))
            if not node.expansions:
                raise ValueError(f"Expansion path {path!r} leaves the forest")
            child_index = path[0]
            children = list(node.expansions[0].children)
            if child_index < 0 or child_index >= len(children):
                raise ValueError(f"Expansion path {path!r} leaves the forest")
            children[child_index] = merge_at(children[child_index], path[1:], expansion)
            first = node.expansions[0].model_copy(update={"children": tuple(children)})
            return node.model_copy(update={"expansions": (first, *node.expansions[1:])})

        root = self.root
        items = (
            expansions.items()
            if isinstance(expansions, Mapping)
            else (((), expansion) for expansion in expansions)
        )
        for path, expansion in items:
            root = merge_at(root, tuple(path), expansion)
        return type(self)(
            root=root,
            readings=(*self.readings, reading),
            tempo_maps=self.tempo_maps,
        )

    def with_tempo_map(self, tempo_map: TempoMap) -> MetricHierarchy:
        """Return a hierarchy with an independent tempo map appended.

        Args:
            tempo_map: Map to append.

        Returns:
            A new hierarchy with the same forest and readings.
        """
        return type(self)(
            root=self.root,
            readings=self.readings,
            tempo_maps=(*self.tempo_maps, tempo_map),
        )

    def policy_at(
        self, reading: Reading | str, at: Coordinate | Fraction | int | float
    ) -> BeatPolicy:
        """Derive the selected reading's counting at a symbolic position.

        Positions are expressed as a share of the root span. Traversal uses
        stated child proportions and returns the deepest asserted partition
        containing the position.

        Args:
            reading: Reading object or registered reading identifier.
            at: Position in the normalized root span.

        Returns:
            A beat-policy view whose grouping reflects the selected partition.

        Raises:
            ValueError: If the reading is unknown, the position is outside the
                root, or the selected partition lacks exact proportions.
        """
        reading_id = reading.id if isinstance(reading, Reading) else reading
        if not any(item.id == reading_id for item in self.readings):
            raise ValueError(f"Unknown metric reading {reading_id!r}")
        if isinstance(at, Coordinate) and at.unit.domain is not Domain.logical:
            allowed = ", ".join(
                sorted(unit.value for unit in TimeUnit if unit.domain is Domain.logical)
            )
            raise ValueError(
                f"Metric position unit {at.unit.value!r} is not symbolic; "
                f"allowed units: {allowed}"
            )
        raw_position = at.value if isinstance(at, Coordinate) else at
        position = Fraction(raw_position)
        if position < 0 or position >= 1:
            raise ValueError("Metric positions must lie in the root span [0, 1)")

        node = self.root
        selected: Expansion | None = None
        while True:
            asserted = [
                expansion
                for expansion in node.expansions
                if reading_id in expansion.readings
            ]
            if not asserted:
                break
            if len(asserted) > 1:
                raise ValueError(
                    f"Reading {reading_id!r} asserts multiple expansions at one node"
                )
            selected = asserted[0]
            proportions = [child.proportion for child in selected.children]
            if any(value is None for value in proportions):
                break
            exact = [Fraction(value) for value in proportions if value is not None]
            running = Fraction(0)
            child_match: tuple[MetricNode, Fraction] | None = None
            for child, share in zip(selected.children, exact, strict=True):
                if share <= 0:
                    raise ValueError("Metric child proportions must be positive")
                if running <= position < running + share:
                    child_match = (child, (position - running) / share)
                    break
                running += share
            if child_match is None:
                break
            node, position = child_match

        if selected is None:
            raise ValueError(f"Reading {reading_id!r} asserts no expansion at {at!r}")
        proportions = [child.proportion for child in selected.children]
        if not proportions or any(value is None for value in proportions):
            raise ValueError("A BeatPolicy view requires exact child proportions")
        exact = [Fraction(value) for value in proportions if value is not None]
        denominator = lcm(*(value.denominator for value in exact))
        quantum_numerator = gcd(
            *(value.numerator * (denominator // value.denominator) for value in exact)
        )
        quantum = Fraction(quantum_numerator, denominator)
        grouping = tuple(int(value / quantum) for value in exact)
        return BeatPolicy(grouping=grouping, division=quantum)

    def to_dict(self) -> dict[str, Any]:
        """Return the forest, readings, and tempo maps as JSON-safe data.

        Returns:
            A complete hierarchy wire dictionary.
        """
        return {
            "root": self.root.to_dict(),
            "readings": [reading.to_dict() for reading in self.readings],
            "tempo_maps": [tempo_map.to_dict() for tempo_map in self.tempo_maps],
        }
