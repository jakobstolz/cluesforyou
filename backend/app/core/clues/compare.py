"""Tier 3: comparison between two same-kind, disjoint groups of cells.

GT/LT propagation is interval bound-tightening: if the ceiling of the
"greater" side is exactly one more than the floor of the "lesser" side,
every remaining unknown in the greater side must be a criminal and every
remaining unknown in the lesser side must be innocent.

EQ ("as many criminal A as criminal B") only propagates in the narrow
case where one side is *fully* known and the other has exactly one
remaining unknown - forcing that unknown to whatever value equalizes the
sums. Like GT/LT, it deliberately doesn't attempt the general case (which
would need case-splitting to solve by hand) - it's included because the
one-side-known pattern is common enough to be useful, and because,
individually weak, it's exactly the kind of clue that only pays off once
combined with several others.
"""

from __future__ import annotations

import random

from backend.app.core.clues.base import Clue, ContradictionError
from backend.app.core.clues.phrasing import compare_clue_text
from backend.app.core.types import Cell, Grid, KnownState, Solution


def _bounds(scope: list[Cell], known: KnownState) -> tuple[int, int, list[Cell]]:
    unknowns = [c for c in scope if c not in known]
    known_criminals = sum(1 for c in scope if known.get(c) is True)
    return known_criminals, known_criminals + len(unknowns), unknowns


class CompareCountClue(Clue):
    tier = 3

    def __init__(
        self,
        scope_a: list[Cell],
        scope_b: list[Cell],
        relation: str,
        label_a: str,
        label_b: str,
        grid: Grid,
        rng: random.Random | None = None,
    ):
        if relation not in ("GT", "LT", "EQ"):
            raise ValueError("relation must be 'GT', 'LT', or 'EQ'")
        self.scope_a = list(scope_a)
        self.scope_b = list(scope_b)
        self.relation = relation
        self.label_a = label_a
        self.label_b = label_b
        super().__init__(frozenset(self.scope_a) | frozenset(self.scope_b), grid, rng=rng)

    def evaluate(self, solution: Solution) -> bool:
        sa = sum(1 for c in self.scope_a if solution[c])
        sb = sum(1 for c in self.scope_b if solution[c])
        if self.relation == "GT":
            return sa > sb
        if self.relation == "LT":
            return sa < sb
        return sa == sb

    def add_to_model(self, model, cell_vars) -> None:
        sa = sum(cell_vars[c] for c in self.scope_a)
        sb = sum(cell_vars[c] for c in self.scope_b)
        if self.relation == "GT":
            model.Add(sa > sb)
        elif self.relation == "LT":
            model.Add(sa < sb)
        else:
            model.Add(sa == sb)

    def _greater_lesser(self) -> tuple[list[Cell], list[Cell]]:
        return (self.scope_a, self.scope_b) if self.relation == "GT" else (self.scope_b, self.scope_a)

    def propagate(self, known: KnownState) -> KnownState:
        if self.relation == "EQ":
            return self._propagate_eq(known)

        greater, lesser = self._greater_lesser()
        min_g, max_g, unk_g = _bounds(greater, known)
        min_l, max_l, unk_l = _bounds(lesser, known)

        if max_g <= min_l:
            raise ContradictionError(self.id)

        facts: KnownState = {}
        if max_g - min_l == 1:
            for c in unk_g:
                facts[c] = True
            for c in unk_l:
                facts[c] = False
        return facts

    def _propagate_eq(self, known: KnownState) -> KnownState:
        min_a, max_a, unk_a = _bounds(self.scope_a, known)
        min_b, max_b, unk_b = _bounds(self.scope_b, known)

        if max_a < min_b or max_b < min_a:
            raise ContradictionError(self.id)

        if min_a == max_a and len(unk_b) == 1:
            needed = min_a - min_b
            if needed not in (0, 1):
                raise ContradictionError(self.id)
            return {unk_b[0]: bool(needed)}
        if min_b == max_b and len(unk_a) == 1:
            needed = min_b - min_a
            if needed not in (0, 1):
                raise ContradictionError(self.id)
            return {unk_a[0]: bool(needed)}
        return {}

    def render_text(self, grid: Grid) -> str:
        return compare_clue_text(self, grid, rng=self._rng)
