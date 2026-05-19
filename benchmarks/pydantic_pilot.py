"""WP2 microbenchmark: pydantic v2 pilot scalars on 100k instances.

Two measurements drive the gate decision before the bulk migration:

A. **Column-builder vs row-wise ``model_dump``** (bulk SemanticField
   construction).  Per the WP2 plan, column-builder MUST be at least
   2× faster on 100k Coordinate instances; otherwise the bulk migration
   is reconsidered.

B. **``model_construct`` vs ``model_validate``** (internal round-trip
   reconstruction from a list of dicts).  Establishes the speedup
   that justifies the "trust the pa.Schema" stance for TTA-internal
   Parquet round-trips.

The results are persisted to ``pydantic_pilot_results.md``.

Run::

    python -m benchmarks.pydantic_pilot

The script reports hardware (CPU + OS), Python version, pydantic
version, mean ± std over N runs, and a single-line conclusion.
"""

from __future__ import annotations

import platform
import statistics
import sys
import time
from fractions import Fraction
from pathlib import Path

import pyarrow as pa
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

N_INSTANCES = 100_000
N_RUNS = 5

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

    For benchmark parity we project each scalar onto the denormalised
    storage shape via a row dict, then call ``pa.array(rows, type=...)``.
    This is the work that would have to happen if bulk SemanticField
    construction routed through ``model_dump``-style row materialisation
    instead of the column-builder pattern.

    ``model_dump`` itself is invoked once per scalar to measure its
    overhead; the resulting dict's ``value`` field is unused (Coordinate's
    value type ``int | float | Fraction`` doesn't serialise uniformly via
    ``model_dump``).  We pull ``c.value`` directly afterwards.
    """
    struct = derive_arrow_struct(Coordinate)
    rows: list[dict[str, object]] = []
    for c in coords:
        # Pay the ``model_dump`` cost to measure the forbidden path
        # honestly.  The result is discarded; ``c.value`` is the real
        # source.
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
# Benchmark B: model_construct vs model_validate (SpecificPitch)
# ---------------------------------------------------------------------------


def _gen_specific_pitch_rows(n: int) -> list[dict[str, object]]:
    """Generate N validated rows simulating a TTA-internal Parquet read."""
    steps = ["C", "D", "E", "F", "G", "A", "B"]
    rows: list[dict[str, object]] = []
    for i in range(n):
        step = steps[i % 7]
        alter = (i % 3) - 1  # -1, 0, +1
        octave = (i // 12) % 8
        rows.append({"step": step, "alter": alter, "octave": octave, "cents": None})
    return rows


def _bulk_model_construct(rows: list[dict[str, object]]) -> list[SpecificPitch]:
    """Internal-round-trip regime: bypass validators."""
    return [SpecificPitch.model_construct(**r) for r in rows]


def _bulk_model_validate(rows: list[dict[str, object]]) -> list[SpecificPitch]:
    """Trust-boundary regime: validators run on every row."""
    return [SpecificPitch.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _time_one(callable_obj, *args) -> float:  # type: ignore[no-untyped-def]
    t0 = time.perf_counter()
    callable_obj(*args)
    return time.perf_counter() - t0


def _bench(name: str, callable_obj, prep_args) -> tuple[float, float]:  # type: ignore[no-untyped-def]
    """Run *callable_obj(*prep_args)* N_RUNS times; return (mean, stdev)."""
    times = [_time_one(callable_obj, *prep_args) for _ in range(N_RUNS)]
    return statistics.mean(times), statistics.pstdev(times)


def main() -> None:
    print(f"WP2 pydantic-pilot microbenchmark — {N_INSTANCES} instances, {N_RUNS} runs")
    print(f"  Python: {sys.version.split()[0]}, pydantic: {pydantic.VERSION}")
    print(f"  Platform: {platform.platform()}")
    print(f"  CPU: {platform.processor() or platform.machine()}")
    print()

    # --- Benchmark A ---
    coords = _gen_coordinates(N_INSTANCES)
    print(f"A: column-builder vs row-wise model_dump on {N_INSTANCES} Coordinates")
    cb_mean, cb_std = _bench("column-builder", _bulk_column_builder, [coords])
    print(f"  column-builder         : {cb_mean*1000:.1f} ± {cb_std*1000:.1f} ms")
    dump_mean, dump_std = _bench("model_dump", _bulk_model_dump_rowwise, [coords])
    print(f"  model_dump row-wise    : {dump_mean*1000:.1f} ± {dump_std*1000:.1f} ms")
    speedup_a = dump_mean / cb_mean
    print(f"  speedup                : {speedup_a:.2f}×")
    gate_a = "PASS" if speedup_a >= 2.0 else "FAIL"
    print(f"  gate (≥ 2.0× required) : {gate_a}")
    print()

    # --- Benchmark B ---
    rows = _gen_specific_pitch_rows(N_INSTANCES)
    print(f"B: model_construct vs model_validate on {N_INSTANCES} SpecificPitch rows")
    cons_mean, cons_std = _bench("model_construct", _bulk_model_construct, [rows])
    print(f"  model_construct        : {cons_mean*1000:.1f} ± {cons_std*1000:.1f} ms")
    valid_mean, valid_std = _bench("model_validate", _bulk_model_validate, [rows])
    print(f"  model_validate         : {valid_mean*1000:.1f} ± {valid_std*1000:.1f} ms")
    speedup_b = valid_mean / cons_mean
    print(f"  speedup                : {speedup_b:.2f}×")
    print()

    # --- Persist results ---
    out_path = Path(__file__).parent / "pydantic_pilot_results.md"
    _write_results(
        out_path,
        coords_results=(cb_mean, cb_std, dump_mean, dump_std, speedup_a, gate_a),
        sp_results=(cons_mean, cons_std, valid_mean, valid_std, speedup_b),
    )
    print(f"Results written to {out_path}")


def _write_results(  # type: ignore[no-untyped-def]
    path: Path,
    *,
    coords_results,
    sp_results,
) -> None:
    cb_mean, cb_std, dump_mean, dump_std, speedup_a, gate_a = coords_results
    cons_mean, cons_std, valid_mean, valid_std, speedup_b = sp_results
    gate_b_note = (
        "model_construct < model_validate"
        if speedup_b < 1.0
        else "model_construct >= model_validate"
    )
    conclusion = (
        "**WP2 GATE A PASSES — bulk pydantic migration justified.** "
        "Column-builder is ≥ 2× faster than row-wise `model_dump` for the "
        "Coordinate scalar, so the column-builder pattern is the canonical "
        "bulk path for the 15+ scalars in the bulk migration."
        if gate_a == "PASS"
        else "**WP2 GATE A FAILS — column-builder speedup below the 2× threshold.** "
        "Reconsider before scaling the migration to 15+ scalar types."
    )
    benchmark_b_note = (
        "**Surprise:** `model_construct` is SLOWER than `model_validate` on "
        "this scalar.  Pydantic v2's `model_validate` calls into an optimised "
        "Rust validator; `model_construct` runs pure Python and on a frozen "
        "model pays per-field `__setattr__` overhead. The implication: "
        "internal-round-trip reads should NOT routinely call `model_construct` "
        "per row when `model_validate` is available — the design assumption "
        "(construct is faster) does not hold for this pydantic / scalar shape.  "
        "Per WP2's locked regime contract, `model_construct` remains the "
        "correct semantic choice for trusted internal data (it bypasses "
        "validation), but its performance benefit on this scalar shape is "
        "negative.  This is flagged for the bulk-migration commission to "
        "reconsider before standardising the regime call sites."
        if speedup_b < 1.0
        else "`model_construct` outpaces `model_validate` as expected — the "
        "internal-round-trip regime is justified on both semantic AND "
        "performance grounds."
    )
    content = f"""# WP2 pydantic-pilot microbenchmark results

Generated by `benchmarks/pydantic_pilot.py`.

## Environment

- Hardware (CPU / machine): `{platform.processor() or platform.machine()}`
- OS / platform: `{platform.platform()}`
- Python: `{sys.version.split()[0]}`
- pydantic: `{pydantic.VERSION}`
- Instances per run: `{N_INSTANCES:,}`
- Runs averaged: `{N_RUNS}`

## A. Bulk SemanticField construction (Coordinate)

| Path                                | Mean ± stdev (ms) |
|-------------------------------------|-------------------|
| column-builder (canonical WP2)      | {cb_mean*1000:.1f} ± {cb_std*1000:.1f} |
| `model_dump` row-wise (forbidden)   | {dump_mean*1000:.1f} ± {dump_std*1000:.1f} |
| Speedup                             | **{speedup_a:.2f}×** |

**Gate (column-builder ≥ 2× faster): {gate_a}.**

## B. Internal round-trip reconstruction (SpecificPitch)

| Path             | Mean ± stdev (ms) |
|------------------|-------------------|
| `model_construct` (internal round-trip regime) | {cons_mean*1000:.1f} ± {cons_std*1000:.1f} |
| `model_validate` (trust-boundary regime)       | {valid_mean*1000:.1f} ± {valid_std*1000:.1f} |
| Speedup                                        | **{speedup_b:.2f}×** ({gate_b_note}) |

{benchmark_b_note}

## Conclusion

{conclusion}
"""
    path.write_text(content)


if __name__ == "__main__":
    main()
