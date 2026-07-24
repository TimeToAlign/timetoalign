# Changelog

## [1.0.0](https://github.com/TimeToAlign/timetoalign/compare/v0.2.0...v1.0.0) (2026-07-24)


### ⚠ BREAKING CHANGES

* renames measures (m) => floating_measures (fm)
* **core:** flatten core/ to four modules and unify the TimeScalar hierarchy
* `extra_columns` will be removed from TabularLoader in the next WP (A5.1); migrate callers to `field_specs`. `loader.events` is preserved during the migration window but will be replaced by `loader.get_events()`.
* any code using the now deprecated (uppercase) names of the rogue enums may fail

### Features

* **alignment:** add MatchClaimField columnar claim store ([f9dbf60](https://github.com/TimeToAlign/timetoalign/commit/f9dbf60c634ac2f46e28e91444ebb37da6051a94))
* **alignment:** add MatchClaimField columnar claim store ([3520bbb](https://github.com/TimeToAlign/timetoalign/commit/3520bbb629f28624a6a3bbc37cd8278bd6b4b9c7))
* **alignment:** affordance "Try" footer on timestamp and claim displays ([2e9cf57](https://github.com/TimeToAlign/timetoalign/commit/2e9cf57d346a162c025d9bfc07bf8c1eea575196))
* **alignment:** affordance "Try" footer on timestamp and claim displays ([426c03b](https://github.com/TimeToAlign/timetoalign/commit/426c03b28a432dca9183fe945854925f0afee882))
* **alignment:** conform GroupTimestamp to the Stamp contract ([9d4d76a](https://github.com/TimeToAlign/timetoalign/commit/9d4d76adca76a42b030cac5051dd2a163b9f7135))
* **alignment:** unify MatchStamp with the Stamp contract and single cross-group resolution API ([90dfad4](https://github.com/TimeToAlign/timetoalign/commit/90dfad4e8d44fc5e4cc944bd51dd82d07ce07568))
* **alignment:** unit-aware coordinate inputs and canonical claim filters ([4d51481](https://github.com/TimeToAlign/timetoalign/commit/4d51481eeb85b495b3f3370752cee29b56de45ca))
* **alignment:** unit-bearing Coordinate anchors through claims and columnar storage ([93e734a](https://github.com/TimeToAlign/timetoalign/commit/93e734afec70ef1503b06a4271d908e3f096c43b))
* computation of default flow based on flow-control elements rather than the "next" field ([31eaa33](https://github.com/TimeToAlign/timetoalign/commit/31eaa333ff9df03b8c9c8fce41774cbbbf1a1510))
* CoordinateField, PitchField, HarmonyField, DurationField, schemas ([936d379](https://github.com/TimeToAlign/timetoalign/commit/936d379afdc836d212d157fb1dd7692a21c21270))
* **core,loader,timelines,alignment:** type-based IDs, curated facade, timeline registry, WarpMap family API ([827a34f](https://github.com/TimeToAlign/timetoalign/commit/827a34f0f638bcfd51719409397fd34fa5ccdb06))
* **core,loader:** enforce scalar/field mirror parity, type-based field dispatch, and vectorised convert_to mirrors ([80e2f81](https://github.com/TimeToAlign/timetoalign/commit/80e2f81cfbed1ea1548af009e242ced11e106a2a))
* **core:** introduce Stamp base class unifying the timestamp family ([3c1ee8b](https://github.com/TimeToAlign/timetoalign/commit/3c1ee8b982630f341d344e16fa75cba4961510c8))
* **core:** one coordinate-resolution canon with a strict unit policy ([ffae3d9](https://github.com/TimeToAlign/timetoalign/commit/ffae3d9b7f21851cb9f023bb9bcf53ab0e8c7532))
* customizable atomic-section naming with volta-suffix labels ([db2ea7e](https://github.com/TimeToAlign/timetoalign/commit/db2ea7e43d810a36e567413891a6acec79c50760))
* **display:** shared affordance-card _repr_html_ for loaders, EventData, fields ([115f6d7](https://github.com/TimeToAlign/timetoalign/commit/115f6d72a843b59a409b47149bea2444cb17a864))
* **display:** shared affordance-card _repr_html_ for loaders, EventData, fields ([7f73a94](https://github.com/TimeToAlign/timetoalign/commit/7f73a94ec3c059679274b0239c9b193272b315ed))
* **flow:** add structural-invariant diagnostics to FlowController ([c8b609d](https://github.com/TimeToAlign/timetoalign/commit/c8b609d197c1fbed71b69f587221877a638bae73))
* improves loading and displaying flow elements from ms3-generated measures TSV ([dedfadb](https://github.com/TimeToAlign/timetoalign/commit/dedfadbb52a28aff0a6416a4853e52c21decd558))
* introduce Protocol hierarchy and core scalars (pitch, note, measure, harmony) ([2c1e98a](https://github.com/TimeToAlign/timetoalign/commit/2c1e98a82fa8c7263f8ae86d32e67983395ea375))
* layered EventData, get_events(properties=), _CANONICAL_FIELD_ORDER, field_specs, Ms3Loader DataField integration ([e2b3363](https://github.com/TimeToAlign/timetoalign/commit/e2b336360cfbe696ac08cd381d78cbfc755e5f4d))
* **loader/tabular:** two-step column_specs + field_specs pipeline ([71113a3](https://github.com/TimeToAlign/timetoalign/commit/71113a33d4f3559787383afe1cd53c138c2f0131))
* **loader:** add ListenHereLoader for audio-to-audio alignment ([decc57c](https://github.com/TimeToAlign/timetoalign/commit/decc57cdf44478f6d3d575e572e875a2579bcf80))
* **loader:** add ListenHereLoader for audio-to-audio alignment ([aecb453](https://github.com/TimeToAlign/timetoalign/commit/aecb4533c43c48b84412d9be9dbe806e71438922))
* **loader:** add PerformancePrecisionLoader for audio-to-score alignment corpora ([5bf4bb7](https://github.com/TimeToAlign/timetoalign/commit/5bf4bb7ab5e86c9ec23a1c4305b071eddf15c685))
* **loader:** afford EnharmonicPitch pitch view across every loader ([7123ea0](https://github.com/TimeToAlign/timetoalign/commit/7123ea0b38f704975a369d0900c9b3f4bf641942))
* **loader:** measured beat features as Beat/Dynamics events ([b19c618](https://github.com/TimeToAlign/timetoalign/commit/b19c6188e81a01badebe0568ebac490dcfbea6d1))
* **loader:** MpmLoader for MPM-Toolbox MSM+MPM+MPR projects ([182f782](https://github.com/TimeToAlign/timetoalign/commit/182f782c8ee45f593876fd03ff3f6560133abad4))
* **loader:** ParangonadaLoader for parangonada CSV exports ([7689cd1](https://github.com/TimeToAlign/timetoalign/commit/7689cd1b99405d66a628ab107d3082608e29a367))
* **loader:** reach ListenHere claims via get_field and query them columnar ([f637004](https://github.com/TimeToAlign/timetoalign/commit/f637004163a3759afa1f322555c65fbd801de6ae))
* **loader:** reach ListenHere claims via get_field and query them columnar ([1ff11e3](https://github.com/TimeToAlign/timetoalign/commit/1ff11e35b098e6ba443ba6adb6bd9a0cee30ab23))
* **loader:** represent note pitch exactly once ([4d66ce7](https://github.com/TimeToAlign/timetoalign/commit/4d66ce7c622b7629bca64a5ccccfadd6dff4e130))
* **loader:** spectrogram graphical timeline completes MpmLoader's domain span ([f019caf](https://github.com/TimeToAlign/timetoalign/commit/f019caff57b82b78f1ffbd00ff7576789d0a62b9))
* **loader:** uid as the one timeline-identifier name; live id_pattern ([c494328](https://github.com/TimeToAlign/timetoalign/commit/c4943280c21da9645910a503856acf1f3040c795))
* **midi:** split MidiEvent into base + ScoreMidiEvent and shrink performance-MIDI schema ([06196fd](https://github.com/TimeToAlign/timetoalign/commit/06196fd2eb9cd75b17d3bcec6409c4ba17cbbd7d))
* raw DataField hierarchy and SemanticField[R] composition ([4d52397](https://github.com/TimeToAlign/timetoalign/commit/4d52397265267abf92dcf47a2bcbbbb62d6709ff))
* **schemas:** migrate Coordinate and SpecificPitch to pydantic v2 with pa.Schema bridge ([a2fd2f4](https://github.com/TimeToAlign/timetoalign/commit/a2fd2f423580ab88d336abccb4bd1bf84d486f5a))
* **schemas:** migrate twelve scalars to pydantic v2 and add the new Duration scalar ([1e6c525](https://github.com/TimeToAlign/timetoalign/commit/1e6c52533808153e7eae78a3d9bc28e39c56e5d6))
* **timelines:** promote BeatGrid with faithful serialization and beat-unit-aware queries ([1d27d02](https://github.com/TimeToAlign/timetoalign/commit/1d27d02b007b8de0edab66ac67b4d1b0a79243b7))


### Bug Fixes

* **alignment:** deepen MatchStamp guarantees and widen claim-factory coordinate inputs ([5b16e20](https://github.com/TimeToAlign/timetoalign/commit/5b16e20275990ef9267d3413a7a9c5bfbb5784f2))
* coerce Fraction timeline length to float at PyArrow boundary ([2354242](https://github.com/TimeToAlign/timetoalign/commit/2354242efcb5849a74b34d2e4dd3099f4e0c34ba))
* coerce Fraction timeline length to float at PyArrow boundary ([6eb05db](https://github.com/TimeToAlign/timetoalign/commit/6eb05dbfb23e948c78f82d3ea623f59976a4ed42))
* **core,alignment,loader:** close review findings on the input canon ([6fa672f](https://github.com/TimeToAlign/timetoalign/commit/6fa672fad3d9c0edb23892d5cb56617a8e0db707))
* **core:** surface metadata version errors in field shape matching ([d287562](https://github.com/TimeToAlign/timetoalign/commit/d2875622c9bbb26fa3f4fa08411869da051fa68a))
* corrects the diagram line displaying the IDs ([41f624f](https://github.com/TimeToAlign/timetoalign/commit/41f624f0d90e00ad6abeb0c912bc9981aae40719))
* FlowControlElement now includes all flow-control elements ([c36ef20](https://github.com/TimeToAlign/timetoalign/commit/c36ef20a905e8f1afb1aaba92cb90ee9b3c18e5b))
* **flow:** repair default traversal for implicit, nested, and final-measure flow control ([4bf5dd3](https://github.com/TimeToAlign/timetoalign/commit/4bf5dd33055e93dc1d2c49dad24e682b7e22d370))
* **flow:** show every flow-control element in the score-map diagram ([a8fb41a](https://github.com/TimeToAlign/timetoalign/commit/a8fb41a4bdc3b84e0e924d21e90ade950ae42721))
* **flow:** show every flow-control element in the score-map diagram ([b08ca1f](https://github.com/TimeToAlign/timetoalign/commit/b08ca1f47331d077c2d7259d0aaa85fd95cc977e))
* improves AtomicSection.__repr__() ([49b72d3](https://github.com/TimeToAlign/timetoalign/commit/49b72d3ceb9cc6c8199ec62dd596589c453b9d90))
* improves ScoreFlowController.diagram() ([9acfb92](https://github.com/TimeToAlign/timetoalign/commit/9acfb922fe38deed4172f392b6e5f6ae37d86011))
* **loader,storage,timelines:** harden the consolidated boundaries after review ([c484eda](https://github.com/TimeToAlign/timetoalign/commit/c484eda5710bc753e1f30fa5cee020962a86da1d))
* **loader:** class-based get_field discovers any PitchField column regardless of blueprint (INC-3) ([9227455](https://github.com/TimeToAlign/timetoalign/commit/922745519987e5c33fb5e83a9de5e6b221da94ac))
* **loader:** keep carried volta columns int64 across group unfolding ([632a76a](https://github.com/TimeToAlign/timetoalign/commit/632a76a532a05ae6c731705d1387aca5291b822b))
* **loader:** recover MEI repeat metadata from unnumbered measures ([0f739d7](https://github.com/TimeToAlign/timetoalign/commit/0f739d742b50368833817b67eafec6f4f45a00d5))
* **loader:** translate partitura navigation markers instead of dropping repeats ([3caa7bf](https://github.com/TimeToAlign/timetoalign/commit/3caa7bff2f6b2fb303dbd3bed30df03166ddeef3))
* **maps,timelines:** harden the unified map family after review ([9b222a2](https://github.com/TimeToAlign/timetoalign/commit/9b222a2bce761b4a5d77b6010fd98c8500b646eb))
* **notebook:** use ensure_data() in how01_score_types (INC-4) ([7ef249b](https://github.com/TimeToAlign/timetoalign/commit/7ef249b093de0b78c0efc9627de303a16b5a7f8b))
* **storage:** blueprint field resolution shares the class-path raw-column promotion ([04ad56f](https://github.com/TimeToAlign/timetoalign/commit/04ad56ff21528f5f8b8908ec8e852983de1a76b6))
* **testdata:** _looks_ready() now verifies non-marker content alongside sentinel (INC-5) ([dd5d55b](https://github.com/TimeToAlign/timetoalign/commit/dd5d55b8070ed022092a4e87b45de0e8fa9d7a66))
* **timelines:** honour conversion_maps on every stamp producer and make row stamps round-trip ([1000577](https://github.com/TimeToAlign/timetoalign/commit/10005772247e0ab7cb3106be2002c0ab7be38291))
* **time:** propagate TimeScalarField outer-struct nulls through every data-shaped mirror ([2b9b3de](https://github.com/TimeToAlign/timetoalign/commit/2b9b3deafedc04f30e371d3f4b66ad26897072c3))
* widen coordinate-accepting alignment APIs to the full coordinate type ([859e27a](https://github.com/TimeToAlign/timetoalign/commit/859e27ac2e2c94903c46202c59bfbad6ecb53fce))


### Documentation

* adds how01_brazilian_flows.py ([2fd39d8](https://github.com/TimeToAlign/timetoalign/commit/2fd39d86d523f6f7be491b646344b44c7377d750))
* adds ToDo ([8c59929](https://github.com/TimeToAlign/timetoalign/commit/8c59929a2ac03f2958586819a8a284a0a0e5d35f))
* **benchmarks:** add vectorized-compute benchmark and split into per-row vs bulk regimes ([75cab53](https://github.com/TimeToAlign/timetoalign/commit/75cab535e4885a2d5ab85e4956a06210ee159594))
* clarify MidiPitch vs EnharmonicPitch are distinct (INC-1) ([474b1c3](https://github.com/TimeToAlign/timetoalign/commit/474b1c3e6840a2f34651a885c81a71de0a90935a))
* condenses 4 notebooks into 2 and integrates them in the homepage ([35a8bed](https://github.com/TimeToAlign/timetoalign/commit/35a8bedf57429fcaa4b140cae825d95e7085fb1b))
* correct stored-uid queries, import homes, and the architecture page ([f33f018](https://github.com/TimeToAlign/timetoalign/commit/f33f0188b19e73ea3f0745b0bc6d64517fb87599))
* drops the redundant calls to .diagram() ([b927a26](https://github.com/TimeToAlign/timetoalign/commit/b927a2649d5ba05b25a705331650559ea042b434))
* how to contribute ([55af161](https://github.com/TimeToAlign/timetoalign/commit/55af161317f9af86190f537188ad0c1000a1f023))
* **howto:** demonstrate one schema-mechanism across fifteen scalars ([6ced737](https://github.com/TimeToAlign/timetoalign/commit/6ced737ccc0925e2a23f28b9e07cad44ea745433))
* **howto:** rewrite the schema-mechanism demo around the internal storage round-trip ([83ec29a](https://github.com/TimeToAlign/timetoalign/commit/83ec29ac2dacd7d838a44c0991507b81441ec552))
* migrate notebooks and pages to the consolidated loader, ID, and map APIs ([4961ce6](https://github.com/TimeToAlign/timetoalign/commit/4961ce6d9135b48b651706bc698eb8751b9137b9))
* migrate notebooks to the consolidated query and loader API ([e8a8062](https://github.com/TimeToAlign/timetoalign/commit/e8a8062445db75d7d16d93c9647b93305153081f))
* modifies notebook for producing the flow diagrams for the three scores of Beethoven op. 35 (Eroica variations) ([d1aa553](https://github.com/TimeToAlign/timetoalign/commit/d1aa5532b5e81bffc3cb848ef90d9393c9c92b95))
* promote DataFields and EventData to a foundational tutorial ([825c272](https://github.com/TimeToAlign/timetoalign/commit/825c272815731852e7ba468d6a12d57e4aaaf2e4))
* promote DataFields and EventData to a foundational tutorial ([79182ff](https://github.com/TimeToAlign/timetoalign/commit/79182ff8b84e23e62c27109586ec38dc32f11bd4))
* promote Pitch and Harmony to a cross-format tutorial ([35aa953](https://github.com/TimeToAlign/timetoalign/commit/35aa953779c2967c9bfe8991abbfe4ac63f9975a))
* promote Pitch and Harmony to a cross-format tutorial ([31b9908](https://github.com/TimeToAlign/timetoalign/commit/31b99083a0a075e2cc3cbd88c0f10530ef838559))
* reference the real midi column in the DataFields tutorial ([9be45f1](https://github.com/TimeToAlign/timetoalign/commit/9be45f1eb6e0be5a564a225f5d463bc67c496175))
* regenerate API reference and MPM how-to for the merged library ([9eed89a](https://github.com/TimeToAlign/timetoalign/commit/9eed89ab422cfa5b1c5d379c455ad9995528ab6f))
* regenerate MPM how-to outputs for the represent-once pitch surface ([4c49df6](https://github.com/TimeToAlign/timetoalign/commit/4c49df6297038b7d0bdcb065693b6f22b168955c))
* remove orphaned PerfectAlignment API-reference stub ([17fb417](https://github.com/TimeToAlign/timetoalign/commit/17fb417caef43bb15cae63427d10af33047a3736))
* remove orphaned PerfectAlignment API-reference stub ([7f59751](https://github.com/TimeToAlign/timetoalign/commit/7f5975140310c636d40256b4a9ebd86ace328e0e))
* renames notebooks to fit the categories ([c45e0e7](https://github.com/TimeToAlign/timetoalign/commit/c45e0e7b5f65843968f2fa9eb4fcdb803616a615))
* replaces invariants table with CSV export ([a096ae4](https://github.com/TimeToAlign/timetoalign/commit/a096ae4adf4464898918eb7e3a1113c4ec55370c))
* replaces invariants table with CSV export ([93af713](https://github.com/TimeToAlign/timetoalign/commit/93af713751f6538387f45aa278c81bd93e71d4a4))
* route cross-group queries through get_matchstamp_at and provision tutorial data on demand ([466e098](https://github.com/TimeToAlign/timetoalign/commit/466e09822ce20d83fe9457a231d498480addd808))
* teach the position/span operator rules in the coordinate how-to ([a4be4bd](https://github.com/TimeToAlign/timetoalign/commit/a4be4bdeaf581b8637c14b6d6066e87a41c78d9f))
* teach the position/span operator rules in the coordinate how-to ([9fae258](https://github.com/TimeToAlign/timetoalign/commit/9fae258b5c1f7c163aafa51a1078db8767aa7de0))
* updates page ([3b27c54](https://github.com/TimeToAlign/timetoalign/commit/3b27c5444dc094e0723468f7fa73023b8fcf78e9))


### Code Refactoring

* **core:** flatten core/ to four modules and unify the TimeScalar hierarchy ([fdf5812](https://github.com/TimeToAlign/timetoalign/commit/fdf5812fb0ead6c825a4db3c6b590f3cdd0d3b91))
* moves enums to core/enums.py and renames members ([b412353](https://github.com/TimeToAlign/timetoalign/commit/b412353bd1da1ab2b71ddad167c1c86fb4bcf307))
* renames measures (m) =&gt; floating_measures (fm) ([50e2194](https://github.com/TimeToAlign/timetoalign/commit/50e2194abb4de8c4dc2cba2f37cce11fefcc5076))

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
