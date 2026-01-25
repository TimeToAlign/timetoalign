"""PartituraLoader: Load scores using partitura."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import partitura as pt
import partitura.score as pts

from timetoalign.core import NumberType, TimeUnit
from timetoalign.loader.schema import fraction_to_struct

from .base import ScoreLoader
from .bundle import ScoreBundle
from .stores import (
    AnnotationEventStore,
    ControlEventStore,
    MeasureEventStore,
    NoteEventStore,
)


class PartituraLoader(ScoreLoader):
    """Load symbolic scores using partitura.

    Supports MusicXML (fully typed) and MIDI (quantized).
    Returns ScoreBundle with category-specific stores.
    """

    def __init__(
        self,
        *,
        force_note_ids: bool = True,
    ) -> None:
        super().__init__()
        self._force_note_ids = force_note_ids

    def _load_source(self, source: Path) -> ScoreBundle:
        """Load score and return ScoreBundle."""
        score = pt.load_score(str(source), force_note_ids=self._force_note_ids)

        # Flatten parts
        parts = []
        if isinstance(score, pts.Score):
            parts = score.parts
        elif isinstance(score, (pts.Part, pts.PartGroup)):
            parts = [score] if isinstance(score, pts.Part) else score.children
        elif isinstance(score, list):
            parts = score

        note_rows = []
        measure_rows = []
        control_rows = []
        annotation_rows = []
        has_rests = False

        for part_idx, part in enumerate(parts):
            part_id = getattr(part, "id", f"P{part_idx+1}")

            # Build measure map for MC lookup
            measures = sorted(part.iter_all(pts.Measure), key=lambda m: m.start.t)
            measure_starts = [m.start.t for m in measures]

            def get_mc(t: int) -> int:
                import bisect

                idx = bisect.bisect_right(measure_starts, t) - 1
                return idx + 1 if idx >= 0 else 1

            # Get quarter beat mapping
            beat_map = part.beat_map  # divs -> quarter beats

            # Get divs_per_quarter for mc_onset calculation
            # divs_pq = (
            #     getattr(part, "_quarter_durations", [480])[0]
            #     if hasattr(part, "_quarter_durations")
            #     else 480
            # )

            # Process Measures
            for i, m in enumerate(measures):
                qb_start = Fraction(float(beat_map(m.start.t))).limit_denominator(10000)
                qb_end = Fraction(float(beat_map(m.end.t))).limit_denominator(10000)
                dur = qb_end - qb_start

                measure_rows.append(
                    {
                        "id": getattr(m, "id", None) or f"measure_{i+1}",
                        "name": str(m.number),
                        "temporal_type": "interval",
                        "event_type": "Measure",
                        "quarterbeats": fraction_to_struct(qb_start),
                        "quarterbeats_float": float(qb_start),
                        "duration_qb": fraction_to_struct(dur),
                        "duration_qb_float": float(dur),
                        "mc": i + 1,
                        "mn": str(m.number),
                        "timesig": None,  # Could extract from part
                        "part_id": part_id,
                    }
                )

            # Process Notes/Rests
            for obj in part.iter_all(include_subclasses=True):
                if isinstance(obj, (pts.Note, pts.Rest, pts.GraceNote)):
                    is_rest = isinstance(obj, pts.Rest)
                    if is_rest:
                        has_rests = True

                    # Temporal
                    start_div = obj.start.t
                    dur_div = obj.duration if hasattr(obj, "duration") else 0

                    qb_start = Fraction(float(beat_map(start_div))).limit_denominator(
                        10000
                    )
                    qb_end = Fraction(
                        float(beat_map(start_div + dur_div))
                    ).limit_denominator(10000)
                    dur_qb = qb_end - qb_start

                    # MC context
                    mc = get_mc(start_div)
                    mn = (
                        str(part.measure_number_map(start_div))
                        if hasattr(part, "measure_number_map")
                        else str(mc)
                    )

                    # mc_onset: offset from measure start
                    if mc > 0 and mc <= len(measure_starts):
                        m_start_div = measure_starts[mc - 1]
                        mc_onset = Fraction(
                            float(beat_map(start_div)) - float(beat_map(m_start_div))
                        ).limit_denominator(10000)
                    else:
                        mc_onset = Fraction(0)

                    # Pitch
                    midi_pitch = None
                    spelled_pitch = None
                    octave = None
                    tpc = None

                    if not is_rest and hasattr(obj, "midi_pitch"):
                        ep = obj.midi_pitch
                        midi_pitch = {"ep": int(ep), "epc": int(ep) % 12}

                        if hasattr(obj, "step"):
                            step = obj.step
                            alter = int(getattr(obj, "alter", 0) or 0)
                            octave = int(getattr(obj, "octave", 4) or 4)

                            gpc_map = {
                                "C": 0,
                                "D": 1,
                                "E": 2,
                                "F": 3,
                                "G": 4,
                                "A": 5,
                                "B": 6,
                            }
                            gpc_int = gpc_map.get(step, 0)

                            acc_str = ""
                            if alter > 0:
                                acc_str = "♯" * alter
                            elif alter < 0:
                                acc_str = "♭" * abs(alter)

                            base_fifths = {
                                "F": -1,
                                "C": 0,
                                "G": 1,
                                "D": 2,
                                "A": 3,
                                "E": 4,
                                "B": 5,
                            }
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

                    note_rows.append(
                        {
                            "id": getattr(obj, "id", None) or f"note_{float(qb_start)}",
                            "name": "",
                            "temporal_type": "interval" if dur_qb > 0 else "instant",
                            "event_type": "Rest" if is_rest else "Note",
                            "quarterbeats": fraction_to_struct(qb_start),
                            "quarterbeats_float": float(qb_start),
                            "duration_qb": fraction_to_struct(dur_qb),
                            "duration_qb_float": float(dur_qb),
                            "mc": mc,
                            "mn": mn,
                            "mc_onset": fraction_to_struct(mc_onset),
                            "mn_onset": fraction_to_struct(
                                mc_onset
                            ),  # Same as mc_onset for Partitura
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
                            "gracenote": (
                                "grace" if isinstance(obj, pts.GraceNote) else None
                            ),
                            "chord_id": None,
                            "voice": getattr(obj, "voice", None),
                            "staff": getattr(obj, "staff", None),
                            "part_id": part_id,
                        }
                    )

                elif isinstance(
                    obj,
                    (
                        pts.TimeSignature,
                        pts.KeySignature,
                        pts.Tempo,
                        pts.Direction,
                        pts.Slur,
                    ),
                ):
                    if isinstance(obj, pts.Words):
                        # Text annotation
                        qb = Fraction(float(beat_map(obj.start.t))).limit_denominator(
                            10000
                        )
                        annotation_rows.append(
                            {
                                "id": getattr(obj, "id", None),
                                "name": getattr(obj, "text", str(obj)),
                                "temporal_type": "instant",
                                "event_type": "Text",
                                "quarterbeats": fraction_to_struct(qb),
                                "quarterbeats_float": float(qb),
                                "duration_qb": None,
                                "duration_qb_float": 0.0,
                                "mc": get_mc(obj.start.t),
                                "mn": (
                                    str(part.measure_number_map(obj.start.t))
                                    if hasattr(part, "measure_number_map")
                                    else None
                                ),
                                "mc_onset": None,
                                "mn_onset": None,
                                "subtype": "Text",
                                "text": getattr(obj, "text", str(obj)),
                                "staff": getattr(obj, "staff", None),
                                "part_id": part_id,
                            }
                        )
                    else:
                        # Control event
                        qb = Fraction(float(beat_map(obj.start.t))).limit_denominator(
                            10000
                        )
                        control_rows.append(
                            {
                                "id": getattr(obj, "id", None) or f"ctrl_{float(qb)}",
                                "name": obj.__class__.__name__,
                                "temporal_type": (
                                    "interval"
                                    if getattr(obj, "end", None)
                                    else "instant"
                                ),
                                "event_type": obj.__class__.__name__,
                                "quarterbeats": fraction_to_struct(qb),
                                "quarterbeats_float": float(qb),
                                "duration_qb": None,
                                "duration_qb_float": 0.0,
                                "mc": get_mc(obj.start.t),
                                "mn": (
                                    str(part.measure_number_map(obj.start.t))
                                    if hasattr(part, "measure_number_map")
                                    else None
                                ),
                                "mc_onset": None,
                                "mn_onset": None,
                                "subtype": obj.__class__.__name__,
                                "value": None,
                                "text": str(obj),
                                "voice": getattr(obj, "voice", None),
                                "staff": getattr(obj, "staff", None),
                                "part_id": part_id,
                            }
                        )

        # Normalize negative start times
        if note_rows:
            min_qb = min(r["quarterbeats_float"] for r in note_rows)
            if min_qb < 0:
                offset = Fraction(-min_qb).limit_denominator(10000)
                for r in note_rows:
                    old_qb = Fraction(
                        r["quarterbeats"]["num"], r["quarterbeats"]["den"]
                    )
                    new_qb = old_qb + offset
                    r["quarterbeats"] = fraction_to_struct(new_qb)
                    r["quarterbeats_float"] = float(new_qb)

        # Build stores
        notes_store = NoteEventStore.from_dicts(
            note_rows,
            unit=TimeUnit.quarters,
            number_type=NumberType.fraction,
            has_rests=has_rests,
        )

        measures_store = (
            MeasureEventStore.from_dicts(
                measure_rows,
                unit=TimeUnit.quarters,
                number_type=NumberType.fraction,
            )
            if measure_rows
            else MeasureEventStore.empty()
        )

        controls_store = (
            ControlEventStore.from_dicts(
                control_rows,
                unit=TimeUnit.quarters,
                number_type=NumberType.fraction,
            )
            if control_rows
            else ControlEventStore.empty()
        )

        annotations_store = (
            AnnotationEventStore.from_dicts(
                annotation_rows,
                unit=TimeUnit.quarters,
                number_type=NumberType.fraction,
            )
            if annotation_rows
            else AnnotationEventStore.empty()
        )

        return ScoreBundle(
            notes=notes_store,
            measures=measures_store,
            controls=controls_store,
            annotations=annotations_store,
            metadata={
                "format": "score",
                "parser": "partitura",
                "source": str(source),
                "has_rests": has_rests,
            },
        )
