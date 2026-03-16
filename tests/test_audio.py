import math
import struct
from apps.server.config import (
    INPUT_SAMPLE_RATE, OUTPUT_SAMPLE_RATE, INPUT_CHUNK_BYTES,
    INPUT_CHUNK_SAMPLES, BYTES_PER_SAMPLE, INPUT_MIME_TYPE,
)


def generate_pcm_tone(freq_hz: float, duration_ms: int, sample_rate: int) -> bytes:
    """Generate a PCM sine wave tone as 16-bit signed LE bytes."""
    num_samples = int(sample_rate * duration_ms / 1000)
    samples = []
    for i in range(num_samples):
        t = i / sample_rate
        value = math.sin(2 * math.pi * freq_hz * t)
        sample = int(value * 32767)
        samples.append(sample)
    return struct.pack(f"<{len(samples)}h", *samples)


def test_input_chunk_size():
    """100ms at 16kHz 16-bit mono = 3200 bytes."""
    chunk = generate_pcm_tone(440, 100, INPUT_SAMPLE_RATE)
    assert len(chunk) == INPUT_CHUNK_BYTES == 3200


def test_output_chunk_size():
    """100ms at 24kHz 16-bit mono = 4800 bytes."""
    chunk = generate_pcm_tone(440, 100, OUTPUT_SAMPLE_RATE)
    assert len(chunk) == 4800


def test_pcm_16bit_roundtrip():
    """Values survive pack/unpack as 16-bit signed LE."""
    original = [0, 32767, -32768, 1000, -1000]
    packed = struct.pack(f"<{len(original)}h", *original)
    unpacked = struct.unpack(f"<{len(original)}h", packed)
    assert list(unpacked) == original


def test_chunk_alignment():
    """Chunk byte count must be even (2 bytes per sample)."""
    assert INPUT_CHUNK_BYTES % BYTES_PER_SAMPLE == 0
    assert INPUT_CHUNK_BYTES // BYTES_PER_SAMPLE == INPUT_CHUNK_SAMPLES


def test_silence_is_zeros():
    """A silent chunk is all zero bytes."""
    silence = b'\x00' * INPUT_CHUNK_BYTES
    samples = struct.unpack(f"<{INPUT_CHUNK_SAMPLES}h", silence)
    assert all(s == 0 for s in samples)


def test_mime_type_format():
    assert INPUT_MIME_TYPE == "audio/pcm;rate=16000"
    assert "rate=16000" in INPUT_MIME_TYPE


def test_generate_pcm_tone():
    """Generated tone has correct length and non-zero amplitude."""
    tone = generate_pcm_tone(440, 100, INPUT_SAMPLE_RATE)
    assert len(tone) == INPUT_CHUNK_BYTES
    samples = struct.unpack(f"<{INPUT_CHUNK_SAMPLES}h", tone)
    assert max(abs(s) for s in samples) > 0
    # Verify it's a valid waveform (crosses zero)
    has_positive = any(s > 0 for s in samples)
    has_negative = any(s < 0 for s in samples)
    assert has_positive and has_negative
