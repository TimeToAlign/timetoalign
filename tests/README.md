# Test suite

Run `pytest` for the everyday development loop. The default lane runs in
parallel through pytest-xdist and does not collect coverage.

Long-running corpus-scale integration tests carry the `slow` marker and are
skipped by default. Run `pytest --runslow` to execute the complete suite.
The complete suite is required before any release and before changes to
loaders, unfolding, or alignment internals.

Coverage is opt-in:

```text
pytest --cov=timetoalign --cov-report=term-missing
```

To run one test file, use for example:

```text
pytest tests/path/to/test_file.py
```

## Layout

Tests live in a directory per subject area, each with a README documenting
what its assertions check and why those are the right values.

| Path | Subject |
|---|---|
| `alignment/` | Claims, graphs, match lines, warp maps, bundles |
| `core/` | Scalars, fields, number storage, stamps, display |
| `display/` | Shared rendering helpers |
| `integration/` | End-to-end corpus walkthroughs |
| `loader/` | Every loader family, and loader parity |
| `maps/` | Conversion maps |
| `storage/` | Event storage and schemas |
| `timelines/` | Timelines, nesting, regions, flow, unfolding |

Two suites sit at the top level rather than in any of them:

| File | Subject |
|---|---|
| `test_number_type_preservation.py` | A declared `number_type` is preserved at every coordinate boundary, whichever object answers the query. Its validation logic is documented in `core/README.md` under "Number type is preserved everywhere". |
| `test_stamp_retrieval_surface.py` | Every stamp-producing object answers the same four precise questions under the same four names, and every table speaks the same two output formats. Its validation logic is documented in `core/README.md` under "One stamp surface, one table surface". |

They stay at the top level because they are cross-cutting rules rather than
subject areas: each asserts the same property of timelines, groups, bundles,
maps and stamps together, and filing either under any one of them would
invite the next person to check only that one.

`helpers.py` beside them holds the one utility both need: `table_column`,
which reads a timestamp-table column through the library's own decoding
boundary. Timestamp-table cells are coordinate structs, so a bare
`column.to_pylist()` yields dicts rather than positions; tests read what a
user reads.
