# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.2
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# # How to Do Coordinate Math
#
# Domains, TimeUnits, NumberTypes, and type-safe Coordinate arithmetic.

# %%
from fractions import Fraction

import pandas as pd

from timetoalign import Coordinate, Domain, NumberType, TimeUnit

# %% [markdown]
# ## The Three Domains
#
# | Domain | Description | Examples |
# |--------|-------------|----------|
# | **Physical** | Real-world time | Seconds, samples |
# | **Logical** | Symbolic/musical | Beats, quarters, ticks |
# | **Graphical** | Visual/spatial | Pixels, centimetres |

# %%
list(Domain)

# %%
Domain.physical == Domain.ph == Domain("physical") == Domain("ph")

# %% [markdown]
# ## TimeUnits

# %%
unit_data = [
    {"unit": u.name, "domain": u.domain.name, "discrete": u.is_discrete}
    for u in TimeUnit
]
pd.DataFrame(unit_data).sort_values(["domain", "discrete", "unit"])

# %%
# Convenient aliases
aliases = {
    "TimeUnit.s": TimeUnit.seconds,
    "TimeUnit.ms": TimeUnit.milliseconds,
    "TimeUnit.q": TimeUnit.quarters,
    "TimeUnit.b": TimeUnit.beats,
    "TimeUnit.px": TimeUnit.pixels,
    "TimeUnit.pulses": TimeUnit.ticks,
    "TimeUnit.divs": TimeUnit.ticks,
}
pd.Series({k: v.name for k, v in aliases.items()}, name="resolves_to")

# %% [markdown]
# ## NumberType
#
# | Type | Python Type | Use Case |
# |------|-------------|----------|
# | `int` | `int` | Discrete units (samples, ticks) |
# | `float` | `float` | Physical time (seconds) |
# | `fraction` | `Fraction` | Exact rationals (beats, quarters) |

# %%
{
    "from int": NumberType.from_number(42),
    "from float": NumberType.from_number(3.14),
    "from Fraction": NumberType.from_number(Fraction(3, 4)),
}

# %% [markdown]
# ### Why Fractions Matter

# %%
float_sum = sum(0.1 for _ in range(10))
fraction_sum = sum(Fraction(1, 10) for _ in range(10))

{
    "10x float": float_sum,
    "10x float == 1": float_sum == 1,
    "10x fraction": fraction_sum,
    "10x fraction == 1": fraction_sum == 1,
}

# %% [markdown]
# ## Coordinates
#
# Immutable, hashable, type-safe value+unit pairs.

# %%
c1 = Coordinate(120, TimeUnit.ticks)
c2 = Coordinate(1.5, TimeUnit.seconds)
c3 = Coordinate(Fraction(3, 4), TimeUnit.quarters)

c1, c2, c3

# %%
{
    "value": c3.value,
    "unit": c3.unit,
    "number_type": c3.number_type,
    "domain": c3.domain,
}

# %% [markdown]
# ### Arithmetic

# %%
x = Coordinate(10, TimeUnit.seconds)
y = Coordinate(5, TimeUnit.seconds)

{"x > y": x > y, "x == y": x == y, "x <= y": x <= y}

# %%
# Unit mismatch raises TypeError
try:
    Coordinate(480, TimeUnit.ticks) + Coordinate(1.0, TimeUnit.seconds)
except TypeError as e:
    print(f"TypeError: {e}")

# %% [markdown]
# ### Type Conversions

# %%
c = Coordinate(Fraction(7, 4), TimeUnit.quarters)

{
    "original": c,
    "to_float()": c.to_float(),
    "to_int()": c.to_int(),
    "to_int('round')": c.to_int("round"),
    "to_fraction()": c.to_fraction(),
}

# %%
original = Coordinate(100, TimeUnit.ticks)

{
    "original": original,
    "with_value(200)": original.with_value(200),
    "with_unit(samples)": original.with_unit(TimeUnit.samples),
}
