"""RepoVizzLoader: ManifestLoader for RepoVizz XML manifests and CSV sensor data.

This module provides a manifest-style loader for RepoVizz data from the EEP
(Expressive Ensemble Performance) dataset. It supports two modes:

1. **XML manifest mode** (primary): Reads a RepoVizz XML manifest file that
   catalogues all data in a recording directory — audio, Essentia descriptors,
   bowing gesture descriptors, MoCap markers, and score alignment files.

2. **Legacy CSV mode** (backwards compatible): Reads a single 2-line CSV file
   for a single sensor signal.

XML Manifest Structure:
    ROOT
    ├── METADATA (title, README, keywords, etc.)
    ├── AudioGroup (ambient + pickup audio with Essentia descriptors)
    ├── Score (4 Annotation elements for .notes files)
    ├── DescriptorGroup (bowing gesture descriptors per instrument)
    └── MoCapGroup (48 MoCap markers × 3 axes each)

CSV File Format (legacy):
    Line 1: Comma-separated key=value metadata pairs.
        Example: ``repoVizz,category=...,name=...,framerate=240,...``
    Line 2: Comma-separated float values (one per sample).
        Example: ``166.568,166.670,166.776,...``

The loader creates :class:`DiscretePhysicalTimeline` instances with the
``samples`` unit and an attached ``SamplesToSeconds`` conversion map.

Reference:
    - ``dashboard/specimens/beethoven_op18-4iv_multimodal/StringQuartetEEP_*/``
    - ``dashboard/processing/notebooks/repovizz_parsing.py``
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from typing_extensions import Self

from timetoalign.core import NumberType, TimeUnit, resolve_id
from timetoalign.loader.base import ManifestData, ManifestLoader
from timetoalign.loader.events import EventData
from timetoalign.loader.store import DictStore

if TYPE_CHECKING:
    from timetoalign.alignment.groups import TimelineGroup
    from timetoalign.timelines import DiscretePhysicalTimeline
    from timetoalign.timelines.base import Timeline


module_logger = logging.getLogger(__name__)


# region CatalogueEntry


@dataclass(frozen=True)
class CatalogueEntry:
    """Metadata for a loadable signal/audio/annotation from an XML manifest.

    This dataclass represents a single loadable item from a RepoVizz
    (or similar) XML manifest. It captures enough metadata to:
    1. Identify the item (xml_id, name)
    2. Categorize it (group, subgroup, file_type)
    3. Load the data (filename, sample_rate, n_samples)
    4. Handle special cases (related_ids for MoCap X/Y/Z grouping)

    The class is frozen (immutable) to enable use as dict keys and to
    ensure catalogue entries don't change after parsing.

    Attributes:
        xml_id: Unique identifier from the XML (ID attribute).
        name: Human-readable name from the XML (Name or name attribute).
        category: Category from the XML (e.g., "Ambient", "Pickup", "AuDesc").
        group: Top-level group: "audio", "score", "descriptors", "mocap".
        subgroup: Second-level grouping (e.g., "ambient", "vln1", "MoCap").
        filename: Data file referenced (None for container elements).
        file_type: File format: "BWF", "CSV", "NOTES", "txt", "wav", etc.
        sample_rate: Sampling rate in Hz (0.0 for non-signal entries).
        n_samples: Number of samples from XML (0 for non-signal entries).
        frame_size: For multi-dimensional signals (1 for scalar).
        metadata: Additional attributes from the XML element.
        related_ids: For MoCapMarker: tuple of (x_id, y_id, z_id) signal IDs.
    """

    xml_id: str
    name: str
    category: str
    group: str
    subgroup: str
    filename: str | None
    file_type: str
    sample_rate: float
    n_samples: int
    frame_size: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
    related_ids: tuple[str, ...] = ()

    @property
    def is_signal(self) -> bool:
        """True if this entry represents a loadable signal (has samples)."""
        return self.n_samples > 0 and self.sample_rate > 0

    @property
    def duration_seconds(self) -> float:
        """Duration in seconds (0 if not a signal)."""
        if not self.is_signal:
            return 0.0
        return self.n_samples / self.sample_rate


# endregion


# region RepovizzDictStore


class RepovizzDictStore(DictStore):
    """``DictStore`` subclass with category properties for RepoVizz data.

    Each property returns a list of catalogue entry IDs for that category,
    enabling lazy loading of specific data types. The actual timeline data
    is loaded on demand via ``loader.create_timeline(id)``.

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
        timetoalign.loader.store.DictStore
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


# endregion


# region RepoVizzInfo (legacy CSV support)


class RepoVizzInfo:
    """Parsed metadata from a RepoVizz CSV file (legacy mode).

    Attributes:
        n_samples: Number of data values on line 2.
        frame_rate: Sampling rate in Hz (from ``framerate`` in the header).
        duration_seconds: Computed as ``n_samples / frame_rate``.
        metadata: Full key=value dict from the header line.
        source_path: Path to the source file.
    """

    def __init__(
        self,
        n_samples: int,
        frame_rate: int,
        metadata: dict[str, str],
        source_path: Path | None = None,
    ) -> None:
        self.n_samples = n_samples
        self.frame_rate = frame_rate
        self.metadata = metadata
        self.source_path = source_path

    @property
    def duration_seconds(self) -> float:
        """Duration in seconds."""
        return self.n_samples / self.frame_rate if self.frame_rate > 0 else 0.0

    def __repr__(self) -> str:
        return (
            f"RepoVizzInfo(n_samples={self.n_samples}, "
            f"frame_rate={self.frame_rate}, "
            f"duration={self.duration_seconds:.2f}s)"
        )


# endregion


# region RepoVizzLoader


class RepoVizzLoader(ManifestLoader):
    """Load RepoVizz XML manifests or single CSV files for creating physical timelines.

    RepoVizzLoader supports two modes:

    **XML Manifest Mode** (when loading a ``.xml`` file):
        Parses the RepoVizz XML manifest and builds a catalogue of all data
        files in the recording directory. Provides lazy access to:
        - Audio recordings (ambient + pickup)
        - Essentia audio descriptors
        - Bowing gesture descriptors
        - MoCap position data
        - Score alignment files (.notes)

    **Legacy CSV Mode** (when loading a ``.csv`` file):
        Reads the 2-line RepoVizz CSV format for a single sensor signal.
        This preserves backwards compatibility with existing code.

    Both modes create :class:`DiscretePhysicalTimeline` instances with the
    ``samples`` unit and an attached ``SamplesToSeconds`` conversion map.

    Examples:
        XML manifest mode::

            >>> loader = RepoVizzLoader.from_file("StringQuartetEEP_I_Normal.xml")
            >>> loader.groups
            ['audio', 'descriptors', 'mocap', 'score']
            >>> loader.timeline_ids[:5]
            ['ROOT0_Audi1_Audi0_Ambi0', 'ROOT0_Audi1_Audi0_Ambi1', ...]

            >>> tl = loader.create_timeline("ROOT0_Audi1_Audi0_Ambi0")
            >>> tl.length
            Coordinate(11753638, samples)

        Legacy CSV mode::

            >>> loader = RepoVizzLoader.from_file("vln1_bb_angle.csv")
            >>> loader.n_samples
            63965
            >>> loader.frame_rate
            240

    See Also:
        timetoalign.loader.base.ManifestLoader
        timetoalign.loader.physical.audio.AudioLoader
        timetoalign.loader.physical.eep_notes.EepNotesLoader
    """

    def __init__(self) -> None:
        """Initialize the loader."""
        super().__init__()
        # XML mode state
        self._store: RepovizzDictStore = RepovizzDictStore()
        self._timeline_specs: list[dict[str, Any]] = []
        self._timeline_cache: dict[str, "DiscretePhysicalTimeline"] = {}
        self._xml_metadata: dict[str, Any] = {}
        self._xml_root_path: Path | None = None
        self._is_xml_mode: bool = False

        # Legacy CSV mode state
        self._info: RepoVizzInfo | None = None
        self._logger = module_logger.getChild(self.__class__.__name__)

    # region Loading

    def load(self, *sources: Path | str) -> Self:
        """Load one or more source files.

        If the source is an ``.xml`` file, uses XML manifest mode.
        Otherwise, falls back to legacy CSV mode.

        Args:
            *sources: Paths to XML manifest or CSV files.

        Returns:
            Self, for method chaining.

        Raises:
            FileNotFoundError: If any source doesn't exist.
            ValueError: If any source is invalid.
        """
        for source in sources:
            path = Path(source)

            if path.suffix.lower() == ".xml":
                self._load_xml(path)
            else:
                # Legacy CSV mode
                manifest = self._load_source(path)
                manifest.source_path = path
                self._sources.append(path)
                self._manifests.append(manifest)

        return self

    def _load_source(self, source: Path) -> ManifestData:
        """Parse a RepoVizz CSV file (legacy mode).

        Reads only the first two lines:
        - Line 1: metadata key=value pairs (extracts ``framerate``)
        - Line 2: counts comma-separated values to determine ``n_samples``

        Args:
            source: Path to the RepoVizz CSV file.

        Returns:
            ManifestData with dimensions and metadata.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the file format is invalid or ``framerate`` is missing.
        """
        if not source.exists():
            raise FileNotFoundError(f"RepoVizz CSV file not found: {source}")

        with open(source, "r", encoding="utf-8") as f:
            metadata_line = f.readline().strip()
            data_line = f.readline().strip()

        if not metadata_line:
            raise ValueError(f"Empty metadata line in {source}")
        if not data_line:
            raise ValueError(f"Empty data line in {source}")

        # Parse metadata: comma-separated key=value pairs
        metadata: dict[str, str] = {}
        for item in metadata_line.split(","):
            parts = item.split("=", 1)
            if len(parts) == 2:
                metadata[parts[0].strip()] = parts[1].strip()

        # Extract frame rate
        frame_rate_str = metadata.get("framerate")
        if frame_rate_str is None:
            raise ValueError(
                f"No 'framerate' found in metadata header of {source}. "
                f"Available keys: {list(metadata.keys())}"
            )
        frame_rate = int(frame_rate_str)

        # Count samples (non-empty comma-separated values on line 2)
        n_samples = sum(1 for v in data_line.split(",") if v.strip())

        # Store parsed info
        self._info = RepoVizzInfo(
            n_samples=n_samples,
            frame_rate=frame_rate,
            metadata=metadata,
            source_path=source,
        )
        self._is_xml_mode = False

        return ManifestData(
            dimensions={
                "n_samples": n_samples,
                "duration_seconds": self._info.duration_seconds,
            },
            metadata={
                "frame_rate": frame_rate,
                "source_format": "repovizz_csv",
                **metadata,
            },
            source_type="sensor",
        )

    def _load_xml(self, source: Path) -> None:
        """Parse a RepoVizz XML manifest file.

        Builds the catalogue by walking the XML element tree and extracting
        metadata for each Audio, Signal, Annotation, and File element.

        Args:
            source: Path to the XML manifest file.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            ET.ParseError: If the XML is malformed.
        """
        if not source.exists():
            raise FileNotFoundError(f"RepoVizz XML manifest not found: {source}")

        tree = ET.parse(source)
        root = tree.getroot()

        self._sources.append(source)
        self._xml_root_path = source.parent
        self._is_xml_mode = True

        # Build catalogue from XML
        catalogue: dict[str, CatalogueEntry] = {}
        specs: list[dict[str, Any]] = []

        self._walk_xml(root, catalogue, specs, group="", subgroup="")

        self._store.set_catalogue(catalogue)
        self._timeline_specs = specs

        # Extract top-level metadata
        self._xml_metadata = {
            "root_id": root.get("ID", ""),
            "source_path": str(source),
        }

        # Find METADATA section for title
        for elem in root.iter():
            if elem.get("Category") == "METADATA":
                for child in elem:
                    if child.get("Category") == "TITLE":
                        self._xml_metadata["title"] = child.get("Text", "")
                        break
                break

        # Load notes from score entries
        self._load_notes(catalogue)

        self._logger.debug(
            "Loaded XML manifest with %d catalogue entries",
            len(catalogue),
        )

    def _load_notes(self, catalogue: dict[str, CatalogueEntry]) -> None:
        """Load notes from .notes files referenced in the catalogue.

        Loads each .notes file via EepNotesLoader and stores them in the
        store, accessible via ``store.notes`` (combined) or
        ``store.notes_for_instrument(instrument)``.

        Args:
            catalogue: The parsed catalogue with score entries.
        """
        from timetoalign.loader.physical.eep_notes import EepNotesLoader

        if self._xml_root_path is None:
            return

        # Get score entry IDs and load each .notes file
        score_ids = [e.xml_id for e in catalogue.values() if e.group == "score"]
        if not score_ids:
            return

        notes_files: list[Path] = []
        for entry_id in score_ids:
            entry = catalogue[entry_id]
            if entry.filename:
                notes_path = self._xml_root_path / entry.filename
                if notes_path.exists():
                    notes_files.append(notes_path)

        if not notes_files:
            return

        # Load all notes via EepNotesLoader
        loader = EepNotesLoader()
        loader.load(*sorted(notes_files))

        # Store combined notes
        combined_notes = loader.events

        # Group by instrument (staff column maps to instrument)
        # staff 1=vln1, 2=vln2, 3=vla, 4=cello
        staff_to_instrument = {1: "vln1", 2: "vln2", 3: "vla", 4: "cello"}
        notes_by_instrument: dict[str, EventData] = {}

        df = combined_notes.to_pandas()
        for staff_num, instrument in staff_to_instrument.items():
            mask = df["staff"] == staff_num
            instrument_df = df.loc[mask].copy()  # type: ignore[arg-type]
            if len(instrument_df) > 0:
                notes_by_instrument[instrument] = EventData.from_dataframe(
                    instrument_df, unit=TimeUnit.seconds  # type: ignore[arg-type]
                )

        self._store.set_notes(combined_notes, notes_by_instrument)

    def _walk_xml(
        self,
        elem: ET.Element,
        catalogue: dict[str, CatalogueEntry],
        specs: list[dict[str, Any]],
        group: str,
        subgroup: str,
    ) -> None:
        """Recursively walk XML and build catalogue entries.

        Args:
            elem: Current XML element.
            catalogue: Dict to populate with CatalogueEntry objects.
            specs: List to populate with timeline spec dicts.
            group: Current top-level group name.
            subgroup: Current second-level group name.
        """
        tag = elem.tag
        category = elem.get("Category", elem.get("category", ""))
        xml_id = elem.get("ID", elem.get("id", ""))
        name = elem.get("Name", elem.get("name", ""))

        # Determine current group/subgroup
        current_group = group
        current_subgroup = subgroup

        if tag == "Generic":
            # Update group/subgroup based on category
            if category in ("AudioGroup", "METADATA"):
                current_group = "audio" if category == "AudioGroup" else "metadata"
            elif category == "Score":
                current_group = "score"
            elif category == "DescriptorGroup":
                current_group = "descriptors"
            elif category == "MoCapGroup":
                current_group = "mocap"
            elif category == "MoCapMarker":
                current_subgroup = name or xml_id
                # MoCap markers are special — collect X/Y/Z signal children
                xyz_ids = self._collect_mocap_xyz(elem)
                if xyz_ids:
                    entry = CatalogueEntry(
                        xml_id=xml_id,
                        name=name,
                        category=category,
                        group="mocap",
                        subgroup=current_subgroup,
                        filename=None,
                        file_type="MoCapMarker",
                        sample_rate=240.0,  # Standard MoCap rate
                        n_samples=0,  # Will be determined from CSV
                        related_ids=tuple(xyz_ids),
                    )
                    catalogue[xml_id] = entry
                    specs.append(
                        {
                            "id": xml_id,
                            "name": name,
                            "group": "mocap",
                            "entry": entry,
                        }
                    )
            else:
                # Other Generic categories become subgroups
                if name:
                    current_subgroup = name.split()[0].lower()  # e.g., "vln1"

        elif tag == "Audio":
            entry = self._parse_audio_entry(elem, current_group, current_subgroup)
            catalogue[entry.xml_id] = entry
            specs.append(
                {
                    "id": entry.xml_id,
                    "name": entry.name,
                    "group": "audio",
                    "entry": entry,
                }
            )

        elif tag == "Signal":
            entry = self._parse_signal_entry(elem, current_group, current_subgroup)
            catalogue[entry.xml_id] = entry
            # Only add to specs if it's a top-level signal (not MoCap X/Y/Z)
            if current_group != "mocap" or category not in ("X", "Y", "Z"):
                specs.append(
                    {
                        "id": entry.xml_id,
                        "name": entry.name,
                        "group": entry.group,
                        "entry": entry,
                    }
                )

        elif tag == "Annotation":
            entry = self._parse_annotation_entry(elem, current_subgroup)
            catalogue[entry.xml_id] = entry
            specs.append(
                {
                    "id": entry.xml_id,
                    "name": entry.name,
                    "group": "score",
                    "entry": entry,
                }
            )

        # Recurse into children
        for child in elem:
            self._walk_xml(child, catalogue, specs, current_group, current_subgroup)

    def _collect_mocap_xyz(self, marker_elem: ET.Element) -> list[str]:
        """Collect X, Y, Z signal IDs from a MoCapMarker element.

        Args:
            marker_elem: The Generic element with Category="MoCapMarker".

        Returns:
            List of signal IDs [x_id, y_id, z_id], or empty if not found.
        """
        xyz_ids: dict[str, str] = {}
        for child in marker_elem:
            if child.tag == "Signal":
                cat = child.get("Category", child.get("category", ""))
                xml_id = child.get("ID", child.get("id", ""))
                if cat in ("X", "Y", "Z") and xml_id:
                    xyz_ids[cat] = xml_id

        if "X" in xyz_ids and "Y" in xyz_ids and "Z" in xyz_ids:
            return [xyz_ids["X"], xyz_ids["Y"], xyz_ids["Z"]]
        return []

    def _parse_audio_entry(
        self,
        elem: ET.Element,
        group: str,
        subgroup: str,
    ) -> CatalogueEntry:
        """Parse an Audio element into a CatalogueEntry."""
        xml_id = elem.get("ID", elem.get("id", ""))
        name = elem.get("Name", elem.get("name", ""))
        filename = elem.get("Filename", elem.get("filename"))
        category = elem.get("Category", elem.get("category", ""))
        sample_rate = float(elem.get("SampleRate", elem.get("samplerate", "0")))
        n_samples = int(elem.get("NumSamples", elem.get("numsamples", "0")))
        file_type = elem.get("FileType", elem.get("filetype", "BWF"))

        return CatalogueEntry(
            xml_id=xml_id,
            name=name,
            category=category,
            group="audio",
            subgroup=subgroup or category.lower(),
            filename=filename,
            file_type=file_type,
            sample_rate=sample_rate,
            n_samples=n_samples,
        )

    def _parse_signal_entry(
        self,
        elem: ET.Element,
        group: str,
        subgroup: str,
    ) -> CatalogueEntry:
        """Parse a Signal element into a CatalogueEntry."""
        xml_id = elem.get("ID", elem.get("id", ""))
        name = elem.get("Name", elem.get("name", ""))
        filename = elem.get("Filename", elem.get("filename"))
        category = elem.get("Category", elem.get("category", ""))
        sample_rate_str = elem.get("SampleRate", elem.get("samplerate", "")) or "0"
        sample_rate = float(sample_rate_str) if sample_rate_str else 0.0
        n_samples_str = elem.get("NumSamples", elem.get("numsamples", "")) or "0"
        n_samples = int(n_samples_str) if n_samples_str else 0
        frame_size_str = elem.get("FrameSize", elem.get("framesize", "")) or "1"
        frame_size = int(frame_size_str) if frame_size_str else 1

        # Determine file type from filename or category
        file_type = "wav"
        if filename:
            if filename.endswith(".csv"):
                file_type = "CSV"
            elif filename.endswith(".wav"):
                file_type = "wav"

        # Determine group from category
        actual_group = group
        if category == "AuDesc":
            actual_group = "audio"  # Audio descriptors stay with audio
        elif category in ("X", "Y", "Z"):
            actual_group = "mocap"
        elif category == "Descriptor" or group == "descriptors":
            actual_group = "descriptors"

        return CatalogueEntry(
            xml_id=xml_id,
            name=name,
            category=category,
            group=actual_group,
            subgroup=subgroup,
            filename=filename,
            file_type=file_type,
            sample_rate=sample_rate,
            n_samples=n_samples,
            frame_size=frame_size,
        )

    def _parse_annotation_entry(
        self,
        elem: ET.Element,
        subgroup: str,
    ) -> CatalogueEntry:
        """Parse an Annotation element into a CatalogueEntry."""
        xml_id = elem.get("ID", elem.get("id", ""))
        name = elem.get("Name", elem.get("name", ""))
        filename = elem.get("Filename", elem.get("filename"))
        category = elem.get("Category", elem.get("category", ""))
        file_type = elem.get("FileType", elem.get("filetype", "NOTES"))

        return CatalogueEntry(
            xml_id=xml_id,
            name=name,
            category=category,
            group="score",
            subgroup=subgroup,
            filename=filename,
            file_type=file_type,
            sample_rate=0.0,
            n_samples=0,
        )

    # endregion

    # region Properties

    @property
    def store(self) -> RepovizzDictStore:
        """The ``RepovizzDictStore`` containing catalogue and cached data."""
        return self._store

    @property
    def is_xml_mode(self) -> bool:
        """True if loader is in XML manifest mode, False for legacy CSV."""
        return self._is_xml_mode

    @property
    def info(self) -> RepoVizzInfo:
        """Return parsed RepoVizz metadata (legacy CSV mode only).

        Raises:
            RuntimeError: If no CSV file has been loaded.
        """
        if self._info is None:
            raise RuntimeError("No CSV file loaded. Use XML mode or call load() first.")
        return self._info

    @property
    def n_samples(self) -> int:
        """Number of data samples (legacy CSV mode only)."""
        return self.info.n_samples

    @property
    def frame_rate(self) -> int:
        """Sampling rate in Hz (legacy CSV mode only)."""
        return self.info.frame_rate

    @property
    def duration_seconds(self) -> float:
        """Duration in seconds (legacy CSV mode only)."""
        return self.info.duration_seconds

    @property
    def timeline_ids(self) -> list[str]:
        """Identifiers for all loadable timelines (XML mode only)."""
        return [spec["id"] for spec in self._timeline_specs]

    @property
    def timeline_specs(self) -> list[dict[str, Any]]:
        """Metadata dicts for each loadable timeline (XML mode only)."""
        return list(self._timeline_specs)

    @property
    def groups(self) -> list[str]:
        """List of all group names present (XML mode only)."""
        return self._store.groups

    @property
    def catalogue(self) -> dict[str, CatalogueEntry]:
        """The full catalogue of entries (XML mode only)."""
        return self._store.catalogue

    # endregion

    # region Timeline Creation

    def create_timeline(
        self,
        uid: str | None = None,
        **kwargs: Any,
    ) -> "DiscretePhysicalTimeline":
        """Create a DiscretePhysicalTimeline from a catalogue entry.

        In XML mode: looks up the entry and creates a timeline with its metadata.
        In legacy CSV mode: creates timeline from the loaded CSV.

        Args:
            uid: Entry lookup key or timeline ID. In XML mode, supports:
                - Audio shorthand: "mono", "binaural", "pickup_vln1"
                - Descriptor pattern: "tonal.ChordsStrength.mono"
                - Exact xml_id or name
            **kwargs: Additional arguments:
                - name: Override the timeline's name (defaults to entry's name).
                - attach_cmap: If True (default), attach a SamplesToSeconds C-map.
                - tl_uid: Override the timeline's ID (defaults to entry's xml_id).

        Returns:
            A DiscretePhysicalTimeline representing the data.

        Raises:
            RuntimeError: If no file has been loaded.
            KeyError: If uid doesn't match any catalogue entry (XML mode).
        """
        name = kwargs.get("name")
        attach_cmap = kwargs.get("attach_cmap", True)
        tl_uid = kwargs.get("tl_uid")  # Override for the actual timeline ID

        if self._is_xml_mode:
            return self._create_timeline_xml(uid, tl_uid, name, attach_cmap)
        else:
            return self._create_timeline_csv(tl_uid or uid, name, attach_cmap)

    def _create_timeline_csv(
        self,
        uid: str | None = None,
        name: str | None = None,
        attach_cmap: bool = True,
    ) -> "DiscretePhysicalTimeline":
        """Create timeline from legacy CSV (backwards compatible)."""
        from timetoalign.timelines import DiscretePhysicalTimeline

        info = self.info

        if uid is None and info.source_path is not None:
            uid = info.source_path.stem
        if name is None and info.source_path is not None:
            name = info.source_path.name

        timeline = DiscretePhysicalTimeline(
            length=info.n_samples,
            unit=TimeUnit.samples,
            number_type=NumberType.int,
            uid=uid,
            name=name,
        )

        if attach_cmap:
            from timetoalign.maps import SamplesToSeconds

            cmap = SamplesToSeconds(sample_rate=info.frame_rate)
            timeline.add_conversion_map(cmap)

        return timeline

    def _resolve_csv_sample_count(self, entry: CatalogueEntry) -> int:
        """Read a RepoVizz CSV file to determine the actual sample count.

        When the XML manifest has an empty ``numsamples`` attribute (common
        for descriptor entries), this method reads the CSV's data line and
        counts the values.

        Args:
            entry: Catalogue entry with a CSV filename.

        Returns:
            Number of samples, or 0 if the file cannot be read.
        """
        if self._xml_root_path is None or not entry.filename:
            return 0

        csv_path = self._xml_root_path / entry.filename
        if not csv_path.exists():
            self._logger.warning("CSV file not found: %s", csv_path)
            return 0

        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                f.readline()  # skip header
                data_line = f.readline().strip()
            if not data_line:
                return 0
            return sum(1 for v in data_line.split(",") if v.strip())
        except Exception:
            self._logger.warning("Failed to read CSV: %s", csv_path, exc_info=True)
            return 0

    def _create_timeline_xml(
        self,
        entry_id: str | None,
        uid: str | None,
        name: str | None,
        attach_cmap: bool,
    ) -> "DiscretePhysicalTimeline":
        """Create timeline from XML catalogue entry."""
        from timetoalign.timelines import DiscretePhysicalTimeline

        if not self._timeline_specs:
            raise RuntimeError("No XML manifest loaded. Call load() first.")

        # If entry_id is not specified, use the first timeline
        if entry_id is None:
            if len(self._timeline_specs) == 1:
                entry_id = self._timeline_specs[0]["id"]
            else:
                raise ValueError(
                    f"Must specify entry_id for XML mode with {len(self._timeline_specs)} entries. "
                    "Use timeline_ids property to see options."
                )

        # Find the entry (entry_id is guaranteed non-None here)
        assert entry_id is not None
        entry = self._find_entry(entry_id)

        # Check cache (include uid in key if overridden)
        cache_key = f"{entry.xml_id}:{uid}" if uid else entry.xml_id
        if cache_key in self._timeline_cache:
            return self._timeline_cache[cache_key]

        # Determine timeline parameters
        tl_uid = uid or entry.xml_id
        tl_name = name or entry.name
        sample_rate = entry.sample_rate if entry.is_signal else 240.0
        n_samples = entry.n_samples if entry.is_signal else 0

        # For MoCap markers, we need to load the CSV to get sample count
        if entry.file_type == "MoCapMarker" and entry.related_ids:
            # Get first signal to determine sample count
            first_signal_id = entry.related_ids[0]
            if first_signal_id in self.catalogue:
                first_signal = self.catalogue[first_signal_id]
                n_samples = first_signal.n_samples
                sample_rate = first_signal.sample_rate

        # For CSV entries with missing n_samples, read from file
        if n_samples == 0 and entry.file_type == "CSV" and entry.filename:
            n_samples = self._resolve_csv_sample_count(entry)
            if sample_rate == 0.0:
                sample_rate = 240.0  # Default descriptor rate

        # For MoCap CSV sub-signals that also lack n_samples
        if n_samples == 0 and entry.file_type == "MoCapMarker" and entry.related_ids:
            for rid in entry.related_ids:
                if rid in self.catalogue:
                    sub = self.catalogue[rid]
                    if sub.filename and sub.n_samples == 0:
                        resolved = self._resolve_csv_sample_count(sub)
                        if resolved > 0:
                            n_samples = resolved
                            sample_rate = sub.sample_rate or 240.0
                            break

        timeline = DiscretePhysicalTimeline(
            length=n_samples,
            unit=TimeUnit.samples,
            number_type=NumberType.int,
            uid=tl_uid,
            name=tl_name,
        )

        if attach_cmap and sample_rate > 0:
            from timetoalign.maps import SamplesToSeconds

            cmap = SamplesToSeconds(sample_rate=int(sample_rate))
            timeline.add_conversion_map(cmap)

        self._timeline_cache[cache_key] = timeline
        return timeline

    def create_timelines(
        self,
        id_pattern: str | None = None,
        *,
        ids: list[str] | None = None,
    ) -> list["Timeline"]:
        """Create multiple timelines.

        Args:
            id_pattern: Regex pattern to filter timeline IDs.
            ids: List of timeline identifiers to create. If None, all are created.

        Returns:
            List of Timeline objects.
        """
        if not self._is_xml_mode:
            return [self.create_timeline()]

        target_ids = ids if ids is not None else self.timeline_ids

        if id_pattern:
            pattern = re.compile(id_pattern)
            target_ids = [tid for tid in target_ids if pattern.search(tid)]

        result: list[Timeline] = [self.create_timeline(uid=tid) for tid in target_ids]
        return result

    def create_group(
        self,
        category: str | None = None,
        ids: list[str] | None = None,
        *,
        id: str | None = None,
        name: str | None = None,
        with_notes: bool = False,
        group_id: str | None = None,  # Deprecated alias for category
    ) -> "TimelineGroup":
        """Create a TimelineGroup containing timelines.

        Args:
            category: Filter to a specific category ("audio", "mocap", etc.).
            ids: Specific timeline IDs to include.
            id: Custom ID for the TimelineGroup. Defaults to
                ``"repovizz:{category or 'all'}"``.
            name: Custom name for the TimelineGroup. Defaults to
                the source filename stem.
            with_notes: If True, add notes as a child of the first audio
                timeline using ``use_conversion_map=True``. This enables
                automatic coordinate transfer from seconds (notes) to
                samples (audio). Default: False.
            group_id: Deprecated alias for ``category``.

        Returns:
            A TimelineGroup containing the specified timelines.

        Raises:
            ValueError: If category is invalid.
            RuntimeError: If no XML manifest loaded.

        Examples:
            Load an EEP recording with all timelines and notes:

            >>> loader = RepoVizzLoader.from_file("recording.xml")
            >>> group = loader.create_group(id="normal", name="Normal Recording", with_notes=True)
        """
        import warnings

        from timetoalign.alignment.groups import TimelineGroup

        # Handle deprecated group_id parameter
        if group_id is not None:
            warnings.warn(
                "group_id is deprecated, use category instead",
                DeprecationWarning,
                stacklevel=2,
            )
            if category is None:
                category = group_id

        if not self._is_xml_mode:
            # Legacy mode: single timeline group
            default_name = "csv"
            if self._info and self._info.source_path:
                default_name = self._info.source_path.stem
            return TimelineGroup(
                id=id or "repovizz:csv",
                name=name or default_name,
                timelines=list(self.create_timelines()),
            )

        if not self._timeline_specs:
            raise RuntimeError("No XML manifest loaded. Call load() first.")

        # Determine which IDs to include
        if ids is not None:
            target_ids = ids
        elif category is not None:
            # Filter by category
            valid_groups = self._store.groups
            if category not in valid_groups:
                raise ValueError(
                    f"Unknown category '{category}'. Valid categories: {valid_groups}"
                )
            target_ids = [
                spec["id"]
                for spec in self._timeline_specs
                if spec.get("group") == category
            ]
        else:
            target_ids = self.timeline_ids

        timelines = list(self.create_timelines(ids=target_ids))

        # Add notes as child of first audio timeline if requested
        if with_notes and self._store.notes is not None:
            # Find the first audio timeline (main audio, usually the mp3)
            audio_timeline = None
            for tl in timelines:
                # Check if this timeline corresponds to an audio entry
                for entry in self._store.catalogue.values():
                    if entry.xml_id == tl.id and entry.group == "audio":
                        # Prefer the main audio (ambient mono, typically mp3)
                        if "mono" in entry.name.lower() or entry.file_type == "BWF":
                            audio_timeline = tl
                            break
                if audio_timeline:
                    break

            # Fallback: use first audio timeline
            if audio_timeline is None:
                audio_ids = self._store.audio
                if audio_ids:
                    for tl in timelines:
                        if tl.id in audio_ids:
                            audio_timeline = tl
                            break

            if audio_timeline:
                from timetoalign.loader.store import SingleStore

                # Create notes timeline from stored notes EventData
                notes_data = self._store.notes
                group_id_str = id or (category or "group")
                notes_store = SingleStore(notes_data, name="notes")
                notes_tl = notes_store.create_timeline(uid=f"{group_id_str}_notes")

                # Add as child with automatic unit conversion (seconds -> samples)
                audio_timeline.add_child(notes_tl, offset=0, use_conversion_map=True)

        # Use source filename as group name if not specified
        default_name: str | None = None
        if self._sources:
            default_name = self._sources[-1].stem

        return TimelineGroup(
            id=id or f"repovizz:{category or 'all'}",
            name=name or default_name,
            timelines=timelines,
        )

    # endregion

    # region Helper Methods

    def _find_entry(self, id: str) -> CatalogueEntry:
        """Look up a catalogue entry by ID, name, pattern, or shorthand.

        Supports multiple lookup strategies:
        1. Exact xml_id match
        2. Exact name match
        3. Audio shorthand: "mono", "binaural", "pickup_vln1", etc.
        4. Descriptor pattern: "tonal.ChordsStrength.mono", "lowlevel.Dissonance.binaural"
        5. Partial/regex match on xml_id

        Args:
            id: Entry identifier, name, shorthand, or pattern.

        Returns:
            The CatalogueEntry.

        Raises:
            KeyError: If not found.
        """
        # 1. Exact match by xml_id
        if id in self.catalogue:
            return self.catalogue[id]

        # 2. Exact match by name
        for entry in self.catalogue.values():
            if entry.name == id:
                return entry

        # 3. Audio shorthand (mono, binaural, pickup_*)
        audio_id = self.find_audio(id)
        if audio_id:
            return self.catalogue[audio_id]

        # 4. Descriptor pattern: "type.name.source" (e.g., "tonal.ChordsStrength.mono")
        if "." in id:
            parts = id.split(".")
            if len(parts) >= 3:
                desc_type, desc_name, source = parts[0], parts[1], parts[2]
                desc_id = self.find_audio_descriptor(desc_type, desc_name, source)
                if desc_id:
                    return self.catalogue[desc_id]

        # 5. Partial/regex match by id
        all_ids = list(self.catalogue.keys())
        try:
            resolved_id = resolve_id(id, all_ids, warn_multiple=True)
            return self.catalogue[resolved_id]
        except KeyError:
            pass

        raise KeyError(
            f"No catalogue entry matching '{id}'. "
            f"Try: audio source (mono, binaural, pickup_vln1), "
            f"descriptor pattern (tonal.ChordsStrength.mono), "
            f"or exact xml_id."
        )

    def get_entry(self, id: str) -> CatalogueEntry:
        """Get a catalogue entry by ID.

        This is the public API for accessing catalogue entries.

        Args:
            id: Entry identifier, name, or partial match.

        Returns:
            The CatalogueEntry.

        Raises:
            KeyError: If not found.
        """
        return self._find_entry(id)

    def find_signal(
        self,
        name_pattern: str,
        source: str | None = None,
    ) -> str | None:
        """Find a signal entry by name pattern.

        Args:
            name_pattern: Regex pattern to match signal names.
            source: Optional source filter (e.g., "mono", "vln1").

        Returns:
            The matching entry ID, or None if not found.
        """
        pattern = re.compile(name_pattern, re.IGNORECASE)

        for entry in self.catalogue.values():
            if not entry.is_signal:
                continue
            if source and source.lower() not in entry.name.lower():
                continue
            if pattern.search(entry.name):
                return entry.xml_id

        return None

    def find_descriptor(
        self,
        descriptor_name: str,
        instrument: str | None = None,
    ) -> str | None:
        """Find a descriptor entry by name.

        Searches both the entry name and filename for matches.  The
        instrument filter is checked against the subgroup first, then
        the filename as a fallback (bowing gesture descriptors often
        encode the instrument in the filename, e.g. ``vln1_bb_angle.csv``).

        Args:
            descriptor_name: Descriptor name (e.g., "bb_angle", "bow_vel").
            instrument: Optional instrument filter (e.g., "vln1", "cello").

        Returns:
            The matching entry ID, or None if not found.
        """
        for entry in self.catalogue.values():
            if entry.group != "descriptors":
                continue
            if instrument:
                inst_lower = instrument.lower()
                # Check subgroup first, then filename
                in_subgroup = (
                    inst_lower in entry.subgroup.lower() if entry.subgroup else False
                )
                in_filename = (
                    inst_lower in entry.filename.lower() if entry.filename else False
                )
                if not (in_subgroup or in_filename):
                    continue
            name_lower = descriptor_name.lower()
            if name_lower in entry.name.lower() or (
                entry.filename and name_lower in entry.filename.lower()
            ):
                return entry.xml_id

        return None

    def find_audio(
        self,
        source: str | None,
    ) -> str | None:
        """Find an audio entry by source name.

        Args:
            source: Source name (e.g., "mono", "binaural", "pickup_vln1").
                For pickup sources, can use "vln1" shorthand.

        Returns:
            The matching entry ID, or None if not found.
        """
        if source is None:
            return None
        source_lower = source.lower()

        for entry in self.catalogue.values():
            if entry.group != "audio":
                continue
            # Audio entries only (not AuDesc signals)
            if (
                entry.file_type not in ("BWF", "mp3", "wav")
                or entry.category == "AuDesc"
            ):
                continue
            if not entry.filename:
                continue

            filename_lower = entry.filename.lower()

            # Match by source name in filename
            if source_lower in filename_lower:
                return entry.xml_id

            # For pickup sources, match instrument suffix
            if source_lower.startswith("pickup_"):
                instrument = source_lower.replace("pickup_", "")
                if f"pickup_{instrument}" in filename_lower or filename_lower.endswith(
                    f"_{instrument}.mp3"
                ):
                    return entry.xml_id
            elif "pickup" in entry.category.lower():
                # Match instrument name for pickup entries
                if source_lower in filename_lower:
                    return entry.xml_id

        return None

    def find_audio_descriptor(
        self,
        descriptor_type: str,
        descriptor_name: str,
        source: str,
    ) -> str | None:
        """Find an audio descriptor entry (Essentia features).

        Audio descriptors are WAV files with feature data extracted from
        audio by Essentia. They're organized by type (tonal, lowlevel,
        rhythm) and named by the feature (ChordsStrength, Dissonance, etc.).

        Args:
            descriptor_type: Type of descriptor ("tonal", "lowlevel", "rhythm").
            descriptor_name: Feature name (e.g., "ChordsStrength", "Dissonance").
            source: Audio source (e.g., "mono", "binaural", "pickup_vln1").

        Returns:
            The matching entry ID, or None if not found.
        """
        source_lower = source.lower()
        type_lower = descriptor_type.lower()
        name_lower = descriptor_name.lower()

        for entry in self.catalogue.values():
            if entry.group != "audio" or entry.category != "AuDesc":
                continue
            if not entry.filename:
                continue

            filename_lower = entry.filename.lower()

            # Match pattern: {prefix}_{source}.wav.{type}.{name}.wav
            if (
                source_lower in filename_lower
                and f".{type_lower}." in filename_lower
                and name_lower in filename_lower
            ):
                return entry.xml_id

        return None

    def get_sample_rate_for_descriptor_type(self, descriptor_type: str) -> int:
        """Get the sample rate for a descriptor type.

        Args:
            descriptor_type: Type of descriptor ("tonal", "lowlevel", "rhythm").

        Returns:
            Sample rate in Hz.
        """
        # Default sample rates from the EEP dataset
        rates = {
            "tonal": 42,
            "lowlevel": 84,
            "rhythm": 172,
            "mocap": 240,
            "descriptors": 240,
        }
        return rates.get(descriptor_type.lower(), 240)

    # endregion

    # region Clear

    def clear(self) -> None:
        """Clear all loaded data."""
        super().clear()
        self._store = RepovizzDictStore()
        self._timeline_specs = []
        self._timeline_cache = {}
        self._xml_metadata = {}
        self._xml_root_path = None
        self._is_xml_mode = False
        self._info = None

    # endregion

    # region Convenience

    @classmethod
    def from_file(cls, *paths: Path | str, **kwargs: Any) -> "RepoVizzLoader":
        """Load files and return the loader (convenience constructor).

        Args:
            *paths: Paths to XML manifest or CSV files.
            **kwargs: Additional keyword arguments passed to ``__init__``.

        Returns:
            A RepoVizzLoader with the files already loaded.
        """
        loader = cls(**kwargs)
        loader.load(*paths)
        return loader

    # endregion

    # region Magic Methods

    def __repr__(self) -> str:
        if self._is_xml_mode:
            n_entries = len(self.catalogue)
            groups = self._store.groups
            return f"RepoVizzLoader(xml, {n_entries} entries, groups={groups})"
        elif self._info is not None:
            return (
                f"RepoVizzLoader("
                f"samples={self._info.n_samples}, "
                f"rate={self._info.frame_rate}Hz, "
                f"duration={self._info.duration_seconds:.2f}s)"
            )
        return "RepoVizzLoader(not loaded)"

    def _repr_html_(self) -> str:
        """Rich HTML representation for Jupyter notebooks."""
        parts = [f"<h4>{self.__class__.__name__}</h4>"]
        parts.append("<table>")

        if self._is_xml_mode:
            parts.append("<tr><td><b>Mode</b></td><td>XML Manifest</td></tr>")
            parts.append(
                f"<tr><td><b>Entries</b></td><td>{len(self.catalogue)}</td></tr>"
            )
            parts.append(
                f"<tr><td><b>Groups</b></td><td>{', '.join(self._store.groups)}</td></tr>"
            )
            if self._xml_metadata.get("title"):
                parts.append(
                    f"<tr><td><b>Title</b></td><td>{self._xml_metadata['title']}</td></tr>"
                )
        elif self._info:
            parts.append("<tr><td><b>Mode</b></td><td>Legacy CSV</td></tr>")
            parts.append(
                f"<tr><td><b>Samples</b></td><td>{self._info.n_samples}</td></tr>"
            )
            parts.append(
                f"<tr><td><b>Rate</b></td><td>{self._info.frame_rate} Hz</td></tr>"
            )
            parts.append(
                f"<tr><td><b>Duration</b></td><td>{self._info.duration_seconds:.2f}s</td></tr>"
            )
        else:
            parts.append("<tr><td><b>Status</b></td><td>Not loaded</td></tr>")

        parts.append("</table>")
        return "\n".join(parts)

    # endregion


# endregion
