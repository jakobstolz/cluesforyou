"""Tier 0: a straight reveal of one cell's status."""

from __future__ import annotations

import random

from backend.app.core.clues.base import Clue, ContradictionError
from backend.app.core.clues.phrasing import direct_clue_text, neighbor_direct_clue_text
from backend.app.core.types import CELL_MASK, Cell, Grid, Solution, identity_text


class DirectRevealClue(Clue):
    """A straight reveal of one cell's status. Optionally framed through a
    neighbor ("X is one of Y's criminal neighbors") instead of the plain
    phrasing - same fact, same tier, same propagate()/evaluate() logic,
    just different flavor text. This costs nothing extra to combine with
    later: a CountConstraintClue over Y's NEIGHBOR scope already accounts
    for any already-known cell in its scope when it propagates, regardless
    of which clue made that cell known - so revealing X this way is
    "free" setup for a future neighbor-count deduction about Y, without
    needing the pairwise-combination machinery at all."""

    tier = 0

    def __init__(
        self,
        cell: Cell,
        is_criminal: bool,
        grid: Grid,
        neighbor_context: Cell | None = None,
        rng: random.Random | None = None,
    ):
        self.cell = cell
        self.is_criminal = is_criminal
        self.neighbor_context = neighbor_context
        self.scope_order: tuple[Cell, ...] = (cell,)
        super().__init__(frozenset({cell}), grid, rng=rng)

    def evaluate(self, solution: Solution) -> bool:
        return solution[self.cell] == self.is_criminal

    def add_to_model(self, model, cell_vars) -> None:
        model.Add(cell_vars[self.cell] == int(self.is_criminal))

    def propagate_mask(self, known_mask: int, criminal_mask: int) -> tuple[int, int]:
        cell_bit = CELL_MASK[self.cell]
        if known_mask & cell_bit:
            if bool(criminal_mask & cell_bit) != self.is_criminal:
                raise ContradictionError(self.id)
            return 0, 0
        return (cell_bit, cell_bit) if self.is_criminal else (cell_bit, 0)

    def render_text(self, grid: Grid) -> str:
        if self.neighbor_context is not None:
            return neighbor_direct_clue_text(
                identity_text(grid, self.cell),
                identity_text(grid, self.neighbor_context),
                self.is_criminal,
                rng=self._rng,
            )
        return direct_clue_text(identity_text(grid, self.cell), self.is_criminal, rng=self._rng)

    def guaranteed_reveal_cell(self) -> Cell | None:
        return self.cell
