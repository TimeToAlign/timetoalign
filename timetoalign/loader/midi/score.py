"""ScoreMidiLoader: Load score MIDI using partitura."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

# Suppress pkg_resources deprecation warning from partitura
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=UserWarning, module="partitura.*")
    warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")
    import partitura as pt
    from partitura.score import Part, PartGroup, Score

from timetoalign.core import NumberType, TimeUnit

from .base import MidiLoader
from .constants import MidiEventType


class ScoreMidiLoader(MidiLoader):
    """Load score MIDI files using partitura.

    This loader uses partitura's sophisticated MIDI parsing to extract structural
    information like voices, parts, and spelled pitches (optional). It is ideal
    for quantized MIDI files representing scores.
    """

    def __init__(
        self,
        *,
        part_voice_assign_mode: int = 0,
        quantization_unit: int | None = None,
        estimate_voice_info: bool = False,
        estimate_key: bool = False,
        assign_note_ids: bool = True,
        unit: TimeUnit | None = None,
        number_type: NumberType = NumberType.float,
        **kwargs: Any,
    ) -> None:
        """Initialize ScoreMidiLoader.

        Args:
            part_voice_assign_mode: Partitura mode for assigning parts/voices (0-5).
            quantization_unit: Quantize times to multiples of this unit.
            estimate_voice_info: Use Chew & Wu algorithm for voice separation.
            estimate_key: Use Krumhansl algorithm for key estimation.
            assign_note_ids: Ensure unique note IDs.
            unit: Time unit for coordinates.
            number_type: Number type for coordinates.
            **kwargs: Additional arguments passed to parent Loader.
        """
        super().__init__(unit=unit, number_type=number_type, **kwargs)
        self._part_voice_assign_mode = part_voice_assign_mode
        self._quantization_unit = quantization_unit
        self._estimate_voice_info = estimate_voice_info
        self._estimate_key = estimate_key
        self._assign_note_ids = assign_note_ids
        self._ticks_per_beat: int | None = None

    @property
    def ticks_per_beat(self) -> int | None:
        """Return the ticks per beat (PPQ) of the loaded file."""
        return self._ticks_per_beat

    def _load_source(self, source: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Load a MIDI file using partitura.

        Args:
            source: Path to the MIDI file.

        Returns:
            Tuple of (metadata, event_rows).
        """
        # Load score using partitura
        # Note: partitura can return Score, Part, PartGroup, or list
        score_data = pt.load_score_midi(
            source,
            part_voice_assign_mode=self._part_voice_assign_mode,
            quantization_unit=self._quantization_unit,
            estimate_voice_info=self._estimate_voice_info,
            estimate_key=self._estimate_key,
            assign_note_ids=self._assign_note_ids,
        )

        # Normalize to a list of parts
        parts: list[Part] = []
        if isinstance(score_data, Score):
            parts = score_data.parts
        elif isinstance(score_data, (Part, PartGroup)):
            # PartGroup handling is recursive in partitura, but we need flat list for note_array
            # Helper to flatten
            def flatten_parts(obj):
                if isinstance(obj, Part):
                    return [obj]
                elif isinstance(obj, PartGroup):
                    flat = []
                    for child in obj.children:
                        flat.extend(flatten_parts(child))
                    return flat
                return []

            parts = flatten_parts(score_data)
        elif isinstance(score_data, list):
            # List of Part/PartGroup
            parts = []
            for item in score_data:
                if isinstance(item, Part):
                    parts.append(item)
                # ... theoretically could be PartGroup in list, but load_score_midi usually returns Score or parts

        if not parts:
            # Empty score
            return {"format": "midi", "parser": "partitura", "parts": 0}, []

        # Get PPQ from the first part (partitura stores this in quarter_map logic usually,
        # but for MIDI loading, it's often implicit or stored in the score object if available)
        # We'll try to get it from the first part's quarter_map if simple
        # NOTE: Partitura's MIDI loader doesn't always expose original PPQ directly on Part.
        # But for now we can leave it None or check if we can extract it.
        # Since we are using note_array, we will rely on its units.

        # Generate note array with all info
        # We use include_staff=True if available in partitura version
        note_array = pt.utils.music.note_array_from_part_list(
            parts,
            include_staff=True,
            include_divs_per_quarter=True,  # To get PPQ info
        )

        # Extract events
        events = []

        # Iterate over structured array
        for row in note_array:
            # row fields: onset_div, duration_div, pitch, voice, id, staff, divs_pq, ...

            # Update PPQ if we found it
            if "divs_pq" in row.dtype.names and self._ticks_per_beat is None:
                self._ticks_per_beat = int(row["divs_pq"])

            event = {
                "id": str(row["id"]),
                "temporal_type": "interval",
                "event_type": MidiEventType.NOTE,
                "start": int(row["onset_div"]),
                "end": int(row["onset_div"] + row["duration_div"]),
                "duration": int(row["duration_div"]),
                "pitch": int(row["pitch"]),
                "velocity": 64,  # Default for score
                "voice": int(row["voice"]) if "voice" in row.dtype.names else None,
                "staff": int(row["staff"]) if "staff" in row.dtype.names else None,
                # Part ID is tricky in unified array, but partitura usually encodes it in ID
                # or we can't easily get it per row without complex mapping.
                # For now, we'll leave part_id null or extract from ID if encoded.
                "part_id": None,
                # Nullable mido fields
                "channel": None,
                "track": None,
                "control": None,
                "value": None,
                "program": None,
            }
            events.append(event)

        metadata = {
            "format": "midi",
            "parser": "partitura",
            "part_voice_assign_mode": self._part_voice_assign_mode,
            "parts": len(parts),
            "ticks_per_beat": self._ticks_per_beat,
        }

        return metadata, events
