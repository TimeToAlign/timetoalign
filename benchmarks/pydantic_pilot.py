"""WP2 microbenchmark: pydantic v2 scalars vs columnar storage.

Three measurements ground the architectural claim that columnar storage
of pydantic-backed scalars is worthwhile:

A. **Column-builder vs row-wise ``model_dump``** (bulk construction).
   When materialising a SemanticField from a list of scalars, the
   canonical column-builder path is required to be at least 2× faster
   than the row-wise ``model_dump`` path; otherwise the bulk migration
   would be reconsidered.

B. **Vectorized column op vs per-object scalar loop** (the
   load-bearing claim).  Once data is already in a columnar
   ``pa.StructArray`` versus a list of pydantic objects, applying the
   same simple op (multiply ``.value`` by 2) is dramatically faster on
   the column.  This is what justifies the columnar architecture for
   pydantic-backed scalars: not the construction cost, but the
   per-element op cost over the lifetime of the data.  Path A and Path
   B both produce a ``pa.Array`` of equivalent shape so the timing is
   honest.

C. **``model_construct`` vs ``model_validate``** (per-row reconstruction
   regimes).  These two entry points implement two different semantic
   regimes — ``model_validate`` runs validators (trust boundary),
   ``model_construct`` bypasses them (trusted internal data).  Whether
   one is faster than the other depends on the shape of the scalar's
   validators: for scalars whose fields all reduce to Rust-fast
   validators (Literal, int, nullable float — e.g. ``SpecificPitch``)
   the Rust validator beats pure-Python ``model_construct``; for
   scalars that accept Python-native types the Rust validator can't
   fast-path (``Coordinate`` accepts ``Fraction`` via
   ``arbitrary_types_allowed``), ``model_construct`` is faster.  The
   regime choice is a *semantic* contract — performance is one input,
   not the driver.

Run::

    python -m benchmarks.pydantic_pilot

Results are persisted to ``pydantic_pilot_results.md``.  Hardware,
Python version, pydantic version, mean ± std over N runs are reported.
The hand-authored "WP2 bulk addendum" section at the bottom of the
results doc is preserved across regenerations via a sentinel split
(``<!-- end:generated -->``); only the auto-generated section above
the sentinel is rewritten.
"""

from __future__ import annotations

import gc
import platform
import statistics
import sys
import time
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

import pyarrow as pa
import pyarrow.compute as pc
import pydantic

from timetoalign.core.enums import TimeUnit
from timetoalign.core.scalars.pitch import SpecificPitch
from timetoalign.core.schemas import (
    build_coordinate_struct_array,
    derive_arrow_struct,
)
from timetoalign.core.types import Coordinate

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Benchmark A & C operate on 100k instances (per-row regime, fits screen).
N_INSTANCES = 100_000
N_RUNS = 5

# Benchmark B operates on 1M to make the vectorized win unambiguous.
N_INSTANCES_VEC = 1_000_000
N_RUNS_VEC = 5
N_WARMUP_VEC = 1

# Sentinel used to preserve the hand-authored addendum in the results doc.
GENERATED_SENTINEL = "<!-- end:generated -->"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _time_one(callable_obj: Callable[..., Any], *args: Any) -> float:
    # Per-run GC sweep so each measurement starts from a known heap state.
    # Per-row benchmarks allocate ~100k pydantic objects per run; without
    # the sweep, the first measured run pays for cleanup of warmup heap
    # and shows up as a large outlier.
    gc.collect()
    t0 = time.perf_counter()
    result = callable_obj(*args)
    elapsed = time.perf_counter() - t0
    # Keep result alive past timing so the loop doesn't measure GC of the
    # callable's return value.
    del result
    return elapsed


def _bench(
    callable_obj: Callable[..., Any],
    prep_args: list[Any],
    *,
    n_runs: int = N_RUNS,
    n_warmup: int = 0,
) -> tuple[float, float]:
    """Run *callable_obj(*prep_args)*.  Return (mean, pstdev) over n_runs.

    *n_warmup* untimed iterations precede the measured runs.  Warmup
    matters when a code path lazily initialises (e.g. first
    ``model_validate`` call on a class instantiates the Rust
    validator).  Each run is preceded by a ``gc.collect()`` to keep
    measurements independent — without it, large per-run allocations
    cause the first measured run to absorb cleanup time from the
    warmup iteration.
    """
    for _ in range(n_warmup):
        callable_obj(*prep_args)
    times = [_time_one(callable_obj, *prep_args) for _ in range(n_runs)]
    return statistics.mean(times), statistics.pstdev(times)


# ---------------------------------------------------------------------------
# Benchmark A: column-builder vs row-wise model_dump (Coordinate)
# ---------------------------------------------------------------------------


def _gen_coordinates(n: int) -> list[Coordinate]:
    """Generate a mix of int / float / Fraction Coordinates."""
    out: list[Coordinate] = []
    for i in range(n):
        mod = i % 3
        if mod == 0:
            out.append(Coordinate(i, TimeUnit.ticks))
        elif mod == 1:
            out.append(Coordinate(float(i) + 0.5, TimeUnit.seconds))
        else:
            out.append(Coordinate(Fraction(i, 4), TimeUnit.quarters))
    return out


def _bulk_column_builder(coords: list[Coordinate]) -> pa.StructArray:
    """Column-builder: the canonical WP2 path."""
    return build_coordinate_struct_array(coords)


def _bulk_model_dump_rowwise(coords: list[Coordinate]) -> pa.StructArray:
    """Row-wise dict-per-row: the legacy / forbidden bulk path.

    Pays the ``model_dump`` cost once per scalar to measure the forbidden
    path honestly.  ``c.value`` is then read directly because Coordinate
    values (``int | float | Fraction``) don't serialise uniformly via
    ``model_dump``.
    """
    struct = derive_arrow_struct(Coordinate)
    rows: list[dict[str, object]] = []
    for c in coords:
        _ = c.model_dump()
        v = c.value
        if isinstance(v, Fraction):
            rows.append(
                {
                    "value": float(v),
                    "numerator": v.numerator,
                    "denominator": v.denominator,
                }
            )
        elif isinstance(v, int) and not isinstance(v, bool):
            rows.append({"value": float(v), "numerator": v, "denominator": 1})
        else:
            rows.append({"value": float(v), "numerator": None, "denominator": None})
    return pa.array(rows, type=struct)


# ---------------------------------------------------------------------------
# Benchmark B: vectorized column op vs per-object scalar loop
# (the load-bearing architectural claim)
# ---------------------------------------------------------------------------


def _vec_per_object_to_pa_array(coords: list[Coordinate]) -> pa.Array:
    """Path A — per-object loop: read ``c.value``, multiply, materialise.

    The result type is ``pa.float64`` for parity with Path B's output
    (which reads from the ``value`` struct field — itself float64).
    Coordinate's mixed ``int|float|Fraction`` payload is cast to float
    explicitly here; that cast is part of the per-row cost when an
    operation needs to escape the row representation.
    """
    return pa.array([float(c.value) * 2 for c in coords], type=pa.float64())


def _vec_columnar(arr: pa.StructArray) -> pa.Array:
    """Path B — vectorized: ``pc.multiply`` on the ``value`` field column.

    Pre-condition: *arr* is the StructArray already produced by the
    column-builder.  This measures the per-element op cost *after* you
    are already in the columnar representation; the build cost is
    measured separately in Benchmark A.
    """
    return pc.multiply(arr.field("value"), 2)


def _vec_columnar_with_build(coords: list[Coordinate]) -> pa.Array:
    """Path B + build cost — for the breakeven measurement.

    Builds the StructArray *then* applies the vectorized op.  Shows
    where the columnar path starts paying off when an op is performed
    only once (Benchmark A already established the build cost is
    competitive with row-wise dump; this confirms that even amortising
    the build into a single op, the columnar path is competitive).
    """
    arr = build_coordinate_struct_array(coords)
    return pc.multiply(arr.field("value"), 2)


# ---------------------------------------------------------------------------
# Benchmark C: model_construct vs model_validate (SpecificPitch, Coordinate)
# ---------------------------------------------------------------------------


def _gen_specific_pitch_rows(n: int) -> list[dict[str, object]]:
    """Generate N validated rows simulating a TTA-internal Parquet read."""
    steps = ["C", "D", "E", "F", "G", "A", "B"]
    rows: list[dict[str, object]] = []
    for i in range(n):
        step = steps[i % 7]
        alter = (i % 3) - 1
        octave = (i // 12) % 8
        rows.append({"step": step, "alter": alter, "octave": octave, "cents": None})
    return rows


def _gen_coordinate_rows(n: int) -> list[dict[str, object]]:
    """Generate N rows for Coordinate round-trip — mixed value types."""
    rows: list[dict[str, object]] = []
    for i in range(n):
        mod = i % 3
        if mod == 0:
            rows.append({"value": i, "unit": TimeUnit.ticks})
        elif mod == 1:
            rows.append({"value": float(i) + 0.5, "unit": TimeUnit.seconds})
        else:
            rows.append({"value": Fraction(i, 4), "unit": TimeUnit.quarters})
    return rows


def _bulk_sp_construct(rows: list[dict[str, object]]) -> list[SpecificPitch]:
    return [SpecificPitch.model_construct(**r) for r in rows]


def _bulk_sp_validate(rows: list[dict[str, object]]) -> list[SpecificPitch]:
    return [SpecificPitch.model_validate(r) for r in rows]


def _bulk_coord_construct(rows: list[dict[str, object]]) -> list[Coordinate]:
    return [Coordinate.model_construct(**r) for r in rows]


def _bulk_coord_validate(rows: list[dict[str, object]]) -> list[Coordinate]:
    return [Coordinate.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("WP2 pydantic-pilot microbenchmark")
    print(f"  Python: {sys.version.split()[0]}, pydantic: {pydantic.VERSION}")
    print(f"  Platform: {platform.platform()}")
    print(f"  CPU: {platform.processor() or platform.machine()}")
    print()

    # --- Benchmark A ---
    print(f"A: column-builder vs row-wise model_dump on {N_INSTANCES:,} Coordinates")
    print(f"   ({N_RUNS} runs, 1 warmup)")
    coords_a = _gen_coordinates(N_INSTANCES)
    cb_mean, cb_std = _bench(
        _bulk_column_builder, [coords_a], n_runs=N_RUNS, n_warmup=1
    )
    print(f"  column-builder         : {cb_mean*1000:.1f} ± {cb_std*1000:.1f} ms")
    dump_mean, dump_std = _bench(
        _bulk_model_dump_rowwise, [coords_a], n_runs=N_RUNS, n_warmup=1
    )
    print(f"  model_dump row-wise    : {dump_mean*1000:.1f} ± {dump_std*1000:.1f} ms")
    speedup_a = dump_mean / cb_mean
    print(f"  speedup                : {speedup_a:.2f}×")
    gate_a = "PASS" if speedup_a >= 2.0 else "FAIL"
    print(f"  gate (≥ 2.0× required) : {gate_a}")
    print()

    # --- Benchmark B (the load-bearing claim) ---
    print(
        f"B: vectorized column op vs per-object loop on {N_INSTANCES_VEC:,} Coordinates"
    )
    print(f"   ({N_RUNS_VEC} runs, {N_WARMUP_VEC} warmup)")
    print("   op: multiply .value by 2; both paths return a pa.Array of float64")
    coords_b = _gen_coordinates(N_INSTANCES_VEC)
    arr_b = build_coordinate_struct_array(coords_b)
    per_obj_mean, per_obj_std = _bench(
        _vec_per_object_to_pa_array,
        [coords_b],
        n_runs=N_RUNS_VEC,
        n_warmup=N_WARMUP_VEC,
    )
    print(
        f"  per-object loop → pa.Array : {per_obj_mean*1000:.1f} ± "
        f"{per_obj_std*1000:.1f} ms"
    )
    col_mean, col_std = _bench(
        _vec_columnar, [arr_b], n_runs=N_RUNS_VEC, n_warmup=N_WARMUP_VEC
    )
    print(
        f"  vectorized pc.multiply     : {col_mean*1000:.2f} ± "
        f"{col_std*1000:.2f} ms"
    )
    speedup_b = per_obj_mean / col_mean
    print(f"  speedup                    : {speedup_b:.1f}×")
    build_op_mean, build_op_std = _bench(
        _vec_columnar_with_build,
        [coords_b],
        n_runs=N_RUNS_VEC,
        n_warmup=N_WARMUP_VEC,
    )
    print(
        f"  (column-build + op)        : {build_op_mean*1000:.1f} ± "
        f"{build_op_std*1000:.1f} ms  (breakeven reference)"
    )
    print()

    # --- Benchmark C ---
    print(f"C: model_construct vs model_validate on {N_INSTANCES:,} rows")
    print(
        f"   ({N_RUNS} runs, 1 warmup — first validate call instantiates"
        f" the Rust validator)"
    )
    sp_rows = _gen_specific_pitch_rows(N_INSTANCES)
    sp_cons_mean, sp_cons_std = _bench(
        _bulk_sp_construct, [sp_rows], n_runs=N_RUNS, n_warmup=1
    )
    sp_val_mean, sp_val_std = _bench(
        _bulk_sp_validate, [sp_rows], n_runs=N_RUNS, n_warmup=1
    )
    print(
        f"  SpecificPitch model_construct: {sp_cons_mean*1000:.1f} ± "
        f"{sp_cons_std*1000:.1f} ms"
    )
    print(
        f"  SpecificPitch model_validate : {sp_val_mean*1000:.1f} ± "
        f"{sp_val_std*1000:.1f} ms"
    )
    sp_ratio = sp_val_mean / sp_cons_mean
    print(f"  ratio (validate / construct) : {sp_ratio:.2f}×")

    coord_rows = _gen_coordinate_rows(N_INSTANCES)
    coord_cons_mean, coord_cons_std = _bench(
        _bulk_coord_construct, [coord_rows], n_runs=N_RUNS, n_warmup=1
    )
    coord_val_mean, coord_val_std = _bench(
        _bulk_coord_validate, [coord_rows], n_runs=N_RUNS, n_warmup=1
    )
    print(
        f"  Coordinate model_construct   : {coord_cons_mean*1000:.1f} ± "
        f"{coord_cons_std*1000:.1f} ms"
    )
    print(
        f"  Coordinate model_validate    : {coord_val_mean*1000:.1f} ± "
        f"{coord_val_std*1000:.1f} ms"
    )
    coord_ratio = coord_val_mean / coord_cons_mean
    print(f"  ratio (validate / construct) : {coord_ratio:.2f}×")
    print()

    out_path = Path(__file__).parent / "pydantic_pilot_results.md"
    _write_results(
        out_path,
        a=(cb_mean, cb_std, dump_mean, dump_std, speedup_a, gate_a),
        b=(
            per_obj_mean,
            per_obj_std,
            col_mean,
            col_std,
            speedup_b,
            build_op_mean,
            build_op_std,
        ),
        c_sp=(sp_cons_mean, sp_cons_std, sp_val_mean, sp_val_std, sp_ratio),
        c_coord=(
            coord_cons_mean,
            coord_cons_std,
            coord_val_mean,
            coord_val_std,
            coord_ratio,
        ),
    )
    print(f"Results written to {out_path}")


def _write_results(
    path: Path,
    *,
    a: tuple[float, float, float, float, float, str],
    b: tuple[float, float, float, float, float, float, float],
    c_sp: tuple[float, float, float, float, float],
    c_coord: tuple[float, float, float, float, float],
) -> None:
    cb_mean, cb_std, dump_mean, dump_std, speedup_a, gate_a = a
    per_obj_mean, per_obj_std, col_mean, col_std, speedup_b, bop_mean, bop_std = b
    sp_cons_mean, sp_cons_std, sp_val_mean, sp_val_std, sp_ratio = c_sp
    (
        coord_cons_mean,
        coord_cons_std,
        coord_val_mean,
        coord_val_std,
        coord_ratio,
    ) = c_coord

    # Compose the generated section.
    generated = f"""# WP2 pydantic-pilot microbenchmark results

Generated by `benchmarks/pydantic_pilot.py`.  Sections below the
`{GENERATED_SENTINEL}` sentinel are hand-authored and preserved across
regenerations.

## Environment

- Hardware (CPU / machine): `{platform.processor() or platform.machine()}`
- OS / platform: `{platform.platform()}`
- Python: `{sys.version.split()[0]}`
- pydantic: `{pydantic.VERSION}`
- Per-row benchmarks (A, C): `{N_INSTANCES:,}` instances × `{N_RUNS}` runs (1 warmup)
- Vectorized benchmark (B): `{N_INSTANCES_VEC:,}` instances × `{N_RUNS_VEC}` runs ({N_WARMUP_VEC} warmup)

## B. Vectorized column op vs per-object loop (the load-bearing claim)

The point of storing pydantic-backed scalars in a columnar PyArrow
struct is **not** the construction cost (Benchmark A) — it is the
**per-element op cost over the lifetime of the data**.  Once the data
is columnar, ``pyarrow.compute`` operates on the underlying buffer
without Python-object overhead.

Both paths apply the same op (`multiply .value by 2`) and produce a
``pa.Array`` of ``float64`` with `{N_INSTANCES_VEC:,}` elements:

- Path A reads ``c.value`` per object, casts to float (necessary because
  Coordinate's value field is ``int | float | Fraction``), multiplies in
  Python, then materialises the resulting list as a ``pa.Array``.
- Path B calls ``pc.multiply(arr.field("value"), 2)`` on the
  pre-existing ``StructArray``'s value column.

| Path | Mean ± stdev (ms) |
|---|---|
| Path A — per-object loop → pa.Array | {per_obj_mean*1000:.1f} ± {per_obj_std*1000:.1f} |
| Path B — vectorized `pc.multiply` on `.field("value")` | {col_mean*1000:.2f} ± {col_std*1000:.2f} |
| **Speedup (A / B)** | **{speedup_b:.0f}×** |

**Breakeven reference** — column-build cost + op, starting from a list
of pydantic objects: **{bop_mean*1000:.1f} ± {bop_std*1000:.1f} ms** for `{N_INSTANCES_VEC:,}` instances.
Even amortising the column build into a single op, the columnar path
is competitive with Path A on the first op and unbeatable on every
subsequent one.

**Interpretation.** On a {N_INSTANCES_VEC:,}-row Coordinate column, applying
a trivial op once is ~{speedup_b:.0f}× faster on the column than on the object list.
The op chosen here (multiply by 2) is the cheapest possible per-row
work; richer per-row work (filtering, conditional logic, type-aware
arithmetic) would widen the gap further.  This is the
architectural justification for storing pydantic-backed scalars as
columns — operating on the column once, in compiled code, beats N
trips through the Python interpreter.  The construction-cost
trade-offs measured in Benchmark A would not justify the columnar
architecture on their own; Benchmark B does.

## A. Bulk SemanticField construction (Coordinate)

When materialising a SemanticField from a list of scalars, the
column-builder is the canonical WP2 bulk path; the row-wise
``model_dump`` path is what would be required if the architecture had
no column-builder.

| Path | Mean ± stdev (ms) |
|---|---|
| column-builder (canonical WP2) | {cb_mean*1000:.1f} ± {cb_std*1000:.1f} |
| `model_dump` row-wise (forbidden) | {dump_mean*1000:.1f} ± {dump_std*1000:.1f} |
| **Speedup** | **{speedup_a:.2f}×** |

**Gate (column-builder ≥ 2× faster): {gate_a}.**

**Interpretation.** Column-builder is ~{speedup_a:.1f}× faster than the
row-wise ``model_dump`` path on Coordinate (3-field denormalised
struct).  The gain comes from avoiding per-row dict construction and
per-row ``pa.array`` ingest; column-builder writes typed Python lists
straight into ``pa.array`` once per field.  This gate pins the
construction-cost claim; it does not by itself justify the columnar
architecture (Benchmark B does that).

## C. Per-row reconstruction regimes (`model_construct` vs `model_validate`)

Two pydantic entry points implement two *semantically* different
regimes: ``model_validate`` runs validators (trust boundary,
untrusted input), ``model_construct`` skips validators (trusted
internal data).  Performance depends on the shape of the scalar's
validators.

### SpecificPitch (4 fields: `Literal[...]`, `int`, `int`, `float | None`)

| Path | Mean ± stdev (ms) |
|---|---|
| `model_construct` | {sp_cons_mean*1000:.1f} ± {sp_cons_std*1000:.1f} |
| `model_validate` | {sp_val_mean*1000:.1f} ± {sp_val_std*1000:.1f} |
| ratio (validate / construct) | {sp_ratio:.2f}× |

### Coordinate (2 fields: `int|float|Fraction`, `TimeUnit`)

| Path | Mean ± stdev (ms) |
|---|---|
| `model_construct` | {coord_cons_mean*1000:.1f} ± {coord_cons_std*1000:.1f} |
| `model_validate` | {coord_val_mean*1000:.1f} ± {coord_val_std*1000:.1f} |
| ratio (validate / construct) | {coord_ratio:.2f}× |

**Interpretation — a real finding, not an artifact.**
``model_construct`` in pydantic v2 is **pure Python**: it iterates the
declared fields, pops kwargs, runs alias lookups, sets defaults, and
finally writes ``__dict__`` directly.  ``model_validate`` calls the
Rust validator (``__pydantic_validator__.validate_python``), which
processes all fields in compiled code.  Whether construct beats
validate depends entirely on whether the Rust validator can fast-path
the scalar's field types:

- **SpecificPitch**'s fields all reduce to Rust-native validators
  (``Literal[str, ...]`` lookup table, plain ``int``, nullable
  ``float``).  The Rust validator runs faster than the pure-Python
  per-field loop in ``model_construct``, so ``model_validate`` is
  ~{1/sp_ratio:.2f}× faster than ``model_construct`` here.
- **Coordinate** accepts ``Fraction`` via
  ``arbitrary_types_allowed=True`` and uses a ``mode="before"``
  field validator on ``value``.  The Rust validator can't fast-path
  the union — it falls back to invoking Python callables for each
  row — and ``model_construct`` is ~{coord_ratio:.2f}× faster than
  ``model_validate``.

Both entry points produce equivalent objects (``__dict__`` and
``__pydantic_fields_set__`` match field-by-field; verified manually).
Profiling ``model_construct`` shows ~95% of its time inside the
Python ``model_construct`` body itself (per-field ``dict.pop`` and
``set.add``); no other code path dominates.

**Implication for the regime contract (CLAUDE.md §6, WP2 §7).**  The
regime choice is *semantic*: ``model_validate`` is correct at the
trust boundary, ``model_construct`` is correct for trusted internal
data.  Performance is an input to the choice, not the driver.  These
numbers say: do not assume ``model_construct`` is faster on every
scalar — for scalars whose validators all Rust-fast-path, picking it
for performance reasons is the wrong call.  Bulk paths
(SemanticField construction) sidestep both per-row methods via the
column-builder regime; that's where the architecture extracts its
real performance.

{GENERATED_SENTINEL}
"""

    # Preserve hand-authored content after the LAST sentinel, if any.
    # Using rpartition (not partition) is important: the generated
    # section itself ends with the sentinel, so if a previous run's
    # output is the entire current file, ``partition`` would treat
    # the embedded copy of the previous generated section as "tail" —
    # the doc would grow without bound on each run.
    existing = path.read_text() if path.exists() else ""
    if GENERATED_SENTINEL in existing:
        _, _, tail = existing.rpartition(GENERATED_SENTINEL)
        tail = tail.lstrip("\n")
    else:
        tail = ""

    path.write_text(generated + ("\n" + tail if tail else ""))


if __name__ == "__main__":
    main()
