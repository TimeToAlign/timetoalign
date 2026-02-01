"""Music21Loader: Load scores using music21."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any

import music21 as m21

from timetoalign.core import NumberType, TimeUnit
from timetoalign.loader.schema import fraction_to_struct

from .base import ScoreLoader
from .bundle import ScoreStore
from .stores import (
    AnnotationEventData,
    ControlEventData,
    MeasureData,
    NoteEventData,
)


class Music21Loader(ScoreLoader):
    """Load symbolic scores using music21.

    Returns ScoreStore with category-specific data.
    Uses recursive element parsing to extract:
    - Notes/Rests (with chord expansion)
    - Measures (structure)
    - Controls (dynamics, tempo, etc.)
    - Annotations (text)
    """

    def _load_source(self, source: Path) -> ScoreStore:
        """Load score and return ScoreStore."""
        score = m21.converter.parse(str(source), forceSource=True)

        note_rows = []
        measure_rows = []
        control_rows = []
        annotation_rows = []
        has_rests = False

        parts = score.parts if score.hasPartLikeStreams() else [score]

        for part_idx, part in enumerate(parts):
            part_id = part.id or f"P{part_idx+1}"

            # Get measure list for MC lookup
            measure_list = list(part.getElementsByClass(m21.stream.Measure))
            measure_offsets = [
                (float(m.offset), i + 1, m) for i, m in enumerate(measure_list)
            ]

            def get_mc_and_onset(offset: float) -> tuple[int | None, Fraction]:
                """Find MC and offset from measure start."""
                mc = None
                mc_onset = Fraction(0)
                for m_off, idx, m in reversed(measure_offsets):
                    if m_off <= offset + 1e-5:
                        mc = idx
                        mc_onset = Fraction(offset - m_off).limit_denominator(10000)
                        break
                return mc, mc_onset

            # ===== Extract Volta (RepeatBracket) information =====
            # Build mapping of measure offset -> volta number
            volta_by_offset: dict[float, int] = {}
            for rb in part.flatten().getElementsByClass(m21.spanner.RepeatBracket):
                volta_num = rb.number
                if volta_num is not None:
                    for el in rb.getSpannedElements():
                        if isinstance(el, m21.stream.Measure):
                            volta_by_offset[float(el.offset)] = int(volta_num)

            # Process Measures
            for i, m in enumerate(measure_list):
                qb = Fraction(float(m.offset)).limit_denominator(10000)
                dur = Fraction(float(m.duration.quarterLength)).limit_denominator(10000)

                # ===== Extract Repeat Barline Information =====
                # Check left barline for repeat start
                start_repeat = False
                left_bl = m.leftBarline
                if left_bl is not None:
                    if isinstance(left_bl, m21.bar.Repeat):
                        if getattr(left_bl, "direction", None) == "start":
                            start_repeat = True
                    elif left_bl.type == "heavy-light":
                        start_repeat = True

                # Check right barline for repeat end
                end_repeat = False
                right_bl = m.rightBarline
                if right_bl is not None:
                    if isinstance(right_bl, m21.bar.Repeat):
                        if getattr(right_bl, "direction", None) == "end":
                            end_repeat = True
                    elif right_bl.type == "light-heavy":
                        end_repeat = True

                # Get volta number if this measure is in a repeat bracket
                volta = volta_by_offset.get(float(m.offset))

                measure_rows.append(
                    {
                        "id": f"measure_{i+1}",
                        "name": str(m.number),
                        "temporal_type": "interval",
                        "event_type": "Measure",
                        "quarterbeats": fraction_to_struct(qb),
                        "quarterbeats_float": float(qb),
                        "duration_qb": fraction_to_struct(dur),
                        "duration_qb_float": float(dur),
                        "mc": i + 1,
                        "mn": str(m.number),
                        "timesig": None,
                        # Flow control fields
                        "start_repeat": start_repeat,
                        "end_repeat": end_repeat,
                        "volta": volta,
                        "part_id": part_id,
                    }
                )

            # Process Notes/Rests/Controls
            flat_part = part.flatten()

            for obj in flat_part:
                if isinstance(
                    obj, (m21.stream.Measure, m21.stream.Part, m21.stream.Score)
                ):
                    continue

                offset = float(obj.offset)
                duration = float(obj.duration.quarterLength)
                qb = Fraction(offset).limit_denominator(10000)
                dur_qb = Fraction(duration).limit_denominator(10000)
                mc, mc_onset = get_mc_and_onset(offset)
                mn = (
                    str(obj.measureNumber)
                    if obj.measureNumber is not None
                    else str(mc) if mc else None
                )

                # Notes (Rests are tracked but not added to notes store)
                # Music21 creates implicit rests that don't exist in source.
                # Gold standard (MS3 TSV) and Partitura exclude these.
                if isinstance(obj, m21.note.GeneralNote):
                    if isinstance(obj, m21.note.Rest):
                        # Track that rests exist but don't add to notes store
                        has_rests = True
                        # Skip adding rest to notes store - matches gold standard
                    elif isinstance(obj, m21.note.Note):
                        note_rows.append(
                            self._make_note_row(
                                obj, qb, dur_qb, mc, mn, mc_onset, part_id
                            )
                        )
                    elif isinstance(obj, m21.chord.Chord):
                        for note in obj.notes:
                            note_rows.append(
                                self._make_note_row(
                                    note,
                                    qb,
                                    dur_qb,
                                    mc,
                                    mn,
                                    mc_onset,
                                    part_id,
                                    chord_id=id(obj),
                                )
                            )

                # Controls
                elif isinstance(
                    obj,
                    (
                        m21.dynamics.Dynamic,
                        m21.tempo.TempoIndication,
                        m21.key.KeySignature,
                        m21.meter.TimeSignature,
                    ),
                ):
                    control_rows.append(
                        {
                            "id": (
                                str(obj.id) if hasattr(obj, "id") else f"ctrl_{offset}"
                            ),
                            "name": obj.__class__.__name__,
                            "temporal_type": "instant",
                            "event_type": obj.__class__.__name__,
                            "quarterbeats": fraction_to_struct(qb),
                            "quarterbeats_float": float(qb),
                            "duration_qb": None,
                            "duration_qb_float": 0.0,
                            "mc": mc,
                            "mn": mn,
                            "mc_onset": (
                                fraction_to_struct(mc_onset)
                                if mc_onset is not None
                                else None
                            ),
                            "mn_onset": (
                                fraction_to_struct(mc_onset)
                                if mc_onset is not None
                                else None
                            ),
                            "subtype": obj.__class__.__name__,
                            "value": None,
                            "text": str(obj),
                            "voice": None,
                            "staff": None,
                            "part_id": part_id,
                        }
                    )

                # Annotations
                elif isinstance(obj, m21.expressions.TextExpression):
                    annotation_rows.append(
                        {
                            "id": (
                                str(obj.id) if hasattr(obj, "id") else f"ann_{offset}"
                            ),
                            "name": getattr(obj, "content", str(obj)),
                            "temporal_type": "instant",
                            "event_type": "TextExpression",
                            "quarterbeats": fraction_to_struct(qb),
                            "quarterbeats_float": float(qb),
                            "duration_qb": None,
                            "duration_qb_float": 0.0,
                            "mc": mc,
                            "mn": mn,
                            "mc_onset": (
                                fraction_to_struct(mc_onset)
                                if mc_onset is not None
                                else None
                            ),
                            "mn_onset": (
                                fraction_to_struct(mc_onset)
                                if mc_onset is not None
                                else None
                            ),
                            "subtype": "TextExpression",
                            "text": getattr(obj, "content", str(obj)),
                            "staff": None,
                            "part_id": part_id,
                        }
                    )

        # Build data
        notes_data = NoteEventData.from_dicts(
            note_rows,
            unit=TimeUnit.quarters,
            number_type=NumberType.fraction,
            has_rests=has_rests,
        )

        measures_data = (
            MeasureData.from_dicts(
                measure_rows,
                unit=TimeUnit.quarters,
                number_type=NumberType.fraction,
            )
            if measure_rows
            else MeasureData.empty()
        )

        controls_data = (
            ControlEventData.from_dicts(
                control_rows,
                unit=TimeUnit.quarters,
                number_type=NumberType.fraction,
            )
            if control_rows
            else ControlEventData.empty()
        )

        annotations_data = (
            AnnotationEventData.from_dicts(
                annotation_rows,
                unit=TimeUnit.quarters,
                number_type=NumberType.fraction,
            )
            if annotation_rows
            else AnnotationEventData.empty()
        )

        return ScoreStore(
            notes=notes_data,
            measures=measures_data,
            controls=controls_data,
            annotations=annotations_data,
            metadata={
                "format": "score",
                "parser": "music21",
                "source": str(source),
                "has_rests": has_rests,
            },
        )

    def _make_note_row(
        self,
        obj: Any,
        qb: Fraction,
        dur_qb: Fraction,
        mc: int | None,
        mn: str | None,
        mc_onset: Fraction,
        part_id: str,
        is_rest: bool = False,
        chord_id: int | None = None,
    ) -> dict[str, Any]:
        """Create note row dict."""
        midi_pitch = None
        spelled_pitch = None
        octave = None
        tpc = None

        if not is_rest and hasattr(obj, "pitch"):
            ep = int(obj.pitch.midi)
            midi_pitch = {"ep": ep, "epc": ep % 12}

            step = obj.pitch.step
            alter = int(obj.pitch.alter or 0)
            octave = obj.pitch.octave or 4

            gpc_map = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
            gpc_int = gpc_map.get(step, 0)

            acc_str = ""
            if alter > 0:
                acc_str = "♯" * alter
            elif alter < 0:
                acc_str = "♭" * abs(alter)

            base_fifths = {"F": -1, "C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5}
            spc_int = base_fifths.get(step, 0) + (7 * alter)
            tpc = spc_int

            spelled_pitch = {
                "gpc_int": gpc_int,
                "gpc_str": step,
                "acc": alter,
                "spc_int": spc_int,
                "spc_str": f"{step}{acc_str}",
                "sp": f"{step}{acc_str}{octave}",
                "cents": 0.0,
            }

        return {
            "id": str(obj.id) if hasattr(obj, "id") else f"note_{float(qb)}",
            "name": "",
            "temporal_type": "interval" if dur_qb > 0 else "instant",
            "event_type": "Rest" if is_rest else "Note",
            "quarterbeats": fraction_to_struct(qb),
            "quarterbeats_float": float(qb),
            "duration_qb": fraction_to_struct(dur_qb),
            "duration_qb_float": float(dur_qb),
            "mc": mc,
            "mn": mn,
            "mc_onset": fraction_to_struct(mc_onset),
            "mn_onset": fraction_to_struct(mc_onset),
            "timesig": None,
            "duration": None,
            "nominal_duration": None,
            "scalar": None,
            "midi_pitch": midi_pitch,
            "spelled_pitch": spelled_pitch,
            "tpc": tpc,
            "octave": octave,
            "velocity": 64,
            "tied": 0,
            "gracenote": None,
            "chord_id": chord_id,
            "voice": getattr(obj, "voice", None),
            "staff": getattr(obj, "staff", None),
            "part_id": part_id,
        }
