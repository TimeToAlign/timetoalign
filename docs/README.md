# TimeToAlign! Documentation

## Tutorial Notebooks

The `notebooks/` directory contains the tutorial series for the TimeToAlign! library.
Each notebook is a jupytext-paired `py:percent` file. The `.py` file is the
git-tracked source of truth; `.ipynb` files are gitignored and regenerated via
`jupytext --sync`.

### Notebook Overview

| #  | Notebook                    | Purpose                                   | Key Benefit Demonstrated                                          | Status          |
|----|-----------------------------|--------------------------------------------|-------------------------------------------------------------------|-----------------|
| 00 | `00_motivation`             | Why alignment matters                      | Problem statement and solution vision                             | Complete        |
| 01 | `01_core_concepts`          | Domains, Timelines, Coordinates            | Unified representation across domains                             | Complete        |
| 02 | `02_loading_data`           | Loaders, EventStores                       | Format-agnostic data ingestion                                    | Complete        |
| 02a| `02a_tabular_loaders`       | Custom loaders, CoordinateField            | Advanced loader configuration                                     | Complete        |
| 03 | `03_conversion_maps`        | Unit transformations                       | Seamless coordinate conversion                                    | Complete        |
| 04 | `04_building_timelines`     | Events, Segments, Hierarchy                | Structured temporal representation                                | Complete        |
| 05 | `05_timestamps`             | Cross-section views                        | Querying timeline hierarchies                                     | Complete        |
| 06 | `06_graphical_timelines`    | TimeAxisPath, images                       | Visual analysis with time                                         | Complete        |
| 07 | `07_alignment_basics`       | TimelineGroup, PerfectAlignment            | Coordinate transfer between timelines                             | Complete        |
| 08 | `08_supra_piano_roll`       | Complete alignment workflow                | `from_file()`, named C-Maps, group timestamps                     | Complete        |
| 09 | `09_beat_grids`             | Metrical structure                         | Measure/beat queries via BeatGrid                                 | Complete        |
| 10 | `10_beethoven_multimodal`   | **Figure 3 acid test**                     | AlignmentBundle, FlowMap, OMR, 16+ timelines, 3 domains          | Infra Complete  |

### Manuscript Relevance

The tutorial notebooks serve as runnable proofs of concept for examples in the
TISMIR manuscript:

| Paper Example                     | Notebook                    | Status          |
|-----------------------------------|-----------------------------|-----------------|
| Ex. 1: Thoresen graphical analysis| `06_graphical_timelines`    | Complete        |
| Ex. 2: SUPRA piano roll           | `08_supra_piano_roll`       | Complete        |
| Ex. 3: Beethoven multimodal       | `10_beethoven_multimodal`   | Infra Complete  |
| Ex. 4: Hendrix song genesis       | (to be created or referenced)| Pending        |

### Data Dependencies

All notebooks source their data from within the `timetoalign/` package tree:

| Data Location                         | Used By                                       |
|---------------------------------------|-----------------------------------------------|
| `tests/data/midi/score/`              | 00, 02, 04                                    |
| `tests/data/score/beethoven_woo71/`   | 02a                                           |
| `tests/data/score/beethoven_op18-4iv_multimodal/` | 09, 10                            |
| `tests/data/audio/`                   | 09                                            |
| `tests/data/supra/`                   | 08                                            |
| `tests/alignment/data/thoresen/`      | 02a, 07                                       |

No notebook should reference the `dashboard/` repository or any path outside
the `timetoalign/` package root.

### Workflow

1. Edit the `.py` file (percent format with `# %%` cell markers)
2. Run `jupytext --sync <notebook>.py` to generate/update the paired `.ipynb`
3. Commit only the `.py` file
