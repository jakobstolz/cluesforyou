"""Tiers 1-2: exact-count constraints over a scope of cells.

One class covers seven player-facing flavors (row/column/name/profession/
global/adjacent/custom-pair counts) since they all share the same
evaluate/CP-SAT/propagate shape - only the scope of cells and how it's
described in text differ.
"""

from __future__ import annotations

import random

from backend.app.core.clues.base import Clue, ContradictionError
from backend.app.core.clues.phrasing import count_clue_text, direct_count_clue_text
from backend.app.core.types import Cell, Grid, KnownState, ScopeKind, Solution


class CountConstraintClue(Clue):
    def __init__(
        self,
        scope: list[Cell],
        scope_kind: ScopeKind,
        target: int,
        grid: Grid,
        index=None,
        rng: random.Random | None = None,
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
        super().__init__(frozenset(self.scope_list), grid, rng=rng)

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
        return count_clue_text(self, grid, rng=self._rng)


class DirectCountClue(CountConstraintClue):
    """A CountConstraintClue that ALSO directly reveals one specific member
    of its own scope - "X is one of N criminals {group}" (or the
    neighbor-framed variant, "X is one of Y's N criminal neighbors").
    Genuinely combines two kinds of information in one clue, unlike the
    purely-flavor-text neighbor-framed DirectRevealClue (see direct.py):
    the immediate tier-0 fact about `cell`, AND the group's exact count -
    which stays valuable for later combination reasoning even after
    `cell` itself is known, exactly like any other CountConstraintClue
    (subclassing it, rather than DirectRevealClue, is what makes that
    "for free" - every isinstance(c, CountConstraintClue) check elsewhere,
    e.g. reasoner.py's combination logic, picks this up automatically).
    A great starter/early candidate: gives the player one deduction for
    free immediately while still setting up a future combination
    deduction with the rest of the group - see generator.py's
    _starter_candidate_cells/_sort_key for how generation biases toward
    actually landing it in the first couple of attached clues."""

    def __init__(
        self,
        cell: Cell,
        is_criminal: bool,
        group_scope: list[Cell],
        scope_kind: ScopeKind,
        target: int,
        grid: Grid,
        index=None,
        rng: random.Random | None = None,
    ):
        if cell not in group_scope:
            raise ValueError("cell must be a member of group_scope")
        self.cell = cell
        self.is_criminal = is_criminal
        super().__init__(group_scope, scope_kind, target, grid, index=index, rng=rng)
        # Overrides the tier CountConstraintClue.__init__ just computed
        # (1 or 2, from the group's target alone) - the direct half always
        # fires unconditionally, regardless of what's known, same as
        # DirectRevealClue.
        self.tier = 0

    def evaluate(self, solution: Solution) -> bool:
        return solution[self.cell] == self.is_criminal and super().evaluate(solution)

    def add_to_model(self, model, cell_vars) -> None:
        # Both halves must be enforced, or CP-SAT's uniqueness check would
        # silently under-constrain the model - the sum-equals-target
        # constraint alone doesn't pin `cell` specifically.
        model.Add(cell_vars[self.cell] == int(self.is_criminal))
        super().add_to_model(model, cell_vars)

    def propagate(self, known: KnownState) -> KnownState:
        if self.cell in known:
            if known[self.cell] != self.is_criminal:
                raise ContradictionError(self.id)
            direct_facts: KnownState = {}
        else:
            direct_facts = {self.cell: self.is_criminal}
        # Seed `cell`'s fact into the group-tightening check even if it
        # wasn't already in `known` - so the rest of the group can tighten
        # in the SAME propagate() call the direct reveal happens in, not a
        # round later.
        seeded = dict(known)
        seeded[self.cell] = self.is_criminal
        return {**direct_facts, **super().propagate(seeded)}

    def guaranteed_reveal_cell(self) -> Cell | None:
        return self.cell

    def render_text(self, grid: Grid) -> str:
        return direct_count_clue_text(self, grid, rng=self._rng)
