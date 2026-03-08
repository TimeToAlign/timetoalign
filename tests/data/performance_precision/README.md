

Performance Precision
================

## Software Instructions
A more comprehensive README (including instructions about how to use the tool) is at: https://github.com/yucongj/CAAMP

## Performance Analysis Example

The data are from the use case example in this published paper: [https://zenodo.org/records/15838699](https://zenodo.org/records/15838699). Note that the recordings are copyrighted (from YouTube), so shouldn't be shared publicly.

In the folder called "PerformancePrecision", there are three subfolders: one contains the scores (currently just *Chopin Nocturne Op. 9 No. 2*), another contains the recordings (currently seven recordings of the same Chopin piece), and the other contains the exported alignmment files which can be loaded back into the software representing the audio-to-score alignment information.

Each recording has three alignment files, each at the bar, the beat, and the note level. The alignment file format is straight-forward: the first column is the score time (MEASURE + POSITION WITHIN THE MEASURE) and the second column is the onset timestamp. Notes within the same chord are treated as one "event" and occupies only one row in the file.

The users can load multiple recordings (of the same piece) to compare their tempo curves.

Connection to parangonar (testing in progress): parangonar generates alignment files that can be imported into Performance Precision.
