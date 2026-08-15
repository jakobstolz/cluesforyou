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
from backend.app.core.types import Cell, Grid, Solution, cells_to_mask


def _bounds_mask(group_mask: int, known_mask: int, criminal_mask: int) -> tuple[int, int, int]:
    """(known_criminals, max_possible_criminals, unknown_mask) for one
    side of the comparison - bitmask equivalent of the old dict-based
    _bounds()."""
    unknown_mask = group_mask & ~known_mask
    known_criminals = (group_mask & known_mask & criminal_mask).bit_count()
    return known_criminals, known_criminals + unknown_mask.bit_count(), unknown_mask


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
        self.scope_a_mask = cells_to_mask(self.scope_a)
        self.scope_b_mask = cells_to_mask(self.scope_b)
        # Matches _greater_lesser()'s "greater side" ordering (GT: a is
        # greater; LT: b is greater), so a simultaneous GT/LT reveal
        # returns cells in the exact order the original propagate() dict-
        # comprehension always did (greater side's forced-True cells,
        # then lesser side's forced-False cells) - see Clue.propagate()'s
        # docstring on why this matters for seed->puzzle reproducibility.
        # EQ never forces more than one cell at once, so either order is
        # fine there.
        self.scope_order = (
            tuple(self.scope_b) + tuple(self.scope_a) if relation == "LT" else tuple(self.scope_a) + tuple(self.scope_b)
        )
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

    def _greater_lesser_masks(self) -> tuple[int, int]:
        return (self.scope_a_mask, self.scope_b_mask) if self.relation == "GT" else (self.scope_b_mask, self.scope_a_mask)

    def propagate_mask(self, known_mask: int, criminal_mask: int) -> tuple[int, int]:
        if self.relation == "EQ":
            return self._propagate_eq_mask(known_mask, criminal_mask)

        greater_mask, lesser_mask = self._greater_lesser_masks()
        min_g, max_g, unk_g = _bounds_mask(greater_mask, known_mask, criminal_mask)
        min_l, max_l, unk_l = _bounds_mask(lesser_mask, known_mask, criminal_mask)

        if max_g <= min_l:
            raise ContradictionError(self.id)

        if max_g - min_l == 1:
            # greater side's unknowns all forced True, lesser side's all
            # forced False - unk_g/unk_l are disjoint (scope_a/scope_b are
            # documented as disjoint groups), so OR-ing them is safe.
            return unk_g | unk_l, unk_g
        return 0, 0

    def _propagate_eq_mask(self, known_mask: int, criminal_mask: int) -> tuple[int, int]:
        min_a, max_a, unk_a = _bounds_mask(self.scope_a_mask, known_mask, criminal_mask)
        min_b, max_b, unk_b = _bounds_mask(self.scope_b_mask, known_mask, criminal_mask)

        if max_a < min_b or max_b < min_a:
            raise ContradictionError(self.id)

        if min_a == max_a and unk_b.bit_count() == 1:
            needed = min_a - min_b
            if needed not in (0, 1):
                raise ContradictionError(self.id)
            return (unk_b, unk_b) if needed else (unk_b, 0)
        if min_b == max_b and unk_a.bit_count() == 1:
            needed = min_b - min_a
            if needed not in (0, 1):
                raise ContradictionError(self.id)
            return (unk_a, unk_a) if needed else (unk_a, 0)
        return 0, 0

    def render_text(self, grid: Grid) -> str:
        return compare_clue_text(self, grid, rng=self._rng)
