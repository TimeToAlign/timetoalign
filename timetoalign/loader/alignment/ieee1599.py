"""Ieee1599Loader: one IEEE 1599 document as a multimodal AlignmentBundle.

An IEEE 1599 file is a multi-layer XML encoding of a single musical work.  Its
pivot is the ``<spine>``: a flat list of ``<event>`` elements, each with an
``id``, that every other layer points back at through ``event_ref``.  The spine
is therefore an abstract, unit-less event ordering — a *virtual timing unit*
(VTU) axis — and each layer (symbolic notation, engraved page images, audio
recordings) states where in *its own* coordinate space a given spine event
occurs.  That is exactly an alignment: the spine is the hub, the layers are
projections, and ``event_ref`` is the correspondence.

``Ieee1599Loader`` reads one document in one call::

    bundle = Ieee1599Loader.from_file(path).create_bundle()

and produces a single :class:`~timetoalign.alignment.bundle.AlignmentBundle`:

============================  =========================================
IEEE 1599 construct           Time To Align! representation
============================  =========================================
``<spine>``                   ``DiscreteLogicalTimeline`` ``spine:dlt1``,
                              unit ``ticks``, ``NumberType.int``
``<logic><los>`` notes,       ONE ``DiscreteLogicalTimeline`` ``los:dlt2``,
rests and lyric syllables     unit ``ticks``
``<notational>`` per          ONE ``ContinuousGraphicalTimeline`` per
``graphic_instance_group``    group, page-image coordinates
``<audio>`` per ``<track>``   ONE ``ContinuousPhysicalTimeline``,
                              unit ``seconds``
every ``event_ref``           one synchronous ``MatchClaim``, projection
                              timeline against the spine, all of them in
                              one columnar ``MatchClaimField``
============================  =========================================

**Spine coordinates.**  The ``timing`` and ``hpos`` attributes of a spine
``<event>`` are *relative* integer deltas against the preceding event.  The
stored coordinate is the running sum — the cumulative VTU — so that two events
notated as simultaneous share one coordinate.  ``hpos`` is accumulated the same
way and kept as a single integer event field; the deltas are not stored
alongside, being recoverable by differencing.  Source event ids
(``part_1_voice0_measure1_ev0``, ``event_cow``, …) are preserved verbatim as
spine event ``id`` values, which is what makes ``event_ref`` resolvable on the
way back out.

**Projected layers.**  Every LOS, graphic and track event carries its raw
``event_ref`` as a field *and* contributes one synchronous claim tying its own
coordinate to the referenced spine event's VTU coordinate.  LOS events sit at
the VTU coordinate of the event they reference (that reference *is* their
temporal position); graphic events are interval events spanning
``upper_left_x`` to ``lower_right_x``; track events are instants at
``start_time`` seconds.

**Fidelity rules.**  Notated durations are kept as the verbatim ``num`` /
``den`` integer pair (``duration_num`` / ``duration_den``) rather than a
reduced :class:`~fractions.Fraction`, so that ``4/4`` does not silently become
``1``; the exact rational is ``Fraction(duration_num, duration_den)``.
``<undefined/>`` accidental placeholders are recorded as the string
``"undefined"``, never dropped and never inferred.  Media files are never
opened: ``file_name`` and ``file_format`` are recorded verbatim even when the
file is absent from disk, and even when the format label contradicts the
extension (``video_avi`` naming a ``.mp4``).

**Known limitations.**

* IEEE 1599 declares its page-image coordinates in pixels
  (``measurement_unit="pixels"`` on every ``<graphic_instance>``), and they
  are not integral in every specimen (``upper_left_x="992.96"``).  The
  timeline types pair ``TimeUnit.pixels`` exclusively with the integer-valued
  :class:`~timetoalign.timelines.types.DiscreteGraphicalTimeline`, whose
  rounding would destroy a coordinate the document states exactly, so the
  boxes are carried verbatim — unscaled — on a
  :class:`~timetoalign.timelines.types.ContinuousGraphicalTimeline` in
  ``points``, the continuous graphical unit that coincides with the pixel at
  72 dpi.  The declared ``measurement_unit`` is kept per page, so the
  document's own wording survives a round trip.
* The ``<structural>`` layer (``<analysis>`` segmentations and ``<petri_nets>``)
  is parsed by nothing yet; it is skipped with a debug log line pending the
  timeline-level external-reference mechanism it needs.
* ``<staff_list>`` clefs, key signatures and time signatures reference spine
  events but are not note/rest/lyric content; they are kept in the curated
  ``staff_list`` store table and do not become timeline events or claims.
* The ``performance`` layer does not occur in any known specimen and is
  skipped with a debug log line, as is any other unrecognised section.

See Also:
    timetoalign.AlignmentBundle
    timetoalign.MatchClaim
    timetoalign.MatchClaimField
    timetoalign.loader.format.xml.XmlLoader
"""

from __future__ import annotations

import logging
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pyarrow as pa
from typing_extensions import Self

from timetoalign.alignment.claims import (
    Agent,
    MatchClaim,
    MatchClaimField,
    MatchMetadata,
)
from timetoalign.core import AgentType, NumberType, TimeUnit
from timetoalign.core.fields import SemanticField
from timetoalign.display.html import code
from timetoalign.loader.format.xml import XmlLoader
from timetoalign.storage.events import EventData
from timetoalign.timelines.types import (
    ContinuousGraphicalTimeline,
    ContinuousPhysicalTimeline,
    DiscreteLogicalTimeline,
)

if TYPE_CHECKING:
    from timetoalign.alignment.bundle import AlignmentBundle
    from timetoalign.timelines.base import Timeline

module_logger = logging.getLogger(__name__)


# region Constants

#: Provenance recorded on every claim.  The alignment is not computed here: it
#: is read off the document's own ``event_ref`` cross-references.
_DEFAULT_AGENT = "IEEE 1599"
_AGENT_IDENTIFIER = "ieee1599_event_ref"

#: Document sections this loader represents.  Anything else is logged and
#: skipped (see the module docstring's limitations).
_KNOWN_SECTIONS = frozenset({"general", "logic", "notational", "audio"})

#: The unit graphic-event boxes are carried in.  The document measures them in
#: pixels, which the timeline types admit only with integer coordinates; the
#: values are stored unscaled (see the module docstring's limitations).
_GRAPHIC_UNIT = TimeUnit.points

# endregion


# region Layer specs


@dataclass
class _EditionSpec:
    """One ``<graphic_instance_group>``: an edition of the engraved score."""

    uid: str
    role: str
    description: str
    pages: list[dict[str, Any]] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class _TrackSpec:
    """One ``<track>``: an audio (or video) rendition of the work."""

    uid: str
    role: str
    file_name: str
    attributes: dict[str, Any] = field(default_factory=dict)
    performers: list[dict[str, Any]] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)


# endregion


# region Parsing helpers


def _int_or_none(value: str | None) -> int | None:
    """Parse an XML attribute as an ``int``, or ``None`` if absent/unparseable."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _float_or_none(value: str | None) -> float | None:
    """Parse an XML attribute as a ``float``, or ``None`` if absent/unparseable."""
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _text_or_none(element: ET.Element) -> str | None:
    """Return an element's stripped text content, or ``None`` if empty."""
    if element.text is None:
        return None
    text = element.text.strip()
    return text or None


def _prune_columns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop keys that are ``None`` in every row.

    Every row is built with the full key set of its layer so that the layers
    stay readable; a specimen without lyrics or without tuplets should not
    carry all-null columns into its timeline or its store table.

    Args:
        rows: Row dicts sharing one key set.

    Returns:
        The same rows, restricted to the keys that carry at least one value.
    """
    if not rows:
        return rows
    kept = [key for key in rows[0] if any(row[key] is not None for row in rows)]
    return [{key: row[key] for key in kept} for row in rows]


def _table_from_rows(rows: list[dict[str, Any]]) -> pa.Table:
    """Build a column-oriented ``pa.Table`` from uniformly-keyed row dicts."""
    if not rows:
        return pa.table({})
    return pa.table({key: [row[key] for row in rows] for key in rows[0]})


# endregion


# region Ieee1599Loader


class Ieee1599Loader(XmlLoader):
    """Load one IEEE 1599 document as a multimodal AlignmentBundle.

    The loader parses a single IEEE 1599 XML file and represents its spine as
    the hub timeline that every other layer is aligned to, exactly as the
    document's own ``event_ref`` cross-references state.  See the module
    docstring for the full construct-by-construct mapping and the fidelity
    rules.

    **Usage follows the standard loader two-phase pattern:**

    1. ``loader.load(path)`` — parse one IEEE 1599 file into curated tables.
    2. ``loader.create_bundle()`` — assemble the AlignmentBundle.
    3. ``loader.create_timeline(uid)`` / ``create_timelines()`` — retrieve
       individual timelines (built once, then cached).

    The parse phase fills a
    :class:`~timetoalign.storage.store.DictStore` with one curated table per
    layer — ``spine``, ``los``, ``staff_list``, ``notational``, ``audio`` —
    rather than the generic tag-flattening its ``XmlLoader`` base performs;
    the layers are too differently shaped for one auto-detected schema to
    describe them.

    Examples:
        >>> loader = Ieee1599Loader.from_file("gymnopedie_01.xml")
        >>> bundle = loader.create_bundle()
        >>> bundle.get_matchstamp_table(from_graph=True).num_rows > 0
        True
    """

    _default_unit = TimeUnit.ticks

    def __init__(self) -> None:
        super().__init__(principal_tags=[])
        # The spine is the loader's frame of reference: VTU ticks, integers.
        self._unit = TimeUnit.ticks
        self._number_type = NumberType.int
        self._events = EventData.empty(self._unit, self._number_type)
        self._logger = module_logger.getChild(self.__class__.__name__)

        self._used_roles: set[str] = set()
        self._spine_uid: str | None = None
        self._los_uid: str | None = None
        #: Spine event id -> cumulative VTU coordinate.
        self._spine_coordinates: dict[str, int] = {}
        self._spine_rows: list[dict[str, Any]] = []
        self._los_rows: list[dict[str, Any]] = []
        self._staff_rows: list[dict[str, Any]] = []
        self._editions: list[_EditionSpec] = []
        self._tracks: list[_TrackSpec] = []
        self._claim_field: MatchClaimField | None = None
        self._timeline_cache: dict[str, "Timeline"] = {}
        self._name: str | None = None

    # region Loading

    def load(self, *sources: Path | str) -> Self:
        """Ingest exactly one IEEE 1599 document.

        Args:
            *sources: A single path to an IEEE 1599 XML file.  The file may
                carry a UTF-8 BOM and a DOCTYPE declaration; no DTD is
                fetched and no media file is opened.

        Returns:
            Self, for method chaining.

        Raises:
            ValueError: If more than one source is given, or if this loader
                has already ingested a document.  One IEEE 1599 document is
                one self-contained work with its own spine; two documents are
                two bundles, so they need two loaders.
        """
        if len(sources) != 1:
            raise ValueError(
                "Ieee1599Loader ingests exactly one IEEE 1599 document per "
                f"loader; got {len(sources)} sources."
            )
        if self._spine_uid is not None:
            raise ValueError(
                "This Ieee1599Loader already holds "
                f"{self._sources[0].name if self._sources else 'a document'}. "
                "Each IEEE 1599 document is a self-contained bundle: use a "
                "new loader, or call clear() first."
            )
        self._name = Path(sources[0]).stem
        return super().load(*sources)

    def clear(self) -> None:
        """Discard the loaded document and every derived artefact."""
        super().clear()
        self._used_roles.clear()
        self._spine_uid = None
        self._los_uid = None
        self._spine_coordinates.clear()
        self._spine_rows.clear()
        self._los_rows.clear()
        self._staff_rows.clear()
        self._editions.clear()
        self._tracks.clear()
        self._claim_field = None
        self._timeline_cache.clear()
        self._name = None
        self._timeline_id_generator.reset()

    def _process_xml(self, root: ET.Element) -> None:
        """Parse one ``<ieee1599>`` root into curated tables and claim fields.

        Overrides the generic ``XmlLoader`` normalisation: the layers of an
        IEEE 1599 document have known, mutually incompatible shapes, so each
        is read into its own curated table instead of being auto-flattened.

        Args:
            root: The ``<ieee1599>`` root element.
        """
        self._read_metadata(root)
        self._read_spine(root)
        self._read_los(root)
        self._read_notational(root)
        self._read_audio(root)
        self._log_skipped_sections(root)
        self._store_tables()
        self._build_claim_field()

    def _read_metadata(self, root: ET.Element) -> None:
        """Collect root attributes and ``<general>`` bibliographic metadata."""
        metadata: dict[str, Any] = {
            key: value for key, value in root.attrib.items() if not key.startswith("_")
        }
        description = root.find("./general/description")
        if description is not None:
            for tag in ("main_title", "work_title", "work_number"):
                element = description.find(tag)
                if element is not None:
                    text = _text_or_none(element)
                    if text is not None:
                        metadata["title" if tag == "main_title" else tag] = text
            authors = [
                {"name": _text_or_none(author), "type": author.get("type")}
                for author in description.findall("author")
            ]
            if authors:
                metadata["authors"] = authors
        self._file_metadata.update(metadata)

    def _read_spine(self, root: ET.Element) -> None:
        """Accumulate the spine's relative deltas into absolute coordinates.

        ``timing`` and ``hpos`` are per-event deltas against the previous
        event; both are accumulated, the timing sum becoming the event's VTU
        coordinate and the hpos sum a single integer field.  Events notated as
        simultaneous carry ``timing="0"`` and so share a coordinate.
        """
        self._spine_uid = self._timeline_id_generator.next_id_with_role(
            DiscreteLogicalTimeline, self._claim_role("spine")
        )
        timing = 0
        hpos = 0
        for event in root.findall("./logic/spine/event"):
            event_id = event.get("id")
            if event_id is None:
                self._logger.debug("Skipping spine <event> without an id.")
                continue
            timing += _int_or_none(event.get("timing")) or 0
            hpos += _int_or_none(event.get("hpos")) or 0
            self._spine_coordinates[event_id] = timing
            self._spine_rows.append(
                {
                    "id": event_id,
                    "event_type": "SpineEvent",
                    "instant": timing,
                    "hpos": hpos,
                }
            )
        self._spine_rows = _prune_columns(self._spine_rows)

    def _read_los(self, root: ET.Element) -> None:
        """Read the ``<los>`` note / rest / lyric content and its staff list.

        Every LOS event is placed at the VTU coordinate of the spine event it
        references.  A ``<chord>`` contributes one event per ``<notehead>``
        (so that each event carries exactly one pitch); the chord is
        recoverable by grouping on ``event_ref`` and ordering by
        ``notehead_index``.
        """
        self._los_uid = self._timeline_id_generator.next_id_with_role(
            DiscreteLogicalTimeline, self._claim_role("los")
        )
        los = root.find("./logic/los")
        if los is None:
            return

        for staff in los.findall("./staff_list/staff"):
            self._read_staff(staff)

        for part in los.findall("part"):
            part_id = part.get("id")
            staff_by_voice = {
                item.get("id"): item.get("staff_ref")
                for item in part.findall("./voice_list/voice_item")
            }
            for measure in part.findall("measure"):
                measure_number = measure.get("number")
                for voice in measure.findall("voice"):
                    voice_id = voice.get("voice_item_ref")
                    context = {
                        "part": part_id,
                        "staff": staff_by_voice.get(voice_id),
                        "voice": voice_id,
                        "measure": measure_number,
                    }
                    for child in voice:
                        self._read_voice_child(child, context)

        for lyrics in los.findall("lyrics"):
            context = {
                "part": lyrics.get("part_ref"),
                "staff": None,
                "voice": lyrics.get("voice_ref"),
                "measure": None,
            }
            for syllable in lyrics.findall("syllable"):
                self._read_syllable(syllable, context)

        self._los_rows = _prune_columns(self._los_rows)
        self._staff_rows = _prune_columns(self._staff_rows)

    def _read_staff(self, staff: ET.Element) -> None:
        """Record a staff's clefs, key signatures and time signatures.

        These reference spine events but are notational attributes rather than
        note/rest/lyric content, so they are kept in the ``staff_list`` store
        table only — they become neither timeline events nor claims.
        """
        staff_id = staff.get("id")
        line_number = _int_or_none(staff.get("line_number"))
        for child in staff:
            row: dict[str, Any] = {
                "staff": staff_id,
                "line_number": line_number,
                "kind": child.tag,
                "event_ref": child.get("event_ref"),
                "shape": child.get("shape"),
                "staff_step": _int_or_none(child.get("staff_step")),
                "octave_num": _int_or_none(child.get("octave_num")),
                "sharp_num": None,
                "flat_num": None,
                "num": None,
                "den": None,
            }
            sharps = child.find("sharp_num")
            if sharps is not None:
                row["sharp_num"] = _int_or_none(sharps.get("number"))
            flats = child.find("flat_num")
            if flats is not None:
                row["flat_num"] = _int_or_none(flats.get("number"))
            indication = child.find("time_indication")
            if indication is not None:
                row["num"] = _int_or_none(indication.get("num"))
                row["den"] = _int_or_none(indication.get("den"))
            self._staff_rows.append(row)

    def _read_voice_child(self, element: ET.Element, context: dict[str, Any]) -> None:
        """Turn one ``<chord>`` or ``<rest>`` into LOS event rows."""
        if element.tag not in ("chord", "rest"):
            self._logger.debug("Skipping unhandled <voice> child <%s>.", element.tag)
            return

        event_ref = element.get("event_ref")
        coordinate = self._coordinate_of(event_ref, element.tag)
        if coordinate is None:
            return

        base = dict(context)
        base["event_ref"] = event_ref
        base["instant"] = coordinate
        base.update(self._duration_fields(element.find("duration")))
        dots = element.find("augmentation_dots")
        base["augmentation_dots"] = (
            _int_or_none(dots.get("number")) if dots is not None else None
        )

        if element.tag == "rest":
            self._los_rows.append(self._los_row(base, "Rest"))
            return

        for index, notehead in enumerate(element.findall("notehead")):
            row = dict(base)
            row["notehead_index"] = index
            pitch = notehead.find("pitch")
            if pitch is not None:
                row["step"] = pitch.get("step")
                row["octave"] = _int_or_none(pitch.get("octave"))
                row["actual_accidental"] = pitch.get("actual_accidental")
            printed = notehead.find("printed_accidentals")
            if printed is not None:
                # A ``<undefined/>`` placeholder is recorded as such: the
                # document declines to state the printed accidental, which is
                # not the same as there being none.
                row["printed_accidental"] = ";".join(child.tag for child in printed)
            row["tie"] = notehead.find("tie") is not None
            self._los_rows.append(self._los_row(row, "Note"))

    def _read_syllable(self, syllable: ET.Element, context: dict[str, Any]) -> None:
        """Turn one lyric ``<syllable>`` into a LOS event row."""
        event_ref = syllable.get("start_event_ref")
        coordinate = self._coordinate_of(event_ref, "syllable")
        if coordinate is None:
            return
        row = dict(context)
        row["event_ref"] = event_ref
        row["instant"] = coordinate
        row["text"] = _text_or_none(syllable)
        row["hyphen"] = syllable.get("hyphen")
        self._los_rows.append(self._los_row(row, "Syllable"))

    @staticmethod
    def _los_row(values: dict[str, Any], event_type: str) -> dict[str, Any]:
        """Complete one LOS row to the layer's full key set."""
        row: dict[str, Any] = {
            "event_type": event_type,
            "instant": None,
            "event_ref": None,
            "part": None,
            "staff": None,
            "voice": None,
            "measure": None,
            "notehead_index": None,
            "duration_num": None,
            "duration_den": None,
            "tuplet_enter_num": None,
            "tuplet_enter_den": None,
            "tuplet_in_num": None,
            "tuplet_in_den": None,
            "augmentation_dots": None,
            "step": None,
            "octave": None,
            "actual_accidental": None,
            "printed_accidental": None,
            "tie": None,
            "text": None,
            "hyphen": None,
        }
        row.update({key: values[key] for key in values if key in row})
        return row

    @staticmethod
    def _duration_fields(duration: ET.Element | None) -> dict[str, Any]:
        """Read ``<duration>`` verbatim, plus any ``<tuplet_ratio>``.

        The ``num`` / ``den`` pair is kept as two integers rather than a
        reduced :class:`~fractions.Fraction`: ``num="4" den="4"`` is a whole
        note *written as* four quarters and must round-trip as such, and the
        column name ``duration`` is reserved by the event machinery for a
        coordinate-valued interval length.  The exact notated value is
        ``Fraction(duration_num, duration_den)``.
        """
        fields: dict[str, Any] = {
            "duration_num": None,
            "duration_den": None,
            "tuplet_enter_num": None,
            "tuplet_enter_den": None,
            "tuplet_in_num": None,
            "tuplet_in_den": None,
        }
        if duration is None:
            return fields
        fields["duration_num"] = _int_or_none(duration.get("num"))
        fields["duration_den"] = _int_or_none(duration.get("den"))
        tuplet = duration.find("tuplet_ratio")
        if tuplet is not None:
            fields["tuplet_enter_num"] = _int_or_none(tuplet.get("enter_num"))
            fields["tuplet_enter_den"] = _int_or_none(tuplet.get("enter_den"))
            fields["tuplet_in_num"] = _int_or_none(tuplet.get("in_num"))
            fields["tuplet_in_den"] = _int_or_none(tuplet.get("in_den"))
        return fields

    def _read_notational(self, root: ET.Element) -> None:
        """Read one edition per ``<graphic_instance_group>``.

        A group's ``<graphic_instance>`` elements are the pages of one
        edition; their ``graphic_event`` boxes all land on that edition's
        single timeline, each keeping its page ``file_name`` and
        ``position_in_group`` so the page a box belongs to stays recoverable.
        """
        for group in root.findall("./notational/graphic_instance_group"):
            description = group.get("description") or "edition"
            role = self._claim_role(description)
            spec = _EditionSpec(
                uid=self._timeline_id_generator.next_id_with_role(
                    ContinuousGraphicalTimeline, role
                ),
                role=role,
                description=description,
                pages=[],
                rows=[],
            )
            for instance in group.findall("graphic_instance"):
                file_name = instance.get("file_name")
                position = _int_or_none(instance.get("position_in_group"))
                spec.pages.append(
                    {
                        "file_name": file_name,
                        "position_in_group": position,
                        "encoding_format": instance.get("encoding_format"),
                        "file_format": instance.get("file_format"),
                        "measurement_unit": instance.get("measurement_unit"),
                    }
                )
                for graphic in instance.findall("graphic_event"):
                    event_ref = graphic.get("event_ref")
                    if self._coordinate_of(event_ref, "graphic_event") is None:
                        continue
                    start = _float_or_none(graphic.get("upper_left_x"))
                    end = _float_or_none(graphic.get("lower_right_x"))
                    if start is None or end is None:
                        self._logger.debug(
                            "<graphic_event> for %r without a horizontal extent; "
                            "skipped.",
                            event_ref,
                        )
                        continue
                    spec.rows.append(
                        {
                            "event_type": "GraphicEvent",
                            "start": start,
                            "end": end,
                            "event_ref": event_ref,
                            "upper_left_y": _float_or_none(graphic.get("upper_left_y")),
                            "lower_right_y": _float_or_none(
                                graphic.get("lower_right_y")
                            ),
                            "file_name": file_name,
                            "position_in_group": position,
                        }
                    )
            spec.rows = _prune_columns(spec.rows)
            self._editions.append(spec)

    def _read_audio(self, root: ET.Element) -> None:
        """Read one physical timeline per ``<track>``.

        ``track_event`` start times are seconds.  The referenced media file is
        never opened: its name, declared formats and performers are recorded
        verbatim, whether or not the file exists and whether or not the
        declared ``file_format`` matches the extension.
        """
        for track in root.findall("./audio/track"):
            file_name = track.get("file_name") or "track"
            role = self._claim_role(Path(file_name).stem)
            spec = _TrackSpec(
                uid=self._timeline_id_generator.next_id_with_role(
                    ContinuousPhysicalTimeline, role
                ),
                role=role,
                file_name=file_name,
                attributes={
                    "encoding_format": track.get("encoding_format"),
                    "file_format": track.get("file_format"),
                },
                performers=[
                    {"name": performer.get("name"), "type": performer.get("type")}
                    for performer in track.findall("./track_general//performer")
                ],
                rows=[],
            )
            for indexing in track.findall("track_indexing"):
                spec.attributes.setdefault("timing_type", indexing.get("timing_type"))
                for event in indexing.findall("track_event"):
                    event_ref = event.get("event_ref")
                    if self._coordinate_of(event_ref, "track_event") is None:
                        continue
                    start_time = _float_or_none(event.get("start_time"))
                    if start_time is None:
                        self._logger.debug(
                            "<track_event> for %r without a start_time; skipped.",
                            event_ref,
                        )
                        continue
                    spec.rows.append(
                        {
                            "event_type": "TrackEvent",
                            "instant": start_time,
                            "event_ref": event_ref,
                            "file_name": file_name,
                        }
                    )
            spec.rows = _prune_columns(spec.rows)
            self._tracks.append(spec)

    def _log_skipped_sections(self, root: ET.Element) -> None:
        """Log every top-level section this loader does not represent."""
        skipped = [child.tag for child in root if child.tag not in _KNOWN_SECTIONS]
        if skipped:
            self._logger.debug(
                "Skipped unrepresented IEEE 1599 sections: %s", ", ".join(skipped)
            )

    def _coordinate_of(self, event_ref: str | None, origin: str) -> int | None:
        """Resolve an ``event_ref`` to its spine VTU coordinate.

        Args:
            event_ref: The referenced spine event id.
            origin: The referring element's tag, for the log message.

        Returns:
            The cumulative VTU coordinate, or ``None`` when the reference is
            missing or dangling (which is logged and skipped, never guessed).
        """
        if event_ref is None:
            self._logger.debug("<%s> without event_ref; skipped.", origin)
            return None
        coordinate = self._spine_coordinates.get(event_ref)
        if coordinate is None:
            self._logger.debug(
                "<%s> references unknown spine event %r; skipped.", origin, event_ref
            )
        return coordinate

    def _claim_role(self, label: str) -> str:
        """Sanitise *label* into a unique timeline-uid role.

        Accents are folded to their base letters, the result is lowercased,
        every run of characters outside ``[a-z0-9_]`` becomes a single ``_``,
        and a numeric suffix disambiguates a role already in use.
        """
        normalised = unicodedata.normalize("NFKD", label)
        folded = "".join(ch for ch in normalised if not unicodedata.combining(ch))
        role = re.sub(r"[^a-z0-9_]+", "_", folded.lower()).strip("_") or "unnamed"
        candidate = role
        suffix = 1
        while candidate in self._used_roles:
            suffix += 1
            candidate = f"{role}_{suffix}"
        self._used_roles.add(candidate)
        return candidate

    # endregion

    # region Curated tables

    def _store_tables(self) -> None:
        """Publish one curated table per layer into the ``DictStore``."""
        self._add_table("spine", self._spine_rows, TimeUnit.ticks, NumberType.int)
        self._add_table("los", self._los_rows, TimeUnit.ticks, NumberType.int)
        self._add_table("staff_list", self._staff_rows, TimeUnit.ticks, NumberType.int)
        self._add_table(
            "notational",
            [
                {"timeline_uid": spec.uid, "edition": spec.description, **row}
                for spec in self._editions
                for row in spec.rows
            ],
            _GRAPHIC_UNIT,
            NumberType.float,
        )
        self._add_table(
            "audio",
            [
                {"timeline_uid": spec.uid, "track": spec.file_name, **row}
                for spec in self._tracks
                for row in spec.rows
            ],
            TimeUnit.seconds,
            NumberType.float,
        )

    def _add_table(
        self,
        name: str,
        rows: list[dict[str, Any]],
        unit: TimeUnit,
        number_type: NumberType,
    ) -> None:
        """Wrap one curated row set as ``EventData`` under *name*."""
        if not rows:
            return
        self._store.add(name, EventData(_table_from_rows(rows), unit, number_type))

    # endregion

    # region Claims

    def _build_claim_field(self) -> None:
        """Build the document's single columnar claim field.

        Every projected event states where the spine event it references falls
        in that layer's own coordinate space, which is one synchronous claim
        ``projection@own_coordinate <-> spine@vtu``.  All three layers go into
        one field: the alignment they express is one alignment, hub-and-spoke
        around the spine, and the coordinate storage carries a unit per row,
        so ``ticks``, page-image coordinates and ``seconds`` sit side by side
        without a per-layer split.

        Claim counts run into the tens of thousands, so the field is assembled
        straight from parallel columns with
        :meth:`MatchClaimField.from_columns`; no :class:`MatchClaim` object is
        ever constructed.
        """
        metadata = MatchMetadata(
            agent=Agent(
                name=str(self._file_metadata.get("creator") or _DEFAULT_AGENT),
                type=AgentType.software,
                identifier=_AGENT_IDENTIFIER,
            ),
            certainty=1.0,
        )
        blocks: list[tuple[str | None, list[dict[str, Any]], str, TimeUnit]] = [
            (self._los_uid, self._los_rows, "instant", TimeUnit.ticks),
            *((spec.uid, spec.rows, "start", _GRAPHIC_UNIT) for spec in self._editions),
            *(
                (spec.uid, spec.rows, "instant", TimeUnit.seconds)
                for spec in self._tracks
            ),
        ]

        timeline_ids: list[str] = []
        units: list[TimeUnit] = []
        projection: list[float] = []
        spine: list[int] = []
        for uid, rows, coordinate_key, unit in blocks:
            if uid is None or not rows:
                continue
            timeline_ids.extend([uid] * len(rows))
            units.extend([unit] * len(rows))
            projection.extend(row[coordinate_key] for row in rows)
            spine.extend(self._spine_coordinates[row["event_ref"]] for row in rows)
        if not timeline_ids:
            return

        # ``unit_a`` is a per-row sequence: the claim coordinate storage keeps
        # one unit per row, which is what lets the three layers share a field.
        self._claim_field = MatchClaimField.from_columns(
            timeline_ids,
            [self._spine_uid] * len(timeline_ids),
            projection,
            np.asarray(spine, dtype=np.int64),
            unit_a=units,
            unit_b=TimeUnit.ticks,
            metadata=metadata,
        )

    def get_field(
        self,
        selector: type[MatchClaim] | type[SemanticField[Any]],
    ) -> MatchClaimField:
        """Return the spine-referenced claim field of the whole document.

        The loader's alignment is reached through the uniform field API, the
        same way any
        :class:`~timetoalign.storage.mixins.SemanticFieldAccessMixin` surfaces
        a semantic view::

            >>> field = loader.get_field(MatchClaim)
            >>> isinstance(field, MatchClaimField)
            True

        The selector may be the :class:`MatchClaim` scalar class or its paired
        :class:`MatchClaimField` class; both resolve to the single
        ``MatchClaimField`` this loader builds, which holds every LOS, graphic
        and track event's claim against the spine.

        Args:
            selector: ``MatchClaim`` or ``MatchClaimField``.

        Returns:
            The :class:`MatchClaimField` of every ``event_ref`` in the
            document.

        Raises:
            RuntimeError: If ``load()`` has not been called yet.
            TypeError: If *selector* is not ``MatchClaim`` /
                ``MatchClaimField``.
        """
        if self._claim_field is None:
            raise RuntimeError(
                "No document loaded yet. Call load() before get_field()."
            )
        if selector is MatchClaim or selector is MatchClaimField:
            return self._claim_field
        selector_name = getattr(selector, "__name__", repr(selector))
        raise TypeError(
            f"Ieee1599Loader.get_field() resolves only MatchClaim / "
            f"MatchClaimField; got {selector_name}."
        )

    # endregion

    # region Properties

    @property
    def claim_field(self) -> MatchClaimField | None:
        """The document's claim field, or ``None`` if nothing is loaded."""
        return self._claim_field

    @property
    def spine_uid(self) -> str | None:
        """The spine timeline's uid (``spine:dlt1``), or ``None`` if unloaded."""
        return self._spine_uid

    @property
    def los_uid(self) -> str | None:
        """The LOS timeline's uid (``los:dlt2``), or ``None`` if unloaded."""
        return self._los_uid

    @property
    def edition_uids(self) -> list[str]:
        """The graphical timeline uids, in document order."""
        return [spec.uid for spec in self._editions]

    @property
    def track_uids(self) -> list[str]:
        """The audio timeline uids, in document order."""
        return [spec.uid for spec in self._tracks]

    @property
    def timeline_uids(self) -> list[str]:
        """Every timeline uid: spine, LOS, editions, tracks."""
        uids = [uid for uid in (self._spine_uid, self._los_uid) if uid is not None]
        return uids + self.edition_uids + self.track_uids

    # endregion

    # region Domain Object Creation

    def create_bundle(self, **kwargs: Any) -> "AlignmentBundle":
        """Assemble the AlignmentBundle from the parsed document.

        Every timeline is added standalone — the connectivity is carried by
        the claims, which relate each projection to the spine, so no
        `TimelineGroup` is needed to express it.  The claim field is added
        columnar with
        :meth:`~timetoalign.alignment.bundle.AlignmentBundle.add_match_claim_field`
        rather than exploded into claim objects.

        Returns:
            An ``AlignmentBundle`` with one spine timeline, one LOS timeline,
            one timeline per edition and per track, and the projection claims.

        Raises:
            RuntimeError: If ``load()`` has not been called yet.
        """
        from timetoalign.alignment.bundle import AlignmentBundle

        if self._spine_uid is None:
            raise RuntimeError(
                "No document loaded yet. Call load() before create_bundle()."
            )

        bundle = AlignmentBundle(name=self._name)
        for timeline in self.create_timelines():
            bundle.add_timeline(timeline, uid=timeline.id)
        if self._claim_field is not None:
            bundle.add_match_claim_field(self._claim_field)
        return bundle

    def create_timelines(self, id_pattern: str | None = None) -> "list[Timeline]":
        """Return every timeline: spine, LOS, editions, tracks.

        Args:
            id_pattern: Optional regular expression filtering timeline uids.
        """
        timelines = [self.create_timeline(uid) for uid in self.timeline_uids]
        return [
            timeline
            for timeline in timelines
            if id_pattern is None or re.search(id_pattern, timeline.id)
        ]

    def create_timeline(self, uid: str | None = None, **kwargs: Any) -> "Timeline":
        """Return one timeline by uid, building it once and caching it.

        Args:
            uid: A timeline uid.  Defaults to the spine's.

        Returns:
            The built `Timeline`.

        Raises:
            RuntimeError: If ``load()`` has not been called yet.
            KeyError: If *uid* names no timeline of this document.
        """
        if self._spine_uid is None:
            raise RuntimeError(
                "No document loaded yet. Call load() before create_timeline()."
            )
        if uid is None:
            uid = self._spine_uid
        if uid in self._timeline_cache:
            return self._timeline_cache[uid]

        timeline = self._build_timeline(uid)
        self._timeline_cache[uid] = timeline
        return timeline

    def _build_timeline(self, uid: str) -> "Timeline":
        """Build the timeline identified by *uid* from its curated rows."""
        if uid == self._spine_uid:
            return self._build_logical(uid, "Spine", self._spine_rows)
        if uid == self._los_uid:
            return self._build_logical(
                uid, "Logically organised symbols", self._los_rows
            )
        for spec in self._editions:
            if spec.uid == uid:
                return self._build_graphical(spec)
        for spec in self._tracks:
            if spec.uid == uid:
                return self._build_physical(spec)
        raise KeyError(
            f"No timeline with uid {uid!r}. Available: {self.timeline_uids}."
        )

    def _build_logical(
        self, uid: str, name: str, rows: list[dict[str, Any]]
    ) -> DiscreteLogicalTimeline:
        """Build a VTU (ticks) timeline from instant rows."""
        length = max((row["instant"] for row in rows), default=0)
        timeline = DiscreteLogicalTimeline(
            length=length,
            unit=TimeUnit.ticks,
            number_type=NumberType.int,
            uid=uid,
            name=name,
        )
        if rows:
            timeline.add_events(rows)
        return timeline

    def _build_graphical(self, spec: _EditionSpec) -> ContinuousGraphicalTimeline:
        """Build one edition's graphical timeline from its graphic-event boxes.

        The coordinates are the document's own page-image numbers, unscaled;
        the unit each page declares them in is kept in ``meta["pages"]``.
        """
        length = max((row["end"] for row in spec.rows), default=0.0)
        timeline = ContinuousGraphicalTimeline(
            length=length,
            unit=_GRAPHIC_UNIT,
            number_type=NumberType.float,
            uid=spec.uid,
            name=spec.description,
            meta={"description": spec.description, "pages": spec.pages},
        )
        if spec.rows:
            timeline.add_events(spec.rows)
        return timeline

    def _build_physical(self, spec: _TrackSpec) -> ContinuousPhysicalTimeline:
        """Build one track's seconds timeline from its track events."""
        length = max((row["instant"] for row in spec.rows), default=0.0)
        timeline = ContinuousPhysicalTimeline(
            length=length,
            unit=TimeUnit.seconds,
            number_type=NumberType.float,
            uid=spec.uid,
            name=Path(spec.file_name).stem,
            meta={
                "file_name": spec.file_name,
                "performers": spec.performers,
                **spec.attributes,
            },
        )
        if spec.rows:
            timeline.add_events(spec.rows)
        return timeline

    # endregion

    # region HTML Representation

    def _repr_count_row(self) -> tuple[str, str]:
        """This loader's payload is spine-referenced claims."""
        return ("Claims", str(len(self)))

    def _repr_rows(self) -> list[tuple[str, str]]:
        """Extend the base rows with the IEEE 1599 layer shape."""
        rows = super()._repr_rows()
        rows.append(("File", code(self._name or "(not loaded)")))
        title = self._file_metadata.get("title")
        if title:
            rows.append(("Title", str(title)))
        rows.append(("Spine events", str(len(self._spine_rows))))
        rows.append(("LOS events", str(len(self._los_rows))))
        rows.append(("Editions", str(len(self._editions))))
        rows.append(("Tracks", str(len(self._tracks))))
        if self._claim_field is not None:
            rows.append(("Claims", str(len(self._claim_field))))
        return rows

    # endregion

    # region Magic Methods

    def __len__(self) -> int:
        """Total number of spine-referenced claims across all layers."""
        return 0 if self._claim_field is None else len(self._claim_field)

    def __repr__(self) -> str:
        if self._spine_uid is None:
            return "Ieee1599Loader(not loaded)"
        return (
            f"Ieee1599Loader(spine={len(self._spine_rows)}, "
            f"los={len(self._los_rows)}, editions={len(self._editions)}, "
            f"tracks={len(self._tracks)}, claims={len(self)})"
        )

    # endregion


# endregion
