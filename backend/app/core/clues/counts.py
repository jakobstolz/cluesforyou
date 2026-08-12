"""Tiers 1-2: exact-count constraints over a scope of cells.

One class covers seven player-facing flavors (row/column/name/profession/
global/adjacent/custom-pair counts) since they all share the same
evaluate/CP-SAT/propagate shape - only the scope of cells and how it's
described in text differ.
"""

from __future__ import annotations

from backend.app.core.clues.base import Clue, ContradictionError
from backend.app.core.clues.phrasing import count_clue_text
from backend.app.core.types import Cell, Grid, KnownState, ScopeKind, Solution


class CountConstraintClue(Clue):
    def __init__(
        self,
        scope: list[Cell],
        scope_kind: ScopeKind,
        target: int,
        grid: Grid,
        index=None,
    ):
        self.scope_list: list[Cell] = list(scope)
        self.scope_kind = scope_kind
        self.target = target
        # Meaning of `index` depends on scope_kind: row/col number (int),
        # name/profession (str), the center cell for ADJACENT, or None for
        # GLOBAL/CUSTOM_PAIR (whose text is derived straight from scope_list).
        self.index = index
        n = len(self.scope_list)
        self.tier = 1 if target in (0, n) else 2
        super().__init__(frozenset(self.scope_list), grid)

    def evaluate(self, solution: Solution) -> bool:
        return sum(1 for c in self.scope_list if solution[c]) == self.target

    def add_to_model(self, model, cell_vars) -> None:
        model.Add(sum(cell_vars[c] for c in self.scope_list) == self.target)

    def propagate(self, known: KnownState) -> KnownState:
        unknowns = [c for c in self.scope_list if c not in known]
        known_criminals = sum(1 for c in self.scope_list if known.get(c) is True)
        min_possible = known_criminals
        max_possible = known_criminals + len(unknowns)
        if self.target < min_possible or self.target > max_possible:
            raise ContradictionError(self.id)
        if not unknowns:
            return {}
        needed = self.target - known_criminals
        if needed == 0:
            return {c: False for c in unknowns}
        if needed == len(unknowns):
            return {c: True for c in unknowns}
        return {}

    def render_text(self, grid: Grid) -> str:
        return count_clue_text(self, grid)
