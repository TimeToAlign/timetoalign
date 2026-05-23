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
| `test_mixins_wp3.py` | Dispatch additions on `SemanticFieldAccessMixin` — `get_field(ScalarClass)` pydantic-scalar dispatch, `IdCoordinate` vs `Coordinate` discrimination via metadata (`matches_pa_field` rejection contracts), `MultipleFieldsError` on ambiguity + `name=` resolution, and `get_fields_satisfying(ProtocolClass)` Protocol-based grouping (covering `GenericPitchLike` and `TimeScalarLike`). |
| `test_column_specs.py` | The `FieldSpec` hierarchy + `resolve_field_spec` universal-resolution table. Each leaf spec (`IntFieldSpec`, `FloatFieldSpec`, `StringFieldSpec`, `RationalFieldSpec`) is exercised on representative source arrays (clean, type-coerced, and rational-string forms); `CompositeFieldSpec` (separator + regex strategies) and `FractionFieldSpec` (raw + semantic via `unit=`) are exercised end-to-end. Resolution table assertions: every entry (Python type, `pa.DataType`, raw `DataField` subclass, `SemanticField` subclass, callable) routes to the correct `FieldSpec` instance. |
| `test_field_specs.py` | Step 2 (`field_specs`) blueprint resolution. Builds a fixture `pa.Table` and a `TabularLoader` subclass with `field_specs = [...]`, verifies that each blueprint matches its declared `source_fields=` entry, that the resulting column receives `b"timetoalign"` metadata (`field_type` = paired class name), that atomic source columns are packed into single-field structs matching the target `pa_schema`, and that unresolvable references raise `KeyError`. Exercises the two currently-supported `source_fields=` shorthands (string for single-source promotion; explicit dict for multi-sub-field mapping) and the negative cases (list shorthand rejected by `resolve_source_fields` today; live-mode SemanticField instances rejected; multi-source dict spec raises `NotImplementedError` at loader-materialisation time). |
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
