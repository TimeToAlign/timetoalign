# Corrupt Test Fixtures

This directory contains intentionally malformed files for testing error handling.

## Files

| File | Description | Expected Error |
|------|-------------|----------------|
| `invalid_header.mid` | Text file with .mid extension | Invalid MIDI header |
| `truncated.mid` | MIDI header bytes but truncated | Unexpected EOF |
| `empty.mid` | Zero-byte file | Empty/invalid file |
| `malformed.musicxml` | XML with unclosed tags | XML parsing error |
| `wrong_schema.tsv` | TSV with wrong columns | Schema/column mismatch |

## Purpose

These files test that loaders:
1. Detect corrupt input gracefully
2. Raise appropriate exceptions with helpful messages
3. Don't crash or hang on malformed data
4. Don't silently produce incorrect results

## Usage

```python
def test_corrupt_midi_raises():
    loader = PerformanceMidiLoader()
    with pytest.raises((ValueError, IOError)):
        loader.load(CORRUPT_DIR / "invalid_header.mid")
```
