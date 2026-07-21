"""Store support for RepoVizz catalogue data."""

from __future__ import annotations

from timetoalign.storage.events import EventData
from timetoalign.storage.store import DictStore

from .repovizz_catalogue import CatalogueEntry


class RepovizzDictStore(DictStore):
    """``DictStore`` subclass with category properties for RepoVizz data.

    Each property returns a list of catalogue entry IDs for that category,
    enabling lazy loading of specific data types. The actual timeline data
    is loaded on demand via ``loader.create_timeline(entry)``.

    Categories correspond to the top-level XML groups:
    - ``.audio`` — Audio file entries (ambient + pickup recordings)
    - ``.score`` — Score annotation entries (.notes files)
    - ``.descriptors`` — Bowing gesture descriptor entries (CSV)
    - ``.mocap`` — MoCap marker entries (X/Y/Z grouped)
    - ``.notes`` — Note events from .notes files (per-instrument)

    Unlike TiliaDictStore which concatenates EventData tables, this store
    returns ID lists because the data is heterogeneous (different sample
    rates, different file formats).

    See Also:
        timetoalign.storage.store.DictStore
        timetoalign.loader.alignment.tilia.TiliaDictStore
    """

    def __init__(
        self,
        data: dict[str, EventData] | None = None,
        catalogue: dict[str, CatalogueEntry] | None = None,
    ) -> None:
        """Initialize RepovizzDictStore.

        Args:
            data: Dictionary mapping IDs to EventData tables (lazy-loaded).
            catalogue: Dictionary mapping IDs to CatalogueEntry metadata.
        """
        super().__init__(data)
        self._catalogue: dict[str, CatalogueEntry] = catalogue or {}
        self._notes: EventData | None = None
        self._notes_by_instrument: dict[str, EventData] = {}

    def set_catalogue(self, catalogue: dict[str, CatalogueEntry]) -> None:
        """Set the catalogue after parsing.

        Args:
            catalogue: Dict mapping xml_id to CatalogueEntry.
        """
        self._catalogue = catalogue

    @property
    def catalogue(self) -> dict[str, CatalogueEntry]:
        """The full catalogue of entries."""
        return self._catalogue

    def _ids_by_group(self, group: str) -> list[str]:
        """Return IDs for entries in a specific group."""
        return [e.xml_id for e in self._catalogue.values() if e.group == group]

    @property
    def audio(self) -> list[str]:
        """IDs of Audio timeline entries."""
        return self._ids_by_group("audio")

    @property
    def score(self) -> list[str]:
        """IDs of Score annotation entries."""
        return self._ids_by_group("score")

    @property
    def descriptors(self) -> list[str]:
        """IDs of bowing gesture descriptor entries."""
        return self._ids_by_group("descriptors")

    @property
    def mocap(self) -> list[str]:
        """IDs of MoCap marker entries."""
        return self._ids_by_group("mocap")

    @property
    def groups(self) -> list[str]:
        """List of all group names present in the catalogue."""
        return sorted(set(e.group for e in self._catalogue.values()))

    @property
    def notes(self) -> EventData | None:
        """Combined note events from all .notes files."""
        return self._notes

    def notes_for_instrument(self, instrument: str) -> EventData | None:
        """Get note events for a specific instrument.

        Args:
            instrument: Instrument name (vln1, vln2, vla, cello).

        Returns:
            EventData for the instrument, or None if not found.
        """
        return self._notes_by_instrument.get(instrument)

    def set_notes(
        self,
        notes: EventData,
        notes_by_instrument: dict[str, EventData],
    ) -> None:
        """Set the notes data after loading.

        Args:
            notes: Combined EventData from all .notes files.
            notes_by_instrument: Dict mapping instrument to EventData.
        """
        self._notes = notes
        self._notes_by_instrument = notes_by_instrument

    def __repr__(self) -> str:
        """Return string representation."""
        group_counts: dict[str, int] = {}
        for e in self._catalogue.values():
            group_counts[e.group] = group_counts.get(e.group, 0) + 1
        parts = ", ".join(f"{k}={v}" for k, v in sorted(group_counts.items()))
        return f"RepovizzDictStore({parts or 'empty'})"
