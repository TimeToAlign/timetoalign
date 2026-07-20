"""IIIFManifestLoader for loading image metadata from IIIF manifests.

IIIF (International Image Interoperability Framework) manifests contain
structured metadata about images, including dimensions, that can be used
to construct graphical timelines without loading the full image data.

This loader supports IIIF Presentation API 2.x and 3.x manifests.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from timetoalign.loader.base import Loader

if TYPE_CHECKING:
    from timetoalign.timelines import Timeline

module_logger = logging.getLogger(__name__)


@dataclass
class IIIFCanvasInfo:
    """Information about a single IIIF canvas (image).

    Attributes:
        id: Canvas identifier (URL or local ID).
        width: Image width in pixels.
        height: Image height in pixels.
        label: Human-readable label for the canvas.
        metadata: Additional canvas metadata.
    """

    id: str
    width: int
    height: int
    label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IIIFManifestInfo:
    """Parsed information from an IIIF manifest.

    Attributes:
        id: Manifest identifier (URL).
        label: Human-readable manifest label.
        canvases: List of canvas information.
        metadata: Manifest-level metadata.
    """

    id: str
    label: str | None
    canvases: list[IIIFCanvasInfo]
    metadata: dict[str, Any] = field(default_factory=dict)


class IIIFManifestLoader(Loader[IIIFManifestInfo]):
    """Load image metadata from IIIF Presentation API manifests.

    IIIF manifests contain canvas dimensions that represent image sizes.
    This loader extracts width/height for use with graphical timelines
    without needing to download or load the actual image files.

    Supports both IIIF Presentation API 2.x and 3.x formats.

    Examples:
        >>> loader = IIIFManifestLoader()
        >>> loader.load("manifest.json")
        >>> loader.dimensions
        {'width': 4096, 'height': 299400}

        >>> # Access individual canvases
        >>> for canvas in loader.manifest_info.canvases:
        ...     print(f"{canvas.label}: {canvas.width}x{canvas.height}")

    Attributes:
        manifest_info: Parsed manifest information (after loading).
    """

    def __init__(self) -> None:
        """Initialize the loader."""
        super().__init__()
        self._manifest_info: IIIFManifestInfo | None = None
        self._source_path: Path | None = None
        self._logger = module_logger.getChild("IIIFManifestLoader")

    def _load_source(self, source: Path) -> IIIFManifestInfo:
        """Load and parse one IIIF manifest file.

        Args:
            source: Path to the IIIF manifest JSON file.

        Returns:
            Parsed IIIF manifest information.

        Raises:
            FileNotFoundError: If the manifest file doesn't exist.
            ValueError: If the manifest is invalid or has no canvases.
            json.JSONDecodeError: If the file is not valid JSON.
        """
        if not source.exists():
            raise FileNotFoundError(f"Manifest file not found: {source}")

        with open(source, encoding="utf-8") as f:
            manifest_data = json.load(f)
        return self._parse_manifest(manifest_data)

    def _accept_source(
        self,
        path: Path,
        source_meta: dict[str, Any],
        payload: IIIFManifestInfo,
    ) -> None:
        """Retain parsed manifest information from the shared lifecycle."""
        super()._accept_source(path, source_meta, payload)
        self._manifest_info = payload
        self._source_path = path
        self._logger.debug(
            f"Loaded manifest from {path}: "
            f"{len(self._manifest_info.canvases)} canvas(es)"
        )

    def _parse_manifest(self, data: dict[str, Any]) -> IIIFManifestInfo:
        """Parse manifest data into structured info.

        Handles both IIIF Presentation API 2.x and 3.x formats.

        Args:
            data: Raw manifest dictionary from JSON.

        Returns:
            Parsed IIIFManifestInfo.

        Raises:
            ValueError: If manifest structure is invalid.
        """
        # Detect API version
        context = data.get("@context", "")
        if isinstance(context, list):
            # IIIF 3.x uses a list of contexts
            is_v3 = any("presentation/3" in str(c) for c in context)
        else:
            is_v3 = "presentation/3" in str(context)

        if is_v3:
            return self._parse_v3_manifest(data)
        else:
            return self._parse_v2_manifest(data)

    def _parse_v2_manifest(self, data: dict[str, Any]) -> IIIFManifestInfo:
        """Parse IIIF Presentation API 2.x manifest.

        In 2.x, canvases are nested in sequences[].canvases[].
        """
        manifest_id = data.get("@id", "")
        label = data.get("label", None)

        # Extract metadata
        metadata = {}
        if "metadata" in data:
            for item in data["metadata"]:
                key = item.get("label", "")
                value = item.get("value", "")
                metadata[key] = value

        # Extract canvases from sequences
        canvases = []
        sequences = data.get("sequences", [])
        for sequence in sequences:
            for canvas_data in sequence.get("canvases", []):
                canvas = self._parse_v2_canvas(canvas_data)
                canvases.append(canvas)

        if not canvases:
            raise ValueError("Manifest contains no canvases")

        return IIIFManifestInfo(
            id=manifest_id,
            label=label,
            canvases=canvases,
            metadata=metadata,
        )

    def _parse_v2_canvas(self, data: dict[str, Any]) -> IIIFCanvasInfo:
        """Parse a single canvas from IIIF 2.x format."""
        canvas_id = data.get("@id", "")
        width = data.get("width")
        height = data.get("height")
        label = data.get("label")

        if width is None or height is None:
            raise ValueError(f"Canvas {canvas_id} missing width/height")

        return IIIFCanvasInfo(
            id=canvas_id,
            width=int(width),
            height=int(height),
            label=label,
        )

    def _parse_v3_manifest(self, data: dict[str, Any]) -> IIIFManifestInfo:
        """Parse IIIF Presentation API 3.x manifest.

        In 3.x, canvases are directly in items[].
        """
        manifest_id = data.get("id", "")
        label = self._extract_v3_label(data.get("label"))

        # Extract metadata
        metadata = {}
        if "metadata" in data:
            for item in data["metadata"]:
                key = self._extract_v3_label(item.get("label", {}))
                value = self._extract_v3_label(item.get("value", {}))
                if key:
                    metadata[key] = value

        # Extract canvases from items
        canvases = []
        for item in data.get("items", []):
            if item.get("type") == "Canvas":
                canvas = self._parse_v3_canvas(item)
                canvases.append(canvas)

        if not canvases:
            raise ValueError("Manifest contains no canvases")

        return IIIFManifestInfo(
            id=manifest_id,
            label=label,
            canvases=canvases,
            metadata=metadata,
        )

    def _parse_v3_canvas(self, data: dict[str, Any]) -> IIIFCanvasInfo:
        """Parse a single canvas from IIIF 3.x format."""
        canvas_id = data.get("id", "")
        width = data.get("width")
        height = data.get("height")
        label = self._extract_v3_label(data.get("label"))

        if width is None or height is None:
            raise ValueError(f"Canvas {canvas_id} missing width/height")

        return IIIFCanvasInfo(
            id=canvas_id,
            width=int(width),
            height=int(height),
            label=label,
        )

    def _extract_v3_label(self, label_data: Any) -> str | None:
        """Extract label string from IIIF 3.x language map.

        In 3.x, labels are language maps like {"en": ["Label text"]}.
        """
        if label_data is None:
            return None
        if isinstance(label_data, str):
            return label_data
        if isinstance(label_data, dict):
            # Try common language codes
            for lang in ["en", "none", "und"]:
                if lang in label_data:
                    values = label_data[lang]
                    if isinstance(values, list) and values:
                        return str(values[0])
                    return str(values)
            # Return first available
            for values in label_data.values():
                if isinstance(values, list) and values:
                    return str(values[0])
                return str(values)
        return None

    # endregion

    # region Properties

    @property
    def manifest_info(self) -> IIIFManifestInfo:
        """Return parsed manifest information.

        Raises:
            RuntimeError: If no manifest has been loaded.
        """
        if self._manifest_info is None:
            raise RuntimeError("No manifest loaded. Call load() first.")
        return self._manifest_info

    @property
    def dimensions(self) -> dict[str, int]:
        """Return dimensions of the first (or only) canvas.

        Returns:
            Dictionary with 'width' and 'height' keys.

        Raises:
            RuntimeError: If no manifest has been loaded.
        """
        info = self.manifest_info
        canvas = info.canvases[0]
        return {"width": canvas.width, "height": canvas.height}

    @property
    def width(self) -> int:
        """Width of the first canvas in pixels."""
        return self.dimensions["width"]

    @property
    def height(self) -> int:
        """Height of the first canvas in pixels."""
        return self.dimensions["height"]

    @property
    def n_canvases(self) -> int:
        """Number of canvases in the manifest."""
        return len(self.manifest_info.canvases)

    @property
    def label(self) -> str | None:
        """Human-readable label from the manifest."""
        return self.manifest_info.label

    @property
    def source_path(self) -> Path | None:
        """Path to the loaded manifest file."""
        return self._source_path

    # endregion

    # region Metadata Access

    def get_metadata(self, key: str) -> str | None:
        """Get a metadata value by key.

        Args:
            key: Metadata label to look up.

        Returns:
            Metadata value, or None if not found.
        """
        return self.manifest_info.metadata.get(key)

    def get_canvas(self, index: int = 0) -> IIIFCanvasInfo:
        """Get canvas information by index.

        Args:
            index: Zero-based canvas index.

        Returns:
            IIIFCanvasInfo for the requested canvas.

        Raises:
            IndexError: If index is out of range.
        """
        return self.manifest_info.canvases[index]

    # endregion

    # region Timeline Creation

    @property
    def name(self) -> str:
        """Human-readable name for the loaded image.

        Returns the manifest label if available, otherwise uses the canvas label,
        or falls back to the source filename.
        """
        if self._manifest_info is None:
            return "Unknown"

        # Try manifest label first
        if self._manifest_info.label:
            return self._manifest_info.label

        # Try first canvas label
        if self._manifest_info.canvases and self._manifest_info.canvases[0].label:
            return self._manifest_info.canvases[0].label

        # Fall back to source filename
        if self._source_path:
            return self._source_path.stem

        return "IIIF Image"

    def create_timeline(
        self,
        uid: str | None = None,
        name: str | None = None,
        axis: str = "height",
    ) -> "Timeline":
        """Create a graphical timeline from the loaded IIIF manifest.

        The timeline length is determined by the image dimensions along the
        specified axis (height by default, for vertical piano rolls).

        Args:
            uid: Unique identifier for the timeline. Auto-generated if None.
            name: Human-readable name. Uses manifest/canvas label if None.
            axis: Which dimension to use as the timeline axis:
                - "height" (default): Timeline length = image height
                - "width": Timeline length = image width

        Returns:
            A DiscreteGraphicalTimeline representing the image.

        Raises:
            RuntimeError: If no manifest has been loaded.
            ValueError: If axis is not "height" or "width".

        Examples:
            >>> loader = IIIFManifestLoader()
            >>> loader.load("manifest.json")
            >>> timeline = loader.create_timeline(uid="dgt1_image")
        """
        from timetoalign import TimeUnit
        from timetoalign.timelines import Timeline

        if self._manifest_info is None:
            raise RuntimeError("No manifest loaded. Call load() first.")

        if axis == "height":
            length = self.height
        elif axis == "width":
            length = self.width
        else:
            raise ValueError(f"axis must be 'height' or 'width', got: {axis!r}")

        return Timeline(
            length=length,
            unit=TimeUnit.pixels,
            uid=uid,
            name=name or self.name,
        )

    # endregion

    def __repr__(self) -> str:
        if self._manifest_info is None:
            return "IIIFManifestLoader(not loaded)"
        return (
            f"IIIFManifestLoader("
            f"canvases={len(self._manifest_info.canvases)}, "
            f"dimensions={self.width}x{self.height})"
        )
