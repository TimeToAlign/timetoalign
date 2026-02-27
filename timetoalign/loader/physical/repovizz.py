"""RepoVizzLoader: ManifestLoader for RepoVizz 2-line CSV sensor data.

This module provides a manifest-style loader for the RepoVizz CSV format used
by motion capture descriptors and other sensor data in the EEP (Expressive
Ensemble Performance) dataset.

File Format:
    Line 1: Comma-separated key=value metadata pairs.
        Example: ``repoVizz,category=...,name=...,framerate=240,minval=-600,maxval=600,``
    Line 2: Comma-separated float values (one per sample).
        Example: ``166.568,166.670,166.776,...``

The loader extracts ``framerate`` from the metadata header and counts the values
on line 2 to determine ``n_samples``. No sample data is stored in memory — only
the manifest (dimensions + metadata) is retained, following the same pattern as
:class:`AudioLoader`.

Reference:
    ``dashboard/processing/notebooks/repovizz_parsing.py`` — ``load_repovizz_csv()``
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from timetoalign.loader.base import ManifestData, ManifestLoader

if TYPE_CHECKING:
    from timetoalign.timelines import DiscretePhysicalTimeline

module_logger = logging.getLogger(__name__)


# region RepoVizzInfo


class RepoVizzInfo:
    """Parsed metadata from a RepoVizz CSV file.

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
    """Load RepoVizz 2-line CSV sensor data metadata for creating physical timelines.

    RepoVizzLoader extracts the sampling rate and sample count from the
    two-line CSV format used by the EEP dataset for motion capture descriptors
    and other sensor signals. No actual sample data is loaded.

    The loader creates :class:`DiscretePhysicalTimeline` instances with the
    ``samples`` unit and an attached ``SamplesToSeconds`` conversion map.

    Examples:
        >>> loader = RepoVizzLoader.from_file("cello_bb_angle.csv")
        >>> loader.n_samples
        63965
        >>> loader.frame_rate
        240

        >>> timeline = loader.create_timeline(uid="mocap_angle")
        >>> timeline.length
        Coordinate(63965, samples)
    """

    def __init__(self) -> None:
        """Initialize the loader."""
        super().__init__()
        self._info: RepoVizzInfo | None = None

    # region Loading

    def _load_source(self, source: Path) -> ManifestData:
        """Parse a RepoVizz CSV file.

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

    # endregion

    # region Properties

    @property
    def info(self) -> RepoVizzInfo:
        """Return parsed RepoVizz metadata.

        Raises:
            RuntimeError: If no file has been loaded.
        """
        if self._info is None:
            raise RuntimeError("No file loaded. Call load() first.")
        return self._info

    @property
    def n_samples(self) -> int:
        """Number of data samples."""
        return self.info.n_samples

    @property
    def frame_rate(self) -> int:
        """Sampling rate in Hz."""
        return self.info.frame_rate

    @property
    def duration_seconds(self) -> float:
        """Duration in seconds."""
        return self.info.duration_seconds

    # endregion

    # region Timeline Creation

    def create_timeline(
        self,
        uid: str | None = None,
        name: str | None = None,
        attach_cmap: bool = True,
    ) -> "DiscretePhysicalTimeline":
        """Create a DiscretePhysicalTimeline from the loaded sensor data.

        The timeline is created with:
        - unit=TimeUnit.samples
        - length=n_samples
        - Optionally, a SamplesToSeconds C-map for coordinate conversion

        Args:
            uid: Unique identifier for the timeline. If None, uses filename stem.
            name: Human-readable name. If None, uses filename.
            attach_cmap: If True, attach a SamplesToSeconds conversion map.

        Returns:
            A DiscretePhysicalTimeline representing the sensor data.

        Raises:
            RuntimeError: If no file has been loaded.
        """
        from timetoalign.core import NumberType, TimeUnit
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

    # endregion

    # region Convenience

    @classmethod
    def from_file(cls, path: Path | str) -> "RepoVizzLoader":
        """Load a RepoVizz CSV file and return the loader.

        Args:
            path: Path to the RepoVizz CSV file.

        Returns:
            A RepoVizzLoader with the file already loaded.
        """
        loader = cls()
        loader.load(path)
        return loader

    # endregion

    def __repr__(self) -> str:
        if self._info is None:
            return "RepoVizzLoader(not loaded)"
        return (
            f"RepoVizzLoader("
            f"samples={self._info.n_samples}, "
            f"rate={self._info.frame_rate}Hz, "
            f"duration={self._info.duration_seconds:.2f}s)"
        )


# endregion
