# Changelog

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
