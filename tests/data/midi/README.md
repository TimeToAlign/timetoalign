# MIDI Test Data Specimens

This directory contains real-world MIDI specimens for testing the `timetoalign` loaders.

Note: All Chopin Op.10 No.3 data (Vienna 4x22 dataset) has been moved to
`../vienna_1x22/`. See that directory for the full specimen collection including
22 performances, match files, MusicXML score, and ms3 ground truth TSVs.

## Directory Structure

- `performance/`: Unquantized performance data (e.g., live recordings, piano rolls).
- `score/`: Quantized score data (e.g., from notation software).

## Specimen Manifest

| Type | Filename | Description | Source |
|------|----------|-------------|--------|
| **Performance** | `supra_raw.mid` | Raw piano roll scan (hole punches) | Supra Rolls dataset |
| **Performance** | `supra_exp.mid` | Expressive piano roll (with velocities) | Supra Rolls dataset |
| **Performance** | `rachmaninoff_perf.mid` | Synchronized piano performance | Rachmaninoff Project |
| **Score** | `beethoven_op18.mid` | String Quartet Op.18 No.4 (4 parts) | OMR Groundtruth |
| **Score** | `rachmaninoff_piano.mid` | Piano score (quantized) | Rachmaninoff Project |
| **Score** | `rachmaninoff_orch.mid` | Orchestral score (quantized) | Rachmaninoff Project |
| **Score** | `beethoven_mtd.mid` | Beethoven Op.106 theme | Musical Themes Dataset |
