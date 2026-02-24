# TimeToAlign!

A Python library for representing and aligning musical timelines.

## Installation

```bash
git clone git@github.com:TimeToAlign/timetoalign.git
cd timetoalign
pip install -e ".[dev]"
```

## Quick Start

```python
import timetoalign as tta

# Create a 60-second audio timeline
audio = tta.ContinuousPhysicalTimeline(length=60.0, uid="audio", name="Piano Recording")

# Add beats and notes -- IDs and temporal_type are inferred automatically
audio.add_events([
    {"event_type": "Beat", "instant": 0.0},
    {"event_type": "Beat", "instant": 0.5},
    {"event_type": "Beat", "instant": 1.0},
    {"event_type": "Note", "start": 0.0, "end": 0.5},
    {"event_type": "Note", "start": 8.0, "end": 12.0},   # spans Intro -> Verse
])

# Nest children (sections of the same recording)
intro  = audio.create_child(length=10.0, offset=0.0,  uid="intro",  name="Intro")
verse  = audio.create_child(length=20.0, offset=10.0, uid="verse",  name="Verse")
chorus = audio.create_child(length=15.0, offset=30.0, uid="chorus", name="Chorus")

# Attach ConversionMaps (seconds -> milliseconds, seconds -> samples at 48 kHz)
audio.add_conversion_map(tta.ScalarMap(scalar=1000, source_unit="seconds", target_unit="milliseconds"))
audio.add_conversion_map(tta.SecondsToSamples(sample_rate=48000))

# The diagram shows the hierarchy at a glance
print(audio.diagram())
```

```
ContinuousPhysicalTimeline[audio] (5 events, 3 children)
                      0 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ 60 seconds
  ├─ Intro            0 ~~~~~                               10
  ├─ Verse           10      ~~~~~~~~~~~~                   30
  └─ Chorus          30                  ~~~~~~~~~          45
```

```python
# A TimeStamp is a cross-section through the entire hierarchy at a given coordinate.
# Only children whose span covers the coordinate appear:
ts = audio.get_timestamp(25.0)
print(ts)
```

```
TimeStamp @25 seconds
  audio         25 seconds
  verse         15 seconds
  milliseconds  25000
  samples       1200000
```

```python
# A TimeIntervalStamp gives the cross-section for a [start, end) range.
# The note at [8, 12) straddles Intro [0, 10) and Verse [10, 30):
# its start falls in Intro, its end in Verse.
tis = audio.get_interval_stamp(8.0, 12.0)
print(tis)
```

```
TimeIntervalStamp [8, 12) seconds
                 start     end
  audio              8      12 seconds
  intro              8       - seconds
  verse              -       2 seconds
  milliseconds    8000   12000
  samples       384000  576000
```

## Tutorial Notebooks

The `docs/notebooks/` directory contains Jupytext percent-script notebooks
covering the library from first principles to full alignment workflows.
To run them, install the `tutorial` extra (which pulls in Jupytext, Jupyter,
and every optional loader dependency the tutorials use):

```bash
cd tta/timetoalign
pip install -e ".[tutorial]"
```

Then generate the paired `.ipynb` files and launch Jupyter:

```bash
jupytext --sync docs/notebooks/*.py
jupyter notebook docs/notebooks/
```

## Development

```bash
# Run the test suite
pytest

# Run linting / pre-commit hooks
tox -e lint
```

## Glossary

### Gemini

| Term                | Definition                                                                                                                                                                                            |
|---------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| AlignmentAnchor     | A set of TimeStamps corresponding to matched events, representing their temporal equivalence across timelines. From a Match of TimeIntervalEvents, we derive a StartAnchor and EndAnchor.             |
| AlignmentBundle     | The primary container object in the implementation that manages a collection of timelines, their groupings, and the coordination of transfers between them.                                           |
| BeatGrid            | A specialized \textit{ContinuousLogicalTimeline} representing metrical structure (measures and beats) using quarter notes as the underlying coordinate unit.                                          |
| Break               | A control event that voids contiguity at its Instant. TimeIntervals cannot span a Break, and Breaks cannot be inserted into existing TimeIntervals.                                                   |
| ChainMap            | A MultiMap that applies multiple ConversionMaps in sequence, creating a conversion path from source to target unit.                                                                                   |
| Child               | A timeline nested within a parent timeline, sharing the same measuring unit. Children are locked upon insertion to prevent side effects from modifications.                                           |
| CombinationMap      | A MultiMap yielding outputs from multiple ConversionMaps simultaneously (e.g., $(x, y)$ coordinate pairs).                                                                                            |
| Commensurable       | Two timelines are commensurable when connected by a Match path or ConversionMap chain, enabling coordinate translation between them.                                                                  |
| ConcatenationMap    | A MultiMap combining bounded ConversionMaps such that each coordinate region is handled by a specific map. Implemented as \textit{PiecewiseMap}.                                                      |
| Contiguity          | A TimeInterval is contiguous if it monotonically spans all coordinates between its start and end. An Instant is contiguous with a TimeInterval if it is synchronous with its EndInstant.              |
| Control Event       | An event affecting flow control: either a Break (voiding contiguity) or a Jump (creating new contiguity).                                                                                             |
| ConversionMap       | A function mapping any coordinate to at most one value (another coordinate, specifier, or constant). Also called C-map.                                                                               |
| Coordinate          | A position on a timeline, expressed as the distance from the origin in the timeline's measuring unit.                                                                                                 |
| Discrete/Continuous | A timeline is discrete when coordinates exist only at discrete points (e.g., pixels, samples); continuous otherwise (e.g., seconds, quarters).                                                        |
| Domain              | One of three temporal categories: Graphical (visual/spatial), Logical (symbolic/musical), or Physical (audio/sound).                                                                                  |
| Event               | Anything associated with a timeline via Instants. An InstantEvent has zero duration; a TimeIntervalEvent has duration defined by start and end coordinates.                                           |
| FlowControlType     | A taxonomy of control events distinguishing between structural markers (e.g., \textit{repeat\_start}, \textit{double\_barline}) and jump instructions (e.g., \textit{dal\_segno}, \textit{to\_coda}). |
| GroupTimestamp      | A view object representing a synchronized instant across all commensurable timelines within a \textit{TimelineGroup}.                                                                                 |
| IdCoordinate        | A coordinate specification that explicitly includes the unique identifier of the timeline to which it belongs, preventing ambiguity in multi-timeline contexts.                                       |
| Instant             | Associates a coordinate with a signification such as \enquote{start of event $e$}. Instants sharing a coordinate are synchronous.                                                                     |
| InterpolationMap    | A \textit{ConversionMap} that performs coordinate conversion via linear interpolation between a set of known correspondence points.                                                                   |
| InverseMap          | The reverse transformation of a bijective ConversionMap.                                                                                                                                              |
| Jump                | A control event with JumpFrom and JumpTo Instants. When active, makes events at JumpTo contiguous with those ending at JumpFrom (e.g., repeats, \textit{dal segno}).                                  |
| Length              | The distance between a timeline's origin and its last Instant. A locked timeline cannot extend its length.                                                                                            |
| LinearMap           | A \textit{ConversionMap} implementing an affine transformation ($f(x) = ax + b$). Includes \textit{ScalarMap} ($b=0$) and \textit{ShiftMap} ($a=1$) as special cases.                                 |
| Match               | A claim---issued by a human or algorithmic agent---that events from disparate timelines are synchronous or equivalent, with associated metadata (agent, criteria, certainty).                         |
| MatchClaim          | The implementation class for a \textit{Match}, representing a specific claim of equivalence between two events, comprising one (instant) or two (interval) \textit{AlignmentAnchor}s.                 |
| MatchLine           | A linked list of Match objects preserving their order, enabling selection and alignment of temporal correspondences.                                                                                  |
| MatchMetadata       | Structured provenance information attached to a \textit{MatchClaim}, recording the agent, decision criteria, and certainty level of the match.                                                        |
| MatchPath           | A graph traversal connecting matched events across multiple timelines (e.g., $A \rightarrow B \rightarrow C$).                                                                                        |
| MetricMap           | A specialized \textit{ConversionMap} that handles complex metrical conversions (e.g., quarter notes to measure count) accounting for time signatures and anacrusis.                                   |
| MultiMap            | An umbrella term for composed ConversionMaps (ChainMap, CombinationMap, ConcatenationMap).                                                                                                            |
| Origin              | The zero coordinate of a timeline, from which all positions are measured.                                                                                                                             |
| PiecewiseMap        | The implementation of a \textit{ConcatenationMap}, applying different sub-maps to disjoint coordinate intervals.                                                                                      |
| Region              | A named part of a timeline defined by a TimeInterval (e.g., \enquote{Chorus}, \enquote{Verse}). Regions are not timelines and cannot hold events or maps directly.                                    |
| RotationMap         | A \textit{ConversionMap} that implements periodic or cyclic transformations using modular arithmetic.                                                                                                 |
| Segment             | A Child timeline that is contiguous with its siblings. A SegmentLine is a parent containing only contiguous Segments.                                                                                 |
| Synchrony           | Strict synchrony: Instants sharing identical coordinates. Pragmatic synchrony: Instants binned together based on a threshold (e.g., for quantisation).                                                |
| TimeInterval        | Defined by a StartInstant and EndInstant; left-inclusive and right-exclusive $[s, e)$. The EndInstant's coordinate must be $\geq$ the StartInstant's.                                                 |
| Timeline            | A positive coordinate axis minimally defined by its origin and measuring unit. Accommodates events and potentially Children.                                                                          |
| TimelineGroup       | A container for a set of commensurable timelines that are bijectively mapped to each other (e.g., via linear interpolation) and share a common timestamp table.                                       |
| TimeStamp           | A cross-section through a timeline hierarchy, comprising the root coordinate, synchronous Child coordinates, and all ConversionMap results.                                                           |
| TraversalMap        | A sequence of TimeIntervals representing a specific traversal path through a timeline (handling Jumps and repeats). Also called T-map.                                                                |
| WarpMap             | A derived timeline where coordinates are re-adjusted based on AlignmentAnchors to align with another timeline.                                                                                        |

### Claude

| Term                | Definition                                                                                                                                                                                |
|---------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| AlignmentAnchor     | A set of TimeStamps corresponding to matched events, representing their temporal equivalence across timelines. From a Match of TimeIntervalEvents, we derive a StartAnchor and EndAnchor. |
| Break               | A control event that voids contiguity at its Instant. TimeIntervals cannot span a Break, and Breaks cannot be inserted into existing TimeIntervals.                                       |
| Child               | A timeline nested within a parent timeline, sharing the same measuring unit. Children are locked upon insertion to prevent side effects from modifications.                               |
| ChainMap            | A MultiMap that applies multiple ConversionMaps in sequence, creating a conversion path from source to target unit.                                                                       |
| CombinationMap      | A MultiMap yielding outputs from multiple ConversionMaps simultaneously (e.g., $(x, y)$ coordinate pairs).                                                                                |
| Commensurable       | Two timelines are commensurable when connected by a Match path or ConversionMap chain, enabling coordinate translation between them.                                                      |
| ConcatenationMap    | A MultiMap combining bounded ConversionMaps such that each coordinate region is handled by a specific map.                                                                                |
| Contiguity          | A TimeInterval is contiguous if it monotonically spans all coordinates between its start and end. An Instant is contiguous with a TimeInterval if it is synchronous with its EndInstant.  |
| Control Event       | An event affecting flow control: either a Break (voiding contiguity) or a Jump (creating new contiguity).                                                                                 |
| ConversionMap       | A function mapping any coordinate to at most one value (another coordinate, specifier, or constant). Also called C-map.                                                                   |
| Coordinate          | A position on a timeline, expressed as the distance from the origin in the timeline's measuring unit.                                                                                     |
| Discrete/Continuous | A timeline is discrete when coordinates exist only at discrete points (e.g., pixels, samples); continuous otherwise (e.g., seconds, quarters).                                            |
| Domain              | One of three temporal categories: Graphical (visual/spatial), Logical (symbolic/musical), or Physical (audio/sound).                                                                      |
| Event               | Anything associated with a timeline via Instants. An InstantEvent has zero duration; a TimeIntervalEvent has duration defined by start and end coordinates.                               |
| Instant             | Associates a coordinate with a signification such as \enquote{start of event $e$}. Instants sharing a coordinate are synchronous.                                                         |
| InverseMap          | The reverse transformation of a bijective ConversionMap.                                                                                                                                  |
| Jump                | A control event with JumpFrom and JumpTo Instants. When active, makes events at JumpTo contiguous with those ending at JumpFrom (e.g., repeats, \textit{dal segno}).                      |
| Length              | The distance between a timeline's origin and its last Instant. A locked timeline cannot extend its length.                                                                                |
| Match               | A claim---issued by a human or algorithmic agent---that events from disparate timelines are synchronous or equivalent, with associated metadata (agent, criteria, certainty).             |
| MatchLine           | A linked list of Match objects preserving their order, enabling selection and alignment of temporal correspondences.                                                                      |
| MatchPath           | A graph traversal connecting matched events across multiple timelines (e.g., $A \rightarrow B \rightarrow C$).                                                                            |
| MultiMap            | An umbrella term for composed ConversionMaps (ChainMap, CombinationMap, ConcatenationMap).                                                                                                |
| Origin              | The zero coordinate of a timeline, from which all positions are measured.                                                                                                                 |
| Region              | A named part of a timeline defined by a TimeInterval (e.g., \enquote{Chorus}, \enquote{Verse}). Regions are not timelines and cannot hold events or maps directly.                        |
| Segment             | A Child timeline that is contiguous with its siblings. A SegmentLine is a parent containing only contiguous Segments.                                                                     |
| Synchrony           | Strict synchrony: Instants sharing identical coordinates. Pragmatic synchrony: Instants binned together based on a threshold (e.g., for quantisation).                                    |
| TimeInterval        | Defined by a StartInstant and EndInstant; left-inclusive and right-exclusive $[s, e)$. The EndInstant's coordinate must be $\geq$ the StartInstant's.                                     |
| Timeline            | A positive coordinate axis minimally defined by its origin and measuring unit. Accommodates events and potentially Children.                                                              |
| TimeStamp           | A cross-section through a timeline hierarchy, comprising the root coordinate, synchronous Child coordinates, and all ConversionMap results.                                               |
| TraversalMap        | A sequence of TimeIntervals representing a specific traversal path through a timeline (handling Jumps and repeats). Also called T-map.                                                    |
| WarpMap             | A derived timeline where coordinates are re-adjusted based on AlignmentAnchors to align with another timeline.                                                                            |

## License

MIT
