"""Tests for core/ids.py."""

import pytest

from timetoalign.core.ids import IdGenerator, ScopedId, TimelineIdGenerator


class TestScopedIdCreation:
    """Tests for ScopedId instantiation."""

    def test_scopedid_creation(self) -> None:
        """Can create basic scoped ID."""
        sid = ScopedId("midi", "n42")
        assert sid.scope == "midi"
        assert sid.local == "n42"

    def test_scopedid_empty_scope(self) -> None:
        """Can create ID with empty scope."""
        sid = ScopedId("", "bare_id")
        assert sid.scope == ""
        assert sid.local == "bare_id"

    def test_scopedid_complex_scope(self) -> None:
        """Can create ID with dots and hyphens in scope."""
        sid = ScopedId("midi.track-1", "note")
        assert sid.scope == "midi.track-1"

    def test_scopedid_invalid_scope_starts_with_digit(self) -> None:
        """Scope starting with digit raises ValueError."""
        with pytest.raises(ValueError, match="Invalid scope"):
            ScopedId("1invalid", "n42")

    def test_scopedid_invalid_scope_special_chars(self) -> None:
        """Scope with special chars raises ValueError."""
        with pytest.raises(ValueError, match="Invalid scope"):
            ScopedId("bad@scope", "n42")

    def test_scopedid_empty_local_raises(self) -> None:
        """Empty local ID raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            ScopedId("midi", "")

    def test_scopedid_local_with_whitespace_raises(self) -> None:
        """Local ID with whitespace raises ValueError."""
        with pytest.raises(ValueError, match="cannot contain whitespace"):
            ScopedId("midi", "bad id")

    def test_scopedid_local_with_colon_raises(self) -> None:
        """Local ID with colon raises ValueError."""
        with pytest.raises(ValueError, match="cannot contain whitespace or colons"):
            ScopedId("midi", "bad:id")

    def test_scopedid_is_frozen(self) -> None:
        """ScopedId is immutable."""
        sid = ScopedId("midi", "n42")
        with pytest.raises(AttributeError):
            sid.scope = "other"  # type: ignore[misc]

    def test_scopedid_is_hashable(self) -> None:
        """ScopedId can be used in sets and as dict keys."""
        s1 = ScopedId("midi", "n42")
        s2 = ScopedId("midi", "n42")
        s3 = ScopedId("score", "n42")

        assert hash(s1) == hash(s2)
        assert s1 in {s2}
        assert len({s1, s2, s3}) == 2


class TestScopedIdStringConversion:
    """Tests for ScopedId string methods."""

    def test_str_with_scope(self) -> None:
        """__str__ includes scope with separator."""
        sid = ScopedId("midi", "n42")
        assert str(sid) == "midi:n42"

    def test_str_without_scope(self) -> None:
        """__str__ returns just local when scope is empty."""
        sid = ScopedId("", "bare_id")
        assert str(sid) == "bare_id"

    def test_repr(self) -> None:
        """__repr__ returns valid representation."""
        sid = ScopedId("midi", "n42")
        assert repr(sid) == "ScopedId(scope='midi', local='n42')"


class TestScopedIdParse:
    """Tests for ScopedId.parse() class method."""

    def test_parse_with_scope(self) -> None:
        """Can parse ID with scope."""
        sid = ScopedId.parse("midi:n42")
        assert sid.scope == "midi"
        assert sid.local == "n42"

    def test_parse_without_scope(self) -> None:
        """Can parse bare ID."""
        sid = ScopedId.parse("bare_id")
        assert sid.scope == ""
        assert sid.local == "bare_id"

    def test_parse_dotted_local(self) -> None:
        """Dotted local IDs are allowed."""
        sid = ScopedId.parse("midi:note.1.start")
        assert sid.scope == "midi"
        assert sid.local == "note.1.start"

    def test_parse_roundtrip(self) -> None:
        """parse(str(id)) == id"""
        original = ScopedId("midi", "n42")
        parsed = ScopedId.parse(str(original))
        assert parsed == original


class TestScopedIdMethods:
    """Tests for ScopedId utility methods."""

    def test_with_scope(self) -> None:
        """with_scope() returns new ID with different scope."""
        s1 = ScopedId("midi", "n42")
        s2 = s1.with_scope("audio")
        assert s2.scope == "audio"
        assert s2.local == "n42"
        assert s1.scope == "midi"  # Original unchanged

    def test_with_local(self) -> None:
        """with_local() returns new ID with different local."""
        s1 = ScopedId("midi", "n42")
        s2 = s1.with_local("n99")
        assert s2.scope == "midi"
        assert s2.local == "n99"
        assert s1.local == "n42"  # Original unchanged

    def test_nested_with_scope(self) -> None:
        """nested() appends to existing scope."""
        s1 = ScopedId("midi", "note")
        s2 = s1.nested("track1")
        assert s2.scope == "midi.track1"
        assert s2.local == "note"

    def test_nested_without_scope(self) -> None:
        """nested() creates scope when none exists."""
        s1 = ScopedId("", "note")
        s2 = s1.nested("track1")
        assert s2.scope == "track1"
        assert s2.local == "note"

    def test_is_scoped_true(self) -> None:
        """is_scoped is True when scope is non-empty."""
        sid = ScopedId("midi", "n42")
        assert sid.is_scoped is True

    def test_is_scoped_false(self) -> None:
        """is_scoped is False when scope is empty."""
        sid = ScopedId("", "bare_id")
        assert sid.is_scoped is False


class TestIdGeneratorCreation:
    """Tests for IdGenerator instantiation."""

    def test_idgenerator_creation(self) -> None:
        """Can create IdGenerator with scope."""
        gen = IdGenerator("test")
        assert gen.scope == "test"
        assert gen.count == 0

    def test_idgenerator_empty_scope(self) -> None:
        """Can create IdGenerator with empty scope."""
        gen = IdGenerator("")
        assert gen.scope == ""


class TestIdGeneratorGetOrCreate:
    """Tests for IdGenerator.get_or_create() method."""

    def test_wrap_external_id(self) -> None:
        """get_or_create with external ID wraps it."""
        gen = IdGenerator("midi")
        result = gen.get_or_create("n42")
        assert result == "midi:n42"

    def test_wrap_external_id_strips_whitespace(self) -> None:
        """External IDs are stripped of whitespace."""
        gen = IdGenerator("midi")
        result = gen.get_or_create("  n42  ")
        assert result == "midi:n42"

    def test_generate_id_no_external(self) -> None:
        """get_or_create without external ID generates one."""
        gen = IdGenerator("midi")
        result = gen.get_or_create(None, type_hint="note")
        assert result == "midi:note_1"

    def test_generate_id_increments(self) -> None:
        """Generated IDs increment counter."""
        gen = IdGenerator("midi")
        r1 = gen.get_or_create(None, type_hint="note")
        r2 = gen.get_or_create(None, type_hint="note")
        r3 = gen.get_or_create(None, type_hint="note")
        assert r1 == "midi:note_1"
        assert r2 == "midi:note_2"
        assert r3 == "midi:note_3"

    def test_generate_id_different_types(self) -> None:
        """Different type hints have independent counters."""
        gen = IdGenerator("midi")
        n1 = gen.get_or_create(None, type_hint="note")
        r1 = gen.get_or_create(None, type_hint="rest")
        n2 = gen.get_or_create(None, type_hint="note")
        assert n1 == "midi:note_1"
        assert r1 == "midi:rest_1"
        assert n2 == "midi:note_2"

    def test_generate_id_default_type_hint(self) -> None:
        """Default type hint is 'event'."""
        gen = IdGenerator("midi")
        result = gen.get_or_create(None)
        assert result == "midi:event_1"

    def test_empty_external_id_generates(self) -> None:
        """Empty string external ID triggers generation."""
        gen = IdGenerator("midi")
        result = gen.get_or_create("", type_hint="note")
        assert result == "midi:note_1"

    def test_whitespace_only_external_id_generates(self) -> None:
        """Whitespace-only external ID triggers generation."""
        gen = IdGenerator("midi")
        result = gen.get_or_create("   ", type_hint="note")
        assert result == "midi:note_1"


class TestIdGeneratorConvenienceMethods:
    """Tests for IdGenerator convenience methods."""

    def test_create(self) -> None:
        """create() is shorthand for get_or_create(None)."""
        gen = IdGenerator("midi")
        result = gen.create(type_hint="note")
        assert result == "midi:note_1"

    def test_wrap(self) -> None:
        """wrap() is shorthand for get_or_create(external_id)."""
        gen = IdGenerator("midi")
        result = gen.wrap("n42")
        assert result == "midi:n42"


class TestIdGeneratorState:
    """Tests for IdGenerator state management."""

    def test_count_tracks_ids(self) -> None:
        """count property tracks total IDs generated/wrapped."""
        gen = IdGenerator("midi")
        assert gen.count == 0
        gen.get_or_create("n1")
        assert gen.count == 1
        gen.get_or_create(None, type_hint="note")
        assert gen.count == 2

    def test_has_seen(self) -> None:
        """has_seen() checks if ID was generated/wrapped."""
        gen = IdGenerator("midi")
        gen.get_or_create("n42")
        assert gen.has_seen("midi:n42") is True
        assert gen.has_seen("midi:n99") is False

    def test_reset(self) -> None:
        """reset() clears counters and seen IDs."""
        gen = IdGenerator("midi")
        gen.get_or_create(None, type_hint="note")
        gen.get_or_create("n42")
        assert gen.count == 2

        gen.reset()
        assert gen.count == 0
        assert gen.has_seen("midi:n42") is False
        # Counter also resets
        result = gen.get_or_create(None, type_hint="note")
        assert result == "midi:note_1"

    def test_reset_counters(self) -> None:
        """reset_counters() clears counters but keeps seen IDs."""
        gen = IdGenerator("midi")
        gen.get_or_create(None, type_hint="note")
        gen.get_or_create("n42")

        gen.reset_counters()
        # Counter resets
        result = gen.get_or_create(None, type_hint="note")
        assert result == "midi:note_1"
        # But seen IDs are kept
        assert gen.has_seen("midi:n42") is True


class TestIdGeneratorEmptyScope:
    """Tests for IdGenerator with empty scope."""

    def test_empty_scope_wrap(self) -> None:
        """Empty scope produces unscoped IDs when wrapping."""
        gen = IdGenerator("")
        result = gen.get_or_create("n42")
        assert result == "n42"

    def test_empty_scope_generate(self) -> None:
        """Empty scope produces unscoped IDs when generating."""
        gen = IdGenerator("")
        result = gen.create(type_hint="note")
        assert result == "note_1"


# region TimelineIdGenerator


class TestTimelineIdGeneratorBasic:
    """Tests for TimelineIdGenerator creation and basic operation."""

    def test_creation(self) -> None:
        """Can create a TimelineIdGenerator."""
        gen = TimelineIdGenerator()
        assert gen.count == 0

    def test_next_id_clt(self) -> None:
        """Generates correct prefix for ContinuousLogicalTimeline."""
        gen = TimelineIdGenerator()
        assert gen.next_id("ContinuousLogicalTimeline") == "clt1"

    def test_next_id_dlt(self) -> None:
        """Generates correct prefix for DiscreteLogicalTimeline."""
        gen = TimelineIdGenerator()
        assert gen.next_id("DiscreteLogicalTimeline") == "dlt1"

    def test_next_id_cpt(self) -> None:
        """Generates correct prefix for ContinuousPhysicalTimeline."""
        gen = TimelineIdGenerator()
        assert gen.next_id("ContinuousPhysicalTimeline") == "cpt1"

    def test_next_id_dpt(self) -> None:
        """Generates correct prefix for DiscretePhysicalTimeline."""
        gen = TimelineIdGenerator()
        assert gen.next_id("DiscretePhysicalTimeline") == "dpt1"

    def test_next_id_cgt(self) -> None:
        """Generates correct prefix for ContinuousGraphicalTimeline."""
        gen = TimelineIdGenerator()
        assert gen.next_id("ContinuousGraphicalTimeline") == "cgt1"

    def test_next_id_dgt(self) -> None:
        """Generates correct prefix for DiscreteGraphicalTimeline."""
        gen = TimelineIdGenerator()
        assert gen.next_id("DiscreteGraphicalTimeline") == "dgt1"

    def test_next_id_base_timeline(self) -> None:
        """Base Timeline class uses 'tl' prefix."""
        gen = TimelineIdGenerator()
        assert gen.next_id("Timeline") == "tl1"

    def test_unknown_type_raises(self) -> None:
        """Unknown timeline type raises ValueError."""
        gen = TimelineIdGenerator()
        with pytest.raises(ValueError, match="Unknown timeline type"):
            gen.next_id("FancyTimeline")


class TestTimelineIdGeneratorCounters:
    """Tests for counter increment and scoping."""

    def test_counter_increments_per_prefix(self) -> None:
        """Counter increments per prefix, not globally."""
        gen = TimelineIdGenerator()
        assert gen.next_id("ContinuousLogicalTimeline") == "clt1"
        assert gen.next_id("ContinuousLogicalTimeline") == "clt2"
        assert gen.next_id("DiscreteLogicalTimeline") == "dlt1"
        assert gen.next_id("ContinuousLogicalTimeline") == "clt3"
        assert gen.next_id("DiscreteLogicalTimeline") == "dlt2"

    def test_count_tracks_total(self) -> None:
        """count property returns sum of all counters."""
        gen = TimelineIdGenerator()
        gen.next_id("ContinuousLogicalTimeline")
        gen.next_id("DiscreteLogicalTimeline")
        gen.next_id("ContinuousLogicalTimeline")
        assert gen.count == 3

    def test_reset_clears_state(self) -> None:
        """reset() clears counters and metadata."""
        gen = TimelineIdGenerator()
        gen.next_id("ContinuousLogicalTimeline")
        gen.next_id("DiscreteLogicalTimeline")
        gen.reset()
        assert gen.count == 0
        assert gen.next_id("ContinuousLogicalTimeline") == "clt1"
        assert gen.next_id("DiscreteLogicalTimeline") == "dlt1"


class TestTimelineIdGeneratorRoles:
    """Tests for role-based ID generation."""

    def test_next_id_with_role(self) -> None:
        """Role prefix is prepended."""
        gen = TimelineIdGenerator()
        assert (
            gen.next_id_with_role("ContinuousLogicalTimeline", "score") == "score:clt1"
        )

    def test_role_and_plain_share_counter(self) -> None:
        """Role and plain IDs share the same prefix counter."""
        gen = TimelineIdGenerator()
        assert gen.next_id("DiscreteLogicalTimeline") == "dlt1"
        assert gen.next_id_with_role("DiscreteLogicalTimeline", "perf") == "perf:dlt2"
        assert gen.next_id_with_role("DiscreteLogicalTimeline", "perf") == "perf:dlt3"

    def test_vienna_pattern(self) -> None:
        """Simulates the Vienna 1x22 pattern: 1 score + 22 performers."""
        gen = TimelineIdGenerator()
        score_id = gen.next_id_with_role("ContinuousLogicalTimeline", "score")
        assert score_id == "score:clt1"

        perf_ids = []
        for _ in range(22):
            perf_ids.append(gen.next_id_with_role("DiscreteLogicalTimeline", "perf"))
        assert perf_ids[0] == "perf:dlt1"
        assert perf_ids[21] == "perf:dlt22"
        assert gen.count == 23


class TestTimelineIdGeneratorMetadata:
    """Tests for metadata association."""

    def test_meta_stored_and_retrieved(self) -> None:
        """Metadata is stored and can be retrieved by ID."""
        gen = TimelineIdGenerator()
        tid = gen.next_id_with_role(
            "DiscreteLogicalTimeline",
            "perf",
            meta={"performer": "p01", "filename": "Chopin_op10_no3_p01.match"},
        )
        assert tid == "perf:dlt1"
        meta = gen.get_meta(tid)
        assert meta is not None
        assert meta["performer"] == "p01"
        assert meta["filename"] == "Chopin_op10_no3_p01.match"

    def test_no_meta_returns_none(self) -> None:
        """get_meta returns None for IDs without metadata."""
        gen = TimelineIdGenerator()
        tid = gen.next_id("ContinuousLogicalTimeline")
        assert gen.get_meta(tid) is None

    def test_meta_cleared_on_reset(self) -> None:
        """reset() clears metadata."""
        gen = TimelineIdGenerator()
        tid = gen.next_id("ContinuousLogicalTimeline", meta={"x": 1})
        gen.reset()
        assert gen.get_meta(tid) is None

    def test_accepts_class_objects(self) -> None:
        """Can pass actual class objects, not just strings."""
        from timetoalign.timelines import (
            ContinuousLogicalTimeline,
            DiscreteLogicalTimeline,
        )

        gen = TimelineIdGenerator()
        assert gen.next_id(ContinuousLogicalTimeline) == "clt1"
        assert gen.next_id(DiscreteLogicalTimeline) == "dlt1"

    def test_accepts_class_objects_with_role(self) -> None:
        """Can pass actual class objects to next_id_with_role."""
        from timetoalign.timelines import ContinuousLogicalTimeline

        gen = TimelineIdGenerator()
        assert gen.next_id_with_role(ContinuousLogicalTimeline, "score") == "score:clt1"


# endregion
