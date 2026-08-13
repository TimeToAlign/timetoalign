# Rekordbox Loader Tests - Validation Strategy

This document explains **how** the upcoming tests prove the Rekordbox loader
correct under the TimeToAlign! Zero Tolerance Validation Policy. Every anchor is
derived directly from the two ground-truth data files and stated as an exact value
with no range or approximation.

## Ground-truth data files

**`rekordbox.xml`** — a Rekordbox library export.

| Fact | Value |
|------|-------|
| Collection ``TRACK`` elements | **46** (``COLLECTION Entries`` == 46) |
| ``TRACK`` elements carrying ``TEMPO`` tags | 46 (every collection track has ≥ 1) |
| Total ``TEMPO`` tags | **155** |
| The mix track ``TrackID`` | **147337955** |
| Mix ``Name`` | ``001-samuel_moriero-impact_halloween_xxl_2025_full_set`` |
| Mix ``TotalTime`` | **5277** (seconds) |
| Mix ``TEMPO`` tag count | **14** |
| Mix first ``TEMPO`` | ``Inizio 0.333``, ``Bpm 160.00``, ``Metro 4/4``, ``Battito 4`` |

**`tracks-to-mix.csv`** — an authored mapping of source tracks onto the mix.

| Fact | Value |
|------|-------|
| Data rows | **94** |
| Columns | ``track``, ``track_start_bar``, ``mix_start_bar``, ``track_end_bar``, ``mix_end_bar``, ``track_loop``, ``analysis`` |
| ``track`` labels | XML ``Name`` prefixed with ``"NN. "`` (a number, a dot, a space) |

---

## (a) `TEMPO` -> beat-grid semantics

**Ground truth.** Each ``TEMPO`` tag opens a **beat grid** on the track's physical
(seconds) timeline.

**Semantics a correct reader must encode.**

- A grid opens at ``Inizio`` seconds, carries tempo ``Bpm`` and meter ``Metro``,
  and its first beat (the beat *at* ``Inizio``) is beat number ``Battito`` of a
  measure. In ``4/4``, ``Battito`` ranges over 1..4.
- **``Battito`` fixes the first measure boundary.** ``Battito 1`` means ``Inizio``
  is itself a downbeat (a measure boundary). ``Battito B`` with ``B ≠ 1`` means the
  grid opens *mid-measure*; the next downbeat arrives ``(Metro − B + 1)`` beats
  later. For the mix's first grid (``Battito 4``, ``Bpm 160.00`` → beat 0.375 s),
  the first beat at ``0.333`` s is beat 4, and **the next beat begins a new
  measure** at ``0.333 + 0.375 = 0.708`` s. The bar containing ``Inizio`` is a
  truncated pickup (only beat 4 falls inside the grid).
- **Measure numbers rise monotonically across all grids of one track.** A pickup is
  the represented tail of nominal bar 0, and the first full downbeat is bar 1. The
  measure counter is continuous: a new grid does **not** reset it. Each downbeat
  increments the measure number; across grid boundaries the count only ever
  increases.
- A grid **ends** at the next grid's ``Inizio``, or at the track ``TotalTime`` for
  the last grid.
- **Boundary precedence.** If the last beat implied by one grid would coincide with
  the first beat of the next grid, the **next grid takes precedence** — that instant
  is counted once, as the next grid's beat, never doubled.

---

## (b) Per-grid bar-span derivation for the mix (14 grids)

**Ground truth.** The mix has 14 grids. In ``4/4`` a bar is 4 beats. At
``Bpm 160.00`` a beat is ``60 / 160 = 0.375`` s and a bar is ``4 × 0.375 = 1.5`` s.

**Derivation.** Each grid's span in seconds is ``next Inizio − this Inizio`` (the
final grid runs to ``TotalTime`` = 5277). Bars = span ÷ bar-length, where
bar-length uses **that grid's own bpm**: ``4 × 60 / Bpm``.

| # | Inizio (s) | Bpm | Battito | Span (s) | Bar (s) | Bars |
|---|-----------|-----|---------|----------|---------|------|
| 1 | 0.333 | 160.00 | 4 | 212.639 | 1.500000 | 141.7593 |
| 2 | 212.972 | 160.00 | 3 | 459.757 | 1.500000 | 306.5047 |
| 3 | 672.729 | 160.00 | 1 | 324.001 | 1.500000 | 216.0007 |
| 4 | 996.730 | 160.00 | 1 | 432.007 | 1.500000 | 288.0047 |
| 5 | 1428.737 | 160.00 | 1 | 669.011 | 1.500000 | 446.0073 |
| 6 | 2097.748 | **159.96** | 1 | 96.023 | 1.500375 | 63.9993 |
| 7 | 2193.771 | **159.96** | 1 | 60.014 | 1.500375 | 39.9993 |
| 8 | 2253.785 | 160.00 | 1 | 432.011 | 1.500000 | 288.0073 |
| 9 | 2685.796 | 160.00 | 1 | 726.008 | 1.500000 | 484.0053 |
| 10 | 3411.804 | 160.00 | 1 | 67.508 | 1.500000 | 45.0053 |
| 11 | 3479.312 | 160.00 | 1 | 670.494 | 1.500000 | 446.9960 |
| 12 | 4149.806 | 160.00 | 1 | 151.496 | 1.500000 | 100.9973 |
| 13 | 4301.302 | **160.38** | 1 | 134.679 | 1.496446 | 89.9992 |
| 14 | 4435.981 | 160.00 | 1 | 841.019 | 1.500000 | 560.6793 |

**Bpm deviations and why they matter.** Three grids do **not** carry ``160.00``:
grids 6 and 7 at ``159.96`` and grid 13 at ``160.38``. These are not noise — the
micro-adjusted bpm is exactly what makes each of those grids span a **whole**
number of bars:

- Grid 6: at ``159.96`` the bar is ``1.500375`` s and ``96.023 / 1.500375 =
  63.9993 ≈ 64`` bars; at a flat ``160.00`` the same 96.023 s would read
  ``64.015`` bars — off by a bar-and-a-half over the grid, so using the grid's own
  bpm is mandatory.
- Grid 7: ``60.014 / 1.500375 = 39.9993 ≈ 40`` bars.
- Grid 13: at ``160.38`` the bar is ``1.496446`` s and ``134.679 / 1.496446 =
  89.9992 ≈ 90`` bars; at ``160.00`` it would read ``89.786`` bars.

A test that computed grids 6/7/13 at a hard-coded ``160.00`` bar length must fail;
the loader must read ``Bpm`` per grid.

**Total mix bar count.** The whole mix, measured at the nominal ``160.00``/``4/4``
grid from ``t = 0`` to ``TotalTime``, is exactly

``5277 s ÷ 1.5 s/bar = 3518 bars`` (equivalently ``3518 × 4 = 14072`` beats).

This is the clean anchor: ``5277`` is an exact multiple of the ``1.5`` s bar. The
per-grid spans in the table sum to ``≈ 3517.97`` bars because grids 1 and 2 start
mid-measure (``Battito 4`` and ``3``) and the summation begins at the first grid
onset ``0.333`` rather than ``0``; the ``0.333`` s of pre-grid material plus the
truncated first pickup bar account for the remainder up to 3518.

---

## (c) Loader expectations: 46 physical-domain timelines

**Ground truth.** The 46 collection tracks.

**Expected.** The loader yields **46 timelines** in the physical domain (seconds),
one per collection track. Each timeline affords **floating-measure (``fm``)**
readings through its grids: given a seconds position, its ``fm`` value is derived
from the grid that contains it (its ``Inizio``, ``Bpm``, ``Metro``, ``Battito``),
with measure numbers continuous across that track's grids per section (a).
An anacrusis occupies its offset inside ``fm [0, 1)``; consequently, the first
full downbeat reads ``fm 1`` and bar ``b`` begins at ``fm b``. Every raw grid
instant is an interpolation anchor, including grid changes that occur mid-bar.

**Example tracks to pin (exact facts).**

- **``See Me Coming``** — single grid: ``Inizio 0.082``, ``Bpm 160.00``,
  ``Metro 4/4``, ``Battito 3``, ``TotalTime 256``. Because ``Battito 3``, the beat
  at ``0.082`` s is beat 3; the next downbeat (beat 1) is ``2 × 0.375 = 0.75`` s
  later at ``0.832`` s. Nominal bar 0 is a truncated pickup holding only beats 3
  and 4 inside the grid; the downbeat at ``0.832`` s reads ``fm 1``.
- **``Fkn Raw``** — four grids (mid-track grid changes), all ``Bpm 160.00``,
  ``Metro 4/4``: ``(0.087, Battito 3)``, ``(48.088, Battito 3)``,
  ``(102.464, Battito 4)``, ``(156.840, Battito 1)``; ``TotalTime 176``. The
  measure count must run continuously across all four grids (no reset at 48.088,
  102.464, or 156.840), and the ``Battito`` on each grid re-anchors where that
  grid's first downbeat falls.
- **``Brace For Impact``** — single grid: ``Inizio 0.145``, ``Bpm 150.00``,
  ``Metro 4/4``, ``Battito 2``, ``TotalTime 220``. Here the bpm is **not** 160:
  beat = ``60 / 150 = 0.4`` s, bar = ``1.6`` s. ``Battito 2`` puts the next
  downbeat ``3 × 0.4 = 1.2`` s after ``0.145`` s, at ``1.345`` s. This example
  guards against a loader that assumed the mix's 160/4/4 for every track.

---

## (d) `tracks-to-mix.csv` ingestion and name resolution

**Ground truth.** 94 data rows. The ``track`` column carries an ``"NN. "`` prefix
(digits, dot, space) over the XML ``Name``.

**Name resolution.** Strip the filename prefix with ``^\d+[a-z]?\.\s*`` (the
letter suffix covers split entries such as ``19a.``/``19b.``/``41a.``), then
resolve in three steps: (1) exact match against an XML collection ``Name``;
(2) case-insensitive substring containment in either direction, guarded by a
minimum needle length of 4 characters — without the guard the bare placeholder
``ID`` mis-resolves inside ``Tunnel Vision - Junkie Kid Remix``; (3) the single
curated equivalence ``Woops (Anderex Edit)`` → ``WOOPS EDIT (FREE DL)``, which
closes a perfect 36 ↔ 36 bijection between mapped csv tracks and real mix
tracks in the collection.

**Expected — exactly which rows resolve.** Of the 94 rows, **88 resolve** and
**6 do not**: the six ``ID``-placeholder rows (``04.``, ``06.``, ``16.``,
``17.``, ``36.``, ``41a.``), whose audio was unavailable at analysis time and
which have no XML track. Unresolved rows are skipped. Of the 42 distinct csv
track labels, 36 resolve; the collection's ``Vielleicht Vielleicht`` track is
the one known mix track never referenced by the csv. Step (2) resolves
``Tonight``, ``HUMBLE``, ``Rodeo``, ``HEROINE``, and ``Hard Beat`` (artist
prefixes and label suffixes in the XML that the csv lacks); a resolver without
the length guard must FAIL the six ``ID`` rows rather than mis-match them.

Total unresolved = 5 + 5 + 14 = **24**; resolved = 94 − 24 = **70**. A test must
assert exactly this split; resolution is by **exact** name equality after prefix
stripping, never substring or fuzzy matching.

---

## (e) Loop semantics

**Ground truth.** A row with ``track_loop = N`` expresses that the mapped material
is looped: it must yield **N adjacent, equal-length intervals** on the mix
timeline, **all claiming the same** track interval ``[track_start_bar,
track_end_bar]``.

**Derivation that makes adjacency and equal length provable.** For a loop row with
mix interval ``[mix_start_bar, mix_end_bar]`` and ``N`` loops, the per-loop length
is

``L = (mix_end_bar − mix_start_bar) / N``.

The N intervals are ``[mix_start_bar + kL, mix_start_bar + (k+1)L]`` for
``k = 0 … N−1``. Adjacency holds because interval ``k`` ends exactly where
interval ``k+1`` begins; equal length holds because every interval has length
``L``; coverage holds because the union is ``[mix_start_bar, mix_end_bar]``. The
mapping is well-formed **iff** ``mix_end_bar − mix_start_bar = N × (track_end_bar −
track_start_bar)`` — i.e. ``L`` equals the track interval's own bar length, so each
mix loop is one full pass of the same track material.

**Every loop row in the CSV (all six resolve by name):**

| track | track [start,end] (bars) | mix [start,end] (bars) | mix span | N | L | check span = N × track span |
|-------|--------------------------|------------------------|----------|---|---|-----------------------------|
| ``10. The Sound`` | [64, 65] = 1 | [827, 839] | 12 | 12 | 1 | 12 = 12 × 1 ✓ |
| ``13. TURN IT UP!`` | [53, 61] = 8 | [1121, 1137] | 16 | 2 | 8 | 16 = 2 × 8 ✓ |
| ``28. Fkn Raw`` | [47, 51] = 4 | [2447, 2455] | 8 | 2 | 4 | 8 = 2 × 4 ✓ |
| ``32. GUCCI BAG - Revelation Live Edit`` | [76, 77] = 1 | [2866, 2878] | 12 | 12 | 1 | 12 = 12 × 1 ✓ |
| ``37. Annihilatiøn`` | [25, 26] = 1 | [3162, 3170] | 8 | 8 | 1 | 8 = 8 × 1 ✓ |
| ``37. Annihilatiøn`` | [59, 60] = 1 | [3166, 3170] | 4 | 4 | 1 | 4 = 4 × 1 ✓ |

**Expected claim count after loop expansion.** The 6 loop rows expand to
``12 + 2 + 2 + 12 + 8 + 4 = 40`` claims.

Total-claim accounting, all derived from the files:

| Category | Rows | Claims |
|----------|------|--------|
| Unresolved by name (skipped) | 24 | 0 |
| Resolved, non-loop, **complete** track interval (both bar endpoints present) | 57 | 57 |
| Resolved, loop rows (expanded) | 6 | 40 |
| Resolved, non-loop, **incomplete** track interval (a bar endpoint is ``NaN``) | 7 | 0 complete bidirectional claims |

The **7 incomplete rows** resolve by name but lack a full ``[track_start_bar,
track_end_bar]`` interval (``08. F THE POLICE`` — no ``track_end_bar`` and no
``mix_end_bar``; ``11. LIKE ME`` ×2; ``14. Tunnel Vision - Junkie Kid Remix`` ×3;
``34. BLOW IT UP`` ×1). They cannot express a bar-unit interval-on-track claim.

Therefore the exact expected count of **complete interval↔interval bar claims** is
``57 + 40 = 97``, with ``24`` rows skipped for name resolution and ``7`` resolved
rows carrying no complete track interval. (If a future loader instead emits one
mix-side placement per resolved row regardless of a missing track endpoint, the
count is ``64 + 40 = 104``; a test must state which policy it asserts. This
iteration pins **97** complete claims and calls the other 7 out explicitly rather
than folding them in silently.)

---

## (f) What a correct claim looks like

**Ground truth.** A claim maps an **interval-on-mix** to an **interval-on-track**,
both in bar units.

**Concrete non-loop row — ``01. See Me Coming`` (first entry).**
``track [1, 89]``, ``mix [1, 89]``. The claim records the mix interval
``[1, 89]`` (88 bars) ↔ the track interval ``[1, 89]`` (88 bars). Endpoint
arithmetic: mix span ``89 − 1 = 88``; track span ``89 − 1 = 88``; equal length,
so this is a 1:1 pass with no stretch.

**Concrete non-loop row — ``01. See Me Coming`` (second entry).**
``track [121, 166]``, ``mix [89, 134]``. Claim: mix ``[89, 134]`` (45 bars) ↔
track ``[121, 166]`` (45 bars). Endpoint arithmetic: ``134 − 89 = 45`` and
``166 − 121 = 45`` — equal length again, but the track side jumps from bar 89 to
bar 121, i.e. this row skips 32 bars of the source before re-entering.

**Concrete loop row — ``13. TURN IT UP!``.** ``track [53, 61]``, ``mix [1121,
1137]``, ``track_loop = 2``. With ``L = (1137 − 1121) / 2 = 8`` (= the track span
``61 − 53``), the row expands to exactly two adjacent, equal-length claims, both
naming the **same** track interval:

- claim 1: mix ``[1121, 1129]`` ↔ track ``[53, 61]``;
- claim 2: mix ``[1129, 1137]`` ↔ track ``[53, 61]``.

They abut at bar 1129 and together cover ``[1121, 1137]``. A correct claim carries
both bar-unit intervals and their orientation (which axis is mix, which is track);
loop expansion must preserve the shared track interval across all N copies.
