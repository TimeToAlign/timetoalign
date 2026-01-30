"""Tests for AudioLoader.

These tests verify that AudioLoader correctly:
1. Extracts metadata from audio files
2. Creates DiscretePhysicalTimelines with correct dimensions
3. Attaches appropriate SamplesToSeconds C-maps
4. Handles various audio formats and backends
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from timetoalign.core import NumberType, TimeUnit
from timetoalign.loader.physical import AudioInfo, AudioLoader
from timetoalign.maps import SamplesToSeconds
from timetoalign.timelines import DiscretePhysicalTimeline

if TYPE_CHECKING:
    pass


# region Test Fixtures


def create_wav_file(
    path: Path,
    n_samples: int = 44100,
    sample_rate: int = 44100,
    channels: int = 1,
    bits_per_sample: int = 16,
) -> Path:
    """Create a minimal WAV file for testing.

    Args:
        path: Path to write the WAV file.
        n_samples: Number of samples (frames).
        sample_rate: Sample rate in Hz.
        channels: Number of channels.
        bits_per_sample: Bit depth.

    Returns:
        Path to the created file.
    """
    bytes_per_sample = bits_per_sample // 8
    data_size = n_samples * channels * bytes_per_sample

    # WAV file structure
    with open(path, "wb") as f:
        # RIFF header
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_size))  # File size - 8
        f.write(b"WAVE")

        # fmt chunk
        f.write(b"fmt ")
        f.write(struct.pack("<I", 16))  # Chunk size
        f.write(struct.pack("<H", 1))  # Audio format (1 = PCM)
        f.write(struct.pack("<H", channels))
        f.write(struct.pack("<I", sample_rate))
        f.write(
            struct.pack("<I", sample_rate * channels * bytes_per_sample)
        )  # Byte rate
        f.write(struct.pack("<H", channels * bytes_per_sample))  # Block align
        f.write(struct.pack("<H", bits_per_sample))

        # data chunk
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        # Write silence (zeros)
        f.write(b"\x00" * data_size)

    return path


@pytest.fixture
def wav_file(tmp_path: Path) -> Path:
    """Create a test WAV file (1 second, 44.1kHz, mono, 16-bit)."""
    return create_wav_file(
        tmp_path / "test.wav",
        n_samples=44100,
        sample_rate=44100,
        channels=1,
        bits_per_sample=16,
    )


@pytest.fixture
def stereo_wav_file(tmp_path: Path) -> Path:
    """Create a stereo test WAV file (2 seconds, 48kHz, stereo, 24-bit)."""
    return create_wav_file(
        tmp_path / "stereo.wav",
        n_samples=96000,
        sample_rate=48000,
        channels=2,
        bits_per_sample=24,
    )


# endregion


# region AudioInfo Tests


class TestAudioInfo:
    """Tests for AudioInfo dataclass."""

    def test_basic_properties(self):
        """Test basic AudioInfo properties."""
        info = AudioInfo(
            n_samples=44100,
            sample_rate=44100,
            channels=1,
            duration_seconds=1.0,
            format="WAV",
        )

        assert info.n_samples == 44100
        assert info.sample_rate == 44100
        assert info.channels == 1
        assert info.duration_seconds == 1.0
        assert info.format == "WAV"

    def test_length_alias(self):
        """Test length_in_samples property is an alias for n_samples."""
        info = AudioInfo(
            n_samples=88200,
            sample_rate=44100,
            channels=2,
            duration_seconds=2.0,
            format="WAV",
        )

        assert info.length_in_samples == info.n_samples
        assert info.length_in_samples == 88200

    def test_mono_stereo_properties(self):
        """Test is_mono and is_stereo properties."""
        mono = AudioInfo(
            n_samples=1000,
            sample_rate=44100,
            channels=1,
            duration_seconds=0.02,
            format="WAV",
        )
        stereo = AudioInfo(
            n_samples=1000,
            sample_rate=44100,
            channels=2,
            duration_seconds=0.02,
            format="WAV",
        )
        surround = AudioInfo(
            n_samples=1000,
            sample_rate=44100,
            channels=6,
            duration_seconds=0.02,
            format="WAV",
        )

        assert mono.is_mono is True
        assert mono.is_stereo is False

        assert stereo.is_mono is False
        assert stereo.is_stereo is True

        assert surround.is_mono is False
        assert surround.is_stereo is False


# endregion


# region AudioLoader Basic Tests


class TestAudioLoaderBasic:
    """Basic tests for AudioLoader that don't require audio files."""

    def test_init(self):
        """Test AudioLoader initialization."""
        loader = AudioLoader()
        assert loader._audio_info is None
        assert loader._source_path is None

    def test_properties_before_load(self):
        """Test that properties raise before loading."""
        loader = AudioLoader()

        with pytest.raises(RuntimeError, match="No audio file loaded"):
            _ = loader.audio_info

        with pytest.raises(RuntimeError, match="No audio file loaded"):
            _ = loader.n_samples

    def test_file_not_found(self, tmp_path: Path):
        """Test error when file doesn't exist."""
        loader = AudioLoader()

        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            loader.load(tmp_path / "nonexistent.wav")

    def test_repr_before_load(self):
        """Test repr before loading."""
        loader = AudioLoader()
        assert repr(loader) == "AudioLoader(not loaded)"


# endregion


# region AudioLoader WAV Tests


class TestAudioLoaderWAV:
    """Tests for AudioLoader with WAV files using built-in wave module."""

    def test_load_wav(self, wav_file: Path):
        """Test loading a WAV file."""
        loader = AudioLoader()
        result = loader.load(wav_file)

        # Should return self for chaining
        assert result is loader

        # Check metadata
        assert loader.n_samples == 44100
        assert loader.sample_rate == 44100
        assert loader.channels == 1
        assert loader.duration_seconds == pytest.approx(1.0, rel=1e-6)
        assert loader.format == "WAV"
        assert loader.source_path == wav_file

    def test_load_stereo_wav(self, stereo_wav_file: Path):
        """Test loading a stereo WAV file."""
        loader = AudioLoader().load(stereo_wav_file)

        assert loader.n_samples == 96000
        assert loader.sample_rate == 48000
        assert loader.channels == 2
        assert loader.duration_seconds == pytest.approx(2.0, rel=1e-6)

    def test_from_file_convenience(self, wav_file: Path):
        """Test from_file class method."""
        loader = AudioLoader.from_file(wav_file)

        assert loader.n_samples == 44100
        assert loader.sample_rate == 44100

    def test_repr_after_load(self, wav_file: Path):
        """Test repr after loading."""
        loader = AudioLoader().load(wav_file)
        r = repr(loader)

        assert "samples=44100" in r
        assert "rate=44100Hz" in r
        assert "duration=1.00s" in r
        assert "format=WAV" in r

    def test_audio_info_access(self, wav_file: Path):
        """Test accessing the full AudioInfo object."""
        loader = AudioLoader().load(wav_file)
        info = loader.audio_info

        assert isinstance(info, AudioInfo)
        assert info.n_samples == 44100
        assert info.source_path == wav_file
        assert info.is_mono is True


# endregion


# region Timeline Creation Tests


class TestAudioLoaderTimeline:
    """Tests for creating timelines from AudioLoader."""

    def test_to_timeline_basic(self, wav_file: Path):
        """Test basic timeline creation."""
        loader = AudioLoader().load(wav_file)
        timeline = loader.to_timeline()

        assert isinstance(timeline, DiscretePhysicalTimeline)
        assert timeline.unit == TimeUnit.samples
        assert timeline.number_type == NumberType.int
        assert timeline.length.value == 44100

    def test_to_timeline_with_uid(self, wav_file: Path):
        """Test timeline creation with custom uid."""
        loader = AudioLoader().load(wav_file)
        timeline = loader.to_timeline(uid="my_audio", name="My Audio File")

        assert timeline.id == "my_audio"
        assert timeline.name == "My Audio File"

    def test_to_timeline_default_uid_from_filename(self, wav_file: Path):
        """Test that uid defaults to filename stem."""
        loader = AudioLoader().load(wav_file)
        timeline = loader.to_timeline()

        assert timeline.id == "test"  # From "test.wav"
        assert timeline.name == "test.wav"

    def test_to_timeline_with_cmap(self, wav_file: Path):
        """Test timeline creation with SamplesToSeconds C-map."""
        loader = AudioLoader().load(wav_file)
        timeline = loader.to_timeline(attach_cmap=True)

        # Should have a C-map to seconds
        cmap = timeline.get_conversion_map(TimeUnit.seconds)
        assert cmap is not None
        assert isinstance(cmap, SamplesToSeconds)

        # Test conversion
        result = cmap(44100)
        assert result == pytest.approx(1.0, rel=1e-6)

    def test_to_timeline_without_cmap(self, wav_file: Path):
        """Test timeline creation without C-map attachment."""
        loader = AudioLoader().load(wav_file)
        timeline = loader.to_timeline(attach_cmap=False)

        # Should NOT have a C-map to seconds
        cmap = timeline.get_conversion_map(TimeUnit.seconds)
        assert cmap is None

    def test_to_timeline_metadata(self, wav_file: Path):
        """Test that timeline has metadata attached."""
        loader = AudioLoader().load(wav_file)
        timeline = loader.to_timeline()

        assert hasattr(timeline, "_metadata")
        assert timeline._metadata["sample_rate"] == 44100
        assert timeline._metadata["channels"] == 1
        assert timeline._metadata["format"] == "WAV"

    def test_create_samples_to_seconds_map(self, wav_file: Path):
        """Test creating a standalone C-map."""
        loader = AudioLoader().load(wav_file)
        cmap = loader.create_samples_to_seconds_map()

        assert isinstance(cmap, SamplesToSeconds)
        assert cmap(44100) == pytest.approx(1.0, rel=1e-6)
        assert cmap(22050) == pytest.approx(0.5, rel=1e-6)


# endregion


# region Integration Tests


class TestAudioLoaderIntegration:
    """Integration tests for AudioLoader with the TTA framework."""

    def test_timeline_coordinate_conversion(self, wav_file: Path):
        """Test coordinate conversion on audio timeline."""
        loader = AudioLoader().load(wav_file)
        timeline = loader.to_timeline()

        # The timeline should be able to convert samples to seconds
        # This tests integration with the C-map system
        half_sample = 22050
        result = timeline.convert_to(half_sample, TimeUnit.seconds)

        assert result == pytest.approx(0.5, rel=1e-6)

    def test_timeline_used_with_metrical_grid(self, stereo_wav_file: Path):
        """Test that audio timeline works with ContinuousPhysicalTimeline workflow."""
        # This tests that the discrete audio timeline can be used alongside
        # continuous physical timelines in the same alignment workflow
        from timetoalign.timelines import ContinuousPhysicalTimeline

        loader = AudioLoader().load(stereo_wav_file)
        discrete_tl = loader.to_timeline(uid="audio_samples")

        # Create a continuous timeline representing the same duration
        continuous_tl = ContinuousPhysicalTimeline(
            length=loader.duration_seconds,
            unit=TimeUnit.seconds,
            uid="audio_seconds",
        )

        # Both should represent the same duration
        assert discrete_tl.length.value == 96000  # samples
        assert continuous_tl.length.value == 2.0  # seconds

        # Convert discrete length to seconds via C-map
        duration_from_discrete = discrete_tl.convert_to(
            discrete_tl.length.value, TimeUnit.seconds
        )
        assert duration_from_discrete == pytest.approx(2.0, rel=1e-6)


# endregion


# region Edge Cases


class TestAudioLoaderEdgeCases:
    """Edge case tests for AudioLoader."""

    def test_very_short_audio(self, tmp_path: Path):
        """Test loading a very short audio file (10 samples)."""
        wav_path = create_wav_file(
            tmp_path / "short.wav",
            n_samples=10,
            sample_rate=44100,
            channels=1,
        )

        loader = AudioLoader().load(wav_path)
        assert loader.n_samples == 10
        assert loader.duration_seconds == pytest.approx(10 / 44100, rel=1e-6)

    def test_high_sample_rate(self, tmp_path: Path):
        """Test loading audio with high sample rate (192kHz)."""
        wav_path = create_wav_file(
            tmp_path / "highres.wav",
            n_samples=192000,
            sample_rate=192000,
            channels=2,
            bits_per_sample=24,
        )

        loader = AudioLoader().load(wav_path)
        assert loader.sample_rate == 192000
        assert loader.duration_seconds == pytest.approx(1.0, rel=1e-6)

    def test_method_chaining(self, wav_file: Path):
        """Test that load() returns self for method chaining."""
        timeline = AudioLoader().load(wav_file).to_timeline()
        assert isinstance(timeline, DiscretePhysicalTimeline)


# endregion
