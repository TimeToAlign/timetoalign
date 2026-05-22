# Loader tests

This directory tests the loader package end-to-end, covering all formats
(``tabular/``, ``score/``, ``midi/``, ``graphical/``, ``format/``,
``physical/``, ``paths/``), the ``EventStore`` and ``EventData`` machinery,
and the shared loader infrastructure (base classes, matchfiles, schemas,
bundles, error handling).

## Categories

| File / Subdirectory | What it validates |
|---------------------|-------------------|
| `test_loader.py` | Generic loader smoke tests and contract checks |
| `test_base_loaders.py` | The `EventLoader` / `ManifestLoader` / `AlignmentLoader` ABCs |
| `test_bundle.py` | `AlignmentBundle` produced by alignment loaders |
| `test_error_handling.py` | Faulty-input behaviour across loaders |
| `test_interval_policy.py` | Half-open interval semantics on event ingestion |
| `test_matchfile_loader.py` | `MatchfileLoader` parity against gold standard |
| `test_parsing.py` | Format-agnostic parsing helpers |
| `test_schema.py` | `TableSchema` and field-spec resolution |
| `test_store.py` | `EventStore` low-level operations |
| `test_tilia_loader.py` | `TiliaJsonLoader` round-trip |
| `test_get_field_by_class.py` | `EventData.get_field(<SemanticField subclass>)` class-based discovery — regression test ensuring that `events.get_field(PitchField)` discovers struct fields even when the loader has not injected `b"timetoalign"` metadata onto the field. |
| `tabular/` | CSV / TSV / Parquet loader specifics |
| `score/` | Music-notation loaders (Ms3, music21, Partitura) |
| `midi/` | Score and performance MIDI loaders |
| `graphical/` | PDF / image loaders |
| `format/` | Cross-format loaders (JSON, XML, TTL) |
| `physical/` | Audio loaders and time-coordinate ingestion |
| `paths/` | Path resolution helpers |

## Data conventions

Tests resolve corpus paths via ``timetoalign.testdata.ensure_data("<corpus>")``
(see ``tests/data/README.md``).  Hardcoded relative ``Path("tests/data/...")``
constants are forbidden — they break under ``jupytext --execute`` and in CI
container layouts.  See ``CLAUDE.md`` "Test Data Provisioning" for the
binding contract.
