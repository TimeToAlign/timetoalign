"""Tests for the MatchClaimField columnar claim store.

MatchClaimField is a genuine ``SemanticField[MatchClaim]`` holding a set of
synchronous-instant pairwise MatchClaims as a single derived struct column
instead of one frozen MatchClaim object per claim, materialising individual
claims only on demand. Field-level shared metadata is injected on read.
Validation strategy and gold values are documented in
``tests/alignment/README.md`` (the "MatchClaimField Tests" section).
"""

from __future__ import annotations

import time

import pyarrow as pa
import pytest

from timetoalign.alignment import (
    Agent,
    MatchClaim,
    MatchClaimField,
    MatchMetadata,
)
from timetoalign.core import AgentType
from timetoalign.core.fields import SemanticField, derive_arrow_struct

# region Fixtures


@pytest.fixture
def meta() -> MatchMetadata:
    """The canonical shared metadata for the gold vector."""
    return MatchMetadata(
        agent=Agent(name="test", type=AgentType.software, identifier="manual")
    )


@pytest.fixture
def gold_field(meta: MatchMetadata) -> MatchClaimField:
    """The canonical 3-claim gold vector (A->B, A->C, B->C)."""
    return MatchClaimField.from_columns(
        timeline_a_ids=["A", "A", "B"],
        timeline_b_ids=["B", "C", "C"],
        coordinate_a=[0.0, 0.0, 1.0],
        coordinate_b=[10.0, 20.0, 21.0],
        metadata=meta,
    )


# endregion


# region Construction & schema


class TestFromColumns:
    """The vectorized constructor and the backing struct column's schema."""

    def test_from_columns_length(self, gold_field: MatchClaimField) -> None:
        assert len(gold_field) == 3

    def test_is_semantic_field(self) -> None:
        assert issubclass(MatchClaimField, SemanticField)
        assert MatchClaimField.scalar_cls is MatchClaim

    def test_pa_schema_is_derived(self) -> None:
        assert MatchClaimField.pa_schema == derive_arrow_struct(MatchClaim)

    def test_table_single_struct_column(self, gold_field: MatchClaimField) -> None:
        table = gold_field.table
        assert table.num_columns == 1
        assert table.column_names == ["match_claim"]
        assert table.schema.field("match_claim").type == MatchClaimField.pa_schema

    def test_timeline_ids(self, gold_field: MatchClaimField) -> None:
        assert gold_field.timeline_ids == {"A", "B", "C"}

    def test_metadata_property(
        self, gold_field: MatchClaimField, meta: MatchMetadata
    ) -> None:
        assert gold_field.metadata is meta

    def test_from_columns_accepts_pyarrow_arrays(self, meta: MatchMetadata) -> None:
        field = MatchClaimField.from_columns(
            timeline_a_ids=pa.array(["A", "B"], type=pa.string()),
            timeline_b_ids=pa.array(["B", "C"], type=pa.string()),
            coordinate_a=pa.array([0.0, 1.0], type=pa.float64()),
            coordinate_b=pa.array([10.0, 11.0], type=pa.float64()),
            metadata=meta,
        )
        assert len(field) == 2
        assert field.table.schema.field("match_claim").type == MatchClaimField.pa_schema

    def test_from_columns_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="equal-length"):
            MatchClaimField.from_columns(
                timeline_a_ids=["A"],
                timeline_b_ids=["B", "C"],
                coordinate_a=[0.0],
                coordinate_b=[1.0],
            )

    def test_translator_strenum_to_string(self) -> None:
        """A StrEnum field stores as pa.string() inside the derived struct.

        ``MatchMetadata.agent.type`` is an ``AgentType`` (a ``FancyStrEnum``);
        its derived sub-field must be ``pa.string()``.
        """
        meta_struct = derive_arrow_struct(MatchMetadata)
        agent_struct = meta_struct.field("agent").type
        assert agent_struct.field("type").type == pa.string()


# endregion


# region Materialisation


class TestGetItem:
    """Row materialisation into MatchClaim objects."""

    def test_getitem_first_row(
        self, gold_field: MatchClaimField, meta: MatchMetadata
    ) -> None:
        claim = gold_field[0]
        assert isinstance(claim, MatchClaim)
        assert claim.timeline_a_id == "A"
        assert claim.timeline_b_id == "B"
        assert claim.is_synchronous is True
        assert claim.is_interval is False
        assert claim.start_anchor.coordinate_a == 0.0
        assert claim.start_anchor.coordinate_b == 10.0
        assert claim.metadata is meta

    def test_getitem_injects_metadata(
        self, gold_field: MatchClaimField, meta: MatchMetadata
    ) -> None:
        """Metadata lives at field level (null in the struct) and is injected."""
        # The struct row carries no per-row metadata.
        struct = gold_field.table.column("match_claim").combine_chunks()
        assert struct.field("metadata").to_pylist() == [None, None, None]
        # The materialised claim nonetheless carries the field-level metadata.
        assert gold_field[1].metadata is meta

    def test_getitem_negative_index(self, gold_field: MatchClaimField) -> None:
        last = gold_field[-1]
        assert last.timeline_a_id == "B"
        assert last.timeline_b_id == "C"
        assert last.start_anchor.coordinate_a == 1.0
        assert last.start_anchor.coordinate_b == 21.0

    def test_getitem_out_of_range_positive(self, gold_field: MatchClaimField) -> None:
        with pytest.raises(IndexError):
            _ = gold_field[3]

    def test_getitem_out_of_range_negative(self, gold_field: MatchClaimField) -> None:
        with pytest.raises(IndexError):
            _ = gold_field[-4]

    def test_iter(self, gold_field: MatchClaimField) -> None:
        claims = list(gold_field)
        assert len(claims) == 3
        assert all(isinstance(c, MatchClaim) for c in claims)
        assert all(c.is_synchronous and not c.is_interval for c in claims)
        assert [(c.timeline_a_id, c.timeline_b_id) for c in claims] == [
            ("A", "B"),
            ("A", "C"),
            ("B", "C"),
        ]

    def test_to_claims(self, gold_field: MatchClaimField) -> None:
        claims = gold_field.to_claims()
        assert len(claims) == 3
        assert all(c.is_synchronous and c.start_anchor is not None for c in claims)
        assert all(c.end_anchor is None for c in claims)


# endregion


# region Filters


class TestFilters:
    """Vectorized connecting / filter views."""

    def test_connecting(self, gold_field: MatchClaimField) -> None:
        connected = gold_field.connecting("C")
        assert len(connected) == 2
        pairs = {
            (connected[i].timeline_a_id, connected[i].timeline_b_id)
            for i in range(len(connected))
        }
        assert pairs == {("A", "C"), ("B", "C")}

    def test_connecting_carries_metadata(
        self, gold_field: MatchClaimField, meta: MatchMetadata
    ) -> None:
        assert gold_field.connecting("C").metadata is meta

    def test_connecting_no_match(self, gold_field: MatchClaimField) -> None:
        assert len(gold_field.connecting("Z")) == 0

    def test_filter_timeline_ids(self, gold_field: MatchClaimField) -> None:
        filtered = gold_field.filter(timeline_ids={"A"})
        assert len(filtered) == 2
        pairs = {
            (filtered[i].timeline_a_id, filtered[i].timeline_b_id)
            for i in range(len(filtered))
        }
        assert pairs == {("A", "B"), ("A", "C")}

    def test_filter_timeline_id_equals_connecting(
        self, gold_field: MatchClaimField
    ) -> None:
        by_filter = gold_field.filter(timeline_id="C")
        by_connecting = gold_field.connecting("C")
        assert by_filter.table.equals(by_connecting.table)

    def test_filter_both_none_copies(self, gold_field: MatchClaimField) -> None:
        copy = gold_field.filter()
        assert len(copy) == 3
        assert copy.table.equals(gold_field.table)

    def test_filter_and_combination(self, gold_field: MatchClaimField) -> None:
        # timeline_id="A" -> rows 0,1; timeline_ids={"B"} -> rows 0,2.
        # AND -> only row 0 (A<->B).
        filtered = gold_field.filter(timeline_id="A", timeline_ids={"B"})
        assert len(filtered) == 1
        assert (filtered[0].timeline_a_id, filtered[0].timeline_b_id) == ("A", "B")

    def test_filter_timeline_ids_multiple(self, gold_field: MatchClaimField) -> None:
        filtered = gold_field.filter(timeline_ids={"A", "B"})
        assert len(filtered) == 3


# endregion


# region from_claims & round-trips


class TestFromClaims:
    """Building from existing claims and round-tripping."""

    def test_roundtrip_from_claims(self, gold_field: MatchClaimField) -> None:
        rebuilt = MatchClaimField.from_claims(gold_field.to_claims())
        assert rebuilt.table.equals(gold_field.table)

    def test_from_claims_adopts_common_metadata(self) -> None:
        meta = MatchMetadata(
            agent=Agent(name="dtw", type=AgentType.software, identifier="warp")
        )
        claims = [
            MatchClaim.from_projection(
                event={"id": "e", "start": 0.0},
                source_tl_id="A",
                target_tl_id="B",
                target_coord=10.0,
                metadata=meta,
            )
            for _ in range(3)
        ]
        field = MatchClaimField.from_claims(claims)
        assert field.metadata == meta

    def test_from_claims_mixed_metadata_stays_none(self) -> None:
        m1 = MatchMetadata(
            agent=Agent(name="a1", type=AgentType.software, identifier="c1")
        )
        m2 = MatchMetadata(
            agent=Agent(name="a2", type=AgentType.software, identifier="c2")
        )
        claims = [
            MatchClaim.from_projection(
                event={"id": "e", "start": 0.0},
                source_tl_id="A",
                target_tl_id="B",
                target_coord=10.0,
                metadata=m,
            )
            for m in (m1, m2)
        ]
        field = MatchClaimField.from_claims(claims)
        assert field.metadata is None

    def test_from_claims_explicit_metadata_overrides(self) -> None:
        per_claim = MatchMetadata(
            agent=Agent(name="a1", type=AgentType.software, identifier="c1")
        )
        override = MatchMetadata(
            agent=Agent(name="override", type=AgentType.software, identifier="c2")
        )
        claims = [
            MatchClaim.from_projection(
                event={"id": "e", "start": 0.0},
                source_tl_id="A",
                target_tl_id="B",
                target_coord=10.0,
                metadata=per_claim,
            )
        ]
        field = MatchClaimField.from_claims(claims, metadata=override)
        assert field.metadata is override

    def test_from_claims_rejects_nomatch(self) -> None:
        nomatch = MatchClaim.nomatch(
            event={"id": "orphan", "start": 5.0},
            source_tl_id="A",
            target_tl_id="B",
        )
        with pytest.raises(ValueError, match="non-synchronous"):
            MatchClaimField.from_claims([nomatch])

    def test_from_claims_rejects_interval(self) -> None:
        interval = MatchClaim.from_events(
            event_a={"id": "a", "start": 0.0, "end": 1.0},
            tl_a_id="A",
            event_b={"id": "b", "start": 10.0, "end": 11.0},
            tl_b_id="B",
            end_coord_key="end",
        )
        assert interval.is_interval
        with pytest.raises(ValueError, match="interval"):
            MatchClaimField.from_claims([interval])

    def test_from_claims_empty(self) -> None:
        field = MatchClaimField.from_claims([])
        assert len(field) == 0
        assert field.metadata is None


class TestDictRoundTrip:
    """to_dict / from_dict serialisation."""

    def test_roundtrip_from_dict(self, gold_field: MatchClaimField) -> None:
        rebuilt = MatchClaimField.from_dict(gold_field.to_dict())
        assert rebuilt.table.equals(gold_field.table)

    def test_roundtrip_preserves_metadata(
        self, gold_field: MatchClaimField, meta: MatchMetadata
    ) -> None:
        rebuilt = MatchClaimField.from_dict(gold_field.to_dict())
        assert rebuilt.metadata == meta

    def test_to_dict_column_contents(self, gold_field: MatchClaimField) -> None:
        data = gold_field.to_dict()
        assert data["timeline_a_id"] == ["A", "A", "B"]
        assert data["timeline_b_id"] == ["B", "C", "C"]
        assert data["coordinate_a"] == [0.0, 0.0, 1.0]
        assert data["coordinate_b"] == [10.0, 20.0, 21.0]

    def test_to_dict_no_metadata(self) -> None:
        field = MatchClaimField.from_columns(
            timeline_a_ids=["A"],
            timeline_b_ids=["B"],
            coordinate_a=[0.0],
            coordinate_b=[1.0],
        )
        assert field.to_dict()["metadata"] is None
        assert MatchClaimField.from_dict(field.to_dict()).metadata is None


# endregion


# region Edge cases, repr & scale


class TestEdgeCases:
    """Empty fields, repr, exports."""

    def test_empty_field(self) -> None:
        field = MatchClaimField.from_columns([], [], [], [])
        assert len(field) == 0
        assert field.timeline_ids == set()
        assert field.to_claims() == []
        assert list(field) == []

    def test_repr(self, gold_field: MatchClaimField) -> None:
        assert repr(gold_field) == "MatchClaimField(claims=3, timelines=3)"

    def test_repr_html_contains_summary(self, gold_field: MatchClaimField) -> None:
        html = gold_field._repr_html_()
        assert "MatchClaimField" in html
        assert "claims=3" in html
        assert "timelines=3" in html

    def test_top_level_export(self) -> None:
        import timetoalign
        from timetoalign.alignment import MatchClaimField as AliasFromAlignment

        assert timetoalign.MatchClaimField is MatchClaimField
        assert AliasFromAlignment is MatchClaimField


class TestScale:
    """The vectorized path scales without building Python objects."""

    def test_scale_builds_columnar(self) -> None:
        n = 100_000
        start = time.perf_counter()
        field = MatchClaimField.from_columns(
            timeline_a_ids=["A"] * n,
            timeline_b_ids=["B"] * n,
            coordinate_a=[float(i) for i in range(n)],
            coordinate_b=[float(i) + 0.5 for i in range(n)],
        )
        elapsed = time.perf_counter() - start

        assert len(field) == n
        # A generous ceiling: the vectorized path must not build N objects.
        assert elapsed < 1.0
        claim = field[50_000]
        assert claim.start_anchor.coordinate_a == 50_000.0
        assert claim.start_anchor.coordinate_b == 50_000.5
        assert field.timeline_ids == {"A", "B"}


# endregion
