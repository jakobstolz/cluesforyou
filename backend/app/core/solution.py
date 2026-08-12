"""Random hidden-solution generation: which cells are criminals."""

from __future__ import annotations

import random

from backend.app.config import NUM_CELLS
from backend.app.core.types import ALL_CELLS, Solution

# Never let a puzzle be nearly-all-criminal or nearly-all-innocent — both
# make for a degenerate, un-fun deduction target. (Rescaled from 6/19 for
# the previous 25-cell grid to the current 20-cell grid, same ~24%-76% band.)
MIN_CRIMINALS = 5
MAX_CRIMINALS = 15


def random_solution(ratio: float, rng: random.Random | None = None) -> Solution:
    """`ratio` is the target fraction of criminals; the actual count is
    rounded and clamped to [MIN_CRIMINALS, MAX_CRIMINALS]."""
    rng = rng or random.Random()
    n = max(MIN_CRIMINALS, min(MAX_CRIMINALS, round(NUM_CELLS * ratio)))
    criminals = set(rng.sample(ALL_CELLS, n))
    return {cell: (cell in criminals) for cell in ALL_CELLS}
