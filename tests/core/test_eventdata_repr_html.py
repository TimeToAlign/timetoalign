"""Exact-presence tests for EventData affordance ``_repr_html_`` cards.

See ``README.md`` for the documented expectations.
"""

from __future__ import annotations

from timetoalign.core import TimeUnit
from timetoalign.loader.midi.events import MidiEventData
from timetoalign.storage.events import EventData


class TestMidiEventDataReprHtml:
    """A loader-produced EventData lists its reachable semantic fields."""

    def _data(self) -> MidiEventData:
        return MidiEventData.from_dicts(
            [
                {
                    "id": "n1",
                    "temporal_type": "interval",
                    "event_type": "Note",
                    "start": 0.0,
                    "end": 1.0,
                    "pitch": 60,
                    "velocity": 80,
                }
            ],
            unit=TimeUnit.seconds,
        )

    def test_core_rows(self) -> None:
        html = self._data()._repr_html_()
        assert "<h4>MidiEventData</h4>" in html
        assert "<tr><td><b>Events</b></td><td>1</td></tr>" in html
        assert "<tr><td><b>Unit</b></td><td>seconds</td></tr>" in html
        assert "<tr><td><b>Number type</b></td><td>float</td></tr>" in html

    def test_fields_row_lists_pitch(self) -> None:
        html = self._data()._repr_html_()
        assert "<b>Fields</b>" in html
        assert "<li><code>pitch</code> : EnharmonicPitch</li>" in html

    def test_try_row(self) -> None:
        html = self._data()._repr_html_()
        assert "<code>get_field(&lt;Scalar&gt;)</code>" in html
        assert "<code>get_pitch_field()</code>" in html
        assert "<code>get_raw(&#x27;&lt;col&gt;&#x27;)</code>" in html


class TestPlainEventDataReprHtml:
    """Columns with no paired field are skipped gracefully (no raise)."""

    def test_no_metadata_fields_none(self) -> None:
        data = EventData.from_dicts(
            [
                {
                    "id": "e1",
                    "temporal_type": "interval",
                    "event_type": "Note",
                    "start": 0.0,
                    "end": 1.0,
                }
            ],
            unit=TimeUnit.seconds,
        )
        html = data._repr_html_()  # must not raise
        assert "<h4>EventData</h4>" in html
        assert "<tr><td><b>Fields</b></td><td>(none)</td></tr>" in html
