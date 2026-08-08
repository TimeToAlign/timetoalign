# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.3
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Inspect, Correct, and Re-Define Flows for Brazilian Choros
#
# For a full API tour, see `tut07_flow_and_grids.ipynb`. The condensed primer below covers
# only what is needed to read the inspection cells in this notebook.
#
# A score is **folded** — repeated sections appear once on the page but play
# multiple times in performance. A performance is **unfolded** — every event
# occupies a unique time point. Two primitives encode this structure, both parsed
# automatically from score files (you never construct them by hand):
#
# - **Break** — voids {{< glossary Contiguity >}} at a coordinate; no
#   {{< glossary TimeInterval >}} may span it (`section_break`, `fine`).
# - **Jump** — makes two non-adjacent coordinates contiguous (`repeat_end`,
#   `da_capo`, `dal_segno`, `to_coda`, and their *al coda* / *al fine* variants).
#
# The `FlowControlElement` enum lists the full vocabulary; the predicates
# `is_jump`, `is_break`, `is_target`, and `is_structural_marker` filter members.
#
# A **FlowMap** is the bidirectional coordinate transform derived from a chosen
# `FlowMode`. `unfold_coordinate(coord)` returns a list of unfolded positions (≥1);
# `fold(coord)` returns a single folded coordinate.
# `FlowMap.from_qb_sections(flow, qb_sections)` is the entry point for manual
# correction or non-standard interpretations.
#
# This notebook inspects three Choros scores. Each piece's section ends by
# exporting all of its available flows to a CSV under the corpus `flows/` directory.

# %% [markdown]
# ## Setup

# %%
from fractions import Fraction
from pathlib import Path

import pandas as pd

from timetoalign import Ms3Loader, __version__
from timetoalign.core.enums import FlowMode
from timetoalign.timelines.flow import compute_qb_sections

DATA_DIR = Path("~/git/brazilian_flows").expanduser()


def make_paths(name: str, data_dir: Path = DATA_DIR) -> tuple[Path, Path]:
    """Return ``(notes_tsv, measures_tsv)`` paths for a Brazilian Choros score basename."""
    return (
        data_dir / "notes" / f"{name}.notes.tsv",
        data_dir / "measures" / f"{name}.measures.tsv",
    )


def load_controller(name: str):
    """Build a ``ScoreFlowController`` from the score's measures TSV."""
    _, measures = make_paths(name)
    return Ms3Loader.from_file(measures).create_flow_controller()


def boundaries_summary(controller) -> dict:
    """Atomic-section count and break positions in QB."""
    boundaries = controller.get_section_boundary_coordinates()
    return {
        "n_atomic_sections": len(boundaries) + 1,
        "break_positions_qb": [float(b) for b in boundaries],
    }


SKIPPED_FLOW_MODES = {
    FlowMode.atomic,  # subsumed by `printed` in this 3-column view; finer structure shown by qb_sections_table
    FlowMode.music21,
    FlowMode.custom,
    FlowMode.partitura_minimal,
    FlowMode.partitura_maximal,
}


def flow_modes_table(controller) -> pd.DataFrame:
    """One row per ``FlowMode`` (excluding `SKIPPED_FLOW_MODES`): folded/unfolded length or raised exception."""
    rows = []
    for mode in FlowMode:
        if mode in SKIPPED_FLOW_MODES:
            continue
        try:
            flow = controller.compute_flow(mode)
            rows.append(
                {
                    "mode": mode.value,
                    "folded_qb": flow.folded_length,
                    "unfolded_qb": flow.unfolded_length,
                    "has_repeats": flow.has_repeats,
                }
            )
        except Exception as exc:
            rows.append({"mode": mode.value, "error": str(exc)})
    return pd.DataFrame(rows)


def qb_sections_table(controller, mode: FlowMode = FlowMode.default) -> pd.DataFrame:
    """QB section boundaries that ``create_flow_map_for_mode(mode)`` would use."""
    flow = controller.compute_flow(mode)
    sections = compute_qb_sections(flow, controller)
    return pd.DataFrame(
        [
            {"section": i, "qb_start": float(s), "qb_end": float(e)}
            for i, (s, e) in enumerate(sections)
        ]
    )


def diagnostics_table(controller, mode: FlowMode = FlowMode.default) -> pd.DataFrame:
    """One row per traversal diagnostic from ``flow_diagnostics(mode)``; empty when the flow traverses cleanly."""
    diagnostics = controller.flow_diagnostics(mode)
    if not diagnostics:
        return pd.DataFrame(columns=["kind", "section_id", "mc", "message"])
    return pd.DataFrame(
        [
            {
                "kind": d.kind,
                "section_id": d.section_id,
                "mc": d.mc,
                "message": d.message,
            }
            for d in diagnostics
        ]
    )


def export_flows(controller, name: str) -> Path:
    """Write every available flow to ``{DATA_DIR}/flows/{name}.csv`` in `.flow.csv` format.

    One block of rows per `FlowMode` not in `SKIPPED_FLOW_MODES`, using the
    library's canonical `Flow.to_csv_rows()` serialisation (columns:
    ``flow_mode``, ``source_file``, ``software_version``, ``mc_start``,
    ``mc_end``, ``atomic_sections``).
    """
    _, measures = make_paths(name)
    software_version = f"timetoalign {__version__}"
    rows = []
    for mode in FlowMode:
        if mode in SKIPPED_FLOW_MODES:
            continue
        flow = controller.compute_flow(mode)
        rows.extend(flow.to_csv_rows(measures.name, software_version))
    out_path = DATA_DIR / "flows" / f"{name}.csv"
    pd.DataFrame(rows).to_csv(out_path, index=False)
    return out_path


# %% [markdown]
# ---
#
# ## score_1988-Ciume_e_brincadeira

# %%
piece_name = "score_1988-Ciume_e_brincadeira"
controller = load_controller(piece_name)
controller

# %%
boundaries_summary(controller)

# %%
controller.breaks

# %%
controller.jumps

# %%
controller.markers

# %%
flow_modes_table(controller)

# %%
qb_sections_table(controller)

# %%
# Export all available flows for this piece to {DATA_DIR}/flows/{piece_name}.csv.
export_flows(controller, piece_name)

# %% [markdown]
# ---
#
# ## score_1361-Medrosa-Anacleto_de_Medeiros

# %%
piece_name = "score_1361-Medrosa-Anacleto_de_Medeiros"
controller = load_controller(piece_name)
controller

# %%
boundaries_summary(controller)

# %%
controller.breaks

# %%
controller.jumps

# %%
controller.markers

# %%
flow_modes_table(controller)

# %%
qb_sections_table(controller)

# %%
# Export all available flows for this piece to {DATA_DIR}/flows/{piece_name}.csv.
export_flows(controller, piece_name)

# %% [markdown]
# ---
#
# ## score_133-Digitalis-Irineu_de_Almeida

# %%
piece_name = "score_133-Digitalis-Irineu_de_Almeida"
controller = load_controller(piece_name)
controller

# %%
boundaries_summary(controller)

# %%
controller.breaks

# %%
controller.jumps

# %%
controller.markers

# %%
flow_modes_table(controller)

# %%
qb_sections_table(controller)

# %%
# Export all available flows for this piece to {DATA_DIR}/flows/{piece_name}.csv.
export_flows(controller, piece_name)

# %% [markdown]
# ---
#
# ## Traversal diagnostics
#
# `check_invariants()` examines the folded atomic graph — the static section
# partition and its `to` edges. `flow_diagnostics()` is its traversal-time
# companion: it reports what surfaces only while the repeat-ends are resolved
# and the default flow is walked — a `flow_cycle` where a guard-disabled edge
# re-enters an already-visited MC and the walk would never terminate (the
# re-entered MC is named), the defensive `flow_nonconvergence` ceiling, an
# `ambiguous_repeat_end` where several open repeat scopes compete (the nearest
# is chosen), or a `dangling_repeat_end` whose `repeats=end` has no supported
# jump target. Like every diagnostic surface here, traversal reports rather than
# raises on a defective source: a malformed score still yields a Flow and a
# table of findings instead of an exception.
#
# The two surfaces are independent. A score whose folded graph satisfies every
# invariant can still fail to traverse, and a graph-level violation need not be
# what stops the walk — as the three scores below show.

# %%
diagnostics_table(load_controller("score_1988-Ciume_e_brincadeira"))

# %%
diagnostics_table(load_controller("score_1361-Medrosa-Anacleto_de_Medeiros"))

# %%
diagnostics_table(load_controller("score_133-Digitalis-Irineu_de_Almeida"))

# %% [markdown]
# `score_1361-Medrosa` traverses cleanly — its frame is empty. `score_1988-Ciume_e_brincadeira`
# is the case where the two surfaces diverge: `check_invariants()` finds nothing
# in the folded graph, yet the default flow reports a `flow_cycle`, because its
# D.S./D.C. edge re-enters an earlier MC with its jump guard already spent.
# `score_133-Digitalis` is the mislabeled-volta specimen: alongside the
# `volta_follows_volta` violations that `check_invariants()` reports for its
# folded graph, traversal adds a `dangling_repeat_end` — a `repeats=end` with no
# open repeat-start scope and no encoded backward edge, so no back-jump is
# produced and the resolution falls through. Neither surface repairs anything;
# both expose the source's under-determined flow for a subsequent reading to
# re-encode.

# %% [markdown]
# ---
#
# ## Demo: FlowMap and Timeline API
#
# Swap `demo_name` to inspect any of the three pieces above. The cells below
# build a controller, a `FlowMap`, and a timeline with multiple flow maps
# attached, then exercise `unfold_coordinate` / `fold` / `inverse`.

# %%
demo_name = "score_1988-Ciume_e_brincadeira"  # or score_1361-... / score_133-...

notes_demo, measures_demo = make_paths(demo_name)
loader_demo = Ms3Loader.from_file(notes_demo, measures_demo)
controller_demo = loader_demo.create_flow_controller()
flow_map = controller_demo.create_flow_map()  # DEFAULT mode
score_tl = loader_demo.create_timeline()
score_tl.add_flow_map(flow_map)
for mode in [FlowMode.printed, FlowMode.single, FlowMode.atomic]:
    score_tl.add_flow_map(controller_demo.create_flow_map_for_mode(mode), id=mode.value)

boundaries_demo = controller_demo.get_section_boundary_coordinates()
{
    "demo_name": demo_name,
    "n_sections": flow_map.n_sections,
    "total_target_length_qb": float(flow_map.total_target_length),
    "attached_maps": score_tl.list_flow_maps(),
}

# %%
# A folded coord inside the first repeated section appears at multiple unfolded positions.
coord = boundaries_demo[0] / 2 if boundaries_demo else Fraction(5)
unfolded = flow_map.unfold_coordinate(coord)
{
    "source_coord": float(coord),
    "unfolded_positions": [float(u) for u in unfolded],
    "n_appearances": len(unfolded),
}

# %%
# Every unfolded position folds back to the same source coord.
for target in unfolded:
    source = flow_map.fold(target)
    print(f"  unfolded {float(target):.3f}  ->  folded {float(source):.3f}")

# %%
# A coord beyond all repeats appears exactly once.
late_coord = flow_map.fold(flow_map.total_target_length - 1)
{
    "source_coord": float(late_coord),
    "n_appearances": len(flow_map.unfold_coordinate(late_coord)),
}

# %%
# Inverse map: swap source and target (useful for back-references into the score).
inverse_map = flow_map.inverse()
{
    "original_n_sections": flow_map.n_sections,
    "inverse_n_sections": inverse_map.n_sections,
    "inverse_source_length": float(inverse_map.total_target_length),
}

# %%
# The same folded coord behaves differently under each attached map.
sample_coord = float(boundaries_demo[0]) / 2 if boundaries_demo else 5.0
pd.DataFrame(
    [
        {
            "map_id": map_id,
            "n_appearances": len(score_tl.unfold_coordinate(sample_coord, id=map_id)),
        }
        for map_id in score_tl.list_flow_maps()
    ]
)

# %%
# Fold a specific unfolded position back to the score.
positions = score_tl.unfold_coordinate(sample_coord)
if len(positions) > 1:
    folded_back = score_tl.fold(positions[1])
    {"second_unfolded": positions[1], "folded_back": folded_back}
