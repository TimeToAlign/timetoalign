# Changelog

## [2.0.0](https://github.com/TimeToAlign/timetoalign/compare/v1.2.0...v2.0.0) (2026-08-18)


### ⚠ BREAKING CHANGES

* **retrieval:** `to_dataframe()` is removed from Timeline, TimelineGroup and AlignmentBundle in favour of `format="table"|"dataframe"` on the table getters; `get_timestamp_of`/`get_timestamps_of` are renamed to `_for`; the `coordinates=` keyword on every table getter is renamed to `at`, which now also accepts event keys; `as_fractions` is deleted because it let a caller override an axis's declared number type; `get_matchstamps` keeps only its claims path; and `Timeline.get_timestamp_table` no longer emits an `axis` column, which was byte-identical to the receiver's own column.
* **retrieval:** raw-float stamp accessors, coordinate pair tuples, and the untyped WarpMap call surface are removed; retrieval defaults return IdCoordinate. Full suite: 4589 passed, 24 skipped.
* **core:** TimelineGroup.get_timestamp_at and AlignmentBundle.get_matchstamp_at now express the axis in the addressed timeline's declared number type (a float query on a rational axis yields an exact fraction; an exact query on a float axis yields a float), and fractional queries on discrete axes round before interpolation.
* **core:** query and derived coordinates on rational axes now surface as exact fractions rather than floats; get_timestamp(9.5) on a quarters timeline yields Fraction(19, 2).
* **core:** RationalField, CoordinateParser and the public DISCRETE_UNITS constant are removed; storage/parsing.py and timelines/engines/coordinate_ops.py are gone. NumberType defaults are now derived from the unit rather than per-timeline/per-loader settings. to_int() defaults to "round" (was "truncate"). Stamp.axis carries the canonical numeric value instead of always-float. Scalar constructors coerce to the unit's representation, so Coordinate(1.5, quarters) now holds Fraction(3, 2); a non-integral exact fraction in a discrete unit raises instead of silently rounding.
* **alignment:** `AlignmentBundle.add_timeline(aligned_to=...)` is now `AlignmentBundle.add_timeline(grouped_with=...)`. No alias is kept; existing call sites must be renamed.

### Features

* **core:** derive number representation from the unit, end to end ([ddf9832](https://github.com/TimeToAlign/timetoalign/commit/ddf9832002a2b8d92eb468c7d393d48cc5fbe463))
* **ieee1599:** nest engraved editions as pages of accolades ([2078b9c](https://github.com/TimeToAlign/timetoalign/commit/2078b9ce83dc2c00395cb8c914ad776fdf737375))
* **retrieval:** complete the retrieval grid across stamps and tables ([897e3d2](https://github.com/TimeToAlign/timetoalign/commit/897e3d26ade6609d957f4add217ee9c3fd68de55))
* **retrieval:** typed coordinate retrieval with format vocabulary, Interval scalar, and typed stamp storage ([b9aebd2](https://github.com/TimeToAlign/timetoalign/commit/b9aebd21145cb6b07fed06f55e88b3a8e845d3a1))


### Bug Fixes

* **alignment:** render claim coordinates exactly, with their units ([0b85da4](https://github.com/TimeToAlign/timetoalign/commit/0b85da410bbfecbbcf6fc2089047929345339718))
* **core:** build the dyadic mirror without a platform-bound exponent ([39d8e59](https://github.com/TimeToAlign/timetoalign/commit/39d8e598b177958fdcce5b87ee2dc486769044f1))
* **core:** exact duration ingestion and uniform stamp-axis number types ([ecc4e31](https://github.com/TimeToAlign/timetoalign/commit/ecc4e31c01eb471c4162b2f5afda1fe2ca1c8a39))
* **core:** express every derived value in its axis's declared number type ([8173232](https://github.com/TimeToAlign/timetoalign/commit/81732328be561fdd4b4baa239e4300d3549d5c26))
* **core:** express retrieved readings on their declared axes and make stamp order deterministic ([a4f64e4](https://github.com/TimeToAlign/timetoalign/commit/a4f64e4da3dedcc96ec230f6ba590ce7d2182799))
* **core:** keep exact rational coordinates exact through conversion and stamps ([ecfa12e](https://github.com/TimeToAlign/timetoalign/commit/ecfa12e4f5377904173347a3be3003cce64b5ef0))
* **core:** stop reporting positions and pitches with more certainty than they carry ([c8272f7](https://github.com/TimeToAlign/timetoalign/commit/c8272f72652f0ac018e552d346c329db3735c9b8))
* **display:** render nested children in the root's columns ([e6a5adc](https://github.com/TimeToAlign/timetoalign/commit/e6a5adc529287c6b276a0cc9d2ec424a5e5e57ac))
* **loader:** keep audio metadata probing quiet on misnamed files ([1454024](https://github.com/TimeToAlign/timetoalign/commit/1454024511c96278c1f4ea513720f02eefaeba1b))
* **timelines:** render discrete coordinates as integers in error messages ([c4ad085](https://github.com/TimeToAlign/timetoalign/commit/c4ad0855066bf9be39a16f5986730d97c934e8bd))


### Documentation

* migrate notebooks and site to the typed retrieval surface ([5bb8ec8](https://github.com/TimeToAlign/timetoalign/commit/5bb8ec87fcaf82292661f36ef2370d5bbfe4a9aa))
* publish the loader walkthrough and fix its heading order ([6b0f428](https://github.com/TimeToAlign/timetoalign/commit/6b0f428506e1bdd3f124466eef7e229f4d97e970))
* re-execute the notebooks whose output drifted ([29ed486](https://github.com/TimeToAlign/timetoalign/commit/29ed486945c97dfa6e4032f13e73794ec687b753))
* **site:** compile the tutorial series into the published notebooks ([ecb0826](https://github.com/TimeToAlign/timetoalign/commit/ecb0826ce73fa95530e95a76e48866e80b65d833))
* **site:** rebuild the published notebooks ([4926205](https://github.com/TimeToAlign/timetoalign/commit/4926205f37199916e0d37db9e99ea2d681d8bd5f))
* **site:** rebuild the published notebooks after the consistency pass ([0042cfe](https://github.com/TimeToAlign/timetoalign/commit/0042cfe9d90d96bbcd1bc92c4421537f93eb8ecc))
* **site:** rebuild the published notebooks after the final corrections ([07d7dba](https://github.com/TimeToAlign/timetoalign/commit/07d7dbadeb84191bc4b0ffe73fd044edc445f2ec))
* **site:** rebuild the published notebooks with exact claim rendering ([192b43f](https://github.com/TimeToAlign/timetoalign/commit/192b43ffa29819cc733fbe8a48999f509e7bb795))
* **tutorials:** close the last gaps between prose and rendered output ([b48d100](https://github.com/TimeToAlign/timetoalign/commit/b48d100ae5edf771ddecca81fba8cc3ab7d93820))
* **tutorials:** make the ten notebooks read as one series ([dc7f5bd](https://github.com/TimeToAlign/timetoalign/commit/dc7f5bdb3c7b9da3552cc8f5001cce5bf64e205a))
* **tutorials:** match every claim in the prose to what the page shows ([9a53baa](https://github.com/TimeToAlign/timetoalign/commit/9a53baa111d7d9c897f0232ada8a17cdf3fa438a))
* **tutorials:** rebuild the tutorial series around a single learning curve ([ac37610](https://github.com/TimeToAlign/timetoalign/commit/ac37610208eb7af585ad02cec08e2fe0ce116c45))
* **tutorials:** show what the library returns, and one idea per cell ([c2a3238](https://github.com/TimeToAlign/timetoalign/commit/c2a32380c6421654b3f2bb1e4a03aa626dd0386f))


### Code Refactoring

* **alignment:** name the bundle grouping parameter grouped_with ([fdcf269](https://github.com/TimeToAlign/timetoalign/commit/fdcf269c3aa097899cf606ba608ed5fe2f2d60a0))

## [1.2.0](https://github.com/TimeToAlign/timetoalign/compare/v1.1.0...v1.2.0) (2026-08-08)


### Features

* **flow:** add FlowMap.from_dict and fill placed gaps with empty segments ([e8c2fce](https://github.com/TimeToAlign/timetoalign/commit/e8c2fce1292fbf0b8a2390a5f5df82d622b94ba3))
* **flow:** place FlowMap spans at given coordinates instead of appending ([1fcd274](https://github.com/TimeToAlign/timetoalign/commit/1fcd274a6fd62714debf77f50b3865aa899d034f))
* **timelines:** guard the default-flow traversal and report traversal diagnostics ([c5ff3a2](https://github.com/TimeToAlign/timetoalign/commit/c5ff3a28365f1ad0844d78a37be780e5b6e5dde9))


### Bug Fixes

* **core:** accept integer-valued float ratio members at the rational wire boundary ([bfe8d77](https://github.com/TimeToAlign/timetoalign/commit/bfe8d77ca59a6011310b5af48e8d9b12bdf8e3ac))
* **testdata:** extract corpora atomically and verify completeness before trusting the cache ([50cadab](https://github.com/TimeToAlign/timetoalign/commit/50cadabfd0594a57b7f6ee8906bd9a1c61555fa7))
* **tests:** point MIDI integration specimens at the midi corpus ([0c23fb3](https://github.com/TimeToAlign/timetoalign/commit/0c23fb3b046c529b34e2130fa74f1c5ec35b444b))


### Performance Improvements

* **midi:** add a mido-backed parser option to ScoreMidiLoader ([bffed90](https://github.com/TimeToAlign/timetoalign/commit/bffed90e029d192a6cd512f550775e66cf50a6ea))


### Documentation

* **core:** document exact binary-expansion semantics for float-to-Fraction conversion ([991032c](https://github.com/TimeToAlign/timetoalign/commit/991032c3eee8f373d4bdf4b0f22089383ff4ad03))
* **howto:** demonstrate traversal diagnostics on the Choros flows notebook ([3465a00](https://github.com/TimeToAlign/timetoalign/commit/3465a006774479ebb09e35488a20413f7e28f58f))
* show placing flows and inverted cuts in the FlowMap how-to ([4c274bf](https://github.com/TimeToAlign/timetoalign/commit/4c274bf13f724e99647869e478f90732dbd5cab0))

## [1.1.0](https://github.com/TimeToAlign/timetoalign/compare/v1.0.1...v1.1.0) (2026-07-30)


### Features

* **display:** recurse timeline diagrams with a depth control ([e1eca24](https://github.com/TimeToAlign/timetoalign/commit/e1eca2483757ee13efc6eca0e38c5b60d82f7361))
* **timelines:** harmonize child creation across concrete classes ([7db621c](https://github.com/TimeToAlign/timetoalign/commit/7db621c610cac63c73baf0a18b19d784fe130fe3))
* **timelines:** parameterize SegmentLine over its segment class ([d9d9d17](https://github.com/TimeToAlign/timetoalign/commit/d9d9d17f1e5de5f375604135f86ce1b7f84b9f03))
* **timelines:** resolve descendant coordinates through get_coordinate ([407c738](https://github.com/TimeToAlign/timetoalign/commit/407c7382c62bca9bbaee81c098d42deecc3b6fba))


### Bug Fixes

* **timelines:** reject appends to length-locked timelines ([b4ba551](https://github.com/TimeToAlign/timetoalign/commit/b4ba55141bac928ac82223faefb9b602124d9ad1))


### Documentation

* construct concrete timeline types in notebooks ([30eac1b](https://github.com/TimeToAlign/timetoalign/commit/30eac1b54193ad4e5f6b524fecdd0bc89bcb7699))
* demonstrate the hierarchical child API across notebooks and reference ([a070a83](https://github.com/TimeToAlign/timetoalign/commit/a070a8364ef03ec18e4229a9275fb62a6699ef80))
* register SegmentLine and inherited timeline methods in the reference ([0533ab3](https://github.com/TimeToAlign/timetoalign/commit/0533ab3fd7cd7a9853a550948ea2665dfacd6518))

## [1.0.1](https://github.com/TimeToAlign/timetoalign/compare/v1.0.0...v1.0.1) (2026-07-24)


### Documentation

* full site render with re-executed notebooks ([41d0c2e](https://github.com/TimeToAlign/timetoalign/commit/41d0c2e04076ed4c160668d637a8a018881c5a95))
* improves project links ([949a8c7](https://github.com/TimeToAlign/timetoalign/commit/949a8c7df26b0b570d126eec320dfd8fa76a5eec))
* open the landing page with the article's lead figure ([699046e](https://github.com/TimeToAlign/timetoalign/commit/699046ee90b65811c43b7a9210e7094e06fd7a89))
* regenerate reference and site after the docstring restatement ([56c4c6c](https://github.com/TimeToAlign/timetoalign/commit/56c4c6c3ede366099e305b475dbcf4fa4cc61746))
* regenerate the API reference with Google-style docstring parsing ([8bc6d6d](https://github.com/TimeToAlign/timetoalign/commit/8bc6d6d5eaa5a957a4121d72859192d5defd4000))
* render Google-style docstrings with a Yields-capable renderer ([62500b0](https://github.com/TimeToAlign/timetoalign/commit/62500b07ab2a2638373b5b136a890e95ac631dcb))
* state model definitions in the library's own voice ([75a12cf](https://github.com/TimeToAlign/timetoalign/commit/75a12cf3d107bf92550781859a6e71b24a598db2))


### Miscellaneous Chores

* release 1.0.1 ([50af5f8](https://github.com/TimeToAlign/timetoalign/commit/50af5f8e892cee5bf3988701794fc9f12cdafe3d))

## [0.2.0](https://github.com/TimeToAlign/timetoalign/compare/v0.1.0...v0.2.0) (2026-05-13)


### Features

* fetch test data on demand via pooch + timetoalign.testdata ([a334d43](https://github.com/TimeToAlign/timetoalign/commit/a334d4330e3bcfa0463fd40bf8599f15980217f1))


### Bug Fixes

* **bundle:** resolve internal IDs and interval components in matchstamp lookup ([f1b0546](https://github.com/TimeToAlign/timetoalign/commit/f1b05467233bdb67ba5e686f85cd54767d175fd7))


### Documentation

* adds how01_flow_control.py ([95290d7](https://github.com/TimeToAlign/timetoalign/commit/95290d74420655e0ea46aa6e1de7780b01c960cd))

## 0.1.0 (2026-05-13)


### Features

* uniform units display across all timestamp APIs ([220c6a5](https://github.com/TimeToAlign/timetoalign/commit/220c6a5cc0aa49f0ee7df757da755189a99c9e7e))


### Bug Fixes

* populate start/end/duration temporal fields in NoteEventData (fixes [#9](https://github.com/TimeToAlign/timetoalign/issues/9), fixes [#10](https://github.com/TimeToAlign/timetoalign/issues/10)) ([00c3734](https://github.com/TimeToAlign/timetoalign/commit/00c3734f492b10dbc12bef76489743b2edd46194))
* populate temporal coordinates in MeasureData, ControlEventData, and AnnotationEventData (fixes [#7](https://github.com/TimeToAlign/timetoalign/issues/7)) ([c6b2eb3](https://github.com/TimeToAlign/timetoalign/commit/c6b2eb36cf2499d32e35ddd835d8da6b13f71540))
* report consistent unit/number_type in ScoreLoader metadata (fixes [#8](https://github.com/TimeToAlign/timetoalign/issues/8)) ([786b65c](https://github.com/TimeToAlign/timetoalign/commit/786b65c790a4ae14530c86cdd4d2c0f3b3e31e9c))
* use quarter_map instead of beat_map in PartituraLoader (fixes [#12](https://github.com/TimeToAlign/timetoalign/issues/12)) ([dcf23c0](https://github.com/TimeToAlign/timetoalign/commit/dcf23c055f5a51774c82fb1dd730f0bba2c5ecd4))


### Documentation

* add redirect index.html and disable Jekyll ([bc71e64](https://github.com/TimeToAlign/timetoalign/commit/bc71e64d7969bc5b8f420c364b1d68d4cd59d2f0))
* add redirect index.html and disable Jekyll ([cb80dd5](https://github.com/TimeToAlign/timetoalign/commit/cb80dd5f1798f7f763eacffd4d2f951b1653234c))
* broaden 'Voice and Staff Information' beyond piano music (fixes [#16](https://github.com/TimeToAlign/timetoalign/issues/16)) ([b918686](https://github.com/TimeToAlign/timetoalign/commit/b918686d6782cd1aadbf69ae93ccc2cf8bd1d88f))
* clarify interpolation methods with distinct y-values and 'next' strategy (fixes [#19](https://github.com/TimeToAlign/timetoalign/issues/19)) ([145a7af](https://github.com/TimeToAlign/timetoalign/commit/145a7afca4638533adde1d9ba04b35a2eff28e93))
* correct path ([7eeecb9](https://github.com/TimeToAlign/timetoalign/commit/7eeecb92cc9c8d4944b187774d98d6e29265544d))
* document large file timeout handling in test README ([fd545a2](https://github.com/TimeToAlign/timetoalign/commit/fd545a2290808950749b96536a4c4efd7891c50b))
* replace deprecated 'bundle' wording with 'store' (fixes [#17](https://github.com/TimeToAlign/timetoalign/issues/17)) ([7ed2ffc](https://github.com/TimeToAlign/timetoalign/commit/7ed2ffc36643254da941f5f4dca53bc42fc029ac))
* replace unreliable septuplet float example with 0.1*10 (fixes [#3](https://github.com/TimeToAlign/timetoalign/issues/3)) ([13f8567](https://github.com/TimeToAlign/timetoalign/commit/13f8567c3d47e4e1b4ae7c33a79abe89e50030fa))
* split notebooks into tuto-notebooks and howto-notebooks (Diátaxis) ([b1dc9e6](https://github.com/TimeToAlign/timetoalign/commit/b1dc9e6d3e58cd3cc4367a09b013ec362c4d300e))
* update test READMEs to reflect cleanup changes ([c481aca](https://github.com/TimeToAlign/timetoalign/commit/c481aca47e55617095bb2741c6db7c1d94b7996f))
* updates autodocs ([592fbdc](https://github.com/TimeToAlign/timetoalign/commit/592fbdc8d094b10f5982f4ae44303bc02da4f406))
* updates homepage ([4402640](https://github.com/TimeToAlign/timetoalign/commit/44026408749517d527008b363d6ca7c881e3d937))
* updates tutorial page ([3d5aa5f](https://github.com/TimeToAlign/timetoalign/commit/3d5aa5faab5cdf04afea0fc48169e01f5a660601))
* writes reduced tutorial notebooks, factoring out older content to how-to notebooks ([faa3fbf](https://github.com/TimeToAlign/timetoalign/commit/faa3fbf7f797ae73bcc573785273f82acea9b1f7))
