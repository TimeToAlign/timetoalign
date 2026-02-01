# Out-of-the-flow Experience

Music encoding edge case for testing purposes. Probably none of the existing playback or
unfolding engines would handle this as a human would. For us, it the flow is largely uncontroversial,
only for MC 10 (MN 6) it has to be decided whether it is repeated the second time, too.

The canonical flow is encoded in the `next` column which has as many MC values as that MC-unit
is played. In other words, every time a measure is visited, the first element is consumed.
-1 marks the last MC unit in the flow.

| mc | mn | volta | barline | repeats | markers | jump_bwd | jump_fwd | play_until | next | comment |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 0 |  |  | firstMeasure |  |  |  |  | 2, 2, 2 |  |
| 2 | 1 |  |  |  |  |  |  |  | 3, 3, 3 |  |
| 3 | 2 |  |  | end |  |  |  |  | 1, 4, 4 | D.C.: senza rep. |
| 4 | 2 |  |  | start |  |  |  |  | 5, 6, 7 | to volta 1, 2, 3 |
| 5 | 2 | 1 |  | end |  |  |  |  | 4 |  |
| 6 | 2 | 2 | double |  |  |  |  |  | 8 |  |
| 7 | 3 | 3 | end |  | fine |  |  |  | -1 |  |
| 8 | 4 |  |  | end |  |  |  |  | 8, 9 | repeats although start repeat is not printed |
| 9 | 5 |  |  | start | segno & coda |  |  |  | 10, 10, 13 | leap to coda only after the D.S. leap |
| 10 | 6 |  |  | startend |  |  |  |  | 10, 11, 10, 11 | repeated bar nested in the middle of repeated 3 bars: here, repeated both times |
| 11 | 7 |  |  | end |  |  |  |  | 9, 12 |  |
| 12 | 8 |  | end |  |  | segno | codab | coda | 9 |  |
| 13 | 9 |  |  |  | codab |  |  |  | 14, 15 |  |
| 14 | 9 | 1 |  | end |  |  |  |  | 13 |  |
| 15 | 10 | 2 |  | lastMeasure |  | start |  | fine | 1 |  |

Three unfolding paths are encoded in `out_of_the_flow_experience-unfoldings.measures.ods` table:

* `mc_canonical`: the suggested path
* `mc_ms3`: unfolding achieved using the `ms3` library (corresponds to the unfolded measures table
  `flow_only/out_of_the_flow_experience-flow_only_unfolded.measures.tsv`)
* `mc_mp3`: problematic unfolding achieved by MuseScore 3, as present in the MP3 file
  created using MuseScore 3.6.2


## Overview
|                file_name                 |measures|labels|
|------------------------------------------|-------:|-----:|
|out_of_the_flow_experience-flow_only      |      10|     0|
|out_of_the_flow_experience-full           |      10|     0|
|out_of_the_flow_experience-polyrhythm_only|       9|     0|


*Overview table automatically updated using [ms3](https://ms3.readthedocs.io/).*
