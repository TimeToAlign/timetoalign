"""AudioLoader for loading audio file metadata into TimeToAlign!

This module provides a manifest-style loader that extracts metadata from audio
files (WAV, FLAC, OGG, MP3, etc.) without loading the actual sample data.
The resulting information can be used to create DiscretePhysicalTimelines
with appropriate sample-to-seconds conversion maps.

Design Philosophy:
    AudioLoader follows the same pattern as IIIFManifestLoader: it extracts
    dimensions and metadata from files without loading the heavy content.
    This allows users to:
    1. Create timelines representing audio files
    2. Attach conversion maps for coordinate transformations
    3. Add events from other loaders (annotations, beat markers, etc.)

Backend Support:
    The loader uses soundfile as the primary backend (for WAV, FLAC, OGG, etc.)
    with optional mutagen support for MP3/M4A metadata. If neither is available,
    it falls back to Python's built-in wave module for WAV files only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from timetoalign.loader.base import Loader

if TYPE_CHECKING:
    from timetoalign.maps import SamplesToSeconds
    from timetoalign.timelines import DiscretePhysicalTimeline

module_logger = logging.getLogger(__name__)


# region Backend Detection


def _get_soundfile():
    """Lazy import of soundfile with helpful error message."""
    try:
        import soundfile

        return soundfile
    except ImportError:
        return None


def _get_mutagen():
    """Lazy import of mutagen for MP3/M4A support."""
    try:
        import mutagen

        return mutagen
    except ImportError:
        return None


def _get_wave():
    """Built-in wave module as fallback for WAV files."""
    import wave

    return wave


# endregion


# region AudioInfo


@dataclass
class AudioInfo:
    """Metadata for an audio file.

    This dataclass holds all relevant information about an audio file
    that is needed to create a DiscretePhysicalTimeline.

    Attributes:
        n_samples: Total number of samples in the file (frames).
        sample_rate: Sample rate in Hz (e.g., 44100, 48000).
        channels: Number of audio channels (1=mono, 2=stereo).
        duration_seconds: Duration in seconds (computed from n_samples/sample_rate).
        format: Audio format/codec (e.g., "WAV", "FLAC", "MP3").
        subtype: Audio subtype/encoding (e.g., "PCM_16", "PCM_24", "VORBIS").
        bits_per_sample: Bit depth (e.g., 16, 24, 32). May be None for lossy formats.
        source_path: Path to the source file.
        extra: Additional format-specific metadata.
    """

    n_samples: int
    sample_rate: int
    channels: int
    duration_seconds: float
    format: str
    subtype: str | None = None
    bits_per_sample: int | None = None
    source_path: Path | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def length_in_samples(self) -> int:
        """Alias for n_samples, matching timeline terminology."""
        return self.n_samples

    @property
    def is_mono(self) -> bool:
        """Whether the audio is mono (single channel)."""
        return self.channels == 1

    @property
    def is_stereo(self) -> bool:
        """Whether the audio is stereo (two channels)."""
        return self.channels == 2


# endregion


# region AudioLoader


class AudioLoader(Loader[AudioInfo]):
    """Load audio file metadata for creating physical timelines.

    AudioLoader extracts metadata from audio files without loading the actual
    sample data. This is efficient for creating DiscretePhysicalTimelines
    that represent audio files in the TimeToAlign! framework.

    The loader automatically:
    - Detects the best available backend (soundfile > mutagen > wave)
    - Extracts sample count, sample rate, channels, and format info
    - Provides methods to create timelines with appropriate C-maps

    Supported formats depend on installed backends:
    - soundfile: WAV, FLAC, OGG, AIFF, and many more (via libsndfile)
    - mutagen: MP3, M4A, FLAC, OGG (metadata only, may not have exact sample count)
    - wave (builtin): WAV only

    Examples:
        >>> loader = AudioLoader()
        >>> loader.load("recording.wav")
        >>> loader.n_samples
        7938048
        >>> loader.sample_rate
        44100
        >>> loader.duration_seconds
        180.0

        >>> # Create a timeline
        >>> timeline = loader.create_timeline(uid="my_audio")
        >>> timeline.unit
        <TimeUnit.samples: 'samples'>
        >>> timeline.length
        Coordinate(7938048, samples)

        >>> # The timeline has a SamplesToSeconds C-map attached
        >>> from timetoalign.core import TimeUnit
        >>> timeline.get_timestamp(44100).get_unit(TimeUnit.seconds)
        1.0

    Attributes:
        audio_info: Parsed audio metadata (after loading).
    """

    def __init__(self) -> None:
        """Initialize the loader."""
        super().__init__()
        self._audio_info: AudioInfo | None = None
        self._source_path: Path | None = None
        self._logger = module_logger.getChild("AudioLoader")

    def _load_source(self, source: Path) -> AudioInfo:
        """Load metadata from one audio file.

        Args:
            source: Path to the audio file.

        Returns:
            Parsed audio metadata.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the file format is not supported or cannot be read.
        """
        if not source.exists():
            raise FileNotFoundError(f"Audio file not found: {source}")

        # Try backends in order of preference
        sf = _get_soundfile()
        if sf is not None:
            try:
                info = self._load_with_soundfile(sf, source)
                self._logger.debug(
                    f"Read audio metadata from {source} using soundfile: "
                    f"{info.n_samples} samples @ {info.sample_rate} Hz"
                )
                return info
            except Exception as e:
                self._logger.debug(f"soundfile failed for {source}: {e}")

        # Try mutagen for MP3/M4A
        mutagen = _get_mutagen()
        if mutagen is not None:
            try:
                info = self._load_with_mutagen(mutagen, source)
                self._logger.debug(
                    f"Read audio metadata from {source} using mutagen: "
                    f"{info.n_samples} samples @ {info.sample_rate} Hz"
                )
                return info
            except Exception as e:
                self._logger.debug(f"mutagen failed for {source}: {e}")

        # Fallback to wave module for WAV files (PCM only)
        if source.suffix.lower() in (".wav", ".wave"):
            try:
                info = self._load_with_wave(source)
                self._logger.debug(
                    f"Read audio metadata from {source} using wave: "
                    f"{info.n_samples} samples @ {info.sample_rate} Hz"
                )
                return info
            except Exception as e:
                self._logger.debug(f"wave module failed for {source}: {e}")

        # Last resort: manual RIFF header parsing (handles IEEE float and other
        # non-PCM WAV formats that Python's wave module rejects)
        if source.suffix.lower() in (".wav", ".wave"):
            try:
                info = self._load_with_riff_parser(source)
                self._logger.debug(
                    f"Read audio metadata from {source} using RIFF parser: "
                    f"{info.n_samples} samples @ {info.sample_rate} Hz"
                )
                return info
            except Exception as e:
                self._logger.debug(f"RIFF parser failed for {source}: {e}")

        raise ValueError(
            f"Cannot read audio file '{source}'. "
            "Install soundfile (pip install soundfile) for broad format support, "
            "or mutagen (pip install mutagen) for MP3/M4A support."
        )

    def _accept_source(
        self,
        path: Path,
        source_meta: dict[str, Any],
        payload: AudioInfo,
    ) -> None:
        """Retain parsed audio information from the shared lifecycle."""
        super()._accept_source(path, source_meta, payload)
        self._audio_info = payload
        self._source_path = path

    def _load_with_soundfile(self, sf, path: Path) -> AudioInfo:
        """Load metadata using soundfile (libsndfile backend)."""
        info = sf.info(str(path))

        return AudioInfo(
            n_samples=info.frames,
            sample_rate=info.samplerate,
            channels=info.channels,
            duration_seconds=info.duration,
            format=info.format,
            subtype=info.subtype,
            bits_per_sample=self._subtype_to_bits(info.subtype),
            source_path=path,
            extra={
                "sections": info.sections,
                "seekable": info.seekable,
            },
        )

    def _load_with_mutagen(self, mutagen, path: Path) -> AudioInfo:
        """Load metadata using mutagen (for MP3, M4A, etc.)."""
        audio = mutagen.File(str(path))
        if audio is None:
            raise ValueError(f"mutagen could not parse {path}")

        # Get audio info
        info = audio.info

        # Sample rate
        sample_rate = getattr(info, "sample_rate", None)
        if sample_rate is None:
            raise ValueError(f"Could not determine sample rate for {path}")

        # Duration and sample count
        duration = getattr(info, "length", None)
        if duration is None:
            raise ValueError(f"Could not determine duration for {path}")

        # Compute sample count from duration (may not be exact for VBR)
        n_samples = int(duration * sample_rate)

        # Channels
        channels = getattr(info, "channels", 2)

        # Bits per sample (if available)
        bits = getattr(info, "bits_per_sample", None)

        # Determine format from file extension
        ext = path.suffix.lower()
        format_map = {
            ".mp3": "MP3",
            ".m4a": "M4A",
            ".aac": "AAC",
            ".flac": "FLAC",
            ".ogg": "OGG",
            ".opus": "OPUS",
        }
        fmt = format_map.get(ext, ext.upper().lstrip("."))

        return AudioInfo(
            n_samples=n_samples,
            sample_rate=sample_rate,
            channels=channels,
            duration_seconds=duration,
            format=fmt,
            subtype=None,
            bits_per_sample=bits,
            source_path=path,
            extra={
                "bitrate": getattr(info, "bitrate", None),
                "codec": getattr(info, "codec", None),
            },
        )

    def _load_with_wave(self, path: Path) -> AudioInfo:
        """Load metadata using Python's built-in wave module (WAV only)."""
        wave = _get_wave()

        with wave.open(str(path), "rb") as wf:
            n_samples = wf.getnframes()
            sample_rate = wf.getframerate()
            channels = wf.getnchannels()
            bits_per_sample = wf.getsampwidth() * 8

            duration_seconds = n_samples / sample_rate

            return AudioInfo(
                n_samples=n_samples,
                sample_rate=sample_rate,
                channels=channels,
                duration_seconds=duration_seconds,
                format="WAV",
                subtype=f"PCM_{bits_per_sample}",
                bits_per_sample=bits_per_sample,
                source_path=path,
            )

    def _load_with_riff_parser(self, path: Path) -> AudioInfo:
        """Load metadata by manually parsing the RIFF/WAV header.

        This handles WAV formats that Python's built-in wave module cannot read,
        including IEEE float (format tag 3) commonly used by audio feature
        extraction tools (e.g., Essentia, RepoVizz).

        Only reads the header chunks (fmt, fact, data) — no sample data is loaded.

        Args:
            path: Path to the WAV file.

        Returns:
            AudioInfo with metadata extracted from the RIFF header.

        Raises:
            ValueError: If the file is not a valid RIFF/WAV file.
        """
        import struct

        format_names = {
            1: "PCM",
            3: "IEEE_FLOAT",
            6: "A_LAW",
            7: "MU_LAW",
            0xFFFE: "EXTENSIBLE",
        }

        with open(path, "rb") as f:
            # RIFF header
            riff_id = f.read(4)
            if riff_id != b"RIFF":
                raise ValueError(f"Not a RIFF file: {path}")
            f.read(4)  # file size (unused)
            wave_id = f.read(4)
            if wave_id != b"WAVE":
                raise ValueError(f"Not a WAVE file: {path}")

            # Parse chunks
            channels = 0
            sample_rate = 0
            bits_per_sample = 0
            format_tag = 0
            n_samples: int | None = None
            data_size = 0

            while True:
                chunk_header = f.read(8)
                if len(chunk_header) < 8:
                    break
                chunk_id = chunk_header[:4]
                chunk_size = struct.unpack("<I", chunk_header[4:])[0]

                if chunk_id == b"fmt ":
                    fmt_data = f.read(chunk_size)
                    format_tag = struct.unpack("<H", fmt_data[:2])[0]
                    channels = struct.unpack("<H", fmt_data[2:4])[0]
                    sample_rate = struct.unpack("<I", fmt_data[4:8])[0]
                    bits_per_sample = struct.unpack("<H", fmt_data[14:16])[0]
                elif chunk_id == b"fact":
                    fact_data = f.read(chunk_size)
                    n_samples = struct.unpack("<I", fact_data[:4])[0]
                elif chunk_id == b"data":
                    data_size = chunk_size
                    break  # data chunk is last relevant chunk
                else:
                    # Skip unknown chunks
                    f.seek(chunk_size, 1)

        if sample_rate == 0:
            raise ValueError(f"No fmt chunk found in {path}")

        # Compute n_samples from data chunk if fact chunk was absent
        if n_samples is None:
            bytes_per_sample = max(bits_per_sample // 8, 1)
            block_align = bytes_per_sample * max(channels, 1)
            n_samples = data_size // block_align if block_align > 0 else 0

        duration_seconds = n_samples / sample_rate if sample_rate > 0 else 0.0
        fmt_name = format_names.get(format_tag, f"UNKNOWN_{format_tag}")
        subtype = f"{fmt_name}_{bits_per_sample}" if bits_per_sample else fmt_name

        return AudioInfo(
            n_samples=n_samples,
            sample_rate=sample_rate,
            channels=channels,
            duration_seconds=duration_seconds,
            format="WAV",
            subtype=subtype,
            bits_per_sample=bits_per_sample,
            source_path=path,
            extra={"format_tag": format_tag},
        )

    def _subtype_to_bits(self, subtype: str | None) -> int | None:
        """Convert soundfile subtype to bits per sample."""
        if subtype is None:
            return None

        bit_map = {
            "PCM_16": 16,
            "PCM_24": 24,
            "PCM_32": 32,
            "PCM_S8": 8,
            "PCM_U8": 8,
            "FLOAT": 32,
            "DOUBLE": 64,
        }
        return bit_map.get(subtype)

    # endregion

    # region Properties

    @property
    def audio_info(self) -> AudioInfo:
        """Return parsed audio metadata.

        Raises:
            RuntimeError: If no audio file has been loaded.
        """
        if self._audio_info is None:
            raise RuntimeError("No audio file loaded. Call load() first.")
        return self._audio_info

    @property
    def n_samples(self) -> int:
        """Total number of samples (frames) in the audio file."""
        return self.audio_info.n_samples

    @property
    def sample_rate(self) -> int:
        """Sample rate in Hz."""
        return self.audio_info.sample_rate

    @property
    def channels(self) -> int:
        """Number of audio channels."""
        return self.audio_info.channels

    @property
    def duration_seconds(self) -> float:
        """Duration in seconds."""
        return self.audio_info.duration_seconds

    @property
    def format(self) -> str:
        """Audio format (e.g., 'WAV', 'FLAC', 'MP3')."""
        return self.audio_info.format

    @property
    def source_path(self) -> Path | None:
        """Path to the loaded audio file."""
        return self._source_path

    # endregion

    # region Timeline Creation

    def create_timeline(
        self,
        uid: str | None = None,
        name: str | None = None,
        attach_cmap: bool = True,
    ) -> "DiscretePhysicalTimeline":
        """Create a DiscretePhysicalTimeline from the loaded audio.

        The timeline is created with:
        - unit=TimeUnit.samples
        - length=n_samples
        - Optionally, a SamplesToSeconds C-map for coordinate conversion

        Args:
            uid: Unique identifier for the timeline. If None, uses filename.
            name: Human-readable name. If None, uses filename.
            attach_cmap: If True, attach a SamplesToSeconds conversion map.

        Returns:
            A DiscretePhysicalTimeline representing the audio file.

        Raises:
            RuntimeError: If no audio file has been loaded.

        Examples:
            >>> loader = AudioLoader().load("song.wav")
            >>> timeline = loader.create_timeline()
            >>> timeline.unit
            <TimeUnit.samples: 'samples'>

            >>> # Convert sample coordinates to seconds
            >>> from timetoalign.core import TimeUnit
            >>> timeline.get_timestamp(44100).get_unit(TimeUnit.seconds)
            1.0
        """
        from timetoalign.core import NumberType, TimeUnit
        from timetoalign.timelines import DiscretePhysicalTimeline

        info = self.audio_info

        # Default uid/name from filename
        if uid is None and info.source_path is not None:
            uid = info.source_path.stem
        if name is None and info.source_path is not None:
            name = info.source_path.name

        # Create the timeline
        timeline = DiscretePhysicalTimeline(
            length=info.n_samples,
            unit=TimeUnit.samples,
            number_type=NumberType.int,
            uid=uid,
            name=name,
        )

        # Attach SamplesToSeconds C-map
        if attach_cmap:
            from timetoalign.maps import SamplesToSeconds

            cmap = SamplesToSeconds(sample_rate=info.sample_rate)
            timeline.add_conversion_map(cmap)

        # Store metadata on the timeline
        timeline._metadata = {
            "source_path": str(info.source_path) if info.source_path else None,
            "sample_rate": info.sample_rate,
            "channels": info.channels,
            "duration_seconds": info.duration_seconds,
            "format": info.format,
            "subtype": info.subtype,
            "bits_per_sample": info.bits_per_sample,
        }

        return timeline

    def create_samples_to_seconds_map(self) -> "SamplesToSeconds":
        """Create a SamplesToSeconds conversion map for this audio.

        Returns:
            A SamplesToSeconds C-map configured with this audio's sample rate.

        Raises:
            RuntimeError: If no audio file has been loaded.
        """
        from timetoalign.maps import SamplesToSeconds

        return SamplesToSeconds(sample_rate=self.audio_info.sample_rate)

    # endregion

    # region Convenience Methods

    @classmethod
    def from_file(cls, path: Path | str) -> "AudioLoader":
        """Load an audio file and return the loader (convenience constructor).

        Args:
            path: Path to the audio file.

        Returns:
            An AudioLoader with the file already loaded.

        Examples:
            >>> loader = AudioLoader.from_file("song.wav")
            >>> print(loader.duration_seconds)
        """
        loader = cls()
        loader.load(path)
        return loader

    # endregion

    def __repr__(self) -> str:
        if self._audio_info is None:
            return "AudioLoader(not loaded)"
        return (
            f"AudioLoader("
            f"samples={self._audio_info.n_samples}, "
            f"rate={self._audio_info.sample_rate}Hz, "
            f"duration={self._audio_info.duration_seconds:.2f}s, "
            f"format={self._audio_info.format})"
        )


# endregion
