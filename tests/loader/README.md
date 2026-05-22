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
| `test_mixins.py` | `EventData` field-access mixins — three-strategy field discovery (metadata, default-column, shape-based `matches_pa_field`), `has_field`, `get_field`, `get_fields`, `get_raw`, and the convenience accessors (`get_pitch_field`, `get_harmony_field`). |
| `test_mixins_wp3.py` | WP3 dispatch additions on `SemanticFieldAccessMixin` — `get_field(ScalarClass)` pydantic-scalar dispatch, `IdCoordinate` vs `Coordinate` discrimination via metadata (`matches_pa_field` rejection contracts), `MultipleFieldsError` on ambiguity + `name=` resolution, and `get_fields_satisfying(ProtocolClass)` Protocol-based grouping (covering `GenericPitchLike` and the new `TimeScalarLike`). |
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
