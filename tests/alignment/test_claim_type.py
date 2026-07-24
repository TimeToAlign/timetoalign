"""Tests for the derived ``MatchClaim.claim_type`` classification.

A :class:`MatchClaim` never stores its semantic kind. ``claim_type`` reads the
kind back from three structural facts: whether the claim is explicit, whether
it is synchronous, and how many of its two sides name an event (``event_a_id`` /
``event_b_id``). This module pins the exact classification for every
construction path and the display consequences that follow from it.

Taxonomy
--------

The classification is evaluated in this order:

======================================  =================  ==================
Structure                               ``ClaimType``      Typical origin
======================================  =================  ==================
``is_explicit`` is False                ``implicit``       ``MatchClaim.implicit``
synchronous, both sides name an event   ``event_match``    ``MatchClaim.from_events`` (ids)
synchronous, one side names an event    ``projection``     ``MatchClaim.from_projection``
synchronous, neither names an event     ``anchor``         ``from_events`` (no ids), ``MatchClaimField``
non-synchronous, one side names it      ``nomatch``        ``MatchClaim.nomatch`` (event has ``id``)
non-synchronous, neither / both name    ``conceptual``     ``MatchClaim.nomatch`` (no ``id``), bare claim
======================================  =================  ==================

The critical distinction this classification draws is between a genuine
**nomatch** and a **conceptual** correspondence. An absence claim that names no
event is, by this taxonomy, conceptual: a real NOMATCH must identify the
orphaned event on exactly one side. A synchronous claim whose two sides are
anonymous coordinates (no event identity) is an **anchor**, and
``is_anonymous`` is True for it.

Display
-------

``__repr__`` shows an uppercase ``[KIND]`` badge for every kind except a plain
``event_match`` (which stays badge-free). ``__str__`` and ``_repr_html_`` report
the derived kind for non-synchronous claims, so a conceptual claim never reads
"NOMATCH".
"""

from __future__ import annotations

from timetoalign.alignment import ClaimType, MatchClaim, MatchClaimField
from timetoalign.core import ClaimType as CoreClaimType
from timetoalign.core import TimeUnit

# region Classification by construction path


class TestClaimTypeClassification:
    """Exact ``claim_type`` for every construction path."""

    def test_from_events_with_ids_is_event_match(self) -> None:
        """Two identified events on either side classify as event_match."""
        claim = MatchClaim.from_events(
            event_a={"id": "e001", "name": "Note C4", "start": 100.0},
            tl_a_id="score:1",
            event_b={"id": "e042", "name": "Note C4", "start": 45.5},
            tl_b_id="recording:1",
            unit_a=TimeUnit.quarters,
            unit_b=TimeUnit.seconds,
        )
        assert claim.claim_type is ClaimType.event_match

    def test_from_events_without_ids_is_anchor(self) -> None:
        """Two anonymous coordinates (no event identity) classify as anchor."""
        claim = MatchClaim.from_events(
            event_a={"start": 0.0},
            tl_a_id="score:1",
            event_b={"start": 1.0},
            tl_b_id="recording:1",
            unit_a=TimeUnit.quarters,
            unit_b=TimeUnit.seconds,
        )
        assert claim.claim_type is ClaimType.anchor
        assert claim.is_anonymous is True

    def test_from_projection_is_projection(self) -> None:
        """A source event projected onto a bare target coordinate is a projection."""
        claim = MatchClaim.from_projection(
            event={"id": "e001", "start": 100.0},
            source_tl_id="score:1",
            target_tl_id="recording:1",
            target_coord=45.5,
            source_unit=TimeUnit.quarters,
            target_unit=TimeUnit.seconds,
        )
        assert claim.claim_type is ClaimType.projection

    def test_nomatch_with_named_event_is_nomatch(self) -> None:
        """An absence claim that names the orphaned event is a genuine nomatch."""
        claim = MatchClaim.nomatch(
            event={"id": "x", "start": 0.0},
            source_tl_id="score:1",
            target_tl_id="recording:1",
            unit=TimeUnit.number,
        )
        assert claim.claim_type is ClaimType.nomatch

    def test_nomatch_without_named_event_is_conceptual(self) -> None:
        """An absence claim that names no event is conceptual, not nomatch.

        A real NOMATCH must identify the orphaned event on exactly one side;
        naming neither side leaves only a structural (conceptual) assertion.
        """
        claim = MatchClaim.nomatch(
            event={},
            source_tl_id="score:1",
            target_tl_id="recording:1",
            unit=TimeUnit.number,
        )
        assert claim.claim_type is ClaimType.conceptual

    def test_implicit_is_implicit(self) -> None:
        """An inferred (non-explicit) claim classifies as implicit."""
        claim = MatchClaim.implicit(
            tl_a_id="score:1",
            coord_a=100.0,
            tl_b_id="recording:1",
            coord_b=45.5,
            unit_a=TimeUnit.quarters,
            unit_b=TimeUnit.seconds,
        )
        assert claim.claim_type is ClaimType.implicit

    def test_bare_non_synchronous_is_conceptual(self) -> None:
        """A bare non-synchronous claim naming no event is conceptual."""
        claim = MatchClaim(
            timeline_a_id="a",
            timeline_b_id="b",
            is_synchronous=False,
        )
        assert claim.claim_type is ClaimType.conceptual

    def test_field_row_materialises_as_anchor(self) -> None:
        """A row from a columnar field carries no event identity -> anchor."""
        field = MatchClaimField.from_columns(
            timeline_a_ids=["A", "A"],
            timeline_b_ids=["B", "B"],
            coordinate_a=[0.0, 1.0],
            coordinate_b=[10.0, 11.0],
            unit_a=TimeUnit.quarters,
            unit_b=TimeUnit.seconds,
        )
        assert len(field) == 2
        claim = field[0]
        assert claim.claim_type is ClaimType.anchor
        assert claim.is_anonymous is True


# endregion


# region Convenience booleans


class TestClaimTypeBooleans:
    """The thin ``is_*`` predicates over ``claim_type``."""

    def test_booleans_on_event_match(self) -> None:
        """An event_match is neither nomatch, conceptual, nor anonymous."""
        claim = MatchClaim.from_events(
            event_a={"id": "e001", "start": 0.0},
            tl_a_id="score:1",
            event_b={"id": "e042", "start": 1.0},
            tl_b_id="recording:1",
            unit_a=TimeUnit.quarters,
            unit_b=TimeUnit.seconds,
        )
        assert claim.is_nomatch is False
        assert claim.is_conceptual is False
        assert claim.is_anonymous is False

    def test_booleans_on_nomatch(self) -> None:
        """A genuine nomatch reports is_nomatch and nothing else."""
        claim = MatchClaim.nomatch(
            event={"id": "x", "start": 0.0},
            source_tl_id="score:1",
            target_tl_id="recording:1",
            unit=TimeUnit.number,
        )
        assert claim.is_nomatch is True
        assert claim.is_conceptual is False
        assert claim.is_anonymous is False

    def test_booleans_on_conceptual(self) -> None:
        """A bare non-synchronous claim reports is_conceptual and nothing else."""
        claim = MatchClaim(
            timeline_a_id="a",
            timeline_b_id="b",
            is_synchronous=False,
        )
        assert claim.is_conceptual is True
        assert claim.is_nomatch is False
        assert claim.is_anonymous is False

    def test_booleans_on_anchor(self) -> None:
        """An anonymous synchronous claim reports is_anonymous and nothing else."""
        claim = MatchClaim.from_events(
            event_a={"start": 0.0},
            tl_a_id="score:1",
            event_b={"start": 1.0},
            tl_b_id="recording:1",
            unit_a=TimeUnit.quarters,
            unit_b=TimeUnit.seconds,
        )
        assert claim.is_anonymous is True
        assert claim.is_nomatch is False
        assert claim.is_conceptual is False


# endregion


# region Display consequences


class TestClaimTypeDisplay:
    """``__repr__`` / ``__str__`` reflect the derived kind, not raw synchrony."""

    def test_repr_conceptual_says_conceptual_not_nomatch(self) -> None:
        """A conceptual claim's repr carries CONCEPTUAL and never NOMATCH."""
        claim = MatchClaim(
            timeline_a_id="a",
            timeline_b_id="b",
            is_synchronous=False,
        )
        r = repr(claim)
        assert "CONCEPTUAL" in r
        assert "NOMATCH" not in r

    def test_str_conceptual_does_not_say_nomatch(self) -> None:
        """A conceptual claim's str header never reads NOMATCH."""
        claim = MatchClaim(
            timeline_a_id="a",
            timeline_b_id="b",
            is_synchronous=False,
        )
        assert "NOMATCH" not in str(claim)

    def test_repr_nomatch_says_nomatch(self) -> None:
        """A genuine nomatch claim's repr carries the NOMATCH badge."""
        claim = MatchClaim.nomatch(
            event={"id": "x", "start": 0.0},
            source_tl_id="score:1",
            target_tl_id="recording:1",
            unit=TimeUnit.number,
        )
        assert "NOMATCH" in repr(claim)


# endregion


# region Enum instantiation


class TestClaimTypeEnum:
    """String and alias instantiation of ``ClaimType``."""

    def test_canonical_name_instantiation(self) -> None:
        """Each canonical member name round-trips through ClaimType(...)."""
        assert ClaimType("event_match") is ClaimType.event_match
        assert ClaimType("projection") is ClaimType.projection
        assert ClaimType("nomatch") is ClaimType.nomatch
        assert ClaimType("anchor") is ClaimType.anchor
        assert ClaimType("implicit") is ClaimType.implicit
        assert ClaimType("conceptual") is ClaimType.conceptual

    def test_alias_instantiation(self) -> None:
        """Short aliases resolve to their canonical member."""
        assert ClaimType("event") is ClaimType.event_match
        assert ClaimType("nomat") is ClaimType.nomatch
        assert ClaimType("anon") is ClaimType.anchor

    def test_core_and_alignment_exports_are_identical(self) -> None:
        """ClaimType is one type, exported from both core and alignment."""
        assert ClaimType is CoreClaimType


# endregion
