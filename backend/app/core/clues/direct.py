"""Tier 0: a straight reveal of one cell's status."""

from __future__ import annotations

from backend.app.core.clues.base import Clue, ContradictionError
from backend.app.core.clues.phrasing import direct_clue_text
from backend.app.core.types import Cell, Grid, KnownState, Solution, identity_text


class DirectRevealClue(Clue):
    tier = 0

    def __init__(self, cell: Cell, is_criminal: bool, grid: Grid):
        self.cell = cell
        self.is_criminal = is_criminal
        super().__init__(frozenset({cell}), grid)

    def evaluate(self, solution: Solution) -> bool:
        return solution[self.cell] == self.is_criminal

    def add_to_model(self, model, cell_vars) -> None:
        model.Add(cell_vars[self.cell] == int(self.is_criminal))

    def propagate(self, known: KnownState) -> KnownState:
        if self.cell in known:
            if known[self.cell] != self.is_criminal:
                raise ContradictionError(self.id)
            return {}
        return {self.cell: self.is_criminal}

    def render_text(self, grid: Grid) -> str:
        return direct_clue_text(identity_text(grid, self.cell), self.is_criminal)
