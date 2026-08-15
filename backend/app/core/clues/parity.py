"""Tier 2: parity constraints over a scope of cells - "there's an odd/even
number of criminals in X." Same shape as CountConstraintClue, but
strictly weaker in practice: it only ever resolves the *last* remaining
unknown cell in its scope (never a batch), since parity alone says
nothing about individual cells until everything else is already known.
That weakness is deliberate - see the plan doc's "new clue mechanics"
section - a puzzle leaning on parity clues can't be cracked by reading
any single one, only by combining several.
"""

from __future__ import annotations

import random

from backend.app.core.clues.base import Clue, ContradictionError
from backend.app.core.clues.phrasing import parity_clue_text
from backend.app.core.types import Cell, Grid, ScopeKind, Solution


class ParityConstraintClue(Clue):
    tier = 2

    def __init__(
        self,
        scope: list[Cell],
        scope_kind: ScopeKind,
        is_odd: bool,
        grid: Grid,
        index=None,
        rng: random.Random | None = None,
    ):
        self.scope_list: list[Cell] = list(scope)
        self.scope_order: tuple[Cell, ...] = tuple(self.scope_list)
        self.scope_kind = scope_kind
        self.is_odd = is_odd
        self.index = index
        super().__init__(frozenset(self.scope_list), grid, rng=rng)

    def evaluate(self, solution: Solution) -> bool:
        count = sum(1 for c in self.scope_list if solution[c])
        return (count % 2 == 1) == self.is_odd

    def add_to_model(self, model, cell_vars) -> None:
        n = len(self.scope_list)
        target_parity = 1 if self.is_odd else 0
        k = model.NewIntVar(0, n // 2 + 1, f"{self.id}_half")
        model.Add(sum(cell_vars[c] for c in self.scope_list) == 2 * k + target_parity)

    def propagate_mask(self, known_mask: int, criminal_mask: int) -> tuple[int, int]:
        scope_mask = self.scope_mask
        unknown_mask = scope_mask & ~known_mask
        known_criminals = (scope_mask & known_mask & criminal_mask).bit_count()
        target_parity = 1 if self.is_odd else 0

        if unknown_mask == 0:
            if (known_criminals % 2) != target_parity:
                raise ContradictionError(self.id)
            return 0, 0
        if unknown_mask.bit_count() == 1:
            needed_parity = (target_parity - known_criminals) % 2
            return (unknown_mask, unknown_mask) if needed_parity else (unknown_mask, 0)
        return 0, 0

    def render_text(self, grid: Grid) -> str:
        return parity_clue_text(self, grid, rng=self._rng)
