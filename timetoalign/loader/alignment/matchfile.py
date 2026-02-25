"""MatchfileLoader: Loader for Vienna Match (.match) alignment files.

This module implements the ``MatchfileLoader`` class, which uses partitura
to parse ``.match`` files and produces:

- A shared ``ContinuousLogicalTimeline`` for the score side (quarter-beat
  coordinates).
- One ``DiscreteLogicalTimeline`` per performance (MIDI tick coordinates).
- ``MatchClaim`` objects linking score events to performance events.

The loader follows the standard two-phase pattern:

1. ``loader.load(*match_files)`` — parses files, builds internal state.
2. ``loader.create_alignment_bundle()`` — assembles an ``AlignmentBundle``.
3. ``loader.create_timeline(id)`` — retrieves individual timelines.

See Also:
    timetoalign.AlignmentBundle
    timetoalign.MatchClaim
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import partitura as pt
from typing_extensions import Self

from timetoalign.alignment.anchors import MatchClaim, MatchMetadata
from timetoalign.core import TimeUnit
from timetoalign.maps.linear import ScalarMap, ShiftMap
from timetoalign.timelines.types import (
    ContinuousLogicalTimeline,
    DiscreteLogicalTimeline,
)

if TYPE_CHECKING:
    from timetoalign.alignment.bundle import AlignmentBundle
    from timetoalign.timelines.base import Timeline

module_logger = logging.getLogger(__name__)


# region Constants

MATCH_META = MatchMetadata(
    agent="vienna_match_v1.0.0",
    decision_criteria="automatic",
    certainty=1.0,
)

# endregion


# region MatchfileLoader


class MatchfileLoader:
    """Load Vienna Match (.match) alignment files via partitura.

    A single ``MatchfileLoader`` instance is intended to process **all**
    ``.match`` files that share the same score (e.g. 22 performances of one
    piece). It builds a shared score timeline on the first compatible file
    and verifies subsequent files against it. Incompatible files (snote ID
    present with different coordinates) are rejected with a warning.

    **Usage follows the standard loader two-phase pattern:**

    1. ``loader.load(*match_files)`` — parses all files, builds internal state.
    2. ``loader.create_alignment_bundle()`` — assembles the result.
    3. ``loader.create_timeline(id)`` — retrieves individual timelines.

    Produces:

    - A ``ContinuousLogicalTimeline`` for the score side (quarter-beat
      coordinates; MIDI divisions available via the attached
      ``quarters_to_divs`` `ScalarMap` C-Map).
    - One ``DiscreteLogicalTimeline`` per performance (MIDI tick coordinates;
      seconds available via the attached ``ticks_to_seconds`` `ScalarMap`).
    - One `MatchClaim` per alignment record per file:
      - Matched notes produce ``MatchClaim.from_events()`` (synchronous
        interval claim).
      - Deletion records produce ``MatchClaim.nomatch()`` (non-synchronous,
        NOMATCH).

    All MatchClaims carry ``MatchMetadata(agent="vienna_match_v1.0.0",
    decision_criteria="automatic", certainty=1.0)``.

    **Coordinate system and normalisation:**
    Score coordinates are stored as **normalised TTA coordinates** (shifted
    so the minimum onset is 0.0). A ``ShiftMap`` named
    ``"raw_to_normalised"`` is attached to the score timeline to expose
    the raw partitura values. The shift amount is computed from the file
    itself and never hardcoded.

    **External score timeline:**
    Pass a score timeline previously built by ``PartituraLoader`` via the
    ``score_timeline=`` parameter of ``create_alignment_bundle()``. The
    loader verifies compatibility (matching snote IDs and coordinates) and
    references the supplied timeline in all MatchClaims. MatchClaims are
    never rebound after creation.

    See Also:
        timetoalign.MatchClaim
        timetoalign.AlignmentBundle

    Args:
        score_unit: Primary unit for the score timeline.
            Default ``TimeUnit.quarters``.
        normalize_anacrusis: If True (default), attach a ``ShiftMap`` that
            maps raw coordinates to normalised (non-negative) coordinates.
            Has no effect on the stored event coordinates, which are always
            the normalised (non-negative) values.
    """

    def __init__(
        self,
        score_unit: TimeUnit = TimeUnit.quarters,
        normalize_anacrusis: bool = True,
    ) -> None:
        self._score_unit = score_unit
        self._normalize_anacrusis = normalize_anacrusis
        self._logger = module_logger.getChild("MatchfileLoader")

        # Internal state accumulated across load() calls
        self._score_timeline: ContinuousLogicalTimeline | None = None
        self._performance_timelines: list[DiscreteLogicalTimeline] = []
        self._claims: list[MatchClaim] = []
        self._rejected_files: list[Path] = []
        self._sources: list[Path] = []

        # Score event tracking: snote_id -> (start, end) in TTA coords
        self._score_events: dict[str, tuple[float, float]] = {}

        # Anacrusis offset (computed from first file)
        self._anacrusis_offset: float = 0.0

        # Header info from first file
        self._midi_clock_units: int | None = None
        self._midi_clock_rate: int | None = None
        self._piece_name: str | None = None

    # region Properties

    @property
    def anacrusis_offset(self) -> float:
        """The anacrusis offset applied to raw score coordinates.

        Equals ``-min(raw_onsets)`` from the first loaded file. Zero if
        no anacrusis or if no files have been loaded.
        """
        return self._anacrusis_offset

    @property
    def rejected_files(self) -> list[Path]:
        """Files rejected due to incompatible score coordinates."""
        return list(self._rejected_files)

    @property
    def sources(self) -> list[Path]:
        """All files passed to ``load()`` (including rejected ones)."""
        return list(self._sources)

    # endregion

    # region Loading

    def load(self, *sources: Path | str) -> Self:
        """Load one or more .match files.

        Parses each file via partitura, builds a shared score timeline
        from the first compatible file, and verifies subsequent files
        against it. Incompatible files are logged with a warning and
        tracked internally.

        This method can be called multiple times to add more files
        incrementally.

        Args:
            *sources: Paths to ``.match`` files.

        Returns:
            Self, for method chaining.

        Raises:
            FileNotFoundError: If any source path does not exist.
            ValueError: If any source is not a ``.match`` file.

        Examples:
            >>> loader = MatchfileLoader()
            >>> loader.load("Chopin_op10_no3_p01.match")
            >>> # or load all at once
            >>> loader.load(*sorted(data_dir.glob("*.match")))
        """
        for source in sources:
            path = Path(source)

            if not path.exists():
                raise FileNotFoundError(f"File not found: {path}")
            if path.suffix.lower() != ".match":
                raise ValueError(f"Not a .match file: {path}")

            self._sources.append(path)
            self._load_source(path)

        return self

    def _load_source(self, path: Path) -> None:
        """Parse a single .match file and accumulate internal state.

        On the first compatible file: builds the shared score timeline
        and attaches C-Maps. On subsequent files: verifies score events
        against the shared timeline and rejects the file on first
        incompatibility.

        Args:
            path: Path to the .match file.
        """
        import warnings

        self._logger.debug(f"Loading {path.name}")

        # Parse with partitura
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            perf, alignment, score = pt.load_match(str(path), create_score=True)

        # Extract header info from file
        header = self._parse_header(path)
        midi_clock_units = header.get("midiClockUnits", 480)
        midi_clock_rate = header.get("midiClockRate", 500000)
        piece_name = header.get("piece", path.stem.rsplit("_", 1)[0])
        midi_filename = header.get("midiFileName", path.stem + ".mid")
        perf_stem = Path(midi_filename).stem

        # Store header info from first file
        if self._midi_clock_units is None:
            self._midi_clock_units = midi_clock_units
            self._midi_clock_rate = midi_clock_rate
            self._piece_name = piece_name

        # Build note array for score coordinates
        score_na = pt.compute_note_array(score)
        score_by_id = {score_na[i]["id"]: score_na[i] for i in range(len(score_na))}

        # Build lookup for performance notes
        pp = perf[0]  # First (and only) PerformedPart
        perf_notes = pp.notes
        perf_by_id = {n["id"]: n for n in perf_notes}

        # Build alignment lookups
        matches = [a for a in alignment if a["label"] == "match"]
        deletions = [a for a in alignment if a["label"] == "deletion"]

        # Compute anacrusis offset from raw score onsets (first file only)
        is_first_file = self._score_timeline is None
        if is_first_file:
            raw_onsets = [float(score_by_id[sid]["onset_beat"]) for sid in score_by_id]
            min_onset = min(raw_onsets)
            self._anacrusis_offset = -min_onset if min_onset < 0 else 0.0

        offset = self._anacrusis_offset

        # Phase 1: Verify or add score events to the shared timeline
        if is_first_file:
            # Compute timeline length from max offset + duration
            raw_onsets = [float(score_by_id[sid]["onset_beat"]) for sid in score_by_id]
            raw_durations = [
                float(score_by_id[sid]["duration_beat"]) for sid in score_by_id
            ]
            max_end = max(onset + dur for onset, dur in zip(raw_onsets, raw_durations))
            timeline_length = max_end + offset

            self._score_timeline = ContinuousLogicalTimeline(
                length=timeline_length,
                unit=self._score_unit,
                uid=f"score:{piece_name}",
            )

            # Add all score events to the timeline
            score_event_dicts = []
            for sid, row in score_by_id.items():
                onset_raw = float(row["onset_beat"])
                dur = float(row["duration_beat"])
                onset_tta = onset_raw + offset
                end_tta = onset_raw + dur + offset
                score_event_dicts.append(
                    {
                        "id": sid,
                        "start": onset_tta,
                        "end": end_tta,
                    }
                )
                self._score_events[sid] = (onset_tta, end_tta)

            self._score_timeline.add_events(score_event_dicts)

            # Attach ShiftMap for raw_to_normalised
            if self._normalize_anacrusis and offset != 0.0:
                shift_map = ShiftMap(
                    offset=offset,
                    source_unit=self._score_unit,
                    target_unit=self._score_unit,
                    uid="raw_to_normalised",
                    name="raw_to_normalised",
                )
                self._score_timeline.add_conversion_map(shift_map)

            # Attach ScalarMap for quarters_to_divs
            divs_map = ScalarMap(
                scalar=midi_clock_units,
                source_unit=TimeUnit.quarters,
                target_unit=TimeUnit.ticks,
                uid="quarters_to_divs",
                name="quarters_to_divs",
            )
            self._score_timeline.add_conversion_map(divs_map)

            self._logger.debug(
                f"Built score timeline '{self._score_timeline.id}' with "
                f"{len(score_event_dicts)} events, anacrusis_offset={offset}"
            )

        else:
            # Subsequent file: verify compatibility
            incompatible = False
            for sid, row in score_by_id.items():
                onset_raw = float(row["onset_beat"])
                dur = float(row["duration_beat"])
                onset_tta = onset_raw + offset
                end_tta = onset_raw + dur + offset

                if sid in self._score_events:
                    stored_start, stored_end = self._score_events[sid]
                    if abs(stored_start - onset_tta) > 1e-10:
                        self._logger.warning(
                            "File '%s': snote '%s' has onset %s but timeline "
                            "stores %s — file rejected.",
                            path.name,
                            sid,
                            onset_tta,
                            stored_start,
                        )
                        incompatible = True
                        break
                else:
                    # New event not yet on timeline — add it
                    self._score_events[sid] = (onset_tta, end_tta)
                    self._score_timeline.add_events(
                        [{"id": sid, "start": onset_tta, "end": end_tta}],
                        allow_expansion=True,
                    )

            if incompatible:
                self._rejected_files.append(path)
                self._logger.warning(
                    "File '%s' rejected due to incompatible score coordinates.",
                    path.name,
                )
                return

        # Phase 2: Build performance timeline
        perf_event_dicts = []
        for note in perf_notes:
            perf_event_dicts.append(
                {
                    "id": note["id"],
                    "start": float(note["note_on_tick"]),
                    "end": float(note["note_off_tick"]),
                }
            )

        # Compute performance timeline length
        if perf_event_dicts:
            perf_max = max(float(e["end"]) for e in perf_event_dicts)
        else:
            perf_max = 0.0

        perf_tl = DiscreteLogicalTimeline(
            length=perf_max,
            unit=TimeUnit.ticks,
            uid=f"perf:{perf_stem}",
        )
        perf_tl.add_events(perf_event_dicts)

        # Attach ticks_to_seconds ScalarMap
        seconds_per_tick = midi_clock_rate / (midi_clock_units * 1_000_000)
        ticks_to_secs = ScalarMap(
            scalar=seconds_per_tick,
            source_unit=TimeUnit.ticks,
            target_unit=TimeUnit.seconds,
            uid=f"ticks_to_seconds:{perf_stem}",
            name="ticks_to_seconds",
        )
        perf_tl.add_conversion_map(ticks_to_secs)

        self._performance_timelines.append(perf_tl)

        self._logger.debug(
            f"Built performance timeline '{perf_tl.id}' with "
            f"{len(perf_event_dicts)} events"
        )

        # Phase 3: Build MatchClaims
        score_tl_id = self._score_timeline.id
        perf_tl_id = perf_tl.id

        # Matched notes: synchronous interval claims
        for match_record in matches:
            score_id = match_record["score_id"]
            perf_id = match_record["performance_id"]

            if score_id not in self._score_events:
                self._logger.warning(
                    "Match references unknown score note '%s' in file '%s'",
                    score_id,
                    path.name,
                )
                continue

            if perf_id not in perf_by_id:
                self._logger.warning(
                    "Match references unknown performance note '%s' in file '%s'",
                    perf_id,
                    path.name,
                )
                continue

            score_start, score_end = self._score_events[score_id]
            perf_note = perf_by_id[perf_id]
            perf_start = float(perf_note["note_on_tick"])
            perf_end = float(perf_note["note_off_tick"])

            claim = MatchClaim.from_events(
                event_a={"start": score_start, "end": score_end},
                tl_a_id=score_tl_id,
                event_b={"start": perf_start, "end": perf_end},
                tl_b_id=perf_tl_id,
                coord_key="start",
                end_coord_key="end",
                metadata=MATCH_META,
            )
            self._claims.append(claim)

        # Deletion records: non-synchronous NOMATCH claims
        for del_record in deletions:
            score_id = del_record["score_id"]

            if score_id not in self._score_events:
                self._logger.warning(
                    "Deletion references unknown score note '%s' in file '%s'",
                    score_id,
                    path.name,
                )
                continue

            score_start, _ = self._score_events[score_id]
            claim = MatchClaim.nomatch(
                event={"start": score_start},
                source_tl_id=score_tl_id,
                target_tl_id=perf_tl_id,
                metadata=MATCH_META,
            )
            self._claims.append(claim)

        self._logger.debug(
            f"Created {len(matches)} match claims and {len(deletions)} "
            f"NOMATCH claims for '{path.name}'"
        )

    # endregion

    # region Header Parsing

    @staticmethod
    def _parse_header(path: Path) -> dict[str, Any]:
        """Parse ``info(...)`` header lines from a .match file.

        Args:
            path: Path to the .match file.

        Returns:
            Dictionary mapping header keys to values.
        """
        header: dict[str, Any] = {}
        info_pattern = re.compile(r"^info\((\w+),(.+)\)\.\s*$")

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.startswith("info("):
                    # Headers are at the top; stop at first non-info line
                    if not line.startswith("%"):
                        break
                    continue

                m = info_pattern.match(line)
                if m:
                    key, value = m.group(1), m.group(2)
                    # Try to convert to int
                    try:
                        header[key] = int(value)
                    except ValueError:
                        header[key] = value

        return header

    # endregion

    # region Domain Object Creation

    def create_alignment_bundle(
        self,
        score_timeline: "Timeline | None" = None,
    ) -> "AlignmentBundle":
        """Assemble an AlignmentBundle from the loaded data.

        Returns an ``AlignmentBundle`` directly. The bundle contains:

        - The score timeline in its own group (``as_group="score"``)
        - Each performance timeline as a standalone timeline
        - All MatchClaims as cross-group claims

        This method takes NO file arguments. Files must be loaded first
        via ``load()``.

        Args:
            score_timeline: Optional pre-existing score timeline. When
                supplied, the bundle uses this timeline instead of the
                loader's internally built one. MatchClaims are NOT
                rebound — they still reference the internally built
                score timeline's uid. For correct cross-referencing,
                the external timeline should have the same uid.

        Returns:
            ``AlignmentBundle`` with score group + standalone performances
            + MatchClaims.

        Raises:
            RuntimeError: If ``load()`` has not been called yet.

        Examples:
            >>> loader = MatchfileLoader()
            >>> loader.load(*match_files)
            >>> bundle = loader.create_alignment_bundle()
            >>> len(bundle.timelines)  # score + 22 performances
            23
        """
        from timetoalign.alignment.bundle import AlignmentBundle

        if self._score_timeline is None:
            raise RuntimeError(
                "No files loaded yet. Call load() before " "create_alignment_bundle()."
            )

        actual_score = (
            score_timeline if score_timeline is not None else self._score_timeline
        )

        bundle = AlignmentBundle()
        bundle.add_timeline(actual_score, uid="score", as_group="score")

        for perf_tl in self._performance_timelines:
            bundle.add_timeline(perf_tl)

        bundle.add_match_claims(self._claims)

        return bundle

    def create_timeline(self, id: str) -> "Timeline":
        """Return a single timeline by uid or role string.

        Args:
            id: Timeline uid (e.g. ``"score:Chopin_op10_no3"``) or a role
                shorthand. For MatchfileLoader:

                - ``"score"`` returns the shared score timeline.
                - ``"perf:N"`` (1-indexed) returns the N-th performance
                  timeline (e.g. ``"perf:1"`` for the first loaded file).
                - The full uid of any loaded timeline is also accepted
                  (e.g. ``"perf:Chopin_op10_no3_p01"``).

        Returns:
            The matching Timeline.

        Raises:
            KeyError: If no timeline with the given uid or role exists.
            RuntimeError: If ``load()`` has not been called yet.
        """
        if self._score_timeline is None:
            raise RuntimeError(
                "No files loaded yet. Call load() before create_timeline()."
            )

        # Direct match: "score" role
        if id == "score":
            return self._score_timeline

        # Direct match: score timeline uid
        if id == self._score_timeline.id:
            return self._score_timeline

        # Check performance timelines by uid
        for perf_tl in self._performance_timelines:
            if id == perf_tl.id:
                return perf_tl

        # Check "perf:N" shorthand (1-indexed)
        if id.startswith("perf:"):
            suffix = id[5:]
            try:
                idx = int(suffix) - 1  # 1-indexed to 0-indexed
                if 0 <= idx < len(self._performance_timelines):
                    return self._performance_timelines[idx]
            except ValueError:
                pass

        # Check "perf:pNN" shorthand
        if id.startswith("perf:p"):
            suffix = id[6:]
            try:
                idx = int(suffix) - 1  # 1-indexed to 0-indexed
                if 0 <= idx < len(self._performance_timelines):
                    return self._performance_timelines[idx]
            except ValueError:
                pass

        raise KeyError(
            f"No timeline with id or role '{id}'. "
            f"Available: 'score', "
            + ", ".join(f"'{tl.id}'" for tl in self._performance_timelines)
        )

    def create_timelines(self) -> list["Timeline"]:
        """Return all timelines produced from loaded data.

        For MatchfileLoader: ``[score_timeline, perf_p01, ..., perf_pN]``.
        The score timeline is always first.

        Returns:
            List of Timeline objects. Empty if ``load()`` has not been
            called yet.
        """
        if self._score_timeline is None:
            return []
        return [self._score_timeline] + list(self._performance_timelines)

    # endregion

    # region Magic Methods

    def __repr__(self) -> str:
        """Return string representation."""
        n_perf = len(self._performance_timelines)
        n_claims = len(self._claims)
        n_rejected = len(self._rejected_files)
        return (
            f"MatchfileLoader(performances={n_perf}, "
            f"claims={n_claims}, rejected={n_rejected})"
        )

    def __len__(self) -> int:
        """Return total number of loaded performance timelines."""
        return len(self._performance_timelines)

    # endregion


# endregion
