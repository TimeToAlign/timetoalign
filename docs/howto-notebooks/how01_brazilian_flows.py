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
# For a full API tour, see `how01_flow_control`. The condensed primer below covers
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
# `FlowMode`. `unfold(coord)` returns a list of unfolded positions (≥1);
# `fold(coord)` returns a single folded coordinate.
# `FlowMap.from_qb_sections(flow, qb_sections)` is the entry point for manual
# correction or non-standard interpretations.
#
# This notebook inspects three Choros scores. Each piece's section ends with a
# placeholder for re-defining the flow when the parsed structure needs adjusting.

# %% [markdown]
# ## Setup

# %%
from fractions import Fraction
from pathlib import Path

import pandas as pd

from timetoalign.core.enums import FlowMode
from timetoalign.loader.score import TSVLoader
from timetoalign.timelines.flow import compute_qb_sections

DATA_DIR = Path("~/git/brazilian_flows").expanduser()


def make_paths(name: str, data_dir: Path = DATA_DIR) -> tuple[Path, Path]:
    """Return ``(notes_tsv, measures_tsv)`` paths for a Brazilian Choros score basename."""
    return (
        data_dir / "notes" / f"{name}.notes.tsv",
        data_dir / "measures" / f"{name}.measures.tsv",
    )


def load_controller(name: str):
    """Build a ``FlowController`` from the score's measures TSV."""
    _, measures = make_paths(name)
    return TSVLoader.from_file(measures).create_flow_controller()


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


# %% [markdown]
# ---
#
# ## score_1988-Ciume_e_brincadeira

# %%
controller = load_controller("score_1988-Ciume_e_brincadeira")
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

# %% [markdown]
# **Corrections / re-definition:** _ToDo_.

# %% [markdown]
# ---
#
# ## score_1361-Medrosa-Anacleto_de_Medeiros

# %%
controller = load_controller("score_1361-Medrosa-Anacleto_de_Medeiros")
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

# %% [markdown]
# **Corrections / re-definition:** _ToDo_.

# %% [markdown]
# ---
#
# ## score_133-Digitalis-Irineu_de_Almeida

# %%
controller = load_controller("score_133-Digitalis-Irineu_de_Almeida")
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

# %% [markdown]
# **Corrections / re-definition:** _ToDo_.

# %% [markdown]
# ---
#
# ## Demo: FlowMap and Timeline API
#
# Swap `demo_name` to inspect any of the three pieces above. The cells below
# build a controller, a `FlowMap`, and a timeline with multiple flow maps
# attached, then exercise `unfold` / `fold` / `inverse`.

# %%
demo_name = "score_1988-Ciume_e_brincadeira"  # or score_1361-... / score_133-...

notes_demo, measures_demo = make_paths(demo_name)
loader_demo = TSVLoader.from_file(notes_demo, measures_demo)
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
unfolded = flow_map.unfold(coord)
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
    "n_appearances": len(flow_map.unfold(late_coord)),
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
            "n_appearances": len(score_tl.unfold(sample_coord, id=map_id)),
        }
        for map_id in score_tl.list_flow_maps()
    ]
)

# %%
# Fold a specific unfolded position back to the score.
positions = score_tl.unfold(sample_coord)
if len(positions) > 1:
    folded_back = score_tl.fold(positions[1])
    {"second_unfolded": positions[1], "folded_back": folded_back}
