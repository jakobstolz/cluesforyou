"""Random grid layout generation.

The grid is populated by sampling NUM_CELLS distinct (name, profession)
pairs from the player's roster pool (see core/roster.py) and shuffling
them into the grid. The pool may hold more entries than the grid needs -
a fresh subset is sampled each generation for variety.

The roster itself is allowed to hold two entries that share a first name
(e.g. two different "Jakob"s with different professions) - but a single
generated grid never does. Clue text like "everyone named Jakob" or
"the people named Jakob" would otherwise become ambiguous (which Jakob?),
so sampling dedupes by name, keeping at most one entry per name.
"""

from __future__ import annotations

import random

from backend.app.config import GRID_COLS, GRID_ROWS, NUM_CELLS
from backend.app.core.types import Grid, Person


def random_grid_layout(pool: list[Person], rng: random.Random | None = None) -> Grid:
    rng = rng or random.Random()

    shuffled = list(pool)
    rng.shuffle(shuffled)

    chosen: list[Person] = []
    seen_names: set[str] = set()
    for person in shuffled:
        if person.name in seen_names:
            continue
        seen_names.add(person.name)
        chosen.append(person)
        if len(chosen) == NUM_CELLS:
            break

    if len(chosen) < NUM_CELLS:
        raise ValueError(
            f"Need at least {NUM_CELLS} people with distinct names in the roster, "
            f"have {len(chosen)} distinct names among {len(pool)} entries"
        )

    rng.shuffle(chosen)
    return [[chosen[r * GRID_COLS + c] for c in range(GRID_COLS)] for r in range(GRID_ROWS)]
