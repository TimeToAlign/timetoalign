"""ListenHereLoader: a dense audio-to-audio AlignmentBundle from one JSON file.

A *Listen Here!* alignment export is a single JSON file describing how many
recordings of one musical work line up in time.  Every recording is warped onto
a shared, equidistant **reference grid**: the file stores, per recording, a
``times`` array whose ``i``-th entry is that recording's clock-time (in seconds)
at reference-grid column ``i``.  Because every recording is sampled against the
same grid, the per-recording arrays are **parallel and equal length** — together
they form a dense alignment matrix of shape ``(recordings × grid columns)``.

Unlike a pairwise score-to-performance export (one score against one
performance), a single Listen Here! file already encodes the alignment of *all*
recordings against one another.  The natural Time To Align! reading is therefore
a **complete pairwise topology**: at every grid column, every unordered pair of
recordings ``(a, b)`` is directly related by a synchronous instant
:class:`~timetoalign.alignment.anchors.MatchClaim`
(``a@times_a[i] ↔ b@times_b[i]``).  For ``R`` recordings and ``N`` grid columns
this is ``C(R, 2) × N`` claims — a very large set for a whole work — so the
claims are held columnar in a
:class:`~timetoalign.alignment.anchors.MatchClaimField` and assembled
**vectorized** (never one Python claim object per row).

``ListenHereLoader`` ingests one alignment JSON file in one call::

    bundle = ListenHereLoader.from_file(alignment_json).create_bundle()

and produces a single :class:`~timetoalign.alignment.bundle.AlignmentBundle`:

* one seconds
  :class:`~timetoalign.timelines.types.ContinuousPhysicalTimeline`
  (``<stem>:cpt1``) per recording, each in its **own** group, with
  ``length`` equal to that recording's stored ``duration``.  The recordings
  carry **no symbolic events** — the timelines hold only a length and a unit;
  all alignment lives in the cross-group claim field; and
* the complete-topology pairwise claims, exposed as
  :attr:`ListenHereLoader.claim_field`.

The reference recording named by ``header.ref`` fixes the grid origin but is
**not** a privileged hub: it is just another recording, related to every other
by direct pairwise claims like any other pair.

The loader reads the *existing* alignment; it never runs an aligner.

A recording's early grid columns may carry **negative** seconds — a recording
that begins after the reference's grid origin is extrapolated backwards before
its first onset.  These negative coordinates are stored faithfully, neither
clamped nor dropped.

See Also:
    timetoalign.AlignmentBundle
    timetoalign.MatchClaim
    timetoalign.MatchClaimField
"""

from __future__ import annotations

import itertools
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from typing_extensions import Self

from timetoalign.alignment.anchors import MatchClaimField, MatchMetadata
from timetoalign.core import TimeUnit
from timetoalign.loader.base import AlignmentLoader
from timetoalign.timelines.types import ContinuousPhysicalTimeline

if TYPE_CHECKING:
    from timetoalign.alignment.bundle import AlignmentBundle
    from timetoalign.timelines.base import Timeline

module_logger = logging.getLogger(__name__)


# region Constants

#: Provenance recorded on every materialised claim.  The agent is read from the
#: file's ``header.createdBy`` (falling back to a generic label); the decision
#: criteria names the alignment method Listen Here! uses (chroma-feature DTW).
_DEFAULT_AGENT = "Listen Here!"
_DECISION_CRITERIA = "dtw_chroma_alignment"

# endregion


# region ListenHereLoader


class ListenHereLoader(AlignmentLoader):
    """Load a Listen Here! alignment JSON file as one AlignmentBundle.

    The loader parses a single alignment JSON file describing many recordings
    of one work warped onto a shared equidistant reference grid, and assembles
    a bundle in which every recording is a seconds timeline in its own group,
    related to every other recording by a complete set of pairwise synchronous
    instant :class:`MatchClaim` rows held columnar in a :class:`MatchClaimField`.

    **Usage follows the standard loader two-phase pattern:**

    1. ``loader.load(alignment_json)`` — parse one alignment JSON file.
    2. ``loader.create_bundle()`` — assemble the AlignmentBundle.
    3. ``loader.create_timeline(id)`` / ``create_timelines()`` — retrieve
       individual timelines.

    The loader reads the existing alignment; it never runs an aligner.
    """

    def __init__(self) -> None:
        super().__init__()

        # Sorted audio keys (file names / URLs from ``body.audio``).
        self._keys: list[str] = []
        # Per key: the stem (basename without extension) and the recording's
        # duration in seconds.
        self._stems: dict[str, str] = {}
        self._durations: dict[str, float] = {}
        self._claim_field: MatchClaimField | None = None
        self._name: str | None = None

    # region Abstract-method satisfaction

    def _load_source(self, source: Path) -> Any:
        """Not used: a Listen Here! export is a single coherent file.

        :class:`ListenHereLoader` ingests one alignment JSON file through
        :meth:`load`; the base class's per-source AlignmentStore merge does
        not apply.
        """
        raise NotImplementedError(
            "ListenHereLoader ingests one alignment JSON file via "
            "load(alignment_json); per-source loading is not used."
        )

    # endregion

    # region Loading

    def load(self, source: str | Path) -> Self:
        """Ingest one Listen Here! alignment JSON file.

        Args:
            source: Path to the ``alignment.json`` file.

        Returns:
            Self, for method chaining.

        Raises:
            ValueError: If ``header.ref`` is missing or is not one of the
                ``body.audio`` keys; if fewer than two recordings are present;
                or if the per-recording ``times`` arrays are not all the same
                length.
        """
        path = Path(source)
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        header = data.get("header", {})
        audio = data.get("body", {}).get("audio", {})

        keys = sorted(audio.keys())
        if len(keys) < 2:
            raise ValueError(
                f"A Listen Here! alignment needs at least 2 recordings; "
                f"found {len(keys)} in {path}."
            )

        ref = header.get("ref")
        if ref not in audio:
            raise ValueError(
                f"header.ref {ref!r} is not one of the body.audio keys "
                f"{keys} in {path}."
            )

        # Normalise each entry to (times, duration) and validate equal lengths.
        times_by_key: dict[str, list[float]] = {}
        for key in keys:
            times, duration = self._normalise_entry(audio[key])
            times_by_key[key] = times
            self._durations[key] = duration
            self._stems[key] = os.path.splitext(os.path.basename(key))[0]

        lengths = {key: len(times_by_key[key]) for key in keys}
        if len(set(lengths.values())) != 1:
            raise ValueError(
                "All recordings' 'times' arrays must have the same length "
                f"(they index a shared reference grid); got {lengths} in {path}."
            )

        self._keys = keys
        self._name = path.stem
        agent = header.get("createdBy", _DEFAULT_AGENT)
        self._claim_field = self._build_claim_field(keys, times_by_key, agent)
        self._sources = [path]
        return self

    @staticmethod
    def _normalise_entry(entry: Any) -> tuple[list[float], float]:
        """Normalise one ``body.audio`` value to ``(times, duration)``.

        A value may be either an object ``{"times": [...], "peaks": [...],
        "duration": <float>}`` or a bare array of times.  ``peaks`` (a
        waveform-display payload) is ignored.  For the bare-array form the
        duration is taken as the maximum time.

        Args:
            entry: The ``body.audio[key]`` value (object or bare list).

        Returns:
            A ``(times, duration)`` pair.
        """
        if isinstance(entry, dict):
            times = [float(t) for t in entry["times"]]
            duration = float(entry["duration"])
            return times, duration
        times = [float(t) for t in entry]
        duration = max(times) if times else 0.0
        return times, duration

    def _build_claim_field(
        self,
        keys: list[str],
        times_by_key: dict[str, list[float]],
        agent: str,
    ) -> MatchClaimField:
        """Build the complete-topology pairwise claim field, vectorized.

        For every unordered pair of recordings ``(a, b)`` and every reference
        grid column ``i``, a synchronous instant claim relates ``a`` at
        ``times_a[i]`` to ``b`` at ``times_b[i]``.  The four parallel columns
        are concatenated across all pairs with numpy and handed to
        :meth:`MatchClaimField.from_columns`, so no :class:`MatchClaim` object
        is constructed.

        Args:
            keys: The sorted audio keys.
            times_by_key: Each key's per-grid-column times (seconds).
            agent: The provenance agent (``header.createdBy``).

        Returns:
            A :class:`MatchClaimField` of ``C(R, 2) × N`` synchronous claims.
        """
        coord_arrays = {
            key: np.asarray(times_by_key[key], dtype=np.float64) for key in keys
        }
        uid_by_key = {key: self._timeline_uid(key) for key in keys}
        ncols = len(next(iter(coord_arrays.values()))) if keys else 0

        a_id_blocks: list[list[str]] = []
        b_id_blocks: list[list[str]] = []
        coord_a_blocks: list[np.ndarray] = []
        coord_b_blocks: list[np.ndarray] = []

        for key_a, key_b in itertools.combinations(keys, 2):
            a_id_blocks.append([uid_by_key[key_a]] * ncols)
            b_id_blocks.append([uid_by_key[key_b]] * ncols)
            coord_a_blocks.append(coord_arrays[key_a])
            coord_b_blocks.append(coord_arrays[key_b])

        timeline_a_ids = [uid for block in a_id_blocks for uid in block]
        timeline_b_ids = [uid for block in b_id_blocks for uid in block]
        coordinate_a = (
            np.concatenate(coord_a_blocks)
            if coord_a_blocks
            else np.empty(0, dtype=np.float64)
        )
        coordinate_b = (
            np.concatenate(coord_b_blocks)
            if coord_b_blocks
            else np.empty(0, dtype=np.float64)
        )

        metadata = MatchMetadata(
            agent=agent,
            decision_criteria=_DECISION_CRITERIA,
            certainty=1.0,
        )
        return MatchClaimField.from_columns(
            timeline_a_ids,
            timeline_b_ids,
            coordinate_a,
            coordinate_b,
            metadata=metadata,
        )

    @staticmethod
    def _timeline_uid(key: str) -> str:
        """The seconds-timeline uid for an audio key: ``<stem>:cpt1``."""
        stem = os.path.splitext(os.path.basename(key))[0]
        return f"{stem}:cpt1"

    @staticmethod
    def _human_name(stem: str) -> str:
        """A human-readable timeline name from a stem (``-`` → space)."""
        return stem.replace("-", " ")

    # endregion

    # region Properties

    @property
    def claim_field(self) -> MatchClaimField:
        """The complete-topology pairwise claim field.

        Raises:
            RuntimeError: If ``load()`` has not been called yet.
        """
        if self._claim_field is None:
            raise RuntimeError(
                "No alignment loaded yet. Call load() before reading claim_field."
            )
        return self._claim_field

    @property
    def recording_keys(self) -> list[str]:
        """The recording stems, in sorted order."""
        return [self._stems[key] for key in self._keys]

    # endregion

    # region Domain Object Creation

    def create_bundle(self) -> "AlignmentBundle":
        """Assemble the AlignmentBundle from the loaded alignment.

        Each recording becomes an empty seconds
        :class:`ContinuousPhysicalTimeline` in its own group, and the complete
        pairwise claim field is added to the bundle.

        Note:
            ``add_match_claims`` takes a list, so the columnar
            :class:`MatchClaimField` is materialised to a list of
            :class:`MatchClaim` objects here.  This simple path is fine for the
            modest grids used in tests and notebooks.  For a whole-work file
            (on the order of a million claims) a columnar bundle-query path
            (vectorising ``get_matchstamp_at`` over a ``MatchClaimField``
            directly) is the documented next step; it is not implemented here.

        Returns:
            An ``AlignmentBundle`` with one group per recording and all
            cross-group pairwise claims.

        Raises:
            RuntimeError: If ``load()`` has not been called yet.
        """
        from timetoalign.alignment.bundle import AlignmentBundle

        if self._claim_field is None:
            raise RuntimeError(
                "No alignment loaded yet. Call load() before create_bundle()."
            )

        bundle = AlignmentBundle(name=self._name)
        for key in self._keys:
            timeline = self._make_timeline(key)
            stem = self._stems[key]
            bundle.add_timeline(timeline, uid=timeline.id, as_group=stem)

        bundle.add_match_claims(self._claim_field.to_claims())
        return bundle

    def create_timelines(self, id_pattern: str | None = None) -> list["Timeline"]:
        """Return one empty seconds timeline per recording, in sorted order.

        Args:
            id_pattern: Unused; present for base-class signature parity.
        """
        return [self._make_timeline(key) for key in self._keys]

    def create_timeline(self, id: str | None = None, **kwargs: Any) -> "Timeline":
        """Return a single recording's seconds timeline by its uid.

        Args:
            id: A timeline uid (``"<stem>:cpt1"``).

        Raises:
            KeyError: If no recording matches.
            RuntimeError: If ``load()`` has not been called yet.
        """
        if self._claim_field is None:
            raise RuntimeError(
                "No alignment loaded yet. Call load() before create_timeline()."
            )

        for key in self._keys:
            if id == self._timeline_uid(key):
                return self._make_timeline(key)

        available = [self._timeline_uid(key) for key in self._keys]
        raise KeyError(
            f"No timeline with uid '{id}'. Available: "
            + ", ".join(f"'{uid}'" for uid in available)
        )

    def _make_timeline(self, key: str) -> ContinuousPhysicalTimeline:
        """Build the empty seconds timeline for one recording key."""
        stem = self._stems[key]
        return ContinuousPhysicalTimeline(
            length=self._durations[key],
            unit=TimeUnit.seconds,
            uid=self._timeline_uid(key),
            name=self._human_name(stem),
        )

    # endregion

    # region HTML Representation

    def _repr_html_(self) -> str:
        """Accurate Jupyter summary consistent with :meth:`__repr__`.

        The base :class:`AlignmentLoader` HTML reads the unpopulated
        per-source ``AlignmentStore`` and reports ``Events: 0``, which
        contradicts this loader (whose data lives in the assembled timelines
        and the claim field).  This override renders the real shape: the
        recording count, the claim count, and the timeline / group structure
        (one empty seconds timeline per recording, each its own group).
        """
        n_recordings = len(self._keys)
        n_claims = len(self._claim_field) if self._claim_field is not None else 0
        loaded = self._claim_field is not None

        parts = [f"<h4>{self.__class__.__name__}</h4>", "<table>"]
        name = self._name or "(not loaded)"
        parts.append(f"<tr><td><b>File</b></td><td><code>{name}</code></td></tr>")
        parts.append(f"<tr><td><b>Recordings</b></td><td>{n_recordings}</td></tr>")
        parts.append(f"<tr><td><b>Claims</b></td><td>{n_claims}</td></tr>")

        if loaded:
            # One empty seconds timeline per recording, each in its own group.
            parts.append(
                f"<tr><td><b>Timelines</b></td><td>{n_recordings} "
                f"in {n_recordings} group(s)</td></tr>"
            )
            stems = ", ".join(f"<code>{s}</code>" for s in self.recording_keys)
            parts.append(f"<tr><td><b>Recordings</b></td><td>{stems}</td></tr>")

        parts.append(
            "<tr><td><b>Create</b></td>"
            "<td>create_bundle(), create_timeline(), create_timelines()</td></tr>"
        )
        parts.append("</table>")
        return "\n".join(parts)

    # endregion

    # region Magic Methods

    def __len__(self) -> int:
        """Number of pairwise claims in the loaded claim field.

        The inherited count reads the per-source ``AlignmentStore``, which this
        single-file loader never populates; the claim count is the meaningful
        size and keeps :meth:`_repr_html_` consistent with :meth:`__repr__`.
        """
        return len(self._claim_field) if self._claim_field is not None else 0

    def __repr__(self) -> str:
        n_recordings = len(self._keys)
        n_claims = len(self._claim_field) if self._claim_field is not None else 0
        return f"ListenHereLoader(recordings={n_recordings}, claims={n_claims})"

    # endregion


# endregion
