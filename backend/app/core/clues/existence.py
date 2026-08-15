"""A single clue spanning an entire partition of the grid at once: "every
row/column/name/profession has at least one criminal among its members."

This is a genuinely different constraint from CountConstraintClue - an
existential lower bound per group, not an exact count - and it only
forces anything once a group is down to its last unknown cell with zero
criminals found so far. That means it tends to fire *late*, after other
clues have already narrowed several groups down, which is exactly the
"needs to combine with whatever else you know" texture that makes puzzles
feel less linear (see the plan doc).
"""

from __future__ import annotations

import random

from backend.app.core.clues.base import Clue, ContradictionError
from backend.app.core.clues.phrasing import group_existence_text
from backend.app.core.types import Cell, Grid, ScopeKind, Solution, cells_to_mask


class AtLeastOneCriminalClue(Clue):
    tier = 2

    def __init__(
        self, groups: list[list[Cell]], partition_kind: ScopeKind, grid: Grid, rng: random.Random | None = None
    ):
        self.groups: list[list[Cell]] = [list(g) for g in groups]
        self.group_masks: list[int] = [cells_to_mask(g) for g in self.groups]
        self.partition_kind = partition_kind
        # Flattened in group order - each group ever forces at most one
        # cell, so this preserves cross-group ordering for a simultaneous
        # multi-group reveal exactly like the original dict-comprehension
        # (iterating self.groups in order) always did.
        self.scope_order: tuple[Cell, ...] = tuple(c for g in self.groups for c in g)
        all_cells = frozenset(c for g in self.groups for c in g)
        super().__init__(all_cells, grid, rng=rng)

    def evaluate(self, solution: Solution) -> bool:
        return all(any(solution[c] for c in g) for g in self.groups)

    def add_to_model(self, model, cell_vars) -> None:
        for g in self.groups:
            model.Add(sum(cell_vars[c] for c in g) >= 1)

    def propagate_mask(self, known_mask: int, criminal_mask: int) -> tuple[int, int]:
        new_known_mask = 0
        for group_mask in self.group_masks:
            unknown_mask = group_mask & ~known_mask
            known_criminals = (group_mask & known_mask & criminal_mask).bit_count()
            if known_criminals == 0 and unknown_mask == 0:
                raise ContradictionError(self.id)
            if known_criminals == 0 and unknown_mask.bit_count() == 1:
                new_known_mask |= unknown_mask
        # Every forced cell here is forced to True (a group's last unknown
        # once it has zero known criminals so far) - new_criminal_mask is
        # identical to new_known_mask.
        return new_known_mask, new_known_mask

    def render_text(self, grid: Grid) -> str:
        return group_existence_text(self, grid, rng=self._rng)
