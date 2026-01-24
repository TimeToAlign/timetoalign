# TimeToAlign

A Python library for representing and aligning musical timelines.

## Installation

```bash
pip install timetoalign
```

## Quick Start

```python
import timetoalign as tta

# Create coordinates
c1 = tta.Coordinate(120, tta.TimeUnit.TICKS)
c2 = tta.Coordinate(1.5, tta.TimeUnit.SECONDS)

# Work with scoped IDs
sid = tta.ScopedId.parse("midi:n42")
print(sid.scope)  # "midi"
print(sid.local)  # "n42"
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
