"""PerformanceMidiLoader: Load performance MIDI using mido."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import mido
import numpy as np
import pyarrow as pa

from timetoalign.core import NumberType, TimeUnit

from .base import MidiLoader
from .constants import MidiEventType


class PerformanceMidiLoader(MidiLoader):
    """Load performance MIDI files using mido.

    This loader parses raw MIDI messages, preserving the performance characteristics
    (timing, velocity, control changes) without attempting structural analysis.

    It pairs note_on/note_off events into Note intervals and stores control
    changes as Instant events.
    """

    _validate_vectorized = False

    @classmethod
    def from_file(
        cls,
        path: Path | str,
        *,
        parse_durations: bool = True,
        on0_means_off: bool = True,
        include_controls: bool = True,
        include_program_changes: bool = True,
    ) -> "PerformanceMidiLoader":
        """Create a loader and load a MIDI file in one step.

        Convenience constructor for loading a single file.

        Args:
            path: Path to the MIDI file.
            parse_durations: Whether to pair note_on/off into intervals.
            on0_means_off: Treat note_on with velocity 0 as note_off.
            include_controls: Include Control Change events.
            include_program_changes: Include Program Change events.

        Returns:
            A new PerformanceMidiLoader instance with the file already loaded.

        Examples:
            >>> loader = PerformanceMidiLoader.from_file("performance.mid")
            >>> loader.ticks_per_beat
            480
        """
        loader = cls(
            parse_durations=parse_durations,
            on0_means_off=on0_means_off,
            include_controls=include_controls,
            include_program_changes=include_program_changes,
        )
        loader.load(path)
        return loader

    def __init__(
        self,
        *,
        parse_durations: bool = True,
        on0_means_off: bool = True,
        include_controls: bool = True,
        include_program_changes: bool = True,
        unit: TimeUnit | None = None,
        number_type: NumberType = NumberType.float,
        **kwargs: Any,
    ) -> None:
        """Initialize PerformanceMidiLoader.

        Args:
            parse_durations: Whether to pair note_on/off into intervals.
            on0_means_off: Treat note_on with velocity 0 as note_off.
            include_controls: Include Control Change events.
            include_program_changes: Include Program Change events.
            unit: Time unit for coordinates.
            number_type: Number type for coordinates.
            **kwargs: Additional arguments passed to parent Loader.
        """
        super().__init__(unit=unit, number_type=number_type, **kwargs)
        self._parse_durations = parse_durations
        self._on0_means_off = on0_means_off
        self._include_controls = include_controls
        self._include_program_changes = include_program_changes
        self._ticks_per_beat: int | None = None

    @property
    def ticks_per_beat(self) -> int | None:
        """Return the ticks per beat (PPQ) of the loaded file."""
        return self._ticks_per_beat

    def _load_source(
        self, source: Path
    ) -> tuple[dict[str, Any], dict[str, pa.ChunkedArray]]:
        """Load a MIDI file using mido.

        Args:
            source: Path to the MIDI file.

        Returns:
            Tuple of metadata and vectorized event field arrays.
        """
        try:
            mid = mido.MidiFile(source)
        except (OSError, EOFError, ValueError) as e:
            # mido raises diverse exceptions for invalid files
            raise ValueError(f"Invalid MIDI file {source}: {e}") from e

        self._ticks_per_beat = mid.ticks_per_beat

        events = []

        for i, track in enumerate(mid.tracks):
            absolute_time = 0
            # active_notes: (channel, pitch) -> event_dict
            active_notes: dict[tuple[int, int], dict[str, Any]] = {}

            for msg in track:
                absolute_time += msg.time

                # Handle Note Events
                if msg.type == "note_on" or msg.type == "note_off":
                    channel = msg.channel
                    note = msg.note
                    velocity = msg.velocity

                    is_note_on = msg.type == "note_on" and velocity > 0
                    is_note_off = msg.type == "note_off" or (
                        self._on0_means_off and msg.type == "note_on" and velocity == 0
                    )

                    if is_note_on:
                        # Start of a note
                        note_event = {
                            "id": f"n{i}_{absolute_time}_{note}_{channel}",
                            "temporal_type": "interval",
                            "event_type": MidiEventType.NOTE,
                            "start": absolute_time,
                            "end": None,  # Will be filled by note_off
                            "duration": None,
                            "pitch": note,
                            "velocity": velocity,
                            "channel": channel,
                            "track": i,
                            "control": None,
                            "value": None,
                            "program": None,
                        }
                        if self._parse_durations:
                            active_notes[(channel, note)] = note_event
                        else:
                            # If not parsing durations, store as instant event (unusual but supported)
                            note_event["temporal_type"] = "instant"
                            note_event["instant"] = absolute_time
                            events.append(note_event)

                    elif is_note_off:
                        if self._parse_durations:
                            if (channel, note) in active_notes:
                                note_event = active_notes.pop((channel, note))
                                note_event["end"] = absolute_time
                                note_event["duration"] = (
                                    absolute_time - note_event["start"]
                                )
                                events.append(note_event)
                            else:
                                # Orphaned note_off - ignore or warn?
                                # For now, ignore to match legacy behavior
                                pass

                # Handle Control Changes
                elif msg.type == "control_change" and self._include_controls:
                    cc_event = {
                        "id": f"cc{i}_{absolute_time}_{msg.control}",
                        "temporal_type": "instant",
                        "event_type": MidiEventType.CONTROL_CHANGE,
                        "instant": absolute_time,
                        "control": msg.control,
                        "value": msg.value,
                        "channel": msg.channel,
                        "track": i,
                        # Other fields null
                        "pitch": None,
                        "velocity": None,
                        "program": None,
                    }
                    events.append(cc_event)

                # Handle Program Changes
                elif msg.type == "program_change" and self._include_program_changes:
                    pc_event = {
                        "id": f"pc{i}_{absolute_time}",
                        "temporal_type": "instant",
                        "event_type": MidiEventType.PROGRAM_CHANGE,
                        "instant": absolute_time,
                        "program": msg.program,
                        "channel": msg.channel,
                        "track": i,
                        # Other fields null
                        "pitch": None,
                        "velocity": None,
                        "control": None,
                        "value": None,
                    }
                    events.append(pc_event)

            # Check for unclosed notes at end of track
            if self._parse_durations and active_notes:
                warnings.warn(
                    f"{len(active_notes)} events on track {i} in {source.name} "
                    f"have not been ended by note_off. Duration set to 0."
                )
                for note_event in active_notes.values():
                    note_event["end"] = absolute_time
                    note_event["duration"] = absolute_time - note_event["start"]
                    events.append(note_event)

        metadata = {
            "format": "midi",
            "parser": "mido",
            "type": mid.type,
            "ticks_per_beat": mid.ticks_per_beat,
            "num_tracks": len(mid.tracks),
            "length_seconds": mid.length,
        }

        if not events:
            return metadata, {}
        table = pa.Table.from_pylist(events)
        fields = {name: table.column(name) for name in table.column_names}
        if "instant" in fields:
            starts = fields.get("start")
            start_values = (
                starts.to_pylist() if starts is not None else [None] * len(events)
            )
            instant_values = fields["instant"].to_pylist()
            fields["start"] = np.asarray(
                [
                    start if start is not None else instant
                    for start, instant in zip(start_values, instant_values)
                ],
                dtype=np.float64,
            )
            del fields["instant"]
        for name in ("start", "end", "duration"):
            if name in fields:
                values = (
                    fields[name].to_pylist()
                    if isinstance(fields[name], (pa.Array, pa.ChunkedArray))
                    else fields[name].tolist()
                )
                dtype = object if any(value is None for value in values) else None
                fields[name] = np.asarray(values, dtype=dtype)
        return metadata, fields
