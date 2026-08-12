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
from backend.app.core.types import Cell, Grid, KnownState, ScopeKind, Solution


class AtLeastOneCriminalClue(Clue):
    tier = 2

    def __init__(
        self, groups: list[list[Cell]], partition_kind: ScopeKind, grid: Grid, rng: random.Random | None = None
    ):
        self.groups: list[list[Cell]] = [list(g) for g in groups]
        self.partition_kind = partition_kind
        all_cells = frozenset(c for g in self.groups for c in g)
        super().__init__(all_cells, grid, rng=rng)

    def evaluate(self, solution: Solution) -> bool:
        return all(any(solution[c] for c in g) for g in self.groups)

    def add_to_model(self, model, cell_vars) -> None:
        for g in self.groups:
            model.Add(sum(cell_vars[c] for c in g) >= 1)

    def propagate(self, known: KnownState) -> KnownState:
        facts: KnownState = {}
        for g in self.groups:
            unknowns = [c for c in g if c not in known]
            known_criminals = sum(1 for c in g if known.get(c) is True)
            if known_criminals == 0 and not unknowns:
                raise ContradictionError(self.id)
            if known_criminals == 0 and len(unknowns) == 1:
                facts[unknowns[0]] = True
        return facts

    def render_text(self, grid: Grid) -> str:
        return group_existence_text(self, grid, rng=self._rng)
